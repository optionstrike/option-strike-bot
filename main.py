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
