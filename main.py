from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
import requests
import os
import time
import json
import csv
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

app = FastAPI()

# =========================
# الإعدادات الأساسية
# =========================
API_KEY = "zgdoQcwoOW5HNLXhuMC6jN1rjIpQQuzU"
TELEGRAM_TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055"
SECRET_KEY = os.getenv("SECRET_KEY", "12345").strip()

REPORT_FILE = "trades_report.csv"

# فلترة تلقائية
MAX_SIGNALS_PER_DAY = 5
MIN_SCORE_TO_SEND = 80

# منع التكرار السريع
DUPLICATE_WINDOW_SEC = int(os.getenv("DUPLICATE_WINDOW_SEC", "300"))
CONFLICT_WINDOW_SEC = int(os.getenv("CONFLICT_WINDOW_SEC", "300"))
DEFAULT_CONTRACT_BUDGET = float(os.getenv("DEFAULT_CONTRACT_BUDGET", "3.0"))
ROUND_TO = int(os.getenv("ROUND_TO", "2"))

# =========================
# ذاكرة داخلية
# =========================
last_signals: Dict[str, Dict[str, Any]] = {}
last_signal_message: Optional[str] = None
last_drafts: Dict[str, Dict[str, Any]] = {}

# قفل الاتجاه لكل سهم
direction_state: Dict[str, Dict[str, Any]] = {}

# تتبع يومي للإشارات التلقائية فقط
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
    "invalid_payload": 0,
}


# =========================
# أدوات مساعدة
# =========================
def roundx(value: float) -> float:
    return round(value, ROUND_TO)


def safe_float(value, default=0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def reset_daily_tracker_if_needed():
    today = datetime.now().strftime("%Y-%m-%d")
    if daily_tracker["date"] != today:
        daily_tracker["date"] = today
        daily_tracker["sent_count"] = 0
        daily_tracker["tickers"] = []


def send_telegram(message: str) -> None:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, json=data, timeout=10)
    except Exception:
        pass


def send_telegram_reply(chat_id: str, message: str) -> None:
    if not TELEGRAM_TOKEN or not chat_id:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message
    }
    try:
        requests.post(url, json=data, timeout=10)
    except Exception:
        pass


def send_telegram_text(text: str):
    send_telegram(text)


def format_strength_label(score: int) -> str:
    if score >= 90:
        return "قوية جدًا"
    if score >= 80:
        return "قوية"
    if score >= 65:
        return "جيدة"
    return "ضعيفة"


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


def choose_strike(price: float, signal: str, strength_score: int, budget: float):
    if price < 25:
        step = 0.5
    elif price < 100:
        step = 1
    elif price < 250:
        step = 2.5
    elif price < 500:
        step = 5
    else:
        step = 10

    if signal == "CALL":
        raw_strike = price * 1.01 if strength_score >= 80 else price
    else:
        raw_strike = price * 0.99 if strength_score >= 80 else price

    strike = round(raw_strike / step) * step
    distance_pct = abs(strike - price) / max(price, 1)
    estimated_premium = max(0.8, budget - (distance_pct * 20))
    estimated_premium = roundx(min(max(estimated_premium, 0.8), budget))

    return {
        "strike": roundx(strike),
        "step": step,
        "estimated_premium": estimated_premium
    }


