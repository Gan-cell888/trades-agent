/* TradeS Agent · UI */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const FIELD_LABELS = [
  { key: "company_name", label: "公司名称", required: true },
  { key: "contact_name", label: "姓名" },
  { key: "title", label: "岗位" },
  { key: "mobile", label: "常用电话（手机）", required: true },
  { key: "mobile2", label: "备用电话1" },
  { key: "mobile3", label: "备用电话2" },
  { key: "website", label: "公司网址 / 网站网址" },
  { key: "department", label: "部门" },
  { key: "email", label: "邮箱" },
  { key: "wechat", label: "微信" },
  { key: "qq", label: "QQ" },
  { key: "region", label: "地区" },
  { key: "industry", label: "行业/主营" },
];

const state = {
  mapping: {},
  mappingB: null,
  columns: [],
  source: "其他",
  filename: "",
  hasB: false,
  view: "home",
  qaSessionId: null,
  qaRoleId: "clean",
  qaFiles: [],
};

/* Theme */
function applyTheme(mode) {
  document.documentElement.setAttribute("data-theme", mode);
  try {
    localStorage.setItem("trades_theme", mode);
  } catch (_) {}
  const label = $("#theme-label");
  if (label) label.textContent = mode === "light" ? "深色" : "明亮";
}
function initTheme() {
  let mode = "dark";
  try {
    mode = localStorage.getItem("trades_theme") || "dark";
  } catch (_) {}
  applyTheme(mode);
}

function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  applyTheme(cur === "light" ? "dark" : "light");
}

/* ---------- View routing ---------- */
function setView(name) {
  state.view = name;
  $("#view-home").classList.toggle("hidden", name !== "home");
  $("#view-workspace").classList.toggle("hidden", name !== "workspace");
  $("#view-qa").classList.toggle("hidden", name !== "qa");
  $$(".nav-link[data-view]").forEach((el) => {
    el.classList.toggle("is-active", el.dataset.view === name);
  });
  window.scrollTo({ top: 0, behavior: name === "home" ? "auto" : "smooth" });
}

$$("[data-view]").forEach((el) => {
  el.addEventListener("click", (e) => {
    e.preventDefault();
    setView(el.dataset.view);
    history.replaceState(null, "", el.dataset.view === "home" ? "#home" : "#workspace");
  });
});
$("#btn-enter-workspace")?.addEventListener("click", () => setView("workspace"));
$("#btn-enter-workspace-2")?.addEventListener("click", () => setView("workspace"));

/* ---------- Panels ---------- */
function setStep(n) {
  $$("#view-workspace .step").forEach((el) => {
    el.classList.toggle("active", Number(el.dataset.step) <= n);
  });
}

function showPanel(id) {
  ["#panel-upload", "#panel-map", "#panel-result", "#panel-agent"].forEach((s) => {
    $(s).classList.toggle("hidden", s !== id);
  });
}

function showError(msg) {
  const el = $("#upload-error");
  if (!msg) {
    el.classList.add("hidden");
    el.textContent = "";
    return;
  }
  el.textContent = msg;
  el.classList.remove("hidden");
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderTable(tableEl, columns, rows) {
  if (!tableEl) return;
  if (!columns || !columns.length) {
    tableEl.innerHTML = "";
    return;
  }
  const thead = `<thead><tr>${columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead>`;
  const body = rows
    .map((r) => `<tr>${columns.map((c) => `<td>${escapeHtml(r[c] ?? "")}</td>`).join("")}</tr>`)
    .join("");
  tableEl.innerHTML = thead + `<tbody>${body}</tbody>`;
}

function renderMapping() {
  const grid = $("#map-grid");
  grid.innerHTML = FIELD_LABELS.map((f) => {
    const cur = state.mapping[f.key] || "";
    const opts = [`<option value="">（不使用）</option>`]
      .concat(
        state.columns.map(
          (c) =>
            `<option value="${escapeHtml(c)}" ${c === cur ? "selected" : ""}>${escapeHtml(c)}</option>`
        )
      )
      .join("");
    return `<div class="map-item">
      <div class="label">${f.required ? "<i>*</i>" : ""}模板字段 · ${f.label}</div>
      <select data-field="${f.key}">${opts}</select>
    </div>`;
  }).join("");

  grid.querySelectorAll("select").forEach((sel) => {
    sel.addEventListener("change", () => {
      state.mapping[sel.dataset.field] = sel.value;
    });
  });
}

function collectMapping() {
  const mapping = {};
  $$("#map-grid select").forEach((sel) => {
    if (sel.value) mapping[sel.dataset.field] = sel.value;
  });
  return mapping;
}

function collectOptions() {
  return {
    split_rows: Number($("#opt-chunk")?.value || 1500),
  };
}

function handleUploadResult(data) {
  showError("");
  state.mapping = data.mapping || {};
  state.columns = data.columns || [];
  state.source = data.source || "其他";
  state.filename = data.filename || "";
  $("#file-name").textContent = data.filename || "—";
  $("#file-rows").textContent = data.rows ?? "—";
  const src = $("#source");
  src.value = ["阿里巴巴", "中国制造", "企查查", "其他"].includes(state.source)
    ? state.source
    : "其他";
  renderMapping();
  renderTable($("#sample-table"), data.columns, data.sample || []);
  showPanel("#panel-agent");
  setStep(2);
  $("#agent-error").classList.add("hidden");
  const und = $("#agent-understand");
  und.classList.remove("hidden");
  und.classList.add("ok");
  und.textContent = `已载入：${data.filename} · ${data.rows} 行。给 Agent 下一条清洗指令开始。`;
  $("#agent-steps").innerHTML = "";
  setView("workspace");
}

async function uploadFiles(fileList, endpoint = "/api/upload") {
  const fd = new FormData();
  const files = Array.from(fileList || []);
  if (!files.length) throw new Error("未选择文件");
  files.forEach((f) => fd.append("file", f, f.name));
  const res = await fetch(endpoint, { method: "POST", body: fd });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "上传失败");
  return data;
}

