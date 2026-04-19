from fastapi import FastAPI, Request
import requests
import yfinance as yf
import pandas as pd
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

app = FastAPI()

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("options_bot")

# =========================
# بياناتك
# =========================
TOKEN = "PUT_YOUR_TELEGRAM_BOT_TOKEN_HERE"
CHAT_ID = "PUT_YOUR_CHAT_ID_HERE"
MASSIVE_API_KEY = "PUT_YOUR_MASSIVE_API_KEY_HERE"

API_SEND = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
API_ANSWER = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
MASSIVE_BASE = "https://api.massive.com"

# =========================
# إعدادات الصياد
# =========================
MAX_SIGNALS_PER_DAY = 5
STOCK_COOLDOWN_DAYS = 3
TREND_CONFIRM_HOURS = 3
SCAN_INTERVAL_SECONDS = 10800  # كل 3 ساعات

# =========================
# فلتر الدخول المباشر
# =========================
ENTRY_MAX_DISTANCE_PCT = 0.015
BREAKOUT_BUFFER_PCT = 0.003

# =========================
# شروط العقود الأساسية
# =========================
MAX_COMPANY_CONTRACT_PRICE = 3.50
MAX_INDEX_CONTRACT_PRICE = 3.70
ENTRY_ZONE_WIDTH = 0.60
UPDATE_STEP_AFTER_TP1 = 0.30

# =========================
# زيرو هيرو الجمعة
# =========================
FRIDAY_ZERO_HERO_ENABLED = True
ZERO_HERO_ONLY_ON_FRIDAY = True
ZERO_HERO_MIN_PRICE = 0.20
ZERO_HERO_MAX_PRICE = 2.00
ZERO_HERO_MIN_SUCCESS_RATE = 75
ZERO_HERO_MIN_OI = 100
ZERO_HERO_MIN_PROB = 65

# =========================
# أصول الارتكاز اليومي
# =========================
INDEX_DAILY_PIVOT = {"US500", "SPY", "QQQ", "SPX", "SPXW", "NDX", "US100"}

# =========================
# فئات الرموز
# =========================
SPAC_TICKERS = {"NBIS", "CRCL", "CRWV"}
INDEX_OPTION_TICKERS = {"SPXW", "SPX", "SPY", "QQQ", "US500", "NDX", "US100"}

# =========================
# قائمة الشركات + المؤشرات
# =========================
WATCHLIST = list(dict.fromkeys([
    "GLD","IBM","V","JPM","SBUX","MMM","QCOM","GOOG","INTC","NFLX","GS","SMH",
    "ABNB","TWLO","DASH","PYPL",
    "DHI","BE","ENPH","JNJ","DELL","BIDU","RDDT","DDOG","UPS","DE","NOW","UBER","INTU",
    "LRCX","LOW","HD","PANW","BA","ZS","MRVL","ULTA","SMCI","MARA","MCD","PDD","FDX",
    "FSLR","COST","SHOP","ALB","NBIS","ARM","CRCL","ABBV","HOOD","BABA","ADBE","LULU","ORCL",
    "LLY","TSM","CVNA","COIN","CRWV","CAT","AMD","SNOW","MDB","AMZN","MU","CRM","GE",
    "NVDA","AAPL","GOOGL","MSFT","TSLA","META","AVGO","CRWD","APP","UNH","MSTR","PLTR",
    "US500","SPY","QQQ","SPX","SPXW","NDX","US100"
]))

HTTP = requests.Session()

# =========================
# منع التكرار
# =========================
_USER_LAST_ACTION = {}
USER_COOLDOWN_SECONDS = 5

def allow(user: str) -> bool:
    now_ts = datetime.now().timestamp()
    last_ts = _USER_LAST_ACTION.get(user)
    if last_ts is not None and (now_ts - last_ts) < USER_COOLDOWN_SECONDS:
        return False
    _USER_LAST_ACTION[user] = now_ts
    return True

# =========================
# تتبع الإشارات
# =========================
LAST_SENT_STOCK = {}
TREND_STATE = {}
DAILY_SIGNAL_STATE = {
    "date": datetime.now().date(),
    "count": 0
}

# =========================
# تتبع العقود المطروحة
# =========================
OPEN_CONTRACT_SIGNALS = {}

# =========================
# Helpers عامة
# =========================
def now_local() -> datetime:
    return datetime.now()

def reset_daily_counter_if_needed():
    today = now_local().date()
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
    return now_local() - last_sent < timedelta(days=STOCK_COOLDOWN_DAYS)

def mark_stock_sent(ticker: str):
    LAST_SENT_STOCK[ticker] = now_local()

