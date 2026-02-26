#!/bin/bash
set -e
echo "=== Kkabi - GCP 설치 ==="

# 시스템 패키지
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv

# 프로젝트 디렉토리
cd ~/kkabi

# 가상환경
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 설정 파일
if [ ! -f config.json ]; then
    cp config.example.json config.json
    echo ""
    echo "⚠️  config.json을 편집하세요:"
    echo "   nano config.json"
    echo ""
    echo "   필요한 값:"
    echo "   - telegram_bot_token: @BotFather에서 생성"
    echo "   - allowed_user_ids: @userinfobot에서 확인"
    echo ""
    exit 1
fi

# 런타임 디렉토리
mkdir -p data/memory/logs data/memory/projects data/uploads logs

# 기본 MEMORY.md
if [ ! -f data/memory/MEMORY.md ]; then
    cat > data/memory/MEMORY.md << 'MEMEOF'
# 장기 메모리

## 나에 대해
- (여기에 본인 정보 추가)

## 활성 프로젝트
- (프로젝트 목록)

## 중요한 결정들
- (결정 사항)

## 환경 정보
- GCP Compute Engine
- (기타 환경)
MEMEOF
fi

# 기본 시스템 프롬프트
if [ ! -f data/system_prompt.txt ]; then
    cat > data/system_prompt.txt << 'SYSEOF'
너는 나의 개인 AI 비서다.
항상 한국어로 답변하고, 간결하게 핵심만 말해.
파일을 수정하거나 코드를 작성할 때는 바로 실행해.
기억해야 할 것이 있으면 data/memory/MEMORY.md에 기록해.
작업 완료 후에는 결과를 간단히 요약해줘.
SYSEOF
fi

# systemd 서비스 등록
sudo cp deploy/kkabi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kkabi
sudo systemctl start kkabi

echo ""
echo "✅ 설치 완료!"
echo ""
echo "확인 명령어:"
echo "  sudo systemctl status kkabi"
echo "  journalctl -u kkabi -f"
echo ""
echo "텔레그램에서 봇에게 '안녕' 보내서 테스트하세요!"
