"""Speech enums to Azure SSML. The model never writes SSML.

    from prosody import to_ssml

    ssml = to_ssml(speech)    # any object with text, volume, rate, pitch
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

DEFAULT_VOICE = "en-US-JennyNeural"

# Azure accepts these SSML prosody values as they are.
VOLUMES = ("x-soft", "soft", "medium", "loud")
RATES = ("slow", "medium", "fast")
PITCHES = ("low", "medium", "high")


def to_ssml(speech, voice: str = DEFAULT_VOICE) -> str:
    for value, allowed in ((speech.volume, VOLUMES), (speech.rate, RATES),
                           (speech.pitch, PITCHES)):
        if value not in allowed:
            raise ValueError("%r is not one of %s" % (value, allowed))
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        "<voice name=%s>"
        '<prosody volume="%s" rate="%s" pitch="%s">%s</prosody>'
        "</voice></speak>"
        % (quoteattr(voice), speech.volume, speech.rate, speech.pitch, escape(speech.text))
    )