function renderQuality(report) {
  if (!report) {
    $("#quality").innerHTML = "";
    return;
  }
  const score = report.score ?? "—";
  const issues = (report.issues || [])
    .map(
      (it) => `<div class="q-item ${it.count ? "warn" : ""}">
        <b>${it.count}</b>
        <span>${escapeHtml(it.label)}</span>
        <em>${it.pct}%</em>
      </div>`
    )
    .join("");
  $("#quality").innerHTML = `
    <div class="q-score"><b>${score}</b><span>质量分 / 100</span></div>
    <div class="q-issues">${issues}</div>
    <p class="muted">${escapeHtml(report.preview_hint || "")}</p>
  `;
}

function renderStats(stats) {
  const items = [
    ["原始", stats.raw_count],
    ["清洗后", stats.cleaned_count],
    ["有效率%", stats.valid_rate],
    ["无手机删除", stats.dropped_no_mobile],
    ["公司重复", stats.duplicated_company],
    ["仅座机删除", stats.dropped_landline_only],
    ["有备用电话", stats.has_backup_phone],
  ];
  $("#stats").innerHTML = items
    .map(([k, v]) => `<div class="stat"><b>${v ?? "—"}</b><span>${k}</span></div>`)
    .join("");
}

function renderSheets(sheets) {
  $("#sheet-chips").innerHTML = (sheets || [])
    .map((s) => `<span class="chip">${escapeHtml(s)}</span>`)
    .join("");
}

function renderAgentSteps(steps) {
  const el = $("#agent-steps");
  if (!el) return;
  el.innerHTML = (steps || [])
    .map((s, i) => {
      const st = s.status || "done";
      const cls = st === "fail" ? "fail" : st === "warn" ? "warn" : "done";
      return `<li class="agent-step ${cls}">
        <span class="agent-step-no">${i + 1}</span>
        <div>
          <strong>${escapeHtml(s.title || s.tool)}</strong>
          <small>${escapeHtml(s.tool || "")}</small>
          <p>${escapeHtml(s.detail || "")}</p>
        </div>
      </li>`;
    })
    .join("");
}

/* ---------- LLM modal ---------- */
function showLlmMsg(text, ok = true) {
  const el = $("#llm-msg");
  el.textContent = text;
  el.classList.remove("hidden");
  el.classList.toggle("ok", ok);
}

function fillLlmForm(profile, id) {
  $("#llm-id").value = id || "custom";
  $("#llm-label").value = profile?.label || "";
  $("#llm-base").value = profile?.base_url || "";
  $("#llm-model").value = profile?.model || "";
  $("#llm-key").value = "";
  $("#llm-key").placeholder = profile?.has_key
    ? `已保存（${profile.api_key_masked}），留空则不修改`
    : "API Key";
  const path = $("#llm-path");
  if (path) {
    const p = profile?.chat_path || "/chat/completions";
    const opt = Array.from(path.options).find((o) => o.value === p);
    if (opt) path.value = p;
    else {
      const o = document.createElement("option");
      o.value = p;
      o.textContent = p;
      path.appendChild(o);
      path.value = p;
    }
  }
  const style = $("#llm-style");
  if (style) style.value = profile?.api_style || "openai";
  const timeout = $("#llm-timeout");
  if (timeout) timeout.value = profile?.timeout || 60;
  const temp = $("#llm-temp");
  if (temp) temp.value = profile?.temperature ?? 0.1;
}

