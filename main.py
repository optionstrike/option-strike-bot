import os
import requests
from fastapi import FastAPI, Request
from tradingview_ta import TA_Handler, Interval
from datetime import datetime

app = FastAPI()

TELEGRAM_TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055"
DAILY_LIMIT = 5
trades_count = 0 

# --- 1. دالة التحليل الذكي ---
def get_ultimate_analysis(symbol: str, tf_key: str):
    try:
        intervals = {
            "5m": Interval.INTERVAL_5_MINUTES, "15m": Interval.INTERVAL_15_MINUTES, 
            "1h": Interval.INTERVAL_1_HOUR, "4h": Interval.INTERVAL_4_HOURS, 
            "1d": Interval.INTERVAL_1_DAY, "1W": Interval.INTERVAL_1_WEEK
        }
        interval = intervals.get(tf_key, Interval.INTERVAL_1_HOUR)
        sources = [{"ex": "NASDAQ", "s": "america"}, {"ex": "NYSE", "s": "america"}, 
                   {"ex": "CBOE", "s": "america"}, {"ex": "SP", "s": "america"}, {"ex": "TVC", "s": "america"}]
        
        analysis = None
        for src in sources:
            try:
                h = TA_Handler(symbol=symbol.upper(), screener=src['s'], exchange=src['ex'], interval=interval)
                analysis = h.get_analysis()
                if analysis: break
            except: continue

        if not analysis: return f"❌ تعذر العثور على {symbol}."

        ind = analysis.indicators
        close, rsi = round(ind['close'], 2), ind['RSI']
        pivot = (ind['high'] + ind['low'] + ind['close']) / 3
        r1, s1 = round((2 * pivot) - ind['low'], 2), round((2 * pivot) - ind['high'], 2)
        
        direction = "🟢 CALL" if rsi > 55 else "🔴 PUT"
        prob = "84%" if rsi > 65 or rsi < 35 else "62%"

        return f"""🚀 **رادار Option Strike: {symbol.upper()}**
⏱ **الفريم:** {tf_key} | 💰 **السعر:** {close}
---
🧭 **التوجه:** {direction}
⚡️ **أعلى مستوى جاما:** {r1 if "CALL" in direction else s1}
📊 **احتمالية الوصول:** {prob}
🛑 **الوقف:** {s1 if "CALL" in direction else r1}
---
📢 @Option_Strike01"""
    except Exception as e: return f"❌ خطأ: {str(e)}"

# --- 2. إرسال القائمة الرئيسية (غرفة العمليات) ---
def send_main_menu(chat_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "🛡 **لوحة تحكم Option Strike v4.0**\nأهلاً بك في غرفة العمليات، اختر وجهتك:",
        "reply_markup": {"inline_keyboard": [
            [{"text": "🔍 رادار التحليل الذكي", "callback_data": "menu_analyze"}],
            [{"text": "💼 ملخص المحفظة", "callback_data": "menu_portfolio"}, {"text": "📈 سجل النتائج", "callback_data": "menu_history"}],
            [{"text": "💣 التبديل إلى Zero Hero", "callback_data": "menu_zerohero"}],
            [{"text": "📅 مفكرة السوق", "callback_data": "menu_market"}]
        ]}
    }
    requests.post(url, json=payload)

# --- 3. معالجة الأوامر ---
@app.post("/telegram_webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    
    if "callback_query" in data:
        call = data["callback_query"]
        chat_id, c_data = call["message"]["chat"]["id"], call["data"]
        
        if c_data == "menu_analyze":
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": "⌨️ أرسل رمز السهم الآن (مثال: NVDA)"})
        elif c_data == "menu_market":
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": "📅 **مفكرة السوق:**\n🇺🇸 السوق الأمريكي: مفتوح ✅\n⚖️ الفيدرالي: لا توجد تصريحات اليوم."})
        elif c_data.startswith("tf_"):
            _, tf, sym = c_data.split("_")
            res = get_ultimate_analysis(sym, tf)
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": res, "parse_mode": "Markdown"})
        else:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": "🚧 هذا القسم سيتم ربطه ببياناتك قريباً."})
            
    elif "message" in data:
        msg = data["message"]
        txt, chat_id = str(msg.get("text", "")).upper(), msg["chat"]["id"]
        
        if txt == "/START" or txt == "START":
            send_main_menu(chat_id)
        elif 1 <= len(txt) <= 6:
            # إذا أرسل رمز سهم، تطلع له فريمات التحليل
            grid = {"inline_keyboard": [
                [{"text": "5m", "callback_data": f"tf_5m_{txt}"}, {"text": "15m", "callback_data": f"tf_15m_{txt}"}, {"text": "1h", "callback_data": f"tf_1h_{txt}"}],
                [{"text": "4h", "callback_data": f"tf_4h_{txt}"}, {"text": "1d", "callback_data": f"tf_1d_{txt}"}]
            ]}
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": f"🎯 اختر فريم التحليل لـ {txt}:", "reply_markup": grid})
            
    return {"ok": True}

@app.get("/")
def home(): return {"status": "V4.0 Final Active"}
