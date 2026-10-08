"""Fuse the audio and vision topics into one /social_context message.

Subscribes to /audio_context and /hri/vision/context, keeps the newest message
from each, and publishes a schema v2.0 context on /social_context, 10 times
each second by default. Start the audio node, the Kinect driver, and the vision
pipeline first, then:

    python3 conversation_initiator/ros/fusion_node.py

The vision people map to the schema like this:

    nearest person with a distance  -> target
    other people with a distance    -> bystanders
    orientation == "facing_robot"   -> facing_robot (unknown becomes false)
    direction                       -> motion (receding becomes leaving)
    dwell_time_s                    -> dwell_s
    face visible without a break    -> gaze_at_robot_s

People without a distance are left out, because the schema requires
distance_m for the target and for each bystander.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mvp"))
from context import audio_to_context, validate  # noqa: E402

MOTION = {"approaching": "approaching", "receding": "leaving", "stationary": "stationary"}


def update_gaze(since, people, now):
    """Seconds that each person's face has been visible without a break.

    since maps id -> time the face appeared, and is updated in place.
    Returns id -> seconds, 0.0 when no face is visible, or None when not measured.
    """
    gaze = {}
    for p in people:
        pid = p.get("id")
        face = p.get("face_visible")
        if face is True:
            since.setdefault(pid, now)
            gaze[pid] = now - since[pid]
        else:
            since.pop(pid, None)
            gaze[pid] = 0.0 if face is False else None
    for pid in list(since):
        if pid not in gaze:
            del since[pid]
    return gaze


def to_target(person, gaze_s):
    target = {
        "distance_m": person["distance_m"],
        "facing_robot": person.get("orientation") == "facing_robot",
    }
    motion = MOTION.get(person.get("direction"))
    if motion:
        target["motion"] = motion
    if person.get("dwell_time_s") is not None:
        target["dwell_s"] = person["dwell_time_s"]
    if gaze_s is not None:
        target["gaze_at_robot_s"] = round(gaze_s, 1)
    return target


def build_context(audio, vision, gaze_since, now):
    """One schema v2.0 context from the newest audio and vision messages.

    Raises ValueError if the result does not match the schema.
    """
    people = vision.get("people", [])
    gaze = update_gaze(gaze_since, people, now)
    measured = sorted((p for p in people if p.get("distance_m") is not None),
                      key=lambda p: p["distance_m"])

    target = to_target(measured[0], gaze.get(measured[0].get("id"))) if measured else None
    bystanders = [
        {"distance_m": p["distance_m"], "facing_robot": p.get("orientation") == "facing_robot"}
        for p in measured[1:]
    ]

    ctx = audio_to_context(audio, target=target, bystanders=bystanders)
    validate(ctx, "social_context")
    return ctx


def main():
    import rclpy
    from std_msgs.msg import String

    rclpy.init()
    node = rclpy.create_node("fusion_node")
    log = node.get_logger()
    rate_hz = node.declare_parameter("rate_hz", 10.0).value
    # The audio node publishes once each second, so it gets a longer limit.
    audio_max_age = node.declare_parameter("audio_max_age_s", 3.0).value
    vision_max_age = node.declare_parameter("vision_max_age_s", 1.0).value

    latest = {"audio": (None, 0.0), "vision": (None, 0.0)}
    gaze_since = {}
    pub = node.create_publisher(String, "/social_context", 10)

    def keep(name):
        def callback(msg):
            try:
                latest[name] = (json.loads(msg.data), time.time())
            except json.JSONDecodeError:
                log.warn(f"{name}: message is not JSON", throttle_duration_sec=5.0)
        return callback

    def tick():
        now = time.time()
        (audio, audio_t), (vision, vision_t) = latest["audio"], latest["vision"]
        if audio is None or vision is None:
            log.info("waiting for /audio_context and /hri/vision/context", throttle_duration_sec=5.0)
            return
        # Old data would look current, and a frozen vision node would look
        # like an empty room. Publishing nothing is safer.
        if now - audio_t > audio_max_age or now - vision_t > vision_max_age:
            log.warn(f"not publishing: audio is {now - audio_t:.1f} s old, "
                     f"vision is {now - vision_t:.1f} s old", throttle_duration_sec=2.0)
            return
        try:
            ctx = build_context(audio, vision, gaze_since, now)
        except ValueError as e:
            log.warn(str(e), throttle_duration_sec=2.0)
            return
        pub.publish(String(data=json.dumps(ctx)))

        t = ctx["target"]
        who = (f"target {t['distance_m']:.2f} m, facing {t['facing_robot']}" if t else "no target")
        log.info(f"/social_context at {rate_hz:.0f} Hz | {who} | "
                 f"{len(ctx['bystanders'])} bystanders | noise {ctx['ambient']['noise_level']} | "
                 f"engaged {ctx['robot']['engaged']}", throttle_duration_sec=1.0)

    node.create_subscription(String, "/audio_context", keep("audio"), 10)
    node.create_subscription(String, "/hri/vision/context", keep("vision"), 10)
    node.create_timer(1.0 / rate_hz, tick)
    log.info(f"publishing /social_context at {rate_hz:.0f} Hz")
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
