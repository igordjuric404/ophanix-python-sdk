# SPDX-License-Identifier: MIT
"""Thin Python client for calling the Tool Gateway HTTP contract."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import hmac
import ipaddress
import inspect
import json
import logging
import math
import os
import random
import re
import secrets
import threading
import time
import tomllib
import warnings
from dataclasses import dataclass, field
from datetime import timezone
from email.utils import parsedate_to_datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version
from pathlib import Path
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Literal, Mapping, Protocol, cast
from urllib.parse import quote
from urllib.parse import urlparse

import httpx

LOGGER = logging.getLogger(__name__)
SDK_PACKAGE_NAME = "ophanix-python-sdk"
COMPAT_PACKAGE_NAME = "ophanix-product-platform"


def _sdk_version() -> str:
    try:
        return version(SDK_PACKAGE_NAME)
    except PackageNotFoundError:
        try:
            return version(COMPAT_PACKAGE_NAME)
        except PackageNotFoundError:
            return _version_from_local_pyproject() or "0.0.0"


def _version_from_local_pyproject() -> str | None:
    for parent in Path(__file__).resolve().parents:
        pyproject = parent / "pyproject.toml"
        if not pyproject.exists():
            continue
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        name = data.get("project", {}).get("name")
        if name in {SDK_PACKAGE_NAME, COMPAT_PACKAGE_NAME}:
            project_version = data.get("project", {}).get("version")
            return project_version if isinstance(project_version, str) else None
    return None


GATEWAY_TOOL_DISCOVERY_PATH = "/api/v1/gateway/tools"
GATEWAY_CAPABILITIES_PATH = "/api/v1/gateway/capabilities"
GATEWAY_TOOL_INVOKE_PATH_PREFIX = "/api/v1/tools"
GATEWAY_TOOL_INVOKE_PATH_SUFFIX = "/invoke"
SDK_GATEWAY_CONTRACT_VERSION = "tool-gateway.v1"
SDK_VERSION = _sdk_version()
SDK_USER_AGENT = f"ophanix-tool-gateway-python/{SDK_VERSION}"
DEFAULT_GATEWAY_TOKEN_ENV_VAR = "OPHANIX_GATEWAY_TOKEN"
RETRYABLE_DISCOVERY_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
RETRYABLE_TOOL_CALL_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
DEFAULT_DISCOVERY_RETRY_MAX_SLEEP_SECONDS = 5.0
DEFAULT_DISCOVERY_RETRY_JITTER_RATIO = 0.2
DEFAULT_TOOL_CALL_RETRY_MAX_SLEEP_SECONDS = 5.0
DEFAULT_TOOL_CALL_RETRY_JITTER_RATIO = 0.2
DEFAULT_CACHE_TTL_SECONDS = 300.0
MAX_ERROR_BODY_STRING_LENGTH = 512
MAX_ERROR_BODY_ITEMS = 20
MAX_ERROR_BODY_DEPTH = 20
MAX_NON_JSON_ERROR_EXCERPT_BYTES = 2048
DEFAULT_MAX_PAYLOAD_BYTES = 1_000_000
DEFAULT_MAX_RESPONSE_BYTES = 1_000_000
DEFAULT_MAX_CACHE_ENTRIES = 256
MAX_GATEWAY_TOKEN_LENGTH = 4096
MAX_IDEMPOTENCY_KEY_LENGTH = 128
RAW_GATEWAY_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._~+/=-]+$")
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:/@+-]+$")
_CACHE_FINGERPRINT_KEY = secrets.token_bytes(32)
_ToolCacheKey = tuple[str, str]
_ListCacheKey = tuple[tuple[str, str], ...]
_ToolCacheValue = tuple[float, "ToolDefinition"]
_ListCacheValue = tuple[float, list["ToolDefinition"]]
TelemetryEventHook = Callable[[Mapping[str, Any]], None]
SENSITIVE_KEY_NAMES = frozenset(
    {
        "authorization",
        "api_key",
        "apikey",
        "client_secret",
        "credential",
        "credentials",
        "email",
        "email_address",
        "id_token",
        "key",
        "password",
        "passwd",
        "phone",
        "phone_number",
        "postal_address",
        "private_key",
        "pwd",
        "refresh_token",
        "secret",
        "social_security_number",
        "ssn",
        "token",
    }
)
SENSITIVE_KEY_SUFFIXES = ("_credential", "_key", "_password", "_secret", "_token")
BEARER_TOKEN_RE = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
SENSITIVE_TEXT_ASSIGNMENT_RE = re.compile(
    r"(?P<key>\b(?:"
    r"authorization|"
    r"api[-_\s]?key|apikey|"
    r"client[-_\s]?secret|"
    r"credential|"
    r"email|"
    r"id[-_\s]?token|"
    r"password|passwd|pwd|"
    r"phone|"
    r"private[-_\s]?key|"
    r"refresh[-_\s]?token|"
    r"access[-_\s]?token|"
    r"social[-_\s]?security[-_\s]?number|ssn|"
    r"secret|"
    r"token"
    r")\b)"
    r"(?P<before_sep>\s*)(?P<sep>[:=])(?P<after_sep>\s*)"
    r"(?P<value>bearer\s+[^\s,;]+|\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    re.IGNORECASE,
)


class TokenProvider(Protocol):
    """Supplies bearer tokens for gateway requests."""

    def get_token(self) -> str:
        """Return the raw bearer token without the `Bearer` prefix."""


class AsyncTokenProvider(Protocol):
    """Supplies bearer tokens for async gateway requests."""

    def get_token(self) -> str | Awaitable[str]:
        """Return, or awaitably return, the raw bearer token."""


@dataclass(frozen=True)
class StaticTokenProvider:
    """Token provider for callers that already have a long-lived gateway token."""

    token: str = field(repr=False)

    def get_token(self) -> str:
        return _require_text(self.token, "token")


@dataclass(frozen=True)
class EnvironmentTokenProvider:
    """Token provider that reads a gateway token from an environment variable."""

    env_var: str = DEFAULT_GATEWAY_TOKEN_ENV_VAR

    def get_token(self) -> str:
        env_var = _require_text(self.env_var, "env_var")
        token = os.environ.get(env_var)
        if token is None:
            raise ToolGatewayValidationError(f"{env_var} environment variable is required")
        return _require_text(token, env_var)


@dataclass(frozen=True)
class ToolCallResult:
    """Typed response returned by a successful gateway invocation."""

    request_id: str
    correlation_id: str
    tool_name: str
    result: Any | None = None
    reason_code: str | None = None
    decision: dict[str, Any] | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolDefinition:
    """SDK view of a Tool Gateway contract."""

    id: str
    name: str
    display_name: str
    description: str
    owner_team: str
    status: str
    required_scope: str
    input_schema_json: dict[str, Any] | None = None
    output_schema_json: dict[str, Any] | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GatewayCompatibility:
    """Result returned by SDK-to-gateway contract probing."""

    compatible: bool
    sdk_version: str
    expected_gateway_contract_version: str
    gateway_contract_version: str | None
    min_sdk_version: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolGatewayClientConfig:
    """Reusable client configuration for sync and async SDK clients."""

    timeout_seconds: float = 5.0
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    max_cache_entries: int = DEFAULT_MAX_CACHE_ENTRIES
    cache_tools: bool = False
    cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS
    allow_insecure_http: bool = False
    user_agent: str | None = None
    discovery_max_retries: int = 2
    discovery_retry_backoff_seconds: float = 0.2
    discovery_retry_max_sleep_seconds: float = DEFAULT_DISCOVERY_RETRY_MAX_SLEEP_SECONDS
    discovery_retry_jitter_ratio: float = DEFAULT_DISCOVERY_RETRY_JITTER_RATIO
    invocation_max_retries: int = 2
    invocation_retry_backoff_seconds: float = 0.2
    invocation_retry_max_sleep_seconds: float = DEFAULT_TOOL_CALL_RETRY_MAX_SLEEP_SECONDS
    invocation_retry_jitter_ratio: float = DEFAULT_TOOL_CALL_RETRY_JITTER_RATIO
    allow_buffered_custom_http_client: bool = False
    raise_event_hook_errors: bool = False


class ToolGatewayError(RuntimeError):
    """Base SDK error for gateway, upstream, and transport failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        retry_after_seconds: float | None = None,
        response_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        self.correlation_id = correlation_id
        self.retry_after_seconds = retry_after_seconds
        self.response_body = _sanitize_error_body(response_body or {})


