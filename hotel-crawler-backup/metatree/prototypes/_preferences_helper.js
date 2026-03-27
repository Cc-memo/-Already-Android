// 全局偏好设置辅助函数
// 可以在所有页面使用，确保偏好设置全局生效

// ============================================
// 立即执行：在脚本加载时就应用主题，避免"闪白"
// ============================================
(function() {
    try {
        const prefs = JSON.parse(localStorage.getItem('user_preferences') || '{}');
        if (prefs.theme === 'dark') {
            // 立即给 html 添加 dark-theme 类
            document.documentElement.classList.add('dark-theme');
            // 立即注入深色模式 CSS（内联在 head 中）
            const style = document.createElement('style');
            style.id = 'dark-theme-immediate';
            style.textContent = `
                html.dark-theme, body.dark-theme { background: #0d1117 !important; color: #c9d1d9 !important; }
                html.dark-theme .layout, body.dark-theme .layout,
                html.dark-theme .main-content, body.dark-theme .main-content,
                html.dark-theme .content, body.dark-theme .content { background: #0d1117 !important; }
                html.dark-theme .header, body.dark-theme .header { background: #161b22 !important; border-bottom: 1px solid #30363d !important; }
                html.dark-theme .page-header, body.dark-theme .page-header,
                html.dark-theme .settings-panel, body.dark-theme .settings-panel,
                html.dark-theme .filter-bar, body.dark-theme .filter-bar,
                html.dark-theme .query-panel, body.dark-theme .query-panel,
                html.dark-theme .result-panel, body.dark-theme .result-panel,
                html.dark-theme .stat-card, body.dark-theme .stat-card,
                html.dark-theme .card, body.dark-theme .card,
                html.dark-theme .quick-actions, body.dark-theme .quick-actions,
                html.dark-theme .table-container, body.dark-theme .table-container,
                html.dark-theme .chart-card, body.dark-theme .chart-card,
                html.dark-theme .export-panel, body.dark-theme .export-panel,
                html.dark-theme .history-panel, body.dark-theme .history-panel,
                html.dark-theme .analysis-tabs, body.dark-theme .analysis-tabs,
                html.dark-theme .info-card, body.dark-theme .info-card,
                html.dark-theme .task-card, body.dark-theme .task-card,
                html.dark-theme .detail-panel, body.dark-theme .detail-panel,
                html.dark-theme .form-container, body.dark-theme .form-container,
                html.dark-theme .room-types, body.dark-theme .room-types,
                html.dark-theme .hotel-header, body.dark-theme .hotel-header,
                html.dark-theme .hotel-info, body.dark-theme .hotel-info,
                html.dark-theme .detail-card, body.dark-theme .detail-card,
                html.dark-theme .platform-tabs, body.dark-theme .platform-tabs,
                html.dark-theme .chart-section, body.dark-theme .chart-section {
                    background: #161b22 !important;
                    border: 1px solid #30363d !important;
                    box-shadow: none !important;
                }
                html.dark-theme input, html.dark-theme select, html.dark-theme textarea,
                html.dark-theme .form-group input, html.dark-theme .form-group select, html.dark-theme .form-group textarea,
                html.dark-theme .form-item input, html.dark-theme .form-item select, html.dark-theme .form-item textarea,
                body.dark-theme input, body.dark-theme select, body.dark-theme textarea,
                body.dark-theme .form-group input, body.dark-theme .form-group select, body.dark-theme .form-group textarea,
                body.dark-theme .form-item input, body.dark-theme .form-item select, body.dark-theme .form-item textarea {
                    background: #0d1117 !important;
                    color: #c9d1d9 !important;
                    border-color: #30363d !important;
                }
                html.dark-theme input::placeholder, html.dark-theme textarea::placeholder,
                body.dark-theme input::placeholder, body.dark-theme textarea::placeholder {
                    color: #6e7681 !important;
                }
                html.dark-theme .form-group label, html.dark-theme .form-item label,
                body.dark-theme .form-group label, body.dark-theme .form-item label {
                    color: #f0f6fc !important;
                }
                html.dark-theme .page-title, html.dark-theme .section-title,
                body.dark-theme .page-title, body.dark-theme .section-title {
                    color: #f0f6fc !important;
                }
                html.dark-theme .btn-upload, body.dark-theme .btn-upload {
                    background: #21262d !important;
                    color: #79c0ff !important;
                    border-color: #58a6ff !important;
                }
                html.dark-theme .btn-secondary, body.dark-theme .btn-secondary {
                    background: #21262d !important;
                    color: #c9d1d9 !important;
                    border-color: #30363d !important;
                }
                html.dark-theme .btn-secondary:hover, body.dark-theme .btn-secondary:hover {
                    background: #30363d !important;
                    border-color: #58a6ff !important;
                    color: #58a6ff !important;
                }
                html.dark-theme .switch-label, body.dark-theme .switch-label {
                    color: #f0f6fc !important;
                }
                html.dark-theme input[type="checkbox"], body.dark-theme input[type="checkbox"] {
                    background: #0d1117 !important;
                    border-color: #30363d !important;
                    accent-color: #58a6ff !important;
                }
                html.dark-theme input[type="date"], body.dark-theme input[type="date"] {
                    background: #0d1117 !important;
                    color: #c9d1d9 !important;
                    border-color: #30363d !important;
                }
                html.dark-theme .info-card, body.dark-theme .info-card {
                    background: #161b22 !important;
                    border: 1px solid #30363d !important;
                }
                html.dark-theme .status-badge, body.dark-theme .status-badge {
                    font-weight: 500 !important;
                }
                /* 任务详情(inject)：返回任务列表、复制 JSON 等 .td-btn 与 JSON 框 .td-pre */
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
                html.dark-theme .td-btn.primary, body.dark-theme .td-btn.primary {
                    background: #238636 !important;
                    color: #fff !important;
                    border-color: #238636 !important;
                }
                html.dark-theme .td-btn.primary:hover, body.dark-theme .td-btn.primary:hover {
                    background: #2ea043 !important;
                    border-color: #2ea043 !important;
                    color: #fff !important;
                }
                html.dark-theme .td-pre, body.dark-theme .td-pre {
                    background: #0d1117 !important;
                    color: #c9d1d9 !important;
                    border: 1px solid #30363d !important;
                }
            `;
            document.head.appendChild(style);
        } else if (prefs.theme === 'auto') {
            if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
                document.documentElement.classList.add('dark-theme');
            }
        }
    } catch (e) {}
})();

