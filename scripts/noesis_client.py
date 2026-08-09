"""Minimal client for the MZO Noesis document-parsing API.

MZO release tooling. Contributors do not need this: guide text is parsed once
and delivered with the release, so every contributor holds the same bytes.

Configuration comes from the environment, never from a file in the tree:

    NOESIS_BASE_URL   the analyze endpoint
    NOESIS_API_KEY    the key, sent as the X-API-Key header

The endpoint answers with NDJSON — one JSON object per line, each a block of
`{"anchor": ..., "content": ...}` — so the response is parsed line by line
rather than as a single document.
"""

import json
import mimetypes
import os
import pathlib
import urllib.error
import urllib.request
import uuid
from typing import Any

TIMEOUT_SECONDS = 900


def _config() -> tuple[str, str]:
    base = os.environ.get("NOESIS_BASE_URL", "").strip()
    key = os.environ.get("NOESIS_API_KEY", "").strip()
    if not base or not key:
        raise SystemExit("set NOESIS_BASE_URL and NOESIS_API_KEY before calling Noesis")
    return base, key


def _multipart(path: pathlib.Path, options: dict[str, Any]) -> tuple[str, bytes]:
    boundary = "----noesis" + uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in options.items():
        if value is None:
            continue
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{rendered}\r\n".encode()
        )
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n".encode()
        + path.read_bytes()
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return boundary, b"".join(parts)


def analyze(path: pathlib.Path, **options: Any) -> list[dict[str, Any]]:
    """Parse one document and return its content blocks in order.

    Useful options: `outputFormat` ("md", "html", "json"), `pageRange`
    ("1-20"), `useOcrToImage`, `inlcudeImage` — the last spelling is the API's.
    """

    base, key = _config()
    boundary, body = _multipart(path, options)

    request = urllib.request.Request(base, data=body, method="POST")
    request.add_header("X-API-Key", key)
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:  # pragma: no cover - network failure path
        detail = error.read()[:400].decode("utf-8", "replace")
        raise SystemExit(f"Noesis returned {error.code}: {detail}") from error

    blocks: list[dict[str, Any]] = []
    for line in payload.decode("utf-8", "replace").splitlines():
        if line.strip():
            blocks.append(json.loads(line))
    return blocks


def markdown(blocks: list[dict[str, Any]]) -> str:
    """Join content blocks into the document text."""

    return "".join(str(block.get("content", "")) for block in blocks)
