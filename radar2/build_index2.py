# -*- coding: utf-8 -*-
"""
news_archive.json(중앙) + local_news.json(지역) → index2.html (청년정책 이슈 레이더)

구성 (의료관광 · 웰니스 이슈 레이더와 같은 틀, 서던 하우스 색)
  - 중앙정부 / 지역정부 토글 : 라디오 버튼 · 자바스크립트 없이 동작
  - 맨 위 : 오늘의 핵심 이슈 헤드라인(최근 3일 기사 묶음, 약하면 7일)
  - 이번 주 핵심 이슈 순위 · 이슈가 몰린 주제 · 30일 추이
  - 주제별 핵심 정리(주제마다 대표 이슈와 기사 3건)
  - 먼저 볼 기사 · 뜨는 주제어 · 지역별(지역) / 기관별(중앙) 보도
  - 6월 이후 월별 흐름(월별 기사 수와 핵심 이슈 3개)
  - 주제별 기사 목록(최근 7일, 10건 + 더보기)

기존 index.html(분석·평가 콘솔)은 건드리지 않음

사용법
  python radar2/build_index2.py            # 최근 7일 기준
  python radar2/build_index2.py --days 14
"""
import argparse, html, io, json, os, re, sys
from collections import Counter
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import rules
import topic
import region
from rules import CEN, LOC, TRACKS, KST

OUT = os.path.join(ROOT, 'index2.html')
SHOW = 10
ARCH_FROM = '2026-06'          # 월별 흐름 시작 월

