# -*- coding: utf-8 -*-
"""일일 이슈 브리핑 PDF 보관함

  briefs/YYYYMMDD.pdf      : 매일 예약 작업이 만든 A4 한 장 브리핑 (청년정책_이슈브리핑_YYYYMMDD.pdf)
  briefs/index.json        : [{date, file, cen, loc, sel, merged, issues:[3건 제목], delayed}]  (선택, 없으면 PDF만 나열)
  briefs/index.html        : 날짜별 전체 목록 (이 스크립트가 생성)
  index2.html              : <!--BRIEFS--> ... <!--/BRIEFS--> 구간을 최신 목록으로 교체

사용법
  python radar2/briefs.py add <pdf경로> --date 2026-10-21 --cen 176 --loc 191 --sel 250 --merged 70 --issue "제목1" --issue "제목2" --issue "제목3"
  python radar2/briefs.py build          # briefs/index.html 재생성 + index2.html 구간 교체
"""
import argparse, glob, html, json, os, re, shutil
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BDIR = os.path.join(ROOT, 'briefs')
IDX = os.path.join(BDIR, 'index.json')
WD = '월화수목금토일'
SHOW = 7


def esc(s):
    return html.escape(s or '')


def load():
    try:
        meta = {m['date']: m for m in json.load(open(IDX, encoding='utf-8'))}
    except Exception:
        meta = {}
    rows = []
    for p in glob.glob(os.path.join(BDIR, '*.pdf')):
        m = re.match(r'(\d{4})(\d{2})(\d{2})\.pdf$', os.path.basename(p))
        if not m:
            continue
        d = '%s-%s-%s' % m.groups()
        r = dict(meta.get(d, {}))
        r.update(date=d, file=os.path.basename(p), kb=os.path.getsize(p) // 1024)
        rows.append(r)
    return sorted(rows, key=lambda r: r['date'], reverse=True)


def dlabel(d):
    y, m, dd = map(int, d.split('-'))
    return '%04d. %02d. %02d. (%s)' % (y, m, dd, WD[date(y, m, dd).weekday()])


def item(r, prefix):
    fn = '청년정책_이슈브리핑_%s.pdf' % r['date'].replace('-', '')
    href = prefix + r['file']
    stat = []
    if r.get('cen') is not None:
        stat.append('신규 %s건 (중앙 %s · 지역 %s)' % (format(r['cen'] + r['loc'], ','), format(r['cen'], ','), format(r['loc'], ',')))
    if r.get('sel') is not None:
        stat.append('선별 %s건 → 통합 %s건' % (format(r['sel'], ','), format(r.get('merged', 0), ',')))
    if r.get('delayed'):
        stat.append('<b class="dl">수집 지연</b>')
    iss = ''.join('<li>%s</li>' % esc(t) for t in r.get('issues', [])[:3])
    return ('<li class="bf"><div class="bd"><b>%s</b><small>%s</small></div>'
            '<div class="bi">%s<div class="bs">%s</div></div>'
            '<div class="bl"><a class="bv" href="%s" target="_blank" rel="noopener">보기</a>'
            '<a class="bdn" href="%s" download="%s">PDF 받기 <small>%s KB</small></a></div></li>'
            % (dlabel(r['date']), '일일 이슈 브리핑', ('<ol>%s</ol>' % iss) if iss else '<span class="bn">핵심 이슈 3건 · A4 1쪽</span>',
               ' · '.join(stat), href, href, fn, format(r['kb'], ',')))


CSS = """<style>
.briefs{background:#fff;border:1px solid var(--rule);border-top:3px solid var(--ink);padding:20px 22px 18px;margin-top:34px}
.briefs .bh{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;flex-wrap:wrap}
.briefs .bh .t{font-size:22px;font-weight:800;letter-spacing:-.6px}
.briefs .bh .t small{display:block;font-size:12.5px;font-weight:600;color:var(--muted);letter-spacing:0;margin-top:2px}
.briefs .bh a{font-size:13px;font-weight:700;color:var(--navy);border-bottom:1px solid var(--rule)}
.blist{list-style:none;margin:12px 0 0;padding:0}
.bf{display:grid;grid-template-columns:150px 1fr auto;gap:8px 18px;align-items:start;padding:12px 0;border-top:1px solid var(--rule2)}
.bf .bd b{display:block;font-size:14px;font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap}
.bf .bd small{font-size:11.5px;color:var(--muted)}
.bf .bi ol{margin:0;padding-left:18px;font-size:13.5px;font-weight:700;line-height:1.5;word-break:keep-all}
.bf .bn{font-size:13px;color:var(--sub)}
.bf .bs{font-size:12px;color:var(--muted);margin-top:3px}
.bf .bs .dl{color:#C6452B}
.bf .bl{display:flex;gap:6px;white-space:nowrap}
.bf .bl a{font-size:12.5px;font-weight:700;border-radius:999px;padding:6px 12px;border:1px solid var(--rule)}
.bf .bl a.bdn{background:#152484;border-color:#152484;color:#fff}
.bf .bl a.bdn small{font-weight:600;opacity:.8}
.bf .bl a.bv:hover{border-color:#152484}
.bempty{font-size:13px;color:var(--muted);padding:12px 0;border-top:1px solid var(--rule2)}
@media(max-width:720px){.bf{grid-template-columns:1fr}.bf .bl{margin-top:2px}}
</style>"""


def section(rows, prefix='briefs/', limit=SHOW, full_link=True):
    body = ''.join(item(r, prefix) for r in rows[:limit]) if rows else ''
    more = ('<a href="briefs/index.html">전체 %d건 보기 →</a>' % len(rows)) if full_link and rows else ''
    return ('%s<section class="briefs" id="briefs"><div class="bh"><div class="t">일일 이슈 브리핑 PDF'
            '<small>매일 오전 수집분을 추려 만든 A4 한 장 브리핑 · 날짜별로 보기 · 내려받기</small></div>%s</div>'
            '%s</section>' % (CSS, more, ('<ul class="blist">%s</ul>' % body) if body else '<div class="bempty">아직 올라온 브리핑이 없음</div>'))


def block(rows):
    return '<!--BRIEFS-->%s<!--/BRIEFS-->' % section(rows)


def page(rows):
    root_css = (':root{--navy:#152484;--coral:#E85A3C;--ink:#16202C;--sub:#4A5463;--muted:#8A93A0;--rule:#E3E7ED;--rule2:#F0F2F5;--bg:#F6F7F9}'
                '*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:"Pretendard","Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",sans-serif;font-size:14px;line-height:1.55}'
                'a{color:inherit;text-decoration:none}.mast{background:#fff;border-bottom:1px solid var(--rule)}'
                '.mast .in{max-width:1080px;margin:0 auto;padding:14px 16px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}'
                '.mast img{height:30px}.mast .sep{width:1px;height:32px;background:var(--rule)}.mast .t1{font-size:12px;font-weight:600;color:var(--muted)}'
                '.mast .t2{font-size:17px;font-weight:800}.mast .bk{margin-left:auto;font-size:13px;font-weight:700;color:var(--navy)}'
                '.ribbon{display:flex;height:4px}.ribbon i{flex:1}.ribbon i:first-child{background:var(--navy)}.ribbon i:last-child{background:var(--coral)}'
                '.wrap{max-width:1080px;margin:0 auto;padding:0 16px 40px}.briefs{margin-top:24px}')
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>일일 이슈 브리핑 모음 | 청년정책 이슈 레이더</title><style>%s</style></head><body>'
            '<header class="mast"><div class="in"><img src="../assets/brand/southernpost_ko.png" alt="(주)서던포스트"><span class="sep"></span>'
            '<div><div class="t1">2026 중앙행정기관 청년정책 분석·평가</div><div class="t2">일일 이슈 브리핑 모음</div></div>'
            '<a class="bk" href="../index2.html">← 이슈 레이더로</a></div><div class="ribbon"><i></i><i></i></div></header>'
            '<div class="wrap">%s</div></body></html>' % (root_css, section(rows, prefix='', limit=10 ** 6, full_link=False)))


