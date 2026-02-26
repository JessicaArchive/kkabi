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
