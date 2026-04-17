import os, httpx, asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI, Request

app = FastAPI()

# --- الإعدادات ---
TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055" 
MARKET_KEY = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2"

async def send_msg(chat_id, text, markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if markup: payload["reply_markup"] = markup
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, timeout=20.0)
    except: pass

async def get_full_analysis(symbol, tf_key, include_option=True):
    try:
        tf_map = {"5m": (5, "minute"), "15m": (15, "minute"), "1h": (1, "hour"), "1d": (1, "day"), "1w": (1, "week")}
        mult, span = tf_map.get(tf_key, (1, "hour"))

        # جلب البيانات من Polygon (البانيو)
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/range/{mult}/{span}/2026-01-01/2026-12-31?adjusted=true&sort=desc&limit=50&apiKey={MARKET_KEY}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=20.0)
            data = r.json()

        if "results" not in data or not data["results"]:
            return f"❌ فشل تحليل {symbol.upper()}. تأكد من الرمز."

        res_list = data["results"][::-1]
        close = res_list[-1]["c"]
        vol = res_list[-1].get("v", 0)
        high_14 = max([x["h"] for x in res_list[-14:]])
        low_14 = min([x["l"] for x in res_list[-14:]])
        
        pivot = (high_14 + low_14 + close) / 3
        is_call = close > pivot

        # حساب أهداف السهم
        t1 = (2 * pivot) - low_14 if is_call else (2 * pivot) - high_14
        t2 = pivot + (high_14 - low_14) if is_call else pivot - (high_14 - low_14)
        t3 = high_14 + 2 * (pivot - low_14) if is_call else low_14 - 2 * (high_14 - pivot)

        report = f"🎯 *Option Strike | سنايبر بوت*\n━━━━━━━━━━━━━━━\n"
        report += f"📊 سهم: `{symbol.upper()}` | فريم: `{tf_key}`\n"
        report += f"💰 السعر: `{close}` | 📈 الفوليوم: `{vol:,.0f}`\n"
        report += f"🧭 التوجه: {'🟢 CALL' if is_call else '🔴 PUT'}\n\n"
        report += f"🎯 *أهداف السهم:*\n1️⃣ `{round(t1, 2)}` | 2️⃣ `{round(t2, 2)}` | 3️⃣ `{round(t3, 2)}` \n"
        report += f"🛑 *الوقف:* `{round(low_14 if is_call else high_14, 2)}`"

        if include_option:
            # طرح العقد
            opt_url = f"https://api.marketdata.app/v1/options/quotes/{symbol.upper()}/?range=itm&side={'call' if is_call else 'put'}&token={MARKET_KEY}"
            async with httpx.AsyncClient() as client:
                r_opt = await client.get(opt_url, timeout=15.0)
                d_opt = r_opt.json()
                if d_opt.get('s') == 'ok':
                    report += f"\n\n📦 *طرح العقد المقترح:*\n"
                    report += f"🔹 السترايك: `{d_opt['strike'][0]}` | 💵 السعر: `{d_opt['mid'][0]}`\n"
                    report += f"✅ هدف العقد (30%): `{round(d_opt['mid'][0] * 1.3, 2)}`"
        
        return report + "\n━━━━━━━━━━━━━━━\n📢 @Option_Strike01"
    except: return f"❌ عطل فني في جلب بيانات {symbol}"

@app.post("/telegram_webhook")
async def telegram(request: Request):
    data = await request.json()
    if "message" in data:
        cid = data["message"]["chat"]["id"]
        txt = data["message"].get("text", "").upper()
        if txt == "/START":
            # لوحة التحكم المطلوبة
            markup = {"inline_keyboard": [
                [{"text": "🔍 رادار التحليل", "callback_data": "radar"}],
                [{"text": "💼 المحفظة", "callback_data": "wallet"}, {"text": "🗓 السوق 17", "callback_data": "market"}],
                [{"text": "💣 Zero Hero", "callback_data": "zero_hero"}]
            ]}
            await send_msg(cid, "🛡 *Option Strike v18.0*\nأرسل رمز السهم للتحليل أو اختر من القائمة:", markup)
        elif 1 <= len(txt) <= 5:
            # خيارات الفريمات
            btns = {"inline_keyboard": [
                [{"text": "5m", "callback_data": f"tf_5m_{txt}"}, {"text": "15m", "callback_data": f"tf_15m_{txt}"}, {"text": "1h", "callback_data": f"tf_1h_{txt}"}],
                [{"text": "Daily 📅", "callback_data": f"tf_1d_{txt}"}, {"text": "Weekly 🗓", "callback_data": f"tf_1w_{txt}"}]
            ]}
            await send_msg(cid, f"🎯 اختر فريم التحليل لـ {txt}:", btns)
            
    elif "callback_query" in data:
        call = data["callback_query"]
        cid, c_data = call["message"]["chat"]["id"], call["data"]
        if c_data.startswith("tf_"):
            _, tf, sym = c_data.split("_")
            await send_msg(cid, f"🔄 جاري قنص أهداف {sym} وعقوده...")
            res = await get_full_analysis(sym, tf, True)
            await send_msg(cid, res)
    return {"ok": True}

@app.on_event("startup")
async def startup():
    # تفعيل القائمة الزرقاء (Menu) على اليسار
    url = f"https://api.telegram.org/bot{TOKEN}/setMyCommands"
    commands = {"commands": [
        {"command": "start", "description": "القائمة الرئيسية ≡"},
        {"command": "results", "description": "نتائج العقود 💰"},
        {"command": "follow", "description": "متابعة السوق 👀"}
    ]}
    async with httpx.AsyncClient() as client: await client.post(url, json=commands)

@app.get("/")
def home(): return "Option Strike Active"