function renderVendors(store) {
  const box = $("#llm-vendors");
  if (!box) return {};
  const profiles = store.profiles || {};
  const presets = store.presets || [];
  const active = store.active_id;

  // 合并：已保存方案 + 预设（未保存）
  const ids = [...Object.keys(profiles), ...presets.map((p) => p.id).filter((id) => !profiles[id])];
  box.innerHTML = ids
    .map((id) => {
      const p = profiles[id] || presets.find((x) => x.id === id) || {};
      const label = p.label || id;
      const icon = p.icon || (profiles[id] ? "●" : "○");
      const color = p.color || "#9ca3af";
      const mark = profiles[id] ? (id === active ? " · 当前" : " · 已保存") : "";
      return `<button type="button" class="vendor-chip ${id === active ? "is-active" : ""}" data-id="${escapeHtml(id)}">
        <span class="vendor-dot" style="background:${escapeHtml(color)}33;color:${escapeHtml(color)}">${escapeHtml(icon)}</span>
        ${escapeHtml(label)}${mark}
      </button>`;
    })
    .join("");

  box.querySelectorAll(".vendor-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.id;
      const p = profiles[id] || presets.find((x) => x.id === id) || {};
      fillLlmForm(p, id);
      const dot = $("#llm-status-dot");
      if (dot) dot.className = "llm-status-dot";
      // 已保存则切换为当前
      if (profiles[id] && id !== active) {
        fetch("/api/llm/profile/activate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        })
          .then((r) => r.json())
          .then(() => loadLlmStatus());
      }
    });
  });
  return profiles;
}

async function loadLlmStatus() {
  try {
    const r = await fetch("/api/llm/config");
    const data = await r.json();
    const store = data.store || {};
    const profiles = renderVendors(store);
    const activeId = store.active_id;
    const active = profiles[activeId];
    if (active) fillLlmForm(active, activeId);
    const pill = $("#llm-current-pill");
    if (pill && active) {
      pill.textContent = `${active.label || activeId} · ${active.model || ""}`;
    }
    const st = $("#llm-status");
    const mini = $("#llm-status-mini");
    const tip = active
      ? active.has_key || String(active.base_url || "").includes("127.0.0.1")
        ? `已接入 · ${active.label || activeId}`
        : `未配置 Key · 本地回答`
      : "未配置模型";
    if (st && active) st.textContent = tip;
    if (mini) mini.textContent = tip;
    return store;
  } catch (_) {
    return null;
  }
}

function openLlmPanel() {
  $("#panel-llm").classList.remove("hidden");
  loadLlmStatus();
}

function closeLlmPanel() {
  $("#panel-llm").classList.add("hidden");
  loadLlmStatus();
}

function parseExtraHeaders() {
  return {};
}

function collectLlmProfile() {
  return {
    label: $("#llm-label").value.trim() || $("#llm-id").value.trim() || "自定义",
    base_url: $("#llm-base").value.trim(),
    model: $("#llm-model").value.trim(),
    chat_path: $("#llm-path")?.value.trim() || "/chat/completions",
    api_style: $("#llm-style")?.value || "openai",
    timeout: Number($("#llm-timeout")?.value || 60),
    temperature: Number($("#llm-temp")?.value || 0.1),
    batch_size: 8,
    max_tokens: 2000,
    extra_headers: {},
  };
}

/* ---------- QA ---------- */
const QA_FAQ = [
  "怎么清洗原始数据？",
  "电话号码如何去掉号码前缀？",
  "如何去重并按中英文分表？",
  "怎么接入大模型？",
  "如何导出公司模板？",
  "质量分析怎么看？",
];

function renderQaFaq() {
  const box = $("#qa-faq");
  if (!box) return;
  box.innerHTML = QA_FAQ.map((q) => `<button type="button" class="chip chip-btn" data-q="${escapeHtml(q)}">${escapeHtml(q)}</button>`).join("");
  box.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("#qa-input").value = btn.dataset.q || btn.textContent;
      sendQa();
    });
  });
}

const QA_ROLES = [
  { id: "clean", name: "清洗专家", desc: "某公司规则与清洗指导" },
  { id: "map", name: "字段映射专家", desc: "列映射与模板导入" },
  { id: "quality", name: "数据质检", desc: "有效率与删除原因" },
  { id: "ops", name: "操作助手", desc: "工作台使用步骤" },
];

