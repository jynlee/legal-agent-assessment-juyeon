"""Parse one guide PDF through Noesis in page chunks.

MZO release tooling. Chunking keeps a single request from covering the whole
document, because one image-heavy page can take a minute on its own and a
failure part-way through a 108-page request would discard the pages that
already succeeded.

    uv run python scripts/parse_guide_pdf.py GUIDE.pdf out/medical --pages 108
"""

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from noesis_client import analyze, markdown


def main() -> None:
    """Parse the PDF and write the block stream and the assembled Markdown."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=pathlib.Path)
    parser.add_argument("out_prefix", type=pathlib.Path)
    parser.add_argument("--pages", type=int, required=True, help="page count of the PDF")
    parser.add_argument("--chunk", type=int, default=20)
    parser.add_argument("--no-ocr", action="store_true")
    args = parser.parse_args()

    blocks: list[dict[str, object]] = []
    for start in range(1, args.pages + 1, args.chunk):
        end = min(start + args.chunk - 1, args.pages)
        began = time.monotonic()
        received = analyze(
            args.pdf,
            outputFormat="md",
            pageRange=f"{start}-{end}",
            useOcrToImage=not args.no_ocr,
        )
        blocks.extend(received)
        print(
            f"  pages {start:>4}-{end:<4} {time.monotonic() - began:6.1f}s  blocks={len(received)}"
        )

    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    ndjson = args.out_prefix.with_suffix(".ndjson")
    text_path = args.out_prefix.with_suffix(".md")

    ndjson.write_text(
        "\n".join(json.dumps(block, ensure_ascii=False) for block in blocks), encoding="utf-8"
    )
    text = markdown(blocks)
    text_path.write_text(text, encoding="utf-8")

    markers = text.count("[PAGE_NUMBER]")
    if markers != args.pages:
        raise SystemExit(f"expected {args.pages} page markers, the parse produced {markers}")
    print(f"blocks={len(blocks)} chars={len(text):,} pages={markers} -> {text_path}")


if __name__ == "__main__":
    main()
