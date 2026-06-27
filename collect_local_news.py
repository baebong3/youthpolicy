# -*- coding: utf-8 -*-
"""
지자체(광역) 청년정책 뉴스 수집기  ·  (주)서던포스트
- 17개 시·도별로 네이버 뉴스에서 "{시도} 청년" / "{시도} 청년정책" 검색
- 시·도 태그 + 감성분류(긍정/부정/중립) → local_news.json 에 누적 병합(id 기준 history 보존)
- index.html 의 '지자체 정책 레이더' 가 이 파일을 fetch 하여 일/주/월/연 리포트로 환류

필요 환경변수(.env):
  NAVER_ID, NAVER_SECRET         (필수 · 네이버 검색 API)
  ANTHROPIC_API_KEY              (선택 · sk-ant- 로 시작하면 Claude 감성분류, 없으면 키워드 분류)

실행:  python collect_local_news.py
"""
import os, re, json, time, html, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

try:
    from dotenv import load_dotenv; load_dotenv()
except Exception:
    pass

KST = timezone(timedelta(hours=9))
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "local_news.json")

NAVER_ID = os.getenv("NAVER_ID", "").strip()
NAVER_SECRET = os.getenv("NAVER_SECRET", "").strip()
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
USE_CLAUDE = ANTHROPIC_KEY.startswith("sk-ant-")

SIDO = ["서울","부산","대구","인천","광주","대전","울산","세종",
        "경기","강원","충북","충남","전북","전남","경북","경남","제주"]
# 시·도 본명 + 별칭(기사에 자주 쓰이는 표기) → 매칭 정확도 보정
ALIAS = {
    "서울":["서울","서울시","서울특별시"], "부산":["부산","부산시"], "대구":["대구","대구시"],
    "인천":["인천","인천시"], "광주":["광주","광주광역시","광주시"], "대전":["대전","대전시"],
    "울산":["울산","울산시"], "세종":["세종","세종시","세종특별자치시"],
    "경기":["경기","경기도"], "강원":["강원","강원도","강원특별자치도"],
    "충북":["충북","충청북도"], "충남":["충남","충청남도"],
    "전북":["전북","전라북도","전북특별자치도"], "전남":["전남","전라남도"],
    "경북":["경북","경상북도"], "경남":["경남","경상남도"], "제주":["제주","제주도","제주특별자치도"],
}
# 광주(전남)·광주(경기) 등 동음 지명 오탐 방지용: 반드시 청년 키워드와 함께여야 채택(아래 KEEP)
QUERIES = []
for s in SIDO:
    QUERIES.append((s, f"{s} 청년정책"))
    QUERIES.append((s, f"{s} 청년 지원"))

POS = ["성과","확대","호평","호응","우수","선정","수상","개선","활성화","증가","최대","돌파",
       "협약","유치","혜택","지원 확대","만족","수혜","성공","우수사례","모범"]
NEG = ["논란","불만","지적","실패","축소","삭감","미흡","부족","문제","비판","우려","갈등",
       "반발","무산","중단","적발","부정","피해","혼란","저조","미달","소진","형평성"]

# === 청년정책 주제 분류(태깅) ===
# 제목/본문에서 아래 주제 키워드가 잡히면 해당 주제로 태깅. 요약의 '많이 언급된 주제'에 사용.
TOPICS = {
    "일자리":   ["일자리","취업","채용","구직","인턴","일경험","취업난","고용","면접","직무"],
    "창업":     ["창업","스타트업","벤처","창업가","로컬창업","청년몰","청년상인"],
    "주거":     ["주거","월세","전세","임대주택","보증금","주택","기숙사","주거급여"],
    "교육·직업훈련": ["직업훈련","역량강화","장학","훈련","자격","부트캠프","아카데미","교육과정"],
    "복지·금융": ["청년수당","청년통장","자산형성","바우처","대출이자","마음건강","고립","은둔","니트","돌봄","복지급여","문화패스"],
    "참여·소통": ["참여기구","청년위원","정책참여단","거버넌스","간담회","네트워크","동아리","청년의회","원탁회의"],
    "정책·기반": ["청년정책","시행계획","기본계획","조례","공모사업","청년센터","청년공간","청년친화","정책발표"],
}
# 제목에 반드시 있어야 하는 청년 표지(이게 없으면 청년정책 기사로 보지 않음)
TITLE_GATE = ["청년", "청춘", "대학생", "사회초년생", "MZ"]
# 명백한 비정책 잡음(제목에 있으면 제외) — 칼럼/연예/스포츠/사건/증시/부고 등
NOISE_KW = ["역사속 오늘","오늘의 운세","부고","인사·","주가","코스피","코스닥","환율","증시",
            "아이돌","데뷔","드라마","예능","연예","가수","배우","걸그룹","보이그룹","컴백","팬미팅",
            "야구","축구","농구","골프","프로구단","감독 선임","FA ","이적","트로피","리그",
            "사망","숨진","구속","檢","피의자","살해","마약","음주운전","성범죄","불법촬영",
            "주식","코인","비트코인","분양가","아파트 청약","청년몰 화재"]
POS = ["성과","확대","호평","호응","우수","선정","수상","개선","활성화","증가","최대","돌파",
       "협약","유치","혜택","지원 확대","만족","수혜","성공","우수사례","모범","출범","개소"]
NEG = ["논란","불만","지적","실패","축소","삭감","미흡","부족","문제","비판","우려","갈등",
       "반발","무산","중단","적발","피해","혼란","저조","미달","조기 소진","형평성","헛도는"]

def topic_tags(title, desc):
    t = title + " " + desc
    return [tp for tp, kws in TOPICS.items() if any(k in t for k in kws)]

