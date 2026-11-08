"""Observed WPF geometry and deterministic playback/lifecycle tests."""
import csv
from pathlib import Path
import random
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage
from image_classifier.slideshow.controller import SlideshowController
from image_classifier.slideshow.motion import EFFECTS
from image_classifier.slideshow.settings import SlideshowSettings


@pytest.mark.parametrize('filename,count',[('wpf-observations.csv',600),('wpf-hidpi.csv',600),('wpf-large.csv',600),('wpf-boundaries.csv',180),('wpf-native.csv',600)])
def test_all_measured_foreground_frames(filename,count):
    path = Path(__file__).parent/'fixtures/slideshow'/filename
    with path.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == count
    for row in rows:
        effect = EFFECTS[f"v2-{int(row['effect']):02}"]
        size = tuple(map(int, row['shape'].split('x')))
        viewport = (float(row.get('viewportWidth',960)),float(row.get('viewportHeight',540)))
        frame = effect.evaluate(float(row['progress']), size, viewport)
        assert frame.scale == pytest.approx(float(row['scaleX']), abs=1e-7)
        assert frame.opacity == pytest.approx(float(row['opacity']), abs=.01)
        assert (frame.x, frame.y) == pytest.approx((float(row['translateX']), float(row['translateY'])), abs=1)
        assert frame.bounds == pytest.approx(tuple(float(row[k]) for k in ('left','top','width','height')), abs=1)


def test_all_nine_zoom_ins_start_fitted_and_centered():
    for number in (*range(1,7),20,29,30):
        frame=EFFECTS[f'v2-{number:02}'].evaluate(0,(1200,800),(960,540))
        assert (frame.scale,frame.x,frame.y) == (1,0,0)


@pytest.mark.parametrize('size', [(1200,800),(800,1200),(1000,1000),(2400,600)])
def test_strength_and_resize(size):
    for effect in EFFECTS.values():
        for viewport in ((960,540), (1920,1080), (3840,2160)):
            stationary = effect.evaluate(.5, size, viewport, 0)
            assert (stationary.scale,stationary.x,stationary.y) == (1,0,0)
            full = effect.evaluate(.5,size,viewport)
            half = effect.evaluate(.5,size,viewport,50)
            assert half.scale == pytest.approx((1+full.scale)/2)
            assert half.x == pytest.approx(full.x/2)
            assert half.opacity == stationary.opacity == full.opacity


@pytest.mark.parametrize('data', [None, [], {'duration':False,'strength':float('nan'),'repeat':0}, {'duration':601,'strength':101}])
def test_settings_invalid_individual_defaults(data):
    assert SlideshowSettings.from_dict(data) == SlideshowSettings()
    assert SlideshowSettings.from_dict({'duration':12,'strength':'bad','shuffle':False}).to_dict()['duration'] == 12


class Loader(QObject):
    ready = pyqtSignal(int, object)
    failed = pyqtSignal(int,str)

    def __init__(self):
        super().__init__()
        self.requests = []
        self.closed = False

    def request(self, path, token, current=True):
        self.requests.append((path,token,current))

    def cancel_pending(self):
        pass

    def close(self):
        self.closed = True

    def deliver(self, request):
        self.ready.emit(request[1], SimpleNamespace(path=request[0],image=QImage(20,10,QImage.Format.Format_RGB32)))


def controller(paths=('a','b','c'), *, shuffle=False, repeat=False):
    loader = Loader()
    now = [0.0]
    c = SlideshowController(paths, paths[0] if paths else '', SlideshowSettings(10,100,shuffle,repeat,False), loader,
                            clock=lambda:now[0],rng=random.Random(41))
    c.start()
    return c,loader,now


def present(c,loader):
    request = next(r for r in reversed(loader.requests) if r[2])
    loader.deliver(request)


def test_pause_and_decode_latency():
    c,loader,now = controller()
    now[0]=30
    assert c.progress == 0
    present(c,loader)
    now[0]=34
    c.pause()
    now[0]=100
    assert c.progress == .4
    c.resume()
    now[0]=106
    c.tick()
    assert c.entry.path == 'b'
    assert c.progress == 0
    now[0]=500
    present(c,loader)
    assert c.progress == 0
    now[0]=502
    assert c.progress == .2


def test_resolution_upgrade_preserves_motion_clock_and_effect():
    c,loader,now = controller()
    present(c,loader)
    entry=c.entry
    frames=[]
    c.frameUpdated.connect(frames.append)
    now[0]=4
    c.refresh_image()
    present(c,loader)
    assert frames and c.entry == entry and c.progress == .4


def test_history_retains_effect_and_paused_navigation():
    c,loader,now = controller()
    present(c,loader)
    first = c.entry
    c.next();present(c,loader)
    second = c.entry
    c.pause();c.previous();present(c,loader)
    assert c.entry == first and not c.playing and c.progress == 0
    c.next();present(c,loader)
    assert c.entry == second and not c.playing


