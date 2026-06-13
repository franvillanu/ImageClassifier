"""Repeatable local benchmark for the decode and sharpen hot paths."""
from __future__ import annotations

import argparse
import os
import sys
import statistics
import tempfile
import time

import numpy as np
from PIL import Image
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QImage, QImageReader, QPixmap
from PyQt6.QtWidgets import QApplication

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from image_classifier.imaging.sharpen import sharpen_cv2


def measure(label, operation, repeats=3):
    samples = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = operation()
        samples.append((time.perf_counter() - started) * 1000)
    print(
        f"{label}: min={min(samples):.1f} ms "
        f"median={statistics.median(samples):.1f} ms"
    )
    return result


def make_fixture(path, width, height):
    horizontal = np.linspace(0, 255, width, dtype=np.uint8)[None, :]
    vertical = np.linspace(0, 255, height, dtype=np.uint8)[:, None]
    pixels = np.empty((height, width, 3), dtype=np.uint8)
    pixels[:, :, 0] = horizontal
    pixels[:, :, 1] = vertical
    pixels[:, :, 2] = (
        (
            horizontal.astype(np.uint16)
            + vertical.astype(np.uint16)
        )
        // 2
    ).astype(np.uint8)
    Image.fromarray(pixels, "RGB").save(path, quality=95, subsampling=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=4000)
    parser.add_argument("--height", type=int, default=3000)
    parser.add_argument("--preview", type=int, default=1920)
    args = parser.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "benchmark.jpg")
        make_fixture(path, args.width, args.height)

        full = measure(
            "Full JPEG decode",
            lambda: QImageReader(path).read(),
        )

        def read_preview():
            reader = QImageReader(path)
            size = reader.size()
            size.scale(
                QSize(args.preview, args.preview),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
            reader.setScaledSize(size)
            return reader.read()

        preview = measure("Scaled JPEG decode", read_preview)
        full_pixmap = QPixmap.fromImage(
            full.convertToFormat(QImage.Format.Format_RGBA8888)
        )
        preview_pixmap = QPixmap.fromImage(
            preview.convertToFormat(QImage.Format.Format_RGBA8888)
        )
        measure(
            "Full LAB sharpen",
            lambda: sharpen_cv2(full_pixmap, 3, 1.0),
            repeats=1,
        )
        measure(
            "Preview LAB sharpen",
            lambda: sharpen_cv2(preview_pixmap, 3, 1.0),
            repeats=2,
        )

    del app


if __name__ == "__main__":
    main()
