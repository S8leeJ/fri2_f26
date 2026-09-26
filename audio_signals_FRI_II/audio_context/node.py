# Goal: put the audio pipeline on ROS. This is what runs on the robot;
# main.py is the same two loops printing to a terminal instead, kept for
# testing on a machine with no ROS.
#
#   ros2 run audio_context node
#   ros2 topic echo /audio_context
#
# No audio logic lives here. Nothing else in the package imports rclpy,
# which is why the rest of the pipeline runs on a laptop.
#
# Topics:
#   out  /audio_context   std_msgs/String   the JSON, once a second
#   in   /engaged         std_msgs/Bool     gates transcription
#   in   /robot_speaking  std_msgs/Bool     audio is discarded while true
#
# The published object is exactly what audio_builder produces. Matching the
# team's schema is a separate conversation: noise_floor_db here is dBFS,
# relative to what the microphone can record, while SCHEMA.md asks for the
# sound pressure scale, and relating the two needs a measurement nobody has
# taken yet.

import json
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

from audio_context import state
from audio_context.audio_builder import Builder
from audio_context.config import CONFIG, check
from audio_context.processor import Processor


class AudioContextNode(Node):

    def __init__(self):
        super().__init__("audio_context")

        # Topic names as parameters, so they can be remapped at launch
        # without editing this file.
        self.declare_parameter("out_topic", "/audio_context")
        self.declare_parameter("engaged_topic", "/engaged")
        self.declare_parameter("speaking_topic", "/robot_speaking")
        out = self.get_parameter("out_topic").value
        eng = self.get_parameter("engaged_topic").value
        spk = self.get_parameter("speaking_topic").value

        # Settings that are wrong but would not crash.
        for problem in check():
            self.get_logger().error(f"config: {problem}")

        self.proc = Processor(CONFIG)
        self.builder = Builder(CONFIG, self.proc.buffer, self.proc.utterance,
                               self.proc.counters, self.proc.stt)

        self.pub = self.create_publisher(String, out, 10)
        self.create_subscription(Bool, eng, self._on_engaged, 10)
        self.create_subscription(Bool, spk, self._on_speaking, 10)

        # Capture runs at about 8 blocks a second on its own thread, while
        # the timer publishes once a second. Keeping them apart means a slow
        # build never stalls the microphone.
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._capture, daemon=True)
        self._thread.start()

        self.create_timer(CONFIG["window_sec"], self._publish)
        self.get_logger().info(f"publishing {out} every "
                               f"{CONFIG['window_sec']:.0f}s")

    # -- subscribers -------------------------------------------------------

    # Both log only on a change. `ros2 topic pub` republishes about once a
    # second and the real nodes will too, so logging every message would
    # bury everything else in the terminal.

    def _on_engaged(self, msg):
        if msg.data == state.engaged():
            return
        state.set_engaged(msg.data)
        if not msg.data:
            # Drop the old text, or it would linger into whatever
            # interaction comes next.
            self.proc.stt.clear()
        self.get_logger().info(f"engaged = {msg.data}")

    def _on_speaking(self, msg):
        # Compare before setting, or it can never look changed.
        if msg.data != state.robot_speaking():
            self.get_logger().info(f"robot_speaking = {msg.data}")
        state.set_robot_speaking(msg.data)

    # -- the two loops -----------------------------------------------------

    def _capture(self):
        # Drain the stream. Checking the flag each block lets this return
        # normally on shutdown, so the microphone is closed properly.
        try:
            for _ in self.proc.split():
                if self._stopping.is_set():
                    return
        except Exception as e:
            self.get_logger().error(f"capture stopped: {e}")

    def _publish(self):
        try:
            self.pub.publish(String(data=json.dumps(self.builder.build())))
        except Exception as e:
            # One bad build should not take the node down, or the robot
            # loses its ears for the rest of the run.
            self.get_logger().error(f"build failed: {e}")

    def shutdown(self):
        self._stopping.set()
        self._thread.join(timeout=2.0)
        self.proc.stt.stop()


def main(args=None):
    rclpy.init(args=args)
    node = AudioContextNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()