"""Sample candidate source chunks per legal domain, for hand-drafting the
retrieval evaluation test set.

    uv run python scripts/sample_eval_source_chunks.py --contributor jynlee

For each of the 10 legal domains, runs `retrieval.build_bm25_query` with the
domain name itself as the query text against the real local index, and
writes the top 8 hits per domain to
`reports/eval/candidate_source_chunks.json`. This file is draft working
material for Tasks 2-3's human-reviewed drafting pass, not the final test
set, and is not itself a submission deliverable -- do not commit it (it
duplicates indexed chunk text at draft-selection scale, which the
committed `retrieval_test_set.json` in Task 2-3 deliberately does not).
No embedding call is made here: BM25 alone is enough to surface
domain-characteristic chunks for a human to read and choose from.
"""

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from opensearch_client import build_client

from legal_agent_assessment.opensearch_index import index_name
from legal_agent_assessment.retrieval import build_bm25_query

DOMAINS = [
    "약사법",
    "의료법",
    "개인정보보호법",
    "의료기기법",
    "표시광고법",
    "미용법",
    "화장품법",
    "무면허의료행위",
    "공중위생법",
    "안마사법",
]

CANDIDATES_PER_DOMAIN = 8


def main() -> None:
    """Query the real index for candidate chunks, one BM25 call per domain."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contributor", required=True)
    args = parser.parse_args()

    client = build_client(
        url=os.environ.get("OPENSEARCH_URL", "http://localhost:9200"),
        profile=os.environ["AWS_PROFILE"],
        region=os.environ.get("AWS_REGION", "ap-northeast-2"),
    )
    name = index_name(args.contributor)

    candidates: dict[str, list[dict[str, object]]] = {}
    for domain in DOMAINS:
        query = build_bm25_query(domain, size=CANDIDATES_PER_DOMAIN)
        response = client.search(index=name, body=query)
        candidates[domain] = [
            {
                "chunk_id": hit["_source"]["chunk_id"],
                "document_kind": hit["_source"]["document_kind"],
                "title": hit["_source"]["title"],
                "text": hit["_source"]["text"],
            }
            for hit in response["hits"]["hits"]
        ]
        print(f">>> {domain}: {len(candidates[domain])} candidates")

    out_dir = pathlib.Path(__file__).resolve().parents[1] / "reports" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "candidate_source_chunks.json"
    out_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">>> wrote {out_path}")


if __name__ == "__main__":
    main()
