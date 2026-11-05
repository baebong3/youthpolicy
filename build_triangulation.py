#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_triangulation.py — 분야(field) 결합 산출물 빌더 (네트워크 불필요, 로컬 JSON만)

제안서 6.2 「분석 축·핵심 산출」의 field×… 축을 '실데이터 스냅샷'으로 고정한다.
네 갈래 실측 출처를 5대 분야 1행으로 결합한다:

  · youth_policy.json  → field_agg : 중앙 과제수·예산·admin·youth·part·total·gap·등급분포
  · sido_compare.json  → meta.field_agg : 분야별 지방 과제 수
  · news_archive.json  → (없으면 daily_news.json) 분야별 기사수·감성(긍/중/부)
  · tasks.json         → 분야별 과제수·예산 합(교차검증)

산출:
  data/triangulation_field.csv , data/triangulation_field.json

파생식:
  NSI(순감성지수) = 100 × (긍정 − 부정) / 뉴스기사수      # 소수 1자리
  gap = admin − youth   (youth_policy.json 실측값 사용)

수집기(collect_*.py)·news_db.py를 건드리지 않는 순수 읽기 전용 스크립트.
"""
import csv
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "data")

FIELDS = ["일자리", "교육·직업훈련", "주거", "금융·복지·문화", "참여·권리"]


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def news_by_field():
    """분야별 기사수·감성 집계. news_archive.json 우선, 없으면 daily_news.json."""
    src = "news_archive.json"
    if not os.path.exists(os.path.join(HERE, src)):
        src = "daily_news.json"
    doc = load(src)
    items = doc.get("items", []) if isinstance(doc, dict) else doc
    agg = defaultdict(lambda: {"n": 0, "pos": 0, "neu": 0, "neg": 0})
    for it in items:
        f = it.get("field")
        if f not in FIELDS:
            continue
        a = agg[f]
        a["n"] += 1
        s = it.get("sentiment")
        if s == "긍정":
            a["pos"] += 1
        elif s == "부정":
            a["neg"] += 1
        else:
            a["neu"] += 1
    return src, agg


def tasks_by_field():
    """tasks.json 분야별 과제수·예산 합(백만원) — 교차검증용."""
    agg = defaultdict(lambda: {"n": 0, "budget": 0})
    for t in load("tasks.json"):
        f = t.get("field")
        agg[f]["n"] += 1
        agg[f]["budget"] += t.get("budget_2026", 0) or 0
    return agg


def build():
    yp = {r["field"]: r for r in load("youth_policy.json")["field_agg"]}
    sido = load("sido_compare.json")["meta"]["field_agg"]
    news_src, news = news_by_field()
    tasks = tasks_by_field()

    rows = []
    for f in FIELDS:
        r = yp[f]
        nw = news.get(f, {"n": 0, "pos": 0, "neu": 0, "neg": 0})
        n_news = nw["n"]
        nsi = round(100.0 * (nw["pos"] - nw["neg"]) / n_news, 1) if n_news else None
        # 교차검증: youth_policy와 tasks의 과제수·예산이 일치하는지 표시
        tk = tasks.get(f, {"n": 0, "budget": 0})
        rows.append({
            "field": f,
            "central_tasks": r["n"],
            "budget_mw": r["budget"],
            "admin": r["admin"],
            "youth": r["youth"],
            "part": r["part"],
            "total": r["total"],
            "gap": r["gap"],
            "grade_우수": r["u"],
            "grade_보통": r["b"],
            "grade_미흡": r["m"],
            "grade_dist": f"우수 {r['u']}/보통 {r['b']}/미흡 {r['m']}",
            "local_tasks": sido.get(f, 0),
            "news_n": n_news,
            "news_pos": nw["pos"],
            "news_neu": nw["neu"],
            "news_neg": nw["neg"],
            "nsi": nsi,
            "xcheck_tasks_ok": (tk["n"] == r["n"]),
            "xcheck_budget_ok": (tk["budget"] == r["budget"]),
        })

    # 합계 행(참고)
    tot = {
        "field": "합계",
        "central_tasks": sum(x["central_tasks"] for x in rows),
        "budget_mw": sum(x["budget_mw"] for x in rows),
        "admin": None, "youth": None, "part": None, "total": None, "gap": None,
        "grade_우수": sum(x["grade_우수"] for x in rows),
        "grade_보통": sum(x["grade_보통"] for x in rows),
        "grade_미흡": sum(x["grade_미흡"] for x in rows),
        "grade_dist": "",
        "local_tasks": sum(x["local_tasks"] for x in rows),
        "news_n": sum(x["news_n"] for x in rows),
        "news_pos": sum(x["news_pos"] for x in rows),
        "news_neu": sum(x["news_neu"] for x in rows),
        "news_neg": sum(x["news_neg"] for x in rows),
        "nsi": None,
        "xcheck_tasks_ok": all(x["xcheck_tasks_ok"] for x in rows),
        "xcheck_budget_ok": all(x["xcheck_budget_ok"] for x in rows),
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    cols = ["field", "central_tasks", "budget_mw", "admin", "youth", "gap",
            "grade_dist", "local_tasks", "news_n", "news_pos", "news_neu",
            "news_neg", "nsi"]
    csv_path = os.path.join(OUT_DIR, "triangulation_field.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for x in rows + [tot]:
            w.writerow(x)

    json_path = os.path.join(OUT_DIR, "triangulation_field.json")
    meta = {
        "generated_by": "build_triangulation.py",
        "axis": "field (제안서 6.2 분석 축 field×…)",
        "sources": {
            "central_perf": "youth_policy.json#field_agg",
            "local_tasks": "sido_compare.json#meta.field_agg",
            "news": news_src,
            "budget_xcheck": "tasks.json",
        },
        "formulas": {
            "nsi": "100*(pos-neg)/news_n",
            "gap": "admin-youth (youth_policy 실측)",
        },
        "note": "예산 단위 백만원. admin/youth/gap은 현재 대시보드 시연값이며, 신규정량 적재 시 실측 대체(제안서 3.5).",
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "rows": rows, "total": tot}, fh,
                  ensure_ascii=False, indent=2)

    # 콘솔 요약표
    print(f"\n분야 결합 삼각검증 스냅샷 (뉴스원: {news_src})")
    print("─" * 108)
    print(f"{'분야':<14}{'중앙과제':>7}{'예산(백만)':>12}{'admin':>7}{'youth':>7}"
          f"{'gap':>6}{'지방과제':>7}{'뉴스':>7}{'긍/중/부':>14}{'NSI':>7}")
    print("─" * 108)
    for x in rows:
        sd = f"{x['news_pos']}/{x['news_neu']}/{x['news_neg']}"
        nsi = f"{x['nsi']:.1f}" if x["nsi"] is not None else "-"
        print(f"{x['field']:<14}{x['central_tasks']:>7,}{x['budget_mw']:>12,}"
              f"{x['admin']:>7}{x['youth']:>7}{x['gap']:>6}{x['local_tasks']:>7,}"
              f"{x['news_n']:>7,}{sd:>14}{nsi:>7}")
    print("─" * 108)
    tot_sd = f"{tot['news_pos']}/{tot['news_neu']}/{tot['news_neg']}"
    print(f"{'합계':<14}{tot['central_tasks']:>7,}{tot['budget_mw']:>12,}"
          f"{'':>7}{'':>7}{'':>6}{tot['local_tasks']:>7,}{tot['news_n']:>7,}"
          f"{tot_sd:>14}{'':>7}")
    xc = "일치" if tot["xcheck_tasks_ok"] and tot["xcheck_budget_ok"] else "불일치"
    print(f"\n교차검증(youth_policy vs tasks 과제수·예산): {xc}")
    print(f"→ 저장: {csv_path}")
    print(f"→ 저장: {json_path}")


if __name__ == "__main__":
    build()