# =========================
# إرسال
# =========================
def send(msg, keyboard=None, chat_id=None):
    target_chat_id = str(chat_id) if chat_id is not None else CHAT_ID
    payload = {
        "chat_id": target_chat_id,
        "text": msg,
        "disable_web_page_preview": True
    }
    if keyboard:
        payload["reply_markup"] = keyboard
    try:
        r = HTTP.post(API_SEND, json=payload, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        logger.exception("Telegram send failed: %s", e)

def answer_callback(cb_id, text=""):
    try:
        r = HTTP.post(API_ANSWER, json={"callback_query_id": cb_id, "text": text}, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Callback answer failed: %s", e)

# =========================
# لوحة الأزرار
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
                {"text": "⚙️ تغيير الفريم", "callback_data": "tf"},
            ]
        ]
    }

def tf_menu():
    tfs = ["1m","5m","15m","30m","1h","4h","1d","1w"]
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
    "1m": ("5d","1m"),
    "5m": ("1mo","5m"),
    "15m": ("1mo","15m"),
    "30m": ("1mo","30m"),
    "1h": ("3mo","60m"),
    "4h": ("6mo","1h"),
    "1d": ("1y","1d"),
    "1w": ("3y","1wk"),
}

# =========================
# تحويل بعض الرموز لـ yfinance
# =========================
def map_symbol_for_data(ticker: str) -> str:
    mapping = {
        "SPX": "^GSPC",
        "SPXW": "^GSPC",
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
# Massive helpers
# =========================
def massive_get(path: str, params=None):
    params = params or {}
    params["apiKey"] = MASSIVE_API_KEY
    url = f"{MASSIVE_BASE}{path}"
    try:
        r = HTTP.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.exception("Massive request failed | path=%s | error=%s", path, e)
        raise

def safe_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur

def parse_contract_price_from_snapshot(item):
    candidates = [
        safe_get(item, "last_trade", "price"),
        safe_get(item, "last_trade", "p"),
        safe_get(item, "session", "close"),
        safe_get(item, "details", "last_price"),
        safe_get(item, "day", "close"),
    ]
    for x in candidates:
        try:
            if x is not None:
                return float(x)
        except (TypeError, ValueError):
            continue
    return None

def parse_underlying_price_from_snapshot(item):
    candidates = [
        safe_get(item, "underlying_asset", "price"),
        safe_get(item, "underlying_asset", "last", "price"),
        safe_get(item, "underlying_asset", "last_trade", "price"),
        safe_get(item, "underlying_asset", "last_trade", "p"),
    ]
    for x in candidates:
        try:
            if x is not None:
                return float(x)
        except (TypeError, ValueError):
            continue
    return None

def parse_contract_meta(item):
    details = safe_get(item, "details", default={}) or {}
    return {
        "ticker": details.get("ticker") or item.get("ticker") or item.get("sym") or item.get("option_ticker"),
        "strike": float(details.get("strike_price", 0) or 0),
        "expiration": details.get("expiration_date", ""),
        "contract_type": (details.get("contract_type") or "").lower(),
        "delta": float(safe_get(item, "greeks", "delta", default=0) or 0),
        "gamma": float(safe_get(item, "greeks", "gamma", default=0) or 0),
        "iv": float(item.get("implied_volatility", 0) or 0),
        "oi": int(item.get("open_interest", 0) or 0),
        "contract_price": parse_contract_price_from_snapshot(item),
        "underlying_price": parse_underlying_price_from_snapshot(item),
    }

def get_option_chain_snapshot(underlying: str):
    data = massive_get(f"/v3/snapshot/options/{underlying}")
    results = data.get("results", [])
    if isinstance(results, dict):
        if "results" in results and isinstance(results["results"], list):
            results = results["results"]
        else:
            results = []
    return results

def get_option_contract_snapshot(underlying: str, option_contract: str):
    data = massive_get(f"/v3/snapshot/options/{underlying}/{option_contract}")
    return data.get("results", data)

def get_option_last_trade(option_contract: str):
    data = massive_get(f"/v2/last/trade/{option_contract}")
    return data.get("results", {})

# =========================
# أدوات خاصة بالعقود
# =========================
def is_spac_ticker(ticker: str) -> bool:
    return ticker in SPAC_TICKERS

def is_index_option_ticker(ticker: str) -> bool:
    return ticker in INDEX_OPTION_TICKERS

def is_friday_now() -> bool:
    return now_local().weekday() == 4

def contract_price_limit_for_ticker(ticker: str) -> float:
    if is_index_option_ticker(ticker):
        return MAX_INDEX_CONTRACT_PRICE
    return MAX_COMPANY_CONTRACT_PRICE

def days_to_expiry(expiration_str: str) -> Optional[int]:
    try:
        exp = datetime.strptime(expiration_str, "%Y-%m-%d").date()
        return (exp - now_local().date()).days
    except Exception as e:
        logger.debug("days_to_expiry parse failed for %s: %s", expiration_str, e)
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
        TREND_STATE[ticker] = {
            "side": side,
            "confirmed_at": now_local(),
            "candidate_side": side,
            "candidate_since": now_local()
        }
        return side

    if prev["side"] == side:
        prev["candidate_side"] = side
        prev["candidate_since"] = now_local()
        return side

    if side == "neutral":
        return prev["side"]

    if prev.get("candidate_side") != side:
        prev["candidate_side"] = side
        prev["candidate_since"] = now_local()
        return prev["side"]

    if now_local() - prev["candidate_since"] >= timedelta(hours=TREND_CONFIRM_HOURS):
        prev["side"] = side
        prev["confirmed_at"] = now_local()
        return side

    return prev["side"]

# =========================
# حسابات أساسية
# =========================
def compute_dynamic_entry_buffer(price: float, ref_range: float) -> float:
    vol_component = ref_range * 0.05
    pct_component = price * 0.0025
    buffer_value = max(0.15, min(max(vol_component, pct_component), max(price * 0.01, 0.15)))
    return round(buffer_value, 2)

def core_metrics(df, ticker=None):
    if df.empty:
        return None

    price = float(df["Close"].iloc[-1])

    if ticker in INDEX_DAILY_PIVOT:
        ref = get_df(ticker, "1d")
        if ref.empty or len(ref) < 2:
            return None
        prev = ref.iloc[-2]
        ref_high = float(prev["High"])
        ref_low = float(prev["Low"])
        ref_close = float(prev["Close"])
        pivot_label = "اليومي"
    else:
        ref = get_df(ticker, "1w")
        if ref.empty or len(ref) < 2:
            return None
        prev = ref.iloc[-2]
        ref_high = float(prev["High"])
        ref_low = float(prev["Low"])
        ref_close = float(prev["Close"])
        pivot_label = "الأسبوعي"

    pivot = (ref_high + ref_low + ref_close) / 3.0
    ref_range = ref_high - ref_low

    # أهداف الكول
    call_tp1 = pivot + ref_range * 0.5
    call_tp2 = pivot + ref_range
    call_tp3 = ref_high + ref_range

    # أهداف البوت
    put_tp1 = pivot - ref_range * 0.5
    put_tp2 = pivot - ref_range
    put_tp3 = ref_low - ref_range

    sl = pivot

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

    if trend == "صاعد 📈" and price > pivot and confirmed_side == "above":
        direction = "CALL 🟢"
    elif trend == "هابط 📉" and price < pivot and confirmed_side == "below":
        direction = "PUT 🔴"
    else:
        direction = "انتظار ⚪"

    entry_buffer = compute_dynamic_entry_buffer(price, ref_range)

    if direction.startswith("CALL"):
        best_entry = pivot + entry_buffer
    elif direction.startswith("PUT"):
        best_entry = pivot - entry_buffer
    else:
        best_entry = pivot

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
        "sl": sl,
        "trend": trend,
        "strongest_trend": strongest_trend,
        "direction": direction,
        "best_entry": best_entry,
        "entry_buffer": entry_buffer,
        "confirmed_side": confirmed_side,
        "ema20": ema20,
        "ema50": ema50
    }

