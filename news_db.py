#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
youthpolicy 뉴스 아카이브 → SQLite 적재/조회/내보내기

  python news_db.py build                     # 로컬 JSON에서 적재
  python news_db.py build --github            # GitHub raw에서 바로 적재
  python news_db.py stats                     # 현황 요약
  python news_db.py search 주거 --scope 지자체 --since 2026-01-01
  python news_db.py sql "SELECT ..." --excel out.xlsx
  python news_db.py export --excel youthpolicy_news.xlsx

정본은 news.db 이며, JSON은 입력원으로만 쓴다.
INSERT OR IGNORE 누적이므로 JSON 아카이브를 초기화해도 DB는 보존된다.
"""
import argparse, json, os, sqlite3, sys, urllib.request
from datetime import datetime

DB = os.environ.get("YOUTHPOLICY_DB", "news.db")
RAW = "https://raw.githubusercontent.com/baebong3/youthpolicy/main/"
FILES = {"central": "news_archive.json", "local": "local_news.json", "daily": "daily_news.json"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
  scope      TEXT NOT NULL,          -- 중앙 | 지자체
  id         TEXT NOT NULL,
  date       TEXT,
  title      TEXT,
  url        TEXT,
  source     TEXT,
  sentiment  TEXT,                   -- 긍정 | 중립 | 부정
  code       TEXT,                   -- 중앙: 과제코드
  field      TEXT,                   -- 중앙: 5대 분야
  dept       TEXT,                   -- 중앙: 소관부처
  sido       TEXT,                   -- 지자체: 시·도
  is_new     INTEGER,
  first_seen TEXT,                   -- DB에 처음 들어온 날 (누적 추적용)
  PRIMARY KEY (scope, id)
);
CREATE TABLE IF NOT EXISTS article_topics (
  scope TEXT NOT NULL, id TEXT NOT NULL, topic TEXT NOT NULL,
  PRIMARY KEY (scope, id, topic)
);
CREATE TABLE IF NOT EXISTS new_policies (
  date TEXT, title TEXT, dept TEXT, field TEXT, summary TEXT,
  PRIMARY KEY (date, title)
);
CREATE TABLE IF NOT EXISTS watchlist (
  date TEXT, code TEXT, name TEXT, dept TEXT, field TEXT, neg INTEGER,
  PRIMARY KEY (date, code)
);
CREATE TABLE IF NOT EXISTS load_log (
  loaded_at TEXT, scope TEXT, seen INTEGER, inserted INTEGER, span_start TEXT, span_end TEXT
);
CREATE INDEX IF NOT EXISTS ix_art_date  ON articles(date);
CREATE INDEX IF NOT EXISTS ix_art_scope ON articles(scope, date);
CREATE INDEX IF NOT EXISTS ix_art_sent  ON articles(sentiment);
CREATE INDEX IF NOT EXISTS ix_art_field ON articles(field);
CREATE INDEX IF NOT EXISTS ix_art_sido  ON articles(sido);
CREATE INDEX IF NOT EXISTS ix_top_topic ON article_topics(topic);
"""

VIEWS = """
DROP VIEW IF EXISTS v_daily;
CREATE VIEW v_daily AS
SELECT date, scope,
       COUNT(*) AS n,
       SUM(sentiment='긍정') AS pos,
       SUM(sentiment='중립') AS neu,
       SUM(sentiment='부정') AS neg,
       ROUND(100.0*(SUM(sentiment='긍정')-SUM(sentiment='부정'))/COUNT(*), 1) AS nsi
FROM articles GROUP BY date, scope;

DROP VIEW IF EXISTS v_monthly;
CREATE VIEW v_monthly AS
SELECT substr(date,1,7) AS ym, scope,
       COUNT(*) AS n,
       SUM(sentiment='긍정') AS pos,
       SUM(sentiment='부정') AS neg,
       ROUND(100.0*(SUM(sentiment='긍정')-SUM(sentiment='부정'))/COUNT(*), 1) AS nsi
FROM articles GROUP BY ym, scope;

DROP VIEW IF EXISTS v_sido_month;
CREATE VIEW v_sido_month AS
SELECT substr(date,1,7) AS ym, sido,
       COUNT(*) AS n,
       SUM(sentiment='부정') AS neg,
       ROUND(100.0*SUM(sentiment='부정')/COUNT(*), 1) AS neg_rate
FROM articles WHERE scope='지자체' AND sido IS NOT NULL
GROUP BY ym, sido;

DROP VIEW IF EXISTS v_topic_month;
CREATE VIEW v_topic_month AS
SELECT substr(a.date,1,7) AS ym, t.topic,
       COUNT(*) AS n,
       SUM(a.sentiment='부정') AS neg
FROM articles a JOIN article_topics t ON t.scope=a.scope AND t.id=a.id
GROUP BY ym, t.topic;
"""

