
"""
Bot SPX / SPXW
----------------
FastAPI bot for Telegram + Polygon/Massive market data.

IMPORTANT:
- Put secrets in environment variables, not inside this file.
- This script is intentionally defensive and logs gracefully.
- Direction model uses a configurable market proxy symbol (default: SPY)
  and executes on SPX index options (underlying: I:SPX).

Required env vars:
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHAT_ID=...
    MARKET_API_KEY=...

Optional env vars:
    APP_HOST=0.0.0.0
    APP_PORT=8000
    TIMEZONE=Asia/Riyadh
    MARKET_DIRECTION_SYMBOL=SPY
    OPTIONS_UNDERLYING=I:SPX
    STRATEGY_MIN_PRICE=0.50
    STRATEGY_MAX_PRICE=1.50
    MAX_CONTRACT_PRICE=3.70
    STRIKE_STEP_FILTER=5
    ENTRY_GAP_MAX=0.60
    SUCCESS_THRESHOLD=60
    MAX_CHAIN_LIMIT=250
"""

from __future__ import annotations

import asyncio
import html
import logging
import math
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI
from pydantic import BaseModel


# =========================
# Config
# =========================

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
TIMEZONE = os.getenv("TIMEZONE", "Asia/Riyadh")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
MARKET_API_KEY = os.getenv("MARKET_API_KEY", "").strip()

MARKET_DIRECTION_SYMBOL = os.getenv("MARKET_DIRECTION_SYMBOL", "SPY").strip().upper()
OPTIONS_UNDERLYING = os.getenv("OPTIONS_UNDERLYING", "I:SPX").strip().upper()

STRATEGY_MIN_PRICE = float(os.getenv("STRATEGY_MIN_PRICE", "0.50"))
STRATEGY_MAX_PRICE = float(os.getenv("STRATEGY_MAX_PRICE", "1.50"))
MAX_CONTRACT_PRICE = float(os.getenv("MAX_CONTRACT_PRICE", "3.70"))
STRIKE_STEP_FILTER = float(os.getenv("STRIKE_STEP_FILTER", "5"))
ENTRY_GAP_MAX = float(os.getenv("ENTRY_GAP_MAX", "0.60"))
SUCCESS_THRESHOLD = int(os.getenv("SUCCESS_THRESHOLD", "60"))
MAX_CHAIN_LIMIT = int(os.getenv("MAX_CHAIN_LIMIT", "250"))

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
MASSIVE_BASE = "https://api.polygon.io"
HTTP_TIMEOUT = 20

RIYADH = ZoneInfo(TIMEZONE)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("bot-spx")


# =========================
# Schedules
# =========================

STRATEGY_TIMES = {"14:00", "16:00", "18:00", "20:00", "22:00"}
DAILY_TIMES = {
    "04:30", "09:00", "14:00", "16:00", "16:30", "17:00", "17:30",
    "18:00", "19:00", "20:00", "20:30", "21:00", "21:30", "22:00", "22:30"
}

# 4:30 AM is pre-market setup
PREMARKET_TIMES = {"04:30"}

sent_slots: set[str] = set()
contracts_open: List[Dict[str, Any]] = []
contracts_closed: List[Dict[str, Any]] = []
daily_reports: List[Dict[str, Any]] = []
strategy_reports: List[Dict[str, Any]] = []
app_task: Optional[asyncio.Task] = None


# =========================
# Models
# =========================

class ManualRunRequest(BaseModel):
    mode: str = "daily"  # daily | strategy
    now_override: Optional[str] = None  # ISO datetime in Riyadh time


@dataclass
class PivotPlan:
    pivot: float
    call_tp1: float
    call_tp2: float
    call_tp3: float
    put_tp1: float
    put_tp2: float
    put_tp3: float
    range_value: float


@dataclass
class MarketState:
    symbol: str
    price: float
    prev_close: float
    daily_high: float
    daily_low: float
    daily_open: float
    pct_change: float
    strongest_direction: str  # CALL | PUT | NEUTRAL
    confidence: int
    risk: str
    reason: str


