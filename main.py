import os, httpx, asyncio
from fastapi import FastAPI, Request
from tradingview_ta import TA_Handler, Interval
from datetime import datetime

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

async def get_pure_analysis(symbol, tf_key):
    try:
        # 1. إعداد الفريمات
        itv_map = {
            "5m": Interval.INTERVAL_5_MINUTES, "1h": Interval.INTERVAL_1_HOUR, 
            "1d": Interval.INTERVAL_1_DAY, "1W": Interval.INTERVAL_1_WEEK, 
            "1M": Interval.INTERVAL_1_MONTH
        }
        itv = itv_map.get(tf_key, Interval.INTERVAL_1_HOUR)
        
        # 2. جلب البيانات الفنية (سريع جداً)
        h = TA_Handler(symbol=symbol.upper(), screener="america", exchange="NASDAQ", interval=itv)
        analysis = await asyncio.to_thread(h.get_analysis)
        ind = analysis.indicators
        
        close = round(ind['close'], 2)
        rsi = ind['RSI']
        is_call = rsi > 50
        
        # 3. حساب مستويات القاما والأهداف
        pivot = (ind['high'] + ind['low'] + ind['close']) / 3
        gamma_level = round((2 * pivot) - ind['low'], 2) if is_call else round((2 * pivot) - ind['high'], 2)
        target_2 = round(pivot + (ind['high'] - ind['low']), 2) if is_call else round(pivot - (ind['high'] - ind['low']), 2)
        
        # 4. حساب الاحتمالية والوقت (معادلات فنية)
        # الاحتمالية تعتمد على قوة RSI والـ MACD
        probability = int(rsi + 20) if is_call else int((100 - rsi) + 20)
        probability = min(94, max(55, probability)) # حصرها بين 55% و 94%
        
        # الوقت المتوقع يعتمد على الفريم
        time_map = {"5m": "15-30 دقيقة", "1h": "2-4 ساعات", "1d": "1-3 أيام", "1W": "1-2 أسبوع", "1M": "شهر+"}
        expected_time = time_map.get(tf_key, "غير محدد")

        return f"""🚀 *رادار التحليل الفني: {symbol.upper()}*
---
⏱ الفريم: {tf_key} | 💰 السعر الحاضر: {close}
🧭 التوجه الأقوى: {'🟢 CALL (شراء)' if is_call else '🔴 PUT (بيع)'}

⚡️ *مستوى القاما (الهدف الأول):* `{gamma_level}`
🎯 *الهدف الثاني (الامتداد):* `{target_2}`

📊 *نسبة الوصول للهدف:* `{probability}%`
⏳ *الوقت المتوقع لتحقيق الهدف:* `{expected_time}`
---
📢 @Option_Strike01"""
    except:
        return f"❌ فشل تحليل {symbol}. تأكد من الرمز الصحيح."

# --- المسارات (ممنوع حذف الـ Webhook الخاص بالـ 80 شركة) ---

@app.post("/webhook")
async def tradingview_signals(request: Request):
    """طرح الـ 80 شركة آلياً (هذا يبقى كما هو شامل العقود لأنك تحتاجه كإشارة آليه)"""
    data = await request.json()
    if data.get("secret") == "12345":
        symbol = data.get("ticker")
        # في الطرح الآلي نستخدم تحليل 1 ساعة
        res = await get_pure_analysis(symbol, "1h")
        await send_msg(CHAT_ID, f"🔥 *إشارة قناص آلي*\n{res}")
    return {"ok": True}

@app.post("/telegram_webhook")
async def telegram_handler(request: Request):
    data = await request.json()
    
    if "callback_query" in data:
        call = data["callback_query"]; cid = call["message"]["chat"]["id"]; c_data = call["data"]
        # تأكيد الاستلام لإلغاء علامة التحميل
        async with httpx.AsyncClient() as client:
            await client.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={"callback_query_id": call["id"]})

        if c_data.startswith("tf_"):
            _, tf, sym = c_data.split("_")
            await send_msg(cid, f"⏳ جاري تحليل {sym} فنيّاً...")
            res = await get_pure_analysis(sym, tf)
            await send_msg(cid, res)
        elif c_data == "menu_analyze":
            await send_msg(cid, "⌨️ أرسل رمز السهم (مثال: TSLA):")
        elif c_data == "menu_market":
            await send_msg(cid, "📅 السوق الأمريكي: 4:30م - 11:00م بتوقيت السعودية.")

    elif "message" in data:
        msg = data["message"]; cid = msg["chat"]["id"]; txt = str(msg.get("text", "")).upper().strip()
        
        if txt in ["/START", "START"]:
            menu = {"inline_keyboard": [
                [{"text": "🔍 رادار التحليل", "callback_data": "menu_analyze"}],
                [{"text": "📅 السوق", "callback_data": "menu_market"}]
            ]}
            await send_msg(cid, "🛡 *لوحة تحكم Option Strike v14.0*", menu)
        elif 1 <= len(txt) <= 6:
            grid = {"inline_keyboard": [
                [{"text": "5m", "callback_data": f"tf_5m_{txt}"}, {"text": "1h", "callback_data": f"tf_1h_{txt}"}, {"text": "1d", "callback_data": f"tf_1d_{txt}"}],
                [{"text": "أسبوعي", "callback_data": f"tf_1W_{txt}"}, {"text": "شهري", "callback_data": f"tf_1M_{txt}"}]
            ]}
            await send_msg(cid, f"🎯 اختر فريم {txt}:", grid)
            
    return {"ok": True}

@app.get("/")
def home(): return "V14 Ready & Fast"
