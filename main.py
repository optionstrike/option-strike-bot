from fastapi import FastAPI, Request
import requests
import yfinance as yf
import pandas as pd
import time
import asyncio
from datetime import datetime, timedelta

app = FastAPI()

# =========================
# بياناتك
# =========================

TOKEN = "8619465902:AAEE0dvsBCneu6c2aQQnarRFI_Jzw8O7VRE"
CHAT_ID = "8371374055"
MASSIVE_API_KEY = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2"

API_SEND = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
API_ANSWER = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"

MASSIVE_BASE = "https://api.polygon.io"

# =========================
# حماية الويب هوك
# =========================

TELEGRAM_SECRET_TOKEN = "OPTION_STRIKE_SECRET_2026_555"

# =========================
# كاش + منع تكرار التحديثات
# =========================

ANALYSIS_CACHE = {}
ANALYSIS_CACHE_TTL_SECONDS = 45

PROCESSED_UPDATES = {}
PROCESSED_UPDATES_TTL_SECONDS = 600

# =========================
# إعدادات الصياد
# =========================

MAX_SIGNALS_PER_DAY = 5
STOCK_COOLDOWN_DAYS = 3
TREND_CONFIRM_HOURS = 3
SCAN_INTERVAL_SECONDS = 10800

# =========================
# فلتر الدخول
# =========================

ENTRY_MAX_DISTANCE_PCT = 0.015
BREAKOUT_BUFFER_PCT = 0.003

# =========================
# شروط العقود
# =========================

MAX_COMPANY_CONTRACT_PRICE = 3.50
MAX_SPAC_CONTRACT_PRICE = 3.70
ENTRY_ZONE_WIDTH = 0.60
UPDATE_STEP_AFTER_TP1 = 0.30

# =========================
# زيرو هيرو
# =========================

FRIDAY_ZERO_HERO_ENABLED = True
ZERO_HERO_ONLY_ON_FRIDAY = True
ZERO_HERO_MIN_PRICE = 0.20
ZERO_HERO_MAX_PRICE = 2.00
ZERO_HERO_MIN_SUCCESS_RATE = 75
ZERO_HERO_MIN_OI = 100
ZERO_HERO_MIN_PROB = 65

# =========================
# الارتكاز
# =========================

INDEX_DAILY_PIVOT = {"US500", "SPY", "QQQ", "SPX", "NDX", "US100"}

SPAC_TICKERS = {
    "NBIS", "CRCL", "CRWV", "MARA", "HOOD", "RDDT", "CVNA", "COIN", "MSTR",
    "PLTR", "APP", "SNOW", "DDOG", "MDB", "TWLO", "DASH", "ABNB", "UBER",
    "SMCI", "ARM", "CRWD", "ENPH", "FSLR", "BE", "ALB", "SHOP", "PYPL",
    "BIDU", "PDD", "BABA", "LULU", "ULTA", "ADBE"
}

# =========================
# قائمة الأسهم
# =========================

WATCHLIST = list(dict.fromkeys([
    "GLD", "IBM", "V", "JPM", "SBUX", "MMM", "QCOM", "GOOG", "INTC", "NFLX", "GS", "SMH",
    "ABNB", "TWLO", "DASH", "PYPL", "DHI", "BE", "ENPH", "JNJ", "DELL", "BIDU", "RDDT",
    "DDOG", "UPS", "DE", "NOW", "UBER", "INTU", "LRCX", "LOW", "HD", "PANW", "BA", "ZS",
    "MRVL", "ULTA", "SMCI", "MARA", "MCD", "PDD", "FDX", "FSLR", "COST", "SHOP", "ALB",
    "NBIS", "ARM", "CRCL", "ABBV", "HOOD", "BABA", "ADBE", "LULU", "ORCL", "LLY", "TSM",
    "CVNA", "COIN", "CRWV", "CAT", "AMD", "SNOW", "MDB", "AMZN", "MU", "CRM", "GE",
    "NVDA", "AAPL", "GOOGL", "MSFT", "TSLA", "META", "AVGO", "CRWD", "APP", "UNH",
    "MSTR", "PLTR", "US500", "SPY", "QQQ", "SPX", "NDX", "US100"
]))

