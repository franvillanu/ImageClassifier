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

REQUIRES = ["FS-1", "FS-2", "FS-3", "FS-4", "OV-1", "OV-2", "OV-3", "EP-1", "EP-2", "EP-3", "EP-4", "FS-5", "FS-7", "FS-8", "FS-9"]


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


def _paint_waves(qapp, window, action, settle_ms=120):
    """Run ``action`` and count Paint events delivered to the main window itself (EP-1 helper)."""
    from PyQt6.QtCore import QEvent, QObject
    import time

    class Counter(QObject):
        paints = 0

        def eventFilter(self, obj, event):
            if obj is window and event.type() == QEvent.Type.Paint:
                Counter.paints += 1
            return False

    counter = Counter()
    qapp.installEventFilter(counter)
    try:
        action()
        end = time.monotonic() + settle_ms / 1000
        while time.monotonic() < end:
            qapp.processEvents()
            time.sleep(0.005)
    finally:
        qapp.removeEventFilter(counter)
    return Counter.paints


def test_ep1_message_has_no_animation_effect(window, qapp):
    """EP-1: a message uses no opacity effect and no property animation, so it repaints only on show/hide."""
    window.show_ephemeral_message("Loop on", duration_ms=50)
    popup = window.ephemeral_messages[0]
    assert popup.graphicsEffect() is None
    assert not hasattr(popup, "fade_anim")
    from PyQt6.QtCore import QPropertyAnimation

    assert popup.findChildren(QPropertyAnimation) == []
    window._fade_out_popup(popup)


def test_ep1_message_total_paints_stay_small(window, qapp):
    """EP-1: showing and hiding a message repaints the window a handful of times, not dozens."""
    paints = _paint_waves(qapp, window, lambda: window.show_ephemeral_message("Loop on", duration_ms=60), settle_ms=400)
    assert paints <= 8, paints  # was 26 with the fade animations


def test_ep2_message_is_content_sized_child_and_click_through(window, qapp):
    """EP-2: the popup is small, a child of the window and transparent for mouse events."""
    window.show_ephemeral_message("Loop on", duration_ms=5000)
    popup = window.ephemeral_messages[0]
    assert not popup.isWindow() and popup.parentWidget() is window
    assert popup.width() < window.width() // 2 and popup.height() < window.height() // 4
    assert popup.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    window._fade_out_popup(popup)


def test_ep3_messages_stack_without_overlap_and_centred(window, qapp):
    """EP-3: simultaneous messages are centred, stacked and never overlap."""
    window.show_ephemeral_message("first", duration_ms=5000)
    window.show_ephemeral_message("second message", duration_ms=5000)
    qapp.processEvents()
    a, b = window.ephemeral_messages[0], window.ephemeral_messages[1]
    assert a is not b
    assert not a.geometry().intersects(b.geometry())
    for popup in (a, b):
        assert abs(popup.geometry().center().x() - window.width() // 2) <= 1
    for popup in list(window.ephemeral_messages):
        window._fade_out_popup(popup)


def test_ep4_message_is_removed_and_deleted_after_duration(window, qapp):
    """EP-4: after its duration the popup is gone and the stack holds no stale entries."""
    import time

    window.show_ephemeral_message("bye", duration_ms=30)
    popup = window.ephemeral_messages[0]
    deadline = time.monotonic() + 1.0
    while window.ephemeral_messages and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    assert window.ephemeral_messages == []
    from PyQt6 import sip

    assert sip.isdeleted(popup) or not popup.isVisible()


def test_fs5_own_windows_do_not_trigger_click_away(window, qapp, monkeypatch):
    """FS-5: with another window of this app active, a deactivation does not leave fullscreen."""
    window.toggle_fullscreen()
    qapp.processEvents()
    assert window.isFullScreen()
    from PyQt6.QtWidgets import QDialog

    other = QDialog()
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: other))
    window._leave_fullscreen_clickaway()
    qapp.processEvents()
    assert window.isFullScreen()
    window.exit_fullscreen()


def test_fs5_losing_focus_to_another_application_leaves_fullscreen(window, qapp, monkeypatch):
    """FS-5: with no window of this app active (focus went elsewhere) click-away still exits."""
    window.toggle_fullscreen()
    qapp.processEvents()
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: None))
    window._leave_fullscreen_clickaway()
    qapp.processEvents()
    assert not window.isFullScreen()


def test_fs5_slideshow_launch_keeps_main_fullscreen(window, qapp, monkeypatch):
    """FS-5: the main window is still fullscreen with the slideshow open, and after it closes."""
    from PyQt6.QtWidgets import QDialog

    window.toggle_fullscreen()
    qapp.processEvents()
    player_stub = QDialog(window)
    player_stub.show()
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: player_stub))
    window.event(__import__("PyQt6.QtCore", fromlist=["QEvent"]).QEvent(
        __import__("PyQt6.QtCore", fromlist=["QEvent"]).QEvent.Type.WindowDeactivate))
    import time

    end = time.monotonic() + 0.15
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)
    assert window.isFullScreen()
    player_stub.close()
    assert window.isFullScreen()
    window.exit_fullscreen()


def test_fs7_border_flag_is_set_before_first_show(monkeypatch, qapp):
    """FS-7: the helper creates the native window, sets Qt's border-in-fullscreen flag and recreates it."""
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtWidgets import QWidget
    from image_classifier.ui import fullscreen_border as fb

    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "windows"))
    widget = QWidget()
    assert fb.enable_border_in_fullscreen(widget) is True
    assert fb.has_border_in_fullscreen(widget)
    widget.show()
    with pytest.raises(RuntimeError):
        fb.enable_border_in_fullscreen(widget)  # too late once shown: the flag is read at creation
    widget.close()


