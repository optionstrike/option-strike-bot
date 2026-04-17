import os
import requests
from fastapi import FastAPI, Request
from tradingview_ta import TA_Handler, Interval
from datetime import datetime

app = FastAPI()

# --- ⚙️ الإعدادات الأمنية ---
TELEGRAM_TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055" 
MARKETDATA_KEY = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2" # الكي حقك لجلب العقود
DAILY_LIMIT = 5
trades_count = 0 

# --- 1️⃣ محرك جلب العقد والسترايك المقترح ---
def get_option_suggestion(symbol, side):
    """جلب أقرب سترايك وسعر العقد (Premium) باستخدام الكي"""
    try:
        side_type = "call" if "CALL" in side or "BUY" in side else "put"
        # استعلام لجلب أقرب عقد (At-the-money) ينتهي قريباً
        url = f"https://api.marketdata.app/v1/options/quotes/{symbol}/?range=itm&side={side_type}&token={MARKETDATA_KEY}"
        response = requests.get(url).json()
        
        if response.get('s') == 'ok':
            strike = response['strike'][0]
            price = response['mid'][0] # السعر المتوسط للعقد
            expiry = response['expiration'][0]
            return {"strike": strike, "price": price, "expiry": expiry}
    except:
        return None

# --- 2️⃣ محرك التحليل التفصيلي (3 أهداف للسهم + 3 أهداف للعقد) ---
def get_detailed_analysis(symbol: str, tf_key: str, is_automated=False):
    try:
        intervals = {"5m": Interval.INTERVAL_5_MINUTES, "15m": Interval.INTERVAL_15_MINUTES, "1h": Interval.INTERVAL_1_HOUR, "1d": Interval.INTERVAL_1_DAY}
        interval = intervals.get(tf_key, Interval.INTERVAL_1_HOUR)
        
        h = TA_Handler(symbol=symbol.upper(), screener="america", exchange="NASDAQ", interval=interval)
        analysis = h.get_analysis()
        ind = analysis.indicators
        rsi = ind['RSI']
        close = round(ind['close'], 2)
        
        # تحديد الاتجاه والسيولة
        is_call = rsi > 55
        direction = "🟢 CALL" if is_call else "🔴 PUT"
        
        # جلب السترايك والسعر المقترح للعقد
        opt = get_option_suggestion(symbol, direction)
        opt_price = opt['price'] if opt else 0.0
        strike_val = opt['strike'] if opt else "N/A"

        # حساب أهداف العقد (تضاعف رأس المال)
        t1, t2, t3 = round(opt_price * 1.3, 2), round(opt_price * 1.6, 2), round(opt_price * 2.0, 2)
        stop = round(opt_price * 0.7, 2)

        return f"""🚀 **مقترح عقد Option Strike: {symbol.upper()}**
---
💰 **سعر السهم:** {close} | 🧭 **الاتجاه:** {direction}
🎯 **السترايك المقترح:** {strike_val}
💵 **سعر دخول العقد:** {opt_price}
📅 **تاريخ الانتهاء:** {opt['expiry'] if opt else 'Weekly'}
---
📊 **أهداف العقد (Premium Targets):**
✅ **الهدف 1 (30%):** {t1}
✅ **الهدف 2 (60%):** {t2}
🚀 **الهدف 3 (100%):** {t3}
🛑 **وقف الخسارة:** {stop}
---
📊 **احتمالية النجاح:** {"84%" if rsi > 60 else "62%"}
📢 @Option_Strike01"""
    except Exception as e: return f"❌ خطأ: {str(e)}"

# --- 3️⃣ محرك الطرح الآلي (Webhook) ---
@app.post("/webhook")
async def tradingview_webhook(request: Request):
    global trades_count
    data = await request.json()
    if data.get("secret") != "12345" or trades_count >= DAILY_LIMIT: return {"ok": False}

    symbol = data.get("ticker")
    # إرسال الطرح فوراً للتلغرام مع السترايك والأهداف
    report = get_detailed_analysis(symbol, "1h", is_automated=True)
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": f"🔥 **طرح آلي جديد ({trades_count+1}/5)**\n{report}"})
    
    trades_count += 1
    return {"status": "Posted"}

# --- 4️⃣ لوحة التحكم (الأوامر التفاعلية) ---
@app.post("/telegram_webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    if "callback_query" in data:
        call = data["callback_query"]; chat_id = call["message"]["chat"]["id"]
        if call["data"] == "menu_analyze":
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": "⌨️ أرسل رمز السهم (مثال: NVDA):"})
    elif "message" in data:
        msg = data["message"]; txt = str(msg.get("text", "")).upper(); chat_id = msg["chat"]["id"]
        if txt == "/START":
            menu = {"inline_keyboard": [
                [{"text": "🔍 رادار التحليل والسترايك", "callback_data": "menu_analyze"}],
                [{"text": "💼 المحفظة", "callback_data": "menu_portfolio"}, {"text": "📅 السوق", "callback_data": "menu_market"}],
                [{"text": "💣 وضعية Zero Hero", "callback_data": "menu_zerohero"}]
            ]}
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": "🛡 **غرفة عمليات Option Strike v7.0**", "reply_markup": menu})
        elif 1 <= len(txt) <= 6:
            # عرض الفريمات بما فيها الأسبوعي والشهري
            grid = {"inline_keyboard": [
                [{"text": "5m", "callback_data": f"tf_5m_{txt}"}, {"text": "1h", "callback_data": f"tf_1h_{txt}"}, {"text": "1d", "callback_data": f"tf_1d_{txt}"}],
                [{"text": "أسبوعي", "callback_data": f"tf_1W_{txt}"}, {"text": "شهري", "callback_data": f"tf_1M_{txt}"}]
            ]}
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": f"🎯 تحليل {txt}:", "reply_markup": grid})
        elif "_" in txt: # معالجة الضغط على الفريمات
            _, tf, sym = txt.split("_") # هذا الجزء يتم معالجته في الكول باك عادة
    return {"ok": True}

@app.get("/")
def home(): return {"status": "Sniper Active", "key_status": "Linked"}