HTTP = requests.Session()

# =========================
# تتبع الإشارات
# =========================

LAST_SENT_STOCK = {}
TREND_STATE = {}

DAILY_SIGNAL_STATE = {
    "date": datetime.now().date(),
    "count": 0
}

OPEN_CONTRACT_SIGNALS = {}

# =========================
# أدوات حماية ومساعدة
# =========================

def cleanup_processed_updates():
    now = datetime.now()
    for key in list(PROCESSED_UPDATES.keys()):
        if now - PROCESSED_UPDATES[key] > timedelta(seconds=PROCESSED_UPDATES_TTL_SECONDS):
            del PROCESSED_UPDATES[key]

def is_duplicate_update(update_id):
    if update_id is None:
        return False
    cleanup_processed_updates()
    if update_id in PROCESSED_UPDATES:
        return True
    PROCESSED_UPDATES[update_id] = datetime.now()
    return False

def cleanup_analysis_cache():
    now = datetime.now()
    for key in list(ANALYSIS_CACHE.keys()):
        cached = ANALYSIS_CACHE[key]
        if now - cached["ts"] > timedelta(seconds=ANALYSIS_CACHE_TTL_SECONDS):
            del ANALYSIS_CACHE[key]

def get_cached_analysis(ticker: str, tf: str):
    cleanup_analysis_cache()
    key = f"{ticker}|{tf}"
    cached = ANALYSIS_CACHE.get(key)
    if not cached:
        return None
    return cached["value"]

def set_cached_analysis(ticker: str, tf: str, value):
    ANALYSIS_CACHE[f"{ticker}|{tf}"] = {
        "ts": datetime.now(),
        "value": value
    }

def request_has_valid_secret(req: Request):
    secret_header = req.headers.get("x-telegram-bot-api-secret-token", "")
    return secret_header == TELEGRAM_SECRET_TOKEN

def looks_like_telegram_update(data):
    if not isinstance(data, dict):
        return False
    if "update_id" in data:
        return True
    if "message" in data:
        return True
    if "callback_query" in data:
        return True
    return False

def reset_daily_counter_if_needed():
    today = datetime.now().date()
    if DAILY_SIGNAL_STATE["date"] != today:
        DAILY_SIGNAL_STATE["date"] = today
        DAILY_SIGNAL_STATE["count"] = 0

def can_send_more_today():
    reset_daily_counter_if_needed()
    return DAILY_SIGNAL_STATE["count"] < MAX_SIGNALS_PER_DAY

def add_daily_signal():
    reset_daily_counter_if_needed()
    DAILY_SIGNAL_STATE["count"] += 1

def stock_in_cooldown(ticker: str) -> bool:
    last_sent = LAST_SENT_STOCK.get(ticker)
    if not last_sent:
        return False
    return datetime.now() - last_sent < timedelta(days=STOCK_COOLDOWN_DAYS)

def mark_stock_sent(ticker: str):
    LAST_SENT_STOCK[ticker] = datetime.now()

# =========================
# إرسال تلغرام
# =========================

def send(msg, keyboard=None, chat_id=None):
    target_chat_id = str(chat_id) if chat_id else CHAT_ID

    payload = {
        "chat_id": target_chat_id,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    if keyboard:
        payload["reply_markup"] = keyboard

    try:
        r = HTTP.post(API_SEND, json=payload, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[SEND ERROR] {e}")

def answer_callback(cb_id, text=""):
    try:
        HTTP.post(API_ANSWER, json={
            "callback_query_id": cb_id,
            "text": text
        }, timeout=10)
    except Exception as e:
        print(f"[CALLBACK ERROR] {e}")

# =========================
# لوحة الأزرار الرئيسية
# =========================

def main_menu():
    return {
        "inline_keyboard": [
            [
                {"text": "📊 تحليل سريع", "callback_data": "quick"},
                {"text": "🔥 تحليل احترافي", "callback_data": "pro"},
            ],
            [
                {"text": "🧲 القاما والسيولة", "callback_data": "gamma"},
                {"text": "📈 دعوم ومقاومات", "callback_data": "sr"},
            ],
            [
                {"text": "🎯 خطة دخول", "callback_data": "plan"},
                {"text": "💎 أفضل عقد", "callback_data": "contract"},
            ],
            [
                {"text": "📰 أخبار السوق", "callback_data": "news"},
                {"text": "⚙️ تغيير الفريم", "callback_data": "tf"},
            ]
        ]
    }

def tf_menu():
    tfs = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]
    rows = []
    row = []
    for i, tf in enumerate(tfs, 1):
        row.append({"text": tf, "callback_data": f"settf:{tf}"})
        if i % 4 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{"text": "⬅️ رجوع", "callback_data": "back"}])
    return {"inline_keyboard": rows}

