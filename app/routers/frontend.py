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
            .message .content { max-width: 75%; padding: 10px 14px; border-radius: 12px; font-size: 14px; line-height: 1.6; word-break: break-word; }
            .message.user .content { background: #1890ff; color: white; border-bottom-right-radius: 4px; }
            .message.assistant .content { background: #fff; color: #333; border-bottom-left-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }

            /* 旧消息加载时灰色背景 */
            .message.assistant.history .content { background: #fafafa; }

            .message .content pre { background: #1e1e1e; color: #d4d4d4; padding: 10px; border-radius: 6px; overflow-x: auto; font-size: 12px; margin-top: 6px; }
            .table-wrap { overflow-x: auto; max-width: 100%; }
            .message .content table { width: 100%; border-collapse: collapse; margin-top: 6px; min-width: 500px; font-size: 12px; }
            .message .content th, .message .content td { border: 1px solid #e8e8e8; padding: 6px 8px; text-align: left; white-space: nowrap; }
            .message .content th { background: #fafafa; font-weight: 500; }
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
        </div>

        <!-- 主区域 -->
        <div class="main">
            <div class="topbar">
                <h1>AI 智能助手</h1>
                <span class="user-info"><span id="userNameDisplay"></span> | <a onclick="logout()">退出</a></span>
            </div>
            <div class="chat-area">
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
                            addMessageEl(role, content, extraClass);
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
            function addMessageEl(role, content, extraClass) {
                const div = document.createElement('div');
                div.className = 'message ' + role + (extraClass ? ' ' + extraClass : '');
                const avatar = role === 'user' ? '我' : 'AI';
                div.innerHTML = '<div class="avatar">' + avatar + '</div><div class="content">' + content + '</div>';
                chatBox.appendChild(div);
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            function addMessage(role, content) {
                addMessageEl(role, content, '');
            }

            function formatAssistantContent(text) {
                // 尝试解析 JSON（数据表格）
                try {
                    const data = JSON.parse(text);
                    if (Array.isArray(data) && data.length > 0) {
                        return formatTable(data);
                    }
                } catch(e) {}
                return escapeHtml(text || '');
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
                if (!data.data || data.data.length === 0) {
                    return escapeHtml(data.message || '查询完成，无数据返回');
                }
                let html = formatTable(data.data);
                if (data.message) html += '<p style="color:#666;margin-top:6px;">' + escapeHtml(data.message) + '</p>';
                return html;
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

                addMessage('user', escapeHtml(q));
                input.value = '';
                input.disabled = true;
                sendBtn.disabled = true;
                typing.classList.add('show');

                try {
                    const res = await fetch(API_QUERY, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                        body: JSON.stringify({ question: q, session_id: activeSessionId, intent: intent })
                    });
                    const data = await res.json();
                    addMessage('assistant', formatResult(data));
                    // 刷新侧边栏列表
                    loadSessionList();
                } catch (e) {
                    addMessage('assistant', '<div class="error-msg">请求失败：' + escapeHtml(e.message) + '</div>');
                } finally {
                    typing.classList.remove('show');
                    input.disabled = false;
                    sendBtn.disabled = false;
                    input.focus();
                }
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
