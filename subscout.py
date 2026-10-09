#!/usr/bin/env python3
"""
SubScout - Two-stage subdomain discovery tool
------------------------------------------------
Stage 1: DNS resolution sweep across a wordlist (fast, stdlib only)
Stage 2: HTTP/HTTPS probing of every resolved host (status codes, redirects)

Usage:
    python3 subscout.py -d example.com
    python3 subscout.py -d example.com -w wordlist.txt -t 100 -o results.txt
    python3 subscout.py -d example.com --dns-only
    python3 subscout.py -d example.com --filter 200,301 -v
"""

import argparse
import os
import socket
import sys
import time
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    import requests
    from requests.exceptions import ConnectionError, Timeout, TooManyRedirects
except ImportError:
    requests = None

# ── Terminal colors (ANSI) ────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"   # 2xx
YELLOW = "\033[93m"   # 3xx / warnings
RED    = "\033[91m"   # 4xx / 5xx
CYAN   = "\033[96m"   # info
DIM    = "\033[2m"

# Built-in list of common subdomains to get started without a wordlist file.
# Supply -w for a larger list (e.g. SecLists' Discovery/DNS/ wordlists).
COMMON_SUBDOMAINS = [
    "www", "mail", "ftp", "smtp", "pop", "imap", "webmail", "cpanel", "whm",
    "admin", "administrator", "portal", "dashboard", "api", "api2", "rest",
    "dev", "development", "staging", "stage", "test", "testing", "uat", "qa",
    "beta", "alpha", "demo", "sandbox", "preview", "preprod", "prod",
    "blog", "forum", "forums", "wiki", "docs", "documentation", "help",
    "support", "kb", "community", "status", "monitor", "health",
    "shop", "store", "cart", "checkout", "payments", "billing", "invoice",
    "cdn", "assets", "static", "media", "images", "img", "video", "files",
    "download", "downloads", "upload", "uploads", "backup",
    "db", "database", "mysql", "postgres", "redis", "mongo",
    "vpn", "remote", "ssh", "sftp", "proxy", "gateway", "firewall",
    "ns", "ns1", "ns2", "ns3", "dns", "dns1", "dns2",
    "mx", "mx1", "mx2", "email", "smtp2", "bounce", "relay",
    "m", "mobile", "app", "apps", "web", "secure", "ssl",
    "intranet", "internal", "corp", "corporate", "extranet",
    "git", "gitlab", "github", "bitbucket", "svn", "code", "repo",
    "jira", "confluence", "jenkins", "ci", "cd", "devops",
    "grafana", "kibana", "elastic", "logstash", "prometheus", "metrics",
    "s3", "storage", "cloud", "aws", "azure", "gcp",
    "old", "new", "v2", "v3", "legacy", "archive",
    "news", "events", "careers", "jobs", "hr",
    "login", "auth", "sso", "oauth", "id", "accounts",
    "crm", "erp", "cms", "wp", "wordpress", "drupal",
]


def status_color(code: int) -> str:
    if 200 <= code < 300:
        return GREEN
    if 300 <= code < 400:
        return YELLOW
    return RED


def load_wordlist(path: str) -> list[str]:
    """Load subdomain candidates from a file, one per line."""
    if not os.path.isfile(path):
        sys.exit(f"[ERROR] Wordlist not found: {path}")
    with open(path, "r", errors="ignore") as f:
        words = [
            line.strip().lower()
            for line in f
            if line.strip() and not line.startswith("#")
        ]
    if not words:
        sys.exit("[ERROR] Wordlist is empty.")
    return words


# ── Stage 1: DNS resolution ───────────────────────────────────────────────────
def resolve(subdomain: str, domain: str) -> dict | None:
    """Attempt to resolve <subdomain>.<domain>. Returns dict with fqdn/ips, or None."""
    fqdn = f"{subdomain}.{domain}"
    try:
        results = socket.getaddrinfo(fqdn, None)
        ips = sorted({r[4][0] for r in results})
        return {"fqdn": fqdn, "ips": ips}
    except (socket.gaierror, socket.herror):
        return None


