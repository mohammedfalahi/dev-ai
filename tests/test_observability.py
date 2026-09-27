import pytest

from packages.observability.redaction import (
    is_sensitive_key,
    scrub_sensitive_data,
    scrub_string,
)
from packages.observability.tracing import (
    NoOpSpan,
    flush_tracing,
    get_langfuse_client,
    is_langfuse_enabled,
    observe,
    record_score,
    reset_client_state,
    trace_span,
    update_current_generation,
    update_current_span,
)


def test_is_sensitive_key():
    assert is_sensitive_key("authorization") is True
    assert is_sensitive_key("Authorization") is True
    assert is_sensitive_key("x-api-key") is True
    assert is_sensitive_key("api_key") is True
    assert is_sensitive_key("secret") is True
    assert is_sensitive_key("client_secret") is True
    assert is_sensitive_key("user_password") is True
    assert is_sensitive_key("access_token") is True
    assert is_sensitive_key("cookie") is True
    assert is_sensitive_key("normal_key") is False
    assert is_sensitive_key("service_name") is False


def test_scrub_string_patterns():
    # Bearer token
    s1 = "Request with Bearer abcdef1234567890 token"
    assert "Bearer [REDACTED]" in scrub_string(s1)

    # API key
    s2 = "My key is pk-lf-1234567890abcdef1234"
    assert "[REDACTED_API_KEY]" in scrub_string(s2)

    # Gemini key
    s3 = "Key AIzaSyABC123456789012345678901234567890 in log"
    assert "[REDACTED_KEY]" in scrub_string(s3)


def test_scrub_sensitive_data_nested():
    data = {
        "service": "checkout-api",
        "authorization": "Bearer super-secret-jwt",
        "api_key": "pk-lf-abcdef1234567890",
        "nested": {
            "password": "my_password",
            "normal_field": "ok",
            "token_store": ["secret1", "secret2"],
            "messages": ["Bearer my_token", "safe_string"],
        },
        "headers": [
            {"name": "x-api-key", "value": "secret-val"},
            {"name": "content-type", "value": "application/json"},
        ],
    }

    scrubbed = scrub_sensitive_data(data)

    assert scrubbed["service"] == "checkout-api"
    assert scrubbed["authorization"] == "[REDACTED]"
    assert scrubbed["api_key"] == "[REDACTED]"
    assert scrubbed["nested"]["password"] == "[REDACTED]"
    assert scrubbed["nested"]["normal_field"] == "ok"
    assert scrubbed["nested"]["token_store"] == "[REDACTED]"
    assert scrubbed["nested"]["messages"][0] == "Bearer [REDACTED]"
    assert scrubbed["nested"]["messages"][1] == "safe_string"
    assert scrubbed["headers"][0]["value"] == "[REDACTED]"
    assert scrubbed["headers"][1]["value"] == "application/json"


def test_noop_fallback_without_credentials(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr("packages.core.config.settings.langfuse_public_key", None)
    monkeypatch.setattr("packages.core.config.settings.langfuse_secret_key", None)
    reset_client_state()

    assert is_langfuse_enabled() is False
    assert get_langfuse_client() is None

    # Sync context manager
    with trace_span("test_span", as_type="span", input={"a": 1}) as span:
        assert isinstance(span, NoOpSpan)
        span.update(output={"b": 2})
        span.score(name="s", value=1.0)

    # Functions should be safe no-ops
    update_current_generation(model="test", input="in", output="out")
    update_current_span(name="span", output="out")
    record_score(name="test_score", value=0.95)
    flush_tracing()


@pytest.mark.asyncio
async def test_noop_async_context_and_decorators(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr("packages.core.config.settings.langfuse_public_key", None)
    monkeypatch.setattr("packages.core.config.settings.langfuse_secret_key", None)
    reset_client_state()

    # Async context manager
    async with trace_span("async_span", as_type="tool") as span:
        assert isinstance(span, NoOpSpan)
        span.update(output={"done": True})

    @observe(name="sync_fn")
    def sync_fn(x, y):
        return x + y

    assert sync_fn(3, 4) == 7

    @observe(name="async_fn")
    async def async_fn(x, y):
        return x * y

    res = await async_fn(5, 6)
    assert res == 30


def test_tracing_when_configured(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test-pub")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test-sec")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
    reset_client_state()

    try:
        assert is_langfuse_enabled() is True
        client = get_langfuse_client()
        assert client is not None

        # Verify context manager creates an actual observation wrapper
        with trace_span("test_configured_span", as_type="retriever", input={"q": "test"}) as span:
            span.update(output={"count": 1})
            assert span is not None

        # Record score without throwing
        record_score(name="unit_test_score", value=1.0)
    finally:
        reset_client_state()
