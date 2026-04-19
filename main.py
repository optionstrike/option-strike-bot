from fastapi import FastAPI, Request
import requests
import yfinance as yf
import pandas as pd
import numpy as np
import time
import asyncio
from urllib.parse import quote_plus
from datetime import datetime, timedelta

app = FastAPI()

# =========================
# بياناتك
# =========================
TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055"
MASSIVE_API_KEY = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2"

API_SEND = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
API_ANSWER = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"

MASSIVE_BASE = "https://api.massive.com"

# =========================
# إعدادات الصيّاد
# =========================
MAX_SIGNALS_PER_DAY = 5
STOCK_COOLDOWN_DAYS = 3
TREND_CONFIRM_HOURS = 3
SCAN_INTERVAL_SECONDS = 3600  # كل ساعة

# =========================
# فلتر الدخول المباشر
# =========================
ENTRY_MAX_DISTANCE_PCT = 0.015   # 1.5%
BREAKOUT_BUFFER_PCT = 0.003      # 0.3%

# =========================
# شروط العقود
# =========================
MAX_COMPANY_CONTRACT_PRICE = 3.50
MAX_SPAC_CONTRACT_PRICE = 3.70
ENTRY_ZONE_WIDTH = 0.60
UPDATE_STEP_AFTER_TP1 = 0.30

# =========================
# أصول الارتكاز اليومي
# =========================
INDEX_DAILY_PIVOT = {"US500", "SPY", "QQQ", "SPX", "NDX", "US100"}

# إذا عندك قائمة SPACs حقيقية لاحقًا حطها هنا
SPAC_TICKERS = {
    "NBIS", "CRCL", "CRWV"
}

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
    "US500","SPY","QQQ","SPX","NDX","US100"
]))

# =========================
# جلسة requests ثابتة
# =========================
HTTP = requests.Session()

# =========================
# منع التكرار السريع للمستخدم
# =========================
_last = {}
COOLDOWN = 5

def allow(user):
    t = time.time()
    if user in _last and t - _last[user] < COOLDOWN:
        return False
    _last[user] = t
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
OPEN_CONTRACT_SIGNALS = {}   # contract_ticker -> state
LAST_DAILY_REPORT_DATE = None

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
    except Exception as e:
        print(f"[SEND ERROR] {e}")

def answer_callback(cb_id, text=""):
    try:
        HTTP.post(API_ANSWER, json={"callback_query_id": cb_id, "text": text}, timeout=10)
    except Exception as e:
        print(f"[CALLBACK ERROR] {e}")

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
        "NDX": "^NDX",
        "SPY": "SPY",
        "QQQ": "QQQ",
        "US500": "^GSPC",
        "US100": "^NDX",
    }
    return mapping.get(ticker, ticker)

def get_df(ticker, tf):
    period, interval = TF.get(tf, ("1y","1d"))
    data_ticker = map_symbol_for_data(ticker)
    s = yf.Ticker(data_ticker)
    df = s.history(period=period, interval=interval)
    if df.empty:
        return df

    df.index = pd.to_datetime(df.index, utc=False)

    if tf == "4h":
        df = df.resample("4H").agg({
            "Open":"first",
            "High":"max",
            "Low":"min",
            "Close":"last",
            "Volume":"sum"
        }).dropna()

    return df

# =========================
# Massive helpers
# =========================
def massive_get(path: str, params=None):
    params = params or {}
    params["apiKey"] = MASSIVE_API_KEY
    url = f"{MASSIVE_BASE}{path}"
    r = HTTP.get(url, params=params, timeout=25)
    r.raise_for_status()
    return r.json()

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
        except:
            pass
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
        except:
            pass
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
# تثبيت الاتجاه 3 ساعات حول الارتكاز
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
            "confirmed_at": datetime.now()
        }
        return side

    if prev["side"] == side:
        return side

    if side == "neutral":
        return prev["side"]

    if datetime.now() - prev["confirmed_at"] >= timedelta(hours=TREND_CONFIRM_HOURS):
        TREND_STATE[ticker] = {
            "side": side,
            "confirmed_at": datetime.now()
        }
        return side

    return prev["side"]

