import json
import logging
import httpx
from pydantic import BaseModel, Field
import pytest

from backend.app.modules.agents.llm_gateway import (
    FakeLLMGateway,
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMRequestError,
    LLMResponseValidationError,
    LLMTimeoutError,
    LLMUnavailableError,
    OpenAICompatibleLLMGateway,
)


class DummyOutputSchema(BaseModel):
    analysis: str
    score: int = Field(ge=0, le=100)
    recommendations: list[str] = Field(default_factory=list)


# =========================================================================
# Configuration Tests
# =========================================================================


def test_missing_api_key_raises_configuration_error(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError) as exc:
        OpenAICompatibleLLMGateway(api_key="")
    assert "LLM_API_KEY" in str(exc.value)


@pytest.mark.parametrize(
    "invalid_url",
    [
        "",
        "   ",
        "ftp://api.openai.com/v1",
        "not-a-url",
        "http://",
        "https://",
    ],
)
def test_invalid_base_url_raises_configuration_error(invalid_url):
    with pytest.raises(LLMConfigurationError) as exc:
        OpenAICompatibleLLMGateway(api_key="valid-key", base_url=invalid_url)
    assert "LLM_BASE_URL" in str(exc.value)


@pytest.mark.parametrize(
    "invalid_model",
    [
        "",
        "   ",
        "x" * 101,
    ],
)
def test_invalid_model_raises_configuration_error(invalid_model):
    with pytest.raises(LLMConfigurationError) as exc:
        OpenAICompatibleLLMGateway(api_key="valid-key", model=invalid_model)
    assert "LLM_MODEL" in str(exc.value)


@pytest.mark.parametrize(
    "invalid_timeout",
    [
        "not-a-number",
        0.5,
        301.0,
        -10.0,
    ],
)
def test_invalid_timeout_raises_configuration_error(invalid_timeout):
    with pytest.raises(LLMConfigurationError) as exc:
        OpenAICompatibleLLMGateway(api_key="valid-key", timeout_seconds=invalid_timeout)
    assert "LLM_TIMEOUT_SECONDS" in str(exc.value)


@pytest.mark.parametrize(
    "invalid_retries",
    [
        "not-an-int",
        -1,
        6,
        100,
    ],
)
def test_invalid_max_retries_raises_configuration_error(invalid_retries):
    with pytest.raises(LLMConfigurationError) as exc:
        OpenAICompatibleLLMGateway(api_key="valid-key", max_retries=invalid_retries)
    assert "LLM_MAX_RETRIES" in str(exc.value)


# =========================================================================
# Structured Response & Validation Tests
# =========================================================================


@pytest.mark.asyncio
async def test_successful_structured_generation():
    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["headers"] = dict(request.headers)
        captured_request["body"] = json.loads(request.read())

        response_payload = {
            "id": "chatcmpl-test-123",
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "analysis": "Team task distribution is balanced.",
                                "score": 85,
                                "recommendations": ["Review workload weekly"],
                            }
                        ),
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 45,
                "total_tokens": 165,
            },
        }
        return httpx.Response(200, json=response_payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(
            api_key="secret-api-key-test-12345",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            http_client=client,
            backoff_factor=0.0,
        )

        result = await gateway.generate_structured(
            system_prompt="You are a workforce analytics specialist.",
            user_prompt="Evaluate current sprint tasks.",
            response_model=DummyOutputSchema,
            correlation_id="corr-abc-123",
        )

        assert result.content.analysis == "Team task distribution is balanced."
        assert result.content.score == 85
        assert result.content.recommendations == ["Review workload weekly"]
        assert result.model == "gpt-4o-mini"
        assert result.request_id == "chatcmpl-test-123"
        assert result.usage is not None
        assert result.usage.total_tokens == 165

        # Verify internal headers
        assert captured_request["headers"]["authorization"] == "Bearer secret-api-key-test-12345"
        assert captured_request["body"]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_pydantic_response_validation():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"analysis": "Ok", "score": 90}),
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, backoff_factor=0.0)
        res = await gateway.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
        assert isinstance(res.content, DummyOutputSchema)
        assert res.content.score == 90


@pytest.mark.asyncio
async def test_api_key_absent_from_exceptions_and_logs(caplog):
    secret_key = "super-secret-production-key-999"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Internal server fault"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(
            api_key=secret_key,
            http_client=client,
            max_retries=1,
            backoff_factor=0.0,
        )

        with caplog.at_level(logging.INFO):
            with pytest.raises(LLMUnavailableError) as exc:
                await gateway.generate_structured(
                    system_prompt="System",
                    user_prompt="User",
                    response_model=DummyOutputSchema,
                    correlation_id="corr-1",
                )

        assert secret_key not in str(exc.value)
        assert secret_key not in repr(exc.value)
        assert secret_key not in caplog.text


