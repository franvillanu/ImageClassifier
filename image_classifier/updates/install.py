"""Launch the downloaded installer elevated and silently."""

from __future__ import annotations

import sys

SHELL_EXECUTE_OK = 32


def installer_arguments(lang: str) -> str:
    inno_lang = "spanish" if lang == "es" else "english"
    return f"/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /UPDATE=1 /LANG={inno_lang}"


def launch_installer(path: str, lang: str = "en") -> bool:
    """Run the installer via ShellExecute (it needs admin, so CreateProcess fails with 740).

    Returns True only if Windows started it; False if the user declined UAC.
    """
    if sys.platform != "win32":
        return False
    import ctypes

    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", path, installer_arguments(lang), None, 1
    )
    return int(result) > SHELL_EXECUTE_OK
