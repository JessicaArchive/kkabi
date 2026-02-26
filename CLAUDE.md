# CLAUDE.md - Kkabi (깨비) 프로젝트 설계서

> 이 파일을 프로젝트 루트에 놓고 Claude Code를 실행하면, Claude가 이 설계를 읽고 프로젝트를 만들어줍니다.
> `claude` 실행 후 "이 설계서대로 프로젝트를 만들어줘"

---

## 프로젝트 개요

OpenClaw 대안으로 쓸 **텔레그램 기반 AI 자동비서 "Kkabi"**를 만든다.
텔레그램으로 명령하면 Claude Code가 실행되고, 크론잡으로 주기적 작업도 수행한다.
웹서핑, GitHub 코드 푸시, 파일 관리 등은 MCP 서버를 통해 처리한다.

**OpenClaw과의 핵심 차이**: OpenClaw은 올인원 Gateway지만, 이건 각 부품을 조립하는 방식이다.
더 가볍고, 공식 Claude Code 토큰을 쓰므로 차단 위험이 없다.

---

## 환경

- 서버: **GCP Compute Engine** (기존 인스턴스 사용)
- OS: Ubuntu 22.04+ (또는 인스턴스에 설치된 리눅스)
- 언어: Python 3.11+
- Claude Code CLI 설치됨 (`claude` 명령어 사용 가능)
- MCP 서버들은 별도 설정 (scripts/setup-mcp.sh)

### GCP 관련 참고
- SSH 접속: `gcloud compute ssh 인스턴스명 --zone=존`
- 프로젝트 경로: `/home/사용자명/kkabi`
- 방화벽: 텔레그램 봇은 아웃바운드만 쓰므로 인바운드 포트 오픈 불필요 (polling 방식)
- 인스턴스가 재시작되어도 봇이 자동 실행되도록 systemd enable 필수

---

## 아키텍처

```
텔레그램 (내 폰)
    ↓ 메시지/파일/음성
텔레그램 봇 (Python, systemd로 항상 실행)
    ↓
    ├─ 일반 메시지 → 대화 맥락 붙여서 Claude Code 호출
    ├─ /명령어    → 각 핸들러 처리
    └─ 파일 전송   → 서버에 저장 후 Claude에게 경로 전달
    ↓
Claude Code CLI (claude -p "..." --dangerously-skip-permissions)
    ↓ MCP 서버 활용 (브라우저, GitHub, 파일 등)
결과 → 텔레그램으로 응답

별도:
크론잡 스케줄러 (APScheduler) → Claude Code → 결과를 텔레그램으로 전송
메모리 시스템 → MEMORY.md + 일별 로그 → Claude 호출 시 컨텍스트로 주입
```

---

## 핵심 기능

### 1. 텔레그램 봇

- python-telegram-bot 라이브러리 (v20+, async)
- 허가된 사용자만 사용 (user_id 화이트리스트)
- 긴 응답은 4096자 단위로 분할 전송
- Claude 실행 시 "⏳ 처리 중..." 메시지 먼저 전송, 완료 후 결과 전송

**명령어:**

| 명령어 | 기능 |
|--------|------|
| 일반 메시지 | 대화 맥락과 함께 Claude에게 전달 |
| /cd <경로> | 작업 디렉토리 변경 |
| /pwd | 현재 작업 디렉토리 |
| /status | 시스템 상태 (업타임, Claude 버전, 메모리 크기, MCP 목록) |
| /cron list | 크론잡 목록 |
| /cron add <표현식> <설명> | 크론잡 추가 |
| /cron remove <ID> | 크론잡 삭제 |
| /cron toggle <ID> | 크론잡 활성화/비활성화 |
| /history [N] | 최근 N개 실행 기록 (기본 10) |
| /memory | 현재 MEMORY.md 내용 요약 |
| /memory add <내용> | 메모리에 수동 추가 |
| /memory clear | 오늘 로그 초기화 |
| /forget | 현재 대화 맥락 초기화 |
| /system <프롬프트> | 시스템 프롬프트 변경 |
| /getfile <경로> | 서버 파일을 텔레그램으로 전송 |
| /cancel | 현재 실행 중인 Claude 작업 취소 |
| /running | 실행 중인 작업 확인 |
| /help | 도움말 |

