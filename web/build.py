#!/usr/bin/env python3
"""Build streaming-watchlist/web/index.html from the watchlist data files.

Includes automatic poster art lookup via the Apple iTunes Search API
(no API key required). Posters are downloaded once, cached in
web/posters/ and web/posters.json, and gracefully fall back to a
gradient placeholder if unavailable.

Run after any data update (the hourly/daily jobs do this automatically):
    python3 streaming-watchlist/web/build.py
"""
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IST = timezone(timedelta(hours=5, minutes=30))
UA = {"User-Agent": "Mozilla/5.0 (streaming-watchlist-builder)"}


def p(*parts):
    return os.path.join(ROOT, *parts)


def read(rel):
    try:
        with open(p(rel), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def esc(s):
    return html.escape(str(s), quote=True)


def inline_md(s):
    s = esc(s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"<em>\1</em>", s)
    return s


SECTIONS = [
    ("mustWatch", "🔥 Must Watch", "Titles newly deserving immediate attention"),
    ("highlyRecommended", "⭐ Highly Recommended", "Strong additions worth your queue"),
    ("hiddenGems", "💎 Hidden Gems", "Excellent but less obvious"),
    ("indianPicks", "🇮🇳 Indian Picks", "Best new Indian content"),
    ("youtubePicks", "▶️ YouTube Picks", "Docs & channels worth following"),
]

# ---------------------------------------------------------------- posters


def slugify(title):
    t = re.sub(r"\(.*?\)", "", title)  # drop parentheticals like (extended cut)
    t = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
    return t or "title"


def clean_for_search(title):
    return re.sub(r"\(.*?\)", "", title).strip()


def load_poster_cache():
    try:
        with open(p("web", "posters.json"), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def save_poster_cache(cache):
    os.makedirs(p("web"), exist_ok=True)
    with open(p("web", "posters.json"), "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=1, ensure_ascii=False)


def get_tmdb_key():
    """TMDB API key from env TMDB_API_KEY or web/tmdb_key.txt (free key)."""
    k = os.environ.get("TMDB_API_KEY", "").strip()
    if k:
        return k
    try:
        with open(p("web", "tmdb_key.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except (FileNotFoundError, OSError):
        return ""


def tmdb_lookup(term, media, api_key):
    """Return a poster URL from TMDB, or None. media: 'movie' | 'tvShow'."""
    if not api_key or not term:
        return None
    etype = "tv" if media == "tvShow" else "movie"
    q = urllib.parse.urlencode(
        {"query": clean_for_search(term), "include_adult": "false", "api_key": api_key})
    name_tokens = [w for w in re.split(r"\W+", term.lower()) if len(w) > 2]
    try:
        req = urllib.request.Request(
            f"https://api.themoviedb.org/3/search/{etype}?{q}", headers=UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None
    for res in data.get("results", []):
        poster = res.get("poster_path")
        name = (res.get("title") or res.get("name") or "").lower()
        if not poster:
            continue
        if name_tokens and not any(w in name for w in name_tokens):
            continue
        return f"https://image.tmdb.org/t/p/w500{poster}"
    return None


def download_image(url, dest):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            data = r.read(3 * 1024 * 1024)
        if len(data) < 1000:
            return False
        with open(dest, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False


def poster_for(entry, cache):
    """Return dict {'file': 'posters/x.jpg'|None, 'remote': url|None} or None."""
    if entry.get("urlType") == "channel":
        return None
    key = entry.get("title", "")
    if key in cache:
        return cache[key]
    if entry.get("poster"):  # manual override from catalog.json
        info = {"file": None, "remote": entry["poster"]}
        cache[key] = info
        return info
    etype = (entry.get("type") or "movie").lower()
    media = "tvShow" if "series" in etype else "movie"
    remote = tmdb_lookup(key, media, get_tmdb_key())
    time.sleep(0.3)
    info = {"file": None, "remote": remote}
    if remote:
        slug = slugify(key)
        os.makedirs(p("web", "posters"), exist_ok=True)
        if download_image(remote, p("web", "posters", f"{slug}.jpg")):
            info["file"] = f"posters/{slug}.jpg"
    if info["file"] or info["remote"]:
        cache[key] = info  # only cache successes; misses retry on next build
    return info


def poster_block(entry, cache):
    info = poster_for(entry, cache)
    if not info:
        return ""
    title = entry.get("title", "")
    initial = esc((title.strip()[:1] or "?").upper())
    ph = f'<div class="ph">{initial}</div>'
    if info.get("file"):
        remote = esc(info.get("remote") or "")
        return (f'<div class="poster"><img class="po" loading="lazy" '
                f'src="{esc(info["file"])}" data-remote="{remote}" '
                f'alt="{esc(title)} poster" onerror="pf(this)">{ph}</div>')
    if info.get("remote"):
        return (f'<div class="poster"><img class="po" loading="lazy" '
                f'src="{esc(info["remote"])}" alt="{esc(title)} poster" '
                f'onerror="pf(this)">{ph}</div>')
    return f'<div class="poster">{ph.replace('class="ph"', 'class="ph" style="display:flex"')}</div>'


# ---------------------------------------------------------------- cards


def card(e, cache):
    title = esc(e.get("title", "Untitled"))
    url = e.get("url") or ""
    if url.startswith("http"):
        t = f'<a class="t" href="{esc(url)}" target="_blank" rel="noopener">{title} ↗</a>'
    else:
        t = f'<span class="t">{title}</span>'
    plat = esc(e.get("platform", "—"))
    note_raw = e.get("note", "")
    note = inline_md(note_raw)
    lc = esc(e.get("lastChecked", "—"))
    score = e.get("score")
    conf = e.get("scoreConfidence", "")
    needs_check = "verify" in note_raw.lower()
    warn = '<span class="warn">⚠️ verify</span>' if needs_check else ""
    score_html = ""
    if isinstance(score, (int, float)):
        w = max(0, min(100, int(score)))
        cls = "hi" if w >= 80 else ("mid" if w >= 65 else "low")
        score_html = (f'<div class="score"><div class="bar"><i class="{cls}" '
                      f'style="width:{w}%"></i></div><span>{w}</span></div>')
    conf_html = f'<span class="chip">{esc(conf)}</span>' if conf else ""
    return (f'<article class="card">{poster_block(e, cache)}'
            f'<div class="cbody">{t}<div class="plat">{plat}</div>'
            f'<p>{note}</p><div class="meta"><span>🕒 {lc}</span>{conf_html}{warn}</div>'
            f'{score_html}</div></article>')


def section(key, heading, sub, data, cache):
    items = data.get("sections", {}).get(key, [])
    cards = "\n".join(card(e, cache) for e in items) or \
        '<p class="empty">Nothing here in the latest scan.</p>'
    return (f'<section id="{key}"><h2>{heading} <span class="count">{len(items)}</span></h2>'
            f'<p class="sub2">{sub}</p><div class="grid">{cards}</div></section>')


# ---------------------------------------------------------------- other blocks


def alerts_html():
    md = read("reports/latest-alerts.md")
    if not md.strip():
        return ('<section id="alerts"><h2>🚨 Alerts</h2>'
                '<p class="empty">No alerts right now.</p></section>')
    out, inlist = [], False
    for line in md.splitlines():
        l = line.strip()
        if not l or l == "---" or l.startswith("# "):
            continue
        if l.startswith("## "):
            if inlist:
                out.append("</ul>")
                inlist = False
            out.append(f"<h3>{inline_md(l[3:])}</h3>")
        elif l.startswith("- "):
            if not inlist:
                out.append("<ul>")
                inlist = True
            out.append(f"<li>{inline_md(l[2:])}</li>")
        else:
            if inlist:
                out.append("</ul>")
                inlist = False
            out.append(f"<p>{inline_md(l)}</p>")
    if inlist:
        out.append("</ul>")
    return f'<section id="alerts"><h2>🚨 Alerts</h2>{"".join(out)}</section>'


GENRES = ["Action", "Thriller", "Sci-Fi", "Mystery", "Drama",
          "Comedy", "Romance", "Documentary", "Animation"]


def _short_title(t):
    return re.sub(r"\s*\(.*$", "", t or "").strip()


def genre_picks(data):
    """🎯 Best title per genre — rotates daily (day-of-year mod top-4)."""
    doy = datetime.now(IST).timetuple().tm_yday
    pool = {}
    for sec in data.get("sections", {}).values():
        for e in sec:
            if not e.get("genres"):
                continue
            k = _short_title(e.get("title", "")).lower()
            cur = pool.get(k)
            if cur is None or len(e.get("note", "")) > len(cur.get("note", "")):
                pool[k] = e
    by_genre = {}
    for e in pool.values():
        for g in e.get("genres", []):
            by_genre.setdefault(g, []).append(e)
    cards = []
    for g in GENRES:
        items = sorted(by_genre.get(g, []),
                       key=lambda e: (-e.get("score", 0), e.get("title", "")))
        if not items:
            continue
        top = items[:4]
        pick, nxt = top[doy % len(top)], top[(doy + 1) % len(top)]
        url = pick.get("url") or ""
        t_html = (f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(pick["title"])} ↗</a>'
                  if url.startswith("http") else esc(pick["title"]))
        note = pick.get("note", "")
        reason = esc(note[:120]) + ("…" if len(note) > 120 else "")
        cards.append(
            f'<div class="gcard"><div class="gname">{esc(g)}</div>'
            f'<div class="gtitle">{t_html}</div>'
            f'<div class="gmeta">{esc(pick.get("platform", "—"))} · score {pick.get("score", "—")}</div>'
            f'<div class="gwhy">{reason}</div>'
            f'<div class="gnext">tomorrow → {esc(_short_title(nxt.get("title", "")))}</div>'
            f'</div>')
    if not cards:
        return ""
    today = esc(datetime.now(IST).strftime("%d %b %Y"))
    return (f'<section id="picks"><h2>🎯 Genre Picks of the Day '
            f'<span class="count">{len(cards)}</span></h2>'
            f'<p class="sub2">Best per genre · rotates daily among each genre\'s top-scored titles · {today}</p>'
            f'<div class="ggrid">{"".join(cards)}</div></section>')


def changelog_rows():
    md = read("data/change-log.md")
    rows = []
    for line in md.splitlines():
        l = line.strip()
        if re.match(r"^\d{1,2} \w{3} \d{4} \|", l):
            parts = [x.strip() for x in l.split("|", 5)]
            while len(parts) < 6:
                parts.append("")
            rows.append("<tr>" + "".join(f"<td>{esc(x)}</td>" for x in parts) + "</tr>")
    rows.reverse()  # newest first
    return rows


def platform_changes(data):
    items = data.get("platformChanges", [])
    if not items:
        return ('<section id="changes"><h2>🔄 Platform Changes</h2>'
                '<p class="empty">None detected.</p></section>')
    lis = "".join(
        f'<li><strong>{esc(i.get("title", ""))}</strong> — {inline_md(i.get("detail", ""))} '
        f'<span class="muted">({esc(i.get("lastChecked", ""))})</span></li>'
        for i in items)
    return (f'<section id="changes"><h2>🔄 Platform Changes '
            f'<span class="count">{len(items)}</span></h2><ul class="plain">{lis}</ul></section>')


def upcoming(data):
    items = data.get("upcoming", [])
    if not items:
        return ""
    lis = "".join(
        f'<li><strong>{esc(i.get("title", ""))}</strong> — {esc(i.get("platform", ""))} · '
        f'{esc(i.get("date", ""))}</li>' for i in items)
    return f'<section id="upcoming"><h2>📅 Upcoming</h2><ul class="plain">{lis}</ul></section>'


def removed(data):
    items = data.get("removed", [])
    n = len(items) if isinstance(items, list) else 0
    body = ""
    if n:
        body = "".join(
            f"<p>— {esc(i if isinstance(i, str) else i.get('title', str(i)))}</p>" for i in items)
    else:
        body = '<p class="empty">No removals detected in the latest scan.</p>'
    return (f'<section id="removed"><h2>🗑️ Removed <span class="count">{n}</span></h2>'
            f'{body}</section>')


def commands():
    rows = [
        ("REFRESH", "Immediate availability/content refresh"),
        ("HOURLY UPDATE", "Run the hourly delta check now"),
        ("DAILY UPDATE", "Run the full daily refresh now"),
        ("WHAT'S NEW", "Recently added content"),
        ("WHAT LEFT", "Recently removed content"),
        ("LEAVING SOON", "Titles that may leave soon"),
        ("PLATFORM CHANGES", "Titles that moved services"),
        ("TODAY'S PICKS", "Today's best recommendations"),
        ("LAST UPDATE", "Per-platform last-checked times"),
    ]
    trs = "".join(
        f'<tr><td><code>{esc(c)}</code></td><td>{esc(d)}</td></tr>' for c, d in rows)
    return (f'<section id="commands"><h2>⌨️ Commands</h2>'
            f'<p class="sub2">Type any command in chat with your assistant.</p>'
            f'<table><thead><tr><th>Command</th><th>Effect</th></tr></thead>'
            f'<tbody>{trs}</tbody></table></section>')


def latest_report_link():
    try:
        reports = [f for f in os.listdir(p("reports"))
                   if re.match(r"^\d{4}-\d{2}-\d{2}\.md$", f)]
        if reports:
            latest = sorted(reports)[-1]
            return f'<a href="../reports/{esc(latest)}">📄 Latest daily report ({esc(latest)})</a>'
    except OSError:
        pass
    return ""


# ---------------------------------------------------------------- styles + page

CSS = """
:root{--bg:#0b0e14;--panel:#131a26;--card:#161f2e;--line:#223046;--txt:#e8edf5;--muted:#8ea0b8;--red:#e5484d;--gold:#f5b83d;--green:#3fb970;--blue:#4c9aff}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font:16px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;padding-bottom:60px}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
header{padding:36px 24px 20px;max-width:1100px;margin:0 auto}
h1{font-size:1.9rem;letter-spacing:-.02em}
.sub{color:var(--muted);margin-top:6px}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin-top:18px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 16px;min-width:110px}
.stat b{display:block;font-size:1.35rem}.stat span{color:var(--muted);font-size:.8rem}
main{max-width:1100px;margin:0 auto;padding:0 24px}
section{margin-top:40px}
h2{font-size:1.3rem;letter-spacing:-.01em;display:flex;align-items:center;gap:10px}
.count{background:var(--panel);border:1px solid var(--line);color:var(--muted);font-size:.78rem;border-radius:999px;padding:2px 10px;font-weight:600}
.sub2{color:var(--muted);font-size:.9rem;margin:4px 0 16px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;display:flex;gap:12px;transition:transform .12s ease,border-color .12s ease}
.card:hover{transform:translateY(-2px);border-color:#33507a}
.poster{position:relative;width:88px;min-height:132px;flex-shrink:0}
.poster .po{width:100%;height:100%;min-height:132px;object-fit:cover;object-position:center top;border-radius:9px;display:block;background:var(--panel)}
.ph{display:none;position:absolute;inset:0;border-radius:9px;background:linear-gradient(145deg,#1c2a42,#0e1522);align-items:center;justify-content:center;font-weight:800;font-size:1.7rem;color:#5f7ba1}
.cbody{flex:1;min-width:0;display:flex;flex-direction:column;gap:7px}
.t{font-weight:700;font-size:1.02rem;color:var(--txt);overflow-wrap:break-word}
a.t{color:var(--txt)}a.t:hover{color:var(--blue)}
.plat{display:inline-block;align-self:flex-start;font-size:.72rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--gold);background:rgba(245,184,61,.1);border:1px solid rgba(245,184,61,.35);border-radius:6px;padding:2px 8px}
.cbody p{color:var(--muted);font-size:.86rem}
.meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap;color:var(--muted);font-size:.74rem}
.chip{background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:1px 8px}
.ggrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}
.gcard{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.gname{font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;opacity:.65}
.gtitle{margin:2px 0;font-weight:600}
.gtitle a{color:inherit}
.gmeta{font-size:.8rem;opacity:.75}
.gwhy{font-size:.8rem;opacity:.85;margin-top:4px}
.gnext{font-size:.75rem;opacity:.6;margin-top:6px}
.warn{color:var(--gold);font-weight:600}
.score{display:flex;align-items:center;gap:10px;margin-top:auto}
.score span{font-weight:800;font-size:.95rem;color:var(--txt)}
.bar{flex:1;height:6px;background:var(--panel);border:1px solid var(--line);border-radius:999px;overflow:hidden}
.bar i{display:block;height:100%}
.bar i.hi{background:var(--red)}.bar i.mid{background:var(--gold)}.bar i.low{background:var(--blue)}
#alerts{background:linear-gradient(180deg,rgba(229,72,77,.08),transparent);border:1px solid rgba(229,72,77,.25);border-radius:16px;padding:20px 22px}
#alerts h3{margin:14px 0 6px;font-size:1.02rem}
#alerts ul{margin:4px 0 4px 20px}
#alerts li,#alerts p{color:var(--muted);font-size:.9rem;margin:4px 0}
ul.plain{margin-left:20px;color:var(--muted);font-size:.92rem}
ul.plain li{margin:6px 0}
.empty{color:var(--muted);font-style:italic;font-size:.9rem;background:var(--panel);border:1px dashed var(--line);border-radius:10px;padding:12px 14px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:.88rem}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--panel);color:var(--muted);font-size:.75rem;text-transform:uppercase;letter-spacing:.05em}
tr:last-child td{border-bottom:none}
code{background:#0d1522;border:1px solid var(--line);border-radius:6px;padding:1px 7px;font-size:.82rem;color:var(--gold)}
.muted{color:var(--muted)}
.log-wrap{overflow-x:auto}
footer{max-width:1100px;margin:48px auto 0;padding:0 24px;color:var(--muted);font-size:.82rem;display:flex;gap:18px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:18px}
@media(max-width:640px){h1{font-size:1.5rem}.grid{grid-template-columns:1fr}header{padding:26px 16px 12px}main{padding:0 16px}.poster{width:72px;min-height:110px}.poster .po{min-height:110px}}
"""

JS = """
function pf(img){
  var r=img.dataset&&img.dataset.remote;
  if(r&&!img.dataset.f){img.dataset.f='1';img.src=r;return}
  img.style.display='none';
  var ph=img.parentElement&&img.parentElement.querySelector('.ph');
  if(ph)ph.style.display='flex';
}
"""


def prune_changelog():
    """Rolling 24h window: move change-log entries older than 24h to
    data/change-log-archive.md so the live log stays a recent-changes feed."""
    path = p("data", "change-log.md")
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    now = datetime.now(IST)
    keep, old = [], []
    for line in lines:
        m = re.match(r"^(\d{1,2}) (\w{3}) (\d{4}) \| (\d{1,2}:\d{2}) \|", line.strip())
        ts = None
        if m:
            try:
                ts = datetime.strptime(
                    f"{m.group(1)} {m.group(2)} {m.group(3)} {m.group(4)}",
                    "%d %b %Y %H:%M").replace(tzinfo=IST)
            except ValueError:
                ts = None
        if ts is not None and now - ts > timedelta(hours=24):
            old.append(line if line.endswith("\n") else line + "\n")
        else:
            keep.append(line)
    if not old:
        return 0
    arch = p("data", "change-log-archive.md")
    with open(arch, "a", encoding="utf-8") as f:
        if not os.path.exists(arch) or os.path.getsize(arch) == 0:
            f.write("# 🗄️ Change Log — Archive\n\n"
                    "Deprecated entries rolled off the live 24-hour change-log by web/build.py.\n\n---\n\n")
        f.writelines(old)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(keep)
    return len(old)


def main():
    pruned = prune_changelog()
    with open(p("data", "catalog.json"), encoding="utf-8") as f:
        data = json.load(f)
    now = datetime.now(IST).strftime("%d %b %Y, %H:%M IST")
    counts = {k: len(data.get("sections", {}).get(k, [])) for k, _, _ in SECTIONS}
    total = sum(counts.values())

    cache = load_poster_cache()
    body_sections = "".join(section(k, h, s, data, cache) for k, h, s in SECTIONS)
    save_poster_cache(cache)
    posters_on_disk = 0
    try:
        posters_on_disk = len([f for f in os.listdir(p("web", "posters"))
                               if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))])
    except OSError:
        pass

    rows = changelog_rows()
    log_table = (
        '<div class="log-wrap"><table><thead><tr><th>Date</th><th>Time</th><th>Title</th>'
        '<th>Change</th><th>Platform</th><th>Action</th></tr></thead><tbody>'
        + ("".join(rows) or '<tr><td colspan="6" class="empty">Log empty.</td></tr>')
        + "</tbody></table></div>")

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🎬 Streaming Watchlist — India</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>🎬 Streaming Watchlist</h1>
  <p class="sub">India · legitimate services only · last built {esc(now)} ·
  hourly delta checks + daily deep refresh · {posters_on_disk} posters cached</p>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>titles tracked</span></div>
    <div class="stat"><b>{counts['mustWatch']}</b><span>must watch</span></div>
    <div class="stat"><b>{counts['hiddenGems']}</b><span>hidden gems</span></div>
    <div class="stat"><b>{len(data.get('platformChanges', []))}</b><span>platform changes</span></div>
    <div class="stat"><b>8</b><span>platforms</span></div>
  </div>
</header>
<main>
  {alerts_html()}
  {genre_picks(data)}
  {body_sections}
  {platform_changes(data)}
  {upcoming(data)}
  {removed(data)}
  <section id="log"><h2>📊 Change Log <span class="count">{len(rows)}</span></h2>
  <p class="sub2">Newest first · rolling 24-hour window — older entries auto-archived to <a href="../data/change-log-archive.md">change-log-archive.md</a>.</p>{log_table}</section>
  {commands()}
</main>
<footer>
  <a href="../README.md">📖 System README</a>
  {latest_report_link()}
  <a href="../data/catalog.json">🗂️ catalog.json</a>
  <a href="../data/change-log.md">📊 change-log.md</a>
  <span>Regenerate: <code>python3 web/build.py</code></span>
  <span>Poster art via TMDB — paste a free API key into web/tmdb_key.txt to enable</span>
</footer>
<script>{JS}</script>
</body>
</html>
"""
    os.makedirs(p("web"), exist_ok=True)
    out = p("web", "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"built {out} — {total} titles, {len(rows)} log rows ({pruned} archived), "
          f"{posters_on_disk} posters cached, generated {now}")


if __name__ == "__main__":
    main()
