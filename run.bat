@echo off
chcp 65001 > nul
title 병동 인수인계 시스템

echo.
echo ==============================================
echo   병동 인수인계 시스템 (Flask + MySQL)
echo ==============================================
echo.

:: ── Python 설치 확인 ────────────────────────────
python --version > nul 2>&1
if errorlevel 1 (
    echo [오류] Python 이 설치되어 있지 않거나 PATH 에 없습니다.
    echo.
    echo  1. https://www.python.org/downloads/ 에서 Python 3.11 이상 설치
    echo  2. 설치 화면에서 "Add Python to PATH" 반드시 체크
    echo  3. 설치 완료 후 이 파일을 다시 실행하세요.
    echo.
    pause
    exit /b 1
)

:: ── .env 파일 확인 ──────────────────────────────
if not exist .env (
    echo [경고] .env 파일이 없습니다.
    echo.
    echo  .env.example 을 복사해서 .env 를 만들고
    echo  DB 접속 정보를 입력한 뒤 다시 실행하세요.
    echo.
    echo  방법: 탐색기에서 .env.example 복사 후 이름을 .env 로 변경
    echo        그 다음 메모장으로 열어 비밀번호 등 수정
    echo.
    pause
    exit /b 1
)

:: ── 가상환경 생성 (최초 1회) ────────────────────
if not exist venv (
    echo [1/3] 가상환경 생성 중...
    python -m venv venv
    if errorlevel 1 (
        echo [오류] 가상환경 생성에 실패했습니다.
        pause
        exit /b 1
    )
    echo       완료!
    echo.
)

:: ── 가상환경 활성화 ─────────────────────────────
call venv\Scripts\activate.bat

:: ── 패키지 설치 (venv 에 없으면 자동 설치) ───────
python -c "import flask" > nul 2>&1
if errorlevel 1 (
    echo [2/3] 필요 패키지 설치 중... (최초 1회, 잠시 기다려주세요)
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [오류] 패키지 설치에 실패했습니다.
        pause
        exit /b 1
    )
    echo       완료!
    echo.
) else (
    echo [2/3] 패키지 확인 완료
)

:: ── 서버 시작 ───────────────────────────────────
echo [3/3] Flask 서버 시작 중...
echo.
echo  접속 주소 : http://localhost:5000
echo  종료 방법 : 이 창에서 Ctrl+C  →  배치파일 종료 Y
echo.
echo ──────────────────────────────────────────────

:: 브라우저 자동 오픈 (2초 후)
start "" /b cmd /c "timeout /t 2 > nul && start http://localhost:5000"

python run.py

echo.
echo 서버가 종료되었습니다.
pause
