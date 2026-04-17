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
            await client.post(url, json=payload, timeout=12.0)
    except: pass

async def get_full_analysis(symbol, tf_key, include_option=False):
    try:
        tf_map = {"5m": (5, "minute"), "1h": (1, "hour"), "1d": (1, "day"), "1W": (1, "week"), "1M": (1, "month")}
        mult, span = tf_map.get(tf_key, (1, "hour"))

        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')

        # جلب البيانات من Polygon
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/range/{mult}/{span}/{start_date}/{end_date}?adjusted=true&sort=desc&limit=100&apiKey={MARKET_KEY}"

        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=12.0)
            data = r.json()

        if "results" not in data or not data["results"]:
            return f"❌ *فشل:* لا توجد بيانات لـ {symbol.upper()}"

        results = data["results"][::-1]
        closes = [c["c"] for c in results]
        high_14 = max([c["h"] for c in results[-14:]])
        low_14 = min([c["l"] for c in results[-14:]])
        close = round(closes[-1], 2)
        # إضاقة الفوليوم (آخر فوليوم مسجل)
        volume = results[-1].get("v", 0)
        formatted_vol = f"{volume:,.0f}"

        # الحسابات الفنية (RSI & Pivot)
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        avg_gain = sum([d for d in deltas[-14:] if d > 0]) / 14
        avg_loss = sum([abs(d) for d in deltas[-14:] if d < 0]) / 14
        rsi = 100 - (100 / (1 + (avg_gain/avg_loss))) if avg_loss != 0 else 100
        
        is_call = rsi > 50
        pivot = (high_14 + low_14 + close) / 3
        
        # أهم شيء: الأهداف
        if is_call:
            t1, t2, t3 = (2 * pivot) - low_14, pivot + (high_14 - low_14), high_14 + 2 * (pivot - low_14)
            sl = low_14
        else:
            t1, t2, t3 = (2 * pivot) - high_14, pivot - (high_14 - low_14), low_14 - 2 * (high_14 - pivot)
            sl = high_14

        res = f"💎 *نتائج قناص {symbol.upper()}*\n"
        res += f"━━━━━━━━━━━━━━━\n"
        res += f"⏱ الفريم: `{tf_key}` | 💰 السعر: `{close}`\n"
        res += f"📊 الفوليوم: `{formatted_vol}`\n"
        res += f"🧭 التوجه: {'🟢 CALL (صعود)' if is_call else '🔴 PUT (هبوط)'}\n\n"
        res += f"🎯 *أهداف السهم (أساسي):*\n"
        res += f"1️⃣ `{round(t1, 2)}` | 2️⃣ `{round(t2, 2)}` | 3️⃣ `{round(t3, 2)}`\n"
        res += f"🛑 *الوقف:* `{round(sl, 2)}`\n\n"
        res += f"📈 الاحتمالية: `{min(94, max(55, int(rsi+20 if is_call else 120-rsi)))}%`"

        if include_option:
            try:
                opt_url = f"https://api.marketdata.app/v1/options/quotes/{symbol.upper()}/?range=itm&side={'call' if is_call else 'put'}&token={MARKET_KEY}"
                async with httpx.AsyncClient() as client:
                    r_opt = await client.get(opt_url, timeout=10.0)
                    d_opt = r_opt.json()
                    if d_opt.get('s') == 'ok':
                        res += f"\n\n📦 *عقد الخيارات المقترح:*\n"
                        res += f"🔹 Strike: `{d_opt['strike'][0]}` | 💵: `{d_opt['mid'][0]}`\n"
                        res += f"✅ هدف (30%): `{round(d_opt['mid'][0] * 1.3, 2)}`"
            except: pass

        return res + "\n━━━━━━━━━━━━━━━\n📢 @Option_Strike01"
    except Exception as e: return f"❌ خطأ فني: {str(e)}"

@app.post("/webhook")
async def signals(request: Request):
    try:
        data = await request.json()
        if str(data.get("secret")) == "12345":
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
            cid, c_data = call["message"]["chat"]["id"], call["data"]
            if c_data.startswith("tf_"):
                _, tf, sym = c_data.split("_")
                await send_msg(cid, f"🔄 جاري تحليل {sym} وجلب الأهداف والعقود...")
                res = await get_full_analysis(sym, tf, include_option=True)
                await send_msg(cid, res)
        elif "message" in data:
            msg = data["message"]
            cid, txt = msg["chat"]["id"], str(msg.get("text", "")).upper().strip()
            if txt in ["/START", "START"]:
                menu = {"inline_keyboard": [[{"text": "🔍 رادار التحليل", "callback_data": "none"}]]}
                await send_msg(cid, "🛡 *Option Strike v18.0*\nأرسل رمز السهم الآن (مثال: AAPL)", menu)
            elif 1 <= len(txt) <= 6:
                btns = {"inline_keyboard": [
                    [{"text": "⏱ 5m", "callback_data": f"tf_5m_{txt}"}, {"text": "⏱ 1h", "callback_data": f"tf_1h_{txt}"}],
                    [{"text": "📅 Daily", "callback_data": f"tf_1d_{txt}"}, {"text": "🗓 Weekly", "callback_data": f"tf_1W_{txt}"}]
                ]}
                await send_msg(cid, f"🎯 *سهم {txt}*\nاختر فريم التحليل:", btns)
    except: pass
    return {"ok": True}

@app.get("/")
def home(): return "Bot is Online"
