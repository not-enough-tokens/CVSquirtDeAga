"""Detector ArUco: tu script original encapsulado tras la interfaz Detector."""
from __future__ import annotations

import cv2
import numpy as np

from core import Detection, Frame


class ArucoDetector:
    name = "aruco"

    def __init__(self, dictionary: int = cv2.aruco.DICT_4X4_50):
        d = cv2.aruco.getPredefinedDictionary(dictionary)
        self._det = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())

    def detect(self, frame: Frame) -> list[Detection]:
        corners, ids, _ = self._det.detectMarkers(frame.gray())
        if ids is None:
            return []
        out = []
        for c, i in zip(corners, ids.flatten()):
            pts = c.reshape(4, 2)
            center = pts.mean(axis=0)
            side = np.linalg.norm(pts - np.roll(pts, 1, axis=0), axis=1).mean()
            out.append(Detection("aruco", int(i), (float(center[0]), float(center[1])),
                                 float(side), 1.0,
                                 {"corners": pts.round(1).tolist()}))
        return out