---

### 2. 대화 맥락 유지 ⭐ (OpenClaw의 핵심 기능)

OpenClaw은 세션 내에서 이전 대화를 기억한다. 우리도 이걸 구현한다.

**방식**: 최근 N개의 대화(질문+응답)를 저장해두고, Claude 호출 시 프롬프트 앞에 붙여준다.

```python
# 개념적 흐름
context = build_context(
    system_prompt=user_system_prompt,     # 사용자 설정 시스템 프롬프트
    memory=load_memory_summary(),          # MEMORY.md 요약
    recent_conversation=get_last_n_turns(5),  # 최근 5턴 대화
    user_message=current_message           # 현재 메시지
)
result = await run_claude(context, work_dir)
save_conversation_turn(current_message, result)  # 대화 기록 저장
```

**Claude에게 전달되는 프롬프트 형식:**
```
[시스템] 너는 내 개인 AI 비서다. 아래 메모리와 대화 맥락을 참고해서 답변해.

[메모리 요약]
- 사용자는 Python과 React를 주로 사용
- 프로젝트: myapp (Next.js), bot-project (Python)
- GitHub: username/myapp

[최근 대화]
나: myapp에서 로그인 버그 좀 고쳐줘
Claude: src/auth.py에서 토큰 만료 체크가 빠져있었습니다. 수정했습니다.
나: 고마워. 그거 GitHub에 올려줘
Claude: 커밋하고 push 완료했습니다. PR #42로 올렸습니다.

[현재 메시지]
PR 머지됐어? 확인해봐
```

**구현 상세:**
- 대화 기록은 SQLite에 저장 (user_message, assistant_response, timestamp)
- 최근 5턴만 프롬프트에 포함 (토큰 절약)
- /forget 명령으로 맥락 초기화 가능
- 각 대화턴의 응답은 500자로 잘라서 저장 (토큰 관리)

---

### 3. 메모리 시스템 ⭐ (OpenClaw의 핵심 기능)

OpenClaw은 세션 간에도 사용자 정보를 기억한다. 우리도 파일 기반 메모리를 구현한다.

**구조:**
```
data/memory/
├── MEMORY.md          ← 장기 기억 (수동 관리, 중요한 것만)
├── logs/
│   ├── 2026-02-27.md  ← 오늘 대화 로그
│   ├── 2026-02-26.md  ← 어제 대화 로그
│   └── ...
└── projects/
    ├── myapp.md       ← 프로젝트별 메모
    └── bot-project.md
```

**MEMORY.md 예시:**
```markdown
# 장기 메모리

## 나에 대해
- 이름: (사용자 이름)
- 주 사용 언어: Python, JavaScript
- 선호: 간결한 코드, 한국어 답변

## 활성 프로젝트
- myapp: Next.js 앱, GitHub username/myapp, Vercel 배포
- bot-project: 이 텔레그램 봇 자체

## 중요한 결정들
- 2026-02-20: DB를 PostgreSQL에서 SQLite로 변경
- 2026-02-25: OpenClaw 대안으로 Claude Code + MCP 구성

## 환경 정보
- VPS: Ubuntu 22.04, 2GB RAM
- GitHub Token: 환경변수에 저장됨
```

**자동 로깅:**
- 매 대화마다 `data/memory/logs/YYYY-MM-DD.md`에 기록
- 형식: `## HH:MM\n**나:** 메시지\n**Claude:** 응답요약\n`
- Claude 응답은 처음 200자만 기록

**메모리 주입:**
- Claude 호출 시 MEMORY.md 내용을 프롬프트 앞부분에 포함
- 일별 로그는 포함하지 않음 (필요하면 Claude가 직접 파일을 읽음)

**자동 기억:**
- Claude에게 "이거 기억해둬"라고 말하면 MEMORY.md에 기록하도록 시스템 프롬프트에 지시
- 30일 이상 된 로그는 크론잡으로 자동 삭제

---

### 4. 파일 전송 ⭐

**텔레그램 → 서버 (업로드):**
- 파일을 보내면 `data/uploads/`에 저장
- Claude에게 "사용자가 파일을 보냈습니다: /path/to/file 확인해주세요" 전달
- 이미지, 문서, 코드 파일 모두 지원
- 최대 50MB (config에서 변경)

