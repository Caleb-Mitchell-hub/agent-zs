"""前端页面路由"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index():
    """AI 助手主页 — 侧边栏对话列表 + 聊天区"""
    return """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI 智能助手</title>
        <style>
            :root {
                --primary: #1890ff;
                --primary-hover: #40a9ff;
                --primary-dark: #096dd9;
                --primary-soft: #e6f7ff;
                --success: #52c41a;
                --warning: #fa8c16;
                --danger: #ff4d4f;
                --surface: #ffffff;
                --border: #e8e8e8;
                --text: #262626;
                --text-secondary: #8c8c8c;
                --text-muted: #bfbfbf;
                --radius: 8px;
            }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; height: 100vh; display: flex; }

            /* ── 侧边栏 ── */
            .sidebar { width: 280px; background: #fff; border-right: 1px solid #e8e8e8; display: flex; flex-direction: column; flex-shrink: 0; }
            .sidebar-header { padding: 16px; border-bottom: 1px solid #e8e8e8; }
            .sidebar-header h3 { font-size: 15px; color: #333; margin-bottom: 12px; display: flex; align-items: center; gap: 6px; }
            .sidebar-header h3 span { font-size: 11px; color: #999; font-weight: normal; }
            .new-chat-btn { width: 100%; padding: 10px 0; background: #1890ff; color: white; border: none; border-radius: 8px; font-size: 14px; cursor: pointer; transition: background 0.2s; }
            .new-chat-btn:hover { background: #40a9ff; }
            .session-list { flex: 1; overflow-y: auto; padding: 8px 0; }
            .session-list::-webkit-scrollbar { width: 4px; }
            .session-list::-webkit-scrollbar-thumb { background: #d9d9d9; border-radius: 2px; }
            .session-item { padding: 12px 16px; cursor: pointer; border-left: 3px solid transparent; display: flex; justify-content: space-between; align-items: center; transition: background 0.15s; }
            .session-item:hover { background: #f5f5f5; }
            .session-item.active { background: #e6f7ff; border-left-color: #1890ff; }
            .session-item .info { overflow: hidden; flex: 1; min-width: 0; }
            .session-item .title { font-size: 13px; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px; }
            .session-item .meta { font-size: 11px; color: #999; }
            .session-item .del-btn { visibility: hidden; background: none; border: none; color: #999; font-size: 16px; cursor: pointer; padding: 2px 6px; border-radius: 4px; line-height: 1; flex-shrink: 0; }
            .session-item:hover .del-btn { visibility: visible; }
            .session-item .del-btn:hover { background: #fff2f0; color: #ff4d4f; }
            .no-sessions { padding: 32px 16px; text-align: center; color: #bbb; font-size: 13px; }

            /* ── 任务区 ── */
            .task-panel { border-top: 1px solid #e8e8e8; max-height: 45%; display: flex; flex-direction: column; }
            .task-panel .task-header { padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; flex-shrink: 0; }
            .task-panel .task-header span { font-size: 13px; color: #333; font-weight: 500; }
            .task-panel .task-header #taskCount { font-size: 11px; color: #999; font-weight: normal; }
            .task-tabs { display: flex; padding: 0 12px 8px; gap: 4px; flex-shrink: 0; }
            .task-tab { flex: 1; padding: 6px 0; text-align: center; font-size: 12px; border: 1px solid #e8e8e8; border-radius: 6px; cursor: pointer; color: #666; }
            .task-tab.active { border-color: var(--primary); color: var(--primary); background: var(--primary-soft); }
            .task-list { overflow-y: auto; padding: 0 8px 8px; flex: 1; }
            .task-list::-webkit-scrollbar { width: 4px; }
            .task-list::-webkit-scrollbar-thumb { background: #d9d9d9; border-radius: 2px; }
            .task-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; gap: 6px; }
            .task-item:hover { background: #f5f5f5; }
            .task-item .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
            .task-item .dot.pending { background: var(--primary); }
            .task-item .dot.doing { background: var(--warning); }
            .task-item .dot.done { background: var(--success); }
            .task-item .dot.overdue { background: var(--danger); }

            /* ── 工作记录（日历视图）── */
            .calendar-area { flex: 1; overflow-y: auto; padding: 16px 20px; }
            .cal-wrap { max-width: 860px; margin: 0 auto; }
            .cal-nav { display: flex; align-items: center; gap: 6px; margin-bottom: 16px; }
            .cal-nav .nav-btn { width: 26px; height: 26px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); cursor: pointer; display: flex; align-items: center; justify-content: center; color: var(--text-secondary); font-size: 14px; transition: all .15s; }
            .cal-nav .nav-btn:hover { color: var(--primary); border-color: var(--primary); }
            .cal-nav .cal-title { font-size: 14px; font-weight: 500; min-width: 108px; text-align: center; }
            .cal-nav select { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 12px; background: var(--surface); outline: none; color: var(--text); }
            .stat-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
            .stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 18px; border-left: 3px solid var(--primary); }
            .stat-card .num { font-size: 26px; font-weight: 700; color: var(--text); line-height: 1.1; }
            .stat-card .lbl { font-size: 12px; color: var(--text-secondary); margin-top: 5px; }
            .stat-card.done { border-left-color: var(--success); }
            .stat-card.created { border-left-color: var(--primary); }
            .stat-card.active { border-left-color: var(--warning); }
            .stat-card.rate { border-left-color: #722ed1; }
            .cal { border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
            .cal-weekhead { display: grid; grid-template-columns: repeat(7, 1fr); background: #fafafa; border-bottom: 1px solid var(--border); }
            .cal-weekhead span { text-align: center; font-size: 11px; color: var(--text-secondary); padding: 8px 0; }
            .cal-weekhead .wk { color: var(--danger); }
            .cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); }
            .cal-cell { min-height: 76px; border-right: 1px solid var(--border); border-bottom: 1px solid var(--border); padding: 6px 8px; cursor: pointer; position: relative; transition: outline .1s; background: #fff; }
            .cal-cell:nth-child(7n) { border-right: none; }
            .cal-cell:hover { outline: 2px solid var(--primary); outline-offset: -2px; z-index: 1; }
            .cal-cell.other { background: #fafafa; }
            .cal-cell .day-num { font-size: 12px; color: var(--text-secondary); width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; border-radius: 50%; }
            .cal-cell.today .day-num { color: #fff; background: var(--primary); font-weight: 500; }
            .cal-cell .cell-stats { display: flex; gap: 10px; margin-top: 8px; font-size: 11px; align-items: center; }
            .cal-cell .c-done { color: #389e0d; font-weight: 600; }
            .cal-cell .c-created { color: var(--primary); }
            .cal-cell .c-done::before { content: '✓'; margin-right: 2px; font-size: 10px; }
            .cal-cell .c-created::before { content: '+'; margin-right: 2px; font-size: 11px; }
            .cal-detail { margin-top: 16px; border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 18px; background: var(--surface); }
            .cal-detail .d-head { font-size: 13px; font-weight: 500; margin-bottom: 8px; }
            .cal-detail .d-item { display: flex; align-items: center; gap: 10px; padding: 7px 0; font-size: 12px; color: var(--text); border-bottom: 1px dashed var(--border); }
            .cal-detail .d-item:last-child { border-bottom: none; }
            .cal-detail .d-item .d-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
            .cal-detail .d-item .d-name { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .cal-detail .d-item .d-time { font-size: 11px; color: var(--text-muted); }
            .cal-detail .d-empty { font-size: 12px; color: var(--text-muted); padding: 4px 0; }
            .year-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
            .mini-cal { border: 1px solid var(--border); border-radius: 6px; padding: 10px; }
            .mini-cal .mc-title { font-size: 12px; font-weight: 500; text-align: center; margin-bottom: 8px; }
            .mini-cal .mc-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; }
            .mini-cal .mc-cell { aspect-ratio: 1; border-radius: 2px; background: #ebedf0; display: flex; align-items: center; justify-content: center; font-size: 8px; color: #999; }
            .mini-cal .mc-cell.has { background: var(--primary-soft); color: var(--primary-dark); font-weight: 600; }
            .mini-cal .mc-cell.today { background: var(--primary); color: #fff; }

            /* ── 主区域 ── */
            .main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
            .topbar { background: #1890ff; color: white; padding: 12px 20px; display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
            .topbar h1 { font-size: 16px; font-weight: 500; }
            .topbar .user-info { font-size: 13px; opacity: 0.9; }
            .topbar .user-info a { color: #fff; text-decoration: underline; cursor: pointer; }
            .topbar .user-info a:hover { opacity: 0.8; }
            .chat-area { flex: 1; display: flex; flex-direction: column; max-width: 860px; margin: 0 auto; width: 100%; padding: 16px 20px; overflow: hidden; }
            .chat-box { flex: 1; overflow-y: auto; padding-right: 4px; }
            .chat-box::-webkit-scrollbar { width: 4px; }
            .chat-box::-webkit-scrollbar-thumb { background: #d9d9d9; border-radius: 2px; }

            .message { margin-bottom: 16px; display: flex; gap: 10px; }
            .message.user { flex-direction: row-reverse; }
            .message .avatar { width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0; }
            .message.user .avatar { background: #1890ff; color: white; }
            .message.assistant .avatar { background: #52c41a; color: white; }
            .message .msg-body { display: flex; flex-direction: column; max-width: 75%; min-width: 0; }
            .message.user .msg-body { align-items: flex-end; }
            .message.assistant .msg-body { align-items: flex-start; }
            .message .content { max-width: 100%; padding: 10px 14px; border-radius: 12px; font-size: 14px; line-height: 1.6; word-break: break-word; }
            .message.user .content { background: #1890ff; color: white; border-bottom-right-radius: 4px; }
            .message.assistant .content { background: #fff; color: #333; border-bottom-left-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); white-space: pre-wrap; }

            /* 旧消息加载时灰色背景 */
            .message.assistant.history .content { background: #fafafa; }

            .message .content pre { background: #1e1e1e; color: #d4d4d4; padding: 10px; border-radius: 6px; overflow-x: auto; font-size: 12px; margin-top: 6px; }
            .table-wrap { overflow-x: auto; max-width: 100%; }
            .message .content table { width: 100%; border-collapse: collapse; margin-top: 6px; min-width: 500px; font-size: 12px; }
            .message .content th, .message .content td { border: 1px solid #e8e8e8; padding: 6px 8px; text-align: left; white-space: nowrap; }
            .message .content th { background: #fafafa; font-weight: 500; }
            /* 消息复制按钮（纯图标，无文字）：用户消息左下角、AI 消息右下角 */
            .message .copy-btn { background: none; border: none; cursor: pointer; padding: 3px; border-radius: 4px; color: #bfbfbf; flex-shrink: 0; display: flex; align-items: center; justify-content: center; margin-top: 4px; transition: color 0.2s, background 0.2s; }
            .message.user .msg-body .copy-btn { align-self: flex-start; }
            .message.assistant .msg-body .copy-btn { align-self: flex-end; }
            .message .copy-btn:hover { color: #1890ff; background: #f0f0f0; }
            .message .copy-btn.copied { color: #52c41a; }
            .error-msg { color: #ff4d4f; background: #fff2f0; border: 1px solid #ffccc7; padding: 10px 12px; border-radius: 8px; font-size: 13px; }
            .quick-actions { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; flex-shrink: 0; }
            .quick-btn { background: #fff; border: 1px solid #d9d9d9; padding: 6px 14px; border-radius: 16px; cursor: pointer; font-size: 12px; transition: all 0.2s; }
            .quick-btn:hover { border-color: #1890ff; color: #1890ff; }
            .input-area { display: flex; gap: 10px; flex-shrink: 0; }
            .input-area input { flex: 1; padding: 10px 14px; border: 1px solid #d9d9d9; border-radius: 8px; font-size: 14px; outline: none; }
            .input-area input:focus { border-color: #1890ff; box-shadow: 0 0 0 2px rgba(24,144,255,0.15); }
            .input-area button { background: #1890ff; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; }
            .input-area button:hover { background: #40a9ff; }
            .input-area button:disabled { background: #d9d9d9; cursor: not-allowed; }
            .typing { display: none; padding: 6px 0; color: #999; font-size: 12px; flex-shrink: 0; }
            .typing.show { display: block; }
            .welcome { text-align: center; padding: 60px 20px; color: #bbb; }
            .welcome h2 { font-size: 22px; color: #999; margin-bottom: 10px; }
            .welcome p { font-size: 13px; }

            /* ── 响应式 ── */
            @media (max-width: 700px) {
                .sidebar { display: none; }
            }
        </style>
    </head>
    <body>
        <!-- 侧边栏 -->
        <div class="sidebar">
            <div class="sidebar-header">
                <h3>对话列表 <span id="sessionCount"></span></h3>
                <button class="new-chat-btn" onclick="newChat()">＋ 新对话</button>
            </div>
            <div class="session-list" id="sessionList">
                <div class="no-sessions">加载中...</div>
            </div>
            <div class="task-panel" id="taskPanel">
                <div class="task-header" onclick="toggleTaskPanel()">
                    <span>任务列表 <span id="taskCount"></span></span><span id="taskArrow">▾</span>
                </div>
                <div class="task-tabs" id="taskTabs">
                    <div class="task-tab active" data-filter="all" onclick="switchTaskTab('all')">全部</div>
                    <div class="task-tab" data-filter="done" onclick="switchTaskTab('done')">已完成</div>
                    <div class="task-tab" data-filter="pending" onclick="switchTaskTab('pending')">待办</div>
                    <div class="task-tab" data-filter="doing" onclick="switchTaskTab('doing')">处理中</div>
                </div>
                <input type="text" id="taskSearch" placeholder="搜索任务..." oninput="loadTasks()" style="margin:0 12px 6px;padding:6px 10px;border:1px solid #e8e8e8;border-radius:6px;font-size:12px;">
                <div class="task-list" id="taskList"></div>
            </div>
        </div>

        <!-- 主区域 -->
        <div class="main">
            <div class="topbar">
                <h1>AI 智能助手</h1>
                <span class="user-info">
                    <a onclick="switchMainView('chat')">聊天</a> |
                    <a onclick="switchMainView('calendar')">工作记录<span id="remindBadge" style="display:none;background:#fff;color:#ff4d4f;border-radius:8px;font-size:10px;padding:0 5px;margin-left:4px;font-weight:600;">提醒</span></a> |
                    <span id="userNameDisplay"></span> | <a onclick="logout()">退出</a>
                </span>
            </div>
            <div class="chat-area" id="chatArea">
                <div class="quick-actions">
                    <button class="quick-btn" onclick="askQuick('查询所有仓库的库存', 'query')">查询库存</button>
                    <button class="quick-btn" onclick="askQuick('统计本月销售额', 'query')">本月销售</button>
                    <button class="quick-btn" onclick="askQuick('采购订单审批流程', 'knowledge')">审批流程</button>
                    <button class="quick-btn" onclick="askQuick('创建采购订单', 'create')">创建订单</button>
                </div>
                <div class="chat-box" id="chatBox">
                    <div class="welcome"><h2>欢迎使用 AI 智能助手</h2><p>点击左侧「新对话」开始，或选择已有对话</p></div>
                </div>
                <div class="typing" id="typing">AI 正在思考...</div>
                <div class="input-area">
                    <input type="text" id="input" placeholder="输入你的问题..." onkeypress="if(event.key==='Enter')send()">
                    <button id="sendBtn" onclick="send()">发送</button>
                </div>
            </div>
            <div class="calendar-area" id="calPanel" style="display:none">
                <div class="cal-wrap">
                    <div class="cal-nav">
                        <button class="nav-btn" onclick="calShift(-1)">‹</button>
                        <span class="cal-title" id="calTitle"></span>
                        <button class="nav-btn" onclick="calShift(1)">›</button>
                        <select id="calView" onchange="switchCalView(this.value)">
                            <option value="month">月视图</option>
                            <option value="year">年视图</option>
                        </select>
                    </div>
                    <div class="stat-cards">
                        <div class="stat-card done"><div class="num" id="kDone">0</div><div class="lbl">本月完成</div></div>
                        <div class="stat-card created"><div class="num" id="kCreated">0</div><div class="lbl">本月创建</div></div>
                        <div class="stat-card active"><div class="num" id="kActive">0</div><div class="lbl">活跃天数</div></div>
                        <div class="stat-card rate"><div class="num" id="kRate">—</div><div class="lbl">完成率</div></div>
                    </div>
                    <div id="calMonth">
                        <div class="cal">
                            <div class="cal-weekhead">
                                <span class="wk">日</span><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span class="wk">六</span>
                            </div>
                            <div class="cal-grid" id="calGrid"></div>
                        </div>
                        <div class="cal-detail" id="calDetail"></div>
                    </div>
                    <div id="calYear" style="display:none">
                        <div class="year-grid" id="yearGrid"></div>
                    </div>
                </div>
            </div>
        </div>

        <script>
            // ── 认证 ──────────────────────────────────────
            const token = localStorage.getItem('token');
            if (!token) { window.location.href = '/login'; }

            function getUserDisplayName() {
                try {
                    const payload = JSON.parse(atob(token.split('.')[1]));
                    return payload.real_name || payload.username || '未命名用户';
                } catch(e) { return '未命名用户'; }
            }
            document.getElementById('userNameDisplay').textContent = getUserDisplayName();

            function logout() {
                localStorage.removeItem('token');
                localStorage.removeItem('userName');
                localStorage.removeItem('activeSessionId');
                window.location.href = '/login';
            }

            // ── 会话管理 ──────────────────────────────────
            const API_QUERY = '/api/v1/query';
            const API_QUERY_STREAM = '/api/v1/query/stream';
            const API_SESSIONS = '/api/v1/sessions';
            let activeSessionId = null;
            const chatBox = document.getElementById('chatBox');
            const input = document.getElementById('input');
            const typing = document.getElementById('typing');
            const sendBtn = document.getElementById('sendBtn');
            const sessionList = document.getElementById('sessionList');

            function generateSessionId() {
                return 'web-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
            }

            async function loadSessionList() {
                try {
                    const res = await fetch(API_SESSIONS, {
                        headers: { 'Authorization': 'Bearer ' + token }
                    });
                    const data = await res.json();
                    if (data.status !== 'ok') return;
                    const sessions = data.sessions || [];
                    document.getElementById('sessionCount').textContent = sessions.length ? '(' + sessions.length + ')' : '';
                    if (sessions.length === 0) {
                        sessionList.innerHTML = '<div class="no-sessions">暂无对话</div>';
                        return;
                    }
                    sessionList.innerHTML = sessions.map(s => {
                        const date = s.last_active_at ? new Date(s.last_active_at).toLocaleDateString('zh-CN') : '';
                        const isActive = s.session_id === activeSessionId;
                        return '<div class="session-item' + (isActive ? ' active' : '') + '" ' +
                            'onclick="openSession(\\'' + s.session_id + '\\')" ' +
                            'title="' + (s.title || '新对话').replace(/"/g, '&quot;') + '">' +
                            '<div class="info">' +
                            '<div class="title">' + escapeHtml(s.title || '新对话') + '</div>' +
                            '<div class="meta">' + date + (s.message_count ? ' · ' + s.message_count + ' 条消息' : '') + '</div>' +
                            '</div>' +
                            '<button class="del-btn" onclick="event.stopPropagation();deleteSession(\\'' + s.session_id + '\\')" title="删除">×</button>' +
                            '</div>';
                    }).join('');
                } catch (e) {
                    console.error('加载会话列表失败', e);
                }
            }

            function escapeHtml(str) {
                const div = document.createElement('div');
                div.textContent = str;
                return div.innerHTML;
            }

            async function openSession(sessionId) {
                if (activeSessionId === sessionId) return;
                activeSessionId = sessionId;
                localStorage.setItem('activeSessionId', sessionId);
                chatBox.innerHTML = '<div style="text-align:center;padding:40px;color:#bbb;">加载中...</div>';
                try {
                    const res = await fetch(API_SESSIONS + '/' + sessionId + '/messages', {
                        headers: { 'Authorization': 'Bearer ' + token }
                    });
                    const data = await res.json();
                    chatBox.innerHTML = '';
                    const msgs = data.messages || [];
                    if (msgs.length === 0) {
                        chatBox.innerHTML = '<div class="welcome"><p>开始新对话吧</p></div>';
                    } else {
                        msgs.forEach(m => {
                            const role = m.role === 'user' ? 'user' : 'assistant';
                            const content = role === 'assistant' ? formatAssistantContent(m.content) : escapeHtml(m.content);
                            const extraClass = 'history';
                            addMessageEl(role, content, extraClass, m.content);
                        });
                    }
                    chatBox.scrollTop = chatBox.scrollHeight;
                } catch (e) {
                    chatBox.innerHTML = '<div class="error-msg">加载消息失败：' + e.message + '</div>';
                }
                loadSessionList();
                input.focus();
            }

            function newChat() {
                activeSessionId = generateSessionId();
                localStorage.setItem('activeSessionId', activeSessionId);
                chatBox.innerHTML = '<div class="welcome"><h2>新对话</h2><p>输入你的问题开始对话</p></div>';
                loadSessionList();
                input.focus();
            }

            async function deleteSession(sessionId) {
                if (!confirm('确定要删除这条对话吗？')) return;
                try {
                    await fetch(API_SESSIONS + '/' + sessionId, {
                        method: 'DELETE',
                        headers: { 'Authorization': 'Bearer ' + token }
                    });
                    if (activeSessionId === sessionId) {
                        newChat();
                    }
                    loadSessionList();
                } catch (e) {
                    alert('删除失败: ' + e.message);
                }
            }

            // ── 消息渲染 ──────────────────────────────────
            function addMessageEl(role, content, extraClass, rawText) {
                const div = document.createElement('div');
                div.className = 'message ' + role + (extraClass ? ' ' + extraClass : '');
                const avatar = role === 'user' ? '我' : 'AI';
                const copyBtn = '<button class="copy-btn" title="复制" onclick="copyMessage(this)">' +
                    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                    '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>' +
                    '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg></button>';
                div.innerHTML = '<div class="avatar">' + avatar + '</div>' +
                    '<div class="msg-body"><div class="content">' + content + '</div>' + copyBtn + '</div>';
                const btn = div.querySelector('.copy-btn');
                if (rawText) {
                    btn.dataset.text = rawText;
                } else {
                    btn.style.visibility = 'hidden';
                }
                chatBox.appendChild(div);
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            function addMessage(role, content, extraClass, rawText) {
                addMessageEl(role, content, extraClass || '', rawText);
            }

            function formatAssistantContent(text) {
                // 尝试解析 JSON（数据表格）
                try {
                    const data = JSON.parse(text);
                    if (Array.isArray(data) && data.length > 0) {
                        return formatTable(data);
                    }
                } catch(e) {}
                // 历史消息按标准 Markdown 表格存储，这里渲染成 HTML 表格
                return formatMarkdown(text || '');
            }

            function formatMarkdown(text) {
                const lines = text.split('\\n');
                let html = '';
                let i = 0;
                while (i < lines.length) {
                    const line = lines[i];
                    const isTable = line.trim().indexOf('|') === 0 && i + 1 < lines.length && lines[i + 1].indexOf('---') !== -1;
                    if (isTable) {
                        const headers = line.trim().slice(1, -1).split('|').map(c => c.trim());
                        let t = '<div class="table-wrap"><table><tr>';
                        headers.forEach(h => { t += '<th>' + escapeHtml(h) + '</th>'; });
                        t += '</tr>';
                        i += 2;
                        while (i < lines.length && lines[i].trim().indexOf('|') === 0) {
                            const cells = lines[i].trim().slice(1, -1).split('|').map(c => c.trim());
                            t += '<tr>';
                            headers.forEach((_, idx) => { t += '<td>' + escapeHtml(cells[idx] !== undefined ? cells[idx] : '') + '</td>'; });
                            t += '</tr>';
                            i++;
                        }
                        t += '</table></div>';
                        html += t;
                        continue;
                    }
                    html += escapeHtml(line);
                    html += '\\n';
                    i++;
                }
                return html;
            }

            function formatTable(rows) {
                if (!rows || rows.length === 0) return '无数据';
                let html = '<div class="table-wrap"><table><tr>';
                const keys = Object.keys(rows[0]);
                keys.forEach(k => html += '<th>' + escapeHtml(String(k)) + '</th>');
                html += '</tr>';
                rows.slice(0, 20).forEach(row => {
                    html += '<tr>';
                    keys.forEach(k => {
                        const v = row[k];
                        html += '<td>' + (v !== null && v !== undefined ? escapeHtml(String(v)) : '-') + '</td>';
                    });
                    html += '</tr>';
                });
                html += '</table></div>';
                if (rows.length > 20) html += '<p style="color:#999;margin-top:6px;">共 ' + rows.length + ' 条，仅显示前 20 条</p>';
                return html;
            }

            function formatResult(data) {
                if (data.status === 'error' || data.status === 'clarify') {
                    return '<div class="error-msg">' + escapeHtml(data.message || '抱歉，无法处理您的请求') + '</div>';
                }
                // 实时展示与复制、历史回看一致：一律渲染为标准 Markdown 文档
                return formatMarkdown(assistantRawText(data) || '');
            }

            // 复制按钮：原始文本（标准 Markdown 表格，与历史回看保持一致）
            function assistantRawText(data) {
                if (!data) return '';
                if (data.status === 'error' || data.status === 'clarify') {
                    return data.message || '';
                }
                if (!data.data || data.data.length === 0) {
                    return data.message || '';
                }
                const rows = data.data;
                const keys = Object.keys(rows[0] || {});
                // 与后端 _data_to_markdown 一致：单元格中的换行转空格，保证表格结构不坏
                const cell = v => (v === null || v === undefined ? '' : String(v).replace(/\\n/g, ' '));
                let md = '';
                if (data.message) md += data.message + '\\n\\n';
                md += '| ' + keys.join(' | ') + ' |\\n';
                md += '| ' + keys.map(() => '---').join(' | ') + ' |\\n';
                rows.forEach(r => {
                    md += '| ' + keys.map(k => cell(r[k])).join(' | ') + ' |\\n';
                });
                return md;
            }

            // 兼容非 HTTPS（http://ip:port 下 navigator.clipboard 不可用，用 execCommand 兜底）
            function copyText(text) {
                if (navigator.clipboard && window.isSecureContext) {
                    return navigator.clipboard.writeText(text);
                }
                const ta = document.createElement('textarea');
                ta.value = text;
                ta.style.position = 'fixed';
                ta.style.opacity = '0';
                document.body.appendChild(ta);
                ta.select();
                let ok = false;
                try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
                document.body.removeChild(ta);
                return ok ? Promise.resolve() : Promise.reject(new Error('复制失败'));
            }

            function copyMessage(btn) {
                const text = btn.dataset.text || '';
                if (!text) return;
                copyText(text).then(() => {
                    btn.classList.add('copied');
                    setTimeout(() => btn.classList.remove('copied'), 1500);
                }).catch(() => {
                    btn.classList.add('copied');
                    btn.style.color = '#ff4d4f';
                    setTimeout(() => { btn.classList.remove('copied'); btn.style.color = ''; }, 1500);
                });
            }

            // ── 查询 ──────────────────────────────────────
            function askQuick(question, intent) {
                input.value = question;
                window._quickIntent = intent || '';
                send();
            }

            async function send() {
                const q = input.value.trim();
                if (!q) return;

                const intent = window._quickIntent || '';
                window._quickIntent = '';

                // 如果没有活跃会话，自动创建
                if (!activeSessionId) {
                    activeSessionId = generateSessionId();
                    localStorage.setItem('activeSessionId', activeSessionId);
                }

                // 移除欢迎页
                const welcome = chatBox.querySelector('.welcome');
                if (welcome) welcome.remove();

                addMessage('user', escapeHtml(q), '', q);
                input.value = '';
                input.disabled = true;
                sendBtn.disabled = true;
                typing.classList.add('show');
                typing.textContent = 'AI 正在思考...';

                try {
                    // SSE 流式请求：分阶段推送进度，最后返回结果
                    const res = await fetch(API_QUERY_STREAM +
                        '?question=' + encodeURIComponent(q) +
                        '&session_id=' + encodeURIComponent(activeSessionId) +
                        '&intent=' + encodeURIComponent(intent), {
                        headers: { 'Authorization': 'Bearer ' + token }
                    });
                    if (!res.ok || !res.body) {
                        throw new Error('流式请求失败：' + res.status);
                    }
                    const reader = res.body.getReader();
                    const decoder = new TextDecoder();
                    let buf = '';
                    let finalData = null;
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        buf += decoder.decode(value, { stream: true });
                        // 逐条解析 SSE 事件（SSE 事件以双换行分隔）
                        let idx;
                        while ((idx = buf.indexOf('\\n\\n')) !== -1) {
                            const raw = buf.slice(0, idx);
                            buf = buf.slice(idx + 2);
                            const dataLine = raw.split('\\n').find(l => l.indexOf('data:') === 0);
                            if (!dataLine) continue;
                            let evt;
                            try { evt = JSON.parse(dataLine.slice(5).trim()); } catch (e) { continue; }
                            if (evt.type === 'progress') {
                                typing.textContent = evt.message;
                            } else if (evt.type === 'result') {
                                finalData = evt.data;
                            }
                        }
                    }
                    if (finalData) {
                        addMessage('assistant', formatResult(finalData), '', assistantRawText(finalData));
                    } else {
                        addMessage('assistant', '<div class="error-msg">未收到查询结果</div>');
                    }
                    // 刷新侧边栏列表
                    loadSessionList();
                } catch (e) {
                    addMessage('assistant', '<div class="error-msg">请求失败：' + escapeHtml(e.message) + '</div>');
                } finally {
                    typing.classList.remove('show');
                    typing.textContent = 'AI 正在思考...';
                    input.disabled = false;
                    sendBtn.disabled = false;
                    input.focus();
                }
            }

            // ── 任务管理 ──────────────────────────────────
            const API_TASKS = '/api/v1/tasks';
            let taskFilter = 'all';
            let currentTasks = [];
            let calYear = new Date().getFullYear(), calMonth = new Date().getMonth();

            async function loadTasks() {
                const q = document.getElementById('taskSearch').value.trim();
                const res = await fetch(`${API_TASKS}?filter=${taskFilter}&q=${encodeURIComponent(q)}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                const data = await res.json();
                renderTaskList(data.tasks || []);
            }
            function renderTaskList(tasks) {
                currentTasks = tasks;
                const el = document.getElementById('taskList');
                document.getElementById('taskCount').textContent = tasks.length ? `(${tasks.length})` : '';
                el.innerHTML = tasks.length ? tasks.map(t => `
                    <div class="task-item" onclick="taskMenu(${t.task_id})">
                        <span class="dot ${t.overdue ? 'overdue' : t.status}"></span>
                        <span style="flex:1;font-size:12px;color:#333;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(t.title)}</span>
                    </div>`).join('') : '<div style="padding:20px;text-align:center;color:#bbb;font-size:12px;">暂无任务</div>';
            }
            function switchTaskTab(filter) {
                taskFilter = filter;
                document.querySelectorAll('.task-tab').forEach(t => t.classList.toggle('active', t.dataset.filter === filter));
                loadTasks();
            }
            function toggleTaskPanel() {
                const list = document.getElementById('taskList');
                const hidden = list.style.display === 'none';
                list.style.display = hidden ? '' : 'none';
                document.getElementById('taskArrow').textContent = hidden ? '▾' : '▸';
            }
            async function taskMenu(id) {
                // 点击任务：在「待办」与「已完成」之间切换状态
                const t = currentTasks.find(x => x.task_id === id);
                if (!t) return;
                const next = t.status === 'done' ? 'pending' : 'done';
                try {
                    await fetch(`${API_TASKS}/${id}`, {
                        method: 'PATCH',
                        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                        body: JSON.stringify({ status: next })
                    });
                    loadTasks();
                } catch (e) { console.error('切换任务状态失败', e); }
            }

            // ── 工作记录（日历视图）──────────────────────
            function pad2(n) { return n < 10 ? '0' + n : '' + n; }
            function switchMainView(v) {
                document.getElementById('chatArea').style.display = v === 'chat' ? '' : 'none';
                document.getElementById('calPanel').style.display = v === 'calendar' ? '' : 'none';
                if (v === 'calendar') renderMonth();
            }
            async function renderMonth() {
                document.getElementById('calTitle').textContent = calYear + '年' + (calMonth + 1) + '月';
                const res = await fetch(`${API_TASKS}/worklog?year=${calYear}&month=${calMonth + 1}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                const d = await res.json();
                const done = d.done_by_day || {};
                const created = d.created_by_day || {};
                const firstDow = new Date(calYear, calMonth, 1).getDay();
                const dim = new Date(calYear, calMonth + 1, 0).getDate();
                const dimPrev = new Date(calYear, calMonth, 0).getDate();
                const now = new Date();
                let cells = '';
                for (let i = 0; i < 42; i++) {
                    let y = calYear, m = calMonth, d, other = false;
                    if (i < firstDow) {
                        m = calMonth - 1; if (m < 0) { m = 11; y--; }
                        d = dimPrev - firstDow + 1 + i; other = true;
                    } else if (i >= firstDow + dim) {
                        m = calMonth + 1; if (m > 11) { m = 0; y++; }
                        d = i - firstDow - dim + 1; other = true;
                    } else {
                        d = i - firstDow + 1;
                    }
                    const key = y + '-' + pad2(m + 1) + '-' + pad2(d);
                    const dn = done[key] || 0, cn = created[key] || 0;
                    const isToday = y === now.getFullYear() && m === now.getMonth() && d === now.getDate();
                    cells += '<div class="cal-cell' + (other ? ' other' : '') + (isToday ? ' today' : '') + '" onclick="showDay(\\'' + key + '\\')">'
                           + '<span class="day-num">' + d + '</span>'
                           + (other ? '' : '<div class="cell-stats"><span class="c-done">' + dn + '</span><span class="c-created">' + cn + '</span></div>')
                           + '</div>';
                }
                document.getElementById('calGrid').innerHTML = cells;
                document.getElementById('kDone').textContent = d.total_done || 0;
                document.getElementById('kCreated').textContent = d.total_created || 0;
                document.getElementById('kActive').textContent = d.active_days || 0;
                document.getElementById('kRate').textContent = d.total_created ? Math.round(d.rate * 100) + '%' : '—';
            }
            async function showDay(dateStr) {
                const el = document.getElementById('calDetail');
                el.innerHTML = '<div class="d-empty">加载中...</div>';
                try {
                    const res = await fetch(`${API_TASKS}/worklog/day?date=${dateStr}`, {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    const d = await res.json();
                    let items = '';
                    (d.done_tasks || []).forEach(t => {
                        items += '<div class="d-item"><span class="d-dot" style="background:var(--success)"></span><span class="d-name">' + escapeHtml(t.title) + '</span><span class="d-time">✓ 完成</span></div>';
                    });
                    (d.created_tasks || []).forEach(t => {
                        items += '<div class="d-item"><span class="d-dot" style="background:var(--primary)"></span><span class="d-name">' + escapeHtml(t.title) + '</span><span class="d-time">＋ 创建</span></div>';
                    });
                    if (!items) items = '<div class="d-empty">当日无工作记录</div>';
                    el.innerHTML = '<div class="d-head">' + dateStr + ' · 工作明细</div>' + items;
                } catch (e) {
                    el.innerHTML = '<div class="d-empty">加载失败</div>';
                }
            }
            function calShift(delta) {
                calMonth += delta;
                if (calMonth < 0) { calMonth = 11; calYear--; }
                if (calMonth > 11) { calMonth = 0; calYear++; }
                renderMonth();
            }
            function switchCalView(v) {
                document.getElementById('calMonth').style.display = v === 'month' ? '' : 'none';
                document.getElementById('calYear').style.display = v === 'year' ? '' : 'none';
                if (v === 'year') renderYear();
            }
            async function renderYear() {
                const year = calYear;
                const datas = await Promise.all(Array.from({ length: 12 }, (_, m) =>
                    fetch(`${API_TASKS}/worklog?year=${year}&month=${m + 1}`, { headers: { 'Authorization': `Bearer ${token}` } }).then(r => r.json())
                ));
                const now = new Date();
                let html = '';
                for (let m = 0; m < 12; m++) {
                    const done = datas[m].done_by_day || {};
                    const firstDow = new Date(year, m, 1).getDay();
                    const dim = new Date(year, m + 1, 0).getDate();
                    let cells = '';
                    for (let i = 0; i < firstDow; i++) cells += '<div class="mc-cell" style="background:transparent"></div>';
                    for (let d = 1; d <= dim; d++) {
                        const key = year + '-' + pad2(m + 1) + '-' + pad2(d);
                        const dn = done[key] || 0;
                        const isToday = year === now.getFullYear() && m === now.getMonth() && d === now.getDate();
                        cells += '<div class="mc-cell' + (dn ? ' has' : '') + (isToday ? ' today' : '') + '">' + d + '</div>';
                    }
                    html += '<div class="mini-cal"><div class="mc-title">' + (m + 1) + '月</div><div class="mc-grid">' + cells + '</div></div>';
                }
                document.getElementById('yearGrid').innerHTML = html;
            }

            // ── SSE 提醒 ──────────────────────────────────
            // 注意：后端 /tasks/events 依赖 Authorization 头鉴权，原生 EventSource 无法携带自定义头，
            // 故用 fetch 流式读取 SSE（与 send() 一致），而不是 brief 里的 new EventSource(?token=)。
            async function initTaskEvents() {
                try {
                    const res = await fetch(API_TASKS + '/events', {
                        headers: { 'Authorization': 'Bearer ' + token }
                    });
                    if (!res.ok || !res.body) return;
                    const reader = res.body.getReader();
                    const decoder = new TextDecoder();
                    let buf = '';
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        buf += decoder.decode(value, { stream: true });
                        let idx;
                        while ((idx = buf.indexOf('\\n\\n')) !== -1) {
                            const raw = buf.slice(0, idx);
                            buf = buf.slice(idx + 2);
                            const dataLine = raw.split('\\n').find(l => l.indexOf('data:') === 0);
                            if (!dataLine) continue;
                            let ev;
                            try { ev = JSON.parse(dataLine.slice(5).trim()); } catch (e) { continue; }
                            if (ev.type === 'task_remind') showRemind(ev.message);
                        }
                    }
                } catch (e) {
                    console.error('SSE 提醒订阅失败', e);
                }
            }
            function showRemind(msg) {
                // 顶部「工作记录」旁角标
                const badge = document.getElementById('remindBadge');
                if (badge) badge.style.display = 'inline';
                // 右下角提醒气泡
                let el = document.getElementById('remindToast');
                if (!el) {
                    el = document.createElement('div');
                    el.id = 'remindToast';
                    el.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#fff;border:1px solid #e8e8e8;box-shadow:0 4px 16px rgba(0,0,0,.12);border-radius:8px;padding:12px 16px;font-size:13px;color:#333;max-width:320px;z-index:999;';
                    document.body.appendChild(el);
                }
                el.textContent = '⏰ ' + msg;
                el.style.display = 'block';
                clearTimeout(el._t);
                el._t = setTimeout(() => { el.style.display = 'none'; }, 5000);
            }

            // ── 初始化 ────────────────────────────────────
            (function init() {
                // 恢复上次活跃会话
                const saved = localStorage.getItem('activeSessionId');
                if (saved) {
                    activeSessionId = saved;
                    openSession(saved);
                }
                loadSessionList();
                // 任务面板 + 日历 + SSE 提醒
                loadTasks();
                renderMonth();
                initTaskEvents();
            })();
        </script>
    </body>
    </html>
    """


@router.get("/favicon.ico")
async def favicon():
    """空 favicon，消除 404"""
    from fastapi.responses import Response
    return Response(status_code=204)


@router.get("/login", response_class=HTMLResponse)
async def login_page():
    """登录页面"""
    return """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>登录 - Agent-Zs</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f0f2f5; height: 100vh; display: flex; flex-direction: column; }
            .header { background: #1890ff; color: white; padding: 16px 24px; text-align: center; }
            .header h1 { font-size: 18px; font-weight: 500; }
            .login-container { flex: 1; display: flex; align-items: center; justify-content: center; }
            .login-card { background: white; border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,0.1); padding: 40px; width: 400px; max-width: 90vw; }
            .login-card h2 { text-align: center; color: #333; margin-bottom: 32px; font-size: 20px; font-weight: 500; }
            .form-group { margin-bottom: 20px; }
            .form-group label { display: block; margin-bottom: 6px; color: #666; font-size: 14px; }
            .form-group input { width: 100%; padding: 10px 12px; border: 1px solid #d9d9d9; border-radius: 6px; font-size: 14px; outline: none; transition: border-color 0.2s; }
            .form-group input:focus { border-color: #1890ff; box-shadow: 0 0 0 2px rgba(24,144,255,0.2); }
            .login-btn { width: 100%; padding: 12px; background: #1890ff; color: white; border: none; border-radius: 6px; font-size: 16px; cursor: pointer; transition: background 0.2s; }
            .login-btn:hover { background: #40a9ff; }
            .login-btn:disabled { background: #d9d9d9; cursor: not-allowed; }
            .error-msg { color: #ff4d4f; font-size: 13px; text-align: center; margin-top: 16px; display: none; }
            .error-msg.show { display: block; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Agent-Zs 企业智能助手</h1>
        </div>
        <div class="login-container">
            <div class="login-card">
                <h2>用户登录</h2>
                <form id="loginForm">
                    <div class="form-group">
                        <label>用户名</label>
                        <input type="text" id="username" placeholder="请输入用户名" autocomplete="username" autofocus>
                    </div>
                    <div class="form-group">
                        <label>密码</label>
                        <input type="password" id="password" placeholder="请输入密码" autocomplete="current-password">
                    </div>
                    <button type="submit" class="login-btn" id="loginBtn">登 录</button>
                </form>
                <div class="error-msg" id="errorMsg"></div>
            </div>
        </div>
        <script>
            // 已登录则直接跳转
            if (localStorage.getItem('token')) {
                window.location.href = '/';
            }

            const form = document.getElementById('loginForm');
            const usernameEl = document.getElementById('username');
            const passwordEl = document.getElementById('password');
            const loginBtn = document.getElementById('loginBtn');
            const errorMsg = document.getElementById('errorMsg');

            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const username = usernameEl.value.trim();
                const password = passwordEl.value.trim();

                if (!username || !password) {
                    showError('请输入用户名和密码');
                    return;
                }

                loginBtn.disabled = true;
                loginBtn.textContent = '登录中...';
                errorMsg.classList.remove('show');

                try {
                    const res = await fetch('/api/v1/auth/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username, password })
                    });
                    const data = await res.json();
                    if (res.ok && data.status === 'ok') {
                        localStorage.setItem('token', data.token);
                        localStorage.setItem('userName', data.user.real_name || data.user.username);
                        window.location.href = '/';
                    } else {
                        showError(data.message || '用户名或密码错误');
                    }
                } catch (err) {
                    showError('网络错误，请检查连接');
                } finally {
                    loginBtn.disabled = false;
                    loginBtn.textContent = '登 录';
                }
            });

            function showError(msg) {
                errorMsg.textContent = msg;
                errorMsg.classList.add('show');
            }
        </script>
    </body>
    </html>
    """