function renderQaRoles() {
  const box = $("#qa-roles");
  if (!box) return;
  box.innerHTML = QA_ROLES.map(
    (r) => `<li data-id="${r.id}" class="${state.qaRoleId === r.id ? "is-active" : ""}">
      <strong>${escapeHtml(r.name)}</strong>
      <span style="display:block;color:var(--text-faint);font-size:11px;margin-top:2px">${escapeHtml(r.desc)}</span>
    </li>`
  ).join("");
  box.querySelectorAll("li").forEach((el) => {
    el.addEventListener("click", () => {
      state.qaRoleId = el.dataset.id;
      const role = QA_ROLES.find((x) => x.id === state.qaRoleId) || QA_ROLES[0];
      const nameEl = $("#qa-role-name");
      const descEl = $("#qa-role-desc");
      if (nameEl) nameEl.textContent = role.name;
      if (descEl) descEl.textContent = role.desc;
      renderQaRoles();
    });
  });
}

function renderMarkdown(text) {
  // 轻量 Markdown（不依赖 CDN）
  let t = escapeHtml(text);
  t = t.replace(/```([\s\S]*?)```/g, (_, c) => `<pre><code>${c.replace(/^\n/, "")}</code></pre>`);
  t = t.replace(/`([^`]+)`/g, "<code>$1</code>");
  t = t.replace(/^### (.+)$/gm, "<p><strong>$1</strong></p>");
  t = t.replace(/^## (.+)$/gm, "<p><strong>$1</strong></p>");
  t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  t = t.replace(/^\s*[-*] (.+)$/gm, "<li>$1</li>");
  t = t.replace(/(<li>[\s\S]+?<\/li>)(?!\s*<li>)/g, "<ul>$1</ul>");
  t = t.replace(/\n{2,}/g, "</p><p>");
  t = t.replace(/\n/g, "<br/>");
  return `<div class="md"><p>${t}</p></div>`;
}

function appendQa(role, text) {
  const box = $("#qa-messages");
  const welcome = $("#qa-welcome");
  if (welcome) welcome.classList.add("hidden");
  const div = document.createElement("div");
  div.className = `qa-msg ${role}`;
  const bubble = document.createElement("div");
  bubble.className = role === "bot" ? "qa-bubble md" : "qa-bubble";
  if (role === "bot") bubble.innerHTML = renderMarkdown(text);
  else bubble.textContent = text;
  div.appendChild(bubble);
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function getQaMessages() {
  return $$("#qa-messages .qa-msg")
    .map((el) => ({
      role: el.classList.contains("user") ? "user" : "bot",
      text: el.querySelector(".qa-bubble")?.textContent || "",
    }))
    .filter((m) => m.text && m.text !== "正在思考…");
}

async function refreshQaHistory() {
  try {
    const res = await fetch("/api/qa/sessions");
    const data = await res.json();
    const box = $("#qa-history");
    if (!box) return;
    const sessions = data.sessions || [];
    if (!sessions.length) {
      box.innerHTML = `<li class="qa-hist-empty">暂无历史对话</li>`;
      return;
    }
    box.innerHTML = sessions
      .map(
        (s) => `<li class="qa-hist-item ${s.id === state.qaSessionId ? "is-active" : ""}" data-id="${escapeHtml(s.id)}">
          <div class="qa-hist-text">
            <strong>${escapeHtml(s.title || "未命名")}</strong>
            <span>${s.count || 0} 条</span>
          </div>
          <button type="button" class="qa-hist-del" data-del="${escapeHtml(s.id)}" title="删除该对话">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M9 7V5h6v2M7 7l1 12h8l1-12"/></svg>
          </button>
        </li>`
      )
      .join("");
    box.querySelectorAll("li[data-id]").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (e.target.closest(".qa-hist-del")) return;
        loadQaSession(el.dataset.id);
      });
    });
    box.querySelectorAll(".qa-hist-del").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const id = btn.dataset.del;
        if (!confirm("删除这条对话记录？")) return;
        const r = await fetch("/api/qa/session/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
        if (r.ok) {
          if (state.qaSessionId === id) resetQaToNew();
          else refreshQaHistory();
        }
      });
    });
  } catch (_) {
    /* ignore */
  }
}

async function loadQaSession(id) {
  if (!id) return;
  const res = await fetch(`/api/qa/session/${encodeURIComponent(id)}`);
  const data = await res.json();
  if (!res.ok) return;
  const s = data.session || {};
  state.qaSessionId = s.id;
  const box = $("#qa-messages");
  box.innerHTML = "";
  const msgs = s.messages || [];
  if (!msgs.length) {
    showQaWelcome();
    refreshQaHistory();
    return;
  }
  msgs.forEach((m) => appendQa(m.role === "user" ? "user" : "bot", m.text));
  refreshQaHistory();
}

function showQaWelcome() {
  const box = $("#qa-messages");
  box.innerHTML = `
    <div class="qa-welcome" id="qa-welcome">
      <div class="qa-welcome-icon">✦</div>
      <h2>欢迎使用 TradeS Agent 问答</h2>
      <p>外贸线索清洗 · 某公司模板 · 操作指导</p>
      <div class="qa-feature-cards">
        <div class="qa-feature-card"><b>清洗规则</b><span>手机号 / 去重 / 分表</span></div>
        <div class="qa-feature-card"><b>字段映射</b><span>某公司 18 列导入</span></div>
        <div class="qa-feature-card"><b>多轮对话</b><span>上下文连续问答</span></div>
      </div>
      <p class="hint">请在左侧选择角色，或直接输入问题</p>
    </div>`;
}

async function saveQaSession() {
  const messages = getQaMessages();
  if (!messages.length) return;
  try {
    const res = await fetch("/api/qa/session/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: state.qaSessionId || "", messages }),
    });
    const data = await res.json();
    if (res.ok && data.session?.id) {
      state.qaSessionId = data.session.id;
      refreshQaHistory();
    }
  } catch (_) {
    /* ignore */
  }
}

function resetQaToNew() {
  state.qaSessionId = null;
  showQaWelcome();
  refreshQaHistory();
}

function exportQaTranscript() {
  const msgs = getQaMessages();
  if (!msgs.length) {
    alert("当前没有可导出的对话");
    return;
  }
  const lines = msgs.map((m) => `## ${m.role === "user" ? "用户" : "助手"}\n\n${m.text}\n`).join("\n---\n\n");
  const blob = new Blob([`# TradeS Agent 问答记录\n\n${lines}`], { type: "text/markdown;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `问答记录_${new Date().toISOString().slice(0, 10)}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function renderQaFiles() {
  const row = $("#qa-file-row");
  if (!row) return;
  if (!state.qaFiles.length) {
    row.classList.add("hidden");
    row.innerHTML = "";
    return;
  }
  row.classList.remove("hidden");
  row.innerHTML = state.qaFiles
    .map(
      (f, i) => `<span class="qa-file-chip">${escapeHtml(f.name)} · ${f.content.length}字
        <button type="button" data-i="${i}" title="移除">×</button></span>`
    )
    .join("");
  row.querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", () => {
      state.qaFiles.splice(Number(b.dataset.i), 1);
      renderQaFiles();
    });
  });
}

