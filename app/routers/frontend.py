"""前端页面路由"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index():
    """AI 助手主页"""
    return """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI 智能助手</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; height: 100vh; display: flex; flex-direction: column; }
            .header { background: #1890ff; color: white; padding: 16px 24px; display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
            .header h1 { font-size: 18px; font-weight: 500; }
            .header .status { font-size: 12px; opacity: 0.8; }
            .container { flex: 1; display: flex; flex-direction: column; max-width: 900px; margin: 0 auto; width: 100%; padding: 20px; overflow: hidden; }
            .chat-box { flex: 1; overflow-y: auto; background: white; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
            .message { margin-bottom: 16px; display: flex; gap: 12px; }
            .message.user { flex-direction: row-reverse; }
            .message .avatar { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; }
            .message.user .avatar { background: #1890ff; color: white; }
            .message.assistant .avatar { background: #52c41a; color: white; }
            .message .content { max-width: 70%; padding: 12px 16px; border-radius: 12px; font-size: 14px; line-height: 1.6; }
            .message.user .content { background: #1890ff; color: white; border-bottom-right-radius: 4px; }
            .message.assistant .content { background: #f0f0f0; color: #333; border-bottom-left-radius: 4px; }
            .message .content pre { background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 13px; margin-top: 8px; }
            /* 表格容器：只允许表格横向滚动 */
            .table-wrap { overflow-x: auto; max-width: 100%; }
            .message .content table { width: 100%; border-collapse: collapse; margin-top: 8px; min-width: 600px; }
            .message .content th, .message .content td { border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 13px; white-space: nowrap; }
            .message .content th { background: #fafafa; }
            .error-msg { color: #ff4d4f; background: #fff2f0; border: 1px solid #ffccc7; padding: 12px; border-radius: 8px; margin-top: 8px; }
            .quick-actions { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
            .quick-btn { background: white; border: 1px solid #d9d9d9; padding: 8px 16px; border-radius: 20px; cursor: pointer; font-size: 13px; transition: all 0.2s; }
            .quick-btn:hover { border-color: #1890ff; color: #1890ff; }
            .input-area { display: flex; gap: 12px; flex-shrink: 0; }
            .input-area input { flex: 1; padding: 12px 16px; border: 1px solid #d9d9d9; border-radius: 8px; font-size: 14px; outline: none; }
            .input-area input:focus { border-color: #1890ff; box-shadow: 0 0 0 2px rgba(24,144,255,0.2); }
            .input-area button { background: #1890ff; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 14px; }
            .input-area button:hover { background: #40a9ff; }
            .input-area button:disabled { background: #d9d9d9; cursor: not-allowed; }
            .typing { display: none; padding: 8px 16px; color: #999; font-size: 13px; }
            .typing.show { display: block; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>AI 智能助手</h1>
            <span class="status">Agent-Zs v1.0</span>
        </div>
        <div class="container">
            <div class="quick-actions">
                <button class="quick-btn" onclick="ask('查询所有仓库的库存')">查询库存</button>
                <button class="quick-btn" onclick="ask('统计本月销售额')">本月销售</button>
                <button class="quick-btn" onclick="ask('采购订单审批流程')">审批流程</button>
                <button class="quick-btn" onclick="ask('创建采购订单')">创建订单</button>
            </div>
            <div class="chat-box" id="chatBox"></div>
            <div class="typing" id="typing">AI 正在思考...</div>
            <div class="input-area">
                <input type="text" id="input" placeholder="输入你的问题..." onkeypress="if(event.key==='Enter')send()">
                <button id="sendBtn" onclick="send()">发送</button>
            </div>
        </div>
        <script>
            const API = '/api/v1/query';
            const chatBox = document.getElementById('chatBox');
            const input = document.getElementById('input');
            const typing = document.getElementById('typing');
            const sendBtn = document.getElementById('sendBtn');

            function addMessage(role, content) {
                const div = document.createElement('div');
                div.className = 'message ' + role;
                const avatar = role === 'user' ? '我' : 'AI';
                div.innerHTML = '<div class="avatar">' + avatar + '</div><div class="content">' + content + '</div>';
                chatBox.appendChild(div);
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            function formatResult(data) {
                // 错误处理：返回友好的错误信息
                if (data.status === 'error' || data.status === 'clarify') {
                    return '<div class="error-msg">' + (data.message || '抱歉，无法处理您的请求') + '</div>';
                }

                if (!data.data || data.data.length === 0) {
                    return data.message || '查询完成，无数据返回';
                }

                // 有数据时返回表格（表格区域可横向滚动）
                let html = '<div class="table-wrap"><table><tr>';
                const keys = Object.keys(data.data[0]);
                keys.forEach(k => html += '<th>' + k + '</th>');
                html += '</tr>';
                data.data.slice(0, 20).forEach(row => {
                    html += '<tr>';
                    keys.forEach(k => html += '<td>' + (row[k] !== null && row[k] !== undefined ? row[k] : '-') + '</td>');
                    html += '</tr>';
                });
                html += '</table></div>';
                if (data.data.length > 20) html += '<p style="color:#999;margin-top:8px">共 ' + data.data.length + ' 条数据</p>';
                if (data.message) html += '<p style="color:#666;margin-top:8px">' + data.message + '</p>';
                return html;
            }

            async function ask(question) {
                input.value = question;
                send();
            }

            async function send() {
                const q = input.value.trim();
                if (!q) return;

                addMessage('user', q);
                input.value = '';
                input.disabled = true;
                sendBtn.disabled = true;
                typing.classList.add('show');

                try {
                    const res = await fetch(API, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer test-token' },
                        body: JSON.stringify({ question: q })
                    });
                    const data = await res.json();
                    addMessage('assistant', formatResult(data));
                } catch (e) {
                    addMessage('assistant', '<div class="error-msg">请求失败：' + e.message + '</div>');
                } finally {
                    typing.classList.remove('show');
                    input.disabled = false;
                    sendBtn.disabled = false;
                    input.focus();
                }
            }

            addMessage('assistant', '你好！我是 AI 智能助手，可以帮你查询数据、创建单据、检索知识。请问有什么需要？');
        </script>
    </body>
    </html>
    """
