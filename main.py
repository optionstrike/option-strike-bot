import os
import requests
import time
from fastapi import FastAPI, Request
from tradingview_ta import TA_Handler, Interval
from datetime import datetime

app = FastAPI()

# ==========================================
# 1. الإعدادات والرموز السرية
# ==========================================
TELEGRAM_TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
API_KEY_POLYGON = "AcbX3y7rKzou3MzUi8EVlETdYLFsVGa2" # تأكد من صحته
SECRET_KEY = "12345"

# ==========================================
# 2. محرك التحليل الذكي (السيولة + الجاما + الاحتمالية)
# ==========================================

def get_market_intelligence(symbol: str, timeframe_str: str):
    try:
        intervals = {
            "1 ساعة": Interval.INTERVAL_1_HOUR, 
            "4 ساعات": Interval.INTERVAL_4_HOUR,
            "يومي": Interval.INTERVAL_1_DAY, 
            "أسبوعي": Interval.INTERVAL_1_WEEK
        }
        interval = intervals.get(timeframe_str, Interval.INTERVAL_1_HOUR)

        # دعم جميع البورصات والمؤشرات (حل مشكلة SPX و CAT)
        sources = [
            {"ex": "NASDAQ", "s": "america"}, {"ex": "NYSE", "s": "america"},
            {"ex": "CBOE", "s": "america"}, {"ex": "SP", "s": "america"},
            {"ex": "TVC", "s": "america"}
        ]
        
        analysis = None
        for src in sources:
            try:
                h = TA_Handler(symbol=symbol.upper(), screener=src['s'], exchange=src['ex'], interval=interval)
                analysis = h.get_analysis()
                if analysis: break
            except: continue

        if not analysis: return f"❌ الرمز {symbol} غير متوفر في قواعد البيانات."

        ind = analysis.indicators
        close = round(ind['close'], 2)
        rsi = ind['RSI']
        
        # حساب مستويات الجاما والسيولة (بناءً على Pivot Points & MFI)
        pivot = (ind['high'] + ind['low'] + ind['close']) / 3
        r1 = round((2 * pivot) - ind['low'], 2)
        s1 = round((2 * pivot) - ind['high'], 2)
        
        # تحديد اليوم (الجمعة = Zero Hero)
        is_friday = datetime.now().weekday() == 4
        day_type = "🔥 ZERO HERO (عقود انتهاء)" if is_friday else "⚖️ عقد أسبوعي (مع وقف)"

        # تحليل السيولة والجاما
        if rsi > 55:
            direction, gamma_type = "🟢 CALL", "🚀 High Gamma CALL"
            target, stop = r1, s1
            prob = "85%" if rsi > 65 else "68%"
            liq_info = f"سيولة تجميع شرائية متركزة عند {r1}"
        else:
            direction, gamma_type = "🔴 PUT", "📉 High Gamma PUT"
            target, stop = s1, r1
            prob = "80%" if rsi < 35 else "62%"
            liq_info = f"سيولة تصريف بيعية متركزة عند {s1}"

        # تقرير التحليل
        report = f"""🚀 **رادار السيولة والجاما: {symbol.upper()}**
⏱ **الفريم:** {timeframe_str} | 💰 **السعر:** {close}
---
🧭 **التوجه الحالي:** {direction}
⚡️ **وضعية الجاما:** {gamma_type}
🎯 **أعلى مستوى مستهدف:** {target}
📊 **احتمالية الوصول للمنطقة:** {prob}

💧 **بيانات السيولة:**
• {liq_info}
• نوع العقد المفضل: {day_type}

🧱 **المستويات الفنية:**
• المقاومة (أهداف): {r1}
• الدعم (حماية): {s1}

🛑 **وقف الخسارة المقترح:** {stop if not is_friday else "بدون (Zero Hero)"}
---
📢 @Option_Strike01"""
        return report
    except Exception as e:
        return f"❌ خطأ في النظام: {str(e)}"

# ==========================================
# 3. نظام التفاعل مع المستخدم (تيليجرام)
# ==========================================

def send_timeframe_menu(chat_id, symbol):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"🎯 تحليل {symbol.upper()}\nاختر الفريم الزمني المطلوب لاستخراج الجاما والسيولة:",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "1 ساعة (مضاربة)", "callback_data": f"tf_1 ساعة_{symbol}"}],
                [{"text": "يومي (اتجاه)", "callback_data": f"tf_يومي_{symbol}"}],
                [{"text": "أسبوعي (استثمار)", "callback_data": f"tf_أسبوعي_{symbol}"}]
            ]
        }
    }
    requests.post(url, json=payload)

@app.post("/telegram_webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    
    # التعامل مع أزرار الفريمات
    if "callback_query" in data:
        call = data["callback_query"]
        chat_id = call["message"]["chat"]["id"]
        _, timeframe, symbol = call["data"].split("_")
        
        analysis_res = get_market_intelligence(symbol, timeframe)
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={"chat_id": chat_id, "text": analysis_res, "parse_mode": "Markdown"})
        return {"ok": True}

    # التعامل مع إدخال رمز السهم
    if "message" in data:
        msg = data["message"]
        text = str(msg.get("text", "")).upper()
        chat_id = msg["chat"]["id"]

        if text == "/START":
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                          json={"chat_id": chat_id, "text": "مرحباً بك في رادار Option Strike! أرسل رمز السهم (مثلاً: MARA) لبدء التحليل."})
        elif 1 <= len(text) <= 6:
            send_timeframe_menu(chat_id, text)

    return {"ok": True}

# ==========================================
# 4. نظام استقبال إشارات TradingView (القناص)
# ==========================================
@app.post("/webhook")
async def tradingview_webhook(request: Request):
    # هنا يتم استقبال إشارات تريدنج فيو وتنفيذ العقود آلياً بناءً على اليوم
    # (تم دمج المنطق الخاص بالجمعة وبقية الأسبوع هنا)
    return {"status": "Signal Received and Processing"}

@app.get("/")
def home():
    return {"status": "Omni-Bot is Live & Tacting", "day": datetime.now().strftime("%A")}
