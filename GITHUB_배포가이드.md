# GitHub 배포 + 매일 8시 자동 업데이트 가이드

목표: 깃허브에 올려서 **고정 링크(GitHub Pages)** 로 보고, **매일 오전 8시 자동으로 전날 기사 갱신**.

> ⚠️ 저는 bb의 깃허브 계정 권한이 없어 대신 push할 수 없습니다.
> 아래 명령을 그대로 복사해 실행하시면 됩니다(bb는 평소 git push 하시니 익숙하실 거예요).

---

## 1. 올릴 파일 준비
`youthpolicy\` 폴더에 아래가 있으면 됩니다(대부분 이미 있음):
```
index.html              ← 대시보드 (★파일명 반드시 index.html)
tasks.json              ← 375과제 데이터
daily_news.json         ← 방금 수집한 실데이터(46건). 그대로 올리면 초기 화면이 됩니다
collect_news.py         ← 수집 스크립트 (Action이 실행)
requirements.txt
.gitignore              ← .env / news.db 제외 (키 유출 방지)
.github\workflows\daily-policy-radar.yml   ← 자동 스케줄
```
`.github\workflows\` 폴더를 만들고 `daily-policy-radar.yml`을 그 안에 넣으세요.

> `.env` 는 절대 올리지 마세요. (`.gitignore`가 막아주지만 확인 권장)
> 깃허브에선 키를 `.env` 대신 **저장소 Secrets**로 넣습니다(3단계).

## 2. 저장소 생성 + 푸시 (PowerShell)
```powershell
cd C:\Users\baebo\youthpolicy

git init
git add .
git commit -m "청년정책 일일 레이더 대시보드"
git branch -M main

# 깃허브에서 빈 저장소(youthpolicy) 먼저 만든 뒤 주소 연결
git remote add origin https://github.com/baebong3/youthpolicy.git
git push -u origin main
```

## 3. Actions Secrets 등록 (자동 수집용 키)
저장소 → **Settings → Secrets and variables → Actions → New repository secret** 에서 3개 등록:
- `NAVER_ID`      = 네이버 Client ID
- `NAVER_SECRET`  = 네이버 Client Secret
- `ANTHROPIC_API_KEY` = (선택) sk-ant-... 있으면 분류 정밀↑

## 4. GitHub Pages 켜기 (고정 링크 생성)
저장소 → **Settings → Pages → Source: `main` / `(root)`** 선택 → Save.
1~2분 뒤 링크 생성:
```
https://baebong3.github.io/youthpolicy/
```
이게 **bb가 매일 볼 HTML 링크**입니다. 북마크해두세요.

## 5. 자동 스케줄 동작 확인
- 워크플로는 **매일 08:00(KST)** 자동 실행되어 전날~당일 새벽 기사를 수집하고
  `daily_news.json`을 커밋합니다 → Pages가 자동 반영.
- 지금 바로 테스트: 저장소 → **Actions → daily-policy-radar → Run workflow**(수동 실행).
  초록색 체크가 뜨고 `daily_news.json`이 갱신되면 성공.
- 이후엔 링크 들어가서 **새로고침(F5)** 만 하면 그날 아침 데이터가 보입니다.

---

## 동작 요약
```
매일 08:00  GitHub Actions
   → collect_news.py 실행(네이버 검색, '청년' 포함 기사만)
   → daily_news.json 커밋
   → GitHub Pages 자동 반영
   → https://baebong3.github.io/youthpolicy/  에서 F5
```

## 참고
- 로컬에서 수동으로 돌리고 싶을 때는 기존처럼 `python collect_news.py` + 로컬서버.
- Action 로그는 저장소 Actions 탭에서 실행별로 확인 가능(수집 건수, 에러 등).
- 매일 새 db로 수집하므로 항상 "최근 기사" 기준입니다(누적 이력은 저장 안 함).
