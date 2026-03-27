(function () {
  function platformLabel(p) {
    const m = { meituan: "美团", ctrip: "携程", fliggy: "飞猪", gaode: "高德" };
    return m[p] || p;
  }

  function ensureLocationField() {
    const textarea = document.getElementById("hotelNames");
    if (!textarea) return null;
    if (document.getElementById("locationInput")) return document.getElementById("locationInput");

    const form = document.querySelector(".quick-crawl-form");
    const group = document.createElement("div");
    group.className = "form-group";
    group.innerHTML = `
      <label>城市/区域 <span style="color:#8C8C8C; font-weight: normal;"></span></label>
      <input id="locationInput" type="text" placeholder="例如：上海" style="width:100%; padding:10px 12px; border:1px solid #D9D9D9; border-radius:6px;" />
      <div class="hint">不填则默认使用“上海”</div>
    `;

    // 插到 textarea 那个 full-width 后面
    const full = textarea.closest(".form-group");
    if (full && full.parentNode) {
      full.parentNode.insertBefore(group, full.nextSibling);
    } else if (form) {
      form.insertBefore(group, form.querySelector(".form-actions") || null);
    }

    return document.getElementById("locationInput");
  }

  async function postJson(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok || payload.success === false) {
      throw new Error(payload.error || `请求失败: ${res.status}`);
    }
    return payload.data;
  }

  function getSelectedPlatforms() {
    const checked = Array.from(
      document.querySelectorAll('.platform-checkboxes input[type="checkbox"]:checked')
    );
    return checked.map((cb) => cb.value).filter(Boolean);
  }

  function ensureExecSourceField() {
    if (document.getElementById("execSourceDesktop")) return;
    const form = document.querySelector(".quick-crawl-form");
    const platformGroup = document.querySelector(".platform-checkboxes")?.closest(".form-group");
    if (!form || !platformGroup) return;

    const group = document.createElement("div");
    group.className = "form-group";
    group.innerHTML = `
      <label>执行端</label>
      <div style="display:flex; align-items:center; gap:18px; padding:6px 0;">
        <label style="display:flex; align-items:center; gap:6px; margin:0; font-weight:normal;">
          <input type="checkbox" id="execSourceDesktop" name="execSource" value="desktop" checked />
          电脑端
        </label>
        <label style="display:flex; align-items:center; gap:6px; margin:0; font-weight:normal;">
          <input type="checkbox" id="execSourceMobile" name="execSource" value="mobile" />
          手机端
        </label>
      </div>
      <div class="hint">可多选；勾选“手机端”将进入手机端任务队列，由 Android-/test/app_scheduler.py 领取执行</div>
    `;
    platformGroup.parentNode.insertBefore(group, platformGroup);
  }

  function getExecSources() {
    return Array.from(document.querySelectorAll('input[name="execSource"]:checked'))
      .map((el) => (el.value || "").trim().toLowerCase())
      .filter(Boolean);
  }

  function ensureDateFields() {
    if (document.getElementById("checkInDate")) return;

    const form = document.querySelector(".quick-crawl-form");
    const group = document.createElement("div");
    group.className = "form-group";
    group.style.gridColumn = "1 / -1";
    
    // 注入样式
    const style = document.createElement("style");
    style.textContent = `
      .hotel-date-picker {
        display: flex;
        align-items: center;
        background: #fff;
        border: 1px solid #D9D9D9; /* 回归标准边框颜色 */
        border-radius: 4px; /* 圆角改小，和上面一致 */
        padding: 0;
        gap: 0;
        margin-top: 8px;
        position: relative;
        /* 去掉夸张的阴影和高度 */
      }
      .hotel-date-picker:hover {
        border-color: #d4af37; /* 悬停仅变色，不浮起 */
      }
      .date-item {
        flex: 1;
        display: flex;
        flex-direction: row;
        align-items: center;
        justify-content: flex-start; /* 改为左对齐 */
        gap: 12px; /* 标签和日期之间的间距 */
        padding: 10px 16px;
        cursor: pointer;
        position: relative;
        transition: background-color 0.2s;
        min-height: 48px;
      }
      .date-item:hover {
        background-color: #FAFAFA;
      }
      .date-item label {
        font-size: 14px;
        color: #595959; /* 标签颜色加深一点 */
        margin: 0 !important;
        font-weight: normal;
        pointer-events: none;
      }
      .date-item .date-display {
        display: flex;
        align-items: baseline;
        gap: 8px;
        pointer-events: none;
      }
      .date-item .date-value {
        font-size: 14px; /* 字号改小，融入整体 */
        font-weight: 400;
        color: #262626; /* 标准黑 */
      }
      .date-item .week-display {
        font-size: 12px;
        color: #8C8C8C;
        font-weight: normal;
      }
      /* 隐形Input覆盖层 */
      .date-item input[type="date"] {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        opacity: 0;
        cursor: pointer;
        z-index: 10;
        font-size: 0; 
      }
      .date-item input[type="date"]::-webkit-calendar-picker-indicator {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        margin: 0;
        padding: 0;
        opacity: 0;
        cursor: pointer;
      }

      .nights-tag {
        position: relative;
        z-index: 2;
        background: #F5F5F5;
        color: #595959;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 12px;
        border: 1px solid #E8E8E8;
        white-space: nowrap;
        margin: 0 -10px;
        font-weight: normal;
      }
      
      .date-separator {
        width: 1px;
        background: #F0F0F0;
        align-self: stretch;
      }

      /* Dark Theme Overrides */
      .dark-theme .hotel-date-picker {
        background: #0d1117;
        border-color: #30363d;
      }
      .dark-theme .date-item:hover {
        background-color: #161b22;
      }
      .dark-theme .date-item label {
        color: #8b949e;
      }
      .dark-theme .date-item .date-value {
        color: #c9d1d9;
      }
      .dark-theme .date-item .week-display {
        color: #8b949e;
      }
      .dark-theme .nights-tag {
        background: #161b22;
        color: #8b949e;
        border-color: #30363d;
      }
      .dark-theme .date-separator {
        background: #30363d;
      }
      
      /* 修复原生日期选择器在深色模式下的配色 */
      .dark-theme input[type="date"] {
        color-scheme: dark;
      }
    `;
    document.head.appendChild(style);

    // 默认日期：今天和明天
    const today = new Date();
    const tomorrow = new Date();
    tomorrow.setDate(today.getDate() + 1);
    const formatDate = (d) => d.toISOString().split('T')[0];
    const getWeek = (d) => "周" + "日一二三四五六".charAt(d.getDay());
    const getDisplayDate = (d) => `${d.getMonth() + 1}月${d.getDate()}日`;

    group.innerHTML = `
      <label>入住/退房时间</label>
      <div class="hotel-date-picker">
        <div class="date-item">
          <label>入住日期</label>
          <div class="date-display">
            <span class="date-value" id="checkInDisplay">${getDisplayDate(today)}</span>
            <span class="week-display" id="checkInWeek">${getWeek(today)}</span>
          </div>
          <input type="date" id="checkInDate" value="${formatDate(today)}">
        </div>
        
        <div class="date-separator"></div>
        <div class="nights-tag" id="nightsInfo">1晚</div>
        <div class="date-separator"></div>

        <div class="date-item">
          <label>退房日期</label>
          <div class="date-display">
            <span class="date-value" id="checkOutDisplay">${getDisplayDate(tomorrow)}</span>
            <span class="week-display" id="checkOutWeek">${getWeek(tomorrow)}</span>
          </div>
          <input type="date" id="checkOutDate" value="${formatDate(tomorrow)}">
        </div>
      </div>
    `;

    // 插入到地点输入框后面
    const loc = document.getElementById("locationInput")?.closest(".form-group");
    if (loc && loc.parentNode) {
      loc.parentNode.insertBefore(group, loc.nextSibling);
    }

    // 绑定逻辑
    const cin = document.getElementById("checkInDate");
    const cout = document.getElementById("checkOutDate");
    const cinDisplay = document.getElementById("checkInDisplay");
    const cinWeek = document.getElementById("checkInWeek");
    const coutDisplay = document.getElementById("checkOutDisplay");
    const coutWeek = document.getElementById("checkOutWeek");
    const info = document.getElementById("nightsInfo");

    function updateUI() {
      // 1. 读取Input值
      const d1 = new Date(cin.value);
      const d2 = new Date(cout.value);
      
      // 2. 更新文字显示
      if (!isNaN(d1)) {
        cinDisplay.textContent = getDisplayDate(d1);
        cinWeek.textContent = getWeek(d1);
      }
      if (!isNaN(d2)) {
        coutDisplay.textContent = getDisplayDate(d2);
        coutWeek.textContent = getWeek(d2);
      }

      // 3. 计算晚数
      const diff = Math.ceil((d2 - d1) / (1000 * 60 * 60 * 24));
      if (diff > 0) {
        info.textContent = `${diff}晚`;
        info.style.color = ""; // 清除内联样式，使用 CSS 定义的颜色
        info.style.borderColor = "";
      } else {
        info.textContent = "无效";
        info.style.color = "#ff4d4f";
        info.style.borderColor = "#ff4d4f";
      }
    }

    cin.addEventListener("input", (e) => {
      // 简单校验：入住变了，如果退房早于入住，自动往后推1天
      const d1 = new Date(e.target.value);
      const d2 = new Date(cout.value);
      if (d1 >= d2) {
        const next = new Date(d1);
        next.setDate(d1.getDate() + 1);
        cout.value = formatDate(next);
      }
      updateUI();
    });
    
    cout.addEventListener("input", updateUI);
  }

  function bind() {
    const form = document.querySelector(".quick-crawl-form");
    if (!form) return;

    const btn = form.querySelector('button[type="submit"]');

    ensureLocationField();
    ensureExecSourceField();
    ensureDateFields();

    // capture=true：抢在原型页的“模拟逻辑”之前拦截
    form.addEventListener(
      "submit",
      async function (e) {
        e.preventDefault();
        e.stopImmediatePropagation();

        const hotelNamesRaw = (document.getElementById("hotelNames")?.value || "").trim();
        if (!hotelNamesRaw) {
          window.showToast && window.showToast("请输入至少一个酒店名称", "error");
          return;
        }

        const hotels = hotelNamesRaw
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean);

        const platforms = getSelectedPlatforms();
        if (!platforms.length) {
          window.showToast && window.showToast("请至少选择一个目标平台", "error");
          return;
        }
        const execSources = getExecSources();
        if (!execSources.length) {
          window.showToast && window.showToast("请至少选择一个执行端", "error");
          return;
        }

        const location = (document.getElementById("locationInput")?.value || "").trim() || "上海";
        const checkIn = document.getElementById("checkInDate")?.value;
        const checkOut = document.getElementById("checkOutDate")?.value;

        if (btn) {
          btn.disabled = true;
          btn.textContent = "创建中...";
        }

        try {
          const requests = [];
          if (execSources.includes("desktop")) {
            requests.push(postJson("/api/crawl-tasks/batch", { hotels, platforms, location, check_in: checkIn, check_out: checkOut }));
          }
          if (execSources.includes("mobile")) {
            requests.push(postJson("/api/app-crawl-tasks", { hotels, platforms, location, check_in: checkIn, check_out: checkOut }));
          }
          await Promise.all(requests);
          const labels = platforms.map(platformLabel).join("、");
          const sourceLabel = execSources
            .map((s) => (s === "mobile" ? "手机端" : "电脑端"))
            .join("、");
          window.showToast &&
            window.showToast(
              `已创建 ${hotels.length} 个任务（${labels} · ${sourceLabel}）`,
              "success"
            );
          setTimeout(() => {
            if (confirm("是否跳转到任务列表查看？")) {
              window.location.href = "crawl-tasks.html";
            }
          }, 600);
        } catch (err) {
          window.showToast && window.showToast(err.message || String(err), "error");
        } finally {
          if (btn) {
            btn.disabled = false;
            btn.textContent = "开始爬取";
          }
        }
      },
      true
    );
  }

  // 加载最近任务列表
  async function loadRecentTasks() {
    const taskList = document.querySelector(".task-list");
    if (!taskList) return;
    
    try {
      // 先显示加载状态
      taskList.innerHTML = '<li style="padding: 20px; text-align: center; color: #8C8C8C;"><i class="fas fa-spinner fa-spin"></i> 加载中...</li>';
      
      const res = await fetch("/api/crawl-tasks/dashboard/recent-tasks-merged", {
        cache: 'no-cache',
        credentials: 'include',
        headers: {
          'Cache-Control': 'no-cache',
          'Pragma': 'no-cache'
        }
      });
      const payload = await res.json();
      if (!res.ok || payload.success === false) {
        throw new Error(payload.error || "加载失败");
      }
      
      const tasks = payload.data || [];
      
      // 清空现有内容
      taskList.innerHTML = "";
      
      if (tasks.length === 0) {
        taskList.innerHTML = '<li style="padding: 20px; text-align: center; color: #8C8C8C;">暂无任务</li>';
        return;
      }
      
      // 状态样式映射
      const statusClassMap = {
        "已完成": "success",
        "爬取中": "running",
        "等待中": "queued",
        "失败": "failed",
        "已取消": "cancelled"
      };
      
      // 渲染任务列表（合并接口返回含 exec_source，手机端跳转手机详情页）
      tasks.forEach((task) => {
        const li = document.createElement("li");
        li.className = "task-item";
        const isMobile = (task.exec_source || "") === "手机端";
        const detailUrl = isMobile
          ? `mobile_task_detail.html?task_id=${encodeURIComponent(task.task_id)}`
          : `task_detail.html?task_id=${encodeURIComponent(task.task_id)}`;
        li.onclick = () => {
          window.location.href = detailUrl;
        };
        
        const statusClass = statusClassMap[task.status] || "queued";
        const sourceLabel = task.exec_source ? ` · ${task.exec_source}` : "";
        
        li.innerHTML = `
          <div class="task-info">
            <h4>${task.hotel_name}</h4>
            <p>${task.platforms} | ${task.time}${sourceLabel}</p>
          </div>
          <span class="task-status ${statusClass}">${task.status}</span>
        `;
        taskList.appendChild(li);
      });
    } catch (err) {
      console.error("加载最近任务失败:", err);
      // 失败时不显示错误，保持页面正常显示
    }
  }
  
  // 加载数据趋势
  let trendChart = null;
  async function loadTrendData() {
    const canvas = document.getElementById("trendChart");
    if (!canvas) return;
    
    try {
      // 等待Chart.js加载完成
      if (typeof Chart === "undefined") {
        setTimeout(loadTrendData, 100);
        return;
      }
      
      // 先销毁可能存在的旧图表实例（包括演示数据图表）
      if (Chart.getChart) {
        const existingChart = Chart.getChart(canvas);
        if (existingChart) {
          existingChart.destroy();
        }
      }
      if (trendChart) {
        trendChart.destroy();
        trendChart = null;
      }
      
      const res = await fetch("/api/crawl-tasks/dashboard/trend-merged", {
        cache: 'no-cache',
        credentials: 'include',
        headers: {
          'Cache-Control': 'no-cache',
          'Pragma': 'no-cache'
        }
      });
      const payload = await res.json();
      if (!res.ok || payload.success === false) {
        throw new Error(payload.error || "加载失败");
      }
      
      const data = payload.data || {};
      const labels = data.labels || [];
      const values = data.values || [];
      
      const ctx = canvas.getContext("2d");
      
      // 创建新图表（使用真实数据）
      trendChart = new Chart(ctx, {
        type: "line",
        data: {
          labels: labels,
          datasets: [
            {
              label: "新增数据量",
              data: values,
              borderColor: "#1a365d",
              backgroundColor: "rgba(26, 54, 93, 0.1)",
              tension: 0.4,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: false,
            },
          },
          scales: {
            y: {
              beginAtZero: true,
            },
          },
        },
      });
    } catch (err) {
      console.error("加载数据趋势失败:", err);
      // 失败时不创建默认图表，保持页面正常显示
    }
  }
  
  // 初始化：加载数据
  function initDashboard() {
    // 立即清空可能存在的演示数据
    const taskList = document.querySelector(".task-list");
    if (taskList) {
      taskList.innerHTML = '<li style="padding: 20px; text-align: center; color: #8C8C8C;"><i class="fas fa-spinner fa-spin"></i> 加载中...</li>';
    }
    
    // 清空图表容器（如果存在旧的Chart实例）
    const canvas = document.getElementById("trendChart");
    if (canvas && typeof Chart !== "undefined") {
      const existingChart = Chart.getChart ? Chart.getChart(canvas) : null;
      if (existingChart) {
        existingChart.destroy();
      }
    }
    
    // 加载真实数据
    loadRecentTasks();
    loadTrendData();
    
    // 每30秒刷新一次数据
    setInterval(() => {
      loadRecentTasks();
      loadTrendData();
    }, 30000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      bind();
      initDashboard();
    });
  } else {
    bind();
    initDashboard();
  }
})();

