"""
collect_news.py — 청년정책 일일 뉴스 수집·매칭·감성분류 파이프라인
2026년 중앙행정기관 청년정책 분석·평가 연구 (국무조정실) / (주)서던포스트

아키텍처 (med-tourism radar 패턴 재사용)
  네이버 뉴스 API + 정책브리핑(korea.kr) RSS + 연합뉴스 RSS
    → 375개 과제 키워드 인덱스 매칭
    → SQLite(news.db) 증분 저장·중복제거
    → Claude Haiku 분류(정책 매핑 + 긍/부정/중립 + 신규정책 탐지)
    → daily_news.json  (대시보드 ⑥ 일일 레이더 모듈이 fetch)

매일 1회 실행(GitHub Actions / Windows 작업 스케줄러 / cron).
환경변수: NAVER_ID, NAVER_SECRET, ANTHROPIC_API_KEY

의존: requests, feedparser, anthropic   (pip install requests feedparser anthropic)
"""
import os, re, json, sqlite3, hashlib, html, time
from datetime import date, datetime, timedelta
from collections import Counter, defaultdict

# .env 파일이 있으면 자동 로딩 (NAVER_ID / NAVER_SECRET / ANTHROPIC_API_KEY)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB = 'news.db'
TASKS = 'tasks.json'                # parse_taskcards.py 산출물
OUT = 'daily_news.json'
OUT_ARCHIVE = 'news_archive.json'
NAVER_ID = os.environ.get('NAVER_ID')
NAVER_SECRET = os.environ.get('NAVER_SECRET')
ANTHROPIC_KEY = (os.environ.get('ANTHROPIC_API_KEY') or '').strip()
# placeholder나 한글이 남아있어도 안전하도록, 형식이 맞을 때만 Claude 사용
USE_CLAUDE = ANTHROPIC_KEY.startswith('sk-ant-')

# ───────────────────────── 1. 키워드 인덱스 ─────────────────────────
STOP = set('지원 사업 운영 강화 확대 제공 추진 청년 정책 및 등 통한 위한 관련'.split())

def build_index(tasks):
    """과제명에서 핵심 명사 추출 → {키워드: [과제…]} 역색인"""
    idx = defaultdict(list)
    for t in tasks:
        toks = re.findall(r'[가-힣A-Za-z]{2,}', t['name'])
        kws = [w for w in toks if w not in STOP and len(w) >= 2]
        t['_kw'] = set(kws[:6])
        for w in t['_kw']:
            idx[w].append(t)
    return idx

def match_policy(title, tasks, idx=None):
    """뉴스 제목 ↔ 과제 매칭. 한글 띄어쓰기 차이에 강하도록 '제목 토큰이 과제명(공백제거)에
    포함되는지'를 확인 + 부처명 일치 보너스. 2점 이상일 때만 채택."""
    ttoks = set(w for w in re.findall(r'[가-힣A-Za-z]{2,}', title) if w not in STOP)
    score = Counter()
    for t in tasks:
        name = re.sub(r'\s+', '', t['name'])
        s = 0
        for w in ttoks:
            if w in name:
                s += 2 if len(w) >= 4 else 1   # 4자 이상 핵심어는 가중치 2(단일로도 채택 가능)
        if t.get('dept') and t['dept'] in title:
            s += 2                              # 부처명 일치 보너스
        if s:
            score[t['code']] = s
    if not score:
        return None
    best, n = score.most_common(1)[0]
    return best if n >= 2 else None   # 가중점수 2 이상

# ───────────────────────── 2. 수집기 ─────────────────────────
def fetch_naver(query, max_results=1000):
    """네이버 검색 API는 쿼리당 최대 1000건(start 1~1000, display 100)까지 제공.
    pubDate가 들어와 며칠/몇 주 전 기사까지 한 번에 긁어옴(첫 실행 백필용)."""
    import requests
    if not (NAVER_ID and NAVER_SECRET):
        return []
    out = []
    for start in range(1, min(max_results, 1000) + 1, 100):
        try:
            r = requests.get('https://openapi.naver.com/v1/search/news.json',
                headers={'X-Naver-Client-Id': NAVER_ID, 'X-Naver-Client-Secret': NAVER_SECRET},
                params={'query': query, 'display': 100, 'start': start, 'sort': 'date'}, timeout=10)
            items = r.json().get('items', [])
        except Exception:
            break
        if not items:
            break
        for it in items:
            t = re.sub(r'<[^>]+>', '', html.unescape(it['title']))
            out.append({'title': t, 'url': it['originallink'] or it['link'],
                        'source': '네이버뉴스', 'pubdate': it.get('pubDate', '')})
        time.sleep(0.1)
        if len(items) < 100:
            break
    return out

def fetch_rss(url, source):
    import feedparser
    out = []
    for e in feedparser.parse(url).entries:
        out.append({'title': re.sub(r'<[^>]+>', '', html.unescape(e.title)),
                    'url': e.link, 'source': source,
                    'pubdate': e.get('published', '')})
    return out

