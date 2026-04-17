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
# فلتر الدخول المباشر
# =========================
ENTRY_MAX_DISTANCE_PCT = 0.015   # 1.5%
BREAKOUT_BUFFER_PCT = 0.003      # 0.3%

# =========================
# أصول الارتكاز اليومي
# =========================
INDEX_DAILY_PIVOT = {"US500", "SPY", "QQQ", "SPX", "NDX", "US100"}

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

    # ===== تحديد نوع الارتكاز =====
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

    # القرار النهائي = الترند + الارتكاز فقط
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

def options_approx(ticker, price):
    try:
        data_ticker = map_symbol_for_data(ticker)
        s = yf.Ticker(data_ticker)
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

def msg_pro(tk, tf, c, o):
    return f"""🔥 {tk} Professional | TF: {tf}

السعر: {c['price']:.2f}
الترند: {c['trend']}
الاتجاه الأقوى: {c['strongest_trend']}

🔵 دعم {c['pivot_label']}: {c['low']:.2f}
🔴 مقاومة {c['pivot_label']}: {c['high']:.2f}
📍 الارتكاز {c['pivot_label']}: {c['pivot']:.2f}
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

📌 دخول: {c['best_entry']:.2f}
🛑 وقف: {c['sl']:.2f}

🎯 الأهداف:
1) {c['tp1']:.2f}
2) {c['tp2']:.2f}
3) {c['tp3']:.2f}

📈 القرار النهائي: {c['direction']}

🧲 معلومات القاما:
القاما: {o['gamma']:.2f}
Magnet: {o['zlow']:.2f} - {o['zhigh']:.2f}
احتمال الوصول: {o['prob']}%
سيولة الكول: {o['call']:.2f}
سيولة البوت: {o['put']:.2f}
الأقوى: {o['liq']}"""

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

def msg_contract(tk, tf, c, o):
    return f"""💎 {tk} Best Contract | TF: {tf}

Type: {c['direction']}
Strike: {o['strike']}
Expiry: {o['expiry']}

الاتجاه الأقوى: {c['strongest_trend']}
📍 الارتكاز {c['pivot_label']}: {c['pivot']:.2f}
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

📌 دخول: {c['best_entry']:.2f}
🛑 وقف: {c['sl']:.2f}

🎯 أهداف:
1) {c['tp1']:.2f}
2) {c['tp2']:.2f}
3) {c['tp3']:.2f}"""

def msg_scanner_signal(tk, c, o, score):
    return f"""🚨 دخول الآن | {tk}

السعر: {c['price']:.2f}
الترند: {c['trend']}
الاتجاه الأقوى: {c['strongest_trend']}

📍 الارتكاز {c['pivot_label']}: {c['pivot']:.2f}
📏 البعد عن الارتكاز: {c['pivot_diff']:+.2f} ({c['pivot_position']})

📌 دخول الآن: {c['best_entry']:.2f}
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
# الصيّاد التلقائي
# =========================
async def scanner_loop():
    await asyncio.sleep(10)
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
                    if c is None:
                        continue

                    o = options_approx(ticker, c["price"])

                    if c["direction"] == "انتظار ⚪":
                        continue

                    if not is_entry_ready_now(c):
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
        if "message" in data:
            msg = data["message"]
            text = msg.get("text", "").strip()
            user = str(msg["chat"]["id"])

            if not allow(user):
                return {"ok": True}

            if text == "/start":
                set_state(user, ticker=None, tf="1d")
                send("👋 أهلاً بك\nأرسل رمز السهم من قائمتك مثل: NVDA أو SPY\nأو اختر من القائمة 👇", main_menu())
                return {"ok": True}

            if text == "/test":
                send("✅ البوت شغال 100%")
                return {"ok": True}

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
            if c is None:
                send("❌ تعذر حساب الارتكاز لهذا الأصل")
                return {"ok": True}

            o = options_approx(ticker, c["price"])

            send(msg_pro(ticker, tf, c, o), main_menu())
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
            if c is None:
                send("❌ تعذر حساب الارتكاز لهذا الأصل")
                return {"ok": True}

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
        "trend_confirm_hours": TREND_CONFIRM_HOURS,
        "entry_max_distance_pct": ENTRY_MAX_DISTANCE_PCT,
        "breakout_buffer_pct": BREAKOUT_BUFFER_PCT
    }
