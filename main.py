from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo

app = FastAPI()

# ==========================================
# 1. الإعدادات (تأكد من صحة البيانات هنا)
# ==========================================
API_KEY = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2"
TELEGRAM_TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055"
SECRET_KEY = "12345"

# القيود والفلترة
MIN_SCORE_TO_SEND = 60         
MAX_SIGNALS_PER_DAY = 5        
DUPLICATE_WINDOW_SEC = 10800   

# إعدادات العقود
DEFAULT_CONTRACT_BUDGET = 3.0
MAX_SPREAD_PCT = 40.0          
MAX_STRIKE_DISTANCE_PCT = 5.0  

# إعدادات الجمعة (Zero Hero)
ZERO_HERO_MAX_ASK = 1.50

# المتابعة
MONITOR_INTERVAL_SEC = 60
ROUND_TO = 2

# ==========================================
# 2. الذاكرة الداخلية
# ==========================================
trades_store: Dict[str, Dict[str, Any]] = {}
daily_tracker = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "sent_count": 0,
    "tickers": []
}

# ==========================================
# 3. الأدوات المساعدة
# ==========================================
def roundx(value: float) -> float: return round(float(value), ROUND_TO)
def safe_float(value, default=0.0) -> float:
    try: return float(value) if value not in [None, ""] else default
    except: return default

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
# 4. جلب بيانات العقود (Polygon)
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
        params = {"underlying_ticker": ticker.upper(), "contract_type": direction.lower(), "limit": 15, "apiKey": API_KEY, "expired": "false"}
        res = requests.get(url, params=params, timeout=10).json()
        contracts = res.get("results", [])
        
        candidates = []
        for c in contracts:
            strike = safe_float(c.get("strike_price"))
            if abs(strike - price) / price > (MAX_STRIKE_DISTANCE_PCT / 100): continue
            
            snap = get_option_snapshot(c.get("ticker"))
            ask, bid = snap['ask'], snap['bid']
            if ask <= 0: continue
            
            if is_friday and ask > ZERO_HERO_MAX_ASK: continue
            if not is_friday and ask > DEFAULT_CONTRACT_BUDGET: continue
            
            spread_pct = ((ask - bid) / ask) * 100 if ask > 0 else 100
            if spread_pct > MAX_SPREAD_PCT: continue
            
            candidates.append({
                "contract": c.get("ticker"), "strike": strike, "expiry": c.get("expiration_date"),
                "ask": ask, "bid": bid, "spread_pct": roundx(spread_pct)
            })
            
        if not candidates: return None
        candidates.sort(key=lambda x: abs(x['strike'] - price))
        return candidates[0]
    except: return None

# ==========================================
# 5. الـ Webhook الرئيسي (مع المترجم الذكي)
# ==========================================
@app.post("/webhook")
async def webhook(request: Request):
    reset_daily_tracker()
    try:
        data = await request.json()
        if str(data.get("secret")) != SECRET_KEY: return JSONResponse({"status": "unauthorized"}, 401)
        
        ticker = str(data.get("ticker")).upper()
        
        # --- بداية المترجم الذكي ---
        raw_signal = str(data.get("signal")).upper()
        if any(word in raw_signal for word in ["LONG", "BUY", "CALL"]):
            signal = "CALL"
        elif any(word in raw_signal for word in ["SHORT", "SELL", "PUT"]):
            signal = "PUT"
        else:
            return {"status": "ignored signal type"}
        # --- نهاية المترجم الذكي ---

        price = safe_float(data.get("price"))
        score = safe_float(data.get("signal_confidence"), 65)

        if daily_tracker["sent_count"] >= MAX_SIGNALS_PER_DAY: return {"status": "limit reached"}
        if score < MIN_SCORE_TO_SEND: return {"status": "low score"}
        if ticker in daily_tracker["tickers"]: return {"status": "duplicate ticker"}

        best = pick_best_contract(ticker, signal, price)
        if not best:
            send_telegram(f"⚠️ إشارة سهم: {ticker}\nالاتجاه: {signal}\nالسعر: {price}\n(لم يعثر على عقد سيولة)")
            return {"status": "stock only sent"}

        # حساب المستويات
        mult = 1.2 if score >= 80 else 1.15
        levels = {
            "tp1": roundx(best['ask'] * mult),
            "tp2": roundx(best['ask'] * (mult + 0.25)),
            "tp3": roundx(best['ask'] * (mult + 0.60)),
            "stop": roundx(best['ask'] * 0.75)
        }
        
        is_friday = is_friday_ny()
        mode = "💣 ZERO HERO" if is_friday else "🎯 SNIPER"
        direction = "🟢 CALL" if signal == "CALL" else "🔴 PUT"
        
        # تعديل الوقف ليوم الجمعة (Zero Hero)
        stop_line = f"🛑 الوقف: {levels['stop']}" if not is_friday else "⚠️ المخاطرة: عالية (عقد انتهاء بدون وقف)"

        alert = f"""🚨 {mode} Alert
📈 السهم: {ticker} | {direction}
💰 سعر السهم: {price}
📊 قوة الإشارة: {score}%

📄 العقد: {best['contract']}
📅 الانتهاء: {"اليوم (جمعة)" if is_friday else best['expiry']}
🎯 السترايك: {best['strike']}
💵 دخول (Ask): {best['ask']}
↔️ السبريد: {best['spread_pct']}%

🎯 الأهداف:
🥇 {levels['tp1']} | 🥈 {levels['tp2']} | 🥉 {levels['tp3']}
{stop_line}

📢 @Option_Strike01"""

        send_telegram(alert)
        
        trade_id = f"{ticker}_{int(time.time())}"
        trades_store[trade_id] = {
            "ticker": ticker, "contract": best['contract'], "entry": best['ask'],
            "levels": levels, "status": "OPEN", "hits": [], "is_zero_hero": is_friday
        }
        
        daily_tracker["sent_count"] += 1
        daily_tracker["tickers"].append(ticker)
        return {"sent": True}

    except Exception as e: return JSONResponse({"error": str(e)}, 500)

# ==========================================
# 6. المتابعة (بدون إغلاق في الزيرو هيرو)
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
                # تحديث الأهداف
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
                
                # فحص الوقف (فقط للأيام العادية وليس للزيرو هيرو)
                if not trade.get("is_zero_hero") and cur_price <= lv['stop']:
                    send_telegram(f"🛑 {trade['ticker']} | ضرب الوقف عند: {cur_price}")
                    trade['status'] = "CLOSED_STOP"
                    
        except: pass
        time.sleep(MONITOR_INTERVAL_SEC)

@app.on_event("startup")
def startup():
    threading.Thread(target=monitor_loop, daemon=True).start()

@app.get("/")
def home(): return {"status": "Live", "signals_today": daily_tracker["sent_count"]}
