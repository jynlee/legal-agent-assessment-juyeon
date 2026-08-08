from pathlib import Path

ENV_EXAMPLE = Path(__file__).parents[1] / ".env.example"


def test_env_example_uses_the_kit_verified_aws_and_model_contract() -> None:
    content = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "AWS_PROFILE=legal-kit" in content
    assert "AWS_REGION=ap-northeast-2" in content
    assert "BEDROCK_REGION=ap-northeast-2" in content
    assert "EMBEDDING_MODEL_ID=global.cohere.embed-v4:0" in content
    assert "EMBEDDING_DIMENSION=1536" in content
    assert "BEDROCK_MODEL_ID_SONNET=global.anthropic.claude-sonnet-4-6" in content


def test_env_example_does_not_invite_secrets_or_unverified_model_ids() -> None:
    content = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "AWS_ACCESS_KEY_ID=" not in content
    assert "AWS_SECRET_ACCESS_KEY=" not in content
    assert "BEDROCK_MODEL_ID_OPUS=" not in content
    assert "BEDROCK_MODEL_ID_HAIKU=" not in content


def test_env_example_keeps_regions_aligned_and_a_versionable_index_prefix() -> None:
    """Kit AWS regions stay aligned and the assessment index remains versionable."""

    content = ENV_EXAMPLE.read_text(encoding="utf-8")

    values = {
        key: value
        for key, value in (
            line.split("=", maxsplit=1)
            for line in content.splitlines()
            if line and not line.startswith("#") and "=" in line
        )
    }

    assert values["AWS_REGION"] == values["BEDROCK_REGION"]
    assert "OPENSEARCH_INDEX_PREFIX=legal-kit-assessment" in content
    assert "\nOPENSEARCH_INDEX=" not in content


def test_index_prefix_stays_inside_the_shared_iam_namespace() -> None:
    """The shared IAM policy allows `legal-kit-*` and implicitly denies the rest.

    A prefix outside that namespace makes every signed request 403 against the
    managed domain, and the failure only appears once a contributor leaves the
    local container.
    """

    content = ENV_EXAMPLE.read_text(encoding="utf-8")

    prefix = next(
        line.split("=", maxsplit=1)[1]
        for line in content.splitlines()
        if line.startswith("OPENSEARCH_INDEX_PREFIX=")
    )

    assert prefix.startswith("legal-kit-"), prefix