# ── 삼각검증 스키마 확장(제안서 3.6·6.3) : 기존 스키마 위에 '추가만' ──
# 네 갈래 출처(시행계획실측·선행연구2차·뉴스·신규정량/정성)를 5대 분야 축에
# 결선한다. 기존 테이블/뷰는 건드리지 않으며, 모두 IF NOT EXISTS.
SCHEMA_TRIANGULATION = """
CREATE TABLE IF NOT EXISTS prior_study (
  record_id     TEXT PRIMARY KEY,       -- 선행연구2차-{일련}
  prior_study   TEXT,                   -- 선행연구·국가승인통계명
  prior_variable TEXT,                  -- 재활용 대상 핵심 변수영역
  field         TEXT,                   -- 5대 분야
  new_item_id   TEXT,                   -- 얹히는 신규 문항 ID(Q-분야-nn)
  indicator     TEXT,                   -- youth / gap / part
  source_type   TEXT DEFAULT '선행연구2차',
  method        TEXT DEFAULT '행정자료',
  unit          TEXT DEFAULT '가구',
  reuse_tier    TEXT,                   -- ★★★ / ★★☆ / ★☆☆
  reliability   TEXT DEFAULT '국가승인통계',
  access        TEXT,                   -- MDIS 등 접근 경로
  n             INTEGER,
  value         REAL,                   -- 재활용 baseline 요약값(있으면)
  period        TEXT,                   -- YYYY / YYYY-MM / wave
  linkage_key   TEXT,                   -- field×조직×target_p×period(비식별)
  first_seen    TEXT,
  version       TEXT DEFAULT 'v1.0',
  note          TEXT
);
CREATE TABLE IF NOT EXISTS survey_item (
  item_id     TEXT PRIMARY KEY,         -- Q-{분야}-{2자리}
  field       TEXT,
  target      TEXT,                     -- 정책대상 세그먼트(target_p 요약)
  indicator   TEXT,                     -- youth / part
  scale       TEXT,                     -- 예: 5점 리커트
  question    TEXT,
  source_type TEXT DEFAULT '신규정량',
  method      TEXT DEFAULT '설문',
  version     TEXT DEFAULT 'v1.0',
  first_seen  TEXT
);
CREATE TABLE IF NOT EXISTS survey_response (
  record_id   TEXT PRIMARY KEY,         -- 신규정량-{일련}
  item_id     TEXT,                     -- survey_item.item_id
  code        TEXT,                     -- 과제코드(시행계획실측 admin과 결합)
  field       TEXT,
  target_p    TEXT,                     -- student·income·work·age 요약
  score       REAL,                     -- 집계 점수 또는 개표 응답값
  n           INTEGER,
  unit        TEXT DEFAULT '개인',
  source_type TEXT DEFAULT '신규정량',
  method      TEXT DEFAULT '설문',
  period      TEXT,                      -- YYYY / YYYY-MM / wave
  linkage_key TEXT,
  first_seen  TEXT
);
CREATE TABLE IF NOT EXISTS qual_finding (
  finding_id  TEXT PRIMARY KEY,         -- 신규정성-{일련}
  field       TEXT,
  target      TEXT,
  gap_theme   TEXT,                     -- 괴리 원인·주제 코딩 결과
  code        TEXT,                     -- 과제코드(있으면)
  variable_id TEXT,                     -- Q-{분야}-nn 결선
  source_type TEXT DEFAULT '신규정성',
  method      TEXT DEFAULT 'FGI·심층인터뷰',
  unit        TEXT DEFAULT '개인',
  evidence    TEXT,                     -- 근거 인용·메모
  period      TEXT,
  linkage_key TEXT,
  first_seen  TEXT
);
CREATE INDEX IF NOT EXISTS ix_prior_field   ON prior_study(field);
CREATE INDEX IF NOT EXISTS ix_svresp_field  ON survey_response(field);
CREATE INDEX IF NOT EXISTS ix_svresp_code   ON survey_response(code);
CREATE INDEX IF NOT EXISTS ix_qual_field    ON qual_finding(field);
"""

