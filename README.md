# SubScout

**A two-stage subdomain discovery tool: DNS resolution first, then HTTP/HTTPS probing of everything that resolves.**

SubScout merges the fast, broad sweep of DNS resolution with the detail of HTTP probing. Stage 1 checks which candidate subdomains actually exist in DNS (catching mail servers, internal services, and anything else — not just websites). Stage 2 then visits every resolved host over HTTP/HTTPS and reports its status code, so you immediately know what's actually live on the web versus just present in DNS.

---

## Why Two Stages

Probing every candidate over HTTP is slow and wasteful — most wordlist entries won't even resolve. Checking DNS first is cheap and fast, and narrows the list down to real hosts before spending time on HTTP requests. This mirrors how recon is normally done manually, just automated into one tool and one report.

---

## Features

- **Stage 1 — DNS resolution**: fast, stdlib-only (`socket.getaddrinfo`), no dependencies required
- **Stage 2 — HTTP/HTTPS probing**: status codes, final URL after redirects, color-coded output
- **Built-in wordlist**: ~130 common subdomains included, so it works with zero setup — pass `-w` for a larger custom list (e.g. SecLists)
- **`--dns-only`**: skip HTTP probing entirely for a pure existence sweep
- **`--filter`**: only show specific HTTP status codes (e.g. `200,301`)
- **`--http-only`**: skip HTTPS and only try HTTP during probing
- **`-v` / `--verbose`**: show redirect chains
- **Separate thread pools** for DNS and HTTP stages, since DNS can safely run at higher concurrency
- **Live progress indicators** for both stages
- **Combined report file**: live web hosts and all DNS-resolved subdomains, saved together

---

## Requirements

- Python 3.10+
- `requests` (only required for HTTP probing — DNS-only mode needs nothing extra)

```bash
pip install requests
```

---

## You Need Your Own Wordlist for Full Coverage

SubScout ships with a built-in list of ~130 common subdomain names so it works out of the box. For real recon, supply a larger wordlist with `-w`:

```
# example wordlist.txt — one subdomain per line
api
staging
internal-api
vpn-east
customer-portal
```

Recommended source: [SecLists](https://github.com/danielmiessler/SecLists) → `Discovery/DNS/`

---

## Usage

```bash
python3 subscout.py -d example.com
```

### Options

| Flag | Description | Default |
|---|---|---|
| `-d`, `--domain` | Target domain (required) | none |
| `-w`, `--wordlist` | Path to subdomain wordlist | built-in ~130 names |
| `-t`, `--threads` | Threads for DNS stage | `50` |
| `--http-threads` | Threads for HTTP stage | `20` |
| `-T`, `--timeout` | HTTP request timeout in seconds | `5` |
| `-o`, `--output` | Save results to this file | none |
| `-v`, `--verbose` | Show redirect chains | off |
| `--http-only` | Only try HTTP (skip HTTPS) during probing | off |
| `--dns-only` | Skip HTTP probing — DNS resolution only | off |
| `--filter` | Comma-separated HTTP status codes to show | all |

### Examples

Default scan using the built-in wordlist:

```bash
python3 subscout.py -d example.com
```

Full scan with a custom wordlist, saved to a file:

```bash
python3 subscout.py -d example.com -w subdomains-10000.txt -t 100 -o results.txt
```

DNS sweep only — no HTTP requests at all:

```bash
python3 subscout.py -d example.com --dns-only
```

Only show live sites and redirects, with redirect chains visible:

```bash
python3 subscout.py -d example.com --filter 200,301 -v
```

---

## Example Output

```
============================================================
  SubScout — Subdomain Discovery
============================================================
  Target   : example.com
  Wordlist : 130 entries (built-in)
  Mode     : DNS + HTTP probing

[Stage 1] DNS Resolution
  Checking 130 candidates with 50 threads...

  Resolved 9 subdomain(s) in 2.1s

[Stage 2] HTTP Probing
  Probing 9 resolved host(s) with 20 threads...

  [200]  www.example.com  (93.184.216.34)
  [301]  api.example.com  (93.184.216.35)
  [403]  admin.example.com  (93.184.216.36)

  3 live web host(s) found in 1.4s

============================================================
  DNS resolved   : 9
  Live web hosts : 3
============================================================
```

---

## Output File Format

When `-o` is used, the saved report includes two sections: live web hosts (status, host, final URL) and the full list of DNS-resolved subdomains with their IP addresses — so you keep the complete picture, not just the web-facing subset.

---

## Limitations

- DNS-only mode will miss subdomains that exist but aren't in your wordlist — it's a wordlist-based brute force, not a full enumeration technique (no certificate transparency log lookups, no passive sources)
- HTTP probing uses GET requests only and does not render JavaScript
- Very high DNS thread counts can trigger local resolver rate limits or OS resource exhaustion

---

## Legal & Ethical Use

Only scan domains you own or have explicit authorization to test, such as targets within the scope of a bug bounty program. Unauthorized subdomain enumeration against systems you don't have permission to test may violate laws and program rules. The author is not responsible for misuse of this tool.

---

## Author

**Oladunni Oluwaseyi**
GitHub: [@oluwaseyi-rgb](https://github.com/oluwaseyi-rgb)
LinkedIn: [Oluwaseyi Oladunni](https://www.linkedin.com/in/oluwaseyi-oladunni-6a42b1407)

---

## License

Released under the MIT License.