def compute_option_targets(estimated_premium: float, strength_score: int):
    if strength_score >= 80:
        stop_mult = 0.75
        tp1_mult, tp2_mult, tp3_mult = 1.25, 1.55, 1.95
    else:
        stop_mult = 0.80
        tp1_mult, tp2_mult, tp3_mult = 1.15, 1.35, 1.60

    return {
        "contract_entry": roundx(estimated_premium),
        "contract_stop": roundx(estimated_premium * stop_mult),
        "contract_target1": roundx(estimated_premium * tp1_mult),
        "contract_target2": roundx(estimated_premium * tp2_mult),
        "contract_target3": roundx(estimated_premium * tp3_mult),
    }


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
        reasons.append("ATR متوفر للحساب")

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
        state["last_change"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elif state["locked_direction"] == "put" and state["above_count"] >= 3:
        state["locked_direction"] = "call"
        state["last_change"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elif state["locked_direction"] is None:
        if state["above_count"] >= 3:
            state["locked_direction"] = "call"
            state["last_change"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elif state["below_count"] >= 3:
            state["locked_direction"] = "put"
            state["last_change"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return state


def get_locked_direction(ticker: str):
    key = ticker.upper()
    if key not in direction_state:
        return None
    return direction_state[key].get("locked_direction")


def can_send_signal(ticker: str, requested_direction: str):
    locked = get_locked_direction(ticker)
    if locked is None:
        return True, "no_lock"

    if locked == requested_direction.lower():
        return True, "matched_lock"

    return False, f"locked_on_{locked}"


# =========================
# فلترة يومية / منع الإزعاج
# =========================
def should_block_signal(ticker: str, signal: str, score: int):
    reset_daily_tracker_if_needed()
    now = time.time()

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

        if prev["signal"] == signal and (now - prev["time"] < DUPLICATE_WINDOW_SEC):
            stats["blocked_duplicate"] += 1
            return True, "duplicate blocked"

        if prev["signal"] != signal and (now - prev["time"] < CONFLICT_WINDOW_SEC):
            stats["blocked_conflict"] += 1
            return True, "conflict blocked"

    return False, "ok"


# =========================
# التقرير
# =========================
def ensure_report_file():
    if not os.path.exists(REPORT_FILE):
        with open(REPORT_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "id",
                "ticker",
                "direction",
                "direction_ar",
                "strike",
                "expiry",
                "contract",
                "pivot",
                "entry_high",
                "entry_low",
                "entry_display",
                "highest_price",
                "current_price",
                "profit_pct",
                "status",
                "created_at",
                "updated_at",
                "closed_at"
            ])


def refresh_report_file():
    ensure_report_file()

    with open(REPORT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id",
            "ticker",
            "direction",
            "direction_ar",
            "strike",
            "expiry",
            "contract",
            "pivot",
            "entry_high",
            "entry_low",
            "entry_display",
            "highest_price",
            "current_price",
            "profit_pct",
            "status",
            "created_at",
            "updated_at",
            "closed_at"
        ])

        for _, data in last_drafts.items():
            writer.writerow([
                data["id"],
                data["ticker"],
                data["direction"],
                data["direction_ar"],
                data["strike"],
                data["expiry"],
                data["contract"],
                f'{data["pivot"]:.2f}',
                f'{data["entry_high"]:.2f}',
                f'{data["entry_low"]:.2f}',
                data["entry_display"],
                f'{data["highest_price"]:.2f}',
                f'{data["current_price"]:.2f}',
                f'{data["profit_pct"]:.2f}',
                data["status"],
                data["created_at"],
                data["updated_at"],
                data["closed_at"]
            ])


# =========================
# الرسالة
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

    if signal == "CALL":
        stop_text = f"كسر {pivot} بإغلاق ساعة"
    else:
        stop_text = f"اختراق {pivot} بإغلاق ساعة"

    return f"""🚨 Option Strike Alert

📈 السهم: {ticker}
{direction}
⏰ الفريم: {interval}
💰 سعر السهم: {price}
🎯 الارتكاز: {pivot}

📊 قوة الإشارة: {strength_label} ({strength_score}/100)
🧠 السبب: {reasons}

🎯 السترايك المقترح: {strike}
💵 سعر العقد التقديري: {contract_entry}

📈 أهداف السهم:
🥇 {stock_t1}
🥈 {stock_t2}
🥉 {stock_t3}

🛑 وقف السهم:
{stop_text}

📈 أهداف العقد:
🥇 {contract_t1}
🥈 {contract_t2}
🥉 {contract_t3}

🛑 وقف العقد:
{contract_stop}
"""


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
# الصفحة الرئيسية
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
        "direction_state": direction_state
    }


@app.get("/last")
def last():
    return {"last_signal": last_signal_message}


@app.get("/test")
def test():
    send_telegram("🔥 البوت شغال بنجاح!")
    return {"status": "ok"}


# =========================
# اختبار قفل الاتجاه يدويًا
# =========================
@app.get("/lock/{ticker}/{pivot}/{close_price}")
def lock_direction(ticker: str, pivot: float, close_price: float):
    state = update_direction_lock(ticker, close_price, pivot)
    return state


# =========================
# Webhook TradingView
# =========================
@app.post("/webhook")
async def webhook(request: Request):
    global last_signal_message

    data = await parse_request_payload(request)

    if not isinstance(data, dict) or not data:
        stats["invalid_payload"] += 1
        return JSONResponse({"error": "Invalid payload"}, status_code=400)

    if str(data.get("secret", "")).strip() != SECRET_KEY:
        stats["blocked_secret"] += 1
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    ticker = str(data.get("ticker", "")).upper().strip()
    signal = str(data.get("signal", "")).upper().strip()
    interval = str(data.get("interval", "1H")).strip()
    price = safe_float(data.get("price"))

    if not ticker or signal not in ["CALL", "PUT"] or price <= 0:
        stats["invalid_payload"] += 1
        return JSONResponse({"error": "Invalid payload"}, status_code=400)

    score_data = score_signal(data)
    strength_score = score_data["strength_score"]
    strength_label = score_data["strength_label"]
    reasons = score_data["reasons"]

    blocked, reason = should_block_signal(ticker, signal, strength_score)
    if blocked:
        return {"status": reason}

    atr = safe_float(data.get("atr"))
    pivot = infer_pivot(price, safe_float(data.get("pivot")), signal, atr)

    # تحديث قفل الاتجاه بالإغلاق الحالي
    update_direction_lock(ticker, price, pivot)

    allowed, _ = can_send_signal(ticker, signal.lower())
    if not allowed:
        stats["blocked_direction_lock"] += 1
        return {"status": f"direction locked on {get_locked_direction(ticker)}"}

    stock_levels = compute_stock_levels(price, pivot, signal, atr)

    budget = safe_float(data.get("budget"), DEFAULT_CONTRACT_BUDGET)
    strike_info = choose_strike(price, signal, strength_score, budget)
    option_levels = compute_option_targets(strike_info["estimated_premium"], strength_score)

    last_signals[ticker] = {
        "signal": signal,
        "time": time.time(),
        "score": strength_score,
        "price": price
    }

    if get_locked_direction(ticker) is None:
        direction_state[ticker] = {
            "locked_direction": signal.lower(),
            "above_count": 1 if signal == "CALL" else 0,
            "below_count": 1 if signal == "PUT" else 0,
            "last_pivot": pivot,
            "last_change": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    payload = {
        "ticker": ticker,
        "signal": signal,
        "interval": interval,
        "price": roundx(price),
        "pivot": pivot,
        "strength_score": strength_score,
        "strength_label": strength_label,
        "reasons": reasons,
        **stock_levels,
        **strike_info,
        **option_levels
    }

    message = build_alert_message(payload)
    last_signal_message = message
    send_telegram(message)
    stats["sent"] += 1

    daily_tracker["sent_count"] += 1
    daily_tracker["tickers"].append(ticker.upper())

    return {
        "status": "sent",
        "strength_score": strength_score,
        "strength_label": strength_label,
        "strike": strike_info["strike"],
        "pivot": pivot
    }


# =========================
# Telegram webhook
# =========================
@app.post("/telegram")
async def telegram_webhook(request: Request):
    global last_signal_message

    update = await parse_request_payload(request)

    try:
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = str(message.get("text", "")).strip()

        if not chat_id or not text:
            return {"ok": True}

        if text == "/start":
            send_telegram_reply(
                chat_id,
                "🔥 أهلاً بك في Option Strike Bot\n\n"
                "الأوامر:\n"
                "/help\n"
                "/status\n"
                "/last"
            )

        elif text == "/help":
            send_telegram_reply(
                chat_id,
                "🧠 البوت يستقبل إشارات TradingView ويرسل:\n"
                "- قوة الإشارة\n"
                "- السترايك المقترح\n"
                "- أهداف ووقف السهم\n"
                "- أهداف ووقف العقد\n"
                "- فلترة 80%+\n"
                "- حد أقصى 5 فرص يوميًا\n"
                "- قفل اتجاه بعد 3 إغلاقات ساعة"
            )

        elif text == "/status":
            send_telegram_reply(
                chat_id,
                f"✅ البوت شغال\n"
                f"الإشارات المرسلة: {stats['sent']}\n"
                f"ممنوع تكرار: {stats['blocked_duplicate']}\n"
                f"ممنوع تضارب: {stats['blocked_conflict']}\n"
                f"مرفوضة لضعفها: {stats['blocked_weak']}\n"
                f"مرفوضة بسبب القفل: {stats['blocked_direction_lock']}\n"
                f"المرسل اليوم: {daily_tracker['sent_count']}/{MAX_SIGNALS_PER_DAY}"
            )

        elif text == "/last":
            send_telegram_reply(chat_id, last_signal_message or "لا توجد إشارة سابقة حتى الآن.")

        else:
            send_telegram_reply(chat_id, "الأمر غير معروف. استخدم /help")

    except Exception:
        pass

    return {"ok": True}


# =========================
# اختبارات بيانات
# =========================
@app.get("/test_polygon")
def test_polygon():
    url = "https://api.polygon.io/v2/aggs/ticker/AAPL/prev"
    res = requests.get(url, params={"apiKey": API_KEY}, timeout=20)

    return {
        "status": res.status_code,
        "data": res.json()
    }


@app.get("/options/{ticker}")
def get_options(ticker: str):
    url = "https://api.polygon.io/v3/reference/options/contracts"

    res = requests.get(url, params={
        "underlying_ticker": ticker.upper(),
        "limit": 50,
        "apiKey": API_KEY
    }, timeout=20)

    return res.json()


# =========================
# اختيار عقد ذكي
# =========================
def get_yahoo_stock_price(ticker: str):
    price_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.upper()}"
    headers = {"User-Agent": "Mozilla/5.0"}

    price_res = requests.get(price_url, headers=headers, timeout=20)

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


def nearest_friday():
    today = datetime.now().date()
    days_ahead = (4 - today.weekday()) % 7
    if days_ahead == 0:
        return today.strftime("%Y-%m-%d")
    return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")


@app.get("/smart/{ticker}/{direction}")
def smart_contract(ticker: str, direction: str):
    url = "https://api.polygon.io/v3/reference/options/contracts"

    res = requests.get(url, params={
        "underlying_ticker": ticker.upper(),
        "limit": 100,
        "apiKey": API_KEY
    }, timeout=20)

    data = res.json().get("results", [])

    filtered = [
        c for c in data
        if c["contract_type"] == direction.lower()
    ]

    current_price = get_yahoo_stock_price(ticker)
    if not current_price:
        current_price = 100.0

    if not filtered:
        strike = round(current_price)
        return {
            "ticker": ticker.upper(),
            "type": direction.lower(),
            "strike": strike,
            "expiry": nearest_friday(),
            "contract": f"FALLBACK_{ticker.upper()}_{direction.upper()}",
            "current_price": current_price,
            "option_price": None,
            "bid": None,
            "ask": None,
            "fallback": True
        }

    filtered.sort(key=lambda x: x["expiration_date"])

    best = min(
        filtered,
        key=lambda x: abs(x["strike_price"] - current_price)
    )

    return {
        "ticker": ticker.upper(),
        "type": best["contract_type"],
        "strike": best["strike_price"],
        "expiry": best["expiration_date"],
        "contract": best["ticker"],
        "current_price": current_price,
        "option_price": None,
        "bid": None,
        "ask": None,
        "fallback": False
    }


# =========================
# Draft / Send / Contract / Update / Report
# =========================
@app.get("/draft/{ticker}/{direction}")
def draft_signal(ticker: str, direction: str, pivot: float = 0.0):
    smart = smart_contract(ticker, direction)

    allowed, _ = can_send_signal(ticker, direction.lower())
    if not allowed:
        return PlainTextResponse(f"الإشارة مرفوضة: الاتجاه مقفل على {get_locked_direction(ticker)}")

    strike = smart["strike"]
    expiry = smart["expiry"]
    contract = smart["contract"]
    current_price = safe_float(smart.get("current_price"), 100.0)
    option_price = smart.get("option_price")
    bid = smart.get("bid")
    ask = smart.get("ask")

    is_call = direction.lower() == "call"
    contract_type = "كول (CALL)" if is_call else "بوت (PUT)"
    direction_ar = "كول" if is_call else "بوت"
    icon = "🟢" if is_call else "🔴"

    pivot_value = roundx(pivot) if pivot > 0 else roundx(current_price)

    if option_price:
        entry_high = round(float(option_price), 2)
    else:
        entry_high = 2.50

    entry_low = round(max(entry_high - 0.50, 0.01), 2)
    entry_display = f"{entry_high:.2f}-{entry_low:.2f}"

    tp1 = round(entry_high + 0.60, 2)
    tp2 = round(entry_high + 1.20, 2)
    tp3 = round(entry_high + 2.00, 2)

    if is_call:
        stop_text = f"كسر {pivot_value:.2f} بإغلاق ساعة = خروج ❌"
    else:
        stop_text = f"اختراق {pivot_value:.2f} بإغلاق ساعة = خروج ❌"

    text = f"""🆕 طرح جديد | {ticker.upper()}

{icon} النوع: {contract_type}
🎯 السترايك: ${strike}
📅 التاريخ: {expiry}

💰 أسعار التنفيذ: {entry_display}

📈 الأهداف:
🥇 الهدف الأول: {tp1:.2f}
🥈 الهدف الثاني: {tp2:.2f}
🥉 الهدف الثالث: {tp3:.2f}

🛑 الوقف:
{stop_text}

⚠️ تنبيه: هذا الطرح تعليمي وليس توصية استثمارية، والقرار النهائي يعود للمتداول.

📢 @Option_Strike01"""

    key = f"{ticker.upper()}_{direction.lower()}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    trade_data = {
        "id": key,
        "ticker": ticker.upper(),
        "direction": direction.lower(),
        "direction_ar": direction_ar,
        "strike": strike,
        "expiry": expiry,
        "contract": contract,
        "pivot": pivot_value,
        "current_price": float(entry_high),
        "option_price": option_price,
        "bid": bid,
        "ask": ask,
        "entry_high": entry_high,
        "entry_low": entry_low,
        "entry_display": entry_display,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "highest_price": entry_high,
        "profit_pct": 0.0,
        "status": "OPEN",
        "created_at": now_str,
        "updated_at": now_str,
        "closed_at": "",
        "message": text
    }

    last_drafts[key] = trade_data
    refresh_report_file()

    return PlainTextResponse(text)


