(function () {
  function platformLabel(p) {
    const m = { meituan: "美团", ctrip: "携程", fliggy: "飞猪", gaode: "高德" };
    return m[p] || p;
  }

  function statusLabel(s) {
    const m = { queued: "等待中", running: "爬取中", success: "已完成", failed: "已失败" };
    return m[s] || s;
  }

  function statusClass(s) {
    const m = { queued: "status-pending", running: "status-running", success: "status-completed", failed: "status-failed" };
    return m[s] || "status-pending";
  }

  function normalizeStatus(status) {
    const s = (status || "").trim().toLowerCase();
    if (!s) return "queued";
    if (s === "cancelled") return "failed";
    return s;
  }

  async function apiGet(url) {
    // 添加时间戳防止浏览器缓存
    const timestamp = new Date().getTime();
    const separator = url.includes('?') ? '&' : '?';
    const urlWithCache = `${url}${separator}_t=${timestamp}`;
    
    const res = await fetch(urlWithCache, { 
      method: "GET",
      cache: 'no-cache',
      headers: {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
      }
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok || payload.success === false) throw new Error(payload.error || `请求失败: ${res.status}`);
    return payload.data;
  }

  function ensureExecSourceFilter() {
    const bar = document.querySelector(".filter-bar");
    if (!bar || document.getElementById("execSourceFilter")) return;
    const anchorItem = bar.querySelectorAll(".filter-item")[1] || null; // 放在“目标平台”后

    const item = document.createElement("div");
    item.className = "filter-item";
    item.innerHTML = `
      <label>执行端：</label>
      <select id="execSourceFilter">
        <option value="all">全部</option>
        <option value="desktop">电脑端</option>
        <option value="mobile">手机端</option>
      </select>
    `;
    if (anchorItem && anchorItem.parentNode) {
      anchorItem.parentNode.insertBefore(item, anchorItem.nextSibling);
    } else {
      bar.appendChild(item);
    }
  }

  function ensureTaskTypeHeader() {
    const headers = Array.from(document.querySelectorAll(".table-container thead th"));
    const typeTh = headers.find((th) => (th.textContent || "").trim() === "任务类型");
    if (typeTh) typeTh.textContent = "执行端";
  }

  function getFilters() {
    const statusSel = document.querySelector(".filter-bar .filter-item:nth-child(1) select");
    const platformSel = document.querySelector(".filter-bar .filter-item:nth-child(2) select");
    const execSel = document.getElementById("execSourceFilter");
    const dateInputs = document.querySelectorAll('.filter-bar input[type="date"]');
    const keywordInput = document.querySelector('.filter-bar input[type="text"]');
    const startDate = dateInputs[0]?.value || "";
    const endDate = dateInputs[1]?.value || "";
    return {
      status: (statusSel?.value || "全部").trim(),
      platform: (platformSel?.value || "全部平台").trim(),
      exec: (execSel?.value || "all").trim().toLowerCase(),
      startDate,
      endDate,
      keyword: (keywordInput?.value || "").trim(),
    };
  }

  function applyFilters(tasks) {
    const f = getFilters();
    const statusMap = { 等待中: "queued", 爬取中: "running", 已完成: "success", 已失败: "failed", 已暂停: "paused" };
    const platformMap = { 美团: "meituan", 携程: "ctrip", 飞猪: "fliggy", 高德: "gaode" };

    return (tasks || []).filter((t) => {
      if (f.status !== "全部" && normalizeStatus(t.status) !== statusMap[f.status]) return false;
      if (f.platform !== "全部平台") {
        const target = platformMap[f.platform];
        const plats = (t.platforms || []).map((p) => (p || "").toLowerCase());
        if (!plats.includes(target)) return false;
      }
      if (f.exec !== "all") {
        const src = (t.exec_source || "电脑端") === "手机端" ? "mobile" : "desktop";
        if (src !== f.exec) return false;
      }
      if (f.keyword) {
        const name = (t.hotel_name || "").toLowerCase();
        if (!name.includes(f.keyword.toLowerCase())) return false;
      }
      if (f.startDate || f.endDate) {
        const created = (t.created_at || "").slice(0, 10);
        if (!created) return false;
        if (f.startDate && created < f.startDate) return false;
        if (f.endDate && created > f.endDate) return false;
      }
      return true;
    });
  }

  function render(tasks) {
    const tbody = document.querySelector(".table-container tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!tasks || !tasks.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="10" style="text-align:center; padding:18px; color:#8C8C8C;">暂无任务</td>`;
      tbody.appendChild(tr);
      return;
    }

    for (const t of tasks) {
      const plats = (t.platforms || []).map(platformLabel).join("、") || "-";
      const created = t.created_at || "-";
      const started = t.started_at || "-";
      const st = t.status || "queued";
      const prog = Number.isFinite(t.progress) ? t.progress : 0;
      const execSource = t.exec_source || "电脑端";

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><input type="checkbox"></td>
        <td>#${(t.task_id || "").slice(0, 8)}</td>
        <td>${t.hotel_name || "-"}</td>
        <td>${plats}</td>
        <td>${execSource}</td>
        <td>${created}</td>
        <td>${started}</td>
        <td><span class="status-badge ${statusClass(st)}">${statusLabel(st)}</span></td>
        <td>
          <div class="progress-bar">
            <div class="progress-fill" style="width: ${Math.max(0, Math.min(100, prog))}%"></div>
          </div>
        </td>
        <td>
          <div class="action-buttons">
            <button class="btn-icon btn-view" title="查看详情"><i class="fas fa-eye"></i></button>
            <button class="btn-icon btn-delete" title="删除任务" style="color: #ff4d4f; margin-left: 8px;"><i class="fas fa-trash-alt"></i></button>
          </div>
        </td>
      `;
      tr.querySelector(".btn-view").addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        // 打开任务详情页（更友好的视觉呈现），而不是直接打开裸 JSON
        const detailUrl =
          execSource === "手机端"
            ? `mobile_task_detail.html?task_id=${encodeURIComponent(t.task_id)}`
            : `task_detail.html?task_id=${encodeURIComponent(t.task_id)}`;
        window.open(detailUrl, "_blank");
      });
      
      tr.querySelector(".btn-delete").addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!confirm("确认删除该任务吗？此操作不可恢复。")) return;
        
        try {
            const delApi =
              execSource === "手机端" ? `/api/app-crawl-tasks/${t.task_id}` : `/api/crawl-tasks/${t.task_id}`;
            const res = await fetch(delApi, { method: "DELETE" });
            const payload = await res.json();
            if (res.ok && payload.success) {
                if (window.showToast) window.showToast("删除成功", "success");
                refresh();
            } else {
                throw new Error(payload.error || "删除失败");
            }
        } catch (err) {
            if (window.showToast) window.showToast(err.message || String(err), "error");
            else alert(err.message || String(err));
        }
      });
      tbody.appendChild(tr);
    }
  }

  async function refresh() {
    const [desktopTasks, mobileTasks] = await Promise.all([
      apiGet("/api/crawl-tasks?limit=100"),
      apiGet("/api/app-crawl-tasks?limit=100").catch(() => []),
    ]);
    const d = (desktopTasks || []).map((t) => ({ ...t, exec_source: "电脑端" }));
    const m = (mobileTasks || []).map((t) => ({ ...t, exec_source: "手机端" }));
    const merged = [...d, ...m].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
    render(applyFilters(merged));
  }

  async function main() {
    try {
      ensureExecSourceFilter();
      ensureTaskTypeHeader();

      // 立即清空表格，防止显示 HTML 中的示例数据
      const tbody = document.querySelector(".table-container tbody");
      if (tbody) {
        tbody.innerHTML = "";
      }
      
      const queryBtn = document.querySelectorAll(".filter-bar .btn-secondary")[0];
      const resetBtn = document.querySelectorAll(".filter-bar .btn-secondary")[1];
      if (queryBtn) queryBtn.addEventListener("click", (e) => { e.preventDefault(); refresh(); });
      if (resetBtn)
        resetBtn.addEventListener("click", (e) => {
          e.preventDefault();
          const statusSel = document.querySelector(".filter-bar .filter-item:nth-child(1) select");
          const platformSel = document.querySelector(".filter-bar .filter-item:nth-child(2) select");
          const execSel = document.getElementById("execSourceFilter");
          const dateInputs = document.querySelectorAll('.filter-bar input[type="date"]');
          const keywordInput = document.querySelector('.filter-bar input[type="text"]');
          if (statusSel) statusSel.selectedIndex = 0;
          if (platformSel) platformSel.selectedIndex = 0;
          if (execSel) execSel.selectedIndex = 0;
          dateInputs.forEach((i) => (i.value = ""));
          if (keywordInput) keywordInput.value = "";
          refresh();
        });
      document.querySelectorAll(".filter-bar select, .filter-bar input").forEach((el) => {
        const eventName = el.tagName === "SELECT" ? "change" : "input";
        el.addEventListener(eventName, () => refresh());
      });

      await refresh();
      // 简单轮询
      setInterval(refresh, 2500);
    } catch (e) {
      window.showToast && window.showToast(e.message || String(e), "error");
    }
  }

  // 立即执行，不等待 DOMContentLoaded，确保尽快清空示例数据
  if (document.readyState === "loading") {
    // 如果还在加载，先清空表格
    const tbody = document.querySelector(".table-container tbody");
    if (tbody) {
      tbody.innerHTML = "";
    }
    document.addEventListener("DOMContentLoaded", main);
  } else {
    main();
  }
})();

