# General Legal Agent Assessment Template

This private repository is the common starting point for independent two-week
General Legal Agent implementations. Every contributor receives the same Git
baseline and byte-identical frozen dataset release in a separate private
repository.

The required vertical slice is:

```text
frozen legal dataset
-> reproducible OpenSearch index
-> measured retrieval pipeline
-> grounded Bedrock LLM answer
-> single-turn GeneralLegalAgent application service
```

## Documents

| English | Korean | Contents |
| --- | --- | --- |
| [README.en.md](README.en.md) | [README.md](README.md) | This file |
| [ASSIGNMENT.md](ASSIGNMENT.md) | [ASSIGNMENT.ko.md](ASSIGNMENT.ko.md) | Objective, fixed constraints, prohibited work |
| [DATASET.md](DATASET.md) | [DATASET.ko.md](DATASET.ko.md) | Release delivery, allowed transformations, lineage |
| [DATASET_SCHEMA.md](DATASET_SCHEMA.md) | [DATASET_SCHEMA.ko.md](DATASET_SCHEMA.ko.md) | Supplied record shape, missing-value conventions, manifest, checks |
| [CONTRACT.md](CONTRACT.md) | [CONTRACT.ko.md](CONTRACT.ko.md) | Portable application-service boundary |
| [SUBMISSION.md](SUBMISSION.md) | [SUBMISSION.ko.md](SUBMISSION.ko.md) | Required evidence |
| [OPENSEARCH_ACCESS.md](OPENSEARCH_ACCESS.md) | [OPENSEARCH_ACCESS.ko.md](OPENSEARCH_ACCESS.ko.md) | Managed domain access and shared-credential rules |
| [AGENTS.md](AGENTS.md) | — | Instructions for coding agents ([CLAUDE.md](CLAUDE.md) points here) |

## Prerequisites

Two tools, and neither is Python.

