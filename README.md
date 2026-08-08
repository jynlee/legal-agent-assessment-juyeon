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

Start here:

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

Questions that require a baseline clarification must be raised before making an
assumption that changes the contract. Any baseline update that affects the
assessment is published to all active contributors at the same time.
