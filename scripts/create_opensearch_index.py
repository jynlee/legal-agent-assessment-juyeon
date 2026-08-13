"""Create the versioned OpenSearch index for this contributor's chunks.

    uv run python scripts/create_opensearch_index.py --contributor jynlee --replicas 0

Idempotent: exits cleanly (prints a message, does not error) if the index
already exists, so re-running after a partial `index_chunks.py` run is safe.
"""

import argparse
import os
import sys
from pathlib import Path

from opensearchpy import RequestError

from legal_agent_assessment.opensearch_index import build_index_body, index_name

sys.path.insert(0, str(Path(__file__).resolve().parent))

from opensearch_client import build_client


def main() -> None:
    """Create the index, or report that it already exists."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contributor", required=True)
    parser.add_argument("--replicas", type=int, required=True)
    args = parser.parse_args()

    url = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")
    profile = os.environ["AWS_PROFILE"]
    region = os.environ.get("AWS_REGION", "ap-northeast-2")

    client = build_client(url=url, profile=profile, region=region)
    name = index_name(args.contributor)
    body = build_index_body(number_of_replicas=args.replicas)

    try:
        client.indices.create(index=name, body=body)
        print(f">>> created index {name}")
    except RequestError as error:
        if error.error == "resource_already_exists_exception":
            print(f">>> index {name} already exists, nothing to do")
        else:
            raise


if __name__ == "__main__":
    main()
