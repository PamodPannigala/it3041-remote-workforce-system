import abc
import asyncio
import json
import logging
import os
from typing import Any, Callable, Generic, TypeVar
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError

logger = logging.getLogger("remote_workforce.agents.llm_gateway")

T = TypeVar("T", bound=BaseModel)

MAX_PROMPT_CHARS = 50_000
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3
MIN_TIMEOUT_SECONDS = 1.0
MAX_TIMEOUT_SECONDS = 300.0
MIN_MAX_RETRIES = 0
MAX_MAX_RETRIES = 5


class LLMError(Exception):
    """Base exception for all LLM gateway errors."""
    pass


class LLMConfigurationError(LLMError):
    """Raised when LLM configuration is missing or invalid."""
    pass


class LLMUnavailableError(LLMError):
    """Raised when the LLM provider is unreachable, overloaded, or down."""
    pass


class LLMTimeoutError(LLMUnavailableError):
    """Raised when LLM request times out."""
    pass


class LLMAuthenticationError(LLMError):
    """Raised when LLM authentication or authorization fails (HTTP 401/403)."""
    pass


class LLMRequestError(LLMError):
    """Raised when LLM provider rejects request with a client error (e.g., HTTP 400)."""
    pass


class LLMResponseValidationError(LLMError):
    """Raised when provider output cannot be parsed as JSON or fails Pydantic schema validation."""
    pass


