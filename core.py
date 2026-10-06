"""Tipos compartidos por todo el pipeline de visión."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import cv2
import numpy as np


@dataclass
class Frame:
    """Una imagen + metadatos. Cachea conversiones para que N detectores
    no repitan el mismo cvtColor sobre el mismo frame."""
    image: np.ndarray          # BGR
    t_capture: float           # time.perf_counter() al terminar la captura
    index: int
    _cache: dict = field(default_factory=dict, repr=False)

    def gray(self) -> np.ndarray:
        if "gray" not in self._cache:
            self._cache["gray"] = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
        return self._cache["gray"]


@dataclass
class Detection:
    kind: str                          # "aruco" | "ball"
    label: int | str                   # id del marcador / clase
    center: tuple[float, float]        # px, coordenadas de la imagen original
    size: float                        # lado medio (aruco) o radio (ball), px
    confidence: float                  # [0, 1]
    extra: dict = field(default_factory=dict)   # p. ej. distancia estimada


@dataclass
class FrameResult:
    frame_index: int
    t_capture: float
    detections: list[Detection]
    timings: dict[str, float]          # segundos por etapa


class Detector(Protocol):
    name: str

    def detect(self, frame: Frame) -> list[Detection]: ...