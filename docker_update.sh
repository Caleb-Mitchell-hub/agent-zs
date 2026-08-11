#!/bin/bash
# 更新容器内文件并重启
set -e
echo "拷贝文件到容器..."
docker cp /opt/agent-zs/app/services/__init__.py agent-zs:/app/app/services/__init__.py
docker cp /opt/agent-zs/app/services/session_service.py agent-zs:/app/app/services/session_service.py
docker cp /opt/agent-zs/app/routers/sessions.py agent-zs:/app/app/routers/sessions.py
docker cp /opt/agent-zs/app/routers/frontend.py agent-zs:/app/app/routers/frontend.py
docker cp /opt/agent-zs/app/routers/query.py agent-zs:/app/app/routers/query.py
docker cp /opt/agent-zs/app/main.py agent-zs:/app/app/main.py
echo "重启容器..."
docker restart agent-zs
echo "等待就绪..."
sleep 5
curl -s http://localhost:8000/health
echo ""
echo "完成!"
