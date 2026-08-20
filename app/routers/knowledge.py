"""知识库管理路由（多租户）

- router（prefix="/knowledge"，以 /api/v1 注册）：文档 / FAQ / 知识库 CRUD 管理接口
- page_router（无前缀，/admin/knowledge）：独立前端管理页

权限：所有管理接口 Depends(require_knowledge_admin)，tenant_id 一律取自 JWT，
绝不接受请求体传入 tenant_id。
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.config import settings
from app.gateway.auth import require_knowledge_admin
from app.services import knowledge_service

router = APIRouter(prefix="/knowledge", tags=["知识库管理"])
page_router = APIRouter(tags=["知识库管理页面"])

# ─────────────────────── 请求模型 ───────────────────────


class BaseCreate(BaseModel):
    name: str
    description: str = ""


class BaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class BaseStatus(BaseModel):
    status: str


class DocCreate(BaseModel):
    title: str
    content: str
    category: str = ""
    tags: str = ""


class DocUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None


class StatusBody(BaseModel):
    status: str


class FaqCreate(BaseModel):
    question: str
    answer: str
    category: str = ""
    aliases: Optional[list[str]] = None


class FaqUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    aliases: Optional[list[str]] = None


class SearchBody(BaseModel):
    query: str
    kb_ids: Optional[list[int]] = None
    source_type: Optional[str] = None
    top_k: int = 5


# ─────────────────────── 知识库 ───────────────────────


@router.get("/bases")
async def list_bases(user_info: dict = Depends(require_knowledge_admin)):
    bases = await knowledge_service.list_bases(user_info["tenant_id"])
    return {"status": "ok", "bases": bases}


@router.post("/bases")
async def create_base(body: BaseCreate, user_info: dict = Depends(require_knowledge_admin)):
    try:
        result = await knowledge_service.create_base(
            user_info["tenant_id"], body.name, body.description, created_by=user_info.get("user_id")
        )
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bases/{kb_id}")
async def get_base(kb_id: int, user_info: dict = Depends(require_knowledge_admin)):
    base = await knowledge_service.get_base(user_info["tenant_id"], kb_id)
    if base is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"status": "ok", "base": base}


@router.put("/bases/{kb_id}")
async def update_base(kb_id: int, body: BaseUpdate, user_info: dict = Depends(require_knowledge_admin)):
    base = await knowledge_service.update_base(user_info["tenant_id"], kb_id, body.name, body.description)
    if base is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"status": "ok", "base": base}


@router.patch("/bases/{kb_id}/status")
async def set_base_status(kb_id: int, body: BaseStatus, user_info: dict = Depends(require_knowledge_admin)):
    try:
        ok = await knowledge_service.set_base_status(user_info["tenant_id"], kb_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"status": "ok", "message": "知识库状态已更新"}


@router.delete("/bases/{kb_id}")
async def delete_base(kb_id: int, user_info: dict = Depends(require_knowledge_admin)):
    ok = await knowledge_service.delete_base(user_info["tenant_id"], kb_id)
    if not ok:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"status": "ok", "message": "知识库已删除"}


# ─────────────────────── 文档 ───────────────────────


@router.get("/bases/{kb_id}/docs")
async def list_documents(kb_id: int, page: int = 1, page_size: int = 20,
                         status: Optional[str] = None, category: Optional[str] = None,
                         keyword: Optional[str] = None, user_info: dict = Depends(require_knowledge_admin)):
    result = await knowledge_service.list_documents(user_info["tenant_id"], kb_id, page, page_size, status, category, keyword)
    return {"status": "ok", **result}


@router.post("/bases/{kb_id}/docs")
async def create_document(kb_id: int, body: DocCreate, user_info: dict = Depends(require_knowledge_admin)):
    try:
        result = await knowledge_service.create_document(
            user_info["tenant_id"], kb_id, body.title, body.content,
            body.category, body.tags, source_type="text", created_by=user_info.get("user_id"),
        )
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bases/{kb_id}/docs/upload")
async def upload_document(kb_id: int, file: UploadFile = File(...),
                          category: str = Form(""), user_info: dict = Depends(require_knowledge_admin)):
    # 后缀白名单校验
    filename = os.path.basename(file.filename or "")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".txt", ".md"):
        raise HTTPException(status_code=400, detail="仅支持 .txt / .md 文件")
    # 大小校验
    max_bytes = settings.knowledge_max_upload_mb * 1024 * 1024
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="文件内容为空")
    if len(raw) > max_bytes:
        raise HTTPException(status_code=400, detail=f"文件大小超过 {settings.knowledge_max_upload_mb}MB 上限")
    content = raw.decode("utf-8", errors="ignore")
    # 标题取文件名（去后缀）
    title = os.path.splitext(filename)[0] or "未命名文档"
    try:
        result = await knowledge_service.create_document(
            user_info["tenant_id"], kb_id, title, content,
            category, "", source_type="upload", file_name=filename, created_by=user_info.get("user_id"),
        )
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bases/{kb_id}/docs/{doc_id}")
async def get_document(kb_id: int, doc_id: int, user_info: dict = Depends(require_knowledge_admin)):
    doc = await knowledge_service.get_document(user_info["tenant_id"], kb_id, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"status": "ok", "doc": doc}


@router.put("/bases/{kb_id}/docs/{doc_id}")
async def update_document(kb_id: int, doc_id: int, body: DocUpdate, user_info: dict = Depends(require_knowledge_admin)):
    doc = await knowledge_service.update_document(
        user_info["tenant_id"], kb_id, doc_id, body.title, body.content, body.category, body.tags
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"status": "ok", "doc": doc}


@router.patch("/bases/{kb_id}/docs/{doc_id}/status")
async def set_document_status(kb_id: int, doc_id: int, body: StatusBody, user_info: dict = Depends(require_knowledge_admin)):
    try:
        ok = await knowledge_service.set_document_status(user_info["tenant_id"], kb_id, doc_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"status": "ok", "message": "文档状态已更新"}


@router.post("/bases/{kb_id}/docs/{doc_id}/reindex")
async def reindex_document(kb_id: int, doc_id: int, user_info: dict = Depends(require_knowledge_admin)):
    ok = await knowledge_service.reindex_document(user_info["tenant_id"], kb_id, doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"status": "ok", "message": "文档已重新索引"}


@router.delete("/bases/{kb_id}/docs/{doc_id}")
async def delete_document(kb_id: int, doc_id: int, user_info: dict = Depends(require_knowledge_admin)):
    ok = await knowledge_service.delete_document(user_info["tenant_id"], kb_id, doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"status": "ok", "message": "文档已删除"}


# ─────────────────────── FAQ ───────────────────────


@router.get("/bases/{kb_id}/faqs")
async def list_faqs(kb_id: int, page: int = 1, page_size: int = 20,
                    status: Optional[str] = None, keyword: Optional[str] = None,
                    user_info: dict = Depends(require_knowledge_admin)):
    result = await knowledge_service.list_faqs(user_info["tenant_id"], kb_id, page, page_size, status, keyword)
    return {"status": "ok", **result}


@router.post("/bases/{kb_id}/faqs")
async def create_faq(kb_id: int, body: FaqCreate, user_info: dict = Depends(require_knowledge_admin)):
    try:
        result = await knowledge_service.create_faq(
            user_info["tenant_id"], kb_id, body.question, body.answer,
            body.category, body.aliases, created_by=user_info.get("user_id"),
        )
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bases/{kb_id}/faqs/{faq_id}")
async def get_faq(kb_id: int, faq_id: int, user_info: dict = Depends(require_knowledge_admin)):
    faq = await knowledge_service.get_faq(user_info["tenant_id"], kb_id, faq_id)
    if faq is None:
        raise HTTPException(status_code=404, detail="FAQ 不存在")
    return {"status": "ok", "faq": faq}


@router.put("/bases/{kb_id}/faqs/{faq_id}")
async def update_faq(kb_id: int, faq_id: int, body: FaqUpdate, user_info: dict = Depends(require_knowledge_admin)):
    faq = await knowledge_service.update_faq(
        user_info["tenant_id"], kb_id, faq_id, body.question, body.answer, body.category, body.aliases
    )
    if faq is None:
        raise HTTPException(status_code=404, detail="FAQ 不存在")
    return {"status": "ok", "faq": faq}


@router.patch("/bases/{kb_id}/faqs/{faq_id}/status")
async def set_faq_status(kb_id: int, faq_id: int, body: StatusBody, user_info: dict = Depends(require_knowledge_admin)):
    try:
        ok = await knowledge_service.set_faq_status(user_info["tenant_id"], kb_id, faq_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="FAQ 不存在")
    return {"status": "ok", "message": "FAQ 状态已更新"}


@router.post("/bases/{kb_id}/faqs/{faq_id}/reindex")
async def reindex_faq(kb_id: int, faq_id: int, user_info: dict = Depends(require_knowledge_admin)):
    ok = await knowledge_service.reindex_faq(user_info["tenant_id"], kb_id, faq_id)
    if not ok:
        raise HTTPException(status_code=404, detail="FAQ 不存在")
    return {"status": "ok", "message": "FAQ 已重新索引"}


@router.delete("/bases/{kb_id}/faqs/{faq_id}")
async def delete_faq(kb_id: int, faq_id: int, user_info: dict = Depends(require_knowledge_admin)):
    ok = await knowledge_service.delete_faq(user_info["tenant_id"], kb_id, faq_id)
    if not ok:
        raise HTTPException(status_code=404, detail="FAQ 不存在")
    return {"status": "ok", "message": "FAQ 已删除"}


# ─────────────────────── 分类 / 检索 ───────────────────────


@router.get("/bases/{kb_id}/categories")
async def list_categories(kb_id: int, user_info: dict = Depends(require_knowledge_admin)):
    cats = await knowledge_service.list_categories(user_info["tenant_id"], kb_id)
    return {"status": "ok", "categories": cats}


@router.post("/search")
async def search(body: SearchBody, user_info: dict = Depends(require_knowledge_admin)):
    result = await knowledge_service.search(
        body.query, user_info["tenant_id"], body.kb_ids, body.source_type, body.top_k
    )
    return result


# ─────────────────────── 前端管理页 ───────────────────────


@page_router.get("/admin/knowledge", response_class=HTMLResponse)
async def knowledge_page():
    return r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>知识库管理 - Agent-Zs</title>
    <style>
        :root {
            --brand: #1677ff; --brand-dark: #0958d9; --brand-light: #e6f4ff;
            --bg: #f5f6f8; --surface: #fff; --border: #e5e8ec;
            --text: #1f2329; --muted: #8f959e; --danger: #f53f3f; --success: #00b42a;
            --warning: #ff7d00; --radius: 8px;
            --shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 16px rgba(0,0,0,.06);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; background: var(--bg); color: var(--text); font-size: 14px; }
        .header { background: linear-gradient(135deg, #0b1e3d, #12315e 55%, #1677ff 140%); color: #fff; padding: 16px 28px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
        .header h1 { font-size: 17px; font-weight: 600; }
        .header a { color: #fff; text-decoration: none; font-size: 13px; opacity: .85; }
        .container { max-width: 1180px; margin: 20px auto; padding: 0 20px; }
        .toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
        .toolbar select { height: 36px; padding: 0 10px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); }
        .btn { height: 36px; padding: 0 16px; border: 0; border-radius: var(--radius); background: var(--brand); color: #fff; font-weight: 600; cursor: pointer; }
        .btn:hover { background: var(--brand-dark); }
        .btn.ghost { background: #fff; color: var(--text); border: 1px solid var(--border); }
        .btn.danger { background: var(--danger); }
        .btn.sm { height: 28px; padding: 0 10px; font-size: 12px; }
        .tabs { display: flex; gap: 6px; margin-bottom: 16px; border-bottom: 1px solid var(--border); }
        .tab { padding: 10px 20px; cursor: pointer; color: var(--muted); border-bottom: 2px solid transparent; font-weight: 500; }
        .tab.active { color: var(--brand); border-bottom-color: var(--brand); font-weight: 600; }
        .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 11px 14px; text-align: left; border-bottom: 1px solid var(--border); font-size: 13px; }
        th { background: #fafbfc; color: var(--muted); font-weight: 600; white-space: nowrap; }
        tr:last-child td { border-bottom: 0; }
        .tag { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; }
        .tag.active { color: var(--success); background: #e8ffea; }
        .tag.disabled { color: var(--muted); background: #f0f1f3; }
        .tag.indexed { color: var(--success); background: #e8ffea; }
        .tag.indexing { color: var(--brand); background: var(--brand-light); }
        .tag.pending { color: var(--warning); background: #fff3e6; }
        .tag.failed { color: var(--danger); background: #ffece8; }
        .actions { display: flex; gap: 6px; flex-wrap: wrap; }
        .empty { padding: 40px; text-align: center; color: var(--muted); }
        .modal-mask { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 200; align-items: center; justify-content: center; }
        .modal-mask.show { display: flex; }
        .modal { width: min(560px, calc(100vw - 32px)); background: #fff; border-radius: 12px; padding: 22px; max-height: 86vh; overflow-y: auto; }
        .modal h3 { margin-bottom: 16px; font-size: 16px; }
        .field { margin-bottom: 14px; }
        .field label { display: block; margin-bottom: 6px; color: var(--muted); font-size: 13px; }
        .field input, .field textarea { width: 100%; padding: 9px 11px; border: 1px solid var(--border); border-radius: var(--radius); font: inherit; outline: 0; }
        .field textarea { min-height: 90px; resize: vertical; }
        .field input:focus, .field textarea:focus { border-color: var(--brand); }
        .modal-footer { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
        .toast { position: fixed; right: 20px; bottom: 20px; z-index: 300; padding: 12px 16px; border-radius: 8px; background: #fff; border: 1px solid var(--border); box-shadow: var(--shadow); display: none; }
    </style>
</head>
<body>
    <div class="header">
        <h1>知识库管理</h1>
        <a href="/">返回聊天</a>
    </div>
    <div class="container">
        <div class="toolbar">
            <select id="kbSelect"><option value="">加载中...</option></select>
            <button class="btn ghost" onclick="openBaseModal()">新建知识库</button>
        </div>
        <div class="tabs">
            <div class="tab active" data-tab="docs" onclick="switchTab('docs')">文档管理</div>
            <div class="tab" data-tab="faqs" onclick="switchTab('faqs')">FAQ 管理</div>
            <div class="tab" data-tab="settings" onclick="switchTab('settings')">知识库设置</div>
        </div>
        <div id="tabDocs">
            <div class="card" id="docsPanel"></div>
        </div>
        <div id="tabFaqs" style="display:none">
            <div class="card" id="faqsPanel"></div>
        </div>
        <div id="tabSettings" style="display:none">
            <div class="card" id="settingsPanel"></div>
        </div>
    </div>

    <div class="modal-mask" id="modal">
        <div class="modal" id="modalBody"></div>
    </div>
    <div class="toast" id="toast"></div>

    <script>
        const token = localStorage.getItem('token');
        if (!token) window.location.href = '/login';
        const API = '/api/v1/knowledge';
        let currentTab = 'docs';
        let kbId = null;
        let bases = [];

        function authHeaders(extra) { return Object.assign({ Authorization: 'Bearer ' + token }, extra || {}); }
        function escapeHtml(v) { const d = document.createElement('div'); d.textContent = v == null ? '' : String(v); return d.innerHTML; }
        function toast(msg) { const t = document.getElementById('toast'); t.textContent = msg; t.style.display = 'block'; clearTimeout(t._t); t._t = setTimeout(() => t.style.display = 'none', 2500); }
        function statusTag(s) { return '<span class="tag ' + escapeHtml(s) + '">' + escapeHtml(s === 'active' ? '启用' : '停用') + '</span>'; }
        function indexTag(s) {
            const map = { pending: '待索引', indexing: '索引中', indexed: '已索引', failed: '失败', stale: '待更新' };
            return '<span class="tag ' + escapeHtml(s) + '">' + escapeHtml(map[s] || s) + '</span>';
        }

        async function api(path, options) {
            const res = await fetch(API + path, options ? Object.assign({ headers: authHeaders(options.headers) }, options) : { headers: authHeaders() });
            const data = await res.json().catch(() => ({}));
            if (res.status === 401) { localStorage.removeItem('token'); window.location.href = '/login'; throw new Error('登录已过期，请重新登录'); }
            if (res.status === 403) { alert('无知识库管理权限'); throw new Error('forbidden'); }
            if (!res.ok) {
                const msg = (data.detail && typeof data.detail === 'object') ? (data.detail.message || JSON.stringify(data.detail)) : (data.message || data.detail);
                throw new Error(msg || ('请求失败 ' + res.status));
            }
            return data;
        }

        function openModal(html) {
            document.getElementById('modalBody').innerHTML = html;
            document.getElementById('modal').classList.add('show');
        }
        function closeModal() { document.getElementById('modal').classList.remove('show'); }
        document.getElementById('modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });

        async function loadBases() {
            const data = await api('/bases');
            bases = data.bases || [];
            const sel = document.getElementById('kbSelect');
            if (!bases.length) { sel.innerHTML = '<option value="">暂无知识库，请新建</option>'; kbId = null; return; }
            sel.innerHTML = bases.map(b => '<option value="' + b.id + '">' + escapeHtml(b.name) + ' (' + b.doc_count + ' 文档 / ' + b.faq_count + ' FAQ)</option>').join('');
            if (!kbId) kbId = bases[0].id;
            sel.value = kbId;
        }
        document.getElementById('kbSelect').addEventListener('change', e => { kbId = Number(e.target.value) || null; refresh(); });

        function switchTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
            document.getElementById('tabDocs').style.display = tab === 'docs' ? '' : 'none';
            document.getElementById('tabFaqs').style.display = tab === 'faqs' ? '' : 'none';
            document.getElementById('tabSettings').style.display = tab === 'settings' ? '' : 'none';
            refresh();
        }

        function refresh() { if (!kbId) return; currentTab === 'docs' ? loadDocs() : currentTab === 'faqs' ? loadFaqs() : loadSettings(); }

        // ── 文档 ──
        async function loadDocs() {
            const data = await api('/bases/' + kbId + '/docs?page_size=100');
            const items = data.items || [];
            const panel = document.getElementById('docsPanel');
            if (!items.length) { panel.innerHTML = '<div class="empty">暂无文档</div>'; return; }
            let rows = items.map(d => '<tr><td>' + escapeHtml(d.title) + '</td><td>' + escapeHtml(d.category || '-') + '</td><td>' + escapeHtml(d.source_type === 'upload' ? '上传' : '文本') + '</td><td>' + statusTag(d.status) + '</td><td>' + indexTag(d.index_status) + '</td><td>' + escapeHtml((d.updated_at || '').slice(0, 16)) + '</td><td><div class="actions">' +
                '<button class="btn ghost sm" onclick="openDocModal(' + d.id + ')">编辑</button>' +
                '<button class="btn ghost sm" onclick="toggleDoc(' + d.id + ',\'' + d.status + '\')">' + (d.status === 'active' ? '停用' : '启用') + '</button>' +
                '<button class="btn ghost sm" onclick="reindexDoc(' + d.id + ')">重索引</button>' +
                '<button class="btn danger sm" onclick="deleteDoc(' + d.id + ')">删除</button>' +
                '</div></td></tr>').join('');
            panel.innerHTML = '<div style="padding:14px 16px;display:flex;justify-content:space-between"><strong>文档列表（' + items.length + '）</strong><button class="btn sm" onclick="openDocModal()">新增文档</button> <button class="btn sm ghost" onclick="openUploadModal()">上传文件</button></div><table><thead><tr><th>标题</th><th>分类</th><th>来源</th><th>状态</th><th>索引</th><th>更新时间</th><th>操作</th></tr></thead><tbody>' + rows + '</tbody></table>';
        }

        async function openDocModal(id) {
            let doc = null;
            if (id) { const data = await api('/bases/' + kbId + '/docs/' + id); doc = data.doc; }
            openModal(
                '<h3>' + (id ? '编辑文档' : '新增文档') + '</h3>' +
                '<div class="field"><label>标题</label><input id="fTitle" value="' + escapeHtml(doc ? doc.title : '') + '"></div>' +
                '<div class="field"><label>分类</label><input id="fCategory" value="' + escapeHtml(doc ? (doc.category || '') : '') + '"></div>' +
                '<div class="field"><label>标签（逗号分隔）</label><input id="fTags" value="' + escapeHtml(doc ? (doc.tags || '') : '') + '"></div>' +
                '<div class="field"><label>正文</label><textarea id="fContent" style="min-height:180px">' + escapeHtml(doc ? (doc.content || '') : '') + '</textarea></div>' +
                '<div class="modal-footer"><button class="btn ghost" onclick="closeModal()">取消</button><button class="btn" onclick="saveDoc(' + (id || 0) + ')">保存</button></div>'
            );
        }
        async function saveDoc(id) {
            const body = { title: document.getElementById('fTitle').value, category: document.getElementById('fCategory').value, tags: document.getElementById('fTags').value, content: document.getElementById('fContent').value };
            if (id) await api('/bases/' + kbId + '/docs/' + id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            else await api('/bases/' + kbId + '/docs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            closeModal(); toast('文档已保存'); loadDocs();
        }
        function openUploadModal() {
            openModal(
                '<h3>上传文档（.txt / .md）</h3>' +
                '<div class="field"><label>文件</label><input id="fFile" type="file" accept=".txt,.md"></div>' +
                '<div class="field"><label>分类</label><input id="fCategory" value=""></div>' +
                '<div class="modal-footer"><button class="btn ghost" onclick="closeModal()">取消</button><button class="btn" onclick="uploadDoc()">上传</button></div>'
            );
        }
        async function uploadDoc() {
            const file = document.getElementById('fFile').files[0];
            if (!file) return alert('请选择文件');
            const fd = new FormData();
            fd.append('file', file);
            fd.append('category', document.getElementById('fCategory').value);
            const res = await fetch(API + '/bases/' + kbId + '/docs/upload', { method: 'POST', headers: authHeaders(), body: fd });
            const data = await res.json().catch(() => ({}));
            if (res.status === 401) { localStorage.removeItem('token'); window.location.href = '/login'; return; }
            if (!res.ok) {
                const msg = (data.detail && typeof data.detail === 'object') ? (data.detail.message || '上传失败') : (data.message || data.detail || '上传失败');
                return alert(msg);
            }
            closeModal(); toast('文档已上传'); loadDocs();
        }
        async function toggleDoc(id, cur) {
            await api('/bases/' + kbId + '/docs/' + id + '/status', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: cur === 'active' ? 'disabled' : 'active' }) });
            toast('状态已更新'); loadDocs();
        }
        async function reindexDoc(id) { await api('/bases/' + kbId + '/docs/' + id + '/reindex', { method: 'POST' }); toast('已重新索引'); loadDocs(); }
        async function deleteDoc(id) { if (!confirm('确定删除该文档？')) return; await api('/bases/' + kbId + '/docs/' + id, { method: 'DELETE' }); toast('文档已删除'); loadDocs(); }

        // ── FAQ ──
        async function loadFaqs() {
            const data = await api('/bases/' + kbId + '/faqs?page_size=100');
            const items = data.items || [];
            const panel = document.getElementById('faqsPanel');
            if (!items.length) { panel.innerHTML = '<div class="empty">暂无 FAQ</div>'; return; }
            let rows = items.map(f => '<tr><td>' + escapeHtml(f.question) + '</td><td>' + escapeHtml((f.answer || '').slice(0, 40)) + '</td><td>' + escapeHtml(f.category || '-') + '</td><td>' + (f.alias_count || 0) + '</td><td>' + (f.hit_count || 0) + '</td><td>' + statusTag(f.status) + '</td><td>' + indexTag(f.index_status) + '</td><td><div class="actions">' +
                '<button class="btn ghost sm" onclick="openFaqModal(' + f.id + ')">编辑</button>' +
                '<button class="btn ghost sm" onclick="toggleFaq(' + f.id + ',\'' + f.status + '\')">' + (f.status === 'active' ? '停用' : '启用') + '</button>' +
                '<button class="btn danger sm" onclick="deleteFaq(' + f.id + ')">删除</button>' +
                '</div></td></tr>').join('');
            panel.innerHTML = '<div style="padding:14px 16px;display:flex;justify-content:space-between"><strong>FAQ 列表（' + items.length + '）</strong><button class="btn sm" onclick="openFaqModal()">新增 FAQ</button></div><table><thead><tr><th>标准问</th><th>答案</th><th>分类</th><th>别名</th><th>命中</th><th>状态</th><th>索引</th><th>操作</th></tr></thead><tbody>' + rows + '</tbody></table>';
        }

        async function openFaqModal(id) {
            let faq = null;
            if (id) { const data = await api('/bases/' + kbId + '/faqs/' + id); faq = data.faq; }
            const aliases = faq ? (faq.aliases || []).join(',') : '';
            openModal(
                '<h3>' + (id ? '编辑 FAQ' : '新增 FAQ') + '</h3>' +
                '<div class="field"><label>标准问</label><input id="fQuestion" value="' + escapeHtml(faq ? faq.question : '') + '"></div>' +
                '<div class="field"><label>答案</label><textarea id="fAnswer" style="min-height:120px">' + escapeHtml(faq ? faq.answer : '') + '</textarea></div>' +
                '<div class="field"><label>分类</label><input id="fCategory" value="' + escapeHtml(faq ? (faq.category || '') : '') + '"></div>' +
                '<div class="field"><label>别名（逗号分隔）</label><input id="fAliases" value="' + escapeHtml(aliases) + '"></div>' +
                '<div class="modal-footer"><button class="btn ghost" onclick="closeModal()">取消</button><button class="btn" onclick="saveFaq(' + (id || 0) + ')">保存</button></div>'
            );
        }
        async function saveFaq(id) {
            const aliases = document.getElementById('fAliases').value.split(',').map(s => s.trim()).filter(Boolean);
            const body = { question: document.getElementById('fQuestion').value, answer: document.getElementById('fAnswer').value, category: document.getElementById('fCategory').value, aliases: aliases };
            if (id) await api('/bases/' + kbId + '/faqs/' + id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            else await api('/bases/' + kbId + '/faqs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            closeModal(); toast('FAQ 已保存'); loadFaqs();
        }
        async function toggleFaq(id, cur) {
            await api('/bases/' + kbId + '/faqs/' + id + '/status', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: cur === 'active' ? 'disabled' : 'active' }) });
            toast('状态已更新'); loadFaqs();
        }
        async function deleteFaq(id) { if (!confirm('确定删除该 FAQ？')) return; await api('/bases/' + kbId + '/faqs/' + id, { method: 'DELETE' }); toast('FAQ 已删除'); loadFaqs(); }

        // ── 设置 ──
        async function loadSettings() {
            const data = await api('/bases/' + kbId);
            const b = data.base;
            const panel = document.getElementById('settingsPanel');
            panel.innerHTML = '<div style="padding:22px"><h3>' + escapeHtml(b.name) + '</h3>' +
                '<p style="color:var(--muted);margin:10px 0 20px">' + escapeHtml(b.description || '暂无描述') + '</p>' +
                '<p style="margin-bottom:6px">状态：' + statusTag(b.status) + '</p>' +
                '<p style="margin-bottom:20px">向量模型：' + escapeHtml(b.embedding_model) + '</p>' +
                '<div class="actions">' +
                '<button class="btn" onclick="openBaseEditModal()">编辑</button>' +
                '<button class="btn ghost" onclick="toggleBase(\'' + b.status + '\')">' + (b.status === 'active' ? '停用' : '启用') + '</button>' +
                '<button class="btn danger" onclick="deleteBase()">删除知识库</button>' +
                '</div></div>';
        }
        function openBaseModal() {
            document.getElementById('modalBody').innerHTML =
                '<h3>新建知识库</h3>' +
                '<div class="field"><label>名称</label><input id="fName"></div>' +
                '<div class="field"><label>描述</label><input id="fDesc"></div>' +
                '<div class="modal-footer"><button class="btn ghost" onclick="closeModal()">取消</button><button class="btn" onclick="createBase()">创建</button></div>';
            openModal(document.getElementById('modalBody').innerHTML);
        }
        function openBaseEditModal() {
            const b = bases.find(x => x.id === kbId);
            document.getElementById('modalBody').innerHTML =
                '<h3>编辑知识库</h3>' +
                '<div class="field"><label>名称</label><input id="fName" value="' + escapeHtml(b.name) + '"></div>' +
                '<div class="field"><label>描述</label><input id="fDesc" value="' + escapeHtml(b.description || '') + '"></div>' +
                '<div class="modal-footer"><button class="btn ghost" onclick="closeModal()">取消</button><button class="btn" onclick="saveBase()">保存</button></div>';
            openModal(document.getElementById('modalBody').innerHTML);
        }
        async function createBase() {
            await api('/bases', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: document.getElementById('fName').value, description: document.getElementById('fDesc').value }) });
            closeModal(); toast('知识库已创建'); await loadBases(); refresh();
        }
        async function saveBase() {
            await api('/bases/' + kbId, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: document.getElementById('fName').value, description: document.getElementById('fDesc').value }) });
            closeModal(); toast('已保存'); await loadBases(); loadSettings();
        }
        async function toggleBase(cur) {
            await api('/bases/' + kbId + '/status', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: cur === 'active' ? 'disabled' : 'active' }) });
            toast('状态已更新'); loadSettings();
        }
        async function deleteBase() {
            if (!confirm('确定删除该知识库及其全部文档/FAQ？此操作不可恢复。')) return;
            await api('/bases/' + kbId, { method: 'DELETE' });
            toast('知识库已删除'); kbId = null; await loadBases(); switchTab('docs');
        }

        (async function init() {
            try { await loadBases(); } catch (e) { document.getElementById('kbSelect').innerHTML = '<option value="">加载失败：' + escapeHtml(e.message) + '</option>'; }
            refresh();
        })();
    </script>
</body>
</html>
    """
