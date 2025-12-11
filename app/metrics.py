from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Deque, Dict, List


@dataclass
class FrameSample:
    timestamp: float
    frame_ms: float
    detect_ms: float
    ocr_ms: float
    events: int
    ocr_attempts: int
    ocr_success: int


class PerformanceTracker:
    """
    Thread-safe circular buffer that stores recent performance samples
    so we can compute FPS, inference latency, OCR hit rate, etc.
    """

    def __init__(self, window: int = 180):
        self.window = max(window, 1)
        self._samples: Deque[FrameSample] = deque(maxlen=self.window)
        self._lock = Lock()

        self._total_frames = 0
        self._total_events = 0
        self._total_ocr_attempts = 0
        self._total_ocr_success = 0
        self._started_at = time.time()

    def record(
        self,
        *,
        frame_ms: float,
        detect_ms: float,
        ocr_ms: float,
        events: int,
        ocr_attempts: int,
        ocr_success: int,
    ) -> None:
        sample = FrameSample(
            timestamp=time.time(),
            frame_ms=max(frame_ms, 0.0),
            detect_ms=max(detect_ms, 0.0),
            ocr_ms=max(ocr_ms, 0.0),
            events=max(events, 0),
            ocr_attempts=max(ocr_attempts, 0),
            ocr_success=max(ocr_success, 0),
        )
        with self._lock:
            self._samples.append(sample)
            self._total_frames += 1
            self._total_events += sample.events
            self._total_ocr_attempts += sample.ocr_attempts
            self._total_ocr_success += sample.ocr_success

    def _summarize_recent(self, samples: List[FrameSample]) -> Dict[str, float]:
        if not samples:
            return {
                "fps": 0.0,
                "frame_ms": 0.0,
                "detect_ms": 0.0,
                "ocr_ms": 0.0,
                "events_per_min": 0.0,
                "ocr_success_rate": 0.0,
                "sample_size": 0,
            }

        frame_time_ms = sum(s.frame_ms for s in samples)
        detect_time_ms = sum(s.detect_ms for s in samples)
        ocr_time_ms = sum(s.ocr_ms for s in samples)
        total_events = sum(s.events for s in samples)
        total_attempts = sum(s.ocr_attempts for s in samples)
        total_success = sum(s.ocr_success for s in samples)

        avg_frame_ms = frame_time_ms / len(samples)
        avg_detect_ms = detect_time_ms / len(samples)
        avg_ocr_ms = ocr_time_ms / len(samples)

        fps = 0.0
        if frame_time_ms > 0:
            fps = len(samples) / (frame_time_ms / 1000.0)

        events_per_min = 0.0
        if frame_time_ms > 0:
            events_per_min = (total_events / (frame_time_ms / 1000.0)) * 60.0

        success_rate = 0.0
        if total_attempts > 0:
            success_rate = (total_success / total_attempts) * 100.0

        return {
            "fps": round(fps, 2),
            "frame_ms": round(avg_frame_ms, 2),
            "detect_ms": round(avg_detect_ms, 2),
            "ocr_ms": round(avg_ocr_ms, 2),
            "events_per_min": round(events_per_min, 2),
            "ocr_success_rate": round(success_rate, 2),
            "sample_size": len(samples),
        }

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            samples = list(self._samples)
            total_frames = self._total_frames
            total_events = self._total_events
            total_attempts = self._total_ocr_attempts
            total_success = self._total_ocr_success
            started_at = self._started_at

        uptime_seconds = max(time.time() - started_at, 0.001)
        totals_success_rate = (
            (total_success / total_attempts) * 100.0 if total_attempts else 0.0
        )

        return {
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "recent": self._summarize_recent(samples),
            "totals": {
                "frames": total_frames,
                "events": total_events,
                "ocr_success_rate": round(totals_success_rate, 2),
                "ocr_attempts": total_attempts,
                "uptime_seconds": int(uptime_seconds),
            },
        }


performance_tracker = PerformanceTracker()