async function addQaFiles(fileList) {
  const list = Array.from(fileList || []);
  for (const file of list) {
    if (file.size > 2 * 1024 * 1024) {
      alert(`${file.name} 超过 2MB，已跳过`);
      continue;
    }
    try {
      const text = await file.text();
      state.qaFiles.push({ name: file.name, content: text.slice(0, 12000) });
    } catch (_) {
      alert(`${file.name} 读取失败`);
    }
  }
  renderQaFiles();
}

async function sendQa() {
  const input = $("#qa-input");
  if (!input) return;
  const question = input.value.trim();
  const files = state.qaFiles.slice();
  if (!question && !files.length) return;
  input.value = "";
  input.style.height = "auto";

  const display = question || `（附件：${files.map((f) => f.name).join("、")}）`;
  appendQa("user", display + (files.length ? `\n附件：${files.map((f) => f.name).join("、")}` : ""));

  const box = $("#qa-messages");
  const botWrap = document.createElement("div");
  botWrap.className = "qa-msg bot";
  const bubble = document.createElement("div");
  bubble.className = "qa-bubble md streaming";
  bubble.textContent = "正在思考…";
  botWrap.appendChild(bubble);
  box.appendChild(botWrap);
  box.scrollTop = box.scrollHeight;

  state.qaFiles = [];
  renderQaFiles();

  const history = getQaMessages().filter((m) => m.text !== "正在思考…");
  let full = "";
  const payload = {
    question,
    history,
    use_llm: true,
    role: state.qaRoleId || "clean",
    use_web_search: !!$("#qa-web-search")?.checked,
    attachments: files.map((f) => ({ filename: f.name, content: f.content })),
  };

  async function fallbackNonStream() {
    try {
      const res = await fetch("/api/qa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...payload, use_llm: true }),
      });
      const data = await res.json();
      full = data.reply || "暂无回复";
      if (data.source === "local" && data.note) {
        full += `\n\n（${data.note}）`;
      }
      bubble.innerHTML = renderMarkdown(full);
    } catch (e) {
      bubble.textContent = "请求失败，请检查网络或模型设置后重试。";
    }
  }

  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 25000);
    const res = await fetch("/api/qa/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: ctrl.signal,
    });
    if (!res.ok) {
      clearTimeout(timer);
      const err = await res.json().catch(() => ({}));
      bubble.textContent = err.error || "回答失败，已切换本地回答";
      await fallbackNonStream();
      bubble.classList.remove("streaming");
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop() || "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        try {
          const obj = JSON.parse(line.slice(5).trim());
          if (obj.type === "content") {
            full += obj.content || "";
            bubble.innerHTML = renderMarkdown(full);
            box.scrollTop = box.scrollHeight;
          } else if (obj.type === "done" && obj.content) {
            full = obj.content;
            bubble.innerHTML = renderMarkdown(full);
          }
        } catch (_) {}
      }
    }
    clearTimeout(timer);
    bubble.classList.remove("streaming");
    if (!full) await fallbackNonStream();
    bubble.classList.remove("streaming");
    if (full) await saveQaSession();
  } catch (e) {
    bubble.classList.remove("streaming");
    bubble.textContent = "网络异常，正在使用本地回答…";
    await fallbackNonStream();
    bubble.classList.remove("streaming");
  }
}