class LLMUsage(BaseModel):
    """Token usage metrics reported by the LLM provider."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResult(Generic[T]):
    """Container for validated structured LLM results with metadata."""

    def __init__(
        self,
        content: T,
        model: str,
        usage: LLMUsage | None = None,
        request_id: str | None = None,
    ):
        self.content = content
        self.model = model
        self.usage = usage
        self.request_id = request_id

    def __repr__(self) -> str:
        return f"LLMResult(model={self.model!r}, request_id={self.request_id!r})"


class LLMGateway(abc.ABC):
    """Abstract interface for all Agent LLM interactions."""

    @abc.abstractmethod
    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        correlation_id: str,
    ) -> LLMResult[T]:
        """
        Generate structured output validated against response_model.
        """
        pass


class OpenAICompatibleLLMGateway(LLMGateway):
    """
    Production asynchronous gateway for OpenAI-compatible Chat Completion providers.
    Enforces strict timeouts, transient-only retries, and Pydantic validation.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        http_client: httpx.AsyncClient | None = None,
        backoff_factor: float = 0.5,
    ):
        # 1. Validate API Key
        raw_key = api_key if api_key is not None else os.getenv("LLM_API_KEY", "")
        self.api_key = str(raw_key).strip()
        if not self.api_key:
            raise LLMConfigurationError("Missing required LLM configuration: LLM_API_KEY is not set")

        # 2. Validate Base URL
        raw_base_url = base_url if base_url is not None else os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        clean_url = str(raw_base_url).strip().rstrip("/")
        if not clean_url:
            raise LLMConfigurationError("Invalid LLM configuration: LLM_BASE_URL cannot be empty")
        parsed_url = urlparse(clean_url)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            raise LLMConfigurationError(
                "Invalid LLM configuration: LLM_BASE_URL must be a valid HTTP or HTTPS URL"
            )
        self.base_url = clean_url

        # 3. Validate Model
        raw_model = model if model is not None else os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.model = str(raw_model).strip()
        if not self.model or len(self.model) > 100:
            raise LLMConfigurationError("Invalid LLM configuration: LLM_MODEL must be a non-empty string up to 100 characters")

        # 4. Validate Timeout Seconds
        raw_timeout = timeout_seconds if timeout_seconds is not None else os.getenv("LLM_TIMEOUT_SECONDS")
        if raw_timeout is not None:
            try:
                parsed_timeout = float(raw_timeout)
                if not (MIN_TIMEOUT_SECONDS <= parsed_timeout <= MAX_TIMEOUT_SECONDS):
                    raise LLMConfigurationError(
                        f"Invalid LLM configuration: LLM_TIMEOUT_SECONDS must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS}"
                    )
                self.timeout_seconds = parsed_timeout
            except (ValueError, TypeError):
                raise LLMConfigurationError(
                    f"Invalid LLM configuration: LLM_TIMEOUT_SECONDS must be a numeric value between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS}"
                ) from None
        else:
            self.timeout_seconds = DEFAULT_TIMEOUT_SECONDS

        # 5. Validate Max Retries
        raw_retries = max_retries if max_retries is not None else os.getenv("LLM_MAX_RETRIES")
        if raw_retries is not None:
            try:
                parsed_retries = int(raw_retries)
                if not (MIN_MAX_RETRIES <= parsed_retries <= MAX_MAX_RETRIES):
                    raise LLMConfigurationError(
                        f"Invalid LLM configuration: LLM_MAX_RETRIES must be an integer between {MIN_MAX_RETRIES} and {MAX_MAX_RETRIES}"
                    )
                self.max_retries = parsed_retries
            except (ValueError, TypeError):
                raise LLMConfigurationError(
                    f"Invalid LLM configuration: LLM_MAX_RETRIES must be an integer between {MIN_MAX_RETRIES} and {MAX_MAX_RETRIES}"
                ) from None
        else:
            self.max_retries = DEFAULT_MAX_RETRIES

        self._custom_client = http_client
        self._backoff_factor = max(float(backoff_factor), 0.0)

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        correlation_id: str,
    ) -> LLMResult[T]:
        # Enforce prompt size limits to mitigate resource exhaustion
        if len(system_prompt) > MAX_PROMPT_CHARS or len(user_prompt) > MAX_PROMPT_CHARS:
            raise LLMRequestError(
                f"Prompt length exceeds maximum allowed limit of {MAX_PROMPT_CHARS} characters"
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        # Safe logging with correlation_id and model only; prompts and API keys are strictly forbidden
        logger.info(
            "Executing structured LLM request for correlation_id=%s model=%s",
            correlation_id,
            self.model,
        )

        attempts = 0
        last_error: Exception | None = None

        while attempts <= self.max_retries:
            attempts += 1
            try:
                if self._custom_client:
                    response = await self._custom_client.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=self.timeout_seconds,
                    )
                else:
                    async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                        response = await client.post(
                            url,
                            json=payload,
                            headers=headers,
                        )

                # Process HTTP status codes
                if response.status_code == 200:
                    try:
                        resp_json = response.json()
                    except Exception:
                        raise LLMResponseValidationError("LLM response body is not valid JSON") from None
                    return self._parse_and_validate(resp_json, response_model, correlation_id)

                if response.status_code in (401, 403):
                    # Authentication failure: never retry
                    raise LLMAuthenticationError(
                        f"LLM provider authentication failed with HTTP {response.status_code}"
                    )

                if response.status_code == 400:
                    # Client/request failure: never retry
                    raise LLMRequestError(
                        "LLM provider rejected request with HTTP 400 Bad Request"
                    )

                if response.status_code in (429, 500, 502, 503, 504):
                    # Transient error: retry if attempts remaining
                    last_error = LLMUnavailableError(
                        f"LLM provider transient failure (HTTP {response.status_code})"
                    )
                    if attempts <= self.max_retries:
                        await self._backoff(attempts)
                        continue
                    raise last_error

                # Any other unexpected non-200 status code
                raise LLMUnavailableError(
                    f"LLM provider returned unexpected status HTTP {response.status_code}"
                )

            except (httpx.TimeoutException, TimeoutError):
                last_error = LLMTimeoutError("LLM provider request timed out")
                if attempts <= self.max_retries:
                    await self._backoff(attempts)
                    continue
                raise last_error from None

            except httpx.TransportError:
                last_error = LLMUnavailableError("LLM provider network transport error")
                if attempts <= self.max_retries:
                    await self._backoff(attempts)
                    continue
                raise last_error from None

        if last_error:
            raise last_error
        raise LLMUnavailableError("LLM provider unavailable after retries")

    async def _backoff(self, attempt: int) -> None:
        if self._backoff_factor > 0:
            delay = self._backoff_factor * (2 ** (attempt - 1))
            await asyncio.sleep(delay)

    def _parse_and_validate(
        self,
        raw_data: Any,
        response_model: type[T],
        correlation_id: str,
    ) -> LLMResult[T]:
        if not isinstance(raw_data, dict):
            raise LLMResponseValidationError("LLM response is not a valid JSON object")

        choices = raw_data.get("choices")
        if not choices or not isinstance(choices, list) or len(choices) == 0:
            raise LLMResponseValidationError("LLM response missing or empty 'choices' list")

        choice = choices[0]
        if not isinstance(choice, dict):
            raise LLMResponseValidationError("LLM response choice is not a valid object")

        message = choice.get("message")
        if message is None or not isinstance(message, dict):
            raise LLMResponseValidationError("LLM response missing assistant message")

        content_str = message.get("content")
        if content_str is None or not isinstance(content_str, str) or not content_str.strip():
            raise LLMResponseValidationError("LLM response missing assistant text content")

        # Parse JSON content
        try:
            parsed_json = json.loads(content_str)
        except (json.JSONDecodeError, TypeError):
            raise LLMResponseValidationError("LLM output is not valid JSON") from None

        # Validate against strict Pydantic model
        try:
            validated_model = response_model.model_validate(parsed_json)
        except ValidationError:
            raise LLMResponseValidationError(
                "LLM response failed Pydantic schema validation"
            ) from None

        # Extract usage metadata safely
        usage_data = raw_data.get("usage")
        usage = None
        if isinstance(usage_data, dict):
            try:
                p_tok = int(usage_data.get("prompt_tokens") or 0)
                c_tok = int(usage_data.get("completion_tokens") or 0)
                t_tok = int(usage_data.get("total_tokens") or (p_tok + c_tok))
                usage = LLMUsage(
                    prompt_tokens=p_tok,
                    completion_tokens=c_tok,
                    total_tokens=t_tok,
                )
            except (ValueError, TypeError):
                usage = None

        model_name = str(raw_data.get("model") or self.model)
        request_id = str(raw_data.get("id")) if raw_data.get("id") is not None else None

        return LLMResult(
            content=validated_model,
            model=model_name,
            usage=usage,
            request_id=request_id,
        )


