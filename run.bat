@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [청년정책 일일 레이더] 뉴스 수집 시작...
python collect_news.py
echo.
echo 완료. daily_news.json 갱신됨. 대시보드를 새로고침하세요.
echo (대시보드 보기: 같은 폴더에서  python -m http.server 8000  실행 후
echo  브라우저에서 http://localhost:8000/index.html )
pause