$("#qa-form")?.addEventListener("submit", (e) => {
  e.preventDefault();
  sendQa();
});

$("#btn-theme")?.addEventListener("click", toggleTheme);
$("#btn-qa-web")?.addEventListener("click", () => {
  const cb = $("#qa-web-search");
  if (cb) {
    cb.checked = !cb.checked;
    $("#btn-qa-web")?.classList.toggle("is-on", cb.checked);
  }
});
$("#btn-qa-attach")?.addEventListener("click", () => $("#qa-file-input")?.click());
$("#qa-form button[type=submit]")?.addEventListener("click", (e) => {
  e.preventDefault();
  sendQa();
});
$("#qa-file-input")?.addEventListener("change", async (e) => {
  await addQaFiles(e.target.files);
  e.target.value = "";
});

$("#qa-input")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendQa();
  }
});
$("#qa-input")?.addEventListener("input", (e) => {
  e.target.style.height = "auto";
  e.target.style.height = Math.min(e.target.scrollHeight, 140) + "px";
});

$("#btn-qa-new")?.addEventListener("click", resetQaToNew);
$("#btn-qa-export")?.addEventListener("click", exportQaTranscript);
$("#btn-qa-clear-history")?.addEventListener("click", async (e) => {
  e.preventDefault();
  if (!confirm("确认清空全部历史对话？此操作不可恢复。")) return;
  await fetch("/api/qa/sessions/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  resetQaToNew();
  refreshQaHistory();
});

/* ---------- Upload / clean / agent ---------- */
$("#drop").addEventListener("click", () => $("#file").click());
$("#drop").addEventListener("dragover", (e) => {
  e.preventDefault();
  $("#drop").classList.add("over");
});
$("#drop").addEventListener("dragleave", () => $("#drop").classList.remove("over"));
$("#drop").addEventListener("drop", async (e) => {
  e.preventDefault();
  $("#drop").classList.remove("over");
  const files = e.dataTransfer.files;
  if (!files || !files.length) return;
  try {
    handleUploadResult(await uploadFiles(files));
  } catch (err) {
    showError(err.message);
  }
});

$("#file").addEventListener("change", async (e) => {
  const files = e.target.files;
  if (!files || !files.length) return;
  try {
    handleUploadResult(await uploadFiles(files));
  } catch (err) {
    showError(err.message);
  }
});

$("#btn-paste")?.addEventListener("click", async () => {
  const content = $("#paste").value.trim();
  if (!content) {
    showError("请先粘贴表格内容（含表头）");
    return;
  }
  try {
    const res = await fetch("/api/upload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, filename: "pasted.csv" }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "解析失败");
    handleUploadResult(data);
  } catch (err) {
    showError(err.message);
  }
});

async function runAgent() {
  const instruction = $("#agent-instruction").value.trim();
  const err = $("#agent-error");
  const und = $("#agent-understand");
  if (!instruction) {
    err.textContent = "请先填写清洗指令";
    err.classList.remove("hidden");
    return;
  }
  err.classList.add("hidden");
  und.classList.remove("hidden");
  und.classList.add("ok");
  und.textContent = "Agent 正在规划并执行…";
  $("#agent-steps").innerHTML =
    '<li class="agent-step"><span class="agent-step-no">…</span><div><strong>执行中</strong><p>请稍候</p></div></li>';

  const res = await fetch("/api/agent/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      instruction,
      use_llm: $("#agent-use-llm").checked,
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    und.classList.add("hidden");
    err.textContent = data.error || "Agent 执行失败";
    err.classList.remove("hidden");
    $("#agent-steps").innerHTML = "";
    return;
  }

  und.textContent = `Agent 已完成：${data.intent?.understand || instruction}`;
  renderAgentSteps(data.steps);
  renderQuality(data.report);
  renderStats(data.stats);
  renderTable($("#result-table"), data.columns, data.preview || []);
  renderSheets(data.sheets);
  const tip = $("#export-info");
  tip.classList.remove("hidden");
  tip.classList.add("ok");
  tip.textContent = `Agent 自检：${data.review || "完成"}（可直接导出）`;
  showPanel("#panel-result");
  setStep(3);
}

$("#btn-agent-run")?.addEventListener("click", async () => {
  try {
    await runAgent();
  } catch (e) {
    const err = $("#agent-error");
    err.textContent = e.message || String(e);
    err.classList.remove("hidden");
  }
});

$("#btn-agent-manual")?.addEventListener("click", () => {
  showPanel("#panel-map");
  setStep(2);
});

$$("#agent-examples .chip-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    $("#agent-instruction").value = btn.dataset.text || btn.textContent;
  });
});