@dataclass
class ContractCandidate:
    ticker: str
    contract_type: str  # call | put
    strike_price: float
    expiration_date: str
    entry_price: float
    entry_low: float
    entry_high: float
    tp1: float
    tp2: float
    tp3: float
    stop_rule: str
    success_rate: int
    risk: str
    opportunity_type: str
    source_underlying_price: float
    open_interest: int
    delta: Optional[float]
    gamma: Optional[float]
    iv: Optional[float]


# =========================
# Helpers
# =========================

def now_riyadh() -> datetime:
    return datetime.now(RIYADH)

def today_str() -> str:
    return now_riyadh().date().isoformat()

def req(url: str, params: Optional[dict] = None) -> dict:
    params = params or {}
    params["apiKey"] = MARKET_API_KEY
    res = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
    res.raise_for_status()
    return res.json()

def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default

def clamp(n: int, low: int, high: int) -> int:
    return max(low, min(high, n))

def round_up_to_step(value: float, step: float) -> float:
    return math.ceil(value / step) * step

def round_down_to_step(value: float, step: float) -> float:
    return math.floor(value / step) * step

def escape_html(text: str) -> str:
    return html.escape(text, quote=False)

def get_expiry_candidates() -> List[str]:
    today = now_riyadh().date()
    return [(today + timedelta(days=i)).isoformat() for i in range(0, 5)]

def format_contract_type(ct: str) -> str:
    return "كول (CALL)" if ct.lower() == "call" else "بوت (PUT)"

def direction_emoji(ct: str) -> str:
    return "🟢" if ct.lower() == "call" else "🔴"

def build_tradingview_option_symbol(contract_ticker: str) -> str:
    # If Polygon returns O:SPXW260423P07040000 -> SPXW260423P7040.0
    raw = contract_ticker.replace("O:", "")
    try:
        under = raw[:-15]
        yy = raw[-15:-13]
        mm = raw[-13:-11]
        dd = raw[-11:-9]
        cp = raw[-9:-8]
        strike_millis = int(raw[-8:])
        strike = strike_millis / 1000
        return f"{under}{yy}{mm}{dd}{cp}{strike:.1f}"
    except Exception:
        return raw

def calc_pivot_from_bar(high: float, low: float, close: float) -> PivotPlan:
    range_value = high - low
    pivot = (high + low + close) / 3.0
    return PivotPlan(
        pivot=round(pivot, 2),
        call_tp1=round(pivot + (range_value * 0.5), 2),
        call_tp2=round(pivot + range_value, 2),
        call_tp3=round(high + range_value, 2),
        put_tp1=round(pivot - (range_value * 0.5), 2),
        put_tp2=round(pivot - range_value, 2),
        put_tp3=round(low - range_value, 2),
        range_value=round(range_value, 2),
    )

def compute_confidence(price: float, pivot: float, range_value: float, gamma_bias: float = 0.0) -> int:
    if range_value <= 0:
        return 55
    distance = abs(price - pivot)
    distance_score = min(20, int((distance / max(range_value, 0.1)) * 20))
    gamma_score = int(max(-10, min(10, gamma_bias)))
    base = 60 + distance_score + gamma_score
    return clamp(base, 50, 92)

def market_risk(confidence: int) -> str:
    if confidence >= 80:
        return "منخفضة"
    if confidence >= 68:
        return "متوسطة"
    return "عالية"

def option_price_from_snapshot(item: dict) -> float:
    for path in [
        ("last_quote", "midpoint"),
        ("last_quote", "ask"),
        ("last_trade", "price"),
        ("day", "close"),
    ]:
        cur = item
        ok = True
        for key in path:
            cur = cur.get(key) if isinstance(cur, dict) else None
            if cur is None:
                ok = False
                break
        if ok:
            return safe_float(cur)
    bid = safe_float(item.get("last_quote", {}).get("bid"))
    ask = safe_float(item.get("last_quote", {}).get("ask"))
    if bid > 0 and ask > 0:
        return round((bid + ask) / 2, 2)
    return 0.0

def entry_range(price: float) -> Tuple[float, float]:
    hi = round(price, 2)
    lo = round(max(0.01, price - ENTRY_GAP_MAX), 2)
    return lo, hi

