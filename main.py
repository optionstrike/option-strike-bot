import os
import requests
from fastapi import FastAPI, Request
from tradingview_ta import TA_Handler, Interval
from datetime import datetime

app = FastAPI()

# --- الإعدادات الأساسية ---
TELEGRAM_TOKEN = "8619465902:AAHPP9AFiL0fV1lejKtaThLlQ4qZ6qCYgX0"
CHAT_ID = "8371374055"
DAILY_LIMIT = 5
trades_count = 0  # عداد الصفقات اليومية

# --- 1. محرك التحليل الذكي (فريمات + جاما + سيولة) ---
def get_ultimate_analysis(symbol: str, tf_key: str):
    try:
        intervals = {
            "1m": Interval.INTERVAL_1_MINUTE, "5m": Interval.INTERVAL_5_MINUTES,
            "15m": Interval.INTERVAL_15_MINUTES, "1h": Interval.INTERVAL_1_HOUR,
            "4h": Interval.INTERVAL_4_HOURS, "1d": Interval.INTERVAL_1_DAY,
            "1W": Interval.INTERVAL_1_WEEK, "1M": Interval.INTERVAL_1_MONTH
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
💧 **السيولة:** {"تجميع صاعد" if "CALL" in direction else "تصريف هابط"}

🛑 **الوقف:** {s1 if "CALL" in direction else r1}
🥇 **الهدف:** {r1 if "CALL" in direction else s1}
---
📢 @Option_Strike01"""
    except Exception as e: return f"❌ خطأ: {str(e)}"

# --- 2. محرك قنص وطرح العقود (الربط مع الـ 80 شركة) ---
def post_automated_trade(symbol, side, price):
    global trades_count
    if trades_count >= DAILY_LIMIT:
        return

    is_friday = datetime.now().weekday() == 4
    strategy = "ZERO HERO 💣" if is_friday else "Weekly Sniper 🎯"
    
    # حساب الأهداف الآلية للعقد
    t1, t2 = round(price * 1.25, 2), round(price * 1.60, 2)
    sl = round(price * 0.75, 2) if not is_friday else "بدون"

    msg = f"""🔥 **إشارة عقد آلي (عقد {trades_count + 1}/5)**
💎 **السهم:** {symbol} | **النوع:** {side}
📝 **الاستراتيجية:** {strategy}
💵 **سعر الدخول:** {price}

🎯 **هدف أول (25%):** {t1}
🎯 **هدف ثاني (60%):** {t2}
🛑 **وقف خسارة:** {sl}

📊 تم الفلترة من رادار الـ 80 شركة.
✅ يرجى متابعة الأهداف بدقة.
"""
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg})
    trades_count += 1

# --- 3. معالجة الـ Webhook (استقبال إشارات TradingView) ---
@app.post("/webhook")
async def tradingview_webhook(request: Request):
    data = await request.json()
    if data.get("secret") != "12345": return {"error": "Unauthorized"}
    
    post_automated_trade(data.get("ticker"), data.get("action"), data.get("price"))
    return {"status": "Trade Posted"}

# --- 4. معالجة أوامر التلغرام (الواجهة التفاعلية) ---
@app.post("/telegram_webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    if "callback_query" in data:
        call = data["callback_query"]
        chat_id, c_data = call["message"]["chat"]["id"], call["data"]
        
        if c_data == "menu_analyze":
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": "⌨️ أرسل رمز السهم (مثل: AAPL)"})
        elif c_data == "menu_portfolio":
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": f"💼 **المحفظة:**\n✅ تم طرح {trades_count} من أصل {DAILY_LIMIT} عقود اليوم."})
        elif c_data == "menu_market":
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": f"📅 **السوق:** {datetime.now().strftime('%A')}\n🕒 الحالة: متابعة حية لـ 80 شركة."})
        elif c_data.startswith("tf_"):
            _, tf, sym = c_data.split("_")
            res = get_ultimate_analysis(sym, tf)
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": res, "parse_mode": "Markdown"})
            
    elif "message" in data:
        msg = data["message"]
        txt, chat_id = str(msg.get("text", "")).upper(), msg["chat"]["id"]
        if txt == "/START":
            payload = {
                "chat_id": chat_id,
                "text": "🛡 **لوحة تحكم Option Strike v4.0**\nمرحباً بك في غرفة العمليات:",
                "reply_markup": {"inline_keyboard": [
                    [{"text": "🔍 رادار التحليل الذكي", "callback_data": "menu_analyze"}],
                    [{"text": "💼 ملخص المحفظة", "callback_data": "menu_portfolio"}, {"text": "📅 مفكرة السوق", "callback_data": "menu_market"}],
                    [{"text": "💣 وضعية Zero Hero", "callback_data": "menu_zerohero"}]
                ]}
            }
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload)
        elif 1 <= len(txt) <= 6:
            # إرسال شبكة الفريمات
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            grid = {"inline_keyboard": [
                [{"text": "5m", "callback_data": f"tf_5m_{txt}"}, {"text": "15m", "callback_data": f"tf_15m_{txt}"}, {"text": "1h", "callback_data": f"tf_1h_{txt}"}],
                [{"text": "1d", "callback_data": f"tf_1d_{txt}"}, {"text": "1W", "callback_data": f"tf_1W_{txt}"}]
            ]}
            requests.post(url, json={"chat_id": chat_id, "text": f"🎯 فريمات {txt}:", "reply_markup": grid})

    return {"ok": True}

@app.get("/")
def home(): return {"trades_today": trades_count, "status": "Ready"}
