#!/usr/bin/env python3
"""Chaotic News Network story generator (Python 3.9+; Pillow for card images).

Add stories:   python3 tools/add_story.py new-story.md [another.md ...]
               python3 tools/add_story.py new-story.json
Rebuild only:  python3 tools/add_story.py --rebuild
Replace one:   python3 tools/add_story.py --replace fixed-story.md

Every story lives in content/<slug>.md (front matter + Markdown body).
Each run copies new stories into content/, then rebuilds everything from it:
stories/<slug>.html, stories/index.html, section/<section>.html,
stories.json, feed.xml, index.html, and the link-preview card images
cards/*.png (drawn by tools/social_cards.py; that part needs Pillow).
See README.md for the story format.
"""
import datetime as dt
import html
import json
import re
import sys
import zlib
from urllib.parse import quote, urlencode
from email.utils import format_datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    TZ = dt.timezone(dt.timedelta(hours=-4))

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
STORIES = ROOT / "stories"
SITE_URL = "https://2three1y.github.io/chaoticnews/"
SITE_NAME = "Chaotic News Network"
TAGLINE = "Unbiased. Unverified. Unhinged."
SATIRE = "Chaotic News is satire. All stories are made up."
X_HANDLE = "ChaoticNewsHQ"
X_URL = f"https://x.com/{X_HANDLE}"
SECTIONS = ["Breaking", "Tech", "Scams", "Beats", "Weather"]
# ---- Laughable labels (Carter, 2026-10-31: "we need laughable labels").
# Rule: the real word comes FIRST, the joke after, so VoiceOver users always
# hear what a thing is before the punchline. Section slugs, URLs, the feed,
# stories.json and the card images keep the plain section names.
SECTION_LABEL = {
    "Breaking": "Breaking: Still Breaking",
    "Tech": "Tech: Beep Boop",
    "Scams": "Scams: Nice Try, Steve",
    "Beats": "Beats: Turn It Up",
    "Weather": "Weather: We Guessed",
}
LABEL = {
    "home": "Top Stories (Probably)",
    "all": "All Stories (Yes, All of Them)",
    "satire_strip": "every story is made up, even this sentence",
    "live_pill": "Live on X",
    "ticker": "Breaking (Still)",
    "ticker_aria": "Breaking news, still breaking",
    "ticker_empty": "Developing story (slowly)",
    "satire_tag": "Satire, Obviously",
    "latest": "Latest (Still Warm)",
    "most_read": "Most Read (By Our Moms)",
    "more_top": "More Top Stories, Somehow",
    "sections": "Sections (Pick Your Chaos)",
    "related": "Related Stories, Allegedly",
    "all_link": "All stories (yes, every single one)",
    "share_head": "Share This Story (We Dare You)",
    "copy": "Copy Link (No Returns)",
    "share": "Share (Spread the Chaos)",
    "post_x": "Post on X (Go Viral, Maybe)",
    "email": "Email (Like It\u2019s 2005)",
    "follow": "Follow @{h} (We\u2019re Needy)",
    "copied": "Link copied. Go cause some chaos.",
    "copy_fail": "Couldn\u2019t copy the link. The clipboard is on a lunch break.",
    "story_satire": "Do not forward this to your aunt as fact.",
    "foot_satire": "Nothing here is real news. If it sounds true, that\u2019s a coincidence.",
    "foot_x": "Live on X: @{h} (Bring Snacks)",
    "rss": "RSS Feed (Vintage Tech)",
    "json": "Story List (JSON, for Robots)",
    "credit": "Co-written with Tab (who fact-checked nothing)",
    "updated_tail": "give or take",
    "newest": "Newest First (Oldest Last, Wild)",
    "by_section": "By Section (Sorted With Love)",
    "index_dek": "Every Chaotic News story, newest first. {n} so far, and zero of them true.",
}
EMPTY_NOTE = {
    "Beats": "No stories yet. The DJ is still on snack break.",
    "Weather": "No stories yet. Forecast: 100% chance of nothing.",
}
EMPTY_DEFAULT = "No stories yet. Check back after nap time."


def sec_label(sec):
    return SECTION_LABEL.get(sec, sec)


def read_label(n):
    return f"{n} min read ({n - 1} if you skim)" if n > 1 else "1 min read (blink and you\u2019re done)"
REQUIRED = ("title", "dek", "section")
# Link-preview cards (Open Graph / X cards). Read by X, Mastodon and the rest of
# the fediverse, Bluesky, Nostr clients, Discord, iMessage, WhatsApp, Facebook,
# Reddit, LinkedIn, Telegram and Slack. Images: cards/*.png, 1200x630, built by
# tools/social_cards.py on every run. No Mastodon account yet: when there is one,
# add its profile URL to FEDIVERSE_PROFILE (adds rel="me" + fediverse:creator).
OG_SITE_NAME = "Chaotic News"
OG_LOCALE = "en_US"
CARD_W, CARD_H = 1200, 630
FEDIVERSE_PROFILE = ""      # e.g. "https://mastodon.social/@ChaoticNewsHQ"
FEDIVERSE_CREATOR = ""      # e.g. "@ChaoticNewsHQ@mastodon.social"
SITE_CARD = "cards/site.png"
SITE_CARD_ALT = ("Chaotic News site card: the red CN logo, the tagline \u201cUnbiased. Unverified. "
                 "Unhinged.\u201d and the words \u201cBreaking news that never happened.\u201d on dark red art, with a yellow "
                 "SATIRE tag and the line \u201cSatire, every story is made up.\u201d")

