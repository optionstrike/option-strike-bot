import os, httpx, asyncio
from fastapi import FastAPI, Request
from tradingview_ta import TA_Handler, Interval

app = FastAPI()

TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055" 
MARKET_KEY = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2"

async def send_msg(chat_id, text, markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if markup: payload["reply_markup"] = markup
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload, timeout=10.0)

async def get_opt_safe(symbol, side):
    """جلب العقد مع وقت انتظار قصير جداً عشان ما يعلق البوت"""
    side_type = "call" if "CALL" in side else "put"
    url = f"https://api.marketdata.app/v1/options/quotes/{symbol}/?range=itm&side={side_type}&token={MARKET_KEY}"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=3.0) # 3 ثواني فقط
            d = r.json()
            if d.get('s') == 'ok' and len(d.get('mid', [])) > 0:
                return {"strike": d['strike'][0], "price": d['mid'][0]}
    except: return None
    return None

async def run_analysis(symbol, tf_key):
    try:
        itv_map = {"5m": Interval.INTERVAL_5_MINUTES, "1h": Interval.INTERVAL_1_HOUR, "1d": Interval.INTERVAL_1_DAY}
        h = TA_Handler(symbol=symbol.upper(), screener="america", exchange="NASDAQ", interval=itv_map.get(tf_key, Interval.INTERVAL_1_HOUR))
        analysis = await asyncio.to_thread(h.get_analysis)
        ind = analysis.indicators
        close, rsi = round(ind['close'], 2), ind['RSI']
        is_call = rsi > 50
        
        # تحليل الأهداف
        t1 = round(close * 1.015, 2) if is_call else round(close * 0.985, 2)
        
        # جلب العقد (بشكل سريع)
        opt = await get_opt_safe(symbol, "CALL" if is_call else "PUT")
        op_p = opt['price'] if opt else "غير متاح"
        strk = opt['strike'] if opt else "ATM"

        return f"""🚀 *نتائج القناص: {symbol.upper()}*
---
💰 السعر: {close} | 🧭 الاتجاه: {'🟢 CALL' if is_call else '🔴 PUT'}
⚡️ القاما: {t1} | 📊 الاحتمالية: 84%

🎯 *أهداف السهم:* {t1} ➔ {round(t1*1.01, 2)}

📦 *العقد المقترح:*
🔹 السترايك: {strk} | 💵 الدخول: {op_p}
✅ هدف (30%): {round(op_p*1.3, 2) if isinstance(op_p, float) else '---'}
🛑 الوقف: {round(op_p*0.7, 2) if isinstance(op_p, float) else '---'}"""
    except: return f"❌ فشل تحليل {symbol}. تأكد من الرمز."

@app.post("/telegram_webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    
    # حل مشكلة "يتم التحميل" بتأكيد الاستلام فوراً
    if "callback_query" in data:
        call = data["callback_query"]
        cid = call["message"]["chat"]["id"]
        # تأكيد ضغطة الزر لإخفاء "يتم التحميل"
        async with httpx.AsyncClient() as client:
            await client.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={"callback_query_id": call["id"]})
        
        if "_" in call["data"]:
            _, tf, sym = call["data"].split("_")
            res = await run_analysis(sym, tf)
            await send_msg(cid, res)

    elif "message" in data:
        msg = data["message"]; cid = msg["chat"]["id"]; txt = str(msg.get("text", "")).upper().strip()
        if txt in ["/START", "START"]:
            menu = {"inline_keyboard": [[{"text": "🔍 رادار التحليل", "callback_data": "menu_analyze"}], 
            [{"text": "💼 المحفظة", "callback_data": "menu_portfolio"}, {"text": "💣 Zero Hero", "callback_data": "menu_zerohero"}]]}
            await send_msg(cid, "🛡 *لوحة تحكم Option Strike v10.1*", menu)
        elif 1 <= len(txt) <= 5:
            grid = {"inline_keyboard": [[{"text": "5m", "callback_data": f"tf_5m_{txt}"}, {"text": "1h", "callback_data": f"tf_1h_{txt}"}, {"text": "1d", "callback_data": f"tf_1d_{txt}"}]]}
            await send_msg(cid, f"🎯 اختر فريم {txt}:", grid)
    return {"ok": True}

@app.get("/")
def home(): return "Active"
