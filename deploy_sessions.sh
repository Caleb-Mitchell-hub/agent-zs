#!/bin/bash
# 部署会话列表功能
set -e

echo "=== 创建目录 ==="
ssh root@172.177.3.43 "mkdir -p /opt/agent-zs/app/services"

echo "=== 上传新文件 ==="
scp app/services/__init__.py root@172.177.3.43:/opt/agent-zs/app/services/__init__.py
scp app/services/session_service.py root@172.177.3.43:/opt/agent-zs/app/services/session_service.py
scp app/routers/sessions.py root@172.177.3.43:/opt/agent-zs/app/routers/sessions.py

echo "=== 上传修改文件 ==="
scp app/routers/frontend.py root@172.177.3.43:/opt/agent-zs/app/routers/frontend.py
scp app/routers/query.py root@172.177.3.43:/opt/agent-zs/app/routers/query.py
scp app/main.py root@172.177.3.43:/opt/agent-zs/app/main.py

echo "=== 重建 Docker ==="
ssh root@172.177.3.43 "cd /opt/agent-zs && docker compose up -d --build agent-zs"

echo "=== 等待就绪 ==="
sleep 8
ssh root@172.177.3.43 "curl -s http://localhost:8000/health"
echo ""
echo "部署完成!"
