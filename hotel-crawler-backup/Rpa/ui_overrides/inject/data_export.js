// 数据导出页面注入脚本
(function() {
    'use strict';

    // 工具函数：显示提示消息
    function showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        const toastMessage = document.getElementById('toastMessage');
        const icon = toast.querySelector('i');
        
        if (!toast || !toastMessage) return;
        
        toastMessage.textContent = message;
        toast.className = 'toast ' + type + ' show';
        
        if (type === 'success') {
            icon.className = 'fas fa-check-circle';
        } else if (type === 'error') {
            icon.className = 'fas fa-exclamation-circle';
        } else {
            icon.className = 'fas fa-info-circle';
        }
        
        setTimeout(() => toast.classList.remove('show'), 3000);
    }

    // 加载导出历史
    async function loadExportHistory() {
        try {
            const response = await fetch('/api/exports?per_page=50');
            const result = await response.json();
            
            if (!result.success) {
                console.error('加载导出历史失败:', result.error);
                return;
            }
            
            const tbody = document.querySelector('.history-panel tbody');
            if (!tbody) return;
            
            // 清空现有内容
            tbody.innerHTML = '';
            
            if (result.data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #999;">暂无导出记录</td></tr>';
                return;
            }
            
            // 渲染导出历史
            result.data.forEach(exp => {
                console.log('📋 [前端] 渲染导出记录:', exp);
                
                const tr = document.createElement('tr');
                const formatText = exp.format === 'excel' ? 'Excel' : 'CSV';
                const rowCount = exp.row_count || 0;
                const createdTime = exp.created_at || '';
                const exportId = exp.id;
                
                if (!exportId) {
                    console.warn('⚠️ [前端] 导出记录缺少ID:', exp);
                }
                
                // 检查是否有文件路径（file_path 不为空表示文件已保存，可以下载）
                const hasFile = exp.file_path && String(exp.file_path).trim() !== '';
                
                tr.innerHTML = `
                    <td>${exp.file_name || ''}</td>
                    <td>${createdTime}</td>
                    <td>${rowCount.toLocaleString()} 条</td>
                    <td>${formatText}</td>
                    <td>
                        ${hasFile ? 
                            `<a href="#" class="btn-link" data-export-id="${exportId || ''}">下载</a>` :
                            `<span style="color: #999; cursor: default;">已过期</span>`
                        }
                    </td>
                `;
                
                // 绑定下载事件（仅当文件存在时）
                if (hasFile) {
                    const downloadLink = tr.querySelector('a[data-export-id]');
                    if (downloadLink) {
                        downloadLink.addEventListener('click', (e) => {
                            e.preventDefault();
                            console.log('🖱️ [前端] 点击下载按钮:', { exportId, fileName: exp.file_name });
                            if (!exportId) {
                                showToast('导出ID无效，无法下载', 'error');
                                return;
                            }
                            downloadExport(exportId, exp.file_name);
                        });
                    }
                }
                
                tbody.appendChild(tr);
            });
        } catch (error) {
            console.error('加载导出历史失败:', error);
            showToast('加载导出历史失败', 'error');
        }
    }

    // 下载导出文件
    async function downloadExport(exportId, fileName) {
        try {
            if (!exportId) {
                console.error('❌ [前端] 导出ID无效:', exportId);
                throw new Error('导出ID无效');
            }
            
            console.log('📥 [前端] 开始下载:', { exportId, fileName, url: `/api/exports/${exportId}/download` });
            const url = `/api/exports/${exportId}/download`;
            const response = await fetch(url);
            
            console.log('📥 [前端] 响应状态:', response.status, response.statusText);
            
            // 检查响应类型
            const contentType = response.headers.get('content-type');
            const isJson = contentType && contentType.includes('application/json');
            
            console.log('📥 [前端] 响应Content-Type:', contentType, 'isJson:', isJson);
            
            if (!response.ok) {
                let errorMsg = '下载失败';
                console.error('❌ [前端] 响应失败:', response.status, response.statusText);
                
                if (isJson) {
                    try {
                        const result = await response.json();
                        console.error('❌ [前端] 错误详情:', result);
                        errorMsg = result.error || errorMsg;
                    } catch (e) {
                        console.error('❌ [前端] 解析错误响应失败:', e);
                        errorMsg = `HTTP ${response.status}: ${response.statusText}`;
                    }
                } else {
                    // 尝试读取响应文本
                    try {
                        const text = await response.text();
                        console.error('❌ [前端] 错误响应文本:', text);
                        errorMsg = text || `HTTP ${response.status}: ${response.statusText}`;
                    } catch (e) {
                        errorMsg = `HTTP ${response.status}: ${response.statusText}`;
                    }
                }
                throw new Error(errorMsg);
            }
            
            // 如果是 JSON 响应（错误情况），处理它
            if (isJson) {
                const result = await response.json();
                if (!result.success) {
                    throw new Error(result.error || '下载失败');
                }
            }
            
            // 获取文件 blob
            const blob = await response.blob();
            
            // 检查 blob 是否有效
            if (!blob || blob.size === 0) {
                throw new Error('文件内容为空');
            }
            
            // 创建下载链接
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = fileName || 'export.xlsx';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(downloadUrl);
            
            showToast('文件下载成功', 'success');
            
            // 刷新历史列表
            setTimeout(() => loadExportHistory(), 500);
        } catch (error) {
            console.error('下载失败:', error);
            showToast('下载失败: ' + error.message, 'error');
        }
    }

    // 处理导出表单提交
    function handleExportForm() {
        const form = document.getElementById('exportForm');
        if (!form) return;
        
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const btn = form.querySelector('button[type="submit"]');
            if (!btn) return;
            
            // 获取表单数据
            const dataRange = document.getElementById('dataRange')?.value || 'all';
            const startDate = document.getElementById('startDate')?.value;
            const endDate = document.getElementById('endDate')?.value;
            
            // 获取选中的平台
            const platforms = [];
            ['meituan', 'ctrip', 'fliggy', 'gaode'].forEach(platform => {
                const checkbox = document.getElementById(`platform-${platform}`);
                if (checkbox && checkbox.checked) {
                    platforms.push(platform);
                }
            });
            
            if (platforms.length === 0) {
                showToast('请至少选择一个平台', 'error');
                return;
            }
            
            // 获取导出格式
            const formatRadio = form.querySelector('input[name="format"]:checked');
            const format = formatRadio ? formatRadio.value : 'excel';
            
            // 准备请求数据
            const requestData = {
                data_range: dataRange,
                platforms: platforms,
                format: format,
                start_date: startDate || null,
                end_date: endDate || null,
                query_params: {}  // 如果是"当前查询结果"，这里可以从 URL 或其他地方获取
            };
            
            // 禁用按钮，显示加载状态
            btn.disabled = true;
            const originalHtml = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 导出中...';
            
            try {
                const response = await fetch('/api/exports', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });
                
                // 检查响应类型：如果是文件下载，直接处理
                const contentType = response.headers.get('content-type') || '';
                const isFile = (
                    contentType.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') ||
                    contentType.includes('text/csv') ||
                    contentType.includes('application/octet-stream')
                );
                
                if (isFile) {
                    // 直接是文件响应，触发下载
                    const blob = await response.blob();
                    const downloadUrl = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = downloadUrl;
                    
                    // 从响应头获取导出ID和文件名
                    const exportId = response.headers.get('X-Export-Id');
                    const contentDisposition = response.headers.get('Content-Disposition') || '';
                    let fileName = 'export.xlsx';
                    const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                    if (match && match[1]) {
                        fileName = match[1].replace(/['"]/g, '');
                    }
                    
                    a.download = fileName;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    window.URL.revokeObjectURL(downloadUrl);
                    
                    const rowCount = response.headers.get('X-Export-Row-Count') || '0';
                    showToast(`导出成功！共 ${rowCount} 条数据，文件已下载`, 'success');
                    
                    // 刷新历史列表（如果有导出ID）
                    if (exportId) {
                        setTimeout(() => loadExportHistory(), 1000);
                    }
                } else {
                    // JSON 响应（错误情况）
                    const result = await response.json();
                    
                    if (!result.success) {
                        throw new Error(result.error || '导出失败');
                    }
                    
                    // 如果返回 JSON 但包含下载链接（兼容旧版本）
                    showToast(`导出成功！共 ${result.data.row_count} 条数据`, 'success');
                    
                    if (result.data.download_url) {
                        setTimeout(() => {
                            downloadExport(result.data.id, result.data.file_name);
                        }, 500);
                    }
                    
                    // 刷新历史列表
                    setTimeout(() => loadExportHistory(), 1000);
                }
                
            } catch (error) {
                console.error('导出失败:', error);
                showToast('导出失败: ' + error.message, 'error');
            } finally {
                // 恢复按钮
                btn.disabled = false;
                btn.innerHTML = originalHtml;
            }
        });
    }

    // 初始化
    function init() {
        // 处理导出表单
        handleExportForm();
        
        // 加载导出历史
        loadExportHistory();
        
        // 监听数据范围变化，显示/隐藏日期选择
        const dataRangeSelect = document.getElementById('dataRange');
        if (dataRangeSelect) {
            dataRangeSelect.addEventListener('change', function() {
                const dateRangeGroup = document.getElementById('dateRangeGroup');
                if (dateRangeGroup) {
                    dateRangeGroup.style.display = this.value === 'date' ? 'block' : 'none';
                }
            });
        }
    }

    // DOM 加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
