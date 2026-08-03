"""Render the dashboard HTML (TailAdmin-style layout) from the analysed model.

No network calls, no AI. Charts use Chart.js from cdnjs (free CDN) with a
text fallback when offline. Chart colors follow a validated palette:
series blue #2a78d6, positive green #008300, negative red #dc2626.
"""
from __future__ import annotations
import html
import json


# ----------------------------------------------------------------- helpers
def _inr(x, dec=0):
    if x is None:
        return "—"
    neg = x < 0
    x = abs(x)
    s = f"{x:,.{dec}f}"
    if "." in s:
        intpart, frac = s.split(".")
    else:
        intpart, frac = s, ""
    intpart = intpart.replace(",", "")
    if len(intpart) > 3:
        last3, rest = intpart[-3:], intpart[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        intpart = ",".join(parts + [last3])
    out = intpart + (("." + frac) if frac else "")
    return ("-₹" if neg else "₹") + out


def _pct(x):
    return "—" if x is None else f"{x:+.2f}%"


def _cls(x):
    if x is None:
        return "flat"
    return "up" if x >= 0 else "down"


def _lakh_cr(x):
    if x is None:
        return "—"
    return f"₹{x/1e7:,.0f} cr"


LEVEL_COLORS = {"act": "#b45309", "warn": "#b91c1c", "good": "#047857",
                "info": "#475569", "": "#475569"}

TICKER_HUES = [210, 25, 160, 45, 330, 120, 260, 0, 190, 285]



def _news_link(n, big=False):
    """Render one news item. Splits Google-News 'Title - Publisher' tails."""
    title = n.get("title", "")
    source = ""
    if " - " in title:
        head, tail = title.rsplit(" - ", 1)
        if 2 < len(tail) <= 34:
            title, source = head, tail
    ncls = "neg" if n.get("negative") else ("pos" if n.get("positive") else "")
    ncls += " big" if big else ""
    src_html = f'<span class="src">{html.escape(source)}</span>' if source else ""
    ev = f'<span class="evt">{html.escape(n["event"])}</span>' if n.get("event") else ""
    return (f'<a class="news {ncls}" href="{html.escape(n.get("link",""))}" target="_blank" rel="noopener">'
            f'<span class="nt">{html.escape(title)}</span>'
            f'<span class="nm2">{src_html}{ev}<em>{html.escape(n.get("published",""))}</em></span></a>')


def _chip(sig):
    color = LEVEL_COLORS.get(sig.get("level", ""), "#475569")
    return f'<span class="chip" style="--c:{color}">{html.escape(sig["text"])}</span>'


def _avatar(ticker):
    hue = TICKER_HUES[sum(ord(c) for c in ticker) % len(TICKER_HUES)]
    return (f'<span class="av" style="--h:{hue}">{html.escape(ticker[:2])}</span>')


# ----------------------------------------------------------------- CSS (plain string — real braces)
CSS = """
:root{--bg:#f4f6fa;--card:#fff;--ink:#0f172a;--muted:#64748b;--line:#e6e8ef;
--up:#008300;--down:#dc2626;--flat:#64748b;--accent:#2a78d6;--sidebar:#0f172a;--sbink:#cbd5e1;}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
background:var(--bg);color:var(--ink);font-size:14px;line-height:1.45}
.up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--flat)} .muted{color:var(--muted)}
.layout{display:flex;min-height:100vh}
/* ---------- sidebar ---------- */
.sidebar{width:225px;background:var(--sidebar);color:var(--sbink);padding:20px 14px;display:flex;
flex-direction:column;gap:4px;position:sticky;top:0;height:100vh;flex-shrink:0}
.brand{color:#fff;font-size:17px;font-weight:800;letter-spacing:-.3px;padding:4px 10px 18px;display:flex;gap:8px;align-items:center}
.navlbl{font-size:10.5px;text-transform:uppercase;letter-spacing:.8px;color:#64748b;padding:8px 10px 4px}
.nav{display:flex;flex-direction:column;gap:2px}
.nav a{color:var(--sbink);text-decoration:none;padding:9px 10px;border-radius:9px;font-size:13.5px;
display:flex;align-items:center;gap:10px;cursor:pointer}
.nav a:hover{background:rgba(255,255,255,.06);color:#fff}
.nav a.active{background:var(--accent);color:#fff;font-weight:600}
.nav .cnt{margin-left:auto;font-size:10.5px;background:rgba(255,255,255,.14);border-radius:99px;padding:1px 7px}
.sidefoot{margin-top:auto;display:flex;flex-direction:column;gap:8px}
.editbtn{border:none;background:rgba(255,255,255,.1);color:#fff;border-radius:9px;padding:9px 12px;
cursor:pointer;font-size:13px;font-weight:600;text-align:left}
.editbtn:hover{background:rgba(255,255,255,.18)}
.stamp{font-size:10.5px;color:#64748b;padding:0 10px;line-height:1.5}
/* ---------- main ---------- */
.main{flex:1;padding:22px 26px;min-width:0}
.topbar{display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap}
.topbar h1{font-size:19px;margin:0;letter-spacing:-.3px}
.topbar .sub{color:var(--muted);font-size:12.5px}
section{display:none} section.show{display:block}
/* ---------- cards ---------- */
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px 16px}
.card .k{color:var(--muted);font-size:11.5px;text-transform:uppercase;letter-spacing:.4px}
.card .v{font-size:21px;font-weight:800;margin-top:5px;letter-spacing:-.4px}
.pill{display:inline-flex;align-items:center;font-size:11.5px;font-weight:700;border-radius:99px;padding:2px 9px;margin-top:6px}
.pill.up{background:#e8f5e9;color:var(--up)} .pill.down{background:#fdecec;color:var(--down)}
.grid-main{display:grid;grid-template-columns:2fr 1fr;gap:14px;margin-bottom:16px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}
.panel h2{font-size:13px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin:0 0 12px;display:flex;align-items:center;gap:8px}
.panel h2 .sp{flex:1}
.rangebtns{display:flex;gap:4px}
.rangebtns button{border:1px solid var(--line);background:#fff;border-radius:7px;padding:3px 9px;cursor:pointer;font-size:11.5px}
.rangebtns button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.chartbox{position:relative;height:260px}
.chartbox.sm{height:220px}
.chartbox.lg{height:340px}
.chartb{border:none;background:none;cursor:pointer;font-size:13px;padding:0 4px;opacity:.45;line-height:1}
.chartb:hover{opacity:1}
.rangebtns2{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
.rangebtns2 button{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:6px 14px;cursor:pointer;font-size:12.5px}
.rangebtns2 button.on{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
.pxstats{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin:10px 2px 0}
.pxstats b{color:var(--ink)}
.nochart{color:var(--muted);font-size:12.5px;padding:30px 0;text-align:center}
/* watch list rows */
.wrow{display:flex;align-items:center;gap:11px;padding:9px 2px;border-bottom:1px solid var(--line)}
.wrow:last-child{border-bottom:none}
.av{width:34px;height:34px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
font-size:11.5px;font-weight:800;color:hsl(var(--h),55%,32%);background:hsl(var(--h),70%,92%);flex-shrink:0}
.wrow .wn{min-width:0} .wrow .wn b{font-size:13px} .wrow .wn div{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wrow .wp{margin-left:auto;text-align:right}
.wrow .wp b{font-size:13px;font-variant-numeric:tabular-nums}
.wrow .wp .pill{margin-top:2px}
.mvgrid{display:flex;gap:8px;flex-wrap:wrap}
.mvr{border:1px solid var(--line);border-radius:10px;padding:8px 10px;min-width:90px}
.mvr-t{font-weight:700;font-size:12.5px}.mvr-p{font-weight:700;font-size:13px}.mvr-s{font-size:10.5px;color:var(--muted)}
.mvr.up{background:#f0f9f0}.mvr.down{background:#fdf2f2}
ul.act{margin:0;padding-left:18px}ul.act li{margin-bottom:8px}
.note{color:#b45309;font-size:12.5px}
ul.corp{columns:2;column-gap:28px}ul.corp li{break-inside:avoid;margin-bottom:8px}
.warnbar{background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;border-radius:10px;padding:8px 12px;font-size:12.5px;margin:10px 0}
/* ---------- table ---------- */
.tablecard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:6px;overflow:auto}
.controls{display:flex;gap:8px;padding:8px;flex-wrap:wrap;align-items:center}
.controls button{border:1px solid var(--line);background:#fff;border-radius:8px;padding:6px 10px;cursor:pointer;font-size:12.5px}
.controls button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.controls button.simbtn{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
.controls button.on::after{content:" ↓";font-size:11px}
.controls button.on.asc::after{content:" ↑"}
.controls input{border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:12.5px;width:150px;margin-left:auto}
.controls input:focus{outline:none;border-color:#94a3b8}
table.data{width:100%;border-collapse:collapse;font-size:13px;min-width:1000px}
table.data th,table.data td{padding:9px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
table.data th{font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted);white-space:nowrap;position:sticky;top:0;background:var(--card);z-index:1}
td.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
td.tk .nm{color:var(--muted);font-size:11.5px;font-weight:400}
td .sub{font-size:11px;color:var(--muted)}
.badge{display:inline-block;margin-left:6px;font-size:9.5px;background:#f1f5f9;color:#64748b;border-radius:6px;padding:1px 5px;vertical-align:middle}
.addd{color:#b45309;font-size:11px;border:1px dashed #fbbf24;border-radius:6px;padding:1px 5px}
.chip{display:inline-block;border:1px solid var(--c);color:var(--c);border-radius:999px;padding:2px 8px;font-size:11px;margin:0 4px 4px 0;white-space:nowrap}
td.sig{min-width:200px} td.nws{min-width:220px;max-width:300px}
.fin{font-size:11.5px;line-height:1.5} td.finc{min-width:150px}
a.news{display:block;color:#27303f;text-decoration:none;font-size:13px;line-height:1.5;margin-bottom:10px;border-left:3px solid var(--line);padding:2px 0 2px 10px;border-radius:2px}
a.news:hover{color:#0f172a;border-left-color:var(--accent);background:rgba(42,120,214,.04)}
a.news .nt{display:block;font-weight:500}
a.news.big{font-size:14.5px;margin-bottom:14px;padding-left:12px}
a.news .nm2{display:flex;gap:8px;align-items:center;margin-top:3px;flex-wrap:wrap}
a.news em{color:var(--muted);font-style:normal;font-size:11px}
a.news .src{font-size:10.5px;font-weight:600;color:var(--muted);background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:1px 7px}
a.news .evt{font-size:10px;font-weight:700;color:#1d4ed8;background:#dbeafe;border-radius:6px;padding:1px 7px;text-transform:uppercase;letter-spacing:.3px}
[data-theme="dark"] a.news{color:#c9d4e3}
[data-theme="dark"] a.news:hover{color:#fff}
[data-theme="dark"] a.news .evt{background:rgba(57,135,229,.18);color:#7ab5f5}
a.news.neg{border-left-color:var(--down)}
a.news.neg .nt{color:#c02626}
[data-theme="dark"] a.news.neg .nt{color:#f26d6d}
a.news.pos{border-left-color:var(--up)}
a.news.pos .nt{color:#04722c}
[data-theme="dark"] a.news.pos .nt{color:#4ade80}
.newsgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:14px}
.newscard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.newscard h3{margin:0 0 12px;font-size:15px;display:flex;gap:9px;align-items:center;border-bottom:1px solid var(--line);padding-bottom:10px}
.newsbar{display:flex;gap:10px;align-items:center;margin-bottom:14px;flex-wrap:wrap}
.newsbar input{border:1px solid var(--line);border-radius:9px;padding:9px 14px;font-size:14px;flex:1;min-width:220px;background:var(--card);color:var(--ink)}
.newsbar input:focus{outline:none;border-color:var(--accent)}
.newsbar button{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:9px;padding:9px 14px;cursor:pointer;font-size:13px}
.newsbar button.on{background:var(--down);color:#fff;border-color:var(--down)}
footer{color:var(--muted);font-size:11.5px;margin-top:22px;line-height:1.6}
/* ---------- allocation + tiles ---------- */
.donutwrap{display:flex;gap:14px;align-items:center}
.donutwrap .chartbox{flex:0 0 200px}
.slegend{flex:1;min-width:0}
.slrow{display:flex;align-items:center;gap:8px;font-size:12.5px;padding:2px 0}
.slrow .dot{width:10px;height:10px;border-radius:3px;flex-shrink:0}
.slrow .sln{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.slrow .slp{font-variant-numeric:tabular-nums;color:var(--muted)}
.minitiles{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.mt{border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.mt .k{color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.3px}
.mt .v{font-size:18px;font-weight:800;margin:2px 0}
.mt .sub{font-size:10.5px}
.taxb{font-size:9px;font-weight:700;border-radius:5px;padding:1px 4px;vertical-align:middle}
.taxb.ltcg{background:#e8f5e9;color:#047857} .taxb.stcg{background:#fef3c7;color:#b45309}
.notes{font-size:11px;color:var(--muted);margin-top:2px;font-style:italic}
.hb{display:inline-block;margin-left:6px;font-size:9.5px;font-weight:800;border-radius:6px;padding:1px 6px;vertical-align:middle}
.hb.hgood{background:#e8f5e9;color:#047857}.hb.hmid{background:#f1f5f9;color:#64748b}.hb.hbad{background:#fdecec;color:#b91c1c}
.calrow{display:flex;align-items:center;gap:10px;padding:7px 2px;border-bottom:1px solid var(--line);font-size:13px}
.calrow:last-child{border-bottom:none}
.cald{color:var(--muted);font-size:11.5px;width:86px;flex-shrink:0}
.calrow .slp{margin-left:auto;color:var(--muted);font-size:11.5px}
.simrow{display:flex;gap:8px;flex-wrap:wrap}
.simrow select,.simrow input{border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:13px;background:var(--card);color:var(--ink)}
.simrow select{min-width:180px}.simrow input{width:130px}
.simbtn{border:none;background:var(--accent);color:#fff;border-radius:8px;padding:8px 16px;cursor:pointer;font-size:13px;font-weight:600}
#simOut table{margin-top:8px}
/* ---------- discipline ---------- */
.floorbar{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:13px 16px;margin-bottom:14px}
.floorbar.breach{border-color:#f87171;background:#fef2f2}
[data-theme="dark"] .floorbar.breach{background:rgba(242,109,109,.08);border-color:rgba(242,109,109,.4)}
.floorhead{display:flex;gap:10px;align-items:center;margin-bottom:8px;flex-wrap:wrap}
.floorgrid{display:flex;gap:18px;flex-wrap:wrap}
.flitem{display:flex;gap:6px;align-items:baseline;font-size:12.5px}
.flitem .muted{font-size:11.5px}
.adbadge{font-size:12.5px;font-weight:800;border:2px solid var(--line);border-radius:999px;padding:3px 12px}
.adbadge.up{border-color:var(--up);color:var(--up)} .adbadge.down{border-color:var(--down);color:var(--down)}
.stage{font-size:9.5px;font-weight:800;border-radius:6px;padding:2px 7px;letter-spacing:.3px}
.stage.s-prove{background:#fef3c7;color:#b45309}.stage.s-monetize{background:#dbeafe;color:#1d4ed8}
.stage.s-systematize{background:#e8f5e9;color:#047857}.stage.s-scale{background:#ede9fe;color:#6d28d9}
.stage.s-—{background:#f1f5f9;color:#94a3b8}
[data-theme="dark"] .stage.s-prove{background:rgba(237,161,0,.15);color:#fbbf24}
[data-theme="dark"] .stage.s-monetize{background:rgba(57,135,229,.15);color:#7ab5f5}
[data-theme="dark"] .stage.s-systematize{background:rgba(49,176,87,.15);color:#4ade80}
[data-theme="dark"] .stage.s-scale{background:rgba(144,133,233,.15);color:#a99ff0}
td.thz{font-size:12px;max-width:260px;line-height:1.45} td.thz.kill{color:#b45309}
.jrow{padding:8px 2px;border-bottom:1px solid var(--line);font-size:13px}
.jrow:last-child{border-bottom:none}
.jnote{font-size:12.5px;color:var(--muted);margin-top:2px;line-height:1.5}
/* ---------- dark mode ---------- */
[data-theme="dark"]{--bg:#0b1220;--card:#141d2f;--ink:#e2e8f0;--muted:#8b98ab;--line:#243147;
--sidebar:#0a0f1a;--sbink:#94a3b8;--accent:#3987e5;--up:#31b057;--down:#f26d6d}
[data-theme="dark"] .controls button,[data-theme="dark"] .rangebtns button{background:var(--card);color:var(--ink)}
[data-theme="dark"] .controls button.on,[data-theme="dark"] .rangebtns button.on{background:#e2e8f0;color:#0b1220;border-color:#e2e8f0}
[data-theme="dark"] .mvr.up{background:rgba(49,176,87,.12)}[data-theme="dark"] .mvr.down{background:rgba(242,109,109,.12)}
[data-theme="dark"] .pill.up{background:rgba(49,176,87,.15)}[data-theme="dark"] .pill.down{background:rgba(242,109,109,.15)}
[data-theme="dark"] .taxb.ltcg,[data-theme="dark"] .hb.hgood{background:rgba(49,176,87,.15);color:#4ade80}
[data-theme="dark"] .taxb.stcg{background:rgba(237,161,0,.15);color:#fbbf24}
[data-theme="dark"] .hb.hbad{background:rgba(242,109,109,.15);color:#f26d6d}
[data-theme="dark"] .hb.hmid{background:#1e293b;color:#8b98ab}
[data-theme="dark"] .badge{background:#1e293b;color:#8b98ab}
[data-theme="dark"] .warnbar{background:rgba(237,161,0,.08);border-color:rgba(237,161,0,.3);color:#fbbf24}
[data-theme="dark"] .mbox,[data-theme="dark"] .tabs button.on{background:var(--card)}
[data-theme="dark"] .tabs button{background:#0f1726;color:var(--ink)}
[data-theme="dark"] table.ed input:focus{background:#0f1726}
[data-theme="dark"] a.news{color:#b6c2d4} [data-theme="dark"] a.news:hover{color:#e2e8f0}
[data-theme="dark"] .mrow button{background:var(--card);color:var(--ink)}
[data-theme="dark"] .mrow button.primary{background:#e2e8f0;color:#0b1220;border-color:#e2e8f0}
[data-theme="dark"] .cfg input{background:var(--card);color:var(--ink)}
/* ---------- modal ---------- */
.modal{position:fixed;inset:0;background:rgba(15,23,42,.45);display:none;align-items:flex-start;justify-content:center;padding:30px 12px;z-index:50;overflow:auto}
.modal.open{display:flex}
.mbox{background:#fff;border-radius:16px;max-width:1000px;width:100%;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,.25)}
.mbox h3{margin:0 0 4px;font-size:17px}
.mbox .hint{color:var(--muted);font-size:12px;margin-bottom:12px;line-height:1.5}
.cfg{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.cfg input{border:1px solid var(--line);border-radius:8px;padding:7px 10px;font-size:12.5px}
.cfg input#cfgRepo{width:220px}.cfg input#cfgTok{flex:1;min-width:240px}
.tabs{display:flex;gap:4px;margin-bottom:10px}
.tabs button{border:1px solid var(--line);background:#f8fafc;border-radius:8px 8px 0 0;padding:7px 16px;cursor:pointer;font-size:13px}
.tabs button.on{background:#fff;border-bottom-color:#fff;font-weight:700}
table.ed{width:100%;border-collapse:collapse;font-size:12.5px;min-width:760px}
table.ed th{font-size:10.5px;text-transform:uppercase;color:var(--muted);text-align:left;padding:6px 4px}
table.ed td{padding:3px 4px;border-bottom:1px solid var(--line)}
table.ed input{width:100%;border:1px solid transparent;border-radius:6px;padding:5px 6px;font-size:12.5px;background:transparent}
table.ed input:focus{border-color:#94a3b8;background:#fff;outline:none}
.edwrap{overflow:auto;max-height:46vh;border:1px solid var(--line);border-radius:0 10px 10px 10px}
.mrow{display:flex;gap:8px;margin-top:12px;align-items:center;flex-wrap:wrap}
.mrow button{border:1px solid var(--line);background:#fff;border-radius:8px;padding:8px 14px;cursor:pointer;font-size:13px}
.mrow button.primary{background:#0f172a;color:#fff;border-color:#0f172a;font-weight:600}
.mrow button:disabled{opacity:.5;cursor:default}
#edStatus{font-size:12.5px}
.delbtn{color:#b91c1c;cursor:pointer;border:none;background:none;font-size:15px;padding:2px 6px}
@media(max-width:980px){.sidebar{display:none}.cards{grid-template-columns:repeat(2,1fr)}
.grid-main{grid-template-columns:1fr}ul.corp{columns:1}}
"""


# ----------------------------------------------------------------- JS (plain string)
JS = """
/* ---------- section nav ---------- */
const navs=document.querySelectorAll('.nav a[data-sec]');
const TITLES={overview:'Overview',holdings:'Holdings',corporate:'Corporate actions',news:'News',insights:'Insights',discipline:'Discipline',booked:'Booked P/L',ledger:'Profit & loss banks',tax:'Tax & returns',watchlist:'Watchlist'};
function show(sec){
  document.querySelectorAll('section[data-sec]').forEach(s=>s.classList.toggle('show',s.dataset.sec===sec));
  navs.forEach(a=>a.classList.toggle('active',a.dataset.sec===sec));
  const t=document.getElementById('secTitle');if(t)t.textContent=TITLES[sec]||sec;
  location.hash=sec;
}
navs.forEach(a=>a.addEventListener('click',e=>{e.preventDefault();show(a.dataset.sec);}));
show(location.hash&&document.querySelector(`section[data-sec="${location.hash.slice(1)}"]`)?location.hash.slice(1):'overview');

/* ---------- holdings table sort + filter ---------- */
const tb=document.querySelector('#tbl tbody');
let curKey='val',curDir=1;
function sortBy(key){
  if(key===curKey)curDir*=-1;else{curKey=key;curDir=1;}
  const rows=[...tb.querySelectorAll('tr')];
  rows.sort((a,b)=>{
    if(key==='date'){
      const x=a.dataset.date||'',y=b.dataset.date||'';
      if(!x&&!y)return 0;if(!x)return 1;if(!y)return -1;
      return (x<y?1:x>y?-1:0)*curDir;
    }
    return ((parseFloat(b.dataset[key])||0)-(parseFloat(a.dataset[key])||0))*curDir;
  });
  rows.forEach(r=>tb.appendChild(r));
  document.querySelectorAll('.controls button[data-sort]').forEach(b=>{
    b.classList.toggle('on',b.dataset.sort===key);
    b.classList.toggle('asc',b.dataset.sort===key&&curDir===-1);
  });
}
document.querySelectorAll('.controls button[data-sort]').forEach(b=>b.addEventListener('click',()=>sortBy(b.dataset.sort)));
const tkF=document.getElementById('tkFilter');
if(tkF)tkF.addEventListener('input',e=>{
  const q=e.target.value.trim().toLowerCase();
  tb.querySelectorAll('tr').forEach(r=>{r.style.display=!q||r.dataset.tk.includes(q)?'':'none';});
});

/* ---------- theme + PWA ---------- */
const IS_DARK=document.documentElement.dataset.theme==='dark';
const C_SERIES=IS_DARK?'#3987e5':'#2a78d6', C_GRID=IS_DARK?'#243147':'#eef1f6',
      C_TICK=IS_DARK?'#8b98ab':'#64748b', C_BENCH=IS_DARK?'#8b98ab':'#64748b',
      C_RING=IS_DARK?'#141d2f':'#fff';
const tBtn=document.getElementById('themeBtn');
if(tBtn){
  tBtn.textContent=IS_DARK?'☀️ Light mode':'🌙 Dark mode';
  tBtn.addEventListener('click',()=>{
    localStorage.setItem('st_theme',IS_DARK?'light':'dark');location.reload();
  });
}
if('serviceWorker' in navigator&&location.protocol==='https:')
  navigator.serviceWorker.register('sw.js').catch(()=>{});

/* ---------- charts ---------- */
const D=window.__DATA||{};
function fmtINR(v){
  const a=Math.abs(v);let s;
  if(a>=1e7)s=(v/1e7).toFixed(2)+' cr';else if(a>=1e5)s=(v/1e5).toFixed(1)+' L';
  else s=v.toLocaleString('en-IN');
  return '₹'+s;
}
let perfChart=null,perfDays=0,perfMode='value';
function drawPerf(days,mode){
  if(days!==undefined)perfDays=days; if(mode)perfMode=mode;
  const box=document.getElementById('perfBox');
  const long5=perfDays===-1;
  const SRC=long5?(D.history5y||{dates:[],values:[]}):D.history;
  const note=document.getElementById('perfNote');
  if(!window.Chart||!SRC||!SRC.dates||!SRC.dates.length){
    box.innerHTML='<div class="nochart">'+(long5?'Five-year history is built on the next scrape.':'Chart appears when data & internet are available.')+'</div>';
    if(note)note.textContent='';return;
  }
  if(!box.querySelector('canvas'))box.innerHTML='<canvas id="perfChart"></canvas>';
  const n=SRC.dates.length,start=(perfDays>0)?Math.max(0,n-perfDays):0;
  const labels=SRC.dates.slice(start);
  if(note){
    note.textContent=long5
      ? (function(){const m=D.history5y.missing||[];const f=D.history5y.from||'';
          const tail=m.length?' — except '+m.slice(0,5).join(', ')+(m.length>5?' and '+(m.length-5)+' more':'')+', which have no price feed.':'.';
          return 'Weekly, from '+f+' — the oldest buy date on your books, where the lot ledger becomes complete. '
            +'Share counts are rebuilt from your buy and sell history, so positions you have since exited count for the period you held them'+tail;})()
      : '';
  }
  const ctx=document.getElementById('perfChart').getContext('2d');
  const g=ctx.createLinearGradient(0,0,0,260);
  g.addColorStop(0,IS_DARK?'rgba(57,135,229,.3)':'rgba(42,120,214,.25)');g.addColorStop(1,'rgba(42,120,214,0)');
  if(perfChart)perfChart.destroy();
  let datasets,fmtY,showLegend=false;
  if(perfMode==='nifty'&&D.benchmark&&!long5){
    // re-index both to 100 at the visible window start for a fair comparison
    const rebase=arr=>{const s=arr.slice(start),b=s[0]||1;return s.map(v=>+(v/b*100).toFixed(2));};
    datasets=[
      {label:'My portfolio',data:rebase(D.benchmark.portfolio),borderColor:C_SERIES,borderWidth:2,pointRadius:0,pointHitRadius:12,tension:.25},
      {label:'Nifty 50',data:rebase(D.benchmark.nifty),borderColor:C_BENCH,borderWidth:2,borderDash:[5,4],pointRadius:0,pointHitRadius:12,tension:.25}];
    fmtY=v=>v.toFixed(0);showLegend=true;
  }else{
    datasets=[{label:'Value',data:SRC.values.slice(start),borderColor:C_SERIES,
      backgroundColor:g,fill:true,borderWidth:2,pointRadius:0,pointHitRadius:12,tension:.25}];
    fmtY=v=>fmtINR(v);
  }
  perfChart=new Chart(ctx,{type:'line',data:{labels,datasets},
    options:{responsive:true,maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:showLegend,position:'top',align:'end',labels:{boxWidth:10,boxHeight:10,usePointStyle:true,font:{size:11}}},
        tooltip:{callbacks:{label:c=>c.dataset.label+': '+(perfMode==='nifty'?c.parsed.y.toFixed(1):fmtINR(c.parsed.y))}}},
      scales:{x:{grid:{display:false},ticks:{maxTicksLimit:7,color:C_TICK,font:{size:10.5}}},
        y:{grid:{color:C_GRID},ticks:{color:C_TICK,font:{size:10.5},callback:fmtY}}}}});
}
const SECTOR_COLORS=['#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4','#008300','#4a3aa7','#94a3b8'];
function drawSector(){
  const box=document.getElementById('sectorBox');
  if(!window.Chart||!D.sectors||!D.sectors.length){box.innerHTML='<div class="nochart">No allocation data.</div>';return;}
  // top 7 by value, fold the rest into "Others"
  let items=D.sectors.slice();
  if(items.length>8){const top=items.slice(0,7);const rest=items.slice(7);
    const o=rest.reduce((a,x)=>a+x.value,0);const op=rest.reduce((a,x)=>a+x.pct,0);
    items=top.concat([{name:'Others',value:o,pct:+op.toFixed(1)}]);}
  const ctx=document.getElementById('sectorChart').getContext('2d');
  new Chart(ctx,{type:'doughnut',data:{labels:items.map(s=>s.name),
    datasets:[{data:items.map(s=>s.value),backgroundColor:SECTOR_COLORS.slice(0,items.length),
      borderColor:C_RING,borderWidth:2}]},
    options:{responsive:true,maintainAspectRatio:false,cutout:'62%',
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.label+': '+fmtINR(c.parsed)+' ('+items[c.dataIndex].pct+'%)'}}}}});
  document.getElementById('sectorLegend').innerHTML=items.map((s,i)=>
    `<div class="slrow"><span class="dot" style="background:${SECTOR_COLORS[i]}"></span>`
    +`<span class="sln">${s.name}</span><span class="slp">${s.pct}%</span></div>`).join('');
}
function drawDiv(){
  if(!window.Chart||!D.div||!D.div.labels.length)
    {document.getElementById('divBox').innerHTML='<div class="nochart">No dividend data yet.</div>';return;}
  const ctx=document.getElementById('divChart').getContext('2d');
  new Chart(ctx,{type:'bar',data:{labels:D.div.labels,datasets:[{data:D.div.values,
    backgroundColor:C_SERIES,borderRadius:4,maxBarThickness:26}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>fmtINR(c.parsed.y)+' received'}}},
      scales:{x:{grid:{display:false},ticks:{color:C_TICK,font:{size:10}}},
        y:{grid:{color:C_GRID},ticks:{color:C_TICK,font:{size:10.5},callback:v=>fmtINR(v)}}}}});
}
function drawMC(){
  const box=document.getElementById('mcBox');
  if(!box)return;
  if(!window.Chart||!D.mc){box.innerHTML='<div class="nochart">Projection appears after enough price history.</div>';return;}
  const m=D.mc,labels=m.months.map(x=>x<12?x+'m':(x/12).toFixed(1).replace(/\\.0$/,'')+'y');
  const ctx=document.getElementById('mcChart').getContext('2d');
  new Chart(ctx,{type:'line',data:{labels,datasets:[
    {label:'90th percentile',data:m.p90,borderColor:'transparent',backgroundColor:IS_DARK?'rgba(57,135,229,.16)':'rgba(42,120,214,.12)',fill:'+1',pointRadius:0,tension:.3},
    {label:'Median',data:m.p50,borderColor:C_SERIES,borderWidth:2,pointRadius:0,pointHitRadius:12,tension:.3},
    {label:'10th percentile',data:m.p10,borderColor:'transparent',backgroundColor:IS_DARK?'rgba(57,135,229,.16)':'rgba(42,120,214,.12)',fill:'-1',pointRadius:0,tension:.3}]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.dataset.label+': '+fmtINR(c.parsed.y)}}},
      scales:{x:{grid:{display:false},ticks:{maxTicksLimit:8,color:C_TICK,font:{size:10.5}}},
        y:{grid:{color:C_GRID},ticks:{color:C_TICK,font:{size:10.5},callback:v=>fmtINR(v)}}}}});
}

function drawBooked(){
  const box=document.getElementById('bookedBox');
  if(!box)return;
  if(!window.Chart||!D.booked||!D.booked.length){
    box.innerHTML='<div class="nochart">Chart appears once you have dated sales recorded.</div>';return;}
  const ctx=document.getElementById('bookedChart').getContext('2d');
  const g=ctx.createLinearGradient(0,0,0,220);
  g.addColorStop(0,IS_DARK?'rgba(57,135,229,.3)':'rgba(42,120,214,.25)');g.addColorStop(1,'rgba(42,120,214,0)');
  new Chart(ctx,{type:'line',data:{labels:D.booked.map(x=>x.date),
    datasets:[{data:D.booked.map(x=>x.cum),borderColor:C_SERIES,backgroundColor:g,fill:true,
      borderWidth:2,pointRadius:3,pointHitRadius:12,stepped:true}]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>'Booked so far: '+fmtINR(c.parsed.y)}}},
      scales:{x:{grid:{display:false},ticks:{maxTicksLimit:8,color:C_TICK,font:{size:10.5}}},
        y:{grid:{color:C_GRID},ticks:{color:C_TICK,font:{size:10.5},callback:v=>fmtINR(v)}}}}});
}

/* ---------- news filters ---------- */
let newsMode='';
function applyNewsFilter(){
  const q=(document.getElementById('newsFilter')?.value||'').trim().toLowerCase();
  document.querySelectorAll('#newsGrid .newscard').forEach(card=>{
    const tkMatch=!q||card.dataset.tk.includes(q);
    let anyVisible=false;
    card.querySelectorAll('a.news').forEach(a=>{
      const modeMatch=!newsMode||(newsMode==='pos'&&a.classList.contains('pos'))||(newsMode==='neg'&&a.classList.contains('neg'));
      a.style.display=modeMatch?'':'none';
      if(modeMatch)anyVisible=true;
    });
    card.style.display=(tkMatch&&anyVisible)?'':'none';
  });
}
const nf=document.getElementById('newsFilter');
if(nf){
  nf.addEventListener('input',applyNewsFilter);
  document.getElementById('posOnly').addEventListener('click',function(){
    newsMode=newsMode==='pos'?'':'pos';
    this.classList.toggle('on',newsMode==='pos');this.style.background=newsMode==='pos'?'var(--up)':'';this.style.color=newsMode==='pos'?'#fff':'';
    document.getElementById('negOnly').classList.remove('on');if(newsMode!=='neg'){document.getElementById('negOnly').style.background='';document.getElementById('negOnly').style.color='';}
    applyNewsFilter();
  });
  document.getElementById('negOnly').addEventListener('click',function(){
    newsMode=newsMode==='neg'?'':'neg';
    this.classList.toggle('on',newsMode==='neg');
    document.getElementById('posOnly').classList.remove('on');document.getElementById('posOnly').style.background='';document.getElementById('posOnly').style.color='';
    applyNewsFilter();
  });
}

/* ---------- sell simulator + tax-lot optimizer ---------- */
const STCG_RATE=0.20,LTCG_RATE=0.125;
function monthsBetween(d1,d2){return (d2.getFullYear()-d1.getFullYear())*12+(d2.getMonth()-d1.getMonth())-(d2.getDate()<d1.getDate()?1:0);}
function initSim(){
  const sel=document.getElementById('simStock');
  if(!sel||!D.rows)return;
  sel.innerHTML=D.rows.map((r,i)=>`<option value="${i}">${r.tk} — ${r.qty} @ ₹${r.price.toFixed(2)}</option>`).join('');
  document.getElementById('simGo').addEventListener('click',runSim);
}
function runSim(){
  const out=document.getElementById('simOut');
  const r=D.rows[+document.getElementById('simStock').value];
  let qty=parseFloat(document.getElementById('simQty').value);
  const px=parseFloat(document.getElementById('simPrice').value)||r.price;
  if(!r||!qty||qty<=0){out.innerHTML='⚠ Enter a quantity.';return;}
  qty=Math.min(qty,r.qty);
  const today=new Date();
  // build lots with tax kind; unknown dates treated as STCG (conservative)
  let lots=r.lots.map(l=>{
    const d=l.buy_date?new Date(l.buy_date):null;
    const lt=d?monthsBetween(d,today)>=12:false;
    const gainPS=px-l.buy_price;
    const taxPS=gainPS>0?gainPS*(lt?LTCG_RATE:STCG_RATE):0;
    return {...l,lt,gainPS,taxPS,known:!!d};
  });
  lots.sort((a,b)=>a.taxPS-b.taxPS);            // cheapest-tax lots first
  let rem=qty,gain=0,tax=0,ltG=0,stG=0;const plan=[];
  for(const l of lots){
    if(rem<=0)break;
    const take=Math.min(rem,l.qty);rem-=take;
    const g=take*l.gainPS;gain+=g;tax+=take*l.taxPS;
    if(g>0)(l.lt?ltG+=g:stG+=g);
    plan.push({take,l});
  }
  const proceeds=qty*px;
  // friction: STT 0.1% + exchange 0.00297% + SEBI + DP ₹15.34 + GST on charges
  const exch=proceeds*0.0000297, sebi=proceeds*0.000001;
  const friction=proceeds*0.001+exch+sebi+15.34+(exch+sebi)*0.18;
  const newVal=D.total-qty*r.price;
  const newPct=((r.qty-qty)*r.price/newVal*100);
  const fmt=v=>'₹'+Math.round(v).toLocaleString('en-IN');
  let planHtml=plan.map(p=>`<tr><td>${p.take.toLocaleString()} sh</td><td class="num">₹${p.l.buy_price.toFixed(2)}</td>`
    +`<td>${p.l.known?(p.l.lt?'LTCG':'STCG'):'STCG?*'}</td><td class="num ${p.take*p.l.gainPS>=0?'up':'down'}">${fmt(p.take*p.l.gainPS)}</td>`
    +`<td class="num">${fmt(p.take*p.l.taxPS)}</td></tr>`).join('');
  out.innerHTML=`<div class="cards" style="margin:10px 0">
    <div class="card"><div class="k">Proceeds</div><div class="v" style="font-size:17px">${fmt(proceeds)}</div></div>
    <div class="card"><div class="k">Gain realised</div><div class="v ${gain>=0?'up':'down'}" style="font-size:17px">${fmt(gain)}</div><span class="muted" style="font-size:10.5px">LTCG ${fmt(ltG)} · STCG ${fmt(stG)}</span></div>
    <div class="card"><div class="k">Est. tax + friction</div><div class="v" style="font-size:17px">${fmt(tax+friction)}</div><span class="muted" style="font-size:10.5px">tax ${fmt(tax)} · charges ${fmt(friction)} — the cost of the impulse, priced now</span></div>
    <div class="card"><div class="k">${r.tk} after sale</div><div class="v" style="font-size:17px">${(r.qty-qty).toLocaleString()} sh</div><span class="muted" style="font-size:10.5px">${newPct.toFixed(1)}% of portfolio</span></div>
  </div>
  <b style="font-size:12.5px">Smartest lots to sell (lowest tax first):</b>
  <div style="overflow:auto"><table class="data" style="min-width:480px"><thead><tr><th>Sell</th><th class="num">Bought at</th><th>Type</th><th class="num">Gain</th><th class="num">Est. tax</th></tr></thead><tbody>${planHtml}</tbody></table></div>
  <div class="muted" style="font-size:11px;margin-top:6px">*Lots without a buy date are treated as STCG (conservative). Brokers sell FIFO by default — ask for specific-lot selling if your broker supports it. Estimates only, not tax advice.</div>`;
}

document.querySelectorAll('.rangebtns:not(.modebtns) button').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.rangebtns:not(.modebtns) button').forEach(x=>x.classList.toggle('on',x===b));
  drawPerf(parseInt(b.dataset.days)||0,undefined);
}));
document.querySelectorAll('.modebtns button').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.modebtns button').forEach(x=>x.classList.toggle('on',x===b));
  drawPerf(undefined,b.dataset.mode);
}));
window.addEventListener('load',()=>{drawPerf(0,'value');drawDiv();drawSector();drawMC();drawBooked();initSim();});

/* ---------- portfolio editor (holdings + watchlist tabs) ---------- */
const $=id=>document.getElementById(id);
const modal=$('edModal'),edStatus=$('edStatus');
const FILES={
  holdings:{path:'holdings.csv',head:['ticker','name','yahoo_symbol','qty','buy_price','buy_date','seed_price','sector','target_price','stop_loss','notes'],
    cols:[['ticker','Ticker'],['name','Name'],['yahoo_symbol','Yahoo symbol'],['qty','Qty'],['buy_price','Buy price'],['buy_date','Buy date'],['sector','Sector'],['target_price','Target'],['stop_loss','Stop'],['notes','Notes']],
    sha:null,orig:null,rows:[]},
  watchlist:{path:'watchlist.csv',head:['ticker','name','yahoo_symbol','target_price','notes'],
    cols:[['ticker','Ticker'],['name','Name'],['yahoo_symbol','Yahoo symbol'],['target_price','Target'],['notes','Notes']],
    sha:null,orig:null,rows:[]},
  discipline:{path:'discipline.csv',head:['ticker','stage','thesis','proof_metric','kill_condition','review_date','horizon_quarters'],
    cols:[['ticker','Ticker'],['stage','Stage'],['thesis','Thesis'],['proof_metric','Proof metric'],['kill_condition','Kill condition'],['review_date','Review date'],['horizon_quarters','Qtrs']],
    sha:null,orig:null,rows:[]},
  journal:{path:'journal.csv',head:['date','ticker','action','note'],
    cols:[['date','Date'],['ticker','Ticker (blank=portfolio)'],['action','Action'],['note','Note']],
    sha:null,orig:null,rows:[]},
  violations:{path:'violations.csv',head:['date','type','ticker','justification'],
    cols:[['date','Date'],['type','Type'],['ticker','Ticker'],['justification','Justification']],
    sha:null,orig:null,rows:[]},
  sells:{path:'sells.csv',head:['ticker','name','qty','buy_price','buy_date','sell_price','sell_date'],
    cols:[['ticker','Ticker'],['name','Name'],['qty','Qty'],['buy_price','Buy price'],['buy_date','Buy date'],['sell_price','Sell price'],['sell_date','Sell date']],
    sha:null,orig:null,rows:[]},
  floor:{path:'floor.csv',head:['key','value'],
    cols:[['key','Setting'],['value','Value']],
    sha:null,orig:null,rows:[]}
};
let curTab='holdings';
function guessRepo(){
  const h=location.hostname,parts=location.pathname.split('/').filter(Boolean);
  if(h.endsWith('.github.io')&&parts.length)return h.split('.')[0]+'/'+parts[0];
  return localStorage.getItem('st_repo')||'';
}
function cfg(){return{repo:$('cfgRepo').value.trim(),tok:$('cfgTok').value.trim()};}
function parseCSV(text){
  const lines=text.replace(/\\r/g,'').split('\\n').filter(l=>l.trim()!=='');
  const parse=l=>{const out=[];let cur='',q=false;
    for(let i=0;i<l.length;i++){const ch=l[i];
      if(q){if(ch==='"'){if(l[i+1]==='"'){cur+='"';i++;}else q=false;}else cur+=ch;}
      else{if(ch==='"')q=true;else if(ch===','){out.push(cur);cur='';}else cur+=ch;}
    }out.push(cur);return out;};
  const head=parse(lines[0]);
  return{head,rows:lines.slice(1).map(parse).map(cells=>{
    const o={};head.forEach((h,i)=>o[h]=cells[i]!==undefined?cells[i]:'');return o;})};
}
function csvField(v){v=String(v==null?'':v);return /[",\\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;}
function toCSV(head,rows){return head.join(',')+'\\n'+rows.map(r=>head.map(h=>csvField(r[h])).join(',')).join('\\n')+'\\n';}
function rowHTML(f,r){
  const tds=f.cols.map(([k])=>`<td><input data-k="${k}" value="${String(r[k]||'').replace(/"/g,'&quot;')}"${k==='buy_date'?' placeholder="YYYY-MM-DD"':''}${k==='yahoo_symbol'?' placeholder="TCS.NS"':''}></td>`).join('');
  return`<tr>${tds}<td><button class="delbtn" title="Remove">✕</button></td></tr>`;
}
function renderTab(){
  const f=FILES[curTab];
  document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('on',b.dataset.tab===curTab));
  $('edHead').innerHTML=f.cols.map(([,l])=>`<th>${l}</th>`).join('')+'<th></th>';
  $('edBody').innerHTML=f.rows.map(r=>rowHTML(f,r)).join('');
}
function captureTab(){
  const f=FILES[curTab];
  f.rows=[...$('edBody').querySelectorAll('tr')].map(tr=>{
    const o={};tr.querySelectorAll('input').forEach(inp=>o[inp.dataset.k]=inp.value.trim());
    const prev=f.rows.find(r=>r.ticker===o.ticker)||{};
    f.head.forEach(h=>{if(!(h in o))o[h]=prev[h]||(h==='seed_price'?'0':'');});
    return o;
  }).filter(r=>r.ticker);
}
async function loadFile(key){
  const{repo,tok}=cfg();const f=FILES[key];
  const headers=tok?{Authorization:'Bearer '+tok}:{};
  const res=await fetch(`https://api.github.com/repos/${repo}/contents/${f.path}?ref=main`,{headers});
  if(res.status===404&&key!=='holdings'){f.sha=null;f.orig=null;f.rows=[];return;}
  if(!res.ok)throw new Error(`${f.path}: GitHub API ${res.status} — check repo name and token`);
  const j=await res.json();f.sha=j.sha;
  const text=decodeURIComponent(escape(atob(j.content.replace(/\\n/g,''))));
  f.orig=text;f.rows=parseCSV(text).rows;
}
async function openEditor(){
  if(!$('cfgRepo').value)$('cfgRepo').value=localStorage.getItem('st_repo')||guessRepo();
  if(!$('cfgTok').value)$('cfgTok').value=localStorage.getItem('st_tok')||'';
  modal.classList.add('open');edStatus.textContent='Loading…';
  try{
    for(const k of Object.keys(FILES))await loadFile(k);
    renderTab();
    edStatus.textContent=`${FILES.holdings.rows.length} holdings, ${FILES.watchlist.rows.length} watchlist, ${FILES.journal.rows.length} journal entries loaded.`;
  }catch(e){$('edBody').innerHTML='';edStatus.textContent='⚠ '+e.message;}
}
const STRUCT_WORDS=/thesis|structur|kill|review|margin|order|result|manage|guidance|debt|demand|capex|market share|no structural change|promoter|regulat|capacity|launch|acquisi|merger|volume/i;
const PRICE_ONLY=/^(the )?(price|stock|share)?\s*(went|is|was|moved|fell|rose|dropped|jumped|crashed|rallied|up|down)?[\s\d.,%₹+-]*$/i;
function validate(){
  for(const r of FILES.holdings.rows){
    if(!r.yahoo_symbol)return`${r.ticker}: Yahoo symbol required (e.g. ${r.ticker}.NS)`;
    if(!r.qty||isNaN(+r.qty)||+r.qty<=0)return`${r.ticker}: quantity must be a positive number`;
    if(r.buy_price===''||isNaN(+r.buy_price)||+r.buy_price<0)return`${r.ticker}: buy price must be a number`;
    if(r.buy_date&&!/^\\d{4}-\\d{2}-\\d{2}$/.test(r.buy_date))return`${r.ticker}: buy date must be YYYY-MM-DD (or blank)`;
  }
  for(const r of FILES.watchlist.rows){
    if(!r.yahoo_symbol)return`watchlist ${r.ticker}: Yahoo symbol required`;
  }
  for(const r of FILES.discipline.rows){
    if(r.stage&&!['PROVE','MONETIZE','SYSTEMATIZE','SCALE'].includes(r.stage.toUpperCase()))
      return`discipline ${r.ticker}: stage must be PROVE, MONETIZE, SYSTEMATIZE or SCALE (or blank)`;
    if(r.review_date&&!/^\d{4}-\d{2}-\d{2}$/.test(r.review_date))
      return`discipline ${r.ticker}: review date must be YYYY-MM-DD`;
  }
  for(const r of FILES.journal.rows){
    if(!/^\d{4}-\d{2}-\d{2}$/.test(r.date))return`journal: date must be YYYY-MM-DD`;
    const note=(r.note||'').trim();
    if(note.length<15)return`journal ${r.date}: note too short — say what changed structurally, or "no structural change"`;
    if(PRICE_ONLY.test(note)||( !STRUCT_WORDS.test(note) && /price|₹|%|up |down |fell|rose/i.test(note)))
      return`journal ${r.date}: price commentary alone doesn't count — reference the thesis, a structural change, or state "no structural change"`;
  }
  for(const r of FILES.sells.rows){
    if(!r.qty||isNaN(+r.qty)||+r.qty<=0)return`sells ${r.ticker}: quantity must be a positive number`;
    if(isNaN(+r.buy_price)||isNaN(+r.sell_price))return`sells ${r.ticker}: buy and sell prices must be numbers`;
    if(!/^\d{4}-\d{2}-\d{2}$/.test(r.sell_date))return`sells ${r.ticker}: sell date must be YYYY-MM-DD`;
    if(r.buy_date&&!/^\d{4}-\d{2}-\d{2}$/.test(r.buy_date))return`sells ${r.ticker}: buy date must be YYYY-MM-DD (or blank)`;
  }
  for(const r of FILES.violations.rows){
    if((r.justification||'').trim().length<20)
      return`violation ${r.date}: justification must be at least 20 characters — deviation is allowed, hiding it is not`;
  }
  return null;
}
async function putFile(key){
  const{repo,tok}=cfg();const f=FILES[key];
  const content=toCSV(f.head,f.rows);
  if(f.orig!==null&&content===f.orig)return false;      // unchanged
  const body={message:`${f.path} edit via dashboard`,content:btoa(unescape(encodeURIComponent(content))),branch:'main'};
  if(f.sha)body.sha=f.sha;
  const res=await fetch(`https://api.github.com/repos/${repo}/contents/${f.path}`,{
    method:'PUT',headers:{Authorization:'Bearer '+tok,'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!res.ok){const j=await res.json().catch(()=>({}));throw new Error(`${f.path}: GitHub ${res.status} ${j.message||''}`);}
  const j=await res.json();f.sha=j.content&&j.content.sha;f.orig=content;
  return true;
}
async function saveEditor(){
  const{repo,tok}=cfg();
  if(!repo||!tok){edStatus.textContent='⚠ Enter repo and token first.';return;}
  captureTab();
  const err=validate();
  if(err){edStatus.textContent='⚠ '+err;return;}
  localStorage.setItem('st_repo',repo);localStorage.setItem('st_tok',tok);
  $('edSave').disabled=true;edStatus.textContent='Committing…';
  try{
    let any=false;
    for(const k of Object.keys(FILES)){if(await putFile(k))any=true;}
    edStatus.textContent=any?'✅ Saved! Rebuilding — refresh in ~2 minutes.':'No changes to save.';
  }catch(e){edStatus.textContent='⚠ '+e.message;}
  $('edSave').disabled=false;
}
document.querySelectorAll('.tabs button').forEach(b=>b.addEventListener('click',()=>{
  captureTab();curTab=b.dataset.tab;renderTab();
}));
$('editBtn').addEventListener('click',openEditor);
$('editBtn2').addEventListener('click',openEditor);
$('edCancel').addEventListener('click',()=>modal.classList.remove('open'));
modal.addEventListener('click',e=>{if(e.target===modal)modal.classList.remove('open');});
$('addRow').addEventListener('click',()=>{
  const f=FILES[curTab];captureTab();
  const empty={};f.head.forEach(h=>empty[h]=h==='seed_price'?'0':'');
  f.rows.push(empty);renderTab();
});
$('edBody').addEventListener('click',e=>{
  if(e.target.classList.contains('delbtn')){e.target.closest('tr').remove();captureTab();}
});
$('edSave').addEventListener('click',saveEditor);

/* ---------- profit & loss banks ---------- */
(function(){
  const sel=document.getElementById('ldPeriod');
  if(!sel) return;
  const R=(window.__DATA.realised||[]).filter(x=>x.sell_date);
  const from=document.getElementById('ldFrom'),to=document.getElementById('ldTo');
  const money=v=>(v<0?'-₹':'₹')+Math.abs(Math.round(v)).toLocaleString('en-IN');
  const iso=d=>d.toISOString().slice(0,10);
  const fyOf=s=>+s.slice(0,4)-(+s.slice(5,7)>=4?0:1);
  const fyLbl=y=>'FY '+y+'-'+String(y+1).slice(2);

  function window_(){
    const v=sel.value, now=new Date(), cy=fyOf(iso(now));
    if(v==='custom')  return [from.value||'0000-01-01', to.value||'9999-12-31', 'custom range'];
    if(v==='all')     return ['0000-01-01','9999-12-31','all time'];
    if(v==='thisfy')  return [cy+'-04-01',(cy+1)+'-03-31',fyLbl(cy)];
    if(v==='lastfy')  return [(cy-1)+'-04-01',cy+'-03-31',fyLbl(cy-1)];
    if(v==='12m'){const d=new Date(now);d.setFullYear(d.getFullYear()-1);return [iso(d),iso(now),'last 12 months'];}
    const y=+v.slice(2); return [y+'-04-01',(y+1)+'-03-31',fyLbl(y)];
  }
  function rowHtml(x){
    const held=(x.months===null||x.months===undefined)?'—':x.months+' mo';
    const pct=(x.pct===null||x.pct===undefined)?'<span class="muted">bonus</span>':(x.pct>=0?'+':'')+x.pct.toFixed(1)+'%';
    return '<tr><td class="tk"><b>'+x.ticker+'</b><div class="nm">'+(x.name||'')+'</div></td>'
      +'<td class="num">'+Number(x.qty).toLocaleString('en-IN')+'</td>'
      +'<td class="num">₹'+Number(x.buy_price).toFixed(2)+' → ₹'+Number(x.sell_price).toFixed(2)+'</td>'
      +'<td class="num">'+held+'</td>'
      +'<td class="num '+(x.gain>=0?'up':'down')+'"><b>'+money(x.gain)+'</b></td>'
      +'<td class="num '+(x.gain>=0?'up':'down')+'">'+pct+'</td>'
      +'<td>'+x.kind+'</td><td>'+x.sell_date+'</td></tr>';
  }
  let curWins=[],curLosses=[];
  function draw(){
    const [a,b,lbl]=window_();
    const inWin=R.filter(x=>x.sell_date>=a&&x.sell_date<=b);
    curWins=inWin.filter(x=>x.gain>0).sort((p,q)=>q.gain-p.gain);
    curLosses=inWin.filter(x=>x.gain<=0).sort((p,q)=>p.gain-q.gain);
    const gW=curWins.reduce((s,x)=>s+x.gain,0), gL=curLosses.reduce((s,x)=>s+x.gain,0);
    const net=gW+gL, n=inWin.length;
    document.getElementById('ldLbl').textContent='· '+lbl;
    const netEl=document.getElementById('ldNet');
    netEl.textContent=n?money(net):'—'; netEl.className='v '+(net>=0?'up':'down');
    document.getElementById('ldNetSub').textContent=n+' trade'+(n===1?'':'s')+' closed'
      +(n?' · est. tax '+money(inWin.reduce((s,x)=>s+(x.tax||0),0))+' · charges '+money(inWin.reduce((s,x)=>s+(x.friction||0),0)):'');
    document.getElementById('ldWin').textContent=money(gW);
    document.getElementById('ldWinSub').textContent=curWins.length+' winner'+(curWins.length===1?'':'s')
      +(curWins.length?' · avg '+money(gW/curWins.length)+' · best '+curWins[0].ticker+' '+money(curWins[0].gain):'');
    document.getElementById('ldLoss').textContent=money(gL);
    document.getElementById('ldLossSub').textContent=curLosses.length+' loser'+(curLosses.length===1?'':'s')
      +(curLosses.length?' · avg '+money(gL/curLosses.length)+' · worst '+curLosses[0].ticker+' '+money(curLosses[0].gain):'');
    const rate=n?Math.round(curWins.length/n*100):null;
    const payoff=(curWins.length&&curLosses.length)?Math.abs((gW/curWins.length)/(gL/curLosses.length)):null;
    document.getElementById('ldRate').textContent=rate===null?'—':rate+'%';
    document.getElementById('ldRateSub').textContent=(payoff===null?'need both winners and losers'
      :'payoff '+payoff.toFixed(2)+'× — '+(payoff>=1?'your winners are bigger than your losers':'your losers are bigger than your winners'));
    document.getElementById('ldWinBody').innerHTML=curWins.map(rowHtml).join('')
      ||'<tr><td colspan="8" class="muted" style="padding:18px">No profitable trades closed in this window.</td></tr>';
    document.getElementById('ldLossBody').innerHTML=curLosses.map(rowHtml).join('')
      ||'<tr><td colspan="8" class="muted" style="padding:18px">No losing trades closed in this window. Clean period.</td></tr>';
  }
  function csv(rows,name){
    const head=['ticker','name','qty','buy_price','buy_date','sell_price','sell_date','months_held','gain','pct','kind','est_tax','charges'];
    const body=rows.map(x=>[x.ticker,'"'+(x.name||'').replace(/"/g,'""')+'"',x.qty,x.buy_price,x.buy_date||'',
      x.sell_price,x.sell_date,x.months===null?'':x.months,x.gain,x.pct===null?'':x.pct,x.kind,x.tax||0,x.friction||0].join(','));
    const blob=new Blob([head.join(',')+'\\n'+body.join('\\n')],{type:'text/csv'});
    const a=document.createElement('a');a.href=URL.createObjectURL(blob);
    a.download=name+'-'+window_()[2].replace(/[^a-z0-9]+/gi,'-').toLowerCase()+'.csv';
    a.click();URL.revokeObjectURL(a.href);
  }
  sel.addEventListener('change',()=>{
    const custom=sel.value==='custom';
    from.style.display=to.style.display=custom?'':'none';
    if(!custom) draw();
  });
  document.getElementById('ldGo').addEventListener('click',draw);
  document.getElementById('ldWinCsv').addEventListener('click',()=>csv(curWins,'profit-bank'));
  document.getElementById('ldLossCsv').addEventListener('click',()=>csv(curLosses,'loss-bank'));
  from.style.display=to.style.display='none';
  draw();
})();

/* ---------- per-stock price history ---------- */
(function(){
  const modal=document.getElementById('pxModal');
  if(!modal) return;
  const META=window.__DATA.px||{}, REAL=(window.__DATA.realised||[]);
  let PX=null, pending=null, cur=null, range='1y', chart=null;
  const money=v=>'₹'+Number(v).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});

  function load(){
    if(PX) return Promise.resolve(PX);
    if(!pending) pending=fetch('prices.json').then(r=>r.json())
      .catch(()=>({daily:{dates:[],series:{}},weekly:{dates:[],series:{}}}))
      .then(j=>{PX=j;return j;});
    return pending;
  }
  function pick(tk){
    const d=(PX.daily||{}), w=(PX.weekly||{});
    if((range==='max'||range==='5y')&&w.series&&w.series[tk]){
      const wv=w.series[tk];
      const k=range==='5y'?261:wv.length;
      const s0=Math.max(0,wv.length-k);
      return {dates:w.dates.slice(s0),vals:wv.slice(s0),step:'weekly'};
    }
    const vals=(d.series||{})[tk];
    if(!vals) return null;
    const n=range==='6m'?126:vals.length;
    const s=Math.max(0,vals.length-n);
    return {dates:d.dates.slice(s),vals:vals.slice(s),step:'daily'};
  }
  function markerRow(labels,events){
    const arr=new Array(labels.length).fill(null);
    let n=0;
    for(const e of events){
      if(!e.d||labels[0]>e.d) continue;        // no date, or predates the window
      let i=labels.findIndex(x=>x>=e.d);
      if(i<0) i=labels.length-1;
      arr[i]=e.p; n++;
    }
    return {arr:arr,n:n};
  }
  function draw(){
    const m=META[cur]||{}, s=pick(cur);
    const box=document.getElementById('pxStats');
    if(chart){chart.destroy();chart=null;}
    if(!s||!s.vals.some(v=>v!==null)){
      box.innerHTML='<span>No price history available for this symbol.</span>';
      return;
    }
    const labels=s.dates, vals=s.vals;
    const buys=(m.lots||[]).map(l=>({d:l.d,p:l.p}));
    const sells=REAL.filter(x=>x.ticker===cur).map(x=>({d:x.sell_date,p:x.sell_price}));
    const ds=[{label:cur,data:vals,borderColor:'#2563eb',borderWidth:1.8,pointRadius:0,
               tension:.15,spanGaps:true,fill:false}];
    if(m.avg) ds.push({label:'Your avg cost',data:labels.map(()=>m.avg),borderColor:'#94a3b8',
               borderWidth:1.2,borderDash:[5,4],pointRadius:0,fill:false});
    const mb=markerRow(labels,buys), ms=markerRow(labels,sells);
    if(mb.n) ds.push({label:'You bought',data:mb.arr,showLine:false,
               pointRadius:6,pointStyle:'triangle',backgroundColor:'#16a34a',borderColor:'#16a34a'});
    if(ms.n) ds.push({label:'You sold',data:ms.arr,showLine:false,
               pointRadius:6,pointStyle:'rectRot',backgroundColor:'#dc2626',borderColor:'#dc2626'});
    chart=new Chart(document.getElementById('pxChart'),{type:'line',data:{labels,datasets:ds},
      options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
        plugins:{legend:{display:true,labels:{boxWidth:10,font:{size:11}}},
          tooltip:{callbacks:{label:c=>c.raw===null?null:c.dataset.label+': '+money(c.raw)}}},
        scales:{x:{ticks:{maxTicksLimit:8,font:{size:10}}},
                y:{ticks:{font:{size:10},callback:v=>'₹'+v.toLocaleString('en-IN')}}}}});
    const clean=vals.filter(v=>v!==null);
    const hi=Math.max(...clean), lo=Math.min(...clean), first=clean[0], last=clean[clean.length-1];
    const chg=(last/first-1)*100;
    let bits='<span>Period high <b>'+money(hi)+'</b></span><span>low <b>'+money(lo)+'</b></span>'
      +'<span>Change over window <b class="'+(chg>=0?'up':'down')+'">'+(chg>=0?'+':'')+chg.toFixed(1)+'%</b></span>'
      +'<span>From high <b class="down">'+((last/hi-1)*100).toFixed(1)+'%</b></span>';
    if(m.avg) bits+='<span>vs your cost <b class="'+(last>=m.avg?'up':'down')+'">'
      +((last/m.avg-1)*100>=0?'+':'')+((last/m.avg-1)*100).toFixed(1)+'%</b></span>';
    box.innerHTML=bits;
    const part=(n,tot,word)=>tot?(n===tot?tot+' '+word+(tot===1?'':'s'):n+' of '+tot+' '+word+'s in view'):'';
    document.getElementById('pxNote').textContent=
      [(s.step==='weekly'?'Weekly closes':'Daily closes'), labels.length+' points',
       part(mb.n,buys.length,'buy')||'no buy dates on file',
       part(ms.n,sells.length,'sale')].filter(Boolean).join(' · ')
      +((buys.length&&!mb.n)||(sells.length&&!ms.n)?' — widen the range to see the rest':'');
  }
  function open(tk){
    cur=tk; range='1y';
    document.querySelectorAll('#pxRange button').forEach(b=>b.classList.toggle('on',b.dataset.r==='1y'));
    const m=META[tk]||{};
    document.getElementById('pxTitle').textContent='📈 '+tk+' — '+(m.name||'');
    document.getElementById('pxSub').textContent=m.qty
      ? Number(m.qty).toLocaleString('en-IN')+' shares at an average cost of '+money(m.avg||0)
        +' · last traded '+money(m.price||0)
      : 'On your watchlist · last traded '+money(m.price||0);
    document.getElementById('pxStats').innerHTML='<span>Loading price history…</span>';
    modal.classList.add('open');
    load().then(draw);
  }
  document.addEventListener('click',e=>{
    const b=e.target.closest('[data-chart]');
    if(b){e.preventDefault();open(b.dataset.chart);}
  });
  document.querySelectorAll('#pxRange button').forEach(b=>b.addEventListener('click',()=>{
    range=b.dataset.r;
    document.querySelectorAll('#pxRange button').forEach(x=>x.classList.toggle('on',x===b));
    if(PX) draw();
  }));
  const close=()=>{modal.classList.remove('open');if(chart){chart.destroy();chart=null;}};
  document.getElementById('pxClose').addEventListener('click',close);
  modal.addEventListener('click',e=>{if(e.target===modal)close();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&modal.classList.contains('open'))close();});
})();
"""


# ----------------------------------------------------------------- render
def render(model) -> str:
    s = model["summary"]
    rows = model["rows"]
    watch = model.get("watch", [])
    meta = model["meta"]
    history = model.get("history", {"dates": [], "values": []})
    div_m = model.get("div_months", {"labels": [], "values": []})
    tax = model.get("tax", {})
    unreal = tax.get("unrealised", {})
    risk = model.get("risk", {})
    disc = model.get("discipline", {})
    floor = disc.get("floor", {"items": [], "breached": False, "unattested": 0})
    adherence = disc.get("adherence", {"score": None, "parts": []})

    # ---- overview pieces
    def pill(x, suffix="%"):
        if x is None:
            return ""
        cls = "up" if x >= 0 else "down"
        arrow = "↑" if x >= 0 else "↓"
        return f'<span class="pill {cls}">{arrow} {abs(x):.2f}{suffix}</span>'

    def mover_card(r):
        c = _cls(r["day_pct"])
        return (f'<div class="mvr {c}"><div class="mvr-t">{html.escape(r["ticker"])}</div>'
                f'<div class="mvr-p {c}">{_pct(r["day_pct"])}</div>'
                f'<div class="mvr-s">{_inr(r["price"],2)}</div></div>')

    gainers = "".join(mover_card(r) for r in s["gainers"]) or "<div class='muted'>No data</div>"
    losers = "".join(mover_card(r) for r in s["losers"]) or "<div class='muted'>No data</div>"

    def action_row(r, note):
        return (f"<li><b>{html.escape(r['ticker'])}</b> — {html.escape(r['name'])} "
                f"<span class='muted'>({_pct(r['pnl_pct'])} vs cost)</span><br>"
                f"<span class='note'>{html.escape(note)}</span></li>")

    sell_list = "".join(
        action_row(r, next((sg["text"] for sg in r["signals"] if sg["type"] == "sell_review"), ""))
        for r in s["sell_review"]
    ) or "<li class='muted'>Nothing meets the ≥15%-in-6-months rule right now.</li>"

    issue_list = "".join(
        action_row(r, "Recent headline flagged — see the News tab.")
        for r in s["issues"]
    ) or "<li class='muted'>No company/scope issues flagged in recent news.</li>"

    # ---- corporate list
    corp_items = []
    for r in rows + watch:
        c = r.get("corp") or {}
        tk = html.escape(r["ticker"])
        if c.get("next_earnings"):
            corp_items.append(f"<li><b>{tk}</b> — results due <b>{html.escape(c['next_earnings'])}</b></li>")
        for d in c.get("dividends", [])[-2:]:
            corp_items.append(f"<li><b>{tk}</b> — dividend ₹{d['amount']} <span class='muted'>({html.escape(d['date'])})</span></li>")
        for sp in c.get("splits", []):
            corp_items.append(f"<li><b>{tk}</b> — stock split {sp['ratio']}:1 <span class='muted'>({html.escape(sp['date'])})</span></li>")
        for n in r.get("news", []):
            if n.get("event"):
                corp_items.append(f"<li><b>{tk}</b> — <a href='{html.escape(n['link'])}' target='_blank' rel='noopener'>"
                                  f"{html.escape(n['title'])}</a> <span class='muted'>[{html.escape(n['event'])}]</span></li>")
    corp_html = "".join(corp_items[:24]) or "<li class='muted'>No corporate actions or event announcements detected.</li>"

    # ---- watchlist rows (panel + full section share markup)
    def watch_row(r):
        return (f'<div class="wrow">{_avatar(r["ticker"])}'
                f'<div class="wn"><b>{html.escape(r["ticker"])}</b><div>{html.escape(r["name"])}</div></div>'
                f'<div class="wp"><b>{_inr(r["price"],2)}</b><br>{pill(r["day_pct"])}</div></div>')

    watch_panel = "".join(watch_row(r) for r in watch[:6]) or \
        "<div class='muted' style='padding:10px 0'>Watchlist is empty — add stocks via ✎ Edit portfolio.</div>"

    def watch_big(r):
        sig = " ".join(_chip(sg) for sg in r["signals"]) or "<span class='muted'>—</span>"
        news_html = "".join(_news_link(n, big=True) for n in r.get("news", [])[:3])
        rsi_txt = "—" if r["rsi"] is None else f"{r['rsi']:.0f}"
        trend_txt = {"up": "▲ up", "down": "▼ down", None: "—"}.get(r["trend"], "—")
        return (f'<div class="newscard"><h3>{_avatar(r["ticker"])} {html.escape(r["ticker"])} '
                f'<span class="muted" style="font-weight:400">{html.escape(r["name"])}</span>'
                f'<button class="chartb" data-chart="{html.escape(r["ticker"])}" title="Price history">📈</button>'
                f'<span class="sp" style="flex:1"></span><b>{_inr(r["price"],2)}</b> {pill(r["day_pct"])}</h3>'
                f'<div class="muted" style="font-size:11.5px;margin-bottom:6px">Trend {trend_txt} · RSI {rsi_txt}</div>'
                f'<div>{sig}</div>{news_html or "<span class=muted>No recent news.</span>"}</div>')

    watch_section = "".join(watch_big(r) for r in watch) or \
        "<div class='muted'>Watchlist is empty — add stocks via ✎ Edit portfolio → Watchlist tab.</div>"

    # ---- news section (all stocks with news)
    news_cards = []
    for r in rows + watch:
        items = r.get("news", [])
        if not items:
            continue
        inner = "".join(_news_link(n, big=True) for n in items)
        news_cards.append(f'<div class="newscard" data-tk="{html.escape((r["ticker"]+" "+r["name"]).lower())}">'
                          f'<h3>{_avatar(r["ticker"])} {html.escape(r["ticker"])}'
                          f'<span class="muted" style="font-weight:400">{html.escape(r["name"])}</span></h3>{inner}</div>')
    news_html_all = "".join(news_cards) or "<div class='muted'>No news fetched yet — appears after the first live run.</div>"

    # ---- tax section pieces
    appr = tax.get("approaching", [])
    appr_html = "".join(
        f"<li><b>{html.escape(a['ticker'])}</b> — {html.escape(a['name'])}: "
        f"~{a['months_to_go']} month(s) to the 1-year mark "
        f"<span class='muted'>(gain {_inr(a['gain'])} would move from 20% STCG to 12.5% LTCG)</span></li>"
        for a in appr) or "<li class='muted'>Nothing within 2 months of the long-term threshold (or buy dates missing).</li>"

    realised = tax.get("realised", [])
    rt = tax.get("realised_totals", {})
    if realised:
        rrows = "".join(
            f"<tr><td><b>{html.escape(x['ticker'])}</b></td><td class='num'>{x['qty']:,.0f}</td>"
            f"<td class='num {_cls(x['gain'])}'>{_inr(x['gain'])}</td><td>{html.escape(x['kind'])}</td>"
            f"<td>{html.escape(x['sell_date'])}</td></tr>" for x in realised)
        realised_html = (f"<table class='data' style='min-width:520px'><thead><tr><th>Stock</th>"
                         f"<th class='num'>Qty</th><th class='num'>Gain</th><th>Type</th><th>Sold</th></tr></thead>"
                         f"<tbody>{rrows}</tbody></table>"
                         f"<div class='muted' style='margin-top:8px'>Realised LTCG {_inr(rt.get('ltcg'))} · "
                         f"STCG {_inr(rt.get('stcg'))} · est. tax {_inr(rt.get('tax'))} · "
                         f"friction (brokerage/STT/charges) {_inr(rt.get('friction'))}</div>")
    else:
        realised_html = ("<div class='muted'>No sales logged yet. Add rows to <code>sells.csv</code> "
                         "(ticker, qty, buy_price, buy_date, sell_price, sell_date) to track realised gains &amp; tax.</div>")

    rates = tax.get("rates", {})
    rate_line = (f"Rates used: STCG {rates.get('stcg',0)*100:.0f}% · LTCG {rates.get('ltcg',0)*100:.1f}% "
                 f"with ₹{rates.get('exemption',0):,.0f} annual LTCG exemption. Editable in scripts/tax.py.")

    # ---- insights section pieces
    rm = risk.get("metrics") or {}
    dd = rm.get("drawdown") or {}
    corr = risk.get("correlation") or {}
    bt = risk.get("backtest") or {}
    mc = risk.get("montecarlo") or {}
    n_snaps = risk.get("n_snapshots", 0)
    first_snap = risk.get("first_snapshot")

    snap_note = (f"Recording daily snapshots since <b>{html.escape(first_snap)}</b> ({n_snaps} so far) — "
                 f"history before that is reconstructed from today's holdings."
                 if first_snap else "Snapshot recording starts with the first live run.")

    pairs_html = "".join(
        f"<div class='slrow'><span class='sln'><b>{html.escape(p['a'])}</b> ↔ <b>{html.escape(p['b'])}</b></span>"
        f"<span class='slp'>{p['corr']:+.2f}</span></div>"
        for p in corr.get("pairs", [])) or "<div class='muted'>Needs more price history.</div>"

    bt_rows = "".join(
        f"<tr><td><b>{html.escape(b['ticker'])}</b></td>"
        f"<td class='num {_cls(b['hold'])}'>{b['hold']:+.1f}%</td>"
        f"<td class='num {_cls(b['rule'])}'>{b['rule']:+.1f}%</td>"
        f"<td>{'sold day ' + str(b['sold_day']) if b['triggered'] else 'never triggered'}</td></tr>"
        for b in bt.get("rows", []))
    bt_verdict = ""
    if bt.get("weighted_hold") is not None:
        diff = bt["weighted_rule"] - bt["weighted_hold"]
        if diff >= 0:
            bt_verdict = (f"Over this window your rule would have <b class='up'>matched or beaten</b> "
                          f"buy-and-hold by {diff:+.1f} pts (value-weighted).")
        else:
            bt_verdict = (f"Over this window buy-and-hold <b class='down'>beat your rule</b> by "
                          f"{-diff:.1f} pts (value-weighted) — the rule sold winners early "
                          f"{bt.get('n_triggered',0)} of {bt.get('n',0)} times.")

    def fmt_dd():
        if not dd or dd.get("dd_pct") is None:
            return "—"
        rec = f" · recovered {html.escape(dd['recovered'])}" if dd.get("recovered") else " · not yet recovered"
        return (f"<span class='down'>{dd['dd_pct']}%</span>"
                f"<div class='sub muted'>{html.escape(dd.get('peak_date',''))} → "
                f"{html.escape(dd.get('trough_date',''))}{rec}</div>")

    # ---- concentration panel (overview)
    conc = s.get("concentration", [])
    conc_html = "".join(
        f"<li><b>{html.escape(c['name'])}</b> ({'stock' if c['kind']=='stock' else 'sector'}) is "
        f"<b>{c['pct']}%</b> of your portfolio — above your {c['limit']:.0f}% limit. Consider trimming or "
        f"diversifying new money elsewhere.</li>"
        for c in conc) or "<li class='muted'>No stock or sector breaches your concentration limits.</li>"

    # ---- upcoming events calendar (corporate section, next 30 days)
    events = []
    for r in rows + watch:
        ne = (r.get("corp") or {}).get("next_earnings")
        if ne:
            try:
                import datetime as _dt
                d = _dt.datetime.strptime(ne, "%d %b %Y").date()
                delta = (d - _dt.date.today()).days
                if 0 <= delta <= 30:
                    events.append((d, r["ticker"], f"results", delta))
            except ValueError:
                pass
    events.sort()
    cal_html = "".join(
        f"<div class='calrow'><span class='cald'>{d.strftime('%a %d %b')}</span>"
        f"<b>{html.escape(tk)}</b> <span class='muted'>{kind}</span>"
        f"<span class='slp'>{'today' if delta==0 else ('tomorrow' if delta==1 else f'in {delta}d')}</span></div>"
        for d, tk, kind, delta in events[:14]) or "<div class='muted'>No dated events in the next 30 days.</div>"

    # ---- family floor + adherence + discipline section pieces
    def floor_icon(ok):
        return "✅" if ok else ("❌" if ok is False else "◻️")
    floor_items_html = "".join(
        f"<div class='flitem'><span>{floor_icon(i['ok'])}</span><b>{html.escape(i['label'])}</b>"
        f"<span class='muted'>{html.escape(i['detail'])}</span></div>"
        for i in floor.get("items", [])) or "<div class='muted'>Set your floor in ✎ Edit portfolio → Floor.</div>"
    floor_cls = "breach" if floor.get("breached") else ""
    floor_note = ("🚨 <b>Floor breached — resolve before opening new positions.</b>"
                  if floor.get("breached") else
                  ("The household floor comes before the portfolio. "
                   + (f"{floor.get('unattested')} item(s) not yet attested." if floor.get("unattested") else "All good.")))

    ad_score = adherence.get("score")
    ad_cls = "up" if (ad_score or 0) >= 70 else ("down" if (ad_score or 0) < 45 else "")
    ad_parts_html = "".join(
        f"<div class='slrow'><span class='sln'>{html.escape(p['name'])} <span class='muted'>· {html.escape(p['detail'])}</span></span>"
        f"<span class='slp'>{round(p['frac']*p['weight'])}/{p['weight']}</span></div>"
        for p in adherence.get("parts", []))

    dmap = disc.get("map", {})
    drows_html = []
    for r in rows:
        if r.get("qty", 0) <= 0:
            continue
        d = dmap.get(r["ticker"], {})
        stage = d.get("stage") or "—"
        rd = d.get("review_date") or ""
        rd_html = html.escape(rd) if rd else "<span class='addd'>set date</span>"
        thesis = d.get("thesis") or ""
        kill = d.get("kill_condition") or ""
        drows_html.append(f"""<tr>
          <td class="tk"><b>{html.escape(r['ticker'])}</b><div class="nm">{html.escape(r['name'])}</div></td>
          <td><span class="stage s-{html.escape(stage.lower())}">{html.escape(stage)}</span></td>
          <td class="thz">{html.escape(thesis) if thesis else "<span class='addd'>no thesis — position is a feeling, not an investment</span>"}</td>
          <td class="thz">{html.escape(d.get('proof_metric','') or '—')}</td>
          <td class="thz kill">{html.escape(kill) if kill else '—'}</td>
          <td class="num">{rd_html}</td>
        </tr>""")
    disc_table = "\n".join(drows_html)

    journal_html = "".join(
        f"<div class='jrow'><span class='cald'>{html.escape(j['date'])}</span>"
        f"<b>{html.escape(j['ticker'] or 'Portfolio')}</b> <span class='muted'>[{html.escape(j['action'])}]</span>"
        f"<div class='jnote'>{html.escape(j['note'])}</div></div>"
        for j in disc.get("journal", [])) or "<div class='muted'>No journal entries yet. If the record does not exist, the learning does not exist — add this week's note via ✎ Edit portfolio → Journal.</div>"

    viol_html = "".join(
        f"<div class='jrow'><span class='cald'>{html.escape(v['date'])}</span>"
        f"<b>{html.escape(v['type'])}</b> <span class='muted'>{html.escape(v['ticker'])}</span>"
        f"<div class='jnote'>{html.escape(v['justification'])}</div></div>"
        for v in disc.get("violations", [])) or "<div class='muted'>No violations recorded. Clean process.</div>"
    js_stats = disc.get("journal_stats", {})

    # ---- booked P/L section pieces
    booked = tax.get("booked", {})
    b_rows = []
    for x in reversed(tax.get("realised", [])):          # newest first
        held_txt = f"{x['months']} mo" if x.get("months") is not None else "—"
        pct_txt = f"{x['pct']:+.1f}%" if x.get("pct") is not None else "—"
        b_rows.append(
            f"<tr><td class='tk'><b>{html.escape(x['ticker'])}</b><div class='nm'>{html.escape(x.get('name',''))}</div></td>"
            f"<td class='num'>{x['qty']:,.0f}</td>"
            f"<td class='num'>{_inr(x.get('buy_price'),2)} → {_inr(x.get('sell_price'),2)}</td>"
            f"<td class='num'>{held_txt}</td>"
            f"<td class='num {_cls(x['gain'])}'><b>{_inr(x['gain'])}</b><div class='sub'>{pct_txt}</div></td>"
            f"<td>{html.escape(x['kind'])}</td>"
            f"<td class='num'>{_inr(x.get('tax'))}<div class='sub muted'>+{_inr(x.get('friction'))} chg</div></td>"
            f"<td>{html.escape(x.get('sell_date',''))}</td></tr>")
    booked_table = "".join(b_rows) or ("<tr><td colspan='8' class='muted' style='padding:18px'>"
        "No sales recorded yet. When you book a profit or loss, add it via ✎ Edit portfolio → Sells "
        "(and reduce the quantity in Holdings) — it appears here with your running total.</td></tr>")
    b_total = booked.get("total", 0)

    # ---- P/L ledger: financial-year presets built from the data we actually have
    _fy_years = sorted({(int(x["sell_date"][:4]) - (0 if int(x["sell_date"][5:7]) >= 4 else 1))
                        for x in tax.get("realised", []) if x.get("sell_date")}, reverse=True)
    _ld_opts = ['<option value="thisfy">This financial year</option>',
                '<option value="lastfy">Last financial year</option>',
                '<option value="12m">Last 12 months</option>',
                '<option value="all" selected>All time</option>']
    _ld_opts += [f'<option value="fy{y}">FY {y}-{str(y + 1)[2:]}</option>' for y in _fy_years]
    _ld_opts.append('<option value="custom">Custom dates…</option>')
    ld_options = "".join(_ld_opts)

    # ---- holdings table rows
    trows = []
    for r in rows:
        signals_html = " ".join(_chip(sg) for sg in r["signals"]) or "<span class='muted'>Hold</span>"
        news_html = "".join(_news_link(n) for n in r.get("news", [])[:3]) or "<span class='muted'>—</span>"
        price_badge = "" if r.get("has_price") else "<span class='badge'>no feed</span>"
        rsi_txt = "—" if r["rsi"] is None else f"{r['rsi']:.0f}"
        trend_txt = {"up": "▲ up", "down": "▼ down", None: "—"}.get(r["trend"], "—")
        held = r.get("months_held")
        held_txt = f"{held} mo" if held is not None else "<span class='addd'>add date</span>"
        c = r.get("corp") or {}
        fin_bits = []
        if c.get("q_label"):
            fin_bits.append(f"<b>{html.escape(c['q_label'])}</b>")
        if c.get("q_revenue") is not None:
            yoy = f" <span class='{_cls(c.get('rev_yoy'))}'>({c['rev_yoy']:+.1f}%)</span>" if c.get("rev_yoy") is not None else ""
            fin_bits.append(f"Rev {_lakh_cr(c['q_revenue'])}{yoy}")
        if c.get("q_profit") is not None:
            yoy = f" <span class='{_cls(c.get('profit_yoy'))}'>({c['profit_yoy']:+.1f}%)</span>" if c.get("profit_yoy") is not None else ""
            fin_bits.append(f"PAT {_lakh_cr(c['q_profit'])}{yoy}")
        if c.get("next_earnings"):
            fin_bits.append(f"<span class='muted'>results {html.escape(c['next_earnings'])}</span>")
        ratio_bits = []
        if c.get("pe") is not None:
            ratio_bits.append(f"PE {c['pe']:.1f}")
        if c.get("roe") is not None:
            ratio_bits.append(f"ROE {c['roe']:.0f}%")
        if c.get("de") is not None:
            ratio_bits.append(f"D/E {c['de']:.2f}")
        if c.get("div_yield"):
            ratio_bits.append(f"Yld {c['div_yield']:.1f}%")
        if ratio_bits:
            fin_bits.append("<span class='muted'>" + " · ".join(ratio_bits) + "</span>")
        fin_html = "<div class='fin'>" + "<br>".join(fin_bits) + "</div>" if fin_bits else "<span class='muted'>—</span>"
        tax_badge = f"<span class='taxb {r['tax_status'].lower()}'>{r['tax_status']}</span>" if r.get("tax_status") else ""
        notes_html = f"<div class='notes'>📝 {html.escape(r['notes'])}</div>" if r.get("notes") else ""
        hv = r.get("health")
        hcls = "hgood" if hv is not None and hv >= 65 else ("hbad" if hv is not None and hv <= 35 else "hmid")
        health_badge = (f"<span class='hb {hcls}' title='Rule-based health score (formula in engine.py)'>{hv}</span>"
                        if hv is not None else "")
        trows.append(f"""<tr data-day="{r['day_pct'] or 0}" data-pnl="{r['pnl_pct'] or 0}" data-val="{r['current']}" data-price="{r['price'] or 0}" data-qty="{r['qty']}" data-date="{html.escape(r.get('buy_date') or '')}" data-tk="{html.escape(r['ticker'].lower())} {html.escape(r['name'].lower())}">
          <td class="tk"><b>{html.escape(r['ticker'])}</b>{health_badge}{price_badge}<button class="chartb" data-chart="{html.escape(r['ticker'])}" title="Price history">📈</button><div class="nm">{html.escape(r['name'])}</div>{notes_html}</td>
          <td class="num">{_inr(r['price'],2)}</td>
          <td class="num {_cls(r['day_pct'])}">{_pct(r['day_pct'])}</td>
          <td class="num">{r['qty']:,.0f}</td>
          <td class="num">{_inr(r['avg_cost'],2)}</td>
          <td class="num">{held_txt}{(' ' + tax_badge) if tax_badge else ''}</td>
          <td class="num">{_inr(r['current'],0)}</td>
          <td class="num {_cls(r['pnl'])}">{_inr(r['pnl'],0)}<div class="sub">{_pct(r['pnl_pct'])}</div></td>
          <td class="num">{trend_txt}<div class="sub">RSI {rsi_txt}</div></td>
          <td class="finc">{fin_html}</td>
          <td class="sig">{signals_html}</td>
          <td class="nws">{news_html}</td>
        </tr>""")
    table_body = "\n".join(trows)

    unresolved = [r["ticker"] for r in rows if not r.get("has_price")]
    unresolved_note = ""
    if unresolved:
        unresolved_note = (f'<div class="warnbar">No live price feed for: '
                           f'{html.escape(", ".join(unresolved))} — showing last known price.</div>')

    sim_rows = [{"tk": r["ticker"], "name": r["name"], "price": r["price"],
                 "qty": r["qty"], "sector": r.get("sector", "Others"),
                 "lots": r.get("lots", [])}
                for r in rows if r.get("has_price") and r["qty"] > 0]
    data_js = json.dumps({"history": history, "div": div_m,
                          "history5y": model.get("history5y") or {},
                          "benchmark": model.get("benchmark"),
                          "sectors": model.get("sectors", []),
                          "mc": risk.get("montecarlo"),
                          "booked": booked.get("series", []),
                          "total": s.get("current"),
                          "realised": tax.get("realised", []),
                          "px": {r["ticker"]: {"name": r["name"], "qty": r["qty"],
                                               "avg": r.get("avg_cost"), "price": r["price"],
                                               "lots": [{"d": l.get("buy_date"), "p": l.get("buy_price"),
                                                         "q": l.get("qty")} for l in (r.get("lots") or [])]}
                                 for r in rows}
                                | {w["ticker"]: {"name": w["name"], "qty": 0, "avg": None,
                                                 "price": w.get("price"), "lots": []}
                                   for w in watch},
                          "rows": sim_rows}, separators=(",", ":"))
    n_watch = len(watch)
    day_cls = "up" if s.get("day_pnl", 0) >= 0 else "down"

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Sensex Tracker</title>
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#0f172a">
<link rel="apple-touch-icon" href="icons/icon-192.png">
<script>(function(){{var t=localStorage.getItem('st_theme');if(!t)t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';document.documentElement.dataset.theme=t;}})();</script>
<script src="chart.umd.min.js"></script>
<style>{CSS}</style></head>
<body>
<div class="layout">
  <aside class="sidebar">
    <div class="brand">📈 Sensex Tracker</div>
    <div class="navlbl">Menu</div>
    <nav class="nav">
      <a data-sec="overview" class="active">🏠 Overview</a>
      <a data-sec="holdings">💼 Holdings <span class="cnt">{s['n_holdings']}</span></a>
      <a data-sec="corporate">🏛️ Corporate actions</a>
      <a data-sec="news">📰 News</a>
      <a data-sec="insights">🔬 Insights</a>
      <a data-sec="discipline">🧭 Discipline</a>
      <a data-sec="booked">💰 Booked P/L</a>
      <a data-sec="ledger">📒 Profit &amp; loss banks</a>
      <a data-sec="tax">🧾 Tax &amp; returns</a>
      <a data-sec="watchlist">⭐ Watchlist <span class="cnt">{n_watch}</span></a>
    </nav>
    <div class="sidefoot">
      <button class="editbtn" id="themeBtn">🌙 Dark mode</button>
      <button class="editbtn" id="editBtn">✎ Edit portfolio</button>
      <div class="stamp">Updated {html.escape(meta['generated'])}<br>{s['n_priced']}/{s['n_holdings']} priced live · rule-based, no AI</div>
    </div>
  </aside>

  <main class="main">
    <div class="topbar">
      <h1 id="secTitle">Overview</h1>
      <span class="sub">Signals follow your rule: book only on ≥15% gain within 6 months, or a company issue.</span>
    </div>

    <!-- ================ OVERVIEW ================ -->
    <section data-sec="overview" class="show">
      <div class="floorbar {floor_cls}">
        <div class="floorhead"><b>🏠 Family floor</b><span class="muted" style="font-size:12px">{floor_note}</span>
          <span class="sp" style="flex:1"></span>
          <span class="adbadge {ad_cls}" title="Process-adherence score — discipline first, returns second">Process {ad_score if ad_score is not None else '—'}/100</span></div>
        <div class="floorgrid">{floor_items_html}</div>
      </div>
      <div class="cards">
        <div class="card"><div class="k">Invested</div><div class="v">{_inr(s['invested'])}</div></div>
        <div class="card"><div class="k">Current value</div><div class="v">{_inr(s['current'])}</div>{pill(s.get('day_pct'))}</div>
        <div class="card"><div class="k">Total P/L</div><div class="v {_cls(s['pnl'])}">{_inr(s['pnl'])}</div>{pill(s['pnl_pct'])}</div>
        <div class="card"><div class="k">Today</div><div class="v {day_cls}">{_inr(s.get('day_pnl'))}</div>
          <span class="muted" style="font-size:11.5px">{len(s['sell_review'])} to review · {len(s['issues'])} flagged</span></div>
      </div>
      {unresolved_note}
      <div class="grid-main">
        <div class="panel">
          <h2>Portfolio performance <span class="sp"></span>
            <span class="rangebtns modebtns" style="margin-right:8px">
              <button data-mode="value" class="on">₹ Value</button><button data-mode="nifty">vs Nifty</button>
            </span>
            <span class="rangebtns">
              <button data-days="63">3M</button><button data-days="126">6M</button>
              <button data-days="0" class="on">1Y</button><button data-days="-1">5Y</button>
            </span></h2>
          <div class="chartbox" id="perfBox"><canvas id="perfChart"></canvas></div>
          <div class="muted" id="perfNote" style="font-size:11px;margin-top:8px;line-height:1.5"></div>
        </div>
        <div class="panel">
          <h2>My watchlist <span class="sp"></span><a data-sec="watchlist" class="muted" style="cursor:pointer;font-size:11px" onclick="show('watchlist')">view all →</a></h2>
          {watch_panel}
        </div>
      </div>
      <div class="grid-main">
        <div class="panel">
          <h2>Top movers today</h2>
          <div class="mvgrid">{gainers}</div>
          <div style="height:10px"></div>
          <div class="mvgrid">{losers}</div>
        </div>
        <div class="panel">
          <h2>Dividends received (12 mo)</h2>
          <div class="chartbox sm" id="divBox"><canvas id="divChart"></canvas></div>
        </div>
      </div>
      <div class="grid-main">
        <div class="panel">
          <h2>Sector allocation</h2>
          <div class="donutwrap">
            <div class="chartbox sm" style="height:200px" id="sectorBox"><canvas id="sectorChart"></canvas></div>
            <div id="sectorLegend" class="slegend"></div>
          </div>
        </div>
        <div class="panel">
          <h2>Returns &amp; tax <span class="sp"></span><a class="muted" style="cursor:pointer;font-size:11px" onclick="show('tax')">details →</a></h2>
          <div class="minitiles">
            <div class="mt"><div class="k">Annualised return (XIRR)</div><div class="v {_cls(tax.get('xirr'))}">{('—' if tax.get('xirr') is None else f"{tax['xirr']:+.1f}%")}</div><div class="sub muted">needs buy dates</div></div>
            <div class="mt"><div class="k">Est. dividend income / yr</div><div class="v">{_inr(tax.get('div_income'))}</div><div class="sub muted">trailing 12m × qty</div></div>
            <div class="mt"><div class="k">Tax if sold today</div><div class="v">{_inr(unreal.get('est_total_tax'))}</div><div class="sub muted">LTCG {_inr(unreal.get('est_ltcg_tax'))} · STCG {_inr(unreal.get('est_stcg_tax'))}</div></div>
            <div class="mt"><div class="k">Nearing 1-yr (LTCG)</div><div class="v">{len(tax.get('approaching', []))}</div><div class="sub muted">hold to cut tax</div></div>
          </div>
        </div>
      </div>
      <div class="grid-main">
        <div class="panel"><h2>⭐ Booking review — ≥15% in 6 months</h2><ul class="act">{sell_list}</ul></div>
        <div class="panel"><h2>⚠️ Possible company issues</h2><ul class="act">{issue_list}</ul></div>
      </div>
      <div class="panel"><h2>⚖️ Concentration &amp; rebalancing</h2><ul class="act">{conc_html}</ul></div>
    </section>

    <!-- ================ HOLDINGS ================ -->
    <section data-sec="holdings">
      <div class="tablecard">
        <div class="controls">
          <span class="muted" style="align-self:center;padding-right:4px">Sort:</span>
          <button data-sort="val" class="on">Value</button>
          <button data-sort="pnl" title="Lifetime gain %">Lifetime gain</button>
          <button data-sort="day" title="Today's move %">Today's gain</button>
          <button data-sort="date" title="When you bought">Buy date</button>
          <button data-sort="price" title="Price per share">Share price</button>
          <button data-sort="qty" title="Number of shares held">Shares held</button>
          <input id="tkFilter" placeholder="Filter… e.g. TATA" spellcheck="false">
        </div>
        <table class="data" id="tbl"><thead><tr>
          <th>Stock</th><th class="num">Price</th><th class="num">Day</th><th class="num">Qty</th>
          <th class="num">Avg cost</th><th class="num">Held</th><th class="num">Value</th><th class="num">P/L</th>
          <th>Trend</th><th>Financials</th><th>Signals</th><th>Recent news</th>
        </tr></thead><tbody>
{table_body}
        </tbody></table>
      </div>
    </section>

    <!-- ================ CORPORATE ================ -->
    <section data-sec="corporate">
      <div class="grid-main">
        <div class="panel"><h2>📅 Upcoming — next 30 days</h2>{cal_html}</div>
        <div class="panel"><h2>ℹ️</h2><div class="muted" style="font-size:12.5px">Dates come from Yahoo's earnings calendar and headline scanning — always confirm on the exchange before acting. Dividend/split history is in the list below.</div></div>
      </div>
      <div class="panel"><h2>🏛️ Corporate actions, results &amp; events</h2><ul class="act corp">{corp_html}</ul></div>
    </section>

    <!-- ================ INSIGHTS ================ -->
    <section data-sec="insights">
      <div class="cards">
        <div class="card"><div class="k">Annualised return</div><div class="v {_cls(rm.get('ann_return'))}">{('—' if rm.get('ann_return') is None else f"{rm['ann_return']:+.1f}%")}</div><span class="muted" style="font-size:11px">from history</span></div>
        <div class="card"><div class="k">Volatility (ann.)</div><div class="v">{('—' if rm.get('volatility') is None else f"{rm['volatility']}%")}</div><span class="muted" style="font-size:11px">daily σ × √252</span></div>
        <div class="card"><div class="k">Max drawdown</div><div class="v" style="font-size:17px">{fmt_dd()}</div></div>
        <div class="card"><div class="k">Beta vs Nifty · risk-adj.</div><div class="v">{('—' if rm.get('beta') is None else rm['beta'])} · {('—' if rm.get('sharpe') is None else rm['sharpe'])}</div><span class="muted" style="font-size:11px">&gt;1 = swings more than market · higher is better</span></div>
      </div>
      <div class="warnbar">📸 {snap_note}</div>
      <div class="grid-main">
        <div class="panel">
          <h2>Where could this go? — 3-year Monte Carlo</h2>
          <div class="chartbox" id="mcBox"><canvas id="mcChart"></canvas></div>
          <div class="muted" style="font-size:11.5px;margin-top:8px">{mc.get('sims','—')} simulations bootstrapped from your portfolio's real daily returns. Bands are the 10th–90th percentile; the middle line is the median. A projection, not a promise.</div>
        </div>
        <div class="panel">
          <h2>Move-together pairs <span class="sp"></span><span class="muted" style="font-size:11px">diversification {corr.get('diversification','—')}/100</span></h2>
          <div class="muted" style="font-size:11.5px;margin-bottom:8px">Highest return-correlation among your larger holdings — pairs near +1.00 behave like one position.</div>
          {pairs_html}
        </div>
      </div>
      <div class="panel">
        <h2>🧪 Your rule, backtested — sell at +{bt.get('gain_pct',15):.0f}% within 6 months vs buy &amp; hold</h2>
        <div style="font-size:13px;margin-bottom:10px">{bt_verdict}</div>
        <div style="overflow:auto"><table class="data" style="min-width:560px"><thead><tr>
          <th>Stock</th><th class="num">Buy &amp; hold</th><th class="num">Your rule</th><th>Rule action</th>
        </tr></thead><tbody>{bt_rows}</tbody></table></div>
        <div class="muted" style="font-size:11.5px;margin-top:8px">Simplified test over the last year of prices: entry at window start, cash after a rule-sell, top {len(bt.get('rows',[]))} by value shown. It measures the rule's tendency, not an exact replay of your trades.</div>
      </div>
    </section>

    <!-- ================ NEWS ================ -->
    <section data-sec="news">
      <div class="newsbar">
        <input id="newsFilter" placeholder="Search news… stock name or ticker" spellcheck="false">
        <button id="posOnly" style="--on:#e8f5e9">🟢 Good news</button>
        <button id="negOnly">🔴 Bad news</button>
      </div>
      <div class="newsgrid" id="newsGrid">{news_html_all}</div>
    </section>

    <!-- ================ DISCIPLINE ================ -->
    <section data-sec="discipline">
      <div class="grid-main">
        <div class="panel">
          <h2>🎯 Process-adherence score <span class="sp"></span><span class="adbadge {ad_cls}">{ad_score if ad_score is not None else '—'}/100</span></h2>
          <div class="muted" style="font-size:12.5px;margin-bottom:10px">Discipline is the tracked metric; the portfolio outcome is secondary. Formula in scripts/discipline.py.</div>
          {ad_parts_html}
        </div>
        <div class="panel">
          <h2>🚫 Violations <span class="sp"></span><span class="muted" style="font-size:11px">{len(disc.get('violations', []))} recorded</span></h2>
          <div class="muted" style="font-size:12.5px;margin-bottom:10px">Rules can be broken — but never silently. Log any deviation with a typed justification (✎ Edit portfolio → Violations).</div>
          {viol_html}
        </div>
      </div>
      <div class="panel" style="margin-bottom:14px">
        <h2>📖 Journal <span class="sp"></span><span class="muted" style="font-size:11px">{js_stats.get('weeks_covered','—')}/{js_stats.get('window','12')} recent weeks covered · {js_stats.get('entries_total',0)} entries</span></h2>
        <div class="muted" style="font-size:12.5px;margin-bottom:10px">Weekly, thesis-focused notes — price commentary alone doesn't count. Say what changed structurally, or say "no structural change."</div>
        {journal_html}
      </div>
      <div class="tablecard">
        <div class="controls"><b style="font-size:13px;padding:4px">📜 Theses, kill conditions &amp; review dates</b>
          <span class="muted" style="font-size:11.5px;align-self:center">A position without a written falsifiable thesis is a feeling. Edit via ✎ Edit portfolio → Discipline.</span></div>
        <table class="data"><thead><tr>
          <th>Position</th><th>Stage</th><th>Thesis</th><th>Proof metric</th><th>Kill condition</th><th class="num">Review</th>
        </tr></thead><tbody>
{disc_table}
        </tbody></table>
      </div>
    </section>

    <!-- ================ BOOKED P/L ================ -->
    <section data-sec="booked">
      <div class="cards">
        <div class="card"><div class="k">Total booked so far</div><div class="v {_cls(b_total)}">{_inr(b_total)}</div><span class="muted" style="font-size:11px">across {booked.get('n',0)} sale(s)</span></div>
        <div class="card"><div class="k">{html.escape(booked.get('fy_label','This FY'))}</div><div class="v {_cls(booked.get('fy',0))}">{_inr(booked.get('fy'))}</div><span class="muted" style="font-size:11px">est. tax {_inr(booked.get('fy_tax'))}</span></div>
        <div class="card"><div class="k">Win rate</div><div class="v">{('—' if booked.get('win_rate') is None else f"{booked['win_rate']}%")}</div><span class="muted" style="font-size:11px">{booked.get('wins',0)} profitable of {booked.get('n',0)}</span></div>
        <div class="card"><div class="k">Costs paid</div><div class="v" style="font-size:18px">{_inr(rt.get('tax'))} <span class="muted" style="font-size:12px">tax</span></div><span class="muted" style="font-size:11px">+ {_inr(rt.get('friction'))} friction (brokerage/STT/charges)</span></div>
      </div>
      <div class="panel" style="margin-bottom:14px">
        <h2>Cumulative booked profit</h2>
        <div class="chartbox sm" id="bookedBox"><canvas id="bookedChart"></canvas></div>
      </div>
      <div class="tablecard">
        <div class="controls"><b style="font-size:13px;padding:4px">💰 Every booking</b>
          <span class="muted" style="font-size:11.5px;align-self:center">Record a sale via ✎ Edit portfolio → Sells (ticker, qty, buy price/date, sell price/date) — and reduce the sold quantity in the Holdings tab.</span></div>
        <table class="data" style="min-width:820px"><thead><tr>
          <th>Stock</th><th class="num">Qty</th><th class="num">Buy → Sell</th><th class="num">Held</th>
          <th class="num">Booked P/L</th><th>Type</th><th class="num">Tax + charges</th><th>Sold on</th>
        </tr></thead><tbody>{booked_table}</tbody></table>
      </div>
    </section>

    <!-- ================ PROFIT & LOSS BANKS ================ -->
    <section data-sec="ledger">
      <div class="panel" style="margin-bottom:14px">
        <h2>🗓️ Period</h2>
        <div class="simrow">
          <select id="ldPeriod">{ld_options}</select>
          <input id="ldFrom" type="date" title="From date">
          <input id="ldTo" type="date" title="To date">
          <button id="ldGo" class="simbtn">Apply</button>
        </div>
        <div class="muted" style="font-size:12px;margin-top:9px">Pick a preset or set your own dates — both banks, the net and the ratios below recalculate for that window. Trades are counted on their <b>sell date</b>.</div>
      </div>
      <div class="cards">
        <div class="card"><div class="k">Net P/L <span class="muted" id="ldLbl" style="font-weight:400"></span></div><div class="v" id="ldNet">—</div><span class="muted" style="font-size:11px" id="ldNetSub"></span></div>
        <div class="card"><div class="k">💚 Profit bank</div><div class="v up" id="ldWin">—</div><span class="muted" style="font-size:11px" id="ldWinSub"></span></div>
        <div class="card"><div class="k">🩹 Loss bank</div><div class="v down" id="ldLoss">—</div><span class="muted" style="font-size:11px" id="ldLossSub"></span></div>
        <div class="card"><div class="k">Win rate &amp; payoff</div><div class="v" id="ldRate">—</div><span class="muted" style="font-size:11px" id="ldRateSub"></span></div>
      </div>
      <div class="warnbar">🩹 A losing trade in this window can still shelter tax: short-term losses set off against both short- and long-term gains, long-term losses only against long-term gains, and anything unabsorbed carries forward eight assessment years if the return is filed on time. Confirm the set-off order with your CA.</div>
      <div class="tablecard" style="margin-bottom:14px">
        <div class="controls"><b style="font-size:13px;padding:4px">💚 Profit bank — every trade you made money on</b>
          <button class="simbtn" id="ldWinCsv" style="margin-left:auto;padding:6px 12px">Download CSV</button></div>
        <table class="data" style="min-width:820px"><thead><tr>
          <th>Stock</th><th class="num">Qty</th><th class="num">Buy → Sell</th><th class="num">Held</th>
          <th class="num">Gain</th><th class="num">Return</th><th>Type</th><th>Sold on</th>
        </tr></thead><tbody id="ldWinBody"></tbody></table>
      </div>
      <div class="tablecard">
        <div class="controls"><b style="font-size:13px;padding:4px">🩹 Loss bank — every trade you lost money on</b>
          <button class="simbtn" id="ldLossCsv" style="margin-left:auto;padding:6px 12px">Download CSV</button></div>
        <table class="data" style="min-width:820px"><thead><tr>
          <th>Stock</th><th class="num">Qty</th><th class="num">Buy → Sell</th><th class="num">Held</th>
          <th class="num">Loss</th><th class="num">Return</th><th>Type</th><th>Sold on</th>
        </tr></thead><tbody id="ldLossBody"></tbody></table>
      </div>
    </section>

    <!-- ================ TAX & RETURNS ================ -->
    <section data-sec="tax">
      <div class="cards">
        <div class="card"><div class="k">Annualised return (XIRR)</div><div class="v {_cls(tax.get('xirr'))}">{('—' if tax.get('xirr') is None else f"{tax['xirr']:+.1f}%")}</div><span class="muted" style="font-size:11px">across dated lots</span></div>
        <div class="card"><div class="k">Unrealised LTCG</div><div class="v {_cls(unreal.get('ltcg_gain'))}">{_inr(unreal.get('ltcg_gain'))}</div><span class="muted" style="font-size:11px">est. tax {_inr(unreal.get('est_ltcg_tax'))}</span></div>
        <div class="card"><div class="k">Unrealised STCG</div><div class="v {_cls(unreal.get('stcg_gain'))}">{_inr(unreal.get('stcg_gain'))}</div><span class="muted" style="font-size:11px">est. tax {_inr(unreal.get('est_stcg_tax'))}</span></div>
        <div class="card"><div class="k">Est. dividend income / yr</div><div class="v">{_inr(tax.get('div_income'))}</div><span class="muted" style="font-size:11px">trailing 12m × qty</span></div>
      </div>
      <div class="warnbar">🧾 Estimates only, <b>not tax advice</b>. Assumes STT-paid listed equity; no surcharge/cess. {html.escape(rate_line)}
        {'' if unreal.get('dated', 0) == unreal.get('n', 0) else f" Only {unreal.get('dated',0)}/{unreal.get('n',0)} holdings have buy dates — add them in the editor for accurate LTCG/STCG split and XIRR."}</div>
      <div class="grid-main">
        <div class="panel"><h2>⏳ Approaching long-term (save tax by holding)</h2><ul class="act">{appr_html}</ul></div>
        <div class="panel"><h2>💸 Realised gains (from sells.csv)</h2>{realised_html}</div>
      </div>
      <div class="panel">
        <h2>🧮 Sell simulator — what happens if I sell?</h2>
        <div class="simrow">
          <select id="simStock"></select>
          <input id="simQty" type="number" min="1" placeholder="Qty">
          <input id="simPrice" type="number" step="0.05" placeholder="Price (blank = last)">
          <button id="simGo" class="simbtn">Simulate</button>
        </div>
        <div id="simOut" class="muted" style="font-size:13px;margin-top:10px">Pick a stock, quantity and (optionally) a price — you'll see the estimated tax, the smartest lots to sell (lowest-tax first), and how your allocation changes. Nothing is executed anywhere; it's pure arithmetic.</div>
      </div>
    </section>

    <!-- ================ WATCHLIST ================ -->
    <section data-sec="watchlist">
      <div class="panel" style="margin-bottom:14px">
        <h2>⭐ Watchlist <span class="sp"></span>
        <button class="editbtn" id="editBtn2" style="background:var(--ink);padding:7px 12px">✎ Edit watchlist</button></h2>
        <div class="muted" style="font-size:12.5px">Stocks you're tracking but don't own. They get the same price, trend, RSI and news scanning as your holdings — add one here first, buy later when it looks right.</div>
      </div>
      <div class="newsgrid">{watch_section}</div>
    </section>

    <footer>
      Prices &amp; fundamentals via Yahoo Finance · news via Google News RSS · indicators (50/200-DMA, RSI-14) computed locally.
      This is information, not investment advice. Signals are mechanical rules — always read the news and use your judgment.
    </footer>
  </main>
</div>

<!-- ---------------- Portfolio editor modal ---------------- -->
<div class="modal" id="edModal">
  <div class="mbox">
    <h3>✎ Edit portfolio</h3>
    <div class="hint">
      Edit your holdings and watchlist; saving commits the files to your GitHub repo and the tracker
      rebuilds in ~1–2 minutes. One-time setup: create a <b>fine-grained personal access token</b>
      (GitHub → Settings → Developer settings → Tokens) scoped to <i>only this repository</i> with
      <b>Contents: Read &amp; write</b>. The token stays in this browser only.
    </div>
    <div class="cfg">
      <input id="cfgRepo" placeholder="owner/repo e.g. harry/sensex-tracker" spellcheck="false">
      <input id="cfgTok" placeholder="GitHub token (github_pat_…)" type="password" spellcheck="false">
    </div>
    <div class="tabs">
      <button data-tab="holdings" class="on">Holdings</button>
      <button data-tab="watchlist">Watchlist</button>
      <button data-tab="discipline">Discipline</button>
      <button data-tab="journal">Journal</button>
      <button data-tab="violations">Violations</button>
      <button data-tab="sells">Sells</button>
      <button data-tab="floor">Floor</button>
    </div>
    <div class="edwrap">
      <table class="ed"><thead><tr id="edHead"></tr></thead><tbody id="edBody"></tbody></table>
    </div>
    <div class="mrow">
      <button id="addRow">+ Add stock</button>
      <span style="flex:1"></span>
      <span id="edStatus" class="muted"></span>
      <button id="edCancel">Cancel</button>
      <button id="edSave" class="primary">Save to GitHub</button>
    </div>
  </div>
</div>

<div class="modal" id="pxModal">
  <div class="mbox" style="max-width:900px">
    <h3 id="pxTitle">Price history</h3>
    <div class="hint" id="pxSub"></div>
    <div class="rangebtns2" id="pxRange">
      <button data-r="6m">6M</button>
      <button data-r="1y" class="on">1Y</button>
      <button data-r="5y">5Y</button>
      <button data-r="max">Since you bought</button>
    </div>
    <div class="chartbox lg"><canvas id="pxChart"></canvas></div>
    <div class="pxstats" id="pxStats"></div>
    <div class="mrow" style="margin-top:14px">
      <span id="pxNote" class="muted" style="font-size:11.5px;flex:1"></span>
      <button id="pxClose">Close</button>
    </div>
  </div>
</div>

<script>window.__DATA={data_js};</script>
<script>{JS}</script>
</body></html>"""