# ---------------------------------------------------------------- parsing

def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)[:80].strip("-") or "story"


def parse_front_matter(text):
    if not text.startswith("---"):
        raise ValueError("story must start with a --- front matter block")
    _, fm, body = text.split("---", 2)
    meta = {}
    for line in fm.strip().splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        meta[key.strip().lower()] = val
    return meta, body.strip() + "\n"


def to_front_matter(meta, body):
    keys = ["title", "dek", "section", "date", "author", "author_title",
            "featured", "dateline", "correction", "updated", "image", "image_alt"]
    lines = ["---"]
    for k in keys + [k for k in meta if k not in keys and k != "body"]:
        if k in meta and meta[k] not in (None, ""):
            v = meta[k]
            if isinstance(v, bool):
                v = "true" if v else "false"
            v = str(v).replace("\n", " ")
            if v[:1] in "\"'" or ":" in v[:1]:
                v = '"' + v + '"'
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body.strip() + "\n"


def load_input(path):
    """Read a .md or .json story; return (meta, body)."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        data = json.loads(text)
        body = data.pop("body", "")
        if isinstance(body, list):
            body = "\n\n".join(body)
        return {k.lower(): v for k, v in data.items()}, body
    return parse_front_matter(text)


def parse_date(value):
    if not value:
        return dt.datetime.now(TZ).replace(second=0, microsecond=0)
    d = dt.datetime.fromisoformat(str(value))
    if d.tzinfo is None:
        d = d.replace(tzinfo=TZ)
    return d

# ---------------------------------------------------------------- markdown

def smart_quotes(s):
    s = re.sub(r'(^|[\s(\[\u2014-])"', "\\1\u201c", s)
    s = s.replace('"', "\u201d")
    s = re.sub(r"(^|[\s(\[\u2014-])'", "\\1\u2018", s)
    return s.replace("'", "\u2019")


def inline(text):
    links = []

    def keep(m):
        links.append((m.group(1), m.group(2)))
        return f"\x00{len(links) - 1}\x00"

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", keep, text)
    text = smart_quotes(text.replace("---", "\u2014").replace(" -- ", " \u2014 "))
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)

    def put(m):
        label, url = links[int(m.group(1))]
        return f'<a href="{html.escape(url)}">{inline(label)}</a>'

    return re.sub(r"\x00(\d+)\x00", put, text)


def markdown(md, dateline=None):
    out, first_para = [], True
    for block in re.split(r"\n\s*\n", md.strip()):
        lines = [l.rstrip() for l in block.strip().splitlines()]
        if not lines:
            continue
        head = lines[0]
        if head.startswith("### "):
            out.append(f"<h3>{inline(head[4:])}</h3>")
        elif head.startswith("## "):
            out.append(f"<h2>{inline(head[3:])}</h2>")
        elif head.startswith("# "):  # only one h1 per page: demote
            out.append(f"<h2>{inline(head[2:])}</h2>")
        elif all(l.startswith(">") for l in lines):
            q = " ".join(l.lstrip("> ").strip() for l in lines)
            out.append(f"<blockquote><p>{inline(q)}</p></blockquote>")
        elif all(re.match(r"^[-*] ", l) for l in lines):
            items = "".join(f"<li>{inline(l[2:])}</li>" for l in lines)
            out.append(f"<ul>{items}</ul>")
        elif all(re.match(r"^\d+\. ", l) for l in lines):
            items = "".join(f"<li>{inline(l.split('. ', 1)[1])}</li>" for l in lines)
            out.append(f"<ol>{items}</ol>")
        else:
            p = inline(" ".join(lines))
            if first_para and dateline:
                p = f'<span class="dateline">{html.escape(dateline.upper())} &mdash;</span> ' + p
            first_para = False
            out.append(f"<p>{p}</p>")
    return "\n  ".join(out)

# ---------------------------------------------------------------- stories

def load_stories():
    stories = []
    for f in sorted(CONTENT.glob("*.md")):
        meta, body = parse_front_matter(f.read_text(encoding="utf-8"))
        for k in REQUIRED:
            if not meta.get(k):
                raise SystemExit(f"{f.name}: missing '{k}' in front matter")
        if meta["section"] not in SECTIONS:
            raise SystemExit(f"{f.name}: section must be one of {', '.join(SECTIONS)}")
        if meta.get("image") and not meta.get("image_alt", "").strip():
            raise SystemExit(f"{f.name}: 'image' needs 'image_alt' (describe the picture for VoiceOver)")
        meta["slug"] = f.stem
        meta["when"] = parse_date(meta.get("date"))
        meta["featured"] = str(meta.get("featured", "")).lower() in ("true", "yes", "1")
        meta["author"] = meta.get("author") or f"{SITE_NAME} Staff"
        meta["body"] = body
        stories.append(meta)
    stories.sort(key=lambda s: s["when"], reverse=True)
    return stories


def nice_date(d, with_time=True):
    s = f"{d.strftime('%A, %B')} {d.day}, {d.year}"
    if with_time:
        s += ", " + d.strftime("%I:%M %p").lstrip("0")
    return s


def time_tag(d, with_time=True):
    return f'<time datetime="{d.isoformat()}">{nice_date(d, with_time)}</time>'


def esc(s):
    return html.escape(str(s), quote=True)


def title_text(s):
    """Plain title with typographic quotes (for <title>, headings)."""
    return esc(smart_quotes(s))

# ---------------------------------------------------------------- templates
# Network-style design (original, clean-room): CN logo bug, section nav,
# BREAKING bar, lead story, story cards, Most Read. Art is generated SVG.

SECTION_SLUG = {s: s.lower() for s in SECTIONS}
SECTION_BLURB = {
    "Breaking": "The news as it breaks, and sometimes before it happens.",
    "Tech": "Gadgets, apps, AI and the bots that are out to get us.",
    "Scams": "Consumer alerts from the front lines of the gift card economy.",
    "Beats": "Music, drops and things that go boom in the speakers.",
    "Weather": "Forecast: chaotic.",
}
# (start colour, end colour, accent) for each section's title-card art
PALETTE = {
    "Breaking": ("#9b0d18", "#1c0306", "#ff3b47"),
    "Tech": ("#123a8c", "#1d0b4a", "#5ab0ff"),
    "Scams": ("#8a5a00", "#241600", "#ffc23d"),
    "Beats": ("#7a1270", "#1e0631", "#ff6ad5"),
    "Weather": ("#04606e", "#071f33", "#5ee6d0"),
}
SHARE_TEXT = "Read on Chaotic News (satire):"


def section_href(prefix, sec):
    return f"{prefix}section/{SECTION_SLUG[sec]}.html"


def svg_art(s, size="card", live=False):
    """Original title-card graphic for a story (no photos). Returns HTML."""
    sec = s["section"]
    c1, c2, acc = PALETTE.get(sec, PALETTE["Breaking"])
    h = zlib.crc32(s["slug"].encode())
    cx, cy = 360 + h % 220, 90 + (h >> 8) % 140
    gid = f"g{h % 100000}-{size}"
    rings = "".join(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#fff" stroke-opacity="{0.16 - i * 0.025:.3f}" stroke-width="{10 - i * 2}"/>'
        for i, r in enumerate((60, 110, 165, 225)))
    bars = "".join(
        f'<rect x="{40 + i * 26}" y="{250 - ((h >> (i * 3)) % 90)}" width="16" height="{(h >> (i * 3)) % 90 + 20}" fill="{acc}" fill-opacity="0.35"/>'
        for i in range(6))
    live_badge = ('<g><rect x="524" y="24" width="92" height="38" rx="4" fill="#d1111c"/>'
                  '<circle cx="545" cy="43" r="7" fill="#fff"/>'
                  '<text x="560" y="51" font-family="Arial,Helvetica,sans-serif" font-weight="900" font-size="22" fill="#fff">LIVE</text></g>'
                  if live else "")
    label = f"{sec} desk title card{' with a LIVE badge' if live else ''}, Chaotic News graphic"
    if s.get("image"):
        return (f'<img class="art art-{size}" src="{{prefix}}{esc(s["image"])}" alt="{esc(s["image_alt"])}" '
                f'loading="lazy" width="640" height="360">')
    return f"""<svg class="art art-{size}" viewBox="0 0 640 360" role="img" aria-label="{esc(label)}" focusable="false" preserveAspectRatio="xMidYMid slice"><defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs><rect width="640" height="360" fill="url(#{gid})"/><path d="M0 360 L250 0 H300 L50 360Z" fill="#fff" fill-opacity="0.05"/><path d="M90 360 L340 0 H360 L110 360Z" fill="#fff" fill-opacity="0.04"/>{rings}{bars}<g><rect x="24" y="24" width="64" height="44" rx="4" fill="{'#fff' if sec == 'Breaking' else '#d1111c'}"/><text x="56" y="56" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="900" font-size="26" fill="{'#d1111c' if sec == 'Breaking' else '#fff'}">CN</text></g>{live_badge}<g><rect x="0" y="292" width="640" height="68" fill="#0b0b0d" fill-opacity="0.92"/><rect x="0" y="292" width="{len(sec) * 17 + 44}" height="68" fill="#d1111c"/><text x="22" y="336" font-family="Arial,Helvetica,sans-serif" font-weight="900" font-size="28" fill="#fff" letter-spacing="1">{esc(sec.upper())}</text><text x="{len(sec) * 17 + 64}" y="335" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="22" fill="#fff" fill-opacity="0.85" letter-spacing="2">CHAOTIC NEWS</text></g></svg>"""


def art(s, prefix, size="card", live=False):
    return svg_art(s, size, live).replace("{prefix}", prefix)


def card_path(kind, slug=None):
    """Repo-relative path of a social card PNG."""
    if kind == "site":
        return SITE_CARD
    if kind == "section":
        return f"cards/section/{slug}.png"
    return f"cards/stories/{slug}.png"


def card_url(rel):
    """Absolute https URL of a card, with a version stamp so networks refetch
    the picture when it changes."""
    p = ROOT / rel
    v = f"?v={zlib.crc32(p.read_bytes()) & 0xffffffff:08x}" if p.exists() else ""
    return f"{SITE_URL}{rel}{v}"


def story_card_alt(s):
    return (f"Chaotic News title card: the headline \u201c{smart_quotes(s['title'])}\u201d "
            f"in white over {s['section']} section art, with the red CN logo, a yellow "
            f"SATIRE tag and the line \u201cSatire, every story is made up.\u201d")


def section_card_alt(sec):
    return (f"Chaotic News {sec} section card: the red CN logo and the words "
            f"\u201c{sec} desk\u201d and \u201c{SECTION_BLURB.get(sec, '')}\u201d over {sec} "
            f"section art, with a yellow SATIRE tag and the line \u201cSatire, every story is made up.\u201d")


def satire_desc(text):
    text = smart_quotes(str(text)).strip()
    return text if text.rstrip(".").endswith("Satire") else f"{text} Satire."


def social_head(prefix, social):
    """<head> tags for link previews on every network."""
    url = social["url"]
    title = social["title"]
    desc = social["description"]
    img = card_url(social["image"])
    alt = social["image_alt"]
    m = [
        f'<link rel="canonical" href="{esc(url)}">',
        f'<meta property="og:type" content="{social.get("type", "website")}">',
        f'<meta property="og:site_name" content="{esc(OG_SITE_NAME)}">',
        f'<meta property="og:locale" content="{OG_LOCALE}">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(desc)}">',
        f'<meta property="og:url" content="{esc(url)}">',
        f'<meta property="og:image" content="{esc(img)}">',
        f'<meta property="og:image:secure_url" content="{esc(img)}">',
        '<meta property="og:image:type" content="image/png">',
        f'<meta property="og:image:width" content="{CARD_W}">',
        f'<meta property="og:image:height" content="{CARD_H}">',
        f'<meta property="og:image:alt" content="{esc(alt)}">',
    ]
    if social.get("type") == "article":
        m += [
            f'<meta property="article:published_time" content="{social["published"]}">',
            f'<meta property="article:modified_time" content="{social["modified"]}">',
            f'<meta property="article:section" content="{esc(social["section"])}">',
            f'<meta property="article:author" content="{esc(social.get("author", SITE_NAME))}">',
            '<meta property="article:tag" content="Satire">',
        ]
    m += [
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:site" content="@{X_HANDLE}">',
        f'<meta name="twitter:creator" content="@{X_HANDLE}">',
        f'<meta name="twitter:title" content="{esc(title)}">',
        f'<meta name="twitter:description" content="{esc(desc)}">',
        f'<meta name="twitter:image" content="{esc(img)}">',
        f'<meta name="twitter:image:alt" content="{esc(alt)}">',
    ]
    if FEDIVERSE_PROFILE:
        m.append(f'<link rel="me" href="{esc(FEDIVERSE_PROFILE)}">')
    if FEDIVERSE_CREATOR:
        m.append(f'<meta name="fediverse:creator" content="{esc(FEDIVERSE_CREATOR)}">')
    m += [
        f'<link rel="icon" href="{prefix}favicon.ico" sizes="any">',
        f'<link rel="icon" type="image/png" sizes="32x32" href="{prefix}favicon-32.png">',
        f'<link rel="apple-touch-icon" href="{prefix}apple-touch-icon.png">',
    ]
    return "\n".join(m)


def page(prefix, title, description, current, skip_label, main_html, ticker, scripts="", social=None):
    home = f"{prefix}./" if prefix else "./"
    nav = [(LABEL["home"], home, "home")]
    for sec in SECTIONS:
        nav.append((sec_label(sec), section_href(prefix, sec), SECTION_SLUG[sec]))
    nav.append((LABEL["all"], f"{prefix}stories/", "all"))
    cur = ' aria-current="page"'
    items = "\n".join(
        f'      <li><a href="{href}"{cur if key == current else ""}>{esc(label)}</a></li>'
        for label, href, key in nav)
    foot_links = " ".join(
        f'<li><a href="{href}">{esc(label)}</a></li>' for label, href, _ in nav)
    return f"""<!DOCTYPE html>