CSS = """<style>
@font-face{font-family:'PretendardSub';font-weight:400;font-display:swap;src:url(assets/fonts/pretendard-sub-Regular.woff2) format('woff2')}
@font-face{font-family:'PretendardSub';font-weight:600;font-display:swap;src:url(assets/fonts/pretendard-sub-SemiBold.woff2) format('woff2')}
@font-face{font-family:'PretendardSub';font-weight:800;font-display:swap;src:url(assets/fonts/pretendard-sub-ExtraBold.woff2) format('woff2')}
:root{
  --navy:#2B3A55;--navy-d:#1C2740;--navy-s:#E7EAF0;--coral:#E85A3C;--coral-d:#C6452B;--coral-s:#FBE7E1;
  --good:#2E8B6F;--ink:#16202C;--sub:#4A5463;--muted:#8A93A0;
  --rule:#E3E7ED;--rule2:#F0F2F5;--bg:#F6F7F9;--card:#FFFFFF;--bar:#D5DAE1;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:'PretendardSub','Pretendard','Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif;
  font-size:14px;line-height:1.55;letter-spacing:-.1px}
a{color:inherit;text-decoration:none}

/* 머리 */
.mast{background:#fff;border-bottom:1px solid var(--rule)}
.mast .in{max-width:1240px;margin:0 auto;padding:14px 16px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:10px}
.brand .mk{width:12px;height:12px;border-radius:3px;background:var(--coral)}
.team{display:flex;flex-direction:column;line-height:1.25}
.team .t1{font-size:12px;font-weight:600;color:var(--muted)}
.team .t2{font-size:17px;font-weight:800;letter-spacing:-.4px}
.mast .upd{margin-left:auto;text-align:right;font-size:12px;color:var(--muted);line-height:1.45}
.mast .upd b{display:block;color:var(--ink);font-weight:600;font-size:13px}
.mast .upd a{color:var(--navy);font-weight:700;border-bottom:1px solid var(--rule)}
.ribbon{display:flex;height:4px}.ribbon i{flex:1}
.ribbon i:nth-child(1){background:var(--navy)}.ribbon i:nth-child(2){background:var(--coral)}

.wrap{max-width:1240px;margin:0 auto;padding:0 16px}

/* 토글 */
.trk{position:absolute;opacity:0;pointer-events:none}
.tabs{display:inline-flex;background:#fff;border:1px solid var(--rule);border-radius:999px;padding:4px;margin:24px 0 22px;gap:2px;flex-wrap:wrap}
.tabs label{cursor:pointer;border-radius:999px;padding:9px 22px;font-weight:800;font-size:14.5px;color:var(--sub);display:flex;align-items:baseline;gap:8px}
.tabs label small{font-weight:600;font-size:12px;color:var(--muted)}
#trk-cen:checked~.wrap .tabs label[for=trk-cen]{background:var(--navy);color:#fff}
#trk-loc:checked~.wrap .tabs label[for=trk-loc]{background:var(--coral);color:#fff}
#trk-cen:checked~.wrap .tabs label[for=trk-cen] small,#trk-loc:checked~.wrap .tabs label[for=trk-loc] small{color:rgba(255,255,255,.85)}
.pane{display:none}
#trk-cen:checked~.wrap .pane-cen{display:block}
#trk-loc:checked~.wrap .pane-loc{display:block}
.pane-cen{--ac:var(--navy);--ac-d:var(--navy-d);--tint:var(--navy-s)}
.pane-loc{--ac:var(--coral);--ac-d:var(--coral-d);--tint:var(--coral-s)}

/* 헤드라인 */
.hero{padding:4px 0 20px 18px;border-left:5px solid var(--ac);margin:0 0 20px}
.eyebrow{font-size:12px;font-weight:800;letter-spacing:1px;color:var(--ac-d)}
.hero h1{font-size:32px;line-height:1.3;font-weight:800;letter-spacing:-1px;margin:6px 0 10px;word-break:keep-all}
.dek{font-size:14px;color:var(--sub);margin:0;word-break:keep-all}
.dek a{color:var(--ink);font-weight:600;border-bottom:1px solid var(--rule)}
.dek a:hover{color:var(--ac-d);border-color:var(--ac)}
.also{list-style:none;margin:12px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:8px}
.also li{font-size:13px;background:#fff;border:1px solid var(--rule);border-radius:999px;padding:5px 12px;word-break:keep-all}
.also li b{color:var(--ac-d);font-weight:800;margin-right:4px}

/* KPI */
.kpis{display:grid;grid-template-columns:repeat(5,1fr);background:#fff;border:1px solid var(--rule);border-top:3px solid var(--ac);margin-bottom:22px}
.kpi{padding:16px 18px;border-left:1px solid var(--rule2)}
.kpi:first-child{border-left:0}
.kv{font-size:32px;font-weight:800;letter-spacing:-1px;line-height:1.1;font-variant-numeric:tabular-nums}
.kv.sm{font-size:22px;letter-spacing:-.6px;line-height:1.5}
.kpi:first-child .kv{color:var(--ac)}
.kpi .kv.neg{color:var(--coral-d)}
.kl{font-size:12.5px;font-weight:600;margin-top:6px}
.ks{font-size:11.5px;color:var(--muted)}

/* 격자 · 카드 */
.grid{display:grid;grid-template-columns:1.35fr 1fr;gap:18px;align-items:start}
.grid>*{min-width:0}
.g2{margin-top:18px}
.card{background:#fff;border:1px solid var(--rule);padding:20px 22px 22px;min-width:0}
.sec{font-size:11.5px;font-weight:800;letter-spacing:1px;color:var(--ac-d)}
.h2{font-size:19px;font-weight:800;letter-spacing:-.5px;margin:4px 0 2px;word-break:keep-all}
.h2 .n{color:var(--muted);font-weight:600;font-size:15px;margin-left:4px}
.cap{font-size:12px;color:var(--muted);margin-bottom:12px;word-break:keep-all}
.note{font-size:12px;color:var(--sub);border-left:3px solid var(--tint);padding-left:10px;margin:14px 0 0;word-break:keep-all}

.chip{display:inline-block;font-size:11px;font-weight:700;border-radius:3px;padding:2px 7px;background:var(--tint);color:var(--ac-d);white-space:nowrap}
.chip.neg{background:#FBE7E1;color:#C6452B}
.chip.pos{background:#E3F2EC;color:#23704F}
.chip.hot{background:var(--ac);color:#fff}
.meta{font-size:12px;color:var(--muted);margin-top:6px}
.meta b{color:var(--sub);font-weight:600}

/* 핵심 이슈 순위 */
.irank{list-style:none;margin:6px 0 0;padding:0}
.irank li{display:grid;grid-template-columns:26px 1fr;gap:4px 10px;padding:12px 0;border-bottom:1px solid var(--rule2)}
.irank li:last-child{border-bottom:0}
.irank .rk{font-size:19px;font-weight:800;color:var(--ink);line-height:1.25;font-variant-numeric:tabular-nums}
.irank li:first-child .rk{color:var(--ac)}
.irank .it{font-size:15px;font-weight:800;line-height:1.45;word-break:keep-all}
.irank .it a:hover{color:var(--ac);text-decoration:underline}
.irank .tr{grid-column:2;display:flex;align-items:center;gap:8px;margin-top:3px}
.irank .b{height:12px;background:var(--bar);border-radius:2px}
.irank li:first-child .b{background:var(--ac)}
.irank .v{font-size:12.5px;font-weight:800;white-space:nowrap;font-variant-numeric:tabular-nums}
.irank .v small{font-weight:600;color:var(--muted);font-size:12px}
.irank .sub{grid-column:2;font-size:12.5px;color:var(--sub);line-height:1.5;word-break:keep-all}
.irank .sub a:hover{color:var(--ac);text-decoration:underline}

/* 가로 막대 */
.hb{margin:4px 0 0}
.hb .r{display:grid;grid-template-columns:104px 1fr;align-items:center;gap:10px;margin:7px 0}
.hb .nm{font-size:12.5px;color:var(--sub);text-align:right;white-space:nowrap}
.hb .tr{display:flex;align-items:center;gap:8px}
.hb .b{height:16px;background:var(--bar);border-radius:2px}
.hb .r.top .b{background:var(--ac)}
.hb .v{font-size:13px;font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap}
.hb .v small{font-weight:600;color:var(--muted);font-size:11.5px;margin-left:3px}
svg .xl{font-size:11px;fill:#8A93A0;text-anchor:middle;font-family:'PretendardSub','Pretendard',sans-serif}
svg .vt{font-size:10.5px;fill:#16202C;font-weight:800;text-anchor:middle;font-family:'PretendardSub','Pretendard',sans-serif}

/* 주제별 핵심 정리 */
.tgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
.tcard{background:#fff;border:1px solid var(--rule);border-top:3px solid var(--ac);padding:18px 20px 16px;min-width:0}
.tcard .th{display:flex;align-items:baseline;justify-content:space-between;gap:10px}
.tcard .tn{font-size:17px;font-weight:800;letter-spacing:-.4px}
.tcard .tc{font-size:13px;font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap}
.tcard .tc small{font-weight:600;color:var(--muted);font-size:12px}
.tcard .tk{font-size:15px;font-weight:800;line-height:1.45;margin:10px 0 4px;word-break:keep-all;color:var(--ac-d)}
.tcard .tk small{font-size:12px;font-weight:600;color:var(--muted);margin-left:4px}
.tcard ul{list-style:none;margin:8px 0 0;padding:0}
.tcard li{padding:8px 0;border-top:1px solid var(--rule2);font-size:13.5px;font-weight:600;line-height:1.45;word-break:keep-all}
.tcard li a:hover{color:var(--ac);text-decoration:underline}
.tcard li .meta{margin-top:2px;font-weight:400}

/* 먼저 볼 기사 */
.lead{border-bottom:1px solid var(--rule);padding:6px 0 16px}
.lead .tt{font-size:20px;font-weight:800;line-height:1.4;letter-spacing:-.5px;margin:8px 0 4px;word-break:keep-all}
.lead .tt a:hover,.rest .tt a:hover{color:var(--ac);text-decoration:underline}
.rest{list-style:none;margin:0;padding:0}
.rest li{display:flex;gap:12px;padding:12px 0;border-bottom:1px solid var(--rule2)}
.rest li:last-child{border-bottom:0}
.rest .rk{font-size:19px;font-weight:800;color:var(--ac);min-width:22px;line-height:1.25;font-variant-numeric:tabular-nums}
.rest .tt{font-size:14.5px;font-weight:700;line-height:1.45;word-break:keep-all}

/* 뜨는 주제어 */
table.kw{width:100%;border-collapse:collapse;font-size:13.5px}
.kw th{font-size:12px;font-weight:800;padding:8px 6px;border-bottom:2px solid var(--ink);text-align:center;white-space:nowrap}
.kw td{padding:8px 6px;border-bottom:1px solid var(--rule2);font-variant-numeric:tabular-nums;text-align:center}
.kw td.w{font-weight:700;word-break:keep-all;text-align:left}
.kw td.r span{display:inline-block;min-width:3.2em;text-align:right}
.kw td.rk{color:var(--muted)}
.kw td.up{color:var(--coral-d);font-weight:800}
.kw tbody tr:last-child td{border-bottom:1px solid var(--rule)}

/* 지역 타일맵 */
.reg{display:grid;grid-template-columns:minmax(0,380px) 1fr;gap:26px;align-items:start}
.reg svg{width:100%;height:auto;display:block}
.reg svg .tn{font-size:13px;font-weight:800;text-anchor:middle;font-family:'PretendardSub','Pretendard',sans-serif}
.reg svg .tv{font-size:15px;font-weight:800;text-anchor:middle;font-variant-numeric:tabular-nums;font-family:'PretendardSub','Pretendard',sans-serif}
.rlist{list-style:none;margin:0;padding:0}
.rlist li{display:grid;grid-template-columns:96px 1fr;gap:10px;padding:10px 0;border-bottom:1px solid var(--rule2)}
.rlist li:last-child{border-bottom:0}
.rlist .rn{font-weight:800;font-size:14px;word-break:keep-all}
.rlist .rn small{display:block;font-size:12px;font-weight:700;color:var(--ac-d);font-variant-numeric:tabular-nums}
.rlist .tt{font-size:13.5px;font-weight:700;line-height:1.45;word-break:keep-all}
.rlist .tt a:hover{color:var(--ac);text-decoration:underline}

/* 월별 흐름 */
table.arch{width:100%;border-collapse:collapse;font-size:13.5px;min-width:720px}
.arch th{font-size:12px;font-weight:800;padding:9px 8px;border-bottom:2px solid var(--ink);text-align:left;white-space:nowrap}
.arch th.c{text-align:center}
.arch td{padding:12px 8px;border-bottom:1px solid var(--rule2);vertical-align:top;word-break:keep-all;line-height:1.5}
.arch td.m{font-weight:800;white-space:nowrap;font-size:14.5px}
.arch td.m small{display:block;font-weight:600;color:var(--muted);font-size:11.5px}
.arch td.n{text-align:center;font-variant-numeric:tabular-nums;white-space:nowrap}
.arch td.n b{display:inline-block;min-width:3.6em;text-align:right;font-size:14px}
.arch td.n small{display:block;color:var(--muted);font-size:11.5px}
.arch ol{margin:0;padding-left:18px}
.arch ol li{margin:2px 0;font-weight:600}
.arch ol li small{color:var(--muted);font-weight:600;margin-left:4px;white-space:nowrap}
.arch ol li a:hover{color:var(--ac);text-decoration:underline}
.arch tbody tr:last-child td{border-bottom:1px solid var(--rule)}

/* 괘선 목록 */
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
table.ttab{width:100%;border-collapse:collapse;table-layout:fixed;font-size:13px;min-width:640px}
.ttab th{text-align:left;font-weight:800;font-size:12px;color:var(--ink);padding:9px 8px;border-bottom:2px solid var(--ink);white-space:nowrap}
.ttab th.c,.ttab td.c{text-align:center}
.ttab td{padding:10px 8px;border-bottom:1px solid var(--rule2);vertical-align:top;word-break:keep-all;line-height:1.5}
.ttab td.d{color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums;text-align:center}
.ttab td.g{color:var(--sub);font-size:12.5px}
.ttab td.ti{font-weight:700}
.ttab td.ti a:hover{color:var(--ac);text-decoration:underline}
.ttab .same{display:inline-block;margin-left:6px;font-size:11px;font-weight:600;color:var(--muted);white-space:nowrap}
.ttab tbody tr:last-child td{border-bottom:1px solid var(--rule)}
.ttab th.sort{cursor:pointer;user-select:none}
.ttab th.sort:after{content:' ↕';font-weight:400;color:var(--muted)}
.ttab th.sort.asc:after{content:' ↑';color:var(--ac)}
.ttab th.sort.desc:after{content:' ↓';color:var(--ac)}
.more{position:absolute;opacity:0;pointer-events:none}
.ttab tr.ex{display:none}
.more:checked~.tw .ttab tr.ex{display:table-row}
.mbtn{display:block;margin-top:14px;text-align:center;font-size:13px;font-weight:700;color:var(--ac-d);
  border:1px solid var(--ac);border-radius:999px;padding:9px;cursor:pointer;background:#fff}
.mbtn:hover{background:var(--tint)}
.mbtn .c{display:none}
.more:checked~.mbtn .o{display:none}
.more:checked~.mbtn .c{display:inline}
.cats{display:grid;gap:18px;margin-top:18px;grid-template-columns:minmax(0,1fr)}
.cats>*{min-width:0}
.shead{margin:34px 0 4px;font-size:22px;font-weight:800;letter-spacing:-.6px}
.shead small{display:block;font-size:12.5px;font-weight:600;color:var(--muted);letter-spacing:0;margin-top:2px}

.foot{margin:34px 0 0;padding:18px 0 40px;border-top:1px solid var(--rule);font-size:12px;color:var(--muted);display:flex;gap:18px;flex-wrap:wrap;justify-content:space-between}
.foot b{color:var(--sub)}

@media(max-width:980px){.grid{grid-template-columns:1fr}.reg{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(3,1fr)}
  .kpi:nth-child(4){border-left:0}.kpi:nth-child(n+4){border-top:1px solid var(--rule2)}}
@media(max-width:720px){.tgrid{grid-template-columns:1fr}}
@media(max-width:640px){
  .hero h1{font-size:23px}.kv{font-size:26px}.kv.sm{font-size:18px}
  .kpis{grid-template-columns:repeat(2,1fr)}
  .kpi{border-left:0!important;border-top:1px solid var(--rule2)}.kpi:nth-child(-n+2){border-top:0}
  .kpi:nth-child(even){border-left:1px solid var(--rule2)!important}
  .kpi:last-child{grid-column:1/-1}
  .mast .upd{margin-left:0;text-align:left;width:100%}
  .card{padding:16px}.lead .tt{font-size:18px}
  .tabs{display:flex}.tabs label{flex:1;justify-content:center;padding:9px 10px}
  .hb .r{grid-template-columns:88px 1fr}
}
@media print{.pane{display:block!important}.tabs,.mbtn{display:none}.ttab tr.ex{display:table-row}}
</style>"""