**서버 → 텔레그램 (다운로드):**
- `/getfile <경로>` → 해당 파일을 텔레그램으로 전송
- 예: `/getfile ~/projects/myapp/report.pdf`

---

### 5. 시스템 프롬프트

기본값 (`data/system_prompt.txt`):
```
너는 나의 개인 AI 비서다.
항상 한국어로 답변하고, 간결하게 핵심만 말해.
파일을 수정하거나 코드를 작성할 때는 바로 실행해.
기억해야 할 것이 있으면 data/memory/MEMORY.md에 기록해.
작업 완료 후에는 결과를 간단히 요약해줘.
```

- `/system <새 프롬프트>`로 변경 가능, 파일에 저장되어 재시작 후 유지

---

### 6. Claude Code 실행 모듈

```bash
claude -p "프롬프트" --dangerously-skip-permissions --output-format text
```

- asyncio subprocess (비동기)
- 타임아웃 5분 (설정 가능)
- 모든 실행 SQLite에 기록

**에러 분류:**

| 에러 | 감지 | 대응 |
|------|------|------|
| CLI 없음 | FileNotFoundError | "claude가 설치되지 않았습니다" |
| 인증 만료 | stderr에 "auth" | "claude login을 다시 실행하세요" |
| 한도 초과 | stderr에 "rate limit" | 자동 재시도 큐 (5분 후, 최대 3회) |
| 타임아웃 | TimeoutError | "5분 초과" |
| MCP 에러 | stderr에 "mcp" | "MCP 서버 연결 실패" |

---

### 7. 위험 명령 승인 모드 ⭐

`--dangerously-skip-permissions`를 쓰기 때문에 Claude가 `rm -rf`도 실행할 수 있다.
특정 키워드가 포함된 프롬프트는 실행 전에 텔레그램으로 확인을 요청한다.

**config:**
```json
{
  "safety": {
    "confirm_keywords": ["삭제", "rm ", "drop ", "reset", "format", "deploy", "push"],
    "confirm_message": "⚠️ 위험할 수 있는 작업입니다. 실행할까요?",
    "auto_approve_cron": false
  }
}
```

**동작 흐름:**
1. 사용자 메시지에 `confirm_keywords` 중 하나가 포함되면
2. "⚠️ 위험할 수 있는 작업입니다: `{메시지}`. 실행할까요?" + 인라인 키보드 [✅ 실행] [❌ 취소]
3. ✅ → 실행, ❌ → 취소
4. 크론잡에서는 `auto_approve_cron: false`면 실행 보류 후 텔레그램으로 승인 요청

---

### 8. 실행 중 상태 표시 + 취소 ⭐

Claude가 5분간 돌 때 "죽은 건가?" 싶어서 같은 명령을 또 보내면 한도만 낭비된다.
실시간 상태 표시와 취소 기능이 필수다.

**구현:**
- Claude 실행 시작 → "⏳ 처리 중..." 메시지 전송 (message_id 저장)
- 10초마다 "⏳ 처리 중... (30초 경과)" 로 메시지 수정 (edit_message)
- `/cancel` → 현재 실행 중인 Claude 프로세스 kill
- `/running` → 실행 중인 작업 있는지 확인
- 완료 시 → "처리 중" 메시지 삭제 후 결과 전송

```python
# 현재 실행 중인 프로세스 추적
running_tasks: dict[int, asyncio.subprocess.Process] = {}
```

---

### 9. 동시 실행 큐 ⭐

메시지를 빠르게 여러 개 보내면 Claude가 동시에 여러 번 실행되어 파일 충돌 + 한도 낭비.
큐로 순서대로 처리한다.

**구현:**
- asyncio.Queue로 실행 큐 관리
- 동시 실행 최대 수: 1 (기본) — config로 변경 가능
- 큐에 쌓이면 "📋 대기 중 (앞에 N개 작업)" 메시지 전송
- 크론잡도 같은 큐를 공유