def dns_stage(domain: str, wordlist: list[str], threads: int) -> list[dict]:
    found = []
    total = len(wordlist)
    completed = 0

    print(f"\n{BOLD}[Stage 1] DNS Resolution{RESET}")
    print(f"  Checking {total:,} candidates with {threads} threads...\n")

    start = time.time()
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(resolve, sub, domain): sub for sub in wordlist}
        for future in as_completed(futures):
            completed += 1
            result = future.result()
            if result:
                found.append(result)
            if completed % 200 == 0 or completed == total:
                pct = completed / total * 100
                print(
                    f"  {DIM}… {completed:,}/{total:,} ({pct:.1f}%), {len(found)} resolved{RESET}",
                    end="\r", flush=True,
                )

    elapsed = time.time() - start
    print(" " * 70, end="\r")
    print(f"  {GREEN}Resolved {len(found)} subdomain(s){RESET} in {elapsed:.1f}s\n")
    return found


# ── Stage 2: HTTP probing ─────────────────────────────────────────────────────
def probe_http(fqdn: str, timeout: int, protocols: list[str]) -> dict | None:
    """Try each protocol for fqdn. Returns result dict on any HTTP response, else None."""
    for scheme in protocols:
        url = f"{scheme}://{fqdn}"
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                headers={"User-Agent": "SubScout/1.0"},
                verify=False,
            )
            return {
                "url": resp.url,
                "status": resp.status_code,
                "scheme": scheme,
                "redirect": resp.url if resp.history else None,
            }
        except (ConnectionError, Timeout, TooManyRedirects):
            continue
        except Exception:
            continue
    return None


def print_result(result: dict, verbose: bool) -> None:
    code = result["status"]
    color = status_color(code)
    line = (
        f"  {color}{BOLD}[{code}]{RESET}  {CYAN}{result['fqdn']}{RESET}  "
        f"{DIM}({', '.join(result['ips'])}){RESET}"
    )
    if verbose and result.get("redirect") and result["redirect"] != f"{result['scheme']}://{result['fqdn']}":
        line += f"\n        {DIM}→ {result['redirect']}{RESET}"
    print(line)


def http_stage(resolved: list[dict], threads: int, timeout: int, protocols: list[str],
               status_filter: set | None, verbose: bool) -> list[dict]:
    live = []
    total = len(resolved)
    completed = 0

    print(f"{BOLD}[Stage 2] HTTP Probing{RESET}")
    print(f"  Probing {total:,} resolved host(s) with {threads} threads...\n")

    start = time.time()
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {
            executor.submit(probe_http, r["fqdn"], timeout, protocols): r
            for r in resolved
        }
        for future in as_completed(futures):
            completed += 1
            dns_result = futures[future]
            http_result = future.result()

            pct = completed / total * 100
            print(f"  {DIM}… {completed:,}/{total:,} ({pct:.1f}%){RESET}", end="\r", flush=True)

            if http_result:
                if status_filter and http_result["status"] not in status_filter:
                    continue
                merged = {**dns_result, **http_result}
                live.append(merged)
                print(" " * 70, end="\r")
                print_result(merged, verbose)

    elapsed = time.time() - start
    print(" " * 70, end="\r")
    print(f"\n  {GREEN}{len(live)} live web host(s){RESET} found in {elapsed:.1f}s\n")
    return live


# ── Output ─────────────────────────────────────────────────────────────────────
def write_output(resolved: list[dict], live: list[dict], path: str, domain: str) -> None:
    with open(path, "w") as fh:
        fh.write(f"# SubScout results for {domain}\n")
        fh.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        fh.write(f"# DNS resolved: {len(resolved)}   Live web hosts: {len(live)}\n\n")

        if live:
            fh.write("## Live Web Hosts\n")
            fh.write(f"{'Status':<8}{'Host':<45}{'Final URL'}\n")
            fh.write("-" * 100 + "\n")
            for r in sorted(live, key=lambda x: x["status"]):
                fh.write(f"{r['status']:<8}{r['fqdn']:<45}{r['url']}\n")
            fh.write("\n")

        fh.write("## All DNS-Resolved Subdomains\n")
        fh.write(f"{'Host':<45}{'IP Address(es)'}\n")
        fh.write("-" * 100 + "\n")
        for r in sorted(resolved, key=lambda x: x["fqdn"]):
            fh.write(f"{r['fqdn']:<45}{', '.join(r['ips'])}\n")

    print(f"{GREEN}Results saved to:{RESET} {path}")