VIEWS_TRIANGULATION = """
DROP VIEW IF EXISTS v_field_year;
CREATE VIEW v_field_year AS
SELECT nz.field, nz.year,
       nz.news_n, nz.pos, nz.neu, nz.neg,
       ROUND(100.0*(nz.pos-nz.neg)/nz.news_n, 1) AS nsi,
       COALESCE(sv.cnt, 0) AS survey_n,
       COALESCE(ql.cnt, 0) AS qual_n
FROM (
    SELECT field, substr(date,1,4) AS year,
           COUNT(*) AS news_n,
           SUM(sentiment='긍정') AS pos,
           SUM(sentiment='중립') AS neu,
           SUM(sentiment='부정') AS neg
    FROM articles WHERE field IS NOT NULL
    GROUP BY field, substr(date,1,4)
) nz
LEFT JOIN (
    SELECT field, substr(period,1,4) AS year, COUNT(*) AS cnt
    FROM survey_response GROUP BY field, substr(period,1,4)
) sv ON sv.field=nz.field AND sv.year=nz.year
LEFT JOIN (
    SELECT field, substr(COALESCE(period, first_seen),1,4) AS year, COUNT(*) AS cnt
    FROM qual_finding GROUP BY field, substr(COALESCE(period, first_seen),1,4)
) ql ON ql.field=nz.field AND ql.year=nz.year;

DROP VIEW IF EXISTS v_field_source;
CREATE VIEW v_field_source AS
SELECT field, '뉴스' AS source_type, COUNT(*) AS n
  FROM articles WHERE field IS NOT NULL GROUP BY field
UNION ALL
SELECT field, '선행연구2차', COUNT(*) FROM prior_study     WHERE field IS NOT NULL GROUP BY field
UNION ALL
SELECT field, '신규정량',   COUNT(*) FROM survey_response WHERE field IS NOT NULL GROUP BY field
UNION ALL
SELECT field, '신규정성',   COUNT(*) FROM qual_finding    WHERE field IS NOT NULL GROUP BY field;
"""


