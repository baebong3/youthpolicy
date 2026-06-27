"""
seed_archive.py — news_archive.json 을 '빈 상태'로 초기화(리셋)
(가짜/시연 데이터를 만들지 않습니다. 실데이터는 collect_news.py가 매일 누적합니다.)

용도:
  - 기존 가짜 시드 아카이브를 깨끗이 비울 때
  - 처음 배포할 때 빈 아카이브 파일을 만들 때

실행:  python seed_archive.py            (news_archive.json 을 빈 파일로 생성/초기화)
주의:  이미 실데이터가 쌓인 news_archive.json 이 있으면 덮어쓰므로,
       리셋이 목적일 때만 실행하세요. (백업: copy news_archive.json news_archive.bak.json)
"""
import json, os
from datetime import date

OUT = 'news_archive.json'

empty = {
    'meta': {
        'generated': date.today().isoformat(),
        'total': 0,
        'demo_backfill': False,                       # 가짜 데이터 아님
        'sources': ['네이버 뉴스 API', '정책브리핑(korea.kr)', '연합뉴스 RSS'],
    },
    'items': []
}

if os.path.exists(OUT):
    # 안전장치: 실데이터가 들어있으면 확인 메시지
    try:
        cur = json.load(open(OUT, encoding='utf-8'))
        n = len(cur.get('items', []))
        if n > 0:
            print(f"⚠️  현재 {OUT} 에 {n}건이 있습니다. 백업을 권장합니다(news_archive.bak.json).")
    except Exception:
        pass

json.dump(empty, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"{OUT} 초기화 완료 (items: 0). 이제 python collect_news.py 로 실데이터를 채우세요.")
