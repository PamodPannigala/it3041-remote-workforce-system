import asyncio
import json
import logging
from typing import Any
import pytest
from pydantic import BaseModel, Field

from backend.app.modules.agents.llm_gateway import (
    DEFAULT_GEMINI_MODEL,
    GeminiLLMGateway,
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMRequestError,
    LLMResponseValidationError,
    LLMTimeoutError,
    LLMUnavailableError,
    create_production_llm_gateway,
)
from google.genai import errors as genai_errors, types as genai_types


class DummyOutputSchema(BaseModel):
    analysis: str
    score: int = Field(ge=0, le=100)
    recommendations: list[str] = Field(default_factory=list)


class MockCandidate:
    def __init__(self, finish_reason="STOP"):
        self.finish_reason = finish_reason


class MockUsageMetadata:
    def __init__(self, prompt_tokens=15, candidates_tokens=25, total_tokens=40):
        self.prompt_token_count = prompt_tokens
        self.candidates_token_count = candidates_tokens
        self.total_token_count = total_tokens


class MockGenerateContentResponse:
    def __init__(
        self,
        parsed=None,
        text=None,
        candidates=None,
        prompt_feedback=None,
        usage_metadata=None,
        response_id="mock-resp-123",
    ):
        self.parsed = parsed
        self.text = text
        self.candidates = candidates if candidates is not None else [MockCandidate("STOP")]
        self.prompt_feedback = prompt_feedback
        self.usage_metadata = usage_metadata or MockUsageMetadata()
        self.response_id = response_id


class MockModels:
    def __init__(self, generate_content_func=None):
        self._generate_content_func = generate_content_func
        self.call_count = 0
        self.last_kwargs: dict[str, Any] = {}

    async def generate_content(self, **kwargs):
        self.call_count += 1
        self.last_kwargs = kwargs
        if self._generate_content_func:
            res = self._generate_content_func(**kwargs)
            if asyncio.iscoroutine(res):
                return await res
            return res
        return MockGenerateContentResponse(
            text=json.dumps({"analysis": "Default mock analysis", "score": 80, "recommendations": ["Do work"]})
        )


class MockAioClient:
    def __init__(self, generate_content_func=None):
        self.models = MockModels(generate_content_func)
        self.closed = False

    async def aclose(self):
        self.closed = True


class MockGenAIClient:
    def __init__(self, generate_content_func=None):
        self.aio = MockAioClient(generate_content_func)


# =========================================================================
# 1. Configuration & Validation Tests
# =========================================================================


def test_missing_api_key_raises_configuration_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError) as exc:
        GeminiLLMGateway(api_key="")
    assert "GEMINI_API_KEY" in str(exc.value)


def test_blank_api_key_raises_configuration_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError) as exc:
        GeminiLLMGateway(api_key="   ")
    assert "GEMINI_API_KEY" in str(exc.value)


def test_valid_configuration_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-test-key-12345")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "45.0")
    monkeypatch.setenv("GEMINI_MAX_RETRIES", "2")
    monkeypatch.setenv("GEMINI_TEMPERATURE", "0.5")
    monkeypatch.setenv("GEMINI_MAX_OUTPUT_TOKENS", "4096")

    client = MockGenAIClient()
    gw = GeminiLLMGateway(client=client)
    assert gw.model == "gemini-2.5-flash"
    assert gw.timeout_seconds == 45.0
    assert gw.max_retries == 2
    assert gw.temperature == 0.5
    assert gw.max_output_tokens == 4096


@pytest.mark.parametrize("invalid_model", ["", "   ", "x" * 101])
def test_invalid_model_raises_configuration_error(invalid_model):
    with pytest.raises(LLMConfigurationError) as exc:
        GeminiLLMGateway(api_key="valid-key", model=invalid_model)
    assert "GEMINI_MODEL" in str(exc.value)