// 加载并应用偏好设置
function loadAndApplyPreferences() {
    try {
        const prefs = JSON.parse(localStorage.getItem('user_preferences') || '{}');
        
        // 应用主题
        if (prefs.theme) {
            applyTheme(prefs.theme);
        }
        
        // 应用语言（如果需要）
        if (prefs.language) {
            applyLanguage(prefs.language);
        }
        
        // 应用每页显示条数（存储到全局变量，供数据表格使用）
        if (prefs.pageSize) {
            window.defaultPageSize = prefs.pageSize;
        }
        
        // 应用时区（存储到全局变量，供日期显示使用）
        if (prefs.timezone) {
            window.userTimezone = prefs.timezone;
        }
        
        return prefs;
    } catch (error) {
        console.error('加载偏好设置失败:', error);
        return {};
    }
}

// 应用主题
function applyTheme(theme) {
    if (!theme) return;
    
    if (theme === 'dark') {
        // 先给 html 加类名，避免 body 未就绪导致“闪白”
        document.documentElement.classList.add('dark-theme');
        if (document.body) document.body.classList.add('dark-theme');
        else document.addEventListener('DOMContentLoaded', () => document.body.classList.add('dark-theme'), { once: true });
        // 添加深色主题样式 - 统一标准样式（基于用户管理页面）
        if (!document.getElementById('dark-theme-style')) {
            const style = document.createElement('style');
            style.id = 'dark-theme-style';
            style.textContent = `
                /* ============================================
                   全局深色模式统一样式 - 标准版
                   基于用户管理页面的优秀设计
                   确保所有文字对比度 ≥ 7:1 (WCAG AAA标准)
                   ============================================ */
                
                html.dark-theme,
                body.dark-theme {
                    background: #0d1117 !important;
                    color: #c9d1d9 !important;
                }
                
                html.dark-theme .main-content,
                body.dark-theme .main-content {
                    background: #0d1117 !important;
                }
                
                html.dark-theme .layout,
                body.dark-theme .layout {
                    background: #0d1117 !important;
                }
                
                /* ========== 侧边栏 ========== */
                html.dark-theme .sidebar,
                body.dark-theme .sidebar {
                    background: linear-gradient(180deg, #161b22 0%, #0d1117 100%) !important;
                }
                
                body.dark-theme .logo {
                    border-bottom-color: rgba(255,255,255,0.2) !important;
                }
                
                body.dark-theme .logo i {
                    color: #fbbf24 !important;
                }
                
                body.dark-theme .logo-text {
                    color: #ffffff !important;
                }
                
                body.dark-theme .menu-item {
                    color: #c9d1d9 !important;
                    text-shadow: none !important;
                    -webkit-text-stroke: 0 !important;
                    text-rendering: optimizeSpeed !important;
                    -webkit-font-smoothing: subpixel-antialiased !important;
                    -moz-osx-font-smoothing: auto !important;
                }
                
                body.dark-theme .menu-item:hover {
                    background: rgba(255,255,255,0.08) !important;
                    color: #fbbf24 !important;
                    text-shadow: none !important;
                }
                
                body.dark-theme .menu-item.active {
                    background: rgba(251, 191, 36, 0.15) !important;
                    color: #fbbf24 !important;
                    border-left-color: #fbbf24 !important;
                    text-shadow: none !important;
                }
                
                body.dark-theme .menu-item i {
                    color: inherit !important;
                    text-shadow: none !important;
                    -webkit-text-stroke: 0 !important;
                    filter: none !important;
                    -webkit-font-smoothing: subpixel-antialiased !important;
                    -moz-osx-font-smoothing: auto !important;
                }
                
                body.dark-theme .menu-item span {
                    text-shadow: none !important;
                    -webkit-text-stroke: 0 !important;
                }
                
                /* ========== 导航菜单（兼容不同页面） ========== */
                body.dark-theme .nav-menu a {
                    color: #c9d1d9 !important;
                    text-shadow: none !important;
                    -webkit-text-stroke: 0 !important;
                }
                
                body.dark-theme .nav-menu a:hover {
                    background: rgba(255,255,255,0.08) !important;
                    color: #fbbf24 !important;
                }
                
                body.dark-theme .nav-menu a.active {
                    background: rgba(251, 191, 36, 0.15) !important;
                    color: #fbbf24 !important;
                    border-left-color: #fbbf24 !important;
                }
                
                body.dark-theme .nav-menu a i {
                    color: inherit !important;
                    text-shadow: none !important;
                    -webkit-text-stroke: 0 !important;
                }
                
                /* ========== 顶部导航 ========== */
                html.dark-theme .header,
                body.dark-theme .header {
                    background: #161b22 !important;
                    border-bottom: 1px solid #30363d !important;
                }
                
                body.dark-theme .breadcrumb {
                    color: #8b949e !important;
                }
                
                body.dark-theme .breadcrumb span {
                    color: #8b949e !important;
                }
                
                body.dark-theme .breadcrumb a {
                    color: #58a6ff !important;
                }
                
                body.dark-theme .breadcrumb a:hover {
                    color: #79c0ff !important;
                }
                
                body.dark-theme .user-info span {
                    color: #c9d1d9 !important;
                }
                
                body.dark-theme .user-info i {
                    color: #8b949e !important;
                }
                
                body.dark-theme .user-info i:hover {
                    color: #c9d1d9 !important;
                }
                
                body.dark-theme #notificationIcon {
                    color: #8b949e !important;
                }
                
                body.dark-theme #notificationIcon:hover {
                    color: #c9d1d9 !important;
                }
                
                body.dark-theme .user-info .fa-chevron-down {
                    color: #8b949e !important;
                }
                
                body.dark-theme .dropdown-menu {
                    background: #161b22 !important;
                    border: 1px solid #30363d !important;
                }
                
                body.dark-theme .dropdown-item {
                    color: #c9d1d9 !important;
                }
                
                body.dark-theme .dropdown-item:hover {
                    background: #21262d !important;
                    color: #fbbf24 !important;
                }
                
                body.dark-theme .dropdown-item i {
                    color: inherit !important;
                }
                
                /* ========== 页面内容 ========== */
                body.dark-theme .page-header {
                    background: #161b22 !important;
                    border: 1px solid #30363d !important;
                }
                
                body.dark-theme .page-title {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .settings-panel,
                body.dark-theme .filter-bar,
                body.dark-theme .table-container,
                body.dark-theme .query-panel,
                body.dark-theme .result-panel,
                body.dark-theme .content,
                body.dark-theme .stat-card,
                body.dark-theme .quick-actions,
                body.dark-theme .card,
                html.dark-theme .page-header,
                body.dark-theme .page-header,
                body.dark-theme .analysis-tabs,
                body.dark-theme .chart-card,
                body.dark-theme .export-panel,
                body.dark-theme .history-panel,
                body.dark-theme .info-card,
                body.dark-theme .task-card,
                body.dark-theme .detail-panel,
                body.dark-theme .form-container,
                body.dark-theme .room-types,
                body.dark-theme .hotel-header,
                body.dark-theme .hotel-info,
                body.dark-theme .detail-card,
                body.dark-theme .platform-tabs,
                body.dark-theme .chart-section {
                    background: #161b22 !important;
                    border: 1px solid #30363d !important;
                }
                
                /* 确保个人设置页面的所有面板都被覆盖（更具体的选择器） */
                body.dark-theme .content .page-header,
                body.dark-theme .content .settings-panel,
                body.dark-theme div.page-header,
                body.dark-theme div.settings-panel {
                    background: #161b22 !important;
                    border: 1px solid #30363d !important;
                    box-shadow: none !important;
                }
                
                body.dark-theme .query-panel h2,
                body.dark-theme .result-header h3 {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .query-panel h2 i,
                body.dark-theme .result-header h3 i {
                    color: #fbbf24 !important;
                }
                
                body.dark-theme .result-header {
                    background: #161b22 !important;
                    border-bottom-color: #30363d !important;
                }
                
                body.dark-theme .section-title {
                    color: #f0f6fc !important;
                    border-bottom-color: #30363d !important;
                }
                
                body.dark-theme .section-title i {
                    color: #fbbf24 !important;
                }
                
                body.dark-theme .form-actions {
                    border-top-color: #30363d !important;
                }
                
                body.dark-theme .slider:before {
                    background-color: #c9d1d9 !important;
                }
                
                /* ========== 表单元素 ========== */
                body.dark-theme .form-group label {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .form-group label .required {
                    color: #f85149 !important;
                }
                
                body.dark-theme .form-group input,
                body.dark-theme .form-group select,
                body.dark-theme .form-group textarea,
                body.dark-theme .form-item input,
                body.dark-theme .form-item select,
                body.dark-theme .form-item textarea,
                body.dark-theme input,
                body.dark-theme select,
                body.dark-theme textarea {
                    background: #0d1117 !important;
                    color: #c9d1d9 !important;
                    border-color: #30363d !important;
                }
                
                body.dark-theme .form-item label {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .form-group input::placeholder,
                body.dark-theme .form-group textarea::placeholder,
                body.dark-theme .form-item input::placeholder,
                body.dark-theme .form-item textarea::placeholder,
                body.dark-theme input::placeholder,
                body.dark-theme textarea::placeholder {
                    color: #6e7681 !important;
                }
                
                body.dark-theme .form-group input:disabled {
                    background: #0d1117 !important;
                    color: #6e7681 !important;
                    cursor: not-allowed;
                }
                
                body.dark-theme .form-group input:read-only {
                    background: #0d1117 !important;
                    color: #8b949e !important;
                    cursor: not-allowed;
                    border-color: #21262d !important;
                }
                
                body.dark-theme .form-group input:focus,
                body.dark-theme .form-group select:focus,
                body.dark-theme .form-group textarea:focus,
                body.dark-theme .form-item input:focus,
                body.dark-theme .form-item select:focus,
                body.dark-theme .form-item textarea:focus,
                body.dark-theme input:focus,
                body.dark-theme select:focus,
                body.dark-theme textarea:focus {
                    border-color: #58a6ff !important;
                    outline: none;
                    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.1);
                    background: #0d1117 !important;
                }
                
                body.dark-theme .form-group .hint,
                body.dark-theme .form-group small {
                    color: #8b949e !important;
                }
                
                /* ========== 按钮 ========== */
                body.dark-theme .btn-primary {
                    background: #238636 !important;
                    color: #ffffff !important;
                }
                
                body.dark-theme .btn-primary:hover {
                    background: #2ea043 !important;
                }
                
                body.dark-theme .btn-primary i {
                    color: #ffffff !important;
                }
                
                body.dark-theme .btn-secondary {
                    background: #21262d !important;
                    color: #c9d1d9 !important;
                    border-color: #30363d !important;
                }
                
                body.dark-theme .btn-secondary:hover {
                    background: #30363d !important;
                    border-color: #58a6ff !important;
                    color: #58a6ff !important;
                }
                
                body.dark-theme .btn-secondary i {
                    color: inherit !important;
                }
                
                body.dark-theme .btn-upload {
                    background: #21262d !important;
                    color: #79c0ff !important;
                    border-color: #58a6ff !important;
                    font-weight: 500 !important;
                }
                
                body.dark-theme .btn-upload:hover {
                    background: #30363d !important;
                    border-color: #79c0ff !important;
                    color: #a5d5ff !important;
                }
                
                body.dark-theme .btn-upload i {
                    color: inherit !important;
                }
                
                body.dark-theme .btn-icon {
                    color: #58a6ff !important;
                    background: transparent !important;
                }
                
                body.dark-theme .btn-icon:hover {
                    color: #79c0ff !important;
                    background: rgba(88, 166, 255, 0.1) !important;
                }
                
                body.dark-theme .btn-icon.danger {
                    color: #f85149 !important;
                }
                
                body.dark-theme .btn-icon.danger:hover {
                    color: #ff6b6b !important;
                    background: rgba(248, 81, 73, 0.1) !important;
                }
                
                /* ========== 任务详情(inject)：.td-btn 返回/复制JSON、.td-pre JSON框 ========== */
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
                html.dark-theme .td-btn.primary, body.dark-theme .td-btn.primary {
                    background: #238636 !important;
                    color: #fff !important;
                    border-color: #238636 !important;
                }
                html.dark-theme .td-btn.primary:hover, body.dark-theme .td-btn.primary:hover {
                    background: #2ea043 !important;
                    border-color: #2ea043 !important;
                    color: #fff !important;
                }
                html.dark-theme .td-pre, body.dark-theme .td-pre {
                    background: #0d1117 !important;
                    color: #c9d1d9 !important;
                    border: 1px solid #30363d !important;
                }
                
                /* ========== 开关 ========== */
                body.dark-theme .slider {
                    background-color: #30363d !important;
                }
                
                body.dark-theme input:checked + .slider {
                    background-color: #58a6ff !important;
                }
                
                body.dark-theme .switch-label {
                    color: #f0f6fc !important;
                    font-weight: 500 !important;
                }
                
                html.dark-theme .switch-label {
                    color: #f0f6fc !important;
                    font-weight: 500 !important;
                }
                
                /* ========== 开关容器 ========== */
                body.dark-theme .switch-container,
                html.dark-theme .switch-container {
                    color: #f0f6fc !important;
                }
                
                /* ========== Checkbox ========== */
                body.dark-theme input[type="checkbox"],
                html.dark-theme input[type="checkbox"] {
                    background: #0d1117 !important;
                    border-color: #30363d !important;
                    accent-color: #58a6ff !important;
                }
                
                body.dark-theme input[type="checkbox"]:checked,
                html.dark-theme input[type="checkbox"]:checked {
                    background: #58a6ff !important;
                    border-color: #58a6ff !important;
                }
                
                body.dark-theme .checkbox-item,
                html.dark-theme .checkbox-item {
                    color: #c9d1d9 !important;
                }
                
                body.dark-theme .checkbox-item label,
                html.dark-theme .checkbox-item label {
                    color: #f0f6fc !important;
                }
                
                /* ========== 日期选择器 ========== */
                body.dark-theme input[type="date"],
                html.dark-theme input[type="date"],
                body.dark-theme input[type="datetime-local"],
                html.dark-theme input[type="datetime-local"] {
                    background: #0d1117 !important;
                    color: #c9d1d9 !important;
                    border-color: #30363d !important;
                }
                
                body.dark-theme input[type="date"]::-webkit-calendar-picker-indicator,
                html.dark-theme input[type="date"]::-webkit-calendar-picker-indicator,
                body.dark-theme input[type="datetime-local"]::-webkit-calendar-picker-indicator,
                html.dark-theme input[type="datetime-local"]::-webkit-calendar-picker-indicator {
                    filter: invert(0.8);
                    cursor: pointer;
                }
                
                /* ========== 表格 ========== */
                body.dark-theme table {
                    background: #161b22 !important;
                }
                
                body.dark-theme th {
                    background: #0d1117 !important;
                    color: #f0f6fc !important;
                    border-bottom: 1px solid #30363d !important;
                }
                
                body.dark-theme td {
                    color: #c9d1d9 !important;
                    border-bottom: 1px solid #21262d !important;
                }
                
                body.dark-theme tbody tr:hover,
                html.dark-theme tbody tr:hover {
                    background: #21262d !important;
                }
                
                /* ========== 数据详情页面 - 房型信息 ========== */
                body.dark-theme .room-types h2,
                html.dark-theme .room-types h2 {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .room-types table,
                html.dark-theme .room-types table {
                    background: #161b22 !important;
                }
                
                body.dark-theme .room-types thead,
                html.dark-theme .room-types thead {
                    background: #0d1117 !important;
                }
                
                body.dark-theme .room-types th,
                html.dark-theme .room-types th {
                    background: #0d1117 !important;
                    color: #f0f6fc !important;
                    border-bottom-color: #30363d !important;
                }
                
                body.dark-theme .room-types td,
                html.dark-theme .room-types td {
                    color: #c9d1d9 !important;
                    border-bottom-color: #21262d !important;
                }
                
                body.dark-theme .room-types tbody tr:hover,
                html.dark-theme .room-types tbody tr:hover {
                    background: #21262d !important;
                }
                
                /* ========== 数据详情页面 - 酒店头部、平台标签、图表、信息卡 ========== */
                body.dark-theme .hotel-header h1,
                html.dark-theme .hotel-header h1 {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .meta-item,
                html.dark-theme .meta-item {
                    color: #8b949e !important;
                }
                
                body.dark-theme .platform-tabs .tabs-header,
                html.dark-theme .platform-tabs .tabs-header {
                    border-bottom-color: #30363d !important;
                }
                
                body.dark-theme .platform-tabs .tab,
                html.dark-theme .platform-tabs .tab {
                    color: #8b949e !important;
                }
                
                body.dark-theme .platform-tabs .tab.active,
                html.dark-theme .platform-tabs .tab.active {
                    color: #58a6ff !important;
                    border-bottom-color: #58a6ff !important;
                }
                
                body.dark-theme .platform-tabs .tab:hover,
                html.dark-theme .platform-tabs .tab:hover {
                    color: #c9d1d9 !important;
                }
                
                body.dark-theme .platform-tabs .tab-content,
                html.dark-theme .platform-tabs .tab-content {
                    color: #c9d1d9 !important;
                }
                
                body.dark-theme .info-grid .info-card,
                html.dark-theme .info-grid .info-card {
                    background: #21262d !important;
                    border: 1px solid #30363d !important;
                }
                
                body.dark-theme .info-grid .info-card label,
                html.dark-theme .info-grid .info-card label {
                    color: #8b949e !important;
                }
                
                body.dark-theme .info-grid .info-card .value,
                html.dark-theme .info-grid .info-card .value {
                    color: #c9d1d9 !important;
                }
                
                body.dark-theme .chart-section h2,
                html.dark-theme .chart-section h2 {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme thead {
                    background: #0d1117 !important;
                }
                
                body.dark-theme th.sortable:hover {
                    background: #21262d !important;
                }
                
                body.dark-theme .platform-badge {
                    background: rgba(88, 166, 255, 0.2) !important;
                    color: #79c0ff !important;
                    border: 1px solid rgba(88, 166, 255, 0.4) !important;
                }
                
                body.dark-theme .star-rating {
                    color: #fbbf24 !important;
                }
                
                body.dark-theme .pagination-info {
                    color: #8b949e !important;
                }
                
                body.dark-theme .pagination-btn {
                    background: #21262d !important;
                    color: #c9d1d9 !important;
                    border-color: #30363d !important;
                }
                
                body.dark-theme .pagination-btn:hover:not(:disabled) {
                    background: #30363d !important;
                    border-color: #58a6ff !important;
                    color: #58a6ff !important;
                }
                
                body.dark-theme .pagination-btn.active {
                    background: rgba(251, 191, 36, 0.2) !important;
                    color: #fbbf24 !important;
                    border-color: #fbbf24 !important;
                }
                
                body.dark-theme .pagination-btn:disabled {
                    opacity: 0.5;
                    cursor: not-allowed;
                }
                
                /* ========== 首页统计卡片 ========== */
                body.dark-theme .stat-card-title {
                    color: #8b949e !important;
                }
                
                body.dark-theme .stat-card-value {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .stat-card-footer {
                    color: #8b949e !important;
                }
                
                body.dark-theme .stat-card-icon.blue {
                    background: rgba(88, 166, 255, 0.2) !important;
                    color: #79c0ff !important;
                }
                
                body.dark-theme .stat-card-icon.green {
                    background: rgba(46, 160, 67, 0.2) !important;
                    color: #56d364 !important;
                }
                
                body.dark-theme .stat-card-icon.orange {
                    background: rgba(251, 191, 36, 0.2) !important;
                    color: #fbbf24 !important;
                }
                
                body.dark-theme .stat-card-icon.purple {
                    background: rgba(163, 113, 247, 0.2) !important;
                    color: #d2a8ff !important;
                }
                
                /* ========== 任务状态标签 ========== */
                body.dark-theme .task-status.success {
                    background: rgba(46, 160, 67, 0.2) !important;
                    color: #56d364 !important;
                    border-color: rgba(46, 160, 67, 0.4) !important;
                }
                
                body.dark-theme .task-status.running {
                    background: rgba(88, 166, 255, 0.2) !important;
                    color: #79c0ff !important;
                    border-color: rgba(88, 166, 255, 0.4) !important;
                }
                
                body.dark-theme .task-status.failed {
                    background: rgba(248, 81, 73, 0.2) !important;
                    color: #ff6b6b !important;
                    border-color: rgba(248, 81, 73, 0.4) !important;
                }
                
                body.dark-theme .status-badge,
                html.dark-theme .status-badge {
                    font-weight: 500 !important;
                }
                
                body.dark-theme .status-pending,
                html.dark-theme .status-pending {
                    background: rgba(251, 191, 36, 0.2) !important;
                    color: #fbbf24 !important;
                    border: 1px solid rgba(251, 191, 36, 0.4) !important;
                }
                
                body.dark-theme .status-running,
                html.dark-theme .status-running,
                body.dark-theme .status-processing,
                html.dark-theme .status-processing {
                    background: rgba(88, 166, 255, 0.2) !important;
                    color: #79c0ff !important;
                    border: 1px solid rgba(88, 166, 255, 0.4) !important;
                }
                
                body.dark-theme .status-completed,
                html.dark-theme .status-completed,
                body.dark-theme .status-success,
                html.dark-theme .status-success {
                    background: rgba(46, 160, 67, 0.2) !important;
                    color: #56d364 !important;
                    border: 1px solid rgba(46, 160, 67, 0.4) !important;
                }
                
                body.dark-theme .status-failed,
                html.dark-theme .status-failed,
                body.dark-theme .status-error,
                html.dark-theme .status-error {
                    background: rgba(248, 81, 73, 0.2) !important;
                    color: #ff6b6b !important;
                    border: 1px solid rgba(248, 81, 73, 0.4) !important;
                }
                
                body.dark-theme .status-paused,
                html.dark-theme .status-paused {
                    background: rgba(201, 209, 217, 0.2) !important;
                    color: #8b949e !important;
                    border: 1px solid rgba(201, 209, 217, 0.4) !important;
                }
                
                /* ========== 任务详情页面 ========== */
                body.dark-theme .info-card h2,
                html.dark-theme .info-card h2 {
                    color: #f0f6fc !important;
                    border-bottom-color: #30363d !important;
                }
                
                body.dark-theme .info-item label,
                html.dark-theme .info-item label {
                    color: #8b949e !important;
                }
                
                body.dark-theme .info-item .value,
                html.dark-theme .info-item .value {
                    color: #c9d1d9 !important;
                }
                
                body.dark-theme .info-grid,
                html.dark-theme .info-grid {
                    gap: 24px;
                }
                
                body.dark-theme .filter-item label,
                html.dark-theme .filter-item label {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .filter-item select,
                html.dark-theme .filter-item select,
                body.dark-theme .filter-item input,
                html.dark-theme .filter-item input {
                    background: #0d1117 !important;
                    color: #c9d1d9 !important;
                    border-color: #30363d !important;
                }
                
                body.dark-theme .progress-section,
                html.dark-theme .progress-section {
                    color: #c9d1d9 !important;
                }
                
                body.dark-theme .progress-info,
                html.dark-theme .progress-info {
                    color: #8b949e !important;
                }
                
                body.dark-theme .progress-bar,
                html.dark-theme .progress-bar {
                    background: #21262d !important;
                }
                
                body.dark-theme .progress-fill,
                html.dark-theme .progress-fill {
                    background: #58a6ff !important;
                }
                
                body.dark-theme .task-item {
                    border-bottom-color: #21262d !important;
                }
                
                body.dark-theme .task-info h4 {
                    color: #c9d1d9 !important;
                }
                
                body.dark-theme .task-info p {
                    color: #8b949e !important;
                }
                
                /* ========== 通用卡片和面板 ========== */
                body.dark-theme .section-title {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .checkbox-item label {
                    color: #c9d1d9 !important;
                }
                
                body.dark-theme .form-group label {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .form-group .hint {
                    color: #8b949e !important;
                }
                
                /* ========== 新建任务页面 ========== */
                body.dark-theme .form-container,
                html.dark-theme .form-container {
                    background: #161b22 !important;
                    border: 1px solid #30363d !important;
                }
                
                body.dark-theme .tabs,
                html.dark-theme .tabs {
                    border-bottom-color: #30363d !important;
                }
                
                body.dark-theme .tab,
                html.dark-theme .tab {
                    color: #8b949e !important;
                }
                
                body.dark-theme .tab.active,
                html.dark-theme .tab.active {
                    color: #fbbf24 !important;
                    border-bottom-color: #fbbf24 !important;
                }
                
                body.dark-theme .tab:hover,
                html.dark-theme .tab:hover {
                    color: #c9d1d9 !important;
                }
                
                body.dark-theme .form-section-title,
                html.dark-theme .form-section-title {
                    color: #f0f6fc !important;
                    border-bottom-color: #30363d !important;
                }
                
                body.dark-theme .tab-content,
                html.dark-theme .tab-content {
                    color: #c9d1d9 !important;
                }
                
                /* ========== 内容网格 ========== */
                body.dark-theme .content-grid {
                    gap: 24px;
                }
                
                body.dark-theme .chart-container {
                    background: transparent !important;
                }
                
                /* ========== 数据分析页面 ========== */
                body.dark-theme .chart-title {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .stat-label {
                    color: #8b949e !important;
                }
                
                body.dark-theme .stat-value {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .tab-btn {
                    color: #8b949e !important;
                }
                
                body.dark-theme .tab-btn.active {
                    color: #fbbf24 !important;
                    border-bottom-color: #fbbf24 !important;
                }
                
                body.dark-theme .tab-btn:hover {
                    color: #c9d1d9 !important;
                }
                
                /* ========== 数据导出页面 ========== */
                body.dark-theme .export-panel .section-title {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .history-panel .section-title {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .btn-link {
                    color: #58a6ff !important;
                }
                
                body.dark-theme .btn-link:hover {
                    color: #79c0ff !important;
                }
                
                /* ========== 标签 ========== */
                body.dark-theme .role-badge,
                body.dark-theme .status-badge {
                    font-weight: 500 !important;
                }
                
                body.dark-theme .role-admin {
                    background: rgba(88, 166, 255, 0.2) !important;
                    color: #79c0ff !important;
                    border: 1px solid rgba(88, 166, 255, 0.4) !important;
                }
                
                body.dark-theme .role-badge[style*="722ED1"],
                body.dark-theme .role-badge[style*="722ed1"],
                body.dark-theme span.role-badge.role-admin[style*="722"] {
                    background: rgba(163, 113, 247, 0.3) !important;
                    color: #d2a8ff !important;
                    border: 1px solid rgba(163, 113, 247, 0.6) !important;
                }
                
                body.dark-theme .role-user {
                    background: rgba(201, 209, 217, 0.2) !important;
                    color: #e6edf3 !important;
                    border: 1px solid rgba(201, 209, 217, 0.4) !important;
                }
                
                body.dark-theme .role-operator {
                    background: rgba(251, 191, 36, 0.2) !important;
                    color: #fbbf24 !important;
                    border: 1px solid rgba(251, 191, 36, 0.4) !important;
                }
                
                body.dark-theme .status-active {
                    background: rgba(46, 160, 67, 0.25) !important;
                    color: #56d364 !important;
                    border: 1px solid rgba(46, 160, 67, 0.5) !important;
                }
                
                body.dark-theme .status-inactive {
                    background: rgba(248, 81, 73, 0.25) !important;
                    color: #ff6b6b !important;
                    border: 1px solid rgba(248, 81, 73, 0.5) !important;
                }
                
                /* ========== 分页 ========== */
                body.dark-theme .pagination {
                    background: #161b22 !important;
                }
                
                body.dark-theme .pagination button {
                    background: #21262d !important;
                    color: #c9d1d9 !important;
                    border-color: #30363d !important;
                }
                
                body.dark-theme .pagination button:hover:not(:disabled) {
                    background: #30363d !important;
                    border-color: #58a6ff !important;
                    color: #58a6ff !important;
                }
                
                body.dark-theme .pagination button:disabled {
                    opacity: 0.5;
                    cursor: not-allowed;
                }
                
                body.dark-theme .pagination .page-info {
                    color: #8b949e !important;
                }
                
                /* ========== 模态框 ========== */
                body.dark-theme .modal {
                    background: rgba(0, 0, 0, 0.7) !important;
                }
                
                body.dark-theme .modal-content {
                    background: #161b22 !important;
                    border: 1px solid #30363d !important;
                }
                
                body.dark-theme .modal-title {
                    color: #f0f6fc !important;
                }
                
                body.dark-theme .modal-close {
                    color: #8b949e !important;
                }
                
                body.dark-theme .modal-close:hover {
                    color: #c9d1d9 !important;
                }
                
                /* ========== Toast ========== */
                body.dark-theme .toast {
                    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
                }
                
                body.dark-theme .toast.success {
                    background: #1a472a !important;
                    color: #3fb950 !important;
                    border-color: #238636 !important;
                }
                
                body.dark-theme .toast.info {
                    background: #1c2128 !important;
                    color: #58a6ff !important;
                    border-color: #30363d !important;
                }
                
                body.dark-theme .toast.error {
                    background: #3d1f1f !important;
                    color: #f85149 !important;
                    border-color: #da3633 !important;
                }
                
                body.dark-theme .toast i {
                    color: inherit !important;
                }
                
                /* ========== 选择框 ========== */
                body.dark-theme select {
                    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%238b949e' d='M6 9L1 4h10z'/%3E%3C/svg%3E");
                    background-repeat: no-repeat;
                    background-position: right 8px center;
                    padding-right: 32px;
                }
                
                body.dark-theme select option {
                    background: #161b22 !important;
                    color: #c9d1d9 !important;
                }
                
                /* ========== 头像 ========== */
                body.dark-theme .avatar-preview {
                    background: #0d1117 !important;
                    border-color: #30363d !important;
                }
                
                body.dark-theme .avatar-preview i {
                    color: #8b949e !important;
                }
                
                body.dark-theme .user-avatar {
                    box-shadow: 0 2px 8px rgba(251, 191, 36, 0.3);
                }
                
                /* ========== 其他 ========== */
                body.dark-theme .form-actions {
                    border-top-color: #30363d !important;
                }
                
                body.dark-theme .loading,
                body.dark-theme .empty-state {
                    color: #8b949e !important;
                }
                
                body.dark-theme #strengthBar1,
                body.dark-theme #strengthBar2,
                body.dark-theme #strengthBar3,
                body.dark-theme #strengthBar4 {
                    background: #30363d !important;
                }
                
                body.dark-theme #strengthText {
                    color: #8b949e !important;
                }
                
                body.dark-theme * {
                    -webkit-font-smoothing: antialiased;
                    -moz-osx-font-smoothing: grayscale;
                }
            `;
            document.head.appendChild(style);
        }
    } else if (theme === 'light') {
        document.body.classList.remove('dark-theme');
    } else if (theme === 'auto') {
        // 跟随系统
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        if (prefersDark) {
            document.body.classList.add('dark-theme');
        } else {
            document.body.classList.remove('dark-theme');
        }
        
        // 监听系统主题变化
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        const handleChange = (e) => {
            if (e.matches) {
                document.body.classList.add('dark-theme');
            } else {
                document.body.classList.remove('dark-theme');
            }
        };
        // 使用addEventListener（现代浏览器）或addListener（旧浏览器）
        if (mediaQuery.addEventListener) {
            mediaQuery.addEventListener('change', handleChange);
        } else {
            mediaQuery.addListener(handleChange);
        }
    }
}

// 导出到全局，供其他页面使用
window.applyTheme = applyTheme;

// 应用语言（如果需要国际化）
function applyLanguage(language) {
    if (!language) return;
    
    // 设置html lang属性
    document.documentElement.lang = language;
    
    // 这里可以添加更多的语言切换逻辑
    // 比如加载对应的语言包等
}

// 获取偏好设置
function getPreferences() {
    try {
        return JSON.parse(localStorage.getItem('user_preferences') || '{}');
    } catch (error) {
        console.error('获取偏好设置失败:', error);
        return {};
    }
}

// 获取每页显示条数
function getPageSize() {
    const prefs = getPreferences();
    return prefs.pageSize || 20;
}

// 获取时区
function getTimezone() {
    const prefs = getPreferences();
    return prefs.timezone || 'Asia/Shanghai';
}

// 获取主题
function getTheme() {
    const prefs = getPreferences();
    return prefs.theme || 'light';
}

// 页面加载时自动应用偏好设置
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadAndApplyPreferences);
} else {
    loadAndApplyPreferences();
}