# =========================
# الفريمات
# =========================

TF = {
    "1m": ("5d", "1m"),
    "5m": ("1mo", "5m"),
    "15m": ("1mo", "15m"),
    "30m": ("1mo", "30m"),
    "1h": ("3mo", "60m"),
    "4h": ("6mo", "1h"),
    "1d": ("1y", "1d"),
    "1w": ("3y", "1wk"),
}

# =========================
# تحويل الرموز لـ yfinance
# =========================

def map_symbol_for_data(ticker: str) -> str:
    mapping = {
        "SPX": "^GSPC",
        "NDX": "^NDX",
        "SPY": "SPY",
        "QQQ": "QQQ",
        "US500": "^GSPC",
        "US100": "^NDX",
    }
    return mapping.get(ticker, ticker)

def get_df(ticker, tf):
    period, interval = TF.get(tf, ("1y", "1d"))
    data_ticker = map_symbol_for_data(ticker)
    s = yf.Ticker(data_ticker)
    df = s.history(period=period, interval=interval, auto_adjust=False)
    if df.empty:
        return df
    df.index = pd.to_datetime(df.index, utc=False)
    if tf == "4h":
        df = df.resample("4H").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum"
        }).dropna()
    return df

# =========================
# Massive / Polygon API
# =========================

def massive_get(path: str, params=None):
    params = params or {}
    params["apiKey"] = MASSIVE_API_KEY
    url = f"{MASSIVE_BASE}{path}"
    try:
        r = HTTP.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[API ERROR] {path}: {e}")
        return {}

def safe_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur

# =========================
# أخبار السوق
# =========================

def get_market_news(ticker: str = None, limit: int = 5):
    try:
        params = {"limit": limit, "order": "desc", "sort": "published_utc"}
        if ticker:
            params["ticker"] = ticker
        data = massive_get("/v2/reference/news", params=params)
        results = data.get("results", [])
        return results
    except Exception as e:
        print(f"[NEWS ERROR] {e}")
        return []

def format_news_message(ticker: str = None):
    news = get_market_news(ticker, limit=5)
    if not news:
        return "❌ لا توجد أخبار متاحة حالياً"

    label = f"أخبار {ticker}" if ticker else "أخبار السوق العامة"
    msg = f"📰 <b>{label}</b>\n{'─' * 30}\n\n"

    for i, item in enumerate(news, 1):
        title = item.get("title", "بدون عنوان")
        publisher = safe_get(item, "publisher", "name", default="")
        published = item.get("published_utc", "")
        url = item.get("article_url", "")

        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            date_str = dt.strftime("%d/%m %H:%M")
        except Exception:
            date_str = ""

        msg += f"<b>{i}. {title}</b>\n"
        if publisher:
            msg += f"📌 {publisher}"
        if date_str:
            msg += f" | 🕐 {date_str}"
        msg += "\n"
        if url:
            msg += f"🔗 <a href='{url}'>اقرأ المزيد</a>\n"
        msg += "\n"

    return msg

# =========================
# بيانات العقود
# =========================

