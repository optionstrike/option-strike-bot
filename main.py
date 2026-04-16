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

# ==========================================
# 1. الإعدادات الأساسية (تم تعديل القيود هنا)
# ==========================================
API_KEY = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2"
TELEGRAM_TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055"
SECRET_KEY = "12345"

REPORT_FILE = "trades_report.csv"

# القيود المطلوبة
MIN_SCORE_TO_SEND = 60         # القوة المطلوبة 60%
MAX_SIGNALS_PER_DAY = 5        # حد الـ 5 عقود يومياً
DUPLICATE_WINDOW_SEC = 10800   # منع تكرار نفس السهم لـ 3 ساعات

# إعدادات الميزانية والعقود
DEFAULT_CONTRACT_BUDGET = 3.0
MAX_SPREAD_PCT = 40.0          # سبريد مرن لضمان التنفيذ
MAX_STRIKE_DISTANCE_PCT = 5.0  # مسافة سترايك مرنة

# إعدادات الجمعة (Zero Hero)
ZERO_HERO_MAX_ASK = 1.50
NON_FRIDAY_MIN_ASK = 0.50

# المتابعة
MONITOR_INTERVAL_SEC = 60
ROUND_TO = 2

# ==========================================
# 2. الذاكرة الداخلية والإحصائيات
# ==========================================
last_signal_message: Optional[str] = None
last_signals: Dict[str, Dict[str, Any]] = {}
trades_store: Dict[str, Dict[str, Any]] = {}
daily_tracker = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "sent_count": 0,
    "tickers": []
}

# ==========================================
# 3. الأدوات المساعدة (Utility)
# ==========================================
def roundx(value: float) -> float: return round(float(value), ROUND_TO)
def safe_float(value, default=0.0) -> float:
    try: return float(value) if value not in [None, ""] else default
    except: return default

def now_str() -> str: return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def is_friday_ny() -> bool:
    ny = ZoneInfo("America/New_York")
    return datetime.now(ny).weekday() == 4

def send_telegram(message: str) -> None:
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=15)
    except Exception as e: print(f"Telegram Error: {e}")

def reset_daily_tracker():
    today = datetime.now().strftime("%Y-%m-%d")
    if daily_tracker["date"] != today:
        daily_tracker["date"] = today
        daily_tracker["sent_count"] = 0
        daily_tracker["tickers"] = []

# ==========================================
# 4. جلب العقود وسعر السوق (Polygon API)
# ==========================================
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
        params = {"underlying_ticker": ticker.upper(), "contract_type": direction.lower(), "limit": 20, "apiKey": API_KEY, "expired": "false"}
        res = requests.get(url, params=params, timeout=10).json()
        contracts = res.get("results", [])
        
        candidates = []
        for c in contracts:
            strike = safe_float(c.get("strike_price"))
            if abs(strike - price) / price > (MAX_STRIKE_DISTANCE_PCT / 100): continue
            
            snap = get_option_snapshot(c.get("ticker"))
            ask, bid = snap['ask'], snap['bid']
            if ask <= 0: continue
            
            # فلتر السعر (الجمعة ضد الأيام العادية)
            if is_friday and ask > ZERO_HERO_MAX_ASK: continue
            if not is_friday and ask > DEFAULT_CONTRACT_BUDGET: continue
            
            spread_pct = ((ask - bid) / ask) * 100 if ask > 0 else 100
            if spread_pct > MAX_SPREAD_PCT: continue
            
            candidates.append({
                "contract": c.get("ticker"), "strike": strike, "expiry": c.get("expiration_date"),
                "ask": ask, "bid": bid, "spread_pct": roundx(spread_pct)
            })
            
        if not candidates: return None
        # اختيار العقد الأقرب للسترايك الحالي
        candidates.sort(key=lambda x: abs(x['strike'] - price))
        return candidates[0]
    except: return None

# ==========================================
# 5. منطق الأهداف (Targets)
# ==========================================
def compute_levels(entry_price, score):
    # إذا كانت الإشارة قوية جداً نوسع الأهداف
    mult = 1.2 if score >= 80 else 1.15
    return {
        "tp1": roundx(entry_price * mult),
        "tp2": roundx(entry_price * (mult + 0.2)),
        "tp3": roundx(entry_price * (mult + 0.5)),
        "stop": roundx(entry_price * 0.75) # وقف عند خسارة 25%
    }

