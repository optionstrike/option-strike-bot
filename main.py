from fastapi import FastAPI, Request
import requests
import yfinance as yf
import pandas as pd
import numpy as np
import time
from urllib.parse import quote_plus

app = FastAPI()

# =========================
# بياناتك
# =========================
TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055"

API_SEND = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
API_ANSWER = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"

# =========================
# منع التكرار
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
# إرسال
# =========================
def send(msg, keyboard=None):
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "disable_web_page_preview": True
    }
    if keyboard:
        payload["reply_markup"] = keyboard
    requests.post(API_SEND, json=payload, timeout=20)

def answer_callback(cb_id, text=""):
    try:
        requests.post(API_ANSWER, json={"callback_query_id": cb_id, "text": text}, timeout=10)
    except:
        pass

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
            rows.append(row); row=[]
    if row: rows.append(row)
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

def get_df(ticker, tf):
    period, interval = TF.get(tf, ("1y","1d"))
    s = yf.Ticker(ticker)
    df = s.history(period=period, interval=interval)
    if df.empty:
        return df
    if tf == "4h":
        df = df.resample("4H").agg({
            "Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"
        }).dropna()
    return df

# =========================
# حسابات أساسية
# =========================
def core_metrics(df):
    price = float(df["Close"].iloc[-1])
    high = float(df["High"].rolling(20).max().iloc[-1])
    low  = float(df["Low"].rolling(20).min().iloc[-1])

    pivot = (high + low + price) / 3.0
    rng = high - low

    tp1 = pivot + rng * 0.5
    tp2 = pivot + rng
    tp3 = high + rng
    sl = pivot

    ema20 = float(df["Close"].ewm(span=20).mean().iloc[-1])
    ema50 = float(df["Close"].ewm(span=50).mean().iloc[-1])
    trend = "صاعد 📈" if ema20 > ema50 else "هابط 📉"

    direction = "CALL 🟢" if price > pivot else "PUT 🔴"
    best_entry = pivot + 0.2 if direction.startswith("CALL") else pivot - 0.2

    return {
        "price": price, "high": high, "low": low,
        "pivot": pivot, "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl,
        "trend": trend, "direction": direction, "best_entry": best_entry
    }

def options_approx(ticker, price):
    try:
        s = yf.Ticker(ticker)
        exps = s.options
        if not exps:
            raise Exception("no exp")
        chain = s.option_chain(exps[0])
        calls = chain.calls
        puts  = chain.puts

        call_wall = calls.loc[calls['openInterest'].idxmax()]
        put_wall  = puts.loc[puts['openInterest'].idxmax()]

        call_strike = float(call_wall['strike'])
        put_strike  = float(put_wall['strike'])

        gamma = call_strike
        zone_low = gamma - 0.5
        zone_high = gamma + 0.5

        dist = abs(price - gamma)
        prob = max(50, 85 - int(dist))

        liquidity = "CALL 🟢" if call_strike > price else "PUT 🔴"

        # اقتراح عقد بسيط
        strike = round(price)
        expiry = "1-2 weeks"

        return {
            "call": call_strike, "put": put_strike,
            "gamma": gamma, "zlow": zone_low, "zhigh": zone_high,
            "prob": prob, "liq": liquidity,
            "strike": strike, "expiry": expiry
        }
    except:
        return {
            "call": price, "put": price,
            "gamma": price, "zlow": price, "zhigh": price,
            "prob": 50, "liq": "—",
            "strike": round(price), "expiry": "—"
        }

# =========================
# بناء الرسائل
# =========================
def msg_quick(tk, tf, c):
    return f"""📊 {tk} | TF: {tf}

السعر: {c['price']:.2f}
الاتجاه: {c['trend']}

🔵 دعم: {c['low']:.2f}
🔴 مقاومة: {c['high']:.2f}

📌 دخول: {c['best_entry']:.2f}
🛑 وقف: {c['sl']:.2f}

📈 القرار: {c['direction']}"""

def msg_pro(tk, tf, c, o):
    return f"""🔥 {tk} Professional | TF: {tf}

السعر: {c['price']:.2f}
الاتجاه: {c['trend']}

🔵 دعم: {c['low']:.2f}
🔴 مقاومة: {c['high']:.2f}

🧲 القاما: {o['gamma']:.2f}
📍 Magnet: {o['zlow']:.2f} - {o['zhigh']:.2f}
📊 احتمال الوصول: {o['prob']}%

💰 كول: {o['call']:.2f}
💸 بوت: {o['put']:.2f}
🔥 الأقوى: {o['liq']}

📌 دخول: {c['best_entry']:.2f}
🛑 وقف: {c['sl']:.2f}

🎯 الأهداف:
1) {c['tp1']:.2f}
2) {c['tp2']:.2f}
3) {c['tp3']:.2f}

📈 القرار: {c['direction']}"""