# ── Main ────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="SubScout - Two-stage subdomain discovery (DNS resolution + HTTP probing)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 subscout.py -d example.com
  python3 subscout.py -d example.com -w wordlist.txt -t 100 -o results.txt
  python3 subscout.py -d example.com --dns-only
  python3 subscout.py -d example.com --filter 200,301 -v

Recommended wordlists:
  https://github.com/danielmiessler/SecLists  ->  Discovery/DNS/
        """,
    )
    parser.add_argument("-d", "--domain", required=True, help="Target domain (e.g. example.com)")
    parser.add_argument("-w", "--wordlist", default=None,
                         help="Path to subdomain wordlist (default: built-in ~130 common names)")
    parser.add_argument("-t", "--threads", type=int, default=50,
                         help="Threads for DNS resolution stage (default: 50)")
    parser.add_argument("--http-threads", type=int, default=20,
                         help="Threads for HTTP probing stage (default: 20)")
    parser.add_argument("-T", "--timeout", type=int, default=5,
                         help="HTTP request timeout in seconds (default: 5)")
    parser.add_argument("-o", "--output", default=None, help="Save results to this file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show redirect chains")
    parser.add_argument("--http-only", action="store_true",
                         help="Only try HTTP (skip HTTPS) during probing")
    parser.add_argument("--dns-only", action="store_true",
                         help="Skip HTTP probing entirely — DNS resolution only")
    parser.add_argument("--filter", type=str, default=None,
                         help="Only show specific HTTP status codes, comma-separated (e.g. 200,301)")
    args = parser.parse_args()

    if not args.dns_only and requests is None:
        sys.exit(
            "[ERROR] 'requests' is required for HTTP probing. Install with: pip install requests\n"
            "        Or pass --dns-only to skip the HTTP stage."
        )

    domain = args.domain.replace("https://", "").replace("http://", "").rstrip("/")
    wordlist = load_wordlist(args.wordlist) if args.wordlist else COMMON_SUBDOMAINS

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"  {CYAN}SubScout{RESET} — Subdomain Discovery")
    print(f"{BOLD}{'=' * 60}{RESET}")
    print(f"  Target   : {domain}")
    print(f"  Wordlist : {len(wordlist):,} entries" + ("" if args.wordlist else " (built-in)"))
    print(f"  Mode     : {'DNS only' if args.dns_only else 'DNS + HTTP probing'}")
    if args.threads > 200:
        print(f"  {YELLOW}Warning: {args.threads} DNS threads may exhaust OS resources or trigger rate limits{RESET}")

    status_filter = None
    if args.filter:
        try:
            status_filter = {int(c.strip()) for c in args.filter.split(",")}
        except ValueError:
            sys.exit("[ERROR] --filter must be comma-separated integers, e.g. 200,301")

    if requests is not None:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    protocols = ["http"] if args.http_only else ["https", "http"]

    resolved = dns_stage(domain, wordlist, args.threads)

    live = []
    if not resolved:
        print(f"{YELLOW}No subdomains resolved — nothing to probe.{RESET}")
    elif not args.dns_only:
        live = http_stage(resolved, args.http_threads, args.timeout, protocols, status_filter, args.verbose)

    print(f"{BOLD}{'=' * 60}{RESET}")
    print(f"  DNS resolved   : {len(resolved)}")
    if not args.dns_only:
        print(f"  Live web hosts : {len(live)}")
    print(f"{BOLD}{'=' * 60}{RESET}\n")

    if args.output:
        write_output(resolved, live, args.output, domain)

    if args.dns_only and resolved:
        print("Resolved subdomains:")
        for r in sorted(resolved, key=lambda x: x["fqdn"]):
            print(f"  {r['fqdn']:<45}{', '.join(r['ips'])}")


if __name__ == "__main__":
    main()
