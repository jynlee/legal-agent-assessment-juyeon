"""Dataset release packaging descriptions."""

import importlib.util
import sys
from pathlib import Path


def module():  # type: ignore[no-untyped-def]
    scripts = Path(__file__).parents[1] / "scripts"
    sys.path.insert(0, str(scripts))
    path = scripts / "package_dataset_release.py"
    spec = importlib.util.spec_from_file_location("package_dataset_release", path)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_delivery_discloses_human_approved_llm_review() -> None:
    document = module().delivery_document("dataset-v2.1", "delivery-1", 10, 20, 30, 5)

    assert "15 review candidates explicitly approved by gyro" in document
    assert "selectionStage" in document