def target_ladder(price: float, opportunity_type: str) -> Tuple[float, float, float]:
    if opportunity_type == "strategy":
        return round(price * 1.40, 2), round(price * 2.00, 2), round(price * 3.00, 2)
    return round(price * 1.25, 2), round(price * 1.50, 2), round(price * 1.75, 2)

def stop_rule_for_type(contract_type: str) -> str:
    if contract_type.lower() == "call":
        return "إغلاق شمعة ساعة تحت الارتكاز ❌"
    return "إغلاق شمعة ساعة فوق الارتكاز ❌"


# =========================
# Data access
# =========================

def get_previous_daily_bar(symbol: str) -> dict:
    end_date = now_riyadh().date()
    start_date = end_date - timedelta(days=10)
    url = f"{MASSIVE_BASE}/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}"
    data = req(url, {"adjusted": "true", "sort": "desc", "limit": 10})
    results = data.get("results", [])
    if len(results) < 2:
        raise RuntimeError(f"Not enough daily bars for {symbol}")
    # last complete prior bar:
    return results[1]

def get_current_market_state() -> Tuple[MarketState, PivotPlan]:
    prev_bar = get_previous_daily_bar(MARKET_DIRECTION_SYMBOL)

    prev_high = safe_float(prev_bar.get("h"))
    prev_low = safe_float(prev_bar.get("l"))
    prev_close = safe_float(prev_bar.get("c"))

    plan = calc_pivot_from_bar(prev_high, prev_low, prev_close)

    # Use last trade snapshot if available, else fall back to previous close
    snap = req(
        f"{MASSIVE_BASE}/v3/snapshot",
        {"ticker.any_of": MARKET_DIRECTION_SYMBOL}
    )
    results = snap.get("results", [])
    item = results[0] if results else {}
    session = item.get("session", {}) if isinstance(item, dict) else {}

    price = safe_float(session.get("price") or session.get("close"), prev_close)
    daily_open = safe_float(session.get("open"), prev_close)
    daily_high = safe_float(session.get("high"), prev_high)
    daily_low = safe_float(session.get("low"), prev_low)
    pct_change = safe_float(session.get("change_percent"), 0.0)

    if price > plan.pivot:
        strongest_direction = "CALL"
        reason = "السعر فوق الارتكاز واتجاه اليوم إيجابي"
    elif price < plan.pivot:
        strongest_direction = "PUT"
        reason = "السعر تحت الارتكاز واتجاه اليوم سلبي"
    else:
        strongest_direction = "NEUTRAL"
        reason = "السعر قريب جدًا من الارتكاز"

    confidence = compute_confidence(price, plan.pivot, plan.range_value, gamma_bias=0)
    risk = market_risk(confidence)

    return (
        MarketState(
            symbol=MARKET_DIRECTION_SYMBOL,
            price=round(price, 2),
            prev_close=round(prev_close, 2),
            daily_high=round(daily_high, 2),
            daily_low=round(daily_low, 2),
            daily_open=round(daily_open, 2),
            pct_change=round(pct_change, 2),
            strongest_direction=strongest_direction,
            confidence=confidence,
            risk=risk,
            reason=reason,
        ),
        plan,
    )

def fetch_option_chain(expiration_date: str, contract_type: str) -> List[dict]:
    data = req(
        f"{MASSIVE_BASE}/v3/snapshot/options/{OPTIONS_UNDERLYING}",
        {
            "expiration_date": expiration_date,
            "contract_type": contract_type.lower(),
            "limit": MAX_CHAIN_LIMIT,
            "sort": "strike_price",
            "order": "asc",
        },
    )
    return data.get("results", []) or []