# =========================
# حسابات أساسية
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

    tp1 = pivot + ref_range * 0.5
    tp2 = pivot + ref_range
    tp3 = ref_high + ref_range
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

    best_entry = pivot + 0.2 if direction.startswith("CALL") else pivot - 0.2

    return {
        "price": price,
        "high": ref_high,
        "low": ref_low,
        "pivot": pivot,
        "pivot_label": pivot_label,
        "pivot_diff": pivot_diff,
        "pivot_position": pivot_position,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "sl": sl,
        "trend": trend,
        "strongest_trend": strongest_trend,
        "direction": direction,
        "best_entry": best_entry,
        "confirmed_side": confirmed_side,
        "ema20": ema20,
        "ema50": ema50
    }

# =========================
# معلومات القاما والسيولة من Massive chain
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
    except:
        return {
            "call": price,
            "put": price,
            "gamma": price,
            "zlow": price,
            "zhigh": price,
            "prob": 50,
            "liq": "—",
        }

# =========================
# اختيار العقد نفسه من Massive
# =========================
def is_spac_ticker(ticker: str) -> bool:
    return ticker in SPAC_TICKERS

def contract_price_limit_for_ticker(ticker: str) -> float:
    return MAX_SPAC_CONTRACT_PRICE if is_spac_ticker(ticker) else MAX_COMPANY_CONTRACT_PRICE

def choose_best_contract_from_massive(ticker: str, c: dict):
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
        elif direction.startswith("PUT"):
            target_type = "put"
        else:
            return None

        limit_price = contract_price_limit_for_ticker(ticker)
        underlying_price = c["price"]

        filtered = []
        for x in parsed:
            if x["contract_type"] != target_type:
                continue
            if not x["expiration"]:
                continue
            if x["contract_price"] is None or x["contract_price"] <= 0:
                continue
            if x["contract_price"] > limit_price:
                continue
            filtered.append(x)

        if not filtered:
            return None

        candidates = []
        for x in filtered:
            strike_distance = abs(x["strike"] - underlying_price)
            delta_score = abs(abs(x["delta"]) - 0.35)

            score = (
                strike_distance * 3
                + delta_score * 10
                - min(x["oi"], 100000) / 12000
                - min(abs(x["gamma"]), 1.0) * 8
                + abs(x["contract_price"] - min(limit_price, x["contract_price"])) * 0.1
            )
            candidates.append((score, x))

        if not candidates:
            return None

        candidates.sort(key=lambda z: z[0])
        best = candidates[0][1]

        contract_price = round(float(best["contract_price"]), 2)
        entry_high = contract_price
        entry_low = round(max(0.10, contract_price - ENTRY_ZONE_WIDTH), 2)

        tp1 = round(contract_price + 0.60, 2)
        tp2 = round(contract_price + 1.20, 2)
        tp3 = round(contract_price + 1.80, 2)

        if target_type == "call":
            stop_text = f"إغلاق شمعة ساعة تحت {c['pivot']:.2f}"
        else:
            stop_text = f"إغلاق شمعة ساعة فوق {c['pivot']:.2f}"

        success_rate = min(92, max(55, int(
            55
            + (10 if c["strongest_trend"] in ["صاعد قوي 🔥", "هابط قوي 🔻"] else 0)
            + (10 if c["direction"] != "انتظار ⚪" else 0)
            + (8 if abs(c["pivot_diff"]) > 0 else 0)
            + (5 if best["oi"] > 1000 else 0)
            + (4 if abs(best["delta"]) >= 0.20 else 0)
        )))

        return {
            "option_ticker": best["ticker"],
            "strike": round(best["strike"], 2),
            "expiration": best["expiration"],
            "contract_type": best["contract_type"],
            "contract_price": contract_price,
            "entry_high": entry_high,
            "entry_low": entry_low,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "stop_text": stop_text,
            "delta": round(best["delta"], 2),
            "gamma": round(best["gamma"], 4),
            "iv": round(best["iv"], 4),
            "oi": best["oi"],
            "success_rate": success_rate,
        }
    except Exception:
        return None