```json
{
  "claude": {
    "max_concurrent": 1,
    "queue_max_size": 10
  }
}

---

### 10. 크론잡 스케줄러

- APScheduler (Python 내부 관리)
- `data/crons.json`에 저장 (재시작 유지)
- 결과를 텔레그램으로 자동 전송
- `silent_on_success: true` 옵션 → 성공 시 알림 안 보냄 (모니터링용)

**crons.json 예시:**
```json
[
  {
    "id": "daily-git-push",
    "name": "매일 자정 깃 푸시",
    "cron": "0 0 * * *",
    "prompt": "~/projects/myapp에서 변경사항 커밋하고 push",
    "work_dir": "~/projects/myapp",
    "enabled": true,
    "silent_on_success": false
  },
  {
    "id": "site-monitor",
    "name": "사이트 모니터링",
    "cron": "0 * * * *",
    "prompt": "https://example.com 접속 정상인지 확인. 에러 있을 때만 알려줘.",
    "work_dir": "~",
    "enabled": true,
    "silent_on_success": true
  }
]
```

---

### 11. 실행 기록 (SQLite)

```sql
CREATE TABLE executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,        -- 'telegram' | 'cron' | 'retry'
    cron_id TEXT,
    prompt TEXT NOT NULL,
    result TEXT,
    duration_sec REAL,
    work_dir TEXT,
    status TEXT NOT NULL,        -- 'success' | 'error' | 'timeout' | 'rate_limited'
    error_message TEXT
);

CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_message TEXT NOT NULL,
    assistant_response TEXT NOT NULL,
    work_dir TEXT,
    duration_sec REAL
);
```

---

## 구현 주의사항

1. **비동기 필수**: Claude 실행 중 봇이 블로킹되면 안 됨. asyncio.create_subprocess_exec 사용.
2. **"처리 중" UX**: 실행 시작 시 "⏳ 처리 중..." 전송 → 완료 시 해당 메시지 삭제/수정 후 결과 전송.
3. **보안**: 모든 핸들러에 인증 데코레이터. allowed_user_ids 외 접근 차단.
4. **메모리 크기**: MEMORY.md는 2000자 이내 권장. 상세 내용은 projects/ 하위로 분리.
5. **로그 정리**: 30일 이상 된 일별 로그 자동 삭제 (크론잡으로).
6. **대화 맥락 크기**: 각 턴 응답은 500자로 잘라서 저장. 토큰 폭발 방지.
7. **graceful shutdown**: SIGTERM 시 Claude 프로세스 정리, 스케줄러 정상 종료.

---

## GCP Compute Engine 배포

### 사전 조건 (인스턴스에서 확인)

```bash
# SSH 접속
gcloud compute ssh 인스턴스명 --zone=존

# 필수 도구 확인
python3 --version    # 3.11+
node --version       # 18+
claude --version     # Claude Code CLI
git --version
```

### Claude Code가 아직 없다면

```bash
# Node.js 설치 (없는 경우)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Claude Code 설치
npm install -g @anthropic-ai/claude-code

# 로그인 (브라우저 없는 서버에서)
claude login --method=manual
# → 표시되는 URL을 로컬 브라우저에서 열고 인증
# → 토큰을 복사해서 터미널에 붙여넣기
```

### 설치 스크립트 (deploy/install.sh)

```bash
#!/bin/bash
set -e
echo "=== Kkabi - GCP 설치 ==="

# 시스템 패키지
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv

# 프로젝트 디렉토리
cd ~/kkabi

# 가상환경 (GCP에서는 venv 권장)
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
```

### systemd 서비스 (deploy/kkabi.service)

```ini
[Unit]
Description=Kkabi - Telegram AI Assistant
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=실제유저이름
WorkingDirectory=/home/실제유저이름/kkabi
ExecStart=/home/실제유저이름/kkabi/venv/bin/python main.py
Restart=always
RestartSec=10

# 환경변수
Environment=PATH=/usr/local/bin:/usr/bin:/bin:/home/실제유저이름/.local/bin:/home/실제유저이름/.npm-global/bin
Environment=GITHUB_TOKEN=ghp_xxxxx

# GCP에서 메모리 제한 (옵션 - 인스턴스 스펙에 맞게)
# MemoryMax=1G

# 로그
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kkabi