def collect_raw():
    """수집 대상: 청년정책 핵심 키워드 다발(쿼리당 최대 1000건) + 정책브리핑/연합뉴스 RSS.
    첫 실행 시 받을 수 있는 최근 기사를 최대한 긁고, 이후 매일 증분 누적."""
    raw = []
    queries = ['청년정책', '청년 일자리', '청년 주거', '청년 월세', '청년 전세',
               '청년 취업', '청년 창업', '청년 인턴', '청년 지원', '청년 장학금',
               '청년 도약계좌', '청년 내일채움', '청년 마음건강', '청년 자산형성']
    for q in queries:
        raw += fetch_naver(q); time.sleep(0.15)
    raw += fetch_rss('https://www.korea.kr/rss/policy.xml', '정책브리핑')
    raw += fetch_rss('https://www.yna.co.kr/rss/news.xml', '연합뉴스')
    return raw

# ───────────────────────── 3. 저장(SQLite 증분) ─────────────────────────
def init_db():
    c = sqlite3.connect(DB)
    c.execute('''CREATE TABLE IF NOT EXISTS news(
        id TEXT PRIMARY KEY, date TEXT, title TEXT, url TEXT, source TEXT,
        code TEXT, field TEXT, dept TEXT, sentiment TEXT, is_new INTEGER)''')
    c.commit(); return c

def upsert(c, rows):
    new = 0
    for r in rows:
        try:
            c.execute('INSERT OR IGNORE INTO news VALUES(?,?,?,?,?,?,?,?,?,?)',
                (r['id'], r['date'], r['title'], r['url'], r['source'],
                 r.get('code'), r.get('field'), r.get('dept'),
                 r.get('sentiment'), int(r.get('is_new', 0))))
            new += c.total_changes
        except Exception:
            pass
    c.commit(); return new

# ───────────────────── 4. Claude 분류(감성 + 신규탐지) ─────────────────────
SENT_POS = re.compile(r'호응|만족|성과|확대|우수|개선|증가|호평|효과|선정')
SENT_NEG = re.compile(r'불만|논란|지적|비판|저조|미흡|소진|사각지대|실효성|복잡|부진')

def classify_local(title):
    """API 미사용 시 키워드 휴리스틱(폴백)"""
    if SENT_NEG.search(title): return '부정'
    if SENT_POS.search(title): return '긍정'
    return '중립'

def classify_claude(batch, tasks):
    """Claude Haiku 일괄 분류 — 정책매핑·감성·신규여부 JSON 반환"""
    import anthropic
    cli = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    names = '\n'.join(f"{t['code']} {t['name']}" for t in tasks)
    titles = '\n'.join(f"{i}. {b['title']}" for i, b in enumerate(batch))
    prompt = (f"다음은 2026년 청년정책 시행계획 과제 목록입니다:\n{names}\n\n"
              f"아래 뉴스 제목들을 각각 분류하세요:\n{titles}\n\n"
              "각 뉴스에 대해 JSON 배열로만 응답: "
              '[{"i":0,"code":"매칭과제번호 또는 null","sentiment":"긍정/부정/중립",'
              '"is_new":true/false}] '
              "(is_new=기존 과제목록에 없는 신규 청년정책이면 true). 다른 말 없이 JSON만.")
    msg = cli.messages.create(model='claude-haiku-4-5-20251001', max_tokens=2000,
                              messages=[{'role': 'user', 'content': prompt}])
    txt = re.sub(r'```json|```', '', msg.content[0].text).strip()
    return json.loads(txt)

