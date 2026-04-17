from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo
# المكتبة الجديدة للتحليل الفني
from tradingview_ta import TA_Handler, Interval, Exchange

app = FastAPI()

# ==========================================
# 1. الإعدادات (نفس بياناتك السابقة)
# ==========================================
API_KEY = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2"
TELEGRAM_TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055"
SECRET_KEY = "12345"

# القيود والفلترة
MIN_SCORE_TO_SEND = 60         
MAX_SIGNALS_PER_DAY = 5        
DUPLICATE_WINDOW_SEC = 10800   

# إعدادات العقود والجمعة
DEFAULT_CONTRACT_BUDGET = 3.0
MAX_SPREAD_PCT = 40.0          
MAX_STRIKE_DISTANCE_PCT = 5.0  
ZERO_HERO_MAX_ASK = 1.50
MONITOR_INTERVAL_SEC = 60
ROUND_TO = 2

# ==========================================
# 2. الذاكرة والبيانات
# ==========================================
trades_store: Dict[str, Dict[str, Any]] = {}
daily_tracker = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "sent_count": 0,
    "tickers": []
}

# ==========================================
# 3. وظائف المساعد الذكي (Telegram Interaction)
# ==========================================

def get_tv_analysis(symbol: str):
    """جلب تحليل حقيقي من تريندنق فيو"""
    try:
        handler = TA_Handler(
            symbol=symbol.upper(),
            screener="america",
            exchange="NASDAQ", # سيحاول البحث في ناسداك أولاً
            interval=Interval.INTERVAL_1_HOUR
        )
        analysis = handler.get_analysis()
        summary = analysis.summary
        indicators = analysis.indicators
        
        # تنسيق النتيجة
        result = f"📊 تحليل TradingView لسهم {symbol.upper()}:\n"
        result += f"القرار: **{summary['RECOMMENDATION']}**\n"
        result += f"🟢 شراء: {summary['BUY']} | 🔴 بيع: {summary['SELL']}\n"
        result += f"📍 السعر الحالي: {indicators['close']}\n"
        result += f"📉 RSI: {round(indicators['RSI'], 2)}"
        return result
    except Exception as e:
        return f"❌ تعذر جلب تحليل {symbol}. تأكد من رمز السهم."

