"""Pure helpers shared by official-source collectors.

Every identifier here derives from stable source coordinates, never from a random
UUID: re-running collection on the same source must reproduce the same identity,
or a re-index appends duplicates instead of overwriting.

`assert_expected_text` is the other half of a collector's contract: an identifier
says *which* source a record claims to be, and the assertion says the body that
arrived is actually that source's text.
"""

from collections.abc import Sequence
from hashlib import sha256

from legal_agent_assessment import textnorm


def content_hash(text: str) -> str:
    return f"sha256:{sha256(text.encode('utf-8')).hexdigest()}"


def artifact_hash(payload: bytes) -> str:
    """

    Hash of a raw artifact as acquired, byte for byte.

    """
    return f"sha256:{sha256(payload).hexdigest()}"


def _identifier(prefix: str, *parts: str) -> str:
    canonical = "\x1f".join(part.strip() for part in parts)
    return f"{prefix}-{sha256(canonical.encode('utf-8')).hexdigest()[:24]}"


def document_id(source_kind: str, source_url: str, source_reference: str) -> str:
    return _identifier("doc", source_kind, source_url, source_reference)


def law_document_id(law_id: str, article_number: str, article_branch_number: str) -> str:
    """

    Stable identity of one logical statute article across amendments.

    `MST` identifies one amended version and therefore does not participate. The
    stable law id and article coordinates identify the document that a later
    acquisition replaces.

    """
    branch = article_branch_number.strip()
    normalized_branch = str(int(branch)) if branch else "0"
    return _identifier("doc", "법령", law_id, str(int(article_number)), normalized_branch)


def appendix_document_id(law_id: str, appendix_number: str, appendix_branch_number: str) -> str:
    """Stable identity of one logical statute appendix across amendments."""

    branch = appendix_branch_number.strip()
    normalized_branch = str(int(branch)) if branch else "0"
    return _identifier("doc", "별표", law_id, str(int(appendix_number)), normalized_branch)


def capture_id(source_group_id_value: str, raw_artifact_hash: str) -> str:
    """Deterministic identity of a restricted observed-advertising capture."""
    return _identifier("capture", source_group_id_value, raw_artifact_hash)


def source_case_id(authority: str, coordinate: str, source_identity: str) -> str:
    """

    Logical official case identity, shared by an original and every record
    derived from it.

    `coordinate` is the official case or decision number where one exists; where
    none does, pass stable source coordinates instead.

    """
    return _identifier("case", authority, coordinate, source_identity)


def source_group_id(namespace: str, coordinate: str) -> str:
    """

    Split-safety grouping key.

    Every row that came from one original post, campaign or decision shares this,
    so an evaluation split cannot put a row and its near-duplicate on opposite
    sides and then score the leakage as recall.

    """
    return _identifier("group", namespace, coordinate)


def record_id(source_case_id_value: str, variant_tag: str = "") -> str:
    """

    Unique identity of one dataset row.

    An original and its generated variants share a `sourceCaseId` by design, so
    that cannot be the row key. `variant_tag` is empty for the original and names
    the variant otherwise.

    """
    return _identifier("rec", source_case_id_value, variant_tag)


def mapping_result_id(source_case_id_value: str, mapping_policy_version: str) -> str:
    """Deterministic identity of one case-mapping result under one policy version."""
    return _identifier("unmapped", source_case_id_value, mapping_policy_version)


def rejection_id(source_reference: str, rejection_stage: str, rejection_code: str) -> str:
    """Deterministic identity of one rejected source or case candidate."""
    return _identifier("rejected", source_reference, rejection_stage, rejection_code)


def curation_row_id(document_id_value: str, mapping_policy_version: str) -> str:
    """Deterministic identity of one reviewable case-curation worksheet row."""
    return _identifier("curation", document_id_value, mapping_policy_version)


def chunk_id(
    document_id_value: str,
    record_id_value: str,
    normalized_chunk_text: str,
    chunking_version: str,
    sequence: int,
) -> str:
    return _identifier(
        "chunk",
        document_id_value,
        record_id_value,
        content_hash(normalized_chunk_text),
        chunking_version,
        str(sequence),
    )


