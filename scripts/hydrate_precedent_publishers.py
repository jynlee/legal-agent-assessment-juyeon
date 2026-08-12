"""Restore publishers omitted by an earlier broad precedent collection run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from collect_legal_raw import PRECEDENT_KEYWORDS, search_precedents_with_publisher


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def discover_publishers(oc: str) -> dict[str, str]:
    """Recover publisher metadata from the paginated search responses."""

    publishers: dict[str, str] = {}
    for keyword in PRECEDENT_KEYWORDS:
        hits = search_precedents_with_publisher(oc, keyword)
        for serial, publisher in hits:
            if publisher:
                publishers.setdefault(serial, publisher)
        print(f"  [{keyword}] {len(hits)} hits")
    return publishers


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oc", required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()

    records = read_jsonl(args.input)
    publishers = discover_publishers(args.oc)
    missing = [str(row.get("판례일련번호") or "") for row in records if not row.get("데이터출처명")]
    unresolved = [serial for serial in missing if not publishers.get(serial)]
    if unresolved:
        raise RuntimeError(f"publisher unresolved for {len(unresolved)} records")

    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        delete=False,
        dir=args.input.parent,
        prefix=f".{args.input.name}.",
    ) as handle:
        temporary = Path(handle.name)
        for row in records:
            serial = str(row.get("판례일련번호") or "")
            if not row.get("데이터출처명"):
                row["데이터출처명"] = publishers[serial]
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(args.input)
    print(f">>> hydrated {len(missing)} publisher values in {args.input}")


if __name__ == "__main__":
    main()
