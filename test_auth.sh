#!/bin/bash
echo '=== 1. 登录测试(root/root) ==='
LOGIN_RESP=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"root","password":"root"}')
echo "$LOGIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('status:', d.get('status')); print('user:', d.get('user',{}).get('username','?')); print('role:', d.get('user',{}).get('roles','?')); print('token:', d.get('token','')[:50]+'...')" 2>/dev/null
TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)

echo ''
echo '=== 2. /auth/me ==='
curl -s http://localhost:8001/api/v1/auth/me -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print('status:', d.get('status')); u=d.get('user',{}); print('username:', u.get('username')); print('is_super_admin:', u.get('is_super_admin')); print('roles:', u.get('roles')); print('permissions:', u.get('permissions'))" 2>/dev/null

echo ''
echo '=== 3. 查询测试(有token) ==='
curl -s -X POST http://localhost:8001/api/v1/query \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question":"查询所有仓库"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('status:', d.get('status')); print('data_len:', len(d.get('data',[])) if d.get('data') else 0)" 2>/dev/null

echo ''
echo '=== 4. 无token访问(预期401) ==='
CODE=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/api/v1/query)
echo "HTTP状态码: $CODE (预期401)"

echo ''
echo '=== 5. 配置中心 ==='
curl -s http://localhost:8001/api/v1/admin/config/llm -H "Authorization: Bearer $TOKEN" | head -c 300
echo ''
