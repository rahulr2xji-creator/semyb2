"""Render-ready FastAPI service for resolving short links."""
from __future__ import annotations

import asyncio
import os
import re
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

# ============================================
# IMPORT YOUR BYPASS FUNCTIONS
# ============================================

from earnlinks import bypass_earnlinks
from shrink import bypass_shrinkme
from sfl import bypass_sfl

# Try both possible names for lnbz
try:
    from lnbz import bypass_lnbz
except ImportError:
    try:
        from inbz import bypass_lnbz
    except ImportError:
        bypass_lnbz = None
        print("⚠️ WARNING: lnbz/inbz module not found")

# ============================================
# CONFIGURATION
# ============================================

TIMEOUT = int(os.getenv("BYPASS_TIMEOUT", "420"))
SYNC_BUDGET = float(os.getenv("SYNC_BUDGET", "20"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))

# ============================================
# API EXPIRY CONFIGURATION
# ============================================

KOLKATA_TZ = timezone(timedelta(hours=5, minutes=30))
API_CREATION_DATE = datetime(2026, 8, 16, 0, 0, 0, tzinfo=KOLKATA_TZ)
API_EXPIRY_DAYS = 3

# ============================================
# DAILY LIMIT CONFIGURATION
# ============================================

DAILY_LIMIT = 100
RESET_HOUR = 0
RESET_MINUTE = 5


def is_api_expired() -> bool:
    now = datetime.now(KOLKATA_TZ)
    expiry_date = API_CREATION_DATE + timedelta(days=API_EXPIRY_DAYS)
    return now > expiry_date


def get_expiry_date() -> str:
    expiry = API_CREATION_DATE + timedelta(days=API_EXPIRY_DAYS)
    return expiry.strftime("%d %B %Y, %I:%M %p IST")


def get_creation_date() -> str:
    return API_CREATION_DATE.strftime("%d %B %Y, %I:%M %p IST")


def get_reset_time() -> datetime:
    now = datetime.now(KOLKATA_TZ)
    reset = now.replace(hour=RESET_HOUR, minute=RESET_MINUTE, second=0, microsecond=0)
    if now >= reset:
        reset += timedelta(days=1)
    return reset


def get_remaining_requests() -> int:
    today = datetime.now(KOLKATA_TZ).date()
    key = f"count_{today.isoformat()}"
    count = REQUEST_COUNTS.get(key, 0)
    return max(0, DAILY_LIMIT - count)


def increment_request_count() -> int:
    today = datetime.now(KOLKATA_TZ).date()
    key = f"count_{today.isoformat()}"
    REQUEST_COUNTS[key] = REQUEST_COUNTS.get(key, 0) + 1
    return REQUEST_COUNTS[key]


def is_daily_limit_reached() -> bool:
    return get_remaining_requests() <= 0


REQUEST_COUNTS: dict[str, int] = {}

# ============================================
# SUPPORTED SHORTLINK FAMILIES
# ============================================

SUPPORTED_FAMILIES = {
    "earnlinks": {
        "domains": ["earnlinks.in"],
        "patterns": [r"earnlinks\.in"],
        "handler": bypass_earnlinks,
        "sample": "https://earnlinks.in/xyz123"
    },
    "shrinkme": {
        "domains": ["shrinkme.click", "shrinke.me"],
        "patterns": [r"shrinkme\.click", r"shrinke\.me"],
        "handler": bypass_shrinkme,
        "sample": "https://shrinkme.click/ZTvkQYPJ"
    },
    "sfl": {
        "domains": ["sfl.gl"],
        "patterns": [r"sfl\.gl"],
        "handler": bypass_sfl,
        "sample": "https://sfl.gl/18PZXXI9"
    },
}

if bypass_lnbz:
    SUPPORTED_FAMILIES["lnbz"] = {
        "domains": ["lnbz.la"],
        "patterns": [r"lnbz\.la"],
        "handler": bypass_lnbz,
        "sample": "https://lnbz.la/Hmvp6"
    }


def detect_family(url: str) -> str | None:
    url_lower = url.lower()
    for family, info in SUPPORTED_FAMILIES.items():
        for pattern in info["patterns"]:
            if re.search(pattern, url_lower):
                return family
    return None


