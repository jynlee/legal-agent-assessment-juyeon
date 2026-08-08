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
    assert "BEDROCK_OPUS_MODEL_ID=" not in content
    assert "BEDROCK_HAIKU_MODEL_ID=" not in content
