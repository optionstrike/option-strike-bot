import os
import httpx
import asyncio
from fastapi import FastAPI, Request
from tradingview_ta import TA_Handler, Interval

app = FastAPI()

# --- الإعدادات ---
TELEGRAM_TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055" 
MARKETDATA_KEY = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2"

async def send_async_msg(chat_id, text, markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if markup: payload["reply_markup"] = markup
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload)
    except Exception as e: print(f"Telegram Error: {e}")

async def get_option_data(symbol, side):
    side_type = "call" if "CALL" in side else "put"
    url = f"https://api.marketdata.app/v1/options/quotes/{symbol}/?range=itm&side={side_type}&token={MARKETDATA_KEY}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10.0)
            data = resp.json()
            if data.get('s') == 'ok' and len(data.get('mid', [])) > 0:
                return {"strike": data['strike'][0], "price": data['mid'][0], "expiry": data['expiration'][0]}
    except: return None
    return None

async def get_ultimate_analysis(symbol: str, tf_key: str):
    try:
        # تصحيح دقيق للفريمات
        intervals = {
            "5m": Interval.INTERVAL_5_MINUTES, "15m": Interval.INTERVAL_15_MINUTES,
            "1h": Interval.INTERVAL_1_HOUR, "4h": Interval.INTERVAL_4_HOURS,
            "1d": Interval.INTERVAL_1_DAY, "1W": Interval.INTERVAL_1_WEEK, "1M": Interval.INTERVAL_1_MONTH
        }
        interval = intervals.get(tf_key, Interval.INTERVAL_1_HOUR)
        
        h = TA_Handler(symbol=symbol.upper(), screener="america", exchange="NASDAQ", interval=interval)
        analysis = await asyncio.to_thread(h.get_analysis)
        
        ind = analysis.indicators
        close, rsi = round(ind['close'], 2), ind['RSI']
        is_call = rsi > 50

        pivot = (ind['high'] + ind['low'] + ind['close']) / 3
        st1 = round((2 * pivot) - ind['low'], 2) if is_call else round((2 * pivot) - ind['high'], 2)
        st2 = round(pivot + (ind['high'] - ind['low']), 2) if is_call else round(pivot - (ind['high'] - ind['low']), 2)
        
        opt = await get_option_data(symbol, "CALL" if is_call else "PUT")
        op_p = opt['price'] if opt else 0.0

        return f"""🚀 رادار Option Strike: {symbol.upper()}
---
⏱ الفريم: {tf_key} | 💰 السعر: {close}
🧭 الاتجاه: {"🟢 CALL" if is_call else "🔴 PUT"}
⚡️ القاما: {st1}

🎯 أهداف السهم: {st1} ➔ {st2}

📦 السترايك: {opt['strike'] if opt else 'ATM'}
💵 دخول العقد: {op_p}
✅ هدف 1: {round(op_p*1.3, 2)}
🚀 هدف 2: {round(op_p*2.0, 2)}
🛑 الوقف: {round(op_p*0.7, 2)}
---
📢 @Option_Strike01"""
    except Exception as e: return f"❌ خطأ: {symbol} غير متاح حالياً."

@app.post("/telegram_webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    if "callback_query" in data:
        call = data["callback_query"]; chat_id = call["message"]["chat"]["id"]; c_data = call["data"]
        if c_data.startswith("tf_"):
            _, tf, sym = c_data.split("_")
            asyncio.create_task(send_async_msg(chat_id, f"⏳ جاري تحليل {sym}..."))
            res = await get_ultimate_analysis(sym, tf)
            await send_async_msg(chat_id, res)
    elif "message" in data:
        msg = data["message"]; chat_id = msg["chat"]["id"]; txt = str(msg.get("text", "")).strip().upper()
        if txt in ["/START", "START"]:
            menu = {"inline_keyboard": [[{"text": "🔍 رادار التحليل", "callback_data": "menu_analyze"}]]}
            await send_async_msg(chat_id, "🛡 لوحة التحكم v8.5", menu)
        elif 1 <= len(txt) <= 6:
            grid = {"inline_keyboard": [[{"text": "5m", "callback_data": f"tf_5m_{txt}"}, {"text": "1h", "callback_data": f"tf_1h_{txt}"}, {"text": "1d", "callback_data": f"tf_1d_{txt}"}]]}
            await send_async_msg(chat_id, f"🎯 اختر فريم {txt}:", grid)
    return {"ok": True}

@app.get("/")
async def home(): return {"status": "V8.5 Online"}
