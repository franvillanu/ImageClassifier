"""Executable form of docs/specs/SPEC-001-fullscreen-and-modals.md.

Every test names the requirement it proves (FS-n / OV-n) in its docstring and in
``REQUIRES``; tests/test_spec_traceability.py fails if a requirement has no test.
"""
import json
import sys
import types

import pytest
from PIL import Image
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QApplication

if sys.platform != "win32":
    _stub = types.ModuleType("image_classifier.shell_win")
    _stub.open_folder_and_select_item = lambda *args, **kwargs: None
    sys.modules.setdefault("image_classifier.shell_win", _stub)

REQUIRES = ["FS-1", "FS-2", "FS-3", "FS-4", "OV-1", "OV-2", "OV-3"]


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    import image_classifier.app as app_module

    config = tmp_path / "viewer_config.json"
    config.write_text(json.dumps({"last_seen_version": app_module.__version__}))
    monkeypatch.setattr(app_module, "get_config_file", lambda: str(config))
    photos = tmp_path / "photos"
    photos.mkdir()
    for index in range(3):
        Image.new("RGB", (800, 600), (40 * index, 90, 140)).save(photos / f"p{index}.jpg")
    win = app_module.PhotoViewer()
    win.resize(900, 650)
    win.show()
    win.load_directory(str(photos), start_at_first=True)
    qapp.processEvents()
    yield win
    win.image_viewer._cancel_pending_loads()
    win._cancel_preloads()
    win._marked_save_timer.stop()
    win.close()


def _top_level_windows():
    return {w for w in QApplication.topLevelWidgets() if w.isVisible()}


def test_fs1_fullscreen_creates_no_extra_top_level_window(window, qapp):
    """FS-1: no cover/helper window is created while changing fullscreen state."""
    before = _top_level_windows()
    seen = set()
    window.toggle_fullscreen()
    seen |= _top_level_windows()
    qapp.processEvents()
    seen |= _top_level_windows()
    window.toggle_fullscreen()
    seen |= _top_level_windows()
    qapp.processEvents()
    seen |= _top_level_windows()
    assert {type(w).__name__ for w in seen - before} == set()
    assert not hasattr(window, "create_screenshot_cover")


def test_fs2_exit_restores_maximized_state_in_one_step(window, qapp):
    """FS-2: leaving fullscreen returns to maximized when it was maximized."""
    window.showMaximized()
    qapp.processEvents()
    assert window.isMaximized()
    window.toggle_fullscreen()
    qapp.processEvents()
    assert window.isFullScreen() and window.is_fullscreen
    window.toggle_fullscreen()
    qapp.processEvents()
    assert not window.isFullScreen() and not window.is_fullscreen
    assert window.isMaximized()


def test_fs2_exit_restores_normal_geometry(window, qapp):
    """FS-2: leaving fullscreen from a normal window restores its exact geometry."""
    window.showNormal()
    window.setGeometry(120, 90, 900, 650)
    qapp.processEvents()
    geometry = window.geometry()
    window.toggle_fullscreen()
    qapp.processEvents()
    window.toggle_fullscreen()
    qapp.processEvents()
    assert not window.isFullScreen() and not window.isMaximized()
    assert window.geometry() == geometry


def test_fs3_exit_button_only_in_fullscreen_and_escape_leaves(window, qapp):
    """FS-3: the exit button exists only in fullscreen; exit_fullscreen() leaves it."""
    assert not window.float_exit.isVisible()
    window.toggle_fullscreen()
    qapp.processEvents()
    assert window.float_exit.isVisible()
    window.exit_fullscreen()
    qapp.processEvents()
    assert not window.isFullScreen()
    assert not window.float_exit.isVisible()


def test_fs4_updates_are_always_re_enabled(window, qapp, monkeypatch):
    """FS-4: the repaint freeze during the state change is lifted even if a step raises."""
    window.toggle_fullscreen()
    qapp.processEvents()
    assert window.updatesEnabled()

    def boom():
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(window, "update_floating_controls", boom)
    with pytest.raises(RuntimeError):
        window.toggle_fullscreen()
    assert window.updatesEnabled()


def test_ov1_settings_overlay_appears_complete_without_nested_event_loop(window, qapp, monkeypatch):
    """OV-1: Settings opens in one step: panel placed inside the overlay, no processEvents()."""
    calls = []
    monkeypatch.setattr(QApplication, "processEvents", staticmethod(lambda *a, **k: calls.append(1)))
    monkeypatch.setattr(QCoreApplication, "processEvents", staticmethod(lambda *a, **k: calls.append(1)))
    window.open_settings_overlay()
    overlay = window.settings_overlay
    assert calls == []
    assert overlay.isVisible()
    panels = [c for c in overlay.children() if hasattr(c, "preferred_height")]
    assert len(panels) == 1
    panel = panels[0]
    assert panel.isVisible()
    assert overlay.rect().contains(panel.geometry())


def test_ov2_overlays_and_tooltips_are_children_of_the_main_window(window, qapp):
    """OV-2: overlays are child widgets, so they never take activation from a fullscreen window."""
    window.toggle_fullscreen()
    qapp.processEvents()
    window.open_settings_overlay()
    qapp.processEvents()
    overlay = window.settings_overlay
    assert not overlay.isWindow()
    assert overlay.parentWidget() is window
    from image_classifier.ui.dialogs import CustomTooltip

    tip = CustomTooltip("tip", parent=window)
    assert not tip.isWindow() and tip.parentWidget() is window
    assert window.isFullScreen()
    window.close_settings_overlay()
    window.toggle_fullscreen()


def test_ov3_closing_settings_restores_menu_and_shortcuts(window, qapp):
    """OV-3: closing Settings leaves no overlay behind and the floating menu is usable again."""
    window.open_settings_overlay()
    qapp.processEvents()
    assert not window.floating_menu.isEnabled()
    window.close_settings_overlay()
    qapp.processEvents()
    assert window.settings_overlay is None
    assert window.floating_menu.isEnabled()