@app.get("/send/{ticker}/{direction}")
def send_signal(ticker: str, direction: str, pivot: float = 0.0):
    text_response = draft_signal(ticker, direction, pivot)
    try:
        text_value = text_response.body.decode("utf-8")
    except Exception:
        text_value = str(text_response)
    send_telegram_text(text_value)
    return text_response


@app.get("/contract/{ticker}/{direction}")
def contract_info(ticker: str, direction: str):
    smart = smart_contract(ticker, direction)

    return {
        "ticker": smart["ticker"],
        "direction": direction.lower(),
        "type": smart["type"],
        "strike": smart["strike"],
        "expiry": smart["expiry"],
        "contract": smart["contract"],
        "current_price": smart.get("current_price"),
        "option_price": smart.get("option_price"),
        "bid": smart.get("bid"),
        "ask": smart.get("ask"),
        "fallback": smart.get("fallback", False)
    }


@app.get("/update/{ticker}/{direction}/{entry}/{current}")
def update_signal(
    ticker: str,
    direction: str,
    entry: float,
    current: float,
    status: str = "OPEN"
):
    key = f"{ticker.upper()}_{direction.lower()}"
    saved = last_drafts.get(key)

    if not saved:
        return PlainTextResponse("لا يوجد طرح محفوظ لهذا السهم/الاتجاه. نفذ /draft أو /send أولاً.")

    strike = saved["strike"]
    direction_ar = saved["direction_ar"]

    highest_price = max(float(saved.get("highest_price", entry)), float(current))
    profit_pct = round(((current - entry) / entry) * 100, 2)

    saved["highest_price"] = round(highest_price, 2)
    saved["current_price"] = round(float(current), 2)
    saved["profit_pct"] = profit_pct
    saved["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    saved["status"] = status.upper()

    if status.upper() in ["WIN", "LOSS", "STOPPED", "CANCELLED"]:
        saved["closed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    refresh_report_file()

    current_label = "الأعلى المحقق" if current >= entry else "السعر الحالي"

    text = f"""🔔 تحديث | {ticker.upper()} ${strike} {direction_ar}

📊 سعر الدخول: {entry:.2f}
💰 {current_label}: {current:.2f}
📈 نسبة الربح: {profit_pct:+.2f}%
📌 الحالة: {saved["status"]}

⚠️ تنبيه: هذا الطرح تعليمي
والقرار النهائي يعود للمتداول.

📢 @Option_Strike01"""

    send_telegram_text(text)
    return PlainTextResponse(text)


@app.get("/lastdraft/{ticker}/{direction}")
def last_draft(ticker: str, direction: str):
    key = f"{ticker.upper()}_{direction.lower()}"
    saved = last_drafts.get(key)

    if not saved:
        return {"error": "no saved draft"}

    return saved


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
    return last_drafts
