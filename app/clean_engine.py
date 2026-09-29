# -*- coding: utf-8 -*-
"""TradeS Agent · 清洗引擎（对齐武汉某公司导入模板 + 2026-09 工作记录规则）

硬性规则：
1. 手机号：1 开头 11 位
2. 去 +86 / 86 / 0086 前缀
3. 去掉座机
4. 去掉国际号（+853/+886/+852 等）
5. 多号码：常用电话 / 备用电话1 / 备用电话2
6. 按公司名称去重，保留第一条有效记录
7. 删除无手机号记录
"""
from __future__ import annotations

import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# 某公司模板列
# ---------------------------------------------------------------------------

MAIBANG_COLUMNS = [
    "公司名称", "部门", "公司网址", "网站网址", "姓名", "岗位",
    "常用电话", "备用电话1", "备用电话2", "性别", "生日",
    "微信", "钉钉", "邮箱", "QQ", "旺旺", "个人传真", "淘到客户时间",
]

MOBILE_SLOTS = ["常用电话", "备用电话1", "备用电话2"]

FIELD_ALIASES: dict[str, list[str]] = {
    "company_name": ["公司名称", "公司", "企业名称", "公司名", "店铺名", "客户名称", "单位名称", "企业", "company"],
    "department": ["部门", "department"],
    "website": ["公司网址", "网站网址", "网站", "网址", "官网", "链接", "website", "url", "site"],
    "contact_name": ["姓名", "联系人", "联系人姓名", "客户姓名", "name", "contact"],
    "title": ["岗位", "职位", "职务", "title"],
    "mobile": ["常用电话", "手机", "手机号", "手机号码", "移动电话", "联系电话", "电话", "联系方式", "mobile", "phone", "tel"],
    "mobile2": ["备用电话1", "备用电话", "备用", "电话2"],
    "mobile3": ["备用电话2", "电话3"],
    "email": ["邮箱", "电子邮件", "email"],
    "wechat": ["微信", "wechat"],
    "qq": ["qq"],
    "region": ["地区", "省", "市", "地址", "所属地区", "region", "city"],
    "industry": ["行业", "主营产品", "主营", "产品", "industry", "product"],
    "source_channel": ["来源", "渠道", "线索来源", "来源渠道", "source"],
}

DEFAULT_CLEANING: dict[str, Any] = {
    "mobile_pattern": r"^1\d{10}$",
    "strip_prefixes": ["+86", "86", "0086"],
    "drop_intl_prefixes": ["+853", "+886", "+852", "+81", "+82", "+852"],
    "drop_landline": True,
    "split_separators": ["、", "；", ";", "/", ",", " ", "　", "|", "｜", "\n", "\t"],
    "dedupe_key": "公司名称",
    "drop_empty_mobile": True,
    "mobile_slots": MOBILE_SLOTS,
    "template_columns": MAIBANG_COLUMNS,
    "split_rows": 1500,
}


def load_cleaning_config(path: Path | None = None) -> dict[str, Any]:
    """读取 config.json 中的 cleaning 段，缺省用 DEFAULT_CLEANING。"""
    cfg = dict(DEFAULT_CLEANING)
    p = path or Path(__file__).resolve().parent / "config.json"
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            cleaning = (data or {}).get("cleaning") or {}
            if isinstance(cleaning, dict):
                for k, v in cleaning.items():
                    cfg[k] = v
        except Exception:
            pass
    return cfg


# ---------------------------------------------------------------------------
# 读表 / 映射
# ---------------------------------------------------------------------------

