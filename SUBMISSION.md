# Submission Requirements

## Source and execution

- Complete source and dependency lock.
- Non-interactive dataset validation, index build, evaluation, and demo commands.
- Clean-checkout setup instructions.
- Unit, integration, and contract tests.
- No secrets, dataset payloads, generated indexes, or restricted artifacts.

## Architecture report

Document:

- record-selection and document-kind decisions;
- normalization, chunking, and deterministic identity rules;
- index mapping, retrieval, fusion, filtering, and reranking;
- embedding and LLM adapter boundaries;
- grounding, citations, refusal, and failure behavior;
- portability boundaries and known Peitho adaptation work;
- dependencies, licences, security assumptions, and operational limitations.

## Retrieval evaluation report

Disclose:

- test-query sources and construction method;
- answerable, unanswerable, and out-of-scope composition;
- relevance-labelling method and treatment of multiple relevant results;
- leakage controls, including source-derived queries;
- exact metric definitions and cutoffs;
- aggregate and per-domain results;
- failed-query analysis;
- latency percentiles, index size, index build time, and rebuild count;
- dataset, normalization, chunking, embedding, and index versions.

## Generation evaluation report

Report grounding, citation integrity, unsupported citation/hallucination,
insufficient-evidence refusal, out-of-scope refusal, latency, token use, and cost.
Separate deterministic retrieval measurements from repeated stochastic generation
measurements.

## Work report

- Initial estimate and milestone plan.
- Actual time by milestone.
- Blocker log, including access and environment failures.
- Completed, incomplete, and deliberately deferred work.
- AWS use: embedding calls, generation calls, input/output tokens, OpenSearch
  usage, rebuild count, and estimated cost. Contributors share one IAM user, so
  billing and CloudTrail cannot attribute any of this to you. It can only come
  from instrumentation you write yourself, recorded from the first call onward,
  and it cannot be reconstructed afterwards.
- What you would do with one additional week.

MZO must be able to rebuild the index and rerun the reported evaluation without
private machine state, IDE state, notebooks, or an unlisted external service.
