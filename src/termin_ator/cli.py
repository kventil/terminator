import argparse
import json
import os
import sys
from dataclasses import dataclass
import ssl
from typing import Dict, Any, Optional

# Optional dependency; we fall back to stdlib if missing
try:  # pragma: no cover
    import requests  # type: ignore
except Exception:
    requests = None
import urllib.request
import urllib.error
import http.cookiejar as cookiejar
from urllib.parse import urlencode, unquote, urlparse
from urllib.request import HTTPCookieProcessor, build_opener
import warnings


DEFAULT_HOST = "https://onlinepraxistermine.de"
DEFAULT_IFRAME_PREFIX = ""
BOOTSTRAP_IFRAME_PREFIX = "/iframe"
DEFAULT_PORTAL = "S55299BD3"


@dataclass
class ClientConfig:
    host: str = DEFAULT_HOST
    iframe_prefix: str = DEFAULT_IFRAME_PREFIX
    portal: str = DEFAULT_PORTAL
    cookie: Optional[str] = None
    xsrf_token: Optional[str] = None
    insecure: bool = False
    auto_auth: bool = True

    def base_url(self) -> str:
        return f"{self.host}{self.iframe_prefix}/{self.portal}"

    def headers(self) -> Dict[str, str]:
        hdrs: Dict[str, str] = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "termin-ator-cli/0.1",
        }
        if self.xsrf_token:
            hdrs["X-XSRF-TOKEN"] = self.xsrf_token
        if self.cookie:
            hdrs["Cookie"] = self.cookie
        return hdrs


def http_get(url: str, headers: Dict[str, str], params: Dict[str, Any], insecure: bool = False) -> Any:
    if requests is not None:
        if insecure:
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # type: ignore[attr-defined]
            except Exception:
                pass
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30, verify=not insecure)
        except Exception as e:
            # Retry once with verify disabled if cert errors occur
            if not insecure and "CERTIFICATE_VERIFY_FAILED" in str(e):
                try:
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # type: ignore[attr-defined]
                except Exception:
                    pass
                resp = requests.get(url, headers=headers, params=params, timeout=30, verify=False)
            else:
                raise
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        return resp.json() if "json" in ct else resp.text
    # stdlib fallback
    full_url = url + ("?" + urlencode(params) if params else "")
    req = urllib.request.Request(full_url, method="GET", headers=headers)
    try:
        context = ssl._create_unverified_context() if insecure else None  # type: ignore[attr-defined]
        with urllib.request.urlopen(req, timeout=30, context=context) as r:  # nosec B310
            data = r.read()
            ct = r.headers.get("content-type", "")
            if "json" in ct:
                return json.loads(data.decode("utf-8"))
            return data.decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} for GET {full_url}: {e.read().decode('utf-8', 'ignore')}")
    except urllib.error.URLError as e:
        if not insecure and "CERTIFICATE_VERIFY_FAILED" in str(getattr(e, "reason", e)):
            context = ssl._create_unverified_context()  # type: ignore[attr-defined]
            with urllib.request.urlopen(req, timeout=30, context=context) as r:  # nosec B310
                data = r.read()
                ct = r.headers.get("content-type", "")
                if "json" in ct:
                    return json.loads(data.decode("utf-8"))
                return data.decode("utf-8")
        raise


def http_post(url: str, headers: Dict[str, str], json_body: Dict[str, Any], insecure: bool = False) -> Any:
    if requests is not None:
        if insecure:
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # type: ignore[attr-defined]
            except Exception:
                pass
        try:
            resp = requests.post(url, headers=headers, json=json_body, timeout=30, verify=not insecure)
        except Exception as e:
            if not insecure and "CERTIFICATE_VERIFY_FAILED" in str(e):
                try:
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # type: ignore[attr-defined]
                except Exception:
                    pass
                resp = requests.post(url, headers=headers, json=json_body, timeout=30, verify=False)
            else:
                raise
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        return resp.json() if "json" in ct else resp.text
    # stdlib fallback
    body_bytes = json.dumps(json_body).encode("utf-8")
    hdrs = {"Content-Type": "application/json", **headers}
    req = urllib.request.Request(url, method="POST", headers=hdrs, data=body_bytes)
    try:
        context = ssl._create_unverified_context() if insecure else None  # type: ignore[attr-defined]
        with urllib.request.urlopen(req, timeout=30, context=context) as r:  # nosec B310
            data = r.read()
            ct = r.headers.get("content-type", "")
            if "json" in ct:
                return json.loads(data.decode("utf-8"))
            return data.decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} for POST {url}: {e.read().decode('utf-8', 'ignore')}")
    except urllib.error.URLError as e:
        if not insecure and "CERTIFICATE_VERIFY_FAILED" in str(getattr(e, "reason", e)):
            context = ssl._create_unverified_context()  # type: ignore[attr-defined]
            with urllib.request.urlopen(req, timeout=30, context=context) as r:  # nosec B310
                data = r.read()
                ct = r.headers.get("content-type", "")
                if "json" in ct:
                    return json.loads(data.decode("utf-8"))
                return data.decode("utf-8")
        raise