<html lang="en-US">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{esc(description)}">
<meta name="theme-color" content="#0b0b0d">
{social_head(prefix, social)}
<link rel="stylesheet" href="{prefix}style.css">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="{prefix}feed.xml">
</head>
<body>
<a class="skip" href="#main">{skip_label}</a>
<header class="site">
  <p class="satire-strip"><strong>Satire:</strong> {LABEL["satire_strip"]}</p>
  <div class="mast">
    <div class="mast-in">
      <a class="brand" href="{home}"><span class="bug" role="img" aria-label="Chaotic News">CN</span><span class="wordmark" aria-hidden="true">Chaotic News</span></a>
      <p class="tagline">{TAGLINE}</p>
      <a class="follow" href="{X_URL}" rel="me"><span class="dot" aria-hidden="true"></span>{LABEL["live_pill"]}</a>
      <!-- YouTube channel link goes here (no channel link yet) -->
    </div>
  </div>
  <nav class="sections" aria-label="Sections">
    <ul>
{items}
    </ul>
  </nav>
{ticker}
</header>

<main id="main">
{main_html}
</main>

<footer class="site-foot">
  <div class="foot-in">
    <p class="foot-brand"><span class="bug bug-sm" aria-hidden="true">CN</span> <span>{SITE_NAME}</span></p>
    <p class="foot-satire"><strong>Satire.</strong> {SATIRE} {LABEL["foot_satire"]}</p>
    <ul class="foot-nav" aria-label="Sections">{foot_links}</ul>
    <p class="social"><a href="{X_URL}" rel="me"><span aria-hidden="true">📺 </span>{esc(LABEL["foot_x"].format(h=X_HANDLE))}</a></p>
    <!-- YouTube channel link goes here (no channel link yet) -->
    <p class="foot-links"><a href="{prefix}feed.xml">{LABEL["rss"]}</a> <span aria-hidden="true">&middot;</span> <a href="{prefix}stories.json">{LABEL["json"]}</a></p>
    <p class="credit">{LABEL["credit"]}</p>
  </div>