@pytest.mark.parametrize("invalid_timeout", ["not-a-number", 0.5, 301.0, -5.0])
def test_invalid_timeout_raises_configuration_error(invalid_timeout):
    with pytest.raises(LLMConfigurationError) as exc:
        GeminiLLMGateway(api_key="valid-key", timeout_seconds=invalid_timeout)
    assert "GEMINI_TIMEOUT_SECONDS" in str(exc.value)


@pytest.mark.parametrize("invalid_retries", ["not-an-int", -1, 6, 100])
def test_invalid_max_retries_raises_configuration_error(invalid_retries):
    with pytest.raises(LLMConfigurationError) as exc:
        GeminiLLMGateway(api_key="valid-key", max_retries=invalid_retries)
    assert "GEMINI_MAX_RETRIES" in str(exc.value)


@pytest.mark.parametrize("invalid_temp", ["not-a-float", -0.1, 2.1])
def test_invalid_temperature_raises_configuration_error(invalid_temp):
    with pytest.raises(LLMConfigurationError) as exc:
        GeminiLLMGateway(api_key="valid-key", temperature=invalid_temp)
    assert "GEMINI_TEMPERATURE" in str(exc.value)


@pytest.mark.parametrize("invalid_max_tokens", ["not-an-int", 0, -10, 8193])
def test_invalid_max_output_tokens_raises_configuration_error(invalid_max_tokens):
    with pytest.raises(LLMConfigurationError) as exc:
        GeminiLLMGateway(api_key="valid-key", max_output_tokens=invalid_max_tokens)
    assert "GEMINI_MAX_OUTPUT_TOKENS" in str(exc.value)


# =========================================================================
# 2. Factory Tests (Fail-Closed & Provider Selection)
# =========================================================================