def read_table(data: bytes, filename: str) -> pd.DataFrame:
    name = (filename or "").lower()
    bio = io.BytesIO(data)
    try:
        if name.endswith((".xlsx", ".xls", ".xlsm")):
            df = pd.read_excel(bio, dtype=str)
        else:
            try:
                bio.seek(0)
                df = pd.read_csv(bio, dtype=str, encoding="utf-8-sig", on_bad_lines="skip")
            except UnicodeDecodeError:
                bio.seek(0)
                df = pd.read_csv(bio, dtype=str, encoding="gbk", on_bad_lines="skip")
    except Exception:
        bio.seek(0)
        try:
            df = pd.read_excel(bio, dtype=str)
        except Exception as e:
            raise ValueError(f"无法解析文件：{e}") from e

    df = df.dropna(how="all").reset_index(drop=True)
    df = df.dropna(axis=1, how="all")
    if df.empty:
        return df
    df.columns = [str(c).strip() for c in df.columns]
    return df


def merge_tables(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def suggest_source(filename: str, columns: list[str]) -> str:
    text = f"{filename} {' '.join(columns)}".lower()
    if "广交会" in text or "canton" in text:
        return "广交会"
    if any(k in text for k in ("中国制造", "made-in-china", "mic")):
        return "中国制造"
    if any(k in text for k in ("阿里", "alibaba", "国际站")):
        return "阿里巴巴"
    return "自定义"


def _norm_header(s: str) -> str:
    return re.sub(r"[\s　*（）()【】\[\]:：]+", "", str(s)).lower()


def auto_map_columns(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    used: set[str] = set()
    norm_cols = {c: _norm_header(c) for c in columns}

    for field, aliases in FIELD_ALIASES.items():
        best, best_score = None, 0
        for col, ncol in norm_cols.items():
            if col in used or not ncol:
                continue
            score = 0
            for a in aliases:
                an = _norm_header(a)
                if ncol == an:
                    score = 100
                elif an and (an in ncol or ncol in an):
                    score = max(score, 70)
            if score > best_score:
                best, best_score = col, score
        if best and best_score >= 70:
            mapping[field] = best
            used.add(best)

    if "mobile" not in mapping:
        for col in columns:
            n = _norm_header(col)
            if any(k in n for k in ("手机", "电话", "联系方式", "mobile", "phone", "常用")):
                mapping["mobile"] = col
                break
    return mapping


# ---------------------------------------------------------------------------
# 电话清洗（工作记录硬规则）
# ---------------------------------------------------------------------------

def _clean_text(v: Any) -> str:
    s = str(v if v is not None else "").strip()
    if s.lower() in ("nan", "none", "null", "-", "—"):
        return ""
    return re.sub(r"\s+", " ", s)


def extract_valid_mobiles(raw: Any, cleaning: dict[str, Any] | None = None) -> list[str]:
    """从字段提取合规手机号（1 开头 11 位），去前缀、丢座机/国际号，保序去重。"""
    cfg = cleaning or DEFAULT_CLEANING
    s = _clean_text(raw)
    if not s:
        return []

    # 统一去常见前缀（含 +86 / 0086 / 裸 86）
    for pfx in sorted(cfg.get("strip_prefixes") or ["+86", "86", "0086"], key=len, reverse=True):
        s = s.replace(pfx, " ")
        s = s.replace(pfx.replace("+", ""), " ") if pfx.startswith("+") else s

    # 国际号直接剔除段
    for pfx in cfg.get("drop_intl_prefixes") or []:
        s = s.replace(pfx, " ")
        if pfx.startswith("+"):
            s = s.replace(pfx[1:], " ")

    seps = cfg.get("split_separators") or DEFAULT_CLEANING["split_separators"]
    pat = "".join(re.escape(x) for x in seps if x)
    chunks = re.split(f"[{pat}]+" if pat else r"[\s，,;；/|｜、]+", s)

    found: list[str] = []
    for chunk in chunks + [s]:
        digits = re.sub(r"\D", "", chunk or "")
        if not digits:
            continue
        # 可能粘在一起：提取所有 11 位手机
        for m in re.findall(r"1\d{10}", digits):
            if re.fullmatch(cfg.get("mobile_pattern") or r"^1\d{10}$", m):
                found.append(m)
        # 整串即手机
        if re.fullmatch(r"1\d{10}", digits) and digits not in found:
            found.append(digits)

    # 再从原串兜底提取
    digits_all = re.sub(r"\D", "", s)
    for m in re.findall(r"1\d{10}", digits_all):
        if m not in found:
            found.append(m)

    out, seen = [], set()
    for x in found:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out[:5]


def _clean_website(v: Any) -> str:
    s = _clean_text(v)
    if not s:
        return ""
    s = re.split(r"[\s，,;；|｜]", s)[0]
    s = re.sub(r"^https?://", "", s, flags=re.I)
    s = s.split("?")[0].split("#")[0].strip("/")
    return s if s and "." in s else ""


# ---------------------------------------------------------------------------
# 主清洗流程
# ---------------------------------------------------------------------------

def run_maibang_clean(
    df: pd.DataFrame,
    mapping: dict[str, str],
    source: str = "自定义",
    cleaning: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按某公司规则清洗。返回 rows / stats / dropped_samples。"""
    cfg = cleaning or DEFAULT_CLEANING
    slots = list(cfg.get("mobile_slots") or MOBILE_SLOTS)
    n = len(df)

    def col(field: str) -> pd.Series | None:
        c = mapping.get(field)
        if c and c in df.columns:
            return df[c]
        return None

    rows: list[dict[str, Any]] = []
    stats = {
        "raw_count": n,
        "cleaned_count": 0,
        "valid_rate": 0.0,
        "dropped_no_mobile": 0,
        "dropped_landline_only": 0,
        "dropped_intl_only": 0,
        "duplicated_company": 0,
        "has_backup_phone": 0,
        "multi_mobile": 0,
        "source": source,
    }
    dropped_samples: list[dict[str, str]] = []
    seen_company: set[str] = set()

    mobile_col = col("mobile")
    mobile2_col = col("mobile2")
    mobile3_col = col("mobile3")
    company_col = col("company_name")

    for i in range(n):
        company = _clean_text(company_col.iloc[i]) if company_col is not None else ""
        raw_cells = []
        for c in (mobile_col, mobile2_col, mobile3_col):
            if c is not None:
                raw_cells.append(str(c.iloc[i]))
        raw_join = " ".join(raw_cells)
        mobiles = extract_valid_mobiles(raw_join, cfg)

        # 删除原因统计
        if not mobiles:
            digits = re.sub(r"\D", "", _clean_text(raw_join))
            if not digits:
                stats["dropped_no_mobile"] += 1
                reason = "无手机号"
            elif digits.startswith("0") or (len(digits) >= 10 and not digits.startswith("1")):
                stats["dropped_landline_only"] += 1
                reason = "仅座机/无效号"
            elif any(p.replace("+", "") in digits for p in (cfg.get("drop_intl_prefixes") or []) if p):
                stats["dropped_intl_only"] += 1
                reason = "仅国际号"
            else:
                stats["dropped_no_mobile"] += 1
                reason = "无有效手机"
            if len(dropped_samples) < 8:
                dropped_samples.append({"公司名称": company, "原始电话": _clean_text(raw_join)[:40], "原因": reason})
            continue

        # 验收：至少公司名 + 有效常用电话
        if not company:
            stats["dropped_no_mobile"] += 1
            if len(dropped_samples) < 12:
                dropped_samples.append({"公司名称": "(空)", "原始电话": mobiles[0] if mobiles else "", "原因": "缺公司名称"})
            continue

        # 公司名去重
        key = company
        if key in seen_company:
            stats["duplicated_company"] += 1
            if len(dropped_samples) < 12:
                dropped_samples.append({"公司名称": company, "原始电话": mobiles[0], "原因": "公司重复"})
            continue
        seen_company.add(key)

        record = {c: "" for c in (cfg.get("template_columns") or MAIBANG_COLUMNS)}
        record["公司名称"] = company
        record["部门"] = _clean_text(col("department").iloc[i]) if col("department") is not None else ""
        web = _clean_website(col("website").iloc[i]) if col("website") is not None else ""
        record["公司网址"] = web
        record["网站网址"] = web
        record["姓名"] = _clean_text(col("contact_name").iloc[i]) if col("contact_name") is not None else ""
        record["岗位"] = _clean_text(col("title").iloc[i]) if col("title") is not None else ""
        record["邮箱"] = _clean_text(col("email").iloc[i]) if col("email") is not None else ""
        record["微信"] = _clean_text(col("wechat").iloc[i]) if col("wechat") is not None else ""
        record["QQ"] = _clean_text(col("qq").iloc[i]) if col("qq") is not None else ""

        for idx, slot in enumerate(slots[:3]):
            record[slot] = mobiles[idx] if idx < len(mobiles) else ""

        if len(mobiles) > 1:
            stats["has_backup_phone"] += 1
        if len(mobiles) >= 2:
            stats["multi_mobile"] += 1

        rows.append(record)

    cleaned = pd.DataFrame(rows, columns=(cfg.get("template_columns") or MAIBANG_COLUMNS))
    stats["cleaned_count"] = int(len(cleaned))
    stats["valid_rate"] = round(stats["cleaned_count"] / n * 100, 1) if n else 0.0
    stats["dropped_samples"] = dropped_samples

    return {"rows": cleaned, "stats": stats, "cleaning": cfg}


def export_maibang_bytes(df: pd.DataFrame) -> bytes:
    cols = [c for c in MAIBANG_COLUMNS if c in df.columns]
    data = df[cols].copy()
    for c in data.columns:
        data[c] = data[c].map(lambda x: "" if x is None else str(x))

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        data.to_excel(writer, index=False, sheet_name="清洗结果")
        ws = writer.book["清洗结果"]
        from openpyxl.utils import get_column_letter
        from openpyxl.styles import Font, PatternFill, Alignment

        widths = {
            "公司名称": 28, "部门": 12, "公司网址": 24, "网站网址": 24, "姓名": 12, "岗位": 12,
            "常用电话": 14, "备用电话1": 14, "备用电话2": 14, "性别": 8, "生日": 12,
            "微信": 14, "钉钉": 12, "邮箱": 20, "QQ": 12, "旺旺": 12, "个人传真": 12, "淘到客户时间": 16,
        }
        for i, col in enumerate(ws.iter_cols(min_row=1, max_row=1), start=1):
            name = col[0].value
            ws.column_dimensions[get_column_letter(i)].width = widths.get(name, 14)
            if name in MOBILE_SLOTS or name in ("QQ", "个人传真", "微信", "钉钉", "旺旺"):
                for r in range(2, ws.max_row + 1):
                    cell = ws.cell(row=r, column=i)
                    cell.number_format = "@"
                    if cell.value is not None:
                        cell.value = str(cell.value)
        fill = PatternFill("solid", fgColor="1F4E79")
        font = Font(color="FFFFFF", bold=True, name="微软雅黑", size=11)
        for cell in ws[1]:
            cell.fill = fill
            cell.font = font
            cell.alignment = Alignment(vertical="center")
        ws.auto_filter.ref = ws.dimensions
        ws.freeze_panes = "A2"
    return buf.getvalue()


def split_and_export(
    df: pd.DataFrame,
    out_dir: Path,
    base_name: str,
    split_rows: int = 1500,
) -> dict[str, Any]:
    """写出主结果 + 分表，返回文件路径列表。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []

    main_path = out_dir / f"{base_name}.xlsx"
    main_path.write_bytes(export_maibang_bytes(df))
    files.append(str(main_path))

    split_dir = out_dir / "分表"
    if split_rows and len(df) > split_rows:
        split_dir.mkdir(parents=True, exist_ok=True)
        for i in range(0, len(df), split_rows):
            part = df.iloc[i : i + split_rows]
            idx = i // split_rows + 1
            p = split_dir / f"{base_name}_分表_{idx:02d}.xlsx"
            p.write_bytes(export_maibang_bytes(part))
            files.append(str(p))

    return {"files": files, "main": str(main_path), "split_count": max(0, (len(df) - 1) // split_rows) if split_rows else 0}
