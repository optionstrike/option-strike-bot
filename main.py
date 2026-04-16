from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse
import requests
import time
import json
import csv
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from zoneinfo import ZoneInfo

app = FastAPI()

# =========================
# الإعدادات الأساسية
# =========================
API_KEY = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2"
TELEGRAM_TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055"
SECRET_KEY = "12345"

REPORT_FILE = "trades_report.csv"

# =========================
# إعدادات القناص
# =========================
MIN_SCORE_TO_SEND = 70
MAX_SIGNALS_PER_DAY = 5

# 3 ساعات
DUPLICATE_WINDOW_SEC = 10800
CONFLICT_WINDOW_SEC = 10800

DEFAULT_CONTRACT_BUDGET = 3.0
ROUND_TO = 2

# فلترة العقود
MIN_OPTION_VOLUME = 50
MIN_OPTION_OI = 100
MAX_SPREAD_PCT = 25.0
MAX_STRIKE_DISTANCE_PCT = 3.0

# الجمعة: زيرو هيرو
ZERO_HERO_FRIDAY_ONLY = True
ZERO_HERO_MAX_ASK = 1.50
NON_FRIDAY_MIN_ASK = 1.00

# المتابعة
MONITOR_INTERVAL_SEC = 60
POST_TP3_STEP_USD = 0.30

# تعطيل فلتر وقت السوق
REQUIRE_MARKET_TIME = False

# =========================
# ذاكرة داخلية
# =========================
last_signal_message: Optional[str] = None
last_signals: Dict[str, Dict[str, Any]] = {}
direction_state: Dict[str, Dict[str, Any]] = {}

trades_store: Dict[str, Dict[str, Any]] = {}
active_trade_index: Dict[str, str] = {}

daily_tracker = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "sent_count": 0,
    "tickers": []
}

stats = {
    "sent": 0,
    "blocked_duplicate": 0,
    "blocked_conflict": 0,
    "blocked_weak": 0,
    "blocked_secret": 0,
    "blocked_daily_limit": 0,
    "blocked_daily_ticker": 0,
    "blocked_direction_lock": 0,
    "blocked_news": 0,
    "blocked_trend": 0,
    "blocked_explosion": 0,
    "blocked_pre_explosion": 0,
    "blocked_no_contract": 0,
    "blocked_budget": 0,
    "blocked_liquidity": 0,
    "blocked_spread": 0,
    "invalid_payload": 0,
    "updated": 0,
    "closed": 0,
    "tp1_alerts": 0,
    "tp2_alerts": 0,
    "tp3_alerts": 0,
    "post_tp3_updates": 0,
    "stop_alerts": 0,
}

# =========================
# أدوات مساعدة
# =========================
def roundx(value: float) -> float:
    return round(float(value), ROUND_TO)


def safe_float(value, default=0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_friday_ny() -> bool:
    ny = ZoneInfo("America/New_York")
    return datetime.now(ny).weekday() == 4


def generate_trade_id(ticker: str, direction: str) -> str:
    return f"{ticker.upper()}_{direction.lower()}_{datetime.now().strftime('%Y%m%d%H%M%S')}"


def reset_daily_tracker_if_needed():
    today = datetime.now().strftime("%Y-%m-%d")
    if daily_tracker["date"] != today:
        daily_tracker["date"] = today
        daily_tracker["sent_count"] = 0
        daily_tracker["tickers"] = []


def send_telegram(message: str) -> None:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Telegram config missing")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        res = requests.post(url, json=data, timeout=15)
        print("Telegram status:", res.status_code)
        print("Telegram response:", res.text)
    except Exception as e:
        print("Telegram send error:", str(e))


def send_telegram_reply(chat_id: str, message: str) -> None:
    if not TELEGRAM_TOKEN or not chat_id:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message
    }

    try:
        requests.post(url, json=data, timeout=15)
    except Exception as e:
        print("Telegram reply error:", str(e))


def format_strength_label(score: int) -> str:
    if score >= 90:
        return "قوية جدًا"
    if score >= 80:
        return "قوية"
    if score >= 65:
        return "جيدة"
    return "ضعيفة"


def nearest_friday() -> str:
    today = datetime.now().date()
    days_ahead = (4 - today.weekday()) % 7
    if days_ahead == 0:
        return today.strftime("%Y-%m-%d")
    return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")


def get_nested(d: Any, path: List[str], default=None):
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def extract_underlying_from_option_ticker(option_ticker: str) -> str:
    cleaned = str(option_ticker).strip()
    if cleaned.startswith("O:"):
        cleaned = cleaned[2:]
    i = 0
    while i < len(cleaned) and cleaned[i].isalpha():
        i += 1
    return cleaned[:i].upper() if i > 0 else ""


def normalize_option_ticker(option_ticker: str) -> str:
    val = str(option_ticker).strip()
    return val[2:] if val.startswith("O:") else val


def extract_quote_prices(raw_results: Dict[str, Any]) -> Dict[str, float]:
    bid = safe_float(
        get_nested(raw_results, ["last_quote", "bid"], 0.0)
        or get_nested(raw_results, ["quote", "bid"], 0.0)
    )
    ask = safe_float(
        get_nested(raw_results, ["last_quote", "ask"], 0.0)
        or get_nested(raw_results, ["quote", "ask"], 0.0)
    )
    volume = safe_float(
        get_nested(raw_results, ["day", "volume"], 0.0)
        or get_nested(raw_results, ["session", "volume"], 0.0)
    )
    oi = safe_float(
        raw_results.get("open_interest", 0.0)
        or get_nested(raw_results, ["details", "open_interest"], 0.0)
    )

    mid = roundx((bid + ask) / 2) if bid > 0 and ask > 0 else 0.0

    return {
        "bid": roundx(bid),
        "ask": roundx(ask),
        "mid": mid,
        "volume": volume,
        "oi": oi,
    }