def filter_chain_for_bot(items: List[dict], market_state: MarketState, mode: str) -> List[ContractCandidate]:
    out: List[ContractCandidate] = []

    target_type = "call" if market_state.strongest_direction == "CALL" else "put"
    if market_state.strongest_direction == "NEUTRAL":
        return out

    underlying_price = market_state.price
    step = STRIKE_STEP_FILTER if STRIKE_STEP_FILTER > 0 else 5

    for item in items:
        details = item.get("details", {}) or {}
        greeks = item.get("greeks", {}) or {}

        if details.get("contract_type", "").lower() != target_type:
            continue

        strike = safe_float(details.get("strike_price"))
        if strike <= 0:
            continue

        # nearest OTM/ATM logic
        if target_type == "call" and strike < round_up_to_step(underlying_price, step):
            continue
        if target_type == "put" and strike > round_down_to_step(underlying_price, step):
            continue

        price = option_price_from_snapshot(item)
        if price <= 0:
            continue

        if mode == "strategy":
            if not (STRATEGY_MIN_PRICE <= price <= STRATEGY_MAX_PRICE):
                continue
            opportunity_type = "strategy"
        else:
            if price > MAX_CONTRACT_PRICE:
                continue
            opportunity_type = "daily"

        entry_low, entry_high = entry_range(price)
        if round(entry_high - entry_low, 2) > ENTRY_GAP_MAX:
            continue

        open_interest = int(safe_float(item.get("open_interest"), 0))
        delta = greeks.get("delta")
        gamma = greeks.get("gamma")
        iv = item.get("implied_volatility")

        # basic quality score
        score = 0
        score += min(20, open_interest // 100)
        score += 8 if delta is not None else 0
        score += 8 if gamma is not None else 0
        score += 10 if price <= MAX_CONTRACT_PRICE else 0
        score += 6 if abs(strike - underlying_price) <= 15 else 0

        success_rate = clamp(SUCCESS_THRESHOLD + score // 4, 60, 90)
        risk = "منخفضة" if success_rate >= 80 else "متوسطة" if success_rate >= 70 else "عالية"
        tp1, tp2, tp3 = target_ladder(price, opportunity_type)

        out.append(
            ContractCandidate(
                ticker=details.get("ticker", ""),
                contract_type=target_type,
                strike_price=round(strike, 2),
                expiration_date=details.get("expiration_date", expiration_date),
                entry_price=round(price, 2),
                entry_low=entry_low,
                entry_high=entry_high,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                stop_rule=stop_rule_for_type(target_type),
                success_rate=success_rate,
                risk=risk,
                opportunity_type=opportunity_type,
                source_underlying_price=round(underlying_price, 2),
                open_interest=open_interest,
                delta=round(delta, 4) if isinstance(delta, (int, float)) else None,
                gamma=round(gamma, 4) if isinstance(gamma, (int, float)) else None,
                iv=round(iv, 4) if isinstance(iv, (int, float)) else None,
            )
        )

    # sort by closeness to underlying, then liquidity
    out.sort(
        key=lambda x: (
            abs(x.strike_price - x.source_underlying_price),
            -x.open_interest,
            x.entry_price,
        )
    )
    return out

def pick_best_contract(mode: str) -> Optional[Tuple[MarketState, PivotPlan, ContractCandidate]]:
    market_state, pivot_plan = get_current_market_state()

    if market_state.strongest_direction == "NEUTRAL":
        return None

    expiries = get_expiry_candidates()
    contract_type = "call" if market_state.strongest_direction == "CALL" else "put"

    for expiry in expiries:
        try:
            chain = fetch_option_chain(expiry, contract_type)
            filtered = filter_chain_for_bot(chain, market_state, mode=mode)
            if filtered:
                return market_state, pivot_plan, filtered[0]
        except Exception as exc:
            logger.warning("Chain fetch failed for %s %s: %s", expiry, contract_type, exc)

    return None


# =========================
# Telegram formatting
# =========================

def build_bot_spacs_report(
    market_state: MarketState,
    pivot_plan: PivotPlan,
    contract: ContractCandidate,
    is_premarket: bool = False,
) -> str:
    trade_symbol = build_tradingview_option_symbol(contract.ticker)
    direction_ar = "CALL" if contract.contract_type == "call" else "PUT"
    opportunity_ar = "استراتيجية" if contract.opportunity_type == "strategy" else "يومية"

    lines = [
        "🤖 <b>بوت سباكس | Option Strike</b>",
        "",
        f"1. الاتجاه العام للسوق (US500): <b>{escape_html(market_state.strongest_direction)}</b>",
        f"2. القاما والسيولة: {'موجودة' if contract.gamma is not None else 'غير مكتملة'} | OI {contract.open_interest}",
        f"3. نقطة الارتكاز (Pivot): <b>{pivot_plan.pivot}</b>",
        f"4. سيناريو الصعود (CALL): فوق {pivot_plan.pivot} → {pivot_plan.call_tp1} / {pivot_plan.call_tp2} / {pivot_plan.call_tp3}",
        f"5. سيناريو الهبوط (PUT): تحت {pivot_plan.pivot} → {pivot_plan.put_tp1} / {pivot_plan.put_tp2} / {pivot_plan.put_tp3}",
        f"6. نطاق أسعار العقود: <b>{contract.entry_low} - {contract.entry_high}</b>",
        f"7. أفضل سترايك: <b>{contract.strike_price}</b>",
        f"8. الأهداف (TP1 / TP2 / TP3): <b>{contract.tp1}</b> / <b>{contract.tp2}</b> / <b>{contract.tp3}</b>",
        f"9. الوقف: {escape_html(contract.stop_rule)}",
        f"10. التوقيت الأفضل للدخول: {'Pre-Market Setup' if is_premarket else 'عند تأكيد الاتجاه'}",
        f"11. نوع الفرصة: <b>{opportunity_ar}</b>",
        f"12. نسبة النجاح: <b>{contract.success_rate}%</b>",
        f"13. المخاطر: <b>{escape_html(contract.risk)}</b>",
        f"14. التوصية النهائية: <b>{direction_ar}</b>",
        f"15. صيد عقود الاستراتيجية: {'مفعل' if contract.opportunity_type == 'strategy' else 'غير مطبق في هذا الطرح'}",
        f"16. صيد القمم والقيعان: {'قاع = CALL / قمة = PUT'}",
        f"17. نظام التقارير: يومي / أسبوعي / شهري / سنوي + أرشفة",
        f"18. تقرير خاص لعقود الاستراتيجية: {'جاهز' if contract.opportunity_type == 'strategy' else 'لا'}",
        f"19. تحديد الاتجاه اليومي من US500: <b>{market_state.reason}</b>",
        f"20. فلترة الأسعار: ≤ {MAX_CONTRACT_PRICE} + فرق تنفيذ {ENTRY_GAP_MAX}",
        f"21. أوقات طرح عقود الاستراتيجية: 2 / 4 / 6 / 8 / 10",
        f"22. أوقات طرح العقود اليومية: 15 عقد من 4:30 فجرًا إلى 10:30 مساءً",
        f"23. جميع العقود تعتمد على US500: <b>نعم</b>",
        f"24. طرح 4:30 فجرًا (Pre-Market Setup): {'نعم' if is_premarket else 'لا'}",
        f"25. تحديث تلقائي للعقود: <b>مفعل</b>",
        f"26. سجل العقود: مفتوحة / مغلقة",
        "",
        f"📊 السعر المرجعي: {market_state.price}",
        f"🧭 الرمز التحليلي: {escape_html(MARKET_DIRECTION_SYMBOL)}",
        f"🧾 عقد TradingView: <code>{escape_html(trade_symbol)}</code>",
        "",
        "⚠️ تنبيه: هذا الطرح تعليمي وليس توصية استثمارية، والقرار النهائي يعود للمتداول",
        "📢 @Option_Strike01",
    ]
    return "\n".join(lines)

def build_new_trade_post(contract: ContractCandidate) -> str:
    symbol_name = "SPXW – S&P 500"
    return "\n".join([
        f"🆕 طرح جديد | {symbol_name}",
        "",
        f"{direction_emoji(contract.contract_type)} النوع: {format_contract_type(contract.contract_type)}",
        f"🎯 السترايك: ${contract.strike_price}",
        f"📅 التاريخ: {contract.expiration_date}",
        "",
        "💰 أسعار التنفيذ:",
        f"من {contract.entry_high:.2f} إلى {contract.entry_low:.2f}",
        "",
        "📈 الأهداف:",
        f"🥇 الهدف الأول: {contract.tp1:.2f}",
        f"🥈 الهدف الثاني: {contract.tp2:.2f}",
        f"🥉 الهدف الثالث: {contract.tp3:.2f}",
        "",
        f"🛑 الوقف: {contract.stop_rule}",
        "",
        "⚠️ تنبيه: هذا الطرح تعليمي وليس توصية استثمارية، والقرار النهائي يعود للمتداول",
        "",
        "📢 @Option_Strike01",
    ])

def build_update_post(contract: ContractCandidate, high_price: float) -> str:
    profit_pct = ((high_price - contract.entry_price) / contract.entry_price) * 100 if contract.entry_price > 0 else 0
    title = f"🔔 تحديث | SPXW ${contract.strike_price} {'كول' if contract.contract_type == 'call' else 'بوت'}"
    return "\n".join([
        title,
        "",
        f"📊 سعر الدخول: {contract.entry_price:.2f}",
        f"💰 الأعلى المحقق: {high_price:.2f}",
        f"📈 نسبة الربح: +{profit_pct:.2f}%",
        "",
        "⚠️ تنبيه: هذا الطرح تعليمي",
        "والقرار النهائي يعود للمتداول.",
        "",
        "📢 @Option_Strike01.",
    ])


# =========================
# Telegram sender
# =========================

def send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram token/chat id missing. Skipping send.")
        return False

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    res = requests.post(TELEGRAM_API, json=payload, timeout=HTTP_TIMEOUT)
    if not res.ok:
        logger.error("Telegram error %s: %s", res.status_code, res.text)
        return False
    return True


# =========================
# Core execution
# =========================

def register_open_contract(contract: ContractCandidate, mode: str) -> None:
    contracts_open.append({
        "ticker": contract.ticker,
        "strike_price": contract.strike_price,
        "contract_type": contract.contract_type,
        "expiration_date": contract.expiration_date,
        "entry_price": contract.entry_price,
        "tp1": contract.tp1,
        "tp2": contract.tp2,
        "tp3": contract.tp3,
        "mode": mode,
        "opened_at": now_riyadh().isoformat(),
        "status": "open",
    })

def maybe_close_contracts() -> None:
    still_open = []
    for row in contracts_open:
        try:
            data = req(
                f"{MASSIVE_BASE}/v3/snapshot/options/{OPTIONS_UNDERLYING}",
                {
                    "expiration_date": row["expiration_date"],
                    "contract_type": row["contract_type"],
                    "strike_price": row["strike_price"],
                    "limit": 5,
                },
            )
            results = data.get("results", [])
            found = None
            for item in results:
                details = item.get("details", {})
                if details.get("ticker") == row["ticker"]:
                    found = item
                    break

            if not found:
                still_open.append(row)
                continue

            current_price = option_price_from_snapshot(found)
            if current_price <= 0:
                still_open.append(row)
                continue

            if current_price >= row["tp3"] or current_price <= max(0.01, row["entry_price"] * 0.5):
                row["closed_at"] = now_riyadh().isoformat()
                row["close_price"] = round(current_price, 2)
                row["status"] = "closed"
                contracts_closed.append(row)
            else:
                row["last_price"] = round(current_price, 2)
                still_open.append(row)
        except Exception as exc:
            logger.warning("Contract update failed: %s", exc)
            still_open.append(row)

    contracts_open[:] = still_open

def run_bot(mode: str = "daily", force_time: Optional[datetime] = None) -> Dict[str, Any]:
    current_dt = force_time or now_riyadh()
    slot = current_dt.strftime("%Y-%m-%d %H:%M")

    result = pick_best_contract(mode=mode)
    if not result:
        msg = f"⏸️ لا توجد فرصة مطابقة الآن | {mode} | {slot}"
        send_telegram(msg)
        return {"ok": False, "message": msg}

    market_state, pivot_plan, contract = result
    is_premarket = current_dt.strftime("%H:%M") in PREMARKET_TIMES

    report = build_bot_spacs_report(market_state, pivot_plan, contract, is_premarket=is_premarket)
    trade_post = build_new_trade_post(contract)

    send_telegram(report)
    send_telegram(f"<pre>{escape_html(trade_post)}</pre>")

    register_open_contract(contract, mode=mode)

    row = {
        "slot": slot,
        "mode": mode,
        "market_state": asdict(market_state),
        "pivot_plan": asdict(pivot_plan),
        "contract": asdict(contract),
    }

    if mode == "strategy":
        strategy_reports.append(row)
    else:
        daily_reports.append(row)

    return {"ok": True, "slot": slot, "mode": mode, "contract": asdict(contract)}

async def scheduler_loop() -> None:
    logger.info("Scheduler loop started")
    while True:
        try:
            now_dt = now_riyadh()
            hhmm = now_dt.strftime("%H:%M")
            slot_key = now_dt.strftime("%Y-%m-%d %H:%M")

            if hhmm in DAILY_TIMES and slot_key not in sent_slots:
                mode = "strategy" if hhmm in STRATEGY_TIMES else "daily"
                logger.info("Running scheduled mode=%s slot=%s", mode, slot_key)
                run_bot(mode=mode, force_time=now_dt)
                sent_slots.add(slot_key)

            maybe_close_contracts()

            # clear old sent slots daily
            old_prefix = (now_dt - timedelta(days=2)).strftime("%Y-%m-%d")
            sent_slots_copy = set(sent_slots)
            for item in sent_slots_copy:
                if item.startswith(old_prefix):
                    sent_slots.discard(item)

        except Exception as exc:
            logger.exception("Scheduler loop error: %s", exc)

        await asyncio.sleep(20)


# =========================
# FastAPI app
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global app_task
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if not MARKET_API_KEY:
        missing.append("MARKET_API_KEY")

    if missing:
        logger.warning("Missing environment variables: %s", ", ".join(missing))
    app_task = asyncio.create_task(scheduler_loop())
    yield
    if app_task:
        app_task.cancel()
        try:
            await app_task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="Bot Spacs SPX", version="1.0.0", lifespan=lifespan)


@app.get("/")
def root():
    return {
        "ok": True,
        "name": "Bot Spacs SPX",
        "timezone": TIMEZONE,
        "direction_symbol": MARKET_DIRECTION_SYMBOL,
        "options_underlying": OPTIONS_UNDERLYING,
        "daily_times": sorted(list(DAILY_TIMES)),
        "strategy_times": sorted(list(STRATEGY_TIMES)),
    }

@app.get("/health")
def health():
    return {
        "ok": True,
        "time": now_riyadh().isoformat(),
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "market_api_configured": bool(MARKET_API_KEY),
        "open_contracts": len(contracts_open),
        "closed_contracts": len(contracts_closed),
    }

@app.get("/status")
def status():
    market_state, pivot_plan = get_current_market_state()
    return {
        "market_state": asdict(market_state),
        "pivot_plan": asdict(pivot_plan),
        "open_contracts": contracts_open[-10:],
        "closed_contracts": contracts_closed[-10:],
    }

@app.post("/run")
def manual_run(payload: ManualRunRequest):
    force_dt = None
    if payload.now_override:
        force_dt = datetime.fromisoformat(payload.now_override)
        if force_dt.tzinfo is None:
            force_dt = force_dt.replace(tzinfo=RIYADH)
        else:
            force_dt = force_dt.astimezone(RIYADH)

    return manual_run_impl(payload.mode, force_dt)

def manual_run_impl(mode: str, force_dt: Optional[datetime]):
    mode = mode.lower().strip()
    if mode not in {"daily", "strategy"}:
        return {"ok": False, "error": "mode must be daily or strategy"}
    return run_bot(mode=mode, force_time=force_dt)

@app.get("/report/daily")
def report_daily():
    return {"count": len(daily_reports), "items": daily_reports[-20:]}

@app.get("/report/strategy")
def report_strategy():
    return {"count": len(strategy_reports), "items": strategy_reports[-20:]}

@app.get("/contracts/open")
def contracts_open_view():
    return {"count": len(contracts_open), "items": contracts_open}

@app.get("/contracts/closed")
def contracts_closed_view():
    return {"count": len(contracts_closed), "items": contracts_closed}

@app.get("/sample-post")
def sample_post():
    result = pick_best_contract(mode="daily")
    if not result:
        return {"ok": False, "message": "No contract found"}
    market_state, pivot_plan, contract = result
    return {
        "bot_report": build_bot_spacs_report(market_state, pivot_plan, contract),
        "new_trade_post": build_new_trade_post(contract),
        "tradingview_symbol": build_tradingview_option_symbol(contract.ticker),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)
