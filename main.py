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

API_SEND = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
API_ANSWER = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"

# =========================
# إعدادات الصيّاد
# =========================
MAX_SIGNALS_PER_DAY = 5
STOCK_COOLDOWN_DAYS = 3
TREND_CONFIRM_HOURS = 3
SCAN_INTERVAL_SECONDS = 3600  # كل ساعة

# =========================
# قائمة الشركات (80 شركة)
# =========================
WATCHLIST = list(dict.fromkeys([
    "GLD","IBM","V","JPM","SBUX","MMM","QCOM","GOOG","INTC","NFLX","GS","SMH",
    "ABNB","TWLO","DASH","PYPL",
    "DHI","BE","ENPH","JNJ","DELL","BIDU","RDDT","DDOG","UPS","DE","NOW","UBER","INTU",
    "LRCX","LOW","HD","PANW","BA","ZS","MRVL","ULTA","SMCI","MARA","MCD","PDD","FDX",
    "FSLR","COST","SHOP","ALB","NBIS","ARM","CRCL","ABBV","HOOD","BABA","ADBE","LULU","ORCL",
    "LLY","TSM","CVNA","COIN","CRWV","CAT","AMD","SNOW","MDB","AMZN","MU","CRM","GE",
    "NVDA","AAPL","GOOGL","MSFT","TSLA","META","AVGO","CRWD","APP","UNH","MSTR","PLTR"
]))

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
LAST_SENT_STOCK = {}         # ticker -> datetime آخر إرسال
TREND_STATE = {}             # ticker -> {"side": "above"/"below"/"neutral", "confirmed_at": datetime}
DAILY_SIGNAL_STATE = {       # إعادة ضبط يومي
    "date": datetime.now().date(),
    "count": 0
}

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

