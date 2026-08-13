from legal_agent_assessment.eval import lexical_overlap_ratio


def test_lexical_overlap_ratio_is_1_when_question_is_a_substring_of_source() -> None:
    source = "약사법 제1조는 국민보건 향상을 목적으로 한다"

    ratio = lexical_overlap_ratio("국민보건 향상을 목적으로", source)

    assert ratio == 1.0


def test_lexical_overlap_ratio_is_0_for_completely_different_text() -> None:
    source = "약사법 제1조는 국민보건 향상을 목적으로 한다"
    ratio = lexical_overlap_ratio("오늘 날씨가 좋네요", source)

    assert ratio == 0.0


def test_lexical_overlap_ratio_is_partial_for_a_genuine_paraphrase() -> None:
    source = "표시광고법은 소비자를 오인하게 하는 광고를 금지한다"
    paraphrase = "이 광고 문구가 소비자를 헷갈리게 만들 수도 있을까요?"

    ratio = lexical_overlap_ratio(paraphrase, source)

    assert 0.0 < ratio < 0.5


def test_lexical_overlap_ratio_handles_a_one_character_question() -> None:
    assert lexical_overlap_ratio("가", "가나다") == 0.0


def test_lexical_overlap_ratio_handles_an_empty_question() -> None:
    assert lexical_overlap_ratio("", "아무 텍스트") == 0.0