def query_id(text: str) -> str:
    """

    Deterministic identity of an evaluation query.

    """
    return _identifier("qry", text)


class ExpectedTextMissing(ValueError):
    """

    A fetched body does not contain the text that source is known to carry.

    Distinct from a transport error on purpose: the request succeeded and
    something arrived. What failed is the claim that it is the right document.

    """


def _comparable(text: str) -> str:
    """

    Fold a body to the form expectations are compared in.

    Character and whitespace normalization are the corpus rules themselves, so a
    middle-dot variant or a `&nbsp;`-derived U+00A0 cannot make a matching body
    look wrong. Line breaks additionally fold to spaces: a snippet that spans a
    break in the source is still the right text, and this check answers "did the
    right document arrive", not "is the layout right".

    """
    normalized = textnorm.normalize_whitespace(textnorm.normalize_chars(text))
    return " ".join(normalized.split("\n"))


def _checked_expectations(expected: Sequence[str]) -> tuple[str, ...]:
    if not expected:
        raise ValueError("expected text requires at least one snippet")
    if any(not snippet.strip() for snippet in expected):
        raise ValueError("expected text must not contain a blank snippet")
    return tuple(expected)


def find_missing_text(body: str, expected: Sequence[str]) -> tuple[str, ...]:
    """

    The expected snippets that are absent from `body`, in the order given.

    """
    comparable = _comparable(body)
    return tuple(
        snippet
        for snippet in _checked_expectations(expected)
        if _comparable(snippet) not in comparable
    )


def assert_expected_text(
    body: str,
    expected: Sequence[str],
    *,
    source_reference: str,
) -> None:
    """

    Verify that a fetched body carries the text this source is known to carry.

    **"The request returned 200" is not "the right body arrived"**
    (`docs/06_COLLECTION_RUNBOOK.md` §2). Every failure this guards against is
    silent: a fuzzy title match loads an unrelated statute; a 별표 number that
    also exists as a 서식 loads the wrong document; a deleted shell is a short
    `삭제` body rather than an absent record; and a 호/목 marker glued to the
    preceding sentence survives `restore_item_breaks` by design, so a locator
    silently resolves to nothing. None of them raise on their own.

    Raises `ExpectedTextMissing` naming the source and the missing snippets. The
    body is never quoted — the message goes into a discovery log, and the body
    may be real source text.

    """
    missing = find_missing_text(body, expected)
    if missing:
        quoted = ", ".join(repr(snippet) for snippet in missing)
        raise ExpectedTextMissing(
            f"{source_reference}: fetched body is missing expected text: {quoted}"
        )


def find_unanchored_item_markers(body: str, markers: Sequence[str]) -> tuple[str, ...]:
    """

    The expected 호/목 markers that do not begin a line, in the order given.

    Containment cannot answer this: a glued marker ('수집라. 수집된') *contains*
    the snippet '라. 수집된'. Only the line position distinguishes a restored
    marker from one absorbed into the previous sentence.

    """
    lines = [
        _comparable(line)
        for line in textnorm.normalize_whitespace(textnorm.normalize_chars(body)).split("\n")
    ]
    return tuple(
        marker
        for marker in _checked_expectations(markers)
        if not any(line.startswith(_comparable(marker)) for line in lines)
    )


def assert_item_markers_begin_lines(
    body: str,
    markers: Sequence[str],
    *,
    source_reference: str,
) -> None:
    """

    Verify that each expected 호/목 marker begins a line.

    A citation locator *is* the 목 number (`제2호 다목`), so a marker that stayed
    glued to the preceding sentence makes the locator resolve to nothing.
    `textnorm.restore_item_breaks` restores only unambiguous cases and leaves a
    fully glued Korean marker alone on purpose, because it cannot be told from a
    sentence ending — this is the backstop the runbook requires for that case
    (`docs/06_COLLECTION_RUNBOOK.md` §2). Run it on 별표 and 행정규칙 bodies
    after `cleaning.clean_instrument_body`.

    """
    unanchored = find_unanchored_item_markers(body, markers)
    if unanchored:
        quoted = ", ".join(repr(marker) for marker in unanchored)
        raise ExpectedTextMissing(
            f"{source_reference}: expected item markers do not begin a line: {quoted}"
        )
