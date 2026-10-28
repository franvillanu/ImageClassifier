import pytest

from image_classifier.updates import check
from image_classifier.updates.check import (
    DOWNLOAD_PREFIX,
    check_for_update,
    newer_release,
    parse_version,
    release_from_tag,
)


def make_release(tag="v2.0.8", name=None, url=None, **extra):
    version = tag.lstrip("v")
    name = name or f"ImageClassifierSetup_v{version}.exe"
    url = url or f"{DOWNLOAD_PREFIX}{tag}/{name}"
    release = {"tag_name": tag, "assets": [{"name": name, "browser_download_url": url}]}
    release.update(extra)
    return release


def test_parse_version():
    assert parse_version("v2.0.7") == (2, 0, 7)
    assert parse_version("2.0.7") == (2, 0, 7)
    assert parse_version("v2.0") == (2, 0, 0)
    for junk in (None, "", "latest", "v2", "v2.0.7.1", "v2.0.x"):
        assert parse_version(junk) is None


def test_newer_equal_older():
    assert newer_release("2.0.7", make_release("v2.0.8")).version == "2.0.8"
    assert newer_release("2.0.8", make_release("v2.0.8")) is None
    assert newer_release("2.0.9", make_release("v2.0.8")) is None


def test_two_part_tag_is_not_newer_than_same_version():
    assert newer_release("2.0.0", make_release("v2.0")) is None
    assert newer_release("2.0.7", make_release("v2.0")) is None


def test_draft_and_prerelease_ignored():
    assert newer_release("2.0.7", make_release("v2.0.8", draft=True)) is None
    assert newer_release("2.0.7", make_release("v2.0.8", prerelease=True)) is None


def test_lookalike_repo_rejected():
    url = "https://github.com/franvillanu/imageclassifier-releases-evil/releases/download/v2.0.8/ImageClassifierSetup_v2.0.8.exe"
    assert newer_release("2.0.7", make_release("v2.0.8", url=url)) is None


def test_encoded_traversal_rejected():
    url = f"{DOWNLOAD_PREFIX}v2.0.8/..%2F..%2Fevil/ImageClassifierSetup_v2.0.8.exe"
    assert newer_release("2.0.7", make_release("v2.0.8", url=url)) is None


def test_missing_or_wrong_asset():
    assert newer_release("2.0.7", {"tag_name": "v2.0.8", "assets": []}) is None
    assert newer_release("2.0.7", make_release("v2.0.8", name="other.exe")) is None


def test_digest_and_size_passed_through():
    release = make_release("v2.0.8")
    release["assets"][0].update(digest="sha256:" + "a" * 64, size=1234)
    offer = newer_release("2.0.7", release)
    assert offer.digest == "sha256:" + "a" * 64
    assert offer.size == 1234


def test_release_from_tag_builds_usual_address():
    release = release_from_tag("v2.0.8")
    assert release["assets"][0]["browser_download_url"] == (
        f"{DOWNLOAD_PREFIX}v2.0.8/ImageClassifierSetup_v2.0.8.exe"
    )
    with pytest.raises(ValueError):
        release_from_tag("nonsense")


def test_check_available_and_current():
    result = check_for_update("2.0.7", lambda url: make_release("v2.0.8"))
    assert result["state"] == "available" and result["offer"].version == "2.0.8"
    assert check_for_update("2.0.8", lambda url: make_release("v2.0.8"))["state"] == "current"


def test_rate_limit_falls_back_to_releases_page():
    def boom(url):
        raise OSError("403")

    result = check_for_update("2.0.7", boom, lambda: "v2.0.8")
    assert result["state"] == "available"
    assert result["offer"].digest is None


def test_both_sources_failing_is_failed():
    def boom(*args):
        raise OSError("down")

    assert check_for_update("2.0.7", boom, boom)["state"] == "failed"


def test_offline_env_var(monkeypatch):
    monkeypatch.setenv("IMAGE_CLASSIFIER_UPDATES_OFFLINE", "1")
    called = []
    result = check_for_update("2.0.7", lambda url: called.append(url))
    assert result["state"] == "failed" and not called


def test_fake_version_env_var(monkeypatch):
    monkeypatch.setenv("IMAGE_CLASSIFIER_FAKE_VERSION", "1.0.0")
    assert check.current_version() == "1.0.0"
