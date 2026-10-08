"""Show the camera image with a box around each tracked person.

Each label shows the track ID, distance, direction, and orientation.
Start it with scripts/view.sh. Stop it with Ctrl+C in its terminal.
"""

import json

import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

GREEN = (0, 255, 0)


class BoxViewer(Node):
    def __init__(self):
        super().__init__("box_viewer")
        self.bridge = CvBridge()
        self.people = []
        self.orientation = {}
        self.create_subscription(String, "/hri/vision/person_context", self._on_people, 10)
        self.create_subscription(String, "/hri/vision/orientation", self._on_orientation, 10)
        self.create_subscription(Image, "/rgb/image_raw", self._on_image, 10)

    def _on_people(self, msg):
        self.people = json.loads(msg.data).get("people", [])

    def _on_orientation(self, msg):
        people = json.loads(msg.data).get("people", [])
        self.orientation = {p["id"]: p.get("orientation", "unknown") for p in people}

    def _on_image(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        for p in self.people:
            x1, y1, x2, y2 = map(int, p["bbox"])
            distance = p.get("distance_m")
            label = (f"id {p['id']}  {distance if distance is not None else '?'} m  "
                     f"{p.get('direction')}  {self.orientation.get(p['id'], '')}")
            cv2.rectangle(frame, (x1, y1), (x2, y2), GREEN, 2)
            cv2.putText(frame, label, (x1, max(20, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, GREEN, 2)
        cv2.imshow("people", frame)
        cv2.waitKey(1)


def main():
    rclpy.init()
    node = BoxViewer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
