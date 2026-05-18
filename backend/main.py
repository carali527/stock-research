from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
import logging
import os
import time
import traceback
import uuid
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
import google.generativeai as genai
import requests
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.websockets import WebSocketDisconnect
from pydantic import BaseModel, Field

from request_trace import bind_request_id, log_json, reset_request_id
from scraper import fetch_yahoo_tw_listed_change_up_rank_items, fetch_yahoo_tw_listed_hot_rank_symbols, fetch_yahoo_tw_quote

# 與 main.py 同目錄的 .env.local（不依賴 uvicorn 啟動時 cwd）；等同 load_dotenv(".env.local") 在 backend 目錄執行時
_BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(_BACKEND_DIR / ".env.local")

# Gemini key（與 gemini_service 一致：GEMINI_API_KEY 或 GOOGLE_API_KEY 擇一，常見為 GOOGLE_API_KEY）
_RAW_GEMINI_KEY = os.getenv("GEMINI_API_KEY") or ""
_RAW_GOOGLE_KEY = os.getenv("GOOGLE_API_KEY") or ""
API_KEY = _RAW_GEMINI_KEY or _RAW_GOOGLE_KEY
DEMO_TOKEN = (os.getenv("DEMO_TOKEN") or "stock-research-demo").strip()


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


DEMO_DAILY_IP_LIMIT = max(0, _env_int("DEMO_DAILY_IP_LIMIT", 2))


def _api_key_source() -> str:
    if _RAW_GEMINI_KEY.strip():
        return "GEMINI_API_KEY"
    if _RAW_GOOGLE_KEY.strip():
        return "GOOGLE_API_KEY"
    return "missing"


def _api_key_fingerprint(key: str | None) -> dict[str, Any]:
    k = (key or "").strip()
    if not k:
        return {"present": False, "len": 0, "fp": ""}
    if len(k) <= 10:
        return {"present": True, "len": len(k), "fp": f"{k[:2]}…{k[-2:]}"}
    return {"present": True, "len": len(k), "fp": f"{k[:4]}…{k[-4:]}"}

if API_KEY:
    genai.configure(api_key=API_KEY)

_APP_LOG_HANDLERS_DONE = False


def _configure_stderr_info_loggers() -> None:
    """
    Uvicorn 預設常只清楚顯示 access log；子模組 logger 的 INFO 不一定會出現在終端機。
    為 stock-research 相關 logger 各掛 stderr StreamHandler（只做一次、reload 後會重跑）。
    """
    global _APP_LOG_HANDLERS_DONE
    if _APP_LOG_HANDLERS_DONE:
        return
    fmt = logging.Formatter("%(levelname)s:%(name)s:%(message)s")
    for name in (
        "main",
        "fugle_market_fetch",
        "market_template",
        "fugle_core_router",
        "gemini_service",
        "request_trace",
    ):
        log = logging.getLogger(name)
        log.setLevel(logging.INFO)
        if any(getattr(h, "_stock_research_stderr", False) for h in log.handlers):
            continue
        h = logging.StreamHandler()
        h.setFormatter(fmt)
        h.setLevel(logging.INFO)
        setattr(h, "_stock_research_stderr", True)
        log.addHandler(h)
        log.propagate = False
    _APP_LOG_HANDLERS_DONE = True


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _configure_stderr_info_loggers()
    yield


app = FastAPI(title="stock-research-backend", version="0.1.0", lifespan=_lifespan)
logger = logging.getLogger(__name__)
_configure_stderr_info_loggers()
log_json(
    logger,
    "startup_gemini_key",
    source=_api_key_source(),
    **_api_key_fingerprint(API_KEY),
)


def _incoming_request_id(request: Request) -> str:
    h = request.headers.get("x-request-id") or request.headers.get("X-Request-ID") or ""
    return h.strip() or str(uuid.uuid4())


def _require_demo_token(request: Request) -> None:
    if not DEMO_TOKEN:
        return
    token = (request.headers.get("x-demo-token") or request.headers.get("X-Demo-Token") or "").strip()
    if token != DEMO_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid demo token")