def build():
    rows = load()
    os.makedirs(BDIR, exist_ok=True)
    open(os.path.join(BDIR, 'index.html'), 'w', encoding='utf-8').write(page(rows))
    p2 = os.path.join(ROOT, 'index2.html')
    if os.path.exists(p2):
        s = open(p2, encoding='utf-8').read()
        if '<!--BRIEFS-->' in s:
            s = re.sub(r'<!--BRIEFS-->.*?<!--/BRIEFS-->', lambda m: block(rows), s, flags=re.S)
        else:
            s = s.replace('<footer class="foot">', block(rows) + '<footer class="foot">', 1)
        open(p2, 'w', encoding='utf-8').write(s)
    print('브리핑 %d건 · briefs/index.html, index2.html 갱신' % len(rows))


def add(a):
    os.makedirs(BDIR, exist_ok=True)
    d = a.date
    shutil.copyfile(a.pdf, os.path.join(BDIR, d.replace('-', '') + '.pdf'))
    try:
        meta = json.load(open(IDX, encoding='utf-8'))
    except Exception:
        meta = []
    meta = [m for m in meta if m.get('date') != d]
    m = {'date': d, 'file': d.replace('-', '') + '.pdf'}
    for k in ('cen', 'loc', 'sel', 'merged'):
        if getattr(a, k) is not None:
            m[k] = getattr(a, k)
    if a.issue:
        m['issues'] = a.issue
    if a.delayed:
        m['delayed'] = True
    meta.append(m)
    meta.sort(key=lambda x: x['date'])
    json.dump(meta, open(IDX, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    build()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd')
    sp.add_parser('build')
    p = sp.add_parser('add')
    p.add_argument('pdf')
    p.add_argument('--date', required=True)
    for k in ('cen', 'loc', 'sel', 'merged'):
        p.add_argument('--' + k, type=int)
    p.add_argument('--issue', action='append')
    p.add_argument('--delayed', action='store_true')
    a = ap.parse_args()
    add(a) if a.cmd == 'add' else build()