SORT_JS = """<script>
document.querySelectorAll('table.sortable').forEach(function(t){
  t.querySelectorAll('th.sort').forEach(function(th){
    th.addEventListener('click',function(){
      var col=+th.dataset.col, asc=!th.classList.contains('asc');
      t.querySelectorAll('th.sort').forEach(function(h){h.classList.remove('asc','desc')});
      th.classList.add(asc?'asc':'desc');
      var tb=t.tBodies[0], rows=[].slice.call(tb.rows);
      rows.sort(function(a,b){
        var x=a.cells[col].dataset.k||a.cells[col].textContent, y=b.cells[col].dataset.k||b.cells[col].textContent;
        return (asc?1:-1)*x.localeCompare(y,'ko');
      });
      rows.forEach(function(r,i){r.classList.toggle('ex',i>=%d);tb.appendChild(r)});
    });
  });
});
</script>""" % SHOW


def esc(s):
    return html.escape(s or '')


def fmt(n):
    return '{:,}'.format(n)


def dt(s):
    return s.replace('-', '.')


def norm(s):
    return re.sub(r'[\W_]+', '', (s or '').lower())


def link(r, text=None):
    return '<a href="%s" target="_blank" rel="noopener">%s</a>' % (esc(r['url']), esc(text or r['title']))


