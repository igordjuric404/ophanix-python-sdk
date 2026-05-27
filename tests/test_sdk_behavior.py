from __future__ import annotations

import asyncio
import json
import os
import threading
import unittest
from collections.abc import Callable
from collections.abc import Mapping
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from typing import Any
from typing import cast

import httpx
import ophanix_tool_gateway as sdk

from ophanix_tool_gateway import (
    AsyncOphanixToolGatewayClient,
    AuthorizationStatus,
    GatewayCompatibility,
    OphanixToolGatewayClient,
    StaticTokenProvider,
    ToolAuthorizationRequired,
    ToolDeniedError,
    ToolGatewayClientConfig,
    ToolGatewayError,
    ToolGatewayValidationError,
)


TOOL_FIXTURE = {
    "id": "tool_claims_lookup",
    "name": "claims.lookup",
    "display_name": "Claims Lookup",
    "description": "Lookup claim state.",
    "owner_team": "Claims",
    "status": "active",
    "required_scope": "claims.lookup:read",
    "input_schema_json": {"type": "object"},
    "output_schema_json": {"type": "object"},
}


class StandaloneSdkBehaviorTests(unittest.TestCase):
    def test_public_api_snapshot_includes_mvp_sdk_types(self) -> None:
        expected_exports = {
            "AsyncOphanixToolGatewayClient",
            "AuthorizationChallenge",
            "AuthorizationStatus",
            "EnvironmentTokenProvider",
            "GatewayCompatibility",
            "OphanixToolGatewayClient",
            "StaticTokenProvider",
            "ToolAuthorizationRequired",
            "ToolGatewayClientConfig",
            "ToolGatewayValidationError",
        }

        self.assertTrue(expected_exports.issubset(set(sdk.__all__)))
        self.assertIs(sdk.GatewayCompatibility, GatewayCompatibility)
        self.assertIs(sdk.ToolGatewayClientConfig, ToolGatewayClientConfig)

    def test_call_tool_returns_typed_result(self) -> None:
        client = _client(
            lambda _request: httpx.Response(
                200,
                json={
                    "request_id": "req-sdk",
                    "correlation_id": "corr-sdk",
                    "tool_name": "claims.lookup",
                    "reason_code": "allowed",
                    "result": {"status": "succeeded"},
                    "error": None,
                },
            )
        )

        result = client.call_tool("claims.lookup", {"claim_id": "claim_123"})

        self.assertEqual(result.request_id, "req-sdk")
        self.assertEqual(result.result, {"status": "succeeded"})

    def test_call_tool_sends_idempotency_key_and_retries_retryable_status(self) -> None:
        calls: list[httpx.Request] = []
        events: list[Mapping[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(503, json={"error": {"code": "try_again"}})
            return httpx.Response(
                200,
                json={
                    "request_id": "req-idem",
                    "correlation_id": "corr-idem",
                    "tool_name": "claims.lookup",
                    "result": {"ok": True},
                    "error": None,
                },
            )

        client = _client(handler, event_hook=events.append)
        client.invocation_retry_backoff_seconds = 0.0
        client.invocation_retry_jitter_ratio = 0.0

        result = client.call_tool(
            "claims.lookup",
            {"claim_id": "claim_123"},
            idempotency_key="idem-sdk-1",
        )

        self.assertEqual(result.result, {"ok": True})
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].headers["Idempotency-Key"], "idem-sdk-1")
        self.assertEqual(calls[1].headers["Idempotency-Key"], "idem-sdk-1")
        self.assertEqual(
            [event["event"] for event in events if event["event"] == "tool_call.retry"],
            ["tool_call.retry"],
        )

    def test_call_tool_does_not_retry_retryable_status_without_idempotency_key(self) -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(503, json={"error": {"code": "try_again"}})

        client = _client(handler)

        with self.assertRaises(ToolGatewayError) as raised:
            client.call_tool("claims.lookup", {"claim_id": "claim_123"})

        self.assertEqual(calls, 1)
        self.assertEqual(raised.exception.code, "try_again")

    def test_call_tool_rejects_invalid_idempotency_key_locally(self) -> None:
        client = _client(lambda _request: httpx.Response(200, json={}))

        with self.assertRaisesRegex(ToolGatewayValidationError, "idempotency_key"):
            client.call_tool(
                "claims.lookup",
                {"claim_id": "claim_123"},
                idempotency_key="bad key",
            )

    def test_list_tools_returns_isolated_schema_copies_from_cache(self) -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=[TOOL_FIXTURE])

        client = _client(handler, cache_tools=True)

        first = client.list_tools()[0]
        self.assertIsNotNone(first.input_schema_json)
        assert first.input_schema_json is not None
        first.input_schema_json["mutated"] = True
        second = client.list_tools()[0]

        self.assertEqual(calls, 1)
        self.assertEqual(second.input_schema_json, {"type": "object"})

    def test_top_level_gateway_error_code_is_preserved(self) -> None:
        client = _client(
            lambda _request: httpx.Response(
                500,
                json={"code": "GATEWAY_UNAVAILABLE", "message": "Gateway down."},
            )
        )

        with self.assertRaises(ToolGatewayError) as raised:
            client.call_tool("claims.lookup", {"claim_id": "claim_123"})

        self.assertEqual(raised.exception.code, "GATEWAY_UNAVAILABLE")

    def test_retry_after_header_is_exposed_on_gateway_errors(self) -> None:
        client = _client(
            lambda _request: httpx.Response(
                429,
                json={"code": "RATE_LIMITED", "message": "Retry later."},
                headers={"Retry-After": "5"},
            )
        )

        with self.assertRaises(ToolGatewayError) as raised:
            client.call_tool("claims.lookup", {"claim_id": "claim_123"})

        self.assertEqual(raised.exception.retry_after_seconds, 5.0)

    def test_generic_403_remains_gateway_error(self) -> None:
        client = _client(
            lambda _request: httpx.Response(
                403,
                json={"error": {"code": "forbidden", "message": "Proxy denied."}},
            )
        )

        with self.assertRaises(ToolGatewayError) as raised:
            client.call_tool("claims.lookup", {"claim_id": "claim_123"})

        self.assertNotIsInstance(raised.exception, ToolDeniedError)
        self.assertEqual(raised.exception.code, "forbidden")

    def test_structured_policy_403_raises_denied_error(self) -> None:
        client = _client(
            lambda _request: httpx.Response(
                403,
                json={
                    "request_id": "req-denied",
                    "correlation_id": "corr-denied",
                    "tool_name": "claims.lookup",
                    "decision": {"decision": "deny"},
                    "reason_code": "permission_missing",
                    "error": {"code": "permission_missing"},
                },
            )
        )

        with self.assertRaises(ToolDeniedError) as raised:
            client.call_tool("claims.lookup", {"claim_id": "claim_123"})

        self.assertEqual(raised.exception.reason_code, "permission_missing")

    def test_authorization_required_response_raises_challenge_error(self) -> None:
        client = _client(
            lambda _request: httpx.Response(
                403,
                json={
                    "request_id": "req-authz",
                    "correlation_id": "corr-authz",
                    "tool_name": "claims.lookup",
                    "decision": {"decision": "pending_authorization"},
                    "reason_code": "authorization_required",
                    "result": None,
                    "error": {
                        "code": "authorization_required",
                        "message": "User authorization is required.",
                        "authorization": {
                            "authorization_session_id": "oauthsess_123",
                            "authorization_url": "https://auth.example.com/start",
                            "provider": "claims-oauth",
                            "required_scopes": ["claims.read"],
                            "approval_state": "pending_authorization",
                        },
                    },
                },
            )
        )

        with self.assertRaises(ToolAuthorizationRequired) as raised:
            client.call_tool("claims.lookup", {"claim_id": "claim_123"})

        self.assertEqual(raised.exception.reason_code, "authorization_required")
        self.assertEqual(raised.exception.challenge.authorization_session_id, "oauthsess_123")
        self.assertEqual(raised.exception.challenge.required_scopes, ("claims.read",))

    def test_authorization_status_helper_polls_gateway(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            return httpx.Response(
                200,
                json={
                    "authorization_session_id": "oauthsess_123",
                    "authorization_url": "https://auth.example.com/start",
                    "provider": "claims-oauth",
                    "required_scopes": ["claims.read"],
                    "status": "authorized",
                    "approval_state": "approved",
                },
            )

        client = _client(handler)

        status = client.get_authorization_status("oauthsess_123")

        self.assertIsInstance(status, AuthorizationStatus)
        self.assertEqual(seen["path"], "/api/v1/gateway/authorizations/oauthsess_123")
        self.assertEqual(status.authorization_session_id, "oauthsess_123")
        self.assertEqual(status.status, "authorized")
        self.assertEqual(status.approval_state, "approved")

    def test_check_compatibility_reads_authenticated_capabilities_contract(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/v1/gateway/capabilities")
            return httpx.Response(
                200,
                json={
                    "gateway_contract_version": "tool-gateway.v1",
                    "min_sdk_version": "0.1.0",
                    "sdk_package": "ophanix-python-sdk",
                },
            )

        client = _client(handler)

        compatibility = client.check_compatibility()

        self.assertTrue(compatibility.compatible)
        self.assertEqual(compatibility.gateway_contract_version, "tool-gateway.v1")
        self.assertEqual(compatibility.expected_gateway_contract_version, "tool-gateway.v1")

    def test_standalone_sdk_live_gateway_contract(self) -> None:
        with _live_gateway_contract_fixture() as gateway:
            client = OphanixToolGatewayClient(
                base_url=gateway.base_url,
                token_provider=StaticTokenProvider("sdk-live-token"),
                allow_insecure_http=True,
                invocation_retry_backoff_seconds=0.0,
                invocation_retry_jitter_ratio=0.0,
            )

            compatibility = client.check_compatibility()
            tools = client.list_all_tools()
            result = client.call_tool(
                "claims.lookup",
                {"claim_id": "claim_123"},
                correlation_id="corr-sdk-live-contract",
                idempotency_key="idem-sdk-live-contract",
            )
            with self.assertRaises(ToolDeniedError) as denied:
                client.call_tool(
                    "claims.hidden",
                    {"claim_id": "claim_123"},
                    correlation_id="corr-sdk-live-denied",
                )
            client.close()

        self.assertTrue(compatibility.compatible)
        self.assertEqual(compatibility.gateway_contract_version, "tool-gateway.v1")
        self.assertEqual([tool.name for tool in tools], ["claims.lookup"])
        self.assertEqual(result.request_id, "req-live-contract")
        self.assertEqual(result.correlation_id, "corr-sdk-live-contract")
        self.assertEqual(result.result["body"], {"claim_id": "claim_123", "verified": True})
        self.assertEqual(denied.exception.reason_code, "tool_call_denied")
        self.assertEqual(
            [request["path"] for request in gateway.requests],
            [
                "/api/v1/gateway/capabilities",
                "/api/v1/gateway/tools",
                "/api/v1/tools/claims.lookup/invoke",
                "/api/v1/tools/claims.hidden/invoke",
            ],
        )
        for request in gateway.requests:
            self.assertEqual(request["authorization"], "Bearer sdk-live-token")
            self.assertTrue(str(request["user_agent"]).startswith("ophanix-tool-gateway-python/"))
        lookup_request = gateway.requests[2]
        self.assertEqual(lookup_request["idempotency_key"], "idem-sdk-live-contract")
        self.assertEqual(lookup_request["body"]["correlation_id"], "corr-sdk-live-contract")
        self.assertEqual(lookup_request["body"]["payload"], {"claim_id": "claim_123"})

    def test_from_config_constructs_client_without_repeating_every_option(self) -> None:
        config = ToolGatewayClientConfig(
            timeout_seconds=2.5,
            cache_tools=True,
            cache_ttl_seconds=10.0,
            discovery_max_retries=0,
        )

        client = OphanixToolGatewayClient.from_config(
            base_url="https://gateway.example.test",
            token_provider=StaticTokenProvider("sdk-token"),
            config=config,
            http_client=httpx.Client(
                transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=[]))
            ),
        )

        self.assertEqual(client.timeout_seconds, 2.5)
        self.assertTrue(client.cache_tools)
        self.assertEqual(client.cache_ttl_seconds, 10.0)
        self.assertEqual(client.discovery_max_retries, 0)

    def test_from_env_constructs_client_from_gateway_environment(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=[TOOL_FIXTURE])

        with patch.dict(
            os.environ,
            {
                "OPHANIX_GATEWAY_BASE_URL": "https://gateway.example.test",
                "OPHANIX_GATEWAY_TOKEN": "sdk-token",
            },
        ):
            client = OphanixToolGatewayClient.from_env(
                http_client=httpx.Client(transport=httpx.MockTransport(handler))
            )
            tools = client.list_tools()

        self.assertEqual([tool.name for tool in tools], ["claims.lookup"])
        self.assertEqual(str(requests[0].url), "https://gateway.example.test/api/v1/gateway/tools?limit=50&offset=0")
        self.assertEqual(requests[0].headers["Authorization"], "Bearer sdk-token")

    def test_from_env_requires_gateway_base_url(self) -> None:
        with patch.dict(os.environ, {"OPHANIX_GATEWAY_TOKEN": "sdk-token"}, clear=True):
            with self.assertRaisesRegex(ToolGatewayValidationError, "OPHANIX_GATEWAY_BASE_URL"):
                OphanixToolGatewayClient.from_env()

    def test_async_from_env_constructs_client_from_gateway_environment(self) -> None:
        async def exercise() -> None:
            requests: list[httpx.Request] = []

            async def handler(request: httpx.Request) -> httpx.Response:
                requests.append(request)
                return httpx.Response(200, json=[TOOL_FIXTURE])

            with patch.dict(
                os.environ,
                {
                    "OPHANIX_GATEWAY_BASE_URL": "https://gateway.example.test",
                    "OPHANIX_GATEWAY_TOKEN": "sdk-token",
                },
            ):
                async with AsyncOphanixToolGatewayClient.from_env(
                    http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
                ) as client:
                    tools = await client.list_tools()

            self.assertEqual([tool.name for tool in tools], ["claims.lookup"])
            self.assertEqual(
                str(requests[0].url),
                "https://gateway.example.test/api/v1/gateway/tools?limit=50&offset=0",
            )
            self.assertEqual(requests[0].headers["Authorization"], "Bearer sdk-token")

        asyncio.run(exercise())

    def test_list_all_tools_enforces_max_total(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            offset = int(request.url.params.get("offset", "0"))
            tool = {**TOOL_FIXTURE, "id": f"tool_{offset}", "name": f"claims.lookup.{offset}"}
            return httpx.Response(200, json=[tool])

        client = _client(handler)

        with self.assertRaises(ToolGatewayError) as raised:
            client.list_all_tools(page_size=1, max_total=1)

        self.assertEqual(raised.exception.code, "tool_discovery_too_large")

    def test_streaming_response_cap_blocks_body_without_content_length(self) -> None:
        client = _client(
            lambda _request: httpx.Response(
                200,
                content=b"x" * 11,
                headers={"content-type": "application/json"},
            ),
        )
        client.max_response_bytes = 10

        with self.assertRaises(ToolGatewayError) as raised:
            client.call_tool("claims.lookup", {"claim_id": "claim_123"})

        self.assertEqual(raised.exception.code, "response_too_large")

    def test_list_tools_status_argument_warns_as_deprecated(self) -> None:
        client = _client(lambda _request: httpx.Response(200, json=[]))

        with self.assertWarns(DeprecationWarning):
            self.assertEqual(client.list_tools(status="active"), [])

    def test_token_provider_rejects_bearer_prefixed_token_locally(self) -> None:
        client = OphanixToolGatewayClient(
            base_url="https://gateway.example.test",
            token_provider=StaticTokenProvider("Bearer sdk-token"),
            http_client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200))),
        )

        with self.assertRaisesRegex(ToolGatewayValidationError, "without the Bearer prefix"):
            client.list_tools()

    def test_token_provider_rejects_tokens_above_gateway_cap_locally(self) -> None:
        client = OphanixToolGatewayClient(
            base_url="https://gateway.example.test",
            token_provider=StaticTokenProvider("a" * 4097),
            http_client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200))),
        )

        with self.assertRaisesRegex(ToolGatewayValidationError, "4096 characters or fewer"):
            client.list_tools()

    def test_get_tool_not_found_sanitizes_lookup_text(self) -> None:
        client = _client(lambda _request: httpx.Response(200, json=[]))

        with self.assertRaises(ToolGatewayError) as raised:
            client.get_tool("token=super-secret-value-that-should-not-be-logged")

        self.assertEqual(raised.exception.code, "tool_not_visible")
        self.assertIn("token=[redacted]", raised.exception.message)
        self.assertNotIn("super-secret-value", raised.exception.message)

    def test_calls_after_close_raise_stable_sdk_error(self) -> None:
        client = _client(lambda _request: httpx.Response(200, json=[]))
        client.close()

        with self.assertRaises(ToolGatewayError) as raised:
            client.list_tools()

        self.assertEqual(raised.exception.code, "client_closed")

    def test_custom_http_client_without_stream_is_rejected_by_default(self) -> None:
        with self.assertRaisesRegex(ToolGatewayValidationError, "must provide stream"):
            OphanixToolGatewayClient(
                base_url="https://gateway.example.test",
                token_provider=StaticTokenProvider("sdk-token"),
                http_client=cast(httpx.Client, _BufferedOnlyClient()),
            )

    def test_strict_event_hook_mode_surfaces_hook_failures(self) -> None:
        def failing_hook(_event: Mapping[str, Any]) -> None:
            raise RuntimeError("hook down")

        client = _client(
            lambda _request: httpx.Response(200, json=[]),
            event_hook=failing_hook,
            raise_event_hook_errors=True,
        )

        with self.assertRaisesRegex(RuntimeError, "hook down"):
            client.call_tool("claims.lookup", {"claim_id": "claim_123"})

    def test_list_all_tools_deduplicates_offset_page_overlap(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            offset = int(request.url.params.get("offset", "0"))
            if offset < 2:
                return httpx.Response(200, json=[TOOL_FIXTURE])
            return httpx.Response(200, json=[])

        client = _client(handler)

        tools = client.list_all_tools(page_size=1)

        self.assertEqual([tool.id for tool in tools], ["tool_claims_lookup"])

    def test_event_hook_receives_retry_and_elapsed_telemetry(self) -> None:
        events: list[Mapping[str, Any]] = []
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503, json={"error": {"code": "try_again"}})
            return httpx.Response(200, json=[TOOL_FIXTURE])

        client = _client(handler, event_hook=events.append)
        client.discovery_max_retries = 1
        client.discovery_retry_backoff_seconds = 0.0

        self.assertEqual([tool.name for tool in client.list_tools()], ["claims.lookup"])

        retry_events = [event for event in events if event["event"] == "tool_discovery.retry"]
        self.assertEqual(len(retry_events), 1)
        self.assertEqual(retry_events[0]["attempt"], 1)
        self.assertEqual(retry_events[0]["status_code"], 503)

    def test_success_event_hook_includes_elapsed_ms(self) -> None:
        events: list[Mapping[str, Any]] = []
        client = _client(
            lambda _request: httpx.Response(
                200,
                json={
                    "request_id": "req-sdk",
                    "correlation_id": "corr-sdk",
                    "tool_name": "claims.lookup",
                    "result": {"ok": True},
                    "error": None,
                },
            ),
            event_hook=events.append,
        )

        client.call_tool("claims.lookup", {"claim_id": "claim_123"})

        success = [event for event in events if event["event"] == "tool_call.success"][0]
        self.assertIsInstance(success["elapsed_ms"], float)

    def test_error_response_sanitization_redacts_common_pii_keys(self) -> None:
        client = _client(
            lambda _request: httpx.Response(
                500,
                json={
                    "error": {
                        "code": "upstream_failed",
                        "email": "patient@example.test",
                        "message": "email: patient@example.test",
                        "ssn": "123-45-6789",
                    }
                },
            )
        )

        with self.assertRaises(ToolGatewayError) as raised:
            client.call_tool("claims.lookup", {"claim_id": "claim_123"})

        self.assertEqual(raised.exception.response_body["error"]["email"], "[redacted]")
        self.assertEqual(raised.exception.response_body["error"]["ssn"], "[redacted]")
        self.assertNotIn("patient@example.test", str(raised.exception.response_body))


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    cache_tools: bool = False,
    event_hook: Callable[[Mapping[str, Any]], None] | None = None,
    raise_event_hook_errors: bool = False,
) -> OphanixToolGatewayClient:
    return OphanixToolGatewayClient(
        base_url="https://gateway.example.test",
        token_provider=StaticTokenProvider("sdk-token"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_tools=cache_tools,
        event_hook=event_hook,
        raise_event_hook_errors=raise_event_hook_errors,
    )


class _BufferedOnlyClient:
    def get(self, *_args: Any, **_kwargs: Any) -> httpx.Response:
        return httpx.Response(200, json=[])

    def post(self, *_args: Any, **_kwargs: Any) -> httpx.Response:
        return httpx.Response(200, json={})

    def close(self) -> None:
        return None


class _LiveGatewayContractFixture:
    def __init__(self) -> None:
        self.base_url = ""
        self.requests: list[dict[str, Any]] = []

    def handler_class(self) -> type[BaseHTTPRequestHandler]:
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                request = fixture._record(self)
                if request["path"] == "/api/v1/gateway/capabilities":
                    self._send_json(
                        200,
                        {
                            "gateway_contract_version": "tool-gateway.v1",
                            "min_sdk_version": "0.1.0",
                            "sdk_package": "ophanix-python-sdk",
                        },
                    )
                    return
                if request["path"] == "/api/v1/gateway/tools":
                    self._send_json(200, [TOOL_FIXTURE])
                    return
                self._send_json(404, {"error": {"code": "not_found"}})

            def do_POST(self) -> None:
                body = self._read_json_body()
                request = fixture._record(self, body=body)
                if request["path"] == "/api/v1/tools/claims.lookup/invoke":
                    self._send_json(
                        200,
                        {
                            "request_id": "req-live-contract",
                            "correlation_id": body.get("correlation_id") or "corr-live-contract",
                            "tool_name": "claims.lookup",
                            "reason_code": "allowed",
                            "decision": {"decision": "allow"},
                            "result": {
                                "status": "succeeded",
                                "body": {
                                    "claim_id": body.get("payload", {}).get("claim_id"),
                                    "verified": True,
                                },
                                "upstream_status_code": 200,
                            },
                            "error": None,
                        },
                    )
                    return
                if request["path"] == "/api/v1/tools/claims.hidden/invoke":
                    self._send_json(
                        403,
                        {
                            "request_id": "req-live-denied",
                            "correlation_id": body.get("correlation_id") or "corr-live-denied",
                            "tool_name": "claims.hidden",
                            "reason_code": "tool_call_denied",
                            "error": {"code": "tool_call_denied"},
                        },
                    )
                    return
                self._send_json(404, {"error": {"code": "not_found"}})

            def log_message(self, _format: str, *_args: object) -> None:
                return None

            def _read_json_body(self) -> dict[str, Any]:
                raw = self.rfile.read(int(self.headers.get("Content-Length") or "0"))
                if not raw:
                    return {}
                decoded = json.loads(raw.decode("utf-8"))
                if not isinstance(decoded, dict):
                    return {}
                return decoded

            def _send_json(self, status_code: int, payload: object) -> None:
                encoded = json.dumps(payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        return Handler

    def _record(
        self,
        handler: BaseHTTPRequestHandler,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = {
            "method": handler.command,
            "path": handler.path.partition("?")[0],
            "authorization": handler.headers.get("Authorization"),
            "user_agent": handler.headers.get("User-Agent"),
            "idempotency_key": handler.headers.get("Idempotency-Key"),
            "body": body or {},
        }
        self.requests.append(request)
        return request


@contextmanager
def _live_gateway_contract_fixture():
    fixture = _LiveGatewayContractFixture()
    server = ThreadingHTTPServer(("127.0.0.1", 0), fixture.handler_class())
    fixture.base_url = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield fixture
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
