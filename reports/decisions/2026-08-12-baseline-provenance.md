# Baseline Provenance

Date: 2026-08-12
Status: Decided
Covers: README.en.md "Contributor repositories from a tag" — "The contributor
repository records the source tag and commit in its initial commit."

This note is the explicit, plain-text record of which MZO baseline tags this
private repository was built from, since the repository's own commit history
carries the tagged commits by hash but never states them in prose.

## Baseline history

| Tag | Commit | Schema | Notes |
| --- | --- | --- | --- |
| `assessment-v1` | `118a1d51e087c126aefb977f74e62d31df965111` (not used directly) | — | Superseded same-day by v3; not a base for this repository. |
| `assessment-v3` | `37bab4ec92c89e796d1b06d1e6955449ca92b46c` | `source-record-v1` | Initial baseline. This private repository (`jynlee/legal-agent-assessment-juyeon`) was created from this exact tagged tree, per the 2026-08-09 MZO email confirming "기준 태그: assessment-v3 / 기준 커밋: 37bab4ec92c89e796d1b06d1e6955449ca92b46c". |
| `assessment-v4` | `b73880e9baaf4353489725e6eeb4f0ea7d70a7b8` | `source-record-v2` | Baseline correction, distributed 2026-08-12 after MZO expanded scope to include statutes (약사법, 의료법, 개인정보 보호법, 의료기기법, 표시·광고의 공정화에 관한 법률, 화장품법, 공중위생관리법, 안마사에 관한 규칙). Merged into this repository's `master` via `git merge assessment-v4` (commit `d35dff65146209fe81a49431f06a244b494388d7`) with no conflicts; the merge adds `StatuteIdentity`/`StatuteUnitKind` to `dataset.py` and MZO's statute-collection tooling under `scripts/` without altering any file this repository had already added. |

## Verification performed for the v4 correction

- Tag `assessment-v4` resolves to commit `b73880e9baaf4353489725e6eeb4f0ea7d70a7b8`
  (`git rev-parse assessment-v4^{commit}`), matching the commit hash MZO stated
  in the 2026-08-12 email.
- Dataset archive `dataset-2026-08-11-v2.1.zip` SHA-256
  `7e62653627a1c74c477584e00e12dcbdde5e3d71c35841141d53e76d9585790f` matches
  the value in the same email.
- All 8 inner files matched their `SHA256SUMS` entries after extraction.
- `scripts/verify_release.py --rag-dir data --file statutes.jsonl --file
  judgements.jsonl --manifest data/release-manifest.json` reported 0 errors,
  0 content-hash mismatches, 1,625 statute + 182 judgement records, all 1,807
  eligible for indexing.
- `assessment-v4` is an ancestor of this repository's `master`
  (`git merge-base --is-ancestor assessment-v4 master`), and
  `git diff assessment-v4 master` shows only files this repository had already
  added — nothing from the v4 tree was removed or modified.

## Why

README.en.md requires the source tag and commit to be recorded in the
contributor repository's initial commit, but this repository's actual initial
commit is a verbatim carry-over of the upstream template's own root commit
(from cloning the tagged tree with full history), so no commit message ever
states the tag/commit in prose. This note is the plain-text record, kept
alongside the record-selection and chunking decision notes so it can be
folded into the Work report's blocker/assumption log at submission time.

**How to apply:** if MZO issues a further baseline correction, append a row to
the table above and re-run the same verification steps before merging.
