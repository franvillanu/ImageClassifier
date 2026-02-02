"""Tests for translations."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from image_classifier.i18n.translations import translations


def test_translations_has_en_and_es():
    assert "en" in translations
    assert "es" in translations


def test_en_and_es_have_same_keys():
    en_keys = set(translations["en"].keys())
    es_keys = set(translations["es"].keys())
    missing_in_es = en_keys - es_keys
    missing_in_en = es_keys - en_keys
    assert not missing_in_es, f"Missing in es: {missing_in_es}"
    assert not missing_in_en, f"Missing in en: {missing_in_en}"


def test_common_keys_non_empty():
    t = translations["en"]
    assert t["photo_viewer_title"] == "Image Classifier"
    assert t["select_folder"]
    assert t["favorites"] == "Favorites"