# Dev-friendly CORS (lock down in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/fugle/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
async def fugle_http_proxy(path: str, request: Request) -> Response:
    """瀏覽器只打同源 `/fugle/...`，金鑰僅在後端 `FUGLE_API_KEY`。"""
    from fugle_market_fetch import FUGLE_BASE, FUGLE_KEY, HEADER_KEY

    if not FUGLE_KEY:
        raise HTTPException(status_code=503, detail="FUGLE_API_KEY not configured")

    url = f"{FUGLE_BASE}/{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    fwd_headers: dict[str, str] = {
        HEADER_KEY: FUGLE_KEY,
        "Accept": request.headers.get("accept") or "application/json",
    }
    ct = request.headers.get("content-type")
    body: bytes | None = None
    if request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()
        if ct:
            fwd_headers["Content-Type"] = ct

    def _call() -> Any:
        return requests.request(
            request.method,
            url,
            headers=fwd_headers,
            data=body if body else None,
            timeout=90,
        )

    r = await asyncio.to_thread(_call)
    out_ct = r.headers.get("Content-Type") or "application/octet-stream"
    return Response(content=r.content, status_code=r.status_code, media_type=out_ct)


@app.websocket("/ws/fugle/streaming")
async def fugle_streaming_ws_proxy(websocket: WebSocket) -> None:
    """瀏覽器連同源 WS，後端用 `FUGLE_API_KEY` 連 Fugle 並雙向轉發（不再把 key 放前端 bundle）。"""
    from fugle_market_fetch import FUGLE_KEY

    if not FUGLE_KEY:
        await websocket.close(code=1011)
        return

    await websocket.accept()

    import websockets
    from websockets.exceptions import ConnectionClosed

    ws_url = "wss://api.fugle.tw/marketdata/v1.0/stock/streaming"

    async def pump_upstream_to_browser(upstream: Any) -> None:
        async for message in upstream:
            if isinstance(message, bytes):
                message = message.decode("utf-8", errors="replace")
            await websocket.send_text(message)

    async def pump_browser_to_upstream(upstream: Any) -> None:
        while True:
            try:
                text = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and str(parsed.get("event", "")).strip().lower() == "auth":
                    continue
            except json.JSONDecodeError:
                pass
            await upstream.send(text)

    try:
        async with websockets.connect(ws_url, max_size=None, open_timeout=30) as upstream:
            await upstream.send(json.dumps({"event": "auth", "data": {"apikey": FUGLE_KEY}}))
            t1 = asyncio.create_task(pump_upstream_to_browser(upstream))
            t2 = asyncio.create_task(pump_browser_to_upstream(upstream))
            done, pending = await asyncio.wait((t1, t2), return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in pending:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    except ConnectionClosed:
        pass
    except Exception as e:
        logger.warning("fugle streaming proxy failed: %s", e)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/api/debug/gemini-models")
def debug_gemini_models() -> dict[str, Any]:
    """
    列出此 API key 可用、且支援 generateContent 的模型；用於排除 404 / v1beta 模型不存在。
    """
    try:
        from gemini_service import generativeai_package_version, list_gemini_models_for_generate_content

        log_json(
            logger,
            "debug_gemini_models_begin",
            source=_api_key_source(),
            **_api_key_fingerprint(API_KEY),
        )
        return {
            "google_generativeai_version": generativeai_package_version(),
            "hint": "請從 models[].generative_model_id 擇一設為 GEMINI_MODEL（或沿用 name，程式會去掉 models/ 前綴）。",
            "api_key": {"source": _api_key_source(), **_api_key_fingerprint(API_KEY)},
            "models": list_gemini_models_for_generate_content(),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get("/api/yahoo/quote/{symbol}")
def yahoo_quote(symbol: str) -> dict[str, Any]:
    try:
        q = fetch_yahoo_tw_quote(symbol)
        return {
            "symbol": q.symbol,
            "name": q.name,
            "price": q.price,
            "change": q.change,
            "changePercent": q.change_percent,
            "asOf": q.as_of,
            "sourceUrl": q.source_url,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Yahoo scrape failed: {e}") from e


@app.get("/api/yahoo/listed-hot-rank")
def yahoo_listed_hot_rank() -> dict[str, Any]:
    try:
        items = fetch_yahoo_tw_listed_hot_rank_symbols()
        return {"items": items, "sourceUrl": "https://tw.stock.yahoo.com/rank/volume?exchange=TAI"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Yahoo scrape failed: {e}") from e


@app.get("/api/yahoo/listed-change-up-rank")
def yahoo_listed_change_up_rank() -> dict[str, Any]:
    try:
        items = fetch_yahoo_tw_listed_change_up_rank_items()
        return {"items": items, "sourceUrl": "https://tw.stock.yahoo.com/rank/change-up?exchange=TAI"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Yahoo scrape failed: {e}") from e


class GeminiRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    data: dict[str, Any] = Field(default_factory=dict)
    stream: bool = True


class GeminiResponse(BaseModel):
    model: str
    analysis: str
    risk: str
    next_step: str


class GeminiStreamRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    data: dict[str, Any] = Field(default_factory=dict)


_RATE: dict[str, list[float]] = {}
_DAILY_IP_USAGE: dict[str, tuple[str, int]] = {}


def _pop_user_note(safe_data: dict[str, Any]) -> str:
    """從 data 取出補充說明（前端 userNote / user_note），並自 safe_data 移除以免重複進 JSON。"""
    for key in ("userNote", "user_note", "userNotes"):
        raw = safe_data.pop(key, None)
        if raw is None:
            continue
        if isinstance(raw, str):
            s = raw.strip()
        elif isinstance(raw, (int, float, bool)):
            s = str(raw).strip()
        elif isinstance(raw, (list, dict)):
            continue
        else:
            s = str(raw).strip()
        if s:
            return s
    return ""


def _prepare_stream_structured_and_market_data(*, question: str, safe_data: dict[str, Any], timeout_s: int = 60) -> dict[str, Any]:
    """
    若 data 帶 prefetchFugleMarketData（或相容旗標）：
    User Question → Rule-based Router（fugle_core_router）→ Call Fugle → 供 Gemini 使用之 structured + safe_data。
    否則：維持 Gemini Stage 1 意圖辨識（不含預抓）。
    """
    prefetch = bool(
        safe_data.pop("prefetchFugleMarketData", False)
        or safe_data.pop("runFugleCoreRouter", False)
        or safe_data.pop("run_fugle_core_router", False)
    )
    if prefetch:
        from fugle_core_router import route_fugle_market_data
        from fugle_market_fetch import execute_market_fetch_with_fallback, merge_symbol_from_prefetch
        from market_template import build_template_question, execute_market_template_fetch, template_symbol_from_payload

        logger.info(
            "[ai-stream] prefetch=ON — Fugle 將先於 Gemini 執行 question_preview=%r",
            (question or "")[:160],
        )

        rs_list: list[str] | None = None
        rs_raw = safe_data.get("resolvedSymbols")
        if isinstance(rs_raw, list):
            rs_list = [str(x).strip() for x in rs_raw if str(x).strip()]

        template_id_raw = safe_data.pop("marketTemplateId", None) or safe_data.pop("templateId", None)
        template_id = str(template_id_raw).strip() if template_id_raw else ""
        name_raw = safe_data.pop("templateStockName", None)
        template_name = str(name_raw).strip() if isinstance(name_raw, str) else ""
        params_raw = safe_data.pop("templateParams", None)
        tf_min = 5
        if isinstance(params_raw, dict):
            v = params_raw.get("timeframeMinutes") if "timeframeMinutes" in params_raw else params_raw.get("timeframe_minutes")
            if isinstance(v, (int, float)):
                tf_min = max(1, min(60, int(v)))
            elif isinstance(v, str) and v.strip().isdigit():
                tf_min = max(1, min(60, int(v.strip())))

        if template_id:
            sym = template_symbol_from_payload(safe_data)
            safe_data.pop("templateSymbol", None)
            safe_data.pop("template_symbol", None)
            user_note = _pop_user_note(safe_data)
            safe_data["market_route"] = {
                "mode": "production_template",
                "template_id": template_id,
                "template_symbol": sym,
                "timeframe_minutes": tf_min,
            }
            structured = {
                "intent": "stock_analysis",
                "market": "TW",
                "symbol": sym,
                "strategy": "",
                "filters": {},
                "marketTemplateId": template_id,
            }
            if user_note:
                structured["userSupplement"] = user_note
            ap = build_template_question(template_id, sym, template_name, timeframe_minutes=tf_min)
            if user_note:
                ap = ap + "\n\n【使用者補充說明】" + user_note
            safe_data["_analysisPrompt"] = ap
            logger.info(
                "[ai-stream] Fugle 順序：先打 API（production_template）template_id=%s symbol=%s",
                template_id,
                sym,
            )
            try:
                pack = execute_market_template_fetch(
                    template_id=template_id,
                    symbol=sym,
                    timeframe_minutes=tf_min,
                    timeout_s=timeout_s,
                )
                fr = pack.get("route")
                if isinstance(fr, dict):
                    safe_data["fugle_route"] = fr
                if pack.get("fugle"):
                    safe_data["fugle"] = pack["fugle"]
                if pack.get("fugle_api_response") is not None:
                    safe_data["fugle_api_response"] = pack["fugle_api_response"]
            except Exception as e:
                safe_data["fugle_prefetch_error"] = str(e)
                logger.warning("[ai-stream] Fugle template fetch failed: %s", e)
            fr_done = safe_data.get("fugle_route")
            logger.info(
                "[ai-stream] Fugle 模板預抓結束 err=%s executed=%s n_calls=%s has_fugle=%s has_fugle_api_response=%s",
                safe_data.get("fugle_prefetch_error"),
                (fr_done or {}).get("executed") if isinstance(fr_done, dict) else None,
                len((fr_done or {}).get("calls") or []) if isinstance(fr_done, dict) else 0,
                "fugle" in safe_data,
                "fugle_api_response" in safe_data,
            )
            return merge_symbol_from_prefetch(structured, safe_data)

        logger.info("[ai-stream] Fugle 順序：Rule Router → API（非模板）")
        routing = route_fugle_market_data(question=question, resolved_symbols=rs_list)
        safe_data["market_route"] = routing
        logger.info(
            "[ai-stream] Router 結果 intent=%s symbol=%s capability=%s",
            routing.get("intent"),
            routing.get("symbol"),
            routing.get("capability_status"),
        )

        structured = {
            "intent": "stock_analysis",
            "market": "TW",
            "symbol": str(routing.get("symbol") or "").strip(),
            "strategy": "",
            "filters": {},
            "router_intent": routing.get("intent"),
            "router_timeframe": routing.get("timeframe"),
            "router_capability": routing.get("capability_status"),
        }

        try:
            pack = execute_market_fetch_with_fallback(question=question, routing=routing, timeout_s=timeout_s)
            fr = pack.get("route")
            if isinstance(fr, dict):
                safe_data["fugle_route"] = fr
            if pack.get("fugle"):
                safe_data["fugle"] = pack["fugle"]
            if pack.get("fugle_api_response") is not None:
                safe_data["fugle_api_response"] = pack["fugle_api_response"]
        except Exception as e:
            safe_data["fugle_prefetch_error"] = str(e)
            logger.warning("[ai-stream] Fugle router fetch failed: %s", e)

        fr_r = safe_data.get("fugle_route")
        logger.info(
            "[ai-stream] Fugle Router 預抓結束 err=%s executed=%s path=%s fallback=%s has_fugle=%s has_fugle_api_response=%s",
            safe_data.get("fugle_prefetch_error"),
            (fr_r or {}).get("executed") if isinstance(fr_r, dict) else None,
            (fr_r or {}).get("path") if isinstance(fr_r, dict) else None,
            (fr_r or {}).get("fallback") if isinstance(fr_r, dict) else None,
            "fugle" in safe_data,
            "fugle_api_response" in safe_data,
        )

        user_note = _pop_user_note(safe_data)
        if user_note:
            structured["userSupplement"] = user_note
            base_q = (question or "").strip()
            safe_data["_analysisPrompt"] = (
                base_q + "\n\n【使用者補充說明】" + user_note if base_q else "【使用者補充說明】" + user_note
            )

        return merge_symbol_from_prefetch(structured, safe_data)

    from gemini_service import parse_and_validate_intent

    return parse_and_validate_intent(question=question, timeout_s=timeout_s)


def _rate_limit(ip: str, *, limit: int = 10, window_s: int = 60):
    now = time.time()
    bucket = _RATE.get(ip, [])
    bucket = [t for t in bucket if now - t < window_s]
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(window_s)},
        )
    bucket.append(now)
    _RATE[ip] = bucket


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or "unknown"
    return request.client.host if request.client else "unknown"


def _taipei_date_key() -> str:
    return datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")


def _seconds_until_taipei_midnight() -> int:
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    tomorrow = (now + timedelta(days=1)).date()
    midnight = datetime.combine(tomorrow, datetime.min.time(), tzinfo=ZoneInfo("Asia/Taipei"))
    return max(1, int((midnight - now).total_seconds()))


def _daily_ip_limit(ip: str, *, limit: int = DEMO_DAILY_IP_LIMIT) -> None:
    if limit <= 0:
        return
    if ip in {"127.0.0.1", "::1", "localhost"}:
        return
    today = _taipei_date_key()
    saved_day, count = _DAILY_IP_USAGE.get(ip, (today, 0))
    if saved_day != today:
        saved_day, count = today, 0
    if count >= limit:
        raise HTTPException(
            status_code=429,
            detail="Demo daily limit reached",
            headers={
                "Retry-After": str(_seconds_until_taipei_midnight()),
                "X-Demo-Daily-Limit": "1",
            },
        )
    _DAILY_IP_USAGE[ip] = (saved_day, count + 1)


@app.post("/api/gemini")
def gemini_chat(req: GeminiRequest, request: Request) -> GeminiResponse:
    try:
        _require_demo_token(request)
        ip = _client_ip(request)
        _rate_limit(ip)
        _daily_ip_limit(ip)
        from gemini_service import IntentRejectedError, cached_call_gemini_json, iter_stage2_stream_chunks

        if req.stream:
            safe_data = dict(req.data or {})
            rid = _incoming_request_id(request)
            safe_data["_requestId"] = rid
            log_json(logger, "gemini_route_stream_begin", request_id=rid, endpoint="/api/gemini")
            tok = bind_request_id(rid)
            try:
                structured = _prepare_stream_structured_and_market_data(
                    question=req.question, safe_data=safe_data, timeout_s=60
                )
            except IntentRejectedError as e:
                raise HTTPException(status_code=422, detail=e.message, headers={"X-Request-ID": rid}) from e
            finally:
                reset_request_id(tok)
            log_json(
                logger,
                "prepare_done",
                request_id=rid,
                endpoint="/api/gemini",
                symbol=structured.get("symbol"),
                intent=structured.get("intent"),
            )
            logger.info("[ai-stream] /api/gemini stream：進入 Gemini Stage2（prepare 已完成）")

            def generate():
                tok2 = bind_request_id(rid)
                try:
                    yield from iter_stage2_stream_chunks(
                        structured=structured, safe_data=safe_data, timeout_s=60, request_id=rid
                    )
                except Exception as e:
                    print("ERROR /api/gemini (stream generator):", e)
                    traceback.print_exc()
                    yield f"\n\n[分析階段錯誤: {e}]\n"
                finally:
                    reset_request_id(tok2)

            return StreamingResponse(
                generate(),
                media_type="text/plain; charset=utf-8",
                headers={"X-Request-ID": rid},
            )

        out = cached_call_gemini_json(question=req.question, safe_data=req.data, timeout_s=60)
        return GeminiResponse(**out)
    except IntentRejectedError as e:
        raise HTTPException(status_code=422, detail=e.message) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini API failed: {e}") from e


@app.post("/api/ai/stream")
def gemini_stream(req: GeminiStreamRequest, request: Request):
    """
    Rule-based Router → Fugle（可選）→ Gemini streaming。
    - data.prefetchFugleMarketData=true：跳過 Gemini Stage 1，改用 fugle_core_router + Fugle REST。
    - 否則：Gemini Stage 1 意圖 gate，再串流分析（無預抓）。
    """
    _require_demo_token(request)
    ip = _client_ip(request)
    _rate_limit(ip)
    _daily_ip_limit(ip)

    from gemini_service import IntentRejectedError, iter_stage2_stream_chunks

    rid = _incoming_request_id(request)
    safe_data = dict(req.data or {})
    safe_data["_requestId"] = rid
    log_json(logger, "ai_stream_begin", request_id=rid, endpoint="/api/ai/stream")

    tok = bind_request_id(rid)
    try:
        structured = _prepare_stream_structured_and_market_data(question=req.question, safe_data=safe_data, timeout_s=60)
    except IntentRejectedError as e:
        raise HTTPException(status_code=422, detail=e.message, headers={"X-Request-ID": rid}) from e
    except Exception as e:
        print("ERROR /api/ai/stream (prepare stage):", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e), headers={"X-Request-ID": rid}) from e
    finally:
        reset_request_id(tok)

    log_json(
        logger,
        "prepare_done",
        request_id=rid,
        endpoint="/api/ai/stream",
        symbol=structured.get("symbol"),
        intent=structured.get("intent"),
    )
    logger.info("[ai-stream] 進入 Gemini Stage2 串流（prepare 已完成；prefetch 時 Fugle 已先於本行執行）")

    def generate():
        tok2 = bind_request_id(rid)
        try:
            yield from iter_stage2_stream_chunks(
                structured=structured, safe_data=safe_data, timeout_s=60, request_id=rid
            )
        except Exception as e:
            print("ERROR /api/ai/stream (generator):", e)
            traceback.print_exc()
            yield f"\n\n[分析階段錯誤: {e}]\n"
        finally:
            reset_request_id(tok2)

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Request-ID": rid},
    )


_STATIC_DIR = _BACKEND_DIR / "static"
_SPA_INDEX = _STATIC_DIR / "index.html"
_ASSETS_DIR = _STATIC_DIR / "assets"

# Vite 產出的 hash 命名靜態檔（JS/CSS/圖片）；與下方 SPA fallback 分開掛載，避免行為依賴 import 當下是否已有 index.html。
if _ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")

# 不可被 SPA fallback 吃掉的前綴；命中這些就維持 JSON 404（與僅掛 StaticFiles(html=True) 不同，深連結須回 index.html）。
_NON_SPA_PREFIXES: tuple[str, ...] = (
    "api/",
    "fugle/",
    "ws/",
    "health",
    "assets/",
)


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> Response:
    if not _SPA_INDEX.is_file():
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    if full_path.startswith(_NON_SPA_PREFIXES):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    candidate = (_STATIC_DIR / full_path).resolve()
    try:
        candidate.relative_to(_STATIC_DIR.resolve())
    except ValueError:
        return FileResponse(_SPA_INDEX)
    if candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(_SPA_INDEX)


if _SPA_INDEX.is_file():
    logger.info("SPA deep linking enabled (index at %s)", _SPA_INDEX)
else:
    logger.warning(
        "Missing %s — build the frontend (Dockerfile copies dist here) or deep links like /stock/demo will 404 on refresh.",
        _SPA_INDEX,
    )