def is_valid_market_time() -> bool:
    return True if not REQUIRE_MARKET_TIME else True


# =========================
# تقرير
# =========================
REPORT_HEADERS = [
    "id",
    "ticker",
    "direction",
    "direction_ar",
    "strike",
    "expiry",
    "contract",
    "pivot",
    "entry_price",
    "entry_high",
    "entry_low",
    "entry_display",
    "bid",
    "ask",
    "spread_pct",
    "highest_price",
    "current_price",
    "profit_pct",
    "tp1_hit",
    "tp2_hit",
    "tp3_hit",
    "stop_hit",
    "last_post_tp3_alert_price",
    "status",
    "created_at",
    "updated_at",
    "closed_at"
]


def ensure_report_file():
    if not os.path.exists(REPORT_FILE):
        with open(REPORT_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(REPORT_HEADERS)


def refresh_report_file():
    ensure_report_file()
    rows = list(trades_store.values())
    rows.sort(key=lambda x: x.get("created_at", ""))

    with open(REPORT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(REPORT_HEADERS)
        for data in rows:
            writer.writerow([
                data.get("id", ""),
                data.get("ticker", ""),
                data.get("direction", ""),
                data.get("direction_ar", ""),
                data.get("strike", ""),
                data.get("expiry", ""),
                data.get("contract", ""),
                f'{safe_float(data.get("pivot")):.2f}',
                f'{safe_float(data.get("entry_price")):.2f}',
                f'{safe_float(data.get("entry_high")):.2f}',
                f'{safe_float(data.get("entry_low")):.2f}',
                data.get("entry_display", ""),
                f'{safe_float(data.get("bid")):.2f}',
                f'{safe_float(data.get("ask")):.2f}',
                f'{safe_float(data.get("spread_pct")):.2f}',
                f'{safe_float(data.get("highest_price")):.2f}',
                f'{safe_float(data.get("current_price")):.2f}',
                f'{safe_float(data.get("profit_pct")):.2f}',
                data.get("tp1_hit", False),
                data.get("tp2_hit", False),
                data.get("tp3_hit", False),
                data.get("stop_hit", False),
                f'{safe_float(data.get("last_post_tp3_alert_price")):.2f}',
                data.get("status", ""),
                data.get("created_at", ""),
                data.get("updated_at", ""),
                data.get("closed_at", "")
            ])


def save_trade_record(data: dict):
    trades_store[data["id"]] = data
    refresh_report_file()


# =========================
# قفل الاتجاه
# =========================
def update_direction_lock(ticker: str, close_price: float, pivot: float):
    key = ticker.upper()

    if key not in direction_state:
        direction_state[key] = {
            "locked_direction": None,
            "above_count": 0,
            "below_count": 0,
            "last_pivot": pivot,
            "last_change": None
        }

    state = direction_state[key]
    state["last_pivot"] = pivot

    if close_price > pivot:
        state["above_count"] += 1
        state["below_count"] = 0
    elif close_price < pivot:
        state["below_count"] += 1
        state["above_count"] = 0

    if state["locked_direction"] == "call" and state["below_count"] >= 3:
        state["locked_direction"] = "put"
        state["last_change"] = now_str()
    elif state["locked_direction"] == "put" and state["above_count"] >= 3:
        state["locked_direction"] = "call"
        state["last_change"] = now_str()
    elif state["locked_direction"] is None:
        if state["above_count"] >= 3:
            state["locked_direction"] = "call"
            state["last_change"] = now_str()
        elif state["below_count"] >= 3:
            state["locked_direction"] = "put"
            state["last_change"] = now_str()

    return state


def get_locked_direction(ticker: str):
    state = direction_state.get(ticker.upper())
    if not state:
        return None
    return state.get("locked_direction")


def can_send_signal(ticker: str, requested_direction: str):
    locked = get_locked_direction(ticker)
    if locked is None:
        return True, "no_lock"
    if locked == requested_direction.lower():
        return True, "matched_lock"
    return False, f"locked_on_{locked}"


# =========================
# فلترة الإرسال
# =========================
def should_block_signal(ticker: str, signal: str, score: int):
    reset_daily_tracker_if_needed()
    now_ts = time.time()

    if score < MIN_SCORE_TO_SEND:
        stats["blocked_weak"] += 1
        return True, "weak blocked"

    if daily_tracker["sent_count"] >= MAX_SIGNALS_PER_DAY:
        stats["blocked_daily_limit"] += 1
        return True, "daily limit reached"

    if ticker.upper() in daily_tracker["tickers"]:
        stats["blocked_daily_ticker"] += 1
        return True, "ticker already sent today"

    if ticker in last_signals:
        prev = last_signals[ticker]

        if prev["signal"] == signal and (now_ts - prev["time"] < DUPLICATE_WINDOW_SEC):
            stats["blocked_duplicate"] += 1
            return True, "duplicate blocked"

        if prev["signal"] != signal and (now_ts - prev["time"] < CONFLICT_WINDOW_SEC):
            stats["blocked_conflict"] += 1
            return True, "conflict blocked"

    return False, "ok"


# =========================
# سكورات وفلاتر
# =========================
def has_news(ticker: str) -> bool:
    try:
        url = f"https://api.polygon.io/v2/reference/news?ticker={ticker}&apiKey={API_KEY}"
        res = requests.get(url, timeout=10)
        data = res.json()
        return len(data.get("results", [])) > 0
    except Exception:
        return False


def passes_trend_filter(data: Dict[str, Any]) -> (bool, str):
    signal = str(data.get("signal", "")).upper()
    ema_fast = safe_float(data.get("ema_fast"))
    ema_slow = safe_float(data.get("ema_slow"))

    if signal == "CALL" and ema_fast < ema_slow:
        return False, "trend blocked"
    if signal == "PUT" and ema_fast > ema_slow:
        return False, "trend blocked"

    return True, "ok"


def passes_explosion_filter(data: Dict[str, Any]) -> (bool, str):
    price = safe_float(data.get("price"))
    pivot = safe_float(data.get("pivot"))
    rsi = safe_float(data.get("rsi"), 50)
    rel_volume = safe_float(data.get("rel_volume"), 1.0)
    signal = str(data.get("signal", "")).upper()

    if pivot > 0 and price > 0:
        distance_pct = abs(price - pivot) / price
        if distance_pct < 0.003:
            return False, "explosion blocked - no movement"
        if distance_pct > 0.025:
            return False, "explosion blocked - too late"

    if signal == "CALL" and rsi < 55:
        return False, "explosion blocked - weak momentum"
    if signal == "PUT" and rsi > 45:
        return False, "explosion blocked - weak momentum"

    if rel_volume < 1.2:
        return False, "explosion blocked - low volume"

    return True, "ok"


def passes_pre_explosion_filter(data: Dict[str, Any]) -> (bool, str):
    price = safe_float(data.get("price"))
    pivot = safe_float(data.get("pivot"))
    rsi = safe_float(data.get("rsi"), 50)
    rel_volume = safe_float(data.get("rel_volume"), 1.0)
    ema_fast = safe_float(data.get("ema_fast"))
    ema_slow = safe_float(data.get("ema_slow"))
    signal = str(data.get("signal", "")).upper()
    confidence = safe_int(data.get("signal_confidence"), 0)

    if price <= 0 or pivot <= 0:
        return False, "pre-explosion invalid"

    if confidence < 70:
        return False, "pre-explosion weak confidence"

    distance_pct = abs(price - pivot) / price
    if distance_pct < 0.0015:
        return False, "pre-explosion too early"
    if distance_pct > 0.0060:
        return False, "pre-explosion too late"

    if rel_volume < 1.05:
        return False, "pre-explosion low volume"

    if signal == "CALL":
        if price <= pivot:
            return False, "pre-explosion call below pivot"
        if rsi < 52:
            return False, "pre-explosion weak call momentum"
        if ema_fast <= ema_slow:
            return False, "pre-explosion call against trend"

    if signal == "PUT":
        if price >= pivot:
            return False, "pre-explosion put above pivot"
        if rsi > 48:
            return False, "pre-explosion weak put momentum"
        if ema_fast >= ema_slow:
            return False, "pre-explosion put against trend"

    return True, "ok"


def score_signal(data: Dict[str, Any]) -> Dict[str, Any]:
    price = safe_float(data.get("price"))
    signal = str(data.get("signal", "")).upper()
    pivot = safe_float(data.get("pivot"))
    atr = safe_float(data.get("atr"))
    rsi = safe_float(data.get("rsi"), 50)
    rel_volume = safe_float(data.get("rel_volume"), 1.0)
    ema_fast = safe_float(data.get("ema_fast"))
    ema_slow = safe_float(data.get("ema_slow"))
    signal_confidence = safe_float(data.get("signal_confidence"), 0)

    reasons = []
    score = 50

    if pivot > 0 and price > 0:
        dist_pct = abs(price - pivot) / price
        if dist_pct >= 0.008:
            score += 12
            reasons.append("ابتعاد جيد عن الارتكاز")
        elif dist_pct >= 0.004:
            score += 7
            reasons.append("ابتعاد مقبول عن الارتكاز")
        else:
            score -= 8
            reasons.append("السعر قريب من الارتكاز")

    if signal == "CALL":
        if rsi >= 60:
            score += 10
            reasons.append("RSI داعم للصعود")
        elif rsi >= 53:
            score += 5
            reasons.append("RSI إيجابي")
        elif rsi < 48:
            score -= 10
            reasons.append("RSI غير داعم")
    elif signal == "PUT":
        if rsi <= 40:
            score += 10
            reasons.append("RSI داعم للهبوط")
        elif rsi <= 47:
            score += 5
            reasons.append("RSI سلبي")
        elif rsi > 52:
            score -= 10
            reasons.append("RSI غير داعم")

    if rel_volume >= 1.5:
        score += 10
        reasons.append("حجم تداول قوي")
    elif rel_volume >= 1.15:
        score += 5
        reasons.append("حجم تداول جيد")
    elif rel_volume < 0.9:
        score -= 6
        reasons.append("حجم تداول ضعيف")

    if ema_fast > 0 and ema_slow > 0:
        if signal == "CALL":
            if ema_fast > ema_slow:
                score += 8
                reasons.append("EMA داعم للكول")
            else:
                score -= 8
                reasons.append("EMA غير داعم للكول")
        elif signal == "PUT":
            if ema_fast < ema_slow:
                score += 8
                reasons.append("EMA داعم للبوت")
            else:
                score -= 8
                reasons.append("EMA غير داعم للبوت")

    if atr > 0:
        score += 4
        reasons.append("ATR متوفر")

    if signal_confidence > 0:
        extra = int((signal_confidence - 50) * 0.25)
        score += extra
        reasons.append("ثقة المؤشر مضافة")

    score = max(0, min(100, score))
    label = format_strength_label(score)

    return {
        "strength_score": score,
        "strength_label": label,
        "reasons": reasons
    }


# =========================
# مستويات السهم والعقد
# =========================
def infer_pivot(price: float, pivot: float, signal: str, atr: float) -> float:
    if pivot > 0:
        return roundx(pivot)

    offset = max(price * 0.003, atr * 0.25 if atr > 0 else price * 0.002)
    return roundx(price - offset) if signal == "CALL" else roundx(price + offset)


def compute_stock_levels(price: float, pivot: float, signal: str, atr: float):
    if atr <= 0:
        atr = max(price * 0.006, 0.5)

    if signal == "CALL":
        stock_stop = roundx(pivot)
        t1 = roundx(price + atr * 0.8)
        t2 = roundx(price + atr * 1.5)
        t3 = roundx(price + atr * 2.4)
    else:
        stock_stop = roundx(pivot)
        t1 = roundx(price - atr * 0.8)
        t2 = roundx(price - atr * 1.5)
        t3 = roundx(price - atr * 2.4)

    return {
        "stock_stop": stock_stop,
        "stock_target1": t1,
        "stock_target2": t2,
        "stock_target3": t3
    }


def compute_option_targets(entry_price: float, strength_score: int):
    if strength_score >= 80:
        tp1_mult, tp2_mult, tp3_mult = 1.25, 1.55, 1.95
        stop_mult = 0.75
    else:
        tp1_mult, tp2_mult, tp3_mult = 1.15, 1.35, 1.60
        stop_mult = 0.80

    return {
        "contract_entry": roundx(entry_price),
        "contract_stop": roundx(entry_price * stop_mult),
        "contract_target1": roundx(entry_price * tp1_mult),
        "contract_target2": roundx(entry_price * tp2_mult),
        "contract_target3": roundx(entry_price * tp3_mult),
    }


# =========================
# الرسائل
# =========================
def build_alert_message(payload: Dict[str, Any]) -> str:
    ticker = payload["ticker"]
    signal = payload["signal"]
    interval = payload["interval"]
    price = payload["price"]
    strength_label = payload["strength_label"]
    strength_score = payload["strength_score"]
    pivot = payload["pivot"]

    strike = payload["strike"]
    expiry = payload.get("expiry", "-")
    contract = payload.get("contract", "-")
    bid = safe_float(payload.get("bid"))
    ask = safe_float(payload.get("ask"))
    spread_pct = safe_float(payload.get("spread_pct"))

    stock_t1 = payload["stock_target1"]
    stock_t2 = payload["stock_target2"]
    stock_t3 = payload["stock_target3"]

    contract_entry = payload["contract_entry"]
    contract_stop = payload["contract_stop"]
    contract_t1 = payload["contract_target1"]
    contract_t2 = payload["contract_target2"]
    contract_t3 = payload["contract_target3"]

    reasons = "، ".join(payload["reasons"][:3]) if payload["reasons"] else "مطابقة الشروط"
    direction = "🟢 CALL" if signal == "CALL" else "🔴 PUT"
    mode_tag = "💣 ZERO HERO" if payload.get("zero_hero", False) else "🎯 SNIPER"

    if signal == "CALL":
        stop_text = f"كسر {pivot:.2f} بإغلاق ساعة"
    else:
        stop_text = f"اختراق {pivot:.2f} بإغلاق ساعة"

    return f"""🚨 {mode_tag} Option Strike Alert

📈 السهم: {ticker}
{direction}
⏰ الفريم: {interval}
💰 سعر السهم: {price:.2f}
🎯 الارتكاز: {pivot:.2f}

📊 قوة الإشارة: {strength_label} ({strength_score}/100)
🧠 السبب: {reasons}

📄 العقد: {contract}
📅 الانتهاء: {expiry}
🎯 السترايك: {strike:.2f}

💵 سعر الدخول الحقيقي (Ask): {contract_entry:.2f}
🟢 Bid: {bid:.2f}
🔴 Ask: {ask:.2f}
↔️ السبريد: {spread_pct:.2f}%

📈 أهداف السهم:
🥇 {stock_t1:.2f}
🥈 {stock_t2:.2f}
🥉 {stock_t3:.2f}

📈 أهداف العقد:
🥇 {contract_t1:.2f}
🥈 {contract_t2:.2f}
🥉 {contract_t3:.2f}

🛑 وقف السهم:
{stop_text}

🛑 وقف العقد:
{contract_stop:.2f}
"""


def build_progress_update_message(trade: Dict[str, Any], title: str) -> str:
    return f"""{title} | {trade['ticker']} ${trade['strike']} {trade['direction_ar']}

📄 العقد: {trade.get('contract', '-')}
📊 سعر الدخول: {safe_float(trade.get('entry_price')):.2f}
💰 السعر الحالي: {safe_float(trade.get('current_price')):.2f}
🏆 الأعلى المحقق: {safe_float(trade.get('highest_price')):.2f}
📈 نسبة الربح: {safe_float(trade.get('profit_pct')):+.2f}%

⚠️ تنبيه: هذا الطرح تعليمي
والقرار النهائي يعود للمتداول.

📢 @Option_Strike01"""


async def parse_request_payload(request: Request) -> Dict[str, Any]:
    try:
        return await request.json()
    except Exception:
        pass

    try:
        raw = await request.body()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


# =========================
# Yahoo
# =========================
def get_yahoo_stock_price(ticker: str):
    price_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.upper()}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        price_res = requests.get(price_url, headers=headers, timeout=20)
    except Exception as e:
        print("Yahoo price request error:", str(e))
        return None

    if price_res.status_code != 200:
        return None

    try:
        price_data = price_res.json()
    except Exception:
        return None

    chart = price_data.get("chart", {})
    result = chart.get("result", [])
    if not result:
        return None

    meta = result[0].get("meta", {})
    current_price = meta.get("regularMarketPrice", 0)

    if not current_price:
        return None

    return float(current_price)


# =========================
# Polygon
# =========================
def get_options_chain(ticker: str, direction: str = None, limit: int = 250):
    url = "https://api.polygon.io/v3/reference/options/contracts"
    params = {
        "underlying_ticker": ticker.upper(),
        "limit": limit,
        "apiKey": API_KEY,
        "expired": "false"
    }

    if direction:
        params["contract_type"] = direction.lower()

    try:
        res = requests.get(url, params=params, timeout=15)
        data = res.json()
        return data.get("results", [])
    except Exception as e:
        print("Options chain error:", str(e))
        return []


def get_option_snapshot(option_ticker: str):
    try:
        clean_contract = normalize_option_ticker(option_ticker)
        underlying = extract_underlying_from_option_ticker(option_ticker)

        if not clean_contract or not underlying:
            return {"bid": 0.0, "ask": 0.0, "mid": 0.0, "volume": 0.0, "oi": 0.0}

        url = f"https://api.polygon.io/v3/snapshot/options/{underlying}/{clean_contract}"
        res = requests.get(url, params={"apiKey": API_KEY}, timeout=15)
        raw = res.json()
        results = raw.get("results", {}) if isinstance(raw, dict) else {}
        return extract_quote_prices(results)

    except Exception as e:
        print("Option snapshot error:", option_ticker, str(e))
        return {"bid": 0.0, "ask": 0.0, "mid": 0.0, "volume": 0.0, "oi": 0.0}


def pick_best_contract(ticker: str, direction: str, price: float, max_ask: float = 3.0):
    contracts = get_options_chain(ticker, direction=direction, limit=250)
    candidates = []

    friday_mode = ZERO_HERO_FRIDAY_ONLY and is_friday_ny()

    for c in contracts:
        strike = safe_float(c.get("strike_price"))
        expiry = str(c.get("expiration_date", ""))
        option_ticker = str(c.get("ticker", "")).strip()

        if not strike or not expiry or not option_ticker:
            continue

        distance_pct = abs(strike - price) / max(price, 1) * 100
        if distance_pct > MAX_STRIKE_DISTANCE_PCT:
            continue

        snap = get_option_snapshot(option_ticker)

        bid = snap["bid"]
        ask = snap["ask"]
        volume = snap["volume"]
        oi = snap["oi"]

        if bid <= 0 or ask <= 0:
            continue

        if friday_mode:
            if ask > ZERO_HERO_MAX_ASK:
                stats["blocked_budget"] += 1
                continue
        else:
            if ask > max_ask:
                stats["blocked_budget"] += 1
                continue
            if ask < NON_FRIDAY_MIN_ASK:
                continue

        if volume < MIN_OPTION_VOLUME or oi < MIN_OPTION_OI:
            stats["blocked_liquidity"] += 1
            continue

        spread = ask - bid
        spread_pct = (spread / ask) * 100 if ask > 0 else 999

        if spread_pct > MAX_SPREAD_PCT:
            stats["blocked_spread"] += 1
            continue

        score = (volume * 2.5) + (oi * 1.5) - (spread_pct * 20)

        candidates.append({
            "contract": option_ticker,
            "strike": roundx(strike),
            "expiry": expiry,
            "bid": roundx(bid),
            "ask": roundx(ask),
            "mid": roundx(snap["mid"]),
            "volume": volume,
            "oi": oi,
            "spread_pct": roundx(spread_pct),
            "score": score,
            "zero_hero": friday_mode and ask <= ZERO_HERO_MAX_ASK
        })

    if not candidates:
        return None

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[0]


# =========================
# Routes
# =========================
@app.get("/")
def home():
    return {"status": "Option Strike Bot running"}


@app.get("/status")
def status():
    reset_daily_tracker_if_needed()
    return {
        "status": "running",
        "stats": stats,
        "tracked_symbols": len(last_signals),
        "daily_tracker": daily_tracker,
        "direction_state": direction_state,
        "stored_trades": len(trades_store)
    }


@app.get("/last")
def last():
    return {"last_signal": last_signal_message}


@app.get("/report")
def report_view():
    ensure_report_file()
    if not os.path.exists(REPORT_FILE):
        return PlainTextResponse("لا يوجد تقرير حتى الآن.")

    with open(REPORT_FILE, "r", encoding="utf-8-sig") as f:
        content = f.read()

    return PlainTextResponse(content)


@app.get("/report/json")
def report_json():
    return trades_store


@app.get("/report/view")
def report_view_html():
    rows = list(trades_store.values())
    rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    html = """
    <html>
    <head>
        <meta charset="utf-8">
        <title>Trades Report</title>
        <style>
            body { font-family: Arial, sans-serif; padding: 20px; direction: rtl; }
            table { border-collapse: collapse; width: 100%; font-size: 13px; }
            th, td { border: 1px solid #ccc; padding: 8px; text-align: center; }
            th { background: #f5f5f5; }
        </style>
    </head>
    <body>
        <h2>تقرير الصفقات</h2>
        <table>
            <tr>
                <th>ID</th>
                <th>السهم</th>
                <th>الاتجاه</th>
                <th>السترايك</th>
                <th>التاريخ</th>
                <th>العقد</th>
                <th>الدخول</th>
                <th>Bid</th>
                <th>Ask</th>
                <th>Spread%</th>
                <th>الأعلى</th>
                <th>الحالي</th>
                <th>الربح %</th>
                <th>TP1</th>
                <th>TP2</th>
                <th>TP3</th>
                <th>Stop</th>
                <th>الحالة</th>
                <th>وقت الإنشاء</th>
                <th>آخر تحديث</th>
                <th>الإغلاق</th>
            </tr>
    """

    for r in rows:
        html += f"""
            <tr>
                <td>{r.get('id','')}</td>
                <td>{r.get('ticker','')}</td>
                <td>{r.get('direction_ar','')}</td>
                <td>{r.get('strike','')}</td>
                <td>{r.get('expiry','')}</td>
                <td>{r.get('contract','')}</td>
                <td>{safe_float(r.get('entry_price')):.2f}</td>
                <td>{safe_float(r.get('bid')):.2f}</td>
                <td>{safe_float(r.get('ask')):.2f}</td>
                <td>{safe_float(r.get('spread_pct')):.2f}</td>
                <td>{safe_float(r.get('highest_price')):.2f}</td>
                <td>{safe_float(r.get('current_price')):.2f}</td>
                <td>{safe_float(r.get('profit_pct')):.2f}</td>
                <td>{r.get('tp1_hit', False)}</td>
                <td>{r.get('tp2_hit', False)}</td>
                <td>{r.get('tp3_hit', False)}</td>
                <td>{r.get('stop_hit', False)}</td>
                <td>{r.get('status','')}</td>
                <td>{r.get('created_at','')}</td>
                <td>{r.get('updated_at','')}</td>
                <td>{r.get('closed_at','')}</td>
            </tr>
        """

    html += """
        </table>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.get("/lock/{ticker}/{pivot}/{close_price}")
def lock_direction(ticker: str, pivot: float, close_price: float):
    state = update_direction_lock(ticker, close_price, pivot)
    return state


@app.get("/smart/{ticker}/{direction}")
def smart_contract(ticker: str, direction: str):
    current_price = get_yahoo_stock_price(ticker) or 100.0
    best = pick_best_contract(ticker.upper(), direction.upper(), current_price, DEFAULT_CONTRACT_BUDGET)

    if not best:
        return {
            "ticker": ticker.upper(),
            "type": direction.lower(),
            "strike": roundx(current_price),
            "expiry": nearest_friday(),
            "contract": f"FALLBACK_{ticker.upper()}_{direction.upper()}",
            "current_price": current_price,
            "option_price": None,
            "bid": None,
            "ask": None,
            "fallback": True
        }

    return {
        "ticker": ticker.upper(),
        "type": direction.lower(),
        "strike": best["strike"],
        "expiry": best["expiry"],
        "contract": best["contract"],
        "current_price": current_price,
        "option_price": best["ask"],
        "bid": best["bid"],
        "ask": best["ask"],
        "spread_pct": best["spread_pct"],
        "fallback": False,
        "zero_hero": best.get("zero_hero", False)
    }


# =========================
# Webhook
# =========================
@app.post("/webhook")
async def webhook(request: Request):
    global last_signal_message

    try:
        data = await parse_request_payload(request)
        print("RAW DATA:", data)

        if not isinstance(data, dict) or not data:
            stats["invalid_payload"] += 1
            return JSONResponse({"error": "Invalid payload"}, status_code=400)

        if str(data.get("secret", "")).strip() != SECRET_KEY:
            stats["blocked_secret"] += 1
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        if not is_valid_market_time():
            return {"status": "blocked by market time"}

        ticker = str(data.get("ticker", "")).upper().strip()
        signal = str(data.get("signal", "")).upper().strip()
        interval = str(data.get("interval", "1H")).strip()
        price = safe_float(data.get("price"))

        if not ticker or signal not in ["CALL", "PUT"] or price <= 0:
            stats["invalid_payload"] += 1
            return JSONResponse({"error": "Invalid payload"}, status_code=400)

        if has_news(ticker):
            stats["blocked_news"] += 1
            return {"status": "blocked - news"}

        trend_ok, trend_reason = passes_trend_filter(data)
        if not trend_ok:
            stats["blocked_trend"] += 1
            return {"status": trend_reason}

        exp_ok, exp_reason = passes_explosion_filter(data)
        if not exp_ok:
            stats["blocked_explosion"] += 1
            return {"status": exp_reason}

        pre_ok, pre_reason = passes_pre_explosion_filter(data)
        if not pre_ok:
            stats["blocked_pre_explosion"] += 1
            return {"status": pre_reason}

        score_data = score_signal(data)
        strength_score = score_data["strength_score"]
        strength_label = score_data["strength_label"]
        reasons = score_data["reasons"]

        blocked, reason = should_block_signal(ticker, signal, strength_score)
        if blocked:
            return {"status": reason}

        atr = safe_float(data.get("atr"))
        pivot = infer_pivot(price, safe_float(data.get("pivot")), signal, atr)

        update_direction_lock(ticker, price, pivot)

        allowed, lock_reason = can_send_signal(ticker, signal.lower())
        if not allowed:
            stats["blocked_direction_lock"] += 1
            return {"status": f"direction locked on {get_locked_direction(ticker)}"}

        stock_levels = compute_stock_levels(price, pivot, signal, atr)
        budget = safe_float(data.get("budget"), DEFAULT_CONTRACT_BUDGET)
        best = pick_best_contract(ticker, signal, price, max_ask=budget)

        if not best:
            stats["blocked_no_contract"] += 1
            return {"status": "no valid contract found"}

        strike = best["strike"]
        contract = best["contract"]
        expiry = best["expiry"]
        bid = best["bid"]
        ask = best["ask"]
        spread_pct = best["spread_pct"]
        zero_hero = best.get("zero_hero", False)

        option_levels = compute_option_targets(ask, strength_score)

        payload = {
            "ticker": ticker,
            "signal": signal,
            "interval": interval,
            "price": roundx(price),
            "pivot": pivot,
            "strength_score": strength_score,
            "strength_label": strength_label,
            "reasons": reasons,
            "strike": strike,
            "expiry": expiry,
            "contract": contract,
            "bid": bid,
            "ask": ask,
            "spread_pct": spread_pct,
            "zero_hero": zero_hero,
            **stock_levels,
            **option_levels
        }

        message = build_alert_message(payload)
        last_signal_message = message
        send_telegram(message)

        stats["sent"] += 1
        last_signals[ticker] = {
            "signal": signal,
            "time": time.time(),
            "score": strength_score,
            "price": price
        }

        daily_tracker["sent_count"] += 1
        daily_tracker["tickers"].append(ticker.upper())

        if get_locked_direction(ticker) is None:
            direction_state[ticker] = {
                "locked_direction": signal.lower(),
                "above_count": 1 if signal == "CALL" else 0,
                "below_count": 1 if signal == "PUT" else 0,
                "last_pivot": pivot,
                "last_change": now_str()
            }

        trade_id = generate_trade_id(ticker, signal)
        trade_key = f"{ticker.upper()}_{signal.lower()}"
        direction_ar = "كول" if signal == "CALL" else "بوت"
        entry_display = f"{ask:.2f}-{bid:.2f}"

        trade_data = {
            "id": trade_id,
            "ticker": ticker.upper(),
            "direction": signal.lower(),
            "direction_ar": direction_ar,
            "strike": strike,
            "expiry": expiry,
            "contract": contract,
            "pivot": pivot,
            "entry_price": ask,
            "entry_high": ask,
            "entry_low": bid,
            "entry_display": entry_display,
            "bid": bid,
            "ask": ask,
            "spread_pct": spread_pct,
            "highest_price": ask,
            "current_price": ask,
            "profit_pct": 0.0,
            "strength_score": strength_score,
            "status": "OPEN",
            "tp1_hit": False,
            "tp2_hit": False,
            "tp3_hit": False,
            "stop_hit": False,
            "last_post_tp3_alert_price": 0.0,
            "created_at": now_str(),
            "updated_at": now_str(),
            "closed_at": ""
        }

        save_trade_record(trade_data)
        active_trade_index[trade_key] = trade_id

        return {
            "status": "sent",
            "strength_score": strength_score,
            "strength_label": strength_label,
            "strike": strike,
            "contract": contract,
            "expiry": expiry,
            "pivot": pivot,
            "zero_hero": zero_hero
        }

    except Exception as e:
        print("WEBHOOK ERROR:", str(e))
        return JSONResponse({"error": str(e)}, status_code=500)


# =========================
# Telegram webhook
# =========================
@app.post("/telegram")
async def telegram_webhook(request: Request):
    global last_signal_message

    try:
        update = await parse_request_payload(request)
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = str(message.get("text", "")).strip()

        if not chat_id or not text:
            return {"ok": True}

        if text == "/start":
            send_telegram_reply(chat_id, "🔥 أهلاً بك في Option Strike Bot\n\n/help\n/status\n/last")
        elif text == "/help":
            send_telegram_reply(
                chat_id,
                "🧠 البوت يستقبل إشارات TradingView ويرسل:\n"
                "- فلترة 70%+\n"
                "- 5 فرص يوميًا\n"
                "- منع التكرار 3 ساعات\n"
                "- قفل اتجاه\n"
                "- اختيار عقد تلقائي\n"
                "- متابعة TP1 / TP2 / TP3\n"
                "- زيرو هيرو يوم الجمعة"
            )
        elif text == "/status":
            send_telegram_reply(
                chat_id,
                f"✅ البوت شغال\n"
                f"الإشارات المرسلة: {stats['sent']}\n"
                f"TP1: {stats['tp1_alerts']}\n"
                f"TP2: {stats['tp2_alerts']}\n"
                f"TP3: {stats['tp3_alerts']}\n"
                f"Post TP3 Updates: {stats['post_tp3_updates']}\n"
                f"Stops: {stats['stop_alerts']}\n"
                f"المرسل اليوم: {daily_tracker['sent_count']}/{MAX_SIGNALS_PER_DAY}"
            )
        elif text == "/last":
            send_telegram_reply(chat_id, last_signal_message or "لا توجد إشارة سابقة حتى الآن.")
        else:
            send_telegram_reply(chat_id, "الأمر غير معروف. استخدم /help")

    except Exception as e:
        print("Telegram webhook error:", str(e))

    return {"ok": True}


# =========================
# متابعة تلقائية
# =========================
def monitor_open_trades():
    updated_count = 0

    for trade_id, trade in list(trades_store.items()):
        if trade.get("status") not in ["OPEN", "RUNNING"]:
            continue

        contract = trade.get("contract", "")
        if not contract:
            continue

        snap = get_option_snapshot(contract)
        bid = snap["bid"]
        ask = snap["ask"]
        mid = snap["mid"]

        if bid <= 0 and ask <= 0 and mid <= 0:
            continue

        current_price = ask if ask > 0 else (mid if mid > 0 else bid)
        entry_price = safe_float(trade.get("entry_price"), 0.0)

        if current_price <= 0 or entry_price <= 0:
            continue

        highest_price = max(safe_float(trade.get("highest_price"), entry_price), current_price)
        profit_pct = round(((current_price - entry_price) / entry_price) * 100, 2)

        spread_pct = 0.0
        if ask > 0 and bid > 0:
            spread_pct = roundx(((ask - bid) / ask) * 100)

        trade["bid"] = roundx(bid)
        trade["ask"] = roundx(ask)
        trade["current_price"] = roundx(current_price)
        trade["highest_price"] = roundx(highest_price)
        trade["profit_pct"] = profit_pct
        trade["spread_pct"] = spread_pct
        trade["updated_at"] = now_str()

        trades_store[trade_id] = trade
        updated_count += 1

    if updated_count > 0:
        refresh_report_file()

    return updated_count


def auto_manage_trade_levels():
    changed = False

    for trade_id, trade in list(trades_store.items()):
        if trade.get("status") not in ["OPEN", "RUNNING"]:
            continue

        current_price = safe_float(trade.get("current_price"))
        entry_price = safe_float(trade.get("entry_price"))
        strength_score = safe_int(trade.get("strength_score"), 80)

        if current_price <= 0 or entry_price <= 0:
            continue

        levels = compute_option_targets(entry_price, strength_score)
        tp1 = levels["contract_target1"]
        tp2 = levels["contract_target2"]
        tp3 = levels["contract_target3"]
        stop = levels["contract_stop"]

        if not trade.get("stop_hit") and current_price <= stop:
            trade["stop_hit"] = True
            trade["status"] = "STOPPED"
            trade["closed_at"] = now_str()
            trades_store[trade_id] = trade
            stats["stop_alerts"] += 1
            stats["closed"] += 1
            send_telegram(build_progress_update_message(trade, "🛑 ضرب الوقف"))
            changed = True
            continue

        if not trade.get("tp1_hit") and current_price >= tp1:
            trade["tp1_hit"] = True
            stats["tp1_alerts"] += 1
            send_telegram(build_progress_update_message(trade, "🎯 الهدف الأول تحقق"))
            changed = True

        if not trade.get("tp2_hit") and current_price >= tp2:
            trade["tp2_hit"] = True
            stats["tp2_alerts"] += 1
            send_telegram(build_progress_update_message(trade, "🚀 الهدف الثاني تحقق"))
            changed = True

        if not trade.get("tp3_hit") and current_price >= tp3:
            trade["tp3_hit"] = True
            trade["status"] = "RUNNING"
            trade["last_post_tp3_alert_price"] = roundx(current_price)
            stats["tp3_alerts"] += 1
            send_telegram(build_progress_update_message(trade, "🏆 الهدف الثالث تحقق"))
            changed = True

        if trade.get("tp3_hit"):
            last_tp3_alert_price = safe_float(trade.get("last_post_tp3_alert_price"), 0.0)
            if last_tp3_alert_price <= 0:
                trade["last_post_tp3_alert_price"] = roundx(current_price)
                changed = True
            elif current_price >= roundx(last_tp3_alert_price + POST_TP3_STEP_USD):
                trade["last_post_tp3_alert_price"] = roundx(current_price)
                stats["post_tp3_updates"] += 1
                send_telegram(build_progress_update_message(trade, "🔔 تحديث بعد الهدف الثالث"))
                changed = True

        trades_store[trade_id] = trade

    if changed:
        refresh_report_file()


def monitor_loop():
    while True:
        try:
            monitor_open_trades()
            auto_manage_trade_levels()
        except Exception as e:
            print("Monitor loop error:", str(e))
        time.sleep(MONITOR_INTERVAL_SEC)


@app.on_event("startup")
def startup_event():
    ensure_report_file()
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    print("Startup complete. Monitor thread started.")


@app.get("/monitor")
def run_monitor():
    updated = monitor_open_trades()
    auto_manage_trade_levels()
    return {"status": "ok", "updated_trades": updated}


@app.get("/update/{ticker}/{direction}/{entry}/{current}")
def update_signal(
    ticker: str,
    direction: str,
    entry: float,
    current: float,
    status: str = "OPEN"
):
    trade_key = f"{ticker.upper()}_{direction.lower()}"
    trade_id = active_trade_index.get(trade_key)

    if not trade_id or trade_id not in trades_store:
        return PlainTextResponse("لا يوجد طرح محفوظ لهذا السهم/الاتجاه.")

    saved = trades_store[trade_id]
    strike = saved["strike"]
    direction_ar = saved["direction_ar"]

    highest_price = max(safe_float(saved.get("highest_price"), entry), float(current))
    current_price = float(current)
    profit_pct = round(((current_price - entry) / entry) * 100, 2)

    saved["highest_price"] = round(highest_price, 2)
    saved["current_price"] = round(current_price, 2)
    saved["profit_pct"] = profit_pct
    saved["status"] = status.upper()
    saved["updated_at"] = now_str()

    if status.upper() in ["STOPPED", "CANCELLED", "LOSS"]:
        saved["closed_at"] = now_str()
        stats["closed"] += 1
    else:
        stats["updated"] += 1

    trades_store[trade_id] = saved
    refresh_report_file()

    text = f"""🔔 تحديث | {ticker.upper()} ${strike} {direction_ar}

📄 العقد: {saved.get("contract", "-")}
📊 سعر الدخول: {entry:.2f}
💰 السعر الحالي: {current_price:.2f}
🏆 الأعلى المحقق: {saved['highest_price']:.2f}
📈 نسبة الربح: {profit_pct:+.2f}%
📌 الحالة: {saved["status"]}

⚠️ تنبيه: هذا الطرح تعليمي
والقرار النهائي يعود للمتداول.

📢 @Option_Strike01"""

    send_telegram(text)
    return PlainTextResponse(text)
