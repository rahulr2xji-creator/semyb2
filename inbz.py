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


def new_impersonated_session():
    if curl_requests is None:
        raise RuntimeError("curl_cffi is not installed. Install with: pip install curl_cffi")
    session = curl_requests.Session(impersonate="chrome136")
    session.headers.update(HEADERS)
    return session


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


def extract_numeric_timer(html: str, default: float = 15.0) -> float:
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


def safe_json(response) -> dict:
    try:
        return response.json() if response.text else {}
    except Exception:
        return {}


def bypass_lnbz(url: str) -> str:
    """Bypass lnbz.la and return final URL."""
    alias = urlparse(url).path.strip("/")
    if not alias:
        raise ValueError("Invalid URL: no alias found")

    session = new_impersonated_session()

    # Step 1: Entry page
    entry = session.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
    soup = BeautifulSoup(entry.text, "html.parser")

    # Step 2: Follow article chain
    current = entry
    current_soup = soup

    for step_index in range(1, 6):
        # Check if we reached final form
        if current_soup.select_one("form#go-link"):
            break

        form = current_soup.select_one("form#go_d2") or current_soup.find("form")
        if not form:
            forms = current_soup.find_all("form")
            if forms:
                form = forms[0]
            else:
                raise ValueError(f"No form found at step {step_index}")

        action = urljoin(current.url, form.get("action", ""))
        hidden = extract_hidden_inputs(form)

        origin = f"{urlparse(current.url).scheme}://{urlparse(current.url).netloc}"
        current = session.post(
            action,
            data=hidden,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
            headers={"Origin": origin, "Referer": current.url},
        )
        current_soup = BeautifulSoup(current.text, "html.parser")

    # Step 3: Final form
    final_form = current_soup.select_one("form#go-link")
    if not final_form:
        raise ValueError("Final go-link form not found after article chain")

    hidden = extract_hidden_inputs(final_form)
    action = urljoin(current.url, final_form.get("action", "/links/go"))

    # Step 4: Wait for timer
    timer = extract_numeric_timer(current.text, default=15.0)
    wait_seconds = max(timer + 1.0, 16.0)
    time.sleep(wait_seconds)

    # Step 5: Submit final form
    submit = session.post(
        action,
        data=hidden,
        timeout=DEFAULT_TIMEOUT,
        headers={
            "Origin": "https://lnbz.la",
            "Referer": current.url,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        },
    )

    payload = safe_json(submit)
    final_url = clean_url(str(payload.get("url", "")))

    if payload.get("status") == "success" and final_url:
        return final_url

    raise ValueError(str(payload.get("message") or "Submit did not return success URL"))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python lnbz_api.py <lnbz_url>")
        sys.exit(1)
    try:
        result = bypass_lnbz(sys.argv[1])
        print(f"\nFinal Link: {result}")
    except Exception as e:
        print(f"\n[-] Error during bypass: {e}")
        sys.exit(1)