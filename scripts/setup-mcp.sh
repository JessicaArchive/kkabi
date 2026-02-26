#!/bin/bash
# MCP 서버 설정 스크립트
# 필요한 MCP 서버를 여기에 추가하세요

set -e
echo "=== MCP 서버 설정 ==="

# 예시: Brave Search MCP
# npx -y @anthropic-ai/claude-code mcp add brave-search -- npx -y @anthropic-ai/mcp-server-brave-search

# 예시: GitHub MCP
# npx -y @anthropic-ai/claude-code mcp add github -- npx -y @anthropic-ai/mcp-server-github

# 예시: Filesystem MCP
# npx -y @anthropic-ai/claude-code mcp add filesystem -- npx -y @anthropic-ai/mcp-server-filesystem /home/유저이름

echo ""
echo "MCP 서버 목록 확인:"
echo "  claude mcp list"
echo ""
echo "MCP 서버 추가 예시:"
echo "  claude mcp add <이름> -- <명령어>"
echo ""
echo "설정이 완료되면 Kkabi를 재시작하세요:"
echo "  sudo systemctl restart kkabi"