**uv** runs everything below. Install it from
[the official instructions](https://docs.astral.sh/uv/getting-started/installation/):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Do not install Python yourself.** `pyproject.toml` pins the interpreter to
3.12, and `uv sync` downloads and uses exactly that regardless of what your
system Python is — a machine whose `python` is 3.10 runs this project on 3.12
without touching the system install. Confirm with `uv run python -V` after
syncing.

**Docker Desktop** provides the local OpenSearch 3.5 container that
`docker compose up -d opensearch` starts. The daemon has to be running before
that command and before `smoke_opensearch.py`.

## Start here

1. Read [ASSIGNMENT.md](ASSIGNMENT.md).
2. Verify the delivered dataset as described in [DATASET.md](DATASET.md).
3. Preserve the portable boundary in [CONTRACT.md](CONTRACT.md).
4. Plan the required evidence in [SUBMISSION.md](SUBMISSION.md).
5. Configure the dedicated AWS CLI profile delivered through the approved
   separate channel, then copy `.env.example` to `.env`. Never put access keys
   in `.env`; AWS SDK credential providers resolve the named `AWS_PROFILE`.
6. Run the local checks.

```powershell
uv sync
docker compose up -d opensearch
uv run python scripts/smoke_opensearch.py
uv run python scripts/smoke_contract.py
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

This template fixes environment and integration boundaries, not retrieval
design. It deliberately does not provide canonical chunks, an index mapping, a
retrieval implementation, a test set, relevance labels, prompts, or pass bars.

## The dataset and where it comes from

Current statutes and court decisions come from the 법제처 국가법령정보 OPEN API
at law.go.kr. Dataset v2 covers 약사법, 의료법, 개인정보 보호법, 의료기기법,
표시·광고의 공정화에 관한 법률, 화장품법, 공중위생관리법, and 안마사에 관한 규칙.
It carries current laws, existing decrees and rules, appendices, and selected
aesthetic-domain decisions whose full text the API publishes.

Official guidance from 보건복지부 and 식품의약품안전처 was approved on content
and then withdrawn on licence: one is published under terms forbidding
commercial use and derivative works, the other's terms could not be confirmed.
Neither is in the release. Guidance is where an abstract requirement becomes a
judgement about a specific advertising phrase, so expect questions the
decisions alone cannot answer, and answer those with
`insufficient_evidence`.

MZO delivers this as a frozen release, and **the frozen release is the
measurement basis**. Build and measure your submission from it. That is what
lets MZO's rerun reproduce your numbers.

**You may look at the raw sources**, which is why their origins are named here.
Every record carries its own source URL, so you can check any decision against
the original. The API is open, but its `OC` id is issued per developer, so
query it directly only with an id you registered yourself.

If you conclude the coverage is wrong — something missing, or something
included that does not belong — **tell gyro. Coverage can change.**

Every record carries the publisher statement its source requires. Include it
in the answer:
an answer that cites a decision without naming where the text came from is not
a complete citation. Licence terms and attribution conditions are settled by
the release manifest.

### How the release was built, and how to check it

The scripts that produced it are in [scripts/](scripts/) — the decisions are
mapped from the collected JSONL, and the manifest counts its coverage from the
records rather than from anything typed in. Reading them is the fastest way to
learn why a record looks the way it does. The guide tooling is kept alongside
them for the release that adds guidance if permission arrives.

**Please verify the release before starting work.** Check the delivered
archive's SHA-256 as its `DELIVERY.md` instructs. After extraction,
`scripts/verify_release.py` recomputes every record content hash, checks record
counts and coverage against the manifest, and exits non-zero on an error. These
checks establish which frozen release you received and whether its records
remain valid for MZO's rerun.

```powershell
uv run python scripts/build_judgement_records.py --rag-dir <dir> `
    --out judgements.jsonl --acquired-at 2026-08-08T14:42:00Z
```

That timestamp is when MZO received the sources. It is an input rather than a
fact about your machine, and it has to be passed because a record carries it:
leave it out and each build stamps its own file times, producing records that
differ from the release in nothing but when they were made. Pass the value
above and the file hashes match what the manifest declares.

Access to the parsing and AWS services is delivered separately.

## OpenSearch 3.5 baseline

This assessment replaces the legacy OpenSearch 2.17 baseline with **OpenSearch
3.5**. Build local and managed indexes that are compatible with 3.5. Do not copy
2.17 mappings or assumptions without revalidating them against 3.5.

## Contributor repositories from a tag

MZO freezes the contributor starting point as an immutable tag such as
`assessment-v1` after the dataset release, model access, and smoke checks are
ready. Each contributor then creates a private repository in their own GitHub
account from the exact tagged tree and grants the designated MZO GitHub account
collaborator access for review. Contributors do not share branches or see one
another's work.

The contributor repository records the source tag and commit in its initial
commit. Work continues on that repository's `master` branch; feature branches
and pull requests are optional. The final submission is identified by the
private repository URL and one exact commit SHA. A later baseline correction
receives a new tag and is distributed to every active contributor at the same
time.

Repository outline:

```text
legal-agent-assessment-template @ assessment-v1
        |-- contributor-a/private-repository (+ MZO collaborator)
        |-- contributor-b/private-repository (+ MZO collaborator)
        `-- contributor-c/private-repository (+ MZO collaborator)
```

Do not create contributor repositories from an untagged moving branch.

## Development cautions: Tier

The following silent failures invalidate otherwise unrelated work. Add a cheap
detector for each one before building the full pipeline.

| Mistake | Found | What it invalidates |
| --- | --- | --- |
| Indexing evaluation queries, expected answers, or relevance labels | MZO rerun | Every retrieval metric |
| Presenting a source-derived near-copy test as real-user quality | Review | The entire retrieval evaluation report |
| Missing chunk lineage | Citation check | Every answer — without provenance, `answered` is not reachable |
| Time, tokens, and cost not recorded as you go | Submission | The work report; the shared IAM user makes it unattributable, so it cannot be reconstructed afterwards |
| Developing against the managed domain without SigV4 | Policy tightening, or a rerun elsewhere | Every OpenSearch call — unsigned requests pass locally and on staging today |

Minimum detectors:

- Reject every index input whose provenance/type is evaluation-only or whose
  path comes from the evaluation artifact tree.
- Verify that every indexed record belongs to the frozen corpus manifest, and
  detect exact or near-duplicate query/expected-answer text in indexed chunks.
- Make ingest and query call the same versioned normalization and embedding
  configuration.
- Reject any chunk missing required lineage fields.
- Append tokens, latency, model ID, and cost inputs for every Bedrock call as the
  call happens.

A green CI run is not proof that these conditions hold.

## Asking questions

**Contact: gyro (MZO).**

Ask when something is undefined.

A useful question states:

1. what is blocked;
2. which readings are possible;
3. how the outcome differs depending on which reading is chosen;
4. which assumption you will proceed on if no answer arrives.


Any baseline update that affects the assessment is published to all active
contributors at the same time.
