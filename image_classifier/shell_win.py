"""Windows Shell integration (COM, Shell32). Only used on Windows."""
import ctypes
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


def open_folder_and_select_item(file_path: str) -> None:
    """Open Explorer and select the given file. Raises OSError on failure."""
    from ctypes import byref, POINTER, c_ulong
    full_pidl = POINTER(c_ulong)()
    hr = SHParseDisplayName(
        LPCWSTR(file_path), None, byref(full_pidl), UINT(0), None
    )
    if hr != 0:
        raise OSError(f"SHParseDisplayName failed (0x{hr & 0xFFFFFFFF:08X})")
    hr2 = SHOpenFolderAndSelectItems(
        full_pidl, UINT(0), None, UINT(0)
    )
    if hr2 != 0:
        raise OSError(f"SHOpenFolderAndSelectItems failed (0x{hr2 & 0xFFFFFFFF:08X})")
