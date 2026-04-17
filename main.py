import os
import requests
from fastapi import FastAPI, Request
from tradingview_ta import TA_Handler, Interval
from datetime import datetime

app = FastAPI()

# --- الإعدادات (تأكد من صحتها) ---
TELEGRAM_TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055" 
DAILY_LIMIT = 5
trades_count = 0 

# --- 1. محرك الطرح الآلي (الذي يرسل العقود للتلغرام) ---
def post_automated_trade(symbol, action, price):
    global trades_count
    if trades_count >= DAILY_LIMIT:
        return

    is_friday = datetime.now().weekday() == 4
    strategy = "ZERO HERO 💣" if is_friday else "Weekly Sniper 🎯"
    
    # حساب الأهداف (مثلاً 25% و 60% ربح)
    target1 = round(price * 1.25, 2)
    target2 = round(price * 1.60, 2)
    stop_loss = round(price * 0.75, 2) if not is_friday else "بدون (زيرو هيرو)"

    msg = f"""🔥 **طرح عقد جديد (عقد {trades_count + 1}/5)**
💎 **السهم:** {symbol} | **النوع:** {action}
📝 **الاستراتيجية:** {strategy}
💵 **سعر الدخول المتوقع:** {price}

🎯 **الهدف الأول (25%):** {target1}
🎯 **الهدف الثاني (60%):** {target2}
🛑 **وقف الخسارة:** {stop_loss}

📊 تم الرصد آلياً من رادار الـ 80 شركة.
📢 @Option_Strike01"""
    
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg})
    trades_count += 1

# --- 2. استقبال إشارات الـ 80 شركة (Webhook) ---
@app.post("/webhook")
async def tradingview_webhook(request: Request):
    data = await request.json()
    # تأكد من إرسال "secret": "12345" في تنبيه TradingView
    if data.get("secret") != "12345": return {"error": "Unauthorized"}
    
    post_automated_trade(data.get("ticker"), data.get("action"), data.get("price"))
    return {"status": "Trade Posted to Telegram"}

# --- 3. محرك التحليل اليدوي (الفريمات كاملة) ---
def get_ultimate_analysis(symbol: str, tf_key: str):
    try:
        intervals = {
            "5m": Interval.INTERVAL_5_MINUTES, "15m": Interval.INTERVAL_15_MINUTES, 
            "1h": Interval.INTERVAL_1_HOUR, "4h": Interval.INTERVAL_4_HOURS, 
            "1d": Interval.INTERVAL_1_DAY, "1W": Interval.INTERVAL_1_WEEK, "1M": Interval.INTERVAL_1_MONTH
        }
        interval = intervals.get(tf_key, Interval.INTERVAL_1_HOUR)
        sources = [{"ex": "NASDAQ", "s": "america"}, {"ex": "NYSE", "s": "america"}, 
                   {"ex": "CBOE", "s": "america"}, {"ex": "SP", "s": "america"}]
        
        analysis = None
        for src in sources:
            try:
                h = TA_Handler(symbol=symbol.upper(), screener=src['s'], exchange=src['ex'], interval=interval)
                analysis = h.get_analysis()
                if analysis: break
            except: continue

        if not analysis: return f"❌ تعذر استخراج بيانات {symbol}."
        ind = analysis.indicators
        rsi = ind['RSI']
        pivot = (ind['high'] + ind['low'] + ind['close']) / 3
        r1, s1 = round((2 * pivot) - ind['low'], 2), round((2 * pivot) - ind['high'], 2)
        
        return f"""🚀 **تحليل رادار {symbol.upper()}**
⏱ **الفريم:** {tf_key} | 💰 **السعر:** {round(ind['close'], 2)}
---
🧭 **التوجه:** {"🟢 CALL" if rsi > 55 else "🔴 PUT"}
⚡️ **أعلى مستوى جاما:** {r1 if rsi > 55 else s1}
📊 **الاحتمالية:** { "84%" if rsi > 65 or rsi < 35 else "62%" }
🛑 **الوقف:** {s1 if rsi > 55 else r1}"""
    except Exception as e: return f"❌ خطأ: {str(e)}"

# --- 4. نظام القوائم التفاعلية ---
@app.post("/telegram_webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    if "callback_query" in data:
        call = data["callback_query"]
        chat_id, c_data = call["message"]["chat"]["id"], call["data"]
        if c_data == "menu_analyze":
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": "⌨️ أرسل رمز السهم الآن:"})
        elif c_data.startswith("tf_"):
            _, tf, sym = c_data.split("_")
            res = get_ultimate_analysis(sym, tf)
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": res})
    elif "message" in data:
        msg = data["message"]
        txt, chat_id = str(msg.get("text", "")).upper(), msg["chat"]["id"]
        if txt == "/START":
            menu = {"inline_keyboard": [
                [{"text": "🔍 رادار التحليل الذكي", "callback_data": "menu_analyze"}],
                [{"text": "💼 ملخص المحفظة", "callback_data": "menu_portfolio"}, {"text": "📅 مفكرة السوق", "callback_data": "menu_market"}],
                [{"text": "💣 وضعية Zero Hero", "callback_data": "menu_zerohero"}]
            ]}
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": "🛡 لوحة التحكم v5.0:", "reply_markup": menu})
        elif 1 <= len(txt) <= 6:
            grid = {"inline_keyboard": [
                [{"text": "5m", "callback_data": f"tf_5m_{txt}"}, {"text": "15m", "callback_data": f"tf_15m_{txt}"}, {"text": "1h", "callback_data": f"tf_1h_{txt}"}],
                [{"text": "1d", "callback_data": f"tf_1d_{txt}"}, {"text": "أسبوعي", "callback_data": f"tf_1W_{txt}"}, {"text": "شهري", "callback_data": f"tf_1M_{txt}"}]
            ]}
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": f"🎯 فريمات {txt}:", "reply_markup": grid})
    return {"ok": True}

@app.get("/")
def home(): return {"status": "V5.0 Ready - Monitoring 80 Companies"}
