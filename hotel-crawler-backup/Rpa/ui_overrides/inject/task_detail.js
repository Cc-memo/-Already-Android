(function () {
  const PLATFORM_LABEL = { meituan: "美团", ctrip: "携程", fliggy: "飞猪", gaode: "高德" };
  const STATUS_LABEL = { queued: "等待中", running: "爬取中", success: "已完成", failed: "已失败" };
  const STATUS_CLASS = { queued: "pending", running: "running", success: "completed", failed: "failed" };

  function qs(name) {
    return new URLSearchParams(location.search).get(name);
  }

  function el(tag, attrs = {}, html = "") {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") e.className = v;
      else if (k === "style") e.setAttribute("style", v);
      else e.setAttribute(k, v);
    }
    if (html) e.innerHTML = html;
    return e;
  }

  async function apiGet(url) {
    const res = await fetch(url, { method: "GET" });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok || payload.success === false) throw new Error(payload.error || `请求失败: ${res.status}`);
    return payload.data;
  }

  function fmt(s) {
    return s || "-";
  }

  function secondsBetween(a, b) {
    if (!a || !b) return null;
    const ta = new Date(a.replace(" ", "T")).getTime();
    const tb = new Date(b.replace(" ", "T")).getTime();
    if (!Number.isFinite(ta) || !Number.isFinite(tb)) return null;
    return Math.max(0, Math.floor((tb - ta) / 1000));
  }

  function fmtDuration(sec) {
    if (sec == null) return "-";
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    if (m <= 0) return `${s}秒`;
    return `${m}分${s}秒`;
  }

  function normalizeRooms(platform, result) {
    // result: { ok, data }  or { ok:false, error }
    if (!result || result.ok !== true) return [];
    const data = result.data;

    if (platform === "ctrip") {
      const list = data?.["房型列表"];
      if (!Array.isArray(list)) return [];
      return list.map((x) => ({
        name: x?.["房型名称"] || x?.name || "-",
        price: x?.["价格"] || x?.price || "-",
        remaining: x?.["剩余房间"] || x?.["剩余房间数"] || x?.remaining || "-",
        notes: x?.["备注"] || x?.notes || "",
      }));
    }

    if (platform === "meituan") {
      if (!Array.isArray(data)) return [];
      return data.map((x) => ({
        name: x?.name || x?.["房型名称"] || "-",
        price: x?.price || x?.["价格"] || "-",
        remaining: x?.remaining || x?.["剩余房间"] || "-",
        notes: x?.tags || x?.["备注"] || "",
      }));
    }

    // 未知平台：尽量兜底
    if (Array.isArray(data)) {
      return data.map((x) => ({
        name: x?.name || x?.["房型名称"] || "-",
        price: x?.price || x?.["价格"] || "-",
        remaining: x?.remaining || x?.["剩余房间"] || "-",
        notes: x?.tags || x?.["备注"] || "",
      }));
    }
    return [];
  }

  function injectStyles() {
    const style = el("style", {}, `
      .td-wrap{display:flex;flex-direction:column;gap:16px}
      .td-top{display:flex;justify-content:space-between;align-items:center;gap:12px}
      .td-title{font-size:20px;font-weight:600;display:flex;align-items:center;gap:10px}
      .td-sub{color:#8C8C8C;font-size:13px;margin-top:2px}
      .td-actions{display:flex;gap:8px;flex-wrap:wrap}
      .td-btn{padding:8px 14px;border-radius:6px;border:1px solid #D9D9D9;background:#fff;cursor:pointer;font-size:13px;color:#595959;display:flex;align-items:center;gap:6px}
      .td-btn.primary{background:#1890FF;color:#fff;border-color:#1890FF}
      .td-btn:hover{border-color:#1890FF;color:#1890FF}
      .td-btn.primary:hover{background:#40a9ff;color:#fff}

      .td-kv{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
      @media (max-width:1100px){.td-kv{grid-template-columns:repeat(2,1fr)}}
      .td-kv .item{display:flex;flex-direction:column;gap:4px}
      .td-kv .k{font-size:12px;color:#8C8C8C}
      .td-kv .v{font-size:14px;color:#262626;font-weight:500;line-height:1.3}

      .td-badge{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:600}
      .td-badge.completed{background:#F6FFED;color:#52C41A}
      .td-badge.running{background:#E6F7FF;color:#1890FF}
      .td-badge.failed{background:#FFF1F0;color:#F5222D}
      .td-badge.pending{background:#FFF7E6;color:#FAAD14}

      .td-progress{height:10px;background:#F0F0F0;border-radius:999px;overflow:hidden}
      .td-progress > div{height:100%;background:#1890FF;transition:width .25s}

      .td-tabs{display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid #F0F0F0;padding-bottom:10px}
      .td-tab{border:1px solid #D9D9D9;background:#fff;border-radius:999px;padding:6px 12px;cursor:pointer;font-size:13px;color:#595959;display:flex;align-items:center;gap:8px}
      .td-tab.active{background:#1890FF;border-color:#1890FF;color:#fff}
      .td-tab .mini{font-size:11px;opacity:.9}

      .td-panel{display:none}
      .td-panel.active{display:block}

      .td-table{width:100%;border-collapse:collapse}
      .td-table th{background:#FAFAFA;padding:12px 14px;border-bottom:1px solid #F0F0F0;font-size:13px;text-align:left}
      .td-table td{padding:12px 14px;border-bottom:1px solid #F0F0F0;font-size:13px;color:#595959;vertical-align:top}
      .td-table tr:hover td{background:#FAFAFA}
      .td-mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace;font-size:12px;line-height:1.5}
      .td-pre{background:#0f172a;color:#e5e7eb;border-radius:10px;padding:14px;overflow:auto}
      .td-note{color:#8C8C8C;font-size:12px}
      .td-err{background:#FFF1F0;border:1px solid #FFCCC7;color:#F5222D;border-radius:10px;padding:10px 12px;font-size:13px}

      /* Dark Theme Overrides */
      html.dark-theme .td-btn, body.dark-theme .td-btn {
        background: #21262d !important;
        color: #c9d1d9 !important;
        border-color: #30363d !important;
      }
      html.dark-theme .td-btn:hover, body.dark-theme .td-btn:hover {
        background: #30363d !important;
        border-color: #58a6ff !important;
        color: #58a6ff !important;
      }
      html.dark-theme .td-tab, body.dark-theme .td-tab {
        background: #21262d !important;
        color: #c9d1d9 !important;
        border-color: #30363d !important;
      }
      html.dark-theme .td-tab:hover, body.dark-theme .td-tab:hover {
        background: #30363d !important;
        border-color: #58a6ff !important;
        color: #58a6ff !important;
      }
      html.dark-theme .td-table th, body.dark-theme .td-table th {
        background: #0d1117 !important;
        color: #f0f6fc !important;
        border-bottom-color: #30363d !important;
      }
      html.dark-theme .td-table td, body.dark-theme .td-table td {
        color: #c9d1d9 !important;
        border-bottom-color: #21262d !important;
      }
      html.dark-theme .td-table tr:hover td, body.dark-theme .td-table tr:hover td {
        background: #161b22 !important;
      }
      html.dark-theme .td-kv .v, body.dark-theme .td-kv .v {
        color: #c9d1d9 !important;
      }
      html.dark-theme .td-progress, body.dark-theme .td-progress {
        background: #30363d !important;
      }
    `);
    document.head.appendChild(style);
  }

  function mount(task) {
    injectStyles();

    const content = document.querySelector(".content");
    if (!content) return;

    const shortId = (task.task_id || "").slice(0, 8);
    const status = task.status || "queued";
    const badgeClass = STATUS_CLASS[status] || "pending";
    const badgeText = STATUS_LABEL[status] || status;
    const duration = fmtDuration(secondsBetween(task.started_at, task.finished_at));
    const plats = (task.platforms || []).map((p) => PLATFORM_LABEL[p] || p).join("、") || "-";
    const prog = Number.isFinite(task.progress) ? task.progress : 0;
    const checkIn = task.check_in || "-";
    const checkOut = task.check_out || "-";

    document.title = `任务详情 - 酒店信息爬取及管理平台`;

    // 重建内容（不堆 JSON）
    content.innerHTML = "";

    const wrap = el("div", { class: "td-wrap" });

    const top = el("div", { class: "page-header td-top" });
    const left = el("div", {}, `
      <div class="td-title"><i class="fas fa-info-circle"></i> 任务详情</div>
      <div class="td-sub">${fmt(task.hotel_name)} · ${plats}</div>
    `);
    const actions = el("div", { class: "td-actions" });
    const btnBack = el("button", { class: "td-btn" }, `<i class="fas fa-arrow-left"></i> 返回任务列表`);
    btnBack.onclick = () => (location.href = "crawl-tasks.html");
    const btnDownload = el("button", { class: "td-btn primary" }, `<i class="fas fa-download"></i> 下载结果(JSON)`);
    btnDownload.onclick = () => {
      const blob = new Blob([JSON.stringify(task, null, 2)], { type: "application/json;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `crawl_task_${shortId}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 500);
    };
    actions.appendChild(btnBack);
    actions.appendChild(btnDownload);
    top.appendChild(left);
    top.appendChild(actions);
    wrap.appendChild(top);

    const infoCard = el("div", { class: "info-card" });
    infoCard.appendChild(el("h2", {}, "基本信息"));
    const kv = el("div", { class: "td-kv" });
    const items = [
      ["任务ID", `#${shortId}`],
      ["酒店名称", fmt(task.hotel_name)],
      ["城市/区域", fmt(task.location)],
      ["入住/退房", `${checkIn} → ${checkOut}`],
      ["创建时间", fmt(task.created_at)],
      ["开始时间", fmt(task.started_at)],
      ["完成时间", fmt(task.finished_at)],
      ["执行时长", duration],
      ["状态", `<span class="td-badge ${badgeClass}">${badgeText}</span>`],
      ["进度", `${Math.max(0, Math.min(100, prog))}%`],
      ["当前平台", fmt(task.current_platform)],
      ["错误", task.error ? `<span class="td-err">${task.error}</span>` : "-"],
    ];
    for (const [k, v] of items) {
      const it = el("div", { class: "item" });
      it.appendChild(el("div", { class: "k" }, k));
      it.appendChild(el("div", { class: "v" }, v));
      kv.appendChild(it);
    }
    infoCard.appendChild(kv);
    infoCard.appendChild(el("div", { class: "progress-section" }, `
      <div class="progress-info"><span>爬取进度</span><span>${Math.max(0, Math.min(100, prog))}%</span></div>
      <div class="td-progress"><div style="width:${Math.max(0, Math.min(100, prog))}%"></div></div>
      <div class="td-note" style="margin-top:8px;">提示：如需查看原始结构化数据，可展开下方“原始 JSON”。</div>
    `));
    wrap.appendChild(infoCard);

    // 平台结果 Tabs
    const resultsCard = el("div", { class: "info-card" });
    resultsCard.appendChild(el("h2", {}, "抓取结果"));
    const tabs = el("div", { class: "td-tabs" });
    const panels = el("div", {});
    const results = task.results || {};
    const platforms = (task.platforms && task.platforms.length ? task.platforms : Object.keys(results)) || [];

    if (!platforms.length) {
      resultsCard.appendChild(el("div", { class: "td-note" }, "暂无结果（任务可能仍在排队/执行中）"));
    } else {
      platforms.forEach((p, idx) => {
        const r = results[p];
        const ok = r && r.ok === true;
        const tab = el("button", { class: "td-tab" }, `
          ${PLATFORM_LABEL[p] || p}
          <span class="mini">${ok ? "成功" : "失败/无数据"}</span>
        `);
        const panel = el("div", { class: "td-panel" });

        if (!r) {
          panel.appendChild(el("div", { class: "td-note" }, "暂无该平台输出"));
        } else if (r.ok !== true) {
          panel.appendChild(el("div", { class: "td-err" }, r.error || "执行失败"));
        } else {
          const rooms = normalizeRooms(p, r);
          if (!rooms.length) {
            panel.appendChild(el("div", { class: "td-note" }, "结果为空（可能未抓到房型或返回结构变更）"));
          } else {
            const table = el("table", { class: "td-table" });
            table.innerHTML = `
              <thead>
                <tr>
                  <th style="width:40%">房型</th>
                  <th style="width:14%">价格</th>
                  <th style="width:16%">剩余</th>
                  <th>备注</th>
                </tr>
              </thead>
              <tbody></tbody>
            `;
            const tb = table.querySelector("tbody");
            rooms.forEach((x) => {
              const tr = document.createElement("tr");
              tr.innerHTML = `
                <td>${fmt(x.name)}</td>
                <td>${fmt(x.price)}</td>
                <td>${fmt(x.remaining)}</td>
                <td>${x.notes ? String(x.notes) : "-"}</td>
              `;
              tb.appendChild(tr);
            });
            panel.appendChild(table);
          }
        }

        tab.onclick = () => {
          tabs.querySelectorAll(".td-tab").forEach((t) => t.classList.remove("active"));
          panels.querySelectorAll(".td-panel").forEach((p0) => p0.classList.remove("active"));
          tab.classList.add("active");
          panel.classList.add("active");
        };

        if (idx === 0) {
          tab.classList.add("active");
          panel.classList.add("active");
        }
        tabs.appendChild(tab);
        panels.appendChild(panel);
      });

      resultsCard.appendChild(tabs);
      resultsCard.appendChild(panels);
    }
    wrap.appendChild(resultsCard);

    // 原始 JSON（折叠）
    const rawCard = el("div", { class: "info-card" });
    rawCard.appendChild(el("h2", {}, "原始 JSON"));
    const details = el("details", {});
    details.appendChild(el("summary", { style: "cursor:pointer; color:#1890FF; font-size:14px;" }, "展开/收起原始数据"));
    const pre = el("pre", { class: "td-pre td-mono", style: "margin-top:12px;" }, "");
    pre.textContent = JSON.stringify(task, null, 2);
    const copyBtn = el("button", { class: "td-btn", style: "margin-top:12px;" }, `<i class="fas fa-copy"></i> 复制 JSON`);
    copyBtn.onclick = async () => {
      try {
        await navigator.clipboard.writeText(pre.textContent);
        window.showToast && window.showToast("已复制到剪贴板", "success");
      } catch (e) {
        window.showToast && window.showToast("复制失败（浏览器权限限制）", "error");
      }
    };
    details.appendChild(pre);
    rawCard.appendChild(details);
    rawCard.appendChild(copyBtn);
    wrap.appendChild(rawCard);

    content.appendChild(wrap);
  }

  async function main() {
    const taskId = qs("task_id");
    if (!taskId) {
      window.showToast && window.showToast("缺少 task_id 参数", "error");
      return;
    }
    try {
      const task = await apiGet(`/api/crawl-tasks/${encodeURIComponent(taskId)}`);
      mount(task);
    } catch (e) {
      window.showToast && window.showToast(e.message || String(e), "error");
      const content = document.querySelector(".content");
      if (content) {
        content.innerHTML = `<div class="info-card"><h2>加载失败</h2><div class="td-err">${e.message || String(e)}</div></div>`;
      }
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", main);
  else main();
})();

