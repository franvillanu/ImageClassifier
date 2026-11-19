"""Windows Shell integration (COM, Shell32). Only used on Windows."""
import ctypes
import subprocess
from ctypes import POINTER, c_ulong, c_void_p
from ctypes.wintypes import LPCWSTR, UINT

# Initialize COM once when module is loaded
try:
    ctypes.windll.ole32.CoInitialize(None)
except Exception:
    pass

HRESULT = ctypes.c_long


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


IID_IShellFolder = GUID(
    0x000214E6, 0x0000, 0x0000,
    (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46),
)

SHParseDisplayName = ctypes.windll.shell32.SHParseDisplayName
SHParseDisplayName.argtypes = [
    LPCWSTR, ctypes.c_void_p,
    POINTER(POINTER(c_ulong)), UINT, ctypes.POINTER(UINT),
]
SHParseDisplayName.restype = HRESULT

SHBindToParent = ctypes.windll.shell32.SHBindToParent
SHBindToParent.argtypes = [
    c_void_p, ctypes.POINTER(GUID),
    ctypes.POINTER(c_void_p), ctypes.POINTER(c_void_p),
]
SHBindToParent.restype = HRESULT

SHOpenFolderAndSelectItems = ctypes.windll.shell32.SHOpenFolderAndSelectItems
SHOpenFolderAndSelectItems.argtypes = [c_void_p, UINT, ctypes.POINTER(c_void_p), UINT]
SHOpenFolderAndSelectItems.restype = HRESULT


CoTaskMemFree = ctypes.windll.ole32.CoTaskMemFree
CoTaskMemFree.argtypes = [c_void_p]
CoTaskMemFree.restype = None

SHELL_ATTEMPTS = 2


def _shell_select(file_path: str) -> bool:
    """Ask the Shell to open the folder with the file selected (SPEC-006 EX-1, EX-3)."""
    full_pidl = POINTER(c_ulong)()
    hr = SHParseDisplayName(LPCWSTR(file_path), None, ctypes.byref(full_pidl), UINT(0), None)
    if hr != 0:
        return False
    try:
        for _ in range(SHELL_ATTEMPTS):
            if SHOpenFolderAndSelectItems(full_pidl, UINT(0), None, UINT(0)) == 0:
                return True
        return False
    finally:
        CoTaskMemFree(full_pidl)


def open_folder_and_select_item(file_path: str) -> None:
    """Open Explorer on the file's folder with the file selected.

    SHOpenFolderAndSelectItems fails intermittently with E_FAIL for paths that work a moment later,
    so it is retried once and then explorer.exe /select is used (SPEC-006 EX-2).
    Raises OSError only if explorer.exe cannot be started either.
    """
    if _shell_select(file_path):
        return
    # Explorer parses its own command line: the /select argument must be passed as one raw string.
    subprocess.Popen(f'explorer.exe /select,"{file_path}"')
