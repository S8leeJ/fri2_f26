"""Publish the newest audio and vision messages together on /social_context.

Subscribes to /audio_context and /hri/vision/context, keeps the newest message
from each, and publishes both in one JSON message, 10 times each second:

    {"t": 1791447072.3,
     "audio": {...the newest /audio_context message...},  "audio_age_s": 0.4,
     "vision": {...the newest /hri/vision/context message...}, "vision_age_s": 0.1}

The audio and vision messages are copied without change. A source that has
not sent anything yet is null. The ages show how old each copy is, so a
frozen node shows as a growing age.

Start the audio node and the vision pipeline first, then:

    python3 fusion/fusion_publisher.py
"""

import json
import time

import rclpy
from std_msgs.msg import String

RATE_HZ = 10.0


def main():
    rclpy.init()
    node = rclpy.create_node("fusion_publisher")
    log = node.get_logger()
    latest = {"audio": (None, None), "vision": (None, None)}
    pub = node.create_publisher(String, "/social_context", 10)

    def keep(name):
        def callback(msg):
            try:
                latest[name] = (json.loads(msg.data), time.time())
            except json.JSONDecodeError:
                log.warn(f"{name}: message is not JSON", throttle_duration_sec=5.0)
        return callback

    def publish():
        now = time.time()
        out = {"t": now}
        for name, (data, received) in latest.items():
            out[name] = data
            out[f"{name}_age_s"] = None if received is None else round(now - received, 2)
        pub.publish(String(data=json.dumps(out)))

    node.create_subscription(String, "/audio_context", keep("audio"), 10)
    node.create_subscription(String, "/hri/vision/context", keep("vision"), 10)
    node.create_timer(1.0 / RATE_HZ, publish)
    log.info(f"publishing /social_context at {RATE_HZ:.0f} Hz")

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
