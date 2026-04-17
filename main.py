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
            await client.post(url, json=payload, timeout=10.0)
    except: pass

async def get_pure_analysis(symbol, tf_key, include_option=False):
    try:
        # 1. إعداد الفريمات
        itv_map = {"5m": Interval.INTERVAL_5_MINUTES, "1h": Interval.INTERVAL_1_HOUR, "1d": Interval.INTERVAL_1_DAY, "1W": Interval.INTERVAL_1_WEEK, "1M": Interval.INTERVAL_1_MONTH}
        itv = itv_map.get(tf_key, Interval.INTERVAL_1_HOUR)
        
        # 2. جلب البيانات الفنية
        h = TA_Handler(symbol=symbol.upper(), screener="america", exchange="NASDAQ", interval=itv)
        analysis = await asyncio.to_thread(h.get_analysis)
        ind = analysis.indicators
        close, rsi = round(ind['close'], 2), ind['RSI']
        is_call = rsi > 50
        
        # 3. حساب مستويات القاما والأهداف الثلاثة (بمعادلات Pivot Points)
        high, low, cp = ind['high'], ind['low'], ind['close']
        pivot = (high + low + cp) / 3
        
        if is_call:
            t1 = round((2 * pivot) - low, 2) # مستوى القاما
            t2 = round(pivot + (high - low), 2)
            t3 = round(high + 2*(pivot - low), 2)
            sl = round(low, 2)
        else:
            t1 = round((2 * pivot) - high, 2) # مستوى القاما
            t2 = round(pivot - (high - low), 2)
            t3 = round(low - 2*(high - pivot), 2)
            sl = round(high, 2)
        
        prob = min(94, max(55, int(rsi + 20) if is_call else int((100 - rsi) + 20)))
        time_est = {"5m": "30د", "1h": "4س", "1d": "3أيام", "1W": "أسبوع+", "1M": "شهر+"}.get(tf_key, "---")

        res = f"""🚀 *نتائج قناص {symbol.upper()}*
---
⏱ الفريم: {tf_key} | 💰 السعر: {close}
🧭 التوجه: {'🟢 CALL (صعود)' if is_call else '🔴 PUT (هبوط)'}

🎯 *أهداف السهم:*
1️⃣ الهدف الأول: `{t1}` (القاما)
2️⃣ الهدف الثاني: `{t2}`
3️⃣ الهدف الثالث: `{t3}`

🛑 *وقف الخسارة:* `{sl}`

📊 الاحتمالية: `{prob}%` | ⏳ الوقت: `{time_est}`"""

        if include_option: # للطرح الآلي فقط يبقى العقد كاملاً
            try:
                side = "call" if is_call else "put"
                url = f"https://api.marketdata.app/v1/options/quotes/{symbol}/?range=itm&side={side}&token={MARKET_KEY}"
                async with httpx.AsyncClient() as client:
                    r = await client.get(url, timeout=2.0)
                    d = r.json()
                    if d.get('s') == 'ok':
                        p = d['mid'][0]
                        res += f"\n\n📦 *العقد المقترح:*\n🔹 السترايك: {d['strike'][0]}\n💵 الدخول: {p}\n✅ هدف (30%): {round(p*1.3, 2)}"
            except: pass
        
        return res + "\n---\n📢 @Option_Strike01"
    except: return f"❌ فشل تحليل {symbol}. تأكد من الرمز."

@app.post("/webhook")
async def signals(request: Request):
    """طرح الـ 80 شركة (بالعقود والأهداف)"""
    data = await request.json()
    if data.get("secret") == "12345":
        symbol = data.get("ticker")
        res = await get_pure_analysis(symbol, "1h", include_option=True)
        await send_msg(CHAT_ID, f"🔥 *طرح آلي*\n{res}")
    return {"ok": True}

@app.post("/telegram_webhook")
async def telegram(request: Request):
    data = await request.json()
    if "callback_query" in data:
        call = data["callback_query"]; cid = call["message"]["chat"]["id"]; c_data = call["data"]
        async with httpx.AsyncClient() as client:
            await client.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={"callback_query_id": call["id"]})
        
        if c_data == "menu_analyze": await send_msg(cid, "⌨️ أرسل الرمز (مثال: TSLA):")
        elif c_data == "menu_market": await send_msg(cid, "📅 السوق: 4:30م - 11:00م")
        elif c_data.startswith("tf_"):
            _, tf, sym = c_data.split("_")
            await send_msg(cid, f"⏳ جاري تحليل {sym}...")
            res = await get_pure_analysis(sym, tf, include_option=False)
            await send_msg(cid, res)

    elif "message" in data:
        msg = data["message"]; cid = msg["chat"]["id"]; txt = str(msg.get("text", "")).upper().strip()
        if txt in ["/START", "START"]:
            keyboard = {"inline_keyboard": [[{"text": "🔍 رادار التحليل", "callback_data": "menu_analyze"}], [{"text": "📅 السوق", "callback_data": "menu_market"}]]}
            await send_msg(cid, "🛡 *Option Strike v16.0*", keyboard)
        elif 1 <= len(txt) <= 6:
            btns = {"inline_keyboard": [
                [{"text": "5m", "callback_data": f"tf_5m_{txt}"}, {"text": "1h", "callback_data": f"tf_1h_{txt}"}, {"text": "1d", "callback_data": f"tf_1d_{txt}"}],
                [{"text": "أسبوعي", "callback_data": f"tf_1W_{txt}"}, {"text": "شهري", "callback_data": f"tf_1M_{txt}"}]
            ]}
            await send_msg(cid, f"🎯 اختر فريم {txt}:", btns)
    return {"ok": True}

@app.get("/")
def home(): return "Ready"
