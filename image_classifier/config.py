"""Config path and defaults. No Qt dependency."""
import os
from PyQt6.QtCore import QStandardPaths

APP_NAME = "Image Classifier"


def get_config_dir() -> str:
    """Writable config directory (e.g. %%LocalAppData%%\\Image Classifier)."""
    path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    # Use app name for subfolder if the path is generic
    if "Image Classifier" not in path:
        path = os.path.join(path, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def get_config_file() -> str:
    """Full path to viewer_config.json."""
    return os.path.join(get_config_dir(), "viewer_config.json")


DEFAULT_CONFIG = {
    "load_last_folder": False,
    "last_directory": None,
    "show_all_images": True,
    "reset_zoom_on_new_image": True,
    "show_filename": False,
    "current_language": "en",
    "rotate_all": False,
    "menu_dock_left": True,
    "loop_navigation": False,
    "last_index": 0,
    "sort_option": "file_name",
    "sort_ascending": True,
    "theme": "black",
}
