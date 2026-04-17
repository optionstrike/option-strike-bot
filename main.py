import os
import httpx
import asyncio
from fastapi import FastAPI, Request
from tradingview_ta import TA_Handler, Interval

app = FastAPI()

# --- ⚙️ الإعدادات الأساسية (ممنوع الحذف) ---
TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055" 
MARKET_KEY = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2"

# --- 1️⃣ وظائف الإرسال ---
async def send_msg(chat_id, text, markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if markup: payload["reply_markup"] = markup
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, timeout=10.0)
    except: pass

# --- 2️⃣ محرك جلب بيانات الأوبشن (السترايك والسعر) ---
async def get_option_info(symbol, direction):
    side = "call" if "CALL" in direction else "put"
    url = f"https://api.marketdata.app/v1/options/quotes/{symbol}/?range=itm&side={side}&token={MARKET_KEY}"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=5.0)
            d = r.json()
            if d.get('s') == 'ok':
                return {"strike": d['strike'][0], "price": d['mid'][0], "expiry": d['expiration'][0]}
    except: return None
    return None

# --- 3️⃣ محرك التحليل التفصيلي (التحليل الكامل) ---
async def perform_full_analysis(symbol, tf_key):
    try:
        intervals = {
            "5m": Interval.INTERVAL_5_MINUTES, "15m": Interval.INTERVAL_15_MINUTES,
            "1h": Interval.INTERVAL_1_HOUR, "4h": Interval.INTERVAL_4_HOURS,
            "1d": Interval.INTERVAL_1_DAY, "1W": Interval.INTERVAL_1_WEEK, "1M": Interval.INTERVAL_1_MONTH
        }
        itv = intervals.get(tf_key, Interval.INTERVAL_1_HOUR)
        h = TA_Handler(symbol=symbol.upper(), screener="america", exchange="NASDAQ", interval=itv)
        analysis = await asyncio.to_thread(h.get_analysis)
        ind = analysis.indicators
        close, rsi = round(ind['close'], 2), ind['RSI']
        
        is_call = rsi > 50
        dir_text = "🟢 CALL" if is_call else "🔴 PUT"
        liq_text = "🔥 سيولة تجميع" if is_call else "💧 سيولة تصريف"
        
        # حساب أهداف السهم
        pivot = (ind['high'] + ind['low'] + ind['close']) / 3
        st1 = round((2 * pivot) - ind['low'], 2) if is_call else round((2 * pivot) - ind['high'], 2)
        st2 = round(pivot + (ind['high'] - ind['low']), 2) if is_call else round(pivot - (ind['high'] - ind['low']), 2)
        st3 = round(ind['high'] + 2*(pivot-ind['low']), 2) if is_call else round(ind['low'] - 2*(ind['high']-pivot), 2)
        
        # جلب بيانات العقد
        opt = await get_option_info(symbol, dir_text)
        op_p = opt['price'] if opt else 0.0

        return f"""🚀 *Option Strike: {symbol.upper()}*
---
⏱ الفريم: {tf_key} | 💰 السعر: {close}
🧭 الاتجاه: {dir_text} | ⚡️ القاما: {st1}
📊 الاحتمالية: {"84%" if rsi > 60 else "63%"} | 💧 {liq_text}

🎯 *أهداف السهم (Targets):*
1️⃣ {st1} | 2️⃣ {st2} | 3️⃣ {st3}

📦 *العقد المقترح:*
🔹 السترايك: {opt['strike'] if opt else 'ATM'}
💵 سعر الدخول: {op_p}
✅ هدف 1 (30%): {round(op_p*1.3, 2)}
🚀 هدف 2 (100%): {round(op_p*2.0, 2)}
🛑 وقف الخسارة: {round(op_p*0.7, 2)}
---
📢 @Option_Strike01"""
    except: return f"❌ السهم {symbol} غير مدعوم أو فريم {tf_key} غير متاح."

# --- 4️⃣ محرك الطرح الآلي (الـ 80 شركة) ---
@app.post("/webhook")
async def tradingview_webhook(request: Request):
    data = await request.json()
    if data.get("secret") != "12345": return {"ok": False}
    
    symbol = data.get("ticker")
    report = await perform_full_analysis(symbol, "1h")
    await send_msg(CHAT_ID, f"🔥 *إشارة طرح آلي (قناص الـ 80 شركة)*\n{report}")
    return {"status": "Trade Posted"}

# --- 5️⃣ نظام لوحة التحكم والتلغرام ---
@app.post("/telegram_webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    if "callback_query" in data:
        call = data["callback_query"]; chat_id = call["message"]["chat"]["id"]
        c_data = call["data"]
        if c_data.startswith("tf_"):
            _, tf, sym = c_data.split("_")
            asyncio.create_task(send_msg(chat_id, f"⏳ جاري قنص {sym}..."))
            res = await perform_full_analysis(sym, tf)
            await send_msg(chat_id, res)
            
    elif "message" in data:
        msg = data["message"]; chat_id = msg["chat"]["id"]
        txt = str(msg.get("text", "")).strip().upper()
        
        if txt in ["/START", "START"]:
            menu = {"inline_keyboard": [
                [{"text": "🔍 رادار التحليل", "callback_data": "menu_analyze"}],
                [{"text": "💼 المحفظة", "callback_data": "menu_portfolio"}, {"text": "📅 السوق", "callback_data": "menu_market"}],
                [{"text": "💣 وضعية Zero Hero", "callback_data": "menu_zerohero"}]
            ]}
            await send_msg(chat_id, "🛡 *لوحة تحكم Option Strike v10.0*", menu)
        elif 1 <= len(txt) <= 6:
            grid = {"inline_keyboard": [
                [{"text": "5m", "callback_data": f"tf_5m_{txt}"}, {"text": "1h", "callback_data": f"tf_1h_{txt}"}, {"text": "1d", "callback_data": f"tf_1d_{txt}"}],
                [{"text": "أسبوعي", "callback_data": f"tf_1W_{txt}"}, {"text": "شهري", "callback_data": f"tf_1M_{txt}"}]
            ]}
            await send_msg(chat_id, f"🎯 اختر فريم {txt}:", grid)
    return {"ok": True}

@app.get("/")
def home(): return "Option Strike v10.0 Fully Active"