# =========================
# معلومات القاما والسيولة
# =========================
def options_info_from_massive(ticker, price):
    try:
        chain = get_option_chain_snapshot(ticker)
        if not chain:
            raise ValueError("empty chain")

        parsed = [parse_contract_meta(x) for x in chain]
        parsed = [x for x in parsed if x["ticker"] and x["contract_price"] is not None]

        if not parsed:
            raise ValueError("no valid contracts")

        calls = [x for x in parsed if x["contract_type"] == "call"]
        puts = [x for x in parsed if x["contract_type"] == "put"]

        best_call_oi = max(calls, key=lambda x: x["oi"]) if calls else None
        best_put_oi = max(puts, key=lambda x: x["oi"]) if puts else None

        near_price_contracts = sorted(parsed, key=lambda x: abs(x["strike"] - price))[:20]
        gamma_candidates = [x for x in near_price_contracts if abs(x["gamma"]) > 0]

        if gamma_candidates:
            gamma_anchor_contract = max(
                gamma_candidates,
                key=lambda x: (abs(x["gamma"]) * max(x["oi"], 1))
            )
            gamma_anchor = gamma_anchor_contract["strike"]
        else:
            gamma_anchor = price

        magnet_width = max(0.5, round(price * 0.005, 2))
        zone_low = gamma_anchor - magnet_width
        zone_high = gamma_anchor + magnet_width

        dist_pct = abs(price - gamma_anchor) / max(price, 1e-9)
        prob = int(max(50, min(85, 85 - dist_pct * 100 * 2)))

        call_strike = best_call_oi["strike"] if best_call_oi else price
        put_strike = best_put_oi["strike"] if best_put_oi else price

        if best_call_oi and best_put_oi:
            if best_call_oi["oi"] > best_put_oi["oi"]:
                liquidity = "CALL 🟢"
            elif best_put_oi["oi"] > best_call_oi["oi"]:
                liquidity = "PUT 🔴"
            else:
                liquidity = "متوازن ⚖️"
        else:
            liquidity = "—"

        return {
            "call": call_strike,
            "put": put_strike,
            "gamma": gamma_anchor,
            "zlow": zone_low,
            "zhigh": zone_high,
            "prob": prob,
            "liq": liquidity,
            "note": "قراءة تقريبية مبنية على OI و Gamma وليست Gamma Exposure كامل."
        }
    except Exception as e:
        logger.warning("options_info_from_massive failed for %s: %s", ticker, e)
        return {
            "call": price,
            "put": price,
            "gamma": price,
            "zlow": price,
            "zhigh": price,
            "prob": 50,
            "liq": "—",
            "note": "تعذر جلب قراءة السلسلة."
        }

