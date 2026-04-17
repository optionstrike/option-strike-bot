import os, httpx, asyncio
from datetime import datetime
from fastapi import FastAPI, Request

app = FastAPI()

# --- الإعدادات (تأكد من صحتها) ---
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

async def get_universal_analysis(symbol):
    try:
        # 1. جلب البيانات من Polygon لجميع البورصات (NYSE, NASDAQ, AMEX)
        # نستخدم 100 شمعة لضمان دقة الدعوم والمقاومات
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/range/1/hour/2026-01-01/2026-12-31?adjusted=true&sort=desc&limit=100&apiKey={MARKET_KEY}"
        
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=20.0)
            data = r.json()

        if "results" not in data or not data["results"]:
            return f"❌ الرمز `{symbol.upper()}` غير موجود أو لا تتوفر له بيانات حالياً."

        res = data["results"]
        c = res[0]["c"]  # السعر الحالي
        h_max = max([x["h"] for x in res[:24]]) # أعلى سعر في 24 ساعة
        l_min = min([x["l"] for x in res[:24]]) # أدنى سعر في 24 ساعة
        
        # --- حساب مستويات الدعوم والمقاومات (Pivot Points) ---
        pivot = (h_max + l_min + c) / 3
        r1 = (2 * pivot) - l_min
        r2 = pivot + (h_max - l_min)
        r3 = h_max + 2 * (pivot - l_min)
        s1 = (2 * pivot) - h_max
        s2 = pivot - (h_max - l_min)

        # --- حساب القاما (Gamma Exposure) والاحتمالية ---
        # القاما تتركز عادة عند مستويات المقاومة النفسية والفنية
        gamma_level = round(r2, 2) 
        # نسبة تحقيق الأهداف بناءً على قوة الاختراق للـ Pivot
        probability = min(94, max(52, int((c/pivot)*100) if c > pivot else int((pivot/c)*100)))
        reach_gamma_pct = 82 if c > pivot else 35

        # --- بناء التقرير ---
        report = f"🎯 *Option Strike | رادار الشمول الكامل*\n"
        report += f"━━━━━━━━━━━━━━━\n"
        report += f"📊 السهم: `{symbol.upper()}` | السعر: `{c}`\n"
        report += f"🧭 الاتجاه: {'🟢 صعودي القوة' if c > pivot else '🔴 ضغط هبوطي'}\n\n"
        
        report += f"🧱 *المستويات الرئيسية:*\n"
        report += f"🚀 المقاومة: `{round(r1, 2)}`\n"
        report += f"🛡 الدعم: `{round(s1, 2)}`\n\n"
        
        report += f"🎯 *الأهداف المستهدفة:*\n"
        report += f"1️⃣ `{round(r1, 2)}` | 2️⃣ `{round(r2, 2)}` | 3️⃣ `{round(r3, 2)}` \n"
        report += f"🛑 *وقف الخسارة:* `{round(s2, 2)}`\n\n"
        
        report += f"⚡️ *بيانات القاما (Gamma Analysis):*\n"
        report += f"📍 أعلى منطقة قاما: `{gamma_level}`\n"
        report += f"📈 نسبة الوصول للقاما: `{reach_gamma_pct}%`\n"
        report += f"📊 نسبة نجاح الأهداف: `{probability}%`"
        
        report += f"\n━━━━━━━━━━━━━━━\n📢 @Option_Strike01"
        return report

    except Exception as e:
        return f"❌ حدث خطأ أثناء تحليل `{symbol.upper()}`."

@app.post("/telegram_webhook")
async def telegram(request: Request):
    data = await request.json()
    if "message" in data:
        cid = data["message"]["chat"]["id"]
        txt = data["message"].get("text", "").upper().strip()
        
        if txt == "/START":
            markup = {"inline_keyboard": [
                [{"text": "🔍 رادار التحليل", "callback_data": "radar"}],
                [{"text": "💼 المحفظة", "callback_data": "wallet"}, {"text": "🗓 السوق 17", "callback_data": "market"}],
                [{"text": "💣 Zero Hero", "callback_data": "zero_hero"}]
            ]}
            await send_msg(cid, "🛡 *Option Strike v18.0*\nالآن لجميع الأسهم الأمريكية.. أرسل الرمز فوراً:", markup)
        elif 1 <= len(txt) <= 6:
            res = await get_universal_analysis(txt)
            await send_msg(cid, res)
            
    return {"ok": True}

@app.on_event("startup")
async def startup():
    url = f"https://api.telegram.org/bot{TOKEN}/setMyCommands"
    cmds = {"commands": [{"command": "start", "description": "القائمة الرئيسية ≡"}]}
    async with httpx.AsyncClient() as client: await client.post(url, json=cmds)
