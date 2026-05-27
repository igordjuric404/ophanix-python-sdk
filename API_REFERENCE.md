# Tool Gateway SDK API Reference

This is the supported public surface for the `ophanix-python-sdk` `0.x`
line.

## Clients

### `OphanixToolGatewayClient`

Synchronous client. Use as a context manager or call `close()`.

Constructor:

```python
OphanixToolGatewayClient(
    *,
    base_url: str,
    token_provider: TokenProvider,
    timeout_seconds: float = 5.0,
    max_payload_bytes: int = 1_000_000,
    max_response_bytes: int = 1_000_000,
    max_cache_entries: int = 256,
    http_client: httpx.Client | None = None,
    cache_tools: bool = False,
    cache_ttl_seconds: float = 300.0,
    event_hook: Callable[[Mapping[str, Any]], None] | None = None,
    allow_insecure_http: bool = False,
    user_agent: str | None = None,
    discovery_max_retries: int = 2,
    discovery_retry_backoff_seconds: float = 0.2,
    discovery_retry_max_sleep_seconds: float = 5.0,
    discovery_retry_jitter_ratio: float = 0.2,
    invocation_max_retries: int = 2,
    invocation_retry_backoff_seconds: float = 0.2,
    invocation_retry_max_sleep_seconds: float = 5.0,
    invocation_retry_jitter_ratio: float = 0.2,
    allow_buffered_custom_http_client: bool = False,
    raise_event_hook_errors: bool = False,
)
```

Methods:

- `from_env(base_url_env_var: str = "OPHANIX_GATEWAY_BASE_URL", token_env_var: str = "OPHANIX_GATEWAY_TOKEN", config: ToolGatewayClientConfig | None = None, ...) -> OphanixToolGatewayClient`
- `call_tool(tool_name: str, payload: dict[str, Any], correlation_id: str | None = None, idempotency_key: str | None = None) -> ToolCallResult`
- `check_compatibility() -> GatewayCompatibility`
- `list_tools(status: Literal["active"] | None = None, owner_team: str | None = None, limit: int = 50, offset: int = 0) -> list[ToolDefinition]`
- `list_all_tools(owner_team: str | None = None, page_size: int = 200, max_total: int | None = None) -> list[ToolDefinition]`
- `get_tool(tool_name: str) -> ToolDefinition`
- `clear_tool_cache() -> None`
- `close() -> None`

### `AsyncOphanixToolGatewayClient`

Async client with the same constructor options and method names. `from_env`,
`call_tool`,
`check_compatibility`, `list_tools`, `list_all_tools`, `get_tool`, and `close`
are available; all except `from_env` are awaitable.

### `ToolGatewayClientConfig`

Reusable configuration accepted by `OphanixToolGatewayClient.from_config(...)`
and `AsyncOphanixToolGatewayClient.from_config(...)`. It includes timeout,
payload/response caps, cache settings, discovery retry settings, idempotent
invocation retry settings, custom client streaming policy, user agent, and
event-hook failure mode. `base_url`,
`token_provider`, `http_client`, and `event_hook` remain constructor inputs.

## Token Providers

- `EnvironmentTokenProvider(env_var: str = "OPHANIX_GATEWAY_TOKEN")`
- `StaticTokenProvider(token: str)`

Custom providers must expose `get_token()` and return the raw bearer token
without the `Bearer` prefix.

Token strings with the `Bearer ` prefix, whitespace, or unsupported characters
raise `ToolGatewayValidationError` before a network request is sent. Tokens must
be 4096 characters or fewer.

## CLI

The package installs `ophanix-tool-gateway`.

- `ophanix-tool-gateway list-tools [--owner-team TEAM] [--limit N] [--offset N]`
- `ophanix-tool-gateway call-tool TOOL_NAME PAYLOAD_JSON [--correlation-id ID] [--idempotency-key KEY]`

Both commands read `OPHANIX_GATEWAY_BASE_URL` and `OPHANIX_GATEWAY_TOKEN` unless
`--base-url` or `--token-env-var` is supplied. Output is JSON.

## Data Classes

- `ToolDefinition`: `id`, `name`, `display_name`, `description`, `owner_team`,
  `status`, `required_scope`, optional input/output schemas, and immutable raw
  response metadata.
- `ToolCallResult`: `request_id`, `correlation_id`, `tool_name`, `result`,
  `reason_code`, optional `decision`, and immutable raw response metadata.
- `GatewayCompatibility`: `compatible`, `sdk_version`,
  `expected_gateway_contract_version`, `gateway_contract_version`,
  `min_sdk_version`, and immutable raw response metadata.

## Errors

- `ToolAuthenticationError`: gateway credential was missing, expired, revoked,
  or invalid.
- `ToolDeniedError`: gateway policy denied the authenticated call.
- `ToolGatewayError`: transport, gateway, upstream, response-size, malformed
  response, or other SDK-level failure.
- `ToolGatewayValidationError`: local configuration or caller input was invalid.
  This is a `ValueError` subclass.

All SDK errors expose `message`, `status_code`, `code`, `request_id`,
`correlation_id`, `retry_after_seconds`, and sanitized `response_body` where
available.

Sanitized `response_body` values redact common credential and PII-like keys:
`authorization`, `api_key`, `credential`, `password`, `secret`, `token`, `key`,
`email`, `phone`, `address`, and `ssn`.

## Event Hook Schema

| Event | Fields |
| --- | --- |
| `tool_call.start` | `tool_name`, `correlation_id`, `idempotent` |
| `tool_call.success` | `tool_name`, `request_id`, `correlation_id`, `reason_code`, `elapsed_ms` |
| `tool_call.denied` | `tool_name`, `status_code`, `elapsed_ms` |
| `tool_call.error` | `tool_name`, `status_code` or `code`, `elapsed_ms` |
| `tool_call.retry` | `tool_name`, `attempt`, `delay_seconds`, `status_code`, `code` |
| `tool_discovery.retry` | `attempt`, `delay_seconds`, `status_code` |

Invocation retries are gated by `idempotency_key`. Without a key, `call_tool`
does not retry transient failures because the SDK cannot prove that the upstream
operation is safe to repeat.

## Compatibility And Deprecations

- `list_tools(status="active")` is accepted for compatibility and emits a
  `DeprecationWarning`. Gateway discovery is always active-only.
- `product_platform.tool_gateway` imports are compatibility shims for earlier
  internal callers through the `0.1.x` line. Prefer `ophanix_tool_gateway` for
  new code.
