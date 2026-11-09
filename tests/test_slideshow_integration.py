"""Playlist boundary, classifier state, config preservation and modal controls."""
import json

import pytest
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QDialog
from image_classifier.slideshow.settings import SlideshowSettings


@pytest.fixture
def classifier(qapp,tmp_path,monkeypatch):
    import image_classifier.app as app_module
    path = tmp_path/'viewer_config.json'
    path.write_text(json.dumps({'future_field':{'keep':42},'slideshow':{'duration':12,'strength':'invalid','shuffle':False,'repeat':False,'fullscreen':False,'future_option':42}}))
    monkeypatch.setattr(app_module,'get_config_file',lambda:str(path))
    window = app_module.PhotoViewer()
    yield window
    player = getattr(window,'_slideshow_player',None)
    if player is not None: player.close()
    window._cancel_preloads()
    window.image_viewer._cancel_pending_loads()
    window._marked_save_timer.stop()
    window.hide()
    window.deleteLater()
    qapp.processEvents()


def test_snapshot_filtered_list_and_preserved_classifier_state(classifier,monkeypatch,qapp,tmp_path):
    from PIL import Image
    import image_classifier.slideshow.player as player_module
    paths=[]
    for i in range(3):
        path=tmp_path/f'{i}.jpg';Image.new('RGB',(80,60),'blue').save(path);paths.append(str(path))
    classifier.image_files=paths[1:]
    classifier.current_index=1
    classifier.current_filter='favorites'
    classifier.image_viewer.zoom_factor=1.7
    classifier.image_viewer.setTransform(QTransform().scale(1.7,1.7))
    real_player=player_module.PlayerWindow
    monkeypatch.setattr(player_module,'PlayerWindow',lambda *a,**kw:real_player(*a,**kw,raster=True))
    monkeypatch.setattr(player_module.SettingsDialog,'exec',lambda self:QDialog.DialogCode.Accepted)
    classifier.open_slideshow()
    player=classifier._slideshow_player
    assert player.controller.playlist == tuple(paths[1:])
    assert player.controller.starting_image == paths[2]
    assert player.windowModality() == Qt.WindowModality.WindowModal
    classifier.image_files.append('later')
    assert 'later' not in player.controller.playlist
    classifier.open_slideshow()
    assert classifier._slideshow_player is player
    qapp.processEvents()
    player.close()
    assert classifier._slideshow_player is None
    assert classifier.current_index == 1
    assert classifier.image_viewer.zoom_factor == 1.7
    assert classifier.image_viewer.transform().m11() == 1.7


def test_cancel_and_config_round_trip(classifier,monkeypatch):
    import image_classifier.slideshow.player as player_module
    classifier.image_files=['a']
    classifier.current_index=0
    monkeypatch.setattr(player_module.SettingsDialog,'exec',lambda self:QDialog.DialogCode.Rejected)
    classifier.open_slideshow()
    assert getattr(classifier,'_slideshow_player',None) is None
    assert classifier.slideshow_settings.duration == 12
    assert classifier.slideshow_settings.strength == 100
    classifier._save_slideshow_settings(SlideshowSettings(22,50,False,True,False))
    saved=json.loads(open(classifier.config_file,encoding='utf-8').read())
    assert saved['future_field'] == {'keep':42}
    assert saved['slideshow']['future_option'] == 42
    classifier.load_config()
    assert classifier.slideshow_settings == SlideshowSettings(22,50,False,True,False)


def test_displayed_path_wins_over_legacy_negative_index(classifier,monkeypatch):
    import image_classifier.slideshow.player as module
    real_player=module.PlayerWindow
    monkeypatch.setattr(module,'PlayerWindow',lambda *a,**kw:real_player(*a,**kw,raster=True))
    monkeypatch.setattr(module.SettingsDialog,'exec',lambda self:QDialog.DialogCode.Accepted)
    classifier.image_files=['first','last']
    classifier.current_index=-1
    classifier._current_path='last'
    classifier.open_slideshow()
    assert classifier._slideshow_player.controller.starting_image == 'last'
    classifier._slideshow_player.close()


def test_settings_restore_previous_pause_state(qapp,monkeypatch):
    from image_classifier.slideshow.player import PlayerWindow,SettingsDialog
    window=PlayerWindow(('missing',),'missing',SlideshowSettings(fullscreen=False),raster=True)
    # Use deterministic loading here: the actual shared decoder is exercised in
    # test_slideshow; this test isolates nested-dialog pause restoration.
    window.controller.state='playing'
    window.controller.playing=True
    monkeypatch.setattr(SettingsDialog,'exec',lambda self:QDialog.DialogCode.Rejected)
    window.open_settings()
    assert window.controller.playing
    window.controller.pause()
    window.open_settings()
    assert not window.controller.playing
    window.close()


def test_repeated_player_close_cancels_resources(qapp):
    from image_classifier.slideshow.player import PlayerWindow
    for _ in range(12):
        player=PlayerWindow(('missing',),'missing',SlideshowSettings(fullscreen=False),raster=True)
        player.show()
        qapp.processEvents()
        loader=player.loader
        player.close()
        assert loader._closed and not loader._jobs and not loader._frames
        qapp.processEvents()


def test_sleep_prevention_covers_loading_and_releases_on_pause(qapp,monkeypatch):
    from image_classifier.slideshow.player import PlayerWindow
    player=PlayerWindow(('missing',),'missing',SlideshowSettings(fullscreen=False),raster=True)
    calls=[]
    monkeypatch.setattr(player,'_prevent_sleep',calls.append)
    player.controller.playing=True
    player.controller._state('loading')
    player.controller.pause()
    assert calls[-2:] == [True,False]
    player.close()
