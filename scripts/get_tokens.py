#!/usr/bin/env python3
"""
Fetch XSRF token and cookies for an onlinepraxistermine.de portal by visiting the iframe page.

Usage examples:
  # Print shell exports (default)
  python3 scripts/get_tokens.py --portal S55299BD3

  # Export to current shell
  eval "$(python3 scripts/get_tokens.py --portal S55299BD3)"

  # JSON output
  python3 scripts/get_tokens.py --portal S55299BD3 --format json
"""
import argparse
import sys
import ssl
import json
from urllib.parse import unquote, urlparse

try:
    import requests  # type: ignore
except Exception:
    requests = None

import urllib.request
import urllib.error
from urllib.request import HTTPCookieProcessor, build_opener
import http.cookiejar as cookiejar
import warnings


def cookie_header_from_jar(jar: "cookiejar.CookieJar") -> str:
    parts = []
    names = set()
    for c in jar:
        parts.append(f"{c.name}={c.value}")
        names.add(c.name)
    if "cookieConsent" not in names:
        parts.append("cookieConsent=true")
    return "; ".join(parts)


def fetch_tokens(host: str, portal: str, iframe_prefix: str = "/iframe", insecure: bool = False):
    iframe_url = f"{host.rstrip('/')}{iframe_prefix}/{portal}"

    # Try requests first
    if requests is not None:
        try:
            if insecure:
                try:
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # type: ignore[attr-defined]
                except Exception:
                    pass
            s = requests.Session()
            s.cookies.set("cookieConsent", "true")
            r = s.get(iframe_url, timeout=15, verify=not insecure)
            r.raise_for_status()
            xsrf = s.cookies.get("XSRF-TOKEN")
            xsrf_val = unquote(xsrf) if xsrf else None
            cookie_header = cookie_header_from_jar(s.cookies)
            return xsrf_val, cookie_header
        except Exception:
            # fall through to urllib
            pass

    # Fallback: urllib
    cj = cookiejar.CookieJar()
    handlers = [HTTPCookieProcessor(cj)]
    try:
        handlers.append(urllib.request.HTTPSHandler(context=ssl._create_unverified_context() if insecure else None))  # type: ignore[attr-defined]
    except Exception:
        pass
    opener = build_opener(*handlers)

    # pre-seed cookieConsent
    try:
        parsed = urlparse(host)
        cj.set_cookie(cookiejar.Cookie(
            version=0,
            name="cookieConsent",
            value="true",
            port=None,
            port_specified=False,
            domain=parsed.hostname or "onlinepraxistermine.de",
            domain_specified=False,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=True,
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={},
            rfc2109=False,
        ))
    except Exception:
        pass

    req = urllib.request.Request(iframe_url, method="GET", headers={"Accept": "text/html,application/xhtml+xml"})
    with opener.open(req, timeout=15) as _:
        pass
    xsrf_val = None
    for c in cj:
        if c.name == "XSRF-TOKEN":
            xsrf_val = unquote(c.value)
            break
    cookie_header = cookie_header_from_jar(cj)
    return xsrf_val, cookie_header


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch XSRF token and cookies for a portal")
    ap.add_argument("--host", default="https://onlinepraxistermine.de", help="Base host")
    ap.add_argument("--portal", default="S55299BD3", help="Portal code")
    ap.add_argument("--iframe-prefix", default="/iframe", help="Iframe prefix for bootstrap")
    ap.add_argument("--format", choices=["shell", "json"], default="shell", help="Output format")
    ap.add_argument("--insecure", action="store_true", help="Disable TLS verification (testing only)")
    ns = ap.parse_args(argv)

    try:
        xsrf, cookie = fetch_tokens(ns.host, ns.portal, ns.iframe_prefix, ns.insecure)
    except Exception as e:
        sys.stderr.write(f"Error fetching tokens: {e}\n")
        return 1

    if ns.format == "json":
        print(json.dumps({"xsrf_token": xsrf, "cookie": cookie}, indent=2))
    else:
        # shell-compatible export lines
        print(f"export TERMIN_XSRF_TOKEN='{xsrf or ''}'")
        print(f"export TERMIN_COOKIE='{cookie or ''}'")
        print("# use with: termin-ator ... --xsrf \"$TERMIN_XSRF_TOKEN\" --cookie \"$TERMIN_COOKIE\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
