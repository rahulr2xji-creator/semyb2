# main.py
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict
from cachetools import TTLCache
import pytz

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import bypass functions from existing files
from lnbz import bypass_lnbz
from sfl import bypass_sfl
from shrinkme import bypass_shrinkme

# ============================================
# CONFIGURATION
# ============================================
KOLKATA_TZ = pytz.timezone('Asia/Kolkata')
DAILY_LIMIT = 100  # 100 requests per day

API_CREATION_DATE = datetime(2026, 8, 16, 0, 0, 0, tzinfo=KOLKATA_TZ)
API_EXPIRY_DAYS = 3  # 7 days validity

DEFAULT_TIMEOUT = 30  # 30 second timeout
CACHE_TTL = 120  # 2 minutes cache

# ============================================
# API EXPIRATION FUNCTIONS
# ============================================
def is_api_expired() -> bool:
    """Check if API has expired based on creation date + 7 days"""
    now = datetime.now(KOLKATA_TZ)
    expiry_date = API_CREATION_DATE + timedelta(days=API_EXPIRY_DAYS)
    return now > expiry_date

def get_expiry_date() -> str:
    """Get formatted expiry date"""
    expiry = API_CREATION_DATE + timedelta(days=API_EXPIRY_DAYS)
    return expiry.strftime("%d %B %Y, %I:%M %p IST")

def get_remaining_days() -> int:
    """Get remaining days until expiry"""
    now = datetime.now(KOLKATA_TZ)
    expiry = API_CREATION_DATE + timedelta(days=API_EXPIRY_DAYS)
    remaining = expiry - now
    return max(0, remaining.days)