# =========================
# حساب نسبة/درجة التوافق
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
# شركات <= 3.50
# SPX/SPXW والمؤشرات <= 3.70
# قرب السترايك له وزن أقل، وجودة العقد أهم
# =========================
def choose_best_contract_from_massive(ticker: str, c: dict, o: dict = None):
    try:
        chain = get_option_chain_snapshot(ticker)
        if not chain:
            logger.info("[CONTRACT DEBUG] %s: empty chain", ticker)
            return None

        parsed = [parse_contract_meta(x) for x in chain]
        parsed = [x for x in parsed if x["ticker"] and x["contract_price"] is not None]

        if not parsed:
            logger.info("[CONTRACT DEBUG] %s: no parsed contracts", ticker)
            return None

        direction = c["direction"]
        if direction.startswith("CALL"):
            target_type = "call"
        elif direction.startswith("PUT"):
            target_type = "put"
        else:
            logger.info("[CONTRACT DEBUG] %s: no direction", ticker)
            return None

        underlying_price = c["price"]
        prob = o["prob"] if o else 50
        limit_price = contract_price_limit_for_ticker(ticker)

        # =========================
        # زيرو هيرو الجمعة
        # =========================
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
                if dte is None or dte < 0 or dte > 3:
                    continue

                strike_distance_pct = abs(x["strike"] - underlying_price) / max(underlying_price, 1e-9)
                delta_score = abs(abs(x["delta"]) - 0.30)

                score = (
                    strike_distance_pct * 8
                    + delta_score * 8
                    - min(x["oi"], 100000) / 10000
                    - min(abs(x["gamma"]), 1.0) * 7
                    + abs(x["contract_price"] - 1.00) * 0.5
                )
                zero_hero_pool.append((score, x))

            if zero_hero_pool:
                zero_hero_pool.sort(key=lambda z: z[0])
                best = zero_hero_pool[0][1]
                contract = build_contract_from_pick(best, c, target_type, mode="ZERO HERO FRIDAY")
                success_rate = calc_success_rate(c, o or {"prob": 50}, contract)
                if success_rate >= ZERO_HERO_MIN_SUCCESS_RATE:
                    contract["success_rate"] = success_rate
                    logger.info("[CONTRACT DEBUG] %s: zero hero picked %s @ %s",
                                ticker, contract["option_ticker"], contract["contract_price"])
                    return contract

        # =========================
        # المرحلة 1: أفضل عقد داخل حد السعر
        # لا نشدد على قرب السترايك
        # =========================
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
            if dte is None or dte < 0 or dte > 45:
                continue
            if x["oi"] < 10:
                continue

            strike_distance_pct = abs(x["strike"] - underlying_price) / max(underlying_price, 1e-9)
            delta_score = abs(abs(x["delta"]) - 0.35)

            score = (
                strike_distance_pct * 6
                + delta_score * 12
                + min(dte, 45) / 18
                - min(x["oi"], 100000) / 9000
                - min(abs(x["gamma"]), 1.0) * 6
                + x["contract_price"] * 0.15
            )

            if 0.22 <= abs(x["delta"]) <= 0.45:
                score -= 2.5

            if x["oi"] >= 500:
                score -= 1.5
            if x["oi"] >= 1500:
                score -= 1.5

            stage1.append((score, x))

        if stage1:
            stage1.sort(key=lambda z: z[0])
            best = stage1[0][1]
            contract = build_contract_from_pick(best, c, target_type, mode="NORMAL")
            contract["success_rate"] = calc_success_rate(c, o or {"prob": 50}, contract)
            logger.info("[CONTRACT DEBUG] %s: stage1 picked %s @ %s",
                        ticker, contract["option_ticker"], contract["contract_price"])
            return contract

        # =========================
        # المرحلة 2: مرونة أكثر لكن داخل حد السعر فقط
        # =========================
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
            if dte is None or dte < 0:
                continue

            strike_distance_pct = abs(x["strike"] - underlying_price) / max(underlying_price, 1e-9)
            delta_score = abs(abs(x["delta"]) - 0.30)

            score = (
                strike_distance_pct * 5
                + delta_score * 10
                + min(max(dte, 0), 60) / 20
                - min(x["oi"], 100000) / 12000
                + x["contract_price"] * 0.10
            )
            stage2.append((score, x))

        if stage2:
            stage2.sort(key=lambda z: z[0])
            best = stage2[0][1]
            contract = build_contract_from_pick(best, c, target_type, mode="NORMAL")
            contract["success_rate"] = calc_success_rate(c, o or {"prob": 50}, contract)
            logger.info("[CONTRACT DEBUG] %s: stage2 picked %s @ %s",
                        ticker, contract["option_ticker"], contract["contract_price"])
            return contract

        logger.info("[CONTRACT DEBUG] %s: no usable contract found under limit %.2f", ticker, limit_price)
        return None

    except Exception as e:
        logger.exception("[CONTRACT PICK ERROR] %s: %s", ticker, e)
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

