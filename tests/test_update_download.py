import hashlib
import io
import os

import pytest

from image_classifier.updates.check import DOWNLOAD_PREFIX, UpdateOffer
from image_classifier.updates.download import DownloadCancelled, download_installer

NAME = "ImageClassifierSetup_v2.0.8.exe"
URL = f"{DOWNLOAD_PREFIX}v2.0.8/{NAME}"
PAYLOAD = b"x" * 200_000


class FakeResponse(io.BytesIO):
    def __init__(self, data, length=None):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data) if length is None else length)}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def opener(data=PAYLOAD, length=None):
    return lambda url, timeout=None: FakeResponse(data, length)


def offer(**kw):
    return UpdateOffer(version="2.0.8", url=kw.pop("url", URL), name=kw.pop("name", NAME), **kw)


def test_downloads_reports_progress_and_renames(tmp_path):
    seen = []
    path = download_installer(
        offer(), str(tmp_path), lambda got, total: seen.append((got, total)), opener=opener()
    )
    assert os.path.basename(path) == NAME
    assert open(path, "rb").read() == PAYLOAD
    assert seen[-1] == (len(PAYLOAD), len(PAYLOAD))
    assert [g for g, _ in seen] == sorted(g for g, _ in seen)
    assert not os.path.exists(path + ".part")


def test_good_digest_accepted(tmp_path):
    digest = "sha256:" + hashlib.sha256(PAYLOAD).hexdigest()
    assert download_installer(offer(digest=digest), str(tmp_path), opener=opener())


def test_digest_mismatch_deletes_file(tmp_path):
    with pytest.raises(IOError):
        download_installer(offer(digest="sha256:" + "0" * 64), str(tmp_path), opener=opener())
    assert os.listdir(tmp_path) == []


def test_incomplete_download_deleted(tmp_path):
    with pytest.raises(IOError):
        download_installer(offer(), str(tmp_path), opener=opener(length=len(PAYLOAD) + 10))
    assert os.listdir(tmp_path) == []


def test_cancel_removes_partial(tmp_path):
    calls = {"n": 0}

    def cancelled():
        calls["n"] += 1
        return calls["n"] > 1

    with pytest.raises(DownloadCancelled):
        download_installer(offer(), str(tmp_path), is_cancelled=cancelled, opener=opener())
    assert os.listdir(tmp_path) == []


def test_bad_url_or_name_rejected(tmp_path):
    with pytest.raises(ValueError):
        download_installer(offer(url="https://evil.example/" + NAME), str(tmp_path), opener=opener())
    with pytest.raises(ValueError):
        download_installer(
            offer(name="evil.exe", url=f"{DOWNLOAD_PREFIX}v2.0.8/evil.exe"),
            str(tmp_path),
            opener=opener(),
        )