</footer>{scripts}
</body>
</html>
"""


def ticker_for(stories, prefix):
    if not stories:
        heads = f'<li>{LABEL["ticker_empty"]}</li>'
    else:
        heads = "\n      ".join(
            f'<li><a href="{prefix}stories/{s["slug"]}.html">{title_text(s["title"])}</a></li>'
            for s in stories[:4])
    return f"""  <section class="ticker" aria-label="{LABEL["ticker_aria"]}">
    <div class="ticker-in">
      <p class="ticker-label">{LABEL["ticker"]}</p>
      <ul>
      {heads}
      </ul>
    </div>
  </section>"""


def local(d):
    try:
        return d.astimezone(TZ)
    except Exception:
        return d


def short_time(d):
    d = local(d)
    return d.strftime("%I:%M %p").lstrip("0") + " " + (d.strftime("%Z") or "ET")


def updated_line(d, word="Updated", joke=True):
    d = local(d)
    txt = f"{word} {short_time(d)}, {d.strftime('%a %B')} {d.day}, {d.year}"
    if joke and word == "Updated":
        txt += f", {LABEL['updated_tail']}"
    return f'<time datetime="{d.isoformat()}">{txt}</time>'


def author_html(s):
    who = f'<span class="author">{esc(s["author"])}</span>'
    if s.get("author_title"):
        who += f', <span class="author-title">{esc(s["author_title"])}</span>'
    return who


def read_minutes(s):
    return max(1, round(len(re.findall(r"\w+", s["body"])) / 230))


def card(s, prefix, base, heading="h3", stories=None, size="card"):
    href = f"{base}{s['slug']}.html"
    return (f'<li class="card">'
            f'<div class="card-art">{art(s, prefix, size)}</div>'
            f'<div class="card-text"><p class="card-kicker"><a href="{section_href(prefix, s["section"])}">{esc(sec_label(s["section"]))}</a></p>'
            f'<{heading}><a href="{href}">{title_text(s["title"])}</a></{heading}>'
            f'<p class="card-dek">{inline(s["dek"])}</p>'
            f'<p class="meta"><time datetime="{s["when"].isoformat()}">{local(s["when"]).strftime("%b")} {local(s["when"]).day}, {short_time(s["when"])}</time></p></div></li>')


def most_read(stories, exclude=(), n=5):
    pool = [s for s in stories if s["slug"] not in exclude] or stories
    return sorted(pool, key=lambda s: zlib.crc32(("read" + s["slug"]).encode()))[:n]


def render_story(s, stories):
    same = [o for o in stories if o["slug"] != s["slug"] and o["section"] == s["section"]]
    other = [o for o in stories if o["slug"] != s["slug"] and o["section"] != s["section"]]
    rel = (same + other)[:4]
    rel_html = "\n    ".join(card(o, "../", "", stories=stories) for o in rel)
    corr = (f'\n  <p class="correction"><strong>Correction:</strong> {inline(s["correction"])}</p>'
            if s.get("correction") else "")
    url = f"{SITE_URL}stories/{s['slug']}.html"
    plain_title = smart_quotes(s["title"])
    x_share = ("https://x.com/intent/post?" +
               urlencode({"text": f"{SHARE_TEXT} {plain_title}", "url": url, "via": X_HANDLE}))
    mail = "mailto:?" + urlencode({"subject": f"{plain_title} (Chaotic News, satire)",
                                   "body": f"{plain_title}\n{url}\n\nSatire: every Chaotic News story is made up."},
                                  quote_via=quote)
    upd = parse_date(s["updated"]) if s.get("updated") else s["when"]
    pub_line = ""
    if s.get("updated") and upd != s["when"]:
        pub_line = f' <span aria-hidden="true">&middot;</span> {updated_line(s["when"], "Published")}'
    pop = "\n    ".join(
        f'<li><a href="{o["slug"]}.html">{title_text(o["title"])}</a></li>'
        for o in most_read(stories, {s["slug"]}))
    main = f"""<div class="story-wrap">
