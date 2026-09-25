# -*- coding: utf-8 -*-
"""
핵심 이슈 주제 추출 - 여러 기사 제목에 겹쳐 나오는 주제어로 그날의 헤드라인을 만듦

  1) 제목을 낱말로 나누고 조사를 떼어 냄(요약은 보조로 약하게 반영)
  2) 일반어(청년 · 정책 · 지원 · 확대 · 개최 등)는 제외, 숫자는 단위가 붙은 경우만 허용(112곳 · 40% 등)
  3) 주제어 1 = 여러 기사 제목에 걸쳐 나온 말 중 (기사 점수 가중) 합이 가장 큰 말
     주제어 2 · 3 = 주제어 1이 나온 기사 제목들에서 함께 자주 나온 말
  4) 대표 기사 제목에서 주제어들이 걸친 구간을 잘라 헤드라인으로 씀
     예) 「연봉 3000만 청년도 월세지원」 → 「연봉 3000만 청년도 월세지원」
     구간이 너무 길거나 어색하면 「주제어 1 · 주제어 2」로 대체

사람이 정한 헤드라인이 있으면 그것을 우선함 : radar2/headline.json
  {"date": "2026-09-25", "중앙": "청년 월세지원 소득기준 상향", "지역": "청년의 날 지역 행사 집중"}
  (date가 오늘과 같을 때만 적용)
"""
import json, os, re
from collections import Counter, defaultdict

JOSA = re.compile(r'(에서는|으로는|에서|으로|까지|부터|에게|이나|이다|하는|하고|했다|한다|된다|하며|했음|됐음|함|됨|음|임|된|은|는|이|가|을|를|의|에|로|과|와|도|만)$')
UNIT = re.compile(r'^\d[\d,.]*(곳|명|건|개|개국|개소|억|조|만명|만|%|배|위)$')

STOP = set('''
청년 청년들 청년층 청년의 청년에 청년이 청년을 청년과 청년정책 청년 정책 정책 청춘 대학생 mz 2030 20대 30대
단독 종합 속보 포토 영상 칼럼 사설 인터뷰 기고 동정 인사 기자수첩 오피니언 시론 기획 르포
기사 관련 대한 위해 통해 대해 이번 올해 지난해 지난 오늘 내년 최근 가장 모든 이상 이하 가운데 최대 최초 최고
확대 개최 추진 강화 지원 발표 증가 감소 선정 협력 시대 넘어 최다 성료 개막 체결 참가 운영 진행 마련 도입 시행
나선다 나서 넓힌다 넓혀 잡아라 쓴다 썼다 쏠린 몰린 뜬다 뜨는 키워야 키운다 달성 돌파 기록 전망 예정 계획 효과
본격 시동 탄력 청신호 눈길 기대 주목 모색 해법 변화 활성화 가능 필요 문제 방안 길 열어야 모집 접수 신청 대상 참여자
센터 사업 행사 프로그램 서비스 산업 시장 기관 기업 협약 mou 업무협약 뉴스 신문 일보 지역 전국 시민 주민 도민 구민 군민
취임 발의 선임 임명 육성 부의장 의장 의원 대표 회장 원장 장관 교수 군수 구청장 이사장 위원장 사장 지정 확장 개발 우수 신규 성공 조성 완료 공개 오픈 선보여 선보인 제공 활용 연계 소개 공략 겨냥 잇는 잇따라
있다 없다 등 및 또 더 수 것 중 명 곳 건 년 월 일 억 조 만 원 위 차 개 약 첫 새 전 후 내 외 제 기 회 명에 명을
the of and in to for a on with by at from is as
시 군 구 도 시는 군은 구는 도는 시가 군이 구가 도가 시장 도지사 교육감 위촉 개소 개관 성황 마무리 호응
'''.split())


def _words(text):
    for m in re.finditer(r'[가-힣A-Za-z0-9][가-힣A-Za-z0-9%·\-]*', text or ''):
        yield m


def _norm_word(w):
    w = w.strip('·-').lower()
    if len(w) > 2:
        w = JOSA.sub('', w)
    return w


def tokens(text):
    out = set()
    for m in _words(text):
        w = _norm_word(m.group(0))
        if len(w) < 2 or w in STOP:
            continue
        if re.search(r'\d', w) and not UNIT.match(w):
            continue
        out.add(w)
    return out


def load_override(root, track, today_s):
    p = os.path.join(root, 'radar2', 'headline.json')
    try:
        d = json.load(open(p, encoding='utf-8'))
        if d.get('date') == today_s and d.get(track):
            return d[track]
    except Exception:
        pass
    return None


