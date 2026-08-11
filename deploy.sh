#!/bin/bash
set -e
echo "===== Agent-Zs 部署 ====="

echo "[1/3] 上传代码文件..."
scp requirements.txt root@172.177.3.43:/opt/agent-zs/requirements.txt
scp app/main.py root@172.177.3.43:/opt/agent-zs/app/main.py
scp app/config.py root@172.177.3.43:/opt/agent-zs/app/config.py
scp app/routers/frontend.py root@172.177.3.43:/opt/agent-zs/app/routers/frontend.py
scp app/routers/auth.py root@172.177.3.43:/opt/agent-zs/app/routers/auth.py
scp app/routers/query.py root@172.177.3.43:/opt/agent-zs/app/routers/query.py
scp app/routers/admin_config.py root@172.177.3.43:/opt/agent-zs/app/routers/admin_config.py
scp app/routers/admin.py root@172.177.3.43:/opt/agent-zs/app/routers/admin.py
scp app/gateway/auth.py root@172.177.3.43:/opt/agent-zs/app/gateway/auth.py
scp app/security/__init__.py root@172.177.3.43:/opt/agent-zs/app/security/__init__.py
scp app/security/auth_service.py root@172.177.3.43:/opt/agent-zs/app/security/auth_service.py
scp app/security/crypto.py root@172.177.3.43:/opt/agent-zs/app/security/crypto.py
scp app/orchestrator/orchestrator.py root@172.177.3.43:/opt/agent-zs/app/orchestrator/orchestrator.py
scp app/orchestrator/langgraph_flow.py root@172.177.3.43:/opt/agent-zs/app/orchestrator/langgraph_flow.py
scp app/agents/data_agent.py root@172.177.3.43:/opt/agent-zs/app/agents/data_agent.py
scp app/tools/database_tool.py root@172.177.3.43:/opt/agent-zs/app/tools/database_tool.py
scp app/agent/llm_client.py root@172.177.3.43:/opt/agent-zs/app/agent/llm_client.py

echo "[2/3] 重建 Docker 容器..."
ssh root@172.177.3.43 "cd /opt/agent-zs && docker compose up -d --build agent-zs"

echo "[3/3] 等待服务就绪..."
sleep 8
ssh root@172.177.3.43 "curl -s http://localhost:8000/health"
echo ""
echo "部署完成!"
