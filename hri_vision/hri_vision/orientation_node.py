import json
import os
import time

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .common import (clamp_box, face_to_camera_deg, gaze_from_head_angle, gaze_label, head_turn,
                     safe_json_loads, square_crop,
                     torso_to_camera_deg)

# scripts/setup_flexo.sh and scripts/run_pipeline.sh download it here.
DEFAULT_FACE_LANDMARKER = "~/.cache/hri_vision/face_landmarker.task"


class OrientationNode(Node):
    """
    Coarse per-person orientation estimator.

    It runs MediaPipe Pose and Face Detection on each tracked person's crop.
    Face visible + broad shoulders -> likely facing robot.
    Narrow shoulder projection -> sideways.
    Broad shoulders with no face -> likely facing away.

    Gaze comes from the head, not the eyes: a visible face that is turned to the
    side or tilted down, for example at a phone, is "away".

    For the rule-based baseline it also gives two angles from MediaPipe's 3D output:
    head_angle_deg (Face Landmarker head pose) and body_angle_deg (Pose world
    landmarks of the shoulders). Each is the angle between where the head or torso
    points and the line to the camera.
    """

    def __init__(self):
        super().__init__("orientation_node")

        self.declare_parameter("image_topic", "/camera/color/image_raw")
        self.declare_parameter("detections_topic", "/hri/vision/detections")
        self.declare_parameter("output_topic", "/hri/vision/orientation")
        self.declare_parameter("max_rate_hz", 5.0)
        self.declare_parameter("min_pose_detection_confidence", 0.45)
        self.declare_parameter("min_face_detection_confidence", 0.45)
        # 0: MediaPipe's short-range face model, about 2 m. 1: full-range, about 5 m.
        self.declare_parameter("face_model_selection", 0)
        self.declare_parameter("sideways_shoulder_ratio", 0.55)
        self.declare_parameter("min_visibility", 0.45)
        # Head limits for gaze, from common.head_turn. 0 turns a check off.
        # Not measured on the robot yet: see CALIBRATION.md.
        self.declare_parameter("gaze_max_yaw_ratio", 0.25)
        self.declare_parameter("gaze_max_pitch_ratio", 0.70)
        # Gaze from the Face Landmarker head angle, used when the model loads. On flexo
        # (Nov 20, 2026, 1.35 m): looking at the camera 1-8 deg, looking down at a
        # watch 34-43 deg. The ratio limits above could not tell these two apart.
        self.declare_parameter("gaze_max_head_angle_deg", 25.0)
        self.declare_parameter("face_landmarker_model", DEFAULT_FACE_LANDMARKER)
        # The face crop for Face Landmarker is this many face-box sizes wide.
        self.declare_parameter("face_crop_scale", 2.0)

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
            model_selection=int(self.get_parameter("face_model_selection").value),
            min_detection_confidence=float(
                self.get_parameter("min_face_detection_confidence").value
            ),
        )

        try:
            self.face_landmarker = self._make_face_landmarker(mp)
        except Exception as exc:  # noqa: BLE001 - the other fields must keep working
            self.get_logger().error(f"Face Landmarker did not start, head_angle_deg stays empty: {exc}")
            self.face_landmarker = None
        self.angle_error_logged = False

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

    def _make_face_landmarker(self, mp):
        path = os.path.expanduser(str(self.get_parameter("face_landmarker_model").value))
        if not os.path.isfile(path):
            self.get_logger().error(
                f"No Face Landmarker model at {path}: head_angle_deg stays empty. "
                "Run scripts/setup_flexo.sh or scripts/run_pipeline.sh, which download it."
            )
            return None
        from mediapipe.tasks import python as mp_tasks
        from mediapipe.tasks.python import vision as mp_vision

        options = mp_vision.FaceLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=path),
            running_mode=mp_vision.RunningMode.IMAGE,
            num_faces=1,
            output_facial_transformation_matrixes=True,
        )
        return mp_vision.FaceLandmarker.create_from_options(options)

    def _head_angle(self, detections, frame_bgr, person_box):
        """Face Landmarker on a square crop centered on the face, so the crop looks along
        the line to the face, and the head pose is measured from that line.

        The face box is relative to the person crop. The face crop is cut from the whole
        frame, so a narrow person box (a person side on) does not cut it short.
        """
        if self.face_landmarker is None:
            return None
        box = max(detections, key=lambda d: d.score[0]).location_data.relative_bounding_box
        x1, y1, x2, y2 = person_box
        pw, ph = x2 - x1, y2 - y1
        cx = x1 + (box.xmin + box.width / 2.0) * pw
        cy = y1 + (box.ymin + box.height / 2.0) * ph
        half = float(self.get_parameter("face_crop_scale").value) * max(box.width * pw, box.height * ph) / 2.0
        face = square_crop(frame_bgr, cx, cy, half)
        if face is None:
            return None
        face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
        if face.shape[0] < 256:
            scale = 256.0 / face.shape[0]
            face = cv2.resize(face, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(face))
        result = self.face_landmarker.detect(image)
        if not result.facial_transformation_matrixes:
            return None
        return face_to_camera_deg(result.facial_transformation_matrixes[0])

    def _body_angle(self, pose_result):
        world = pose_result.pose_world_landmarks
        if not world:
            return None
        left, right = world.landmark[11], world.landmark[12]
        min_vis = float(self.get_parameter("min_visibility").value)
        if left.visibility < min_vis or right.visibility < min_vis:
            return None
        return torso_to_camera_deg((left.x, left.y, left.z), (right.x, right.y, right.z))

    def _gaze(self, face_visible, turn, head_angle):
        """Gaze for Jev's scene: from the Face Landmarker head angle when the model
        is loaded, else from the face-point ratios."""
        if self.face_landmarker is not None:
            return gaze_from_head_angle(
                face_visible, head_angle, float(self.get_parameter("gaze_max_head_angle_deg").value))
        return gaze_label(face_visible, turn,
                          float(self.get_parameter("gaze_max_yaw_ratio").value),
                          float(self.get_parameter("gaze_max_pitch_ratio").value))

    def _baseline_angles(self, face_result, pose_result, frame_bgr, person_box, face_visible):
        """(head_angle_deg, body_angle_deg) for the baseline. A failure here leaves them
        empty and never stops the fields that Jev uses."""
        try:
            head = (self._head_angle(face_result.detections, frame_bgr, person_box)
                    if face_visible else None)
            return head, self._body_angle(pose_result)
        except Exception as exc:  # noqa: BLE001
            if not self.angle_error_logged:
                self.get_logger().error(f"Baseline angles failed, left empty: {exc}")
                self.angle_error_logged = True
            return None, None

    def _on_image(self, msg: Image):
        try:
            self.latest_bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as exc:
            self.get_logger().error(f"RGB conversion failed: {exc}")

    def _head_turn(self, detections, rgb):
        # A crop can hold a second face, for example a person behind. Use the surest one.
        face = max(detections, key=lambda d: d.score[0])
        fd = self.mp.solutions.face_detection
        h, w = rgb.shape[:2]
        points = []
        for key in (fd.FaceKeyPoint.RIGHT_EYE, fd.FaceKeyPoint.LEFT_EYE,
                    fd.FaceKeyPoint.NOSE_TIP, fd.FaceKeyPoint.MOUTH_CENTER):
            p = fd.get_key_point(face, key)
            if p is None:
                return None
            points.append((p.x * w, p.y * h))
        return head_turn(*points)

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
            turn = self._head_turn(face_result.detections, rgb) if face_visible else None
            head_angle, body_angle = self._baseline_angles(face_result, pose_result, self.latest_bgr,
                                                           box, face_visible)

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
                    "gaze": self._gaze(face_visible, turn, head_angle),
                    "head_yaw": round(turn[0], 3) if turn else None,
                    "head_pitch": round(turn[1], 3) if turn else None,
                    "head_angle_deg": round(head_angle, 1) if head_angle is not None else None,
                    "body_angle_deg": round(body_angle, 1) if body_angle is not None else None,
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
            if self.face_landmarker is not None:
                self.face_landmarker.close()
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
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
