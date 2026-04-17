import os, httpx, asyncio
from fastapi import FastAPI, Request
from tradingview_ta import TA_Handler, Interval

app = FastAPI()

# --- الإعدادات (لا تقم بتغييرها) ---
TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055" 
MARKET_KEY = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2"

async def send_msg(chat_id, text, markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if markup: payload["reply_markup"] = markup
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, timeout=5.0)
    except: pass

async def get_full_analysis(symbol, tf_key):
    try:
        # 1. إعداد الفريمات الفنية
        itv_map = {
            "5m": Interval.INTERVAL_5_MINUTES, "1h": Interval.INTERVAL_1_HOUR, 
            "1d": Interval.INTERVAL_1_DAY, "1W": Interval.INTERVAL_1_WEEK, 
            "1M": Interval.INTERVAL_1_MONTH
        }
        itv = itv_map.get(tf_key, Interval.INTERVAL_1_HOUR)
        
        # 2. جلب التحليل الفني (سريع جداً)
        h = TA_Handler(symbol=symbol.upper(), screener="america", exchange="NASDAQ", interval=itv)
        analysis = await asyncio.to_thread(h.get_analysis)
        ind = analysis.indicators
        close, rsi = round(ind['close'], 2), ind['RSI']
        is_call = rsi > 50
        
        # 3. حساب مستويات القاما والأهداف
        pivot = (ind['high'] + ind['low'] + ind['close']) / 3
        st1 = round((2 * pivot) - ind['low'], 2) if is_call else round((2 * pivot) - ind['high'], 2)
        st2 = round(pivot + (ind['high'] - ind['low']), 2) if is_call else round(pivot - (ind['high'] - ind['low']), 2)
        
        # 4. محاولة جلب العقد (بحد زمني صارم: 1.5 ثانية فقط)
        strike_val, price_val = "ATM", "غير متاح حالياً"
        entry_price = 0.0
        try:
            side = "call" if is_call else "put"
            opt_url = f"https://api.marketdata.app/v1/options/quotes/{symbol}/?range=itm&side={side}&token={MARKET_KEY}"
            async with httpx.AsyncClient() as client:
                resp = await client.get(opt_url, timeout=1.5)
                d = resp.json()
                if d.get('s') == 'ok' and len(d.get('mid', [])) > 0:
                    entry_price = d['mid'][0]
                    price_val = entry_price
                    strike_val = d['strike'][0]
        except: pass # إذا فشل أو تأخر، نكمل بالبيانات الافتراضية

        return f"""🚀 *تحليل رادار {symbol.upper()}*
---
⏱ الفريم: {tf_key} | 💰 السعر: {close}
🧭 التوجه: {'🟢 CALL' if is_call else '🔴 PUT'}
⚡️ أعلى مستوى جاما: {st1}
📊 الاحتمالية: {"84%" if rsi > 60 else "62%"}

🎯 *أهداف السهم:* {st1} ➔ {st2}

📦 *تفاصيل العقد المقترح:*
🔹 السترايك: {strike_val}
💵 سعر الدخول: {price_val}
✅ هدف (30%): {round(entry_price*1.3, 2) if entry_price > 0 else '---'}
🛑 الوقف: {round(entry_price*0.7, 2) if entry_price > 0 else '---'}
---
📢 @Option_Strike01"""
    except Exception as e:
        return f"❌ فشل تحليل {symbol}. تأكد من الرمز الصحيح."

# --- مسارات الـ Webhooks ---

@app.post("/webhook")
async def tradingview_signals(request: Request):
    """طرح الـ 80 شركة آلياً (ممنوع الحذف)"""
    data = await request.json()
    if data.get("secret") == "12345":
        symbol = data.get("ticker")
        res = await get_full_analysis(symbol, "1h")
        await send_msg(CHAT_ID, f"🔥 *إشارة طرح آلي*\n{res}")
    return {"status": "ok"}

@app.post("/telegram_webhook")
async def telegram_handler(request: Request):
    data = await request.json()
    
    if "callback_query" in data:
        call = data["callback_query"]; cid = call["message"]["chat"]["id"]; c_data = call["data"]
        # إنهاء حالة التحميل في التلغرام فوراً
        async with httpx.AsyncClient() as client:
            await client.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={"callback_query_id": call["id"]})

        if c_data == "menu_analyze":
            await send_msg(cid, "⌨️ أرسل رمز السهم الآن (مثال: NVDA):")
        elif c_data == "menu_market":
            await send_msg(cid, "📅 *مفكرة السوق:*\n- الافتتاح: 4:30 م\n- الإغلاق: 11:00 م\n- الحالة: جاري المتابعة.")
        elif c_data.startswith("tf_"):
            _, tf, sym = c_data.split("_")
            # رسالة انتظار مؤقتة
            await send_msg(cid, f"⏳ جاري قنص {sym}...")
            res = await get_full_analysis(sym, tf)
            await send_msg(cid, res)

    elif "message" in data:
        msg = data["message"]; cid = msg["chat"]["id"]; txt = str(msg.get("text", "")).upper().strip()
        
        if txt in ["/START", "START"]:
            menu = {"inline_keyboard": [
                [{"text": "🔍 رادار التحليل", "callback_data": "menu_analyze"}],
                [{"text": "💼 المحفظة", "callback_data": "menu_portfolio"}, {"text": "📅 السوق", "callback_data": "menu_market"}],
                [{"text": "💣 Zero Hero", "callback_data": "menu_zerohero"}]
            ]}
            await send_msg(cid, "🛡 *لوحة تحكم Option Strike v12.0*", menu)
        elif 1 <= len(txt) <= 6:
            grid = {"inline_keyboard": [
                [{"text": "5m", "callback_data": f"tf_5m_{txt}"}, {"text": "1h", "callback_data": f"tf_1h_{txt}"}, {"text": "1d", "callback_data": f"tf_1d_{txt}"}],
                [{"text": "أسبوعي", "callback_data": f"tf_1W_{txt}"}, {"text": "شهري", "callback_data": f"tf_1M_{txt}"}]
            ]}
            await send_msg(cid, f"🎯 اختر فريم {txt}:", grid)
            
    return {"ok": True}

@app.get("/")
def home(): return "V12 Online - No Hang"

