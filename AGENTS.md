# Contributor Instructions

- Read `ASSIGNMENT.md`, `DATASET.md`, `CONTRACT.md`, and `SUBMISSION.md` before
  implementation. Read `README.md` for the development cautions.
- Write code, identifiers, commits, and source documentation in English.
- English documents are authoritative. `README.md` and every `*.ko.md` file are
  Korean translations for human readers; `README.en.md` is the English source of
  `README.md`. When you change an English document, update its Korean
  translation in the same commit, and never let the two disagree in substance.
- Ask the MZO contact (gyro) when something is undefined, instead of assuming.
  Questions are expected and are not penalized. If no answer arrives in time,
  state the assumption, proceed on it, and record both in the blocker log.
- Treat the delivered dataset manifest and checksums as immutable.
- Do not add external corpus records or generated legal evidence.
- Never commit credentials, real PII, restricted raw artifacts, dataset files,
  generated indexes, or model outputs containing sensitive data.
- Keep deterministic logic separate from filesystem, network, OpenSearch,
  Bedrock, CLI, and environment configuration.
- Preserve the public contract in `src/legal_agent_assessment/contracts.py`.
- Add dependencies only when they are used and explain material choices in the
  final architecture report.
- Run `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy src`, and `uv run pytest` before submission.