[Install]
WantedBy=multi-user.target
```

**주의**: `실제유저이름` 부분을 GCP 인스턴스의 실제 사용자명으로 바꿔야 한다. `whoami`로 확인.

### 데이터 백업 (deploy/backup.sh)

GCP VM이 삭제되거나 장애 나면 메모리와 대화 기록이 날아간다.
Google Cloud Storage에 주기적으로 백업한다.

```bash
#!/bin/bash
# GCS 버킷으로 data/ 백업
# 크론잡으로 매일 실행: 0 3 * * * /home/유저/kkabi/deploy/backup.sh

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
```

```bash
# 백업 크론잡 등록
crontab -e
# 매일 새벽 3시 백업
0 3 * * * /home/유저이름/kkabi/deploy/backup.sh >> /home/유저이름/kkabi/logs/backup.log 2>&1
```

### GCP 운영 팁

1. **인스턴스 재시작 후 자동 실행**: systemd enable 해놨으므로 VM 재부팅 시 자동으로 봇이 올라온다.

2. **Claude Code 인증 유지**: `claude login --method=manual`로 한 인증은 토큰이 만료될 수 있다. 만료 시 봇이 "인증 만료" 에러를 텔레그램으로 알려주므로, SSH 접속해서 재인증하면 된다.

3. **비용 관리**: e2-micro (무료 티어)로도 돌아가지만, Claude Code + MCP 서버가 메모리를 좀 먹으므로 e2-small (2GB RAM) 이상 추천. 월 ~$15 수준.

4. **디스크**: 기본 10GB면 충분하지만, 파일 업로드를 많이 쓸 계획이면 늘려두기.

5. **로그 관리**: `journalctl`이 디스크를 먹으므로 주기적 정리 필요.
   ```bash
   sudo journalctl --vacuum-time=7d
   ```

---

## macOS 배포

macOS에서는 **launchd**로 항상 실행한다. 코드는 GCP와 100% 동일하고 데몬 등록만 다르다.

### 설치

```bash
# 프로젝트 클론
cd ~
git clone <repo-url> kkabi
cd kkabi

# 가상환경
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 설정
cp config.example.json config.json
nano config.json  # 봇 토큰, 사용자 ID 입력

# 디렉토리 생성
mkdir -p data/memory/logs data/memory/projects data/uploads logs
```

### launchd 서비스 (deploy/com.kkabi.plist)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kkabi</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/유저이름/kkabi/venv/bin/python</string>
        <string>/Users/유저이름/kkabi/main.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/유저이름/kkabi</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/유저이름/kkabi/logs/stdout.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/유저이름/kkabi/logs/stderr.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/Users/유저이름/.npm-global/bin</string>
        <key>GITHUB_TOKEN</key>
        <string>ghp_xxxxx</string>
    </dict>
</dict>
</plist>
```

### 서비스 등록 및 관리

```bash
# plist 복사
cp deploy/com.kkabi.plist ~/Library/LaunchAgents/

# 서비스 등록 (로그인 시 자동 시작)
launchctl load ~/Library/LaunchAgents/com.kkabi.plist

# 상태 확인
launchctl list | grep kkabi

# 중지
launchctl unload ~/Library/LaunchAgents/com.kkabi.plist

# 재시작
launchctl unload ~/Library/LaunchAgents/com.kkabi.plist
launchctl load ~/Library/LaunchAgents/com.kkabi.plist

# 로그 확인
tail -f ~/kkabi/logs/stdout.log
tail -f ~/kkabi/logs/stderr.log
```

### macOS 주의사항

1. **슬립 방지**: 맥이 잠들면 봇이 멈춘다. 항상 실행하려면:
   - 시스템 설정 → 에너지 절약 → "네트워크 접근 시 깨우기" 활성화
   - 또는 `caffeinate -s &`로 슬립 방지 (임시)
   - 서버 용도면 `pmset` 설정 변경:
     ```bash
     sudo pmset -a sleep 0          # 잠들지 않음
     sudo pmset -a disablesleep 1   # 완전 비활성화
     ```

2. **Claude Code 인증**: macOS에서는 브라우저가 있으므로 `claude login`만 하면 자동 인증.

3. **백업**: iCloud Drive나 로컬 Time Machine 활용.
   ```bash
   # data/ 를 iCloud에 동기화
   rsync -av ~/kkabi/data/ ~/Library/Mobile\ Documents/com~apple~CloudDocs/kkabi-backup/
   ```

