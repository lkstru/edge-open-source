# Changelog

## 1.1.0 — 2026-10-28

- Add ProxyScrape and Proxio public JSON sources, with Proxio CC BY 4.0 attribution.
- Deduplicate across sources and balance source/protocol sampling within each country’s 16-new-candidate budget.
- Rotate new candidates using local attempt history.
- Revalidate previously published nodes separately from the new-candidate budget; check uncovered countries first.
- Recheck every initially successful node before export and reject publication of nonempty snapshots missing second-verification markers.
- Preserve the previous published-node pool across empty scans and failed deployments.
- Keep personal configuration, scan history, published-node caches, and generated snapshots out of Git.
- Add offline regression coverage for source adapters, sampling, security exclusions, and previous-node retention.

## 1.0.0 — 2026-10-28

- Initial public source package for Mac-side collection and verification with static Pages publishing.
- Added per-country sampling default of 16 candidates.
- Added a no-empty-publication guard and configurable Pages project name.
- Excluded account-specific deployment artifacts and live proxy snapshots from the public source package.
