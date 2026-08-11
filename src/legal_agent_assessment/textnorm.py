"""General-purpose text normalization. No legal-domain knowledge lives here.

Ported from Peitho `scripts/textnorm.py` (baseline b38f308). Legal-specific rules
(deleted articles, amendment markers, whitelists) belong in `cleaning.py`.

The behaviour is deliberately identical to Peitho's, because the delivered corpus
is re-processed by Peitho after handover: a rule that differs here changes
`normalizedText`, which changes `contentHash`, which changes every derived
identifier. Port fixes back rather than diverging.
"""

import re
from collections import Counter

# Middle-dot unification: to the 법제처 official notation U+318D 'ㆍ'.
# NOTE: blanket NFKC corrupts this ('ㆍ' -> 'ᆞ'), so it is never used (measured).
DOT_VARIANTS = "·ᆞ‧∙•・"
_DOT_TABLE = str.maketrans(dict.fromkeys(DOT_VARIANTS, "ㆍ"))
# Fullwidth ASCII (FF01-FF5E) -> halfwidth (21-7E), ideographic space -> space.
_FULLWIDTH_TABLE = {codepoint: codepoint - 0xFEE0 for codepoint in range(0xFF01, 0xFF5F)}
_FULLWIDTH_TABLE[0x3000] = 0x20

_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_IMG_RE = re.compile(r"<img[^>]*>\s*(?:</img>)?")
_IMG_SRC_RE = re.compile(r'src="([^"]*)"')
# Only tags starting with a Latin letter, so Korean angle notation such as
# '<개정 2016.2.3>' survives. Removing those is a legal-domain decision that
# `cleaning.clean_law` makes explicitly, with a counter.
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9]*[^>]*>")

# Characters that must behave as an ordinary space. Written as codepoints because
# every one of them is invisible in source, so a literal here would be unreviewable.
#
# U+00A0 is the one that actually bites: `&nbsp;` decodes to it, so a body written
# with the entity would hash differently from an identical body written with a
# plain space - while looking the same to a reader - and every expected-text
# assertion against it would fail for a reason nothing displays. The rest are the
# Unicode space separators that turn up in converted documents.
_SPACE_CODEPOINTS: tuple[int, ...] = (
    0x09,  # tab
    0x20,  # space
    0xA0,  # no-break space  <- what `&nbsp;` decodes to
    0x1680,  # ogham space mark
    *range(0x2000, 0x200B),  # en quad .. hair space
    0x202F,  # narrow no-break space
    0x205F,  # medium mathematical space
    0x3000,  # ideographic space
)
_SPACE_CLASS = "".join(re.escape(chr(point)) for point in _SPACE_CODEPOINTS)
_WS_RE = re.compile(f"[{_SPACE_CLASS}]+")
_MULTI_NL_RE = re.compile(r"\n{2,}")

# Item-marker restoration. Korean markers are the 14 letters '가'..'하' only —
# the range [가-하] would cover the whole Hangul syllable block, so they are
# enumerated. Numbers are 1-2 digits plus a period; circled 항 marks included.
_ITEM_LETTERS = "가나다라마바사아자차카타파하"
_BULLETS = "▶▷■○●"
_BULLET_RE = re.compile(rf"(?<=\S)[{_SPACE_CLASS}]*([{_BULLETS}])")
_ESCAPED_DASH_RE = re.compile(rf"(?<=\S)[{_SPACE_CLASS}]*(\\-)")
# Only markers already separated by a space are restored. That requirement is
# what stops a sentence ending ('한다.', '따른다.') being read as a marker.
_INLINE_ITEM_RE = re.compile(
    rf"(?<=\S)[{_SPACE_CLASS}]+((?:[{_ITEM_LETTERS}]|\d{{1,2}})\.)(?=[{_SPACE_CLASS}])"
)
_INLINE_CIRCLED_RE = re.compile(rf"(?<=\S)[{_SPACE_CLASS}]+([①-⑮])")
# A space alone cannot guard Korean date notation: the month/day of
# `2019. 12. 12.` are shaped exactly like a numbered 호 marker, and every
# 행정규칙/별표 body carries a `[시행 …]` header and 부칙 dates. If the preceding
# text ends in a digit (optionally with a period), it is not a marker.
_TRAILING_NUMBER_RE = re.compile(r"\d\.?$")


