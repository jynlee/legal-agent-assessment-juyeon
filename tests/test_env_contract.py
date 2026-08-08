from pathlib import Path

ENV_EXAMPLE = Path(__file__).parents[1] / ".env.example"


def test_env_example_uses_the_kit_verified_aws_and_model_contract() -> None:
    content = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "AWS_PROFILE=legal-kit" in content
    assert "AWS_REGION=ap-northeast-2" in content
    assert "BEDROCK_MODEL_ID_EMBED=global.cohere.embed-v4:0" in content
    assert "EMBEDDING_DIMENSION=1536" in content
    assert "BEDROCK_MODEL_ID_SONNET=global.anthropic.claude-sonnet-4-6" in content


def test_env_example_does_not_invite_secrets_or_unverified_model_ids() -> None:
    content = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "AWS_ACCESS_KEY_ID=" not in content
    assert "AWS_SECRET_ACCESS_KEY=" not in content
    assert "BEDROCK_MODEL_ID_OPUS=" not in content
    assert "BEDROCK_MODEL_ID_HAIKU=" not in content


def test_env_example_keeps_one_region_and_a_versionable_index_prefix() -> None:
    """AWS_REGION is the only region, and the index name is a prefix.

    A second BEDROCK_REGION can silently disagree with AWS_REGION, and a fixed
    OPENSEARCH_INDEX blocks the versioned index that ASSIGNMENT.md requires and
    RuntimeVersions.index records.
    """

    content = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "BEDROCK_REGION=" not in content
    assert "OPENSEARCH_INDEX_PREFIX=legal-agent-assessment" in content
    assert "\nOPENSEARCH_INDEX=" not in content
