"""
後端直接呼叫 Fugle Market Data REST（不依賴 Gemini Router）。
需在 backend/.env.local 設定 FUGLE_API_KEY（或與前端相同的金鑰變數）。
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from request_trace import log_json

logger = logging.getLogger(__name__)

FUGLE_BASE = "https://api.fugle.tw"
FUGLE_KEY = (os.getenv("FUGLE_API_KEY") or os.getenv("VITE_FUGLE_API_KEY") or "").strip()
HEADER_KEY = "X-API-KEY"


def _taipei_today_ymd() -> str:
    return datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")


def _normalize_symbol(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return ""
    i = t.find(".")
    if i > 0:
        return t[:i]
    return t


def resolve_symbol(structured: dict[str, Any], safe_data: dict[str, Any]) -> str:
    s = _normalize_symbol(str(structured.get("symbol") or ""))
    if s:
        return s
    rs = safe_data.get("resolvedSymbols")
    if isinstance(rs, list):
        for x in rs:
            sx = _normalize_symbol(str(x))
            if sx:
                return sx
    return ""


_VALID_MIN_TF = frozenset({1, 3, 5, 10, 15, 30, 60})


def _extract_minute_timeframe(question: str) -> int | None:
    m = re.search(r"(\d+)\s*分\s*[kK]", question)
    if m:
        try:
            v = int(m.group(1))
            if v in _VALID_MIN_TF:
                return v
        except ValueError:
            pass
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
    """列表／篩選：無單一標的時才走 tickers（避免『2330 產業』誤判）。"""
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


def classify_fugle_intent(question: str, symbol: str) -> str:
    """
    問題類型 → 預抓 API（與 Fugle REST 對照）。
    順序：列表 → 逐筆 → 分價量 → K線技術 → 即時行情 → 基本資料／漲跌停 → 有代號預設技術 → 無代號列表。
    （技術需在即時之前，避免「日K＋漲跌幅」誤判為 quote。）
    """
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


def _wants_daily_historical_candles(question: str) -> bool:
    """日／週／月或長區間 → historical/candles；否則用 intraday/candles（分鐘 K）。"""
    if _extract_minute_timeframe(question) is not None:
        return False
    q = question
    daily_kw = (
        "日K",
        "日線",
        "週K",
        "周K",
        "月K",
        "月線",
        "三個月",
        "半年",
        "一年",
        "近年",
        "歷史",
        "還原",
        "長線",
    )
    return any(k in q for k in daily_kw)


def _historical_timeframe_for_question(question: str) -> str:
    if "週K" in question or "周K" in question:
        return "W"
    if "月K" in question or "月線" in question:
        return "M"
    return "D"


# 口語產業／主題 → Fugle tickers `industry` 代碼（見官方文件）
_INDUSTRY_FROM_QUESTION: tuple[tuple[str, str], ...] = (
    ("半導體", "24"),
    ("金融保險", "17"),
    ("金融股", "17"),
    ("金融", "17"),
    ("營建", "14"),
    ("水泥", "01"),
    ("食品", "02"),
    ("塑膠", "03"),
    ("生技醫療", "22"),
    ("電機", "05"),
    ("鋼鐵", "10"),
    ("航運", "15"),
    ("光電", "26"),
    ("通信網路", "27"),
    ("電子零組件", "28"),
    ("電腦及週邊", "25"),
    ("油電燃氣", "23"),
)


def build_intraday_tickers_params(question: str) -> dict[str, Any]:
    """GET intraday/tickers 查詢參數（依問題粗調 type／exchange／market／industry／旗標）。"""
    q = question
    params: dict[str, Any] = {"type": "EQUITY", "date": _taipei_today_ymd()}

    if "興櫃" in q:
        params["exchange"] = "TPEx"
        params["market"] = "ESB"
    elif "上櫃" in q:
        params["exchange"] = "TPEx"
        params["market"] = "OTC"
    elif "上市" in q or "臺證" in q or "台證" in q:
        params["exchange"] = "TWSE"
        params["market"] = "TSE"
    else:
        params["exchange"] = "TWSE"

    if "注意股" in q:
        params["isAttention"] = True
    if "處置股" in q:
        params["isDisposition"] = True
    if "停牌" in q or "暫停交易" in q:
        params["isHalted"] = True

    for needle, code in _INDUSTRY_FROM_QUESTION:
        if needle in q:
            params["industry"] = code
            break

    return params


def _candles_rows_from_response(data: dict[str, Any]) -> list[Any]:
    rows = data.get("data")
    if isinstance(rows, list):
        return rows
    alt = data.get("candles")
    return alt if isinstance(alt, list) else []


def _get(path: str, *, params: dict[str, Any] | None = None, timeout_s: int = 30) -> dict[str, Any]:
    if not FUGLE_KEY:
        raise RuntimeError("缺少 FUGLE_API_KEY：請在 backend/.env.local 設定（與前端 Fugle 金鑰相同即可）")
    url = f"{FUGLE_BASE}{path}"
    p = params or {}
    try:
        r = requests.get(url, headers={HEADER_KEY: FUGLE_KEY, "Accept": "application/json"}, params=p, timeout=timeout_s)
    except requests.RequestException as e:
        logger.warning("[Fugle] HTTP request failed path=%s params=%s err=%s", path, p, e)
        raise
    try:
        r.raise_for_status()
    except requests.HTTPError:
        preview = (r.text or "")[:400]
        logger.warning("[Fugle] GET HTTP error path=%s params=%s status=%s preview=%s", path, p, r.status_code, preview)
        raise
    data = r.json()
    row_n = 0
    if isinstance(data, dict):
        arr = data.get("data")
        if isinstance(arr, list):
            row_n = len(arr)
        log_json(
            logger,
            "fugle_http_ok",
            path=path,
            params=p,
            http_status=r.status_code,
            top_keys=list(data.keys())[:14],
            data_rows=row_n,
        )
    else:
        log_json(logger, "fugle_http_ok", path=path, http_status=r.status_code, body_type=type(data).__name__)
    return data


def execute_core_router_fetch(
    *,
    question: str,
    routing: dict[str, Any],
    timeout_s: int = 60,
) -> dict[str, Any]:
    """
    依 `fugle_core_router.route_fugle_market_data` 產出之 routing JSON 呼叫 Fugle。
    回傳形狀與 prefetch 類似：{ route, fugle?, fugle_api_response? }。
    """
    intent = routing.get("intent")
    sym = _normalize_symbol(str(routing.get("symbol") or ""))

    meta: dict[str, Any] = {"executed": False, "intent": intent}
    out: dict[str, Any] = {"route": meta}

    logger.info(
        "[Fugle] core_router intent=%s symbol=%s capability=%s",
        intent,
        sym,
        routing.get("capability_status"),
    )

    if routing.get("capability_status") != "SUPPORTED":
        meta["skip_reason"] = routing.get("reason") or "UNSUPPORTED"
        logger.info("[Fugle] core_router skip (not SUPPORTED) reason=%s", meta["skip_reason"])
        return out

    na = routing.get("next_action")
    if not isinstance(na, dict) or na.get("type") != "CALL_FUGLE_API":
        meta["skip_reason"] = "missing_next_action"
        logger.info("[Fugle] core_router skip missing_next_action na=%s", type(na).__name__)
        return out

    endpoint = str(na.get("endpoint") or "").strip()
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    full_path = "/marketdata/v1.0/stock" + endpoint
    logger.info("[Fugle] core_router CALL path=%s intent=%s symbol=%s", full_path, intent, sym)

    try:
        if intent == "MARKET_LIST":
            params = build_intraday_tickers_params(question)
            meta["params"] = dict(params)
            data = _get(full_path, params=params, timeout_s=timeout_s)
            meta["executed"] = True
            meta["path"] = full_path
            out["fugle_api_response"] = _truncate_payload(data, max_list=150)
            return out

        if intent == "TECHNICAL_ANALYSIS":
            tf = str(routing.get("timeframe") or "1")
            params = {"timeframe": tf, "sort": "asc"}
            meta["params"] = params
            data = _get(full_path, params=params, timeout_s=timeout_s)
            meta["executed"] = True
            meta["path"] = full_path
            body = data if isinstance(data, dict) else {}
            rows = _candles_rows_from_response(body)
            candles: list[dict[str, Any]] = []
            if isinstance(rows, list):
                tail = rows[-80:] if len(rows) > 80 else rows
                for row in tail:
                    if not isinstance(row, dict):
                        continue
                    candles.append(
                        {
                            "date": str(row.get("date") or ""),
                            "open": row.get("open"),
                            "high": row.get("high"),
                            "low": row.get("low"),
                            "close": row.get("close"),
                            "volume": row.get("volume"),
                        }
                    )
            out["fugle"] = {"symbol": sym, "candlesSnapshot": candles, "timeframe": tf}
            out["fugle_api_response"] = _truncate_payload(data, max_list=200)
            return out

        data = _get(full_path, timeout_s=timeout_s)
        meta["executed"] = True
        meta["path"] = full_path
        out["fugle_api_response"] = _truncate_payload(data, max_list=200)
        return out

    except requests.RequestException as e:
        raise RuntimeError(f"Fugle HTTP 錯誤: {e}") from e


def _router_historical_tf(routing: dict[str, Any]) -> str:
    tok = str(routing.get("timeframe") or "1d")
    if tok == "1w":
        return "W"
    if tok == "1m":
        return "M"
    return "D"


def _router_period_days(routing: dict[str, Any]) -> int:
    p = routing.get("required_period")
    if p == "3 months":
        return 100
    if p == "6 months":
        return 190
    if p == "1 year":
        return 370
    if p == "2 years":
        return 740
    return 120


def execute_market_fetch_with_fallback(
    *,
    question: str,
    routing: dict[str, Any],
    timeout_s: int = 60,
) -> dict[str, Any]:
    """
    先依 Core Router 的 SUPPORTED 路徑呼叫 Fugle。
    若為 TECHNICAL_ANALYSIS 且 Router 標為 UNSUPPORTED（日K／長區間等無法用 intraday/candles），
    改以 GET historical/candles 抓取日／週／月 K，仍帶回 fugle／fugle_api_response。
    """
    logger.info(
        "[Fugle] with_fallback start intent=%s capability=%s",
        routing.get("intent"),
        routing.get("capability_status"),
    )
    out = execute_core_router_fetch(question=question, routing=routing, timeout_s=timeout_s)
    if out.get("fugle_api_response") is not None:
        m = out.get("route") if isinstance(out.get("route"), dict) else {}
        logger.info(
            "[Fugle] with_fallback core path done executed=%s path=%s has_response=%s",
            m.get("executed"),
            m.get("path"),
            True,
        )
        return out

    if routing.get("intent") != "TECHNICAL_ANALYSIS":
        logger.info("[Fugle] with_fallback no data, not TECHNICAL_ANALYSIS — return core out only")
        return out
    if routing.get("capability_status") != "UNSUPPORTED":
        logger.info("[Fugle] with_fallback no data, capability not UNSUPPORTED — return core out only")
        return out

    sym = _normalize_symbol(str(routing.get("symbol") or ""))
    if not sym:
        logger.info("[Fugle] with_fallback historical skip empty symbol")
        return out

    htf = _router_historical_tf(routing)
    days = _router_period_days(routing)
    end = _taipei_today_ymd()
    start = (datetime.now(ZoneInfo("Asia/Taipei")).date() - timedelta(days=days)).strftime("%Y-%m-%d")
    path = f"/marketdata/v1.0/stock/historical/candles/{quote(sym, safe='')}"
    params: dict[str, Any] = {
        "timeframe": htf,
        "from": start,
        "to": end,
        "sort": "asc",
        "fields": "open,high,low,close,volume",
    }

    meta = dict(out.get("route") or {})
    meta["executed"] = True
    meta["fallback"] = "historical_candles"
    meta["path"] = path
    meta["params"] = params
    meta["note"] = "Core Router 將 intraday/candles 標為 UNSUPPORTED；改以 historical/candles 提供日／週／月 K。"

    logger.info(
        "[Fugle] with_fallback HISTORICAL path=%s timeframe=%s from=%s to=%s",
        path,
        htf,
        start,
        end,
    )

    try:
        data = _get(path, params=params, timeout_s=timeout_s)
    except requests.RequestException as e:
        raise RuntimeError(f"Fugle HTTP 錯誤（historical fallback）: {e}") from e

    body = data if isinstance(data, dict) else {}
    rows = _candles_rows_from_response(body)
    candles: list[dict[str, Any]] = []
    if isinstance(rows, list):
        tail = rows[-200:] if len(rows) > 200 else rows
        for row in tail:
            if not isinstance(row, dict):
                continue
            candles.append(
                {
                    "date": str(row.get("date") or ""),
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": row.get("volume"),
                }
            )

    return {
        "route": meta,
        "fugle": {"symbol": sym, "candlesSnapshot": candles, "timeframe": htf},
        "fugle_api_response": _truncate_payload(data, max_list=250),
    }


def _truncate_payload(obj: Any, *, max_list: int = 120, max_chars: int = 80_000) -> Any:
    """避免 prompt 爆炸：列表截斷、整體 JSON 過長則縮減。"""
    if isinstance(obj, dict):
        out = {k: _truncate_payload(v, max_list=max_list, max_chars=max_chars) for k, v in obj.items()}
        raw = json.dumps(out, ensure_ascii=False)
        if len(raw) > max_chars:
            return {"_truncated": True, "preview": raw[:max_chars] + "…"}
        return out
    if isinstance(obj, list):
        if len(obj) > max_list:
            return obj[:max_list] + [f"…（共 {len(obj)} 筆，已截斷為前 {max_list} 筆）"]
        return [_truncate_payload(x, max_list=max_list, max_chars=max_chars) for x in obj]
    return obj


def prefetch_fugle_for_question(
    *,
    question: str,
    structured: dict[str, Any],
    safe_data: dict[str, Any],
    timeout_s: int = 30,
) -> dict[str, Any]:
    """
    依規則選 API、抓取 JSON，回傳 { route, fugle? , raw_preview? }。
    fugle 區塊 Shape 盡量符合前端 gemini_service 表格化（symbol + candlesSnapshot）。
    """
    symbol = resolve_symbol(structured, safe_data)
    intent = classify_fugle_intent(question, symbol)

    route: dict[str, Any] = {
        "need_market_data": True,
        "intent": intent,
        "api": "",
        "params": {},
    }
    fugle_block: dict[str, Any] | None = None
    raw_truncated: dict[str, Any] | None = None

    try:
        if intent == "MARKET_LIST":
            path = "/marketdata/v1.0/stock/intraday/tickers"
            params = build_intraday_tickers_params(question)
            route["api"] = path
            route["params"] = dict(params)
            data = _get(path, params=params, timeout_s=timeout_s)
            raw_truncated = _truncate_payload(data, max_list=150)

        elif intent == "TICKER_INFO":
            if not symbol:
                raise RuntimeError("需要股票代號才能查 ticker 基本資料")
            path = f"/marketdata/v1.0/stock/intraday/ticker/{quote(symbol, safe='')}"
            route["api"] = "/marketdata/v1.0/stock/intraday/ticker/{symbol}"
            route["params"] = {"symbol": symbol}
            data = _get(path, timeout_s=timeout_s)
            raw_truncated = _truncate_payload(data)

        elif intent == "REALTIME_QUOTE":
            if not symbol:
                raise RuntimeError("需要股票代號才能查即時行情")
            path = f"/marketdata/v1.0/stock/intraday/quote/{quote(symbol, safe='')}"
            route["api"] = "/marketdata/v1.0/stock/intraday/quote/{symbol}"
            route["params"] = {"symbol": symbol}
            data = _get(path, timeout_s=timeout_s)
            raw_truncated = _truncate_payload(data)

        elif intent == "TECHNICAL_ANALYSIS":
            if not symbol:
                raise RuntimeError("需要股票代號才能查 K 線")
            wants_hist = _wants_daily_historical_candles(question)
            if wants_hist:
                htf = _historical_timeframe_for_question(question)
                path = f"/marketdata/v1.0/stock/historical/candles/{quote(symbol, safe='')}"
                end = _taipei_today_ymd()
                start = (datetime.now(ZoneInfo("Asia/Taipei")).date() - timedelta(days=120)).strftime("%Y-%m-%d")
                params = {
                    "timeframe": htf,
                    "from": start,
                    "to": end,
                    "sort": "asc",
                    "fields": "open,high,low,close,volume",
                }
                route["api"] = "/marketdata/v1.0/stock/historical/candles/{symbol}"
                route["params"] = {"symbol": symbol, "timeframe": htf, "from": start, "to": end}
                data = _get(path, params=params, timeout_s=timeout_s)
            else:
                tf_raw = _extract_minute_timeframe(question) or 1
                path = f"/marketdata/v1.0/stock/intraday/candles/{quote(symbol, safe='')}"
                # intraday/candles 文件未列 fields；僅 timeframe / sort / type
                params = {"timeframe": str(tf_raw), "sort": "asc"}
                route["api"] = "/marketdata/v1.0/stock/intraday/candles/{symbol}"
                route["params"] = {"symbol": symbol, "timeframe": str(tf_raw)}
                data = _get(path, params=params, timeout_s=timeout_s)

            body = data if isinstance(data, dict) else {}
            rows = _candles_rows_from_response(body)
            candles: list[dict[str, Any]] = []
            if isinstance(rows, list):
                tail = rows[-80:] if len(rows) > 80 else rows
                for row in tail:
                    if not isinstance(row, dict):
                        continue
                    candles.append(
                        {
                            "date": str(row.get("date") or ""),
                            "open": row.get("open"),
                            "high": row.get("high"),
                            "low": row.get("low"),
                            "close": row.get("close"),
                            "volume": row.get("volume"),
                        }
                    )
            fugle_block = {"symbol": symbol, "candlesSnapshot": candles, "timeframe": route["params"].get("timeframe")}
            raw_truncated = _truncate_payload(data, max_list=200)

        elif intent == "TRADE_FLOW":
            if not symbol:
                raise RuntimeError("需要股票代號才能查逐筆成交")
            path = f"/marketdata/v1.0/stock/intraday/trades/{quote(symbol, safe='')}"
            route["api"] = "/marketdata/v1.0/stock/intraday/trades/{symbol}"
            route["params"] = {"symbol": symbol}
            data = _get(path, timeout_s=timeout_s)
            raw_truncated = _truncate_payload(data, max_list=200)

        elif intent == "VOLUME_PROFILE":
            if not symbol:
                raise RuntimeError("需要股票代號才能查分價量")
            path = f"/marketdata/v1.0/stock/intraday/volumes/{quote(symbol, safe='')}"
            route["api"] = "/marketdata/v1.0/stock/intraday/volumes/{symbol}"
            route["params"] = {"symbol": symbol}
            data = _get(path, timeout_s=timeout_s)
            raw_truncated = _truncate_payload(data)

        else:
            route["need_market_data"] = False
            route["intent"] = "UNKNOWN"
            route["api"] = ""

    except requests.RequestException as e:
        raise RuntimeError(f"Fugle HTTP 錯誤: {e}") from e

    out: dict[str, Any] = {"route": route}
    if fugle_block is not None:
        out["fugle"] = fugle_block
    if raw_truncated is not None:
        out["fugle_api_response"] = raw_truncated
    return out


def merge_symbol_from_prefetch(structured: dict[str, Any], safe_data: dict[str, Any]) -> dict[str, Any]:
    out = dict(structured)
    if str(out.get("symbol") or "").strip():
        return out
    sym = resolve_symbol(out, safe_data)
    if sym:
        out["symbol"] = sym
    return out
