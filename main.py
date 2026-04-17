import os, httpx, asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI, Request

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

async def get_full_analysis(symbol, tf_key, include_option=False):
    try:
        # 1. ضبط الفريمات لتتوافق مع Polygon
        tf_map = {
            "5m": (5, "minute"),
            "1h": (1, "hour"),
            "1d": (1, "day"),
            "1W": (1, "week"),
            "1M": (1, "month")
        }
        mult, span = tf_map.get(tf_key, (1, "hour"))

        # 2. تحديد تاريخ ديناميكي لضمان سرعة الاستجابة
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')

        # رابط Polygon مع جلب أحدث البيانات أولاً (sort=desc)
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/range/{mult}/{span}/{start_date}/{end_date}?adjusted=true&sort=desc&limit=100&apiKey={MARKET_KEY}"

        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=10.0)
            data = r.json()

        if "results" not in data or not data["results"]:
            return f"❌ فشل تحليل {symbol}. لا توجد بيانات كافية."

        # ترتيب البيانات من الأقدم للأحدث للحسابات
        results = data["results"][::-1]
        closes = [c["c"] for c in results]
        highs = [c["h"] for c in results]
        lows = [c["l"] for c in results]

        close = round(closes[-1], 2)
        high = max(highs[-14:])
        low = min(lows[-14:])

        # حساب RSI مبسط
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d for d in deltas if d > 0]
        losses = [abs(d) for d in deltas if d < 0]
        avg_gain = sum(gains[-14:]) / 14 if gains else 1
        avg_loss = sum(losses[-14:]) / 14 if losses else 1
        rs = avg_gain / avg_loss if avg_loss != 0 else 0
        rsi = 100 - (100 / (1 + rs))

        is_call = rsi > 50
        pivot = (high + low + close) / 3

        # تحديد الأهداف بناءً على Pivot
        if is_call:
            t1, t2, t3 = (2 * pivot) - low, pivot + (high - low), high + 2 * (pivot - low)
            sl = low
        else:
            t1, t2, t3 = (2 * pivot) - high, pivot - (high - low), low - 2 * (high - pivot)
            sl = high

        prob = min(94, max(55, int(rsi + 20) if is_call else int((100 - rsi) + 20)))
        time_est = {"5m": "30د", "1h": "4س", "1d": "3أيام", "1W": "أسبوع+", "1M": "شهر+"}.get(tf_key, "---")

        res = f"🚀 *نتائج قناص {symbol.upper()}*\n---\n⏱ الفريم: {tf_key} | 💰 السعر: {close}\n🧭 التوجه: {'🟢 CALL' if is_call else '🔴 PUT'}\n\n🎯 *الأهداف:*\n1️⃣ `{round(t1, 2)}` | 2️⃣ `{round(t2, 2)}` | 3️⃣ `{round(t3, 2)}`\n🛑 *الوقف:* `{round(sl, 2)}`\n\n📊 الاحتمالية: `{prob}%` | ⏳ الوقت: `{time_est}`"

        # --- قسم جلب العقود (MarketData) ---
        if include_option:
            try:
                side = "call" if is_call else "put"
                # جلب عقود ITM القريبة
                opt_url = f"https://api.marketdata.app/v1/options/quotes/{symbol.upper()}/?range=itm&side={side}&token={MARKET_KEY}"
                async with httpx.AsyncClient() as client:
                    r_opt = await client.get(opt_url, timeout=5.0)
                    d_opt = r_opt.json()
                    if d_opt.get('s') == 'ok':
                        strike = d_opt['strike'][0]
                        price = d_opt['mid'][0]
                        res += f"\n\n📦 *العقد المقترح:* {strike} | 💵: {price}\n✅ هدف العقد (30%): {round(price * 1.3, 2)}"
            except: 
                res += "\n\n⚠️ تعذر جلب بيانات العقد حالياً."

        return res + "\n---\n📢 @Option_Strike01"

    except Exception as e:
        return f"❌ خطأ فني في {symbol}: {str(e)}"

@app.post("/webhook")
async def signals(request: Request):
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
    try:
        data = await request.json()
        if "callback_query" in data:
            call = data["callback_query"]
            cid = call["message"]["chat"]["id"]
            c_data = call["data"]
            await send_msg(cid, "⏳ جاري التحليل واستخراج العقود...")
            if c_data.startswith("tf_"):
                _, tf, sym = c_data.split("_")
                res = await get_full_analysis(sym, tf, include_option=True) # تفعيل العقود في التحليل اليدوي أيضاً
                await send_msg(cid, res)
        elif "message" in data:
            msg = data["message"]
            cid = msg["chat"]["id"]
            txt = str(msg.get("text", "")).upper().strip()
            if txt in ["/START", "START"]:
                menu = {"inline_keyboard": [[{"text": "🔍 رادار التحليل", "callback_data": "menu_analyze"}]]}
                await send_msg(cid, "🛡 *Option Strike v18.0 جاهز*\nأدخل رمز السهم مباشرة (مثال: NVDA)", menu)
            elif 1 <= len(txt) <= 6:
                btns = {"inline_keyboard": [
                    [{"text": "5m", "callback_data": f"tf_5m_{txt}"}, {"text": "1h", "callback_data": f"tf_1h_{txt}"}, {"text": "1d", "callback_data": f"tf_1d_{txt}"}]
                ]}
                await send_msg(cid, f"🎯 اختر فريم التحليل لـ {txt}:", btns)
    except: pass
    return {"ok": True}

@app.get("/")
def home(): return "Bot is Running"
