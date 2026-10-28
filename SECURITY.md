# Security policy

## Scope

This project handles public proxy endpoints and publishes generated configuration files. It does not relay client traffic through Cloudflare. The generated Pages assets are public unless a deployment adds a separate access-control layer.

## Reporting a vulnerability

Do not file public issues containing credentials, Cloudflare account data, subscription URLs with secrets, or live proxy addresses. Use the repository host's private vulnerability-reporting feature when available. Otherwise, contact the maintainer through a private channel listed in the repository profile.

## Safe handling

- Never commit `.env` files, Wrangler credentials, live scan output, proxy snapshots, or personal deployment reports.
- Treat public proxies as untrusted. Do not send credentials or confidential data through them.
- Keep TLS certificate verification enabled. Do not add a direct-connection fallback after proxy verification fails.
- Review third-party source terms before collecting or republishing their data.