def test_fs7_main_window_and_player_have_the_flag(window, qapp, tmp_path, monkeypatch):
    """FS-7: both OpenGL windows (main viewer, slideshow player) are created with the flag on Windows."""
    import image_classifier.app as app_module
    import image_classifier.slideshow.player as player_module
    from image_classifier.slideshow.settings import SlideshowSettings

    calls = []
    monkeypatch.setattr(app_module, "enable_border_in_fullscreen", lambda w: calls.append(("main", w.isVisible())))
    monkeypatch.setattr(player_module, "enable_border_in_fullscreen", lambda w: calls.append(("player", w.isVisible())))
    main = app_module.PhotoViewer()
    path = tmp_path / "s.jpg"
    Image.new("RGB", (400, 300), (90, 90, 90)).save(path)
    player = player_module.PlayerWindow([str(path)], str(path), SlideshowSettings(3, 100, False, True, True), raster=True)
    assert ("main", False) in calls and ("player", False) in calls  # applied before the first show
    player.close()
    main._marked_save_timer.stop()
    main.close()


def _msg(message_id):
    import ctypes
    import ctypes.wintypes as wt

    msg = wt.MSG()
    msg.message = message_id
    return msg, ctypes.addressof(msg)


class _FsWidget:
    def __init__(self, fullscreen):
        self.fs = fullscreen

    def isFullScreen(self):
        return self.fs

    def winId(self):
        return 42


def test_fs8_frame_painted_in_background_colour_while_fullscreen():
    """FS-8: WM_NCPAINT and WM_NCACTIVATE paint the frame in the given colour while fullscreen."""
    from image_classifier.ui import fullscreen_border as fb

    painted = []
    painter = lambda hwnd, color: painted.append((hwnd, color))
    keep_paint, address = _msg(fb.WM_NCPAINT)
    assert fb.handle_frame_message(_FsWidget(True), address, "#212121", painter) == (True, 0)
    keep_act, address = _msg(fb.WM_NCACTIVATE)
    assert fb.handle_frame_message(_FsWidget(True), address, "#212121", painter) == (True, 1)
    assert painted == [(42, "#212121"), (42, "#212121")]
    assert fb.colorref("#212121") == 0x212121 and fb.colorref("#1A202C") == 0x2C201A


def test_fs8_frame_left_to_windows_when_not_fullscreen_or_other_message():
    """FS-8: windowed/maximized frames and unrelated messages are untouched; errors never escape."""
    from image_classifier.ui import fullscreen_border as fb

    painted = []
    keep, address = _msg(fb.WM_NCPAINT)
    assert fb.handle_frame_message(_FsWidget(False), address, "#000000", lambda *a: painted.append(a)) is None
    keep2, address2 = _msg(0x000F)  # WM_PAINT
    assert fb.handle_frame_message(_FsWidget(True), address2, "#000000", lambda *a: painted.append(a)) is None
    assert painted == []

    def boom(*_):
        raise OSError("gdi failure")

    assert fb.handle_frame_message(_FsWidget(True), address, "#000000", boom) is None


def test_fs8_both_windows_route_native_events_through_the_frame_handler(window, qapp, monkeypatch):
    """FS-8: the main window (theme colour) and the player (black) hand frame messages to the handler."""
    import image_classifier.app as app_module
    import image_classifier.slideshow.player as player_module

    seen = []
    monkeypatch.setattr(app_module, "handle_frame_message", lambda w, m, c: seen.append(("main", c)) or (True, 0))
    monkeypatch.setattr(player_module, "handle_frame_message", lambda w, m, c: seen.append(("player", c)) or (True, 0))
    assert window.nativeEvent(b"windows_generic_MSG", 0) == (True, 0)
    assert player_module.PlayerWindow.nativeEvent(window, b"windows_generic_MSG", 0) == (True, 0)
    assert ("main", window.image_viewer.bg_color) in seen and ("player", "#000000") in seen


def test_fs9_exit_to_maximized_uses_work_area_then_restores_normal_rect(window, qapp, monkeypatch):
    """FS-9: entering from maximized sets the normal placement to the work area; once maximized
    again, the user's own normal rectangle is put back."""
    import image_classifier.app as app_module

    calls = []
    monkeypatch.setattr(app_module, "get_normal_rect", lambda hwnd: (100, 100, 1124, 868))
    monkeypatch.setattr(app_module, "work_area_rect", lambda hwnd: (0, 0, 3840, 2088))
    monkeypatch.setattr(app_module, "set_normal_rect", lambda hwnd, rect: calls.append(rect) or True)
    window.showMaximized()
    qapp.processEvents()
    window.toggle_fullscreen()
    qapp.processEvents()
    assert calls == [(0, 0, 3840, 2088)]
    window.toggle_fullscreen()
    for _ in range(20):
        qapp.processEvents()
    assert window.isMaximized()
    assert calls == [(0, 0, 3840, 2088), (100, 100, 1124, 868)]
    assert window._fs_restore_normal_rect is None


def test_fs9_normal_rect_restore_waits_until_really_maximized(window, qapp, monkeypatch):
    """FS-9: the restore does not run while the window is not maximized yet (Qt reports it late)."""
    import image_classifier.app as app_module

    calls = []
    monkeypatch.setattr(app_module, "set_normal_rect", lambda hwnd, rect: calls.append(rect) or True)
    window.showNormal()
    qapp.processEvents()
    window._fs_restore_normal_rect = (1, 2, 3, 4)
    window._restore_normal_rect_if_maximized()
    assert calls == [] and window._fs_restore_normal_rect == (1, 2, 3, 4)
    window.showMaximized()
    for _ in range(10):
        qapp.processEvents()
    assert calls == [(1, 2, 3, 4)]
