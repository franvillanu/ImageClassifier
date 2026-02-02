# Image Classifier package
"""Image Classifier – desktop app for organizing photos and choosing favorites."""

__version__ = "2.0"


def run():
    """Run the application. Uses the main script in the project root."""
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "image_classifier_app",
        os.path.join(root, "image-classifier.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()
