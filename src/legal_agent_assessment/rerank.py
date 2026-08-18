"""Semantic reranking over the fused retrieval pool: builds a rerank prompt
and parses Claude's relevance selection.

Implements the "1. Weight RRF fusion toward kNN" follow-up named in
reports/retrieval-evaluation-report.md's "Failed-query analysis": rank-based
fusion has a real ceiling (12 of 42 answerable questions' gold chunk was
present in one retriever's top-50 but too deep in rank for any fusion
weight to promote it into the top-10). A semantic reranker reads the
candidate text directly instead of relying on rank consensus, so it is not
bound by that ceiling the same way. Pure: no boto3, no network, matching
AGENTS.md's I/O separation -- src/legal_agent_assessment/agent.py is the
network-facing caller, same pattern as judge.py and generation.py.

Unlike judge.py (evaluation-only tooling, deliberately never threaded into
RuntimeVersions), this module's output directly determines which citations
a real GeneralLegalResponse can ever contain -- RERANK_PROMPT_VERSION is
threaded into RuntimeVersions.rerank for the same reproducibility reason
generation.PROMPT_VERSION is.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from legal_agent_assessment.contracts import Citation

# Bumped whenever _RERANK_PROMPT_TEMPLATE changes. Kept next to the template
# so the two cannot silently desync -- same convention as
# generation.PROMPT_VERSION and judge.JUDGE_PROMPT_VERSION.
RERANK_PROMPT_VERSION = "rerank-prompt-v1"

_RERANK_PROMPT_TEMPLATE = """You are selecting which of several retrieved \
source excerpts are actually relevant to a Korean legal question, before \
another system uses only your selection to draft an answer. This is a \
relevance filter, not an answer -- do not answer the question yourself.

Question: {question}

Candidate sources (each labelled with its chunk_id):
{candidates}

Select every candidate that is actually relevant to answering this \
specific question -- a source about a related but different topic, a \
different specific technique, or a different specific claim is not \
relevant just because it shares a general legal domain. Order your \
selection from most to least relevant. Select as many or as few as are \
genuinely relevant; do not pad the list to reach any particular count, \
and do not select none if any candidate is genuinely on point.

Do not show your work. Do not write any text before or after the JSON \
object -- your entire response must be the JSON object itself and \
nothing else.

Respond with exactly one JSON object in this shape:
{{"relevant_chunk_ids": [string, ...]}}"""

# Same lever judge.py uses for the same reason: assistant-turn prefill is
# rejected outright by this model/endpoint (real ValidationException,
# 2026-08-14), so a system prompt is the strongest available way to force
# raw-JSON-only output short of prefill.
RERANK_SYSTEM_PROMPT = (
    "You only ever output a single raw JSON object as your entire "
    "response. Never include prose, analysis, markdown formatting, "
    "or any text before or after the JSON object."
)

_MAX_RERANKED_IDS = 10


def build_rerank_prompt(question: str, candidates: Sequence[Citation]) -> str:
    """Build the rerank prompt for one question's fused candidate pool.

    Candidates are shown with their chunk_id as a label (matching
    generation.build_answer_prompt's own convention) so the model's
    response can reference them unambiguously.
    """

    candidate_text = "\n\n".join(
        f"[{citation.chunk_id}] {citation.title}\n{citation.excerpt}" for citation in candidates
    )
    return _RERANK_PROMPT_TEMPLATE.format(question=question, candidates=candidate_text)


@dataclass(frozen=True, slots=True)
class ParsedRerank:
    """One parsed, validator-safe rerank outcome: relevant chunk_ids, most
    relevant first."""

    chunk_ids: tuple[str, ...]


def _strip_code_fence(raw_text: str) -> str:
    """Unwrap a markdown-fenced payload, if the model wrapped one.

    Same shape as generation._strip_code_fence and judge._strip_code_fence
    -- duplicated rather than imported, per this project's one-file-one-
    responsibility convention.
    """

    stripped = raw_text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    body = lines[1:]
    if body and body[-1].strip().startswith("```"):
        body = body[:-1]
    return "\n".join(body).strip()


def parse_rerank_response(raw_text: str, *, candidate_ids: Sequence[str]) -> ParsedRerank:
    """Parse Claude's rerank JSON response.

    Never trusts the model's own output: any returned id not present in
    `candidate_ids` (the real ids actually offered) is dropped rather than
    passed through -- the same "never trust the model" philosophy
    generation.parse_answer_response already applies to cited_chunk_ids.
    Duplicates are dropped, keeping first occurrence (the model's own
    stated relevance order). Capped at 10 ids, matching this project's
    fused top-10 cutoff, so a model that ignores the "do not pad" prompt
    instruction cannot smuggle more candidates through than generation
    would ever have received before this change.

    Uses `json.JSONDecoder().raw_decode`, not `json.loads`, for the same
    reason generation.parse_answer_response does: a real 2026-08-18 crash
    showed this model sometimes writes prose after closing its JSON fence,
    and only the first JSON value should ever be trusted.
    """

    try:
        parsed, _end = json.JSONDecoder().raw_decode(_strip_code_fence(raw_text))
    except json.JSONDecodeError as error:
        raise ValueError(f"could not parse rerank response as JSON: {raw_text!r}") from error

    if not isinstance(parsed, dict):
        raise ValueError(f"could not parse rerank response as JSON: {raw_text!r}")

    raw_ids = parsed.get("relevant_chunk_ids")
    if not isinstance(raw_ids, list):
        return ParsedRerank(chunk_ids=())

    candidate_id_set = set(candidate_ids)
    seen: set[str] = set()
    kept: list[str] = []
    for chunk_id in raw_ids:
        if isinstance(chunk_id, str) and chunk_id in candidate_id_set and chunk_id not in seen:
            seen.add(chunk_id)
            kept.append(chunk_id)
        if len(kept) >= _MAX_RERANKED_IDS:
            break

    return ParsedRerank(chunk_ids=tuple(kept))


__all__ = [
    "RERANK_PROMPT_VERSION",
    "RERANK_SYSTEM_PROMPT",
    "ParsedRerank",
    "build_rerank_prompt",
    "parse_rerank_response",
]
