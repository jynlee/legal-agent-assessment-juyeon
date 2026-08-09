# scripts

## Contributor smoke checks

| Script | Checks |
| --- | --- |
| `smoke_opensearch.py` | the local endpoint runs OpenSearch 3.5 |
| `smoke_contract.py` | the application-service contract round-trips |

## Release verification

`verify_release.py` runs the deterministic checks from
[DATASET_SCHEMA.md](../DATASET_SCHEMA.md) over a delivered release. MZO runs it
before delivery; run it yourself after verifying the checksums.

```powershell
uv run python scripts/verify_release.py --rag-dir <dir> `
    --file judgements.jsonl --file guides.jsonl --manifest release-manifest.json
```

It exits non-zero on an error and prints warnings with counts. Warnings
describe the corpus — placeholder dates, duplicate decisions, body-only
records — and are not failures.

## MZO release build

These produce the release; contributors do not run them. They are here so that
how the corpus was built is visible rather than asserted.

| Script | Produces |
| --- | --- |
| `noesis_client.py` | client for the document-parsing API (`NOESIS_BASE_URL`, `NOESIS_API_KEY`) |
| `parse_guide_pdf.py` | Markdown and the block stream for one guide PDF |
| `build_guide_records.py` | `guides.jsonl` — needs `uv sync --group release` for pypdf |
| `build_judgement_records.py` | `judgements.jsonl` from the collected precedent JSONL |
| `build_release_manifest.py` | `release-manifest.json`, counting coverage from the records |

Order: parse each guide, build both record files, write the manifest, verify.

```powershell
uv run python scripts/parse_guide_pdf.py <guide.pdf> parsed/medical --pages 108
uv run python scripts/build_guide_records.py --parsed parsed --pdf-dir <pdfs> --out guides.jsonl
uv run python scripts/build_judgement_records.py --rag-dir <dir> --out judgements.jsonl
uv run python scripts/build_release_manifest.py --rag-dir <dir> `
    --file judgements.jsonl --file guides.jsonl `
    --dataset-version dataset-v1 --delivery-id delivery-0001 --out release-manifest.json
```

No dataset file, parsed Markdown, or manifest is committed here. `data/` and
`delivery/` are ignored, and the release travels outside Git.