def _cookie_header_from_jar(jar: "cookiejar.CookieJar") -> str:
    parts = []
    names = set()
    for c in jar:
        parts.append(f"{c.name}={c.value}")
        names.add(c.name)
    if "cookieConsent" not in names:
        parts.append("cookieConsent=true")
    return "; ".join(parts)


def ensure_tokens(cfg: ClientConfig) -> None:
    """Populate cfg.cookie and cfg.xsrf_token if missing by visiting the iframe HTML page."""
    if not cfg.auto_auth:
        return
    if cfg.cookie and cfg.xsrf_token:
        return
    iframe_url = f"{cfg.host}{BOOTSTRAP_IFRAME_PREFIX}/{cfg.portal}"

    # Try via requests session for simplicity
    if requests is not None:
        try:
            if cfg.insecure:
                try:
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # type: ignore[attr-defined]
                except Exception:
                    pass
            s = requests.Session()
            s.cookies.set("cookieConsent", "true")
            r = s.get(iframe_url, timeout=15, verify=not cfg.insecure)
            r.raise_for_status()
            xsrf = s.cookies.get("XSRF-TOKEN")
            if xsrf:
                cfg.xsrf_token = unquote(xsrf)
            cfg.cookie = _cookie_header_from_jar(s.cookies)
            return
        except Exception:
            pass

    # Fallback: urllib with CookieJar
    cj = cookiejar.CookieJar()
    handlers = [HTTPCookieProcessor(cj)]
    try:
        handlers.append(urllib.request.HTTPSHandler(context=ssl._create_unverified_context() if cfg.insecure else None))  # type: ignore[attr-defined]
    except Exception:
        pass
    opener = build_opener(*handlers)
    # Pre-seed cookieConsent
    try:
        cj.set_cookie(cookiejar.Cookie(
            version=0,
            name="cookieConsent",
            value="true",
            port=None,
            port_specified=False,
            domain=urlparse(cfg.host).hostname or "onlinepraxistermine.de",
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
    try:
        with opener.open(req, timeout=15) as _:
            pass
        xsrf = None
        for c in cj:
            if c.name == "XSRF-TOKEN":
                xsrf = c.value
                break
        if xsrf:
            cfg.xsrf_token = unquote(xsrf)
        cfg.cookie = _cookie_header_from_jar(cj)
    except Exception as e:
        msg = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in msg:
            reason = "CERTIFICATE_VERIFY_FAILED"
        elif "self signed" in msg or "self-signed" in msg:
            reason = "SELF_SIGNED_CERT"
        else:
            reason = "bootstrap error"
        # Short, single-line info to stderr so it won't interfere with stdout
        sys.stderr.write(
            f"[info] auto-auth skipped ({reason}); continuing without tokens. "
            f"Use --insecure or provide --cookie/--xsrf if needed.\n"
        )


def cmd_dates(cfg: ClientConfig, args: argparse.Namespace) -> int:
    url = f"{cfg.base_url()}/dates"
    params = {
        "v": args.v,
        "doctor": args.doctor,
        "insurance": args.insurance,
        "visitreason": args.visitreason,
    }
    if args.dry_run:
        print(json.dumps({"method": "GET", "url": url, "params": params, "headers": cfg.headers()}, indent=2))
        return 0
    ensure_tokens(cfg)
    data = http_get(url, headers=cfg.headers(), params=params, insecure=cfg.insecure)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def cmd_doctors(cfg: ClientConfig, args: argparse.Namespace) -> int:
    url = f"{cfg.host}/{cfg.portal}/doctors"
    if args.dry_run:
        print(json.dumps({"method": "GET", "url": url, "headers": cfg.headers()}, indent=2))
        return 0
    ensure_tokens(cfg)
    data = http_get(url, headers=cfg.headers(), params={}, insecure=cfg.insecure)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def cmd_availability(cfg: ClientConfig, args: argparse.Namespace) -> int:
    # List available dates per doctor
    docs_url = f"{cfg.host}/{cfg.portal}/doctors"
    if args.dry_run:
        print(json.dumps({"method": "GET", "url": docs_url, "headers": cfg.headers()}, indent=2))
        return 0
    ensure_tokens(cfg)
    docs = http_get(docs_url, headers=cfg.headers(), params={}, insecure=cfg.insecure)
    if isinstance(docs, str):
        docs = json.loads(docs)
    results = []
    for d in docs:
        doc_id = d.get("doc_id")
        name = d.get("name")
        params = {
            "v": args.v,
            "doctor": doc_id,
            "insurance": args.insurance,
            "visitreason": args.visitreason,
        }
        dates = http_get(f"{cfg.host}/{cfg.portal}/dates", headers=cfg.headers(), params=params, insecure=cfg.insecure)
        results.append({"doctor": doc_id, "name": name, "dates": dates})
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


def cmd_confirm(cfg: ClientConfig, args: argparse.Namespace) -> int:
    url = f"{cfg.base_url()}/booking-is-confirmed"
    body = {"appointment_id": args.appointment_id}
    if args.dry_run:
        print(json.dumps({"method": "POST", "url": url, "json": body, "headers": cfg.headers()}, indent=2))
        return 0
    ensure_tokens(cfg)
    data = http_post(url, headers=cfg.headers(), json_body=body, insecure=cfg.insecure)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="termin-ator",
        description="CLI for onlinepraxistermine.de portals (fetch dates, confirm bookings)",
    )
    p.add_argument("--host", default=os.getenv("TERMIN_HOST", DEFAULT_HOST), help=f"API host (default: {DEFAULT_HOST})")
    p.add_argument("--iframe-prefix", default=os.getenv("TERMIN_IFRAME_PREFIX", DEFAULT_IFRAME_PREFIX), help=f"Path prefix (default: {DEFAULT_IFRAME_PREFIX})")
    p.add_argument("--portal", default=os.getenv("TERMIN_PORTAL", DEFAULT_PORTAL), help="Portal code (e.g., S55299BD3)")
    p.add_argument("--cookie", default=os.getenv("TERMIN_COOKIE"), help="Cookie header value (including XSRF-TOKEN and session)")
    p.add_argument("--xsrf", default=os.getenv("TERMIN_XSRF_TOKEN"), help="X-XSRF-TOKEN header value")
    p.add_argument("--dry-run", action="store_true", help="Print request without sending")
    p.add_argument("--insecure", action="store_true", help="Disable TLS verification (only for testing)")
    p.add_argument("--no-auto-auth", dest="auto_auth", action="store_false", help="Disable automatic cookie/XSRF bootstrap")
    p.set_defaults(auto_auth=True)

    sub = p.add_subparsers(dest="cmd", required=False)

    sp_dates = sub.add_parser("dates", help="Fetch available dates")
    sp_dates.add_argument("--v", default="2", help="API version parameter")
    sp_dates.add_argument("--doctor", default="USER-1-DOC-1", help="Doctor id")
    sp_dates.add_argument("--insurance", default="Gesetzlich", help="Insurance type")
    sp_dates.add_argument("--visitreason", default="Spezial", help="Visit reason")
    sp_dates.set_defaults(func=cmd_dates)

    sp_doctors = sub.add_parser("doctors", help="List doctors in the portal")
    sp_doctors.set_defaults(func=cmd_doctors)

    sp_avail = sub.add_parser("availability", help="List available dates per doctor")
    sp_avail.add_argument("--v", default="2", help="API version parameter")
    sp_avail.add_argument("--insurance", default="Gesetzlich", help="Insurance type")
    sp_avail.add_argument("--visitreason", default="Spezial", help="Visit reason")
    sp_avail.set_defaults(func=cmd_availability)

    sp_confirm = sub.add_parser("confirm", help="Confirm a booking for an appointment id")
    sp_confirm.add_argument("appointment_id", type=int, help="Appointment id to confirm")
    sp_confirm.set_defaults(func=cmd_confirm)

    # Default to availability when no subcommand is provided
    p.set_defaults(func=cmd_availability, cmd="availability", v="2", insurance="Gesetzlich", visitreason="Spezial")

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    cfg = ClientConfig(
        host=ns.host,
        iframe_prefix=ns.iframe_prefix,
        portal=ns.portal,
        cookie=ns.cookie,
        xsrf_token=ns.xsrf,
        insecure=ns.insecure,
        auto_auth=ns.auto_auth,
    )
    try:
        return ns.func(cfg, ns)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