<article class="story">
  <p class="kicker"><a href="{section_href('../', s['section'])}">{esc(sec_label(s['section']))}</a><span class="tag-satire">{LABEL["satire_tag"]}</span></p>
  <h1>{title_text(s['title'])}</h1>
  <p class="dek">{inline(s['dek'])}</p>
  <div class="byline">
    <span class="bug bug-sm" aria-hidden="true">CN</span>
    <div>
      <p class="by">By {author_html(s)}</p>
      <p class="when">{updated_line(upd)}{pub_line} <span aria-hidden="true">&middot;</span> {read_label(read_minutes(s))}</p>
    </div>
  </div>
  <figure class="hero-art">{art(s, '../', 'hero', live=s['section'] == 'Breaking')}</figure>
  <p class="satire-note"><strong>Satire.</strong> {SATIRE} {LABEL["story_satire"]}</p>
  <div class="body">
  {markdown(s['body'], s.get('dateline'))}{corr}
  </div>
  <div class="share">
    <p class="share-label">{LABEL["share_head"]}</p>
    <ul>
      <li><button type="button" class="share-btn" data-copy="{esc(url)}" data-done="{esc(LABEL['copied'])}" data-fail="{esc(LABEL['copy_fail'])}" hidden>{LABEL["copy"]}</button></li>
      <li><button type="button" class="share-btn" data-share="{esc(url)}" data-title="{esc(plain_title)}" hidden>{LABEL["share"]}</button></li>
      <li><a class="share-btn" href="{esc(x_share)}">{LABEL["post_x"]}</a></li>
      <li><a class="share-btn" href="{esc(mail)}">{LABEL["email"]}</a></li>
      <li><a class="share-btn" href="{X_URL}" rel="me">{esc(LABEL["follow"].format(h=X_HANDLE))}</a></li>
    </ul>
    <p class="share-status" id="share-status" role="status"></p>
  </div>