# =========================
# فلترة الصيّاد
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
# فلتر الدخول المباشر
# =========================
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
    except:
        return date_str

# =========================
# بناء الرسائل
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

🧲 معلومات داعمة:
القاما: {o['gamma']:.2f}
Magnet: {o['zlow']:.2f} - {o['zhigh']:.2f}
احتمال الوصول: {o['prob']}%
سيولة الكول: {o['call']:.2f}
سيولة البوت: {o['put']:.2f}
الأقوى: {o['liq']}"""

    if not contract:
        return base + "\n\n❌ لم يتم العثور على عقد مناسب ضمن حد السعر."

    return base + f"""

💎 العقد المختار:
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
📊 نسبة النجاح: {contract['success_rate']}%
Δ Delta: {contract['delta']:.2f}
Γ Gamma: {contract['gamma']:.4f}
IV: {contract['iv']:.4f}
OI: {contract['oi']}"""

def msg_channel_post(tk, contract):
    type_ar = "CALL" if contract["contract_type"] == "call" else "PUT"
    color = "🟢" if contract["contract_type"] == "call" else "🔴"

    return f"""🆕 طرح جديد | {tk}

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

def msg_contract_update(title, entry_price, current_price):
    pnl = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
    return f"""🔔 تحديث | {title}

📊 سعر الدخول: {entry_price:.2f}
💰 السعر الحالي: {current_price:.2f}
📈 نسبة الربح: {pnl:+.2f}%

⚠️ تنبيه: هذا الطرح تعليمي
والقرار النهائي يعود للمتداول.

📢 @Option_Strike01."""

def msg_gamma(tk, tf, c, o):
    return f"""🧲 {tk} Gamma & Liquidity | TF: {tf}

🧲 القاما: {o['gamma']:.2f}
📍 Magnet: {o['zlow']:.2f} - {o['zhigh']:.2f}
📊 احتمال الوصول: {o['prob']}%

💰 سيولة الكول: {o['call']:.2f}
💸 سيولة البوت: {o['put']:.2f}
🔥 الأقوى: {o['liq']}

📍 الارتكاز {c['pivot_label']}: {c['pivot']:.2f}
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

الاتجاه الأقوى: {c['strongest_trend']}
السعر الحالي: {c['price']:.2f}"""

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

🎯 أهداف:
1) {c['tp1']:.2f}
2) {c['tp2']:.2f}
3) {c['tp3']:.2f}

📈 القرار: {c['direction']}"""

def msg_contract(tk, tf, c, contract):
    if not contract:
        return "❌ لم يتم العثور على عقد مناسب ضمن حد السعر."
    return f"""💎 {tk} Best Contract | TF: {tf}

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

