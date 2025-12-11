import cv2, threading, time, os
from contextlib import nullcontext
from datetime import datetime
from typing import List, Optional

from flask import current_app

try:
    from .detector import VehicleDetector, DetectionEvent
    DETECTOR_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover - optional dependency
    VehicleDetector = None
    DetectionEvent = None
    DETECTOR_IMPORT_ERROR = exc


class Camera:
    def __init__(self):
        self.cap = None
        self.lock = threading.Lock()
        self.running = False
        self.app = None
        self.video_path: Optional[str] = None
        self.cam_index: Optional[int] = None
        self.source_label: str = "video file"
        self._configure_source()
        self.loop_video = self.cam_index is None
        self.detector: Optional[VehicleDetector] = None
        self.detector_error: Optional[Exception] = DETECTOR_IMPORT_ERROR

    def _configure_source(self):
        """Determine whether to use webcam (CAM_INDEX) or a video file (VIDEO_PATH)."""
        env_cam = os.getenv('CAM_INDEX', '').strip()
        env_video = os.getenv('VIDEO_PATH', '').strip()
        base_video = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'videos', 'gate_demo.mp4'))

        if env_cam:
            try:
                self.cam_index = int(env_cam)
                self.source_label = f"webcam #{self.cam_index}"
                print(f"[INFO] Camera configured to use webcam index {self.cam_index}")
                return
            except ValueError:
                print(f"[WARN] Invalid CAM_INDEX '{env_cam}'. Falling back to video file.")

        self.video_path = os.path.abspath(env_video) if env_video else base_video
        self.source_label = os.path.basename(self.video_path)
        print(f"[INFO] Camera configured to use video file: {self.video_path}")

    def _open(self):
        if self.cam_index is not None:
            backend = cv2.CAP_DSHOW if os.name == 'nt' else 0
            print(f"[INFO] Opening webcam index {self.cam_index}")
            self.cap = cv2.VideoCapture(self.cam_index, backend)
            if not self.cap or not self.cap.isOpened():
                error = f"Failed to open webcam index {self.cam_index}"
                print(f"[ERROR] {error}")
                self.cap = None
                return False, error
            print("[INFO] Webcam opened successfully.")
            return True, None

        if not self.video_path or not os.path.exists(self.video_path):
            error = f"Video file not found: {self.video_path}"
            print(f"[ERROR] {error}")
            self.cap = None
            return False, error

        print(f"[INFO] Opening video file: {self.video_path}")
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap or not self.cap.isOpened():
            error = "Failed to open video file."
            print(f"[ERROR] {error}")
            self.cap = None
            return False, error

        print("[INFO] Video file opened successfully.")
        return True, None

    def start(self):
        with self.lock:
            if self.running:
                return True, None
            ok, error = self._open()
            if not ok:
                return False, error or "Unable to open source"
            try:
                self.app = current_app._get_current_object()
            except RuntimeError:
                self.app = None
            self._ensure_detector()
            if self.detector_error:
                msg = f"Detector unavailable: {self.detector_error}"
                print(f"[ERROR] {msg}")
                self.stop()
                return False, msg
            self.running = self.cap is not None and self.cap.isOpened()
            if not self.running:
                self.stop()
                return False, "Camera/video not available"
            return True, None

    def stop(self):
        with self.lock:
            if self.cap:
                try:
                    self.cap.release()
                except Exception:
                    pass
            self.cap = None
            self.running = False

    def frames(self):
        from .events import emit_vehicle_event

        while True:
            with self.lock:
                if not self.running or not self.cap:
                    break
                ok, frame = self.cap.read()
                if not ok and self.loop_video:
                    # Loop: reopen the file
                    self.cap.release()
                    reopened, _ = self._open()
                    if not reopened:
                        break
                    continue
            if not ok:
                break

            annotated, events = self._detect(frame)
            self._emit_events(events, emit_vehicle_event)

            try:
                annotated = cv2.resize(annotated, (960, 540))
            except Exception:
                pass
            ok, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ok:
                yield buf.tobytes()
            else:
                time.sleep(0.01)

    def _ensure_detector(self):
        if self.detector or self.detector_error:
            return
        if VehicleDetector is None:
            print(f"[WARN] YOLO detector unavailable: {self.detector_error}")
            return
        try:
            self.detector = VehicleDetector()
            print("[INFO] YOLOv8 vehicle detector initialized.")
        except Exception as exc:  # pragma: no cover - runtime failure guard
            self.detector_error = exc
            print(f"[ERROR] Failed to initialize YOLO detector: {exc}")

    def _detect(self, frame):
        if not self.detector:
            return frame, []
        try:
            return self.detector.process_frame(frame)
        except Exception as exc:  # pragma: no cover - runtime failure guard
            print(f"[ERROR] YOLO detection failed: {exc}")
            return frame, []

    def _emit_events(self, events: List[DetectionEvent], emit_callable):
        if not events:
            return
        ctx = self.app.app_context() if self.app else nullcontext()
        with ctx:
            for event in events:
                payload = {
                    'vehicle_number': event.vehicle_number,
                    'status': event.status,
                    'authorized_as': event.authorized_as,
                    'confidence': event.confidence,
                    'snapshot_path': event.snapshot_path,
                    'vehicle_type': event.vehicle_type,
                    'time_stamp': event.timestamp or datetime.utcnow(),
                }
                try:
                    emit_callable(payload)
                except Exception as exc:  # pragma: no cover - runtime failure guard
                    print(f"[ERROR] Failed to emit vehicle event: {exc}")

    def describe_source(self) -> str:
        return self.source_label

camera = Camera()