def schip(r):
    s = r.get('sentiment')
    if s == '부정':
        return '<span class="chip neg">부정</span>'
    if s == '긍정':
        return '<span class="chip pos">긍정</span>'
    return ''


def where(r, track):
    """지역 트랙은 시도, 중앙 트랙은 제목에 나온 기관(첫 번째)"""
    if track == LOC:
        return r.get('sido') or '-'
    ag = rules.agencies(r['title'])
    return ag[0] if ag else '-'


def group_same(rows):
    """점수순 기사 목록에서 같은 사안(제목 주제어 3개 이상 · 짧은 제목은 절반 이상 겹침)을 묶음
    → [(대표 기사, [같은 사안 기사...]), ...] 대표 점수순"""
    groups = []
    for r in rows:
        tt = topic.tokens(r['title'])
        for g in groups:
            c = len(tt & g[2])
            if c >= 3 or (c >= 2 and c / max(min(len(tt), len(g[2])), 1) >= 0.5):
                g[1].append(r)
                break
        else:
            groups.append((r, [], tt))
    return [(a, b) for a, b, _ in groups]


def policy_first(sts, track, k):
    """기사 묶음 중 정부 · 제도(지역은 지자체 행정 포함) 기사가 30% 이상인 묶음을 앞세워 k개"""
    pol = lambda s: sum(rules.is_policy(a, track == LOC) for a in s[1]) >= 0.3 * len(s[1])
    return ([s for s in sts if s[0] and pol(s)] + [s for s in sts if s[0] and not pol(s)])[:k]


def load(track, today_s):
    d = json.load(open(os.path.join(ROOT, TRACKS[track]['file']), encoding='utf-8'))
    items, seen = [], set()
    for it in sorted(d.get('items', []), key=lambda x: x['date'], reverse=True):
        if not it.get('title') or not it.get('date'):
            continue
        k = norm(it['title'])
        if k in seen:                       # 같은 제목은 한 건만
            continue
        seen.add(k)
        r = dict(it)
        r['date'] = r['date'][:10]
        r['score'] = rules.score_item(r, today_s)
        r['cat'] = rules.category(r['title'])
        r['src'] = r.get('url')
        items.append(r)
    return items


def since(today, days):
    return (today - timedelta(days=days - 1)).isoformat()


