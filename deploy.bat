@echo off
echo ============================================
echo Agent-Zs 部署脚本
echo ============================================

echo [1/3] 上传修改的代码文件...
scp requirements.txt root@172.177.3.43:/opt/agent-zs/requirements.txt
scp app/orchestrator/planner.py root@172.177.3.43:/opt/agent-zs/app/orchestrator/planner.py
scp app/orchestrator/orchestrator.py root@172.177.3.43:/opt/agent-zs/app/orchestrator/orchestrator.py
scp app/orchestrator/langgraph_flow.py root@172.177.3.43:/opt/agent-zs/app/orchestrator/langgraph_flow.py
scp app/routers/frontend.py root@172.177.3.43:/opt/agent-zs/app/routers/frontend.py
scp app/routers/query.py root@172.177.3.43:/opt/agent-zs/app/routers/query.py
scp app/routers/admin_config.py root@172.177.3.43:/opt/agent-zs/app/routers/admin_config.py
scp app/models/schemas.py root@172.177.3.43:/opt/agent-zs/app/models/schemas.py
scp app/security/__init__.py root@172.177.3.43:/opt/agent-zs/app/security/__init__.py
scp app/security/crypto.py root@172.177.3.43:/opt/agent-zs/app/security/crypto.py
scp app/security/auth_service.py root@172.177.3.43:/opt/agent-zs/app/security/auth_service.py
scp app/config_center/__init__.py root@172.177.3.43:/opt/agent-zs/app/config_center/__init__.py
scp app/config_center/cache.py root@172.177.3.43:/opt/agent-zs/app/config_center/cache.py
scp app/config_center/service.py root@172.177.3.43:/opt/agent-zs/app/config_center/service.py
scp app/tools/database_tool.py root@172.177.3.43:/opt/agent-zs/app/tools/database_tool.py
scp app/tools/search_tool.py root@172.177.3.43:/opt/agent-zs/app/tools/search_tool.py
scp app/tools/rag_tool.py root@172.177.3.43:/opt/agent-zs/app/tools/rag_tool.py
scp app/tools/report_templates.py root@172.177.3.43:/opt/agent-zs/app/tools/report_templates.py
scp app/tools/registry.py root@172.177.3.43:/opt/agent-zs/app/tools/registry.py
scp app/tools/follow_up_router.py root@172.177.3.43:/opt/agent-zs/app/tools/follow_up_router.py
scp app/tools/time_tool.py root@172.177.3.43:/opt/agent-zs/app/tools/time_tool.py
scp app/db/schema.py root@172.177.3.43:/opt/agent-zs/app/db/schema.py
scp app/agents/report_agent.py root@172.177.3.43:/opt/agent-zs/app/agents/report_agent.py
scp app/memory/extractor.py root@172.177.3.43:/opt/agent-zs/app/memory/extractor.py
scp app/runtime/engine.py root@172.177.3.43:/opt/agent-zs/app/runtime/engine.py
scp app/main.py root@172.177.3.43:/opt/agent-zs/app/main.py
scp app/config.py root@172.177.3.43:/opt/agent-zs/app/config.py
scp app/routers/auth.py root@172.177.3.43:/opt/agent-zs/app/routers/auth.py
scp app/routers/admin.py root@172.177.3.43:/opt/agent-zs/app/routers/admin.py
scp app/routers/sessions.py root@172.177.3.43:/opt/agent-zs/app/routers/sessions.py
scp app/agents/data_agent.py root@172.177.3.43:/opt/agent-zs/app/agents/data_agent.py
scp app/agents/knowledge_agent.py root@172.177.3.43:/opt/agent-zs/app/agents/knowledge_agent.py
scp app/services/__init__.py root@172.177.3.43:/opt/agent-zs/app/services/__init__.py
scp app/services/session_service.py root@172.177.3.43:/opt/agent-zs/app/services/session_service.py
scp app/gateway/auth.py root@172.177.3.43:/opt/agent-zs/app/gateway/auth.py
scp app/gateway/rate_limit.py root@172.177.3.43:/opt/agent-zs/app/gateway/rate_limit.py
scp app/agent/llm_client.py root@172.177.3.43:/opt/agent-zs/app/agent/llm_client.py

echo [1.5/3] 上传配置中心 SQL 脚本并初始化数据库...
scp scripts/init_config_center.sql root@172.177.3.43:/opt/agent-zs/scripts/init_config_center.sql
ssh root@172.177.3.43 "docker exec -i wms-mysql mysql -u wms -pZsds2604! wms < /opt/agent-zs/scripts/init_config_center.sql 2>&1 || echo 'SQL 执行失败或表已存在（幂等脚本可重试）'"

echo [2/3] 重建 agent-zs 容器...
ssh root@172.177.3.43 "cd /opt/agent-zs && docker compose up -d --build agent-zs"

echo [3/3] 部署完成。等待服务就绪...
ssh root@172.177.3.43 "sleep 8 && curl -s http://localhost:8000/health"
echo.
echo 部署完成！