# ───────────────────────── 5. 일일 산출 ─────────────────────────
def export_archive(c):
    """news.db 전체 → news_archive.json 으로 병합 누적(기존 항목 보존, id 기준 중복제거).
    주/월/연 리포트가 이 파일을 읽음. 시드(시연용 1년)와 실데이터가 함께 쌓임."""
    rows = c.execute('SELECT date,title,url,source,code,field,dept,sentiment,is_new FROM news').fetchall()
    new_items = [{'id': hashlib.md5((str(code)+title).encode()).hexdigest()[:10],
                  'date': d, 'title': title, 'url': url, 'source': src,
                  'code': code, 'field': field, 'dept': dept,
                  'sentiment': sent or '중립', 'is_new': int(isnew or 0)}
                 for d, title, url, src, code, field, dept, sent, isnew in rows]
    merged = {}
    demo = False
    if os.path.exists(OUT_ARCHIVE):
        try:
            arch = json.load(open(OUT_ARCHIVE, encoding='utf-8'))
            demo = bool(arch.get('meta', {}).get('demo_backfill'))
            for it in arch.get('items', []):
                merged[it['id']] = it
        except Exception:
            pass
    for it in new_items:
        merged[it['id']] = it
    items = sorted(merged.values(), key=lambda x: x['date'], reverse=True)
    dates = [i['date'] for i in items] or [date.today().isoformat()]
    meta = {'generated': date.today().isoformat(), 'span_start': min(dates), 'span_end': max(dates),
            'total': len(items), 'demo_backfill': demo,
            'sources': ['정책브리핑(korea.kr)', '네이버 뉴스 API', '연합뉴스 RSS']}
    json.dump({'meta': meta, 'items': items}, open(OUT_ARCHIVE, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f"news_archive.json 누적: 총 {len(items)}건 ({meta['span_start']}~{meta['span_end']})")


def build_daily(c, tasks):
    today = date.today().isoformat()
    rows = c.execute('SELECT date,title,url,source,code,field,dept,sentiment,is_new '
                     'FROM news WHERE date>=? ORDER BY date DESC',
                     ((date.today() - timedelta(days=2)).isoformat(),)).fetchall()
    items, new_pol = [], []
    code2 = {t['code']: t for t in tasks}
    for d, title, url, src, code, field, dept, sent, isnew in rows:
        if isnew:
            new_pol.append({'title': title, 'dept': dept or '-', 'field': field or '-',
                            'date': d, 'summary': ''})
            continue
        if not code: continue
        items.append({'id': hashlib.md5((code+title).encode()).hexdigest()[:10],
                      'date': d, 'title': title, 'source': src, 'url': url,
                      'code': code, 'field': code2[code]['field'],
                      'dept': code2[code]['dept'], 'sentiment': sent or '중립'})
    sc = Counter(i['sentiment'] for i in items)
    neg = Counter(i['code'] for i in items if i['sentiment'] == '부정')
    watch = [{'code': cd, 'name': code2[cd]['name'][:22], 'dept': code2[cd]['dept'],
              'field': code2[cd]['field'], 'neg': n} for cd, n in neg.most_common(8)]
    fld_neg = Counter(i['field'] for i in items if i['sentiment'] == '부정')
    top = fld_neg.most_common(1)[0][0] if fld_neg else '-'
    brief = (f"{today} 기준 청년정책 뉴스 {len(items)}건 수집"
             f"(긍정 {sc['긍정']}·부정 {sc['부정']}·중립 {sc['중립']}). "
             f"신규 정책 {len(new_pol)}건 탐지. 부정 뉴스는 '{top}' 분야 집중 → 체감도 모니터링 강화 필요.")
    out = {'meta': {'date': today, 'collected': len(items),
                    'sentiment': {'긍정': sc['긍정'], '부정': sc['부정'], '중립': sc['중립']},
                    'new_count': len(new_pol),
                    'sources': ['정책브리핑(korea.kr)', '네이버 뉴스 API', '연합뉴스 RSS'],
                    'demo': False},
           'brief': brief, 'new_policies': new_pol, 'watch': watch,
           'items': items}
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f"daily_news.json 생성: {len(items)}건 / 신규 {len(new_pol)} / 주의 {len(watch)}")

def parse_pubdate(s):
    """네이버 pubDate(RFC822: 'Mon, 26 Jun 2026 10:00:00 +0900') → 'YYYY-MM-DD'. 실패 시 오늘."""
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).date().isoformat()
    except Exception:
        return date.today().isoformat()

def main():
    tasks = json.load(open(TASKS, encoding='utf-8'))
    idx = build_index(tasks)
    c = init_db()
    raw = collect_raw()
    # 매칭 + 중복 키
    staged = []
    for r in raw:
        title = r['title']
        code = match_policy(title, tasks, idx)
        rid = hashlib.md5((title + r['url']).encode()).hexdigest()[:12]
        staged.append({'id': rid, 'date': parse_pubdate(r.get('pubdate', '')), 'title': title,
                       'url': r['url'], 'source': r['source'], 'code': code})
    # 분류
    if USE_CLAUDE:
        for k in range(0, len(staged), 20):
            for res in classify_claude(staged[k:k+20], tasks):
                s = staged[k + res['i']]
                s['sentiment'] = res.get('sentiment', '중립')
                s['is_new'] = res.get('is_new', False)
                if res.get('code'): s['code'] = res['code']
    else:
        if ANTHROPIC_KEY:  # 키는 있는데 형식이 틀린 경우(예: placeholder/한글) 안내
            print("※ ANTHROPIC_API_KEY 형식이 올바르지 않아 키워드 방식으로 폴백합니다. (sk-ant- 로 시작하는지 확인)")
        for s in staged:
            s['sentiment'] = classify_local(s['title'])
            s['is_new'] = (s['code'] is None and '청년' in s['title']
                           and re.search(r'신설|신규|시행|도입|출시', s['title']) is not None)
    # 매칭/신규 + 제목에 '청년'이 반드시 포함된 기사만 저장
    keep = [s for s in staged if ('청년' in s['title']) and (s.get('code') or s.get('is_new'))]
    for s in keep:
        t = next((x for x in tasks if x['code'] == s.get('code')), None)
        s['field'] = t['field'] if t else None
        s['dept'] = t['dept'] if t else None
    upsert(c, keep)
    build_daily(c, tasks)
    export_archive(c)

if __name__ == '__main__':
    main()
