"""Verify that the local assessment OpenSearch endpoint runs version 3.5."""

import json
import os
from typing import Any
from urllib.request import urlopen


def main() -> None:
    """Read the root endpoint and reject an incompatible engine version."""

    endpoint = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")
    with urlopen(endpoint, timeout=5) as response:
        payload: dict[str, Any] = json.load(response)

    version = str(payload.get("version", {}).get("number", ""))
    if not version.startswith("3.5."):
        raise SystemExit(f"expected OpenSearch 3.5.x, received {version or 'unknown'}")
    print(f"OpenSearch {version} is ready at {endpoint}")


if __name__ == "__main__":
    main()
