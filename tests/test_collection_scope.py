"""The fixed dataset-v2 collection boundary."""

import importlib.util
from pathlib import Path
from types import ModuleType


def load_script(name: str) -> ModuleType:
    """Load one collection script without requiring scripts to be a package."""

    path = Path(__file__).parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_law_whitelist_is_the_fixed_eight_instruments() -> None:
    raw = load_script("collect_legal_raw")

    assert raw.LAW_WHITELIST == (
        ("약사법", "법률"),
        ("의료법", "법률"),
        ("개인정보 보호법", "법률"),
        ("의료기기법", "법률"),
        ("표시ㆍ광고의 공정화에 관한 법률", "법률"),
        ("화장품법", "법률"),
        ("공중위생관리법", "법률"),
        ("안마사에 관한 규칙", "보건복지부령"),
    )


def test_precedent_discovery_covers_every_fixed_law_and_domain_issue() -> None:
    raw = load_script("collect_legal_raw")

    assert set(raw.PRECEDENT_KEYWORDS) >= {
        "약사법",
        "의료법",
        "개인정보 보호법",
        "의료기기법",
        "표시광고",
        "화장품",
        "공중위생관리법",
        "안마사",
        "미용",
        "무면허 의료행위",
    }
