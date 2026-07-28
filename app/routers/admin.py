"""管理端点 - API Key 配置"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class APIKeyConfig(BaseModel):
    """API Key 配置"""
    provider: str = "deepseek"
    api_key: str
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"


class APIKeyResponse(BaseModel):
    """API Key 响应（隐藏敏感信息）"""
    provider: str
    model: str
    base_url: str
    api_key_masked: str


# 临时存储（生产环境应使用数据库或配置文件）
_api_config = {
    "provider": "deepseek",
    "api_key": "",
    "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com",
}


@router.get("/admin/config", response_model=APIKeyResponse)
async def get_config():
    """获取当前配置（隐藏 API Key）"""
    api_key = _api_config.get("api_key", "")
    masked = api_key[:8] + "****" + api_key[-4:] if len(api_key) > 12 else "****"

    return APIKeyResponse(
        provider=_api_config["provider"],
        model=_api_config["model"],
        base_url=_api_config["base_url"],
        api_key_masked=masked,
    )


@router.post("/admin/config")
async def update_config(config: APIKeyConfig):
    """更新配置"""
    global _api_config

    # 验证 API Key 格式
    if not config.api_key or len(config.api_key) < 10:
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": "API Key 格式无效", "error_code": "INVALID_CONFIG"},
        )

    # 更新配置
    _api_config = {
        "provider": config.provider,
        "api_key": config.api_key,
        "model": config.model,
        "base_url": config.base_url,
    }

    # 更新全局设置
    settings.llm_provider = config.provider
    settings.llm_api_key = config.api_key
    settings.llm_model = config.model
    settings.llm_base_url = config.base_url

    logger.info(f"配置已更新: provider={config.provider}, model={config.model}")

    return {"status": "ok", "message": "配置已更新"}


@router.get("/admin")
async def admin_page():
    """管理页面 HTML"""
    html = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Agent-Zs 管理页面</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; padding: 20px; }
            .container { max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #333; margin-bottom: 20px; font-size: 24px; }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 8px; font-weight: 500; color: #555; }
            input, select { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
            input:focus, select:focus { outline: none; border-color: #4a90d9; box-shadow: 0 0 0 2px rgba(74,144,217,0.2); }
            button { background: #4a90d9; color: white; border: none; padding: 14px 28px; border-radius: 6px; cursor: pointer; font-size: 16px; width: 100%; }
            button:hover { background: #357abd; }
            .message { padding: 12px; border-radius: 6px; margin-bottom: 20px; display: none; }
            .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
            .current-config { background: #f8f9fa; padding: 15px; border-radius: 6px; margin-bottom: 20px; }
            .current-config p { margin: 5px 0; color: #666; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔧 Agent-Zs 管理页面</h1>

            <div id="message" class="message"></div>

            <div class="current-config">
                <h3>当前配置</h3>
                <p><strong>服务商:</strong> <span id="current-provider">-</span></p>
                <p><strong>模型:</strong> <span id="current-model">-</span></p>
                <p><strong>API Key:</strong> <span id="current-key">-</span></p>
            </div>

            <form id="config-form">
                <div class="form-group">
                    <label for="provider">LLM 服务商</label>
                    <select id="provider" name="provider">
                        <option value="deepseek">DeepSeek</option>
                        <option value="openai">OpenAI</option>
                        <option value="anthropic">Anthropic (Claude)</option>
                    </select>
                </div>

                <div class="form-group">
                    <label for="api_key">API Key</label>
                    <input type="password" id="api_key" name="api_key" placeholder="输入你的 API Key" required>
                </div>

                <div class="form-group">
                    <label for="model">模型名称</label>
                    <input type="text" id="model" name="model" placeholder="deepseek-chat">
                </div>

                <div class="form-group">
                    <label for="base_url">API 地址</label>
                    <input type="text" id="base_url" name="base_url" placeholder="https://api.deepseek.com">
                </div>

                <button type="submit">保存配置</button>
            </form>
        </div>

        <script>
            // 加载当前配置
            async function loadConfig() {
                try {
                    const response = await fetch('/api/v1/admin/config');
                    const data = await response.json();
                    document.getElementById('current-provider').textContent = data.provider;
                    document.getElementById('current-model').textContent = data.model;
                    document.getElementById('current-key').textContent = data.api_key_masked;
                    document.getElementById('provider').value = data.provider;
                    document.getElementById('model').value = data.model;
                    document.getElementById('base_url').value = data.base_url;
                } catch (e) {
                    console.error('加载配置失败:', e);
                }
            }

            // 保存配置
            document.getElementById('config-form').addEventListener('submit', async (e) => {
                e.preventDefault();

                const formData = {
                    provider: document.getElementById('provider').value,
                    api_key: document.getElementById('api_key').value,
                    model: document.getElementById('model').value,
                    base_url: document.getElementById('base_url').value,
                };

                try {
                    const response = await fetch('/api/v1/admin/config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(formData),
                    });

                    const data = await response.json();
                    const msgEl = document.getElementById('message');

                    if (response.ok) {
                        msgEl.className = 'message success';
                        msgEl.textContent = '✅ 配置已保存';
                        loadConfig();
                    } else {
                        msgEl.className = 'message error';
                        msgEl.textContent = '❌ ' + (data.detail?.message || '保存失败');
                    }
                    msgEl.style.display = 'block';
                    setTimeout(() => msgEl.style.display = 'none', 3000);
                } catch (e) {
                    console.error('保存失败:', e);
                }
            });

            // 页面加载时获取配置
            loadConfig();
        </script>
    </body>
    </html>
    """
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)