def test_shuffle_cycles_and_repeat_boundary():
    c,loader,now = controller(shuffle=True,repeat=True)
    paths=[]
    for _ in range(12):
        present(c,loader);paths.append(c.entry.path);c.next()
    assert paths[0] == 'a'
    for i in range(0,12,3):
        assert set(paths[i:i+3]) == {'a','b','c'}
        if i: assert paths[i-1] != paths[i]


def test_end_and_single_repeat():
    c,loader,now = controller(('a',))
    present(c,loader);now[0]=10;c.tick()
    assert c.progress == 1 and c.state == 'paused'
    c,loader,now = controller(('a',),repeat=True)
    present(c,loader);now[0]=10;c.tick();present(c,loader)
    assert c.progress == 0 and c.playing


def test_empty_all_failed_and_late_results():
    c,loader,now = controller(())
    assert c.state == 'stopped'
    c,loader,now = controller(repeat=True)
    errors=[]
    c.error.connect(errors.append)
    for _ in range(3):
        loader.failed.emit(c._token,c.entry.path)
    assert c.state == 'stopped' and errors == ['all_failed']
    c,loader,now = controller()
    stale=loader.requests[-1]
    c.next();loader.deliver(stale)
    assert c._waiting
    c.close();present(c,loader)
    assert loader.closed and c.state == 'stopped'


def test_raster_player_close_releases_resources(qapp):
    from image_classifier.slideshow.player import PlayerWindow
    window = PlayerWindow(('missing',),'missing',SlideshowSettings(fullscreen=False),raster=True)
    window.show();qapp.processEvents()
    window.close()
    assert window.controller._closed
    assert window.surface.pixmap is None


def test_real_shared_loader_handles_sources_smaller_than_preview(qapp,tmp_path):
    import time
    from PIL import Image
    from image_classifier.slideshow.loading import SlideLoader
    path = tmp_path/'small.jpg'
    Image.new('RGB',(80,60),'red').save(path)
    loader = SlideLoader()
    results=[]
    loader.ready.connect(lambda token,frame:results.append((token,frame)))
    loader.request(str(path),7)
    deadline=time.monotonic()+5
    while not results and time.monotonic()<deadline:
        qapp.processEvents()
        time.sleep(.005)
    assert len(results)==1 and results[0][0]==7
    assert not results[0][1].image.isNull()
    loader.close()


def test_disabling_repeat_discards_preloaded_next_cycle():
    c,loader,now = controller(('a',),repeat=True)
    present(c,loader)
    c.set_settings(SlideshowSettings(10,100,False,False,False))
    now[0]=10;c.tick()
    assert c.state == 'paused' and c.progress == 1


def test_settings_during_loading_do_not_cancel_the_incoming_frame():
    c,loader,now=controller()
    incoming=loader.requests[-1]
    cancellations=[]
    loader.cancel_pending=lambda:cancellations.append(True)
    c.pause()
    c.set_settings(SlideshowSettings(20,50,True,False,False))
    assert not cancellations
    loader.deliver(incoming)
    assert not c._waiting and c.entry.path == 'a' and not c.playing
    assert c.active_settings.duration == 10


def test_failed_final_candidate_ends_without_loading_forever():
    c,loader,now = controller(('a','b'))
    present(c,loader)
    c.next()
    loader.failed.emit(c._token,'b')
    assert c.state == 'paused' and not c._waiting and c.progress == 1


def test_deleted_preloaded_file_is_rejected(qapp,tmp_path):
    import time
    from image_classifier.slideshow.loading import SlideLoader
    loader=SlideLoader()
    failures=[]
    loader.failed.connect(lambda token,path:failures.append((token,path)))
    loader.request(str(tmp_path/'removed.jpg'),19)
    deadline=time.monotonic()+5
    while not failures and time.monotonic()<deadline:
        qapp.processEvents()
        time.sleep(.005)
    assert failures == [(19,str(tmp_path/'removed.jpg'))]
    loader.close()


def test_unavailable_opengl_uses_shared_raster_surface(qapp,monkeypatch):
    import image_classifier.slideshow.surface as module
    def unavailable(*args,**kwargs):
        raise RuntimeError('No OpenGL context')
    monkeypatch.setattr(module,'GLSurface',unavailable)
    surface=module.SlideSurface()
    assert isinstance(surface.canvas,module.RasterSurface)
    events=[]
    surface.fallbackActivated.connect(lambda:events.append(True))
    surface.show();qapp.processEvents()
    assert events == [True]
    surface.close()


def test_real_missing_and_corrupt_files_stop_without_repeating(qapp,tmp_path):
    import time
    from image_classifier.slideshow.loading import SlideLoader
    bad=tmp_path/'corrupt.jpg'
    bad.write_bytes(b'not a photograph')
    paths=(str(tmp_path/'removed.jpg'),str(bad))
    loader=SlideLoader()
    c=SlideshowController(paths,paths[0],SlideshowSettings(repeat=True),loader)
    errors=[];skips=[]
    c.error.connect(errors.append);c.skipped.connect(skips.append)
    c.start()
    deadline=time.monotonic()+5
    while not errors and time.monotonic()<deadline:
        qapp.processEvents()
        time.sleep(.005)
    assert errors == ['all_failed'] and set(skips) == set(paths)
    assert c.state == 'stopped'
    c.close()

