# Security Policy

## Reporting

Do not open a public issue for vulnerabilities, leaked credentials, customer data, private keys, or exploitable production details. Use GitHub private vulnerability reporting when enabled, or report through the verified private address `security@dominionhealing.org`.

## Immediate handling

For a suspected secret exposure:

1. stop further distribution;
2. revoke or rotate the affected credential;
3. preserve non-secret evidence;
4. open an incident under `operations/INCIDENT_RESPONSE.md`;
5. identify every consumer and log location;
6. verify replacement credentials and service health; and
7. add a preventive control and regression check.

## Repository rules

- Secrets live in approved GitHub Environments or the designated secret manager.
- Never commit `.env` files, credentials, tokens, private keys, customer records, or raw production logs.
- Use secret references and hashes rather than secret values.
- Grant tools and workflows least privilege.
- Pin third-party GitHub Actions to full commit SHAs.
- Require review and passing governance checks before merging control-plane changes.
- Treat model-generated code, commands, legal claims, and completion claims as untrusted until independently verified.
