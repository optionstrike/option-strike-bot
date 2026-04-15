from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests
import os
import time
import json
from typing import Dict, Any, Optional

app = FastAPI()
API_KEY = "zgd0qCw0OW5HNLXhuMC6jN1rjIpQQuzU"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0").strip()
CHAT_ID = os.getenv("CHAT_ID", "8371374055").strip()
SECRET_KEY = os.getenv("SECRET_KEY", "12345").strip()

# إعدادات قابلة للتعديل من Render
DUPLICATE_WINDOW_SEC = int(os.getenv("DUPLICATE_WINDOW_SEC", "300"))
CONFLICT_WINDOW_SEC = int(os.getenv("CONFLICT_WINDOW_SEC", "300"))
MIN_STRENGTH_TO_SEND = int(os.getenv("MIN_STRENGTH_TO_SEND", "40"))
DEFAULT_CONTRACT_BUDGET = float(os.getenv("DEFAULT_CONTRACT_BUDGET", "3.0"))
ROUND_TO = int(os.getenv("ROUND_TO", "2"))

# ذاكرة بسيطة داخلية
last_signals: Dict[str, Dict[str, Any]] = {}
last_signal_message: Optional[str] = None
stats = {
    "sent": 0,
    "blocked_duplicate": 0,
    "blocked_conflict": 0,
    "blocked_weak": 0,
    "blocked_secret": 0,
    "invalid_payload": 0,
}


def roundx(value: float) -> float:
    return round(value, ROUND_TO)


def safe_float(value, default=0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


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


def format_strength_label(score: int) -> str:
    if score >= 80:
        return "قوية جدًا"
    if score >= 65:
        return "قوية"
    if score >= 50:
        return "متوسطة"
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
        stock_stop = roundx(min(pivot, price - atr * 0.75))
        t1 = roundx(price + atr * 0.8)
        t2 = roundx(price + atr * 1.5)
        t3 = roundx(price + atr * 2.4)
    else:
        stock_stop = roundx(max(pivot, price + atr * 0.75))
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
        if strength_score >= 80:
            raw_strike = price * 1.01
        elif strength_score >= 65:
            raw_strike = price * 1.005
        elif strength_score >= 50:
            raw_strike = price
        else:
            raw_strike = price * 0.995
    else:
        if strength_score >= 80:
            raw_strike = price * 0.99
        elif strength_score >= 65:
            raw_strike = price * 0.995
        elif strength_score >= 50:
            raw_strike = price
        else:
            raw_strike = price * 1.005

    strike = round(raw_strike / step) * step
    distance_pct = abs(strike - price) / max(price, 1)
    estimated_premium = max(0.6, budget - (distance_pct * 20))
    estimated_premium = roundx(min(max(estimated_premium, 0.8), budget))

    return {
        "strike": roundx(strike),
        "step": step,
        "estimated_premium": estimated_premium
    }


def compute_option_targets(estimated_premium: float, strength_score: int):
    if strength_score >= 80:
        tp1_mult, tp2_mult, tp3_mult = 1.25, 1.55, 1.95
        stop_mult = 0.72
    elif strength_score >= 65:
        tp1_mult, tp2_mult, tp3_mult = 1.20, 1.45, 1.75
        stop_mult = 0.75
    elif strength_score >= 50:
        tp1_mult, tp2_mult, tp3_mult = 1.15, 1.35, 1.60
        stop_mult = 0.78
    else:
        tp1_mult, tp2_mult, tp3_mult = 1.10, 1.25, 1.45
        stop_mult = 0.82

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


def should_block_signal(ticker: str, signal: str, score: int):
    now = time.time()

    if score < MIN_STRENGTH_TO_SEND:
        stats["blocked_weak"] += 1
        return True, "weak blocked"

    if ticker in last_signals:
        prev = last_signals[ticker]

        if prev["signal"] == signal and (now - prev["time"] < DUPLICATE_WINDOW_SEC):
            stats["blocked_duplicate"] += 1
            return True, "duplicate blocked"

        if prev["signal"] != signal and (now - prev["time"] < CONFLICT_WINDOW_SEC):
            stats["blocked_conflict"] += 1
            return True, "conflict blocked"

    return False, "ok"


def build_alert_message(payload: Dict[str, Any]) -> str:
    ticker = payload["ticker"]
    signal = payload["signal"]
    interval = payload["interval"]
    price = payload["price"]
    strength_label = payload["strength_label"]
    strength_score = payload["strength_score"]
    pivot = payload["pivot"]

    strike = payload["strike"]

    stock_stop = payload["stock_stop"]
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
{stock_stop}

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


@app.get("/")
def home():
    return {"status": "Option Strike Bot running"}


@app.get("/status")
def status():
    return {
        "status": "running",
        "stats": stats,
        "tracked_symbols": len(last_signals)
    }


@app.get("/last")
def last():
    return {"last_signal": last_signal_message}


@app.get("/test")
def test():
    send_telegram("🔥 البوت شغال بنجاح!")
    return {"status": "ok"}


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

    return {
        "status": "sent",
        "strength_score": strength_score,
        "strength_label": strength_label,
        "strike": strike_info["strike"]
    }


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
                "الأوامر المتاحة:\n"
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
                "- فلترة ذكية ومنع تضارب"
            )

        elif text == "/status":
            send_telegram_reply(
                chat_id,
                f"✅ البوت شغال\n"
                f"الإشارات المرسلة: {stats['sent']}\n"
                f"ممنوع تكرار: {stats['blocked_duplicate']}\n"
                f"ممنوع تضارب: {stats['blocked_conflict']}\n"
                f"مرفوضة لضعفها: {stats['blocked_weak']}"
            )

        elif text == "/last":
            send_telegram_reply(chat_id, last_signal_message or "لا توجد إشارة سابقة حتى الآن.")

        else:
            send_telegram_reply(chat_id, "الأمر غير معروف. استخدم /help")

    except Exception:
        pass

    return {"ok": True}
@app.get("/test")
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
@app.get("/smart/{ticker}/{direction}")
def smart_contract(ticker: str, direction: str):
    import datetime

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

    filtered.sort(key=lambda x: x["expiration_date"])

    if not filtered:
        return {"error": "no contracts"}

 # نجيب سعر السهم الحالي من Yahoo Finance
    price_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.upper()}"
    price_res = requests.get(price_url, timeout=20)
    price_data = price_res.json()

    result = price_data.get("chart", {}).get("result", [])
    if not result:
        return {"error": "could not get current stock price", "price_data": price_data}

    meta = result[0].get("meta", {})
    current_price = meta.get("regularMarketPrice", 0)

    if not current_price:
        return {"error": "could not get current stock price", "price_data": price_data}

    # نختار أقرب سترايك للسعر
    best = min(
        filtered,
        key=lambda x: abs(x["strike_price"] - current_price)
    )

    return {
        "ticker": ticker.upper(),
        "type": best["contract_type"],
        "strike": best["strike_price"],
        "expiry": best["expiration_date"],
        "contract": best["ticker"]
    }
