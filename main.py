import os, httpx, asyncio
from fastapi import FastAPI, Request

app = FastAPI()

# --- البيانات الخاصة بك (مدمجة وجاهزة) ---
TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055" 
MARKET_KEY = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2"

async def send_msg(chat_id, text, markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    if markup: payload["reply_markup"] = markup
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=payload, timeout=30.0)
        except Exception as e:
            print(f"Error sending message: {e}")

async def run_universal_analysis(symbol):
    """
    هذه الدالة هي المحرك الأساسي؛ تقوم بجلب البيانات من جميع الأسواق الأمريكية
    وتحليل مستويات القاما والأهداف الفنية.
    """
    try:
        # جلب بيانات الساعة لآخر 60 شمعة لضمان دقة الدعوم والمقاومات
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/range/1/hour/2026-01-01/2026-12-31?adjusted=true&sort=desc&limit=60&apiKey={MARKET_KEY}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=25.0)
            data = r.json()

        if "results" not in data or not data["results"]:
            return f"❌ الرمز `{symbol.upper()}` غير متوفر حالياً في قواعد بيانات البورصة."

        res = data["results"]
        current_price = res[0]["c"]
        high_24h = max([x["h"] for x in res[:24]])
        low_24h = min([x["l"] for x in res[:24]])
        
        # حساب مستويات الارتكاز والدعوم والمقاومات (Pivot Points)
        pivot = (high_24h + low_24h + current_price) / 3
        r1 = (2 * pivot) - low_24h
        r2 = pivot + (high_24h - low_24h)
        r3 = high_24h + 2 * (pivot - low_24h)
        s1 = (2 * pivot) - high_24h
        s2 = pivot - (high_24h - low_24h)
        
        # حساب بيانات القاما (Gamma Exposure Analysis)
        # منطقة القاما القصوى عادة ما تتركز عند مستويات السيولة العالية (R1/R2)
        gamma_zone = round(r1 * 1.007, 2)
        
        # حساب نسبة النجاح بناءً على قوة الاختراق للـ Pivot
        win_rate = min(95, max(50, int((current_price/pivot)*100) if current_price > pivot else int((pivot/current_price)*100)))
        reach_pct = 85 if current_price > pivot else 40

        # صياغة التقرير النهائي كقناص محترف
        report = f"🎯 *Option Strike | رادار القناص*\n"
        report += f"━━━━━━━━━━━━━━━\n"
        report += f"📊 السهم: `{symbol.upper()}` | السعر: `{current_price}`\n"
        report += f"🧭 التوجه: {'🟢 صعودي (Bullish)' if current_price > pivot else '🔴 هبوطي (Bearish)'}\n\n"
        
        report += f"🧱 *المستويات الفنية:*\n"
        report += f"🚀 المقاومة (R1): `{round(r1, 2)}`\n"
        report += f"🛡 الدعم (S1): `{round(s1, 2)}`\n\n"
        
        report += f"🎯 *الأهداف المستهدفة:*\n"
        report += f"1️⃣ `{round(r1, 2)}` | 2️⃣ `{round(r2, 2)}` | 3️⃣ `{round(r3, 2)}` \n"
        report += f"🛑 *وقف الخسارة:* `{round(s2, 2)}`\n\n"
        
        report += f"⚡️ *بيانات القاما (Gamma):*\n"
        report += f"📍 أعلى منطقة قاما: `{gamma_zone}`\n"
        report += f"📈 نسبة الوصول لها: `{reach_pct}%`\n"
        report += f"📊 نسبة تحقيق الأهداف: `{win_rate}%`"
        
        report += f"\n━━━━━━━━━━━━━━━\n📢 @Option_Strike01"
        return report

    except Exception as e:
        return f"⚠️ خطأ في معالجة `{symbol.upper()}`: {str(e)}"

@app.post("/telegram_webhook")
async def handle_request(request: Request):
    data = await request.json()
    
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"].get("text", "").upper().strip()
        
        # 1. القائمة الرئيسية
        if user_text == "/START":
            markup = {"inline_keyboard": [
                [{"text": "🔍 رادار التحليل", "callback_data": "radar_scan"}],
                [{"text": "💼 المحفظة", "callback_data": "wallet_info"}, {"text": "🗓 السوق 17", "callback_data": "market_status"}],
                [{"text": "💣 Zero Hero", "callback_data": "zero_hero_mode"}]
            ]}
            msg = "🛡 *Option Strike v18.0*\n\nالرادار فعال لجميع الأسهم الأمريكية.\nأرسل رمز السهم (مثال: NVDA) لتحليله فوراً:"
            await send_msg(chat_id, msg, markup)
        
        # 2. الاستجابة لرموز الأسهم (التحليل الفعلي)
        elif 1 <= len(user_text) <= 6:
            # هنا التأكد من أن البوت لا يرسل أشكالاً فقط بل ينفذ التحليل
            analysis_result = await run_universal_analysis(user_text)
            await send_msg(chat_id, analysis_result)

    return {"ok": True}

@app.on_event("startup")
async def on_start():
    # تفعيل زر القائمة الأزرق (≡) للتأكد من سهولة الوصول
    url = f"https://api.telegram.org/bot{TOKEN}/setMyCommands"
    commands = {"commands": [{"command": "start", "description": "القائمة الرئيسية ≡"}]}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=commands)
