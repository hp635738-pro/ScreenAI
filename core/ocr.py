"""OCR engine built on EasyOCR (fully offline once models are cached).

Exposes ``detect_text(image)`` and ``find_text("Export")`` returning
bounding boxes and confidences. The EasyOCR reader is created lazily in
whatever worker thread needs it, so the GUI never freezes; a custom
reader (or ``reader_factory``) can be injected for tests.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PySide6.QtGui import QImage


class OcrError(RuntimeError):
    """Raised when OCR cannot run."""


@dataclass(slots=True)
class TextDetection:
    text: str
    confidence: float
    polygon: tuple[tuple[int, int], ...]
    bbox: tuple[int, int, int, int]  # x, y, width, height

    @property
    def center(self) -> tuple[int, int]:
        x, y, width, height = self.bbox
        return (x + width // 2, y + height // 2)


class OcrEngine:
    """EasyOCR wrapper with a small, stable interface."""

    def __init__(
        self,
        languages: Sequence[str] = ("en",),
        gpu: bool = False,
        *,
        reader=None,
        reader_factory: Callable[..., object] | None = None,
        vision=None,
        download_enabled: bool = True,
    ) -> None:
        self._languages = list(languages)
        self._gpu = gpu
        self._reader = reader
        self._reader_factory = reader_factory or self._default_factory
        self._vision = vision
        # download_enabled only affects first-time model download; all
        # inference is local. Pass False to guarantee zero network use.
        self._download_enabled = download_enabled

    @property
    def is_loaded(self) -> bool:
        return self._reader is not None

    def ensure_loaded(self) -> None:
        if self._reader is None:
            self._reader = self._reader_factory(
                self._languages, self._gpu, self._download_enabled
            )

    # -------------------------------------------------------------- OCR

    def detect_text(self, image) -> list[TextDetection]:  # noqa: ANN001
        """Detect text in ``image`` (QImage, PIL image or file path).

        Returns detections with bounding boxes, sorted by confidence.
        """
        self.ensure_loaded()
        pixels = self.to_pixels(image)
        try:
            raw = self._reader.readtext(self._as_array(pixels))
        except Exception as exc:  # noqa: BLE001 - report to the UI layer
            raise OcrError(f"OCR failed: {exc}") from exc

        detections = [self._to_detection(item) for item in raw]
        detections.sort(key=lambda d: (-d.confidence, len(d.text)))
        return detections

    def find_text(self, target: str, image=None) -> TextDetection | None:  # noqa: ANN001
        """Find ``target`` in ``image`` (or the attached vision frame)."""
        if image is None:
            if self._vision is None:
                raise OcrError("find_text needs an image when no vision engine is attached")
            image = self._vision.grab().pil_image
        needle = " ".join(target.lower().split())
        if not needle:
            return None
        matches = [
            detection
            for detection in self.detect_text(image)
            if needle in " ".join(detection.text.lower().split())
        ]
        exact = [d for d in matches if " ".join(d.text.lower().split()) == needle]
        pool = exact or matches
        return pool[0] if pool else None

    # ---------------------------------------------------------- helpers

    @staticmethod
    def _to_detection(item) -> TextDetection:  # noqa: ANN001
        bbox, text, confidence = item
        points = tuple((int(x), int(y)) for x, y in bbox)
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        rect = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        return TextDetection(str(text), float(confidence), points, rect)

    @staticmethod
    def _as_array(pil_image: Image.Image):  # noqa: ANN001
        try:
            import numpy
        except ImportError:  # pragma: no cover - numpy ships with easyocr
            return pil_image
        return numpy.asarray(pil_image)

    @staticmethod
    def to_pixels(image) -> Image.Image:  # noqa: ANN001
        """Normalise supported image inputs to a PIL RGB image."""
        if isinstance(image, Image.Image):
            return image.convert("RGB")
        if isinstance(image, QImage):
            qt_image = image.convertToFormat(QImage.Format.Format_RGB888)
            width, height = qt_image.width(), qt_image.height()
            stride = qt_image.bytesPerLine()
            raw = bytes(qt_image.bits())[: qt_image.sizeInBytes()]
            return Image.frombytes("RGB", (width, height), raw, "raw", "RGB", stride)
        if isinstance(image, (str, Path)):
            return Image.open(image).convert("RGB")
        raise OcrError(f"Unsupported image type: {type(image)}")

    @staticmethod
    def _default_factory(languages, gpu, download_enabled):  # noqa: ANN001
        try:
            import easyocr
        except ImportError as exc:
            raise OcrError("easyocr is not installed") from exc
        return easyocr.Reader(languages, gpu=gpu, download_enabled=download_enabled)