def parse_contract_price_from_snapshot(item):
    candidates = [
        safe_get(item, "last_trade", "price"),
        safe_get(item, "last_trade", "p"),
        safe_get(item, "session", "close"),
        safe_get(item, "session", "last"),
        safe_get(item, "details", "last_price"),
        safe_get(item, "day", "close"),
        safe_get(item, "day", "last"),
        safe_get(item, "min", "close"),
    ]
    for x in candidates:
        try:
            if x is not None and float(x) > 0:
                return float(x)
        except Exception:
            pass
    return None

def parse_underlying_price_from_snapshot(item):
    candidates = [
        safe_get(item, "underlying_asset", "price"),
        safe_get(item, "underlying_asset", "last", "price"),
        safe_get(item, "underlying_asset", "last_trade", "price"),
        safe_get(item, "underlying_asset", "value"),
    ]
    for x in candidates:
        try:
            if x is not None:
                return float(x)
        except Exception:
            pass
    return None

def parse_contract_meta(item):
    details = safe_get(item, "details", default={}) or {}
    greeks = safe_get(item, "greeks", default={}) or {}
    return {
        "ticker": details.get("ticker") or item.get("ticker") or item.get("option_ticker"),
        "strike": float(details.get("strike_price", 0) or 0),
        "expiration": details.get("expiration_date", ""),
        "contract_type": (details.get("contract_type") or "").lower(),
        "delta": float(greeks.get("delta", 0) or 0),
        "gamma": float(greeks.get("gamma", 0) or 0),
        "iv": float(item.get("implied_volatility", 0) or 0),
        "oi": int(item.get("open_interest", 0) or 0),
        "contract_price": parse_contract_price_from_snapshot(item),
        "underlying_price": parse_underlying_price_from_snapshot(item),
    }

def get_option_chain_snapshot(underlying: str):
    try:
        data = massive_get(f"/v3/snapshot/options/{underlying}", params={"limit": 250})
        results = data.get("results", [])
        if isinstance(results, list):
            return results
        return []
    except Exception as e:
        print(f"[CHAIN ERROR] {underlying}: {e}")
        return []

def get_option_contract_snapshot(underlying: str, option_contract: str):
    try:
        data = massive_get(f"/v3/snapshot/options/{underlying}/{option_contract}")
        return data.get("results", data)
    except Exception:
        return {}

def get_option_last_trade(option_contract: str):
    try:
        data = massive_get(f"/v2/last/trade/{option_contract}")
        return data.get("results", {})
    except Exception:
        return {}

# =========================
# أدوات خاصة بالعقود
# =========================

def is_spac_ticker(ticker: str) -> bool:
    return ticker in SPAC_TICKERS

def is_friday_now() -> bool:
    return datetime.now().weekday() == 4

def contract_price_limit_for_ticker(ticker: str) -> float:
    return MAX_SPAC_CONTRACT_PRICE if is_spac_ticker(ticker) else MAX_COMPANY_CONTRACT_PRICE

def days_to_expiry(expiration_str: str):
    try:
        exp = datetime.strptime(expiration_str, "%Y-%m-%d").date()
        return (exp - datetime.now().date()).days
    except Exception:
        return None

def build_contract_from_pick(best, c, target_type, mode="NORMAL"):
    contract_price = round(float(best["contract_price"]), 2)
    return {
        "option_ticker": best["ticker"],
        "strike": round(best["strike"], 2),
        "expiration": best["expiration"],
        "contract_type": best["contract_type"],
        "contract_price": contract_price,
        "entry_high": contract_price,
        "entry_low": round(max(0.10, contract_price - ENTRY_ZONE_WIDTH), 2),
        "tp1": round(contract_price + 0.60, 2),
        "tp2": round(contract_price + 1.20, 2),
        "tp3": round(contract_price + 1.80, 2),
        "stop_text": f"إغلاق شمعة ساعة {'تحت' if target_type == 'call' else 'فوق'} {c['pivot']:.2f}",
        "delta": round(best["delta"], 2),
        "gamma": round(best["gamma"], 4),
        "iv": round(best["iv"], 4),
        "oi": best["oi"],
        "mode": mode
    }

# =========================
# تثبيت الاتجاه
# =========================

