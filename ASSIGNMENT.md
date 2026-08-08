# Assignment

## Objective

Build a reproducible, grounded General Legal Agent application service from the
frozen legal dataset supplied by MZO. Demonstrate what one developer can design,
implement, measure, and document within two weeks.

## Required work

You own all of the following:

1. Analyze the supplied records and decide how each document kind is used.
2. Normalize and chunk the corpus with explicit, versioned rules.
3. Create a versioned OpenSearch 3.5 index reproducibly.
4. Implement query embedding, retrieval, and any fusion or reranking you choose.
5. Build a test set and relevance judgements suitable for your retrieval claim.
6. Define and compute quantitative retrieval metrics such as Recall@k, MRR, or
   nDCG, explaining why each metric and cutoff is appropriate.
7. Generate grounded answers through the fixed Bedrock Claude model policy.
8. Return verifiable citations and explicit insufficient-evidence,
   out-of-scope, and dependency-unavailable states.
9. Expose the single-turn, stateless application-service contract.
10. Supply tests, reproducible commands, architecture decisions, limitations,
    effort, actual time, and cost evidence.

## Fixed constraints

- Dataset: only the frozen MZO release. Additional corpus data is prohibited.
- Search: AWS managed OpenSearch 3.5 compatibility.
- Embedding: AWS Bedrock Cohere Embed v4, 1536 dimensions.
- Generation: the Kit-verified Bedrock Claude Sonnet 4.6 model ID published in
  `.env.example`.
- Ingest and query use the same embedding model, dimension, and preprocessing.
- Work duration: two weeks after the start conditions are satisfied.
- Runtime boundary: one database-free, single-turn, stateless application
  service with typed, serializable input and output.

Record exact Bedrock inference-profile IDs, prompts, inference parameters,
dataset/chunk/index versions, tokens, latency, and estimated cost. Do not guess
Opus or Haiku model IDs from display names. MZO performs the official comparison
using one frozen Sonnet configuration unless it later publishes an equal baseline
update to every active contributor.

## Explicitly not provided

MZO does not prescribe:

- record selection within the supplied coverage;
- normalization and chunking strategy;
- index mapping or vector engine parameters;
- dense, BM25, hybrid, fusion, or reranking strategy;
- test queries, relevance judgements, metrics, cutoffs, or pass bars;
- prompts, answer composition, or internal framework.

If test-set construction blocks progress, request help. MZO may then publish a
small common schema or example to every active contributor. Private scaffolding
that changes one contributor's assessment is not provided.

## Prohibited work

- Adding external corpus records, web-search results, or synthetic legal evidence.
- Indexing evaluation queries, expected answers, or relevance labels.
- Presenting a source-derived near-copy retrieval test as real-user quality.
- Claiming that an answer is legal advice or that conduct is definitively lawful.
- Importing Peitho, taking a Peitho DB session, or implementing Peitho auth,
  tenancy, persistence, DI, `ITool`, or deployment.
- Committing credentials, real PII, restricted raw data, or generated datasets.

## Acceptance boundary

Contributor-reported metrics are evidence, not the official certification
result. MZO rebuilds and reruns each submission from the frozen release. Only
MZO-rerun results may be supplied to the external certification body. Delivery
does not guarantee that one complete submission, or any component, is selected.
