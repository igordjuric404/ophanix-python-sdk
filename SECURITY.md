# Security Policy

## Supported Versions

The standalone SDK is currently pre-1.0. Security fixes are applied to the
latest released `0.x` line and to the main development branch. Older internal
builds should upgrade to the latest validated wheel before reporting behavior as
a product defect.

## Reporting A Vulnerability

Report suspected vulnerabilities in the SDK, gateway contract, token handling,
or packaging pipeline through GitHub private vulnerability reporting for this
repository before public disclosure:

`https://github.com/ophanix/ophanix-python-sdk/security/advisories/new`

If your organization has a private security intake for this repository, use
that channel first and reference the GitHub advisory once it is created. Do not
open a public issue for unpatched credential, authentication, SSRF, release, or
data-exposure bugs.

MVP escalation owner: route SDK and Tool Gateway security reports to the
Product Platform security maintainer/on-call for this repository. If an internal
owner alias is unavailable, use GitHub private vulnerability reporting and tag
the issue `ophanix-python-sdk` after triage.

The expected response target is:

- Initial acknowledgement: 2 business days.
- Triage/update: 5 business days after acknowledgement.
- Fix timeline: based on severity, exploitability, and release coordination.

When reporting an issue, include:

- SDK package version.
- Python version.
- Gateway version or deployment identifier.
- Whether the issue affects sync client, async client, direct HTTP callers, or
  server-side gateway behavior.
- A minimal reproduction that does not include live tokens, credentials, or
  sensitive payload data.

Do not include raw bearer tokens, API keys, customer payloads, private upstream
URLs, or customer identifiers in reports. Use redacted examples, request IDs,
and correlation IDs when possible.

## Security Expectations

- Use HTTPS gateway URLs outside localhost development.
- Store gateway tokens in a secret manager or environment variable, not source
  code.
- Rotate gateway credentials before expiry and after suspected exposure.
- Keep `max_payload_bytes`, `max_response_bytes`, and request timeouts bounded
  for production agents.
- Do not implement automatic retries for mutating tool calls unless the gateway
  and tool contract provide idempotency semantics.