def get_confirmed_side_hourly(ticker: str, pivot: float):
    df_1h = get_df(ticker, "1h")
    if df_1h.empty or len(df_1h) < 3:
        return "neutral"

    closes = df_1h["Close"].tail(3)

    if all(closes > pivot):
        side = "above"
    elif all(closes < pivot):
        side = "below"
    else:
        side = "neutral"

    prev = TREND_STATE.get(ticker)

    if prev is None:
        TREND_STATE[ticker] = {"side": side, "confirmed_at": datetime.now()}
        return side

    if prev["side"] == side:
        return side

    if side == "neutral":
        return prev["side"]

    if datetime.now() - prev["confirmed_at"] >= timedelta(hours=TREND_CONFIRM_HOURS):
        TREND_STATE[ticker] = {"side": side, "confirmed_at": datetime.now()}
        return side

    return prev["side"]

# =========================
# حسابات الارتكاز
# =========================

def core_metrics(df, ticker=None):
    if df.empty:
        return None

    price = float(df["Close"].iloc[-1])

    if ticker in INDEX_DAILY_PIVOT:
        ref = get_df(ticker, "1d")
        if ref.empty or len(ref) < 2:
            return None
        prev = ref.iloc[-2]
        pivot_label = "اليومي"
    else:
        ref = get_df(ticker, "1w")
        if ref.empty or len(ref) < 2:
            return None
        prev = ref.iloc[-2]
        pivot_label = "الأسبوعي"

    ref_high = float(prev["High"])
    ref_low = float(prev["Low"])
    ref_close = float(prev["Close"])

    pivot = (ref_high + ref_low + ref_close) / 3.0
    ref_range = ref_high - ref_low

    call_tp1 = pivot + ref_range * 0.5
    call_tp2 = pivot + ref_range
    call_tp3 = ref_high + ref_range * 0.5

    put_tp1 = pivot - ref_range * 0.5
    put_tp2 = pivot - ref_range
    put_tp3 = ref_low - ref_range * 0.5

    pivot_diff = price - pivot
    if pivot_diff > 0:
        pivot_position = "فوق الارتكاز"
    elif pivot_diff < 0:
        pivot_position = "تحت الارتكاز"
    else:
        pivot_position = "على الارتكاز"

    ema20 = float(df["Close"].ewm(span=20).mean().iloc[-1])
    ema50 = float(df["Close"].ewm(span=50).mean().iloc[-1])
    trend = "صاعد 📈" if ema20 > ema50 else "هابط 📉"

    confirmed_side = get_confirmed_side_hourly(ticker, pivot) if ticker else "neutral"

    if confirmed_side == "above":
        strongest_trend = "صاعد قوي 🔥"
    elif confirmed_side == "below":
        strongest_trend = "هابط قوي 🔻"
    else:
        strongest_trend = "محايد ⚖️"

    if trend == "صاعد 📈" and price > pivot:
        direction = "CALL 🟢"
    elif trend == "هابط 📉" and price < pivot:
        direction = "PUT 🔴"
    elif confirmed_side == "above":
        direction = "CALL 🟢"
    elif confirmed_side == "below":
        direction = "PUT 🔴"
    elif price > pivot:
        direction = "CALL 🟢"
    else:
        direction = "PUT 🔴"

    best_entry = pivot + 0.2 if direction.startswith("CALL") else pivot - 0.2

    return {
        "price": price,
        "high": ref_high,
        "low": ref_low,
        "pivot": pivot,
        "pivot_label": pivot_label,
        "pivot_diff": pivot_diff,
        "pivot_position": pivot_position,
        "call_tp1": call_tp1,
        "call_tp2": call_tp2,
        "call_tp3": call_tp3,
        "put_tp1": put_tp1,
        "put_tp2": put_tp2,
        "put_tp3": put_tp3,
        "tp1": call_tp1,
        "tp2": call_tp2,
        "tp3": call_tp3,
        "sl": pivot,
        "trend": trend,
        "strongest_trend": strongest_trend,
        "direction": direction,
        "best_entry": best_entry,
        "confirmed_side": confirmed_side,
        "ema20": ema20,
        "ema50": ema50
    }
