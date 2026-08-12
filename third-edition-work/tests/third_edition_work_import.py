from __future__ import annotations

import importlib.util
from pathlib import Path


def load_builder():
    path = Path(__file__).resolve().parents[1] / "tools" / "book_builder.py"
    spec = importlib.util.spec_from_file_location("third_edition_book_builder", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
