from fastapi import FastAPI, Request
import requests
import io
import json
import os
import yfinance as yf
import pandas as pd
import time
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from deep_translator import GoogleTranslator

app = FastAPI()

# =========================
# بياناتك
# =========================

TOKEN = "8619465902:AAEDTuUFEEEgIq-sjr5-d4oCaiyuMzFSYPs"
CHAT_ID = "8371374055"
MASSIVE_API_KEY = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2"

# مفتاح الأخبار الاقتصادية - غيّره لاحقاً
FMP_API_KEY = "xQ7wdkVapeynP4FsDL4dBLMisFkbN2qL"

API_SEND = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
API_SEND_PHOTO = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
API_EDIT_MEDIA = f"https://api.telegram.org/bot{TOKEN}/editMessageMedia"
API_ANSWER = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"

MASSIVE_BASE = "https://api.polygon.io"
FMP_BASE = "https://financialmodelingprep.com/stable"

# =========================
# حماية الويب هوك
# =========================

TELEGRAM_SECRET_TOKEN = "OPTION_STRIKE_SECRET_2026_555"
TRADINGVIEW_SECRET = "OPTION_STRIKE_TV_2026"

# =========================
# كاش + منع تكرار التحديثات
# =========================

ANALYSIS_CACHE = {}
ANALYSIS_CACHE_TTL_SECONDS = 45

PROCESSED_UPDATES = {}
PROCESSED_UPDATES_TTL_SECONDS = 600

EARNINGS_CACHE = {}
EARNINGS_CACHE_TTL_SECONDS = 600

ECON_CACHE = {}
ECON_CACHE_TTL_SECONDS = 300

NEWS_CACHE = {}
NEWS_CACHE_TTL_SECONDS = 900

# =========================
# إعدادات الصياد
# =========================

MAX_SIGNALS_PER_DAY = 6
MAX_SIGNALS_PER_SCAN = 1
STOCK_COOLDOWN_DAYS = 3
TREND_CONFIRM_HOURS = 1
SCAN_INTERVAL_SECONDS = 20

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
# أهداف العقود الجديدة
# =========================

CONTRACT_TP1_ADD = 0.60
CONTRACT_TARGET_LOOKBACK_DAYS = 10
CONTRACT_TARGET_MIN_GAP = 0.12

# =========================
# الأخبار الاقتصادية
# =========================

ECON_NEWS_ALERT_ENABLED = True
ECON_NEWS_ALERT_MINUTES_BEFORE = 5
ECON_NEWS_ONLY_IMPORTANT = True

IMPORTANT_EVENT_KEYWORDS = [
    "cpi", "inflation", "interest rate", "fomc", "federal reserve", "fed",
    "unemployment", "jobless", "non farm", "nonfarm", "payroll", "nfp",
    "pmi", "retail sales", "ppi", "powell", "trump", "consumer confidence",
    "gdp", "core cpi", "core pce", "oil inventories", "crude oil", "rate decision"
]

# =========================
# إعلانات الشركات
# =========================

EARNINGS_LOOKAHEAD_DAYS = 7
EARNINGS_MAX_BUTTONS = 100

# =========================
# زيرو هيرو
# =========================

FRIDAY_ZERO_HERO_ENABLED = True
ZERO_HERO_ONLY_ON_FRIDAY = True
ZERO_HERO_MIN_PRICE = 0.70
ZERO_HERO_MAX_PRICE = 2.50
ZERO_HERO_MIN_SUCCESS_RATE = 75
ZERO_HERO_MIN_OI = 100
ZERO_HERO_MIN_PROB = 65

# =========================
# عقود الحيتان - مستقلة عن الطرح العادي
# =========================

WHALE_CONTRACTS_ENABLED = True
WHALE_MAX_SIGNALS_PER_DAY = 6
WHALE_MAX_SIGNALS_PER_SCAN = 1
WHALE_MIN_PRICE = 0.70
WHALE_MAX_PRICE = 1.50
WHALE_MIN_DTE_DAYS = 7
WHALE_MAX_DTE_DAYS = 35
WHALE_MIN_OI = 50
WHALE_MIN_SCORE = 60
# =========================
# نظام الحيتان المطور - قناص الانفجارات
# مستقل عن الطرح العادي ولا يغير شروط الشركات
# =========================
WHALE_ENHANCED_EXPLOSION_ENABLED = True
WHALE_MIN_EXPLOSION_SCORE = 75
WHALE_CONSOLIDATION_BARS = 12
WHALE_STRUCTURE_BARS = 24
WHALE_MAX_CONSOLIDATION_RANGE_PCT = 0.060
WHALE_NEAR_LEVEL_PCT = 0.020
WHALE_VOLUME_SPIKE_MULT = 1.40
WHALE_VOLUME_RISING_MULT = 1.15
WHALE_ATR_COMPRESSION_MULT = 0.95
WHALE_ENTRY_ZONE_WIDTH = 0.60
WHALE_SLOT_TIMES_RIYADH = [(17, 30), (18, 30), (19, 30), (20, 30), (21, 30), (22, 30)]
# ملاحظة مهمة:
# الحيتان مستقلة تماماً عن الطرح العادي:
# - لا تستخدم عداد الطرح العادي
# - لا تستخدم تبريد الشركات العادي
# - حتى لو نفس الشركة انطرحت عادي، عقد الحيتان يطلع إذا شروطه مكتملة
WHALE_ALLOW_SAME_TICKER_AS_REGULAR = True


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

INDEX_TICKERS = {"US500", "SPY", "QQQ", "SPX", "NDX", "US100"}

MIN_DTE_DAYS = 1
MAX_DTE_DAYS = 30
INDEX_MAX_DTE_DAYS = 7

MARKET_TZ = ZoneInfo("America/New_York")
RIYADH_TZ = ZoneInfo("Asia/Riyadh")

MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
NO_ENTRY_FIRST_MINUTES = 30

# =========================
# قائمة الأسهم
# =========================

PRIORITY_45_TICKERS = [
    "NVDA", "AAPL", "GOOGL", "MSFT", "META", "TSLA", "UNH", "MSTR", "COIN", "LLY",
    "AVGO", "APP", "CRWD", "TSM", "PLTR", "CVNA", "AMD", "CRWV", "CAT", "SNOW",
    "CRM", "COST", "MU", "MDB", "AMZN", "FSLR", "GE", "NBIS", "CRCL", "DELL",
    "LRCX", "HD", "LOW", "ADBE", "ORCL", "ARM", "BA", "FDX", "RDDT", "GLD",
    "IBM", "GS", "SMH", "V"
]

FRIDAY_ZERO_HERO_TICKERS = ["TSLA", "MU", "META", "APP", "CAT", "CVNA"]

WATCHLIST = list(dict.fromkeys(PRIORITY_45_TICKERS))

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
SIGNAL_HISTORY = []

# =========================
# أرشفة التقارير والعقود
# =========================
REPORTS_DIR = "reports_archive"
SIGNAL_HISTORY_FILE = os.path.join(REPORTS_DIR, "signal_history.json")
REPORT_IMAGE_WIDTH = 1080
REPORT_IMAGE_HEIGHT = 1620

ECON_ALERT_SENT = set()
LAST_SCANNER_SLOT_KEY = None
LAST_WHALE_SLOT_KEY = None

WHALE_DAILY_SIGNAL_STATE = {
    "date": datetime.now().date(),
    "count": 0
}
WHALE_LAST_SENT_CONTRACT = {}
WHALE_HISTORY = []
WHALE_HISTORY_FILE = os.path.join(REPORTS_DIR, "whale_signal_history.json")


# =========================
# حفظ واسترجاع أرشيف العقود
# =========================

def _dt_to_str(v):
    return v.isoformat() if isinstance(v, datetime) else v

def _dt_from_str(v):
    if not v or isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v))
    except Exception:
        return None

def _safe_float(v, default=0.0):
    try:
        if v in [None, "", "—"]:
            return default
        return float(v)
    except Exception:
        return default

def save_signal_archive():
    try:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        data = []
        for row in SIGNAL_HISTORY:
            clean = dict(row)
            clean["created_at"] = _dt_to_str(clean.get("created_at"))
            data.append(clean)
        with open(SIGNAL_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ARCHIVE SAVE ERROR] {e}")