</article>

<aside class="rail" aria-labelledby="popular-heading">
  <h2 id="popular-heading" class="rail-head">{LABEL["most_read"]}</h2>
  <ol class="most-read">
    {pop}
  </ol>
</aside>
</div>

<section class="related" aria-labelledby="related-heading">
  <h2 id="related-heading" class="section-head">{LABEL["related"]}</h2>
  <ul class="cards">
    {rel_html}
  </ul>
  <p class="more"><a href="./">{LABEL["all_link"]}</a></p>
</section>"""
    social = {"type": "article", "title": plain_title, "description": satire_desc(s["dek"]),
              "url": url, "image": card_path("story", s["slug"]), "image_alt": story_card_alt(s),
              "published": s["when"].isoformat(), "modified": upd.isoformat(),
              "section": s["section"], "author": s["author"]}
    return page("../", f"{title_text(s['title'])} | {SITE_NAME}", f"{smart_quotes(s['dek'])} Satire from {SITE_NAME}.",
                SECTION_SLUG[s["section"]], "Skip to story", main, ticker_for(stories, "../"),
                '\n<script src="../share.js"></script>', social)


HOME_SOCIAL = {"type": "website", "title": f"{OG_SITE_NAME}: {TAGLINE}",
               "description": "Breaking news that never happened. Every story is made up. Satire.",
               "url": SITE_URL, "image": SITE_CARD, "image_alt": SITE_CARD_ALT}


def render_home(stories):
    if not stories:
        main = f'<h1 class="page-head">{LABEL["home"]}</h1>\n<p>{EMPTY_DEFAULT}</p>'
        return page("", f"{SITE_NAME}", TAGLINE, "home", "Skip to top stories", main, ticker_for(stories, ""), social=HOME_SOCIAL)
    lead, rest = stories[0], stories[1:]
    grid = rest[:3]
    shown = {lead["slug"]} | {s["slug"] for s in grid}
    pop = most_read(stories, {lead["slug"]})
    more = [s for s in stories if s["slug"] not in shown]
    seen, more_list = set(), []
    for s in more:
        if s["slug"] not in seen and s["slug"] != lead["slug"]:
            seen.add(s["slug"])
            more_list.append(s)
    more_list = more_list[:8]
    grid_html = "\n    ".join(card(s, "", "stories/", stories=stories) for s in grid)
    pop_html = "\n    ".join(
        f'<li><a href="stories/{s["slug"]}.html">{title_text(s["title"])}</a></li>' for s in pop)
    more_html = "\n    ".join(
        f'<li><span class="mini-kicker">{esc(sec_label(s["section"]))}</span> <a href="stories/{s["slug"]}.html">{title_text(s["title"])}</a></li>'
        for s in more_list)
    sec_counts = []
    for sec in SECTIONS:
        n = sum(1 for s in stories if s["section"] == sec)
        sec_counts.append(f'<li><a href="{section_href("", sec)}">{esc(sec_label(sec))} <span class="count">{n} {"story" if n == 1 else "stories"}</span></a></li>')
    main = f"""<h1 class="page-head"><span class="vh">Chaotic News: </span>{LABEL["home"]}</h1>
<div class="home-grid">
<div class="home-main">
<article class="lead">
  <div class="lead-art">{art(lead, '', 'hero', live=True)}</div>
  <p class="kicker"><a href="{section_href('', lead['section'])}">{esc(sec_label(lead['section']))}</a><span class="tag-satire">{LABEL["satire_tag"]}</span></p>
  <h2 class="lead-head"><a href="stories/{lead['slug']}.html">{title_text(lead['title'])}</a></h2>
  <p class="dek">{inline(lead['dek'])}</p>
  <p class="meta">By {author_html(lead)} <span aria-hidden="true">&middot;</span> {updated_line(lead['when'])}</p>
</article>

<section aria-labelledby="latest-heading">
  <h2 id="latest-heading" class="section-head">{LABEL["latest"]}</h2>
  <ul class="cards">
    {grid_html}
  </ul>
</section>
</div>

<aside class="rail" aria-label="Most read and more top stories">
  <section aria-labelledby="popular-heading">
    <h2 id="popular-heading" class="rail-head">{LABEL["most_read"]}</h2>
    <ol class="most-read">
    {pop_html}
    </ol>
  </section>
  <section aria-labelledby="more-heading">
    <h2 id="more-heading" class="rail-head">{LABEL["more_top"]}</h2>
    <ul class="more-top">
    {more_html}
    </ul>
  </section>
  <section aria-labelledby="sections-heading">
    <h2 id="sections-heading" class="rail-head">{LABEL["sections"]}</h2>
    <ul class="sec-list">
    {''.join(sec_counts)}
    </ul>
  </section>