def test_factory_creates_gemini_gateway(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-factory-123")
    gw = create_production_llm_gateway()
    assert isinstance(gw, GeminiLLMGateway)
    assert gw.model == DEFAULT_GEMINI_MODEL


def test_factory_creates_openai_compatible_gateway(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_KEY", "test-openai-key")
    gw = create_production_llm_gateway()
    assert gw.__class__.__name__ == "OpenAICompatibleLLMGateway"


def test_factory_never_returns_fake_gateway(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    with pytest.raises(LLMConfigurationError) as exc:
        create_production_llm_gateway()
    assert "FakeLLMGateway cannot be selected by production configuration" in str(exc.value)


def test_factory_fails_closed_on_unsupported_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unsupported_provider_xyz")
    with pytest.raises(LLMConfigurationError) as exc:
        create_production_llm_gateway()
    assert "Unsupported LLM provider" in str(exc.value)


def test_factory_fails_closed_when_no_provider_and_no_keys(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError) as exc:
        create_production_llm_gateway()
    assert "Missing required LLM configuration" in str(exc.value)


# =========================================================================
# 3. Structured Generation & Parameter Mapping Tests
# =========================================================================


@pytest.mark.asyncio
async def test_successful_structured_generation_via_text():
    mock_payload = {
        "analysis": "Team productivity is strong across all metrics.",
        "score": 92,
        "recommendations": ["Maintain current cadence", "Review blockers"],
    }
    mock_client = MockGenAIClient(
        generate_content_func=lambda **kwargs: MockGenerateContentResponse(
            text=json.dumps(mock_payload),
            response_id="gemini-resp-001",
            usage_metadata=MockUsageMetadata(prompt_tokens=50, candidates_tokens=30, total_tokens=80),
        )
    )

    gw = GeminiLLMGateway(
        api_key="test-key-mock",
        model="gemini-2.5-flash",
        temperature=0.3,
        max_output_tokens=1024,
        client=mock_client,
        backoff_factor=0.0,
    )

    result = await gw.generate_structured(
        system_prompt="You are a productivity expert.",
        user_prompt="Analyze team throughput.",
        response_model=DummyOutputSchema,
        correlation_id="corr-test-123",
    )

    assert isinstance(result.content, DummyOutputSchema)
    assert result.content.analysis == "Team productivity is strong across all metrics."
    assert result.content.score == 92
    assert result.content.recommendations == ["Maintain current cadence", "Review blockers"]
    assert result.model == "gemini-2.5-flash"
    assert result.request_id == "gemini-resp-001"
    assert result.usage is not None
    assert result.usage.prompt_tokens == 50
    assert result.usage.completion_tokens == 30
    assert result.usage.total_tokens == 80

    # Verify parameter mapping in call to SDK
    last_kwargs = mock_client.aio.models.last_kwargs
    assert last_kwargs["model"] == "gemini-2.5-flash"
    assert last_kwargs["contents"] == "Analyze team throughput."
    config = last_kwargs["config"]
    assert config.system_instruction == "You are a productivity expert."
    assert config.temperature == 0.3
    assert config.response_schema is not None
    assert getattr(config.response_schema, "type", None) == genai_types.Type.OBJECT


@pytest.mark.asyncio
async def test_successful_structured_generation_via_parsed():
    parsed_model = DummyOutputSchema(
        analysis="Parsed directly by SDK",
        score=88,
        recommendations=["Action 1"],
    )
    mock_client = MockGenAIClient(
        generate_content_func=lambda **kwargs: MockGenerateContentResponse(
            parsed=parsed_model,
            response_id="gemini-parsed-002",
        )
    )

    gw = GeminiLLMGateway(api_key="test-key", client=mock_client, backoff_factor=0.0)
    result = await gw.generate_structured(
        system_prompt="Sys",
        user_prompt="User",
        response_model=DummyOutputSchema,
        correlation_id="corr-parsed",
    )
    assert result.content.analysis == "Parsed directly by SDK"
    assert result.content.score == 88


# =========================================================================
# 4. Error Mapping & Bounded Retries Tests
# =========================================================================


@pytest.mark.asyncio
async def test_authentication_error_never_retried():
    attempts = 0

    def fail_auth(**kwargs):
        nonlocal attempts
        attempts += 1
        raise genai_errors.ClientError(401, {"error": {"message": "Invalid API Key", "code": 401}})

    mock_client = MockGenAIClient(generate_content_func=fail_auth)
    gw = GeminiLLMGateway(api_key="bad-key", max_retries=3, client=mock_client, backoff_factor=0.0)

    with pytest.raises(LLMAuthenticationError) as exc:
        await gw.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
    assert "Gemini authentication failed" in str(exc.value)
    assert attempts == 1  # Strictly never retried


@pytest.mark.asyncio
async def test_client_error_400_never_retried():
    attempts = 0

    def fail_client_error(**kwargs):
        nonlocal attempts
        attempts += 1
        raise genai_errors.ClientError(400, {"error": {"message": "Bad Request", "code": 400}})

    mock_client = MockGenAIClient(generate_content_func=fail_client_error)
    gw = GeminiLLMGateway(api_key="key", max_retries=3, client=mock_client, backoff_factor=0.0)

    with pytest.raises(LLMRequestError) as exc:
        await gw.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
    assert "rejected request with HTTP 400" in str(exc.value)
    assert attempts == 1


@pytest.mark.asyncio
async def test_rate_limit_429_retried_and_raises_unavailable():
    attempts = 0

    def fail_429(**kwargs):
        nonlocal attempts
        attempts += 1
        raise genai_errors.ClientError(429, {"error": {"message": "Quota exceeded", "code": 429}})

    mock_client = MockGenAIClient(generate_content_func=fail_429)
    gw = GeminiLLMGateway(api_key="key", max_retries=2, client=mock_client, backoff_factor=0.0)

    with pytest.raises(LLMUnavailableError) as exc:
        await gw.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
    assert "rate limit or quota exceeded" in str(exc.value)
    assert attempts == 3  # Initial attempt + 2 retries


@pytest.mark.asyncio
async def test_server_error_500_retried_and_recovers():
    attempts = 0

    def fail_then_succeed(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise genai_errors.ServerError(503, {"error": {"message": "Service unavailable", "code": 503}})
        return MockGenerateContentResponse(
            text=json.dumps({"analysis": "Recovered after retry", "score": 90, "recommendations": []})
        )

    mock_client = MockGenAIClient(generate_content_func=fail_then_succeed)
    gw = GeminiLLMGateway(api_key="key", max_retries=3, client=mock_client, backoff_factor=0.0)

    result = await gw.generate_structured(
        system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
    )
    assert result.content.analysis == "Recovered after retry"
    assert attempts == 3


@pytest.mark.asyncio
async def test_timeout_error_retried():
    attempts = 0

    def fail_timeout(**kwargs):
        nonlocal attempts
        attempts += 1
        raise asyncio.TimeoutError()

    mock_client = MockGenAIClient(generate_content_func=fail_timeout)
    gw = GeminiLLMGateway(api_key="key", max_retries=1, client=mock_client, backoff_factor=0.0)

    with pytest.raises(LLMTimeoutError) as exc:
        await gw.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
    assert "timed out" in str(exc.value)
    assert attempts == 2


@pytest.mark.asyncio
async def test_cancellation_propagates_immediately():
    attempts = 0

    def cancel_call(**kwargs):
        nonlocal attempts
        attempts += 1
        raise asyncio.CancelledError()

    mock_client = MockGenAIClient(generate_content_func=cancel_call)
    gw = GeminiLLMGateway(api_key="key", max_retries=3, client=mock_client, backoff_factor=0.0)

    with pytest.raises(asyncio.CancelledError):
        await gw.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
    assert attempts == 1  # Never retried on task cancellation


# =========================================================================
# 5. Output Validation & Safety Tests
# =========================================================================


@pytest.mark.asyncio
async def test_malformed_json_raises_validation_error():
    mock_client = MockGenAIClient(
        generate_content_func=lambda **kwargs: MockGenerateContentResponse(
            text="This is not valid JSON string {"
        )
    )
    gw = GeminiLLMGateway(api_key="key", client=mock_client, backoff_factor=0.0)

    with pytest.raises(LLMResponseValidationError) as exc:
        await gw.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
    assert "not valid JSON" in str(exc.value)


@pytest.mark.asyncio
async def test_schema_mismatch_raises_validation_error():
    # Missing required field 'score'
    mock_client = MockGenAIClient(
        generate_content_func=lambda **kwargs: MockGenerateContentResponse(
            text=json.dumps({"analysis": "Only analysis, missing score"})
        )
    )
    gw = GeminiLLMGateway(api_key="key", client=mock_client, backoff_factor=0.0)

    with pytest.raises(LLMResponseValidationError) as exc:
        await gw.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
    assert "failed Pydantic schema validation" in str(exc.value)


@pytest.mark.asyncio
async def test_empty_candidates_raises_validation_error():
    mock_client = MockGenAIClient(
        generate_content_func=lambda **kwargs: MockGenerateContentResponse(candidates=[])
    )
    gw = GeminiLLMGateway(api_key="key", client=mock_client, backoff_factor=0.0)

    with pytest.raises(LLMResponseValidationError) as exc:
        await gw.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
    assert "returned no candidates" in str(exc.value)


@pytest.mark.asyncio
async def test_safety_blocked_candidate_raises_validation_error():
    mock_client = MockGenAIClient(
        generate_content_func=lambda **kwargs: MockGenerateContentResponse(
            candidates=[MockCandidate(finish_reason="SAFETY")]
        )
    )
    gw = GeminiLLMGateway(api_key="key", client=mock_client, backoff_factor=0.0)

    with pytest.raises(LLMResponseValidationError) as exc:
        await gw.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
    assert "blocked by safety policy" in str(exc.value)


@pytest.mark.asyncio
async def test_output_size_exact_boundary_limits():
    # Exactly 50,000 chars total length
    prefix = '{"analysis": "'
    suffix = '", "score": 75, "recommendations": []}'
    pad_len = 50_000 - len(prefix) - len(suffix)
    exact_50k_text = prefix + ("a" * pad_len) + suffix
    assert len(exact_50k_text) == 50_000

    mock_client_50k = MockGenAIClient(
        generate_content_func=lambda **kwargs: MockGenerateContentResponse(text=exact_50k_text)
    )
    gw_50k = GeminiLLMGateway(api_key="key", client=mock_client_50k, backoff_factor=0.0)
    res = await gw_50k.generate_structured(
        system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
    )
    assert len(res.content.analysis) == pad_len

    # 50,001 chars exceeds MAX_OUTPUT_CHARS
    over_50k_text = exact_50k_text + "x"
    assert len(over_50k_text) == 50_001
    mock_client_over = MockGenAIClient(
        generate_content_func=lambda **kwargs: MockGenerateContentResponse(text=over_50k_text)
    )
    gw_over = GeminiLLMGateway(api_key="key", client=mock_client_over, backoff_factor=0.0)

    with pytest.raises(LLMResponseValidationError) as exc:
        await gw_over.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c2"
        )
    assert "exceeds maximum allowed limit of 50000 characters" in str(exc.value)


@pytest.mark.asyncio
async def test_model_string_passed_unchanged_without_double_prefixing():
    # Without models/ prefix
    mock_client_1 = MockGenAIClient()
    gw_1 = GeminiLLMGateway(api_key="test-key", model="gemini-3.6-flash", client=mock_client_1)
    await gw_1.generate_structured(
        system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
    )
    assert mock_client_1.aio.models.last_kwargs["model"] == "gemini-3.6-flash"

    # With models/ prefix
    mock_client_2 = MockGenAIClient()
    gw_2 = GeminiLLMGateway(api_key="test-key", model="models/gemini-3.6-flash", client=mock_client_2)
    await gw_2.generate_structured(
        system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c2"
    )
    assert mock_client_2.aio.models.last_kwargs["model"] == "models/gemini-3.6-flash"
    assert not mock_client_2.aio.models.last_kwargs["model"].startswith("models/models/")


@pytest.mark.asyncio
async def test_overall_timeout_bounds_all_retries_and_backoff():
    # Each attempt takes 0.4s; with 5 retries that would take >2.0s if not bounded overall
    async def slow_failing_call(**kwargs):
        await asyncio.sleep(0.4)
        raise genai_errors.ServerError(503, {"error": {"message": "Service unavailable", "code": 503}})

    mock_client = MockGenAIClient(generate_content_func=slow_failing_call)
    gw = GeminiLLMGateway(
        api_key="key",
        timeout_seconds=1.0,
        max_retries=5,
        client=mock_client,
        backoff_factor=0.05,
    )

    loop = asyncio.get_running_loop()
    start_time = loop.time()

    with pytest.raises(LLMTimeoutError) as exc:
        await gw.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )

    elapsed = loop.time() - start_time
    assert "overall timeout limit of 1.0s" in str(exc.value)
    # Elapsed time must be bounded by overall timeout budget (~1.0s), never multiplying across 5 retries
    assert elapsed < 1.4


# =========================================================================
# 6. Security, Redaction & Lifecycle Tests
# =========================================================================


def test_api_key_redacted_from_repr_and_str():
    secret = "secret-super-classified-api-key-999"
    gw = GeminiLLMGateway(api_key=secret, model="gemini-3.6-flash")
    assert secret not in repr(gw)
    assert secret not in str(gw)
    assert "gemini-3.6-flash" in repr(gw)


@pytest.mark.asyncio
async def test_safe_logging_never_logs_prompt_or_key(caplog):
    secret = "super-secret-gemini-token-777"
    system_prompt = "CONFIDENTIAL_GEMINI_SYSTEM_PROMPT"
    user_prompt = "CONFIDENTIAL_GEMINI_USER_PROMPT"
    correlation_id = "corr-gemini-audit-001"

    mock_client = MockGenAIClient()
    gw = GeminiLLMGateway(api_key=secret, client=mock_client, backoff_factor=0.0)

    with caplog.at_level(logging.INFO):
        await gw.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=DummyOutputSchema,
            correlation_id=correlation_id,
        )

    log_text = caplog.text
    assert correlation_id in log_text
    assert secret not in log_text
    assert system_prompt not in log_text
    assert user_prompt not in log_text


@pytest.mark.asyncio
async def test_async_close_lifecycle():
    mock_client = MockGenAIClient()
    gw = GeminiLLMGateway(api_key="test-key", client=mock_client)
    await gw.aclose()
    assert gw.model == DEFAULT_GEMINI_MODEL


# =========================================================================
# 7. Specialist Agent Smoke Test Tooling & Schema Compatibility Tests
# =========================================================================

from backend.scripts.smoke_test_gemini import (
    parse_args,
    run_agent_smoke_test,
    AGENT_SPECS,
    normalize_agent_name,
)
from backend.app.modules.agents import (
    ProductivityFindingOutput,
    CollaborationFindingOutput,
    WellbeingFindingOutput,
    TaskAssignmentFindingOutput,
)
from backend.app.modules.agents.llm_gateway import (
    _clean_gemini_schema,
    _prepare_response_schema,
)


def test_smoke_test_cli_agent_selection_and_mapping():
    # Test CLI parser arguments
    assert parse_args(["--agent", "productivity"]).agent == "productivity"
    assert parse_args(["--agent", "collaboration"]).agent == "collaboration"
    assert parse_args(["--agent", "wellbeing"]).agent == "wellbeing"
    assert parse_args(["--agent", "task_assignment"]).agent == "task_assignment"
    assert parse_args(["--agent", "task-assignment"]).agent == "task-assignment"
    assert parse_args([]).agent == "productivity"

    # Test exact response-model mapping
    assert AGENT_SPECS["productivity"]["response_model"] is ProductivityFindingOutput
    assert AGENT_SPECS["collaboration"]["response_model"] is CollaborationFindingOutput
    assert AGENT_SPECS["wellbeing"]["response_model"] is WellbeingFindingOutput
    assert AGENT_SPECS["task_assignment"]["response_model"] is TaskAssignmentFindingOutput

    # Test normalized name lookups
    assert normalize_agent_name("productivity") == "productivity"
    assert normalize_agent_name("task-assignment") == "task_assignment"
    assert normalize_agent_name("task_assignment") == "task_assignment"


@pytest.mark.asyncio
async def test_smoke_test_unknown_agent_rejection(capsys):
    success = await run_agent_smoke_test("invalid_agent_name")
    assert success is False
    captured = capsys.readouterr()
    assert "FAIL: Unknown agent 'invalid_agent_name'" in captured.out
    assert "GEMINI_API_KEY" not in captured.out


@pytest.mark.asyncio
async def test_smoke_test_makes_exactly_one_provider_call(capsys):
    mock_responses = {
        "productivity": {
            "summary": "Team productivity is on track.",
            "confidence": 0.95,
        },
        "collaboration": {
            "summary": "Team communication is healthy.",
            "confidence": 0.90,
        },
        "wellbeing": {
            "summary": "Team well-being metrics are stable.",
            "confidence": 0.85,
        },
        "task_assignment": {
            "summary": "Candidate C-01 recommended for task.",
            "confidence": 0.92,
        },
    }

    for agent_key, payload in mock_responses.items():
        mock_client = MockGenAIClient(
            generate_content_func=lambda **kwargs: MockGenerateContentResponse(
                text=json.dumps(payload),
                usage_metadata=MockUsageMetadata(prompt_tokens=40, candidates_tokens=60, total_tokens=100),
            )
        )
        gw = GeminiLLMGateway(api_key="test-key", client=mock_client, model="gemini-3.6-flash")

        success = await run_agent_smoke_test(agent_key, gateway=gw)
        assert success is True
        assert mock_client.aio.models.call_count == 1

        captured = capsys.readouterr()
        assert "PASS" in captured.out
        assert "Selected Schema:" in captured.out
        assert "Pydantic Schema Validation: True" in captured.out
        assert "test-key" not in captured.out
        assert "CONFIDENTIAL" not in captured.out


def test_schema_sanitizer_preserves_supported_constraints_and_removes_only_additional_properties():
    for model_cls in [
        ProductivityFindingOutput,
        CollaborationFindingOutput,
        WellbeingFindingOutput,
        TaskAssignmentFindingOutput,
    ]:
        schema = _prepare_response_schema(model_cls)
        assert schema is not None
        # additional_properties must be None at root
        assert getattr(schema, "additional_properties", None) is None
        # title, description must be preserved
        assert getattr(schema, "title", None) == model_cls.__name__
        assert getattr(schema, "description", None) is not None

        # Verify recursive sanitization on properties
        if hasattr(schema, "properties") and schema.properties:
            for prop_name, prop_val in schema.properties.items():
                assert getattr(prop_val, "additional_properties", None) is None
                # Title and constraints must be preserved
                assert getattr(prop_val, "title", None) is not None
                if prop_name == "confidence":
                    assert getattr(prop_val, "minimum", None) == 0.0
                    assert getattr(prop_val, "maximum", None) == 1.0

                if hasattr(prop_val, "items") and prop_val.items:
                    assert getattr(prop_val.items, "additional_properties", None) is None
                    if hasattr(prop_val.items, "properties") and prop_val.items.properties:
                        for inner_name, inner_val in prop_val.items.properties.items():
                            assert getattr(inner_val, "additional_properties", None) is None
                            assert getattr(inner_val, "title", None) is not None
                            if inner_name == "confidence":
                                assert getattr(inner_val, "minimum", None) == 0.0
                                assert getattr(inner_val, "maximum", None) == 1.0


def test_schema_sanitizer_normalizes_dict_keywords():
    raw_dict = {
        "title": "SampleSchema",
        "type": "object",
        "additionalProperties": False,
        "additional_properties": False,
        "properties": {
            "score": {
                "title": "Score",
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "additionalProperties": False,
            },
            "items": {
                "title": "Items",
                "type": "array",
                "minItems": 1,
                "maxItems": 10,
                "items": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 50,
                    "additionalProperties": False,
                },
            },
        },
    }

    cleaned = _clean_gemini_schema(raw_dict)
    assert "additionalProperties" not in cleaned
    assert "additional_properties" not in cleaned
    assert cleaned["title"] == "SampleSchema"
    assert cleaned["properties"]["score"]["minimum"] == 0.0
    assert cleaned["properties"]["score"]["maximum"] == 1.0
    assert "additionalProperties" not in cleaned["properties"]["score"]
    assert cleaned["properties"]["items"]["minItems"] == 1
    assert cleaned["properties"]["items"]["maxItems"] == 10
    assert "additionalProperties" not in cleaned["properties"]["items"]["items"]


@pytest.mark.asyncio
async def test_invalid_gemini_output_fails_local_pydantic_validation():
    # Return output missing required fields or violating bounds
    invalid_payload = {
        "summary": "Valid summary",
        "confidence": 1.5,  # Out of bounds (> 1.0)
    }
    mock_client = MockGenAIClient(
        generate_content_func=lambda **kwargs: MockGenerateContentResponse(
            text=json.dumps(invalid_payload)
        )
    )
    gw = GeminiLLMGateway(api_key="test-key", client=mock_client, model="gemini-3.1-flash-lite")

    with pytest.raises(LLMResponseValidationError) as exc:
        await gw.generate_structured(
            system_prompt="S",
            user_prompt="U",
            response_model=ProductivityFindingOutput,
            correlation_id="c-invalid-001",
        )
    assert "failed Pydantic schema validation" in str(exc.value)
