# Contributing

Thanks for considering a contribution.

## Before opening a change

- Keep live proxy endpoints, generated scan reports, account identifiers, domains, tokens, and Wrangler state out of commits.
- Do not add a Worker, VLESS relay, or code that forwards client traffic through Cloudflare without first discussing the change with maintainers.
- Preserve certificate verification and the no-direct-fallback behavior.
- Respect the terms and rate limits of data sources.

## Local development

Python tests use mocked HTTP responses and do not intentionally contact public proxies:

```sh
python3 -m unittest -v test_collect.py test_publish.py test_source_adapters.py test_previous_nodes.py
```

The live scanner and Pages publisher access public sources and Cloudflare. Do not run them as part of routine tests. Run them only when you intend to perform a real scan or deploy to a Pages project you control.

## Pull requests

Describe the user-visible change, the files affected, and the checks run. Remove local output and credentials before committing.
