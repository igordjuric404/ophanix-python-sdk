"""Command line helpers for the Ophanix Tool Gateway SDK."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from ophanix_tool_gateway.sdk import (
    DEFAULT_GATEWAY_BASE_URL_ENV_VAR,
    DEFAULT_GATEWAY_TOKEN_ENV_VAR,
    EnvironmentTokenProvider,
    OphanixToolGatewayClient,
    ToolCallResult,
    ToolDefinition,
    ToolGatewayError,
    ToolGatewayValidationError,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list-tools":
            return _list_tools(args)
        if args.command == "call-tool":
            return _call_tool(args)
    except (ToolGatewayError, ToolGatewayValidationError, json.JSONDecodeError) as exc:
        _write_json({"error": _error_payload(exc)}, stream=sys.stderr)
        return 1
    parser.print_help(sys.stderr)
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ophanix-tool-gateway",
        description="Call governed Ophanix Tool Gateway tools.",
    )
    parser.add_argument(
        "--base-url",
        help=f"Gateway base URL. Defaults to ${DEFAULT_GATEWAY_BASE_URL_ENV_VAR}.",
    )
    parser.add_argument(
        "--token-env-var",
        default=DEFAULT_GATEWAY_TOKEN_ENV_VAR,
        help=f"Environment variable containing the raw gateway token. Defaults to {DEFAULT_GATEWAY_TOKEN_ENV_VAR}.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    list_tools = subcommands.add_parser("list-tools", help="List callable tools visible to the token.")
    list_tools.add_argument("--owner-team")
    list_tools.add_argument("--limit", type=int, default=50)
    list_tools.add_argument("--offset", type=int, default=0)

    call_tool = subcommands.add_parser("call-tool", help="Invoke one governed tool.")
    call_tool.add_argument("tool_name")
    call_tool.add_argument("payload_json", help="JSON object payload to send to the tool.")
    call_tool.add_argument("--correlation-id")
    call_tool.add_argument("--idempotency-key")
    return parser


def _list_tools(args: argparse.Namespace) -> int:
    with _client_from_args(args) as client:
        tools = client.list_tools(
            owner_team=args.owner_team,
            limit=args.limit,
            offset=args.offset,
        )
    _write_json({"tools": [_tool_to_json(tool) for tool in tools]})
    return 0


def _call_tool(args: argparse.Namespace) -> int:
    payload = json.loads(args.payload_json)
    if not isinstance(payload, dict):
        raise ToolGatewayValidationError("payload_json must decode to a JSON object")
    with _client_from_args(args) as client:
        result = client.call_tool(
            args.tool_name,
            payload,
            correlation_id=args.correlation_id,
            idempotency_key=args.idempotency_key,
        )
    _write_json(_result_to_json(result))
    return 0


def _client_from_args(args: argparse.Namespace) -> OphanixToolGatewayClient:
    if args.base_url:
        return OphanixToolGatewayClient(
            base_url=args.base_url,
            token_provider=EnvironmentTokenProvider(args.token_env_var),
        )
    return OphanixToolGatewayClient.from_env(token_env_var=args.token_env_var)


def _tool_to_json(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "id": tool.id,
        "name": tool.name,
        "display_name": tool.display_name,
        "description": tool.description,
        "owner_team": tool.owner_team,
        "status": tool.status,
        "required_scope": tool.required_scope,
        "input_schema_json": tool.input_schema_json,
        "output_schema_json": tool.output_schema_json,
    }


def _result_to_json(result: ToolCallResult) -> dict[str, Any]:
    return {
        "request_id": result.request_id,
        "correlation_id": result.correlation_id,
        "tool_name": result.tool_name,
        "reason_code": result.reason_code,
        "decision": result.decision,
        "result": result.result,
    }


def _error_payload(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, ToolGatewayError):
        return {
            "message": exc.message,
            "status_code": exc.status_code,
            "code": exc.code,
            "request_id": exc.request_id,
            "correlation_id": exc.correlation_id,
        }
    if isinstance(exc, json.JSONDecodeError):
        return {"message": "payload_json must be valid JSON", "code": "invalid_json"}
    return {"message": str(exc), "code": "invalid_configuration"}


def _write_json(payload: dict[str, Any], *, stream: Any | None = None) -> None:
    stream = stream or sys.stdout
    stream.write(json.dumps(payload, sort_keys=True))
    stream.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