---

## Windows 배포

Windows는 두 가지 방법이 있다. **WSL2 추천** (Linux와 동일하게 쓸 수 있어서).

### 방법 A: WSL2 사용 (추천)

WSL2 안에서 Linux와 동일하게 설치하고, systemd로 데몬 등록한다.

```powershell
# 1. WSL2 설치 (PowerShell 관리자 권한)
wsl --install -d Ubuntu

# 2. WSL 접속
wsl

# 3. 이후는 Linux(GCP)와 100% 동일
cd ~
git clone <repo-url> kkabi
cd kkabi
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# ... (GCP 설치 과정 그대로)
```

**WSL2에서 systemd 활성화:**
```bash
# /etc/wsl.conf 편집
sudo nano /etc/wsl.conf
```
```ini
[boot]
systemd=true
```
```bash
# WSL 재시작 (PowerShell에서)
wsl --shutdown
wsl
```

이후 systemd 서비스 등록은 GCP와 동일:
```bash
sudo cp deploy/kkabi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kkabi
sudo systemctl start kkabi
```

**Windows 부팅 시 WSL 자동 시작:**
```
# 시작 프로그램에 추가 (shell:startup 폴더에 .vbs 파일)
```

`deploy/start-wsl.vbs`:
```vbs
Set ws = CreateObject("Wscript.Shell")
ws.Run "wsl -d Ubuntu", 0
```
이 파일을 `shell:startup` 폴더에 넣으면 Windows 부팅 시 WSL이 백그라운드에서 시작되고, systemd가 깨비를 자동 실행한다.

---

### 방법 B: 네이티브 Windows (WSL 없이)

WSL을 쓸 수 없는 환경이라면 작업 스케줄러를 사용한다.

```powershell
# 설치
cd %USERPROFILE%
git clone <repo-url> kkabi
cd kkabi
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
cp config.example.json config.json
# config.json 편집
```

**작업 스케줄러 등록 (deploy/install-windows.bat):**
```bat
@echo off
echo === Kkabi Windows 설치 ===

:: 작업 스케줄러에 등록 (로그온 시 자동 시작, 크래시 시 재시작)
schtasks /create ^
  /tn "Kkabi" ^
  /tr "\"%USERPROFILE%\kkabi\venv\Scripts\python.exe\" \"%USERPROFILE%\kkabi\main.py\"" ^
  /sc onlogon ^
  /rl highest ^
  /f

:: 지금 바로 시작
schtasks /run /tn "Kkabi"

echo.
echo 완료! 작업 스케줄러에서 "Kkabi" 확인하세요.
echo 중지: schtasks /end /tn "Kkabi"
echo 삭제: schtasks /delete /tn "Kkabi" /f
```

**Windows 주의사항:**

1. **Claude Code on Windows**: Claude Code는 공식적으로 WSL 사용을 권장한다. 네이티브 Windows에서 돌리면 일부 MCP 서버가 동작하지 않을 수 있음.
2. **경로**: Windows 경로(`C:\Users\...`)와 config.json의 `work_dir`이 맞는지 확인.
3. **PowerShell vs CMD**: `main.py` 실행 시 환경변수가 잡히는지 확인. `GITHUB_TOKEN` 등은 시스템 환경변수로 등록 권장.

---

## 크로스 플랫폼 요약

| 항목 | GCP (Linux) | macOS | Windows (WSL2) | Windows (네이티브) |
|------|-------------|-------|----------------|-------------------|
| 코드 | 동일 | 동일 | 동일 | 동일 |
| 데몬 | systemd | launchd | systemd | 작업 스케줄러 |
| 자동 시작 | systemctl enable | RunAtLoad | systemctl enable | schtasks /sc onlogon |
| 크래시 복구 | Restart=always | KeepAlive | Restart=always | 수동 재실행 |
| Claude Code | ✅ | ✅ | ✅ | ⚠️ WSL 권장 |
| MCP 서버 | ✅ | ✅ | ✅ | ⚠️ 일부 제한 |
| 슬립 문제 | 없음 | ⚠️ 설정 필요 | 없음 | ⚠️ 절전 설정 |
| 추천도 | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐ |

---

## 테스트 시나리오

