# api/kis_api.py
import http.client
import json
import os
import time
from dotenv import load_dotenv

import requests

from config import ACCOUNT_NO
from extensions import cache

load_dotenv()

APP_KEY = os.getenv("appkey")
APP_SECRET = os.getenv("secretkey")
URL_BASE = "https://openapivts.koreainvestment.com:29443"

ACCOUNT_CODE, PRODUCT_CODE = ACCOUNT_NO.split("-")[0], ACCOUNT_NO.split("-")[1]

_kis_token = None
_kis_token_expiry = 0

def get_kis_access_token():
    global _kis_token, _kis_token_expiry

    # ✅ 만료 전이면 재사용
    if _kis_token and time.time() < _kis_token_expiry - 10:
        return _kis_token

    conn = http.client.HTTPSConnection("openapivts.koreainvestment.com", 29443)
    payload = json.dumps({
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    })
    headers = {"content-type": "application/json; charset=UTF-8"}

    conn.request("POST", "/oauth2/tokenP", payload, headers)
    res = conn.getresponse()
    decoded = json.loads(res.read().decode("utf-8"))

    if "access_token" not in decoded:
        raise Exception(f"access_token 발급 실패: {decoded}")

    _kis_token = decoded["access_token"]
    _kis_token_expiry = time.time() + int(decoded.get("expires_in", 0))
    return _kis_token

def _request_overseas_daily_price(ticker: str, exchange: str = "NAS"):
    token = get_kis_access_token()

    url = f"{URL_BASE}/uapi/overseas-price/v1/quotations/dailyprice"
    headers = {
        "content-type": "application/json; charset=UTF-8",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "HHDFS76240000",
    }

    now = time.strftime("%Y%m%d")
    params = {"AUTH": "", "EXCD": exchange, "SYMB": ticker, "GUBN": "0", "BYMD": now, "MODP": "1"}

    res = requests.get(url, headers=headers, params=params, timeout=8)
    res.raise_for_status()
    return res.json()

# ✅ 진짜 1시간 캐시 (ticker+exchange 별로)
@cache.memoize(timeout=60 * 60)
def get_overseas_daily_price(ticker: str, exchange: str = "NAS"):
    return _request_overseas_daily_price(ticker, exchange)
