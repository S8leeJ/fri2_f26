"""Local API for the playground UI. Wraps the MVP; it does not change how it decides.

    uvicorn server:app --port 8000

Keys stay in ../mvp/.env and never leave this process. Bind to 127.0.0.1 only.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from typing import Any, Dict, Optional

import dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

MVP = pathlib.Path(__file__).resolve().parent.parent / "mvp"
sys.path.insert(0, str(MVP))

from context import SCHEMA_PATH, validate  # noqa: E402
from mvp import (  # noqa: E402
    DEFAULT_MODEL,
    ENV_KEY,
    PACING,
    VIGNETTES,
    decide,
    is_timeout,
    load_vignettes,
    make_client,
)
from postfilter import SPEAKS, enforce  # noqa: E402

dotenv.load_dotenv(MVP / ".env")

# Fastest working key first, so it is the default in the picker.
PROVIDER_ORDER = ("groq", "gemini", "anthropic", "jev")
TIMEOUT_S = 15.0
# Groq's free tier allows about 4 turns a minute. One retry after a 429
# turns a burst of clicks into a short wait instead of an error.
PACING["busy_retries"] = 1

app = FastAPI(title="Read the Room playground")
_clients: Dict[str, Any] = {}


def _client(provider: str):
    if provider not in _clients:
        _clients[provider] = make_client(provider, TIMEOUT_S)
    return _clients[provider]


class Turn(BaseModel):
    provider: str
    model: Optional[str] = None
    context: Dict[str, Any]


class NewVignette(BaseModel):
    context: Dict[str, Any]
    note: str = ""


@app.get("/api/providers")
def providers():
    return [{"name": p, "model": DEFAULT_MODEL[p]}
            for p in PROVIDER_ORDER if os.environ.get(ENV_KEY[p])]


@app.get("/api/presets")
def presets():
    return [{"id": v["file"], "expect": v.get("expect"), "note": v.get("note", ""),
             "context": v["context"]} for v in load_vignettes()]


@app.get("/api/schema")
def schema():
    return json.loads(SCHEMA_PATH.read_text())


@app.post("/api/turn")
def turn(req: Turn):
    if req.provider not in DEFAULT_MODEL or not os.environ.get(ENV_KEY[req.provider]):
        raise HTTPException(400, "provider %s has no key in mvp/.env" % req.provider)
    ctx = req.context
    try:
        validate(ctx)
    except ValueError as e:
        raise HTTPException(422, str(e))

    # The gate skips the model when nobody is there, so the playground does too.
    if ctx.get("target") is None:
        return {"action_raw": None, "action_final": "remain_silent", "blocked_by": "no_person",
                "decision": None, "speech": None, "speech_error": None,
                "ms1": None, "ms2": None, "model": None}

    model = req.model or DEFAULT_MODEL[req.provider]
    try:
        r = decide(req.provider, _client(req.provider), model, ctx, 6)
    except Exception as e:  # noqa: BLE001 - shown to the user, not swallowed
        msg = "TIMEOUT" if is_timeout(e) else str(e)[:300] or type(e).__name__
        raise HTTPException(502, "%s call failed: %s" % (req.provider, msg))

    final, blocked_by = enforce(ctx, r.action)
    # A line for an action the post-filter blocked is never said.
    speech = r.speech.model_dump() if r.speech and final in SPEAKS else None
    return {"action_raw": r.action, "action_final": final, "blocked_by": blocked_by,
            "decision": r.decision, "speech": speech, "speech_error": r.speech_error,
            "ms1": r.ms1, "ms2": r.ms2, "model": model}


@app.post("/api/vignettes")
def save_vignette(req: NewVignette):
    try:
        validate(req.context)
    except ValueError as e:
        raise HTTPException(422, str(e))
    used = [int(m.group(1)) for f in VIGNETTES.glob("*.json")
            if (m := re.match(r"(\d+)_", f.name))]
    num = "%03d" % (max(used, default=0) + 1)
    slug = re.sub(r"[^a-z0-9]+", "_", req.note.lower()).strip("_")[:40] or "scene"
    path = VIGNETTES / ("%s_playground_%s.json" % (num, slug))
    body = {"id": num, "expect": None,
            "note": req.note or "Saved from the playground. Needs a label.",
            "context": req.context}
    with open(path, "x") as f:
        f.write(json.dumps(body, indent=2) + "\n")
    return {"file": path.name}