</aside>
</div>
<p class="more"><a href="stories/">All {len(stories)} stories, newest first (freshness not guaranteed)</a></p>"""
    return page("", f"{SITE_NAME}: {TAGLINE}",
                f"Satire news, updated daily. Latest: {smart_quotes(lead['title'])}",
                "home", "Skip to top stories", main, ticker_for(stories, ""), social=HOME_SOCIAL)


def render_section(sec, stories):
    mine = [s for s in stories if s["section"] == sec]
    if mine:
        items = "\n    ".join(card(s, "../", "../stories/", stories=stories) for s in mine)
        body = f'<ul class="cards">\n    {items}\n  </ul>'
    else:
        body = f'<p class="empty">{esc(EMPTY_NOTE.get(sec, EMPTY_DEFAULT))}</p>'
    pop = "\n    ".join(
        f'<li><a href="../stories/{s["slug"]}.html">{title_text(s["title"])}</a></li>'
        for s in most_read(stories, {s["slug"] for s in mine}))
    n = len(mine)
    main = f"""<div class="home-grid">
<div class="home-main">
<h1 class="section-title">{esc(sec_label(sec))}</h1>
<p class="dek">{esc(SECTION_BLURB.get(sec, ""))} {n} {"story" if n == 1 else "stories"} so far.</p>
<section aria-labelledby="sec-latest">
  <h2 id="sec-latest" class="section-head">Latest in {esc(sec)}</h2>
  {body}
</section>
</div>
<aside class="rail" aria-labelledby="popular-heading">
  <h2 id="popular-heading" class="rail-head">{LABEL["most_read"]}</h2>
  <ol class="most-read">
    {pop}
  </ol>
</aside>
</div>
<p class="more"><a href="../stories/">{LABEL["all_link"]}</a></p>"""
    return page("../", f"{esc(sec)} | {SITE_NAME}", f"{SECTION_BLURB.get(sec, '')} Satire from {SITE_NAME}.",
                SECTION_SLUG[sec], f"Skip to {esc(sec)} stories", main, ticker_for(stories, "../"),
                social={"type": "website", "title": f"{sec} | {OG_SITE_NAME}",
                        "description": satire_desc(SECTION_BLURB.get(sec, "")),
                        "url": f"{SITE_URL}section/{SECTION_SLUG[sec]}.html",
                        "image": card_path("section", SECTION_SLUG[sec]),
                        "image_alt": section_card_alt(sec)})


def render_index(stories):
    items = "\n    ".join(card(s, "../", "", stories=stories) for s in stories) or f"<li>{EMPTY_DEFAULT}</li>"
    secs = []
    for sec in SECTIONS:
        mine = [s for s in stories if s["section"] == sec]
        if mine:
            lis = "".join(f'<li><a href="{s["slug"]}.html">{title_text(s["title"])}</a></li>' for s in mine)
            body = f'<ul>{lis}</ul>'
        else:
            body = f'<p>{esc(EMPTY_NOTE.get(sec, EMPTY_DEFAULT))}</p>'
        secs.append(f'<h3 id="{sec.lower()}"><a href="{section_href("../", sec)}">{esc(sec_label(sec))}</a></h3>\n  {body}')
    main = f"""<h1 class="section-title">{LABEL["all"]}</h1>
<p class="dek">{LABEL["index_dek"].format(n=len(stories))}</p>

<section aria-labelledby="newest-heading">
  <h2 id="newest-heading" class="section-head">{LABEL["newest"]}</h2>
  <ul class="cards">
    {items}
  </ul>
</section>

<section class="by-section" aria-labelledby="sections-heading">
  <h2 id="sections-heading" class="section-head">{LABEL["by_section"]}</h2>
  {chr(10).join(secs)}
</section>"""
    return page("../", f"All stories | {SITE_NAME}", "Every Chaotic News story, newest first.",
                "all", "Skip to stories", main, ticker_for(stories, "../"),
                social={"type": "website", "title": f"All stories | {OG_SITE_NAME}",
                        "description": "Every Chaotic News story, newest first. Satire.",
                        "url": f"{SITE_URL}stories/", "image": SITE_CARD, "image_alt": SITE_CARD_ALT})


def render_feed(stories):
    now = stories[0]["when"] if stories else dt.datetime.now(TZ)
    items = []
    for s in stories[:30]:
        url = f"{SITE_URL}stories/{s['slug']}.html"
        items.append(f"""  <item>
    <title>{esc(smart_quotes(s['title']))}</title>
    <link>{url}</link>
    <guid isPermaLink="true">{url}</guid>
    <pubDate>{format_datetime(s['when'])}</pubDate>
    <category>{esc(s['section'])}</category>
    <description>{esc(smart_quotes(s['dek']))}</description>
  </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{SITE_NAME}</title>
  <link>{SITE_URL}</link>
  <atom:link href="{SITE_URL}feed.xml" rel="self" type="application/rss+xml"/>
  <description>{TAGLINE} {SATIRE}</description>
  <language>en-us</language>
  <lastBuildDate>{format_datetime(now)}</lastBuildDate>
{chr(10).join(items)}
</channel>
</rss>
"""


def manifest(stories):
    return [{"slug": s["slug"], "title": smart_quotes(s["title"]), "dek": smart_quotes(s["dek"]),
             "date": s["when"].isoformat(), "section": s["section"], "author": s["author"],
             "url": f"{SITE_URL}stories/{s['slug']}.html", "featured": s["featured"],
             "card": card_url(card_path("story", s["slug"])), "card_alt": story_card_alt(s)}
            for s in stories]


def build_cards(stories):
    """Draw the social card PNGs (needs Pillow). Without Pillow the pages still
    build and point at the cards already in cards/."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import social_cards
    except ImportError as e:
        print(f"warning: social cards not redrawn ({e}); run: pip install pillow", file=sys.stderr)
        return
    pal = PALETTE["Breaking"]
    social_cards.draw_card(ROOT / SITE_CARD, "Breaking news that never happened.", "Top Stories",
                           pal, "site", kicker=TAGLINE)
    for sec in SECTIONS:
        social_cards.draw_card(ROOT / card_path("section", SECTION_SLUG[sec]), f"{sec} desk",
                               sec, PALETTE.get(sec, pal), "section-" + sec,
                               kicker=SECTION_BLURB.get(sec))
    keep = set()
    for s in stories:
        p = ROOT / card_path("story", s["slug"])
        keep.add(p.name)
        social_cards.draw_card(p, smart_quotes(s["title"]), s["section"],
                               PALETTE.get(s["section"], pal), s["slug"])
    for old in (ROOT / "cards" / "stories").glob("*.png"):
        if old.name not in keep:
            old.unlink()
    social_cards.draw_icons(ROOT)