def get_supported_list() -> list[dict]:
    return [
        {
            "family": family,
            "domains": info["domains"],
            "example": info["sample"]
        }
        for family, info in SUPPORTED_FAMILIES.items()
    ]


# ============================================
# EXPIRED PAGE HTML
# ============================================

EXPIRED_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Expired</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e, #16213e, #0f3460);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
            color: #fff;
        }
        .container {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(20px);
            border-radius: 30px;
            padding: 60px 50px;
            max-width: 550px;
            width: 100%;
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 25px 50px rgba(0, 0, 0, 0.5);
            animation: fadeIn 0.8s ease-out;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .icon { font-size: 80px; margin-bottom: 20px; display: block; animation: pulse 2s infinite; }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }
        h1 {
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 15px;
            background: linear-gradient(135deg, #f093fb, #f5576c);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .subtitle {
            font-size: 16px;
            color: rgba(255, 255, 255, 0.7);
            margin-bottom: 30px;
            line-height: 1.6;
        }
        .expiry-card {
            background: rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 20px;
            margin: 25px 0;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .expiry-card .label {
            font-size: 13px;
            color: rgba(255, 255, 255, 0.5);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }
        .expiry-card .date {
            font-size: 18px;
            font-weight: 600;
            color: #ff6b6b;
        }
        .expiry-card .days {
            font-size: 14px;
            color: rgba(255, 255, 255, 0.6);
            margin-top: 5px;
        }
        .btn {
            display: inline-block;
            padding: 16px 40px;
            background: linear-gradient(135deg, #f093fb, #f5576c);
            color: #fff;
            text-decoration: none;
            border-radius: 50px;
            font-weight: 600;
            font-size: 18px;
            transition: all 0.3s ease;
            box-shadow: 0 10px 30px rgba(245, 87, 108, 0.3);
            border: none;
            cursor: pointer;
            margin-top: 10px;
        }
        .btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 40px rgba(245, 87, 108, 0.5);
        }
        .footer {
            margin-top: 30px;
            font-size: 13px;
            color: rgba(255, 255, 255, 0.3);
        }
        .status-badge {
            display: inline-block;
            padding: 6px 16px;
            background: rgba(255, 107, 107, 0.2);
            border: 1px solid rgba(255, 107, 107, 0.3);
            border-radius: 20px;
            font-size: 13px;
            color: #ff6b6b;
            margin-bottom: 15px;
        }
        @media (max-width: 480px) {
            .container { padding: 40px 25px; }
            h1 { font-size: 26px; }
            .btn { padding: 14px 30px; font-size: 16px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <span class="icon">⏰</span>
        <div class="status-badge">⚠️ API EXPIRED</div>
        <h1>API Has Expired</h1>
        <p class="subtitle">
            This API is no longer active.<br>
            Please get a new API key to continue using the service.
        </p>
        <div class="expiry-card">
            <div class="label">📅 Expired On</div>
            <div class="date">{expiry_date}</div>
            <div class="days">This API was valid for {expiry_days} days</div>
        </div>
        <a href="https://t.me/+PEvs6Jg6JXthN2U9" target="_blank" class="btn">🚀 GET NEW API</a>
        <div class="footer">
            <p>Join our Telegram channel for latest updates</p>
            <p style="margin-top:5px;font-size:11px;color:rgba(255,255,255,0.2);">
                Created: {creation_date}
            </p>
        </div>
    </div>
</body>
</html>
"""

# ============================================
# FASTAPI APP
# ============================================

app = FastAPI(title="Bypass API", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS: dict[str, dict] = {}
RESULT_CACHE: dict[str, dict] = {}
ACTIVE_JOBS: dict[str, str] = {}
LOCK = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENCY", "2")))


def _normalize(value: str) -> str:
    value = value.strip().strip("\"'")
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value


def _payload(job_id: str) -> dict:
    job = JOBS[job_id]
    result = {
        "success": job.get("success", False),
        "status": job.get("status", "running"),
        "source": job["source"],
        "family": job.get("family"),
        "job_id": job_id,
        "took": round(time.time() - job["started"], 1),
        "developer": "semy",
    }
    for key in ("bypassed", "error"):
        if key in job:
            result[key] = job[key]
    if result["status"] == "running":
        result["pending"] = True
        result["poll"] = f"/job?id={job_id}"
    return result


async def _worker(job_id: str, source: str, family: str, handler):
    job = JOBS[job_id]
    try:
        async with LOCK:
            if asyncio.iscoroutinefunction(handler):
                destination = await asyncio.wait_for(handler(source), timeout=TIMEOUT)
            else:
                destination = await asyncio.wait_for(
                    asyncio.to_thread(handler, source),
                    timeout=TIMEOUT
                )
        job.update(status="done", success=True, bypassed=destination)
        RESULT_CACHE[source] = {"bypassed": destination, "stored": time.time()}
    except asyncio.TimeoutError:
        job.update(status="error", success=False, error="Bypass timed out")
    except Exception as error:
        traceback.print_exc()
        job.update(
            status="error",
            success=False,
            error=f"{type(error).__name__}: {error}",
        )
    finally:
        job["took"] = round(time.time() - job["started"], 1)
        ACTIVE_JOBS.pop(source, None)


async def _start(source: str, family: str, handler):
    cached = RESULT_CACHE.get(source)
    if cached and time.time() - cached["stored"] <= CACHE_TTL:
        return {
            "success": True,
            "status": "done",
            "source": source,
            "family": family,
            "took": 0,
            "bypassed": cached["bypassed"],
            "cached": True,
            "developer": "semy",
        }

    active = ACTIVE_JOBS.get(source)
    if active and JOBS.get(active, {}).get("status") == "running":
        return _payload(active)

    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "source": source,
        "family": family,
        "started": time.time(),
        "status": "running",
        "success": False,
    }
    ACTIVE_JOBS[source] = job_id
    task = asyncio.create_task(_worker(job_id, source, family, handler))
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=SYNC_BUDGET)
    except asyncio.TimeoutError:
        pass
    return _payload(job_id)


# ============================================
# ✅ ONLY ENDPOINT: /semybypass
# ============================================

@app.get("/semybypass")
async def semybypass(url: str = Query(None, description="Shortlink URL to bypass")):
    
    # 1️⃣ CHECK: API EXPIRED → HTML PAGE
    if is_api_expired():
        return HTMLResponse(
            EXPIRED_PAGE.format(
                expiry_date=get_expiry_date(),
                expiry_days=API_EXPIRY_DAYS,
                creation_date=get_creation_date(),
            ),
            status_code=403,
        )

    # 2️⃣ CHECK: NO URL → JSON with supported links
    if not url:
        return JSONResponse({
            "success": False,
            "error": "Missing 'url' parameter",
            "example": "/semybypass?url=https://shrinkme.click/ZTvkQYPJ",
            "supported_links": get_supported_list(),
            "daily_remaining": get_remaining_requests(),
            "daily_limit": DAILY_LIMIT,
            "resets_at": get_reset_time().strftime("%I:%M %p IST"),
            "expires_on": get_expiry_date(),
            "developer": "semy",
        })

    # 3️⃣ CHECK: SUPPORTED LINK?
    normalized_url = _normalize(url)
    family = detect_family(normalized_url)
    
    if not family:
        return JSONResponse({
            "success": False,
            "error": "Link not supported",
            "input_url": normalized_url,
            "supported_families": list(SUPPORTED_FAMILIES.keys()),
            "supported_domains": [d for info in SUPPORTED_FAMILIES.values() for d in info["domains"]],
            "developer": "semy",
        }, status_code=400)

    # 4️⃣ CHECK: DAILY LIMIT REACHED → JSON
    if is_daily_limit_reached():
        return JSONResponse({
            "success": False,
            "error": "Daily limit reached",
            "daily_limit": DAILY_LIMIT,
            "resets_at": get_reset_time().strftime("%I:%M %p IST"),
            "remaining": 0,
            "developer": "semy",
        }, status_code=429)

    # 5️⃣ PROCESS: Increment & Bypass
    increment_request_count()
    handler = SUPPORTED_FAMILIES[family]["handler"]
    result = await _start(normalized_url, family, handler)
    return JSONResponse(result)


# ============================================
# RUN
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