def _clean_title(t):
    t = re.sub(r'케이\s*\(K\)\s*-?\s*', 'K-', t or '')                       # 케이(K)-의료관광 → K-의료관광
    t = re.sub(r'\[[^\]]*\]|\([^)]*\)|【[^】]*】', ' ', t)       # [단독] (종합) 등
    t = re.sub(r'[\"“”‘’\'「」『』<>…·,:;!?]|\.{2,}', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


ACTION = set('확대 지정 선정 도입 시행 개정 폐지 허용 완화 강화 급증 감소 증가 개최 출범 체결 추진 논의 발표 신설 확정 중단 재개 돌파'.split())


def _span(title, keys, k1):
    """제목에서 주제어들이 걸친 구간(낱말 단위)을 잘라내고, 바로 뒤 서술어(확대 · 지정 등)가 있으면 붙임"""
    t = _clean_title(title)
    ws = t.split(' ')
    hit = lambda w: _norm_word(w) in keys or any(k in w.lower() for k in keys)
    pos = [i for i, w in enumerate(ws) if hit(w)]
    if not pos:
        return None
    if len(pos) == 1:                                   # 주제어가 하나뿐이면 앞뒤 한 낱말씩
        i = pos[0]
        a, b = max(i - 1, 0), i
    else:
        a, b = min(pos), max(pos)
    while a > 0 and b - a < 5 and len(' '.join(ws[a - 1:b + 1])) <= 30:   # 너무 짧으면 앞 낱말로 맥락 보강
        a -= 1
    words = list(ws[a:b + 1])                           # 조사는 끝 낱말에서만 뗌(중간은 자연스러운 문장 유지)
    if len(words[-1]) > 2:
        words[-1] = JOSA.sub('', words[-1])
    if b + 1 < len(ws) and _norm_word(ws[b + 1]) in ACTION:
        words.append(_norm_word(ws[b + 1]))
    s = ' '.join(w for w in words if w)
    return s if 4 <= len(s) <= 34 else None


def _seg_title(title):
    """제목을 말줄임 · 쉼표 · 하이픈 경계로 나눈 마디 목록(따옴표 · 머리말 제거, 가운뎃점은 유지)"""
    s = re.sub(r'케이\s*\(K\)\s*-?\s*', 'K-', title or '')
    if re.search(r'(\.{2,}|…)\s*$', s):                  # 끝이 잘린 제목 : 잘린 낱말은 버림
        s = re.sub(r'\s*\S*(\.{2,}|…)\s*$', '', s)
    s = re.sub(r'\[[^\]]*\]|\([^)]*\)|【[^】]*】', ' ', s)
    s = re.sub(r'[\"“”‘’\'「」『』<>]', '', s)
    segs = [re.sub(r'\s+', ' ', x).strip(' ·') for x in re.split(r'…|\.{2,}|,| - |\||:|;|!|\?', s)]
    return [x for x in segs if x]


def _fit(seg, lim=60):
    ws = seg.split(' ')
    while len(' '.join(ws)) > lim and len(ws) > 2:
        ws = ws[:-1]
    if len(ws[-1]) > 2:
        ws[-1] = JOSA.sub('', ws[-1]) or ws[-1]
    return ' '.join(ws)


def _story_head(best, story_tokens, lim=46):
    """대표 제목 → 헤드라인 : 주제어가 가장 많은 마디를 중심으로, 앞의 주체 마디(기관 · 지자체명)와
    뒤 마디를 46자 안에서 이어 붙임(말줄임 없이 완결된 마디 단위)"""
    segs = _seg_title(best['title'])
    if not segs:
        return None
    who = re.compile(r'(의원|부의장|의장|대표|회장|원장|병원장|장관|차관|교수|시장|군수|구청장|지사|청장|이사장|위원장|사장|총장)$')
    good = [j for j in range(len(segs)) if not who.search(segs[j])] or list(range(len(segs)))
    full = ', '.join(segs)
    if len(full) <= lim and not any(who.search(x) for x in segs):
        return _fit(full, 60)                              # 제목 전체가 짧으면 그대로(주체가 빠지지 않게)
    i = max(good, key=lambda j: (len(tokens(segs[j]) & story_tokens), -j))
    out = segs[i]
    if i > 0 and not who.search(segs[i - 1]) and len(segs[i - 1]) <= 14 and len(segs[i - 1]) + 2 + len(out) <= lim:
        out = segs[i - 1] + ', ' + out                     # 짧은 앞 마디(주체)는 살림
    for sg in segs[i + 1:]:
        if who.search(sg) or len(out) + 2 + len(sg) > lim:
            break
        out += ', ' + sg
    return _fit(out, 60)


def stories(items, k=5, max_df=0.08):
    """items : 기사(score 포함) → 기사 묶음 k개 [(헤드라인, 기사 목록, 출처 수), ...] (큰 순)

    묶음 : 제목 주제어가 3개 이상(짧은 제목은 2개 이상이면서 절반 이상) 겹치는 기사
    수천 건도 빨리 돌도록 역색인으로 이웃을 한 번만 계산(너무 흔한 낱말은 이웃 판정에서 제외)
    묶음 크기 = 기사 점수 가중 합 × 출처 다양성, 가장 큰 묶음부터 떼어 내며 반복
    """
    docs = [(it, tokens(it['title'])) for it in items if re.search('[가-힣]', it['title'])]
    docs = [(it, tt) for it, tt in docs if len(tt) >= 2]
    n = len(docs)
    if n < 2:
        return []
    df = Counter(t for _, tt in docs for t in tt)
    cap = max(40, int(n * max_df))
    inv = defaultdict(list)
    for i, (_, tt) in enumerate(docs):
        for t in tt:
            if df[t] <= cap:
                inv[t].append(i)
    nb = [set() for _ in range(n)]
    for i, (_, tt) in enumerate(docs):
        c = Counter()
        for t in tt:
            if df[t] <= cap:
                c.update(inv[t])
        for j, m in c.items():
            if j == i:
                continue
            if m >= 3 or (m >= 2 and m / max(min(len(tt), len(docs[j][1])), 1) >= 0.5):
                nb[i].add(j)
    src = lambda o: o.get('media') or o.get('src') or o['url']
    wt = [0.5 + max(it['score'], 0) / 2.0 for it, _ in docs]   # 정책 관련도 높은 기사 묶음을 앞세움
    alive = set(range(n))
    out = []
    while len(out) < k:
        best, best_w = None, 0
        for i in alive:
            st = (nb[i] & alive) | {i}
            if len(st) < 2:
                continue
            media = len(set(src(docs[j][0]) for j in st))
            if media < 2:
                continue
            w = sum(wt[j] for j in st) * (1 + 0.15 * min(media, 20))
            if w > best_w:
                best, best_w = st, w
        if not best:
            break
        story = [docs[j] for j in best]
        cnt = Counter(t for _, ot in story for t in ot)
        story_tokens = {t for t, c in cnt.items() if c >= max(2, len(story) // 3)}
        cut = lambda d: bool(re.search(r'(\.{2,}|…)\s*$', d[0]['title']))
        rep = max(story, key=lambda d: (not cut(d), sum(len(d[1] & o[1]) for o in story if o[0] is not d[0]),
                                        d[0]['score']))
        arts = sorted((o for o, _ in story), key=lambda x: (-x['score'], x['date']))
        arts.remove(rep[0]); arts.insert(0, rep[0])
        media = len(set(src(o) for o in arts))
        out.append((_story_head(rep[0], story_tokens), arts, media))
        alive -= best
    return out


def extract(items):
    """가장 큰 기사 묶음 하나 → (헤드라인, 기사 목록) / 없으면 (None, [])"""
    st = stories(items, 1) if items else []
    return (st[0][0], st[0][1]) if st else (None, [])


def rising(now_items, prev_items, k=8, min_now=3):
    """이번 기간 대비 직전 기간 제목 주제어 기사 수 변화 → [(낱말, 이번, 직전), ...] 증가 폭 큰 순"""
    def df(items):
        c = Counter()
        for it in items:
            c.update(tokens(it['title']))
        return c
    a, b = df(now_items), df(prev_items)
    try:
        import region
        places = {w for v in region.ALIAS.values() for w in v.split()} | set(region.SIDO)
    except Exception:
        places = set()
    ok = lambda w: (not UNIT.match(w) and re.search('[가-힣]', w)
                    and w not in places and re.sub(r'(시|군|도|구)(의회|청)?$', '', w) not in places)
    # 인명(○○○ 의원 · 부의장 · 대표 등 직함 앞 세 글자)과 서술어(~다)는 주제어에서 뺌
    role = re.compile(r'([가-힣]{3})\s*(?:[가-힣]{0,8}\s*)?(의원|부의장|의장|대표|회장|원장|병원장|장관|차관|교수|시장|군수|구청장|지사|청장|이사장|위원장|사장|총장|국장|과장|센터장|씨)')
    names = set()
    for it in now_items:
        for m in role.finditer(it['title']):
            names.add(m.group(1))
        names.update(re.findall(r'([가-힣]{3})\s*[가-힣]*(?:의회|시장|군수)\s*[가-힣]*(?:의장|부의장|의원)', it['title']))
    ok2 = lambda w: ok(w) and w not in names and not w.endswith('다')
    rows = [(w, n, b.get(w, 0)) for w, n in a.items() if n >= min_now and ok2(w)]
    rows.sort(key=lambda r: (-(r[1] - r[2]), -r[1], r[0]))
    rows = [r for r in rows if r[1] > r[2]]
    # 같은 사건의 낱말이 줄줄이 오르지 않도록, 이미 뽑힌 낱말과 늘 함께 나오는 낱말은 건너뜀
    picked, seen_docs = [], []
    for w, n, p in rows:
        docs = {i for i, it in enumerate(now_items) if w in tokens(it['title'])}
        if any(len(docs & d) / max(len(docs), 1) >= 0.6 for d in seen_docs):
            continue
        picked.append((w, n, p)); seen_docs.append(docs)
        if len(picked) >= k:
            break
    return picked
