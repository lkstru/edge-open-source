# Files to keep

## Keep the complete source folder

For a working copy or a public repository, keep the complete project tree. The runtime depends on a small set of files working together:

| File or folder | Required? | Purpose |
| --- | --- | --- |
| `scan-mode.zsh` | Yes for Finder launchers | Shared daily/deep mode menu. |
| `source_adapters.py` | Yes | Parses and fetches the additional public JSON sources. |
| `collect.py` | Yes | Downloads candidate lists, filters them, runs local HTTPS checks, and generates outputs. |
| `publish.py` | Yes for publishing | Validates a fresh snapshot and invokes Wrangler to publish Pages assets. |
| `countries.json` | Yes | ISO country/region catalog shown by the site and checked by the publisher. |
| `web/` | Yes | Static page, browser code, styles, 404 page, and response security headers. |
| `deploy/wrangler.toml` | Yes for Pages publishing | Wrangler Pages build settings. |
| `package.json`, `package-lock.json` | Yes for publishing | Pin Wrangler and make dependency installation reproducible. |
| `run-macos.command` | Recommended | Finder one-click scan, validation, and deployment launcher. |
| `collect-only.command` | Optional | Finder launcher for a scan that does not publish. |
| `test_collect.py`, `test_publish.py`, `test_source_adapters.py`, `test_previous_nodes.py`, `test_scan_modes.py` | Recommended | Offline regression tests with mocked source requests. |
| `README.md`, `README.zh-TW.md`, `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md` | Recommended | Usage, licensing, security, and contributor guidance. |

## Keep private local configuration separately

- `deploy/project.env` is created from `deploy/project.env.example` on first run. Keep it in your private working copy; it names the Pages project and branch and is excluded from Git by `.gitignore`.
- Wrangler authentication is stored in the local user profile, not in this project. Do not copy it into a repository or archive. If it is lost, log in again with Wrangler.
- Do not publish generated `output/` or `dist/`. They can contain real proxy endpoints and subscription configuration. They can be regenerated, but keep a private backup only if you need a rollback snapshot.

## Rebuildable items

- `node_modules/`: recreate with `npm ci --ignore-scripts`.
- `output/`, `dist/`, `__pycache__/`, temporary locks, and Wrangler caches: generated locally; not needed in the public source archive.

## Before sharing an archive

Use `lkstru-edge-open-source.zip` or create a new archive from the clean source folder. Do not include local `.env` files, Wrangler state, live node lists, generated subscription files, deployment screenshots, account migration reports, or private backup folders. The clean package intentionally contains no live node snapshot or account-specific Cloudflare identifier.

## Existing installation versus public source

The public source package is a clean template. Keep the currently working local installation and its private configuration until you have configured and independently confirmed the public-source copy. The Pages deployment itself is managed by Cloudflare; source files do not contain its account settings or credentials.

Keep `.scan-history.json` and `.published-nodes.json` private. Both are optional local state, never public release files.