def send_telegram_with_menu(message: str):
    """إرسال رسالة مع أزرار التحكم"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": {
            "keyboard": [
                [{"text": "📈 تحليل سهم معين"}, {"text": "💰 نتائج العقود"}],
                [{"text": "📋 طلب تقرير اليوم"}]
            ],
            "resize_keyboard": True
        }
    }
    requests.post(url, json=payload)

# معالج الرسائل القادمة من المستخدم
@app.post("/telegram_webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    if "message" not in data: return {"ok": True}
    
    msg = data["message"]
    user_id = str(msg["from"]["id"])
    text = msg.get("text", "")

    # التأكد أنك أنت المرسل فقط
    if user_id != CHAT_ID: return {"ok": True}

    if text.lower() in ["/start", "start", "مرحبا"]:
        send_telegram_with_menu("هلا بك ياقلبي! وش حاب نسوي اليوم؟")
    
    elif "تحليل سهم" in text:
        send_telegram("أرسل رمز السهم فقط (مثال: NVDA)")
        
    elif "نتائج العقود" in text:
        open_trades = sum(1 for t in trades_store.values() if t['status'] == "OPEN")
        summary = f"💰 ملخص اليوم:\n- الصفقات المنفذة: {daily_tracker['sent_count']}/{MAX_SIGNALS_PER_DAY}\n- الصفقات المفتوحة حالياً: {open_trades}"
        send_telegram(summary)

    elif "تقرير" in text:
        send_telegram("📋 جاري إعداد التقرير التفصيلي وإرساله لك...")
        # هنا يمكن إضافة دالة لجلب تفاصيل الربح والخسارة PnL

    elif len(text) <= 5 and text.isalpha(): # إذا أرسلت رمز سهم
        analysis_res = get_tv_analysis(text)
        send_telegram(analysis_res)

    return {"ok": True}

# ==========================================
# 4. دوال تنفيذ الصفقات (نفس منطقك السابق)
# ==========================================
def roundx(value: float) -> float: return round(float(value), ROUND_TO)
def safe_float(value, default=0.0) -> float:
    try: return float(value) if value not in [None, ""] else default
    except: return default

def is_friday_ny() -> bool:
    ny = ZoneInfo("America/New_York")
    return datetime.now(ny).weekday() == 4

def send_telegram(message: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})

def get_option_snapshot(symbol):
    try:
        url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/options/tickers/{symbol.replace('O:','') }?apiKey={API_KEY}"
        res = requests.get(url, timeout=10).json()
        ticker_data = res.get("ticker", {})
        last_quote = ticker_data.get("lastQuote", {})
        return {"ask": safe_float(last_quote.get("a")), "bid": safe_float(last_quote.get("b"))}
    except: return {"ask": 0, "bid": 0}

def pick_best_contract(ticker, direction, price):
    try:
        is_friday = is_friday_ny()
        url = "https://api.polygon.io/v3/reference/options/contracts"
        params = {"underlying_ticker": ticker.upper(), "contract_type": direction.lower(), "limit": 15, "apiKey": API_KEY, "expired": "false"}
        res = requests.get(url, params=params, timeout=10).json()
        contracts = res.get("results", [])
        
        candidates = []
        for c in contracts:
            strike = safe_float(c.get("strike_price"))
            if abs(strike - price) / price > (MAX_STRIKE_DISTANCE_PCT / 100): continue
            snap = get_option_snapshot(c.get("ticker"))
            ask = snap['ask']
            if ask <= 0: continue
            if is_friday and ask > ZERO_HERO_MAX_ASK: continue
            if not is_friday and ask > DEFAULT_CONTRACT_BUDGET: continue
            
            spread_pct = ((ask - snap['bid']) / ask) * 100 if ask > 0 else 100
            if spread_pct > MAX_SPREAD_PCT: continue
            
            candidates.append({
                "contract": c.get("ticker"), "strike": strike, "expiry": c.get("expiration_date"),
                "ask": ask, "bid": snap['bid'], "spread_pct": roundx(spread_pct)
            })
            
        if not candidates: return None
        candidates.sort(key=lambda x: abs(x['strike'] - price))
        return candidates[0]
    except: return None

@app.post("/webhook")
async def webhook(request: Request):
    # (نفس منطق استقبال الإشارات السابق بدون تغيير لضمان الاستقرار)
    try:
        data = await request.json()
        if str(data.get("secret")) != SECRET_KEY: return JSONResponse({"status": "unauthorized"}, 401)
        
        ticker = str(data.get("ticker")).upper()
        raw_signal = str(data.get("signal")).upper()
        signal = "CALL" if any(word in raw_signal for word in ["LONG", "BUY", "CALL"]) else "PUT"

        price = safe_float(data.get("price"))
        score = safe_float(data.get("signal_confidence"), 65)

        if score < MIN_SCORE_TO_SEND: return {"status": "low score"}

        best = pick_best_contract(ticker, signal, price)
        if not best: return {"status": "no liquidity"}

        # حساب المستويات والإرسال
        is_friday = is_friday_ny()
        alert = f"🚨 تنبيه جديد: {ticker}\nالنوع: {signal}\nالعقد: {best['contract']}\nالسعر: {best['ask']}"
        send_telegram(alert)
        
        return {"status": "success"}
    except Exception as e: return {"error": str(e)}

@app.on_event("startup")
def startup():
    # ملاحظة: لإرسال الأوامر للبوت، يجب تفعيل Webhook من تيليجرام أولاً لمرة واحدة
    # عبر الرابط: https://api.telegram.org/bot<TOKEN>/setWebhook?url=<YOUR_RENDER_URL>/telegram_webhook
    pass

@app.get("/")
def home(): return {"status": "Bot is Online and Tacting"}