# =========================
# فلتر الدخول
# =========================
def is_entry_ready_now(c):
    if c["direction"] == "انتظار ⚪":
        return False

    price = c["price"]
    entry = c["best_entry"]

    near_entry = abs(price - entry) / max(abs(entry), 1e-9) <= ENTRY_MAX_DISTANCE_PCT

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
    except Exception as e:
        logger.debug("Date format parse failed for %s: %s", date_str, e)
        return date_str

# =========================
# الرسائل
# =========================
def msg_quick(tk, tf, c):
    return f"""📊 {tk} | TF: {tf}

السعر: {c['price']:.2f}
الترند: {c['trend']}
الاتجاه الأقوى: {c['strongest_trend']}

📍 الارتكاز {c['pivot_label']}: {c['pivot']:.2f}
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

🔵 دعم: {c['low']:.2f}
🔴 مقاومة: {c['high']:.2f}

📌 دخول: {c['best_entry']:.2f}
🛑 وقف: {c['sl']:.2f}

🎯 أهداف الكول:
1) {c['call_tp1']:.2f}
2) {c['call_tp2']:.2f}
3) {c['call_tp3']:.2f}

🎯 أهداف البوت:
1) {c['put_tp1']:.2f}
2) {c['put_tp2']:.2f}
3) {c['put_tp3']:.2f}

📈 القرار: {c['direction']}"""

def msg_pro(tk, tf, c, o, contract=None):
    base = f"""🔥 {tk} Professional | TF: {tf}

السعر: {c['price']:.2f}
الترند: {c['trend']}
الاتجاه الأقوى: {c['strongest_trend']}

🔵 دعم {c['pivot_label']}: {c['low']:.2f}
🔴 مقاومة {c['pivot_label']}: {c['high']:.2f}
📍 الارتكاز {c['pivot_label']}: {c['pivot']:.2f}
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

📈 القرار النهائي: {c['direction']}

🎯 أهداف الكول:
1) {c['call_tp1']:.2f}
2) {c['call_tp2']:.2f}
3) {c['call_tp3']:.2f}

🎯 أهداف البوت:
1) {c['put_tp1']:.2f}
2) {c['put_tp2']:.2f}
3) {c['put_tp3']:.2f}

🧲 معلومات داعمة:
القاما المرجحة: {o['gamma']:.2f}
Magnet: {o['zlow']:.2f} - {o['zhigh']:.2f}
احتمال الوصول التقريبي: {o['prob']}%
سيولة الكول: {o['call']:.2f}
سيولة البوت: {o['put']:.2f}
الأقوى: {o['liq']}"""

    if not contract:
        return base + "\n\n❌ لم يتم العثور على عقد مناسب."

    mode_line = f"\n🎯 الوضع: {contract.get('mode', 'NORMAL')}" if contract.get("mode") else ""

    return base + f"""

💎 العقد المختار:{mode_line}
الرمز: {contract['option_ticker']}
النوع: {contract['contract_type'].upper()}
السترايك: {contract['strike']:.2f}
الانتهاء: {format_arabic_date(contract['expiration'])}
سعر العقد الحالي: {contract['contract_price']:.2f}
نطاق الدخول: {contract['entry_high']:.2f} – {contract['entry_low']:.2f}

🎯 أهداف العقد:
1) {contract['tp1']:.2f}
2) {contract['tp2']:.2f}
3) {contract['tp3']:.2f}

🛑 الوقف: {contract['stop_text']}
📊 درجة توافق الإشارة: {contract.get('success_rate', 0)}%
Δ Delta: {contract['delta']:.2f}
Γ Gamma: {contract['gamma']:.4f}
IV: {contract['iv']:.4f}
OI: {contract['oi']}"""

