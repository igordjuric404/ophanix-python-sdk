# SPDX-License-Identifier: MIT
"""Minimal async worker integration for the Ophanix Tool Gateway SDK."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from ophanix_tool_gateway import (
    AsyncOphanixToolGatewayClient,
    EnvironmentTokenProvider,
    ToolDeniedError,
    ToolGatewayClientConfig,
    ToolGatewayError,
)


async def handle_claim_job(claim_id: str) -> dict[str, Any]:
    config = ToolGatewayClientConfig(
        timeout_seconds=5.0,
        max_payload_bytes=64_000,
        max_response_bytes=256_000,
        cache_tools=True,
        cache_ttl_seconds=60.0,
    )
    async with AsyncOphanixToolGatewayClient.from_config(
        base_url=os.environ["OPHANIX_GATEWAY_BASE_URL"],
        token_provider=EnvironmentTokenProvider(),
        config=config,
    ) as client:
        compatibility = await client.check_compatibility()
        if not compatibility.compatible:
            raise RuntimeError(
                "Tool Gateway contract mismatch: "
                f"expected {compatibility.expected_gateway_contract_version}, "
                f"got {compatibility.gateway_contract_version!r}"
            )
        try:
            result = await client.call_tool(
                "claims.lookup",
                {"claim_id": claim_id},
                correlation_id=f"claim-job:{claim_id}",
            )
        except ToolDeniedError:
            return {"status": "denied", "claim_id": claim_id}
        except ToolGatewayError as exc:
            return {"status": "gateway_error", "code": exc.code, "claim_id": claim_id}
        return {"status": "ok", "result": result.result}


if __name__ == "__main__":
    print(asyncio.run(handle_claim_job(os.environ.get("CLAIM_ID", "claim_123"))))