@pytest.mark.asyncio
async def test_authorization_header_used_internally():
    captured_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": json.dumps({"analysis": "A", "score": 10})}}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="custom-secret-key-123", http_client=client, backoff_factor=0.0)
        await gateway.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
        assert captured_headers.get("authorization") == "Bearer custom-secret-key-123"


# =========================================================================
# Retries & Transport Error Tests
# =========================================================================


@pytest.mark.asyncio
async def test_timeout_behavior_and_retry():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ReadTimeout("Connection timed out after 30s")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(
            api_key="valid-key",
            http_client=client,
            max_retries=2,
            backoff_factor=0.0,
        )

        with pytest.raises(LLMTimeoutError):
            await gateway.generate_structured(
                system_prompt="System",
                user_prompt="User",
                response_model=DummyOutputSchema,
                correlation_id="corr-1",
            )

        assert call_count == 3


@pytest.mark.asyncio
async def test_transport_retry():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("Connection refused by peer")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": json.dumps({"analysis": "Connected", "score": 75})}}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, max_retries=2, backoff_factor=0.0)
        res = await gateway.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
        assert call_count == 2
        assert res.content.analysis == "Connected"


@pytest.mark.asyncio
async def test_http_429_retry():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, json={"error": "Rate limit exceeded"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": json.dumps({"analysis": "Rate cleared", "score": 80})}}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, max_retries=2, backoff_factor=0.0)
        res = await gateway.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
        assert call_count == 2
        assert res.content.analysis == "Rate cleared"


@pytest.mark.asyncio
async def test_http_5xx_retry():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(503, json={"error": "Service overloaded"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": json.dumps({"analysis": "Service recovered", "score": 85})}}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, max_retries=2, backoff_factor=0.0)
        res = await gateway.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
        assert call_count == 2
        assert res.content.analysis == "Service recovered"


@pytest.mark.asyncio
async def test_no_retry_for_client_error_400():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(400, json={"error": "Bad request"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, max_retries=3, backoff_factor=0.0)
        with pytest.raises(LLMRequestError):
            await gateway.generate_structured(
                system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
            )
        assert call_count == 1


@pytest.mark.asyncio
async def test_no_retry_for_auth_error_401_or_403():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, json={"error": "Unauthorized"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, max_retries=3, backoff_factor=0.0)
        with pytest.raises(LLMAuthenticationError):
            await gateway.generate_structured(
                system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
            )
        assert call_count == 1


# =========================================================================
# Provider Response Parsing Defects
# =========================================================================


@pytest.mark.asyncio
async def test_malformed_assistant_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "{not valid json}"}}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, backoff_factor=0.0)
        with pytest.raises(LLMResponseValidationError) as exc:
            await gateway.generate_structured(
                system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
            )
        assert "not valid JSON" in str(exc.value)


@pytest.mark.asyncio
async def test_schema_invalid_assistant_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": json.dumps({"analysis": "Ok", "score": 999})}}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, backoff_factor=0.0)
        with pytest.raises(LLMResponseValidationError) as exc:
            await gateway.generate_structured(
                system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
            )
        assert "schema validation" in str(exc.value)


@pytest.mark.asyncio
async def test_missing_choices():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, backoff_factor=0.0)
        with pytest.raises(LLMResponseValidationError) as exc:
            await gateway.generate_structured(
                system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
            )
        assert "missing or empty 'choices'" in str(exc.value)


@pytest.mark.asyncio
async def test_empty_choices():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, backoff_factor=0.0)
        with pytest.raises(LLMResponseValidationError) as exc:
            await gateway.generate_structured(
                system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
            )
        assert "missing or empty 'choices'" in str(exc.value)


@pytest.mark.asyncio
async def test_missing_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, backoff_factor=0.0)
        with pytest.raises(LLMResponseValidationError) as exc:
            await gateway.generate_structured(
                system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
            )
        assert "missing assistant message" in str(exc.value)


@pytest.mark.asyncio
async def test_missing_content():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {}}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, backoff_factor=0.0)
        with pytest.raises(LLMResponseValidationError) as exc:
            await gateway.generate_structured(
                system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
            )
        assert "missing assistant text content" in str(exc.value)


@pytest.mark.asyncio
async def test_non_string_content():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, backoff_factor=0.0)
        with pytest.raises(LLMResponseValidationError) as exc:
            await gateway.generate_structured(
                system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
            )
        assert "missing assistant text content" in str(exc.value)