def count_dot_variants(text: str) -> int:
    """

    Count occurrences of the middle-dot variants that unification targets.

    """
    return sum(text.count(character) for character in DOT_VARIANTS)


def normalize_chars(text: str) -> str:
    """

    Character normalization: middle-dot family -> 'ㆍ', fullwidth ASCII -> halfwidth.

    """
    return text.translate(_DOT_TABLE).translate(_FULLWIDTH_TABLE)


def normalize_whitespace(text: str) -> str:
    """

    Whitespace normalization: collapse runs of spaces/tabs, trim lines, drop
    blank lines. Line breaks themselves are preserved — they are chunk
    boundaries.

    """
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _MULTI_NL_RE.sub("\n", text).strip()


def replace_br(text: str) -> tuple[str, int]:
    """

    Replace `<br>` with a newline — replacement, not removal, so paragraph
    boundaries survive. Returns the text and the replacement count.

    """
    count = len(_BR_RE.findall(text))
    return _BR_RE.sub("\n", text), count


def index_image_markers(text: str, label: str = "이미지") -> tuple[str, int]:
    """

    Replace `<img ...>` with '[이미지N]' markers numbered by first appearance.

    The same `src` gets the same number, so a repeated image (a judgement
    referring to one trademark several times) stays distinguishable from text
    alone. A tag with no `src` takes the next number in order. Returns the text
    and the number of unique images.

    """
    src_index: dict[str, int] = {}

    def substitute(match: re.Match[str]) -> str:
        src_match = _IMG_SRC_RE.search(match.group(0))
        key = src_match.group(1) if src_match else f"__nosrc_{len(src_index)}"
        if key not in src_index:
            src_index[key] = len(src_index) + 1
        return f"[{label}{src_index[key]}]"

    return _IMG_RE.sub(substitute, text), len(src_index)


def strip_html_tags(text: str, replacement: str = " ") -> tuple[str, int]:
    """

    Residual-HTML safety net. Only tags starting with a Latin letter are
    removed, so Korean angle notation such as '<개정 2016.2.3>' is left alone.
    Returns the text and the removal count.

    """
    count = len(_HTML_TAG_RE.findall(text))
    return _HTML_TAG_RE.sub(replacement, text), count


def _break_before_item(match: re.Match[str]) -> str:
    """

    Move one 호/목 marker onto its own line, unless the preceding text ends in a
    digit — that makes it part of a date rather than a marker.

    """
    marker = match.group(1)
    if marker[0].isdigit() and _TRAILING_NUMBER_RE.search(match.string[: match.start()]):
        return match.group(0)
    return f"\n{marker}"


def restore_item_breaks(text: str) -> str:
    r"""

    Restore line breaks lost in front of 호/목 markers.

    Converting a table-based original (HWP) to Markdown drops the line break
    inside a cell, so the marker glues onto the preceding sentence
    ("… 수집라. 수집된 정보를"). 별표 and 행정규칙 are exactly that shape — 조문
    plus 호/목 lists — and a citation locator *is* the 목 number, so a lost break
    breaks locator derivation.

    Restoration is limited to the unambiguous cases:

    - bullets (▶▷■○●) and the escaped list dash (`\-`), which cannot occur
      mid-word;
    - a 호/목/항 marker that has content before it and is **already separated by
      a space**;
    - for numeric markers additionally, that the preceding text does not end in a
      digit — so the month/day of `2019. 12. 12.` are not read as 호 markers.

    The space requirement is the first guard: the `다.` of "…라고 한다." is glued
    to the previous syllable and is left alone. Conversely a Korean marker fully
    glued to the preceding text ("수집라.") is indistinguishable from a sentence
    ending, so this function does not restore it — ingestion must additionally
    assert that the expected 목 text arrived (see `docs/06_COLLECTION_RUNBOOK.md`).

    Run this **before anything else touches 별표/행정규칙 text**
    (`docs/03_PIPELINE.md`).

    """
    text = _BULLET_RE.sub(r"\n\1", text)
    text = _ESCAPED_DASH_RE.sub(r"\n\1", text)
    text = _INLINE_ITEM_RE.sub(_break_before_item, text)
    return _INLINE_CIRCLED_RE.sub(r"\n\1", text)


def new_stats() -> Counter[str]:
    """

    A fresh cleaning-statistics counter.

    """
    return Counter()
