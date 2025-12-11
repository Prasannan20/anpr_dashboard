from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Sequence, Tuple, Optional

import cv2
import numpy as np
import re
from ultralytics import YOLO

from .metrics import PerformanceTracker, performance_tracker

try:
    import easyocr  # type: ignore
    OCR_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - optional dependency
    easyocr = None
    OCR_IMPORT_ERROR = exc

try:  # Torch 2.6+ safe loading workaround
    import importlib
    import pkgutil

    from torch.serialization import add_safe_globals  # type: ignore
    from torch.nn import ModuleList, Sequential  # type: ignore
    from ultralytics.nn import modules  # type: ignore
    from ultralytics.nn.tasks import DetectionModel  # type: ignore

    safe_items = {DetectionModel, ModuleList, Sequential}

    def collect_types(mod):
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name, None)
            if isinstance(attr, type):
                safe_items.add(attr)

    collect_types(modules)
    conv_cls = getattr(modules, 'Conv', None)
    if conv_cls:
        safe_items.add(conv_cls)
    if hasattr(modules, "__path__"):
        for _, name, _ in pkgutil.walk_packages(modules.__path__, modules.__name__ + "."):
            try:
                submod = importlib.import_module(name)
            except Exception:
                continue
            collect_types(submod)

    add_safe_globals(list(safe_items))
except Exception:
    pass

try:  # Fallback: force torch.load to allow full checkpoints on PyTorch 2.6+
    import torch
    from ultralytics.nn import tasks as yolo_tasks  # type: ignore

    def torch_safe_load_override(weight):
        return torch.load(weight, map_location="cpu", weights_only=False), weight  # type: ignore[arg-type]

    yolo_tasks.torch_safe_load = torch_safe_load_override  # type: ignore[attr-defined]
except Exception:
    pass


@dataclass
class DetectionEvent:
    vehicle_number: str
    confidence: int
    snapshot_path: str
    status: str = 'IN'
    authorized_as: str = 'Unauthorized'
    vehicle_type: str = 'Vehicle'
    timestamp: datetime | None = None


