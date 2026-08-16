from __future__ import annotations

import json
import re
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

DEFAULT_TIMEOUT = 60
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def clean_url(value: str) -> str:
    if not value:
        return ""
    return value.strip().strip('"\'').rstrip('.,);]')


def extract_continue_hint(html: str) -> str | None:
    patterns = [
        r"https://themezon\.net/link\.php\?link=[A-Za-z0-9_-]+",
        r"link\.php\?link=([A-Za-z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            if pattern.startswith("https://"):
                return clean_url(match.group(0))
            return f"https://themezon.net/link.php?link={match.group(1)}"
    return None


def extract_hidden_inputs(root) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        inputs = root.find_all("input")
    except Exception:
        inputs = []
    for element in inputs:
        name = (element.get("name") or "").strip()
        if not name:
            continue
        value = element.get("value") or ""
        data[name] = value
    return data


def extract_numeric_timer(html: str, default: float = 12.0) -> float:
    patterns = [
        r'id=["\']timer["\'][^>]*>\s*(\d+(?:\.\d+)?)',
        r'class=["\'][^"\']*timer[^"\']*["\'][^>]*>\s*(\d+(?:\.\d+)?)',
        r'count\d*\s*=\s*(\d+(?:\.\d+)?)',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except Exception:
                continue
    return default


def new_impersonated_session():
    if curl_requests is None:
        raise RuntimeError("curl_cffi is not installed. Install with: pip install curl_cffi")
    session = curl_requests.Session(impersonate="chrome136")
    session.headers.update(HEADERS)
    return session


def resolve_themezon_article(continue_url: str, referer: str) -> str | None:
    session = new_impersonated_session()
    try:
        response = session.get(
            continue_url,
            headers={"Referer": referer},
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=False,
        )
    except Exception:
        return None

    if response.status_code == 302:
        location = response.headers.get("location", "")
        if "url=" in location:
            parsed = urlparse(location)
            target = re.search(r"url=([^&]+)", parsed.query)
            if target:
                return clean_url(target.group(1))
        return clean_url(location)

    if response.status_code == 200:
        redirect_match = re.search(
            r'window\.location\.href\s*=\s*"([^"]+)"',
            response.text,
            re.IGNORECASE,
        )
        if redirect_match:
            wrapped = clean_url(redirect_match.group(1))
            parsed = urlparse(wrapped)
            if "url=" in parsed.query:
                target = re.search(r"url=([^&]+)", parsed.query)
                if target:
                    return clean_url(target.group(1))
            return wrapped

    return None


def resolve_mrproblogger_final(alias: str, referer: str, wait_seconds: float) -> str | None:
    session = new_impersonated_session()
    mrproblogger_url = f"https://en.mrproblogger.com/{alias}"
    try:
        page = session.get(
            mrproblogger_url,
            headers={"Referer": referer},
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
    except Exception:
        return None

    soup = BeautifulSoup(page.text, "html.parser")
    timer = extract_numeric_timer(page.text, default=12.0)
    wait = max(wait_seconds, timer - 0.5)
    time.sleep(wait)

    form = soup.select_one("form#go-link")
    if not form:
        return None

    hidden = extract_hidden_inputs(form)
    action = urljoin(page.url, form.get("action") or "/links/go")

    try:
        submit = session.post(
            action,
            data=hidden,
            headers={
                "Referer": page.url,
                "Origin": f"{urlparse(page.url).scheme}://{urlparse(page.url).netloc}",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
    except Exception:
        return None

    try:
        payload = submit.json()
    except Exception:
        return None

    if isinstance(payload, dict) and payload.get("status") == "success":
        return clean_url(str(payload.get("url") or ""))

    return None


def bypass_shrinkme(url: str) -> str:
    """Bypass shrinkme.click and return final URL."""
    alias = urlparse(url).path.strip("/")
    if not alias:
        raise ValueError("Invalid shrinkme URL: no alias found")

    # Step 1: Direct MrProBlogger shortcut
    final = resolve_mrproblogger_final(
        alias=alias,
        referer="https://themezon.net/",
        wait_seconds=11.6,
    )
    if final:
        return final

    # Step 2: Load shrinkme entry
    session = new_impersonated_session()
    entry = session.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True)

    continue_hint = extract_continue_hint(entry.text)
    if not continue_hint:
        raise ValueError("No continue hint found in entry page")

    # Step 3: Resolve ThemeZon article
    article_url = resolve_themezon_article(continue_hint, url)
    if not article_url:
        raise ValueError("Failed to resolve ThemeZon article")

    # Step 4: Final MrProBlogger
    final = resolve_mrproblogger_final(
        alias=alias,
        referer=article_url,
        wait_seconds=12.0,
    )
    if final:
        return final

    raise ValueError("MrProBlogger final submit did not return a downstream URL")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python shrinkme_api.py <shrinkme_url>")
        sys.exit(1)
    try:
        result = bypass_shrinkme(sys.argv[1])
        print(f"\nFinal Link: {result}")
    except Exception as e:
        print(f"\n[-] Error during bypass: {e}")
        sys.exit(1)