def msg_gamma(tk, tf, c, o):
    return f"""🧲 {tk} Gamma & Liquidity | TF: {tf}

🧲 القاما: {o['gamma']:.2f}
📍 Magnet: {o['zlow']:.2f} - {o['zhigh']:.2f}
📊 احتمال الوصول: {o['prob']}%

💰 سيولة الكول: {o['call']:.2f}
💸 سيولة البوت: {o['put']:.2f}
🔥 الأقوى: {o['liq']}

السعر الحالي: {c['price']:.2f}"""

def msg_sr(tk, tf, c):
    return f"""📈 {tk} Support/Resistance | TF: {tf}

🔵 دعم: {c['low']:.2f}
🔴 مقاومة: {c['high']:.2f}

Pivot: {c['pivot']:.2f}"""

def msg_plan(tk, tf, c):
    return f"""🎯 {tk} Entry Plan | TF: {tf}

📌 دخول: {c['best_entry']:.2f}
🛑 وقف: {c['sl']:.2f}

🎯 أهداف:
1) {c['tp1']:.2f}
2) {c['tp2']:.2f}
3) {c['tp3']:.2f}

📈 القرار: {c['direction']}"""

def msg_contract(tk, tf, c, o):
    return f"""💎 {tk} Best Contract | TF: {tf}

Type: {c['direction']}
Strike: {o['strike']}
Expiry: {o['expiry']}

📌 دخول: {c['best_entry']:.2f}
🛑 وقف: {c['sl']:.2f}

🎯 أهداف:
1) {c['tp1']:.2f}
2) {c['tp2']:.2f}
3) {c['tp3']:.2f}"""

# =========================
# تخزين حالة المستخدم
# =========================
STATE = {}  # user_id -> {"ticker": str, "tf": str}

def set_state(user, ticker=None, tf=None):
    s = STATE.get(user, {"ticker": None, "tf": "1d"})
    if ticker: s["ticker"] = ticker
    if tf: s["tf"] = tf
    STATE[user] = s

def get_state(user):
    return STATE.get(user, {"ticker": None, "tf": "1d"})

# =========================
# Webhook
# =========================
@app.post("/")
async def webhook(req: Request):
    data = await req.json()

    try:
        # رسالة نصية
        if "message" in data:
            msg = data["message"]
            text = msg.get("text", "").strip()
            user = str(msg["chat"]["id"])

            if not allow(user):
                return {"ok": True}

            if text == "/start":
                set_state(user, ticker=None, tf="1d")
                send("👋 أهلاً بك\nأرسل رمز السهم مثل: NVDA\nأو اختر من القائمة 👇", main_menu())
                return {"ok": True}

            if text == "/test":
                send("✅ البوت شغال 100%")
                return {"ok": True}

            # parse ticker + tf
            parts = text.upper().split()
            ticker = parts[0]
            tf = parts[1].lower() if len(parts) > 1 else get_state(user)["tf"]

            set_state(user, ticker=ticker, tf=tf)

            df = get_df(ticker, tf)
            if df.empty:
                send("❌ السهم غير صحيح أو لا توجد بيانات")
                return {"ok": True}

            c = core_metrics(df)
            o = options_approx(ticker, c["price"])

            send(msg_pro(ticker, tf, c, o), main_menu())
            return {"ok": True}

        # أزرار
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
                send("اختر الفريم 👇", tf_menu())
                return {"ok": True}

            if data_cb.startswith("settf:"):
                new_tf = data_cb.split(":")[1]
                set_state(user, tf=new_tf)
                send(f"تم تغيير الفريم إلى {new_tf}", main_menu())
                return {"ok": True}

            if data_cb == "back":
                send("رجوع للقائمة", main_menu())
                return {"ok": True}

            if not ticker:
                send("أرسل رمز السهم أولاً مثل: NVDA")
                return {"ok": True}

            df = get_df(ticker, tf)
            if df.empty:
                send("❌ لا توجد بيانات")
                return {"ok": True}

            c = core_metrics(df)
            o = options_approx(ticker, c["price"])

            if data_cb == "quick":
                send(msg_quick(ticker, tf, c), main_menu())
            elif data_cb == "pro":
                send(msg_pro(ticker, tf, c, o), main_menu())
            elif data_cb == "gamma":
                send(msg_gamma(ticker, tf, c, o), main_menu())
            elif data_cb == "sr":
                send(msg_sr(ticker, tf, c), main_menu())
            elif data_cb == "plan":
                send(msg_plan(ticker, tf, c), main_menu())
            elif data_cb == "contract":
                send(msg_contract(ticker, tf, c, o), main_menu())

            return {"ok": True}

    except Exception as e:
        send(f"❌ خطأ: {str(e)}")

    return {"ok": True}

# =========================
# حالة السيرفر
# =========================
@app.get("/")
def home():
    return {"status": "LIVE"}
