"""
Request 全鏈路追蹤：ContextVar request_id + 單行 JSON log。
"""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar, Token
from typing import Any

_request_id_ctx: ContextVar[str] = ContextVar("stock_research_request_id", default="")


def get_request_id() -> str:
    return _request_id_ctx.get() or ""


def bind_request_id(rid: str) -> Token:
    """設定目前請求的 request_id；回傳 Token 供 reset_request_id。"""
    clean = (rid or "").strip()
    return _request_id_ctx.set(clean if clean else str(uuid.uuid4()))


def reset_request_id(token: Token) -> None:
    _request_id_ctx.reset(token)


def new_request_id() -> str:
    return str(uuid.uuid4())


def log_json(logger: logging.Logger, stage: str, *, request_id: str | None = None, **fields: Any) -> None:
    """單行 JSON，便於 grep / 日誌系統欄位化。request_id 可顯式傳入（prepare 結束 reset 後仍要打同一支 id）。"""
    rid = (request_id or "").strip() or get_request_id()
    rec: dict[str, Any] = {"request_id": rid, "stage": stage}
    for k, v in fields.items():
        rec[k] = v
    logger.info(json.dumps(rec, ensure_ascii=False, default=str))
