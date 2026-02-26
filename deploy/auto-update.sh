#!/bin/bash
# GitHub에서 변경사항 감지 시 자동 pull + 서비스 재시작
# 크론잡: * * * * * /home/yejiseulkim/kkabi/deploy/auto-update.sh

cd /home/yejiseulkim/kkabi || exit 1

# 원격 변경사항 확인
git fetch origin main --quiet 2>/dev/null

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "$(date): 변경 감지, 업데이트 중..."
    git reset --hard origin/main --quiet
    source venv/bin/activate
    pip install -r requirements.txt --quiet 2>/dev/null
    sudo systemctl restart kkabi
    echo "$(date): 업데이트 완료 ($(git rev-parse --short HEAD))"
fi