def get_df(ticker, tf):
    period, interval = TF.get(tf, ("1y","1d"))
    s = yf.Ticker(ticker)
    df = s.history(period=period, interval=interval)
    if df.empty:
        return df

    # توحيد التوقيت وترتيب البيانات
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
# تثبيت الاتجاه 3 ساعات
# =========================
def get_confirmed_side_hourly(ticker: str):
    df_1h = get_df(ticker, "1h")
    if df_1h.empty or len(df_1h) < 20:
        return "neutral"

    price = float(df_1h["Close"].iloc[-1])
    high = float(df_1h["High"].rolling(20).max().iloc[-1])
    low = float(df_1h["Low"].rolling(20).min().iloc[-1])
    pivot = (high + low + price) / 3.0

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

    # إذا نفس الجهة، خله ثابت
    if prev["side"] == side:
        return side

    # إذا رجع محايد، لا نقلب الاتجاه المؤكد مباشرة
    if side == "neutral":
        return prev["side"]

    # يحتاج 3 ساعات تثبيت فعلية قبل تغيير الحالة
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

    base_trend = "صاعد 📈" if ema20 > ema50 else "هابط 📉"

    confirmed_side = get_confirmed_side_hourly(ticker) if ticker else "neutral"

    if confirmed_side == "above":
        strongest_trend = "صاعد قوي 🔥"
    elif confirmed_side == "below":
        strongest_trend = "هابط قوي 🔻"
    else:
        strongest_trend = "محايد ⚖️"

    # القرار النهائي
    if price > pivot and confirmed_side == "above" and ema20 > ema50:
        direction = "CALL 🟢"
    elif price < pivot and confirmed_side == "below" and ema20 < ema50:
        direction = "PUT 🔴"
    else:
        direction = "انتظار ⚪"

    best_entry = pivot + 0.2 if direction.startswith("CALL") else pivot - 0.2

    return {
        "price": price,
        "high": high,
        "low": low,
        "pivot": pivot,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "sl": sl,
        "trend": base_trend,
        "strongest_trend": strongest_trend,
        "direction": direction,
        "best_entry": best_entry,
        "confirmed_side": confirmed_side,
        "ema20": ema20,
        "ema50": ema50
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

        if calls.empty or puts.empty:
            raise Exception("empty chain")

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

        strike = round(price)
        expiry = "1-2 weeks"

        return {
            "call": call_strike,
            "put": put_strike,
            "gamma": gamma,
            "zlow": zone_low,
            "zhigh": zone_high,
            "prob": prob,
            "liq": liquidity,
            "strike": strike,
            "expiry": expiry
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
            "strike": round(price),
            "expiry": "—"
        }

# =========================
# فلترة الصيّاد
# =========================
def calc_score(c, o):
    score = 0

    if c["direction"].startswith("CALL") or c["direction"].startswith("PUT"):
        score += 30

    if c["strongest_trend"] in ["صاعد قوي 🔥", "هابط قوي 🔻"]:
        score += 25

    if o["prob"] >= 60:
        score += 20

    if o["liq"] != "—":
        score += 10

    if c["trend"] == "صاعد 📈" and c["direction"].startswith("CALL"):
        score += 10
    if c["trend"] == "هابط 📉" and c["direction"].startswith("PUT"):
        score += 10

    if c["price"] > c["pivot"] and c["direction"].startswith("CALL"):
        score += 5
    if c["price"] < c["pivot"] and c["direction"].startswith("PUT"):
        score += 5

    return score

# =========================
# بناء الرسائل
# =========================
def msg_quick(tk, tf, c):
    return f"""📊 {tk} | TF: {tf}

السعر: {c['price']:.2f}
الاتجاه: {c['trend']}
الاتجاه الأقوى: {c['strongest_trend']}

🔵 دعم: {c['low']:.2f}
🔴 مقاومة: {c['high']:.2f}

📌 دخول: {c['best_entry']:.2f}
🛑 وقف: {c['sl']:.2f}

📈 القرار: {c['direction']}"""

def msg_pro(tk, tf, c, o):
    return f"""🔥 {tk} Professional | TF: {tf}

السعر: {c['price']:.2f}
الاتجاه: {c['trend']}
الاتجاه الأقوى: {c['strongest_trend']}

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

الاتجاه الأقوى: {c['strongest_trend']}
السعر الحالي: {c['price']:.2f}"""

def msg_sr(tk, tf, c):
    return f"""📈 {tk} Support/Resistance | TF: {tf}

🔵 دعم: {c['low']:.2f}
🔴 مقاومة: {c['high']:.2f}

Pivot: {c['pivot']:.2f}
الاتجاه الأقوى: {c['strongest_trend']}"""

def msg_plan(tk, tf, c):
    return f"""🎯 {tk} Entry Plan | TF: {tf}

الاتجاه الأقوى: {c['strongest_trend']}
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

الاتجاه الأقوى: {c['strongest_trend']}
📌 دخول: {c['best_entry']:.2f}
🛑 وقف: {c['sl']:.2f}

🎯 أهداف:
1) {c['tp1']:.2f}
2) {c['tp2']:.2f}
3) {c['tp3']:.2f}"""

def msg_scanner_signal(tk, c, o, score):
    return f"""🚨 فرصة قوية | {tk}

السعر: {c['price']:.2f}
الاتجاه: {c['trend']}
الاتجاه الأقوى: {c['strongest_trend']}

📌 دخول: {c['best_entry']:.2f}
🛑 وقف: {c['sl']:.2f}

🎯 الأهداف:
1) {c['tp1']:.2f}
2) {c['tp2']:.2f}
3) {c['tp3']:.2f}

🧲 القاما: {o['gamma']:.2f}
📊 احتمال الوصول: {o['prob']}%
💰 سيولة: {o['liq']}

📈 القرار: {c['direction']}
⭐ Score: {score}%"""

# =========================
# تخزين حالة المستخدم
# =========================
STATE = {}  # user_id -> {"ticker": str, "tf": str}

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
# الصيّاد التلقائي
# =========================
async def scanner_loop():
    await asyncio.sleep(10)  # مهلة قصيرة بعد التشغيل
    while True:
        try:
            reset_daily_counter_if_needed()

            if not can_send_more_today():
                await asyncio.sleep(SCAN_INTERVAL_SECONDS)
                continue

            results = []

            for ticker in WATCHLIST:
                try:
                    if stock_in_cooldown(ticker):
                        continue

                    df = get_df(ticker, "1h")
                    if df.empty or len(df) < 20:
                        continue

                    c = core_metrics(df, ticker=ticker)
                    o = options_approx(ticker, c["price"])

                    # فقط إشارات فعلية، وليس انتظار
                    if c["direction"] == "انتظار ⚪":
                        continue

                    score = calc_score(c, o)
                    if score < 60:
                        continue

                    results.append((ticker, score, c, o))
                except:
                    continue

            results.sort(key=lambda x: x[1], reverse=True)

            sent_now = 0
            for ticker, score, c, o in results:
                if not can_send_more_today():
                    break

                if stock_in_cooldown(ticker):
                    continue

                send(msg_scanner_signal(ticker, c, o, score))
                mark_stock_sent(ticker)
                add_daily_signal()
                sent_now += 1

                if sent_now >= MAX_SIGNALS_PER_DAY:
                    break

        except Exception as e:
            send(f"❌ خطأ في الصيّاد: {str(e)}")

        await asyncio.sleep(SCAN_INTERVAL_SECONDS)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(scanner_loop())

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
                send("👋 أهلاً بك\nأرسل رمز السهم من قائمتك مثل: NVDA\nأو اختر من القائمة 👇", main_menu())
                return {"ok": True}

            if text == "/test":
                send("✅ البوت شغال 100%")
                return {"ok": True}

            # parse ticker + tf
            parts = text.upper().split()
            ticker = parts[0]
            tf = parts[1].lower() if len(parts) > 1 else get_state(user)["tf"]

            if ticker not in WATCHLIST:
                send("❌ هذا السهم غير موجود في قائمتك")
                return {"ok": True}

            set_state(user, ticker=ticker, tf=tf)

            df = get_df(ticker, tf)
            if df.empty:
                send("❌ السهم غير صحيح أو لا توجد بيانات")
                return {"ok": True}

            c = core_metrics(df, ticker=ticker)
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

            if ticker not in WATCHLIST:
                send("❌ هذا السهم غير موجود في قائمتك")
                return {"ok": True}

            df = get_df(ticker, tf)
            if df.empty:
                send("❌ لا توجد بيانات")
                return {"ok": True}

            c = core_metrics(df, ticker=ticker)
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
    return {
        "status": "LIVE",
        "watchlist_count": len(WATCHLIST),
        "daily_limit": MAX_SIGNALS_PER_DAY,
        "stock_cooldown_days": STOCK_COOLDOWN_DAYS,
        "trend_confirm_hours": TREND_CONFIRM_HOURS
    }