SHARE_JS = '// Chaotic News share buttons. Local file, no trackers.\n// Written by tools/add_story.py (SHARE_JS); the copy messages come from each\n// button\'s data-done / data-fail, set from LABEL in the generator.\n(function () {\n  var status = document.getElementById("share-status");\n  function say(msg) {\n    if (!status) return;\n    status.textContent = msg;\n    clearTimeout(say.t);\n    say.t = setTimeout(function () { status.textContent = ""; }, 5000);\n  }\n  document.querySelectorAll("[data-copy]").forEach(function (b) {\n    if (!navigator.clipboard) return;\n    b.hidden = false;\n    b.addEventListener("click", function () {\n      navigator.clipboard.writeText(b.getAttribute("data-copy")).then(\n        function () { say(b.getAttribute("data-done") || "Link copied."); },\n        function () { say(b.getAttribute("data-fail") || "Couldn\'t copy the link."); });\n    });\n  });\n  document.querySelectorAll("[data-share]").forEach(function (b) {\n    if (!navigator.share) return;\n    b.hidden = false;\n    b.addEventListener("click", function () {\n      navigator.share({ title: b.getAttribute("data-title"), url: b.getAttribute("data-share") }).catch(function () {});\n    });\n  });\n})();\n'


def rebuild():
    stories = load_stories()
    build_cards(stories)
    STORIES.mkdir(exist_ok=True)
    keep = {f"{s['slug']}.html" for s in stories} | {"index.html"}
    for old in STORIES.glob("*.html"):
        if old.name not in keep:
            old.unlink()
    for s in stories:
        (STORIES / f"{s['slug']}.html").write_text(render_story(s, stories), encoding="utf-8")
    (STORIES / "index.html").write_text(render_index(stories), encoding="utf-8")
    sec_dir = ROOT / "section"
    sec_dir.mkdir(exist_ok=True)
    for sec in SECTIONS:
        (sec_dir / f"{SECTION_SLUG[sec]}.html").write_text(render_section(sec, stories), encoding="utf-8")
    (ROOT / "index.html").write_text(render_home(stories), encoding="utf-8")
    (ROOT / "feed.xml").write_text(render_feed(stories), encoding="utf-8")
    (ROOT / "share.js").write_text(SHARE_JS, encoding="utf-8")
    (ROOT / "stories.json").write_text(json.dumps(manifest(stories), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return stories


def add(path, replace=False):
    meta, body = load_input(path)
    for k in REQUIRED:
        if not meta.get(k):
            raise SystemExit(f"{path}: missing '{k}'")
    if meta["section"] not in SECTIONS:
        raise SystemExit(f"{path}: section must be one of {', '.join(SECTIONS)}")
    if not body.strip():
        raise SystemExit(f"{path}: story has no body")
    if meta.get("image") and not str(meta.get("image_alt", "")).strip():
        raise SystemExit(f"{path}: 'image' needs 'image_alt' (describe the picture for VoiceOver)")
    slug = slugify(meta.pop("slug", "") or meta["title"])
    meta["date"] = parse_date(meta.get("date")).isoformat()
    dest = CONTENT / f"{slug}.md"
    if dest.exists() and not replace and Path(path).resolve() != dest.resolve():
        raise SystemExit(f"{slug} already exists (use --replace to overwrite)")
    words = len(re.findall(r"\w+", body))
    if words < 200:
        print(f"warning: {slug} is only {words} words", file=sys.stderr)
    CONTENT.mkdir(exist_ok=True)
    dest.write_text(to_front_matter(meta, body), encoding="utf-8")
    return slug


def main(argv):
    replace = "--replace" in argv
    files = [a for a in argv if not a.startswith("--")]
    if not files and "--rebuild" not in argv:
        print(__doc__)
        return 1
    added = [add(f, replace) for f in files]
    stories = rebuild()
    for slug in added:
        print(f"added  stories/{slug}.html")
    print(f"built  {len(stories)} stories, stories/index.html, stories.json, feed.xml, index.html, cards/*.png")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
