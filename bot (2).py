from fastapi import FastAPI, Request
import requests
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

# =========================
# إعدادات الصياد
# =========================

MAX_SIGNALS_PER_DAY = 5
STOCK_COOLDOWN_DAYS = 3
TREND_CONFIRM_HOURS = 3
SCAN_INTERVAL_SECONDS = 3600

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
SIGNAL_HISTORY = []
ECON_ALERT_SENT = set()

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
    return datetime.now().weekday() == 4

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
IV: {contract['iv']:.4f} | OI: {contract['oi']}"""

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

⚠️ تنبيه: هذا الطرح تعليمي
والقرار النهائي يعود للمتداول

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

def msg_open_contracts():
    if not OPEN_CONTRACT_SIGNALS:
        return "📂 لا توجد عقود مفتوحة حالياً."

    msg = "📂 <b>العقود المفتوحة</b>\n\n"

    for i, (_, sig) in enumerate(OPEN_CONTRACT_SIGNALS.items(), 1):
        msg += (
            f"{i}. <b>{sig['ticker']}</b>\n"
            f"العقد: <code>{sig['option_ticker']}</code>\n"
            f"النوع: {'CALL' if sig['contract_type'] == 'call' else 'PUT'}\n"
            f"سعر الدخول: {sig['entry_price']:.2f}\n"
            f"أعلى سعر: {sig['highest_price']:.2f}\n"
            f"TP1: {sig['tp1']:.2f} | TP2: {sig['tp2']:.2f} | TP3: {sig['tp3']:.2f}\n"
            f"تم التحديث الأول: {'نعم' if sig['first_update_sent'] else 'لا'}\n"
            f"وقت الإضافة: {sig['created_at'].strftime('%d/%m %H:%M')}\n\n"
        )

    return msg

def msg_daily_report():
    reset_daily_counter_if_needed()

    msg = (
        f"📋 <b>التقرير اليومي</b>\n\n"
        f"📊 عدد الإشارات اليوم: {DAILY_SIGNAL_STATE['count']}/{MAX_SIGNALS_PER_DAY}\n"
        f"📂 العقود المفتوحة حالياً: {len(OPEN_CONTRACT_SIGNALS)}\n"
        f"📈 الأسهم في القائمة: {len(WATCHLIST)}\n\n"
    )

    if OPEN_CONTRACT_SIGNALS:
        best_sig = max(
            OPEN_CONTRACT_SIGNALS.values(),
            key=lambda x: ((x['highest_price'] - x['entry_price']) / x['entry_price']) if x['entry_price'] > 0 else 0
        )
        best_pnl = ((best_sig["highest_price"] - best_sig["entry_price"]) / best_sig["entry_price"]) * 100 if best_sig["entry_price"] > 0 else 0

        msg += (
            f"🏆 <b>أفضل عقد اليوم</b>\n"
            f"{best_sig['ticker']} | {'CALL' if best_sig['contract_type'] == 'call' else 'PUT'}\n"
            f"سعر الدخول: {best_sig['entry_price']:.2f}\n"
            f"أعلى سعر: {best_sig['highest_price']:.2f}\n"
            f"نسبة الربح: {best_pnl:+.2f}%\n"
        )
    else:
        msg += "ℹ️ لا توجد عقود مفتوحة لعرض أفضل أداء حالياً."

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
    wins = 0
    losses = 0
    call_count = 0
    put_count = 0
    tp1_hits = 0
    tp2_hits = 0
    tp3_hits = 0

    best_row = None
    worst_row = None
    total_pnl = 0.0

    for row in week_rows:
        entry = row.get("entry_price", 0) or 0
        high = row.get("highest_price", entry) or entry
        pnl = ((high - entry) / entry) * 100 if entry > 0 else 0.0
        total_pnl += pnl

        if high >= row.get("tp1", 10**9):
            tp1_hits += 1
        if high >= row.get("tp2", 10**9):
            tp2_hits += 1
        if high >= row.get("tp3", 10**9):
            tp3_hits += 1

        if pnl > 0:
            wins += 1
        else:
            losses += 1

        if row.get("contract_type") == "call":
            call_count += 1
        else:
            put_count += 1

        if best_row is None or pnl > best_row["pnl"]:
            best_row = {"row": row, "pnl": pnl}
        if worst_row is None or pnl < worst_row["pnl"]:
            worst_row = {"row": row, "pnl": pnl}

    success_rate = (wins / total) * 100 if total else 0
    avg_pnl = total_pnl / total if total else 0

    msg = f"""🗓 <b>التقرير الأسبوعي</b>

📅 الفترة: {week_start.strftime('%d/%m')} - {week_end.strftime('%d/%m')}

📊 إجمالي العقود: {total}
✅ الرابحة: {wins}
❌ الخاسرة: {losses}
📈 نسبة النجاح: <b>{success_rate:.2f}%</b>

📦 توزيع العقود:
🟢 Call: {call_count}
🔴 Put: {put_count}

🎯 تحقيق الأهداف:
TP1: {tp1_hits}/{total}
TP2: {tp2_hits}/{total}
TP3: {tp3_hits}/{total}

📉 متوسط الأداء: {avg_pnl:+.2f}%"""

    if best_row:
        r = best_row["row"]
        msg += f"""