class FakeLLMGateway(LLMGateway):
    """
    Deterministic in-memory test double for unit testing agent workflows
    without network calls or external LLM credentials.
    """

    def __init__(
        self,
        default_response: BaseModel | None = None,
        handler: Callable[..., Any] | None = None,
    ):
        self.default_response = default_response
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def last_call(self) -> dict[str, Any] | None:
        return self.calls[-1] if self.calls else None

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        correlation_id: str,
    ) -> LLMResult[T]:
        call_record = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response_model": response_model,
            "correlation_id": correlation_id,
        }
        self.calls.append(call_record)

        if self.handler:
            result = self.handler(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
                correlation_id=correlation_id,
            )
            if asyncio.iscoroutine(result):
                result = await result
            if isinstance(result, BaseModel):
                content = response_model.model_validate(result.model_dump())
            elif isinstance(result, dict):
                content = response_model.model_validate(result)
            else:
                content = result
            return LLMResult(
                content=content,
                model="fake-llm-model",
                usage=LLMUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
                request_id=f"fake-req-{correlation_id}",
            )

        if self.default_response is not None:
            if isinstance(self.default_response, response_model):
                content = self.default_response
            elif isinstance(self.default_response, BaseModel):
                content = response_model.model_validate(self.default_response.model_dump())
            elif isinstance(self.default_response, dict):
                content = response_model.model_validate(self.default_response)
            else:
                content = self.default_response
            return LLMResult(
                content=content,
                model="fake-llm-model",
                usage=LLMUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
                request_id=f"fake-req-{correlation_id}",
            )

        raise LLMUnavailableError("FakeLLMGateway has no default_response or handler configured")
