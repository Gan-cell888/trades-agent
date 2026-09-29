# -*- coding: utf-8 -*-
"""问答历史会话（本机 JSON 存储）"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

STORE_PATH = Path(__file__).resolve().parent / "qa_sessions.json"


def _load() -> list[dict[str, Any]]:
    if not STORE_PATH.is_file():
        return []
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(items: list[dict[str, Any]]) -> None:
    STORE_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def list_sessions() -> list[dict[str, Any]]:
    items = _load()
    items.sort(key=lambda x: x.get("updated_at") or 0, reverse=True)
    out = []
    for it in items:
        msgs = it.get("messages") or []
        preview = ""
        for m in msgs:
            if m.get("role") == "user" and m.get("text"):
                preview = str(m["text"])[:40]
                break
        if not preview and msgs:
            preview = str(msgs[-1].get("text") or "")[:40]
        out.append({
            "id": it.get("id"),
            "title": it.get("title") or preview or "未命名对话",
            "preview": preview,
            "count": len(msgs),
            "updated_at": it.get("updated_at"),
        })
    return out


def get_session(session_id: str) -> dict[str, Any] | None:
    for it in _load():
        if it.get("id") == session_id:
            return it
    return None


def create_session(title: str = "新对话") -> dict[str, Any]:
    now = time.time()
    item = {
        "id": uuid.uuid4().hex[:12],
        "title": (title or "新对话")[:40],
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    items = _load()
    items.append(item)
    _save(items)
    return item


def save_messages(session_id: str, messages: list[dict[str, Any]], title: str | None = None) -> dict[str, Any]:
    items = _load()
    found = None
    for it in items:
        if it.get("id") == session_id:
            found = it
            break
    if found is None:
        found = {
            "id": session_id or uuid.uuid4().hex[:12],
            "title": "新对话",
            "created_at": time.time(),
            "messages": [],
        }
        items.append(found)
    found["messages"] = [
        {"role": m.get("role", "user"), "text": str(m.get("text") or "")[:4000]}
        for m in (messages or [])
        if str(m.get("text") or "").strip()
    ]
    if title:
        found["title"] = title[:40]
    elif found["messages"]:
        for m in found["messages"]:
            if m["role"] == "user":
                found["title"] = m["text"][:24] or found.get("title") or "新对话"
                break
    found["updated_at"] = time.time()
    _save(items)
    return found


def delete_session(session_id: str) -> bool:
    items = _load()
    n = len(items)
    items = [it for it in items if it.get("id") != session_id]
    if len(items) == n:
        return False
    _save(items)
    return True


def clear_all() -> int:
    items = _load()
    _save([])
    return len(items)
