"""Measure what browsing feels like: time-to-image, UI freezes, and held-key behaviour.

Drives the real PhotoViewer window through a folder of photos and reports:
  * time from pressing Next/Previous until the new photo is on screen
  * the longest freeze of the UI thread per step (a freeze > ~50 ms is felt as a hitch)
  * when the full-resolution frame is ready (needed for zoom/edit/save)
  * holding the arrow key across 10 photos (~30 presses/second)

Usage (run from the project root, on the machine you want to measure):
    python scripts/benchmark_navigation.py "D:\\Photos\\Some folder"
    python scripts/benchmark_navigation.py <folder> --json results.json

Use a folder with at least 22 photos. Settings and the preview disk cache are redirected
to Qt's test locations, so your real configuration is not touched. The disk preview cache
is cleared before the first-visit pass so "first visit" really means first visit.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import types

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if sys.platform != "win32":
    # shell_win binds Windows APIs at import time; the benchmark never calls it.
    _stub = types.ModuleType("image_classifier.shell_win")
    _stub.open_folder_and_select_item = lambda *args, **kwargs: None
    sys.modules["image_classifier.shell_win"] = _stub

from PyQt6.QtCore import QElapsedTimer, QStandardPaths, QThreadPool, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

STALL_THRESHOLD_MS = 25


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", help="folder with at least 22 photos")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--dwell", type=int, default=900, help="ms spent on each photo")
    parser.add_argument("--json", help="write raw results to this file")
    args = parser.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)
    QStandardPaths.setTestModeEnabled(True)

    import image_classifier.app as app_module
    from image_classifier.imaging.loader import ImageLoaderRunnable

    window = app_module.PhotoViewer()
    window.setWindowState(window.windowState() & ~window.windowState().__class__.WindowMaximized)
    window.resize(args.width, args.height)
    window.show()
    viewer = window.image_viewer

    clock = QElapsedTimer()
    clock.start()

    def now():
        return clock.nsecsElapsed() / 1e6

    stalls = []
    last_beat = [now()]

    def heartbeat():
        current = now()
        gap = current - last_beat[0]
        if gap > STALL_THRESHOLD_MS:
            stalls.append(gap)
        last_beat[0] = current

    beat = QTimer()
    beat.setInterval(2)
    beat.timeout.connect(heartbeat)
    beat.start()

    events = []
    original_loaded = viewer.onImageLoaded

    def on_loaded(pixmap, reset_zoom, preserve_zoom, load_id, full_resolution=True):
        current = load_id == viewer.current_load_id
        original_loaded(pixmap, reset_zoom, preserve_zoom, load_id, full_resolution=full_resolution)
        if current:
            events.append({"t": now(), "index": window.current_index, "full": full_resolution})

    viewer.onImageLoaded = on_loaded

    if hasattr(viewer, "_attach_full_resolution"):
        original_attach = viewer._attach_full_resolution

        def on_attach(pixmap, load_id):
            current = load_id == viewer.current_load_id
            original_attach(pixmap, load_id)
            if current:
                events.append({"t": now(), "index": window.current_index, "full": True})

        viewer._attach_full_resolution = on_attach

    def pump(ms):
        end = now() + ms
        while now() < end:
            app.processEvents()
            time.sleep(0.0005)

    def busy():
        count = QThreadPool.globalInstance().activeThreadCount()
        if hasattr(ImageLoaderRunnable, "thread_pool"):
            count += ImageLoaderRunnable.thread_pool().activeThreadCount()
        return count

    def wait_idle(timeout=30000):
        end = now() + timeout
        while now() < end:
            app.processEvents()
            if busy() == 0:
                pump(400)
                if busy() == 0:
                    return
            time.sleep(0.001)

    def wait_for(index, since, timeout=20000):
        end = now() + timeout
        while now() < end:
            app.processEvents()
            if any(e["index"] == index for e in events[since:]):
                return
            time.sleep(0.001)

    def step(direction):
        stalls.clear()
        target = window.current_index + direction
        before = len(events)
        started = now()
        (window.show_next_image if direction > 0 else window.show_previous_image)()
        pump(args.dwell)
        mine = [e for e in events[before:] if e["index"] == target]
        return {
            "to_image": (mine[0]["t"] - started) if mine else None,
            "full_ready": next((e["t"] - started for e in mine if e["full"]), None),
            "worst_freeze": max(stalls, default=0.0),
        }

    pump(300)
    ImageLoaderRunnable.clear_disk_cache()
    opened = now()
    window.load_directory(args.folder, start_at_first=True)
    if len(window.image_files) < 22:
        print(f"Need at least 22 photos, found {len(window.image_files)}.")
        os._exit(2)
    wait_for(0, 0)
    first_image = events[0]["t"] - opened if events else None
    wait_idle()

    first_visit = [step(+1) for _ in range(10)]
    revisit = [step(-1) for _ in range(8)]
    wait_idle()

    window.current_index = 10
    window.show_image()
    wait_idle()
    stalls.clear()
    before = len(events)
    for _ in range(10):
        window.show_next_image()
        pump(33)
    released = now()
    target = window.current_index
    wait_for(target, before)
    landed = next((e["t"] - released for e in events[before:] if e["index"] == target), None)
    burst_freeze_total = sum(stalls)
    pump(1000)

    def describe(rows, key):
        values = [r[key] for r in rows if r[key] is not None]
        if not values:
            return "n/a"
        return f"median {statistics.median(values):7.1f} ms   max {max(values):7.1f} ms"

    print(f"Folder: {args.folder}  ({len(window.image_files)} photos, window {args.width}x{args.height})")
    print(f"Open folder -> first photo on screen: {first_image:.0f} ms")
    for name, rows in (("Next photo, first visit", first_visit), ("Previous photo, revisit", revisit)):
        print(name)
        print(f"   time to image     {describe(rows, 'to_image')}")
        print(f"   worst UI freeze   {describe(rows, 'worst_freeze')}")
        print(f"   full-res ready    {describe(rows, 'full_ready')}")
    print("Arrow key held over 10 photos")
    print(f"   final photo shown {landed:.0f} ms after release" if landed is not None else "   final photo not shown")
    print(f"   UI frozen in total {burst_freeze_total:.0f} ms during the burst")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "first_image_ms": first_image,
                    "first_visit": first_visit,
                    "revisit": revisit,
                    "burst": {"landed_ms": landed, "frozen_ms": burst_freeze_total},
                },
                handle,
                indent=1,
            )
    QStandardPaths.setTestModeEnabled(False)
    os._exit(0)


if __name__ == "__main__":
    main()
