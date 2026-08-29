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


def load_json(name, use_github):
    if use_github:
        with urllib.request.urlopen(RAW + name, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    with open(name, encoding="utf-8") as f:
        return json.load(f)


def connect():
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
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

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