class ToolDeniedError(ToolGatewayError):
    """Raised when gateway policy denies a tool call."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str | None = None,
        status_code: int | None = 403,
        request_id: str | None = None,
        correlation_id: str | None = None,
        response_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            code=reason_code,
            request_id=request_id,
            correlation_id=correlation_id,
            response_body=response_body,
        )
        self.reason_code = reason_code


class ToolAuthenticationError(ToolGatewayError):
    """Raised when gateway authentication fails before policy evaluation."""


class ToolGatewayValidationError(ValueError):
    """Raised when SDK configuration or caller input is invalid."""


@dataclass(frozen=True)
class _AuthContext:
    headers: dict[str, str]
    cache_key: str


@dataclass(frozen=True)
class _ClientConfig:
    base_url: str
    timeout_seconds: float
    max_payload_bytes: int
    max_response_bytes: int
    max_cache_entries: int
    cache_tools: bool
    cache_ttl_seconds: float
    allow_insecure_http: bool
    user_agent: str
    discovery_max_retries: int
    discovery_retry_backoff_seconds: float
    discovery_retry_max_sleep_seconds: float
    discovery_retry_jitter_ratio: float
    invocation_max_retries: int
    invocation_retry_backoff_seconds: float
    invocation_retry_max_sleep_seconds: float
    invocation_retry_jitter_ratio: float
    allow_buffered_custom_http_client: bool


class OphanixToolGatewayClient:
    """Small synchronous SDK client for external Python agents."""

    @classmethod
    def from_config(
        cls,
        *,
        base_url: str,
        token_provider: TokenProvider,
        config: ToolGatewayClientConfig,
        http_client: httpx.Client | None = None,
        event_hook: TelemetryEventHook | None = None,
    ) -> "OphanixToolGatewayClient":
        """Construct a sync client from a reusable configuration object."""

        config = _require_client_config(config)
        return cls(
            base_url=base_url,
            token_provider=token_provider,
            timeout_seconds=config.timeout_seconds,
            max_payload_bytes=config.max_payload_bytes,
            max_response_bytes=config.max_response_bytes,
            max_cache_entries=config.max_cache_entries,
            http_client=http_client,
            cache_tools=config.cache_tools,
            cache_ttl_seconds=config.cache_ttl_seconds,
            event_hook=event_hook,
            allow_insecure_http=config.allow_insecure_http,
            user_agent=config.user_agent,
            discovery_max_retries=config.discovery_max_retries,
            discovery_retry_backoff_seconds=config.discovery_retry_backoff_seconds,
            discovery_retry_max_sleep_seconds=config.discovery_retry_max_sleep_seconds,
            discovery_retry_jitter_ratio=config.discovery_retry_jitter_ratio,
            invocation_max_retries=config.invocation_max_retries,
            invocation_retry_backoff_seconds=config.invocation_retry_backoff_seconds,
            invocation_retry_max_sleep_seconds=config.invocation_retry_max_sleep_seconds,
            invocation_retry_jitter_ratio=config.invocation_retry_jitter_ratio,
            allow_buffered_custom_http_client=config.allow_buffered_custom_http_client,
            raise_event_hook_errors=config.raise_event_hook_errors,
        )

    def __init__(
        self,
        *,
        base_url: str,
        token_provider: TokenProvider,
        timeout_seconds: float = 5.0,
        max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_cache_entries: int = DEFAULT_MAX_CACHE_ENTRIES,
        http_client: httpx.Client | None = None,
        cache_tools: bool = False,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        event_hook: TelemetryEventHook | None = None,
        allow_insecure_http: bool = False,
        user_agent: str | None = None,
        discovery_max_retries: int = 2,
        discovery_retry_backoff_seconds: float = 0.2,
        discovery_retry_max_sleep_seconds: float = DEFAULT_DISCOVERY_RETRY_MAX_SLEEP_SECONDS,
        discovery_retry_jitter_ratio: float = DEFAULT_DISCOVERY_RETRY_JITTER_RATIO,
        invocation_max_retries: int = 2,
        invocation_retry_backoff_seconds: float = 0.2,
        invocation_retry_max_sleep_seconds: float = DEFAULT_TOOL_CALL_RETRY_MAX_SLEEP_SECONDS,
        invocation_retry_jitter_ratio: float = DEFAULT_TOOL_CALL_RETRY_JITTER_RATIO,
        allow_buffered_custom_http_client: bool = False,
        raise_event_hook_errors: bool = False,
    ) -> None:
        if token_provider is None:
            raise ToolGatewayValidationError("token_provider is required")
        if not callable(getattr(token_provider, "get_token", None)):
            raise ToolGatewayValidationError("token_provider must provide get_token()")
        config = _client_config(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_payload_bytes=max_payload_bytes,
            max_response_bytes=max_response_bytes,
            max_cache_entries=max_cache_entries,
            cache_tools=cache_tools,
            cache_ttl_seconds=cache_ttl_seconds,
            allow_insecure_http=allow_insecure_http,
            user_agent=user_agent,
            discovery_max_retries=discovery_max_retries,
            discovery_retry_backoff_seconds=discovery_retry_backoff_seconds,
            discovery_retry_max_sleep_seconds=discovery_retry_max_sleep_seconds,
            discovery_retry_jitter_ratio=discovery_retry_jitter_ratio,
            invocation_max_retries=invocation_max_retries,
            invocation_retry_backoff_seconds=invocation_retry_backoff_seconds,
            invocation_retry_max_sleep_seconds=invocation_retry_max_sleep_seconds,
            invocation_retry_jitter_ratio=invocation_retry_jitter_ratio,
            allow_buffered_custom_http_client=allow_buffered_custom_http_client,
        )
        self.token_provider = token_provider
        self.base_url = config.base_url
        self.timeout_seconds: float = config.timeout_seconds
        self.max_payload_bytes: int = config.max_payload_bytes
        self.max_response_bytes: int = config.max_response_bytes
        self.max_cache_entries: int = config.max_cache_entries
        self.cache_tools: bool = config.cache_tools
        self.cache_ttl_seconds: float = config.cache_ttl_seconds
        self.allow_insecure_http: bool = config.allow_insecure_http
        self.user_agent: str = config.user_agent
        self.discovery_max_retries: int = config.discovery_max_retries
        self.discovery_retry_backoff_seconds: float = config.discovery_retry_backoff_seconds
        self.discovery_retry_max_sleep_seconds: float = config.discovery_retry_max_sleep_seconds
        self.discovery_retry_jitter_ratio: float = config.discovery_retry_jitter_ratio
        self.invocation_max_retries: int = config.invocation_max_retries
        self.invocation_retry_backoff_seconds: float = config.invocation_retry_backoff_seconds
        self.invocation_retry_max_sleep_seconds: float = config.invocation_retry_max_sleep_seconds
        self.invocation_retry_jitter_ratio: float = config.invocation_retry_jitter_ratio
        self.allow_buffered_custom_http_client: bool = config.allow_buffered_custom_http_client
        self.event_hook = _optional_event_hook(event_hook)
        self.raise_event_hook_errors = _require_bool(raise_event_hook_errors, "raise_event_hook_errors")
        self._sleep: Callable[[float], None] = time.sleep
        self._random: Callable[[], float] = random.random
        self._cache_lock = threading.RLock()
        self._tool_cache: dict[_ToolCacheKey, _ToolCacheValue] | None = (
            {} if self.cache_tools else None
        )
        self._list_cache: dict[_ListCacheKey, _ListCacheValue] | None = (
            {} if self.cache_tools else None
        )
        self._owns_http_client = http_client is None
        self._closed = False
        _validate_sync_http_client(
            http_client,
            allow_buffered_custom_http_client=config.allow_buffered_custom_http_client,
        )
        self._http_client = http_client or httpx.Client(timeout=self.timeout_seconds)

    def close(self) -> None:
        """Close the underlying HTTP client if this SDK instance created it."""

        if self._owns_http_client:
            self._http_client.close()
        self._closed = True

    def call_tool(
        self,
        tool_name: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ToolCallResult:
        """Invoke one registered gateway tool with bearer authentication."""

        self._ensure_open()
        started_at = time.perf_counter()
        normalized_tool_name = _require_text(tool_name, "tool_name")
        _require_json_object(payload, "payload", max_bytes=self.max_payload_bytes)
        body: dict[str, Any] = {"payload": payload}
        auth_context = self._auth_context()
        headers = auth_context.headers
        normalized_correlation_id = _optional_header_text(correlation_id, "correlation_id")
        if normalized_correlation_id is not None:
            body["correlation_id"] = normalized_correlation_id
            headers["X-Correlation-ID"] = normalized_correlation_id
        normalized_idempotency_key = _optional_idempotency_key(idempotency_key)
        if normalized_idempotency_key is not None:
            headers["Idempotency-Key"] = normalized_idempotency_key
        self._emit_event(
            {
                "event": "tool_call.start",
                "tool_name": normalized_tool_name,
                "correlation_id": normalized_correlation_id,
                "idempotent": normalized_idempotency_key is not None,
            }
        )
        attempts = 0
        max_retries = self.invocation_max_retries if normalized_idempotency_key is not None else 0
        while True:
            try:
                response = _send_limited_sync_request(
                    self._http_client,
                    "POST",
                    (
                        f"{self.base_url}{GATEWAY_TOOL_INVOKE_PATH_PREFIX}/"
                        f"{quote(normalized_tool_name, safe='')}{GATEWAY_TOOL_INVOKE_PATH_SUFFIX}"
                    ),
                    max_response_bytes=self.max_response_bytes,
                    json=body,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            except httpx.TransportError as exc:
                if attempts < max_retries:
                    self._sleep_before_tool_call_retry(
                        attempts,
                        tool_name=normalized_tool_name,
                        response=None,
                        response_body=None,
                    )
                    attempts += 1
                    continue
                self._emit_event(
                    {
                        "event": "tool_call.error",
                        "tool_name": normalized_tool_name,
                        "code": "transport_error",
                        "elapsed_ms": _elapsed_ms(started_at),
                    }
                )
                raise ToolGatewayError("Tool Gateway transport error.", code="transport_error") from exc
            except httpx.HTTPError as exc:
                self._emit_event(
                    {
                        "event": "tool_call.error",
                        "tool_name": normalized_tool_name,
                        "code": "transport_error",
                        "elapsed_ms": _elapsed_ms(started_at),
                    }
                )
                raise ToolGatewayError("Tool Gateway transport error.", code="transport_error") from exc
            response_body = _response_json(response, max_response_bytes=self.max_response_bytes)
            if _should_retry_tool_call_response(
                response,
                response_body,
                attempts=attempts,
                max_retries=max_retries,
            ):
                self._sleep_before_tool_call_retry(
                    attempts,
                    tool_name=normalized_tool_name,
                    response=response,
                    response_body=response_body,
                )
                attempts += 1
                continue
            break
        if response.status_code == 403:
            self._emit_event(
                {
                    "event": "tool_call.denied",
                    "tool_name": normalized_tool_name,
                    "status_code": response.status_code,
                    "elapsed_ms": _elapsed_ms(started_at),
                }
            )
            _raise_denied(response_body, response.status_code)
        if response.status_code >= 400:
            self._emit_event(
                {
                    "event": "tool_call.error",
                    "tool_name": normalized_tool_name,
                    "status_code": response.status_code,
                    "elapsed_ms": _elapsed_ms(started_at),
                }
            )
            _raise_gateway_error(
                response_body,
                response.status_code,
                retry_after_seconds=_retry_after_seconds(response),
            )
        result = _tool_call_result(response_body)
        self._emit_event(
            {
                "event": "tool_call.success",
                "tool_name": result.tool_name,
                "request_id": result.request_id,
                "correlation_id": result.correlation_id,
                "reason_code": result.reason_code,
                "elapsed_ms": _elapsed_ms(started_at),
            }
        )
        return result

    def list_tools(
        self,
        *,
        status: Literal["active"] | None = None,
        owner_team: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ToolDefinition]:
        """List Tool Gateway contracts visible to the configured caller."""

        self._ensure_open()
        auth_context = self._auth_context()
        if status is not None:
            warnings.warn(
                "list_tools(status=...) is deprecated; gateway discovery returns active tools only.",
                DeprecationWarning,
                stacklevel=2,
            )
        params = _tool_list_params(status, owner_team, limit, offset)
        return self._list_tools_with_auth(params, auth_context)

    def list_all_tools(
        self,
        *,
        owner_team: str | None = None,
        page_size: int = 200,
        max_total: int | None = None,
    ) -> list[ToolDefinition]:
        """List every callable tool by following gateway discovery pagination."""

        page_size = _require_integer(page_size, "page_size")
        if page_size <= 0:
            raise ToolGatewayValidationError("page_size must be greater than zero")
        if page_size > 200:
            raise ToolGatewayValidationError("page_size must be less than or equal to 200")
        max_total = _optional_positive_integer(max_total, "max_total")
        self._ensure_open()
        auth_context = self._auth_context()
        tools: list[ToolDefinition] = []
        seen: set[str] = set()
        offset = 0
        while True:
            params = _tool_list_params(None, owner_team, page_size, offset)
            page = self._list_tools_with_auth(params, auth_context)
            new_tools: list[ToolDefinition] = []
            for tool in page:
                dedupe_key = tool.id or tool.name
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                new_tools.append(tool)
            if max_total is not None and len(tools) + len(new_tools) > max_total:
                raise ToolGatewayError(
                    "Tool discovery exceeded max_total.",
                    code="tool_discovery_too_large",
                )
            tools.extend(new_tools)
            if len(page) < page_size:
                return tools
            offset += page_size

    def clear_tool_cache(self) -> None:
        """Clear cached discovery results when permissions or tool contracts change."""

        with self._cache_lock:
            if self._tool_cache is not None:
                self._tool_cache.clear()
            if self._list_cache is not None:
                self._list_cache.clear()

    def check_compatibility(self) -> GatewayCompatibility:
        """Probe the gateway contract version exposed by the authenticated endpoint."""

        self._ensure_open()
        auth_context = self._auth_context()
        try:
            response = _send_limited_sync_request(
                self._http_client,
                "GET",
                f"{self.base_url}{GATEWAY_CAPABILITIES_PATH}",
                max_response_bytes=self.max_response_bytes,
                headers=auth_context.headers,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise ToolGatewayError("Tool Gateway transport error.", code="transport_error") from exc
        response_body = _response_json(response, max_response_bytes=self.max_response_bytes)
        if response.status_code >= 400:
            _raise_gateway_error(
                response_body,
                response.status_code,
                retry_after_seconds=_retry_after_seconds(response),
            )
        return _gateway_compatibility(response_body)

    def get_tool(self, tool_name: str) -> ToolDefinition:
        """Return one tool definition by name or id from the list contract."""

        self._ensure_open()
        normalized_tool_name = _require_text(tool_name, "tool_name")
        auth_context = self._auth_context()
        cache_key = _tool_cache_key(auth_context.cache_key, normalized_tool_name)
        cached = self._cached_tool(cache_key)
        if cached is not None:
            return cached
        page_size = 200
        offset = 0
        while True:
            params = _tool_list_params(None, None, page_size, offset)
            tools = self._list_tools_with_auth(params, auth_context)
            for tool in tools:
                if tool.name == normalized_tool_name or tool.id == normalized_tool_name:
                    return tool
            if len(tools) < page_size:
                break
            offset += page_size
        raise ToolGatewayError(
            f"Tool is not visible through gateway discovery: {_safe_lookup_text(normalized_tool_name)}",
            status_code=404,
            code="tool_not_visible",
        )

    def __enter__(self) -> OphanixToolGatewayClient:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def _auth_context(self) -> _AuthContext:
        token_value = self.token_provider.get_token()
        if inspect.isawaitable(token_value):
            _close_awaitable(token_value)
            raise ToolGatewayValidationError(
                "sync token_provider.get_token() must return a string; "
                "use AsyncOphanixToolGatewayClient for awaitable tokens"
            )
        token = _require_gateway_token(token_value)
        token_fingerprint = _token_cache_fingerprint(token)
        return _AuthContext(
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": self.user_agent,
            },
            cache_key=token_fingerprint,
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise ToolGatewayError("Tool Gateway client is closed.", code="client_closed")

    def _list_tools_with_auth(
        self,
        params: list[tuple[str, str]],
        auth_context: _AuthContext,
    ) -> list[ToolDefinition]:
        cache_key = _list_cache_key(auth_context.cache_key, params)
        cached = self._cached_list(cache_key)
        if cached is not None:
            return cached
        response = self._get_discovery_response(params, headers=auth_context.headers)
        response_data = _response_data(response, max_response_bytes=self.max_response_bytes)
        if response.status_code >= 400:
            _raise_gateway_error(
                _mapping_response(response_data),
                response.status_code,
                retry_after_seconds=_retry_after_seconds(response),
            )
        if not isinstance(response_data, list):
            raise ToolGatewayError(
                "Tool Gateway returned an invalid tools response.",
                code="invalid_response",
            )
        tools = [
            _tool_definition(_require_mapping(item, "tool definition"))
            for item in response_data
        ]
        self._remember_tools(tools, credential_cache_key=auth_context.cache_key)
        if self._list_cache is not None:
            with self._cache_lock:
                self._list_cache[cache_key] = (
                    self._cache_deadline(),
                    [_clone_tool_definition(tool) for tool in tools],
                )
                _trim_cache(self._list_cache, self.max_cache_entries)
        return tools

    def _get_discovery_response(
        self,
        params: list[tuple[str, str]],
        *,
        headers: dict[str, str],
    ) -> httpx.Response:
        attempts = 0
        while True:
            try:
                response = _send_limited_sync_request(
                    self._http_client,
                    "GET",
                    f"{self.base_url}{GATEWAY_TOOL_DISCOVERY_PATH}",
                    max_response_bytes=self.max_response_bytes,
                    params=dict(params),
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            except httpx.TransportError as exc:
                if attempts < self.discovery_max_retries:
                    self._sleep_before_discovery_retry(attempts, response=None)
                    attempts += 1
                    continue
                raise ToolGatewayError(
                    "Tool Gateway transport error.",
                    code="transport_error",
                ) from exc
            except httpx.HTTPError as exc:
                raise ToolGatewayError(
                    "Tool Gateway transport error.",
                    code="transport_error",
                ) from exc
            if (
                response.status_code in RETRYABLE_DISCOVERY_STATUS_CODES
                and attempts < self.discovery_max_retries
            ):
                self._sleep_before_discovery_retry(attempts, response=response)
                attempts += 1
                continue
            return response

    def _sleep_before_discovery_retry(
        self,
        attempt: int,
        *,
        response: httpx.Response | None,
    ) -> None:
        delay = self._discovery_retry_delay(attempt, response=response)
        self._emit_event(
            {
                "event": "tool_discovery.retry",
                "attempt": attempt + 1,
                "delay_seconds": delay,
                "status_code": response.status_code if response is not None else None,
            }
        )
        if delay <= 0:
            return
        self._sleep(delay)

    def _sleep_before_tool_call_retry(
        self,
        attempt: int,
        *,
        tool_name: str,
        response: httpx.Response | None,
        response_body: dict[str, Any] | None,
    ) -> None:
        delay = self._tool_call_retry_delay(attempt, response=response)
        self._emit_event(
            {
                "event": "tool_call.retry",
                "tool_name": tool_name,
                "attempt": attempt + 1,
                "delay_seconds": delay,
                "status_code": response.status_code if response is not None else None,
                "code": _gateway_error_code(response_body or {}),
            }
        )
        if delay <= 0:
            return
        self._sleep(delay)

    def _tool_call_retry_delay(
        self,
        attempt: int,
        *,
        response: httpx.Response | None,
    ) -> float:
        retry_after = _retry_after_seconds(response)
        if retry_after is not None:
            return min(retry_after, self.invocation_retry_max_sleep_seconds)
        delay = float(
            min(
                self.invocation_retry_backoff_seconds * (2**attempt),
                self.invocation_retry_max_sleep_seconds,
            )
        )
        if delay <= 0 or self.invocation_retry_jitter_ratio <= 0:
            return delay
        jitter = float(1 + ((self._random() * 2 - 1) * self.invocation_retry_jitter_ratio))
        return float(min(delay * jitter, self.invocation_retry_max_sleep_seconds))

    def _discovery_retry_delay(
        self,
        attempt: int,
        *,
        response: httpx.Response | None,
    ) -> float:
        retry_after = _retry_after_seconds(response)
        if retry_after is not None:
            return min(retry_after, self.discovery_retry_max_sleep_seconds)
        delay = float(
            min(
                self.discovery_retry_backoff_seconds * (2**attempt),
                self.discovery_retry_max_sleep_seconds,
            )
        )
        if delay <= 0 or self.discovery_retry_jitter_ratio <= 0:
            return delay
        jitter = float(1 + ((self._random() * 2 - 1) * self.discovery_retry_jitter_ratio))
        return float(min(delay * jitter, self.discovery_retry_max_sleep_seconds))

    def _remember_tools(self, tools: list[ToolDefinition], *, credential_cache_key: str) -> None:
        if self._tool_cache is None:
            return
        deadline = self._cache_deadline()
        with self._cache_lock:
            for tool in tools:
                self._tool_cache[_tool_cache_key(credential_cache_key, tool.name)] = (
                    deadline,
                    _clone_tool_definition(tool),
                )
                self._tool_cache[_tool_cache_key(credential_cache_key, tool.id)] = (
                    deadline,
                    _clone_tool_definition(tool),
                )
            _trim_cache(self._tool_cache, self.max_cache_entries)

    def _cached_tool(self, cache_key: _ToolCacheKey) -> ToolDefinition | None:
        if self._tool_cache is None:
            return None
        with self._cache_lock:
            cached = self._tool_cache.get(cache_key)
            if cached is None:
                return None
            expires_at, tool = cached
            if expires_at <= time.monotonic():
                self._tool_cache.pop(cache_key, None)
                return None
            return _clone_tool_definition(tool)

    def _cached_list(self, cache_key: _ListCacheKey) -> list[ToolDefinition] | None:
        if self._list_cache is None:
            return None
        with self._cache_lock:
            cached = self._list_cache.get(cache_key)
            if cached is None:
                return None
            expires_at, tools = cached
            if expires_at <= time.monotonic():
                self._list_cache.pop(cache_key, None)
                return None
            return [_clone_tool_definition(tool) for tool in tools]

    def _cache_deadline(self) -> float:
        return time.monotonic() + self.cache_ttl_seconds

    def _emit_event(self, event: dict[str, Any]) -> None:
        if self.event_hook is None:
            return
        try:
            self.event_hook(MappingProxyType(dict(event)))
        except Exception:
            if self.raise_event_hook_errors:
                raise
            LOGGER.debug("Tool Gateway SDK event hook failed.", exc_info=True)


class AsyncOphanixToolGatewayClient:
    """Async SDK client for external Python agents running on event loops."""

    @classmethod
    def from_config(
        cls,
        *,
        base_url: str,
        token_provider: TokenProvider | AsyncTokenProvider,
        config: ToolGatewayClientConfig,
        http_client: httpx.AsyncClient | None = None,
        event_hook: TelemetryEventHook | None = None,
    ) -> "AsyncOphanixToolGatewayClient":
        """Construct an async client from a reusable configuration object."""

        config = _require_client_config(config)
        return cls(
            base_url=base_url,
            token_provider=token_provider,
            timeout_seconds=config.timeout_seconds,
            max_payload_bytes=config.max_payload_bytes,
            max_response_bytes=config.max_response_bytes,
            max_cache_entries=config.max_cache_entries,
            http_client=http_client,
            cache_tools=config.cache_tools,
            cache_ttl_seconds=config.cache_ttl_seconds,
            event_hook=event_hook,
            allow_insecure_http=config.allow_insecure_http,
            user_agent=config.user_agent,
            discovery_max_retries=config.discovery_max_retries,
            discovery_retry_backoff_seconds=config.discovery_retry_backoff_seconds,
            discovery_retry_max_sleep_seconds=config.discovery_retry_max_sleep_seconds,
            discovery_retry_jitter_ratio=config.discovery_retry_jitter_ratio,
            invocation_max_retries=config.invocation_max_retries,
            invocation_retry_backoff_seconds=config.invocation_retry_backoff_seconds,
            invocation_retry_max_sleep_seconds=config.invocation_retry_max_sleep_seconds,
            invocation_retry_jitter_ratio=config.invocation_retry_jitter_ratio,
            allow_buffered_custom_http_client=config.allow_buffered_custom_http_client,
            raise_event_hook_errors=config.raise_event_hook_errors,
        )

    def __init__(
        self,
        *,
        base_url: str,
        token_provider: TokenProvider | AsyncTokenProvider,
        timeout_seconds: float = 5.0,
        max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_cache_entries: int = DEFAULT_MAX_CACHE_ENTRIES,
        http_client: httpx.AsyncClient | None = None,
        cache_tools: bool = False,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        event_hook: TelemetryEventHook | None = None,
        allow_insecure_http: bool = False,
        user_agent: str | None = None,
        discovery_max_retries: int = 2,
        discovery_retry_backoff_seconds: float = 0.2,
        discovery_retry_max_sleep_seconds: float = DEFAULT_DISCOVERY_RETRY_MAX_SLEEP_SECONDS,
        discovery_retry_jitter_ratio: float = DEFAULT_DISCOVERY_RETRY_JITTER_RATIO,
        invocation_max_retries: int = 2,
        invocation_retry_backoff_seconds: float = 0.2,
        invocation_retry_max_sleep_seconds: float = DEFAULT_TOOL_CALL_RETRY_MAX_SLEEP_SECONDS,
        invocation_retry_jitter_ratio: float = DEFAULT_TOOL_CALL_RETRY_JITTER_RATIO,
        allow_buffered_custom_http_client: bool = False,
        raise_event_hook_errors: bool = False,
    ) -> None:
        if token_provider is None:
            raise ToolGatewayValidationError("token_provider is required")
        if not callable(getattr(token_provider, "get_token", None)):
            raise ToolGatewayValidationError("token_provider must provide get_token()")
        config = _client_config(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_payload_bytes=max_payload_bytes,
            max_response_bytes=max_response_bytes,
            max_cache_entries=max_cache_entries,
            cache_tools=cache_tools,
            cache_ttl_seconds=cache_ttl_seconds,
            allow_insecure_http=allow_insecure_http,
            user_agent=user_agent,
            discovery_max_retries=discovery_max_retries,
            discovery_retry_backoff_seconds=discovery_retry_backoff_seconds,
            discovery_retry_max_sleep_seconds=discovery_retry_max_sleep_seconds,
            discovery_retry_jitter_ratio=discovery_retry_jitter_ratio,
            invocation_max_retries=invocation_max_retries,
            invocation_retry_backoff_seconds=invocation_retry_backoff_seconds,
            invocation_retry_max_sleep_seconds=invocation_retry_max_sleep_seconds,
            invocation_retry_jitter_ratio=invocation_retry_jitter_ratio,
            allow_buffered_custom_http_client=allow_buffered_custom_http_client,
        )
        self.token_provider = token_provider
        self.base_url = config.base_url
        self.timeout_seconds: float = config.timeout_seconds
        self.max_payload_bytes: int = config.max_payload_bytes
        self.max_response_bytes: int = config.max_response_bytes
        self.max_cache_entries: int = config.max_cache_entries
        self.cache_tools: bool = config.cache_tools
        self.cache_ttl_seconds: float = config.cache_ttl_seconds
        self.allow_insecure_http: bool = config.allow_insecure_http
        self.user_agent: str = config.user_agent
        self.discovery_max_retries: int = config.discovery_max_retries
        self.discovery_retry_backoff_seconds: float = config.discovery_retry_backoff_seconds
        self.discovery_retry_max_sleep_seconds: float = config.discovery_retry_max_sleep_seconds
        self.discovery_retry_jitter_ratio: float = config.discovery_retry_jitter_ratio
        self.invocation_max_retries: int = config.invocation_max_retries
        self.invocation_retry_backoff_seconds: float = config.invocation_retry_backoff_seconds
        self.invocation_retry_max_sleep_seconds: float = config.invocation_retry_max_sleep_seconds
        self.invocation_retry_jitter_ratio: float = config.invocation_retry_jitter_ratio
        self.allow_buffered_custom_http_client: bool = config.allow_buffered_custom_http_client
        self.event_hook = _optional_event_hook(event_hook)
        self.raise_event_hook_errors = _require_bool(raise_event_hook_errors, "raise_event_hook_errors")
        self._sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
        self._random: Callable[[], float] = random.random
        self._cache_lock = threading.RLock()
        self._tool_cache: dict[_ToolCacheKey, _ToolCacheValue] | None = (
            {} if self.cache_tools else None
        )
        self._list_cache: dict[_ListCacheKey, _ListCacheValue] | None = (
            {} if self.cache_tools else None
        )
        self._owns_http_client = http_client is None
        self._closed = False
        _validate_async_http_client(
            http_client,
            allow_buffered_custom_http_client=config.allow_buffered_custom_http_client,
        )
        self._http_client = http_client or httpx.AsyncClient(timeout=self.timeout_seconds)

    async def close(self) -> None:
        """Close the underlying HTTP client if this SDK instance created it."""

        if self._owns_http_client:
            await self._http_client.aclose()
        self._closed = True

    async def call_tool(
        self,
        tool_name: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ToolCallResult:
        """Invoke one registered gateway tool with bearer authentication."""

        self._ensure_open()
        started_at = time.perf_counter()
        normalized_tool_name = _require_text(tool_name, "tool_name")
        _require_json_object(payload, "payload", max_bytes=self.max_payload_bytes)
        body: dict[str, Any] = {"payload": payload}
        auth_context = await self._auth_context()
        headers = auth_context.headers
        normalized_correlation_id = _optional_header_text(correlation_id, "correlation_id")
        if normalized_correlation_id is not None:
            body["correlation_id"] = normalized_correlation_id
            headers["X-Correlation-ID"] = normalized_correlation_id
        normalized_idempotency_key = _optional_idempotency_key(idempotency_key)
        if normalized_idempotency_key is not None:
            headers["Idempotency-Key"] = normalized_idempotency_key
        self._emit_event(
            {
                "event": "tool_call.start",
                "tool_name": normalized_tool_name,
                "correlation_id": normalized_correlation_id,
                "idempotent": normalized_idempotency_key is not None,
            }
        )
        attempts = 0
        max_retries = self.invocation_max_retries if normalized_idempotency_key is not None else 0
        while True:
            try:
                response = await _send_limited_async_request(
                    self._http_client,
                    "POST",
                    (
                        f"{self.base_url}{GATEWAY_TOOL_INVOKE_PATH_PREFIX}/"
                        f"{quote(normalized_tool_name, safe='')}{GATEWAY_TOOL_INVOKE_PATH_SUFFIX}"
                    ),
                    max_response_bytes=self.max_response_bytes,
                    json=body,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            except httpx.TransportError as exc:
                if attempts < max_retries:
                    await self._sleep_before_tool_call_retry(
                        attempts,
                        tool_name=normalized_tool_name,
                        response=None,
                        response_body=None,
                    )
                    attempts += 1
                    continue
                self._emit_event(
                    {
                        "event": "tool_call.error",
                        "tool_name": normalized_tool_name,
                        "code": "transport_error",
                        "elapsed_ms": _elapsed_ms(started_at),
                    }
                )
                raise ToolGatewayError("Tool Gateway transport error.", code="transport_error") from exc
            except httpx.HTTPError as exc:
                self._emit_event(
                    {
                        "event": "tool_call.error",
                        "tool_name": normalized_tool_name,
                        "code": "transport_error",
                        "elapsed_ms": _elapsed_ms(started_at),
                    }
                )
                raise ToolGatewayError("Tool Gateway transport error.", code="transport_error") from exc
            response_body = _response_json(response, max_response_bytes=self.max_response_bytes)
            if _should_retry_tool_call_response(
                response,
                response_body,
                attempts=attempts,
                max_retries=max_retries,
            ):
                await self._sleep_before_tool_call_retry(
                    attempts,
                    tool_name=normalized_tool_name,
                    response=response,
                    response_body=response_body,
                )
                attempts += 1
                continue
            break
        if response.status_code == 403:
            self._emit_event(
                {
                    "event": "tool_call.denied",
                    "tool_name": normalized_tool_name,
                    "status_code": response.status_code,
                    "elapsed_ms": _elapsed_ms(started_at),
                }
            )
            _raise_denied(response_body, response.status_code)
        if response.status_code >= 400:
            self._emit_event(
                {
                    "event": "tool_call.error",
                    "tool_name": normalized_tool_name,
                    "status_code": response.status_code,
                    "elapsed_ms": _elapsed_ms(started_at),
                }
            )
            _raise_gateway_error(
                response_body,
                response.status_code,
                retry_after_seconds=_retry_after_seconds(response),
            )
        result = _tool_call_result(response_body)
        self._emit_event(
            {
                "event": "tool_call.success",
                "tool_name": result.tool_name,
                "request_id": result.request_id,
                "correlation_id": result.correlation_id,
                "reason_code": result.reason_code,
                "elapsed_ms": _elapsed_ms(started_at),
            }
        )
        return result

    async def list_tools(
        self,
        *,
        status: Literal["active"] | None = None,
        owner_team: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ToolDefinition]:
        """List Tool Gateway contracts visible to the configured caller."""

        self._ensure_open()
        auth_context = await self._auth_context()
        if status is not None:
            warnings.warn(
                "list_tools(status=...) is deprecated; gateway discovery returns active tools only.",
                DeprecationWarning,
                stacklevel=2,
            )
        params = _tool_list_params(status, owner_team, limit, offset)
        return await self._list_tools_with_auth(params, auth_context)

    async def list_all_tools(
        self,
        *,
        owner_team: str | None = None,
        page_size: int = 200,
        max_total: int | None = None,
    ) -> list[ToolDefinition]:
        """List every callable tool by following gateway discovery pagination."""

        page_size = _require_integer(page_size, "page_size")
        if page_size <= 0:
            raise ToolGatewayValidationError("page_size must be greater than zero")
        if page_size > 200:
            raise ToolGatewayValidationError("page_size must be less than or equal to 200")
        max_total = _optional_positive_integer(max_total, "max_total")
        self._ensure_open()
        auth_context = await self._auth_context()
        tools: list[ToolDefinition] = []
        seen: set[str] = set()
        offset = 0
        while True:
            params = _tool_list_params(None, owner_team, page_size, offset)
            page = await self._list_tools_with_auth(params, auth_context)
            new_tools: list[ToolDefinition] = []
            for tool in page:
                dedupe_key = tool.id or tool.name
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                new_tools.append(tool)
            if max_total is not None and len(tools) + len(new_tools) > max_total:
                raise ToolGatewayError(
                    "Tool discovery exceeded max_total.",
                    code="tool_discovery_too_large",
                )
            tools.extend(new_tools)
            if len(page) < page_size:
                return tools
            offset += page_size

    def clear_tool_cache(self) -> None:
        """Clear cached discovery results when permissions or tool contracts change."""

        with self._cache_lock:
            if self._tool_cache is not None:
                self._tool_cache.clear()
            if self._list_cache is not None:
                self._list_cache.clear()

    async def check_compatibility(self) -> GatewayCompatibility:
        """Probe the gateway contract version exposed by the authenticated endpoint."""

        self._ensure_open()
        auth_context = await self._auth_context()
        try:
            response = await _send_limited_async_request(
                self._http_client,
                "GET",
                f"{self.base_url}{GATEWAY_CAPABILITIES_PATH}",
                max_response_bytes=self.max_response_bytes,
                headers=auth_context.headers,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise ToolGatewayError("Tool Gateway transport error.", code="transport_error") from exc
        response_body = _response_json(response, max_response_bytes=self.max_response_bytes)
        if response.status_code >= 400:
            _raise_gateway_error(
                response_body,
                response.status_code,
                retry_after_seconds=_retry_after_seconds(response),
            )
        return _gateway_compatibility(response_body)

    async def get_tool(self, tool_name: str) -> ToolDefinition:
        """Return one tool definition by name or id from the list contract."""

        self._ensure_open()
        normalized_tool_name = _require_text(tool_name, "tool_name")
        auth_context = await self._auth_context()
        cache_key = _tool_cache_key(auth_context.cache_key, normalized_tool_name)
        cached = self._cached_tool(cache_key)
        if cached is not None:
            return cached
        page_size = 200
        offset = 0
        while True:
            params = _tool_list_params(None, None, page_size, offset)
            tools = await self._list_tools_with_auth(params, auth_context)
            for tool in tools:
                if tool.name == normalized_tool_name or tool.id == normalized_tool_name:
                    return tool
            if len(tools) < page_size:
                break
            offset += page_size
        raise ToolGatewayError(
            f"Tool is not visible through gateway discovery: {_safe_lookup_text(normalized_tool_name)}",
            status_code=404,
            code="tool_not_visible",
        )

    async def __aenter__(self) -> AsyncOphanixToolGatewayClient:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def _auth_context(self) -> _AuthContext:
        token_value = self.token_provider.get_token()
        if inspect.isawaitable(token_value):
            token_value = await token_value
        token = _require_gateway_token(token_value)
        token_fingerprint = _token_cache_fingerprint(token)
        return _AuthContext(
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": self.user_agent,
            },
            cache_key=token_fingerprint,
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise ToolGatewayError("Tool Gateway client is closed.", code="client_closed")

    async def _list_tools_with_auth(
        self,
        params: list[tuple[str, str]],
        auth_context: _AuthContext,
    ) -> list[ToolDefinition]:
        cache_key = _list_cache_key(auth_context.cache_key, params)
        cached = self._cached_list(cache_key)
        if cached is not None:
            return cached
        response = await self._get_discovery_response(params, headers=auth_context.headers)
        response_data = _response_data(response, max_response_bytes=self.max_response_bytes)
        if response.status_code >= 400:
            _raise_gateway_error(
                _mapping_response(response_data),
                response.status_code,
                retry_after_seconds=_retry_after_seconds(response),
            )
        if not isinstance(response_data, list):
            raise ToolGatewayError(
                "Tool Gateway returned an invalid tools response.",
                code="invalid_response",
            )
        tools = [
            _tool_definition(_require_mapping(item, "tool definition"))
            for item in response_data
        ]
        self._remember_tools(tools, credential_cache_key=auth_context.cache_key)
        if self._list_cache is not None:
            with self._cache_lock:
                self._list_cache[cache_key] = (
                    self._cache_deadline(),
                    [_clone_tool_definition(tool) for tool in tools],
                )
                _trim_cache(self._list_cache, self.max_cache_entries)
        return tools

    async def _get_discovery_response(
        self,
        params: list[tuple[str, str]],
        *,
        headers: dict[str, str],
    ) -> httpx.Response:
        attempts = 0
        while True:
            try:
                response = await _send_limited_async_request(
                    self._http_client,
                    "GET",
                    f"{self.base_url}{GATEWAY_TOOL_DISCOVERY_PATH}",
                    max_response_bytes=self.max_response_bytes,
                    params=dict(params),
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            except httpx.TransportError as exc:
                if attempts < self.discovery_max_retries:
                    await self._sleep_before_discovery_retry(attempts, response=None)
                    attempts += 1
                    continue
                raise ToolGatewayError(
                    "Tool Gateway transport error.",
                    code="transport_error",
                ) from exc
            except httpx.HTTPError as exc:
                raise ToolGatewayError(
                    "Tool Gateway transport error.",
                    code="transport_error",
                ) from exc
            if (
                response.status_code in RETRYABLE_DISCOVERY_STATUS_CODES
                and attempts < self.discovery_max_retries
            ):
                await self._sleep_before_discovery_retry(attempts, response=response)
                attempts += 1
                continue
            return response

    async def _sleep_before_discovery_retry(
        self,
        attempt: int,
        *,
        response: httpx.Response | None,
    ) -> None:
        delay = self._discovery_retry_delay(attempt, response=response)
        self._emit_event(
            {
                "event": "tool_discovery.retry",
                "attempt": attempt + 1,
                "delay_seconds": delay,
                "status_code": response.status_code if response is not None else None,
            }
        )
        if delay <= 0:
            return
        await self._sleep(delay)

    async def _sleep_before_tool_call_retry(
        self,
        attempt: int,
        *,
        tool_name: str,
        response: httpx.Response | None,
        response_body: dict[str, Any] | None,
    ) -> None:
        delay = self._tool_call_retry_delay(attempt, response=response)
        self._emit_event(
            {
                "event": "tool_call.retry",
                "tool_name": tool_name,
                "attempt": attempt + 1,
                "delay_seconds": delay,
                "status_code": response.status_code if response is not None else None,
                "code": _gateway_error_code(response_body or {}),
            }
        )
        if delay <= 0:
            return
        await self._sleep(delay)

    def _tool_call_retry_delay(
        self,
        attempt: int,
        *,
        response: httpx.Response | None,
    ) -> float:
        retry_after = _retry_after_seconds(response)
        if retry_after is not None:
            return min(retry_after, self.invocation_retry_max_sleep_seconds)
        delay = float(
            min(
                self.invocation_retry_backoff_seconds * (2**attempt),
                self.invocation_retry_max_sleep_seconds,
            )
        )
        if delay <= 0 or self.invocation_retry_jitter_ratio <= 0:
            return delay
        jitter = float(1 + ((self._random() * 2 - 1) * self.invocation_retry_jitter_ratio))
        return float(min(delay * jitter, self.invocation_retry_max_sleep_seconds))

    def _discovery_retry_delay(
        self,
        attempt: int,
        *,
        response: httpx.Response | None,
    ) -> float:
        retry_after = _retry_after_seconds(response)
        if retry_after is not None:
            return min(retry_after, self.discovery_retry_max_sleep_seconds)
        delay = float(
            min(
                self.discovery_retry_backoff_seconds * (2**attempt),
                self.discovery_retry_max_sleep_seconds,
            )
        )
        if delay <= 0 or self.discovery_retry_jitter_ratio <= 0:
            return delay
        jitter = float(1 + ((self._random() * 2 - 1) * self.discovery_retry_jitter_ratio))
        return float(min(delay * jitter, self.discovery_retry_max_sleep_seconds))

    def _remember_tools(self, tools: list[ToolDefinition], *, credential_cache_key: str) -> None:
        if self._tool_cache is None:
            return
        deadline = self._cache_deadline()
        with self._cache_lock:
            for tool in tools:
                self._tool_cache[_tool_cache_key(credential_cache_key, tool.name)] = (
                    deadline,
                    _clone_tool_definition(tool),
                )
                self._tool_cache[_tool_cache_key(credential_cache_key, tool.id)] = (
                    deadline,
                    _clone_tool_definition(tool),
                )
            _trim_cache(self._tool_cache, self.max_cache_entries)

    def _cached_tool(self, cache_key: _ToolCacheKey) -> ToolDefinition | None:
        if self._tool_cache is None:
            return None
        with self._cache_lock:
            cached = self._tool_cache.get(cache_key)
            if cached is None:
                return None
            expires_at, tool = cached
            if expires_at <= time.monotonic():
                self._tool_cache.pop(cache_key, None)
                return None
            return _clone_tool_definition(tool)

    def _cached_list(self, cache_key: _ListCacheKey) -> list[ToolDefinition] | None:
        if self._list_cache is None:
            return None
        with self._cache_lock:
            cached = self._list_cache.get(cache_key)
            if cached is None:
                return None
            expires_at, tools = cached
            if expires_at <= time.monotonic():
                self._list_cache.pop(cache_key, None)
                return None
            return [_clone_tool_definition(tool) for tool in tools]

    def _cache_deadline(self) -> float:
        return time.monotonic() + self.cache_ttl_seconds

    def _emit_event(self, event: dict[str, Any]) -> None:
        if self.event_hook is None:
            return
        try:
            self.event_hook(MappingProxyType(dict(event)))
        except Exception:
            if self.raise_event_hook_errors:
                raise
            LOGGER.debug("Tool Gateway SDK event hook failed.", exc_info=True)


def _client_config(
    *,
    base_url: object,
    timeout_seconds: object,
    max_payload_bytes: object,
    max_response_bytes: object,
    max_cache_entries: object,
    cache_tools: object,
    cache_ttl_seconds: object,
    allow_insecure_http: object,
    user_agent: object | None,
    discovery_max_retries: object,
    discovery_retry_backoff_seconds: object,
    discovery_retry_max_sleep_seconds: object,
    discovery_retry_jitter_ratio: object,
    invocation_max_retries: object,
    invocation_retry_backoff_seconds: object,
    invocation_retry_max_sleep_seconds: object,
    invocation_retry_jitter_ratio: object,
    allow_buffered_custom_http_client: object,
) -> _ClientConfig:
    allow_insecure_http = _require_bool(allow_insecure_http, "allow_insecure_http")
    normalized_base_url = _normalize_base_url(
        base_url,
        allow_insecure_http=allow_insecure_http,
    )
    timeout_seconds = _require_finite_number(
        timeout_seconds,
        "timeout_seconds",
        minimum=0,
        include_minimum=False,
    )
    max_payload_bytes = _require_integer(max_payload_bytes, "max_payload_bytes")
    if max_payload_bytes <= 0:
        raise ToolGatewayValidationError("max_payload_bytes must be greater than zero")
    max_response_bytes = _require_integer(max_response_bytes, "max_response_bytes")
    if max_response_bytes <= 0:
        raise ToolGatewayValidationError("max_response_bytes must be greater than zero")
    max_cache_entries = _require_integer(max_cache_entries, "max_cache_entries")
    if max_cache_entries <= 0:
        raise ToolGatewayValidationError("max_cache_entries must be greater than zero")
    cache_ttl_seconds = _require_finite_number(
        cache_ttl_seconds,
        "cache_ttl_seconds",
        minimum=0,
        include_minimum=False,
    )
    discovery_max_retries = _require_integer(discovery_max_retries, "discovery_max_retries")
    if discovery_max_retries < 0:
        raise ToolGatewayValidationError("discovery_max_retries must be greater than or equal to zero")
    discovery_retry_backoff_seconds = _require_finite_number(
        discovery_retry_backoff_seconds,
        "discovery_retry_backoff_seconds",
        minimum=0,
        include_minimum=True,
    )
    discovery_retry_max_sleep_seconds = _require_finite_number(
        discovery_retry_max_sleep_seconds,
        "discovery_retry_max_sleep_seconds",
        minimum=0,
        include_minimum=True,
    )
    discovery_retry_jitter_ratio = _require_finite_number(
        discovery_retry_jitter_ratio,
        "discovery_retry_jitter_ratio",
        minimum=0,
        include_minimum=True,
    )
    if discovery_retry_jitter_ratio > 1:
        raise ToolGatewayValidationError("discovery_retry_jitter_ratio must be less than or equal to 1")
    invocation_max_retries = _require_integer(invocation_max_retries, "invocation_max_retries")
    if invocation_max_retries < 0:
        raise ToolGatewayValidationError("invocation_max_retries must be greater than or equal to zero")
    invocation_retry_backoff_seconds = _require_finite_number(
        invocation_retry_backoff_seconds,
        "invocation_retry_backoff_seconds",
        minimum=0,
        include_minimum=True,
    )
    invocation_retry_max_sleep_seconds = _require_finite_number(
        invocation_retry_max_sleep_seconds,
        "invocation_retry_max_sleep_seconds",
        minimum=0,
        include_minimum=True,
    )
    invocation_retry_jitter_ratio = _require_finite_number(
        invocation_retry_jitter_ratio,
        "invocation_retry_jitter_ratio",
        minimum=0,
        include_minimum=True,
    )
    if invocation_retry_jitter_ratio > 1:
        raise ToolGatewayValidationError("invocation_retry_jitter_ratio must be less than or equal to 1")
    return _ClientConfig(
        base_url=normalized_base_url,
        timeout_seconds=timeout_seconds,
        max_payload_bytes=max_payload_bytes,
        max_response_bytes=max_response_bytes,
        max_cache_entries=max_cache_entries,
        cache_tools=_require_bool(cache_tools, "cache_tools"),
        cache_ttl_seconds=cache_ttl_seconds,
        allow_insecure_http=allow_insecure_http,
        user_agent=_optional_header_text(user_agent, "user_agent") or SDK_USER_AGENT,
        discovery_max_retries=discovery_max_retries,
        discovery_retry_backoff_seconds=discovery_retry_backoff_seconds,
        discovery_retry_max_sleep_seconds=discovery_retry_max_sleep_seconds,
        discovery_retry_jitter_ratio=discovery_retry_jitter_ratio,
        invocation_max_retries=invocation_max_retries,
        invocation_retry_backoff_seconds=invocation_retry_backoff_seconds,
        invocation_retry_max_sleep_seconds=invocation_retry_max_sleep_seconds,
        invocation_retry_jitter_ratio=invocation_retry_jitter_ratio,
        allow_buffered_custom_http_client=_require_bool(
            allow_buffered_custom_http_client,
            "allow_buffered_custom_http_client",
        ),
    )


def _require_client_config(config: object) -> ToolGatewayClientConfig:
    if not isinstance(config, ToolGatewayClientConfig):
        raise ToolGatewayValidationError("config must be a ToolGatewayClientConfig")
    return config


def _normalize_base_url(base_url: object, *, allow_insecure_http: bool = False) -> str:
    normalized = _require_text(base_url, "base_url").rstrip("/")
    if not normalized:
        raise ToolGatewayValidationError("base_url is required")
    if _has_control_character(normalized):
        raise ToolGatewayValidationError("base_url must not contain control characters")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ToolGatewayValidationError("base_url must be an absolute http or https URL")
    if parsed.username is not None or parsed.password is not None:
        raise ToolGatewayValidationError("base_url must not include credentials")
    if parsed.query or parsed.fragment:
        raise ToolGatewayValidationError("base_url must not include a query string or fragment")
    if (
        parsed.scheme == "http"
        and not allow_insecure_http
        and not _is_local_http_host(parsed.hostname)
    ):
        raise ToolGatewayValidationError(
            "base_url must use https unless it targets localhost or allow_insecure_http=True"
        )
    return normalized


def _validate_sync_http_client(
    http_client: object | None,
    *,
    allow_buffered_custom_http_client: bool,
) -> None:
    if http_client is None:
        return
    if isinstance(http_client, httpx.AsyncClient):
        raise ToolGatewayValidationError("http_client must be an httpx.Client-compatible sync client")
    if not allow_buffered_custom_http_client and not callable(getattr(http_client, "stream", None)):
        raise ToolGatewayValidationError(
            "http_client must provide stream(); pass allow_buffered_custom_http_client=True "
            "only if the injected client enforces equivalent response-size limits."
        )
    for method_name in ("get", "post", "close"):
        if not callable(getattr(http_client, method_name, None)):
            raise ToolGatewayValidationError("http_client must provide get(), post(), and close()")


def _validate_async_http_client(
    http_client: object | None,
    *,
    allow_buffered_custom_http_client: bool,
) -> None:
    if http_client is None:
        return
    if isinstance(http_client, httpx.Client):
        raise ToolGatewayValidationError("http_client must be an httpx.AsyncClient-compatible async client")
    if not allow_buffered_custom_http_client and not callable(getattr(http_client, "stream", None)):
        raise ToolGatewayValidationError(
            "http_client must provide async stream(); pass allow_buffered_custom_http_client=True "
            "only if the injected client enforces equivalent response-size limits."
        )
    for method_name in ("get", "post", "aclose"):
        if not callable(getattr(http_client, method_name, None)):
            raise ToolGatewayValidationError("http_client must provide async get(), post(), and aclose()")


def _optional_event_hook(event_hook: object | None) -> TelemetryEventHook | None:
    if event_hook is None:
        return None
    if not callable(event_hook):
        raise ToolGatewayValidationError("event_hook must be callable")
    return event_hook


def _tool_list_params(
    status: Literal["active"] | None,
    owner_team: str | None,
    limit: int,
    offset: int,
) -> list[tuple[str, str]]:
    limit = _require_integer(limit, "limit")
    offset = _require_integer(offset, "offset")
    if limit <= 0:
        raise ToolGatewayValidationError("limit must be greater than zero")
    if limit > 200:
        raise ToolGatewayValidationError("limit must be less than or equal to 200")
    if offset < 0:
        raise ToolGatewayValidationError("offset must be greater than or equal to zero")
    params: list[tuple[str, str]] = []
    normalized_status = _optional_text(status)
    normalized_owner_team = _optional_text(owner_team)
    if normalized_status is not None and normalized_status != "active":
        raise ToolGatewayValidationError("gateway discovery only supports active callable tools")
    if normalized_owner_team is not None:
        params.append(("owner_team", normalized_owner_team))
    params.append(("limit", str(limit)))
    params.append(("offset", str(offset)))
    return params


def _list_cache_key(credential_cache_key: str, params: list[tuple[str, str]]) -> _ListCacheKey:
    return (("__credential", credential_cache_key), *params)


def _tool_cache_key(credential_cache_key: str, tool_lookup: str) -> _ToolCacheKey:
    return (credential_cache_key, tool_lookup)


def _close_awaitable(value: Awaitable[Any]) -> None:
    close = getattr(value, "close", None)
    if callable(close):
        close()


def _tool_call_result(body: dict[str, Any]) -> ToolCallResult:
    error = body.get("error")
    if error not in (None, {}):
        raise ToolGatewayError(
            "Tool Gateway returned an error in a successful HTTP response.",
            code="invalid_response",
            response_body=body,
        )
    request_id = _required_response_string(body, "request_id")
    correlation_id = _required_response_string(body, "correlation_id")
    tool_name = _required_response_string(body, "tool_name")
    return ToolCallResult(
        request_id=request_id,
        correlation_id=correlation_id,
        tool_name=tool_name,
        reason_code=_optional_response_string_field(body, "reason_code"),
        decision=_optional_response_mapping_field(body, "decision"),
        result=body.get("result"),
        raw=_immutable_mapping(body),
    )


def _tool_definition(body: dict[str, Any]) -> ToolDefinition:
    description_value = body.get("description")
    if description_value is not None and not isinstance(description_value, str):
        raise ToolGatewayError(
            "Tool Gateway response field must be a string: description.",
            code="invalid_response",
            response_body=body,
        )
    return ToolDefinition(
        id=_required_response_string(body, "id"),
        name=_required_response_string(body, "name"),
        display_name=_required_response_string(body, "display_name"),
        description=_response_string(description_value) or "",
        owner_team=_required_response_string(body, "owner_team"),
        status=_required_response_string(body, "status"),
        required_scope=_required_response_string(body, "required_scope"),
        input_schema_json=_optional_response_mapping_field(body, "input_schema_json"),
        output_schema_json=_optional_response_mapping_field(body, "output_schema_json"),
        raw=_immutable_mapping(body),
    )


def _gateway_compatibility(body: dict[str, Any]) -> GatewayCompatibility:
    gateway_contract_version = _optional_response_string_field(body, "gateway_contract_version")
    min_sdk_version = _optional_response_string_field(body, "min_sdk_version")
    return GatewayCompatibility(
        compatible=gateway_contract_version == SDK_GATEWAY_CONTRACT_VERSION,
        sdk_version=SDK_VERSION,
        expected_gateway_contract_version=SDK_GATEWAY_CONTRACT_VERSION,
        gateway_contract_version=gateway_contract_version,
        min_sdk_version=min_sdk_version,
        raw=_immutable_mapping(body),
    )


def _clone_tool_definition(tool: ToolDefinition) -> ToolDefinition:
    return ToolDefinition(
        id=tool.id,
        name=tool.name,
        display_name=tool.display_name,
        description=tool.description,
        owner_team=tool.owner_team,
        status=tool.status,
        required_scope=tool.required_scope,
        input_schema_json=copy.deepcopy(tool.input_schema_json),
        output_schema_json=copy.deepcopy(tool.output_schema_json),
        raw=_immutable_mapping(_mutable_mapping(tool.raw)),
    )


def _trim_cache(cache: dict[Any, Any], max_entries: int) -> None:
    while len(cache) > max_entries:
        cache.pop(next(iter(cache)))


def _raise_denied(body: dict[str, Any], status_code: int) -> None:
    reason_code = body.get("reason_code")
    if reason_code is None:
        _raise_gateway_error(body, status_code)
    raise ToolDeniedError(
        "Tool call denied by gateway policy.",
        reason_code=str(reason_code),
        status_code=status_code,
        request_id=_optional_string(body.get("request_id")),
        correlation_id=_optional_string(body.get("correlation_id")),
        response_body=body,
    )


def _raise_gateway_error(
    body: dict[str, Any],
    status_code: int,
    *,
    retry_after_seconds: float | None = None,
) -> None:
    error = _optional_mapping(body.get("error")) or {}
    code = error.get("code") or body.get("code") or body.get("reason_code")
    if status_code == 401:
        raise ToolAuthenticationError(
            "Tool Gateway authentication failed.",
            status_code=status_code,
            code=str(code) if code is not None else None,
            request_id=_optional_string(body.get("request_id")),
            correlation_id=_optional_string(body.get("correlation_id")),
            retry_after_seconds=retry_after_seconds,
            response_body=body,
        )
    raise ToolGatewayError(
        f"Tool Gateway returned HTTP {status_code}.",
        status_code=status_code,
        code=str(code) if code is not None else None,
        request_id=_optional_string(body.get("request_id")),
        correlation_id=_optional_string(body.get("correlation_id")),
        retry_after_seconds=retry_after_seconds,
        response_body=body,
    )


def _send_limited_sync_request(
    http_client: Any,
    method: str,
    url: str,
    *,
    max_response_bytes: int,
    **kwargs: Any,
) -> httpx.Response:
    stream = getattr(http_client, "stream", None)
    if callable(stream):
        with stream(method, url, **kwargs) as response:
            return _limited_sync_response(response, max_response_bytes=max_response_bytes)
    request_method = getattr(http_client, method.lower())
    return cast(httpx.Response, request_method(url, **kwargs))


async def _send_limited_async_request(
    http_client: Any,
    method: str,
    url: str,
    *,
    max_response_bytes: int,
    **kwargs: Any,
) -> httpx.Response:
    stream = getattr(http_client, "stream", None)
    if callable(stream):
        async with stream(method, url, **kwargs) as response:
            return await _limited_async_response(response, max_response_bytes=max_response_bytes)
    request_method = getattr(http_client, method.lower())
    response = request_method(url, **kwargs)
    return cast(httpx.Response, await response if inspect.isawaitable(response) else response)


def _limited_sync_response(
    response: httpx.Response,
    *,
    max_response_bytes: int,
) -> httpx.Response:
    _ensure_response_content_length_within_limit(response, max_response_bytes=max_response_bytes)
    content = bytearray()
    for chunk in response.iter_bytes():
        content.extend(chunk)
        if len(content) > max_response_bytes:
            raise _response_too_large_error(response.status_code)
    return _materialized_response(response, bytes(content))


async def _limited_async_response(
    response: httpx.Response,
    *,
    max_response_bytes: int,
) -> httpx.Response:
    _ensure_response_content_length_within_limit(response, max_response_bytes=max_response_bytes)
    content = bytearray()
    async for chunk in response.aiter_bytes():
        content.extend(chunk)
        if len(content) > max_response_bytes:
            raise _response_too_large_error(response.status_code)
    return _materialized_response(response, bytes(content))


def _materialized_response(response: httpx.Response, content: bytes) -> httpx.Response:
    return httpx.Response(
        response.status_code,
        headers=response.headers,
        content=content,
        request=getattr(response, "request", None),
        extensions=getattr(response, "extensions", {}) or {},
    )


def _response_json(
    response: httpx.Response,
    *,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> dict[str, Any]:
    return _mapping_response(_response_data(response, max_response_bytes=max_response_bytes))


def _response_data(
    response: httpx.Response,
    *,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> Any:
    _ensure_response_within_limit(response, max_response_bytes=max_response_bytes)
    try:
        return response.json()
    except ValueError:
        return {
            "error": {
                "code": "non_json_response",
                "message": "Tool Gateway returned a non-JSON response.",
                "body_excerpt": _sanitize_text(_response_text_excerpt(response)),
            }
        }


def _ensure_response_within_limit(
    response: httpx.Response,
    *,
    max_response_bytes: int,
) -> None:
    _ensure_response_content_length_within_limit(response, max_response_bytes=max_response_bytes)
    content = getattr(response, "content", b"")
    if isinstance(content, bytes) and len(content) > max_response_bytes:
        raise _response_too_large_error(response.status_code)


def _ensure_response_content_length_within_limit(
    response: httpx.Response,
    *,
    max_response_bytes: int,
) -> None:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_response_bytes:
                raise _response_too_large_error(response.status_code)
        except ValueError:
            pass


def _response_too_large_error(status_code: int | None) -> ToolGatewayError:
    return ToolGatewayError(
        "Tool Gateway response exceeds max_response_bytes.",
        code="response_too_large",
        status_code=status_code,
        response_body={"error": {"code": "response_too_large"}},
    )


def _mapping_response(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"result": value}


def _optional_mapping(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _optional_response_mapping_field(
    body: dict[str, Any],
    field_name: str,
) -> dict[str, Any] | None:
    value = body.get(field_name)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ToolGatewayError(
            f"Tool Gateway response field must be an object: {field_name}.",
            code="invalid_response",
            response_body=body,
        )
    return copy.deepcopy(value)


def _optional_response_string_field(body: dict[str, Any], field_name: str) -> str | None:
    value = body.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolGatewayError(
            f"Tool Gateway response field must be a string: {field_name}.",
            code="invalid_response",
            response_body=body,
        )
    return value


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _immutable_mapping(value: dict[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {str(key): _immutable_value(child_value) for key, child_value in value.items()}
    )


def _immutable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _immutable_mapping(value)
    if isinstance(value, Mapping):
        return _immutable_mapping(_mutable_mapping(value))
    if isinstance(value, list):
        return tuple(_immutable_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_immutable_value(item) for item in value)
    return copy.deepcopy(value)


def _mutable_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _mutable_value(child_value) for key, child_value in value.items()}


def _mutable_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _mutable_mapping(value)
    if isinstance(value, tuple):
        return [_mutable_value(item) for item in value]
    if isinstance(value, list):
        return [_mutable_value(item) for item in value]
    return copy.deepcopy(value)


def _response_text_excerpt(response: httpx.Response) -> str:
    content = getattr(response, "content", b"")
    if isinstance(content, bytes):
        excerpt = content[:MAX_NON_JSON_ERROR_EXCERPT_BYTES]
        return excerpt.decode(response.encoding or "utf-8", errors="replace")
    return str(content)[:MAX_NON_JSON_ERROR_EXCERPT_BYTES]


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ToolGatewayValidationError(f"{field_name} must be a string")
    stripped = value.strip()
    if not stripped:
        raise ToolGatewayValidationError(f"{field_name} is required")
    return stripped


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolGatewayValidationError("optional text values must be strings")
    stripped = value.strip()
    return stripped or None


def _require_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolGatewayValidationError(f"{field_name} must be an integer")
    return value


def _optional_positive_integer(value: object | None, field_name: str) -> int | None:
    if value is None:
        return None
    integer = _require_integer(value, field_name)
    if integer <= 0:
        raise ToolGatewayValidationError(f"{field_name} must be greater than zero")
    return integer


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ToolGatewayValidationError(f"{field_name} must be a boolean")
    return value


def _require_finite_number(
    value: object,
    field_name: str,
    *,
    minimum: float,
    include_minimum: bool,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolGatewayValidationError(f"{field_name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ToolGatewayValidationError(f"{field_name} must be a finite number")
    if include_minimum:
        if normalized < minimum:
            raise ToolGatewayValidationError(f"{field_name} must be greater than or equal to {minimum:g}")
    elif normalized <= minimum:
        raise ToolGatewayValidationError(f"{field_name} must be greater than {minimum:g}")
    return normalized


def _require_header_text(value: object, field_name: str) -> str:
    stripped = _require_text(value, field_name)
    if _has_control_character(stripped):
        raise ToolGatewayValidationError(f"{field_name} must not contain header control characters")
    return stripped


def _optional_header_text(value: object | None, field_name: str) -> str | None:
    stripped = _optional_text(value)
    if stripped is None:
        return None
    if _has_control_character(stripped):
        raise ToolGatewayValidationError(f"{field_name} must not contain header control characters")
    return stripped


def _optional_idempotency_key(value: object | None) -> str | None:
    if value is None:
        return None
    key = _optional_header_text(value, "idempotency_key")
    if key is None:
        return None
    if len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ToolGatewayValidationError(
            f"idempotency_key must be {MAX_IDEMPOTENCY_KEY_LENGTH} characters or fewer"
        )
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        raise ToolGatewayValidationError("idempotency_key contains unsupported characters")
    return key


def _require_gateway_token(value: object) -> str:
    token = _require_header_text(value, "token")
    if token.lower().startswith("bearer "):
        raise ToolGatewayValidationError("token must be the raw gateway token without the Bearer prefix")
    if any(character.isspace() for character in token):
        raise ToolGatewayValidationError("token must not contain whitespace")
    if len(token) > MAX_GATEWAY_TOKEN_LENGTH:
        raise ToolGatewayValidationError(
            f"token must be {MAX_GATEWAY_TOKEN_LENGTH} characters or fewer"
        )
    if not RAW_GATEWAY_TOKEN_PATTERN.fullmatch(token):
        raise ToolGatewayValidationError("token contains unsupported characters")
    return token


def _gateway_error_code(body: dict[str, Any]) -> str | None:
    error = _optional_mapping(body.get("error")) or {}
    code = error.get("code") or body.get("code") or body.get("reason_code")
    return str(code) if code is not None else None


def _should_retry_tool_call_response(
    response: httpx.Response,
    body: dict[str, Any],
    *,
    attempts: int,
    max_retries: int,
) -> bool:
    if attempts >= max_retries:
        return False
    if response.status_code == 409:
        return _gateway_error_code(body) == "idempotency_in_progress"
    return response.status_code in RETRYABLE_TOOL_CALL_STATUS_CODES


def _token_cache_fingerprint(token: str) -> str:
    return hmac.new(_CACHE_FINGERPRINT_KEY, token.encode("utf-8"), hashlib.sha256).hexdigest()


def _safe_lookup_text(value: str, *, max_length: int = 80) -> str:
    sanitized = _sanitize_text(value)
    if len(sanitized) <= max_length:
        return sanitized
    return f"{sanitized[:max_length]}..."


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 3)


def _require_json_object(
    value: object,
    field_name: str,
    *,
    max_bytes: int | None = None,
) -> None:
    if not isinstance(value, dict):
        raise ToolGatewayValidationError(f"{field_name} must be a dictionary")
    _validate_json_value(value, field_name, seen=set())
    try:
        serialized = json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ToolGatewayValidationError(f"{field_name} must be JSON serializable") from exc
    if max_bytes is not None and len(serialized.encode("utf-8")) > max_bytes:
        raise ToolGatewayValidationError(f"{field_name} exceeds max_payload_bytes")


def _validate_json_value(value: object, field_name: str, *, seen: set[int]) -> None:
    if isinstance(value, dict):
        object_id = id(value)
        if object_id in seen:
            raise ToolGatewayValidationError(f"{field_name} must not contain cycles")
        seen.add(object_id)
        for key, child_value in value.items():
            if not isinstance(key, str):
                raise ToolGatewayValidationError(f"{field_name} keys must be strings")
            _validate_json_value(child_value, field_name, seen=seen)
        seen.remove(object_id)
        return
    if isinstance(value, list):
        object_id = id(value)
        if object_id in seen:
            raise ToolGatewayValidationError(f"{field_name} must not contain cycles")
        seen.add(object_id)
        for child_value in value:
            _validate_json_value(child_value, field_name, seen=seen)
        seen.remove(object_id)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ToolGatewayValidationError(f"{field_name} must contain only finite numbers")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return
    raise ToolGatewayValidationError(f"{field_name} must be JSON serializable")


def _sanitize_error_body(value: Any) -> dict[str, Any]:
    sanitized = _sanitize_error_value(value)
    return sanitized if isinstance(sanitized, dict) else {"result": sanitized}


def _sanitize_error_value(
    value: Any,
    *,
    key: str | None = None,
    depth: int = 0,
) -> Any:
    if depth > MAX_ERROR_BODY_DEPTH:
        return "[truncated]"
    if key is not None and _is_sensitive_key(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {
            str(child_key): _sanitize_error_value(
                child_value,
                key=str(child_key),
                depth=depth + 1,
            )
            for child_key, child_value in list(value.items())[:MAX_ERROR_BODY_ITEMS]
        }
    if isinstance(value, list):
        return [
            _sanitize_error_value(item, key=key, depth=depth + 1)
            for item in value[:MAX_ERROR_BODY_ITEMS]
        ]
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _sanitize_text(str(value))


def _is_sensitive_key(key: str) -> bool:
    normalized = _normalize_sensitive_key(key)
    return normalized in SENSITIVE_KEY_NAMES or normalized.endswith(SENSITIVE_KEY_SUFFIXES)


def _normalize_sensitive_key(key: str) -> str:
    with_word_boundaries = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key.strip())
    return re.sub(r"[^a-z0-9]+", "_", with_word_boundaries.lower()).strip("_")


def _truncate_string(value: str) -> str:
    if len(value) <= MAX_ERROR_BODY_STRING_LENGTH:
        return value
    return f"{value[:MAX_ERROR_BODY_STRING_LENGTH - 3]}..."


def _sanitize_text(value: str) -> str:
    redacted = SENSITIVE_TEXT_ASSIGNMENT_RE.sub(_redact_sensitive_assignment, value)
    redacted = BEARER_TOKEN_RE.sub("Bearer [redacted]", redacted)
    return _truncate_string(redacted)


def _redact_sensitive_assignment(match: re.Match[str]) -> str:
    return (
        f"{match.group('key')}"
        f"{match.group('before_sep')}"
        f"{match.group('sep')}"
        f"{match.group('after_sep')}"
        "[redacted]"
    )


def _retry_after_seconds(response: httpx.Response | None) -> float | None:
    if response is None:
        return None
    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return None
    stripped = retry_after.strip()
    if not stripped:
        return None
    try:
        seconds = float(stripped)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(stripped)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        seconds = retry_at.timestamp() - time.time()
    if not math.isfinite(seconds):
        return None
    return max(0.0, seconds)


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ToolGatewayError(
            f"Tool Gateway returned an invalid {label}.",
            code="invalid_response",
        )
    return value


def _required_response_string(body: dict[str, Any], field_name: str) -> str:
    value = _response_string(body.get(field_name))
    if not value:
        raise ToolGatewayError(
            f"Tool Gateway response is missing required field: {field_name}.",
            code="invalid_response",
            response_body=body,
        )
    return value


def _response_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _is_local_http_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    normalized = hostname.strip("[]").lower()
    if normalized in {"localhost", "::1"} or normalized.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False
