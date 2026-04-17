import os, httpx, asyncio
from fastapi import FastAPI, Request
from tradingview_ta import TA_Handler, Interval

app = FastAPI()

# --- الإعدادات الثابتة ---
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

async def get_full_analysis(symbol, tf_key, include_option=False):
    try:
        itv_map = {
            "5m": Interval.INTERVAL_5_MINUTES, 
            "1h": Interval.INTERVAL_1_HOUR, 
            "1d": Interval.INTERVAL_1_DAY, 
            "1W": Interval.INTERVAL_1_WEEK, 
            "1M": Interval.INTERVAL_1_MONTH
        }
        itv = itv_map.get(tf_key, Interval.INTERVAL_1_HOUR)
        
        # استخدام "america" كبورصة عامة لضمان عمل أسهم مثل DELL و NVDA معاً
        h = TA_Handler(
            symbol=symbol.upper(),
            screener="america",
            exchange="america", 
            interval=itv
        )
        
        # زيادة وقت الانتظار قليلاً لضمان جلب البيانات الفنية
        analysis = await asyncio.wait_for(asyncio.to_thread(h.get_analysis), timeout=5.0)
        
        ind = analysis.indicators
        close, rsi = round(ind['close'], 2), ind['RSI']
        is_call = rsi > 50
        pivot = (ind['high'] + ind['low'] + ind['close']) / 3
        
        # حساب الأهداف بناءً على مستويات Gamma/Pivot
        t1 = round((2 * pivot) - ind['low'], 2) if is_call else round((2 * pivot) - ind['high'], 2)
        t2 = round(pivot + (ind['high'] - ind['low']), 2) if is_call else round(pivot - (ind['high'] - ind['low']), 2)
        t3 = round(ind['high'] + 2*(pivot - ind['low']), 2) if is_call else round(ind['low'] - 2*(ind['high'] - pivot), 2)
        sl = round(ind['low'], 2) if is_call else round(ind['high'], 2)
        
        prob = min(94, max(55, int(rsi + 20) if is_call else int((100 - rsi) + 20)))
        time_est = {"5m": "30د", "1h": "4س", "1d": "3أيام", "1W": "أسبوع+", "1M": "شهر+"}.get(tf_key, "---")

        res = f"🚀 *نتائج قناص {symbol.upper()}*\n---\n⏱ الفريم: {tf_key} | 💰 السعر: {close}\n🧭 التوجه: {'🟢 CALL' if is_call else '🔴 PUT'}\n\n🎯 *الأهداف:*\n1️⃣ `{t1}` | 2️⃣ `{t2}` | 3️⃣ `{t3}`\n🛑 *الوقف:* `{sl}`\n\n📊 الاحتمالية: `{prob}%` | ⏳ الوقت: `{time_est}`"

        # جلب بيانات العقود إذا كان الطلب يتضمن ذلك (مثل الطرح الآلي)
        if include_option:
            try:
                side = "call" if is_call else "put"
                opt_url = f"https://api.marketdata.app/v1/options/quotes/{symbol}/?range=itm&side={side}&token={MARKET_KEY}"
                async with httpx.AsyncClient() as client:
                    r = await client.get(opt_url, timeout=2.0)
                    d = r.json()
                    if d.get('s') == 'ok':
                        p = d['mid'][0]
                        res += f"\n\n📦 *العقد:* {d['strike'][0]} | 💵: {p}\n✅ هدف (30%): {round(p*1.3, 2)}"
            except: pass

        return res + "\n---\n📢 @Option_Strike01"
    except Exception as e:
        print(f"Analysis Error for {symbol}: {e}")
        return f"❌ فشل تحليل {symbol}. تأكد من الرمز أو حاول لاحقاً."

@app.post("/webhook")
async def signals(request: Request):
    """استقبال التنبيهات الآلية (الطرح الآلي)"""
    try:
        data = await request.json()
        if data.get("secret") == "12345":
            symbol = data.get("ticker")
            res = await get_full_analysis(symbol, "1h", include_option=True)
            await send_msg(CHAT_ID, f"🔥 *طرح آلي*\n{res}")
    except: pass
    return {"ok": True}

@app.post("/telegram_webhook")
async def telegram(request: Request):
    """الرد على رسائل وتفاعلات المستخدمين في تليجرام"""
    data = await request.json()
    
    # التعامل مع الضغط على الأزرار
    if "callback_query" in data:
        call = data["callback_query"]
        cid = call["message"]["chat"]["id"]
        c_data = call["data"]
        
        async with httpx.AsyncClient() as client:
            await client.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={"callback_query_id": call["id"]})
        
        if c_data == "menu_analyze":
            await send_msg(cid, "⌨️ أرسل الرمز الآن (مثال: AAPL):")
        elif c_data == "menu_market":
            await send_msg(cid, "📅 السوق الأمريكي: 4:30م - 11:00م بتوقيت مكة")
        elif c_data == "menu_portfolio":
            await send_msg(cid, "💼 *محفظتك:*\n- العمليات المفتوحة: 0\n- الأرباح اليوم: $0.00")
        elif c_data == "menu_zerohero":
            await send_msg(cid, "💣 *Zero Hero:*\nقريباً.. سيتم طرح عقود انتهاء اليوم هنا.")
        elif c_data.startswith("tf_"):
            _, tf, sym = c_data.split("_")
            await send_msg(cid, f"⏳ جاري قنص {sym}...")
            # الطلب اليدوي يظهر التحليل الفني (بدون عقد لتجنب التأخير)
            res = await get_full_analysis(sym, tf, include_option=False)
            await send_msg(cid, res)

    # التعامل مع الرسائل النصية (إرسال رمز السهم)
    elif "message" in data:
        msg = data["message"]
        cid = msg["chat"]["id"]
        txt = str(msg.get("text", "")).upper().strip()
        
        if txt in ["/START", "START"]:
            menu = {"inline_keyboard": [
                [{"text": "🔍 رادار التحليل", "callback_data": "menu_analyze"}],
                [{"text": "💼 المحفظة", "callback_data": "menu_portfolio"}, {"text": "📅 السوق", "callback_data": "menu_market"}],
                [{"text": "💣 Zero Hero", "callback_data": "menu_zerohero"}]
            ]}
            await send_msg(cid, "🛡 *لوحة تحكم Option Strike v18.0*", menu)
        elif 1 <= len(txt) <= 6:
            btns = {"inline_keyboard": [
                [{"text": "5m", "callback_data": f"tf_5m_{txt}"}, {"text": "1h", "callback_data": f"tf_1h_{txt}"}, {"text": "1d", "callback_data": f"tf_1d_{txt}"}],
                [{"text": "أسبوعي", "callback_data": f"tf_1W_{txt}"}, {"text": "شهري", "callback_data": f"tf_1M_{txt}"}]
            ]}
            await send_msg(cid, f"🎯 اختر فريم التحليل لـ {txt}:", btns)
            
    return {"ok": True}

@app.get("/")
def home(): 
    return "Bot is Running Successfully"
