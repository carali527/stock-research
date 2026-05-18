"""
股票小幫手｜Production 固定模板：template_id → 明確 Fugle API（可複合呼叫）。
與自由文字 Router 分離，避免 UI 選項與實際抓取不一致。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import fugle_market_fetch as fm
from request_trace import log_json

logger = logging.getLogger(__name__)
SHORT_TREND_DAYS = 10


def _sym(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return ""
    i = t.find(".")
    return t[:i] if i > 0 else t


def _path(sym: str) -> str:
    return quote(_sym(sym), safe="")


def _rows_from_candles(body: dict[str, Any], *, max_rows: int = 200) -> list[dict[str, Any]]:
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    tail = rows[-max_rows:] if len(rows) > max_rows else rows
    for row in tail:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "date": str(row.get("date") or ""),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
            }
        )
    return out


def _date_key(row: dict[str, Any]) -> str:
    raw = str(row.get("date") or row.get("time") or row.get("timestamp") or "").strip()
    return raw[:10] if len(raw) >= 10 else raw


def _latest_n_date_rows(body: dict[str, Any], n_days: int) -> list[dict[str, Any]]:
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return []

    date_keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = _date_key(row)
        if key and key not in seen:
            seen.add(key)
            date_keys.append(key)

    keep = set(date_keys[-n_days:])
    return [row for row in rows if isinstance(row, dict) and _date_key(row) in keep]


def _with_data_rows(body: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = dict(body) if isinstance(body, dict) else {}
    out["data"] = rows
    return out


def _daily_summary_from_intraday_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = _date_key(row)
        if not key:
            continue
        grouped.setdefault(key, []).append(row)

    out: list[dict[str, Any]] = []
    for key in sorted(grouped):
        day_rows = grouped[key]
        if not day_rows:
            continue
        first = day_rows[0]
        last = day_rows[-1]
        highs = [r.get("high") for r in day_rows if isinstance(r.get("high"), (int, float))]
        lows = [r.get("low") for r in day_rows if isinstance(r.get("low"), (int, float))]
        volumes = [r.get("volume") for r in day_rows if isinstance(r.get("volume"), (int, float))]
        out.append(
            {
                "date": key,
                "open": first.get("open"),
                "high": max(highs) if highs else None,
                "low": min(lows) if lows else None,
                "close": last.get("close"),
                "volume": sum(volumes) if volumes else None,
                "bars": len(day_rows),
            }
        )
    return out


def execute_market_template_fetch(
    *,
    template_id: str,
    symbol: str,
    timeframe_minutes: int = 5,
    timeout_s: int = 60,
) -> dict[str, Any]:
    """
    回傳 { route, fugle?, fugle_api_response }，與 execute_market_fetch_with_fallback 相容。
    """
    sym = _sym(symbol)
    tid = (template_id or "").strip().lower().replace("-", "_")
    if not sym:
        raise RuntimeError("此模板需要股票代號（請傳 templateSymbol 或 resolvedSymbols）")
    logger.info(
        "[Fugle] production_template START template_id=%s symbol=%s timeframe_minutes=%s",
        tid,
        sym,
        timeframe_minutes,
    )
    calls: list[dict[str, Any]] = []
    merged: dict[str, Any] = {}
    fugle_block: dict[str, Any] | None = None

    def one(label: str, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        data = fm._get(path, params=params or {}, timeout_s=timeout_s)
        calls.append({"label": label, "path": path, "params": params or {}})
        return data

    if tid == "candles_short":
        tf = max(1, min(60, int(timeframe_minutes or 5)))
        if tf not in (1, 3, 5, 10, 15, 30, 60):
            tf = 5
        path_m = f"/marketdata/v1.0/stock/historical/candles/{_path(sym)}"
        params_m = {
            "timeframe": str(tf),
            "sort": "asc",
            "fields": "open,high,low,close,volume",
        }
        body_m = one("historical_intraday_candles_10d", path_m, params=params_m)
        minute_rows = _latest_n_date_rows(body_m if isinstance(body_m, dict) else {}, SHORT_TREND_DAYS)
        minute_body = _with_data_rows(body_m if isinstance(body_m, dict) else {}, minute_rows)

        end = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")
        start = (datetime.now(ZoneInfo("Asia/Taipei")).date() - timedelta(days=60)).strftime("%Y-%m-%d")
        params_d = {
            "timeframe": "D",
            "from": start,
            "to": end,
            "sort": "asc",
            "fields": "open,high,low,close,volume",
        }
        body_d = one("historical_daily_candles_10d", path_m, params=params_d)
        daily_rows = _latest_n_date_rows(body_d if isinstance(body_d, dict) else {}, SHORT_TREND_DAYS)
        daily_body = _with_data_rows(body_d if isinstance(body_d, dict) else {}, daily_rows)

        merged["historical_daily_candles_10d"] = fm._truncate_payload(daily_body, max_list=20)
        merged["historical_intraday_candles_10d"] = fm._truncate_payload(minute_body, max_list=600)
        fugle_block = {
            "symbol": sym,
            "dailyCandles": _rows_from_candles(daily_body),
            "candlesSnapshot": _rows_from_candles(minute_body, max_rows=800),
            "intradayDailySummary": _daily_summary_from_intraday_rows(minute_rows),
            "intradayRows": len(minute_rows),
            "timeframe": str(tf),
            "dateRangeDays": SHORT_TREND_DAYS,
            "intradayAvailableDays": len({_date_key(r) for r in minute_rows if _date_key(r)}),
        }

    elif tid == "support_resistance":
        path_c = f"/marketdata/v1.0/stock/intraday/candles/{_path(sym)}"
        pc = {"timeframe": "5", "sort": "asc"}
        body_c = one("intraday_candles_5m", path_c, params=pc)
        merged["intraday_candles"] = fm._truncate_payload(body_c, max_list=200)
        path_v = f"/marketdata/v1.0/stock/intraday/volumes/{_path(sym)}"
        body_v = one("intraday_volumes", path_v)
        merged["intraday_volumes"] = fm._truncate_payload(body_v, max_list=200)
        fugle_block = {"symbol": sym, "candlesSnapshot": _rows_from_candles(body_c if isinstance(body_c, dict) else {}), "timeframe": "5"}

    elif tid == "trade_flow":
        path = f"/marketdata/v1.0/stock/intraday/trades/{_path(sym)}"
        merged["intraday_trades"] = fm._truncate_payload(one("intraday_trades", path), max_list=200)

    elif tid == "volume_profile":
        path = f"/marketdata/v1.0/stock/intraday/volumes/{_path(sym)}"
        merged["intraday_volumes"] = fm._truncate_payload(one("intraday_volumes", path), max_list=200)

    elif tid == "trend_strength":
        path_q = f"/marketdata/v1.0/stock/intraday/quote/{_path(sym)}"
        merged["quote"] = fm._truncate_payload(one("quote", path_q), max_list=200)
        path_c = f"/marketdata/v1.0/stock/intraday/candles/{_path(sym)}"
        pc = {"timeframe": "5", "sort": "asc"}
        body_c = one("intraday_candles_5m", path_c, params=pc)
        merged["intraday_candles"] = fm._truncate_payload(body_c, max_list=200)
        path_v = f"/marketdata/v1.0/stock/intraday/volumes/{_path(sym)}"
        merged["intraday_volumes"] = fm._truncate_payload(one("intraday_volumes", path_v), max_list=200)
        fugle_block = {"symbol": sym, "candlesSnapshot": _rows_from_candles(body_c if isinstance(body_c, dict) else {}), "timeframe": "5"}

    elif tid == "daily_quant":
        end = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")
        start = (datetime.now(ZoneInfo("Asia/Taipei")).date() - timedelta(days=120)).strftime("%Y-%m-%d")
        path = f"/marketdata/v1.0/stock/historical/candles/{_path(sym)}"
        params = {
            "timeframe": "D",
            "from": start,
            "to": end,
            "sort": "asc",
            "fields": "open,high,low,close,volume",
        }
        body = one("historical_candles_D", path, params=params)
        merged["historical_candles"] = fm._truncate_payload(body, max_list=250)
        fugle_block = {"symbol": sym, "candlesSnapshot": _rows_from_candles(body if isinstance(body, dict) else {}), "timeframe": "D"}

    else:
        raise RuntimeError(f"未知的 marketTemplateId: {template_id}")

    route: dict[str, Any] = {
        "mode": "production_template",
        "template_id": tid,
        "symbol": sym,
        "executed": True,
        "calls": calls,
    }
    if tid == "candles_short":
        route["timeframe_minutes"] = timeframe_minutes
        route["date_range_days"] = SHORT_TREND_DAYS

    k_rows = len((fugle_block or {}).get("candlesSnapshot") or []) if isinstance(fugle_block, dict) else 0
    log_json(
        logger,
        "production_template_done",
        template_id=tid,
        symbol=sym,
        n_calls=len(calls),
        labels=[c.get("label") for c in calls],
        has_fugle_block=fugle_block is not None,
        candles_snapshot_rows=k_rows,
        merged_keys=list(merged.keys()),
    )

    return {
        "route": route,
        "fugle": fugle_block,
        "fugle_api_response": merged,
    }


def build_template_question(template_id: str, symbol: str, name: str, *, timeframe_minutes: int = 5) -> str:
    """與前端一致的固定問句（供 Gemini 對齊輸出範圍）。"""
    tag = f"{symbol} {name}".strip() if name else symbol
    tid = (template_id or "").strip().lower().replace("-", "_")
    if tid == "candles_short":
        return (
            f"分析 {tag} 最近 {SHORT_TREND_DAYS} 個交易日的短期走勢。"
            f"請優先使用附帶的近 {SHORT_TREND_DAYS} 日日K判斷趨勢、波動、支撐壓力，"
            f"再用可取得的 {timeframe_minutes} 分K近 {SHORT_TREND_DAYS} 日資料作為盤中細節補充；"
            f"若分K不足 {SHORT_TREND_DAYS} 個交易日，必須明確說明。"
        )
    if tid == "support_resistance":
        return f"{tag} 最近支撐壓力在哪？（僅用附帶分K 與分價量：支撐價、壓力價、成交密集區、是否接近壓力。）"
    if tid == "trade_flow":
        return f"{tag} 有沒有主力進出？（僅用附帶逐筆成交：大單方向、連續買賣、是否像掃單；不做明日預測。）"
    if tid == "volume_profile":
        return f"{tag} 籌碼集中在哪個價格？（僅用附帶分價量：成交密集價位、支撐區、壓力區。）"
    if tid == "trend_strength":
        return f"{tag} 現在是多頭還空頭？（綜合附帶的即時行情、5 分K、分價量：趨勢方向、動能、是否可能轉折；僅引用數據。）"
    if tid == "daily_quant":
        return (
            f"請根據附帶行情資料，分析 {tag} 最近約三個月的日K：列出最近 5 個交易日的日期、收盤價、成交量，"
            f"並計算這 5 日的累積漲跌幅（寫出計算式與中間數字）。"
        )
    return f"{tag} 股票分析（template={tid}）"


def template_symbol_from_payload(safe_data: dict[str, Any]) -> str:
    for key in ("templateSymbol", "template_symbol"):
        raw = safe_data.get(key)
        if isinstance(raw, str) and raw.strip():
            return _sym(raw)
    rs = safe_data.get("resolvedSymbols")
    if isinstance(rs, list):
        for x in rs:
            sx = _sym(str(x))
            if sx:
                return sx
    return ""
