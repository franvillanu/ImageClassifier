"""Native, synthetic-image slideshow soak/performance harness (no user photos).

Example: py scripts/verify_slideshow_windows.py --seconds 1800 --output soak.json
Frame intervals measure completed QPainter paints, excluding loading and the first
second of each slide. This is a machine-specific measurement, not a 4K guarantee.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from PyQt6.QtCore import QStandardPaths, QTimer
from PyQt6.QtWidgets import QApplication
from image_classifier.slideshow.player import PlayerWindow
from image_classifier.slideshow.settings import SlideshowSettings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--height', type=int, default=1080)
    parser.add_argument('--raster', action='store_true')
    parser.add_argument('--fullscreen', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    app = QApplication([])
    QStandardPaths.setTestModeEnabled(True)
    with tempfile.TemporaryDirectory(prefix='slideshow-qa-') as folder:
        paths = []
        for index, (size, extension) in enumerate((((3000,2000),'jpg'),((1600,2400),'png'),((2000,2000),'webp'),((4000,1000),'bmp'),((1200,1800),'tiff'),((1920,1080),'jpg'))):
            image = Image.new('RGB', size, (30+index*20,60,100))
            draw = ImageDraw.Draw(image)
            for x in range(0,size[0],100): draw.line((x,0,x,size[1]),fill='white',width=3)
            for y in range(0,size[1],100): draw.line((0,y,size[0],y),fill='yellow',width=3)
            draw.text((size[0]//2,size[1]//2),str(index),fill='red',stroke_width=3)
            path = str(Path(folder)/f'grid-{index}.{extension}')
            image.save(path)
            paths.append(path)
        window = PlayerWindow(paths, paths[0], SlideshowSettings(3,100,True,True,args.fullscreen), raster=args.raster)
        window.resize(args.width,args.height)
        intervals = []
        presented = []
        failures = []
        states = []
        last = [None]
        fallback = [False]
        start = time.monotonic()
        def painted():
            now = time.monotonic()
            c = window.controller
            if c.state == 'playing' and c.elapsed > 1:
                if last[0] is not None: intervals.append((now-last[0])*1000)
                last[0] = now
            else: last[0] = None
        window.surface.framePainted.connect(painted)
        window.surface.fallbackActivated.connect(lambda:fallback.__setitem__(0,True))
        window.controller.presented.connect(lambda e,f:presented.append(e.effect_id))
        window.controller.error.connect(failures.append)
        window.controller.stateChanged.connect(states.append)
        window.show()
        window.raise_()
        window.activateWindow()
        heartbeat = QTimer(window)
        heartbeat.setInterval(60000)
        heartbeat.timeout.connect(lambda:print(json.dumps({'elapsed_seconds':round(time.monotonic()-start),
                                                         'slides':len(presented),'state':window.controller.state}),flush=True))
        heartbeat.start()
        def finish():
            elapsed = time.monotonic()-start
            values = sorted(intervals)
            output = dict(platform=platform.platform(), requested_size=[args.width,args.height],
                          actual_size=[window.width(),window.height()],dpr=window.devicePixelRatioF(),
                          physical_size=[round(window.width()*window.devicePixelRatioF()),round(window.height()*window.devicePixelRatioF())],
                          elapsed_seconds=elapsed,requested_seconds=args.seconds,
                          renderer=type(window.surface.canvas).__name__,raster_fallback=fallback[0],
                          fullscreen=window.isFullScreen(),
                          slides_presented=len(presented),effects_seen=sorted(set(presented)),errors=failures,
                          state_counts=dict(Counter(states)),frames_measured=len(values),
                          p95_ms=values[min(len(values)-1,int(len(values)*.95))] if values else None,
                          maximum_ms=max(values) if values else None,
                          target_p95_ms=25)
            window.close()
            output['resources_released'] = window.surface.pixmap is None and window.loader._closed
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(output,indent=2),encoding='utf-8')
            print(json.dumps(output,indent=2),flush=True)
            app.quit()
        QTimer.singleShot(args.seconds*1000,finish)
        app.exec()


if __name__ == '__main__':
    main()