def load_json(name, use_github):
    if use_github:
        with urllib.request.urlopen(RAW + name, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    with open(name, encoding="utf-8") as f:
        return json.load(f)


def connect():
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    # 삼각검증 확장(추가만, 기존 스키마 보존) — 테이블 먼저, 뷰는 그 위에
    con.executescript(SCHEMA_TRIANGULATION)
    con.executescript(VIEWS_TRIANGULATION)
    return con


def build(args):
    con = connect()
    today = datetime.now().strftime("%Y-%m-%d")
    total_new = 0

    for scope, key in (("중앙", "central"), ("지자체", "local")):
        try:
            doc = load_json(FILES[key], args.github)
        except Exception as e:
            print(f"[건너뜀] {FILES[key]}: {e}")
            continue
        items = doc.get("items", [])
        meta = doc.get("meta", {})
        before = con.execute("SELECT COUNT(*) FROM articles WHERE scope=?", (scope,)).fetchone()[0]

        rows, topics = [], []
        for it in items:
            rows.append((
                scope, it.get("id"), it.get("date"), it.get("title"), it.get("url"),
                it.get("source"), it.get("sentiment"), it.get("code"), it.get("field"),
                it.get("dept"), it.get("sido"), it.get("is_new"), today,
            ))
            for tp in (it.get("topics") or []):
                topics.append((scope, it.get("id"), tp))

        con.executemany(
            "INSERT OR IGNORE INTO articles"
            "(scope,id,date,title,url,source,sentiment,code,field,dept,sido,is_new,first_seen)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        con.executemany("INSERT OR IGNORE INTO article_topics(scope,id,topic) VALUES (?,?,?)", topics)

        after = con.execute("SELECT COUNT(*) FROM articles WHERE scope=?", (scope,)).fetchone()[0]
        added = after - before
        total_new += added
        con.execute("INSERT INTO load_log VALUES (?,?,?,?,?,?)",
                    (today, scope, len(items), added, meta.get("span_start"), meta.get("span_end")))
        print(f"  {scope}: 원본 {len(items):,}건 → 신규 {added:,}건 (누적 {after:,}건)")

    # 당일 파일의 신규정책 / 워치리스트
    try:
        d = load_json(FILES["daily"], args.github)
        gen = (d.get("meta") or {}).get("generated", today)[:10]
        con.executemany(
            "INSERT OR IGNORE INTO new_policies(date,title,dept,field,summary) VALUES (?,?,?,?,?)",
            [(p.get("date") or gen, p.get("title"), p.get("dept"), p.get("field"), p.get("summary"))
             for p in d.get("new_policies", [])])
        con.executemany(
            "INSERT OR IGNORE INTO watchlist(date,code,name,dept,field,neg) VALUES (?,?,?,?,?,?)",
            [(gen, w.get("code"), w.get("name"), w.get("dept"), w.get("field"), w.get("neg"))
             for w in d.get("watch", [])])
        print(f"  당일: 신규정책 {len(d.get('new_policies', [])):,}건, 워치 {len(d.get('watch', [])):,}건")
    except Exception as e:
        print(f"[건너뜀] {FILES['daily']}: {e}")

    con.executescript(VIEWS)
    con.commit()
    print(f"\n완료 — 이번 실행 신규 {total_new:,}건 · DB: {os.path.abspath(DB)}")
    stats(args, con)


def stats(args, con=None):
    con = con or connect()
    q = con.execute("""SELECT scope, COUNT(*), MIN(date), MAX(date),
                              SUM(sentiment='긍정'), SUM(sentiment='중립'), SUM(sentiment='부정')
                       FROM articles GROUP BY scope""").fetchall()
    print("\n" + "─" * 74)
    print(f"{'구분':<8}{'건수':>10}{'시작':>13}{'종료':>13}{'긍정':>8}{'중립':>8}{'부정':>8}")
    print("─" * 74)
    for r in q:
        print(f"{r[0]:<8}{r[1]:>10,}{r[2] or '-':>13}{r[3] or '-':>13}{r[4]:>8,}{r[5]:>8,}{r[6]:>8,}")
    tot = con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    print("─" * 74)
    print(f"{'합계':<8}{tot:>10,}")
    for label, sql in (("분야(중앙)", "SELECT field, COUNT(*) c FROM articles WHERE scope='중앙' AND field IS NOT NULL GROUP BY field ORDER BY c DESC LIMIT 6"),
                       ("시·도(지자체)", "SELECT sido, COUNT(*) c FROM articles WHERE scope='지자체' AND sido IS NOT NULL GROUP BY sido ORDER BY c DESC LIMIT 6"),
                       ("주제(지자체)", "SELECT topic, COUNT(*) c FROM article_topics GROUP BY topic ORDER BY c DESC LIMIT 8")):
        rows = con.execute(sql).fetchall()
        if rows:
            print(f"\n{label}: " + " · ".join(f"{a} {b:,}" for a, b in rows))


def search(args):
    con = connect()
    where, prm = ["title LIKE ?"], [f"%{args.keyword}%"]
    if args.scope:
        where.append("scope=?"); prm.append(args.scope)
    if args.sido:
        where.append("sido=?"); prm.append(args.sido)
    if args.sentiment:
        where.append("sentiment=?"); prm.append(args.sentiment)
    if args.since:
        where.append("date>=?"); prm.append(args.since)
    if args.until:
        where.append("date<=?"); prm.append(args.until)
    sql = (f"SELECT date, scope, COALESCE(sido, field, '') AS seg, sentiment, title, url "
           f"FROM articles WHERE {' AND '.join(where)} ORDER BY date DESC LIMIT ?")
    rows = con.execute(sql, prm + [args.limit]).fetchall()
    n = con.execute(f"SELECT COUNT(*) FROM articles WHERE {' AND '.join(where)}", prm).fetchone()[0]
    print(f"\n검색어 '{args.keyword}' — 전체 {n:,}건 중 최근 {len(rows):,}건\n" + "─" * 100)
    for d, sc, seg, se, t, u in rows:
        print(f"{d}  [{sc}/{seg}]  {se}  {t[:52]}")
    if args.excel:
        to_excel(rows, ["date", "scope", "seg", "sentiment", "title", "url"], args.excel)


def run_sql(args):
    con = connect()
    cur = con.execute(args.query)
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    print("\t".join(cols))
    for r in rows[:args.limit]:
        print("\t".join("" if v is None else str(v) for v in r))
    print(f"\n({len(rows):,}행)")
    if args.excel:
        to_excel(rows, cols, args.excel)


def to_excel(rows, cols, path):
    try:
        import pandas as pd
        pd.DataFrame(rows, columns=cols).to_excel(path, index=False)
        print(f"→ 저장: {os.path.abspath(path)}")
    except ImportError:
        import csv
        path = os.path.splitext(path)[0] + ".csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(cols); w.writerows(rows)
        print(f"(pandas 없음 → CSV) 저장: {os.path.abspath(path)}")


def export(args):
    con = connect()
    sheets = {
        "articles": "SELECT * FROM articles ORDER BY date DESC",
        "월별추이": "SELECT * FROM v_monthly ORDER BY ym, scope",
        "시도월별": "SELECT * FROM v_sido_month ORDER BY ym, n DESC",
        "주제월별": "SELECT * FROM v_topic_month ORDER BY ym, n DESC",
        "신규정책": "SELECT * FROM new_policies ORDER BY date DESC",
        "워치리스트": "SELECT * FROM watchlist ORDER BY date DESC, neg DESC",
    }
    try:
        import pandas as pd
    except ImportError:
        print("엑셀 내보내기는 pandas·openpyxl이 필요합니다: pip install pandas openpyxl")
        return
    with pd.ExcelWriter(args.excel, engine="openpyxl") as xw:
        for name, sql in sheets.items():
            df = pd.read_sql(sql, con)
            df.to_excel(xw, sheet_name=name[:31], index=False)
            print(f"  {name}: {len(df):,}행")
    print(f"→ 저장: {os.path.abspath(args.excel)}")


def triangulate(args):
    """v_field_year(분야×연도 삼각검증)를 콘솔 출력. 뉴스 감성 + survey/qual 카운트."""
    con = connect()
    rows = con.execute(
        "SELECT field, year, news_n, pos, neu, neg, nsi, survey_n, qual_n "
        "FROM v_field_year ORDER BY field, year"
    ).fetchall()
    print("\n삼각검증 — 분야×연도 (v_field_year)")
    print("─" * 88)
    print(f"{'분야':<14}{'연도':>6}{'뉴스':>8}{'긍정':>7}{'중립':>7}{'부정':>7}"
          f"{'NSI':>8}{'설문':>7}{'정성':>7}")
    print("─" * 88)
    for r in rows:
        f, y, n, pos, neu, neg, nsi, sv, ql = r
        print(f"{f:<14}{y:>6}{n:>8,}{pos:>7,}{neu:>7,}{neg:>7,}"
              f"{(nsi if nsi is not None else 0):>8.1f}{sv:>7,}{ql:>7,}")
    if not rows:
        print("(articles 비어 있음 — 먼저 'python news_db.py build' 실행)")
    print("─" * 88)
    print("NSI = 100·(긍정−부정)/뉴스건수. 설문/정성은 survey_response·qual_finding 적재 시 증가.")
    # 분야×출처유형 요약도 함께 노출
    src = con.execute(
        "SELECT field, source_type, n FROM v_field_source ORDER BY field, source_type"
    ).fetchall()
    if src:
        print("\n분야×출처유형 (v_field_source)")
        for f, st, n in src:
            print(f"  {f:<14} {st:<10} {n:>8,}")


def main():
    ap = argparse.ArgumentParser(description="youthpolicy 뉴스 아카이브 DB")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="JSON → SQLite 적재(누적)")
    b.add_argument("--github", action="store_true", help="GitHub raw에서 직접 내려받아 적재")
    b.set_defaults(func=build)

    s = sub.add_parser("stats", help="현황 요약")
    s.set_defaults(func=lambda a: stats(a))

    f = sub.add_parser("search", help="제목 키워드 검색")
    f.add_argument("keyword")
    f.add_argument("--scope", choices=["중앙", "지자체"])
    f.add_argument("--sido")
    f.add_argument("--sentiment", choices=["긍정", "중립", "부정"])
    f.add_argument("--since"); f.add_argument("--until")
    f.add_argument("--limit", type=int, default=40)
    f.add_argument("--excel")
    f.set_defaults(func=search)

    q = sub.add_parser("sql", help="임의 SQL 실행")
    q.add_argument("query")
    q.add_argument("--limit", type=int, default=60)
    q.add_argument("--excel")
    q.set_defaults(func=run_sql)

    e = sub.add_parser("export", help="엑셀 다중 시트 내보내기")
    e.add_argument("--excel", default="youthpolicy_news.xlsx")
    e.set_defaults(func=export)

    t = sub.add_parser("triangulate", help="분야×연도 삼각검증(v_field_year) 출력")
    t.set_defaults(func=triangulate)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
