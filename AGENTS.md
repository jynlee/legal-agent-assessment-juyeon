# Contributor Instructions

- Read `ASSIGNMENT.md`, `DATASET.md`, `CONTRACT.md`, and `SUBMISSION.md` before
  implementation.
- Write code, identifiers, commits, and documentation in English.
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