# ============================================
# HTML TEMPLATE - ONLY FOR EXPIRED PAGE (ROOT)
# ============================================
EXPIRED_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Expired - Link Bypasser</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
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
            from {
                opacity: 0;
                transform: translateY(-30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        .icon {
            font-size: 80px;
            margin-bottom: 20px;
            display: block;
            animation: pulse 2s infinite;
        }
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
        .btn:active {
            transform: translateY(0);
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
            .container {
                padding: 40px 25px;
            }
            h1 {
                font-size: 26px;
            }
            .btn {
                padding: 14px 30px;
                font-size: 16px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <span class="icon">⏰</span>
        <div class="status-badge">⚠️ API EXPIRED</div>
        <h1>API Has Expired</h1>
        <p class="subtitle">
            This Link Bypasser API is no longer active.<br>
            Please get a new API key to continue using the service.
        </p>
        
        <div class="expiry-card">
            <div class="label">📅 Expired On</div>
            <div class="date">{{ expiry_date }}</div>
            <div class="days">This API was valid for {{ expiry_days }} days</div>
        </div>
        
        <a href="https://t.me/+PEvs6Jg6JXthN2U9" target="_blank" class="btn">
            🚀 GET NEW API
        </a>
        
        <div class="footer">
            <p>Join our Telegram channel for latest updates</p>
            <p style="margin-top:5px;font-size:11px;color:rgba(255,255,255,0.2);">
                Created: {{ creation_date }}
            </p>
        </div>
    </div>
</body>
</html>
"""

# ============================================
# FASTAPI APPLICATION
# ============================================
app = FastAPI(title="Link Bypasser API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache for bypassed links
cache = TTLCache(maxsize=1000, ttl=CACHE_TTL)

# Rate limiting storage
request_counts: Dict[str, Dict[str, int]] = {}

# Supported domains
SUPPORTED_DOMAINS = {
    "lnbz.la": "lnbz",
    "sfl.gl": "sfl",
    "shrinkme.click": "shrinkme",
    "shrinkme.io": "shrinkme",
}

def is_supported_url(url: str) -> tuple[bool, Optional[str]]:
    """Check if URL is supported and return the bypass type."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    for domain, bypass_type in SUPPORTED_DOMAINS.items():
        if domain in parsed.netloc:
            return True, bypass_type
    return False, None

def get_cache_key(url: str) -> str:
    """Generate cache key for a URL."""
    return hashlib.md5(url.encode()).hexdigest()

def check_rate_limit(client_ip: str) -> tuple[bool, int]:
    """Check if client has exceeded rate limit."""
    now = datetime.now(KOLKATA_TZ)
    
    if client_ip not in request_counts:
        request_counts[client_ip] = {"count": 0, "date": now}
        return True, DAILY_LIMIT - 1
    
    # Check if we need to reset
    if now.date() > request_counts[client_ip]["date"].date():
        request_counts[client_ip] = {"count": 0, "date": now}
        return True, DAILY_LIMIT - 1
    
    if request_counts[client_ip]["count"] >= DAILY_LIMIT:
        return False, 0
    
    return True, DAILY_LIMIT - request_counts[client_ip]["count"] - 1

def increment_rate_limit(client_ip: str):
    """Increment rate limit counter."""
    if client_ip in request_counts:
        request_counts[client_ip]["count"] += 1

# ============================================
# ROOT ENDPOINT - HTML ONLY WHEN EXPIRED
# ============================================
@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint - Shows HTML only when API expired"""
    if is_api_expired():
        return HTMLResponse(
            EXPIRED_PAGE_TEMPLATE.replace(
                "{{ expiry_date }}", get_expiry_date()
            ).replace(
                "{{ expiry_days }}", str(API_EXPIRY_DAYS)
            ).replace(
                "{{ creation_date }}", API_CREATION_DATE.strftime("%d %B %Y, %I:%M %p IST")
            ),
            status_code=403
        )
    
    # When API is active - Return JSON
    return JSONResponse(
        content={
            "status": "active",
            "message": "Link Bypasser API is active",
            "endpoint": "/bypass?url=<your_link>",
            "expiry_date": get_expiry_date(),
            "remaining_days": get_remaining_days(),
            "supported_services": list(SUPPORTED_DOMAINS.keys()),
            "rate_limit": f"{DAILY_LIMIT} requests/day per IP",
            "cache_ttl": f"{CACHE_TTL} seconds",
            "timeout": f"{DEFAULT_TIMEOUT} seconds"
        }
    )

# ============================================
# BYPASS ENDPOINT - ALWAYS JSON
# ============================================
@app.get("/bypass")
async def bypass_link(
    request: Request,
    url: str = Query(..., description="The shortened URL to bypass")
):
    """Main endpoint to bypass shortened links - Always returns JSON"""
    import asyncio
    
    # Check API expiry - Return JSON error
    if is_api_expired():
        return JSONResponse(
            status_code=403,
            content={
                "error": "API Expired",
                "message": "This API has expired. Please get a new API key.",
                "expiry_date": get_expiry_date(),
                "created_date": API_CREATION_DATE.strftime("%d %B %Y, %I:%M %p IST"),
                "valid_days": API_EXPIRY_DAYS
            }
        )
    
    # Get client IP
    client_ip = request.client.host if request.client else "unknown"
    
    # Validate URL
    if not url.startswith(('http://', 'https://')):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid URL",
                "message": "URL must start with http:// or https://"
            }
        )
    
    # Check if URL is supported
    is_supported, bypass_type = is_supported_url(url)
    if not is_supported:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Unsupported URL",
                "message": "This link shortener is not supported",
                "supported_services": list(SUPPORTED_DOMAINS.keys())
            }
        )
    
    # ============================================
    # RATE LIMIT - ONLY FOR SUPPORTED LINKS
    # ============================================
    allowed, remaining = check_rate_limit(client_ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": f"Daily limit of {DAILY_LIMIT} requests reached",
                "limit": DAILY_LIMIT,
                "remaining": 0,
                "reset_time": "12:05 AM IST"
            }
        )
    
    # Check cache
    cache_key = get_cache_key(url)
    cached_result = cache.get(cache_key)
    if cached_result:
        increment_rate_limit(client_ip)
        return JSONResponse(
            content={
                "success": True,
                "original_url": url,
                "final_url": cached_result,
                "bypass_type": bypass_type,
                "cached": True,
                "remaining_requests": remaining
            }
        )
    
    # Perform bypass
    try:
        # Map bypass type to function
        bypass_functions = {
            "lnbz": bypass_lnbz,
            "sfl": bypass_sfl,
            "shrinkme": bypass_shrinkme,
        }
        
        bypass_func = bypass_functions.get(bypass_type)
        if not bypass_func:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Unsupported bypass type",
                    "message": f"No bypass handler for {bypass_type}"
                }
            )
        
        # Run bypass with timeout
        final_url = await asyncio.wait_for(
            bypass_func(url),
            timeout=DEFAULT_TIMEOUT
        )
        
        # Cache result
        cache[cache_key] = final_url
        
        # Increment rate limit
        increment_rate_limit(client_ip)
        
        return JSONResponse(
            content={
                "success": True,
                "original_url": url,
                "final_url": final_url,
                "bypass_type": bypass_type,
                "cached": False,
                "remaining_requests": remaining - 1
            }
        )
        
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504,
            content={
                "error": "Timeout",
                "message": f"Bypass timed out after {DEFAULT_TIMEOUT} seconds"
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Bypass failed",
                "message": str(e)
            }
        )

# ============================================
# STATUS ENDPOINT - ALWAYS JSON
# ============================================
@app.get("/status")
async def status(request: Request):
    """Get API status and usage information - Always returns JSON"""
    if is_api_expired():
        return JSONResponse(
            status_code=403,
            content={
                "status": "expired",
                "message": "API has expired",
                "expiry_date": get_expiry_date(),
                "created_date": API_CREATION_DATE.strftime("%d %B %Y, %I:%M %p IST"),
                "valid_days": API_EXPIRY_DAYS
            }
        )
    
    client_ip = request.client.host if request.client else "unknown"
    current_count = request_counts.get(client_ip, {}).get("count", 0)
    
    return JSONResponse(
        content={
            "status": "active",
            "expiry_date": get_expiry_date(),
            "remaining_days": get_remaining_days(),
            "daily_limit": DAILY_LIMIT,
            "used_today": current_count,
            "remaining_today": max(0, DAILY_LIMIT - current_count),
            "reset_time": "12:05 AM IST",
            "cache_size": len(cache),
            "cache_ttl": f"{CACHE_TTL} seconds"
        }
    )

# ============================================
# SUPPORTED ENDPOINT - ALWAYS JSON
# ============================================
@app.get("/supported")
async def list_supported():
    """List all supported services - Always returns JSON"""
    if is_api_expired():
        return JSONResponse(
            status_code=403,
            content={
                "error": "API Expired",
                "message": "This API has expired. Please get a new API key.",
                "expiry_date": get_expiry_date()
            }
        )
    
    return JSONResponse(
        content={
            "supported_services": [
                {
                    "domain": domain,
                    "type": bypass_type,
                    "example": f"https://{domain}/your-link"
                }
                for domain, bypass_type in SUPPORTED_DOMAINS.items()
            ]
        }
    )

# ============================================
# RUN APPLICATION
# ============================================
if __name__ == "__main__":
    # Check API expiry
    if is_api_expired():
        print("⚠️ API has expired on", get_expiry_date())
        print("Please create a new API key.")
    else:
        print("✅ API is active until", get_expiry_date())
        print(f"📊 Remaining days: {get_remaining_days()}")
    
    print("🚀 Starting Link Bypasser API server...")
    print("📌 Endpoint: /bypass?url=<your_link>")
    print("📊 Rate Limit: 100 requests/day per IP (only for supported links)")
    print("⚡ Cache TTL: 2 minutes")
    print("⏱️ Timeout: 30 seconds")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)