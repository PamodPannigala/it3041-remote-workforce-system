import abc
import asyncio
import json
import logging
import os
from typing import Any, Callable, Generic, TypeVar
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError

try:
    from google import genai
    from google.genai import errors as genai_errors, types as genai_types
    GENAI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore
    genai_errors = None  # type: ignore
    genai_types = None  # type: ignore
    GENAI_AVAILABLE = False

logger = logging.getLogger("remote_workforce.agents.llm_gateway")

T = TypeVar("T", bound=BaseModel)

MAX_PROMPT_CHARS = 50_000
MAX_OUTPUT_CHARS = 50_000
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3
MIN_TIMEOUT_SECONDS = 1.0
MAX_TIMEOUT_SECONDS = 300.0
MIN_MAX_RETRIES = 0
MAX_MAX_RETRIES = 5
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_TEMPERATURE = 0.2
MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0
DEFAULT_MAX_OUTPUT_TOKENS = 2048
MIN_MAX_OUTPUT_TOKENS = 1
MAX_MAX_OUTPUT_TOKENS = 8192


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


def _clean_gemini_schema(schema: Any) -> Any:
    """
    Recursively strips attributes incompatible with the Gemini Developer API schema parser.
    Preserves supported keywords: title, description, minimum, maximum, min_items (minItems),
    max_items (maxItems), min_length (minLength), max_length (maxLength), nullable, format,
    enum, required, properties, and items.
    Removes:
    1. additional_properties / additionalProperties (causes HTTP 400 Unknown name "additional_properties").
    2. min_items / max_items on arrays of nested objects (causes HTTP 400 Request contains an invalid argument).
    """
    if isinstance(schema, dict):
        schema.pop("additionalProperties", None)
        schema.pop("additional_properties", None)
        if schema.get("type") in ("array", "ARRAY"):
            items = schema.get("items")
            if isinstance(items, dict) and (items.get("type") in ("object", "OBJECT") or "properties" in items):
                schema.pop("maxItems", None)
                schema.pop("minItems", None)
                schema.pop("max_items", None)
                schema.pop("min_items", None)
        if "properties" in schema and isinstance(schema["properties"], dict):
            for prop in schema["properties"].values():
                _clean_gemini_schema(prop)
        if "items" in schema:
            _clean_gemini_schema(schema["items"])
        if "anyOf" in schema and isinstance(schema["anyOf"], list):
            for item in schema["anyOf"]:
                _clean_gemini_schema(item)
        return schema

    if not isinstance(schema, genai_types.Schema):
        return schema

    if hasattr(schema, "additional_properties"):
        schema.additional_properties = None

    # Strip min_items / max_items if array items are nested objects (incompatible in Gemini Developer API)
    if getattr(schema, "type", None) == genai_types.Type.ARRAY and schema.items is not None:
        if getattr(schema.items, "type", None) == genai_types.Type.OBJECT or getattr(schema.items, "properties", None):
            if hasattr(schema, "max_items"):
                schema.max_items = None
            if hasattr(schema, "min_items"):
                schema.min_items = None

    if schema.properties:
        for prop in schema.properties.values():
            _clean_gemini_schema(prop)
    if schema.items:
        _clean_gemini_schema(schema.items)
    if schema.any_of:
        for item in schema.any_of:
            _clean_gemini_schema(item)
    return schema


def _prepare_response_schema(response_model: type[BaseModel] | Any) -> Any:
    """Prepares a Pydantic model into a clean Gemini types.Schema for generate_content."""
    if not GENAI_AVAILABLE or genai_types is None:
        return response_model
    try:
        from google.genai import _transformers
        schema = _transformers.t_schema(None, response_model)
        return _clean_gemini_schema(schema)
    except Exception:
        return response_model