def daily_chart(items, today, ac, n=21, w=470, h=180):
    days = [(today - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]
    cnt = {d: 0 for d in days}
    for it in items:
        if it['date'] in cnt:
            cnt[it['date']] += 1
    vmax = max(max(cnt.values()), 1) * 1.25
    step = (w - 12) / n
    bw = step * 0.64
    base = h - 22
    o = io.StringIO()
    o.write('<svg viewBox="0 0 %d %d" width="100%%" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="최근 3주 일별 기사 수">' % (w, h))
    o.write('<line x1="6" y1="%d" x2="%d" y2="%d" stroke="#E3E7ED"/>' % (base, w - 6, base))
    for i, d in enumerate(days):
        cx = 6 + step * i + step / 2
        v = cnt[d]
        bh = v / vmax * (base - 18)
        col = ac if i == n - 1 else '#D5DAE1'
        if v:
            o.write('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="1.5" fill="%s"/>' % (cx - bw / 2, base - bh, bw, bh, col))
            o.write('<text x="%.1f" y="%.1f" class="vt">%s</text>' % (cx, base - bh - 4, fmt(v)))
        if i % 4 == 0 or i == n - 1:
            o.write('<text x="%.1f" y="%d" class="xl">%s</text>' % (cx, h - 5, d[5:].replace('-', '.')))
    o.write('</svg>')
    return o.getvalue()


def hbars(pairs, top_key=None, unit=''):
    if not pairs:
        return '<p class="note">해당 기간 기사 없음</p>'
    mx = max(v for _, v, _ in pairs) or 1
    return '<div class="hb">' + ''.join(
        '<div class="r%s"><span class="nm">%s</span><span class="tr"><span class="b" style="width:%.1f%%"></span>'
        '<span class="v">%s%s</span></span></div>'
        % (' top' if k == top_key else '', esc(k), max(v / mx * 78, 2), fmt(v), ('<small>%s</small>' % esc(x)) if x else '')
        for k, v, x in pairs) + '</div>'


def issue_rank(sts, track):
    if not sts:
        return '<p class="note">여러 기사가 함께 다룬 이슈가 아직 없음</p>'
    mx = max(len(s[1]) for s in sts)
    o = '<ol class="irank">'
    for i, (h, arts, _) in enumerate(sts, 1):
        r = arts[0]
        d0, d1 = min(a['date'] for a in arts), max(a['date'] for a in arts)
        span = d0[5:].replace('-', '.') + ('' if d0 == d1 else '~' + d1[5:].replace('-', '.'))
        cats = Counter(a['cat'] for a in arts).most_common(1)[0][0]
        extra = ''
        if track == LOC:
            sd = Counter(a.get('sido') for a in arts if a.get('sido'))
            if sd:
                extra = ' · ' + ' '.join('%s %s' % (k, fmt(v)) for k, v in sd.most_common(3))
        o += ('<li><span class="rk">%d</span><div class="it">%s</div>'
              '<div class="tr"><span class="b" style="width:%.1f%%"></span><span class="v">%s건 <small>%s · %s%s</small></span></div>'
              '<div class="sub">대표 기사 %s</div></li>'
              % (i, link(r, h), max(len(arts) / mx * 58, 3), fmt(len(arts)), esc(cats), span, esc(extra), link(r)))
    return o + '</ol>'


def rising_table(rows, n_prev, n_now):
    if not rows:
        return '<p class="note">직전 7일보다 늘어난 주제어가 없음</p>'
    o = ('<table class="kw"><thead><tr><th>순위</th><th style="text-align:left">주제어</th><th>최근 7일</th><th>직전 7일</th><th>증감</th></tr></thead><tbody>')
    for i, (w, n, p) in enumerate(rows, 1):
        o += ('<tr><td class="rk">%d</td><td class="w">%s</td><td class="r"><span>%s</span></td><td class="r"><span>%s</span></td>'
              '<td class="r up"><span>▲ %s</span></td></tr>' % (i, esc(w.upper() if re.fullmatch('[a-z]+', w) else w), fmt(n), fmt(p), fmt(n - p)))
    return o + '</tbody></table>'


def region_card(items, ac_hex):
    by = {sd: [] for sd in region.SIDO}
    for it in items:
        sd = it.get('sido')
        if sd in by:
            by[sd].append(it)
    mx = max((len(v) for v in by.values()), default=0) or 1
    TW, TH, G = 86, 60, 6
    svg = '<svg viewBox="0 0 %d %d" role="img" aria-label="시도별 기사 수">' % (4 * TW + 3 * G, 5 * TH + 4 * G)
    for sd, (cx, cy) in region.TILE.items():
        n = len(by[sd])
        x, y = cx * (TW + G), cy * (TH + G)
        if n:
            op = 0.14 + 0.86 * (n / mx) ** 0.6
            svg += '<rect x="%d" y="%d" width="%d" height="%d" rx="4" fill="%s" fill-opacity="%.2f"/>' % (x, y, TW, TH, ac_hex, op)
            col = '#FFFFFF' if op > 0.55 else '#16202C'
        else:
            svg += '<rect x="%d" y="%d" width="%d" height="%d" rx="4" fill="#EEF0F3"/>' % (x, y, TW, TH)
            col = '#A3AAB5'
        svg += ('<text class="tn" x="%d" y="%d" fill="%s">%s</text><text class="tv" x="%d" y="%d" fill="%s">%s</text>'
                % (x + TW / 2, y + 25, col, sd, x + TW / 2, y + 46, col, fmt(n)))
    svg += '</svg>'
    top = sorted(((sd, v) for sd, v in by.items() if v), key=lambda kv: -len(kv[1]))[:6]
    li = ''
    for sd, v in top:
        r = sorted(v, key=lambda x: (-x['score'], x['date']))[0]
        li += ('<li><div class="rn">%s<small>%s건</small></div><div><div class="tt">%s</div>'
               '<div class="meta">%s · %s</div></div></li>' % (sd, fmt(len(v)), link(r), dt(r['date']), esc(r['cat'])))
    return svg, '<ol class="rlist">%s</ol>' % li


def agency_card(items):
    by = {}
    for it in items:
        for a in rules.agencies(it['title']):
            by.setdefault(a, []).append(it)
    rows = sorted(by.items(), key=lambda kv: -len(kv[1]))
    bars = hbars([(a, len(v), '') for a, v in rows[:10]], rows[0][0] if rows else None)
    li = ''
    for a, v in rows[:6]:
        r = sorted(v, key=lambda x: (-x['score'], x['date']))[0]
        li += ('<li><div class="rn">%s<small>%s건</small></div><div><div class="tt">%s</div>'
               '<div class="meta">%s · %s</div></div></li>' % (esc(a), fmt(len(v)), link(r), dt(r['date']), esc(r['cat'])))
    n_hit = sum(1 for it in items if rules.agencies(it['title']))
    return bars, '<ol class="rlist">%s</ol>' % li, n_hit


def cat_table(key, rows, track):
    groups = group_same(rows)
    ordered = [g[0] for g in groups] + [m for g in groups for m in g[1]]
    dup = {id(g[0]): len(g[1]) for g in groups}
    body = ''
    for i, r in enumerate(ordered):
        s = r.get('sentiment') or '중립'
        body += ('<tr%s><td class="d" data-k="%s">%s</td><td class="g">%s</td><td class="ti" data-k="%s">%s</td>'
                 '<td class="c" data-k="%s">%s</td></tr>'
                 % (' class="ex"' if i >= SHOW else '', r['date'], r['date'][5:].replace('-', '.'),
                    esc(where(r, track)), esc(r['title']),
                    link(r) + ('<span class="same">같은 사안 %s건 더</span>' % fmt(dup[id(r)]) if dup.get(id(r)) else ''),
                    s, schip(r) or '<span class="meta">중립</span>'))
    rest = len(ordered) - SHOW
    o = '<input class="more" type="checkbox" id="more-%s">' % key if rest > 0 else ''
    o += ('<div class="tw"><table class="ttab sortable"><colgroup><col style="width:9%%"><col style="width:15%%">'
          '<col style="width:66%%"><col style="width:10%%"></colgroup><thead><tr>'
          '<th class="sort c" data-col="0">일자</th><th class="sort" data-col="1">%s</th>'
          '<th class="sort" data-col="2">제목</th><th class="sort c" data-col="3">감성</th></tr></thead>'
          '<tbody>%s</tbody></table></div>' % ('시도' if track == LOC else '언급 기관', body))
    if rest > 0:
        o += ('<label class="mbtn" for="more-%s"><span class="o">더보기 %s건</span><span class="c">접기</span></label>'
              % (key, fmt(rest)))
    return o


def headline(items, track, today):
    """오늘의 핵심 이슈 : 수동 지정 → 최근 3일 기사 묶음(3건 이상) → 최근 7일 묶음 → 점수 1위 기사"""
    today_s = today.isoformat()
    ov = topic.load_override(ROOT, track, today_s)
    if ov:
        return ov, [], '담당자 지정', []
    for days in (3, 7):
        pool = [r for r in items if r['date'] >= since(today, days) and rules.relevant(r)]
        sts = [s for s in topic.stories(pool, 8) if s[0]]
        pol = [s for s in sts if len(s[1]) >= (5 if days == 3 else 4)
               and sum(rules.is_policy(a, track == LOC) for a in s[1]) >= 0.3 * len(s[1])]
        if pol:
            top = pol[0]
            rest = policy_first([s for s in sts if s is not top], track, 3)
            return top[0], top[1], '최근 %d일 관련 기사 %s건' % (days, fmt(len(top[1]))), rest
    pool = sorted([r for r in items if r['date'] >= since(today, 7) and rules.relevant(r)], key=lambda x: (-x['score'], x['date']))
    if pool:
        return topic._fit(topic._seg_title(pool[0]['title'])[0] if topic._seg_title(pool[0]['title']) else pool[0]['title']), pool[:1], '점수 1위 기사 기준', []
    return TRACKS[track]['label'] + ' 청년정책 이슈 없음', [], '', []


def month_label(m):
    y, mm = m.split('-')
    return '%s년 %d월' % (y, int(mm))


def archive(items, track, today):
    months = sorted({r['date'][:7] for r in items if r['date'][:7] >= ARCH_FROM}, reverse=True)
    mx = max((sum(1 for r in items if r['date'][:7] == m and rules.relevant(r)) for m in months), default=1) or 1
    body = ''
    for m in months:
        pool = [r for r in items if r['date'][:7] == m and rules.relevant(r)]
        neg = sum(1 for r in pool if r.get('sentiment') == '부정')
        sts = policy_first(topic.stories(pool, 8), track, 3)
        cats = Counter(r['cat'] for r in pool if r['cat'] != '기타').most_common(2)
        partial = ' (진행 중)' if m == today.isoformat()[:7] else ''
        lis = ''.join('<li>%s<small>%s건</small></li>' % (link(a[0], h), fmt(len(a))) for h, a, _ in sts if h) \
            or '<li>묶음 이슈 없음</li>'
        body += ('<tr><td class="m">%s<small>%s</small></td>'
                 '<td class="n"><b>%s</b><small>부정 %s건</small></td>'
                 '<td class="g">%s</td><td><ol>%s</ol></td></tr>'
                 % (month_label(m), partial.strip(' ()') or '월 합계', fmt(len(pool)), fmt(neg),
                    ' · '.join('%s %s' % (esc(c), fmt(n)) for c, n in cats), lis))
    early = [r for r in items if r['date'][:7] < ARCH_FROM]
    cap_early = (' · 그 이전 수집분 %s건(%s~)은 누적 수에만 포함' % (fmt(len(early)), dt(min(r['date'] for r in early))[:7])) if early else ''
    return ('<div class="tw"><table class="arch"><colgroup><col style="width:13%%"><col style="width:11%%"><col style="width:22%%"><col style="width:54%%"></colgroup>'
            '<thead><tr><th>월</th><th class="c">기사 수</th><th>많이 다룬 주제</th><th>그달의 핵심 이슈 3</th></tr></thead>'
            '<tbody>%s</tbody></table></div>' % body), cap_early


def pane(items, track, days, today):
    today_s = today.isoformat()
    tkey = 'cen' if track == CEN else 'loc'
    ac = '#2B3A55' if track == CEN else '#E85A3C'
    rel_all = [r for r in items if rules.relevant(r)]
    recent = [r for r in rel_all if r['date'] >= since(today, days)]
    prev = [r for r in rel_all if since(today, 2 * days) <= r['date'] < since(today, days)]
    by_cat = {}
    for r in recent:
        by_cat.setdefault(r['cat'], []).append(r)
    cat_order = sorted(by_cat, key=lambda c: (c == '기타', -len(by_cat[c])))
    top_cat = cat_order[0] if cat_order else None
    n_today = sum(1 for r in items if r['date'] == today_s)
    n_since_jun = sum(1 for r in items if r['date'][:7] >= ARCH_FROM)
    neg7 = sum(1 for r in recent if r.get('sentiment') == '부정')

    o = io.StringIO()
    # 1) 오늘의 핵심 이슈
    head, cl, basis, others = headline(items, track, today)
    rep = ''
    if cl:
        r = cl[0]
        rep = ' · 대표 기사 %s %s' % (link(r), dt(r['date']))
    o.write('<section class="hero"><div class="eyebrow">%s 오늘의 핵심 이슈 · %s</div><h1>%s</h1><p class="dek">%s%s</p>'
            % (esc(TRACKS[track]['label']), dt(today_s), esc(head), basis, rep))
    if others:
        o.write('<ul class="also">' + ''.join('<li><b>함께 본 이슈</b>%s <span class="meta">%s건</span></li>'
                                               % (link(a[0], h), fmt(len(a))) for h, a, _ in others if h) + '</ul>')
    o.write('</section>')

    # 2) KPI
    kp = [(fmt(len(recent)), '', '최근 %d일 기사' % days, '청년정책 관련 · 중복 제외'),
          (fmt(n_today), '', '오늘 보도', dt(today_s) + ' 기준'),
          (fmt(n_since_jun), '', '6월 이후 누적', ('수집 전체 %s건' % fmt(len(items))) if len(items) > n_since_jun
           else '%s 수집 시작' % dt(min(r['date'] for r in items))),
          (fmt(neg7), 'neg', '부정 보도', '최근 %d일 · 비중 %.1f%%' % (days, neg7 / max(len(recent), 1) * 100)),
          (top_cat or '-', 'sm', '최다 주제', ('%s건' % fmt(len(by_cat[top_cat]))) if top_cat else '')]
    o.write('<div class="kpis">' + ''.join(
        '<div class="kpi"><div class="kv %s">%s</div><div class="kl">%s</div><div class="ks">%s</div></div>' % (c, v, l, s)
        for v, c, l, s in kp) + '</div>')

    # 3) 이번 주 핵심 이슈 순위 + 주제 분포 · 추이
    sts = topic.stories(recent, 6)
    o.write('<div class="grid">')
    o.write('<section class="card"><div class="sec">ISSUES</div><div class="h2">이번 주 핵심 이슈 순위</div>'
            '<div class="cap">최근 %d일 청년정책 기사 중 같은 사안을 다룬 기사 묶음 · 막대는 관련 기사 수(건) · 제목을 누르면 대표 기사</div>%s</section>'
            % (days, issue_rank(sts, track)))
    o.write('<div style="display:grid;gap:18px;min-width:0">')
    pairs = [(c, len(by_cat[c]), '%.0f%%' % (len(by_cat[c]) / max(len(recent), 1) * 100)) for c in cat_order]
    pairs.sort(key=lambda x: -x[1])
    o.write('<section class="card"><div class="sec">MIX</div><div class="h2">이슈가 몰린 주제</div>'
            '<div class="cap">최근 %d일 · 단위 : 건 · 괄호 옆은 비중</div>%s</section>' % (days, hbars(pairs, top_cat)))
    o.write('<section class="card"><div class="sec">DAILY</div><div class="h2">최근 3주 보도 추이</div>'
            '<div class="cap">보도일 기준 · 단위 : 건 · 마지막 막대가 오늘</div>%s</section>' % daily_chart(rel_all, today, ac))
    o.write('</div></div>')

    # 4) 주제별 핵심 정리
    o.write('<div class="shead">주제별 핵심 정리<small>최근 %d일 · 주제마다 가장 크게 다뤄진 이슈와 먼저 볼 기사 3건</small></div>' % days)
    o.write('<div class="tgrid">')
    for c in cat_order:
        v = by_cat[c]
        st = topic.stories(v, 1)
        tk = ('<div class="tk">%s<small>관련 %s건</small></div>' % (link(st[0][1][0], st[0][0]), fmt(len(st[0][1])))) if st and st[0][0] else ''
        neg = sum(1 for r in v if r.get('sentiment') == '부정')
        used = {id(a) for a in st[0][1]} if st else set()
        arts = [g[0] for g in group_same(sorted(v, key=lambda x: (-x['score'], x['date']))) if id(g[0]) not in used]
        li = ''.join('<li>%s<div class="meta">%s%s %s</div></li>'
                     % (link(r), dt(r['date']), (' · ' + esc(where(r, track))) if where(r, track) != '-' else '', schip(r))
                     for r in arts[:3])
        o.write('<section class="tcard"><div class="th"><span class="tn">%s</span><span class="tc">%s건 <small>부정 %s건</small></span></div>%s<ul>%s</ul></section>'
                % (esc(c), fmt(len(v)), fmt(neg), tk, li))
    o.write('</div>')

    # 5) 먼저 볼 기사 + 뜨는 주제어
    tops = [g[0] for g in group_same(sorted(recent, key=lambda x: (-x['score'], x['date'])))][:5]
    o.write('<div class="grid g2">')
    o.write('<section class="card"><div class="sec">LEAD</div><div class="h2">먼저 볼 기사</div>'
            '<div class="cap">정부 · 국회 · 예산 · 제도 관련성, 부정 보도, 최신성으로 매긴 점수순</div>')
    if tops:
        r = tops[0]
        chips = '<span class="chip">%s</span> %s' % (esc(r['cat']), schip(r))
        if r['score'] >= 9:
            chips += ' <span class="chip hot">주목</span>'
        wh = lambda r: (' · <b>%s</b>' % esc(where(r, track))) if where(r, track) != '-' else ''
        o.write('<div class="lead">%s<div class="tt">%s</div><div class="meta">%s%s · 점수 %s</div></div><ol class="rest">'
                % (chips, link(r), dt(r['date']), wh(r), fmt(r['score'])))
        for i, r in enumerate(tops[1:], 2):
            o.write('<li><span class="rk">%d</span><div><div class="tt">%s</div><div class="meta">%s%s · %s · 점수 %s %s</div></div></li>'
                    % (i, link(r), dt(r['date']), wh(r), esc(r['cat']), fmt(r['score']), schip(r)))
        o.write('</ol>')
    else:
        o.write('<p class="note">해당 기간 기사 없음</p>')
    o.write('</section>')
    rows = topic.rising(recent, prev)
    o.write('<section class="card"><div class="sec">KEYWORDS</div><div class="h2">뜨는 주제어</div>'
            '<div class="cap">제목에 나온 주제어의 기사 수 · 최근 7일과 직전 7일 비교 · 단위 : 건</div>%s'
            '<p class="note">같은 사안에서 함께 나오는 말은 하나만 남김</p></section>' % rising_table(rows, len(prev), len(recent)))
    o.write('</div>')

    # 6) 지역별(지역) / 기관별(중앙)
    if track == LOC:
        svg, rl = region_card(recent, ac)
        o.write('<section class="card g2"><div class="sec">REGION</div><div class="h2">시도별 보도</div>'
                '<div class="cap">최근 %d일 · 색이 진할수록 기사가 많음 · 오른쪽은 기사 많은 시도의 대표 기사 · 단위 : 건</div>'
                '<div class="reg"><div>%s</div><div>%s</div></div></section>' % (days, svg, rl))
    else:
        bars, rl, n_hit = agency_card(recent)
        o.write('<section class="card g2"><div class="sec">AGENCY</div><div class="h2">기관별 보도</div>'
                '<div class="cap">최근 %d일 · 제목에 기관명이 나온 기사 %s건 · 오른쪽은 기관별 대표 기사 · 단위 : 건</div>'
                '<div class="reg"><div>%s</div><div>%s</div></div></section>' % (days, fmt(n_hit), bars, rl))

    # 7) 월별 흐름
    tb, cap_early = archive(items, track, today)
    o.write('<section class="card g2"><div class="sec">ARCHIVE</div><div class="h2">6월 이후 월별 흐름</div>'
            '<div class="cap">월별 청년정책 기사 수 · 많이 다룬 주제 · 그달 가장 크게 다뤄진 이슈 3개(관련 기사 수)%s</div>%s</section>'
            % (cap_early, tb))

    # 8) 주제별 기사 목록
    o.write('<div class="shead">주제별 기사 목록<small>최근 %d일 · 같은 사안은 대표 기사 한 건만 앞에 두고 나머지는 더보기 안에 · 머리글을 누르면 일자 · %s · 제목 · 감성순 정렬</small></div>'
            % (days, '시도' if track == LOC else '기관'))
    o.write('<div class="cats">')
    for ci, c in enumerate(cat_order):
        v = sorted(by_cat[c], key=lambda x: (-x['score'], x['date']))
        o.write('<section class="card"><div class="sec">%s</div><div class="h2">%s<span class="n">%s건</span></div>%s</section>'
                % (esc(TRACKS[track]['label']), esc(c), fmt(len(v)), cat_table('%s-%d' % (tkey, ci), v, track)))
    o.write('</div>')
    return o.getvalue(), len(recent), head


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=7)
    a = ap.parse_args()
    now = datetime.now(KST)
    today = now.date()
    cen = load(CEN, today.isoformat())
    loc = load(LOC, today.isoformat())
    cen_html, n_cen, cen_head = pane(cen, CEN, a.days, today)
    loc_html, n_loc, loc_head = pane(loc, LOC, a.days, today)

    o = io.StringIO()
    o.write('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>청년정책 이슈 레이더 | 중앙정부 · 지역정부</title>'
            '<link rel="preload" href="assets/fonts/pretendard-sub-ExtraBold.woff2" as="font" type="font/woff2" crossorigin>')
    o.write(CSS + '</head><body>')
    o.write('<input class="trk" type="radio" name="trk" id="trk-cen" checked><input class="trk" type="radio" name="trk" id="trk-loc">')
    o.write('<header class="mast"><div class="in"><div class="brand"><span class="mk"></span>'
            '<div class="team"><span class="t1">(주)서던포스트 · 2026 중앙행정기관 청년정책 분석·평가</span>'
            '<span class="t2">청년정책 이슈 레이더</span></div></div>'
            '<div class="upd"><b>%s 업데이트</b>매일 08:00 자동 수집 · <a href="index.html">분석·평가 콘솔로</a></div>'
            '</div><div class="ribbon"><i></i><i></i></div></header>' % now.strftime('%Y.%m.%d %H:%M'))
    o.write('<div class="wrap">')
    o.write('<div class="tabs"><label for="trk-cen">중앙정부 <small>최근 %d일 %s건</small></label>'
            '<label for="trk-loc">지역정부 <small>최근 %d일 %s건</small></label></div>' % (a.days, fmt(n_cen), a.days, fmt(n_loc)))
    o.write('<div class="pane pane-cen">%s</div><div class="pane pane-loc">%s</div>' % (cen_html, loc_html))
    o.write('<footer class="foot"><span><b>(주)서던포스트</b> · 청년정책 이슈 레이더 · 중앙(과제 매칭 뉴스) · 지역(17개 시도 청년정책 뉴스)</span>'
            '<span>네이버 뉴스 검색 API · 감성은 자동 분류 · 점수는 편집 판단을 돕는 보조 지표임</span></footer>')
    o.write('</div>' + SORT_JS + '</body></html>')
    out = o.getvalue().replace('—', '-').replace('–', '-')
    open(OUT, 'w', encoding='utf-8').write(out)
    print('생성 : %s (%s bytes · 중앙 %d건 · 지역 %d건)' % (OUT, fmt(len(out.encode('utf-8'))), n_cen, n_loc))
    print('  헤드라인 : 중앙 「%s」 / 지역 「%s」' % (cen_head, loc_head))


if __name__ == '__main__':
    main()