def is_policy_related(title, desc):
    # 1) 제목에 청년 표지 필수
    if not any(g in title for g in TITLE_GATE):
        return False
    # 2) 제목에 잡음 키워드 있으면 제외
    if any(k in title for k in NOISE_KW):
        return False
    # 3) 정책 주제가 하나 이상 잡혀야 채택
    return len(topic_tags(title, desc)) >= 1

def _req(url, headers=None, data=None):
    req = urllib.request.Request(url, headers=headers or {}, data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

def naver_search(query, start=1, display=100):
    if not (NAVER_ID and NAVER_SECRET):
        return []
    url = "https://openapi.naver.com/v1/search/news.json?" + urllib.parse.urlencode(
        {"query": query, "display": display, "start": start, "sort": "date"})
    try:
        raw = _req(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        return json.loads(raw).get("items", [])
    except Exception as e:
        print("  ! 네이버 검색 실패:", query, e); return []

def clean(t):
    return html.unescape(re.sub(r"<[^>]+>", "", t or "")).strip()

def pubdate_to_iso(s):
    try:
        dt = datetime.strptime(s, "%a, %d %b %Y %H:%M:%S %z").astimezone(KST)
        return dt.date().isoformat()
    except Exception:
        return datetime.now(KST).date().isoformat()

def sido_of(title, desc, hinted):
    """기사에 hinted 시·도 별칭이 실제로 등장하면 채택(동음 오탐 완화)."""
    text = title + " " + desc
    for al in ALIAS[hinted]:
        if al in text:
            return hinted
    return None

def classify_keyword(title, desc):
    t = title + " " + desc
    p = sum(t.count(w) for w in POS); n = sum(t.count(w) for w in NEG)
    if n > p and n > 0: return "부정"
    if p > n and p > 0: return "긍정"
    return "중립"

def classify_claude(batch):
    """batch: list[str] 제목. 반환: list[str] 감성. 실패 시 키워드 폴백."""
    try:
        import anthropic
        cli = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        joined = "\n".join(f"{i+1}. {t}" for i, t in enumerate(batch))
        msg = cli.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=500,
            messages=[{"role": "user", "content":
                "다음 청년정책 관련 뉴스 제목들의 감성을 각각 긍정/부정/중립 중 하나로만 판정해라. "
                "정책 성과·지원확대=긍정, 불만·논란·축소=부정, 단순 발표·사실전달=중립. "
                "번호당 한 단어로 줄바꿈 출력:\n" + joined}])
        lines = [l.strip() for l in msg.content[0].text.splitlines() if l.strip()]
        out = []
        for l in lines:
            if "긍정" in l: out.append("긍정")
            elif "부정" in l: out.append("부정")
            else: out.append("중립")
        if len(out) == len(batch): return out
    except Exception as e:
        print("  ! Claude 분류 실패, 키워드 폴백:", e)
    return None

def load_existing():
    if os.path.exists(OUT):
        try:
            return json.load(open(OUT, encoding="utf-8"))
        except Exception:
            pass
    return {"meta": {}, "items": []}

def main():
    if not (NAVER_ID and NAVER_SECRET):
        print("NAVER_ID / NAVER_SECRET 환경변수가 필요합니다 (.env)."); return
    existing = load_existing()
    seen = {it["id"]: it for it in existing.get("items", [])}
    new_cnt = 0
    for hinted, q in QUERIES:
        print(f"· {q}")
        for start in (1, 101):                     # 최대 200건/쿼리
            items = naver_search(q, start=start)
            if not items: break
            for it in items:
                title = clean(it.get("title")); desc = clean(it.get("description"))
                if "청년" not in (title + desc):     # 청년 키워드 필수
                    continue
                if not is_policy_related(title, desc):  # 청년'정책' 연관성 필수(잡음 제거)
                    continue
                sido = sido_of(title, desc, hinted)
                if not sido:                          # 동음 오탐 방지
                    continue
                url = it.get("link") or it.get("originallink") or ""
                _id = re.sub(r"\W", "", url)[-16:] or str(abs(hash(title)))[:12]
                if _id in seen:                       # 중복 skip(history 보존)
                    continue
                seen[_id] = {"id": _id, "date": pubdate_to_iso(it.get("pubDate")),
                             "title": title, "sido": sido, "source": "네이버뉴스",
                             "url": url, "sentiment": None, "topics": topic_tags(title, desc),
                             "_t": title, "_d": desc}
                new_cnt += 1
            time.sleep(0.12)

    # 감성 미분류 항목 처리
    todo = [v for v in seen.values() if v.get("sentiment") is None]
    print(f"신규 {new_cnt}건 · 감성분류 대상 {len(todo)}건 (Claude={USE_CLAUDE})")
    if USE_CLAUDE:
        for i in range(0, len(todo), 20):
            chunk = todo[i:i+20]
            res = classify_claude([c["_t"] for c in chunk])
            for c, s in zip(chunk, res or []):
                c["sentiment"] = s
            for c in chunk:
                if c.get("sentiment") is None:
                    c["sentiment"] = classify_keyword(c["_t"], c.get("_d",""))
    for v in seen.values():
        if v.get("sentiment") is None:
            v["sentiment"] = classify_keyword(v.get("_t",""), v.get("_d",""))

    items = []
    for v in seen.values():
        v.pop("_t", None); v.pop("_d", None)
        items.append(v)
    items.sort(key=lambda x: x["date"], reverse=True)
    out = {"meta": {"generated": datetime.now(KST).isoformat(timespec="seconds"),
                    "total": len(items), "demo_backfill": False,
                    "sources": ["네이버 뉴스 API"]},
           "items": items}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"완료 · 누적 {len(items)}건 → {OUT}")

if __name__ == "__main__":
    main()
