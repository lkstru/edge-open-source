# LKSTRU Edge

Mac-side public-proxy collection and verification, with static Cloudflare Pages publishing for Shadowrocket remote configurations. The Cloudflare deployment serves files only: it does not relay client traffic or run a VPN tunnel.

**This project republishes public HTTP/SOCKS5 proxy endpoints. Publicly listed does not mean owner-authorized, safe, private, or reliable. Review the source providers' terms and local law before using or republishing any endpoint. Do not use these proxies for sensitive accounts or confidential traffic.**

繁體中文說明：[README.zh-TW.md](README.zh-TW.md)

## What it does

- Fetches candidates from ProxySpace, HProxy, ProxyScrape, and Proxio on the Mac.
- Filters invalid addresses, ports, country labels, offline entries, and known TLS-intercepting endpoints.
- Tests a bounded sample with the system `curl`, validating HTTPS certificates, observed exit country through two endpoints, and basic YouTube reachability.
- Exports a Shadowrocket configuration and country-specific files from verified candidates only.
- Publishes a static snapshot to a Pages project you configure.
- Stops publishing if no candidate passed verification, preserving the last deployed snapshot.

The client connects directly to the selected proxy. Cloudflare Pages serves the snapshot and does not forward the client's proxy traffic. There is no Worker, VLESS relay, scheduled scan, or background Mac service in this project.

## Requirements

- macOS with Python 3.11 or newer, `curl`, Node.js, and npm.
- A Cloudflare account and a Pages project that you own.
- A Wrangler login on the Mac. The first deployment may open a browser for Cloudflare authorization.
- Shadowrocket for using the generated remote configuration.

## First-time setup

1. Create a Cloudflare Pages project, or choose a Pages project you already own.
2. Double-click `run-macos.command`. On first use it installs the locked Wrangler dependency if needed and creates `deploy/project.env` from the example.
3. Enter your Pages project name in `deploy/project.env`, save, and double-click `run-macos.command` again.
4. Complete Wrangler authorization in the browser if prompted. The command will collect, verify, build, validate, and publish the static snapshot.

The project name and any local authorization state are not committed. Do not add Cloudflare tokens, credentials, or personal configuration to the repository.

## Regular use

Double-click `run-macos.command` to refresh and publish. It revalidates previously published nodes, then samples up to 16 different new candidates per country, testing up to 8 at a time. A full scan can take tens of minutes. The command does not change macOS proxy settings, turn on a VPN, or modify an existing Shadowrocket configuration.

In Shadowrocket, add the website's remote configuration URL from the **Config** page. After a new Pages deployment, refresh that remote configuration in Shadowrocket. Choosing a configuration is separate from downloading or importing it.

`collect-only.command` runs a scan without publishing. The CLI equivalents are:

```sh
# Install the locked Wrangler dependency once
npm ci --ignore-scripts

# Collect and verify all listed countries without publishing
python3 collect.py --countries ALL --limit 16 --workers 8

# Collect a targeted set with a larger sample
python3 collect.py --countries JP,TW,HK,US --limit 24 --workers 8

# Publish a fresh local snapshot (must be no older than 30 minutes)
python3 publish.py --skip-refresh

# Verify a deployment against the local dist/ directory
python3 check_live.py https://YOUR-PAGES-PROJECT.pages.dev
```

An empty verified result is not published by default. To intentionally publish a REJECT-only configuration, pass `--allow-empty`; this requires an explicit terminal command.

## Verification details and limits

The scanner downloads HProxy's global list once and requests ProxySpace lists by country and protocol. It bounds source and verification concurrency, rejects private or invalid endpoints, and does not fall back to direct requests when proxy verification fails. It checks the reported country and IP through Cloudflare Trace and ProxySpace Geo, then checks a small public YouTube resource. These checks do not prove video playback, iPhone connectivity, DNS or IPv6 leak prevention, UDP behavior, throughput, or continued availability.

The source lists may have no candidates for many countries. Increasing the sample limit can only help where a source has candidates; it cannot create an exit in a country not represented by those sources. Public proxies can disappear or be controlled by unknown parties. The client-to-proxy connection itself is not encrypted for plain HTTP/SOCKS5 proxies, even when the destination website uses HTTPS.

The 30-minute expiry is a warning and download gate on this website. It does not remove already published static files or revoke a configuration already imported by a client. Refresh the scan and deployment, and remove outdated configurations from clients yourself.

## Public-data notice

The generated Pages files (`nodes.json`, `subscribe.conf`, and country configurations) are public static assets unless you add a separate access-control layer. Anyone who can fetch the URLs can read the published proxy endpoints. This repository contains no account-specific domain, account ID, token, deployment report, or live proxy snapshot.

## Repository contents

- `collect.py`, `publish.py`: local collection, verification, export, and Pages publishing.
- `web/`: static country/status page and security headers.
- `countries.json`: ISO country and region catalog.
- `test_collect.py`, `test_publish.py`: offline tests using mocked network requests.
- `deploy/`: Pages build settings and an example local project-name file.
- `run-macos.command`, `collect-only.command`: Finder launchers.

See [SECURITY.md](SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md), and [LICENSE](LICENSE).

Data-source references: [ProxySpace](https://proxyspace.pro/) and [HProxy free proxy list](https://hproxy.com/docs/free-proxy-list). This project is independent and is not endorsed by either provider, Cloudflare, or Shadowrocket.

## v1.1.0 workflow and upgrade

Previously published nodes are fully revalidated before new candidates are checked. They do not consume the per-country budget of 16 new candidates. New candidates are deduplicated, balanced across sources and protocols, rotated using local attempt history, and ordered to check countries without a successful old node first. Every initially successful node must pass a second complete HTTPS/country/YouTube check before export. Historical success is never reused as current evidence; country coverage can still decrease.

`.scan-history.json` stores up to 30 days of local attempt times. `.published-nodes.json` stores the successfully published pool. Both are excluded from Git. The first upgrade bootstraps from an existing `dist/nodes.json`. Source errors are recorded while other sources continue; empty scans stop publication. Nonempty snapshots without second-verification markers cannot be published, so perform a fresh scan after upgrading.

See [SOURCES.md](SOURCES.md) for source interfaces, protocol mapping, and Proxio CC BY 4.0 data attribution. Source counts in the local report are assignments after deduplication, not guaranteed incremental or exclusive contributions.