# ==========================================
# 6. الـ Webhook الرئيسي
# ==========================================
@app.post("/webhook")
async def webhook(request: Request):
    global last_signal_message
    reset_daily_tracker()
    
    try:
        data = await request.json()
        if str(data.get("secret")) != SECRET_KEY: return JSONResponse({"status": "unauthorized"}, 401)
        
        ticker = str(data.get("ticker")).upper()
        signal = str(data.get("signal")).upper()
        price = safe_float(data.get("price"))
        score = safe_float(data.get("signal_confidence"), 65) # سكور افتراضي إذا لم يرسل

        # الفلاتر الأساسية (العدد والسكور)
        if daily_tracker["sent_count"] >= MAX_SIGNALS_PER_DAY: return {"status": "daily limit reached"}
        if score < MIN_SCORE_TO_SEND: return {"status": "low score"}
        if ticker in daily_tracker["tickers"]: return {"status": "ticker already sent"}

        # البحث عن عقد
        best = pick_best_contract(ticker, signal, price)
        if not best:
            # إرسال تنبيه سهم فقط لعدم ضياع الفرصة
            msg = f"⚠️ إشارة سهم: {ticker}\nالاتجاه: {signal}\nالسعر: {price}\n(لم يعثر البوت على عقد سيولة حالياً)"
            send_telegram(msg)
            return {"status": "sent stock alert only"}

        # حساب الأهداف
        levels = compute_levels(best['ask'], score)
        
        # إرسال الرسالة للتلجرام
        mode = "💣 ZERO HERO" if is_friday_ny() else "🎯 SNIPER"
        direction = "🟢 CALL" if signal == "CALL" else "🔴 PUT"
        
        alert = f"""🚨 {mode} Alert
📈 السهم: {ticker} | {direction}
💰 سعر السهم: {price}
📊 قوة الإشارة: {score}%

📄 العقد: {best['contract']}
📅 الانتهاء: {best['expiry']}
🎯 السترايك: {best['strike']}
💵 دخول (Ask): {best['ask']}
↔️ السبريد: {best['spread_pct']}%

🎯 الأهداف:
🥇 {levels['tp1']} | 🥈 {levels['tp2']} | 🥉 {levels['tp3']}
🛑 الوقف: {levels['stop']}

📢 @Option_Strike01"""

        send_telegram(alert)
        last_signal_message = alert
        
        # حفظ الصفقة للمتابعة
        trade_id = f"{ticker}_{int(time.time())}"
        trades_store[trade_id] = {
            "ticker": ticker, "contract": best['contract'], "entry": best['ask'],
            "levels": levels, "status": "OPEN", "hits": []
        }
        
        daily_tracker["sent_count"] += 1
        daily_tracker["tickers"].append(ticker)
        
        return {"status": "success", "sent": True}

    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

# ==========================================
# 7. المتابعة الآلية (Monitor)
# ==========================================
def monitor_loop():
    while True:
        try:
            for tid, trade in list(trades_store.items()):
                if trade['status'] != "OPEN": continue
                
                snap = get_option_snapshot(trade['contract'])
                cur_price = snap['ask'] if snap['ask'] > 0 else snap['bid']
                if cur_price <= 0: continue
                
                lv = trade['levels']
                # فحص الأهداف
                if cur_price >= lv['tp3'] and "tp3" not in trade['hits']:
                    send_telegram(f"🏆 {trade['ticker']} | هدف ثالث محقق: {cur_price}")
                    trade['hits'].append("tp3")
                    trade['status'] = "CLOSED_PROFIT"
                elif cur_price >= lv['tp2'] and "tp2" not in trade['hits']:
                    send_telegram(f"🚀 {trade['ticker']} | هدف ثاني محقق: {cur_price}")
                    trade['hits'].append("tp2")
                elif cur_price >= lv['tp1'] and "tp1" not in trade['hits']:
                    send_telegram(f"🎯 {trade['ticker']} | هدف أول محقق: {cur_price}")
                    trade['hits'].append("tp1")
                
                # فحص الوقف
                if cur_price <= lv['stop']:
                    send_telegram(f"🛑 {trade['ticker']} | ضرب الوقف عند: {cur_price}")
                    trade['status'] = "CLOSED_STOP"
                    
        except: pass
        time.sleep(MONITOR_INTERVAL_SEC)

@app.on_event("startup")
def startup():
    threading.Thread(target=monitor_loop, daemon=True).start()

@app.get("/")
def home(): return {"status": "Option Strike Bot Active", "daily_count": daily_tracker["sent_count"]}
