"""Screen-recognition primitives with explicit confidence scores.

This module performs offline image analysis only. It does not capture a window
and never sends input events. Capture adapters supply NumPy image frames, while
the runtime decides whether a classified observation is safe to act upon.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import cv2
import numpy as np

from .models import MatchResult, Observation, ScreenState


@dataclass(frozen=True)
class BoundingBox:
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    bbox: BoundingBox | None = None
    source: str = "template"


@dataclass(frozen=True)
class Template:
    label: str
    image: np.ndarray
    threshold: float = 0.90

    def __post_init__(self) -> None:
        if self.image.ndim not in (2, 3):
            raise ValueError("template image must be grayscale or color")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("template threshold must be between 0.0 and 1.0")


class TemplateMatcher:
    """Matches named UI templates across a small, configured scale range."""

    def __init__(
        self,
        templates: Iterable[Template],
        scales: Sequence[float] = (0.8, 0.9, 1.0, 1.1, 1.2),
    ) -> None:
        self.templates = tuple(templates)
        self.scales = tuple(scales)
        if not self.templates:
            raise ValueError("at least one template is required")
        if not self.scales or any(scale <= 0 for scale in self.scales):
            raise ValueError("scales must contain positive values")

    @classmethod
    def from_directory(
        cls, directory: str | Path, scales: Sequence[float] = (0.8, 0.9, 1.0, 1.1, 1.2)
    ) -> "TemplateMatcher":
        """Load PNG/JPEG templates using filenames as stable labels."""
        directory = Path(directory)
        templates: list[Template] = []
        for path in sorted(directory.glob("*")):
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                continue
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"could not decode template: {path}")
            templates.append(Template(label=path.stem, image=image))
        return cls(templates, scales)

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Return one best candidate per template, including low-confidence ones."""
        frame_gray = _grayscale(frame)
        detections: list[Detection] = []
        for template in self.templates:
            template_gray = _grayscale(template.image)
            best = _best_template_match(frame_gray, template_gray, self.scales)
            if best is None:
                continue
            confidence, bbox = best
            detections.append(Detection(template.label, confidence, bbox))
        return detections

    def recognized(self, frame: np.ndarray) -> list[Detection]:
        """Return template detections that meet their configured thresholds."""
        thresholds = {template.label: template.threshold for template in self.templates}
        return [item for item in self.detect(frame) if item.confidence >= thresholds[item.label]]


class OcrReader:
    """Lazily imports the OCR bridge so image-only tests need no Tesseract binary."""

    def __init__(self, language: str = "eng", psm: int = 6) -> None:
        self.language = language
        self.psm = psm

    def read(self, frame: np.ndarray) -> str:
        try:
            import pytesseract
        except ImportError as error:  # pragma: no cover - requirements protect this path
            raise RuntimeError("pytesseract is not installed") from error
        try:
            return pytesseract.image_to_string(
                frame, lang=self.language, config=f"--psm {self.psm}"
            ).strip()
        except pytesseract.TesseractNotFoundError as error:
            raise RuntimeError(
                "Tesseract executable is not available; install it before enabling OCR"
            ) from error


class KeywordClassifier:
    """Maps OCR text to a state without relying on a single fixed UI language."""

    def __init__(
        self,
        state_keywords: Mapping[ScreenState, Sequence[str]],
        victory_keywords: Sequence[str] = ("victory", "胜利"),
        defeat_keywords: Sequence[str] = ("defeat", "失败"),
    ) -> None:
        self.state_keywords = {
            state: tuple(_normalize(keyword) for keyword in keywords)
            for state, keywords in state_keywords.items()
        }
        self.victory_keywords = tuple(_normalize(keyword) for keyword in victory_keywords)
        self.defeat_keywords = tuple(_normalize(keyword) for keyword in defeat_keywords)

    def classify(self, text: str) -> Observation | None:
        normalized = _normalize(text)
        if not normalized:
            return None
        result = self._match_result(normalized)
        for state, keywords in self.state_keywords.items():
            if any(keyword in normalized for keyword in keywords):
                confidence = max(len(keyword) / max(len(normalized), 1) for keyword in keywords if keyword in normalized)
                return Observation(
                    state=state,
                    confidence=min(1.0, max(0.90, confidence)),
                    result=result if state == ScreenState.RESULT_CONFIRMED else None,
                    metadata={"ocr_text": text},
                )
        return None

    def _match_result(self, normalized: str) -> MatchResult | None:
        if any(keyword in normalized for keyword in self.victory_keywords):
            return MatchResult.VICTORY
        if any(keyword in normalized for keyword in self.defeat_keywords):
            return MatchResult.DEFEAT
        return None


class SceneClassifier:
    """Combines template and OCR evidence into a single conservative observation."""

    def __init__(self, label_states: Mapping[str, ScreenState], keyword_classifier: KeywordClassifier) -> None:
        self.label_states = dict(label_states)
        self.keyword_classifier = keyword_classifier

    def classify(self, detections: Iterable[Detection], ocr_text: str = "") -> Observation:
        candidates: list[Observation] = []
        for detection in detections:
            state = self.label_states.get(detection.label)
            if state is None:
                continue
            metadata = {"source": detection.source, "label": detection.label}
            if detection.bbox is not None:
                metadata["bbox"] = ",".join(
                    str(value)
                    for value in (
                        detection.bbox.left,
                        detection.bbox.top,
                        detection.bbox.width,
                        detection.bbox.height,
                    )
                )
            candidates.append(Observation(state, detection.confidence, metadata=metadata))
        ocr_observation = self.keyword_classifier.classify(ocr_text)
        if ocr_observation is not None:
            candidates.append(ocr_observation)
        if not candidates:
            return Observation(ScreenState.UNKNOWN_SCREEN, confidence=1.0)
        return max(candidates, key=lambda candidate: candidate.confidence)


def _grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    if image.ndim == 3 and image.shape[2] in (3, 4):
        code = cv2.COLOR_BGR2GRAY if image.shape[2] == 3 else cv2.COLOR_BGRA2GRAY
        return cv2.cvtColor(image, code)
    raise ValueError("frame must have one, three, or four channels")


def _best_template_match(
    frame_gray: np.ndarray, template_gray: np.ndarray, scales: Sequence[float]
) -> tuple[float, BoundingBox] | None:
    best: tuple[float, BoundingBox] | None = None
    for scale in scales:
        if scale == 1.0:
            resized = template_gray
        else:
            resized = cv2.resize(template_gray, dsize=None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        height, width = resized.shape[:2]
        if height > frame_gray.shape[0] or width > frame_gray.shape[1]:
            continue
        scores = cv2.matchTemplate(frame_gray, resized, cv2.TM_CCOEFF_NORMED)
        _, confidence, _, location = cv2.minMaxLoc(scores)
        candidate = (float(confidence), BoundingBox(location[0], location[1], width, height))
        if best is None or candidate[0] > best[0]:
            best = candidate
    return best


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())
