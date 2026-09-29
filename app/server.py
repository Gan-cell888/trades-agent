# -*- coding: utf-8 -*-
"""TradeS Agent · 本地数据清洗服务（武汉某公司模板 / 工作记录规则）"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import llm_client
from agent_core import local_qa_answer, run_agent
import qa_store
from clean_engine import (
    MAIBANG_COLUMNS,
    auto_map_columns,
    export_maibang_bytes,
    load_cleaning_config,
    merge_tables,
    read_table,
    run_maibang_clean,
    split_and_export,
    suggest_source,
)

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
CONFIG_PATH = BASE / "config.json"
OUT_DEFAULT = Path(os.path.expanduser("~")) / "Desktop" / "清洗"

QA_SYSTEM = """你是公司内部「数据清洗与线索整理」助手，服务外贸软件公司的业务同事。
你熟悉：广交会/中国制造/阿里巴巴线索清洗、手机号规则、武汉某公司导入模板。
清洗规则：手机号 1 开头 11 位；去掉号码前缀；去座机；去国际号；多号码按常用/备用1/备用2；
按公司名称去重；删除无手机号记录；导出列为某公司模板。
禁止编造清洗条数与路径；不确定写「待核实」；不泄露 Key。
回答中文、简洁、可执行。"""


def web_search(query: str, limit: int = 5) -> list[dict]:
    """从公开搜索引擎抓取标题/链接/摘要（尽力而为）。"""
    import re
    import urllib.parse
    import urllib.request

    q = urllib.parse.quote(query)
    candidates = [
        f"https://www.bing.com/search?q={q}&setlang=zh-CN",
        f"https://html.duckduckgo.com/html/?q={q}",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    for url in candidates:
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=6) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            results: list[dict] = []
            if "bing" in url:
                blocks = re.split(r'<li class="b_algo"', html, flags=re.I)[1:]
                for block in blocks:
                    tm = re.search(r'<a class="tilk"[^>]*href="([^"]+)"', block, re.I)
                    if tm:
                        link = tm.group(1)
                        label = re.search(r'aria-label="([^"]*)"', block, re.I)
                        title = label.group(1) if label else ""
                    else:
                        hm = re.search(r'<h2>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S | re.I)
                        if not hm:
                            continue
                        link, title = hm.group(1), hm.group(2)
                    if link.startswith("/"):
                        link = "https://www.bing.com" + link
                    if not link.startswith("http"):
                        continue
                    sm = re.search(r'<p[^>]*>(.*?)</p>', block, re.S | re.I)
                    if not sm:
                        sm = re.search(r'class="b_caption"[^>]*>(.*?)</div>', block, re.S | re.I)
                    snippet = re.sub(r"<[^>]+>", " ", sm.group(1) if sm else "")
                    snippet = re.sub(r"\s+", " ", snippet)[:220].strip()
                    title = re.sub(r"<[^>]+>", "", title or "").strip()
                    h2 = re.search(r"<h2[^>]*>\s*<a[^>]*>(.*?)</a>", block, re.S | re.I)
                    if h2:
                        t2 = re.sub(r"<[^>]+>", "", h2.group(1)).strip()
                        if t2:
                            title = t2
                    if not title:
                        title = urllib.parse.urlparse(link).netloc
                    results.append({"title": title[:80], "url": link, "snippet": snippet})
                    if len(results) >= limit:
                        break
            else:
                for m in re.finditer(
                    r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</',
                    html,
                    re.S | re.I,
                ):
                    link, title, snippet = m.group(1), m.group(2), m.group(3)
                    title = re.sub(r"<[^>]+>", "", title)[:80]
                    snippet = re.sub(r"<[^>]+>", "", snippet)[:220]
                    if "uddg=" in link:
                        link = urllib.parse.unquote(link.split("uddg=")[-1].split("&")[0])
                    if title and link:
                        results.append({"title": title, "url": link, "snippet": snippet})
                    if len(results) >= limit:
                        break
            if results:
                return results
        except Exception:
            continue
    return []


def load_app_config() -> dict:
    cfg = {
        "server": {"host": "127.0.0.1", "port": 8787, "auto_open_browser": True},
        "cleaning": load_cleaning_config(CONFIG_PATH),
    }
    if CONFIG_PATH.is_file():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if isinstance(data.get("server"), dict):
                    cfg["server"].update(data["server"])
                if isinstance(data.get("cleaning"), dict):
                    cfg["cleaning"].update(data["cleaning"])
        except Exception:
            pass
    return cfg


APP_CFG = load_app_config()
HOST = str(APP_CFG["server"].get("host") or "127.0.0.1")
PORT = int(os.environ.get("TRADES_PORT") or APP_CFG["server"].get("port") or 8787)

_STATE: dict = {
    "dfs": [],           # list[DataFrame]
    "filenames": [],
    "source": "自定义",
    "mapping": {},
    "last_result": None,
    "last_export": None,  # {"files": [], "stats": {}}
}


class Handler(BaseHTTPRequestHandler):
    server_version = "TradeSClean/0.3"

    def log_message(self, fmt, *args):
        sys.stderr.write("[TradeS] " + (fmt % args) + "\n")

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/health":
            return self._json({"ok": True, "port": PORT, "host": HOST})
        if path == "/api/llm/config":
            return self._json({"store": llm_client.public_store()})
        if path == "/api/qa/sessions":
            return self._json({"sessions": qa_store.list_sessions()})
        if path.startswith("/api/qa/session/"):
            sid = path.split("/api/qa/session/", 1)[1]
            item = qa_store.get_session(sid)
            if not item:
                return self._json({"error": "对话不存在"}, 404)
            return self._json({"session": item})
        if path.startswith("/api/clean/download/"):
            return self._download(path.split("/api/clean/download/", 1)[1])
        if path in ("/", "/index.html"):
            return self._file(STATIC / "index.html", "text/html; charset=utf-8")
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            fp = (STATIC / rel).resolve()
            if not str(fp).startswith(str(STATIC.resolve())) or not fp.is_file():
                return self._json({"error": "not found"}, 404)
            ctype = "application/octet-stream"
            suffix = fp.suffix.lower()
            mimes = {
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".webp": "image/webp",
                ".svg": "image/svg+xml",
                ".woff2": "font/woff2",
            }
            ctype = mimes.get(suffix, ctype)
            return self._file(fp, ctype)
        return self._json({"error": "not found"}, 404)

    def _file(self, fp: Path, ctype: str):
        if not fp.is_file():
            return self._json({"error": "not found"}, 404)
        self._send(200, fp.read_bytes(), ctype)

    def do_POST(self):
        path = unquote(urlparse(self.path).path)
        try:
            routes = {
                "/api/upload": lambda: self._upload(slot="df"),
                "/api/upload_b": lambda: self._upload(slot="df_b"),
                "/api/clean": self._clean,
                "/api/clean/run": self._clean,
                "/api/export": self._export,
                "/api/agent/run": self._agent_run,
                "/api/qa": self._qa,
                "/api/qa/stream": self._qa_stream,
                "/api/qa/upload": self._qa_upload,
                "/api/qa/search": self._qa_search,
                "/api/qa/session/save": self._qa_save,
                "/api/qa/session/delete": self._qa_delete,
                "/api/qa/sessions/clear": self._qa_clear,
                "/api/compare": self._compare,
                "/api/llm/config": self._llm_save_config,
                "/api/llm/profile": self._llm_save_profile,
                "/api/llm/profile/activate": self._llm_activate,
                "/api/llm/profile/delete": self._llm_delete_profile,
                "/api/llm/preset": self._llm_preset,
                "/api/llm/test": self._llm_test,
                "/api/llm/validate": self._llm_validate,
            }
            if path in routes:
                return routes[path]()
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    # -------- upload / clean / export --------

    def _parse_upload(self):
        body = self._read_body()
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" in ctype:
            return _parse_multipart_multi(body, ctype)
        payload = json.loads(body.decode("utf-8") or "{}")
        raw = payload.get("content", "")
        filename = payload.get("filename") or "pasted.csv"
        return [(filename, read_table(raw.encode("utf-8"), filename))]

    def _upload(self, slot: str = "df"):
        items = self._parse_upload()
        if not items:
            return self._json({"error": "未读到文件"}, 400)
        frames, names = [], []
        for filename, df in items:
            if df is None or df.empty:
                continue
            frames.append(df)
            names.append(filename)
        if not frames:
            return self._json({"error": "文件为空或无法解析"}, 400)

        merged = merge_tables(frames) if len(frames) > 1 else frames[0]
        columns = list(merged.columns)
        mapping = auto_map_columns(columns)
        source = suggest_source(" ".join(names), columns)

        if slot == "df":
            _STATE["dfs"] = frames
            _STATE["filenames"] = names
            _STATE["mapping"] = mapping
            _STATE["source"] = source
            _STATE["last_result"] = None
            _STATE["last_export"] = None
        _STATE[f"{slot}_merged"] = merged

        sample = merged.head(8).astype(str).fillna("").to_dict(orient="records")
        return self._json({
            "filename": " + ".join(names),
            "filenames": names,
            "source": source,
            "rows": int(len(merged)),
            "columns": columns,
            "mapping": mapping,
            "sample": sample,
            "template_columns": MAIBANG_COLUMNS,
        })

    def _clean(self):
        merged = _STATE.get("df_merged")
        if merged is None or merged.empty:
            return self._json({"error": "请先上传表格"}, 400)
        payload = json.loads(self._read_body().decode("utf-8") or "{}") or {}
        mapping = payload.get("mapping") or _STATE.get("mapping") or {}
        source = payload.get("source") or _STATE.get("source") or "自定义"
        cleaning = {**load_cleaning_config(CONFIG_PATH), **(payload.get("cleaning") or {})}

        result = run_maibang_clean(merged, mapping, source=source, cleaning=cleaning)
        _STATE["last_result"] = result

        rows = result["rows"]
        preview = rows.head(20).astype(str).fillna("").to_dict(orient="records")
        cols = list(rows.columns)
        return self._json({
            "stats": result["stats"],
            "columns": cols,
            "preview": preview,
            "source": source,
            "filename": " + ".join(_STATE.get("filenames") or []),
            "sheets": ["清洗结果"],
        })

    def _export(self):
        result = _STATE.get("last_result")
        if not result:
            return self._json({"error": "请先执行清洗"}, 400)
        payload = json.loads(self._read_body().decode("utf-8") or "{}") or {}
        source = payload.get("source") or _STATE.get("source") or "自定义"
        split_rows = int(payload.get("split_rows") or load_cleaning_config(CONFIG_PATH).get("split_rows") or 1500)
        out_dir = payload.get("output_dir") or load_cleaning_config(CONFIG_PATH).get("output_dir") or str(OUT_DEFAULT)
        out_dir_p = Path(out_dir).expanduser()

        base_name = f"{source}_清洗结果"
        written = split_and_export(result["rows"], out_dir_p, base_name, split_rows=split_rows)
        _STATE["last_export"] = written
        _STATE["last_export"]["stats"] = result["stats"]

        # 同时提供浏览器下载主文件
        main_path = Path(written["main"])
        raw = main_path.read_bytes()
        self._send(
            200,
            raw,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            {
                "Content-Disposition": f"attachment; filename*=UTF-8''{_url_quote(main_path.name)}",
                "X-Row-Count": str(result["stats"].get("cleaned_count", 0)),
                "X-Output-Dir": _url_quote(str(out_dir_p)),
                "X-Files": _url_quote(" | ".join(written["files"])),
            },
        )

    def _download(self, token: str):
        # 简单 token：文件名编码
        name = unquote(token)
        last = _STATE.get("last_export") or {}
        for fp in last.get("files") or []:
            p = Path(fp)
            if p.name == name or fp.endswith(name):
                if p.is_file():
                    return self._send(
                        200,
                        p.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        {"Content-Disposition": f"attachment; filename*=UTF-8''{_url_quote(p.name)}"},
                    )
        return self._json({"error": "文件不存在"}, 404)

    # -------- agent / qa --------

    def _agent_run(self):
        merged = _STATE.get("df_merged")
        if merged is None or merged.empty:
            return self._json({"error": "请先上传表格"}, 400)
        payload = json.loads(self._read_body().decode("utf-8") or "{}") or {}
        instruction = (payload.get("instruction") or "").strip()
        if not instruction:
            return self._json({"error": "请填写清洗指令"}, 400)
        out = run_agent(
            merged,
            instruction,
            source=_STATE.get("source") or "自定义",
            mapping=payload.get("mapping") or _STATE.get("mapping"),
            use_llm=bool(payload.get("use_llm", True)),
        )
        cleaned = out.get("cleaned") or {}
        _STATE["last_result"] = cleaned
        return self._json({
            "steps": out.get("steps"),
            "intent": out.get("intent"),
            "stats": out.get("stats"),
            "columns": out.get("preview_columns") or [],
            "preview": out.get("preview") or [],
            "sheets": out.get("sheets") or ["清洗结果"],
            "review": (out.get("result_summary") or {}).get("review"),
        })

    def _qa(self):
        payload = json.loads(self._read_body().decode("utf-8") or "{}") or {}
        question = (payload.get("question") or "").strip()
        history = payload.get("history") or []
        role = payload.get("role") or "clean"
        if not question:
            return self._json({"error": "请输入问题"}, 400)
        role_hint = {
            "clean": "重点回答清洗规则：手机号、去重、删除、导出。",
            "map": "重点回答字段映射与某公司模板列。",
            "quality": "重点回答有效率、删除原因、质量口径。",
            "ops": "重点回答工作台操作步骤。",
        }.get(role, "")
        try:
            cfg = llm_client.load_config()
            has_llm = bool(cfg.get("api_key")) or "127.0.0.1" in str(cfg.get("base_url", "")) or "localhost" in str(cfg.get("base_url", ""))
            if has_llm and payload.get("use_llm", True):
                msgs = [{"role": "system", "content": QA_SYSTEM + ("\n" + role_hint if role_hint else "")}]
                for h in history[-6:]:
                    r = "assistant" if h.get("role") == "bot" else "user"
                    msgs.append({"role": r, "content": str(h.get("text") or "")[:500]})
                msgs.append({"role": "user", "content": question})
                reply = llm_client.chat(msgs, cfg)
                return self._json({"reply": reply, "source": "llm"})
        except Exception as e:
            return self._json({"reply": local_qa_answer(question), "source": "local", "note": f"模型不可用：{e}"})
        return self._json({"reply": local_qa_answer(question), "source": "local"})

    def _qa_search(self):
        """简易联网搜索：抓取公开搜索结果摘要，供问答引用。"""
        payload = json.loads(self._read_body().decode("utf-8") or "{}") or {}
        q = (payload.get("query") or "").strip()
        if not q:
            return self._json({"error": "请输入搜索词"}, 400)
        results = web_search(q, limit=int(payload.get("limit") or 5))
        return self._json({"ok": True, "query": q, "results": results, "count": len(results)})

    def _qa_upload(self):
        """附件上传：提取文本内容，供问答引用。"""
        body = self._read_body()
        ctype = self.headers.get("Content-Type", "")
        try:
            if "multipart/form-data" in ctype:
                items = _parse_multipart_multi(body, ctype)
            else:
                payload = json.loads(body.decode("utf-8") or "{}") or {}
                filename = payload.get("filename") or "file.txt"
                content = payload.get("content") or ""
                items = [(filename, content)]
        except Exception as e:
            return self._json({"error": f"上传失败：{e}"}, 400)

        files = []
        for filename, raw in items:
            text = ""
            if isinstance(raw, str):
                text = raw[:20000]
            else:
                try:
                    text = raw.decode("utf-8", errors="replace")[:20000]
                except Exception:
                    text = ""
            # 只保留可读文本片段
            text = "".join(ch if ch == "\n" or ch == "\t" or (32 <= ord(ch) < 127) or ord(ch) > 127 else " " for ch in text)
            files.append({
                "filename": filename,
                "chars": len(text),
                "preview": text[:2000],
                "content": text[:12000],
            })
        return self._json({"ok": True, "files": [{"filename": f["filename"], "chars": f["chars"], "preview": f["preview"]} for f in files], "contents": files})

    def _build_qa_messages(self, payload: dict) -> list:
        question = (payload.get("question") or "").strip()
        history = payload.get("history") or []
        role = payload.get("role") or "clean"
        attachments = payload.get("attachments") or []
        use_web = bool(payload.get("use_web_search"))
        role_hint = {
            "clean": "重点回答清洗规则：手机号、去重、删除、导出。",
            "map": "重点回答字段映射与某公司模板列。",
            "quality": "重点回答有效率、删除原因、质量口径。",
            "ops": "重点回答工作台操作步骤。",
        }.get(role, "")
        system = QA_SYSTEM + ("\n" + role_hint if role_hint else "")
        if use_web:
            system += "\n已启用联网搜索，回答时优先依据下方「联网检索结果」，并标注来源；无结果时说明未能联网获取。"
        msgs = [{"role": "system", "content": system}]
        for h in history[-6:]:
            r = "assistant" if h.get("role") == "bot" else "user"
            msgs.append({"role": r, "content": str(h.get("text") or "")[:500]})
        user_content = question
        if use_web and question:
            hits = web_search(question, limit=5)
            if hits:
                lines = ["【联网检索结果】"]
                for i, h in enumerate(hits, 1):
                    lines.append(f"{i}. {h.get('title')} | {h.get('url')}\n   {h.get('snippet')}")
                user_content = "\n".join(lines) + "\n\n请结合上述结果回答用户问题。\n" + question
        if attachments:
            parts = []
            for a in attachments[:3]:
                parts.append(f"【附件 {a.get('filename', 'file')}】\n{str(a.get('content') or a.get('preview') or '')[:4000]}")
            user_content = ("\n\n".join(parts) + "\n\n用户问题：" + user_content) if user_content else "\n\n".join(parts)
        msgs.append({"role": "user", "content": user_content[:8000]})
        return msgs

    def _qa_stream(self):
        """SSE 流式问答（HTTP chunked）。"""
        payload = json.loads(self._read_body().decode("utf-8") or "{}") or {}
        question = (payload.get("question") or "").strip()
        if not question and not payload.get("attachments"):
            return self._json({"error": "请输入问题"}, 400)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def emit(obj: dict):
            data = f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8")
            try:
                self.wfile.write(f"{len(data):x}\r\n".encode("ascii") + data + b"\r\n")
                self.wfile.flush()
            except Exception:
                pass

        def emit_done():
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except Exception:
                pass

        emit({"type": "meta", "ok": True})
        msgs = self._build_qa_messages(payload)
        full: list[str] = []
        try:
            cfg = llm_client.load_config()
            has_llm = bool(cfg.get("api_key")) or "127.0.0.1" in str(cfg.get("base_url", "")) or "localhost" in str(cfg.get("base_url", ""))
            if has_llm and payload.get("use_llm", True):
                for piece in llm_client.chat_stream(msgs, cfg):
                    full.append(piece)
                    emit({"type": "content", "content": piece})
            else:
                text = local_qa_answer(question or "请分析附件")
                for i in range(0, len(text), 12):
                    piece = text[i : i + 12]
                    full.append(piece)
                    emit({"type": "content", "content": piece})
        except Exception as e:
            text = local_qa_answer(question or "请分析附件")
            if not full:
                emit({"type": "content", "content": text})
                full.append(text)
            emit({"type": "note", "content": f"（模型不可用：{str(e)[:120]}）"})
        emit({"type": "done", "content": "".join(full)})
        emit_done()

    def _qa_save(self):
        payload = json.loads(self._read_body().decode("utf-8") or "{}") or {}
        sid = payload.get("id") or ""
        messages = payload.get("messages") or []
        if not isinstance(messages, list):
            return self._json({"error": "messages 须为数组"}, 400)
        item = qa_store.save_messages(sid, messages, title=payload.get("title"))
        return self._json({"ok": True, "session": {
            "id": item["id"],
            "title": item.get("title"),
            "count": len(item.get("messages") or []),
            "updated_at": item.get("updated_at"),
        }})

    def _qa_delete(self):
        payload = json.loads(self._read_body().decode("utf-8") or "{}") or {}
        sid = payload.get("id") or ""
        if not sid:
            return self._json({"error": "缺少 id"}, 400)
        ok = qa_store.delete_session(str(sid))
        if not ok:
            return self._json({"error": "对话不存在"}, 404)
        return self._json({"ok": True, "sessions": qa_store.list_sessions()})

    def _qa_clear(self):
        n = qa_store.clear_all()
        return self._json({"ok": True, "removed": n, "sessions": []})

    def _compare(self):
        return self._json({"error": "当前版本请用「清洗去重」覆盖重复公司"}, 400)

    # -------- llm --------

    def _llm_save_config(self):
        payload = json.loads(self._read_body().decode("utf-8") or "{}") or {}
        llm_client.save_config(payload)
        return self._json({"ok": True, "store": llm_client.public_store()})

    def _llm_save_profile(self):
        payload = json.loads(self._read_body().decode("utf-8") or "{}") or {}
        pid = payload.get("id") or payload.get("profile_id") or "custom"
        data = payload.get("profile") or payload
        llm_client.upsert_profile(pid, data, activate=bool(payload.get("activate", True)))
        return self._json({"ok": True, "store": llm_client.public_store()})

    def _llm_activate(self):
        payload = json.loads(self._read_body().decode("utf-8") or "{}") or {}
        pid = payload.get("id") or payload.get("profile_id")
        if not pid:
            return self._json({"error": "缺少 id"}, 400)
        try:
            llm_client.set_active(str(pid))
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        return self._json({"ok": True, "store": llm_client.public_store()})

    def _llm_delete_profile(self):
        payload = json.loads(self._read_body().decode("utf-8") or "{}") or {}
        pid = payload.get("id") or payload.get("profile_id")
        if not pid:
            return self._json({"error": "缺少 id"}, 400)
        llm_client.delete_profile(str(pid))
        return self._json({"ok": True, "store": llm_client.public_store()})

    def _llm_preset(self):
        payload = json.loads(self._read_body().decode("utf-8") or "{}") or {}
        return self._json({"ok": True, "profile": llm_client.clone_preset(payload.get("preset_id") or "custom")})

    def _llm_test(self):
        payload = json.loads(self._read_body().decode("utf-8") or "{}") or {}
        # 允许「未保存就测试」：表单配置优先，id 仅用于取本地已存 Key
        store = llm_client.load_store()
        pid = str(payload.get("id") or payload.get("profile_id") or "")
        if pid and pid in store["profiles"]:
            cfg = dict(store["profiles"][pid])
        else:
            cfg = llm_client.load_config()
        for k in ("base_url", "model", "chat_path", "api_style", "temperature", "max_tokens", "extra_headers"):
            if payload.get(k) is not None:
                cfg[k] = payload[k]
        if payload.get("api_key"):
            cfg["api_key"] = payload["api_key"]
        if payload.get("timeout"):
            cfg["timeout"] = int(payload["timeout"])
        try:
            return self._json(llm_client.test_connection(cfg))
        except Exception as e:
            return self._json({"error": str(e)}, 502)

    def _llm_validate(self):
        result = _STATE.get("last_result")
        if not result:
            return self._json({"error": "请先执行清洗"}, 400)
        rows = result["rows"]
        records = rows.head(15).astype(str).fillna("").to_dict(orient="records")
        try:
            ai = llm_client.validate_rows(records)
        except Exception as e:
            return self._json({"error": f"AI 校验失败：{e}"}, 502)
        return self._json({
            "summary": ai.get("summary", ""),
            "checked": ai.get("checked"),
            "fail_count": 0,
            "preview": records[:10],
        })


def _url_quote(s: str) -> str:
    from urllib.parse import quote
    return quote(s)


def _parse_multipart_multi(body: bytes, ctype: str):
    m = re.search(r'boundary="?([^";]+)"?', ctype)
    if not m:
        raise ValueError("multipart boundary 缺失")
    boundary = b"--" + m.group(1).encode()
    parts = body.split(boundary)
    items = []
    for part in parts:
        if b"Content-Disposition" not in part:
            continue
        header, _, data = part.partition(b"\r\n\r\n")
        if b'name="file"' not in header and b'name="files"' not in header and b'name="file_b"' not in header:
            continue
        fn = re.search(rb'filename="([^"]+)"', header)
        filename = fn.group(1).decode("utf-8", errors="replace") if fn else "upload.xlsx"
        file_bytes = data.rstrip(b"\r\n")
        if not file_bytes:
            continue
        items.append((filename, read_table(file_bytes, filename)))
    return items


def _find_free_port(host: str, start: int) -> int:
    import socket

    port = start
    for _ in range(20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                port += 1
    return start


def main():
    os.chdir(BASE)
    global PORT
    PORT = _find_free_port(HOST, PORT)
    url = f"http://{HOST}:{PORT}"
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print("=" * 48)
    print("  [TradeS Agent] 服务已启动")
    print(f"  访问地址: {url}")
    print("  （浏览器应自动打开；若未打开请手动复制上方地址）")
    print("  按 Ctrl+C 可停止服务。")
    print("=" * 48)
    sys.stdout.flush()

    def _open():
        try:
            if APP_CFG["server"].get("auto_open_browser", True):
                webbrowser.open(url)
        except Exception:
            pass

    threading.Timer(0.8, _open).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[TradeS] 已停止")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
