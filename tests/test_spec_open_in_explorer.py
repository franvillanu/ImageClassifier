"""SPEC-006 — Open in Explorer (docs/specs/SPEC-006-open-in-explorer.md)."""
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows Shell only")

if sys.platform == "win32":
    from image_classifier import shell_win


S_OK, E_FAIL = 0, -2147467259  # 0x80004005 as a signed HRESULT


class FakeShell:
    """Stands in for the Shell32/Ole32 calls and explorer.exe."""

    def __init__(self, monkeypatch, results, popen_error=None):
        self.results = list(results)
        self.calls = 0
        self.freed = []
        self.popen = []
        self.popen_error = popen_error
        monkeypatch.setattr(shell_win, "SHParseDisplayName", self._parse)
        monkeypatch.setattr(shell_win, "SHOpenFolderAndSelectItems", self._open)
        monkeypatch.setattr(shell_win, "CoTaskMemFree", self.freed.append)
        monkeypatch.setattr(shell_win.subprocess, "Popen", self._popen)

    def _parse(self, path, ctx, out, flags, attrs):
        return S_OK

    def _open(self, pidl, cidl, apidl, flags):
        self.calls += 1
        return self.results.pop(0) if self.results else S_OK

    def _popen(self, cmd, **kwargs):
        if self.popen_error:
            raise self.popen_error
        self.popen.append(cmd)


PATH = r"C:\Fotos\playa 1.jpg"


def test_ex1_shell_call_is_used_when_it_works(monkeypatch):
    """EX-1"""
    shell = FakeShell(monkeypatch, [S_OK])
    shell_win.open_folder_and_select_item(PATH)
    assert shell.calls == 1 and shell.popen == []


def test_ex1_shell_call_is_retried_once(monkeypatch):
    """EX-1"""
    shell = FakeShell(monkeypatch, [E_FAIL, S_OK])
    shell_win.open_folder_and_select_item(PATH)
    assert shell.calls == 2 and shell.popen == []


def test_ex2_falls_back_to_explorer_select_without_error(monkeypatch):
    """EX-2"""
    # The bug: two E_FAIL results used to raise OSError and show the error dialog.
    shell = FakeShell(monkeypatch, [E_FAIL, E_FAIL])
    shell_win.open_folder_and_select_item(PATH)
    assert shell.calls == 2
    assert shell.popen == [f'explorer.exe /select,"{PATH}"']


def test_ex2_error_only_when_explorer_cannot_start(monkeypatch):
    """EX-2"""
    FakeShell(monkeypatch, [E_FAIL, E_FAIL], popen_error=FileNotFoundError("explorer.exe"))
    with pytest.raises(OSError):
        shell_win.open_folder_and_select_item(PATH)


@pytest.mark.parametrize("results", [[S_OK], [E_FAIL, E_FAIL]])
def test_ex3_pidl_is_always_freed(monkeypatch, results):
    """EX-3"""
    shell = FakeShell(monkeypatch, results)
    shell_win.open_folder_and_select_item(PATH)
    assert len(shell.freed) == 1
