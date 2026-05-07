#!/bin/bash
# 小红书接口 - 一键登录脚本
# 用法:
#   ./login.sh "a1=xxx; web_session=xxx"
#   ./login.sh "a1=xxx; web_session=xxx" http://127.0.0.1:8000
#   ./login.sh "$XHS_COOKIE"   # 从环境变量读取

set -euo pipefail

COOKIE="${1:?错误: 请提供 Cookie 字符串，例如: ./login.sh \"a1=xxx; web_session=xxx\"}"
BASE="${2:-http://127.0.0.1:8000}"

echo "=== 1. 创建会话 ==="
CREATE=$(curl -s --max-time 90 -X POST "$BASE/v1/sessions" \
  -H "Content-Type: application/json" \
  -d '{"purpose":"auto-login"}')
SID=$(echo "$CREATE" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['session_id'])")
echo "session_id: $SID"

echo ""
echo "=== 2. 绑定会话 ==="
BIND=$(curl -s --max-time 90 -X POST "$BASE/v1/sessions/$SID/bind")
TOKEN=$(echo "$BIND" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['token'])")
echo "token: $TOKEN"

echo ""
echo "=== 3. Cookie 登录 ==="
# 用 Python 生成合法的 JSON（避免 shell 对分号/引号转义出错）
BODY=$(python3 -c "
import json, sys
cookie = sys.argv[1]
token = sys.argv[2]
print(json.dumps({'token': token, 'action': 'cookie', 'cookie': cookie}))
" "$COOKIE" "$TOKEN")

LOGIN=$(curl -s --max-time 90 -X POST "$BASE/v1/sessions/$SID/login" \
  -H "Content-Type: application/json" \
  -d "$BODY")
echo "$LOGIN" | python3 -m json.tool

echo ""
echo "=== 4. 验证登录态 ==="
curl -s --max-time 30 "$BASE/v1/sessions/$SID/login/status?token=$TOKEN" | python3 -m json.tool

echo ""
echo "=========================================="
echo "  登录成功！"
echo "  session_id: $SID"
echo "  token:      $TOKEN"
echo "  服务地址:   $BASE"
echo ""
echo "  后续使用示例:"
echo "  curl -X POST \"$BASE/v1/sessions/\$SID/search\" \\"
echo "    -H \"Content-Type: application/json\" \\"
echo "    -d '{\"token\":\"\$TOKEN\",\"keyword\":\"关键词\"}'"
echo ""
echo "  用完解绑:"
echo "  curl -X POST \"$BASE/v1/sessions/\$SID/unbind\" \\"
echo "    -H \"Content-Type: application/json\" \\"
echo "    -d '{\"token\":\"\$TOKEN\"}'"
echo "=========================================="