1. "안녕" → Claude 응답 확인
2. "아까 그거 뭐였지?" → 대화 맥락 참조
3. `/cd ~/myproject` → "파일 목록 보여줘" → 해당 디렉토리 기준
4. 텔레그램에 .py 파일 전송 → "이 코드 리뷰해줘" → 파일 기반 응답
5. `/getfile ~/projects/output.txt` → 파일 수신
6. `/cron add "*/5 * * * *" "현재 시각 알려줘"` → 5분마다 알림
7. "Python 좋아하는 거 기억해둬" → `/memory` → 기록 확인
8. `/system 존댓말로 답변해` → 이후 응답 변화
9. `/forget` → 맥락 초기화 확인
10. `/history` → 실행 기록 확인
11. "이 폴더 삭제해줘" → ⚠️ 승인 키보드 표시 → ❌ 취소 → 실행 안 됨
12. 오래 걸리는 작업 → "⏳ 처리 중... (30초 경과)" 업데이트 확인 → `/cancel` → 작업 중단
13. 메시지 3개 빠르게 전송 → "📋 대기 중 (앞에 2개)" → 순서대로 처리

---

## 나중에 확장 (지금은 안 만듦)

- [ ] 웹훅 수신 (GitHub PR → 자동 리뷰, 서버 알림 → 자동 분석. FastAPI 서버 필요)
- [ ] 스마트 알림 (on_change: 상태 변할 때만, digest: 하루 1번 모아서)
- [ ] 헬스체크 + GCP Uptime Check 연동
- [ ] 명령어 별칭 (/alias add 배포 "빌드하고 푸시해줘")
- [ ] 음성 메시지 (Whisper STT → Claude)
- [ ] 웹 대시보드 (FastAPI)
- [ ] 프로젝트 프리셋 (`/project myapp`)
- [ ] 멀티 세션 (동시 작업)
- [ ] 이미지 입력 (스크린샷 분석)

---

## 프로젝트 구조

```
kkabi/
├── CLAUDE.md
├── config.example.json
├── config.json              ← (gitignore)
├── requirements.txt
├── main.py                  ← 엔트리포인트 (봇 + 스케줄러)
├── bot/
│   ├── __init__.py
│   ├── handlers.py          ← 텔레그램 명령어 핸들러
│   ├── sender.py            ← 메시지 분할, "처리 중" 표시, 진행 상태 업데이트
│   ├── file_transfer.py     ← 파일 업/다운로드
│   └── safety.py            ← 위험 명령 승인 (인라인 키보드)
├── claude/
│   ├── __init__.py
│   ├── runner.py            ← Claude CLI 호출 + 프로세스 추적 (cancel용)
│   ├── context.py           ← 맥락 + 메모리 + 시스템프롬프트 조립
│   ├── retry.py             ← 한도 초과 재시도 큐
│   └── queue.py             ← 동시 실행 큐 (asyncio.Queue)
├── scheduler/
│   ├── __init__.py
│   └── cron.py              ← APScheduler 크론잡
├── memory/
│   ├── __init__.py
│   ├── manager.py           ← MEMORY.md 읽기/쓰기, 일별 로그
│   └── prompts.py           ← 메모리 프롬프트 템플릿
├── db/
│   ├── __init__.py
│   └── store.py             ← SQLite
├── data/                    ← (gitignore)
│   ├── assistant.db
│   ├── crons.json
│   ├── system_prompt.txt
│   ├── uploads/
│   └── memory/
│       ├── MEMORY.md
│       ├── logs/
│       └── projects/
├── logs/
├── scripts/
│   └── setup-mcp.sh
├── deploy/
│   ├── kkabi.service              ← Linux systemd
│   ├── com.kkabi.plist            ← macOS launchd
│   ├── install.sh                 ← Linux/GCP 설치
│   ├── install-mac.sh             ← macOS 설치
│   ├── install-windows.bat        ← Windows 설치
│   ├── start-wsl.vbs              ← Windows 부팅 시 WSL 자동 시작
│   └── backup.sh                  ← GCS 백업
└── .gitignore
```

## 의존성 (requirements.txt)

```
python-telegram-bot>=20.0
apscheduler>=3.10
aiosqlite>=0.19
```