$("#btn-back-upload").addEventListener("click", () => {
  showPanel("#panel-upload");
  setStep(1);
});

$("#btn-clean").addEventListener("click", async () => {
  const mapping = collectMapping();
  if (!mapping.company_name && !mapping.mobile) {
    showError("请至少映射「公司名称」或「手机」字段");
    return;
  }
  showError("");
  const res = await fetch("/api/clean", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mapping,
      source: $("#source").value,
      options: collectOptions(),
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    showError(data.error || "清洗失败");
    return;
  }
  renderQuality(data.report);
  renderStats(data.stats);
  renderTable($("#result-table"), data.columns, data.preview || []);
  renderSheets(data.sheets);
  $("#export-info").classList.add("hidden");
  showPanel("#panel-result");
  setStep(3);
});

$("#btn-back-map").addEventListener("click", () => {
  showPanel("#panel-map");
  setStep(2);
});

$("#btn-export").addEventListener("click", async () => {
  const scope = document.querySelector('input[name="scope"]:checked')?.value || "all";
  const res = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scope, split_rows: Number($("#opt-chunk")?.value || 1500) }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    showError(data.error || "导出失败");
    return;
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  let filename = "清洗模板.xlsx";
  const m = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  if (m) filename = decodeURIComponent(m[1]);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
  const n = res.headers.get("X-Row-Count") || "";
  const outDir = decodeURIComponent(res.headers.get("X-Output-Dir") || "");
  const filesHeader = decodeURIComponent(res.headers.get("X-Files") || "");
  const tip = $("#export-info");
  tip.innerHTML = `已导出 <strong>${n}</strong> 条某公司模板记录。`
    + (outDir ? `<br>输出目录：<code>${escapeHtml(outDir)}</code>` : "")
    + (filesHeader ? `<br>文件：${escapeHtml(filesHeader.replaceAll(" | ", "<br>"))}` : "");
  tip.classList.remove("hidden");
  tip.classList.add("ok");
  setStep(4);
});

/* LLM events · 供应商式面板 */
$("#btn-llm-settings")?.addEventListener("click", openLlmPanel);
$("#btn-llm-settings-2")?.addEventListener("click", openLlmPanel);
$("#btn-llm-close")?.addEventListener("click", closeLlmPanel);
$("#btn-llm-refresh")?.addEventListener("click", () => loadLlmStatus());

$("#btn-llm-eye")?.addEventListener("click", () => {
  const input = $("#llm-key");
  if (!input) return;
  input.type = input.type === "password" ? "text" : "password";
});

$("#btn-llm-new")?.addEventListener("click", () => {
  fillLlmForm(
    {
      label: "自定义 / Custom",
      base_url: "",
      model: "",
      chat_path: "/chat/completions",
      api_style: "openai",
      timeout: 60,
      temperature: 0.1,
    },
    `provider-${Date.now().toString().slice(-6)}`
  );
  const dot = $("#llm-status-dot");
  if (dot) dot.className = "llm-status-dot";
  showLlmMsg("请填写供应商信息后点「保存」");
});

