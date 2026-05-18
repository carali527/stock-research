"""
台股市場資料 Core Router（非 LLM）：依使用者問題輸出 routing JSON，
供後續決定是否呼叫 Fugle、以及如何與 Gemini 組 payload。

規格重點：
- GET /intraday/candles/{symbol} 僅能提供盤中分K；日K／週K／月K／長區間日線 → capability UNSUPPORTED，不硬選 API。
"""

from __future__ import annotations

import json
import re
from typing import Any

# --- Symbol -----------------------------------------------------------------

_SYMBOL_CODE_RE = re.compile(r"\b(\d{4,6}[A-Za-z]?)\b")

_SYMBOL_ALIASES: dict[str, str] = {
    "台積電": "2330",
    "台積電公司": "2330",
    "聯發科": "2454",
    "鴻海": "2317",
}


def _normalize_symbol(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return ""
    i = t.find(".")
    return t[:i] if i > 0 else t


def extract_symbol(question: str, resolved_symbols: list[str] | None) -> str:
    """四位數以上代號 → 俗名對照 → 前端 resolvedSymbols（取第一個有效）。"""
    q = question or ""
    for m in _SYMBOL_CODE_RE.finditer(q):
        s = _normalize_symbol(m.group(1))
        if s:
            return s
    for alias, sym in _SYMBOL_ALIASES.items():
        if alias in q:
            return sym
    if resolved_symbols:
        for x in resolved_symbols:
            s = _normalize_symbol(str(x))
            if s:
                return s
    return ""


# --- Intent -----------------------------------------------------------------

_VALID_MIN_TF = frozenset({1, 3, 5, 10, 15, 30, 60})


def _extract_minute_timeframe(question: str) -> int | None:
    m = re.search(r"(\d+)\s*分\s*[kK]", question)
    if not m:
        return None
    try:
        v = int(m.group(1))
        return v if v in _VALID_MIN_TF else None
    except ValueError:
        return None


def _has_strong_technical_keyword(question: str) -> bool:
    return any(
        x in question
        for x in (
            "K線",
            "k線",
            "K棒",
            "分K",
            "技術分析",
            "OHLC",
            "OHLCV",
            "candle",
            "Candle",
            "RSI",
            "MACD",
            "均線",
            "布林",
            "KD",
        )
    )


def _market_list_trigger(question: str, symbol: str) -> bool:
    if symbol:
        return False
    q = question
    markers = (
        "股票列表",
        "有哪些股票",
        "哪些股票",
        "哪幾檔",
        "上市股票列表",
        "注意股",
        "今日注意股",
        "處置股",
        "停牌",
        "暫停交易",
        "成交量排行",
        "查產業股票",
        "上櫃股票",
        "興櫃股票",
        "上市股票",
        "金融股有哪些",
        "半導體股票",
    )
    if any(m in q for m in markers):
        return True
    if "有哪些" in q and any(x in q for x in ("ETF", "類股", "產業", "股票")):
        return True
    if "ETF" in q and any(x in q for x in ("哪些", "列表", "有什麼")):
        return True
    return False


def classify_intent(question: str, symbol: str) -> str:
    q = question

    if _market_list_trigger(q, symbol):
        return "MARKET_LIST"

    trade_kw = (
        "逐筆",
        "逐筆成交",
        "成交明細",
        "成交流水",
        "每筆成交",
        "即時成交細節",
        "主力進出",
        "主力掃單",
        "掃單",
        "大單",
        "tick",
        "Tick",
        "TICK",
    )
    if any(x in q for x in trade_kw):
        return "TRADE_FLOW"

    vol_kw = (
        "分價量",
        "volume profile",
        "Volume Profile",
        "籌碼密集區",
        "成交量分布",
        "成交量分佈",
        "成交密集",
        "哪個價位成交最多",
        "哪個價格交易最多",
    )
    if any(x in q for x in vol_kw):
        return "VOLUME_PROFILE"

    # 需在 REALTIME 之前：模板「日K…累積漲跌幅」含「漲跌幅」，若先判即時會誤打 quote
    tech_kw = (
        "日K",
        "日線",
        "交易日",
        "K線",
        "k線",
        "K棒",
        "技術分析",
        "OHLC",
        "OHLCV",
        "candle",
        "Candle",
        "支撐",
        "壓力",
        "RSI",
        "MACD",
        "均線",
        "趨勢",
        "高點",
        "低點",
        "波段",
        "量價分析",
        "量價",
        "走勢",
    )
    if any(x in q for x in tech_kw):
        return "TECHNICAL_ANALYSIS"

    quote_kw = (
        "五檔",
        "委買",
        "委賣",
        "內盤",
        "外盤",
        "即時行情",
        "即時",
        "現價",
        "現在多少",
        "多少錢",
        "最新成交",
        "最後成交",
        "即時價",
        "現在價",
        "最新價格",
        "最新報價",
        "漲跌幅",
        "bid",
        "ask",
        "Bid",
        "Ask",
        "買盤",
        "賣盤",
        "目前盤勢",
        "即時成交量",
    )
    if any(x in q for x in quote_kw):
        return "REALTIME_QUOTE"

    ticker_kw = (
        "基本資料",
        "股票資訊",
        "漲停",
        "跌停",
        "當沖",
        "previousClose",
        "referencePrice",
        "securityStatus",
        "證券別",
        "可不可以當沖",
        "什麼產業",
        "哪個產業",
        "屬於什麼產業",
        "產業別",
        "哪一種產業",
        "是 ETF",
        "ETF嗎",
        "股票狀態",
    )
    if symbol and any(k in q for k in ticker_kw) and not _has_strong_technical_keyword(q):
        return "TICKER_INFO"

    if any(x in q for x in ("漲停", "跌停", "當沖", "基本資料", "股票資訊")):
        return "TICKER_INFO"

    if symbol:
        return "TECHNICAL_ANALYSIS"
    return "MARKET_LIST"


# --- Timeframe & capability (intraday candles only for TECHNICAL) ------------


def _extract_chart_timeframe_token(question: str) -> str | None:
    """回傳規格中的 timeframe 標記：1d / 1w / 1m；分鐘改由 _extract_minute_timeframe 處理。"""
    q = question
    if "日K" in q or "日線" in q:
        return "1d"
    if "週K" in q or "周K" in q:
        return "1w"
    if "月K" in q or "月線" in q:
        return "1m"
    return None


def _extract_required_period(question: str) -> str | None:
    q = question
    if "三個月" in q or "3個月" in q:
        return "3 months"
    if "半年" in q or "六個月" in q or "6個月" in q:
        return "6 months"
    if "一年" in q or "12個月" in q:
        return "1 year"
    if "兩年" in q:
        return "2 years"
    return None


def _intraday_candles_unsupported(question: str) -> tuple[bool, str]:
    """
    /intraday/candles 僅盤中分K。
    補捉未帶明確日K／週K／月K字樣、但仍屬長區間日線語意之情況。
    """
    q = question
    if _extract_minute_timeframe(q) is not None:
        return (False, "")
    if _extract_chart_timeframe_token(q) in ("1d", "1w", "1m"):
        return (False, "")
    if _extract_required_period(q):
        return (False, "")

    if ("還原" in q or "歷史" in q) and any(k in q for k in ("日線", "日K", "收盤價", "日收")):
        return (True, "/intraday/candles 僅支援盤中分K，無法提供長區間歷史日線")

    return (False, "")


def _required_fields(intent: str, question: str) -> list[str]:
    q = question
    if intent == "REALTIME_QUOTE":
        if any(x in q for x in ("五檔", "委買", "委賣")):
            return ["bids", "asks"]
        if "漲跌幅" in q:
            return ["changePercent", "lastPrice"]
        return ["lastTrade", "lastPrice", "total"]
    if intent == "TECHNICAL_ANALYSIS":
        return ["date", "open", "high", "low", "close", "volume"]
    if intent == "TICKER_INFO":
        out = ["previousClose", "referencePrice", "limitUpPrice", "limitDownPrice", "canDayTrade"]
        if any(x in q for x in ("產業", "類股")):
            out.append("industry")
        return out
    if intent == "TRADE_FLOW":
        return ["price", "size", "volume", "time"]
    if intent == "VOLUME_PROFILE":
        return ["price", "volume", "volumeAtBid", "volumeAtAsk"]
    if intent == "MARKET_LIST":
        return ["symbol", "name"]
    return []


def _api_template(intent: str) -> str | None:
    return {
        "MARKET_LIST": "/intraday/tickers",
        "TICKER_INFO": "/intraday/ticker/{symbol}",
        "REALTIME_QUOTE": "/intraday/quote/{symbol}",
        "TECHNICAL_ANALYSIS": "/intraday/candles/{symbol}",
        "TRADE_FLOW": "/intraday/trades/{symbol}",
        "VOLUME_PROFILE": "/intraday/volumes/{symbol}",
    }.get(intent)


def _endpoint_for(intent: str, symbol: str) -> str | None:
    tpl = _api_template(intent)
    if not tpl:
        return None
    if "{symbol}" in tpl:
        if not symbol:
            return None
        return tpl.replace("{symbol}", symbol)
    return tpl


def route_fugle_market_data(*, question: str, resolved_symbols: list[str] | None = None) -> dict[str, Any]:
    """
    產出 routing JSON（dict）。規格欄位與 capability 規則見模組 docstring。
    """
    q = (question or "").strip()
    symbol = extract_symbol(q, resolved_symbols)
    intent = classify_intent(q, symbol)

    base: dict[str, Any] = {
        "need_market_data": True,
        "intent": intent,
        "symbol": symbol or None,
        "timeframe": None,
        "required_fields": _required_fields(intent, q),
        "required_period": None,
        "api": None,
        "capability_status": "SUPPORTED",
        "reason": "",
        "next_action": None,
        "gemini_payload": None,
    }

    needs_symbol = intent != "MARKET_LIST"
    if needs_symbol and not symbol:
        base["capability_status"] = "UNSUPPORTED"
        base["reason"] = "此 intent 需要股票代號（symbol），問題中無法解析代號且無 resolved_symbols。"
        base["api"] = None
        base["gemini_payload"] = None
        return base

    api_tpl = _api_template(intent)
    base["api"] = api_tpl

    if intent == "TECHNICAL_ANALYSIS":
        minute_tf = _extract_minute_timeframe(q)
        chart_tf = _extract_chart_timeframe_token(q)
        period = _extract_required_period(q)

        if minute_tf is not None:
            base["timeframe"] = str(minute_tf)
        elif chart_tf:
            base["timeframe"] = chart_tf
            if period:
                base["required_period"] = period
        elif period:
            base["timeframe"] = "1d"
            base["required_period"] = period
        else:
            base["timeframe"] = "1"

        unsupported = False
        reason = ""
        if minute_tf is None:
            if chart_tf in ("1d", "1w", "1m"):
                unsupported = True
                if period == "3 months" and chart_tf == "1d":
                    reason = "/intraday/candles 僅支援盤中分K，無法提供三個月日K"
                else:
                    reason = "/intraday/candles 僅支援盤中分K，無法提供日K／週K／月K"
            elif period is not None:
                unsupported = True
                reason = "/intraday/candles 僅支援盤中分K，無法提供多日／多個月歷史日線"
            else:
                extra_unsup, extra_reason = _intraday_candles_unsupported(q)
                if extra_unsup:
                    unsupported = True
                    reason = extra_reason

        if unsupported:
            base["capability_status"] = "UNSUPPORTED"
            base["reason"] = reason
            base["api"] = None
            base["next_action"] = None
            base["gemini_payload"] = None
            return base

    ep = _endpoint_for(intent, symbol)
    if base["capability_status"] == "SUPPORTED" and ep:
        base["next_action"] = {
            "type": "CALL_FUGLE_API",
            "endpoint": ep,
            "method": "GET",
        }
        base["gemini_payload"] = {
            "question": q,
            "data_source": "FUGLE_API_RESPONSE",
        }

    return base


def route_fugle_market_data_json(*, question: str, resolved_symbols: list[str] | None = None) -> str:
    """僅 JSON 字串（無 Markdown），方便記錄或傳輸。"""
    return json.dumps(route_fugle_market_data(question=question, resolved_symbols=resolved_symbols), ensure_ascii=False)