class GeminiLLMGateway(LLMGateway):
    """
    Production asynchronous gateway for Google Gemini models using the official google-genai SDK.
    Enforces strict timeouts, transient-only retries, structured JSON schema outputs, and Pydantic validation.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        client: Any | None = None,
        backoff_factor: float = 0.5,
    ):
        if not GENAI_AVAILABLE:
            raise LLMConfigurationError(
                "The google-genai package is required to use GeminiLLMGateway. Install with 'pip install google-genai'."
            )

        # 1. Validate API Key
        raw_key = (
            api_key
            if api_key is not None
            else (os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY", ""))
        )
        self._api_key = str(raw_key).strip()
        if not self._api_key:
            raise LLMConfigurationError(
                "Missing required LLM configuration: GEMINI_API_KEY is not set"
            )

        # 2. Validate Model
        raw_model = (
            model
            if model is not None
            else (os.getenv("GEMINI_MODEL") or os.getenv("LLM_MODEL", DEFAULT_GEMINI_MODEL))
        )
        self.model = str(raw_model).strip()
        if not self.model or len(self.model) > 100:
            raise LLMConfigurationError(
                "Invalid LLM configuration: GEMINI_MODEL must be a non-empty string up to 100 characters"
            )

        # 3. Validate Timeout Seconds
        raw_timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else (os.getenv("GEMINI_TIMEOUT_SECONDS") or os.getenv("LLM_TIMEOUT_SECONDS"))
        )
        if raw_timeout is not None:
            try:
                parsed_timeout = float(raw_timeout)
                if not (MIN_TIMEOUT_SECONDS <= parsed_timeout <= MAX_TIMEOUT_SECONDS):
                    raise LLMConfigurationError(
                        f"Invalid LLM configuration: GEMINI_TIMEOUT_SECONDS must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS}"
                    )
                self.timeout_seconds = parsed_timeout
            except (ValueError, TypeError):
                raise LLMConfigurationError(
                    f"Invalid LLM configuration: GEMINI_TIMEOUT_SECONDS must be a numeric value between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS}"
                ) from None
        else:
            self.timeout_seconds = DEFAULT_TIMEOUT_SECONDS

        # 4. Validate Max Retries
        raw_retries = (
            max_retries
            if max_retries is not None
            else (os.getenv("GEMINI_MAX_RETRIES") or os.getenv("LLM_MAX_RETRIES"))
        )
        if raw_retries is not None:
            try:
                parsed_retries = int(raw_retries)
                if not (MIN_MAX_RETRIES <= parsed_retries <= MAX_MAX_RETRIES):
                    raise LLMConfigurationError(
                        f"Invalid LLM configuration: GEMINI_MAX_RETRIES must be an integer between {MIN_MAX_RETRIES} and {MAX_MAX_RETRIES}"
                    )
                self.max_retries = parsed_retries
            except (ValueError, TypeError):
                raise LLMConfigurationError(
                    f"Invalid LLM configuration: GEMINI_MAX_RETRIES must be an integer between {MIN_MAX_RETRIES} and {MAX_MAX_RETRIES}"
                ) from None
        else:
            self.max_retries = DEFAULT_MAX_RETRIES

        # 5. Validate Temperature
        raw_temp = (
            temperature
            if temperature is not None
            else (os.getenv("GEMINI_TEMPERATURE") or os.getenv("LLM_TEMPERATURE"))
        )
        if raw_temp is not None:
            try:
                parsed_temp = float(raw_temp)
                if not (MIN_TEMPERATURE <= parsed_temp <= MAX_TEMPERATURE):
                    raise LLMConfigurationError(
                        f"Invalid LLM configuration: GEMINI_TEMPERATURE must be between {MIN_TEMPERATURE} and {MAX_TEMPERATURE}"
                    )
                self.temperature = parsed_temp
            except (ValueError, TypeError):
                raise LLMConfigurationError(
                    f"Invalid LLM configuration: GEMINI_TEMPERATURE must be a numeric value between {MIN_TEMPERATURE} and {MAX_TEMPERATURE}"
                ) from None
        else:
            self.temperature = DEFAULT_TEMPERATURE

        # 6. Validate Max Output Tokens
        raw_max_tokens = (
            max_output_tokens
            if max_output_tokens is not None
            else (os.getenv("GEMINI_MAX_OUTPUT_TOKENS") or os.getenv("LLM_MAX_OUTPUT_TOKENS"))
        )
        if raw_max_tokens is not None:
            try:
                parsed_max_tokens = int(raw_max_tokens)
                if not (MIN_MAX_OUTPUT_TOKENS <= parsed_max_tokens <= MAX_MAX_OUTPUT_TOKENS):
                    raise LLMConfigurationError(
                        f"Invalid LLM configuration: GEMINI_MAX_OUTPUT_TOKENS must be an integer between {MIN_MAX_OUTPUT_TOKENS} and {MAX_MAX_OUTPUT_TOKENS}"
                    )
                self.max_output_tokens = parsed_max_tokens
            except (ValueError, TypeError):
                raise LLMConfigurationError(
                    f"Invalid LLM configuration: GEMINI_MAX_OUTPUT_TOKENS must be an integer between {MIN_MAX_OUTPUT_TOKENS} and {MAX_MAX_OUTPUT_TOKENS}"
                ) from None
        else:
            self.max_output_tokens = DEFAULT_MAX_OUTPUT_TOKENS

        self._custom_client = client
        self._backoff_factor = max(float(backoff_factor), 0.0)
        self._client: Any = client if client is not None else None

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def aclose(self) -> None:
        """Close the underlying client resources if instantiated."""
        if self._client is not None and self._custom_client is None:
            aio_client = getattr(self._client, "aio", None)
            if aio_client is not None:
                if hasattr(aio_client, "aclose") and callable(aio_client.aclose):
                    await aio_client.aclose()
            self._client = None

    def __repr__(self) -> str:
        return f"GeminiLLMGateway(model={self.model!r})"

    def __str__(self) -> str:
        return f"GeminiLLMGateway(model={self.model!r})"

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

        # Enforce ONE overall deadline for all attempts and backoffs
        try:
            return await asyncio.wait_for(
                self._execute_with_retries(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=response_model,
                    correlation_id=correlation_id,
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise LLMTimeoutError(
                f"Gemini provider request exceeded overall timeout limit of {self.timeout_seconds}s"
            ) from None

    async def _execute_with_retries(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        correlation_id: str,
    ) -> LLMResult[T]:
        prepared_schema = _prepare_response_schema(response_model)
        config = genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            response_mime_type="application/json",
            response_schema=prepared_schema,
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
        )

        # Safe logging with correlation_id and model only; prompts and API keys are strictly forbidden
        logger.info(
            "Executing structured Gemini LLM request for correlation_id=%s model=%s",
            correlation_id,
            self.model,
        )

        attempts = 0
        last_error: Exception | None = None
        client = self._get_client()

        while attempts <= self.max_retries:
            attempts += 1
            try:
                response = await client.aio.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=config,
                )
                return self._parse_and_validate(response, response_model, correlation_id)

            except asyncio.CancelledError:
                # Task cancellation must always propagate immediately
                raise

            except (genai_errors.ClientError, genai_errors.APIError) as exc:
                status_code = getattr(exc, "code", None)
                if status_code in (401, 403):
                    # Authentication/permission failure: never retry
                    raise LLMAuthenticationError(
                        f"Gemini authentication failed with HTTP {status_code}"
                    ) from None

                if status_code in (400, 404, 422):
                    # Client request failure: never retry
                    raise LLMRequestError(
                        f"Gemini provider rejected request with HTTP {status_code}"
                    ) from None

                if status_code == 429:
                    # Rate limiting / quota exceeded: transient failure
                    last_error = LLMUnavailableError(
                        "Gemini rate limit or quota exceeded (HTTP 429)"
                    )
                    if attempts <= self.max_retries:
                        await self._backoff(attempts)
                        continue
                    raise last_error from None

                if isinstance(exc, genai_errors.ServerError) or (status_code and status_code >= 500):
                    # Server error: transient failure
                    last_error = LLMUnavailableError(
                        f"Gemini server error (HTTP {status_code})"
                    )
                    if attempts <= self.max_retries:
                        await self._backoff(attempts)
                        continue
                    raise last_error from None

                last_error = LLMUnavailableError(
                    f"Gemini API error (HTTP {status_code})"
                )
                if attempts <= self.max_retries:
                    await self._backoff(attempts)
                    continue
                raise last_error from None

            except (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException):
                last_error = LLMTimeoutError("Gemini provider request timed out")
                if attempts <= self.max_retries:
                    await self._backoff(attempts)
                    continue
                raise last_error from None

            except (httpx.TransportError, ConnectionError):
                last_error = LLMUnavailableError("Gemini provider network transport error")
                if attempts <= self.max_retries:
                    await self._backoff(attempts)
                    continue
                raise last_error from None

            except LLMResponseValidationError:
                # Output parsing/validation error: never retry
                raise

            except Exception as exc:
                err_str = str(exc).lower()
                if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                    last_error = LLMUnavailableError("Gemini rate limit or quota exceeded")
                    if attempts <= self.max_retries:
                        await self._backoff(attempts)
                        continue
                    raise last_error from None
                if "401" in err_str or "403" in err_str or "permission" in err_str or "unauthenticated" in err_str:
                    raise LLMAuthenticationError("Gemini authentication failed") from None

                last_error = LLMUnavailableError(f"Gemini provider error: {type(exc).__name__}")
                if attempts <= self.max_retries:
                    await self._backoff(attempts)
                    continue
                raise last_error from None

        if last_error:
            raise last_error
        raise LLMUnavailableError("Gemini provider unavailable after retries")

    async def _backoff(self, attempt: int) -> None:
        if self._backoff_factor > 0:
            delay = self._backoff_factor * (2 ** (attempt - 1))
            await asyncio.sleep(delay)

    def _parse_and_validate(
        self,
        response: Any,
        response_model: type[T],
        correlation_id: str,
    ) -> LLMResult[T]:
        if response is None:
            raise LLMResponseValidationError("Gemini response is None")

        # 1. Inspect candidates and finish reason
        candidates = getattr(response, "candidates", None)
        if not candidates or len(candidates) == 0:
            prompt_feedback = getattr(response, "prompt_feedback", None)
            block_reason = getattr(prompt_feedback, "block_reason", None) if prompt_feedback else None
            if block_reason:
                raise LLMResponseValidationError(f"Gemini request was blocked by prompt safety filter ({block_reason})")
            raise LLMResponseValidationError("Gemini response returned no candidates")

        candidate = candidates[0]
        finish_reason = getattr(candidate, "finish_reason", None)
        finish_reason_str = str(finish_reason).upper() if finish_reason else ""
        if any(
            blocked in finish_reason_str
            for blocked in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED", "SPII")
        ):
            raise LLMResponseValidationError(
                f"Gemini response was blocked by safety policy (finish_reason: {finish_reason})"
            )

        # 2. Extract structured output
        validated_model: T
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            if isinstance(parsed, response_model):
                validated_model = parsed
            elif isinstance(parsed, BaseModel):
                try:
                    validated_model = response_model.model_validate(parsed.model_dump())
                except ValidationError:
                    raise LLMResponseValidationError("Gemini parsed response failed Pydantic schema validation") from None
            elif isinstance(parsed, dict):
                try:
                    validated_model = response_model.model_validate(parsed)
                except ValidationError:
                    raise LLMResponseValidationError("Gemini parsed response failed Pydantic schema validation") from None
            else:
                try:
                    validated_model = response_model.model_validate(parsed)
                except ValidationError:
                    raise LLMResponseValidationError("Gemini parsed response failed Pydantic schema validation") from None
        else:
            text = getattr(response, "text", None)
            if text is None or not str(text).strip():
                raise LLMResponseValidationError("Gemini response missing text content")

            text_str = str(text).strip()
            if len(text_str) > MAX_OUTPUT_CHARS:
                raise LLMResponseValidationError(
                    f"Gemini response length ({len(text_str)}) exceeds maximum allowed limit of {MAX_OUTPUT_CHARS} characters"
                )

            try:
                parsed_json = json.loads(text_str)
            except (json.JSONDecodeError, TypeError):
                raise LLMResponseValidationError("Gemini output is not valid JSON") from None

            try:
                validated_model = response_model.model_validate(parsed_json)
            except ValidationError:
                raise LLMResponseValidationError("Gemini response failed Pydantic schema validation") from None

        # 3. Extract token usage metadata safely
        usage: LLMUsage | None = None
        usage_meta = getattr(response, "usage_metadata", None)
        if usage_meta is not None:
            try:
                p_tok = int(getattr(usage_meta, "prompt_token_count", 0) or 0)
                c_tok = int(getattr(usage_meta, "candidates_token_count", 0) or 0)
                t_tok = int(getattr(usage_meta, "total_token_count", 0) or (p_tok + c_tok))
                usage = LLMUsage(
                    prompt_tokens=p_tok,
                    completion_tokens=c_tok,
                    total_tokens=t_tok,
                )
            except (ValueError, TypeError):
                usage = None

        request_id = getattr(response, "response_id", None)
        if request_id is not None:
            request_id = str(request_id)

        return LLMResult(
            content=validated_model,
            model=self.model,
            usage=usage,
            request_id=request_id,
        )


def create_production_llm_gateway(provider: str | None = None) -> LLMGateway:
    """
    Factory function to create production LLM gateways based on environment configuration.
    Strictly fails closed: never silently falls back to FakeLLMGateway.
    FakeLLMGateway is only available as an explicitly injected test double.
    """
    selected_provider = (
        provider
        if provider is not None
        else (os.getenv("LLM_PROVIDER") or "")
    ).strip().lower()

    if selected_provider == "gemini":
        return GeminiLLMGateway()

    if selected_provider in ("openai", "openai_compatible"):
        return OpenAICompatibleLLMGateway()

    if not selected_provider:
        if os.getenv("GEMINI_API_KEY"):
            return GeminiLLMGateway()
        if os.getenv("LLM_API_KEY"):
            return OpenAICompatibleLLMGateway()
        raise LLMConfigurationError(
            "Missing required LLM configuration: LLM_PROVIDER is not set and no valid API key was found"
        )

    if selected_provider == "fake":
        raise LLMConfigurationError(
            "FakeLLMGateway cannot be selected by production configuration; it is strictly an offline test double"
        )

    raise LLMConfigurationError(
        f"Unsupported LLM provider: '{selected_provider}'. Supported providers are: 'gemini', 'openai_compatible'"
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
