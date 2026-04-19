from fastapi import FastAPI, Request
import requests
import yfinance as yf
import pandas as pd
import time
import asyncio
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

# ✅ Base URL
MASSIVE_BASE = "https://api.polygon.io"

# =========================
# إعدادات الصياد
# =========================

MAX_SIGNALS_PER_DAY = 5
STOCK_COOLDOWN_DAYS = 3
TREND_CONFIRM_HOURS = 3
SCAN_INTERVAL_SECONDS = 10800

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
"NBIS", "CRCL", "CRWV"
}

# =========================
# قائمة الأسهم
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
# إرسال تلغرام
# =========================

def send(msg, keyboard=None, chat_id=None):
    target_chat_id = str(chat_id) if chat_id is not None else CHAT_ID
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
        try:
            payload.pop("parse_mode", None)
            r = HTTP.post(API_SEND, json=payload, timeout=20)
            r.raise_for_status()
        except Exception as e2:
            print(f"[SEND ERROR 2] {e2}")

def answer_callback(cb_id, text=""):
    try:
        HTTP.post(API_ANSWER, json={"callback_query_id": cb_id, "text": text}, timeout=10)
    except Exception as e:
        print(f"[CALLBACK ERROR] {e}")

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
                {"text": "📰 أخبار السوق", "callback_data": "news"},
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
# أخبار السوق
# =========================

def get_market_news(ticker: str = None, limit: int = 5):
    try:
        params = {"limit": limit, "order": "desc", "sort": "published_utc"}
        if ticker:
            params["ticker"] = ticker
        data = massive_get("/v2/reference/news", params=params)
        results = data.get("results", [])
        return results
    except Exception as e:
        print(f"[NEWS ERROR] {e}")
        return []

def format_news_message(ticker: str = None):
    news = get_market_news(ticker, limit=5)
    if not news:
        return "❌ لا توجد أخبار متاحة حالياً"

    label = f"أخبار {ticker}" if ticker else "أخبار السوق"
    msg = f"📰 <b>{label}</b>\n{'─' * 30}\n\n"

    for i, item in enumerate(news, 1):
        title = item.get("title", "بدون عنوان")
        publisher = safe_get(item, "publisher", "name", default="")
        published = item.get("published_utc", "")
        url = item.get("article_url", "")

        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            date_str = dt.strftime("%d/%m %H:%M")
        except:
            date_str = ""

        msg += f"<b>{i}. {title}</b>\n"
        if publisher:
            msg += f"📌 {publisher}"
        if date_str:
            msg += f" | 🕐 {date_str}"
        msg += "\n"
        if url:
            msg += f"🔗 <a href='{url}'>اقرأ المزيد</a>\n"
        msg += "\n"

    return msg