$("#btn-llm-save")?.addEventListener("click", async () => {
  try {
    const id = $("#llm-id").value.trim() || "custom";
    const profile = collectLlmProfile();
    const key = $("#llm-key").value.trim();
    const body = { id, profile, activate: true };
    if (key) body.profile.api_key = key;
    const res = await fetch("/api/llm/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      showLlmMsg(data.error || "保存失败", false);
      return;
    }
    await loadLlmStatus();
    showLlmMsg(`「${profile.label || id}」已保存并设为当前模型`);
  } catch (err) {
    showLlmMsg(err.message || String(err), false);
  }
});

$("#btn-llm-delete")?.addEventListener("click", async () => {
  const id = $("#llm-id").value.trim();
  if (!id) {
    showLlmMsg("请先选择要删除的供应商", false);
    return;
  }
  if (!confirm(`确认删除供应商「${id}」？`)) return;
  const res = await fetch("/api/llm/profile/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  const data = await res.json();
  if (!res.ok) {
    showLlmMsg(data.error || "删除失败", false);
    return;
  }
  await loadLlmStatus();
  showLlmMsg("已删除");
});

$("#btn-llm-test")?.addEventListener("click", async () => {
  const dot = $("#llm-status-dot");
  if (dot) {
    dot.className = "llm-status-dot loading";
  }
  showLlmMsg("正在测试连接…");
  try {
    const profile = collectLlmProfile();
    const key = $("#llm-key").value.trim();
    const body = { ...profile };
    if (key) body.api_key = key;
    const id = $("#llm-id").value.trim();
    if (id) body.id = id;
    const res = await fetch("/api/llm/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      if (dot) dot.className = "llm-status-dot err";
      showLlmMsg(data.error || "连接失败", false);
      return;
    }
    if (dot) dot.className = "llm-status-dot ok";
    showLlmMsg(`连接成功 · ${data.model || ""} · 回复：${data.reply || "OK"}`);
  } catch (err) {
    if (dot) dot.className = "llm-status-dot err";
    showLlmMsg(err.message || String(err), false);
  }
});

$("#btn-llm-validate")?.addEventListener("click", async () => {
  const tip = $("#ai-result");
  tip.classList.remove("hidden");
  tip.classList.add("ok");
  tip.textContent = "AI 校验中，请稍候…";
  $("#ai-table-wrap").classList.add("hidden");
  const res = await fetch("/api/llm/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ limit: 50 }),
  });
  const data = await res.json();
  if (!res.ok) {
    tip.classList.remove("ok");
    tip.textContent = data.error || "AI 校验失败";
    return;
  }
  tip.textContent = `已校验 ${data.checked} 条 · 待确认 ${data.fail_count} 条 · ${data.summary || ""}`;
  renderTable($("#ai-table"), ["公司名称", "手机", "官网", "AI校验", "AI意见"], data.preview || []);
  $("#ai-table-wrap").classList.remove("hidden");
});

/* 点击涟漪 */
function bindRipples() {
  document.addEventListener("pointerdown", (e) => {
    const el = e.target.closest(".btn-primary, .btn-ghost, .chip-btn, .icon-btn, .vendor-chip, .nav-link");
    if (!el) return;
    el.classList.add("ripple-host");
    const rect = el.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const span = document.createElement("span");
    span.className = "ripple";
    span.style.width = span.style.height = `${size}px`;
    span.style.left = `${e.clientX - rect.left - size / 2}px`;
    span.style.top = `${e.clientY - rect.top - size / 2}px`;
    el.appendChild(span);
    setTimeout(() => span.remove(), 560);
  });
}

function bindCursorGlow() {
  const glow = document.getElementById("cursor-glow");
  if (!glow) return;
  let raf = 0;
  let x = window.innerWidth / 2;
  let y = window.innerHeight / 2;
  const apply = () => {
    raf = 0;
    glow.style.setProperty("--mx", `${x}px`);
    glow.style.setProperty("--my", `${y}px`);
    glow.style.opacity = "1";
  };
  window.addEventListener(
    "pointermove",
    (e) => {
      x = e.clientX;
      y = e.clientY;
      if (!raf) raf = requestAnimationFrame(apply);
    },
    { passive: true }
  );
  apply();
}

/* init */
initTheme();
bindRipples();
bindCursorGlow();
loadLlmStatus();
refreshQaHistory();
const hashView = (location.hash || "").replace("#", "");
if (hashView === "workspace" || hashView === "qa") setView(hashView);
else setView("home");