@pytest.mark.asyncio
async def test_missing_or_malformed_usage_handled_gracefully():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"analysis": "Ok", "score": 50}),
                        }
                    }
                ],
                "usage": "malformed-not-a-dict",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(
            api_key="valid-key",
            http_client=client,
            backoff_factor=0.0,
        )

        result = await gateway.generate_structured(
            system_prompt="System",
            user_prompt="User",
            response_model=DummyOutputSchema,
            correlation_id="corr-1",
        )

        assert result.content.analysis == "Ok"
        assert result.usage is None


@pytest.mark.asyncio
async def test_non_json_provider_error_body_handled_safely():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html><body>502 Bad Gateway Nginx</body></html>")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(
            api_key="valid-key",
            http_client=client,
            max_retries=0,
            backoff_factor=0.0,
        )

        with pytest.raises(LLMUnavailableError) as exc:
            await gateway.generate_structured(
                system_prompt="System",
                user_prompt="User",
                response_model=DummyOutputSchema,
                correlation_id="corr-1",
            )
        assert "502" in str(exc.value)


@pytest.mark.asyncio
async def test_max_retry_enforcement():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, json={"error": "Internal error"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, max_retries=2, backoff_factor=0.0)
        with pytest.raises(LLMUnavailableError):
            await gateway.generate_structured(
                system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
            )
        assert call_count == 3


@pytest.mark.asyncio
async def test_prompt_size_limits():
    gateway = OpenAICompatibleLLMGateway(
        api_key="valid-key",
        backoff_factor=0.0,
    )

    oversized_prompt = "x" * 50001
    with pytest.raises(LLMRequestError) as exc:
        await gateway.generate_structured(
            system_prompt="System",
            user_prompt=oversized_prompt,
            response_model=DummyOutputSchema,
            correlation_id="corr-1",
        )
    assert "Prompt length exceeds" in str(exc.value)


@pytest.mark.asyncio
async def test_usage_parsing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": json.dumps({"analysis": "Ok", "score": 70})}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(api_key="valid-key", http_client=client, backoff_factor=0.0)
        res = await gateway.generate_structured(
            system_prompt="S", user_prompt="U", response_model=DummyOutputSchema, correlation_id="c1"
        )
        assert res.usage is not None
        assert res.usage.prompt_tokens == 50
        assert res.usage.completion_tokens == 20
        assert res.usage.total_tokens == 70


@pytest.mark.asyncio
async def test_correlation_only_safe_logging(caplog):
    secret_key = "sensitive-api-token-xyz"
    system_prompt = "CONFIDENTIAL_SYSTEM_INSTRUCTIONS_SECRET"
    user_prompt = "CONFIDENTIAL_USER_PROMPT_WITH_PRIVATE_EVIDENCE"
    correlation_id = "corr-audit-log-999"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"analysis": "Done", "score": 80}),
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = OpenAICompatibleLLMGateway(
            api_key=secret_key,
            http_client=client,
            backoff_factor=0.0,
        )

        with caplog.at_level(logging.INFO):
            await gateway.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=DummyOutputSchema,
                correlation_id=correlation_id,
            )

        log_text = caplog.text
        assert correlation_id in log_text
        assert secret_key not in log_text
        assert system_prompt not in log_text
        assert user_prompt not in log_text
        assert "Authorization" not in log_text
        assert "Bearer" not in log_text


# =========================================================================
# FakeLLMGateway Tests
# =========================================================================


@pytest.mark.asyncio
async def test_fake_llm_gateway_deterministic_default_response():
    fake_response = DummyOutputSchema(
        analysis="Simulated deterministic result",
        score=77,
        recommendations=["Action A", "Action B"],
    )
    fake_gateway = FakeLLMGateway(default_response=fake_response)

    result = await fake_gateway.generate_structured(
        system_prompt="System",
        user_prompt="User",
        response_model=DummyOutputSchema,
        correlation_id="corr-fake-1",
    )

    assert result.content.analysis == "Simulated deterministic result"
    assert result.content.score == 77
    assert len(result.content.recommendations) == 2
    assert fake_gateway.call_count == 1
    assert fake_gateway.last_call["correlation_id"] == "corr-fake-1"


@pytest.mark.asyncio
async def test_fake_llm_gateway_custom_handler():
    def custom_handler(system_prompt, user_prompt, response_model, correlation_id):
        return {
            "analysis": f"Handled for {correlation_id}",
            "score": 95,
            "recommendations": ["Custom action"],
        }

    fake_gateway = FakeLLMGateway(handler=custom_handler)

    result = await fake_gateway.generate_structured(
        system_prompt="System",
        user_prompt="User",
        response_model=DummyOutputSchema,
        correlation_id="corr-custom-99",
    )

    assert result.content.analysis == "Handled for corr-custom-99"
    assert result.content.score == 95
    assert fake_gateway.call_count == 1
