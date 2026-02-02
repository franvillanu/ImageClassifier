#!/usr/bin/env python3
"""Image Classifier – run the app from project root.

Usage (from project root):
  python run.py
  python -m image_classifier
"""
import os
import sys

# Ensure project root is on path
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

# Run the app (same as: python image-classifier.py)
from image_classifier import run
run()
