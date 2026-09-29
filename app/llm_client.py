# -*- coding: utf-8 -*-
"""大模型客户端：多套自定义模型接入（OpenAI 兼容协议）

支持保存多个模型方案（DeepSeek / GPT / 通义 / Ollama / 自建网关等），
可切换启用、自定义路径与请求头。
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent / "llm_config.json"

# 单条模型方案字段
PROFILE_FIELDS = (
    "label",
    "base_url",
    "api_key",
    "model",
    "chat_path",
    "api_style",
    "timeout",
    "batch_size",
    "temperature",
    "max_tokens",
    "extra_headers",
)

DEFAULT_PROFILE: dict[str, Any] = {
    "label": "DeepSeek",
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "",
    "model": "deepseek-chat",
    "chat_path": "/chat/completions",
    "api_style": "openai",  # openai | openai_no_auth
    "timeout": 60,
    "batch_size": 8,
    "temperature": 0.1,
    "max_tokens": 2000,
    "extra_headers": {},
}

PRESETS: list[dict[str, Any]] = [
    {
        "id": "mimo_api",
        "label": "MiMo API Key",
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "model": "mimo-v2.5",
        "api_style": "openai",
        "icon": "🟡",
        "color": "#f5c542",
    },
    {
        "id": "mimo_token",
        "label": "MiMo Token Plan",
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "model": "mimo-v2.6-pro",
        "api_style": "openai",
        "icon": "🟠",
        "color": "#ff8a3d",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_style": "openai",
        "icon": "🔵",
        "color": "#4b7cf7",
    },
    {
        "id": "kimi",
        "label": "Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "api_style": "openai",
        "icon": "⚫",
        "color": "#c4c4c4",
    },
    {
        "id": "zhipu",
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "api_style": "openai",
        "icon": "🔷",
        "color": "#5b8def",
    },
    {
        "id": "qwen",
        "label": "千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "api_style": "openai",
        "icon": "🟣",
        "color": "#a78bfa",
    },
    {
        "id": "custom",
        "label": "自定义 / Custom",
        "base_url": "",
        "model": "",
        "api_style": "openai",
        "chat_path": "/chat/completions",
        "icon": "✨",
        "color": "#9ca3af",
    },
]


def _default_store() -> dict[str, Any]:
    return {
        "active_id": "deepseek",
        "profiles": {
            "deepseek": {**DEFAULT_PROFILE, "label": "DeepSeek"},
        },
    }


def _normalize_profile(p: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_PROFILE)
    if isinstance(p, dict):
        for k in PROFILE_FIELDS:
            if k in p and p[k] is not None:
                out[k] = p[k]
    if not isinstance(out.get("extra_headers"), dict):
        out["extra_headers"] = {}
    out["timeout"] = int(out.get("timeout") or 60)
    out["batch_size"] = int(out.get("batch_size") or 8)
    try:
        out["temperature"] = float(out.get("temperature") if out.get("temperature") is not None else 0.1)
    except Exception:
        out["temperature"] = 0.1
    if out.get("max_tokens") is not None:
        try:
            out["max_tokens"] = int(out["max_tokens"])
        except Exception:
            out["max_tokens"] = 2000
    if not out.get("chat_path"):
        out["chat_path"] = "/chat/completions"
    # 纠正历史错误域名：xiaomimi.com → xiaomimimo.com
    base = str(out.get("base_url") or "")
    if "xiaomimi.com" in base and "xiaomimimo.com" not in base:
        out["base_url"] = base.replace("xiaomimi.com", "xiaomimimo.com")
    return out


def load_store() -> dict[str, Any]:
    """读取完整配置仓（多方案）。兼容旧单配置格式。"""
    store = _default_store()
    if CONFIG_PATH.is_file():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if isinstance(data, dict) and "profiles" in data and isinstance(data.get("profiles"), dict):
            profiles = {}
            for pid, p in data["profiles"].items():
                if isinstance(p, dict):
                    profiles[str(pid)] = _normalize_profile(p)
            if profiles:
                store["profiles"] = profiles
            store["active_id"] = data.get("active_id") or next(iter(profiles), "deepseek")
        elif isinstance(data, dict) and ("base_url" in data or "model" in data):
            # 旧格式：单配置 → 迁移为一个 profile
            store = {
                "active_id": "default",
                "profiles": {"default": _normalize_profile(data)},
            }
    if store.get("active_id") not in store["profiles"]:
        store["active_id"] = next(iter(store["profiles"]), "deepseek")

    # 环境变量覆盖当前激活方案
    active = store["profiles"][store["active_id"]]
    if not active.get("api_key"):
        active["api_key"] = os.environ.get("TRADES_LLM_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    if os.environ.get("TRADES_LLM_BASE"):
        active["base_url"] = os.environ["TRADES_LLM_BASE"]
    if os.environ.get("TRADES_LLM_MODEL"):
        active["model"] = os.environ["TRADES_LLM_MODEL"]
    return store


def save_store(store: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "active_id": store.get("active_id"),
        "profiles": {
            pid: _normalize_profile(p) for pid, p in (store.get("profiles") or {}).items()
        },
    }
    if not payload["profiles"]:
        payload = _default_store()
    if payload["active_id"] not in payload["profiles"]:
        payload["active_id"] = next(iter(payload["profiles"]))
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def load_config() -> dict[str, Any]:
    """返回当前激活方案（兼容旧接口）。"""
    store = load_store()
    cfg = dict(store["profiles"][store["active_id"]])
    cfg["enabled"] = True
    return cfg


def save_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """按旧接口保存到当前激活方案。"""
    store = load_store()
    active_id = store["active_id"]
    merged = _normalize_profile({**store["profiles"][active_id], **cfg})
    if cfg.get("clear_key"):
        merged["api_key"] = ""
    elif cfg.get("api_key"):
        merged["api_key"] = cfg["api_key"]
    store["profiles"][active_id] = merged
    save_store(store)
    return merged


def upsert_profile(profile_id: str, data: dict[str, Any], activate: bool = True) -> dict[str, Any]:
    store = load_store()
    pid = (profile_id or "").strip() or "custom"
    base = store["profiles"].get(pid, dict(DEFAULT_PROFILE))
    merged = _normalize_profile({**base, **{k: data[k] for k in PROFILE_FIELDS if k in data}})
    if data.get("clear_key"):
        merged["api_key"] = ""
    elif data.get("api_key"):
        merged["api_key"] = data["api_key"]
    if not merged.get("label"):
        merged["label"] = pid
    store["profiles"][pid] = merged
    if activate:
        store["active_id"] = pid
    save_store(store)
    return {"id": pid, "profile": merged}


def delete_profile(profile_id: str) -> dict[str, Any]:
    store = load_store()
    pid = str(profile_id)
    if pid not in store["profiles"]:
        raise ValueError("方案不存在")
    if len(store["profiles"]) <= 1:
        raise ValueError("至少保留一个模型方案")
    del store["profiles"][pid]
    if store.get("active_id") == pid:
        store["active_id"] = next(iter(store["profiles"]))
    save_store(store)
    return {"ok": True, "active_id": store["active_id"], "ids": list(store["profiles"].keys())}


def set_active(profile_id: str) -> dict[str, Any]:
    store = load_store()
    pid = str(profile_id)
    if pid not in store["profiles"]:
        raise ValueError("方案不存在")
    store["active_id"] = pid
    save_store(store)
    return {"ok": True, "active_id": pid, "profile": store["profiles"][pid]}


def public_store(store: dict[str, Any] | None = None) -> dict[str, Any]:
    """脱敏后的配置，供前端展示。"""
    store = store or load_store()
    profiles = {}
    for pid, p in store["profiles"].items():
        q = dict(p)
        key = q.get("api_key") or ""
        q["api_key_masked"] = mask_key(key)
        q["has_key"] = bool(key)
        q.pop("api_key", None)
        profiles[pid] = q
    return {
        "active_id": store["active_id"],
        "profiles": profiles,
        "presets": PRESETS,
    }


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "***"
    return key[:4] + "***" + key[-4:]


def _chat_url(cfg: dict[str, Any]) -> str:
    base = str(cfg.get("base_url") or "").strip().rstrip("/")
    if not base:
        raise ValueError("接口地址（Base URL）为空，请填写完整地址，例如 https://api.deepseek.com/v1")
    if not re.match(r"^https?://", base, re.I):
        raise ValueError(f"接口地址无效（需以 http:// 或 https:// 开头）：{base[:80]}")
    if base.endswith("/chat/completions"):
        return base
    path = str(cfg.get("chat_path") or "/chat/completions")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def _make_ssl_context(verify: bool = True):
    """兼容代理/企业网关导致的 TLS 异常。"""
    import ssl

    try:
        ctx = ssl.create_default_context()
    except Exception:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    # 兼容部分网关：允许 TLS1.2+
    try:
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    except Exception:
        pass
    return ctx


def _http_post_json(url: str, payload: dict, headers: dict, timeout: int, verify: bool = True) -> dict:
    import ssl
    import urllib.error
    import urllib.request

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_err: Exception | None = None

    def once(use_verify: bool) -> dict:
        nonlocal last_err
        ctx = _make_ssl_context(verify=use_verify)
        handlers = []
        if url.startswith("https://"):
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        # 尊重系统代理；失败再试直连
        opener = urllib.request.build_opener(*handlers)
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise ValueError(f"大模型接口 HTTP {e.code}: {body[:300]}") from e
        except Exception as e:
            last_err = e
            raise

    try:
        return once(verify)
    except ValueError:
        raise
    except Exception as e1:
        # SSL/网络异常：先关闭证书校验再试一次（常见于公司代理 MITM）
        if verify and ("SSL" in str(e1) or "EOF" in str(e1) or "certificate" in str(e1).lower()):
            try:
                return once(False)
            except ValueError:
                raise
            except Exception as e2:
                last_err = e2
        # 再尝试不走代理（有些环境代理会掐断 TLS）
        try:
            import urllib.request as ur

            proxy_handler = ur.ProxyHandler({})
            ctx = _make_ssl_context(verify=False)
            opener = ur.build_opener(proxy_handler, ur.HTTPSHandler(context=ctx))
            req = ur.Request(url, data=data, headers=headers, method="POST")
            with opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except ValueError:
            raise
        except Exception as e3:
            last_err = e3

    msg = str(last_err)
    if "getaddrinfo" in msg or "Name or service" in msg or "11001" in msg:
        raise ValueError(
            "无法解析接口域名（DNS 失败）。请检查 Base URL 是否正确、是否能上网。"
            "正确示例：https://api.deepseek.com/v1 或 https://api.xiaomimimo.com/v1"
            f"详情：{msg[:160]}"
        )
    if "SSL" in msg or "EOF" in msg or "certificate" in msg.lower():
        raise ValueError(
            "无法连接大模型接口（TLS/SSL 被中断）。"
            "常见原因：公司代理/防火墙拦截 HTTPS、网络不稳。"
            "可尝试：1) 切换网络或关代理 2) 本地 Ollama。"
            f"详情：{msg[:180]}"
        )
    raise ValueError(f"无法连接大模型接口：{msg[:200]}")


def chat(messages: list[dict[str, str]], cfg: dict[str, Any] | None = None) -> str:
    """调用 OpenAI 兼容 chat completions。"""
    cfg = cfg or load_config()
    url = _chat_url(cfg)
    local_hint = "localhost" in url or "127.0.0.1" in url
    if not cfg.get("api_key") and not local_hint and cfg.get("api_style") != "openai_no_auth":
        raise ValueError("未配置 API Key，请先在「大模型设置」中填写")

    payload: dict[str, Any] = {
        "model": cfg.get("model") or "custom-model",
        "messages": messages,
        "temperature": cfg.get("temperature") if cfg.get("temperature") is not None else 0.1,
        "stream": False,
    }
    if cfg.get("max_tokens"):
        payload["max_tokens"] = int(cfg["max_tokens"])

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.get('api_key') or 'no-key'}",
    }
    # 自定义请求头（可覆盖 Authorization）
    extra = cfg.get("extra_headers") or {}
    if isinstance(extra, dict):
        for k, v in extra.items():
            if k and v is not None:
                headers[str(k)] = str(v)
    if cfg.get("api_style") == "openai_no_auth":
        headers.pop("Authorization", None)

    timeout = int(cfg.get("timeout") or 60)
    verify = bool(cfg.get("ssl_verify", True))
    data = _http_post_json(url, payload, headers, timeout, verify=verify)

    try:
        return data["choices"][0]["message"]["content"] or ""
    except Exception as e:
        raise ValueError(f"响应格式异常：{str(data)[:300]}") from e


def chat_stream(messages: list[dict[str, str]], cfg: dict[str, Any] | None = None):
    """流式对话：优先 OpenAI stream，失败则整段生成后按块 yield。"""
    cfg = cfg or load_config()
    url = _chat_url(cfg)
    local_hint = "localhost" in url or "127.0.0.1" in url
    if not cfg.get("api_key") and not local_hint and cfg.get("api_style") != "openai_no_auth":
        raise ValueError("未配置 API Key，请先在「大模型设置」中填写")

    payload: dict[str, Any] = {
        "model": cfg.get("model") or "custom-model",
        "messages": messages,
        "temperature": cfg.get("temperature") if cfg.get("temperature") is not None else 0.1,
        "stream": True,
    }
    if cfg.get("max_tokens"):
        payload["max_tokens"] = int(cfg["max_tokens"])

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {cfg.get('api_key') or 'no-key'}",
    }
    extra = cfg.get("extra_headers") or {}
    if isinstance(extra, dict):
        for k, v in extra.items():
            if k and v is not None:
                headers[str(k)] = str(v)
    if cfg.get("api_style") == "openai_no_auth":
        headers.pop("Authorization", None)

    import ssl
    import urllib.request

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ctx = _make_ssl_context(verify=bool(cfg.get("ssl_verify", True)))
    handlers = [urllib.request.HTTPSHandler(context=ctx)] if url.startswith("https://") else []
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    timeout = int(cfg.get("timeout") or 60)

    try:
        with opener.open(req, timeout=timeout) as resp:
            buf = b""
            while True:
                chunk = resp.read(256)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line or not line.startswith(b"data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == b"[DONE]":
                        return
                    try:
                        obj = json.loads(raw.decode("utf-8", errors="replace"))
                        delta = obj.get("choices", [{}])[0].get("delta") or {}
                        text = delta.get("content") or ""
                        if text:
                            yield text
                    except Exception:
                        continue
        return
    except Exception:
        # 回退：非流式整段，再切块输出
        cfg2 = dict(cfg)
        full = chat(messages, cfg2)
        step = 12
        for i in range(0, len(full), step):
            yield full[i : i + step]


def parse_json_reply(text: str) -> Any:
    """从模型回复中解析 JSON（兼容 ```json 包裹）。"""
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("{") if "{" in s else 0 :]
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        return json.loads(s[start : end + 1])
    start = s.find("[")
    end = s.rfind("]")
    if start >= 0 and end > start:
        return json.loads(s[start : end + 1])
    raise ValueError("模型未返回合法 JSON")


VALIDATE_SYSTEM = """你是外贸客户资料清洗质检员。根据给定线索行，判断清洗结果是否可靠，并给出简短中文意见。
只输出 JSON，不要其它文字。格式：
{
  "rows": [
    {
      "index": 0,
      "ok": true,
      "issues": ["问题1"],
      "suggestions": ["建议1"],
      "confidence": 0.9
    }
  ],
  "summary": "整体评价一句话"
}
关注点：
1) 公司名称是否像真实企业、是否中英文混杂噪音
2) 手机号是否为中国大陆手机号、是否与公司/地区明显不匹配
3) 官网域名是否规范、是否与公司名无关
4) 行业/主营/关键词是否互相矛盾
5) 是否仍缺关键字段（公司名或电话）
不确定时 ok=false 且在 issues 里说明。"""


def validate_rows(rows: list[dict[str, Any]], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """批量 AI 校验清洗结果行。"""
    cfg = cfg or load_config()
    batch_size = max(1, min(int(cfg.get("batch_size") or 8), 20))
    all_rows: list[dict] = []
    summaries: list[str] = []

    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        slim = []
        for offset, r in enumerate(chunk):
            slim.append({
                "index": i + offset,
                "公司名称": r.get("公司名称", ""),
                "姓名": r.get("姓名", ""),
                "手机": r.get("手机", ""),
                "座机": r.get("座机", ""),
                "官网": r.get("官网", ""),
                "所属地区": r.get("所属地区", ""),
                "行业/主营产品": r.get("行业/主营产品", ""),
                "关键词": r.get("关键词", ""),
                "备注": r.get("备注", ""),
            })
        user = "请校验以下客户线索清洗结果：\n" + json.dumps(slim, ensure_ascii=False)
        raw = chat(
            [
                {"role": "system", "content": VALIDATE_SYSTEM},
                {"role": "user", "content": user},
            ],
            cfg,
        )
        parsed = parse_json_reply(raw)
        if isinstance(parsed, dict):
            all_rows.extend(parsed.get("rows") or [])
            if parsed.get("summary"):
                summaries.append(str(parsed["summary"]))
        elif isinstance(parsed, list):
            all_rows.extend(parsed)

    all_rows.sort(key=lambda x: int(x.get("index", 0)))
    return {
        "rows": all_rows,
        "summary": " ".join(summaries)[:500],
        "checked": len(all_rows),
    }


MAP_SYSTEM = """你是表格字段映射助手。给定源表列名列表和候选标准字段，输出最佳映射。
只输出 JSON：
{"mapping": {"company_name": "源列名", "mobile": "源列名", ...}, "notes": "一句话说明"}
标准字段键：company_name, contact_name, title, mobile, landline, website, region, industry, keyword, trade_attr, credit_code, source_channel。
只映射有把握的字段。"""


def suggest_mapping_ai(columns: list[str], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """用大模型建议字段映射。"""
    cfg = cfg or load_config()
    user = f"源表列名：{json.dumps(columns, ensure_ascii=False)}"
    raw = chat(
        [
            {"role": "system", "content": MAP_SYSTEM},
            {"role": "user", "content": user},
        ],
        cfg,
    )
    parsed = parse_json_reply(raw)
    mapping = (parsed or {}).get("mapping") or {}
    clean_map = {k: v for k, v in mapping.items() if v in columns}
    return {"mapping": clean_map, "notes": (parsed or {}).get("notes", "")}


def test_connection(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """连通性测试。"""
    cfg = cfg or load_config()
    raw = chat(
        [{"role": "user", "content": "请只回复：OK"}],
        cfg,
    )
    return {
        "success": True,
        "reply": raw[:100],
        "model": cfg.get("model"),
        "base_url": cfg.get("base_url"),
        "url": _chat_url(cfg),
    }


def clone_preset(preset_id: str) -> dict[str, Any]:
    """从预设克隆一份自定义配置。"""
    preset = next((p for p in PRESETS if p.get("id") == preset_id), None)
    if not preset:
        raise ValueError("预设不存在")
    p = deepcopy(DEFAULT_PROFILE)
    p.update({k: preset[k] for k in ("label", "base_url", "model", "api_style") if k in preset})
    if preset.get("chat_path"):
        p["chat_path"] = preset["chat_path"]
    return p