🏆 <b>أفضل عقد بالأسبوع</b>
{r['ticker']} | {'CALL' if r['contract_type'] == 'call' else 'PUT'}
دخول: {r['entry_price']:.2f}
الأعلى: {r['highest_price']:.2f}
الربح: {best_row['pnl']:+.2f}%"""

    if worst_row:
        r = worst_row["row"]
        msg += f"""

📉 <b>أضعف عقد بالأسبوع</b>
{r['ticker']} | {'CALL' if r['contract_type'] == 'call' else 'PUT'}
دخول: {r['entry_price']:.2f}
الأعلى: {r['highest_price']:.2f}
النتيجة: {worst_row['pnl']:+.2f}%"""

    msg += """

⚠️ تنبيه: هذا التقرير تعليمي
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
        "tp1": contract["tp1"],
        "tp2": contract["tp2"],
        "tp3": contract["tp3"],
        "first_update_sent": False,
        "last_update_trigger_price": contract["tp1"],
        "created_at": datetime.now(),
        "channel_title": f"{ticker} ${contract['strike']:.2f} {'كول' if contract['contract_type'] == 'call' else 'بوت'}"
    }
    OPEN_CONTRACT_SIGNALS[key] = row
    SIGNAL_HISTORY.append(row)

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
    candidates = [
        item.get("date"),
        item.get("datetime"),
        item.get("eventDate"),
        item.get("timestamp")
    ]
    for c in candidates:
        if not c:
            continue
        try:
            s = str(c).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=MARKET_TZ)
            return dt.astimezone(RIYADH_TZ)
        except Exception:
            try:
                dt = datetime.strptime(str(c), "%Y-%m-%d %H:%M:%S")
                dt = dt.replace(tzinfo=MARKET_TZ)
                return dt.astimezone(RIYADH_TZ)
            except Exception:
                pass
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

    rows = fmp_get("/economic-calendar", params={"from": day_from, "to": day_to})  # fixed endpoint
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
        data = fmp_get("/earning_calendar", params={"from": date_str, "to": date_str})
        results = data if isinstance(data, list) else []
        filtered = []

        for item in results:
            ticker = (item.get("symbol") or "").upper().strip()
            if not ticker or ticker not in WATCHLIST:
                continue

            item["ticker"] = ticker
            item["date"] = item.get("date", date_str)
            item["time"] = item.get("time", "")
            item["session_label"] = classify_earnings_session(item.get("time", ""), item)
            item["estimated_eps"] = item.get("epsEstimated")
            item["previous_eps"] = item.get("eps")
            item["estimated_revenue"] = item.get("revenueEstimated")
            item["previous_revenue"] = item.get("revenue")
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

    for ticker in WATCHLIST:
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
        send(msg_channel_post(ticker, contract), chat_id=CHAT_ID)

        register_contract_signal(ticker, contract)
        mark_stock_sent(ticker)
        add_daily_signal()
        sent_now += 1

        if sent_now >= MAX_SIGNALS_PER_DAY:
            break

def contract_update_cycle():
    for option_ticker, sig in list(OPEN_CONTRACT_SIGNALS.items()):
        try:
            price = get_live_contract_price(sig["ticker"], option_ticker)
            if price is None:
                continue

            if price > sig["highest_price"]:
                sig["highest_price"] = price

            if (not sig["first_update_sent"]) and price >= sig["tp1"]:
                send(msg_contract_update(sig["channel_title"], sig["entry_price"], price), chat_id=CHAT_ID)
                sig["first_update_sent"] = True
                sig["last_update_trigger_price"] = price
                continue

            if sig["first_update_sent"] and price >= sig["last_update_trigger_price"] + UPDATE_STEP_AFTER_TP1:
                send(msg_contract_update(sig["channel_title"], sig["entry_price"], price), chat_id=CHAT_ID)
                sig["last_update_trigger_price"] = price

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
    await asyncio.sleep(10)
    while True:
        try:
            await asyncio.to_thread(scanner_cycle)
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
    asyncio.create_task(scanner_loop())
    asyncio.create_task(contract_update_loop())
    asyncio.create_task(economic_alert_loop())
    send("✅ البوت شغال ومتصل!\n🔍 الصياد يبدأ بعد 10 ثواني…", chat_id=CHAT_ID)

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
                {"text": "📋 التقرير اليومي", "callback_data": "daily_report"},
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

        if ticker not in WATCHLIST:
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
            send(msg_channel_post(ticker, contract), chat_id=CHAT_ID)
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

            if not text:
                send("❌ أرسل رمز سهم صحيح مثل: <code>NVDA</code>", chat_id=user)
                return {"ok": True}

            parts = text.upper().split()
            ticker = parts[0]
            tf = parts[1].lower() if len(parts) > 1 else get_state(user)["tf"]

            if ticker not in WATCHLIST:
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

            if data_cb == "weekly_report":
                send(msg_weekly_report(), main_menu(), chat_id=user)
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
                send(msg_daily_report(), main_menu(), chat_id=user)
                return {"ok": True}

            if not ticker:
                send("❗ أرسل رمز السهم أولاً مثل: <code>NVDA</code>\nثم اضغط الزر مرة ثانية", main_menu(), chat_id=user)
                return {"ok": True}

            if ticker not in WATCHLIST:
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
        "watchlist_count": len(WATCHLIST),
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
