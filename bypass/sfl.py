from __future__ import annotations

import json
import re
import sys
import time
import uuid
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


def new_impersonated_session():
    if curl_requests is None:
        raise RuntimeError("curl_cffi is not installed. Install with: pip install curl_cffi")
    session = curl_requests.Session(impersonate="chrome136")
    session.headers.update(HEADERS)
    return session


def safe_json(response) -> dict:
    try:
        return response.json() if response.text else {}
    except Exception:
        return {}


def extract_sfl_ready_target(html: str) -> str | None:
    patterns = [
        r'window\.location\.href\s*=\s*["\']([^"\']+)["\']',
        r'location\.href\s*=\s*["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            value = match.group(1).replace("\\/", "/")
            if value.startswith("http://") or value.startswith("https://"):
                return clean_url(value)
    return None


def is_cloudflare_block(response) -> bool:
    text = response.text.lower()
    server = str(response.headers.get("server", "")).lower()
    title = ""
    soup = BeautifulSoup(response.text, "html.parser")
    if soup.title and soup.title.string:
        title = soup.title.string.lower()
    return (
        response.status_code in {403, 429}
        and "cloudflare" in (server + title + text)
    )


def bypass_sfl(url: str) -> str:
    """Bypass sfl.gl and return final URL."""
    session = new_impersonated_session()

    # Step 1: Entry with impersonation
    entry = session.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True)

    if is_cloudflare_block(entry):
        # Try WARP proxy fallback
        proxy = {"http": "http://127.0.0.1:40000", "https": "http://127.0.0.1:40000"}
        proxy_session = new_impersonated_session()
        try:
            proxy_session.proxies = proxy
        except Exception:
            pass
        proxy_entry = proxy_session.get(
            url,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
            proxies=proxy,
        )
        if is_cloudflare_block(proxy_entry):
            raise ValueError("Cloudflare blocking all egress paths")
        session = proxy_session
        entry = proxy_entry

    soup = BeautifulSoup(entry.text, "html.parser")

    # Step 2: Find form
    form = soup.find("form")
    if not form:
        raise ValueError("Entry form not found")

    action = urljoin(entry.url, form.get("action", ""))
    hidden = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if name:
            hidden[name] = inp.get("value", "")

    # Step 3: Redirect to article
    redirect_url = f"{action}?{requests.compat.urlencode(hidden)}"
    redirect_response = session.get(
        redirect_url,
        timeout=DEFAULT_TIMEOUT,
        allow_redirects=False,
        headers={"Referer": entry.url},
    )

    article_url = redirect_response.headers.get("location", "")
    if not article_url:
        article_url = redirect_response.url
    article_url = urljoin(action, article_url)

    if not article_url or "khaddavi" not in article_url:
        raise ValueError("No article URL found")

    # Step 4: Load article
    article = session.get(
        article_url,
        timeout=DEFAULT_TIMEOUT,
        allow_redirects=True,
        headers={"Referer": redirect_url},
    )

    # Step 5: API session
    app_base = f"{urlparse(article.url).scheme}://{urlparse(article.url).netloc}"
    api_headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": app_base,
        "Referer": article.url,
    }

    session_resp = session.post(
        f"{app_base}/api/session",
        json={},
        headers=api_headers,
        timeout=DEFAULT_TIMEOUT,
    )
    session_payload = safe_json(session_resp)

    wait_seconds = 10 if int(session_payload.get("step") or 1) == 1 else 3
    time.sleep(wait_seconds)

    # Step 6: Verify
    verify_response = session.post(
        f"{app_base}/api/verify",
        json={"_a": True, "captcha": None, "passcode": None},
        headers={
            **api_headers,
            "Idempotency-Key": str(uuid.uuid4()),
        },
        timeout=DEFAULT_TIMEOUT,
    )

    # Step 7: Go
    go_response = session.post(
        f"{app_base}/api/go",
        json={"key": hidden.get("alias"), "size": 0, "_dvc": "desktop"},
        headers={
            **api_headers,
            "Idempotency-Key": str(uuid.uuid4()),
        },
        timeout=DEFAULT_TIMEOUT,
    )
    go_payload = safe_json(go_response)

    ready_url = go_payload.get("url")
    if not ready_url:
        raise ValueError("Ready URL not found in API response")

    # Step 8: Ready page
    ready = session.get(
        ready_url,
        timeout=DEFAULT_TIMEOUT,
        allow_redirects=True,
        headers={"Referer": article.url},
    )

    final_url = extract_sfl_ready_target(ready.text)
    if final_url:
        return final_url

    raise ValueError("Ready page did not contain final URL")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sfl_api.py <sfl_url>")
        sys.exit(1)
    try:
        result = bypass_sfl(sys.argv[1])
        print(f"\nFinal Link: {result}")
    except Exception as e:
        print(f"\n[-] Error during bypass: {e}")
        sys.exit(1)