def load_signal_archive():
    try:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        if not os.path.exists(SIGNAL_HISTORY_FILE):
            return
        with open(SIGNAL_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        SIGNAL_HISTORY.clear()
        OPEN_CONTRACT_SIGNALS.clear()
        for row in data:
            row["created_at"] = _dt_from_str(row.get("created_at")) or datetime.now()
            SIGNAL_HISTORY.append(row)
            if row.get("option_ticker"):
                OPEN_CONTRACT_SIGNALS[row["option_ticker"]] = row
        print(f"[ARCHIVE LOADED] {len(SIGNAL_HISTORY)} signals")
    except Exception as e:
        print(f"[ARCHIVE LOAD ERROR] {e}")

def save_whale_archive():
    try:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        data = []
        for row in WHALE_HISTORY:
            clean = dict(row)
            clean["created_at"] = _dt_to_str(clean.get("created_at"))
            data.append(clean)
        with open(WHALE_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WHALE ARCHIVE SAVE ERROR] {e}")

def load_whale_archive():
    try:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        if not os.path.exists(WHALE_HISTORY_FILE):
            return
        with open(WHALE_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        WHALE_HISTORY.clear()
        for row in data:
            row["created_at"] = _dt_from_str(row.get("created_at")) or datetime.now()
            row.setdefault("first_update_sent", False)
            row.setdefault("last_update_trigger_price", row.get("tp1", row.get("entry_price", 0)))
            row.setdefault("category", "whale")
            WHALE_HISTORY.append(row)
            if row.get("option_ticker"):
                OPEN_CONTRACT_SIGNALS[row["option_ticker"]] = row
        print(f"[WHALE ARCHIVE LOADED] {len(WHALE_HISTORY)} signals")
    except Exception as e:
        print(f"[WHALE ARCHIVE LOAD ERROR] {e}")

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

def cleanup_generic_cache(cache: dict, ttl_seconds: int):
    now = datetime.now()
    for key in list(cache.keys()):
        cached = cache[key]
        if now - cached["ts"] > timedelta(seconds=ttl_seconds):
            del cache[key]

def get_cached_item(cache: dict, ttl_seconds: int, key: str):
    cleanup_generic_cache(cache, ttl_seconds)
    cached = cache.get(key)
    if not cached:
        return None
    return cached["value"]

def set_cached_item(cache: dict, key: str, value):
    cache[key] = {"ts": datetime.now(), "value": value}

def request_has_valid_secret(req: Request):
    secret_header = req.headers.get("x-telegram-bot-api-secret-token", "")
    return secret_header == TELEGRAM_SECRET_TOKEN

def is_tradingview_payload(data):
    if not isinstance(data, dict):
        return False
    if data.get("secret") == TRADINGVIEW_SECRET and "ticker" in data and "signal" in data:
        return True
    return False

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

def reset_whale_daily_counter_if_needed():
    today = datetime.now(RIYADH_TZ).date()
    if WHALE_DAILY_SIGNAL_STATE["date"] != today:
        WHALE_DAILY_SIGNAL_STATE["date"] = today
        WHALE_DAILY_SIGNAL_STATE["count"] = 0
        WHALE_LAST_SENT_CONTRACT.clear()

def can_send_more_whales_today():
    reset_whale_daily_counter_if_needed()
    return WHALE_DAILY_SIGNAL_STATE["count"] < WHALE_MAX_SIGNALS_PER_DAY

def add_whale_signal():
    reset_whale_daily_counter_if_needed()
    WHALE_DAILY_SIGNAL_STATE["count"] += 1

def stock_in_cooldown(ticker: str) -> bool:
    last_sent = LAST_SENT_STOCK.get(ticker)
    if not last_sent:
        return False
    return datetime.now() - last_sent < timedelta(days=STOCK_COOLDOWN_DAYS)

def mark_stock_sent(ticker: str):
    LAST_SENT_STOCK[ticker] = datetime.now()

def is_in_no_entry_window():
    now_et = datetime.now(MARKET_TZ)

    if now_et.weekday() >= 5:
        return False

    market_open = now_et.replace(
        hour=MARKET_OPEN_HOUR,
        minute=MARKET_OPEN_MINUTE,
        second=0,
        microsecond=0
    )
    no_entry_end = market_open + timedelta(minutes=NO_ENTRY_FIRST_MINUTES)

    return market_open <= now_et < no_entry_end

def is_us_market_open_now():
    """
    فلتر حماية لعقود الحيتان والطرح الآلي:
    يمنع الإرسال إذا السوق الأمريكي مقفل.
    لا يعتمد على توقيت السعودية فقط لأن التوقيت الصيفي يتغير.
    """
    now_et = datetime.now(MARKET_TZ)
    if now_et.weekday() >= 5:
        return False

    market_open = now_et.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close

def get_market_open_close_riyadh(target_date=None):
    now_et = datetime.now(MARKET_TZ)
    if target_date is None:
        target_date = now_et.date()

    market_open_et = datetime(target_date.year, target_date.month, target_date.day, MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, tzinfo=MARKET_TZ)
    market_close_et = datetime(target_date.year, target_date.month, target_date.day, 16, 0, tzinfo=MARKET_TZ)
    return market_open_et.astimezone(RIYADH_TZ), market_close_et.astimezone(RIYADH_TZ)

def get_regular_scan_slots_riyadh(target_date=None):
    now_riyadh = datetime.now(RIYADH_TZ)
    if target_date is None:
        target_date = now_riyadh.date()

    raw_times = [(17, 0), (17, 30), (18, 0), (19, 0), (20, 0), (21, 0)]
    return [datetime(target_date.year, target_date.month, target_date.day, hh, mm, tzinfo=RIYADH_TZ) for hh, mm in raw_times]

def get_whale_scan_slots_riyadh(target_date=None):
    now_riyadh = datetime.now(RIYADH_TZ)
    if target_date is None:
        target_date = now_riyadh.date()
    return [datetime(target_date.year, target_date.month, target_date.day, hh, mm, tzinfo=RIYADH_TZ) for hh, mm in WHALE_SLOT_TIMES_RIYADH]

def get_friday_zero_hero_slots_riyadh(target_date=None):
    now_riyadh = datetime.now(RIYADH_TZ)
    if target_date is None:
        target_date = now_riyadh.date()

    raw_times = [(16, 45), (17, 0), (17, 15), (17, 45), (18, 15), (19, 0)]
    return [datetime(target_date.year, target_date.month, target_date.day, hh, mm, tzinfo=RIYADH_TZ) for hh, mm in raw_times]

def get_active_watchlist(now_riyadh=None):
    now_riyadh = now_riyadh or datetime.now(RIYADH_TZ)
    if now_riyadh.weekday() == 4 and FRIDAY_ZERO_HERO_ENABLED:
        return FRIDAY_ZERO_HERO_TICKERS
    return WATCHLIST

def get_due_scanner_slot_key(now_riyadh=None):
    now_riyadh = now_riyadh or datetime.now(RIYADH_TZ)

    if now_riyadh.weekday() >= 5:
        return None

    slots = get_friday_zero_hero_slots_riyadh(now_riyadh.date()) if (now_riyadh.weekday() == 4 and FRIDAY_ZERO_HERO_ENABLED) else get_regular_scan_slots_riyadh(now_riyadh.date())

    for slot in slots:
        diff = (now_riyadh - slot).total_seconds()
        if 0 <= diff <= 70:
            return slot.strftime('%Y-%m-%d %H:%M')
    return None

def get_due_whale_slot_key(now_riyadh=None):
    now_riyadh = now_riyadh or datetime.now(RIYADH_TZ)
    if (not WHALE_CONTRACTS_ENABLED) or now_riyadh.weekday() >= 5:
        return None
    for slot in get_whale_scan_slots_riyadh(now_riyadh.date()):
        diff = (now_riyadh - slot).total_seconds()
        if 0 <= diff <= 70:
            return slot.strftime('%Y-%m-%d %H:%M')
    return None

def parse_float(x, default=None):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default

def round_price(x):
    try:
        return round(float(x), 2)
    except Exception:
        return x

# =========================
# FMP API (الأخبار الاقتصادية)
# =========================

def fmp_get(path: str, params=None):
    params = params or {}
    params["apikey"] = FMP_API_KEY
    url = f"{FMP_BASE}{path}"

    try:
        r = HTTP.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[FMP ERROR] {e}")
        return []

# =========================
# جلب الأخبار الاقتصادية
# =========================

def get_economic_calendar():
    cache_key = "econ_calendar"

    cached = get_cached_item(ECON_CACHE, ECON_CACHE_TTL_SECONDS, cache_key)
    if cached:
        return cached

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")

        data = fmp_get("/economic-calendar", {
            "from": today,
            "to": future
        })

        if not isinstance(data, list) or not data:
            data = fmp_get("/economic_calendar", {
                "from": today,
                "to": future
            })

        if isinstance(data, list):
            set_cached_item(ECON_CACHE, cache_key, data)
            return data

        return []

    except Exception as e:
        print(f"[ECON FETCH ERROR] {e}")
        return []

# =========================
# فلترة الأخبار المهمة
# =========================

def is_important_event(event_name: str):
    if not event_name:
        return False

    name = event_name.lower()

    for keyword in IMPORTANT_EVENT_KEYWORDS:
        if keyword in name:
            return True

    return False

# =========================
# تنسيق الخبر
# =========================

def format_econ_event(event):
    name = event.get("event", "خبر")
    country = event.get("country", "")
    impact = event.get("impact", "")

    date_str = event.get("date", "")
    time_str = event.get("time", "")

    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
        dt_riyadh = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(RIYADH_TZ)
        time_display = dt_riyadh.strftime("%H:%M")
    except:
        time_display = time_str

    impact_emoji = "🔥" if impact == "High" else "⚠️" if impact == "Medium" else "ℹ️"

    return f"{impact_emoji} {name}\n🌍 {country} | ⏰ {time_display}"

# =========================
# تنبيه قبل الخبر
# =========================

def check_economic_news_alerts():
    if not ECON_NEWS_ALERT_ENABLED:
        return

    events = get_economic_calendar()
    now = datetime.now(ZoneInfo("UTC"))

    for event in events:
        try:
            name = event.get("event", "")
            if ECON_NEWS_ONLY_IMPORTANT and not is_important_event(name):
                continue

            date_str = event.get("date", "")
            time_str = event.get("time", "")

            if not date_str or not time_str:
                continue

            event_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
            event_dt = event_dt.replace(tzinfo=ZoneInfo("UTC"))

            alert_time = event_dt - timedelta(minutes=ECON_NEWS_ALERT_MINUTES_BEFORE)

            event_id = f"{name}_{event_dt}"

            if event_id in ECON_ALERT_SENT:
                continue

            if alert_time <= now <= event_dt:
                msg = f"""🚨 <b>تنبيه خبر اقتصادي</b>

{format_econ_event(event)}

⏳ بعد {ECON_NEWS_ALERT_MINUTES_BEFORE} دقائق

⚠️ السوق قد يكون متذبذب
"""

                send(msg, chat_id=CHAT_ID)
                ECON_ALERT_SENT.add(event_id)

        except Exception as e:
            print(f"[ECON ALERT ERROR] {e}")

# =========================
# حلقة الأخبار الاقتصادية
# =========================

async def econ_news_loop():
    await asyncio.sleep(15)

    while True:
        try:
            await asyncio.to_thread(check_economic_news_alerts)
        except Exception as e:
            print(f"[ECON LOOP ERROR] {e}")

        await asyncio.sleep(60)
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

def strip_html_tags(text_value):
    try:
        import re
        return re.sub(r"<[^>]+>", "", str(text_value or "")).replace("&nbsp;", " ").strip()
    except Exception:
        return str(text_value or "").strip()

def get_stock_news(ticker: str, limit: int = 3):
    key = f"news:{ticker}:{limit}"
    cached = get_cached_item(NEWS_CACHE, NEWS_CACHE_TTL_SECONDS, key)
    if cached is not None:
        return cached

    rows = []
    try:
        data = massive_get("/v2/reference/news", params={"ticker": ticker, "limit": max(limit, 1), "order": "desc", "sort": "published_utc"})
        rows = data.get("results", []) or []
    except Exception as e:
        print(f"[NEWS ERROR] {ticker}: {e}")
        rows = []

    cleaned = []
    for item in rows[:limit]:
        title = strip_html_tags(item.get("title") or item.get("headline") or item.get("description") or "")
        published = item.get("published_utc") or item.get("publishedAt") or item.get("published") or ""
        publisher = safe_get(item, "publisher", "name", default="") or item.get("publisher") or ""
        if title:
            cleaned.append({
                "title": title,
                "published": published,
                "publisher": strip_html_tags(publisher),
            })

    set_cached_item(NEWS_CACHE, key, cleaned)
    return cleaned

def format_news_brief(news_rows):
    if not news_rows:
        return "لا توجد أخبار حديثة"

    parts = []
    for item in news_rows[:2]:
        title = strip_html_tags(item.get("title", ""))
        published = str(item.get("published", ""))
        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(RIYADH_TZ)
            published_label = dt.strftime("%d/%m %H:%M")
        except Exception:
            published_label = published[:16] if published else ""

        publisher = item.get("publisher", "")
        line = title
        extra = " | ".join([x for x in [publisher, published_label] if x])
        if extra:
            line += f" ({extra})"
        parts.append(f"• {line}")

    return "\n".join(parts) if parts else "لا توجد أخبار حديثة"

def format_earnings_brief(event):
    if not event:
        return "لا يوجد إعلان قريب هذا الأسبوع"

    date_str = event.get("date") or "غير محدد"
    session_label = event.get("session_label") or classify_earnings_session(event.get("time", ""), event)
    eps_est = event.get("eps_estimate") or event.get("eps") or event.get("epsEstimated") or ""
    rev_est = event.get("revenue_estimate") or event.get("revenue") or event.get("revenueEstimated") or ""

    extra = []
    if eps_est not in [None, ""]:
        extra.append(f"EPS: {eps_est}")
    if rev_est not in [None, ""]:
        extra.append(f"Rev: {rev_est}")

    suffix = f" | {' | '.join(extra)}" if extra else ""
    return f"{format_arabic_date(date_str)} | {session_label}{suffix}"

def safe_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur

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

def get_option_aggregate_bars(option_ticker: str, days: int = CONTRACT_TARGET_LOOKBACK_DAYS):
    try:
        to_date = datetime.now(MARKET_TZ).date()
        from_date = to_date - timedelta(days=days)
        data = massive_get(
            f"/v2/aggs/ticker/{option_ticker}/range/1/hour/{from_date.strftime('%Y-%m-%d')}/{to_date.strftime('%Y-%m-%d')}",
            params={"adjusted": "true", "sort": "asc", "limit": 5000}
        )
        return data.get("results", []) or []
    except Exception as e:
        print(f"[OPTION BARS ERROR] {option_ticker}: {e}")
        return []

# =========================
# أدوات خاصة بالعقود
# =========================

def is_spac_ticker(ticker: str) -> bool:
    return ticker in SPAC_TICKERS

def is_friday_now() -> bool:
    return datetime.now(RIYADH_TZ).weekday() == 4

def contract_price_limit_for_ticker(ticker: str) -> float:
    return MAX_SPAC_CONTRACT_PRICE if is_spac_ticker(ticker) else MAX_COMPANY_CONTRACT_PRICE

def days_to_expiry(expiration_str: str):
    try:
        exp = datetime.strptime(expiration_str, "%Y-%m-%d").date()
        return (exp - datetime.now().date()).days
    except Exception:
        return None

def derive_dynamic_target_fallbacks(contract_price: float):
    tp1 = round_price(contract_price + CONTRACT_TP1_ADD)

    dynamic_add_2 = max(contract_price * 0.35, 0.90)
    dynamic_add_3 = max(contract_price * 0.65, 1.50)

    tp2 = round_price(contract_price + dynamic_add_2)
    tp3 = round_price(contract_price + dynamic_add_3)

    if tp2 <= tp1:
        tp2 = round_price(tp1 + 0.25)
    if tp3 <= tp2:
        tp3 = round_price(tp2 + 0.35)

    return tp1, tp2, tp3

def derive_contract_targets_from_chart(option_ticker: str, contract_price: float):
    tp1, fallback_tp2, fallback_tp3 = derive_dynamic_target_fallbacks(contract_price)

    bars = get_option_aggregate_bars(option_ticker, CONTRACT_TARGET_LOOKBACK_DAYS)
    if not bars:
        return tp1, fallback_tp2, fallback_tp3

    highs = []
    swings = []

    for bar in bars:
        h = parse_float(bar.get("h"))
        if h is not None and h > contract_price:
            highs.append(round(h, 2))

    for i in range(1, len(bars) - 1):
        prev_h = parse_float(bars[i - 1].get("h"))
        cur_h = parse_float(bars[i].get("h"))
        next_h = parse_float(bars[i + 1].get("h"))
        if prev_h is None or cur_h is None or next_h is None:
            continue
        if cur_h > contract_price and cur_h >= prev_h and cur_h >= next_h:
            swings.append(round(cur_h, 2))

    candidates = sorted(set(swings or highs))

    min_tp2 = max(tp1 + CONTRACT_TARGET_MIN_GAP, round_price(contract_price + max(contract_price * 0.22, 0.55)))
    min_tp3 = max(min_tp2 + CONTRACT_TARGET_MIN_GAP, round_price(contract_price + max(contract_price * 0.40, 0.95)))

    tp2 = next((x for x in candidates if x >= min_tp2), None)
    if tp2 is None:
        tp2 = fallback_tp2

    tp3 = next((x for x in candidates if x > tp2 and x >= min_tp3), None)
    if tp3 is None:
        if highs:
            mx = max(highs)
            tp3 = mx if mx > tp2 else fallback_tp3
        else:
            tp3 = fallback_tp3

    if tp2 <= tp1:
        tp2 = round_price(tp1 + CONTRACT_TARGET_MIN_GAP)
    if tp3 <= tp2:
        tp3 = round_price(tp2 + max(CONTRACT_TARGET_MIN_GAP, 0.20))

    return round_price(tp1), round_price(tp2), round_price(tp3)

def build_contract_from_pick(best, c, target_type, mode="NORMAL"):
    contract_price = round(float(best["contract_price"]), 2)
    tp1, tp2, tp3 = derive_contract_targets_from_chart(best["ticker"], contract_price)
    return {
        "option_ticker": best["ticker"],
        "strike": round(best["strike"], 2),
        "expiration": best["expiration"],
        "contract_type": best["contract_type"],
        "contract_price": contract_price,
        "entry_high": contract_price,
        "entry_low": round(max(0.10, contract_price - ENTRY_ZONE_WIDTH), 2),
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
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
    if df_1h.empty or len(df_1h) < 1:
        return "neutral"

    last_close = float(df_1h["Close"].iloc[-1])

    if last_close > pivot:
        side = "above"
    elif last_close < pivot:
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
    call_tp3 = ref_high + ref_range

    put_tp1 = pivot - ref_range * 0.5
    put_tp2 = pivot - ref_range
    put_tp3 = ref_low - ref_range

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

# =========================
# القاما والسيولة
# =========================

def options_info_from_massive(ticker, price):
    try:
        chain = get_option_chain_snapshot(ticker)
        if not chain:
            raise Exception("empty chain")

        parsed = [parse_contract_meta(x) for x in chain]
        parsed = [x for x in parsed if x["ticker"] and x["contract_price"] is not None]

        if not parsed:
            raise Exception("no valid contracts")

        calls = [x for x in parsed if x["contract_type"] == "call"]
        puts = [x for x in parsed if x["contract_type"] == "put"]

        best_call_oi = max(calls, key=lambda x: x["oi"]) if calls else None
        best_put_oi = max(puts, key=lambda x: x["oi"]) if puts else None

        call_strike = best_call_oi["strike"] if best_call_oi else price
        put_strike = best_put_oi["strike"] if best_put_oi else price

        gamma = best_call_oi["strike"] if best_call_oi else price
        zone_low = gamma - 0.5
        zone_high = gamma + 0.5

        dist = abs(price - gamma)
        prob = max(50, 85 - int(dist))

        liquidity = "CALL 🟢" if call_strike > price else "PUT 🔴"

        return {
            "call": call_strike,
            "put": put_strike,
            "gamma": gamma,
            "zlow": zone_low,
            "zhigh": zone_high,
            "prob": prob,
            "liq": liquidity,
        }
    except Exception as e:
        print(f"[OPTIONS INFO ERROR] {ticker}: {e}")
        return {
            "call": price, "put": price, "gamma": price,
            "zlow": price, "zhigh": price, "prob": 50, "liq": "—",
        }

# =========================
# نسبة النجاح
# =========================

def calc_success_rate(c: dict, o: dict, contract: dict):
    return min(92, max(55, int(
        55
        + (10 if c["strongest_trend"] in ["صاعد قوي 🔥", "هابط قوي 🔻"] else 0)
        + (10 if c["direction"] != "انتظار ⚪" else 0)
        + (8 if abs(c["pivot_diff"]) > 0 else 0)
        + (5 if contract["oi"] > 1000 else 0)
        + (4 if abs(contract["delta"]) >= 0.20 else 0)
        + (5 if o["prob"] >= 65 else 0)
    )))
# =========================
# اختيار العقد
# =========================

def choose_best_contract_from_massive(ticker: str, c: dict, o: dict = None):
    try:
        chain = get_option_chain_snapshot(ticker)
        if not chain:
            return None

        parsed = [parse_contract_meta(x) for x in chain]
        parsed = [x for x in parsed if x["ticker"] and x["contract_price"] is not None]

        if not parsed:
            return None

        direction = c["direction"]
        if direction.startswith("CALL"):
            target_type = "call"
        else:
            target_type = "put"

        underlying_price = c["price"]
        prob = o["prob"] if o else 50
        limit_price = contract_price_limit_for_ticker(ticker)

        friday_mode = (
            FRIDAY_ZERO_HERO_ENABLED
            and ((ZERO_HERO_ONLY_ON_FRIDAY and is_friday_now()) or (not ZERO_HERO_ONLY_ON_FRIDAY))
        )

        if friday_mode and c["strongest_trend"] in ["صاعد قوي 🔥", "هابط قوي 🔻"] and prob >= ZERO_HERO_MIN_PROB:
            zero_hero_pool = []
            for x in parsed:
                if x["contract_type"] != target_type:
                    continue
                if not x["expiration"]:
                    continue
                if x["contract_price"] is None or x["contract_price"] <= 0:
                    continue
                if not (ZERO_HERO_MIN_PRICE <= x["contract_price"] <= ZERO_HERO_MAX_PRICE):
                    continue
                if x["oi"] < ZERO_HERO_MIN_OI:
                    continue
                dte = days_to_expiry(x["expiration"])
                if dte is None or dte != 0:
                    continue
                strike_distance_pct = abs(x["strike"] - underlying_price) / max(underlying_price, 1e-9)
                delta_score = abs(abs(x["delta"]) - 0.30)
                score = (
                    strike_distance_pct * 18
                    + delta_score * 5
                    - min(x["oi"], 100000) / 12000
                    - min(abs(x["gamma"]), 1.0) * 6
                    + abs(x["contract_price"] - 1.00) * 0.6
                )
                zero_hero_pool.append((score, x))

            if zero_hero_pool:
                zero_hero_pool.sort(key=lambda z: z[0])
                best = zero_hero_pool[0][1]
                contract = build_contract_from_pick(best, c, target_type, mode="ZERO HERO FRIDAY")
                success_rate = calc_success_rate(c, o or {"prob": 50}, contract)
                if success_rate >= ZERO_HERO_MIN_SUCCESS_RATE:
                    contract["success_rate"] = success_rate
                    return contract

        stage1 = []
        for x in parsed:
            if x["contract_type"] != target_type:
                continue
            if not x["expiration"]:
                continue
            if x["contract_price"] is None or x["contract_price"] <= 0:
                continue
            if x["contract_price"] > limit_price:
                continue

            dte = days_to_expiry(x["expiration"])

            if ticker in INDEX_TICKERS or is_spac_ticker(ticker):
                if dte is None or dte < 0 or dte > INDEX_MAX_DTE_DAYS:
                    continue
            else:
                if dte is None or dte < MIN_DTE_DAYS or dte > MAX_DTE_DAYS:
                    continue

            if x["oi"] < 10:
                continue
            strike_distance_pct = abs(x["strike"] - underlying_price) / max(underlying_price, 1e-9)
            delta_score = abs(abs(x["delta"]) - 0.35)
            dte_penalty = min(max(dte, 0), 45) / 25
            score = (
                strike_distance_pct * 22
                + delta_score * 5
                + dte_penalty
                - min(x["oi"], 100000) / 15000
                - min(abs(x["gamma"]), 1.0) * 4
                + abs(x["contract_price"] - limit_price) * 0.10
            )
            stage1.append((score, x))

        if stage1:
            stage1.sort(key=lambda z: z[0])
            best = stage1[0][1]
            contract = build_contract_from_pick(best, c, target_type, mode="NORMAL")
            contract["success_rate"] = calc_success_rate(c, o or {"prob": 50}, contract)
            return contract

        stage2 = []
        for x in parsed:
            if x["contract_type"] != target_type:
                continue
            if not x["expiration"]:
                continue
            if x["contract_price"] is None or x["contract_price"] <= 0:
                continue
            if x["contract_price"] > limit_price:
                continue

            dte = days_to_expiry(x["expiration"])

            if ticker in INDEX_TICKERS or is_spac_ticker(ticker):
                if dte is None or dte < 0 or dte > INDEX_MAX_DTE_DAYS:
                    continue
            else:
                if dte is None or dte < MIN_DTE_DAYS or dte > MAX_DTE_DAYS:
                    continue

            score = (
                abs(x["contract_price"] - limit_price) * 1.5
                - min(x["oi"], 100000) / 20000
                + min(max(dte, 0), 60) / 40
            )
            stage2.append((score, x))

        if stage2:
            stage2.sort(key=lambda z: z[0])
            best = stage2[0][1]
            contract = build_contract_from_pick(best, c, target_type, mode="NORMAL")
            contract["success_rate"] = calc_success_rate(c, o or {"prob": 50}, contract)
            return contract

        stage3 = []
        for x in parsed:
            if x["contract_type"] != target_type:
                continue
            if not x["expiration"]:
                continue
            if x["contract_price"] is None or x["contract_price"] <= 0:
                continue

            dte = days_to_expiry(x["expiration"])

            if ticker in INDEX_TICKERS or is_spac_ticker(ticker):
                if dte is None or dte < 0 or dte > INDEX_MAX_DTE_DAYS:
                    continue
            else:
                if dte is None or dte < MIN_DTE_DAYS or dte > MAX_DTE_DAYS:
                    continue

            strike_distance_pct = abs(x["strike"] - underlying_price) / max(underlying_price, 1e-9)
            score = strike_distance_pct * 10 - min(x["oi"], 100000) / 20000
            stage3.append((score, x))

        if stage3:
            stage3.sort(key=lambda z: z[0])
            best = stage3[0][1]
            contract = build_contract_from_pick(best, c, target_type, mode="BEST AVAILABLE")
            contract["success_rate"] = calc_success_rate(c, o or {"prob": 50}, contract)
            return contract

        return None

    except Exception as e:
        print(f"[CONTRACT PICK ERROR] {ticker}: {e}")
        return None


def calc_rsi_from_close(close_series, length=14):
    try:
        delta = close_series.diff()
        gain = delta.clip(lower=0).rolling(length).mean()
        loss = (-delta.clip(upper=0)).rolling(length).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1])
    except Exception:
        return 50.0

def calc_atr_from_df(df, length=14):
    try:
        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        close = df["Close"].astype(float)
        prev_close = close.shift(1)
        tr = pd.concat([
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(length).mean()
    except Exception:
        return pd.Series(dtype=float)

def get_us500_whale_bias():
    try:
        df_m = get_df("US500", "1h")
        if df_m.empty or len(df_m) < 60:
            return "NEUTRAL"
        close = df_m["Close"].astype(float)
        ema20 = float(close.ewm(span=20).mean().iloc[-1])
        ema50 = float(close.ewm(span=50).mean().iloc[-1])
        last = float(close.iloc[-1])
        if last > ema20 > ema50:
            return "CALL"
        if last < ema20 < ema50:
            return "PUT"
        return "NEUTRAL"
    except Exception:
        return "NEUTRAL"

def detect_whale_explosion_setup(df, ticker: str, base_c: dict, market_bias: str = "NEUTRAL"):
    """
    قناص الحيتان المطور:
    يبحث عن تجميع + قرب مستوى مهم + ارتفاع فوليوم + ضغط ATR + توافق السوق.
    يرجع setup مستقل للـ whale فقط ولا يغير منطق الطرح العادي.
    """
    try:
        if df is None or df.empty or len(df) < max(60, WHALE_STRUCTURE_BARS + 5):
            return None

        close = df["Close"].astype(float)
        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        volume = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series([0] * len(df), index=df.index)

        price = float(close.iloc[-1])
        recent_close = close.tail(WHALE_CONSOLIDATION_BARS)
        recent_high = float(high.tail(WHALE_CONSOLIDATION_BARS).max())
        recent_low = float(low.tail(WHALE_CONSOLIDATION_BARS).min())
        structure_high = float(high.tail(WHALE_STRUCTURE_BARS).max())
        structure_low = float(low.tail(WHALE_STRUCTURE_BARS).min())
        structure_range = max(structure_high - structure_low, 1e-9)

        consolidation_range_pct = (recent_high - recent_low) / max(price, 1e-9)
        consolidation_ok = consolidation_range_pct <= WHALE_MAX_CONSOLIDATION_RANGE_PCT

        atr_series = calc_atr_from_df(df, 14)
        if atr_series.empty or atr_series.dropna().empty:
            atr_now = 0.0
            atr_avg = 0.0
            atr_compression_ok = False
        else:
            atr_now = float(atr_series.iloc[-1])
            atr_avg = float(atr_series.tail(30).mean())
            atr_compression_ok = atr_avg > 0 and atr_now <= atr_avg * WHALE_ATR_COMPRESSION_MULT

        last_vol = float(volume.iloc[-1])
        vol3 = float(volume.tail(3).mean())
        prev_vol10 = float(volume.iloc[-13:-3].mean()) if len(volume) >= 13 else float(volume.tail(10).mean())
        volume_spike_ok = prev_vol10 > 0 and last_vol >= prev_vol10 * WHALE_VOLUME_SPIKE_MULT
        volume_rising_ok = prev_vol10 > 0 and vol3 >= prev_vol10 * WHALE_VOLUME_RISING_MULT

        rsi = calc_rsi_from_close(close, 14)
        prev_rsi = calc_rsi_from_close(close.iloc[:-1], 14) if len(close) > 20 else rsi

        dist_to_resistance = abs(structure_high - price) / max(price, 1e-9)
        dist_to_support = abs(price - structure_low) / max(price, 1e-9)
        near_resistance = dist_to_resistance <= WHALE_NEAR_LEVEL_PCT
        near_support = dist_to_support <= WHALE_NEAR_LEVEL_PCT

        range_position = (price - structure_low) / structure_range
        bottom_zone = range_position <= 0.30
        top_zone = range_position >= 0.70

        # تحديد الاتجاه الذكي للحيتان: قاع = CALL / قمة = PUT / اختراق مقاومة = CALL / كسر دعم = PUT
        if bottom_zone or (near_resistance and (volume_rising_ok or volume_spike_ok) and rsi >= 48):
            direction_type = "call"
            direction = "CALL 🟢"
            trigger_level = structure_high if near_resistance else structure_low
            level_name = "قاع تجميع" if bottom_zone else "مقاومة قبل الانفجار"
        elif top_zone or (near_support and (volume_rising_ok or volume_spike_ok) and rsi <= 52):
            direction_type = "put"
            direction = "PUT 🔴"
            trigger_level = structure_low if near_support else structure_high
            level_name = "قمة تصريف" if top_zone else "دعم قبل الكسر"
        else:
            return None

        score = 0

        # Volume = 25
        if volume_spike_ok:
            score += 25
        elif volume_rising_ok:
            score += 18

        # RSI = 20
        if direction_type == "call":
            if 48 <= rsi <= 68 and rsi >= prev_rsi:
                score += 20
            elif rsi >= 45:
                score += 12
        else:
            if 32 <= rsi <= 52 and rsi <= prev_rsi:
                score += 20
            elif rsi <= 55:
                score += 12

        # قرب من مستوى مهم = 20
        if near_resistance or near_support or bottom_zone or top_zone:
            score += 20

        # تجميع + ضغط ATR = 20
        if consolidation_ok and atr_compression_ok:
            score += 20
        elif consolidation_ok or atr_compression_ok:
            score += 12

        # توافق US500 = 15
        if market_bias == "NEUTRAL":
            score += 7
        elif market_bias == ("CALL" if direction_type == "call" else "PUT"):
            score += 15

        reasons = []
        if consolidation_ok:
            reasons.append("تجميع واضح")
        if atr_compression_ok:
            reasons.append("ضغط ATR")
        if volume_spike_ok:
            reasons.append("فوليوم انفجاري")
        elif volume_rising_ok:
            reasons.append("فوليوم يرتفع")
        if near_resistance:
            reasons.append("قرب مقاومة")
        if near_support:
            reasons.append("قرب دعم")
        if bottom_zone:
            reasons.append("منطقة قاع")
        if top_zone:
            reasons.append("منطقة قمة")
        if market_bias != "NEUTRAL":
            reasons.append(f"US500 {market_bias}")

        setup = {
            "direction": direction,
            "direction_type": direction_type,
            "explosion_score": int(min(100, score)),
            "rsi": round(rsi, 2),
            "consolidation_range_pct": round(consolidation_range_pct * 100, 2),
            "atr_now": round(atr_now, 4),
            "atr_avg": round(atr_avg, 4),
            "volume_spike": bool(volume_spike_ok),
            "volume_rising": bool(volume_rising_ok),
            "near_resistance": bool(near_resistance),
            "near_support": bool(near_support),
            "bottom_zone": bool(bottom_zone),
            "top_zone": bool(top_zone),
            "trigger_level": round(float(trigger_level), 2),
            "level_name": level_name,
            "reasons": " + ".join(reasons) if reasons else "إعداد حيتان"
        }

        if setup["explosion_score"] < WHALE_MIN_EXPLOSION_SCORE:
            return None

        enhanced_c = dict(base_c)
        enhanced_c["direction"] = direction
        enhanced_c["whale_setup"] = setup
        return enhanced_c

    except Exception as e:
        print(f"[WHALE SETUP ERROR] {ticker}: {e}")
        return None


def choose_whale_contract_from_massive(ticker: str, c: dict, o: dict = None):
    try:
        chain = get_option_chain_snapshot(ticker)
        if not chain:
            return None

        parsed = [parse_contract_meta(x) for x in chain]
        parsed = [x for x in parsed if x["ticker"] and x["contract_price"] is not None]
        if not parsed:
            return None

        whale_setup = c.get("whale_setup", {}) or {}
        direction = c.get("direction", "")
        target_type = whale_setup.get("direction_type") or ("call" if direction.startswith("CALL") else "put")
        underlying_price = c.get("price", 0) or 0

        pool = []
        for x in parsed:
            if x["contract_type"] != target_type:
                continue
            if not x["expiration"]:
                continue
            if x["contract_price"] is None or not (WHALE_MIN_PRICE <= x["contract_price"] <= WHALE_MAX_PRICE):
                continue
            dte = days_to_expiry(x["expiration"])
            if dte is None or dte < WHALE_MIN_DTE_DAYS or dte > WHALE_MAX_DTE_DAYS:
                continue
            if x["oi"] < WHALE_MIN_OI:
                continue

            option_key = x.get("ticker")
            if WHALE_LAST_SENT_CONTRACT.get(option_key) == datetime.now(RIYADH_TZ).date().isoformat():
                continue

            strike_distance_pct = abs(x["strike"] - underlying_price) / max(underlying_price, 1e-9)
            delta_score = abs(abs(x["delta"]) - 0.30)
            volume = _safe_float(x.get("volume", x.get("vol", 0)))
            score = (
                strike_distance_pct * 18
                + delta_score * 5
                + abs(x["contract_price"] - 1.00) * 0.6
                - min(x["oi"], 100000) / 12000
                - min(volume, 50000) / 10000
                - min(abs(x["gamma"]), 1.0) * 4
            )
            pool.append((score, x))

        if not pool:
            return None

        pool.sort(key=lambda z: z[0])
        best = pool[0][1]
        contract = build_contract_from_pick(best, c, target_type, mode="WHALE EXPLOSION")
        contract["entry_low"] = max(WHALE_MIN_PRICE, round(contract["entry_high"] - WHALE_ENTRY_ZONE_WIDTH, 2))
        contract["success_rate"] = calc_success_rate(c, o or {"prob": 50}, contract)
        whale_setup = c.get("whale_setup", {}) or {}
        contract["explosion_score"] = whale_setup.get("explosion_score", contract["success_rate"])
        contract["whale_reasons"] = whale_setup.get("reasons", "إعداد حيتان")
        contract["whale_level_name"] = whale_setup.get("level_name", "منطقة حيتان")
        contract["whale_trigger_level"] = whale_setup.get("trigger_level", c.get("pivot", 0))
        contract["whale_rsi"] = whale_setup.get("rsi", 50)
        contract["whale_consolidation_range_pct"] = whale_setup.get("consolidation_range_pct", 0)
        return contract

    except Exception as e:
        print(f"[WHALE CONTRACT PICK ERROR] {ticker}: {e}")
        return None

# =========================
# فلترة الصياد
# =========================

def calc_score(c, o):
    score = 0
    if c["direction"].startswith("CALL") or c["direction"].startswith("PUT"):
        score += 35
    if c["strongest_trend"] in ["صاعد قوي 🔥", "هابط قوي 🔻"]:
        score += 25
    if abs(c["pivot_diff"]) > 0:
        score += 10
    if o["prob"] >= 60:
        score += 15
    if c["trend"] == "صاعد 📈" and c["direction"].startswith("CALL"):
        score += 10
    if c["trend"] == "هابط 📉" and c["direction"].startswith("PUT"):
        score += 10
    return score

def is_entry_ready_now(c):
    if c["direction"] == "انتظار ⚪":
        return False

    price = c["price"]
    entry = c["best_entry"]
    near_entry = abs(price - entry) / max(entry, 1e-9) <= ENTRY_MAX_DISTANCE_PCT

    breakout_call = (
        c["direction"].startswith("CALL")
        and price >= c["best_entry"] * (1 - BREAKOUT_BUFFER_PCT)
        and c["confirmed_side"] == "above"
    )

    breakout_put = (
        c["direction"].startswith("PUT")
        and price <= c["best_entry"] * (1 + BREAKOUT_BUFFER_PCT)
        and c["confirmed_side"] == "below"
    )

    return near_entry or breakout_call or breakout_put

# =========================
# تنسيق التاريخ
# =========================

def format_arabic_date(date_str: str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        months = {
            1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
            7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"
        }
        return f"{dt.day} {months[dt.month]} {dt.year}"
    except Exception:
        return date_str

def format_short_date(date_str: str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%d/%m")
    except Exception:
        return date_str

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



# =========================
# صور الطرح والتحديث
# =========================

def _img_font(size: int, bold: bool = False):
    try:
        from PIL import ImageFont
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
        for path in candidates:
            if os.path.exists(path):
                return ImageFont.truetype(path, size=size)
        return ImageFont.load_default()
    except Exception:
        return None

def _contract_type_en(row: dict):
    return "Call" if row.get("contract_type") == "call" else "Put"

def _format_option_header(row: dict):
    ticker = row.get("ticker", "—")
    strike = float(row.get("strike", 0) or 0)
    exp = row.get("expiration", "")
    try:
        exp_dt = datetime.strptime(exp, "%Y-%m-%d")
        exp_txt = exp_dt.strftime("%d %b %y")
    except Exception:
        exp_txt = str(exp)
    return f"{ticker} ${strike:g}", f"{exp_txt}  {_contract_type_en(row)}"

def build_contract_image(row: dict, is_update: bool = False):
    """صورة بسيطة جداً مثل شاشة عقد الأوبشن. تفاصيل الطرح تبقى في الكابشن فقط."""
    try:
        from PIL import Image, ImageDraw
    except Exception as e:
        print(f"[IMAGE ERROR] Pillow غير متوفر: {e}")
        return None

    width, height = 1080, 1080
    bg = (8, 13, 24)
    panel = (13, 21, 36)
    line = (34, 48, 72)
    white = (245, 247, 250)
    muted = (148, 163, 184)
    green = (28, 199, 130)
    red = (255, 77, 109)
    orange = (255, 145, 43)

    is_call = row.get("contract_type") == "call"
    accent = green if is_call else red

    entry = float(row.get("entry_price", row.get("contract_price", 0)) or 0)
    current = float(row.get("current_price", entry) or entry)
    high = float(row.get("highest_price", current) or current)
    display_price = high if is_update else current
    pnl = ((display_price - entry) / entry) * 100 if entry > 0 else 0
    change_abs = display_price - entry if is_update else 0
    change_color = green if pnl >= 0 else red

    title1, title2 = _format_option_header(row)
    option_ticker = str(row.get("option_ticker", ""))
    oi = row.get("oi", "—")
    vol = row.get("volume", row.get("vol", "—"))
    mid = row.get("mid", row.get("contract_price", entry))

    f_logo = _img_font(34, True)
    f_title = _img_font(54, True)
    f_sub = _img_font(34, False)
    f_price = _img_font(150, True)
    f_change = _img_font(42, True)
    f_label = _img_font(34, False)
    f_value = _img_font(36, True)
    f_small = _img_font(27, False)

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((46, 46, width-46, height-46), radius=46, fill=panel, outline=line, width=2)

    draw.text((78, 78), "OPTION STRIKE", fill=orange, font=f_logo)
    pill = "UPDATE" if is_update else "LIVE OPTION"
    pill_fill = (18, 40, 34) if is_call else (48, 22, 32)
    draw.rounded_rectangle((780, 74, 1000, 126), radius=22, fill=pill_fill, outline=accent, width=2)
    draw.text((812, 84), pill, fill=accent, font=f_small)

    draw.text((78, 180), title1, fill=white, font=f_title)
    draw.text((78, 248), title2, fill=muted, font=f_sub)
    draw.text((78, 385), f"{display_price:.2f}", fill=accent if is_update else white, font=f_price)

    if is_update:
        draw.text((84, 555), f"{change_abs:+.2f}   {pnl:+.2f}%", fill=change_color, font=f_change)
        status = "WINNING" if pnl >= 0 else "LOSING"
        draw.rounded_rectangle((78, 625, 350, 685), radius=22, fill=(9, 14, 25), outline=change_color, width=2)
        draw.text((110, 637), status, fill=change_color, font=f_label)
    else:
        draw.text((84, 555), "Clean setup • details in caption", fill=muted, font=f_change)

    y = 735
    stats = [("Mid", mid), ("Open Int.", oi), ("Vol.", vol)]
    if is_update:
        stats = [("Entry", entry), ("High", high), ("PnL", f"{pnl:+.2f}%")]
    for label, value in stats:
        draw.text((90, y), str(label), fill=muted, font=f_label)
        value_txt = f"{value:.2f}" if isinstance(value, float) else str(value)
        draw.text((690, y), value_txt, fill=white, font=f_value)
        y += 70

    draw.line((78, 950, 1002, 950), fill=line, width=2)
    footer = option_ticker[:55] if option_ticker else "@Option_Strike01"
    draw.text((78, 978), footer, fill=muted, font=f_small)
    draw.text((805, 978), "@Option_Strike01", fill=orange, font=f_small)

    bio = io.BytesIO()
    bio.name = f"{row.get('ticker','OPTION')}_{'update' if is_update else 'new'}.png"
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio

def send_contract_image(row: dict, caption: str = "", keyboard=None, chat_id=None):
    target_chat_id = str(chat_id) if chat_id else CHAT_ID
    photo = build_contract_image(row, is_update=False)
    if photo is None:
        return send(caption, keyboard=keyboard, chat_id=target_chat_id)
    data = {"chat_id": target_chat_id, "caption": caption, "parse_mode": "HTML"}
    if keyboard:
        data["reply_markup"] = json.dumps(keyboard)
    try:
        r = HTTP.post(API_SEND_PHOTO, data=data, files={"photo": photo}, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[SEND PHOTO ERROR] {e}")
        return send(caption, keyboard=keyboard, chat_id=target_chat_id)

def edit_contract_image(row: dict, caption: str = "", chat_id=None):
    target_chat_id = str(chat_id) if chat_id else CHAT_ID
    message_id = row.get("message_id")
    if not message_id:
        return send_contract_image(row, caption=caption, chat_id=target_chat_id)
    photo = build_contract_image(row, is_update=True)
    if photo is None:
        return send(caption, chat_id=target_chat_id)
    media = {"type": "photo", "media": "attach://photo", "caption": caption, "parse_mode": "HTML"}
    data = {"chat_id": target_chat_id, "message_id": message_id, "media": json.dumps(media)}
    try:
        r = HTTP.post(API_EDIT_MEDIA, data=data, files={"photo": photo}, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[EDIT PHOTO ERROR] {e}")
        return send_contract_image(row, caption=caption, chat_id=target_chat_id)


def _report_stats(rows: list):
    st = {"total": len(rows), "wins": 0, "losses": 0, "calls": 0, "puts": 0, "tp1": 0, "tp2": 0, "tp3": 0, "entry": 0.0, "high": 0.0, "net": 0.0, "equity": []}
    acc = 0.0
    for row in rows:
        pnl, current, high = calc_signal_pnl(row)
        entry = _safe_float(row.get("entry_price"))
        net = max(0.0, high - entry) if high >= entry else current - entry
        st["entry"] += entry; st["high"] += high; st["net"] += net
        acc += net; st["equity"].append(acc)
        st["wins" if net >= 0 else "losses"] += 1
        st["calls" if row.get("contract_type") == "call" else "puts"] += 1
        if high >= _safe_float(row.get("tp1"), 10**9): st["tp1"] += 1
        if high >= _safe_float(row.get("tp2"), 10**9): st["tp2"] += 1
        if high >= _safe_float(row.get("tp3"), 10**9): st["tp3"] += 1
    st["success"] = (st["wins"] / st["total"] * 100) if st["total"] else 0.0
    return st

def _format_report_fallback(rows, title, period_text):
    st = _report_stats(rows)
    msg = f"📊 <b>{title}</b>\n📅 {period_text}\n\nإجمالي العقود: <b>{st['total']}</b>\nالرابحة: {st['wins']}\nالخاسرة: {st['losses']}\nنسبة النجاح: <b>{st['success']:.2f}%</b>\n\n"
    msg += f"TP1: {st['tp1']}/{st['total']}\nTP2: {st['tp2']}/{st['total']}\nTP3: {st['tp3']}/{st['total']}\n\n"
    if not rows:
        msg += "❌ لا توجد عقود في هذه الفترة.\n"
    for i, row in enumerate(rows, 1):
        msg += format_report_contract_line(row, i) + "\n"
    return msg + "\n📢 @Option_Strike01"

def build_report_image(rows: list, title: str, period_text: str):
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    st = _report_stats(rows)
    W, H = REPORT_IMAGE_WIDTH, REPORT_IMAGE_HEIGHT
    bg=(2,7,10); panel=(7,17,22); line=(170,97,25); gold=(229,151,45); green=(83,188,52); red=(210,61,42); white=(238,238,226)
    img=Image.new("RGB",(W,H),bg); d=ImageDraw.Draw(img)
    f_title=_img_font(58,True); f_sub=_img_font(32,False); f_box=_img_font(25,True); f_num=_img_font(44,True); f_med=_img_font(28,True); f_small=_img_font(21,False); f_tiny=_img_font(18,False)
    d.rectangle((8,8,W-8,H-8), outline=line, width=3)
    d.text((55,60),"OPTION\nSTRIKE",fill=gold,font=_img_font(36,True),spacing=0)
    d.text((540,55),title,fill=gold,font=f_title,anchor="ma")
    d.text((540,125),"تقرير الشركات",fill=gold,font=f_sub,anchor="ma")
    d.rounded_rectangle((345,170,735,220),radius=12,outline=line,width=2,fill=(10,17,22)); d.text((540,181),period_text,fill=white,font=f_sub,anchor="ma")
    for x,label,value,color in [(20,"إجمالي العقود",st['total'],white),(210,"الرابحة",st['wins'],green),(400,"الخاسرة",st['losses'],red),(590,"نسبة النجاح",f"{st['success']:.2f}%",green)]:
        d.rounded_rectangle((x,240,x+175,375),radius=10,outline=line,width=2,fill=panel); d.text((x+88,258),str(label),fill=gold,font=f_box,anchor="ma"); d.text((x+88,304),str(value),fill=color,font=f_num,anchor="ma")
    total=max(st['total'],1)
    d.rounded_rectangle((785,240,1060,375),radius=10,outline=line,width=2,fill=panel); d.text((922,258),"توزيع العقود",fill=gold,font=f_box,anchor="ma")
    d.text((835,303),f"CALL ({st['calls']})  {st['calls']/total*100:.2f}%",fill=green,font=f_small); d.text((835,336),f"PUT ({st['puts']})  {st['puts']/total*100:.2f}%",fill=red,font=f_small)
    d.rounded_rectangle((20,390,550,610),radius=10,outline=line,width=2,fill=panel); d.text((285,405),"الأداء خلال الفترة",fill=gold,font=f_box,anchor="ma")
    chart=(65,455,520,575); d.rectangle(chart,outline=(31,55,58),width=1); eq=st['equity'] or [0]; mn=min(eq+[0]); mx=max(eq+[1]); mx = mx if mx != mn else mn+1
    pts=[]
    for i,v in enumerate(eq):
        pts.append((chart[0]+int((chart[2]-chart[0])*(i/max(len(eq)-1,1))), chart[3]-int((chart[3]-chart[1])*((v-mn)/(mx-mn)))))
    if len(pts)>1: d.line(pts,fill=green,width=4)
    for p in pts: d.ellipse((p[0]-4,p[1]-4,p[0]+4,p[1]+4),fill=green)
    d.rounded_rectangle((570,390,1060,610),radius=10,outline=line,width=2,fill=panel); d.text((815,405),"تحقيق الأهداف",fill=gold,font=f_box,anchor="ma")
    for i,(lab,val) in enumerate([("TP1",st['tp1']),("TP2",st['tp2']),("TP3",st['tp3'])]):
        y=455+i*48; pct=(val/total*100) if st['total'] else 0
        d.text((610,y),lab,fill=white,font=f_med); d.text((700,y),f"{val} / {st['total']}",fill=white,font=f_small); d.rectangle((820,y+8,980,y+24),fill=(30,43,43)); d.rectangle((820,y+8,820+int(160*pct/100),y+24),fill=green); d.text((995,y),f"{pct:.2f}%",fill=green,font=f_small)
    d.rounded_rectangle((20,625,1060,1435),radius=10,outline=line,width=2,fill=panel); d.text((540,638),"جميع العقود",fill=gold,font=f_med,anchor="ma")
    xs=[1040,980,875,770,650,530,405,290,165]; headers=["#","الشركة","النوع","تاريخ الانتهاء","دخول","أعلى","الصافي","نسبة الربح","الحالة"]; y=680
    for x,h in zip(xs,headers): d.text((x,y),h,fill=gold,font=f_tiny,anchor="ra")
    d.line((35,y+30,1045,y+30),fill=line,width=1); y+=40
    for idx,row in enumerate(rows[:24],1):
        entry=_safe_float(row.get('entry_price')); high=_safe_float(row.get('highest_price'),entry); current=_safe_float(row.get('current_price'),high); net=max(0,high-entry) if high>=entry else current-entry; pct=(net/entry*100) if entry else 0; ctype='CALL' if row.get('contract_type')=='call' else 'PUT'; color=green if net>=0 else red; status='رابح' if net>=0 else 'خاسر'
        vals=[idx,row.get('ticker','—'),ctype,format_short_date(row.get('expiration','')),f"{entry:.2f}",f"{high:.2f}",f"{net:.2f}",f"{pct:.0f}%",status]
        for x,v in zip(xs,vals): d.text((x,y),str(v),fill=color if x in [290,405,165] else white,font=f_tiny,anchor="ra")
        y+=29
        if y>1400: break
    for x1,x2,lab,val,col in [(35,330,"مجموع الدخول",st['entry'],white),(365,660,"مجموع أعلى سعر",st['high'],white),(695,1045,"صافي الربح",st['net'],green if st['net']>=0 else red)]:
        d.rounded_rectangle((x1,1450,x2,1525),radius=10,outline=line,fill=(5,15,18),width=2); d.text(((x1+x2)//2,1463),lab,fill=white,font=f_small,anchor="ma"); d.text(((x1+x2)//2,1492),f"$ {val:.2f}",fill=col,font=f_med,anchor="ma")
    d.text((540,1560),"تداول بذكاء .. وانضباط    |    @Option_Strike01",fill=gold,font=f_small,anchor="ma")
    bio=io.BytesIO(); bio.name="option_strike_report.png"; img.save(bio,format="PNG"); bio.seek(0); return bio

def send_report_image(rows: list, title: str, period_text: str, chat_id=None, keyboard=None):
    target_chat_id = str(chat_id) if chat_id else CHAT_ID
    photo = build_report_image(rows, title, period_text)
    if photo is None:
        return send(_format_report_fallback(rows, title, period_text), keyboard=keyboard, chat_id=target_chat_id)
    data = {"chat_id": target_chat_id, "caption": f"📊 <b>{title}</b>\n📅 {period_text}\n\n📢 @Option_Strike01", "parse_mode": "HTML"}
    if keyboard: data["reply_markup"] = json.dumps(keyboard)
    try:
        r = HTTP.post(API_SEND_PHOTO, data=data, files={"photo": photo}, timeout=30); r.raise_for_status(); return r.json()
    except Exception as e:
        print(f"[SEND REPORT PHOTO ERROR] {e}"); return send(_format_report_fallback(rows, title, period_text), keyboard=keyboard, chat_id=target_chat_id)

def rows_for_day(day=None):
    d = day or datetime.now(RIYADH_TZ).date(); return [x for x in SIGNAL_HISTORY if x.get("created_at") and x["created_at"].date() == d]

def rows_for_week():
    ws=get_week_start(); we=ws+timedelta(days=6); return [x for x in SIGNAL_HISTORY if x.get("created_at") and ws <= x["created_at"].date() <= we], ws, we

def rows_for_month(year:int, month:int):
    return [x for x in SIGNAL_HISTORY if x.get("created_at") and x["created_at"].year==year and x["created_at"].month==month]

def rows_for_year(year:int):
    return [x for x in SIGNAL_HISTORY if x.get("created_at") and x["created_at"].year==year]

def report_menu():
    return {"inline_keyboard":[[{"text":"📋 تقرير اليوم","callback_data":"daily_report_img"},{"text":"🗓 تقرير الأسبوع","callback_data":"weekly_report_img"}],[{"text":"📅 تقرير شهري","callback_data":"report_months"},{"text":"📆 تقرير سنوي","callback_data":"yearly_report_img"}],[{"text":"🏠 رجوع","callback_data":"back"}]]}

def months_archive_menu():
    keys=sorted({(x["created_at"].year,x["created_at"].month) for x in SIGNAL_HISTORY if x.get("created_at")}, reverse=True); rows=[]; row=[]
    for y,m in keys[:24]:
        row.append({"text":f"{m:02d}/{y}","callback_data":f"month_report:{y}:{m}"})
        if len(row)==3: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([{"text":"🏠 رجوع","callback_data":"reports_menu"}]); return {"inline_keyboard":rows}

def whale_rows_for_day(day=None):
    d = day or datetime.now(RIYADH_TZ).date()
    return [x for x in WHALE_HISTORY if x.get("created_at") and x["created_at"].date() == d]

def whale_rows_for_week():
    ws = get_week_start(); we = ws + timedelta(days=6)
    return [x for x in WHALE_HISTORY if x.get("created_at") and ws <= x["created_at"].date() <= we], ws, we

def whale_rows_for_month(year:int, month:int):
    return [x for x in WHALE_HISTORY if x.get("created_at") and x["created_at"].year == year and x["created_at"].month == month]

def whale_rows_for_year(year:int):
    return [x for x in WHALE_HISTORY if x.get("created_at") and x["created_at"].year == year]

def whale_report_menu():
    return {"inline_keyboard":[[{"text":"📋 تقرير الحيتان اليومي","callback_data":"whale_daily_report_img"},{"text":"🗓 تقرير الحيتان الأسبوعي","callback_data":"whale_weekly_report_img"}],[{"text":"📅 تقرير الحيتان الشهري","callback_data":"whale_report_months"},{"text":"📆 تقرير الحيتان السنوي","callback_data":"whale_yearly_report_img"}],[{"text":"🏠 رجوع","callback_data":"back"}]]}

def whale_months_archive_menu():
    keys = sorted({(x["created_at"].year, x["created_at"].month) for x in WHALE_HISTORY if x.get("created_at")}, reverse=True)
    rows=[]; row=[]
    for y,m in keys[:24]:
        row.append({"text":f"{m:02d}/{y}","callback_data":f"whale_month_report:{y}:{m}"})
        if len(row)==3:
            rows.append(row); row=[]
    if row:
        rows.append(row)
    rows.append([{"text":"🏠 رجوع","callback_data":"whale_reports_menu"}])
    return {"inline_keyboard":rows}

def answer_callback(cb_id, text=""):
    try:
        HTTP.post(API_ANSWER, json={
            "callback_query_id": cb_id,
            "text": text
        }, timeout=10)
    except Exception as e:
        print(f"[CALLBACK ERROR] {e}")

# =========================
# الرسائل
# =========================

def msg_quick(tk, tf, c):
    return f"""📊 <b>{tk}</b> | TF: {tf}

💰 السعر: <b>{c['price']:.2f}</b>
📊 الترند: {c['trend']}
🔥 الاتجاه الأقوى: {c['strongest_trend']}

📍 الارتكاز {c['pivot_label']}: <b>{c['pivot']:.2f}</b>
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

🔵 دعم: {c['low']:.2f}
🔴 مقاومة: {c['high']:.2f}

🟢 أهداف CALL:
1️⃣ {c['call_tp1']:.2f}
2️⃣ {c['call_tp2']:.2f}
3️⃣ {c['call_tp3']:.2f}

🔴 أهداف PUT:
1️⃣ {c['put_tp1']:.2f}
2️⃣ {c['put_tp2']:.2f}
3️⃣ {c['put_tp3']:.2f}

📌 دخول: {c['best_entry']:.2f}
🛑 وقف: {c['sl']:.2f}

📈 القرار: <b>{c['direction']}</b>"""

def msg_pro(tk, tf, c, o, contract=None):
    base = f"""🔥 <b>{tk} احترافي</b> | TF: {tf}

💰 السعر: <b>{c['price']:.2f}</b>
📊 الترند: {c['trend']}
🔥 الاتجاه الأقوى: {c['strongest_trend']}

🔵 دعم {c['pivot_label']}: {c['low']:.2f}
🔴 مقاومة {c['pivot_label']}: {c['high']:.2f}
📍 الارتكاز {c['pivot_label']}: <b>{c['pivot']:.2f}</b>
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

🟢 أهداف CALL (فوق الارتكاز):
1️⃣ {c['call_tp1']:.2f}
2️⃣ {c['call_tp2']:.2f}
3️⃣ {c['call_tp3']:.2f}

🔴 أهداف PUT (تحت الارتكاز):
1️⃣ {c['put_tp1']:.2f}
2️⃣ {c['put_tp2']:.2f}
3️⃣ {c['put_tp3']:.2f}

📈 <b>القرار النهائي: {c['direction']}</b>

🧲 <b>معلومات داعمة:</b>
القاما: {o['gamma']:.2f}
Magnet: {o['zlow']:.2f} - {o['zhigh']:.2f}
احتمال الوصول: {o['prob']}%
سيولة الكول: {o['call']:.2f}
سيولة البوت: {o['put']:.2f}
الأقوى: {o['liq']}"""

    if not contract:
        return base + "\n\n❌ لم يتم العثور على عقد متاح."

    mode_line = f"\n🎯 الوضع: {contract.get('mode', 'NORMAL')}" if contract.get("mode") else ""

    return base + f"""

💎 <b>العقد المختار:</b>{mode_line}
الرمز: <code>{contract['option_ticker']}</code>
النوع: {contract['contract_type'].upper()}
السترايك: {contract['strike']:.2f}
الانتهاء: {format_arabic_date(contract['expiration'])}
سعر العقد: <b>{contract['contract_price']:.2f}</b>
نطاق الدخول: {contract['entry_high']:.2f} – {contract['entry_low']:.2f}

🎯 أهداف العقد:
1️⃣ {contract['tp1']:.2f}
2️⃣ {contract['tp2']:.2f}
3️⃣ {contract['tp3']:.2f}

🛑 الوقف: {contract['stop_text']}
📊 نسبة النجاح: <b>{contract['success_rate']}%</b>
Δ Delta: {contract['delta']:.2f} | Γ Gamma: {contract['gamma']:.4f}
IV: {contract['iv']:.4f} | OI: {contract['oi']}

📰 آخر الأخبار:
{format_news_brief(contract.get('news_items', []))}

📆 الإعلان القادم:
{format_earnings_brief(contract.get('earnings_event'))}"""

def msg_channel_post(tk, contract):
    type_ar = "CALL" if contract["contract_type"] == "call" else "PUT"
    color = "🟢" if contract["contract_type"] == "call" else "🔴"

    mode_line = ""
    if contract.get("mode") == "ZERO HERO FRIDAY":
        mode_line = "\n⚡ <b>الوضع: زيرو هيرو الجمعة</b>"

    return f"""🆕 <b>طرح جديد | {tk}</b>{mode_line}

{color} النوع: <b>{type_ar}</b>
🎯 السترايك: ${contract['strike']:.2f}
📅 التاريخ: {format_arabic_date(contract['expiration'])}

💰 نطاق الدخول: {contract['entry_high']:.2f} – {contract['entry_low']:.2f}

📈 الأهداف:
🥇 {contract['tp1']:.2f}
🥈 {contract['tp2']:.2f}
🥉 {contract['tp3']:.2f}

🛑 الوقف: {contract['stop_text']}
📊 نسبة النجاح: <b>{contract['success_rate']}%</b>

📰 آخر الأخبار:
{format_news_brief(contract.get('news_items', []))}

📆 الإعلان القادم:
{format_earnings_brief(contract.get('earnings_event'))}

⚠️ تنبيه: هذا الطرح تعليمي
والقرار النهائي يعود للمتداول

📢 @Option_Strike01"""

def msg_whale_channel_post(tk, contract):
    type_ar = "CALL" if contract["contract_type"] == "call" else "PUT"
    color = "🟢" if contract["contract_type"] == "call" else "🔴"
    return f"""🐋 <b>طرح عقود الحيتان | {tk}</b>

{color} النوع: <b>{type_ar}</b>
🎯 السترايك: ${contract['strike']:.2f}
📅 التاريخ: {format_arabic_date(contract['expiration'])}

💰 نطاق الدخول: {contract['entry_high']:.2f} – {contract['entry_low']:.2f}

📈 الأهداف:
🥇 {contract['tp1']:.2f}
🥈 {contract['tp2']:.2f}
🥉 {contract['tp3']:.2f}

🛑 الوقف: {contract['stop_text']}
📊 نسبة النجاح: <b>{contract['success_rate']}%</b>
🔥 نسبة الانفجار: <b>{contract.get('explosion_score', contract['success_rate'])}%</b>

🐋 سبب الاختيار:
{contract.get('whale_reasons', 'إعداد حيتان')}

📍 المنطقة: {contract.get('whale_level_name', 'منطقة حيتان')} عند {float(contract.get('whale_trigger_level', 0) or 0):.2f}

⚠️ تنبيه: هذا الطرح تعليمي
والقرار النهائي يعود للمتداول.

📢 @Option_Strike01"""
def msg_contract_update(title, entry_price, current_price):
    pnl = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
    emoji = "🚀" if pnl >= 50 else "📈" if pnl >= 0 else "📉"
    return f"""🔔 <b>تحديث | {title}</b>

📊 سعر الدخول: {entry_price:.2f}
💰 السعر الحالي: {current_price:.2f}
{emoji} نسبة الربح: <b>{pnl:+.2f}%</b>

⚠️ تنبيه: هذا الطرح تعليمي
والقرار النهائي يعود للمتداول.

📢 @Option_Strike01"""

def msg_gamma(tk, tf, c, o):
    return f"""🧲 <b>{tk} - القاما والسيولة</b> | TF: {tf}

🧲 القاما: {o['gamma']:.2f}
📍 Magnet: {o['zlow']:.2f} - {o['zhigh']:.2f}
📊 احتمال الوصول: <b>{o['prob']}</b>%

💰 سيولة الكول: {o['call']:.2f}
💸 سيولة البوت: {o['put']:.2f}
🔥 الأقوى: {o['liq']}

📍 الارتكاز {c['pivot_label']}: {c['pivot']:.2f}
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

الاتجاه الأقوى: {c['strongest_trend']}
السعر الحالي: <b>{c['price']:.2f}</b>"""

def msg_sr(tk, tf, c):
    return f"""📈 <b>{tk} - دعوم ومقاومات</b> | TF: {tf}

🔵 دعم {c['pivot_label']}: <b>{c['low']:.2f}</b>
🔴 مقاومة {c['pivot_label']}: <b>{c['high']:.2f}</b>

📍 الارتكاز {c['pivot_label']}: <b>{c['pivot']:.2f}</b>
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

🟢 أهداف CALL (فوق الارتكاز):
1️⃣ {c['call_tp1']:.2f}
2️⃣ {c['call_tp2']:.2f}
3️⃣ {c['call_tp3']:.2f}

🔴 أهداف PUT (تحت الارتكاز):
1️⃣ {c['put_tp1']:.2f}
2️⃣ {c['put_tp2']:.2f}
3️⃣ {c['put_tp3']:.2f}

الاتجاه الأقوى: {c['strongest_trend']}
السعر الحالي: <b>{c['price']:.2f}</b>"""

def msg_plan(tk, tf, c):
    return f"""🎯 <b>{tk} - خطة الدخول</b> | TF: {tf}

الاتجاه الأقوى: {c['strongest_trend']}
📍 الارتكاز {c['pivot_label']}: {c['pivot']:.2f}
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

📌 دخول: <b>{c['best_entry']:.2f}</b>
🛑 وقف: {c['sl']:.2f}

🟢 أهداف CALL:
1️⃣ {c['call_tp1']:.2f}
2️⃣ {c['call_tp2']:.2f}
3️⃣ {c['call_tp3']:.2f}

🔴 أهداف PUT:
1️⃣ {c['put_tp1']:.2f}
2️⃣ {c['put_tp2']:.2f}
3️⃣ {c['put_tp3']:.2f}

📈 القرار: <b>{c['direction']}</b>"""

def msg_contract(tk, tf, c, contract):
    if not contract:
        return "❌ لم يتم العثور على عقد متاح لهذا السهم."
    mode_line = f"\nMode: {contract.get('mode', 'NORMAL')}" if contract.get("mode") else ""
    return f"""💎 <b>{tk} - أفضل عقد</b> | TF: {tf}{mode_line}

النوع: {contract['contract_type'].upper()}
السترايك: {contract['strike']:.2f}
الانتهاء: {format_arabic_date(contract['expiration'])}
سعر العقد: <b>{contract['contract_price']:.2f}</b>

الاتجاه الأقوى: {c['strongest_trend']}
📍 الارتكاز {c['pivot_label']}: {c['pivot']:.2f}
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

📌 نطاق الدخول: {contract['entry_high']:.2f} – {contract['entry_low']:.2f}
🛑 الوقف: {contract['stop_text']}

🎯 أهداف العقد:
1️⃣ {contract['tp1']:.2f}
2️⃣ {contract['tp2']:.2f}
3️⃣ {contract['tp3']:.2f}

📊 نسبة النجاح: <b>{contract['success_rate']}%</b>"""


def calc_signal_pnl(row: dict):
    entry = row.get("entry_price", 0) or 0
    current = row.get("current_price") or row.get("highest_price") or entry
    high = row.get("highest_price") or current or entry
    if entry <= 0:
        return 0.0, current, high
    pnl = ((current - entry) / entry) * 100
    return pnl, current, high

def calc_signal_high_pnl(row: dict):
    entry = row.get("entry_price", 0) or 0
    high = row.get("highest_price") or entry
    if entry <= 0:
        return 0.0
    return ((high - entry) / entry) * 100

def signal_status(row: dict):
    pnl, current, high = calc_signal_pnl(row)
    entry = row.get("entry_price", 0) or 0
    if high >= row.get("tp3", 10**9):
        return "🏆 حقق TP3"
    if high >= row.get("tp2", 10**9):
        return "🥈 حقق TP2"
    if high >= row.get("tp1", 10**9):
        return "🥇 حقق TP1"
    if current < entry:
        return "🔴 خاسر"
    if current > entry:
        return "🟢 رابح"
    return "⚪ مفتوح"

def format_report_contract_line(row: dict, idx: int):
    pnl, current, high = calc_signal_pnl(row)
    high_pnl = calc_signal_high_pnl(row)
    type_txt = "CALL" if row.get("contract_type") == "call" else "PUT"
    type_icon = "🟢" if row.get("contract_type") == "call" else "🔴"
    exp = format_short_date(row.get("expiration", ""))
    created = row.get("created_at")
    created_txt = created.strftime("%d/%m %H:%M") if created else "—"
    status = signal_status(row)
    return (
        f"{idx}) <b>{row.get('ticker', '—')} {type_icon} {type_txt}</b> | "
        f"{exp} | <code>{row.get('option_ticker', '—')}</code>\n"
        f"   الحالة: <b>{status}</b>\n"
        f"   دخول: {row.get('entry_price', 0):.2f} | الحالي: {current:.2f} | الأعلى: {high:.2f}\n"
        f"   الأداء الحالي: <b>{pnl:+.2f}%</b> | أعلى ربح: <b>{high_pnl:+.2f}%</b>\n"
        f"   الأهداف: {row.get('tp1', 0):.2f} / {row.get('tp2', 0):.2f} / {row.get('tp3', 0):.2f}\n"
        f"   وقت الطرح: {created_txt}\n"
    )

def msg_open_contracts():
    if not OPEN_CONTRACT_SIGNALS:
        return "📂 لا توجد عقود مفتوحة حالياً."

    msg = "📂 <b>العقود المفتوحة</b>\n\n"

    for i, (_, sig) in enumerate(OPEN_CONTRACT_SIGNALS.items(), 1):
        msg += (
            f"{i}. <b>{sig['ticker']}</b>\n"
            f"العقد: <code>{sig['option_ticker']}</code>\n"
            f"التاريخ: {format_short_date(sig.get('expiration', ''))}\n"
            f"النوع: {'CALL' if sig['contract_type'] == 'call' else 'PUT'}\n"
            f"الحالة: {signal_status(sig)}\n"
            f"سعر الدخول: {sig['entry_price']:.2f}\n"
            f"السعر الحالي: {sig.get('current_price', sig['highest_price']):.2f}\n"
            f"أعلى سعر: {sig['highest_price']:.2f}\n"
            f"TP1: {sig['tp1']:.2f} | TP2: {sig['tp2']:.2f} | TP3: {sig['tp3']:.2f}\n"
            f"تم التحديث الأول: {'نعم' if sig['first_update_sent'] else 'لا'}\n"
            f"وقت الإضافة: {sig['created_at'].strftime('%d/%m %H:%M')}\n\n"
        )

    return msg

def msg_daily_report():
    reset_daily_counter_if_needed()
    today = datetime.now().date()
    today_rows = [x for x in SIGNAL_HISTORY if x.get("created_at") and x["created_at"].date() == today]

    total = len(today_rows)
    wins = losses = open_count = tp1_hits = tp2_hits = tp3_hits = 0

    for row in today_rows:
        pnl, current, high = calc_signal_pnl(row)
        if high >= row.get("tp1", 10**9):
            tp1_hits += 1
        if high >= row.get("tp2", 10**9):
            tp2_hits += 1
        if high >= row.get("tp3", 10**9):
            tp3_hits += 1
        if current < row.get("entry_price", 0):
            losses += 1
        elif current > row.get("entry_price", 0) or high >= row.get("tp1", 10**9):
            wins += 1
        else:
            open_count += 1

    success_rate = (wins / total) * 100 if total else 0
    msg = (
        f"📋 <b>تقرير عقود اليوم</b>\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"📅 التاريخ: {datetime.now(RIYADH_TZ).strftime('%d/%m/%Y')}\n"
        f"📊 إجمالي العقود: <b>{total}</b>\n"
        f"🟢 الرابحة: {wins}\n"
        f"🔴 الخاسرة: {losses}\n"
        f"⚪ المفتوحة بدون حركة: {open_count}\n"
        f"📈 نسبة النجاح: <b>{success_rate:.2f}%</b>\n\n"
        f"🎯 تحقيق الأهداف:\n"
        f"TP1: {tp1_hits}/{total}\n"
        f"TP2: {tp2_hits}/{total}\n"
        f"TP3: {tp3_hits}/{total}\n\n"
        f"📦 <b>جميع العقود:</b>\n"
        f"━━━━━━━━━━━━━━\n"
    )
    if not today_rows:
        msg += "❌ لا توجد عقود مسجلة اليوم.\n"
    else:
        for i, row in enumerate(today_rows, 1):
            msg += format_report_contract_line(row, i) + "\n"
    msg += (
        "⚠️ تنبيه: هذا التقرير تعليمي\n"
        "والقرار النهائي يعود للمتداول.\n\n"
        "📢 @Option_Strike01"
    )
    return msg

def msg_earnings_list(events, mode: str):
    title_map = {
        "all": "إعلانات الأسبوع",
        "pre": "إعلانات قبل الافتتاح",
        "post": "إعلانات بعد الإغلاق"
    }
    title = title_map.get(mode, "إعلانات الشركات")

    if not events:
        return f"📆 <b>{title}</b>\n\n❌ لا توجد شركات مطابقة حالياً."

    return f"📆 <b>{title}</b>\n\n📊 العدد: {len(events)}\nاختر الشركة من الأزرار بالأسفل 👇"

def fmt_billions(n):
    try:
        n = float(n)
        if abs(n) >= 1_000_000_000:
            return f"{n / 1_000_000_000:.2f}B"
        if abs(n) >= 1_000_000:
            return f"{n / 1_000_000:.2f}M"
        return f"{n:.2f}"
    except Exception:
        return "—"

def pct_change_safe(new_val, old_val):
    try:
        if new_val is None or old_val is None:
            return None
        new_val = float(new_val)
        old_val = float(old_val)
        if old_val == 0:
            return None
        return ((new_val - old_val) / abs(old_val)) * 100
    except Exception:
        return None

def analyze_earnings_financials(event: dict):
    score = 0

    estimated_eps = event.get("estimated_eps")
    previous_eps = event.get("previous_eps")
    estimated_revenue = event.get("estimated_revenue")
    previous_revenue = event.get("previous_revenue")

    eps_growth = pct_change_safe(estimated_eps, previous_eps)
    rev_growth = pct_change_safe(estimated_revenue, previous_revenue)

    if eps_growth is not None:
        score += 15 if eps_growth > 0 else -15 if eps_growth < 0 else 0
    if rev_growth is not None:
        score += 12 if rev_growth > 0 else -12 if rev_growth < 0 else 0

    if score >= 15:
        bias = "إيجابي"
    elif score <= -15:
        bias = "سلبي"
    else:
        bias = "محايد"

    return {
        "bias": bias,
        "score": score,
        "eps_growth": eps_growth,
        "rev_growth": rev_growth,
        "estimated_eps": estimated_eps,
        "previous_eps": previous_eps,
        "estimated_revenue": estimated_revenue,
        "previous_revenue": previous_revenue
    }

def build_earnings_trade_view(ticker: str, c: dict, o: dict, contract: dict, event: dict):
    financial = analyze_earnings_financials(event)
    tech_score = calc_score(c, o)
    final_score = tech_score + financial["score"] * 0.4

    if contract and final_score >= 75:
        opportunity = "✅ فرصة مناسبة"
        entry_style = "قبل الإعلان بحذر"
    elif contract and final_score >= 60:
        opportunity = "⚠️ مراقبة فقط"
        entry_style = "بعد الإعلان بتأكيد"
    else:
        opportunity = "❌ لا يوجد عقد مناسب"
        entry_style = "تجنب"

    expected = "CALL 🟢" if c["direction"].startswith("CALL") else "PUT 🔴"

    return {
        "financial": financial,
        "tech_score": tech_score,
        "final_score": round(final_score, 1),
        "opportunity": opportunity,
        "entry_style": entry_style,
        "expected": expected
    }

def msg_earnings_analysis(ticker: str, event: dict, c: dict, o: dict, contract: dict, trade_view: dict):
    financial = trade_view["financial"]
    return f"""📆 <b>تحليل إعلان | {ticker}</b>

📅 التاريخ: {format_arabic_date(event.get('date', ''))}
🕐 الوقت: {event.get('time', 'غير محدد')}
⏰ التوقيت: {event.get('session_label', 'غير محدد')}

💹 <b>التحليل المالي:</b>
التقييم المالي: <b>{financial['bias']}</b>
نمو EPS المتوقع: {"—" if financial['eps_growth'] is None else f"{financial['eps_growth']:+.2f}%"}
نمو الإيرادات المتوقع: {"—" if financial['rev_growth'] is None else f"{financial['rev_growth']:+.2f}%"}
EPS السابق: {financial['previous_eps'] if financial['previous_eps'] is not None else '—'}
EPS المتوقع: {financial['estimated_eps'] if financial['estimated_eps'] is not None else '—'}
الإيرادات السابقة: {fmt_billions(financial['previous_revenue'])}
الإيرادات المتوقعة: {fmt_billions(financial['estimated_revenue'])}

📈 <b>التحليل الفني:</b>
السعر: <b>{c['price']:.2f}</b>
الترند: {c['trend']}
الاتجاه الأقوى: {c['strongest_trend']}
القرار الفني: <b>{c['direction']}</b>

🎯 <b>النتيجة:</b>
التوقع: <b>{trade_view['expected']}</b>
نوع الدخول: <b>{trade_view['entry_style']}</b>
الفرصة: <b>{trade_view['opportunity']}</b>
السكور الفني: {trade_view['tech_score']}
السكور النهائي: <b>{trade_view['final_score']}</b>

{"❌ لا يوجد عقد مناسب حالياً لهذه الفرصة." if not contract else f'''💎 <b>العقد المقترح:</b>
الرمز: <code>{contract['option_ticker']}</code>
النوع: {contract['contract_type'].upper()}
السترايك: {contract['strike']:.2f}
الانتهاء: {format_arabic_date(contract['expiration'])}
سعر العقد: <b>{contract['contract_price']:.2f}</b>
نطاق الدخول: {contract['entry_high']:.2f} – {contract['entry_low']:.2f}

🎯 أهداف العقد:
1️⃣ {contract['tp1']:.2f}
2️⃣ {contract['tp2']:.2f}
3️⃣ {contract['tp3']:.2f}

🛑 الوقف: {contract['stop_text']}
📊 نسبة النجاح: <b>{contract['success_rate']}%</b>'''}"""

# =========================
# التقرير الأسبوعي
# =========================

def get_week_start(dt=None):
    now = dt or datetime.now(MARKET_TZ)
    return (now - timedelta(days=now.weekday())).date()

def msg_weekly_report():
    week_start = get_week_start()
    week_end = week_start + timedelta(days=6)
    week_rows = [x for x in SIGNAL_HISTORY if x.get("created_at") and week_start <= x["created_at"].date() <= week_end]

    if not week_rows:
        return (
            f"🗓 <b>التقرير الأسبوعي</b>\n\n"
            f"الفترة: {week_start.strftime('%d/%m')} - {week_end.strftime('%d/%m')}\n"
            f"❌ لا توجد عقود مسجلة هذا الأسبوع."
        )

    total = len(week_rows)
    wins = losses = open_count = call_count = put_count = tp1_hits = tp2_hits = tp3_hits = 0
    total_high_pnl = 0.0

    for row in week_rows:
        pnl, current, high = calc_signal_pnl(row)
        total_high_pnl += calc_signal_high_pnl(row)

        if high >= row.get("tp1", 10**9):
            tp1_hits += 1
        if high >= row.get("tp2", 10**9):
            tp2_hits += 1
        if high >= row.get("tp3", 10**9):
            tp3_hits += 1

        if current < row.get("entry_price", 0):
            losses += 1
        elif current > row.get("entry_price", 0) or high >= row.get("tp1", 10**9):
            wins += 1
        else:
            open_count += 1

        if row.get("contract_type") == "call":
            call_count += 1
        else:
            put_count += 1

    success_rate = (wins / total) * 100 if total else 0
    avg_high_pnl = total_high_pnl / total if total else 0

    msg = f"""🗓 <b>تقرير عقود الأسبوع</b>
━━━━━━━━━━━━━━

📅 الفترة: {week_start.strftime('%d/%m')} - {week_end.strftime('%d/%m')}

📊 إجمالي العقود: <b>{total}</b>
🟢 الرابحة: {wins}
🔴 الخاسرة: {losses}
⚪ المفتوحة بدون حركة: {open_count}
📈 نسبة النجاح: <b>{success_rate:.2f}%</b>

📦 توزيع العقود:
🟢 CALL: {call_count}
🔴 PUT: {put_count}

🎯 تحقيق الأهداف:
TP1: {tp1_hits}/{total}
TP2: {tp2_hits}/{total}
TP3: {tp3_hits}/{total}

📉 متوسط أعلى أداء: <b>{avg_high_pnl:+.2f}%</b>

📦 <b>جميع عقود الأسبوع:</b>
━━━━━━━━━━━━━━
"""

    for i, row in enumerate(week_rows, 1):
        msg += format_report_contract_line(row, i) + "\n"

    msg += """⚠️ تنبيه: هذا التقرير تعليمي
والقرار النهائي يعود للمتداول.

📢 @Option_Strike01"""
    return msg

# =========================
# تسجيل العقد
# =========================

def register_contract_signal(ticker: str, contract: dict):
    key = contract["option_ticker"]
    row = {
        "ticker": ticker,
        "option_ticker": contract["option_ticker"],
        "contract_type": contract["contract_type"],
        "strike": contract["strike"],
        "expiration": contract["expiration"],
        "entry_price": contract["contract_price"],
        "highest_price": contract["contract_price"],
        "current_price": contract["contract_price"],
        "tp1": contract["tp1"],
        "tp2": contract["tp2"],
        "tp3": contract["tp3"],
        "first_update_sent": False,
        "last_update_trigger_price": contract["tp1"],
        "created_at": datetime.now(),
        "channel_title": f"{ticker} ${contract['strike']:.2f} {'كول' if contract['contract_type'] == 'call' else 'بوت'}",
        "message_id": contract.get("message_id"),
        "mid": contract.get("mid", contract.get("contract_price")),
        "oi": contract.get("oi", "—"),
        "volume": contract.get("volume", contract.get("vol", "—"))
    }
    OPEN_CONTRACT_SIGNALS[key] = row
    SIGNAL_HISTORY.append(row)
    save_signal_archive()

def register_whale_signal(ticker: str, contract: dict):
    key = contract["option_ticker"]
    row = {
        "ticker": ticker,
        "option_ticker": contract["option_ticker"],
        "contract_type": contract["contract_type"],
        "strike": contract["strike"],
        "expiration": contract["expiration"],
        "entry_price": contract["contract_price"],
        "highest_price": contract["contract_price"],
        "current_price": contract["contract_price"],
        "tp1": contract["tp1"],
        "tp2": contract["tp2"],
        "tp3": contract["tp3"],
        "first_update_sent": False,
        "last_update_trigger_price": contract["tp1"],
        "created_at": datetime.now(RIYADH_TZ),
        "channel_title": f"{ticker} ${contract['strike']:.2f} {'كول' if contract['contract_type'] == 'call' else 'بوت'}",
        "message_id": contract.get("message_id"),
        "mid": contract.get("mid", contract.get("contract_price")),
        "oi": contract.get("oi", "—"),
        "volume": contract.get("volume", contract.get("vol", "—")),
        "category": "whale"
    }
    OPEN_CONTRACT_SIGNALS[key] = row
    WHALE_HISTORY.append(row)
    WHALE_LAST_SENT_CONTRACT[key] = datetime.now(RIYADH_TZ).date().isoformat()
    save_whale_archive()

def get_live_contract_price(underlying: str, option_ticker: str):
    try:
        snap = get_option_contract_snapshot(underlying, option_ticker)
        price = parse_contract_price_from_snapshot(snap)
        if price is not None:
            return float(price)
    except Exception:
        pass
    try:
        lt = get_option_last_trade(option_ticker)
        p = lt.get("p") or lt.get("price")
        if p is not None:
            return float(p)
    except Exception:
        pass
    return None
# =========================
# الأخبار الاقتصادية - تجهيز وعرض
# =========================

def normalize_impact_label(raw):
    if raw is None:
        return "غير محدد"
    s = str(raw).strip().lower()
    if s in ["high", "3", "3.0", "h"]:
        return "🔥 عالي"
    if s in ["medium", "2", "2.0", "m"]:
        return "⚠️ متوسط"
    if s in ["low", "1", "1.0", "l"]:
        return "منخفض"
    if "high" in s:
        return "🔥 عالي"
    if "medium" in s:
        return "⚠️ متوسط"
    if "low" in s:
        return "منخفض"
    return str(raw)

def parse_event_datetime(item):
    date_value = item.get("date") or item.get("eventDate") or item.get("datetime") or item.get("timestamp")
    time_value = item.get("time") or item.get("eventTime") or ""

    candidates = []
    if date_value and time_value:
        candidates.extend([f"{date_value} {time_value}", f"{date_value}T{time_value}"])

    candidates.extend([item.get("datetime"), item.get("timestamp"), item.get("date"), item.get("eventDate")])

    for c in candidates:
        if not c:
            continue

        raw = str(c).strip().replace("Z", "+00:00")

        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("UTC") if time_value else MARKET_TZ)
            return dt.astimezone(RIYADH_TZ)
        except Exception:
            pass

        for fmt, tz in [('%Y-%m-%d %H:%M:%S', ZoneInfo('UTC')), ('%Y-%m-%d %H:%M', ZoneInfo('UTC')), ('%Y-%m-%d', MARKET_TZ)]:
            try:
                dt = datetime.strptime(raw, fmt).replace(tzinfo=tz)
                return dt.astimezone(RIYADH_TZ)
            except Exception:
                continue

    return None

def is_important_event_name(name: str) -> bool:
    if not name:
        return False
    n = name.lower()
    return any(k in n for k in IMPORTANT_EVENT_KEYWORDS)

def get_economic_calendar_cached(day_from: str, day_to: str):
    key = f"econ:{day_from}:{day_to}"
    cached = get_cached_item(ECON_CACHE, ECON_CACHE_TTL_SECONDS, key)
    if cached is not None:
        return cached

    rows = fmp_get("/economic-calendar", params={"from": day_from, "to": day_to})
    if not isinstance(rows, list) or not rows:
        rows = fmp_get("/economic_calendar", params={"from": day_from, "to": day_to})
    if not isinstance(rows, list):
        rows = []

    cleaned = []
    for item in rows:
        name = item.get("event") or item.get("title") or item.get("name") or ""
        impact_label = normalize_impact_label(item.get("impact"))
        if ECON_NEWS_ONLY_IMPORTANT:
            if not is_important_event_name(name):
                continue
            if impact_label not in ["🔥 عالي", "⚠️ متوسط"]:
                continue

        dt = parse_event_datetime(item)
        cleaned.append({
            "name": name,
            "country": item.get("country", ""),
            "impact": impact_label,
            "actual": item.get("actual"),
            "previous": item.get("previous"),
            "estimate": item.get("estimate"),
            "date_obj": dt,
            "raw": item
        })

    cleaned.sort(key=lambda x: x["date_obj"] or datetime.now(RIYADH_TZ))
    set_cached_item(ECON_CACHE, key, cleaned)
    return cleaned

def get_economic_events(mode: str):
    today = datetime.now(RIYADH_TZ).date()

    if mode == "today":
        start = today
        end = today
    elif mode == "week":
        start = today
        end = today + timedelta(days=6)
    else:
        start = today + timedelta(days=7)
        end = today + timedelta(days=13)

    return get_economic_calendar_cached(start.isoformat(), end.isoformat())

def format_event_value(v):
    if v is None or v == "":
        return "—"
    return str(v)

def format_economic_message(mode: str):
    title_map = {
        "today": "أخبار اليوم",
        "week": "أخبار الأسبوع",
        "nextweek": "أخبار الأسبوع القادم"
    }
    title = title_map.get(mode, "الأخبار المهمة")
    events = get_economic_events(mode)

    if not events:
        return f"📰 <b>{title}</b>\n\n❌ لا توجد أخبار مهمة حالياً."

    msg = f"📰 <b>{title}</b>\n{'─' * 30}\n\n"

    for i, ev in enumerate(events[:20], 1):
        dt = ev["date_obj"]
        time_str = dt.strftime("%d/%m %H:%M") if dt else "غير محدد"
        msg += (
            f"<b>{i}. {ev['name']}</b>\n"
            f"🕐 {time_str}\n"
            f"📍 الدولة: {ev['country'] or '—'}\n"
            f"📊 التأثير: {ev['impact']}\n"
            f"السابق: {format_event_value(ev['previous'])} | المتوقع: {format_event_value(ev['estimate'])} | الفعلي: {format_event_value(ev['actual'])}\n"
            f"⚠️ يفضل تجنب الدخول قبل الخبر\n\n"
        )

    return msg

def get_upcoming_economic_alerts():
    if not ECON_NEWS_ALERT_ENABLED:
        return []

    now = datetime.now(RIYADH_TZ)
    start = now.date().isoformat()
    end = (now.date() + timedelta(days=1)).isoformat()

    rows = get_economic_calendar_cached(start, end)
    alerts = []

    for ev in rows:
        dt = ev["date_obj"]
        if not dt:
            continue
        minutes_left = (dt - now).total_seconds() / 60.0
        if 0 <= minutes_left <= ECON_NEWS_ALERT_MINUTES_BEFORE + 1:
            if abs(minutes_left - ECON_NEWS_ALERT_MINUTES_BEFORE) <= 1.2:
                key = f"{ev['name']}|{dt.isoformat()}"
                if key not in ECON_ALERT_SENT:
                    alerts.append((key, ev))
    return alerts

def economic_alert_cycle():
    alerts = get_upcoming_economic_alerts()
    for key, ev in alerts:
        dt = ev["date_obj"]
        time_str = dt.strftime("%d/%m %H:%M") if dt else "غير محدد"
        send(
            f"⏰ <b>تنبيه خبر مهم بعد {ECON_NEWS_ALERT_MINUTES_BEFORE} دقائق</b>\n\n"
            f"📰 الخبر: {ev['name']}\n"
            f"🕐 الوقت: {time_str}\n"
            f"📊 التأثير: {ev['impact']}\n"
            f"السابق: {format_event_value(ev['previous'])}\n"
            f"المتوقع: {format_event_value(ev['estimate'])}\n\n"
            f"⚠️ يفضل تجنب الدخول قبل الخبر",
            chat_id=CHAT_ID
        )
        ECON_ALERT_SENT.add(key)

# =========================
# إعلانات الشركات
# =========================

def classify_earnings_session(time_str: str, item: dict = None):
    item = item or {}
    raw_session = str(item.get("session", "") or item.get("timing", "") or item.get("when", "")).strip().lower()

    if raw_session in {"bmo", "before market", "before open", "pre-market", "premarket"}:
        return "قبل الافتتاح"
    if raw_session in {"amc", "after market", "after close", "post-market", "postmarket"}:
        return "بعد الإغلاق"

    if not time_str:
        return "غير محدد"

    try:
        hh, mm, ss = [int(x) for x in time_str.split(":")]
        total = hh * 3600 + mm * 60 + ss
        if total < (9 * 3600 + 30 * 60):
            return "قبل الافتتاح"
        if total >= (16 * 3600):
            return "بعد الإغلاق"
        return "أثناء السوق"
    except Exception:
        return "غير محدد"

def get_earnings_for_date(date_str: str):
    key = f"earnings:{date_str}"
    cached = get_cached_item(EARNINGS_CACHE, EARNINGS_CACHE_TTL_SECONDS, key)
    if cached is not None:
        return cached

    try:
        data = massive_get("/benzinga/v1/earnings", params={"date": date_str, "limit": 1000})

        if isinstance(data, dict):
            results = data.get("results") or data.get("earnings") or data.get("data") or []
        elif isinstance(data, list):
            results = data
        else:
            results = []

        filtered = []
        for item in results:
            ticker = (item.get("ticker") or item.get("symbol") or "").upper().strip()
            if not ticker or ticker not in set(WATCHLIST) | set(FRIDAY_ZERO_HERO_TICKERS):
                continue

            event_date = item.get("date") or item.get("reportDate") or item.get("earnings_date") or date_str
            event_time = item.get("time") or item.get("hour") or item.get("eventTime") or ""

            item["ticker"] = ticker
            item["date"] = event_date
            item["time"] = event_time
            item["session_label"] = classify_earnings_session(event_time, item)
            filtered.append(item)

        filtered.sort(key=lambda x: (x.get("date", ""), x.get("time", "") or "99:99:99", x.get("ticker", "")))
        set_cached_item(EARNINGS_CACHE, key, filtered)
        return filtered
    except Exception as e:
        print(f"[EARNINGS ERROR] {date_str}: {e}")
        return []

def get_weekly_earnings_events(days: int = EARNINGS_LOOKAHEAD_DAYS):
    today = datetime.now(MARKET_TZ).date()
    events = []
    seen = set()

    for i in range(days):
        d = today + timedelta(days=i)
        rows = get_earnings_for_date(d.isoformat())
        for item in rows:
            k = (item.get("ticker"), item.get("date"), item.get("time"), item.get("session_label"))
            if k in seen:
                continue
            seen.add(k)
            events.append(item)

    events.sort(key=lambda x: (x.get("date", ""), x.get("time", "") or "99:99:99", x.get("ticker", "")))
    return events

def filter_earnings_events(events, mode: str):
    if mode == "pre":
        return [x for x in events if x.get("session_label") == "قبل الافتتاح"]
    if mode == "post":
        return [x for x in events if x.get("session_label") == "بعد الإغلاق"]
    return events

def get_ticker_earnings_event_in_week(ticker: str, target_date: str = None):
    events = get_weekly_earnings_events(EARNINGS_LOOKAHEAD_DAYS)
    matches = [x for x in events if x.get("ticker") == ticker]
    if target_date:
        exact = [x for x in matches if x.get("date") == target_date]
        if exact:
            return exact[0]
    return matches[0] if matches else None

# =========================
# دورة الصياد
# =========================

def scanner_cycle():
    reset_daily_counter_if_needed()
    if not can_send_more_today():
        return

    if is_in_no_entry_window():
        print("[SCANNER] داخل أول نصف ساعة من الافتتاح - لا يوجد دخول حالياً")
        return

    results = []

    for ticker in get_active_watchlist():
        try:
            if stock_in_cooldown(ticker):
                continue

            df = get_df(ticker, "1h")
            if df.empty or len(df) < 20:
                continue

            c = core_metrics(df, ticker=ticker)
            if c is None:
                continue

            if not is_entry_ready_now(c):
                continue

            o = options_info_from_massive(ticker, c["price"])
            contract = choose_best_contract_from_massive(ticker, c, o)
            if not contract:
                continue

            score = calc_score(c, o)
            if score < 60:
                continue

            news_items = get_stock_news(ticker, limit=3)
            earnings_event = get_ticker_earnings_event_in_week(ticker)
            contract["news_items"] = news_items
            contract["earnings_event"] = earnings_event

            results.append((ticker, score, c, o, contract))

        except Exception as e:
            print(f"[SCANNER ITEM ERROR] {ticker}: {e}")
            continue

    results.sort(key=lambda x: x[1], reverse=True)

    sent_now = 0
    for ticker, score, c, o, contract in results:
        if not can_send_more_today():
            break
        if stock_in_cooldown(ticker):
            continue

        send(msg_pro(ticker, "1h", c, o, contract), chat_id=CHAT_ID)
        time.sleep(1)
        photo_res = send_contract_image({"ticker": ticker, **contract}, caption=msg_channel_post(ticker, contract), chat_id=CHAT_ID)
        try:
            contract["message_id"] = photo_res.get("result", {}).get("message_id")
        except Exception:
            contract["message_id"] = None

        register_contract_signal(ticker, contract)
        mark_stock_sent(ticker)
        add_daily_signal()
        sent_now += 1

        if sent_now >= MAX_SIGNALS_PER_SCAN:
            break

def whale_scanner_cycle():
    reset_whale_daily_counter_if_needed()
    if not can_send_more_whales_today():
        return

    if not is_us_market_open_now():
        print("[WHALE SCANNER] السوق الأمريكي مغلق - لا يوجد طرح حيتان حالياً")
        return

    if is_in_no_entry_window():
        print("[WHALE SCANNER] داخل أول نصف ساعة من الافتتاح - لا يوجد دخول حالياً")
        return

    results = []
    market_bias = get_us500_whale_bias() if WHALE_ENHANCED_EXPLOSION_ENABLED else "NEUTRAL"
    for ticker in WATCHLIST:
        try:
            df = get_df(ticker, "1h")
            if df.empty or len(df) < 20:
                continue

            c = core_metrics(df, ticker=ticker)
            if c is None:
                continue

            if WHALE_ENHANCED_EXPLOSION_ENABLED:
                c = detect_whale_explosion_setup(df, ticker, c, market_bias=market_bias)
                if c is None:
                    continue
            else:
                if not is_entry_ready_now(c):
                    continue

            o = options_info_from_massive(ticker, c["price"])
            contract = choose_whale_contract_from_massive(ticker, c, o)
            if not contract:
                continue

            score = int(contract.get("explosion_score") or calc_score(c, o))
            if score < max(WHALE_MIN_SCORE, WHALE_MIN_EXPLOSION_SCORE if WHALE_ENHANCED_EXPLOSION_ENABLED else WHALE_MIN_SCORE):
                continue

            contract["news_items"] = get_stock_news(ticker, limit=2)
            contract["earnings_event"] = get_ticker_earnings_event_in_week(ticker)
            results.append((ticker, score, c, o, contract))

        except Exception as e:
            print(f"[WHALE SCANNER ITEM ERROR] {ticker}: {e}")
            continue

    results.sort(key=lambda x: x[1], reverse=True)

    sent_now = 0
    for ticker, score, c, o, contract in results:
        if not can_send_more_whales_today():
            break

        send(msg_pro(ticker, "1h", c, o, contract), chat_id=CHAT_ID)
        time.sleep(1)
        photo_res = send_contract_image({"ticker": ticker, **contract}, caption=msg_whale_channel_post(ticker, contract), chat_id=CHAT_ID)
        try:
            contract["message_id"] = photo_res.get("result", {}).get("message_id")
        except Exception:
            contract["message_id"] = None

        register_whale_signal(ticker, contract)
        add_whale_signal()
        sent_now += 1

        if sent_now >= WHALE_MAX_SIGNALS_PER_SCAN:
            break

def contract_update_cycle():
    for option_ticker, sig in list(OPEN_CONTRACT_SIGNALS.items()):
        try:
            price = get_live_contract_price(sig["ticker"], option_ticker)
            if price is None:
                continue

            sig["current_price"] = price

            if price > sig["highest_price"]:
                sig["highest_price"] = price

            if (not sig["first_update_sent"]) and price >= sig["tp1"]:
                edit_contract_image(sig, caption=msg_contract_update(sig["channel_title"], sig["entry_price"], price), chat_id=CHAT_ID)
                sig["first_update_sent"] = True
                sig["last_update_trigger_price"] = price
                if sig.get("category") == "whale":
                    save_whale_archive()
                else:
                    save_signal_archive()
                continue

            if sig["first_update_sent"] and price >= sig["last_update_trigger_price"] + UPDATE_STEP_AFTER_TP1:
                edit_contract_image(sig, caption=msg_contract_update(sig["channel_title"], sig["entry_price"], price), chat_id=CHAT_ID)
                sig["last_update_trigger_price"] = price
                if sig.get("category") == "whale":
                    save_whale_archive()
                else:
                    save_signal_archive()

            if sig.get("category") == "whale":
                save_whale_archive()
            else:
                save_signal_archive()

        except Exception as e:
            print(f"[CONTRACT UPDATE ERROR] {option_ticker}: {e}")

# =========================
# اللوبات
# =========================

async def contract_update_loop():
    await asyncio.sleep(20)
    while True:
        try:
            await asyncio.to_thread(contract_update_cycle)
        except Exception as e:
            send(f"❌ خطأ في متابعة العقود: {str(e)}", chat_id=CHAT_ID)
        await asyncio.sleep(300)

async def scanner_loop():
    global LAST_SCANNER_SLOT_KEY, LAST_WHALE_SLOT_KEY
    await asyncio.sleep(10)
    while True:
        try:
            slot_key = get_due_scanner_slot_key()
            if slot_key and slot_key != LAST_SCANNER_SLOT_KEY:
                await asyncio.to_thread(scanner_cycle)
                LAST_SCANNER_SLOT_KEY = slot_key

            whale_slot_key = get_due_whale_slot_key()
            if whale_slot_key and whale_slot_key != LAST_WHALE_SLOT_KEY:
                await asyncio.to_thread(whale_scanner_cycle)
                LAST_WHALE_SLOT_KEY = whale_slot_key
        except Exception as e:
            send(f"❌ خطأ في الصياد: {str(e)}", chat_id=CHAT_ID)
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)

async def economic_alert_loop():
    await asyncio.sleep(30)
    while True:
        try:
            await asyncio.to_thread(economic_alert_cycle)
        except Exception as e:
            send(f"❌ خطأ في تنبيهات الأخبار: {str(e)}", chat_id=CHAT_ID)
        await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    load_signal_archive()
    load_whale_archive()
    asyncio.create_task(scanner_loop())
    asyncio.create_task(contract_update_loop())
    asyncio.create_task(economic_alert_loop())
    send("✅ البوت شغال ومتصل!\n🕔 الصياد مرتبط بمواعيد الطرح المحددة تلقائياً.", chat_id=CHAT_ID)

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
                {"text": "📂 العقود المفتوحة", "callback_data": "open_contracts"},
                {"text": "📊 التقارير", "callback_data": "reports_menu"},
            ],
            [
                {"text": "🐋 تقرير عقود الحيتان", "callback_data": "whale_reports_menu"},
            ],
            [
                {"text": "📆 إعلانات الشركات", "callback_data": "earnings_menu"},
                {"text": "🗓 التقرير الأسبوعي", "callback_data": "weekly_report"},
            ],
            [
                {"text": "📰 الأخبار المهمة", "callback_data": "econ_menu"},
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

def earnings_menu():
    return {
        "inline_keyboard": [
            [{"text": "📅 إعلانات الأسبوع", "callback_data": "earnings_week:all"}],
            [{"text": "🌅 قبل الافتتاح", "callback_data": "earnings_week:pre"}],
            [{"text": "🌙 بعد الإغلاق", "callback_data": "earnings_week:post"}],
            [{"text": "⬅️ رجوع", "callback_data": "back"}]
        ]
    }

def econ_menu():
    return {
        "inline_keyboard": [
            [{"text": "📅 أخبار اليوم", "callback_data": "econ:today"}],
            [{"text": "🗓 أخبار الأسبوع", "callback_data": "econ:week"}],
            [{"text": "📆 أخبار الأسبوع القادم", "callback_data": "econ:nextweek"}],
            [{"text": "⬅️ رجوع", "callback_data": "back"}]
        ]
    }

def earnings_list_keyboard(events):
    rows = []
    for item in events[:EARNINGS_MAX_BUTTONS]:
        ticker = item.get("ticker", "")
        date_str = item.get("date", "")
        session_label = item.get("session_label", "غير محدد")
        label = f"{ticker} | {session_label} | {format_short_date(date_str)}"
        rows.append([{
            "text": label[:60],
            "callback_data": f"earnpick:{ticker}:{date_str}"
        }])

    rows.append([{"text": "⬅️ رجوع", "callback_data": "earnings_menu"}])
    return {"inline_keyboard": rows}

# =========================
# حالة المستخدم
# =========================

STATE = {}

def set_state(user, ticker=None, tf=None):
    s = STATE.get(user, {"ticker": None, "tf": "1d"})
    if ticker is not None:
        s["ticker"] = ticker
    if tf is not None:
        s["tf"] = tf
    STATE[user] = s

def get_state(user):
    return STATE.get(user, {"ticker": None, "tf": "1d"})

# =========================
# مساعد لتحليل السهم
# =========================

async def analyze_ticker(ticker: str, tf: str, user: str, announce: bool = True, use_cache: bool = True):
    if use_cache:
        cached = get_cached_analysis(ticker, tf)
        if cached:
            return cached

    if announce:
        send(f"⏳ جاري تحليل <b>{ticker}</b> على فريم {tf}…", chat_id=user)

    df = await asyncio.to_thread(get_df, ticker, tf)
    if df.empty:
        send("❌ لا توجد بيانات لهذا السهم", chat_id=user)
        return None, None, None

    c = await asyncio.to_thread(core_metrics, df, ticker)
    if c is None:
        send("❌ تعذر حساب الارتكاز لهذا الأصل", chat_id=user)
        return None, None, None

    try:
        o = await asyncio.wait_for(
            asyncio.to_thread(options_info_from_massive, ticker, c["price"]),
            timeout=12
        )
    except Exception:
        o = {
            "call": c["price"], "put": c["price"], "gamma": c["price"],
            "zlow": c["price"], "zhigh": c["price"], "prob": 50, "liq": "—"
        }

    try:
        contract = await asyncio.wait_for(
            asyncio.to_thread(choose_best_contract_from_massive, ticker, c, o),
            timeout=20
        )
    except Exception:
        contract = None

    result = (c, o, contract)
    set_cached_analysis(ticker, tf, result)
    return result

# =========================
# TradingView
# =========================

def normalize_signal_value(signal: str):
    s = str(signal or "").strip().lower()
    if s in {"buy", "long", "call"}:
        return "CALL"
    if s in {"sell", "short", "put"}:
        return "PUT"
    return s.upper()

def process_tradingview_signal(payload: dict):
    try:
        ticker = str(payload.get("ticker", "")).upper().strip()
        signal = normalize_signal_value(payload.get("signal", ""))
        tf = str(payload.get("interval", "1h")).lower()

        if not ticker:
            send("❌ TradingView: لا يوجد ticker في الرسالة", chat_id=CHAT_ID)
            return {"ok": True}

        if ticker not in set(WATCHLIST) | set(FRIDAY_ZERO_HERO_TICKERS):
            send(f"❌ TradingView: السهم {ticker} غير موجود في القائمة", chat_id=CHAT_ID)
            return {"ok": True}

        if tf not in TF:
            tf = "1h"

        df = get_df(ticker, tf)
        if df.empty:
            send(f"❌ TradingView: لا توجد بيانات لـ {ticker}", chat_id=CHAT_ID)
            return {"ok": True}

        c = core_metrics(df, ticker=ticker)
        if c is None:
            send(f"❌ TradingView: تعذر حساب الارتكاز لـ {ticker}", chat_id=CHAT_ID)
            return {"ok": True}

        if signal == "CALL":
            c["direction"] = "CALL 🟢"
        elif signal == "PUT":
            c["direction"] = "PUT 🔴"

        o = options_info_from_massive(ticker, c["price"])
        contract = choose_best_contract_from_massive(ticker, c, o)

        send(
            f"📡 <b>تنبيه TradingView</b>\n"
            f"السهم: <b>{ticker}</b>\n"
            f"الإشارة: <b>{signal}</b>\n"
            f"الفريم: <b>{tf}</b>",
            chat_id=CHAT_ID
        )

        if contract:
            send(msg_pro(ticker, tf, c, o, contract), chat_id=CHAT_ID)
            time.sleep(1)
            photo_res = send_contract_image({"ticker": ticker, **contract}, caption=msg_channel_post(ticker, contract), chat_id=CHAT_ID)
            try:
                contract["message_id"] = photo_res.get("result", {}).get("message_id")
            except Exception:
                contract["message_id"] = None
            register_contract_signal(ticker, contract)
        else:
            send(msg_pro(ticker, tf, c, o, None), chat_id=CHAT_ID)

        return {"ok": True}

    except Exception as e:
        send(f"❌ TradingView Error: {str(e)}", chat_id=CHAT_ID)
        return {"ok": True}

# =========================
# Webhook
# =========================

@app.post("/")
async def webhook(req: Request):
    try:
        data = await req.json()
    except Exception:
        return {"ok": True}

    # دعم TradingView على نفس الرابط
    if is_tradingview_payload(data):
        return await asyncio.to_thread(process_tradingview_signal, data)

    # Telegram only
    if not request_has_valid_secret(req):
        print("[WEBHOOK BLOCKED] Invalid Telegram secret token")
        return {"ok": True}

    if not looks_like_telegram_update(data):
        print("[WEBHOOK BLOCKED] Invalid update shape")
        return {"ok": True}

    incoming_text = str(safe_get(data, "message", "text", default="") or "").strip()
    if incoming_text != "/start":
        if is_duplicate_update(data.get("update_id")):
            return {"ok": True}

    try:
        if "message" in data:
            msg = data["message"]
            text = msg.get("text", "").strip()
            user = str(msg["chat"]["id"])

            if msg.get("from", {}).get("is_bot"):
                return {"ok": True}

            if text == "/start":
                set_state(user, ticker=None, tf="1d")
                send(
                    "🔥 <b>مرحباً بك في عالم اوبشن سترايك</b>\n\n"
                    "📊 بوت احترافي لتحليل الأسهم واختيار أفضل العقود\n\n"
                    "⚡ ماذا تحتاج الآن؟ اختر من القائمة بالأسفل 👇\n\n"
                    "💡 يمكنك إرسال رمز سهم مباشرة مثل:\n"
                    "<code>NVDA</code> أو <code>AAPL</code>",
                    main_menu(),
                    chat_id=user
                )
                return {"ok": True}

            if text == "/test":
                send("✅ البوت شغال 100%\n🔗 متصل بالـ APIs", chat_id=user)
                return {"ok": True}

            if text == "/scan":
                send("🔍 جاري تشغيل الصياد يدوياً...", chat_id=user)
                await asyncio.to_thread(scanner_cycle)
                return {"ok": True}

            if text == "/whales":
                send("🐋 جاري تشغيل صيد عقود الحيتان يدوياً...", chat_id=user)
                await asyncio.to_thread(whale_scanner_cycle)
                return {"ok": True}

            if not text:
                send("❌ أرسل رمز سهم صحيح مثل: <code>NVDA</code>", chat_id=user)
                return {"ok": True}

            parts = text.upper().split()
            ticker = parts[0]
            tf = parts[1].lower() if len(parts) > 1 else get_state(user)["tf"]

            if ticker not in set(WATCHLIST) | set(FRIDAY_ZERO_HERO_TICKERS):
                send(
                    f"❌ السهم <b>{ticker}</b> غير موجود في القائمة\n\n"
                    f"أمثلة: NVDA, AAPL, TSLA, SPY",
                    chat_id=user
                )
                return {"ok": True}

            if tf not in TF:
                send("❌ الفريم غير مدعوم. الفريمات: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w", chat_id=user)
                return {"ok": True}

            set_state(user, ticker=ticker, tf=tf)

            c, o, contract = await analyze_ticker(ticker, tf, user, announce=True, use_cache=True)
            if c is None:
                return {"ok": True}

            send(msg_pro(ticker, tf, c, o, contract), main_menu(), chat_id=user)
            return {"ok": True}

        if "callback_query" in data:
            cb = data["callback_query"]
            user = str(cb["message"]["chat"]["id"])
            data_cb = cb.get("data", "")
            cb_id = cb.get("id")

            answer_callback(cb_id, "جارٍ التنفيذ...")

            st = get_state(user)
            ticker = st.get("ticker")
            tf = st.get("tf", "1d")

            if data_cb == "tf":
                send("⚙️ اختر الفريم الزمني 👇", tf_menu(), chat_id=user)
                return {"ok": True}

            if data_cb == "earnings_menu":
                send("📆 اختر نوع إعلانات الشركات 👇", earnings_menu(), chat_id=user)
                return {"ok": True}

            if data_cb.startswith("earnings_week:"):
                mode = data_cb.split(":")[1]
                events = await asyncio.to_thread(get_weekly_earnings_events, EARNINGS_LOOKAHEAD_DAYS)
                events = filter_earnings_events(events, mode)
                send(msg_earnings_list(events, mode), earnings_list_keyboard(events), chat_id=user)
                return {"ok": True}

            if data_cb.startswith("earnpick:"):
                try:
                    _, tk, event_date = data_cb.split(":")
                except Exception:
                    send("❌ تعذر قراءة بيانات الإعلان", main_menu(), chat_id=user)
                    return {"ok": True}

                send(f"⏳ جاري دراسة إعلان <b>{tk}</b>...", chat_id=user)

                event = await asyncio.to_thread(get_ticker_earnings_event_in_week, tk, event_date)
                if not event:
                    send("❌ لم يتم العثور على بيانات الإعلان لهذه الشركة هذا الأسبوع.", earnings_menu(), chat_id=user)
                    return {"ok": True}

                c, o, contract = await analyze_ticker(tk, "1h", user, announce=False, use_cache=False)
                if c is None:
                    send("❌ تعذر تحليل السهم حالياً", earnings_menu(), chat_id=user)
                    return {"ok": True}

                trade_view = build_earnings_trade_view(tk, c, o, contract, event)
                send(msg_earnings_analysis(tk, event, c, o, contract, trade_view), main_menu(), chat_id=user)
                return {"ok": True}

            if data_cb == "whale_reports_menu":
                send("🐋 اختر تقرير عقود الحيتان 👇", whale_report_menu(), chat_id=user)
                return {"ok": True}

            if data_cb == "whale_daily_report_img":
                rows = whale_rows_for_day()
                send_report_image(rows, "تقرير عقود الحيتان اليومي", datetime.now(RIYADH_TZ).strftime("%d/%m/%Y"), chat_id=user, keyboard=whale_report_menu())
                return {"ok": True}

            if data_cb == "whale_weekly_report_img":
                rows, ws, we = whale_rows_for_week()
                send_report_image(rows, "تقرير عقود الحيتان الأسبوعي", f"{ws.strftime('%d/%m/%Y')} - {we.strftime('%d/%m/%Y')}", chat_id=user, keyboard=whale_report_menu())
                return {"ok": True}

            if data_cb == "whale_yearly_report_img":
                y = datetime.now(RIYADH_TZ).year
                rows = whale_rows_for_year(y)
                send_report_image(rows, "تقرير عقود الحيتان السنوي", str(y), chat_id=user, keyboard=whale_report_menu())
                return {"ok": True}

            if data_cb == "whale_report_months":
                send("📅 اختر شهر تقرير الحيتان من الأرشيف 👇", whale_months_archive_menu(), chat_id=user)
                return {"ok": True}

            if data_cb.startswith("whale_month_report:"):
                try:
                    _, y, m = data_cb.split(":")
                    y, m = int(y), int(m)
                    rows = whale_rows_for_month(y, m)
                    send_report_image(rows, "تقرير عقود الحيتان الشهري", f"{m:02d}/{y}", chat_id=user, keyboard=whale_months_archive_menu())
                except Exception as e:
                    send(f"❌ تعذر عرض تقرير الحيتان الشهري: {e}", whale_report_menu(), chat_id=user)
                return {"ok": True}

            if data_cb == "reports_menu":
                send("📊 اختر نوع التقرير 👇", report_menu(), chat_id=user)
                return {"ok": True}

            if data_cb == "daily_report_img":
                rows = rows_for_day()
                send_report_image(rows, "التقرير اليومي", datetime.now(RIYADH_TZ).strftime("%d/%m/%Y"), chat_id=user, keyboard=report_menu())
                return {"ok": True}

            if data_cb == "weekly_report_img":
                rows, ws, we = rows_for_week()
                send_report_image(rows, "التقرير الأسبوعي", f"{ws.strftime('%d/%m/%Y')} - {we.strftime('%d/%m/%Y')}", chat_id=user, keyboard=report_menu())
                return {"ok": True}

            if data_cb == "yearly_report_img":
                y = datetime.now(RIYADH_TZ).year
                rows = rows_for_year(y)
                send_report_image(rows, "التقرير السنوي", str(y), chat_id=user, keyboard=report_menu())
                return {"ok": True}

            if data_cb == "report_months":
                send("📅 اختر الشهر من الأرشيف 👇", months_archive_menu(), chat_id=user)
                return {"ok": True}

            if data_cb.startswith("month_report:"):
                try:
                    _, y, m = data_cb.split(":")
                    y, m = int(y), int(m)
                    rows = rows_for_month(y, m)
                    send_report_image(rows, "التقرير الشهري", f"{m:02d}/{y}", chat_id=user, keyboard=months_archive_menu())
                except Exception as e:
                    send(f"❌ تعذر عرض التقرير الشهري: {e}", report_menu(), chat_id=user)
                return {"ok": True}

            if data_cb == "weekly_report":
                rows, ws, we = rows_for_week()
                send_report_image(rows, "التقرير الأسبوعي", f"{ws.strftime('%d/%m/%Y')} - {we.strftime('%d/%m/%Y')}", chat_id=user, keyboard=main_menu())
                return {"ok": True}

            if data_cb == "econ_menu":
                send("📰 اختر قسم الأخبار المهمة 👇", econ_menu(), chat_id=user)
                return {"ok": True}

            if data_cb == "econ:today":
                send(format_economic_message("today"), main_menu(), chat_id=user)
                return {"ok": True}

            if data_cb == "econ:week":
                send(format_economic_message("week"), main_menu(), chat_id=user)
                return {"ok": True}

            if data_cb == "econ:nextweek":
                send(format_economic_message("nextweek"), main_menu(), chat_id=user)
                return {"ok": True}

            if data_cb.startswith("settf:"):
                new_tf = data_cb.split(":")[1]
                if new_tf not in TF:
                    send("❌ هذا الفريم غير مدعوم", main_menu(), chat_id=user)
                    return {"ok": True}

                set_state(user, tf=new_tf)
                tf = new_tf

                if ticker:
                    send(f"✅ تم تغيير الفريم إلى <b>{new_tf}</b>\n⏳ جاري إعادة التحليل...", chat_id=user)
                    c, o, contract = await analyze_ticker(ticker, tf, user, announce=False, use_cache=False)
                    if c:
                        send(msg_pro(ticker, tf, c, o, contract), main_menu(), chat_id=user)
                else:
                    send(f"✅ تم تغيير الفريم إلى <b>{new_tf}</b>\n\nأرسل رمز السهم الآن 👇", main_menu(), chat_id=user)
                return {"ok": True}

            if data_cb == "back":
                send("🏠 القائمة الرئيسية", main_menu(), chat_id=user)
                return {"ok": True}

            if data_cb == "open_contracts":
                send(msg_open_contracts(), main_menu(), chat_id=user)
                return {"ok": True}

            if data_cb == "daily_report":
                rows = rows_for_day()
                send_report_image(rows, "التقرير اليومي", datetime.now(RIYADH_TZ).strftime("%d/%m/%Y"), chat_id=user, keyboard=main_menu())
                return {"ok": True}

            if not ticker:
                send("❗ أرسل رمز السهم أولاً مثل: <code>NVDA</code>\nثم اضغط الزر مرة ثانية", main_menu(), chat_id=user)
                return {"ok": True}

            if ticker not in set(WATCHLIST) | set(FRIDAY_ZERO_HERO_TICKERS):
                send(f"❌ السهم <b>{ticker}</b> غير موجود في القائمة", chat_id=user)
                return {"ok": True}

            c, o, contract = await analyze_ticker(ticker, tf, user, announce=False, use_cache=True)
            if c is None:
                return {"ok": True}

            if data_cb == "quick":
                send(msg_quick(ticker, tf, c), main_menu(), chat_id=user)
            elif data_cb == "pro":
                send(msg_pro(ticker, tf, c, o, contract), main_menu(), chat_id=user)
            elif data_cb == "gamma":
                send(msg_gamma(ticker, tf, c, o), main_menu(), chat_id=user)
            elif data_cb == "sr":
                send(msg_sr(ticker, tf, c), main_menu(), chat_id=user)
            elif data_cb == "plan":
                send(msg_plan(ticker, tf, c), main_menu(), chat_id=user)
            elif data_cb == "contract":
                send(msg_contract(ticker, tf, c, contract), main_menu(), chat_id=user)
            else:
                send("❌ الزر غير معروف أو غير مربوط بشكل صحيح", main_menu(), chat_id=user)

            return {"ok": True}

    except Exception as e:
        try:
            err_user = None
            if "message" in data:
                err_user = str(data["message"]["chat"]["id"])
            elif "callback_query" in data:
                err_user = str(data["callback_query"]["message"]["chat"]["id"])
            if err_user:
                send(f"❌ خطأ: {str(e)}", chat_id=err_user)
        except Exception:
            pass

        print(f"[WEBHOOK ERROR] {e}")

    return {"ok": True}

# =========================
# حالة السيرفر
# =========================

@app.get("/")
def home():
    return {
        "status": "LIVE ✅",
        "api": "Polygon.io + FMP",
        "watchlist_count": len(get_active_watchlist()),
        "daily_limit": MAX_SIGNALS_PER_DAY,
        "stock_cooldown_days": STOCK_COOLDOWN_DAYS,
        "trend_confirm_hours": TREND_CONFIRM_HOURS,
        "max_company_contract_price": MAX_COMPANY_CONTRACT_PRICE,
        "max_spac_contract_price": MAX_SPAC_CONTRACT_PRICE,
        "friday_zero_hero_enabled": FRIDAY_ZERO_HERO_ENABLED,
        "zero_hero_price_range": f"{ZERO_HERO_MIN_PRICE} - {ZERO_HERO_MAX_PRICE}",
        "features": [
            "أهداف CALL و PUT منفصلة",
            "جميع الفريمات",
            "زيرو هيرو الجمعة",
            "صياد 5 شركات يومياً",
            "عقود لجميع الأسهم",
            "إعلانات الشركات",
            "التقرير الأسبوعي",
            "TP1 ثابت + TP2/TP3 من شارت العقد",
            "الأخبار الاقتصادية المهمة",
            "تنبيه قبل الخبر بـ 5 دقائق",
            "TradingView webhook",
            "/start سريع وثابت"
        ]
    }