class VehicleDetector:
    """
    Wrapper around a YOLOv8 model to detect vehicles on video frames.

    Each call to `process_frame` returns an annotated frame alongside a list
    of `DetectionEvent` instances for newly observed vehicles. A lightweight
    spatial/temporal memory is used to reduce duplicate emissions.
    """

    VEHICLE_CLASS_IDS: Sequence[int] = (2, 3, 5, 7)  # car, motorcycle, bus, truck (COCO ids)
    COLOR = (0, 255, 0)

    def __init__(
        self,
        model_path: str | None = None,
        confidence_threshold: float = 0.45,
        cooldown_seconds: float = 3.0,
        distance_threshold: float = 120.0,
        snapshot_dir: str | None = None,
        metrics_tracker: Optional[PerformanceTracker] = None,
    ) -> None:
        if model_path is None:
            model_path = os.getenv('YOLO_MODEL_PATH', 'yolov8n.pt')

        self.model = YOLO(model_path)
        raw_names = self.model.model.names if hasattr(self.model, 'model') else self.model.names
        if isinstance(raw_names, dict):
            self.names = raw_names
        else:
            self.names = {int(idx): str(name) for idx, name in enumerate(raw_names)}
        self.confidence_threshold = confidence_threshold
        self.cooldown_seconds = cooldown_seconds
        self.distance_threshold = distance_threshold

        base_dir = os.path.dirname(__file__)
        if snapshot_dir is None:
            snapshot_dir = os.path.join(base_dir, 'static', 'snapshots')
        os.makedirs(snapshot_dir, exist_ok=True)

        self.snapshot_dir = snapshot_dir
        self.snapshot_rel_dir = os.path.relpath(snapshot_dir, base_dir).replace('\\', '/')

        # OCR performance tuning (can be overridden via env vars)
        self.ocr_max_variants = max(int(os.getenv('OCR_VARIANTS', 5)), 1)
        self.ocr_early_stop_conf = float(os.getenv('OCR_EARLY_CONF', 0.6))
        self.ocr_min_confidence = float(os.getenv('OCR_MIN_CONF', 0.35))
        self.ocr_fallback_confidence = float(os.getenv('OCR_FALLBACK_CONF', 0.25))

        # recent detections memory
        self._recent: List[Tuple[Tuple[float, float], float]] = []
        # OCR temporal consistency: store recent plate readings per vehicle position
        self._plate_readings: dict = {}  # key: (center_x, center_y), value: list of (plate, confidence, timestamp)
        self.ocr_reader = None
        self.ocr_error = OCR_IMPORT_ERROR
        self.metrics = metrics_tracker or performance_tracker

    def _ensure_ocr(self):
        if self.ocr_reader or self.ocr_error:
            return
        if easyocr is None:
            self.ocr_error = OCR_IMPORT_ERROR or RuntimeError("easyocr not installed")
            print(f"[WARN] License plate OCR unavailable: {self.ocr_error}")
            return
        try:
            self.ocr_reader = easyocr.Reader(['en'], gpu=False)
            print("[INFO] EasyOCR reader initialized for license plates.")
        except Exception as exc:  # pragma: no cover - runtime failure guard
            self.ocr_error = exc
            print(f"[ERROR] Failed to initialize EasyOCR: {exc}")

    def _normalize_plate(self, text: str) -> str | None:
        cleaned = re.sub(r'[^A-Z0-9]', '', text.upper())
        match = re.match(r'^([A-Z]{2})(\d{1,2})([A-Z]{1,2})(\d{3,4})$', cleaned)
        if not match:
            return None
        state, district, series, number = match.groups()
        return f"{state} {int(district):02d} {series} {int(number):04d}"

    def _preprocess_roi(self, roi: np.ndarray) -> List[np.ndarray]:
        """Apply multiple preprocessing techniques to improve OCR accuracy."""
        processed = []
        if roi.size == 0:
            return processed

        limit = self.ocr_max_variants

        def add_variant(img):
            if len(processed) < limit:
                processed.append(img)

        # Original ROI
        add_variant(roi.copy())
        if len(processed) >= limit:
            return processed
        
        # Convert to grayscale if needed
        if len(roi.shape) == 3:
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        else:
            gray = roi.copy()
        
        # Resize to minimum height for better OCR (EasyOCR works better with larger text)
        min_height = 50
        if gray.shape[0] < min_height:
            scale = min_height / gray.shape[0]
            new_width = int(gray.shape[1] * scale)
            gray = cv2.resize(gray, (new_width, min_height), interpolation=cv2.INTER_CUBIC)
        
        # Method 1: Grayscale
        add_variant(gray)
        if len(processed) >= limit:
            return processed
        
        # Method 2: Grayscale with contrast enhancement (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        add_variant(enhanced)
        if len(processed) >= limit:
            return processed
        
        # Method 3: Threshold (binary)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        add_variant(thresh)
        if len(processed) >= limit:
            return processed
        
        # Method 4: Adaptive threshold
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        add_variant(adaptive)
        if len(processed) >= limit:
            return processed
        
        # Method 5: Denoised + enhanced
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        denoised_enhanced = clahe.apply(denoised)
        add_variant(denoised_enhanced)
        if len(processed) >= limit:
            return processed
        
        # Method 6: Morphological operations to clean up text
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        morph = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
        add_variant(morph)
        if len(processed) >= limit:
            return processed
        
        # Method 7: Sharpen image
        kernel_sharpen = np.array([[-1, -1, -1],
                                   [-1,  9, -1],
                                   [-1, -1, -1]])
        sharpened = cv2.filter2D(gray, -1, kernel_sharpen)
        add_variant(sharpened)
        if len(processed) >= limit:
            return processed
        
        # Method 8: High contrast version
        high_contrast = cv2.convertScaleAbs(gray, alpha=1.5, beta=30)
        add_variant(high_contrast)
        
        return processed

    def _get_spatial_key(self, center: Tuple[float, float]) -> Tuple[int, int]:
        """Convert center to spatial key for approximate matching (handles slight movement)."""
        # Round to nearest 20 pixels for spatial hashing
        grid_size = 20
        return (int(center[0] // grid_size), int(center[1] // grid_size))
    
    def _get_best_plate_from_readings(self, center: Tuple[float, float], current_time: float) -> str | None:
        """Get best plate number from temporal readings using voting."""
        # Use spatial key for approximate matching
        key = self._get_spatial_key(center)
        if key not in self._plate_readings:
            return None
        
        # Clean old readings (older than 3 seconds)
        self._plate_readings[key] = [
            (plate, conf, ts) for plate, conf, ts in self._plate_readings[key]
            if (current_time - ts) <= 3.0
        ]
        
        if not self._plate_readings[key]:
            del self._plate_readings[key]
            return None
        
        # Count votes for each plate (weighted by confidence)
        plate_votes: dict[str, float] = {}
        for plate, conf, _ in self._plate_readings[key]:
            plate_votes[plate] = plate_votes.get(plate, 0.0) + conf
        
        # Return plate with highest weighted votes
        if plate_votes:
            best_plate = max(plate_votes.items(), key=lambda x: x[1])[0]
            total_votes = plate_votes[best_plate]
            # Only return if we have at least 2 readings or high confidence
            if len(self._plate_readings[key]) >= 2 or total_votes >= 0.7:
                return best_plate
        
        return None

    def _read_license_plate(self, frame: np.ndarray, box: Tuple[int, int, int, int], center: Tuple[float, float] | None = None) -> str | None:
        if self.ocr_error:
            return None
        self._ensure_ocr()
        if not self.ocr_reader:
            return None
        
        current_time = time.time()
        
        # Check temporal consistency first
        if center:
            cached_plate = self._get_best_plate_from_readings(center, current_time)
            if cached_plate:
                return cached_plate
        
        x1, y1, x2, y2 = box
        h = max(y2 - y1, 1)
        w = max(x2 - x1, 1)
        
        # Better ROI extraction - focus on bottom 30-40% of vehicle
        roi_top = max(y2 - int(h * 0.35), y1)
        # Add padding but ensure we don't go out of bounds
        padding_x = max(5, int(w * 0.1))
        roi = frame[roi_top:y2, max(0, x1-padding_x):min(frame.shape[1], x2+padding_x)]
        
        if roi.size == 0 or roi.shape[0] < 10 or roi.shape[1] < 20:
            return None
        
        # Allowlist: Only allow alphanumeric characters (A-Z, 0-9)
        allowlist = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        
        # Try multiple preprocessing techniques
        processed_rois = self._preprocess_roi(roi)
        best_candidate: str | None = None
        best_confidence: float = 0.0
        
        for processed_roi in processed_rois:
            try:
                # Use allowlist and adjust parameters for better accuracy
                results = self.ocr_reader.readtext(
                    processed_roi,
                    allowlist=allowlist,
                    paragraph=False,
                    detail=1,
                    width_ths=0.6,  # Lower threshold to catch more text
                    height_ths=0.6,
                    slope_ths=0.1,
                    mag_ratio=2.0  # Magnify image for better recognition
                )
                
                for _, text, conf in results:
                    # Lower confidence threshold to get more candidates
                    if conf < 0.25:
                        continue
                    candidate = self._normalize_plate(text)
                    if candidate and conf > best_confidence:
                        best_candidate = candidate
                        best_confidence = conf
                if best_candidate and best_confidence >= self.ocr_early_stop_conf:
                    break
            except Exception as exc:  # pragma: no cover - runtime failure guard
                # Continue with next preprocessing method
                continue
        
        if not best_candidate:
            return None
        
        # Store reading for temporal consistency
        if center:
            key = self._get_spatial_key(center)
            if key not in self._plate_readings:
                self._plate_readings[key] = []
            self._plate_readings[key].append((best_candidate, best_confidence, current_time))
            # Keep only last 15 readings per position
            if len(self._plate_readings[key]) > 15:
                self._plate_readings[key] = self._plate_readings[key][-15:]
        
        # Return bestcandidate if confidence is reasonable, otherwise wait for more frames
        min_confidence = self.ocr_min_confidence
        fallback_confidence = self.ocr_fallback_confidence
        if center:
            key = self._get_spatial_key(center)
            readings_count = len(self._plate_readings.get(key, []))
            if best_confidence >= min_confidence or readings_count >= 2:
                return best_candidate
        else:
            if best_confidence >= min_confidence:
                return best_candidate
        
        return best_candidate if best_confidence >= fallback_confidence else None

    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, List[DetectionEvent]]:
        """
        Run detection on a BGR OpenCV frame.

        Returns:
            annotated_frame: np.ndarray
            events: list of DetectionEvent for newly detected vehicles
        """
        frame_start = time.perf_counter()
        detect_start = time.perf_counter()
        results = self.model.predict(
            source=frame,
            conf=self.confidence_threshold,
            classes=list(self.VEHICLE_CLASS_IDS),
            device='cpu',
            verbose=False,
        )
        detect_duration_ms = (time.perf_counter() - detect_start) * 1000.0
        ocr_duration_ms = 0.0
        ocr_attempts = 0
        ocr_success = 0

        if not results:
            frame_duration_ms = (time.perf_counter() - frame_start) * 1000.0
            self._record_metrics(
                frame_ms=frame_duration_ms,
                detect_ms=detect_duration_ms,
                ocr_ms=ocr_duration_ms,
                events=0,
                ocr_attempts=ocr_attempts,
                ocr_success=ocr_success,
            )
            return frame, []

        result = results[0]
        boxes = getattr(result, 'boxes', None)
        if boxes is None or boxes.xyxy is None or boxes.xyxy.shape[0] == 0:
            frame_duration_ms = (time.perf_counter() - frame_start) * 1000.0
            self._record_metrics(
                frame_ms=frame_duration_ms,
                detect_ms=detect_duration_ms,
                ocr_ms=ocr_duration_ms,
                events=0,
                ocr_attempts=ocr_attempts,
                ocr_success=ocr_success,
            )
            return frame, []

        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        classes = boxes.cls.cpu().numpy()

        annotated = frame.copy()
        events: List[DetectionEvent] = []
        now = time.time()

        for coords, conf, cls_id in zip(xyxy, confs, classes):
            confidence = float(conf)
            if confidence < self.confidence_threshold:
                continue

            x1, y1, x2, y2 = (
                max(int(coords[0]), 0),
                max(int(coords[1]), 0),
                min(int(coords[2]), frame.shape[1] - 1),
                min(int(coords[3]), frame.shape[0] - 1),
            )
            if x2 <= x1 or y2 <= y1:
                continue
            center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

            label = self.names.get(int(cls_id), 'vehicle').upper()
            text = f"{label} {confidence*100:.1f}%"
            cv2.rectangle(annotated, (x1, y1), (x2, y2), self.COLOR, 2)
            cv2.putText(
                annotated,
                text,
                (x1, max(y1 - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                self.COLOR,
                2,
                cv2.LINE_AA,
            )

            vehicle_type = self._map_vehicle_type(int(cls_id))
            # Pass center for temporal consistency so we only emit when we have a real reading
            ocr_attempts += 1
            ocr_single_start = time.perf_counter()
            plate_number = self._read_license_plate(frame, (x1, y1, x2, y2), center)
            ocr_duration_ms += (time.perf_counter() - ocr_single_start) * 1000.0
            if not plate_number:
                continue
            ocr_success += 1
            if not self._is_new_detection(center, now):
                continue
            snapshot_path = self._save_snapshot(annotated)
            events.append(
                DetectionEvent(
                    vehicle_number=plate_number,
                    confidence=int(confidence * 100),
                    snapshot_path=snapshot_path,
                    vehicle_type=vehicle_type,
                    timestamp=datetime.utcnow(),
                )
            )

        frame_duration_ms = (time.perf_counter() - frame_start) * 1000.0
        self._record_metrics(
            frame_ms=frame_duration_ms,
            detect_ms=detect_duration_ms,
            ocr_ms=ocr_duration_ms,
            events=len(events),
            ocr_attempts=ocr_attempts,
            ocr_success=ocr_success,
        )
        return annotated, events

    def _is_new_detection(self, center: Tuple[float, float], timestamp: float) -> bool:
        """De-duplicate detections within a spatial + temporal window."""
        self._recent = [
            (c, t) for (c, t) in self._recent if (timestamp - t) <= self.cooldown_seconds
        ]
        for prev_center, prev_time in self._recent:
            if (timestamp - prev_time) > self.cooldown_seconds:
                continue
            if self._distance(center, prev_center) <= self.distance_threshold:
                return False
        self._recent.append((center, timestamp))
        return True

    @staticmethod
    def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        return float(np.linalg.norm(np.array(a) - np.array(b)))

    def _map_vehicle_type(self, class_id: int) -> str:
        mapping = {
            2: 'Car',
            3: 'Motorcycle',
            5: 'Bus',
            7: 'Truck',
        }
        return mapping.get(class_id, 'Vehicle')

    def _record_metrics(
        self,
        *,
        frame_ms: float,
        detect_ms: float,
        ocr_ms: float,
        events: int,
        ocr_attempts: int,
        ocr_success: int,
    ) -> None:
        if not self.metrics:
            return
        try:
            self.metrics.record(
                frame_ms=frame_ms,
                detect_ms=detect_ms,
                ocr_ms=ocr_ms,
                events=events,
                ocr_attempts=ocr_attempts,
                ocr_success=ocr_success,
            )
        except Exception:
            # Metrics must never break detection loop
            pass

    def _save_snapshot(self, frame: np.ndarray) -> str:
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
        filename = f"vehicle_{timestamp}.jpg"
        path = os.path.join(self.snapshot_dir, filename)
        try:
            cv2.imwrite(path, frame)
        except Exception as exc:  # pragma: no cover - filesystem failures
            print(f"[ERROR] Failed to save snapshot: {exc}")
        rel_path = f"{self.snapshot_rel_dir}/{filename}"
        return rel_path.replace('\\', '/')


