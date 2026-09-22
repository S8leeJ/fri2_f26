import json
import time

import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .common import clamp_box, safe_json_loads


class OrientationNode(Node):
    """
    Coarse per-person orientation estimator.

    It runs MediaPipe Pose and Face Detection on each tracked person's crop.
    Face visible + broad shoulders -> likely facing robot.
    Narrow shoulder projection -> sideways.
    Broad shoulders with no face -> likely facing away.

    This is intentionally a coarse HRI signal, not an eye-gaze estimator.
    """

    def __init__(self):
        super().__init__("orientation_node")

        self.declare_parameter("image_topic", "/camera/color/image_raw")
        self.declare_parameter("detections_topic", "/hri/vision/detections")
        self.declare_parameter("output_topic", "/hri/vision/orientation")
        self.declare_parameter("max_rate_hz", 5.0)
        self.declare_parameter("min_pose_detection_confidence", 0.45)
        self.declare_parameter("min_face_detection_confidence", 0.45)
        self.declare_parameter("sideways_shoulder_ratio", 0.55)
        self.declare_parameter("min_visibility", 0.45)

        try:
            import mediapipe as mp
        except ImportError as exc:
            raise RuntimeError(
                "MediaPipe is not installed. Run: pip install mediapipe"
            ) from exc

        self.mp = mp
        self.bridge = CvBridge()
        self.latest_bgr = None
        self.last_processed_monotonic = 0.0

        # Legacy MediaPipe Solutions API is deliberately used here because it
        # requires no external .task model file and is easy to deploy offline.
        self.pose = mp.solutions.pose.Pose(
            static_image_mode=True,
            model_complexity=0,
            enable_segmentation=False,
            min_detection_confidence=float(
                self.get_parameter("min_pose_detection_confidence").value
            ),
        )
        self.face_detector = mp.solutions.face_detection.FaceDetection(
            model_selection=0,
            min_detection_confidence=float(
                self.get_parameter("min_face_detection_confidence").value
            ),
        )

        self.image_sub = self.create_subscription(
            Image, str(self.get_parameter("image_topic").value), self._on_image, 10
        )
        self.detection_sub = self.create_subscription(
            String,
            str(self.get_parameter("detections_topic").value),
            self._on_detections,
            10,
        )
        self.publisher = self.create_publisher(
            String, str(self.get_parameter("output_topic").value), 10
        )

        self.get_logger().info(
            "Orientation ready: MediaPipe Pose + Face Detection on tracked person crops"
        )

    def _on_image(self, msg: Image):
        try:
            self.latest_bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as exc:
            self.get_logger().error(f"RGB conversion failed: {exc}")

    def _on_detections(self, msg: String):
        if self.latest_bgr is None:
            return

        max_rate = float(self.get_parameter("max_rate_hz").value)
        now = time.monotonic()
        if max_rate > 0 and now - self.last_processed_monotonic < 1.0 / max_rate:
            return
        self.last_processed_monotonic = now

        data = safe_json_loads(msg.data)
        if data is None:
            return

        h, w = self.latest_bgr.shape[:2]
        results = []

        for person in data.get("people", []):
            try:
                track_id = int(person["id"])
                box = clamp_box(person["bbox"], w, h)
            except (KeyError, TypeError, ValueError):
                continue

            if box is None:
                continue

            x1, y1, x2, y2 = box
            crop = self.latest_bgr[y1:y2, x1:x2]
            if crop.size == 0:
                continue

            # Upscale tiny crops; MediaPipe is much more stable above ~200 px.
            crop_h, crop_w = crop.shape[:2]
            scale = max(1.0, 240.0 / max(1, crop_h))
            if scale > 1.0:
                crop = cv2.resize(
                    crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR
                )

            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

            pose_result = self.pose.process(rgb)
            face_result = self.face_detector.process(rgb)
            face_visible = bool(face_result.detections)

            body_orientation = "unknown"
            shoulder_ratio = None

            if pose_result.pose_landmarks:
                lm = pose_result.pose_landmarks.landmark
                left_shoulder = lm[11]
                right_shoulder = lm[12]
                left_hip = lm[23]
                right_hip = lm[24]

                min_vis = float(self.get_parameter("min_visibility").value)
                visible = (
                    left_shoulder.visibility >= min_vis
                    and right_shoulder.visibility >= min_vis
                    and left_hip.visibility >= min_vis
                    and right_hip.visibility >= min_vis
                )

                if visible:
                    shoulder_width = abs(left_shoulder.x - right_shoulder.x)
                    shoulder_mid_y = (left_shoulder.y + right_shoulder.y) / 2.0
                    hip_mid_y = (left_hip.y + right_hip.y) / 2.0
                    torso_height = max(abs(hip_mid_y - shoulder_mid_y), 1e-3)
                    shoulder_ratio = shoulder_width / torso_height

                    sideways_threshold = float(
                        self.get_parameter("sideways_shoulder_ratio").value
                    )
                    if shoulder_ratio < sideways_threshold:
                        body_orientation = "sideways"
                    else:
                        body_orientation = "front_or_back"

            if body_orientation == "sideways":
                orientation = "sideways"
            elif face_visible:
                # Face detection is a practical proxy for "facing toward robot."
                orientation = "facing_robot"
            elif body_orientation == "front_or_back":
                orientation = "likely_facing_away"
            else:
                orientation = "unknown"

            results.append(
                {
                    "id": track_id,
                    "orientation": orientation,
                    "body_orientation": body_orientation,
                    "face_visible": face_visible,
                    "shoulder_ratio": (
                        round(float(shoulder_ratio), 3)
                        if shoulder_ratio is not None
                        else None
                    ),
                    # Coarse gaze proxy. Fine eye-gaze can replace this later.
                    "gaze": "toward_robot" if face_visible else "unknown",
                }
            )

        payload = {
            "stamp": data.get("stamp"),
            "people": results,
        }
        out = String()
        out.data = json.dumps(payload, separators=(",", ":"))
        self.publisher.publish(out)

    def destroy_node(self):
        try:
            self.pose.close()
            self.face_detector.close()
        except Exception:
            pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = OrientationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