📊 نسبة النجاح: {contract['success_rate']}%"""

# =========================
# تخزين حالة المستخدم
# =========================
STATE = {}

def set_state(user, ticker=None, tf=None):
    s = STATE.get(user, {"ticker": None, "tf": "1d"})
    if ticker:
        s["ticker"] = ticker
    if tf:
        s["tf"] = tf
    STATE[user] = s

def get_state(user):
    return STATE.get(user, {"ticker": None, "tf": "1d"})

# =========================
# تسجيل العقد المطروح ومتابعته
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
        "created_at": datetime.now(),
        "channel_title": f"{ticker} ${contract['strike']:.2f} {'كول' if contract['contract_type']=='call' else 'بوت'}"
    }

def get_live_contract_price(underlying: str, option_ticker: str):
    try:
        snap = get_option_contract_snapshot(underlying, option_ticker)
        price = parse_contract_price_from_snapshot(snap)
        if price is not None:
            return float(price)
    except:
        pass

    try:
        lt = get_option_last_trade(option_ticker)
        p = lt.get("p")
        if p is not None:
            return float(p)
    except:
        pass

    return None

# =========================
# نسخة blocking للفحص الخلفي
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
            if c is None:
                continue

            if c["direction"] == "انتظار ⚪":
                continue

            if not is_entry_ready_now(c):
                continue

            o = options_info_from_massive(ticker, c["price"])
            contract = choose_best_contract_from_massive(ticker, c)
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

            if not sig["first_update_sent"] and price >= sig["tp1"]:
                send(msg_contract_update(sig["channel_title"], sig["entry_price"], price))
                sig["first_update_sent"] = True
                sig["last_update_trigger_price"] = price
                continue

            if sig["first_update_sent"]:
                if price >= sig["last_update_trigger_price"] + UPDATE_STEP_AFTER_TP1:
                    send(msg_contract_update(sig["channel_title"], sig["entry_price"], price))
                    sig["last_update_trigger_price"] = price
        except Exception as e:
            print(f"[CONTRACT UPDATE ERROR] {option_ticker}: {e}")

# =========================
# متابعة العقود المطروحة
# =========================
async def contract_update_loop():
    await asyncio.sleep(20)
    while True:
        try:
            await asyncio.to_thread(contract_update_cycle)
        except Exception as e:
            send(f"❌ خطأ في متابعة العقود: {str(e)}")

        await asyncio.sleep(300)

# =========================
# الصيّاد التلقائي
# =========================
async def scanner_loop():
    await asyncio.sleep(10)
    while True:
        try:
            await asyncio.to_thread(scanner_cycle)
        except Exception as e:
            send(f"❌ خطأ في الصيّاد: {str(e)}")

        await asyncio.sleep(SCAN_INTERVAL_SECONDS)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(scanner_loop())
    asyncio.create_task(contract_update_loop())

# =========================
# Webhook
# =========================
@app.post("/")
async def webhook(req: Request):
    try:
        data = await req.json()
    except Exception:
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

            df = await asyncio.to_thread(get_df, ticker, tf)
            if df.empty:
                send("❌ السهم غير صحيح أو لا توجد بيانات", chat_id=user)
                return {"ok": True}

            c = await asyncio.to_thread(core_metrics, df, ticker)
            if c is None:
                send("❌ تعذر حساب الارتكاز لهذا الأصل", chat_id=user)
                return {"ok": True}

            o = await asyncio.to_thread(options_info_from_massive, ticker, c["price"])
            contract = await asyncio.to_thread(choose_best_contract_from_massive, ticker, c)

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

            df = await asyncio.to_thread(get_df, ticker, tf)
            if df.empty:
                send("❌ لا توجد بيانات", chat_id=user)
                return {"ok": True}

            c = await asyncio.to_thread(core_metrics, df, ticker)
            if c is None:
                send("❌ تعذر حساب الارتكاز لهذا الأصل", chat_id=user)
                return {"ok": True}

            o = await asyncio.to_thread(options_info_from_massive, ticker, c["price"])
            contract = await asyncio.to_thread(choose_best_contract_from_massive, ticker, c)

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
        try:
            if "message" in data:
                user = str(data["message"]["chat"]["id"])
                send(f"❌ خطأ: {str(e)}", chat_id=user)
            elif "callback_query" in data:
                user = str(data["callback_query"]["message"]["chat"]["id"])
                send(f"❌ خطأ: {str(e)}", chat_id=user)
            else:
                send(f"❌ خطأ: {str(e)}")
        except:
            print(f"[WEBHOOK ERROR] {e}")

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
        "massive_connected": True
    }