def msg_channel_post(tk, contract):
    type_ar = "CALL" if contract["contract_type"] == "call" else "PUT"
    color = "🟢" if contract["contract_type"] == "call" else "🔴"

    mode_line = ""
    if contract.get("mode") == "ZERO HERO FRIDAY":
        mode_line = "\n⚡ الوضع: زيرو هيرو الجمعة"

    return f"""🆕 طرح جديد | {tk}{mode_line}

{color} النوع: {type_ar}
🎯 السترايك: ${contract['strike']:.2f}
📅 التاريخ: {format_arabic_date(contract['expiration'])}

💰 الأسعار المناسبة للدخول: {contract['entry_high']:.2f} – {contract['entry_low']:.2f}

📈 الأهداف:
🥇 {contract['tp1']:.2f}
🥈 {contract['tp2']:.2f}
🥉 {contract['tp3']:.2f}

🛑 الوقف: {contract['stop_text']}

⚠️ تنبيه: هذا الطرح تعليمي
والقرار النهائي يعود للمتداول

📢 @Option_Strike01"""

def msg_contract_update(title, entry_price, highest_price):
    pnl = ((highest_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
    return f"""🔔 تحديث | {title}

📊 سعر الدخول: {entry_price:.2f}
💰 السعر الأعلى: {highest_price:.2f}
📈 نسبة الربح: {pnl:+.2f}%

⚠️ تنبيه: هذا الطرح تعليمي
والقرار النهائي يعود للمتداول.

📢 @Option_Strike01."""

def msg_gamma(tk, tf, c, o):
    return f"""🧲 {tk} Gamma & Liquidity | TF: {tf}

🧲 القاما المرجحة: {o['gamma']:.2f}
📍 Magnet: {o['zlow']:.2f} - {o['zhigh']:.2f}
📊 احتمال الوصول التقريبي: {o['prob']}%

💰 سيولة الكول: {o['call']:.2f}
💸 سيولة البوت: {o['put']:.2f}
🔥 الأقوى: {o['liq']}

📍 الارتكاز {c['pivot_label']}: {c['pivot']:.2f}
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

الاتجاه الأقوى: {c['strongest_trend']}
السعر الحالي: {c['price']:.2f}

ℹ️ {o.get('note', '')}"""

def msg_sr(tk, tf, c):
    return f"""📈 {tk} Support/Resistance | TF: {tf}

🔵 دعم {c['pivot_label']}: {c['low']:.2f}
🔴 مقاومة {c['pivot_label']}: {c['high']:.2f}

📍 الارتكاز {c['pivot_label']}: {c['pivot']:.2f}
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

الاتجاه الأقوى: {c['strongest_trend']}"""

def msg_plan(tk, tf, c):
    return f"""🎯 {tk} Entry Plan | TF: {tf}

الاتجاه الأقوى: {c['strongest_trend']}
📍 الارتكاز {c['pivot_label']}: {c['pivot']:.2f}
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

📌 دخول: {c['best_entry']:.2f}
🛑 وقف: {c['sl']:.2f}

🎯 أهداف الكول:
1) {c['call_tp1']:.2f}
2) {c['call_tp2']:.2f}
3) {c['call_tp3']:.2f}

🎯 أهداف البوت:
1) {c['put_tp1']:.2f}
2) {c['put_tp2']:.2f}
3) {c['put_tp3']:.2f}

📈 القرار: {c['direction']}"""

def msg_contract(tk, tf, c, contract):
    if not contract:
        return "❌ لم يتم العثور على عقد مناسب."
    mode_line = f"\nMode: {contract.get('mode', 'NORMAL')}" if contract.get("mode") else ""
    return f"""💎 {tk} Best Contract | TF: {tf}{mode_line}

Type: {contract['contract_type'].upper()}
Strike: {contract['strike']:.2f}
Expiry: {contract['expiration']}
Contract Price: {contract['contract_price']:.2f}

الاتجاه الأقوى: {c['strongest_trend']}
📍 الارتكاز {c['pivot_label']}: {c['pivot']:.2f}
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

📌 نطاق الدخول: {contract['entry_high']:.2f} – {contract['entry_low']:.2f}
🛑 وقف: {contract['stop_text']}

🎯 أهداف العقد:
1) {contract['tp1']:.2f}
2) {contract['tp2']:.2f}
3) {contract['tp3']:.2f}

📊 درجة توافق الإشارة: {contract.get('success_rate', 0)}%"""

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
# تسجيل العقد
# =========================
def register_contract_signal(ticker: str, contract: dict):
    key = contract["option_ticker"]
    OPEN_CONTRACT_SIGNALS[key] = {
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
        "created_at": now_local(),
        "channel_title": f"{ticker} ${contract['strike']:.2f} {'كول' if contract['contract_type']=='call' else 'بوت'}"
    }

def get_live_contract_price(underlying: str, option_ticker: str):
    try:
        snap = get_option_contract_snapshot(underlying, option_ticker)
        price = parse_contract_price_from_snapshot(snap)
        if price is not None:
            return float(price)
    except Exception as e:
        logger.debug("Contract snapshot fetch failed | %s | %s", option_ticker, e)

    try:
        lt = get_option_last_trade(option_ticker)
        p = lt.get("p")
        if p is not None:
            return float(p)
    except Exception as e:
        logger.debug("Last trade fetch failed | %s | %s", option_ticker, e)

    return None

# =========================
# دورات خلفية
# =========================
def scanner_cycle():
    reset_daily_counter_if_needed()

    if not can_send_more_today():
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
            if c is None or c["direction"] == "انتظار ⚪":
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
            logger.warning("[SCANNER ITEM ERROR] %s: %s", ticker, e)
            continue

    results.sort(key=lambda x: x[1], reverse=True)

    sent_now = 0
    for ticker, score, c, o, contract in results:
        if not can_send_more_today():
            break

        if stock_in_cooldown(ticker):
            continue

        send(msg_pro(ticker, "1h", c, o, contract))
        send(msg_channel_post(ticker, contract))

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

            if (not sig["first_update_sent"]) and sig["highest_price"] >= sig["tp1"]:
                send(msg_contract_update(sig["channel_title"], sig["entry_price"], sig["highest_price"]))
                sig["first_update_sent"] = True
                sig["last_update_trigger_price"] = sig["highest_price"]
                continue

            if sig["first_update_sent"] and sig["highest_price"] >= sig["last_update_trigger_price"] + UPDATE_STEP_AFTER_TP1:
                send(msg_contract_update(sig["channel_title"], sig["entry_price"], sig["highest_price"]))
                sig["last_update_trigger_price"] = sig["highest_price"]

        except Exception as e:
            logger.warning("[CONTRACT UPDATE ERROR] %s: %s", option_ticker, e)

async def contract_update_loop():
    await asyncio.sleep(20)
    while True:
        try:
            await asyncio.to_thread(contract_update_cycle)
        except Exception as e:
            send(f"❌ خطأ في متابعة العقود: {str(e)}")
        await asyncio.sleep(300)

async def scanner_loop():
    await asyncio.sleep(10)
    while True:
        try:
            await asyncio.to_thread(scanner_cycle)
        except Exception as e:
            send(f"❌ خطأ في الصياد: {str(e)}")
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting bot tasks...")
    asyncio.create_task(scanner_loop())
    asyncio.create_task(contract_update_loop())
    logger.info("Bot tasks started successfully.")

# =========================
# Webhook
# =========================
@app.post("/")
async def webhook(req: Request):
    try:
        data = await req.json()
    except Exception as e:
        logger.warning("Invalid webhook JSON: %s", e)
        return {"ok": True}

    try:
        if "message" in data:
            msg = data["message"]
            text = msg.get("text", "").strip()
            user = str(msg["chat"]["id"])

            if not allow(user):
                return {"ok": True}

            if text == "/start":
                set_state(user, ticker=None, tf="1d")
                send("👋 أهلاً بك\nأرسل رمز السهم من قائمتك مثل: NVDA أو SPY\nأو اختر من القائمة 👇", main_menu(), chat_id=user)
                return {"ok": True}

            if text == "/test":
                send("✅ البوت شغال 100%", chat_id=user)
                return {"ok": True}

            if not text:
                send("❌ أرسل رمز سهم صحيح مثل: NVDA", chat_id=user)
                return {"ok": True}

            parts = text.upper().split()
            ticker = parts[0]
            tf = parts[1].lower() if len(parts) > 1 else get_state(user)["tf"]

            if ticker not in WATCHLIST:
                send("❌ هذا السهم غير موجود في قائمتك", chat_id=user)
                return {"ok": True}

            if tf not in TF:
                send("❌ الفريم غير مدعوم", chat_id=user)
                return {"ok": True}

            set_state(user, ticker=ticker, tf=tf)
            send(f"⏳ جاري تحديث تحليل {ticker}...", chat_id=user)

            df = await asyncio.to_thread(get_df, ticker, tf)
            if df.empty:
                send("❌ السهم غير صحيح أو لا توجد بيانات", chat_id=user)
                return {"ok": True}

            c = await asyncio.to_thread(core_metrics, df, ticker)
            if c is None:
                send("❌ تعذر حساب الارتكاز لهذا الأصل", chat_id=user)
                return {"ok": True}

            try:
                o = await asyncio.wait_for(
                    asyncio.to_thread(options_info_from_massive, ticker, c["price"]),
                    timeout=12
                )
            except Exception as e:
                logger.warning("options_info timeout/fail for %s: %s", ticker, e)
                o = {
                    "call": c["price"],
                    "put": c["price"],
                    "gamma": c["price"],
                    "zlow": c["price"],
                    "zhigh": c["price"],
                    "prob": 50,
                    "liq": "—",
                    "note": "fallback"
                }

            try:
                contract = await asyncio.wait_for(
                    asyncio.to_thread(choose_best_contract_from_massive, ticker, c, o),
                    timeout=15
                )
            except Exception as e:
                logger.warning("choose_best_contract timeout/fail for %s: %s", ticker, e)
                contract = None

            send(msg_pro(ticker, tf, c, o, contract), main_menu(), chat_id=user)
            if contract:
                send(msg_channel_post(ticker, contract), main_menu(), chat_id=user)

            return {"ok": True}

        if "callback_query" in data:
            cb = data["callback_query"]
            user = str(cb["message"]["chat"]["id"])
            data_cb = cb.get("data", "")
            cb_id = cb.get("id")

            answer_callback(cb_id)

            st = get_state(user)
            ticker = st.get("ticker")
            tf = st.get("tf", "1d")

            if data_cb == "tf":
                send("اختر الفريم 👇", tf_menu(), chat_id=user)
                return {"ok": True}

            if data_cb.startswith("settf:"):
                new_tf = data_cb.split(":")[1]
                if new_tf not in TF:
                    send("❌ الفريم غير مدعوم", main_menu(), chat_id=user)
                    return {"ok": True}
                set_state(user, tf=new_tf)
                send(f"تم تغيير الفريم إلى {new_tf}", main_menu(), chat_id=user)
                return {"ok": True}

            if data_cb == "back":
                send("رجوع للقائمة", main_menu(), chat_id=user)
                return {"ok": True}

            if not ticker:
                send("أرسل رمز السهم أولاً مثل: NVDA", chat_id=user)
                return {"ok": True}

            if ticker not in WATCHLIST:
                send("❌ هذا السهم غير موجود في قائمتك", chat_id=user)
                return {"ok": True}

            send(f"⏳ جاري تحديث تحليل {ticker}...", chat_id=user)

            df = await asyncio.to_thread(get_df, ticker, tf)
            if df.empty:
                send("❌ لا توجد بيانات", chat_id=user)
                return {"ok": True}

            c = await asyncio.to_thread(core_metrics, df, ticker)
            if c is None:
                send("❌ تعذر حساب الارتكاز لهذا الأصل", chat_id=user)
                return {"ok": True}

            try:
                o = await asyncio.wait_for(
                    asyncio.to_thread(options_info_from_massive, ticker, c["price"]),
                    timeout=12
                )
            except Exception as e:
                logger.warning("options_info timeout/fail for %s: %s", ticker, e)
                o = {
                    "call": c["price"],
                    "put": c["price"],
                    "gamma": c["price"],
                    "zlow": c["price"],
                    "zhigh": c["price"],
                    "prob": 50,
                    "liq": "—",
                    "note": "fallback"
                }

            try:
                contract = await asyncio.wait_for(
                    asyncio.to_thread(choose_best_contract_from_massive, ticker, c, o),
                    timeout=15
                )
            except Exception as e:
                logger.warning("choose_best_contract timeout/fail for %s: %s", ticker, e)
                contract = None

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

            return {"ok": True}

    except Exception as e:
        logger.exception("Webhook error: %s", e)
        try:
            if "message" in data:
                user = str(data["message"]["chat"]["id"])
                send(f"❌ خطأ داخلي: {str(e)}", chat_id=user)
            elif "callback_query" in data:
                user = str(data["callback_query"]["message"]["chat"]["id"])
                send(f"❌ خطأ داخلي: {str(e)}", chat_id=user)
            else:
                send(f"❌ خطأ داخلي: {str(e)}")
        except Exception as nested_e:
            logger.exception("[WEBHOOK ERROR] %s", nested_e)

    return {"ok": True}

# =========================
# حالة السيرفر
# =========================
@app.get("/")
def home():
    return {
        "status": "LIVE",
        "watchlist_count": len(WATCHLIST),
        "daily_limit": MAX_SIGNALS_PER_DAY,
        "stock_cooldown_days": STOCK_COOLDOWN_DAYS,
        "trend_confirm_hours": TREND_CONFIRM_HOURS,
        "entry_max_distance_pct": ENTRY_MAX_DISTANCE_PCT,
        "breakout_buffer_pct": BREAKOUT_BUFFER_PCT,
        "max_company_contract_price": MAX_COMPANY_CONTRACT_PRICE,
        "max_index_contract_price": MAX_INDEX_CONTRACT_PRICE,
        "friday_zero_hero_enabled": FRIDAY_ZERO_HERO_ENABLED,
        "zero_hero_min_price": ZERO_HERO_MIN_PRICE,
        "zero_hero_max_price": ZERO_HERO_MAX_PRICE,
        "massive_connected": bool(MASSIVE_API_KEY),
        "telegram_connected": bool(TOKEN and CHAT_ID)
    }
