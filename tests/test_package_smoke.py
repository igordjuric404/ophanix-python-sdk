from __future__ import annotations

import py_compile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import ophanix_tool_gateway
from ophanix_tool_gateway import ToolCallResult, ToolDefinition
from ophanix_tool_gateway import cli


class PackageSmokeTests(unittest.TestCase):
    def test_public_exports_are_available(self) -> None:
        self.assertIsNotNone(ophanix_tool_gateway.OphanixToolGatewayClient)
        self.assertIsNotNone(ophanix_tool_gateway.AsyncOphanixToolGatewayClient)
        self.assertIsNotNone(ophanix_tool_gateway.ToolGatewayError)
        self.assertIsNotNone(ophanix_tool_gateway.ToolAuthenticationError)
        self.assertIsNotNone(ophanix_tool_gateway.ToolGatewayValidationError)

    def test_examples_compile(self) -> None:
        package_root = Path(__file__).resolve().parents[1]

        py_compile.compile(
            str(package_root / "examples" / "async_worker_example.py"),
            doraise=True,
        )

    def test_cli_lists_tools_as_json(self) -> None:
        client = _FakeClient(
            tools=[
                ToolDefinition(
                    id="tool_claims_lookup",
                    name="claims.lookup",
                    display_name="Claims Lookup",
                    description="Lookup claim state.",
                    owner_team="Claims",
                    status="active",
                    required_scope="claims.lookup:read",
                )
            ]
        )
        output = StringIO()

        with patch.object(cli, "_client_from_args", return_value=client), redirect_stdout(output):
            exit_code = cli.main(["list-tools", "--limit", "1"])

        self.assertEqual(exit_code, 0)
        self.assertIn('"name": "claims.lookup"', output.getvalue())

    def test_cli_calls_tool_with_payload_json(self) -> None:
        client = _FakeClient()
        output = StringIO()

        with patch.object(cli, "_client_from_args", return_value=client), redirect_stdout(output):
            exit_code = cli.main(
                [
                    "call-tool",
                    "claims.lookup",
                    '{"claim_id": "claim_123"}',
                    "--correlation-id",
                    "corr-cli",
                    "--idempotency-key",
                    "idem-cli",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(client.calls, [("claims.lookup", {"claim_id": "claim_123"}, "corr-cli", "idem-cli")])
        self.assertIn('"request_id": "req-cli"', output.getvalue())


class _FakeClient:
    def __init__(self, tools: list[ToolDefinition] | None = None) -> None:
        self.tools = tools or []
        self.calls: list[tuple[str, dict[str, object], str | None, str | None]] = []

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None

    def list_tools(
        self,
        *,
        owner_team: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ToolDefinition]:
        return self.tools[offset : offset + limit]

    def call_tool(
        self,
        tool_name: str,
        payload: dict[str, object],
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ToolCallResult:
        self.calls.append((tool_name, payload, correlation_id, idempotency_key))
        return ToolCallResult(
            request_id="req-cli",
            correlation_id=correlation_id or "corr-cli",
            tool_name=tool_name,
            result={"ok": True},
        )


if __name__ == "__main__":
    unittest.main()
