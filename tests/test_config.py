"""Tests for config path and defaults."""
import os
import sys

# Ensure package is on path when running tests from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from image_classifier.config import get_config_dir, get_config_file, DEFAULT_CONFIG


def test_default_config_has_expected_keys():
    assert "load_last_folder" in DEFAULT_CONFIG
    assert "last_directory" in DEFAULT_CONFIG
    assert "theme" in DEFAULT_CONFIG
    assert "current_language" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["theme"] == "black"
    assert DEFAULT_CONFIG["current_language"] == "en"


def test_get_config_dir_returns_path():
    path = get_config_dir()
    assert path
    assert isinstance(path, str)
    assert "Image Classifier" in path or "image" in path.lower()


def test_get_config_file_ends_with_json():
    path = get_config_file()
    assert path.endswith(".json")
    assert "viewer_config" in path
