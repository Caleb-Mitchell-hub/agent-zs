"""Frontend page routes."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index():
    """Main AI assistant page."""
    return r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent-Zs</title>
    <style>
        :root {
            --bg: #f3f6fc;
            --panel: rgba(255, 255, 255, 0.88);
            --panel-strong: #fff;
            --text: #17223a;
            --muted: #6f7d96;
            --faint: #9aa7bd;
            --line: rgba(151, 166, 193, 0.28);
            --blue: #2f66f6;
            --blue-dark: #2352d1;
            --green: #1e9d64;
            --amber: #d8892d;
            --red: #d95b64;
            --drawer-width: 344px;
            --shadow: 0 24px 60px rgba(43, 64, 105, 0.14);
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            height: 100vh;
            overflow: hidden;
            color: var(--text);
            font-family: "Microsoft YaHei", "PingFang SC", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background:
                radial-gradient(circle at 75% 8%, rgba(230, 238, 255, .95), transparent 34%),
                linear-gradient(135deg, #fafdff 0%, var(--bg) 56%, #eaf1ff 100%);
        }
        button, input, select { font: inherit; }
        button { border: 0; cursor: pointer; }
        .sidebar {
            position: fixed;
            z-index: 30;
            inset: 18px auto 18px 18px;
            width: var(--drawer-width);
            min-width: 0;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            background: rgba(255, 255, 255, 0.88);
            border: 1px solid rgba(255, 255, 255, .86);
            border-radius: 24px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(22px);
            transition: transform .28s ease, opacity .2s ease;
        }
        .drawer-collapsed .sidebar { transform: translateX(calc(-100% - 30px)); opacity: 0; pointer-events: none; }
        .sidebar-header { padding: 20px 18px 16px; border-bottom: 1px solid var(--line); }
        .drawer-heading { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
        .brand-mark { width: 34px; height: 34px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 10px; color: #fff; background: linear-gradient(145deg, #2d6cff, #3f55d8); box-shadow: 0 9px 18px rgba(47, 102, 246, .22); }
        .brand-mark svg { width: 20px; height: 20px; }
        .drawer-name { min-width: 0; flex: 1; font-size: 16px; font-weight: 800; letter-spacing: -.02em; }
        .drawer-name small { display: block; margin-top: 2px; color: var(--muted); font-size: 11px; font-weight: 600; letter-spacing: .02em; }
        .drawer-toggle { width: 32px; height: 32px; }
        .new-chat-btn, .send-btn {
            color: #fff;
            background: linear-gradient(135deg, var(--blue), #4660e9);
            border-radius: 12px;
            font-weight: 700;
            box-shadow: 0 12px 24px rgba(37, 99, 235, 0.18);
        }
        .new-chat-btn { width: 100%; display: flex; align-items: center; justify-content: center; gap: 8px; padding: 12px 14px; }
        .new-chat-btn svg { width: 16px; height: 16px; }
        .search, .task-input, .composer-input {
            width: 100%;
            color: var(--text);
            background: rgba(255,255,255,0.84);
            border: 1px solid var(--line);
            border-radius: 8px;
            outline: 0;
        }
        .search { margin: 14px 16px 8px; width: calc(100% - 32px); padding: 10px 12px; font-size: 12px; border-radius: 12px; }
        .search:focus, .task-input:focus, .composer-input:focus { border-color: rgba(37,99,235,.45); box-shadow: 0 0 0 3px rgba(37,99,235,.10); }
        .session-list { flex: 1 1 46%; overflow-y: auto; padding: 4px 10px 14px; min-height: 0; }
        .session-group-head, .task-group-head { padding: 10px 10px 6px; color: var(--faint); font-size: 11px; letter-spacing: 0; }
        .session-group-head { cursor: pointer; user-select: none; display: flex; align-items: center; gap: 5px; }
        .session-group-head:hover { color: var(--muted); }
        .session-group-head .caret { display: inline-block; width: 11px; color: var(--muted); transition: transform .15s ease; }
        .session-group.collapsed .session-item { display: none; }
        .session-group.collapsed .caret { transform: rotate(-90deg); }
        .session-item {
            display: flex;
            gap: 10px;
            align-items: center;
            margin: 0 2px 6px;
            padding: 12px 10px;
            border-radius: 12px;
            border: 1px solid transparent;
        }
        .session-item:hover { background: rgba(255,255,255,.85); border-color: var(--line); }
        .session-item.active { background: rgba(37,99,235,.08); border-color: rgba(37,99,235,.20); }
        .session-info { min-width: 0; flex: 1; }
        .session-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; font-weight: 650; }
        .session-meta { margin-top: 3px; color: var(--faint); font-size: 11px; }
        .icon-btn { width: 30px; height: 30px; display: grid; place-items: center; color: var(--muted); background: transparent; border-radius: 9px; }
        .icon-btn svg { width: 17px; height: 17px; }
        .icon-btn:hover { color: var(--blue); background: rgba(37,99,235,.08); }
        .danger:hover { color: var(--red); background: rgba(220,38,38,.08); }
        .empty { padding: 34px 12px; text-align: center; color: var(--faint); font-size: 13px; }
        .task-panel { flex: 1 1 54%; min-height: 0; display: flex; flex-direction: column; border-top: 1px solid var(--line); }
        .task-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 18px 8px; font-size: 13px; font-weight: 800; }
        .task-tabs { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; padding: 0 16px 9px; }
        .task-tab { padding: 7px 0; color: var(--muted); background: rgba(255,255,255,.75); border: 1px solid var(--line); border-radius: 9px; font-size: 12px; }
        .task-tab.active { color: var(--blue); background: rgba(37,99,235,.08); border-color: rgba(37,99,235,.24); font-weight: 700; }
        .task-add { display: flex; gap: 6px; padding: 0 16px 8px; }
        .task-input { padding: 9px 10px; font-size: 12px; }
        .task-add-btn { width: 38px; border-radius: 10px; color: #fff; background: var(--blue); font-weight: 800; }
        .task-list { overflow-y: auto; padding: 0 10px 14px; }
        .task-item { display: flex; align-items: center; gap: 9px; padding: 10px; border-radius: 10px; font-size: 12px; }
        .task-item:hover { background: rgba(255,255,255,.8); }
        .dot { width: 8px; height: 8px; border-radius: 50%; flex: 0 0 auto; }
        .pending { background: var(--blue); }
        .doing { background: var(--amber); }
        .done { background: var(--green); }
        .overdue { background: var(--red); }
        .main { width: 100%; height: 100vh; min-width: 0; min-height: 0; display: flex; flex-direction: column; }
        .topbar {
            height: 72px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 34px 0 390px;
            background: rgba(255,255,255,.42);
            border-bottom: 1px solid var(--line);
            backdrop-filter: blur(16px);
            transition: padding-left .28s ease;
        }
        .drawer-collapsed .topbar { padding-left: 18px; }
        .drawer-open-btn { display: none; width: 36px; height: 36px; color: var(--blue); background: rgba(47,102,246,.08); border-radius: 11px; }
        .drawer-collapsed .drawer-open-btn { display: grid; place-items: center; }
        .drawer-open-btn svg { width: 18px; height: 18px; }
        .nav { display: flex; align-items: center; gap: 12px; color: var(--muted); font-size: 13px; }
        .nav a { color: var(--blue); text-decoration: none; font-weight: 650; cursor: pointer; }
        .embedded-mode #userNameDisplay, .embedded-mode #logoutBtn { display: none; }
        .badge { display: none; margin-left: 4px; padding: 1px 6px; border-radius: 999px; color: #fff; background: var(--red); font-size: 10px; }
        .chat-area, .calendar-area { flex: 1; min-height: 0; overflow: hidden; }
        .chat-area { display: flex; flex-direction: column; max-width: 1280px; width: 100%; margin: 0 auto; padding: 24px 30px 28px; }
        .drawer-open .chat-area, .drawer-open .calendar-area { max-width: none; width: auto; margin-left: calc(var(--drawer-width) + 120px); margin-right: 34px; }
        .quick-actions { display: none; }
        .quick-btn { padding: 8px 13px; color: var(--muted); background: rgba(255,255,255,.82); border: 1px solid var(--line); border-radius: 999px; font-size: 12px; }
        .quick-btn:hover { color: var(--blue); border-color: rgba(37,99,235,.25); }
        .chat-box { flex: 1; min-height: 0; overflow-y: auto; padding: 16px 4px 26px 0; }
        .welcome { padding: 78px 20px; text-align: center; color: var(--muted); }
        .welcome h2 { margin: 0 0 10px; font-size: 24px; color: var(--text); }
        .message { display: flex; gap: 14px; align-items: flex-start; margin: 0 0 30px; }
        .message.user { flex-direction: row-reverse; }
        .avatar { width: 38px; height: 38px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 50%; color: #fff; font-size: 12px; font-weight: 800; }
        .user .avatar { background: linear-gradient(135deg, var(--blue), #4660e9); }
        .assistant .avatar { color: var(--blue); background: rgba(255,255,255,.82); border: 1px solid rgba(47,102,246,.18); }
        .msg-body { max-width: min(860px, 84%); display: flex; flex-direction: column; min-width: 0; }
        .user .msg-body { align-items: flex-end; }
        .content { padding: 15px 18px; border-radius: 18px; line-height: 1.78; font-size: 14px; overflow-wrap: anywhere; }
        .user .content { color: var(--text); background: rgba(229, 237, 255, .92); border: 1px solid rgba(47,102,246,.08); }
        .assistant .content { padding: 1px 4px; background: transparent; border: 0; box-shadow: none; }
        .content p { margin: 0 0 .78em; }
        .content p:last-child { margin-bottom: 0; }
        .content h1, .content h2, .content h3 { margin: .95em 0 .5em; line-height: 1.35; }
        .content h1 { font-size: 1.28em; }
        .content h2 { font-size: 1.16em; }
        .content h3 { font-size: 1.05em; }
        .content ul, .content ol { margin: .5em 0 .9em; padding-left: 1.35em; }
        .content blockquote { margin: .8em 0; padding: .15em 0 .15em 12px; border-left: 3px solid rgba(37,99,235,.38); color: var(--muted); background: rgba(37,99,235,.04); }
        .content code:not(pre code) { padding: .12em .36em; border-radius: 6px; background: rgba(15,23,42,.07); }
        .content pre { margin: .85em 0 0; padding: 14px; overflow-x: auto; border-radius: 8px; color: #e5e7eb; background: #111827; }
        .table-wrap { margin-top: .7em; overflow-x: auto; }
        table { width: 100%; min-width: 520px; border-collapse: collapse; font-size: 12.5px; }
        th, td { padding: 8px 10px; border: 1px solid var(--line); text-align: left; white-space: nowrap; }
        th { background: rgba(37,99,235,.06); }
        .message-meta { display: flex; align-items: center; gap: 5px; min-height: 28px; margin-top: 7px; color: var(--faint); font-size: 11px; }
        .user .message-meta { justify-content: flex-end; }
        .message-action { width: 28px; height: 28px; display: grid; place-items: center; color: var(--faint); background: transparent; border-radius: 8px; }
        .message-action svg { width: 16px; height: 16px; }
        .message-action:hover, .message-action.selected { color: var(--blue); background: rgba(47,102,246,.08); }
        .message-time { padding: 0 5px; }
        .typing { display: none; flex: 0 0 auto; align-items: center; gap: 9px; width: fit-content; margin: 0 0 14px 52px; padding: 9px 13px; border-radius: 999px; color: var(--muted); background: rgba(255,255,255,.84); border: 1px solid var(--line); font-size: 12.5px; }
        .typing.show { display: inline-flex; }
        .typing-dots { display: inline-flex; gap: 4px; }
        .typing-dots span { width: 6px; height: 6px; border-radius: 50%; background: var(--blue); animation: pulse 1.2s infinite ease-in-out; }
        .typing-dots span:nth-child(2) { animation-delay: .15s; }
        .typing-dots span:nth-child(3) { animation-delay: .3s; }
        @keyframes pulse { 0%, 80%, 100% { opacity: .32; transform: translateY(0); } 40% { opacity: 1; transform: translateY(-3px); } }
        .composer { display: flex; flex: 0 0 auto; gap: 10px; align-items: center; padding: 9px 10px 9px 14px; background: rgba(255,255,255,.86); border: 1px solid rgba(151,166,193,.32); border-radius: 20px; box-shadow: 0 14px 34px rgba(43,64,105,.08); }
        .composer-input { flex: 1; padding: 10px 5px; background: transparent; border: 0; }
        .composer-input:focus { border: 0; box-shadow: none; }
        .send-btn { width: 42px; height: 42px; display: grid; place-items: center; padding: 0; border-radius: 13px; }
        .send-btn svg { width: 19px; height: 19px; }
        .send-btn:disabled { background: #cbd5e1; box-shadow: none; cursor: not-allowed; }
        .error-msg { color: #b91c1c; background: #fef2f2; border: 1px solid #fecaca; padding: 10px 12px; border-radius: 8px; }
        .calendar-area { overflow-y: auto; padding: 18px 22px; }
        .cal-wrap { max-width: 930px; margin: 0 auto; }
        .cal-nav { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
        .cal-title { min-width: 120px; text-align: center; font-weight: 750; }
        .nav-btn, .cal-nav select { height: 32px; border: 1px solid var(--line); background: #fff; border-radius: 8px; }
        .nav-btn { width: 32px; color: var(--muted); }
        .stat-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
        .stat-card { background: var(--panel-strong); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }
        .stat-card .num { font-size: 24px; font-weight: 850; }
        .stat-card .lbl { margin-top: 4px; color: var(--muted); font-size: 12px; }
        .cal, .cal-detail, .mini-cal { background: var(--panel-strong); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
        .cal-weekhead, .cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); }
        .cal-weekhead { color: var(--muted); background: #f8fafc; border-bottom: 1px solid var(--line); font-size: 12px; }
        .cal-weekhead span { padding: 9px 0; text-align: center; }
        .cal-cell { min-height: 78px; padding: 7px 8px; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); cursor: pointer; }
        .cal-cell:nth-child(7n) { border-right: 0; }
        .cal-cell.other { background: #f8fafc; }
        .day-num { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; color: var(--muted); font-size: 12px; }
        .today .day-num { color: #fff; background: var(--blue); }
        .cell-stats { display: flex; gap: 10px; margin-top: 8px; font-size: 11px; }
        .c-done { color: var(--green); font-weight: 800; }
        .c-created { color: var(--blue); }
        .cal-detail { margin-top: 16px; padding: 15px 16px; }
        .d-head { margin-bottom: 8px; font-size: 13px; font-weight: 750; }
        .d-item { display: flex; align-items: center; gap: 10px; padding: 7px 0; border-bottom: 1px dashed var(--line); font-size: 12px; }
        .d-item:last-child { border-bottom: 0; }
        .d-dot { width: 7px; height: 7px; border-radius: 50%; }
        .d-name { flex: 1; min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
        .d-time, .d-empty { color: var(--faint); font-size: 12px; }
        .year-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
        .mini-cal { padding: 10px; }
        .mc-title { margin-bottom: 8px; text-align: center; font-size: 12px; font-weight: 750; }
        .mc-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; }
        .mc-cell { aspect-ratio: 1; display: grid; place-items: center; border-radius: 4px; background: #edf2f7; color: var(--faint); font-size: 9px; }
        .mc-cell.has { color: var(--blue-dark); background: #dbeafe; font-weight: 800; }
        .mc-cell.today { color: #fff; background: var(--blue); }
        .toast { position: fixed; right: 20px; bottom: 20px; z-index: 50; display: none; max-width: 340px; padding: 12px 14px; border-radius: 12px; background: #fff; border: 1px solid var(--line); box-shadow: var(--shadow); color: var(--text); font-size: 13px; }
        @media (max-width: 760px) {
            .sidebar { inset: 12px; width: auto; border-radius: 22px; }
            .topbar, .drawer-collapsed .topbar { padding: 0 16px; }
            .nav #userNameDisplay, .nav #logoutBtn { display: none; }
            .nav { gap: 9px; }
            .chat-area, .drawer-open .chat-area, .drawer-open .calendar-area { max-width: 100%; width: 100%; margin: 0; padding: 14px; }
            .msg-body { max-width: 86%; }
            .stat-cards, .year-grid { grid-template-columns: repeat(2, 1fr); }
        }
        /* The accepted concept uses an open editorial workspace instead of a card drawer. */
        :root {
            --bg: #fff;
            --panel: #fff;
            --panel-strong: #fff;
            --text: #17243b;
            --muted: #718096;
            --faint: #8795aa;
            --line: #e7ebf0;
            --line-strong: #d6dee8;
            --blue: #2f6bff;
            --blue-dark: #1f4fd2;
            --green: #20a99a;
            --amber: #e5a13d;
            --red: #f47d72;
            --drawer-width: 292px;
            --shadow: none;
        }
        body { background: #fff; }
        .sidebar {
            inset: 0 auto 0 0;
            width: var(--drawer-width);
            padding: 0;
            background: #fff;
            border: 0;
            border-right: 1px solid var(--line-strong);
            border-radius: 0;
            box-shadow: none;
            backdrop-filter: none;
        }
        .drawer-collapsed .sidebar { transform: translateX(-100%); opacity: 0; }
        .sidebar-header { padding: 28px 32px 18px; border-bottom: 0; }
        .drawer-heading { flex-direction: column; align-items: flex-start; gap: 22px; margin-bottom: 0; }
        .brand-mark { display: none; }
        .drawer-name { font-size: 20px; font-weight: 750; letter-spacing: -.04em; }
        .drawer-name small { display: none; }
        .drawer-toggle { width: 24px; height: 24px; }
        .drawer-toggle svg { width: 26px; height: 26px; }
        .new-chat-btn, #sessionSearch, #taskTabs, #taskSearch, .task-add { display: none; }
        .drawer-title-row { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
        .new-chat-btn { width: 30px; height: 30px; display: grid; place-items: center; flex: 0 0 auto; padding: 0; color: var(--blue); background: rgba(47,107,255,.07); border: 1px solid rgba(47,107,255,.2); border-radius: 50%; box-shadow: none; }
        .new-chat-btn:hover, .new-chat-btn:focus-visible { color: #fff; background: var(--blue); border-color: var(--blue); outline: 0; }
        .new-chat-btn svg { width: 16px; height: 16px; }
        .new-chat-btn span { display: none; }
        .search, .task-input { background: transparent; border: 0; border-bottom: 1px solid var(--line-strong); border-radius: 0; }
        .search { margin: 0 32px 12px; width: calc(100% - 64px); padding: 10px 0; }
        .search:focus, .task-input:focus { border-color: var(--blue); box-shadow: none; }
        .session-list { flex: 1 1 60%; padding: 4px 32px 16px; }
        .session-group-head { padding: 14px 0 8px; color: var(--faint); border-bottom: 1px solid var(--line); font-size: 12px; }
        .session-group-head .caret { width: 12px; }
        .session-item { margin: 0; padding: 14px 0 14px 12px; border: 0; border-left: 3px solid transparent; border-radius: 0; gap: 12px; align-items: baseline; }
        .session-item:hover { background: transparent; border-right: 0; border-top: 0; border-bottom: 0; }
        .session-item.active { background: transparent; border-color: transparent; border-left-color: var(--blue); }
        .session-title { font-size: 14px; font-weight: 650; }
        .session-meta { margin-top: 5px; color: var(--faint); font-size: 11px; }
        .icon-btn { border-radius: 0; }
        .task-panel { flex: 1 1 40%; padding: 20px 32px 24px; border-top: 1px solid var(--line-strong); }
        .task-head { padding: 0 0 12px; font-size: 20px; letter-spacing: -.03em; }
        .task-list { padding: 0; }
        .task-group-head { padding: 14px 0 7px; color: var(--faint); font-size: 11px; }
        .task-item { padding: 8px 0; border-radius: 0; font-size: 13px; }
        .dot { width: 7px; height: 7px; }
        .pending { background: var(--blue); }
        .doing { background: var(--amber); }
        .done { background: var(--green); }
        .overdue { background: var(--red); }
        .main { background: transparent; }
        .topbar { height: 72px; justify-content: flex-end; padding: 0 36px; background: #fff; border-bottom: 1px solid var(--line); backdrop-filter: none; }
        .drawer-open .topbar { padding-left: calc(var(--drawer-width) + 36px); }
        .drawer-collapsed .topbar { padding-left: 18px; }
        .drawer-open-btn { width: 34px; height: 34px; color: var(--blue); background: transparent; border-radius: 0; }
        .nav { gap: 24px; color: var(--text); font-size: 13px; }
        .nav a { color: var(--text); font-weight: 650; }
        .nav a:hover, .nav a:focus { color: var(--blue); }
        .chat-area { max-width: none; width: 100%; margin: 0; padding: 28px 34px 24px; background: #fff; }
        .drawer-open .chat-area, .drawer-open .calendar-area { max-width: none; width: auto; margin-left: calc(var(--drawer-width) + 120px); margin-right: 34px; }
        .chat-box { width: 100%; max-width: 760px; margin: 0; padding: 20px 0 42px; }
        .welcome { padding: 96px 20px; text-align: left; }
        .welcome h2 { font-size: 22px; font-weight: 650; }
        .message { gap: 18px; margin-bottom: 48px; }
        .avatar { width: 58px; height: auto; min-height: 24px; border-radius: 0; color: var(--text); background: transparent; font-size: 13px; font-weight: 700; justify-items: start; }
        .user .avatar, .assistant .avatar { color: var(--text); background: transparent; border: 0; }
        .msg-body { max-width: 760px; }
        .content { padding: 0; border-radius: 0; line-height: 1.85; font-size: 15px; }
        .user .content { color: var(--text); background: transparent; border: 0; }
        .assistant .content { padding: 24px 0 0; border-top: 2px solid var(--blue); }
        .message-meta { margin-top: 12px; color: var(--faint); }
        .message-action:hover, .message-action.selected { color: var(--blue); background: transparent; }
        .typing { max-width: 760px; width: 100%; margin: 0 0 18px; padding: 0 0 8px; border: 0; border-radius: 0; color: var(--muted); background: transparent; }
        .composer { max-width: 760px; width: 100%; margin: 0; gap: 12px; padding: 12px 0 0; background: #fff; border: 0; border-top: 1px solid var(--line-strong); border-radius: 0; box-shadow: none; }
        .composer-input { padding: 8px 0; font-size: 16px; background: transparent; border: 0; }
        .composer-input:focus { border: 0; box-shadow: none; }
        .attach-btn, .send-btn { width: 34px; height: 34px; display: grid; place-items: center; flex: 0 0 auto; padding: 0; color: var(--blue); background: transparent; border: 0; border-radius: 0; box-shadow: none; }
        .attach-btn { color: var(--muted); }
        .attach-btn:hover, .attach-btn.selected { color: var(--blue); }
        .attach-btn svg { width: 19px; height: 19px; }
        .send-btn svg { width: 20px; height: 20px; }
        .send-btn:disabled { color: var(--faint); background: transparent; box-shadow: none; }
        .attachment-status { max-width: 760px; width: 100%; margin: 0 0 8px; display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 12px; }
        .attachment-status[hidden] { display: none; }
        .attachment-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .attachment-clear { width: 20px; height: 20px; color: var(--faint); background: transparent; font-size: 18px; line-height: 1; }
        .attachment-clear:hover { color: var(--red); }
        /* A collapsed drawer gives the chat workspace the full viewport width. */
        .drawer-collapsed .chat-area, .drawer-collapsed .calendar-area { max-width: none; width: 100%; margin: 0; }
        .drawer-collapsed .chat-box,
        .drawer-collapsed .typing,
        .drawer-collapsed .composer,
        .drawer-collapsed .attachment-status { max-width: none; }
        .drawer-collapsed .msg-body { max-width: none; flex: 1; }
        @media (max-width: 760px) {
            .sidebar { inset: 0 auto 0 0; width: min(var(--drawer-width), calc(100vw - 28px)); border-radius: 0; }
            .sidebar-header { padding: 24px 26px 18px; }
            .search { margin-left: 26px; margin-right: 26px; width: calc(100% - 52px); }
            .session-list, .task-panel { padding-left: 26px; padding-right: 26px; }
            .topbar, .drawer-open .topbar, .drawer-collapsed .topbar { padding: 0 18px; }
            .nav { gap: 12px; }
            .nav #userNameDisplay, .nav #logoutBtn { display: none; }
            .chat-area, .drawer-open .chat-area, .drawer-open .calendar-area { width: 100%; margin: 0; padding: 22px 18px 22px; }
            .chat-box, .typing, .composer, .attachment-status { max-width: 100%; }
            .message { gap: 10px; margin-bottom: 34px; }
            .avatar { width: 38px; }
            .content { font-size: 14px; }
            .assistant .content { padding-top: 16px; }
        }
    </style>
</head>
<body class="drawer-open">
    <aside class="sidebar" id="sidebar" aria-label="&#23545;&#35805;&#19982;&#20219;&#21153;&#21015;&#34920;">
        <div class="sidebar-header">
            <div class="drawer-heading">
                <button class="icon-btn drawer-toggle" id="drawerToggle" type="button" aria-label="&#25910;&#36215;&#20391;&#36793;&#26639;" title="&#25910;&#36215;&#20391;&#36793;&#26639;"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg></button>
                <div class="drawer-title-row">
                    <div class="drawer-name">&#23545;&#35805;</div>
                    <button class="new-chat-btn" id="newChatBtn" type="button" aria-label="&#26032;&#24314;&#23545;&#35805;" title="&#26032;&#24314;&#23545;&#35805;"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg><span>&#26032;&#23545;&#35805;</span></button>
                </div>
            </div>
        </div>
        <input class="search" id="sessionSearch" type="text" placeholder="&#25628;&#32034;&#23545;&#35805;...">
        <span id="sessionCount" hidden></span>
        <div class="session-list" id="sessionList"><div class="empty">&#21152;&#36733;&#20013;...</div></div>
        <section class="task-panel">
            <div class="task-head"><span>&#20219;&#21153; <span id="taskCount"></span></span><button class="icon-btn" id="taskToggle" title="toggle">&#9662;</button></div>
            <div class="task-tabs" id="taskTabs">
                <button class="task-tab active" data-filter="all">&#20840;&#37096;</button>
                <button class="task-tab" data-filter="done">&#24050;&#23436;&#25104;</button>
                <button class="task-tab" data-filter="pending">&#24453;&#21150;</button>
                <button class="task-tab" data-filter="doing">&#22788;&#29702;&#20013;</button>
            </div>
            <input class="search" id="taskSearch" type="text" placeholder="&#25628;&#32034;&#20219;&#21153;...">
            <div class="task-add">
                <input class="task-input" id="taskAddInput" type="text" placeholder="&#26032;&#22686;&#20219;&#21153;&#65292;&#22238;&#36710;&#30830;&#35748;...">
                <button class="task-add-btn" id="taskAddBtn">+</button>
            </div>
            <div class="task-list" id="taskList"></div>
        </section>
    </aside>
    <main class="main">
        <header class="topbar">
            <button class="drawer-open-btn" id="drawerRailBtn" type="button" aria-label="&#23637;&#24320;&#20391;&#36793;&#26639;" title="&#23637;&#24320;&#20391;&#36793;&#26639;"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg></button>
            <nav class="nav">
                <a id="chatNav">&#32842;&#22825;</a>
                <a id="calendarNav">&#24037;&#20316;&#35760;&#24405;<span class="badge" id="remindBadge">&#25552;&#37266;</span></a>
                <span id="userNameDisplay"></span>
                <a id="logoutBtn">&#36864;&#20986;</a>
            </nav>
        </header>
        <section class="chat-area" id="chatArea">
            <div class="quick-actions">
                <button class="quick-btn" data-intent="query" data-q="&#26597;&#35810;&#25152;&#26377;&#20179;&#24211;&#30340;&#24211;&#23384;">&#26597;&#35810;&#24211;&#23384;</button>
                <button class="quick-btn" data-intent="query" data-q="&#32479;&#35745;&#26412;&#26376;&#38144;&#21806;&#39069;">&#26412;&#26376;&#38144;&#21806;</button>
                <button class="quick-btn" data-intent="knowledge" data-q="&#37319;&#36141;&#35746;&#21333;&#23457;&#25209;&#27969;&#31243;">&#23457;&#25209;&#27969;&#31243;</button>
                <button class="quick-btn" data-intent="create" data-q="&#21019;&#24314;&#37319;&#36141;&#35746;&#21333;">&#21019;&#24314;&#35746;&#21333;</button>
            </div>
            <div class="chat-box" id="chatBox">
                <div class="welcome"><h2>&#27426;&#36814;&#20351;&#29992; Agent-Zs</h2><p>&#36755;&#20837;&#38382;&#39064;&#25110;&#36873;&#25321;&#24038;&#20391;&#21382;&#21490;&#23545;&#35805;&#24320;&#22987;&#12290;</p></div>
            </div>
            <div class="typing" id="typing"><span class="typing-dots"><span></span><span></span><span></span></span><span id="typingLabel">AI &#27491;&#22312;&#29983;&#25104;</span></div>
            <div class="attachment-status" id="attachmentStatus" hidden><span class="attachment-name" id="attachmentName"></span><button class="attachment-clear" id="attachmentClear" type="button" aria-label="&#31227;&#38500;&#38468;&#20214;" title="&#31227;&#38500;&#38468;&#20214;">&times;</button></div>
            <div class="composer">
                <input class="composer-input" id="input" type="text" placeholder="&#36755;&#20837;&#20320;&#30340;&#38382;&#39064;...">
                <input id="fileInput" type="file" hidden>
                <button class="attach-btn" id="attachBtn" type="button" aria-label="&#19978;&#20256;&#25991;&#20214;" title="&#19978;&#20256;&#25991;&#20214;"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21.4 11.6-8.9 8.9a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.4-8.4"/></svg></button>
                <button class="send-btn" id="sendBtn" aria-label="&#21457;&#36865;" title="&#21457;&#36865;"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m4 4 16 8-16 8 3.5-8L4 4Z"/><path d="M7.5 12H20"/></svg></button>
            </div>
        </section>
        <section class="calendar-area" id="calPanel" style="display:none">
            <div class="cal-wrap">
                <div class="cal-nav">
                    <button class="nav-btn" id="calPrev">&#8249;</button>
                    <span class="cal-title" id="calTitle"></span>
                    <button class="nav-btn" id="calNext">&#8250;</button>
                    <select id="calView">
                        <option value="month">&#26376;&#35270;&#22270;</option>
                        <option value="year">&#24180;&#35270;&#22270;</option>
                    </select>
                </div>
                <div class="stat-cards">
                    <div class="stat-card"><div class="num" id="kDone">0</div><div class="lbl">&#26412;&#26376;&#23436;&#25104;</div></div>
                    <div class="stat-card"><div class="num" id="kCreated">0</div><div class="lbl">&#26412;&#26376;&#21019;&#24314;</div></div>
                    <div class="stat-card"><div class="num" id="kActive">0</div><div class="lbl">&#27963;&#36291;&#22825;&#25968;</div></div>
                    <div class="stat-card"><div class="num" id="kRate">&#8212;</div><div class="lbl">&#23436;&#25104;&#29575;</div></div>
                </div>
                <div id="calMonth">
                    <div class="cal">
                        <div class="cal-weekhead"><span>&#26085;</span><span>&#19968;</span><span>&#20108;</span><span>&#19977;</span><span>&#22235;</span><span>&#20116;</span><span>&#20845;</span></div>
                        <div class="cal-grid" id="calGrid"></div>
                    </div>
                    <div class="cal-detail" id="calDetail"></div>
                </div>
                <div id="calYear" style="display:none"><div class="year-grid" id="yearGrid"></div></div>
            </div>
        </section>
    </main>
    <div class="toast" id="remindToast"></div>
    <script>
        const params = new URLSearchParams(window.location.search);
        const incomingToken = params.get('token');
        const incomingApiBase = params.get('api_base');

        function resolveAppBase() {
            return window.location.pathname.startsWith('/agent-ai') ? '/agent-ai/' : '/';
        }

        function resolveApiBase() {
            if (incomingApiBase) return incomingApiBase.replace(/\/$/, '');
            if (window.location.pathname.startsWith('/agent-ai')) return '/agent-ai-api';
            return '/api/v1';
        }

        const APP_BASE = resolveAppBase();
        document.documentElement.classList.toggle('embedded-mode', window.self !== window.top || window.location.pathname.startsWith('/agent-ai'));
        const API_BASE = resolveApiBase();
        const LOGIN_PATH = `${APP_BASE}login`;

        if (incomingToken) {
            localStorage.setItem('agent_zs_token', incomingToken);
            params.delete('token');
            const cleanQuery = params.toString();
            history.replaceState({}, document.title, window.location.pathname + (cleanQuery ? `?${cleanQuery}` : ''));
        }

        let token = localStorage.getItem('agent_zs_token');
        if (!token) window.location.href = LOGIN_PATH;

        window.addEventListener('message', event => {
            if (event.origin !== window.location.origin) return;
            if (!event.data || event.data.type !== 'ERP_AGENT_ZS_SSO_TOKEN' || !event.data.token) return;
            localStorage.setItem('agent_zs_token', event.data.token);
            token = event.data.token;
        });

        const API_QUERY_STREAM = `${API_BASE}/query/stream`;
        const API_SESSIONS = `${API_BASE}/sessions`;
        const API_TASKS = `${API_BASE}/tasks`;
        let activeSessionId = localStorage.getItem('activeSessionId') || '';
        let taskFilter = 'all';
        let currentTasks = [];
        let calYear = new Date().getFullYear();
        let calMonth = new Date().getMonth();

        const chatBox = document.getElementById('chatBox');
        const input = document.getElementById('input');
        const typing = document.getElementById('typing');
        const typingLabel = document.getElementById('typingLabel');
        const sendBtn = document.getElementById('sendBtn');
        const attachBtn = document.getElementById('attachBtn');
        const fileInput = document.getElementById('fileInput');
        const attachmentStatus = document.getElementById('attachmentStatus');
        const attachmentName = document.getElementById('attachmentName');
        const attachmentClear = document.getElementById('attachmentClear');
        const sessionList = document.getElementById('sessionList');
        let selectedFile = null;

        function t(s) { return s; }
        const text = {
            unnamed: '\u672a\u547d\u540d\u7528\u6237',
            newChat: '\u65b0\u5bf9\u8bdd',
            noSessions: '\u6682\u65e0\u5bf9\u8bdd',
            noMatch: '\u6ca1\u6709\u5339\u914d\u7684\u5bf9\u8bdd',
            loading: '\u52a0\u8f7d\u4e2d...',
            noTasks: '\u6682\u65e0\u4efb\u52a1',
            deleteConfirm: '\u786e\u5b9a\u8981\u5220\u9664\u8fd9\u6761\u5bf9\u8bdd\u5417\uff1f',
            requestFailed: '\u8bf7\u6c42\u5931\u8d25\uff1a',
            noResult: '\u672a\u6536\u5230\u67e5\u8be2\u7ed3\u679c',
            thinking: 'AI \u6b63\u5728\u751f\u6210',
            searching: '\u6b63\u5728\u68c0\u7d22\u8d44\u6599',
            reasoning: '\u6b63\u5728\u6574\u7406\u601d\u8def',
            answering: '\u6b63\u5728\u751f\u6210\u56de\u7b54',
            checking: '\u6b63\u5728\u6821\u9a8c\u7ed3\u679c'
        };

        function escapeHtml(value) {
            const div = document.createElement('div');
            div.textContent = value == null ? '' : String(value);
            return div.innerHTML;
        }
        function svgIcon(name) {
            const paths = {
                copy: '<rect x="9" y="9" width="10" height="10" rx="2"></rect><path d="M6 15H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1"></path>',
                up: '<path d="M7 10v10M7 10 11 3a2 2 0 0 1 3.7 1.4L14 8h5a2 2 0 0 1 2 2l-1 7a3 3 0 0 1-3 3H7"></path><path d="M3 10h4v10H3z"></path>',
                down: '<path d="M7 14V4M7 14 11 21a2 2 0 0 0 3.7-1.4L14 16h5a2 2 0 0 0 2-2l-1-7a3 3 0 0 0-3-3H7"></path><path d="M3 14h4V4H3z"></path>'
            };
            return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (paths[name] || '') + '</svg>';
        }
        function formatMessageTime(value) {
            const date = value ? new Date(value) : new Date();
            if (Number.isNaN(date.getTime())) return '刚刚';
            const now = new Date();
            const sameDay = date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
            const time = pad2(date.getHours()) + ':' + pad2(date.getMinutes());
            if (sameDay) return '今天 ' + time;
            return pad2(date.getMonth() + 1) + '月' + pad2(date.getDate()) + '日 ' + time;
        }
        function generateSessionId() {
            return 'web-' + Date.now() + '-' + Math.random().toString(36).slice(2, 11);
        }
        const LOCAL_SESSION_CACHE_KEY = 'agent_zs_conversation_cache_v1';
        function readConversationCache() {
            try {
                const raw = localStorage.getItem(LOCAL_SESSION_CACHE_KEY);
                const cache = raw ? JSON.parse(raw) : {};
                return cache && typeof cache === 'object' ? cache : {};
            } catch (e) {
                return {};
            }
        }
        function writeConversationCache(cache) {
            try { localStorage.setItem(LOCAL_SESSION_CACHE_KEY, JSON.stringify(cache)); } catch (e) {}
        }
        function cacheConversationMessage(sessionId, role, content, createdAt) {
            if (!sessionId || !content) return;
            const cache = readConversationCache();
            const messages = Array.isArray(cache[sessionId]) ? cache[sessionId] : [];
            messages.push({ role: role, content: String(content), created_at: createdAt || new Date().toISOString() });
            cache[sessionId] = messages.slice(-200);
            writeConversationCache(cache);
        }
        function loadCachedConversation(sessionId) {
            const cache = readConversationCache();
            return Array.isArray(cache[sessionId]) ? cache[sessionId] : [];
        }
        function replaceCachedConversation(sessionId, messages) {
            if (!sessionId || !Array.isArray(messages) || !messages.length) return;
            const cache = readConversationCache();
            cache[sessionId] = messages.slice(-200).map(message => ({
                role: message.role === 'user' ? 'user' : 'assistant',
                content: String(message.content == null ? '' : message.content),
                created_at: message.created_at || message.createdAt || message.timestamp || new Date().toISOString()
            }));
            writeConversationCache(cache);
        }
        function removeCachedConversation(sessionId) {
            const cache = readConversationCache();
            if (!Object.prototype.hasOwnProperty.call(cache, sessionId)) return;
            delete cache[sessionId];
            writeConversationCache(cache);
        }
        function mergeCachedSessions(sessions) {
            const serverSessions = Array.isArray(sessions) ? sessions : [];
            const serverIds = new Set(serverSessions.map(session => session.session_id));
            const localOnly = Object.entries(readConversationCache())
                .filter(([sessionId, messages]) => !serverIds.has(sessionId) && Array.isArray(messages) && messages.length)
                .map(([sessionId, messages]) => {
                    const firstUserMessage = messages.find(message => message.role === 'user');
                    const lastMessage = messages[messages.length - 1];
                    return {
                        session_id: sessionId,
                        title: (firstUserMessage && firstUserMessage.content || text.newChat).slice(0, 50),
                        last_active_at: lastMessage && lastMessage.created_at || null,
                        message_count: messages.length,
                        _localOnly: true
                    };
                });
            return serverSessions.concat(localOnly).sort((a, b) => {
                return new Date(b.last_active_at || 0).getTime() - new Date(a.last_active_at || 0).getTime();
            });
        }
        function getUserDisplayName() {
            try {
                const encoded = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
                const binary = atob(encoded + '='.repeat((4 - encoded.length % 4) % 4));
                const bytes = Uint8Array.from(binary, ch => ch.charCodeAt(0));
                const payload = JSON.parse(new TextDecoder('utf-8').decode(bytes));
                return payload.real_name || payload.username || text.unnamed;
            } catch (e) {
                return text.unnamed;
            }
        }
        document.getElementById('userNameDisplay').textContent = getUserDisplayName();

        function authHeaders(extra) {
            return Object.assign({ Authorization: 'Bearer ' + token }, extra || {});
        }
        function setThinking(message) {
            typingLabel.textContent = message || text.thinking;
            typing.classList.add('show');
        }
        function hideThinking() {
            typing.classList.remove('show');
            typingLabel.textContent = text.thinking;
        }
        function normalizeThinking(message) {
            const raw = String(message || '');
            if (/\u68c0\u7d22|\u641c\u7d22|\u67e5\u8be2|\u8bfb\u53d6/.test(raw)) return text.searching;
            if (/\u5206\u6790|\u6574\u7406|\u601d\u8003|\u63a8\u7406/.test(raw)) return text.reasoning;
            if (/\u56de\u7b54|\u751f\u6210|\u64b0\u5199|\u8f93\u51fa/.test(raw)) return text.answering;
            if (/\u6821\u9a8c|\u786e\u8ba4|\u6838\u5bf9/.test(raw)) return text.checking;
            return text.thinking;
        }

        function renderInlineMarkdown(value) {
            const code = [];
            let html = escapeHtml(value).replace(/`([^`]+)`/g, (_, v) => {
                code.push(v);
                return '@@CODE' + (code.length - 1) + '@@';
            });
            html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
            html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            html = html.replace(/@@CODE(\d+)@@/g, (_, i) => '<code>' + code[Number(i)] + '</code>');
            return html;
        }
        function formatMarkdown(value) {
            const lines = String(value || '').replace(/\r\n/g, '\n').split('\n');
            const blocks = [];
            let paragraph = [];
            let listType = '';
            let listItems = [];
            let inCode = false;
            let codeLang = '';
            let codeLines = [];
            const flushParagraph = () => {
                if (!paragraph.length) return;
                blocks.push('<p>' + paragraph.join('<br>') + '</p>');
                paragraph = [];
            };
            const flushList = () => {
                if (!listItems.length) return;
                blocks.push('<' + listType + '>' + listItems.join('') + '</' + listType + '>');
                listItems = [];
                listType = '';
            };
            const flushCode = () => {
                blocks.push('<pre data-lang="' + escapeHtml(codeLang) + '"><code>' + escapeHtml(codeLines.join('\n')) + '</code></pre>');
                codeLang = '';
                codeLines = [];
            };
            for (let i = 0; i < lines.length; i++) {
                const raw = lines[i];
                const line = raw.trim();
                if (inCode) {
                    if (/^```/.test(line)) { flushCode(); inCode = false; } else { codeLines.push(raw); }
                    continue;
                }
                if (/^```/.test(line)) { flushParagraph(); flushList(); inCode = true; codeLang = line.slice(3).trim(); continue; }
                if (!line) { flushParagraph(); flushList(); continue; }
                if (/^#{1,6}\s+/.test(line)) {
                    flushParagraph(); flushList();
                    const level = Math.min(3, line.match(/^#{1,6}/)[0].length);
                    blocks.push('<h' + level + '>' + renderInlineMarkdown(line.replace(/^#{1,6}\s+/, '')) + '</h' + level + '>');
                    continue;
                }
                if (/^>\s?/.test(line)) { flushParagraph(); flushList(); blocks.push('<blockquote>' + renderInlineMarkdown(line.replace(/^>\s?/, '')) + '</blockquote>'); continue; }
                if (/^[-*+]\s+/.test(line)) {
                    flushParagraph(); if (listType && listType !== 'ul') flushList();
                    listType = 'ul'; listItems.push('<li>' + renderInlineMarkdown(line.replace(/^[-*+]\s+/, '')) + '</li>'); continue;
                }
                if (/^\d+\.\s+/.test(line)) {
                    flushParagraph(); if (listType && listType !== 'ol') flushList();
                    listType = 'ol'; listItems.push('<li>' + renderInlineMarkdown(line.replace(/^\d+\.\s+/, '')) + '</li>'); continue;
                }
                const next = lines[i + 1] || '';
                if (/\|/.test(line) && /^\s*\|?[\s:-]+\|[\s|:-]*$/.test(next)) {
                    flushParagraph(); flushList();
                    const headers = line.replace(/^\|/, '').replace(/\|$/, '').split('|').map(x => x.trim());
                    let table = '<div class="table-wrap"><table><thead><tr>' + headers.map(h => '<th>' + renderInlineMarkdown(h) + '</th>').join('') + '</tr></thead><tbody>';
                    i += 2;
                    while (i < lines.length && /\|/.test(lines[i])) {
                        const row = lines[i].trim();
                        if (!row) break;
                        const cells = row.replace(/^\|/, '').replace(/\|$/, '').split('|').map(x => x.trim());
                        table += '<tr>' + headers.map((_, idx) => '<td>' + renderInlineMarkdown(cells[idx] || '') + '</td>').join('') + '</tr>';
                        i++;
                    }
                    i--;
                    blocks.push(table + '</tbody></table></div>');
                    continue;
                }
                flushList();
                paragraph.push(renderInlineMarkdown(raw));
            }
            flushParagraph();
            flushList();
            if (inCode) flushCode();
            return blocks.join('\n');
        }
        function formatTable(rows) {
            if (!rows || !rows.length) return '\u65e0\u6570\u636e';
            const keys = Object.keys(rows[0]);
            let html = '<div class="table-wrap"><table><thead><tr>' + keys.map(k => '<th>' + escapeHtml(k) + '</th>').join('') + '</tr></thead><tbody>';
            rows.slice(0, 20).forEach(row => {
                html += '<tr>' + keys.map(k => '<td>' + escapeHtml(row[k] == null ? '-' : row[k]) + '</td>').join('') + '</tr>';
            });
            html += '</tbody></table></div>';
            if (rows.length > 20) html += '<p>\u5171 ' + rows.length + ' \u6761\uff0c\u4ec5\u663e\u793a\u524d 20 \u6761</p>';
            return html;
        }
        function assistantRawText(data) {
            if (!data) return '';
            if (data.status === 'error' || data.status === 'clarify') return data.message || '';
            if (data.preview === true) return formatTaskPlanRaw(data);
            if (!data.data || !data.data.length) return data.message || '';
            const keys = Object.keys(data.data[0] || {});
            let md = data.message ? data.message + '\n\n' : '';
            md += '| ' + keys.join(' | ') + ' |\n';
            md += '| ' + keys.map(() => '---').join(' | ') + ' |\n';
            data.data.forEach(row => {
                md += '| ' + keys.map(k => String(row[k] == null ? '' : row[k]).replace(/\n/g, ' ')).join(' | ') + ' |\n';
            });
            return md;
        }
        function formatResult(data) {
            if (data.preview === true) return formatTaskPlanPreview(data);
            if (data.status === 'error' || data.status === 'clarify') {
                return '<div class="error-msg">' + escapeHtml(data.message || '\u62b1\u6b49\uff0c\u65e0\u6cd5\u5904\u7406\u60a8\u7684\u8bf7\u6c42') + '</div>';
            }
            return formatMarkdown(assistantRawText(data));
        }
        function addMessageEl(role, content, extraClass, rawText, createdAt) {
            const div = document.createElement('div');
            div.className = 'message ' + role + (extraClass ? ' ' + extraClass : '');
            const actions = role === 'assistant'
                ? '<button class="message-action" type="button" data-feedback="up" aria-label="\u70b9\u8d5e" title="\u70b9\u8d5e">' + svgIcon('up') + '</button><button class="message-action" type="button" data-feedback="down" aria-label="\u8e29" title="\u8e29">' + svgIcon('down') + '</button>'
                : '';
            const copy = rawText ? '<button class="message-action copy-btn" type="button" aria-label="\u590d\u5236" title="\u590d\u5236">' + svgIcon('copy') + '</button>' : '';
            div.innerHTML = '<div class="avatar">' + (role === 'user' ? '\u6211' : 'AI') + '</div><div class="msg-body"><div class="content">' + content + '</div><div class="message-meta"><span class="message-time">' + escapeHtml(formatMessageTime(createdAt)) + '</span>' + actions + copy + '</div></div>';
            const btn = div.querySelector('.copy-btn');
            if (btn) {
                btn.dataset.text = rawText || '';
                btn.addEventListener('click', () => copyText(btn.dataset.text || ''));
            }
            const feedback = Array.from(div.querySelectorAll('[data-feedback]'));
            feedback.forEach(item => item.addEventListener('click', () => {
                feedback.forEach(other => other.classList.toggle('selected', other === item && !item.classList.contains('selected')));
            }));
            chatBox.appendChild(div);
            scrollChatToBottom();
            return div;
        }
        function scrollChatToBottom(behavior) {
            requestAnimationFrame(() => {
                chatBox.scrollTo({ top: chatBox.scrollHeight, behavior: behavior || 'auto' });
            });
        }
        function addMessage(role, content, extraClass, rawText) {
            return addMessageEl(role, content, extraClass || '', rawText);
        }
        async function copyText(value) {
            try {
                if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(value);
                else {
                    const ta = document.createElement('textarea');
                    ta.value = value; ta.style.position = 'fixed'; ta.style.opacity = '0';
                    document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
                }
            } catch (e) {}
        }
        function formatFileSize(bytes) {
            if (!bytes) return '0 B';
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        }
        function setSelectedFile(file) {
            selectedFile = file || null;
            if (!selectedFile) {
                attachmentName.textContent = '';
                attachmentStatus.hidden = true;
                attachBtn.classList.remove('selected');
                fileInput.value = '';
                attachBtn.title = '\u4e0a\u4f20\u6587\u4ef6';
                return;
            }
            attachmentName.textContent = selectedFile.name + ' · ' + formatFileSize(selectedFile.size);
            attachmentStatus.hidden = false;
            attachBtn.classList.add('selected');
            attachBtn.title = '\u5df2\u9009\u62e9\uff1a' + selectedFile.name;
        }
        function updateSessionCount(count) {
            const countEl = document.getElementById('sessionCount');
            if (countEl) countEl.textContent = count ? '(' + count + ')' : '';
        }

        async function loadSessionList() {
            try {
                const res = await fetch(API_SESSIONS, { headers: authHeaders() });
                if (!res.ok) throw new Error('sessions ' + res.status);
                const data = await res.json();
                let sessions = mergeCachedSessions(data.sessions || []);
                document.getElementById('sessionCount').textContent = sessions.length ? '(' + sessions.length + ')' : '';
                const kw = document.getElementById('sessionSearch').value.trim().toLowerCase();
                if (kw) sessions = sessions.filter(s => (s.title || text.newChat).toLowerCase().includes(kw));
                if (!sessions.length) { sessionList.innerHTML = '<div class="empty">' + (kw ? text.noMatch : text.noSessions) + '</div>'; return; }
                const todayStart = new Date(new Date().setHours(0,0,0,0)).getTime();
                const yesterdayStart = todayStart - 86400000;
                const groups = [{ name: '\u4eca\u5929', items: [] }, { name: '\u6628\u5929', items: [] }, { name: '\u66f4\u65e9', items: [] }];
                sessions.forEach(s => {
                    const ts = s.last_active_at ? new Date(s.last_active_at).getTime() : 0;
                    (ts >= todayStart ? groups[0] : ts >= yesterdayStart ? groups[1] : groups[2]).items.push(s);
                });
                sessionList.innerHTML = groups.filter(g => g.items.length).map(g => (
                    '<div class="session-group"><div class="session-group-head"><span class="caret">▾</span>' + g.name + ' <span>(' + g.items.length + ')</span></div>' +
                    g.items.map(s => {
                        const title = s.title || text.newChat;
                        const meta = (s.last_active_at ? new Date(s.last_active_at).toLocaleDateString('zh-CN') : '') + (s.message_count ? ' · ' + s.message_count + ' \u6761\u6d88\u606f' : '');
                        return '<div class="session-item' + (s.session_id === activeSessionId ? ' active' : '') + '" data-id="' + escapeHtml(s.session_id) + '"><div class="session-info"><div class="session-title">' + escapeHtml(title) + '</div><div class="session-meta">' + escapeHtml(meta) + '</div></div><button class="icon-btn danger" data-del="' + escapeHtml(s.session_id) + '" title="\u5220\u9664">×</button></div>';
                    }).join('') + '</div>'
                )).join('');
            } catch (e) {
                const sessions = mergeCachedSessions([]);
                document.getElementById('sessionCount').textContent = sessions.length ? '(' + sessions.length + ')' : '';
                const kw = document.getElementById('sessionSearch').value.trim().toLowerCase();
                const visible = kw ? sessions.filter(s => (s.title || text.newChat).toLowerCase().includes(kw)) : sessions;
                if (!visible.length) {
                    sessionList.innerHTML = '<div class="empty">' + (kw ? text.noMatch : text.noSessions) + '</div>';
                    return;
                }
                sessionList.innerHTML = visible.map(s => {
                    const title = s.title || text.newChat;
                    const meta = (s.last_active_at ? new Date(s.last_active_at).toLocaleDateString('zh-CN') : '') + (s.message_count ? ' · ' + s.message_count + ' \u6761\u6d88\u606f' : '');
                    return '<div class="session-item' + (s.session_id === activeSessionId ? ' active' : '') + '" data-id="' + escapeHtml(s.session_id) + '"><div class="session-info"><div class="session-title">' + escapeHtml(title) + '</div><div class="session-meta">' + escapeHtml(meta) + '</div></div><button class="icon-btn danger" data-del="' + escapeHtml(s.session_id) + '" title="\u5220\u9664">×</button></div>';
                }).join('');
            }
        }
        async function openSession(sessionId) {
            if (!sessionId) return;
            activeSessionId = sessionId;
            localStorage.setItem('activeSessionId', sessionId);
            chatBox.innerHTML = '<div class="empty">' + text.loading + '</div>';
            const cachedMessages = loadCachedConversation(sessionId);
            try {
                const res = await fetch(API_SESSIONS + '/' + encodeURIComponent(sessionId) + '/messages', { headers: authHeaders() });
                if (!res.ok) throw new Error('messages ' + res.status);
                const data = await res.json();
                const serverMessages = data.messages || [];
                const msgs = serverMessages.length ? serverMessages : cachedMessages;
                if (serverMessages.length) replaceCachedConversation(sessionId, serverMessages);
                chatBox.innerHTML = '';
                if (!msgs.length) chatBox.innerHTML = '<div class="welcome"><p>' + text.newChat + '</p></div>';
                msgs.forEach(m => addMessageEl(m.role === 'user' ? 'user' : 'assistant', m.role === 'user' ? escapeHtml(m.content) : formatMarkdown(m.content), 'history', m.content, m.created_at || m.createdAt || m.timestamp));
                scrollChatToBottom('auto');
            } catch (e) {
                if (cachedMessages.length) {
                    chatBox.innerHTML = '';
                    cachedMessages.forEach(m => addMessageEl(m.role === 'user' ? 'user' : 'assistant', m.role === 'user' ? escapeHtml(m.content) : formatMarkdown(m.content), 'history', m.content, m.created_at));
                    scrollChatToBottom('auto');
                    loadSessionList();
                    return;
                }
                chatBox.innerHTML = '<div class="error-msg">\u52a0\u8f7d\u6d88\u606f\u5931\u8d25\uff1a' + escapeHtml(e.message) + '</div>';
            }
            loadSessionList();
        }
        async function deleteSession(sessionId) {
            if (!confirm(text.deleteConfirm)) return;
            try {
                await fetch(API_SESSIONS + '/' + encodeURIComponent(sessionId), { method: 'DELETE', headers: authHeaders() });
                removeCachedConversation(sessionId);
                if (activeSessionId === sessionId) newChat();
                loadSessionList();
            } catch (e) {
                alert('\u5220\u9664\u5931\u8d25: ' + e.message);
            }
        }
        function newChat() {
            activeSessionId = generateSessionId();
            localStorage.setItem('activeSessionId', activeSessionId);
            chatBox.innerHTML = '<div class="welcome"><h2>' + text.newChat + '</h2><p>\u8f93\u5165\u95ee\u9898\u5f00\u59cb\u5bf9\u8bdd\u3002</p></div>';
            loadSessionList();
            input.focus();
        }

        function formatTaskPlanRaw(data) {
            const items = data.data || [];
            return (data.message ? data.message + '\n\n' : '') + items.map(it => '- ' + it.title).join('\n');
        }
        function formatTaskPlanPreview(data) {
            const items = data.data || [];
            const attr = JSON.stringify(items).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
            let html = '<div class="task-plan-preview">';
            if (data.message) html += '<p>' + escapeHtml(data.message) + '</p>';
            html += '<div class="plan-list">' + items.map((it, i) => '<label class="task-item"><input type="checkbox" class="plan-check" checked data-idx="' + i + '"><span>' + escapeHtml(it.title) + '</span><span class="session-meta">' + escapeHtml(it.date + (it.time ? ' ' + it.time : '')) + '</span></label>').join('') + '</div>';
            html += '<div style="display:flex;gap:8px;margin-top:10px"><button class="send-btn" data-plan="' + attr + '" onclick="confirmTaskPlan(this)">\u786e\u8ba4\u843d\u5e93</button><button class="task-tab" data-cancel-plan="1">\u53d6\u6d88</button></div></div>';
            return html;
        }
        async function confirmTaskPlan(btn) {
            const box = btn.closest('.task-plan-preview');
            const items = JSON.parse(btn.dataset.plan || '[]');
            const checked = [];
            box.querySelectorAll('.plan-check:checked').forEach(cb => checked.push(items[Number(cb.dataset.idx)]));
            if (!checked.length) return alert('\u8bf7\u81f3\u5c11\u52fe\u9009\u4e00\u4e2a\u5b50\u4efb\u52a1');
            btn.disabled = true;
            try {
                const res = await fetch(API_TASKS + '/plan', { method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ items: checked }) });
                const data = await res.json();
                if (res.ok && data.status === 'ok') { box.innerHTML = '<span style="color:var(--green)">\u5df2\u521b\u5efa ' + data.count + ' \u4e2a\u5b50\u4efb\u52a1</span>'; loadTasks(); }
                else { alert('\u843d\u5e93\u5931\u8d25\uff1a' + (data.message || res.status)); btn.disabled = false; }
            } catch (e) { alert('\u843d\u5e93\u5931\u8d25\uff1a' + e.message); btn.disabled = false; }
        }

        async function send() {
            const q = input.value.trim();
            if (!q) return;
            const intent = window._quickIntent || '';
            window._quickIntent = '';
            if (!activeSessionId) {
                activeSessionId = generateSessionId();
                localStorage.setItem('activeSessionId', activeSessionId);
            }
            const welcome = chatBox.querySelector('.welcome');
            if (welcome) welcome.remove();
            const sentAt = new Date().toISOString();
            addMessageEl('user', escapeHtml(q), '', q, sentAt);
            cacheConversationMessage(activeSessionId, 'user', q, sentAt);
            input.value = '';
            input.disabled = true;
            sendBtn.disabled = true;
            setThinking(text.thinking);
            try {
                const url = API_QUERY_STREAM + '?question=' + encodeURIComponent(q) + '&session_id=' + encodeURIComponent(activeSessionId) + '&intent=' + encodeURIComponent(intent);
                const res = await fetch(url, { headers: authHeaders() });
                if (!res.ok || !res.body) throw new Error('\u6d41\u5f0f\u8bf7\u6c42\u5931\u8d25\uff1a' + res.status);
                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buf = '';
                let finalData = null;
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buf += decoder.decode(value, { stream: true });
                    let idx;
                    while ((idx = buf.indexOf('\n\n')) !== -1) {
                        const raw = buf.slice(0, idx);
                        buf = buf.slice(idx + 2);
                        const dataLine = raw.split('\n').find(line => line.indexOf('data:') === 0);
                        if (!dataLine) continue;
                        let evt;
                        try { evt = JSON.parse(dataLine.slice(5).trim()); } catch (e) { continue; }
                        if (evt.type === 'progress') setThinking(normalizeThinking(evt.message));
                        if (evt.type === 'result') finalData = evt.data;
                    }
                }
                if (finalData) {
                    if (finalData.task_created) loadTasks();
                    const assistantText = assistantRawText(finalData);
                    if (assistantText) cacheConversationMessage(activeSessionId, 'assistant', assistantText, new Date().toISOString());
                    // 重新读取已落库的会话消息，确保当前页和刷新后的展示完全一致。
                    await openSession(activeSessionId);
                } else {
                    addMessage('assistant', '<div class="error-msg">' + text.noResult + '</div>');
                }
            } catch (e) {
                addMessage('assistant', '<div class="error-msg">' + text.requestFailed + escapeHtml(e.message) + '</div>');
            } finally {
                hideThinking();
                input.disabled = false;
                sendBtn.disabled = false;
                input.focus();
            }
        }

        async function loadTasks() {
            try {
                const q = document.getElementById('taskSearch').value.trim();
                const res = await fetch(API_TASKS + '?filter=' + encodeURIComponent(taskFilter) + '&q=' + encodeURIComponent(q), { headers: authHeaders() });
                const data = await res.json();
                renderTaskList(data.tasks || []);
            } catch (e) {
                document.getElementById('taskList').innerHTML = '<div class="empty">' + text.noTasks + '</div>';
            }
        }
        function renderTaskList(tasks) {
            currentTasks = tasks;
            document.getElementById('taskCount').textContent = tasks.length ? '(' + tasks.length + ')' : '';
            const el = document.getElementById('taskList');
            if (!tasks.length) { el.innerHTML = '<div class="empty">' + text.noTasks + '</div>'; return; }
            const now = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
            const tomorrow = today + 86400000;
            const afterTomorrow = tomorrow + 86400000;
            function groupOf(task) {
                if (task.overdue) return { key: 'overdue', name: '\u5df2\u8fc7\u671f' };
                if (!task.deadline) return { key: 'none', name: '\u65e0\u622a\u6b62\u65e5\u671f' };
                const t = new Date(task.deadline).getTime();
                if (t < today) return { key: 'overdue', name: '\u5df2\u8fc7\u671f' };
                if (t < tomorrow) return { key: 'today', name: '\u4eca\u5929' };
                if (t < afterTomorrow) return { key: 'tomorrow', name: '\u660e\u5929' };
                return { key: 'later', name: '\u66f4\u665a' };
            }
            const order = ['overdue', 'none', 'today', 'tomorrow', 'later'];
            const groups = {};
            tasks.forEach(task => {
                const g = groupOf(task);
                (groups[g.key] = groups[g.key] || { name: g.name, items: [] }).items.push(task);
            });
            el.innerHTML = order.map(key => {
                const g = groups[key];
                if (!g) return '';
                return '<div><div class="task-group-head">' + g.name + ' <span>(' + g.items.length + ')</span></div>' + g.items.map(task => '<div class="task-item" data-task="' + task.task_id + '"><span class="dot ' + (task.overdue ? 'overdue' : task.status) + '"></span><span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escapeHtml(task.title) + '</span></div>').join('') + '</div>';
            }).join('');
        }
        async function addTask() {
            const el = document.getElementById('taskAddInput');
            const title = el.value.trim();
            if (!title) return;
            try {
                const res = await fetch(API_TASKS, { method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ title }) });
                const data = await res.json();
                if (res.ok && data.status === 'ok') { el.value = ''; loadTasks(); }
                else alert('\u521b\u5efa\u5931\u8d25\uff1a' + (data.message || res.status));
            } catch (e) { alert('\u521b\u5efa\u5931\u8d25\uff1a' + e.message); }
        }
        async function taskMenu(id) {
            const task = currentTasks.find(x => String(x.task_id) === String(id));
            if (!task) return;
            const next = task.status === 'done' ? 'pending' : 'done';
            try {
                await fetch(API_TASKS + '/' + encodeURIComponent(id), { method: 'PATCH', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ status: next }) });
                loadTasks();
            } catch (e) { console.error('\u5207\u6362\u4efb\u52a1\u72b6\u6001\u5931\u8d25', e); }
        }

        function pad2(n) { return n < 10 ? '0' + n : String(n); }
        function switchMainView(view) {
            document.getElementById('chatArea').style.display = view === 'chat' ? '' : 'none';
            document.getElementById('calPanel').style.display = view === 'calendar' ? '' : 'none';
            if (view === 'calendar') renderMonth();
        }
        async function renderMonth() {
            document.getElementById('calTitle').textContent = calYear + '\u5e74 ' + (calMonth + 1) + '\u6708';
            const res = await fetch(API_TASKS + '/worklog?year=' + calYear + '&month=' + (calMonth + 1), { headers: authHeaders() });
            const data = await res.json();
            const done = data.done_by_day || {};
            const created = data.created_by_day || {};
            const firstDow = new Date(calYear, calMonth, 1).getDay();
            const dim = new Date(calYear, calMonth + 1, 0).getDate();
            const dimPrev = new Date(calYear, calMonth, 0).getDate();
            const now = new Date();
            let cells = '';
            for (let i = 0; i < 42; i++) {
                let y = calYear, m = calMonth, d, other = false;
                if (i < firstDow) { m = calMonth - 1; if (m < 0) { m = 11; y--; } d = dimPrev - firstDow + 1 + i; other = true; }
                else if (i >= firstDow + dim) { m = calMonth + 1; if (m > 11) { m = 0; y++; } d = i - firstDow - dim + 1; other = true; }
                else d = i - firstDow + 1;
                const key = y + '-' + pad2(m + 1) + '-' + pad2(d);
                const isToday = y === now.getFullYear() && m === now.getMonth() && d === now.getDate();
                cells += '<div class="cal-cell' + (other ? ' other' : '') + (isToday ? ' today' : '') + '" data-day="' + key + '"><span class="day-num">' + d + '</span>' + (other ? '' : '<div class="cell-stats"><span class="c-done">' + (done[key] || 0) + '</span><span class="c-created">' + (created[key] || 0) + '</span></div>') + '</div>';
            }
            document.getElementById('calGrid').innerHTML = cells;
            document.getElementById('kDone').textContent = data.total_done || 0;
            document.getElementById('kCreated').textContent = data.total_created || 0;
            document.getElementById('kActive').textContent = data.active_days || 0;
            document.getElementById('kRate').textContent = data.total_created ? Math.round(data.rate * 100) + '%' : '\u2014';
        }
        async function showDay(day) {
            const el = document.getElementById('calDetail');
            el.innerHTML = '<div class="d-empty">' + text.loading + '</div>';
            try {
                const res = await fetch(API_TASKS + '/worklog/day?date=' + encodeURIComponent(day), { headers: authHeaders() });
                const data = await res.json();
                let items = '';
                (data.done_tasks || []).forEach(task => { items += '<div class="d-item"><span class="d-dot done"></span><span class="d-name">' + escapeHtml(task.title) + '</span><span class="d-time">\u2713 \u5b8c\u6210</span></div>'; });
                (data.created_tasks || []).forEach(task => { items += '<div class="d-item"><span class="d-dot pending"></span><span class="d-name">' + escapeHtml(task.title) + '</span><span class="d-time">\u25cf \u521b\u5efa</span></div>'; });
                if (!items) items = '<div class="d-empty">\u5f53\u65e5\u65e0\u5de5\u4f5c\u8bb0\u5f55</div>';
                el.innerHTML = '<div class="d-head">' + day + ' · \u5de5\u4f5c\u660e\u7ec6</div>' + items;
            } catch (e) { el.innerHTML = '<div class="d-empty">\u52a0\u8f7d\u5931\u8d25</div>'; }
        }
        function calShift(delta) {
            calMonth += delta;
            if (calMonth < 0) { calMonth = 11; calYear--; }
            if (calMonth > 11) { calMonth = 0; calYear++; }
            renderMonth();
        }
        async function renderYear() {
            const year = calYear;
            const datas = await Promise.all(Array.from({ length: 12 }, (_, m) => fetch(API_TASKS + '/worklog?year=' + year + '&month=' + (m + 1), { headers: authHeaders() }).then(r => r.json())));
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
                    const isToday = year === now.getFullYear() && m === now.getMonth() && d === now.getDate();
                    cells += '<div class="mc-cell' + (done[key] ? ' has' : '') + (isToday ? ' today' : '') + '">' + d + '</div>';
                }
                html += '<div class="mini-cal"><div class="mc-title">' + (m + 1) + '\u6708</div><div class="mc-grid">' + cells + '</div></div>';
            }
            document.getElementById('yearGrid').innerHTML = html;
        }
        async function initTaskEvents() {
            try {
                const res = await fetch(API_TASKS + '/events', { headers: authHeaders() });
                if (res.status === 401) return;
                if (!res.ok || !res.body) { setTimeout(initTaskEvents, 3000); return; }
                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buf = '';
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buf += decoder.decode(value, { stream: true });
                    let idx;
                    while ((idx = buf.indexOf('\n\n')) !== -1) {
                        const raw = buf.slice(0, idx);
                        buf = buf.slice(idx + 2);
                        const dataLine = raw.split('\n').find(line => line.indexOf('data:') === 0);
                        if (!dataLine) continue;
                        let ev;
                        try { ev = JSON.parse(dataLine.slice(5).trim()); } catch (e) { continue; }
                        if (ev.type === 'task_remind') showRemind(ev.message);
                    }
                }
                setTimeout(initTaskEvents, 3000);
            } catch (e) { setTimeout(initTaskEvents, 3000); }
        }
        function showRemind(message) {
            document.getElementById('remindBadge').style.display = 'inline';
            const toast = document.getElementById('remindToast');
            toast.textContent = message;
            toast.style.display = 'block';
            clearTimeout(toast._timer);
            toast._timer = setTimeout(() => { toast.style.display = 'none'; }, 5000);
        }

        function setDrawerCollapsed(collapsed) {
            document.body.classList.toggle('drawer-collapsed', collapsed);
            document.body.classList.toggle('drawer-open', !collapsed);
            localStorage.setItem('agent_zs_drawer_collapsed', collapsed ? '1' : '0');
            document.getElementById('drawerToggle').setAttribute('aria-expanded', String(!collapsed));
            document.getElementById('drawerRailBtn').setAttribute('aria-expanded', String(!collapsed));
        }

        setDrawerCollapsed(localStorage.getItem('agent_zs_drawer_collapsed') === '1');
        document.getElementById('drawerToggle').addEventListener('click', () => setDrawerCollapsed(true));
        document.getElementById('drawerRailBtn').addEventListener('click', () => setDrawerCollapsed(false));
        document.getElementById('newChatBtn').addEventListener('click', newChat);
        document.getElementById('sendBtn').addEventListener('click', send);
        attachBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', event => setSelectedFile(event.target.files[0] || null));
        attachmentClear.addEventListener('click', () => setSelectedFile(null));
        input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
        document.getElementById('logoutBtn').addEventListener('click', () => {
            localStorage.removeItem('agent_zs_token');
            localStorage.removeItem('userName');
            localStorage.removeItem('activeSessionId');
            window.location.href = LOGIN_PATH;
        });
        document.getElementById('chatNav').addEventListener('click', () => switchMainView('chat'));
        document.getElementById('calendarNav').addEventListener('click', () => switchMainView('calendar'));
        document.getElementById('sessionSearch').addEventListener('input', loadSessionList);
        document.getElementById('taskSearch').addEventListener('input', loadTasks);
        document.getElementById('taskAddBtn').addEventListener('click', addTask);
        document.getElementById('taskAddInput').addEventListener('keydown', e => { if (e.key === 'Enter') addTask(); });
        document.getElementById('taskToggle').addEventListener('click', () => {
            const list = document.getElementById('taskList');
            const hidden = list.style.display === 'none';
            list.style.display = hidden ? '' : 'none';
            document.getElementById('taskToggle').textContent = hidden ? '\u25be' : '\u25b8';
        });
        document.getElementById('taskTabs').addEventListener('click', e => {
            const btn = e.target.closest('.task-tab');
            if (!btn) return;
            taskFilter = btn.dataset.filter;
            document.querySelectorAll('.task-tab').forEach(x => x.classList.toggle('active', x === btn));
            loadTasks();
        });
        sessionList.addEventListener('click', e => {
            const del = e.target.closest('[data-del]');
            if (del) { e.stopPropagation(); deleteSession(del.dataset.del); return; }
            const head = e.target.closest('.session-group-head');
            if (head) { head.parentElement.classList.toggle('collapsed'); return; }
            const row = e.target.closest('.session-item');
            if (row) openSession(row.dataset.id);
        });
        document.getElementById('taskList').addEventListener('click', e => {
            const row = e.target.closest('[data-task]');
            if (row) taskMenu(row.dataset.task);
        });
        document.addEventListener('click', e => {
            const cancelPlan = e.target.closest('[data-cancel-plan]');
            if (cancelPlan) cancelPlan.closest('.task-plan-preview').remove();
        });
        document.getElementById('calGrid').addEventListener('click', e => {
            const cell = e.target.closest('[data-day]');
            if (cell) showDay(cell.dataset.day);
        });
        document.getElementById('calPrev').addEventListener('click', () => calShift(-1));
        document.getElementById('calNext').addEventListener('click', () => calShift(1));
        document.getElementById('calView').addEventListener('change', e => {
            document.getElementById('calMonth').style.display = e.target.value === 'month' ? '' : 'none';
            document.getElementById('calYear').style.display = e.target.value === 'year' ? '' : 'none';
            if (e.target.value === 'year') renderYear();
        });
        document.querySelectorAll('.quick-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                input.value = btn.dataset.q;
                window._quickIntent = btn.dataset.intent || '';
                send();
            });
        });

        (function init() {
            if (activeSessionId) openSession(activeSessionId);
            loadSessionList();
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
    """Return an empty favicon to avoid noisy 404s."""
    from fastapi.responses import Response

    return Response(status_code=204)


@router.get("/login", response_class=HTMLResponse)
async def login_page():
    """Login page."""
    return r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Agent-Zs</title>
    <style>
        * { box-sizing: border-box; }
        body { margin: 0; min-height: 100vh; display: grid; place-items: center; color: #111827; font-family: "Microsoft YaHei", "PingFang SC", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: linear-gradient(180deg, #fbfdff 0%, #eef3fb 100%); }
        .card { width: min(400px, calc(100vw - 32px)); padding: 34px; border-radius: 8px; border: 1px solid rgba(148, 163, 184, .28); background: rgba(255,255,255,.9); box-shadow: 0 18px 40px rgba(15, 23, 42, .10); }
        h1 { margin: 0 0 6px; font-size: 22px; }
        p { margin: 0 0 28px; color: #6b7280; font-size: 13px; }
        label { display: block; margin: 16px 0 6px; color: #4b5563; font-size: 13px; font-weight: 650; }
        input { width: 100%; padding: 11px 12px; border: 1px solid rgba(148, 163, 184, .36); border-radius: 8px; outline: 0; font: inherit; }
        input:focus { border-color: rgba(37,99,235,.55); box-shadow: 0 0 0 3px rgba(37,99,235,.12); }
        button { width: 100%; margin-top: 22px; padding: 12px; color: #fff; border: 0; border-radius: 8px; cursor: pointer; font: inherit; font-weight: 800; background: linear-gradient(135deg, #2563eb, #4f46e5); }
        button:disabled { background: #cbd5e1; cursor: not-allowed; }
        .error { display: none; margin-top: 14px; color: #b91c1c; font-size: 13px; text-align: center; }
        .error.show { display: block; }
    </style>
</head>
<body>
    <form class="card" id="loginForm">
        <h1>Agent-Zs</h1>
        <p>&#20225;&#19994;&#26234;&#33021;&#21161;&#25163;</p>
        <label for="username">&#29992;&#25143;&#21517;</label>
        <input id="username" type="text" autocomplete="username" autofocus placeholder="&#35831;&#36755;&#20837;&#29992;&#25143;&#21517;">
        <label for="password">&#23494;&#30721;</label>
        <input id="password" type="password" autocomplete="current-password" placeholder="&#35831;&#36755;&#20837;&#23494;&#30721;">
        <button id="loginBtn" type="submit">&#30331;&#24405;</button>
        <div class="error" id="errorMsg"></div>
    </form>
    <script>
        function resolveAppBase() {
            return window.location.pathname.startsWith('/agent-ai') ? '/agent-ai/' : '/';
        }

        function resolveApiBase() {
            return window.location.pathname.startsWith('/agent-ai') ? '/agent-ai-api' : '/api/v1';
        }

        const APP_BASE = resolveAppBase();
        document.documentElement.classList.toggle('embedded-mode', window.self !== window.top || window.location.pathname.startsWith('/agent-ai'));
        const API_BASE = resolveApiBase();

        if (localStorage.getItem('agent_zs_token')) window.location.href = APP_BASE;
        const form = document.getElementById('loginForm');
        const usernameEl = document.getElementById('username');
        const passwordEl = document.getElementById('password');
        const loginBtn = document.getElementById('loginBtn');
        const errorMsg = document.getElementById('errorMsg');
        function showError(message) {
            errorMsg.textContent = message;
            errorMsg.classList.add('show');
        }
        form.addEventListener('submit', async event => {
            event.preventDefault();
            const username = usernameEl.value.trim();
            const password = passwordEl.value.trim();
            if (!username || !password) return showError('\u8bf7\u8f93\u5165\u7528\u6237\u540d\u548c\u5bc6\u7801');
            loginBtn.disabled = true;
            loginBtn.textContent = '\u767b\u5f55\u4e2d...';
            errorMsg.classList.remove('show');
            try {
                const res = await fetch(`${API_BASE}/auth/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                const data = await res.json();
                if (res.ok && data.status === 'ok') {
                    localStorage.setItem('agent_zs_token', data.token);
                    localStorage.setItem('userName', data.user.real_name || data.user.username);
                    window.location.href = APP_BASE;
                } else {
                    showError(data.message || '\u7528\u6237\u540d\u6216\u5bc6\u7801\u9519\u8bef');
                }
            } catch (e) {
                showError('\u7f51\u7edc\u9519\u8bef\uff0c\u8bf7\u68c0\u67e5\u8fde\u63a5');
            } finally {
                loginBtn.disabled = false;
                loginBtn.textContent = '\u767b\u5f55';
            }
        });
    </script>
</body>
</html>
    """
