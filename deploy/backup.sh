#!/bin/bash
# GCS 버킷으로 data/ 백업
# 크론잡으로 매일 실행: 0 3 * * * /home/유저이름/kkabi/deploy/backup.sh

BUCKET="gs://내버킷이름/kkabi-backup"
DATA_DIR="/home/유저이름/kkabi/data"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

echo "=== 백업 시작: $TIMESTAMP ==="

# data/ 전체를 GCS에 동기화
gsutil -m rsync -r "$DATA_DIR" "$BUCKET/latest/"

# 주 1회 스냅샷 (일요일)
if [ "$(date +%u)" = "7" ]; then
    gsutil -m cp -r "$DATA_DIR" "$BUCKET/snapshots/$TIMESTAMP/"
fi

echo "=== 백업 완료 ==="
