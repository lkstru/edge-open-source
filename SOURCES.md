# Data sources and attribution

The application code is licensed under MIT. Third-party proxy datasets have their own terms. Public listing and a dataset license do not establish authorization from a proxy endpoint's owner.

| Source | Interface used | Interpretation |
| --- | --- | --- |
| [ProxySpace](https://proxyspace.pro/) | Country-specific HTTP and SOCKS5 TXT lists | Candidates only; locally verified. |
| [HProxy](https://hproxy.com/docs/free-proxy-list) | Global public JSON list | Alive HTTP/SOCKS5 records; TLS interception flags exclude the endpoint across all sources. |
| [ProxyScrape](https://proxyscrape.com/free-proxy-list) | Official v4 public JSON API, bounded pagination | Only explicit HTTP/SOCKS5 records; unknown HTTPS semantics are not guessed. |
| [Proxio](https://proxio.io/) | [Official JSON mirror](https://github.com/proxio-io/proxy-list) | HTTP, SOCKS5, and HTTPS-as-HTTP-CONNECT per its README. |

## Proxio dataset credit

Proxio public proxy data is provided by [proxio.io](https://proxio.io/) under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/). This application filters, deduplicates, samples, verifies, and reformats that data. Generated configurations and the website include a credit link. This credit does not imply Proxio endorsement.

ProxyScrape downloads are bounded at 10,000 raw records per scan; if pagination exceeds that bound the source reports an error rather than silently accepting a truncated pool. Proxio's JSON response is bounded by download size. Source labels such as alive, HTTPS, country, or reliability do not replace local validation. A verified proxy is not a trusted operator.
