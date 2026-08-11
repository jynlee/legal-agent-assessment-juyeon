"""Selection ledger orchestration and duplicate suppression."""

import importlib.util
import sys
from pathlib import Path


def load_module():  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[1] / "scripts" / "select_precedents.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("select_precedents", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(serial: str, *, body: str, provider: str = "대법원") -> dict[str, object]:
    return {
        "판례일련번호": serial,
        "사건명": "의료법위반",
        "사건번호": "2099도1111",
        "법원명": "대법원",
        "선고일자": "20990101",
        "판시사항": "",
        "판결요지": "",
        "참조조문": "의료법 제27조",
        "참조판례": "",
        "content": body,
        "데이터출처명": provider,
    }


def test_duplicate_decision_keeps_only_richer_representative() -> None:
    module = load_module()
    short = row("1", body="피부관리 의료행위")
    rich = row("2", body="피부관리실의 무면허 의료행위 " * 10)

    selected, ledger = module.select_all([short, rich])

    assert [item["판례일련번호"] for item in selected] == ["2"]
    duplicate = next(item for item in ledger if item.case_serial == "1")
    assert duplicate.duplicate_of == "precedent-2"
