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
SATIRE = "Chaotic News is satire. Some stories start from real news, but every joke is made up."
X_HANDLE = "ChaoticNewsHQ"
X_URL = f"https://x.com/{X_HANDLE}"
SECTIONS = ["Breaking", "Tech", "Gaming", "Scams", "Beats", "Weather"]
# ---- Laughable labels (Carter, 2026-10-31: "we need laughable labels").
# Rule: the real word comes FIRST, the joke after, so VoiceOver users always
# hear what a thing is before the punchline. Section slugs, URLs, the feed,
# stories.json and the card images keep the plain section names.
SECTION_LABEL = {
    "Breaking": "Breaking: Still Breaking",
    "Tech": "Tech: Beep Boop",
    "Gaming": "Gaming: Touch Grass Later",
    "Scams": "Scams: Nice Try, Steve",
    "Beats": "Beats: Turn It Up",
    "Weather": "Weather: We Guessed",
}
LABEL = {
    "home": "Top Stories (Probably)",
    "all": "All Stories (Yes, All of Them)",
    "satire_strip": "some stories are real news, every joke is made up, even this sentence",
    "live_pill": "Live on X",
    "ticker": "Breaking (Still)",
    "ticker_aria": "Breaking news, still breaking",
    "ticker_empty": "Developing story (slowly)",
    "satire_tag": "Satire, Obviously",
    "latest": "Latest (Still Warm)",
    "most_read": "Most Read (By Our Moms)",
    "more_top": "More Top Stories, Somehow",
    "sections": "Sections (Pick Your Chaos)",
    "related": "More Stories (Allegedly Related)",
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
    "Gaming": "Games, consoles, controllers and the economy of skins.",
    "Scams": "Consumer alerts from the front lines of the gift card economy.",
    "Beats": "Music, drops and things that go boom in the speakers.",
    "Weather": "Forecast: chaotic.",
}
# (start colour, end colour, accent) for each section's title-card art
PALETTE = {
    "Breaking": ("#9b0d18", "#1c0306", "#ff3b47"),
    "Tech": ("#123a8c", "#1d0b4a", "#5ab0ff"),
    "Gaming": ("#1f6b2a", "#071f0c", "#7dff8a"),
    "Scams": ("#8a5a00", "#241600", "#ffc23d"),
    "Beats": ("#7a1270", "#1e0631", "#ff6ad5"),
    "Weather": ("#04606e", "#071f33", "#5ee6d0"),
}
SHARE_TEXT = "Read on Chaotic News (satire):"


def section_href(prefix, sec):
    return f"{prefix}section/{SECTION_SLUG[sec]}.html"


LAZY = {"card": 'loading="lazy" '}


_SVG_N = __import__("itertools").count(1)


def svg_art(s, size="card", live=False):
    """Original title-card graphic for a story (no photos). Returns HTML."""
    sec = s["section"]
    c1, c2, acc = PALETTE.get(sec, PALETTE["Breaking"])
    h = zlib.crc32(s["slug"].encode())
    cx, cy = 360 + h % 220, 90 + (h >> 8) % 140
    gid = f"g{h % 100000}-{size}-{next(_SVG_N)}"  # unique per use (a story can appear twice on a page)
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
                f'{LAZY.get(size, "")}width="1280" height="720">')
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


NAV_NAME = {"Breaking": "Breaking", "Tech": "Tech", "Gaming": "Gaming", "Scams": "Scams",
            "Beats": "Beats", "Weather": "Weather"}
REPO_URL = "https://github.com/2three1y/chaoticnews"
MADE_BY_URL = "https://2three1y.github.io/"
DEFAULT_DATELINE = "SOMEWHERE ONLINE (CN)"
PHOTO_CREDIT = "Illustration: Chaotic News. Not a real photo, obviously."


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


def short_date(d):
    d = local(d)
    return f"{d.strftime('%b')} {d.day}"


def topic_label(s, prefix=None):
    """'Tech · Nov 2'. With a prefix the section name links to its section page."""
    sec = esc(s["section"])
    if prefix is not None:
        sec = f'<a href="{section_href(prefix, s["section"])}">{sec}</a>'
    return (f'<p class="topic">{sec} · <time datetime="{s["when"].isoformat()}">'
            f'{short_date(s["when"])}</time></p>')


def most_read(stories, exclude=(), n=5):
    pool = [s for s in stories if s["slug"] not in exclude] or stories
    return sorted(pool, key=lambda s: zlib.crc32(("read" + s["slug"]).encode()))[:n]


def item(s, prefix, base, heading="h3", thumb=True, dek=True):
    """One numbered story in an <ol>: headline first (so VoiceOver reads '1. Headline'),
    then the topic label, dek and picture. CSS puts the picture on the left."""
    href = f"{base}{s['slug']}.html"
    pic = f'<div class="item-pic">{art(s, prefix, "card")}</div>' if thumb else ""
    d = f'<p class="item-dek">{inline(s["dek"])}</p>' if dek else ""
    return (f'<li class="item{"" if thumb else " item-text"}"><div class="item-in">'
            f'<{heading} class="item-head"><a href="{href}">{title_text(s["title"])}</a></{heading}>'
            f'{topic_label(s)}{d}{pic}</div></li>')


def story_list(items, cls="river"):
    return f'<ol class="{cls}">\n    ' + "\n    ".join(items) + "\n  </ol>"


# ---------------------------------------------------------------- v2 design
# Round 2 (Carter, 2026-11-02 8:02 PM: "we can do better on making us look like
# [a real news] website"): dense front page, trending strip, breaking label,
# breadcrumbs, author boxes with staff bios, related cards, a fake newsletter
# block, a joke ad slot, About / Contact / Corrections pages.

STAFF = {
    "Lorraine Static": dict(slug="lorraine-static", title="Breaking News Correspondent",
        bio="Lorraine Static has covered breaking news for 22 years, 19 of them by accident. Her hair has been struck by lightning four times and was promoted twice.",
        alt="Cartoon headshot of Lorraine Static: a news anchor with huge sprayed blonde hair crackling with static sparks, a red blazer and a microphone."),
    "Penny Popup": dict(slug="penny-popup", title="Consumer Affairs Correspondent",
        bio="Penny Popup has investigated 3,000 scams and fallen for none of them, except one free cruise, which she maintains was real and is still waiting to board.",
        alt="Cartoon headshot of Penny Popup: a reporter with big round glasses and a brown bob, squinting suspiciously through a magnifying glass."),
    "Gary Breakingnews": dict(slug="gary-breakingnews", title="Scams Desk",
        bio="Gary legally changed his last name in 2019 to seem more credible. It did not work. He covers scams, bots and anyone who asks for payment in gift cards.",
        alt="Cartoon headshot of Gary Breakingnews: a sweaty, alarmed reporter with a giant bushy mustache, a fedora with a press card and a trench coat."),
    "Hank Unverified": dict(slug="hank-unverified", title="Senior Field Reporter",
        bio="Hank Unverified has never confirmed a single fact and is proud of that record. He files every story from the field, which is usually an actual field.",
        alt="Cartoon headshot of Hank Unverified: an older reporter with gray stubble in a wet windbreaker, holding a notepad and shrugging doubtfully."),
    "Dex Voltage": dict(slug="dex-voltage", title="Technology Editor",
        bio="Dex Voltage owns 11 phones and charges none of them. He has been asked to leave three electronics stores for \u201casking too many follow-up questions.\u201d",
        alt="Cartoon headshot of Dex Voltage: a grinning tech editor with spiky electric-blue hair, a hoodie and VR goggles pushed up on his forehead."),
    "Trent Respawn": dict(slug="trent-respawn", title="Gaming Editor",
        bio="Trent Respawn has 4,000 hours in a farming game and still cannot find the carrots. He reviews games, controllers and the snacks you eat near them.",
        alt="Cartoon headshot of Trent Respawn: a sleepy gaming editor in a big headset and backwards cap, holding a controller with a smug smile."),
    "Marge Bandwidth": dict(slug="marge-bandwidth", title="Home & Family Tech Correspondent",
        bio="Marge Bandwidth is the unpaid IT department for 14 relatives. Her fix for every problem is unplugging it for 30 seconds, which she says works 100% of the time.",
        alt="Cartoon headshot of Marge Bandwidth: a cheerful woman with curly red hair holding a Wi-Fi router up like a trophy, cables draped over her shoulders."),
}
STAFF_DEFAULT = dict(slug="", title="Staff",
    bio="Chaotic News Network Staff is a team of reporters who all claim somebody else wrote this.", alt="")

ADS = [
    dict(img="images/ads/router-gold.jpg",
         alt="Cartoon ad picture: a shiny golden Wi-Fi router on a velvet pillow under a museum spotlight, with a tiny family staring at it in awe.",
         head="RouterMax Gold\u2122: Wi-Fi So Strong It Reaches Your Grandma\u2019s House",
         copy="Six bars. Phones only show five. Now you\u2019ll never know what the sixth one does.",
         cta="Learn More (There Is No More)"),
    dict(img="images/ads/skip-button.jpg",
         alt="Cartoon ad picture: a teenager slamming a giant red button on a pedestal while a pile of homework vanishes in a puff of smoke and confetti.",
         head="The SKIP Button\u2122. Skips Homework, Chores and \u201cWe Need to Talk.\u201d",
         copy="Not sold in stores. Or anywhere. Side effects include: still having homework.",
         cta="Order Now (You Can\u2019t)"),
]

TRENDING = [
    ("Clocky the Agentic Clock", "local-agentic-clock-says-task-will-be-done-in-2-minutes-has-said-so-since-tuesday"),
    ("Big D Randy", "big-d-randy-takes-out-local-ai"),
    ("Steve From Microsoft", "steve-from-microsoft-asks-supervisor-also-named-steve"),
    ("V-Bucks Crash", "v-bucks-freefall-as-item-shop-goes-free"),
    ("Kyle\u2019s Slide", "modders-finish-decade-long-project-group-project-waiting-on-kyles-slide"),
    ("CarPlay", "man-swaps-four-cables-carplay-connects-in-driveway"),
    ("Pikmin Day", "pikmin-get-national-holiday-before-teen-gets-birthday-off"),
    ("Bulgeet & Bibi", "bulgeet-bibi-website-zero-working-buttons"),
]

BUILD_TIME = dt.datetime.now(TZ).replace(second=0, microsecond=0)


def staff(name):
    return STAFF.get(name, dict(STAFF_DEFAULT, title=""))


def headshot(name, prefix, cls="headshot", size=96, short=False):
    st = STAFF.get(name)
    if not st:
        return f'<span class="{cls} headshot-none" aria-hidden="true">CN</span>'
    return (f'<img class="{cls}" src="{prefix}images/staff/{st["slug"]}.jpg" alt="{esc("Cartoon headshot of " + name) if short else esc(st["alt"])}" '
            f'width="{size}" height="{size}" loading="lazy">')


def ago_tag(d, word="Updated"):
    """Static text a reader can trust, refreshed by site.js to 'Updated 12 min ago'."""
    d = local(d)
    txt = f"{word} {short_time(d)}, {d.strftime('%b')} {d.day}, {d.year}"
    return f'<time class="ago" datetime="{d.isoformat()}" data-ago="{word}">{txt}</time>'


LAZY_ATTR = 'loading="lazy" '


def pic(s, prefix, cls="pic", lazy=True):
    if s.get("image"):
        return (f'<img class="{cls}" src="{prefix}{esc(s["image"])}" alt="{esc(s["image_alt"])}" '
                + (LAZY_ATTR if lazy else "") + 'width="1280" height="720">')
    return art(s, prefix, "card")


def ad_slot(prefix, n=0, idn="ad"):
    a = ADS[n % len(ADS)]
    return f"""<aside class="ad" aria-labelledby="{idn}-label">
  <p class="ad-label" id="{idn}-label">Advertisement</p>
  <div class="ad-body">
    <img src="{prefix}{a["img"]}" alt="{esc(a["alt"])}" width="640" height="480" loading="lazy">
    <p class="ad-head">{esc(a["head"])}</p>
    <p class="ad-copy">{esc(a["copy"])}</p>
    <p class="ad-cta">{esc(a["cta"])}</p>
    <p class="ad-fine">Fake ad. Chaotic News is satire and sells nothing.</p>
  </div>
</aside>"""


def newsletter(idn="nl"):
    return f"""<section class="newsletter" aria-labelledby="{idn}-head">
  <div class="nl-in">
    <p class="nl-kicker">Newsletter</p>
    <h2 id="{idn}-head" class="nl-head">The Daily Chaos</h2>
    <p class="nl-dek">The day\u2019s most made-up headlines, delivered to your inbox never. Join 0 readers who have already not signed up.</p>
    <p class="nl-row"><button type="button" class="nl-btn" data-nl="Gotcha. There is no newsletter, this is a satire site. Your inbox is safe. For now.">Sign Me Up</button></p>
    <p class="nl-status" role="status"></p>
    <p class="nl-fine">No email needed, none collected. Chaotic News is satire.</p>
  </div>
</section>"""


def trending_strip(stories, prefix):
    have = {s["slug"] for s in stories}
    items = "".join(f'<li><a href="{prefix}stories/{slug}.html">{esc(lbl)}</a></li>'
                    for lbl, slug in TRENDING if slug in have)
    return f"""  <div class="trending" role="region" aria-labelledby="trending-label">
    <div class="wrap trending-in">
      <p class="trending-label" id="trending-label">Trending</p>
      <ul>{items}</ul>
    </div>
  </div>"""


def ticker_for(stories, prefix):
    """Breaking bar: a red label and the newest headline. Static (never moves)."""
    if not stories:
        return ""
    s = stories[0]
    return f"""  <div class="breaking" role="region" aria-labelledby="breaking-label">
    <div class="wrap breaking-in">
      <p class="breaking-label" id="breaking-label"><span class="pulse" aria-hidden="true"></span>Breaking</p>
      <p class="breaking-head"><a href="{prefix}stories/{s["slug"]}.html">{title_text(s["title"])}</a></p>
    </div>
  </div>
{trending_strip(stories, prefix)}"""


def page(prefix, title, description, current, skip_label, main_html, ticker, scripts="", social=None, count=None):
    home = f"{prefix}./" if prefix else "./"
    nav = [("Home", home, "home")]
    for sec in SECTIONS:
        nav.append((NAV_NAME.get(sec, sec), section_href(prefix, sec), SECTION_SLUG[sec]))
    nav.append(("All Stories", f"{prefix}stories/", "all"))
    cur = ' aria-current="page"'
    items = "\n".join(
        f'      <li><a href="{href}"{cur if key == current else ""}>{esc(label)}</a></li>'
        for label, href, key in nav)
    foot_secs = "\n".join(
        f'        <li><a href="{section_href(prefix, sec)}">{esc(sec_label(sec))}</a></li>' for sec in SECTIONS)
    now = dt.datetime.now(TZ)
    today = f"{now.strftime('%A, %B')} {now.day}, {now.year}"
    issue = f"Vol. 1, No. {count}" if count else "Vol. 1"
    return f"""<!DOCTYPE html>
<html lang="en-US">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{esc(description)}">
<meta name="theme-color" content="#cc0a17">
{social_head(prefix, social)}
<link rel="stylesheet" href="{prefix}style.css">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="{prefix}feed.xml">
</head>
<body>
<a class="skip" href="#main">{skip_label}</a>
<header class="site">
  <div class="topbar">
    <div class="wrap topbar-in">
      <p class="today"><time id="today" datetime="{now.date().isoformat()}">{today}</time></p>
      <p class="edition">U.S. Edition · {issue} · Est. Last Thursday</p>
      <p class="topbar-x"><a href="{X_URL}" rel="me">{LABEL["live_pill"]}: @{X_HANDLE}</a></p>
    </div>
  </div>
  <div class="mast">
    <div class="wrap mast-in">
      <p class="brand"><span class="bug" aria-hidden="true">CN</span><a class="wordmark" href="{home}">Chaotic News</a></p>
      <p class="tagline">{TAGLINE}</p>
      <p class="satire-strip"><strong>Satire:</strong> {LABEL["satire_strip"]}</p>
    </div>
  </div>
  <nav class="sections" aria-label="Sections">
    <ul class="wrap">
{items}
    </ul>
  </nav>
{ticker}
</header>

<main id="main" class="wrap">
{main_html}
</main>

<footer class="site-foot">
  <div class="wrap foot-in">
    <div class="foot-col foot-about">
      <p class="foot-brand"><span class="bug bug-sm" aria-hidden="true">CN</span> <span>{SITE_NAME}</span></p>
      <p class="foot-tag">{TAGLINE}</p>
      <p class="foot-satire"><strong>Satire.</strong> {SATIRE} {LABEL["foot_satire"]}</p>
    </div>
    <nav class="foot-col" aria-label="Sections, footer">
      <h2 class="foot-head">Sections</h2>
      <ul>
        <li><a href="{home}">{LABEL["home"]}</a></li>
{foot_secs}
        <li><a href="{prefix}stories/">{LABEL["all"]}</a></li>
      </ul>
    </nav>
    <nav class="foot-col" aria-label="Company">
      <h2 class="foot-head">Company</h2>
      <ul>
        <li><a href="{prefix}about.html">About Us (Allegedly)</a></li>
        <li><a href="{prefix}about.html#staff">Our Staff</a></li>
        <li><a href="{prefix}contact.html">Contact (We Might Answer)</a></li>
        <li><a href="{prefix}corrections.html">Corrections (We Have Never Been Wrong)</a></li>
      </ul>
    </nav>
    <div class="foot-col">
      <h2 class="foot-head">Follow and More</h2>
      <ul>
        <li><a href="{X_URL}" rel="me">{esc(LABEL["foot_x"].format(h=X_HANDLE))}</a></li>
        <li><a href="{prefix}feed.xml">{LABEL["rss"]}</a></li>
        <li><a href="{prefix}stories.json">{LABEL["json"]}</a></li>
        <li><a href="{REPO_URL}">View on GitHub</a></li>
        <!-- YouTube channel link goes here (no channel link yet) -->
      </ul>
    </div>
  </div>
  <div class="wrap foot-base">
    <p class="credit">{LABEL["credit"]} · <a href="{MADE_BY_URL}">Made by Chaotic Carter</a></p>
    <p class="copy">© {now.year} {SITE_NAME}. All rights reserved, none of it real.</p>
  </div>
</footer>
<script src="{prefix}site.js"></script>{scripts}
</body>
</html>
"""


def rail_most_read(stories, prefix_base, exclude=()):
    pop = "\n    ".join(
        f'<li><a href="{prefix_base}{o["slug"]}.html">{title_text(o["title"])}</a>{topic_label(o)}</li>'
        for o in most_read(stories, exclude))
    return f"""<section class="rail-box" aria-labelledby="popular-heading">
  <h2 id="popular-heading" class="rail-head">{LABEL["most_read"]}</h2>
  <ol class="most-read">
    {pop}
  </ol>
</section>"""


def card(s, prefix, base, heading="h3", size="sm", dek=False, by=False):
    """One numbered story card (<li>): headline first, then topic, dek, byline, picture."""
    href = f"{base}{s['slug']}.html"
    d = f'<p class="card-dek">{inline(s["dek"])}</p>' if dek else ""
    b = f'<p class="card-by">By {esc(s["author"])}</p>' if by else ""
    return (f'<li class="card card-{size}"><div class="card-in">'
            f'<{heading} class="card-head"><a href="{href}">{title_text(s["title"])}</a></{heading}>'
            f'{topic_label(s)}{d}{b}<div class="card-pic">{pic(s, prefix)}</div></div></li>')


def headline_item(s, base):
    return f'<li><a href="{base}{s["slug"]}.html">{title_text(s["title"])}</a>{topic_label(s)}</li>'


def body_html(s):
    return markdown(s['body'], s.get('dateline') or DEFAULT_DATELINE)


# ---- Reply stories (Carter, 2026-11-03: "We reply and our replies become stories
# lol and we could embed our tweets. We could also tell the actual news in a
# chaotic way.") A story with `x_post:` in its front matter is a reply story:
# the news part is REAL and sourced, the jokes are ours. It gets its own note
# (instead of "all stories are made up"), our post embedded with X's standard
# blockquote (a plain readable link if X's script doesn't load), and a
# "where the real news came from" list with the source and the post we replied to.
# Front matter: x_post, x_post_text, x_post_date, x_replied_to (@handle),
# x_replied_to_url, source_url, source_title, source_outlet,
# optional source2_url, source2_title, source2_outlet.
X_WIDGET = '\n<script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>'
REPLY_NOTE = ("Real news, chaotic voice. The news in this story is real, and the source is linked at the bottom. "
              "The jokes, the \u201carea man\u201d and anything he says are made up by us. This started as our reply on X.")


def satire_note(s):
    if s.get("x_post"):
        return f'<p class="satire-note"><strong>Reply Story.</strong> {REPLY_NOTE}</p>'
    return f'<p class="satire-note"><strong>{LABEL["satire_tag"]}.</strong> {SATIRE} {LABEL["story_satire"]}</p>'


def x_reply_block(s):
    if not s.get("x_post"):
        return ""
    who = s.get("x_replied_to", "").lstrip("@")
    srcs = []
    for n in ("", "2"):
        u = s.get(f"source{n}_url")
        if u:
            outlet = s.get(f"source{n}_outlet", "")
            srcs.append(f'<li>The real story: <a href="{esc(u)}">{esc(smart_quotes(s.get(f"source{n}_title", u)))}</a>'
                        f'{f" ({esc(outlet)})" if outlet else ""}</li>')
    if s.get("x_replied_to_url"):
        srcs.append(f'<li>The post we replied to: <a href="{esc(s["x_replied_to_url"])}">@{esc(who)} on X</a></li>')
    srcs.append(f'<li>Our reply: <a href="{esc(s["x_post"])}">@{X_HANDLE} on X</a></li>')
    tweet_url = s["x_post"].replace("https://x.com/", "https://twitter.com/")
    return f"""
  <section class="x-reply" aria-labelledby="x-reply-heading">
    <h2 id="x-reply-heading" class="x-reply-head">Our Reply on X</h2>
    <blockquote class="twitter-tweet" data-dnt="true" data-conversation="none"><p lang="en" dir="ltr">{esc(s.get("x_post_text", ""))}</p>&mdash; Chaotic News (@{X_HANDLE}) <a href="{esc(tweet_url)}">{esc(s.get("x_post_date", ""))}</a></blockquote>
  </section>
  <section class="x-sources" aria-labelledby="x-sources-heading">
    <h2 id="x-sources-heading" class="x-reply-head">Where the Real News Came From</h2>
    <ul>
      {"".join(srcs)}
    </ul>
  </section>"""


def render_story(s, stories):
    same = [o for o in stories if o["slug"] != s["slug"] and o["section"] == s["section"]]
    other = [o for o in stories if o["slug"] != s["slug"] and o["section"] != s["section"]]
    rel = (same[:3] + other)[:4]
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
    st = staff(s["author"])
    atitle = s.get("author_title") or st["title"]
    sec = s["section"]
    caption = f'<figcaption>{PHOTO_CREDIT}</figcaption>' if s.get("image") else ""
    more_link = (f'<p class="author-more"><a href="../about.html#{st["slug"]}">More about {esc(s["author"])}</a></p>'
                 if st.get("slug") else "")
    main = f"""<nav class="crumbs" aria-label="Breadcrumb">
  <ol>
    <li><a href="../">Home</a></li>
    <li><span class="sep" aria-hidden="true">›</span><a href="{section_href('../', sec)}">{esc(sec)}</a></li>
  </ol>
</nav>
<div class="story-wrap">
<article class="story">
  {topic_label(s, '../')}
  <h1>{title_text(s['title'])}</h1>
  <p class="dek">{inline(s['dek'])}</p>
  <div class="byline">
    {headshot(s["author"], "../", "byline-face", 48, short=True)}
    <div class="byline-text">
      <p class="by">By <span class="author">{esc(s["author"])}</span>{f', <span class="author-title">{esc(atitle)}</span>' if atitle else ''}</p>
      <p class="when">{ago_tag(upd)} · Published {short_date(s["when"])} · {read_label(read_minutes(s))}</p>
    </div>
  </div>
  <div class="share share-top">
    <p class="share-label">Share</p>
    <ul>
      <li><a class="share-btn" href="{esc(x_share)}">Post on X</a></li>
      <li><a class="share-btn" href="{esc(mail)}">Email</a></li>
      <li><button type="button" class="share-btn" data-copy="{esc(url)}" data-done="{esc(LABEL['copied'])}" data-fail="{esc(LABEL['copy_fail'])}" hidden>Copy Link</button></li>
    </ul>
  </div>
  <figure class="hero-art">{pic(s, '../', 'pic', lazy=False)}{caption}</figure>
  {satire_note(s)}
  <div class="body">
  {body_html(s)}{corr}
  </div>{x_reply_block(s)}
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
  <section class="author-box" aria-labelledby="author-heading">
    {headshot(s["author"], "../", "author-face", 96)}
    <div class="author-text">
      <h2 id="author-heading" class="author-head">About the Author: {esc(s["author"])}</h2>
      <p class="author-role">{esc(atitle)}</p>
      <p class="author-bio">{esc(st["bio"])}</p>
      {more_link}
    </div>
  </section>
</article>

<aside class="rail" aria-label="More from Chaotic News">
{rail_most_read(stories, "", {s["slug"]})}
{ad_slot("../", zlib.crc32(s["slug"].encode()) % 2, "ad-rail")}
</aside>
</div>

<section class="related" aria-labelledby="related-heading">
  <h2 id="related-heading" class="section-head">{LABEL["related"]}</h2>
  <ol class="cards cards-4">
    {"".join(card(o, "../", "") for o in rel)}
  </ol>
  <p class="more"><a href="./">{LABEL["all_link"]}</a></p>
</section>
{newsletter()}"""
    social = {"type": "article", "title": plain_title, "description": satire_desc(s["dek"]),
              "url": url, "image": card_path("story", s["slug"]), "image_alt": story_card_alt(s),
              "published": s["when"].isoformat(), "modified": upd.isoformat(),
              "section": s["section"], "author": s["author"]}
    return page("../", f"{title_text(s['title'])} | {SITE_NAME}", f"{smart_quotes(s['dek'])} Satire from {SITE_NAME}.",
                SECTION_SLUG[s["section"]], "Skip to story", main, ticker_for(stories, "../"),
                '\n<script src="../share.js"></script>' + (X_WIDGET if s.get("x_post") else ""), social, len(stories))


HOME_SOCIAL = {"type": "website", "title": f"{OG_SITE_NAME}: {TAGLINE}",
               "description": "Breaking news that never happened, plus real news told chaotic. Every joke is made up. Satire.",
               "url": SITE_URL, "image": SITE_CARD, "image_alt": SITE_CARD_ALT}


def pick_lead(stories):
    feat = [s for s in stories if s.get("featured")]
    return (feat or stories)[0]


def render_home(stories):
    if not stories:
        main = f'<h1 class="page-head">{LABEL["home"]}</h1>\n<p>{EMPTY_DEFAULT}</p>'
        return page("", f"{SITE_NAME}", TAGLINE, "home", "Skip to top stories", main, ticker_for(stories, ""), social=HOME_SOCIAL)
    lead = stories[0]
    rest = [s for s in stories if s is not lead]
    second = rest[:3]                 # with pictures, left column
    heads = rest[3:11]                # headline-only, right column
    lead_related = [s for s in rest if s["section"] == lead["section"]][:3] or rest[:3]
    top_row = rest[11:15] if len(rest) > 11 else rest[:4]
    blocks = []
    for n, sec in enumerate(SECTIONS):
        mine = [s for s in stories if s["section"] == sec]
        hid = f"sec-{SECTION_SLUG[sec]}"
        if len(mine) == 1:
            body = f"""<ol class="river">
    {card(mine[0], "", "stories/", "h3", "row", dek=True, by=True)}
  </ol>"""
            more = (f'<p class="more"><a href="{section_href("", sec)}">More {esc(sec)} stories '
                    f'(1 in all, but it is a good one)</a></p>')
        elif mine:
            big, small = mine[0], mine[1:5]
            body = f"""<ol class="sec-grid">
    {card(big, "", "stories/", "h3", "lg", dek=True, by=True)}
    {"".join(card(s, "", "stories/", "h3", "sm") for s in small)}
  </ol>"""
            more = (f'<p class="more"><a href="{section_href("", sec)}">More {esc(sec)} stories '
                    f'({len(mine)} in all)</a></p>')
        else:
            body = f'<p class="empty">{esc(EMPTY_NOTE.get(sec, EMPTY_DEFAULT))}</p>'
            more = f'<p class="more"><a href="{section_href("", sec)}">Go to {esc(sec)}</a></p>'
        blocks.append(f"""<section class="sec-block" aria-labelledby="{hid}">
  <h2 id="{hid}" class="section-head"><a href="{section_href("", sec)}">{esc(sec_label(sec))}</a></h2>
  {body}
  {more}
</section>""")
        if n == 1:
            blocks.append(newsletter())
        if n == 3:
            blocks.append(f'<div class="ad-wide">{ad_slot("", 1, "ad-mid")}</div>')
    rel_html = "".join(f'<li><a href="stories/{s["slug"]}.html">{title_text(s["title"])}</a></li>' for s in lead_related)
    main = f"""<h1 class="page-head">{LABEL["home"]}</h1>
<div class="front">
<article class="front-lead">
  <figure class="lead-pic">{pic(lead, "", "pic", lazy=False)}</figure>
  {topic_label(lead)}
  <h2 class="lead-head"><a href="stories/{lead["slug"]}.html">{title_text(lead["title"])}</a></h2>
  <p class="lead-dek">{inline(lead["dek"])}</p>
  <p class="lead-by">By {esc(lead["author"])} · {ago_tag(lead["when"], "Updated")}</p>
  <ul class="lead-related" aria-label="Related coverage">{rel_html}</ul>
</article>
<section class="front-second" aria-labelledby="second-heading">
  <h2 id="second-heading" class="col-head">{LABEL["more_top"]}</h2>
  <ol class="cards cards-stack">
    {"".join(card(s, "", "stories/", "h3", "md") for s in second)}
  </ol>
</section>
<section class="front-heads" aria-labelledby="latest-heading">
  <h2 id="latest-heading" class="col-head">{LABEL["latest"]}</h2>
  <ol class="latest">
    {"".join(headline_item(s, "stories/") for s in heads)}
  </ol>
  <p class="more"><a href="stories/">{LABEL["all_link"]}</a></p>
  {ad_slot("", 0, "ad-top")}
</section>
</div>

<section class="top-row" aria-labelledby="row-heading">
  <h2 id="row-heading" class="section-head">Don\u2019t Miss (Seriously, Don\u2019t)</h2>
  <ol class="cards cards-4">
    {"".join(card(s, "", "stories/", "h3", "sm") for s in top_row)}
  </ol>
</section>

{chr(10).join(blocks)}

<div class="bottom-rail">
{rail_most_read(stories, "stories/", {lead["slug"]})}
</div>"""
    return page("", f"{SITE_NAME}: {TAGLINE}", f"Satire news, updated daily. Latest: {smart_quotes(lead['title'])}",
                "home", "Skip to top stories", main, ticker_for(stories, ""), social=HOME_SOCIAL, count=len(stories))


def render_section(sec, stories):
    mine = [s for s in stories if s["section"] == sec]
    n = len(mine)
    if mine:
        lead, rest = mine[0], mine[1:]
        lead_html = f"""<article class="sec-lead">
  <figure class="lead-pic">{pic(lead, "../", "pic", lazy=False)}</figure>
  <div class="sec-lead-text">
    {topic_label(lead)}
    <h2 class="lead-head"><a href="../stories/{lead["slug"]}.html">{title_text(lead["title"])}</a></h2>
    <p class="lead-dek">{inline(lead["dek"])}</p>
    <p class="lead-by">By {esc(lead["author"])} · {ago_tag(lead["when"], "Updated")}</p>
  </div>
</article>"""
        rest_html = (f"""<section aria-labelledby="sec-latest">
  <h2 id="sec-latest" class="section-head">More in {esc(sec)}</h2>
  <ol class="river" start="2">
    {"".join(card(s, "../", "../stories/", "h3", "row", dek=True, by=True) for s in rest)}
  </ol>
</section>""" if rest else "")
        body = lead_html + "\n" + rest_html
    else:
        others = stories[:5]
        body = (f'<p class="empty">{esc(EMPTY_NOTE.get(sec, EMPTY_DEFAULT))}</p>\n'
                f'<section aria-labelledby="sec-latest"><h2 id="sec-latest" class="section-head">Meanwhile, Elsewhere in the Chaos</h2>'
                f'<ol class="river">{"".join(card(s, "../", "../stories/", "h3", "row", dek=True) for s in others)}</ol></section>')
    main = f"""<nav class="crumbs" aria-label="Breadcrumb">
  <ol>
    <li><a href="../">Home</a></li>
    <li><span class="sep" aria-hidden="true">›</span><a href="{section_href('../', sec)}" aria-current="page">{esc(sec)}</a></li>
  </ol>
</nav>
<div class="sec-front-head">
<h1 class="section-title">{esc(sec_label(sec))}</h1>
<p class="section-dek">{esc(SECTION_BLURB.get(sec, ""))} {n} {"story" if n == 1 else "stories"} so far.</p>
</div>
<div class="page-grid">
<div class="page-main">
{body}
<p class="more"><a href="../stories/">{LABEL["all_link"]}</a></p>
</div>
<aside class="rail" aria-label="More from Chaotic News">
{rail_most_read(stories, "../stories/", {s["slug"] for s in mine})}
{ad_slot("../", SECTIONS.index(sec), "ad-rail")}
</aside>
</div>
{newsletter()}"""
    return page("../", f"{esc(sec)} | {SITE_NAME}", f"{SECTION_BLURB.get(sec, '')} Satire from {SITE_NAME}.",
                SECTION_SLUG[sec], f"Skip to {esc(sec)} stories", main, ticker_for(stories, "../"),
                social={"type": "website", "title": f"{sec} | {OG_SITE_NAME}",
                        "description": satire_desc(SECTION_BLURB.get(sec, "")),
                        "url": f"{SITE_URL}section/{SECTION_SLUG[sec]}.html",
                        "image": card_path("section", SECTION_SLUG[sec]),
                        "image_alt": section_card_alt(sec)}, count=len(stories))


def render_index(stories):
    items = (f'<ol class="river">{"".join(card(s, "../", "", "h3", "row", dek=True, by=True) for s in stories)}</ol>'
             if stories else f"<p>{EMPTY_DEFAULT}</p>")
    secs = []
    for sec in SECTIONS:
        mine = [s for s in stories if s["section"] == sec]
        if mine:
            lis = "".join(f'<li><a href="{s["slug"]}.html">{title_text(s["title"])}</a>{topic_label(s)}</li>' for s in mine)
            body = f'<ol class="latest">{lis}</ol>'
        else:
            body = f'<p class="empty">{esc(EMPTY_NOTE.get(sec, EMPTY_DEFAULT))}</p>'
        secs.append(f'<div class="by-sec"><h3 id="{sec.lower()}" class="sub-head"><a href="{section_href("../", sec)}">{esc(sec_label(sec))}</a></h3>\n  {body}</div>')
    main = f"""<nav class="crumbs" aria-label="Breadcrumb">
  <ol>
    <li><a href="../">Home</a></li>
    <li><span class="sep" aria-hidden="true">›</span><a href="./" aria-current="page">All Stories</a></li>
  </ol>
</nav>
<div class="sec-front-head">
<h1 class="section-title">{LABEL["all"]}</h1>
<p class="section-dek">{LABEL["index_dek"].format(n=len(stories))}</p>
</div>
<div class="page-grid">
<div class="page-main">
<section aria-labelledby="newest-heading">
  <h2 id="newest-heading" class="section-head">{LABEL["newest"]}</h2>
  {items}
</section>
</div>
<aside class="rail" aria-label="More from Chaotic News">
{ad_slot("../", 0, "ad-rail")}
</aside>
</div>
<section class="by-section" aria-labelledby="sections-heading">
  <h2 id="sections-heading" class="section-head">{LABEL["by_section"]}</h2>
  <div class="by-sec-grid">
  {chr(10).join(secs)}
  </div>
</section>"""
    return page("../", f"All stories | {SITE_NAME}", "Every Chaotic News story, newest first.",
                "all", "Skip to stories", main, ticker_for(stories, "../"),
                social={"type": "website", "title": f"All stories | {OG_SITE_NAME}",
                        "description": "Every Chaotic News story, newest first. Satire.",
                        "url": f"{SITE_URL}stories/", "image": SITE_CARD, "image_alt": SITE_CARD_ALT}, count=len(stories))


def info_page(stories, slug, title, h1, dek, inner):
    main = f"""<nav class="crumbs" aria-label="Breadcrumb">
  <ol>
    <li><a href="./">Home</a></li>
    <li><span class="sep" aria-hidden="true">›</span><a href="{slug}.html" aria-current="page">{esc(title)}</a></li>
  </ol>
</nav>
<div class="info">
<h1 class="section-title">{esc(h1)}</h1>
<p class="section-dek">{dek}</p>
{inner}
</div>"""
    return page("", f"{esc(title)} | {SITE_NAME}", f"{title}. Satire from {SITE_NAME}.", slug,
                "Skip to content", main, ticker_for(stories, ""),
                social={"type": "website", "title": f"{title} | {OG_SITE_NAME}",
                        "description": f"{title}. Every Chaotic News story is made up. Satire.",
                        "url": f"{SITE_URL}{slug}.html", "image": SITE_CARD, "image_alt": SITE_CARD_ALT},
                count=len(stories))


def render_about(stories):
    people = []
    for name, st in STAFF.items():
        mine = [s for s in stories if s["author"] == name][:3]
        lis = "".join(f'<li><a href="stories/{s["slug"]}.html">{title_text(s["title"])}</a></li>' for s in mine)
        recent = f'<p class="staff-recent-label">Recent stories:</p><ul class="staff-recent">{lis}</ul>' if lis else ""
        people.append(f"""<li class="staff-card" id="{st["slug"]}">
    {headshot(name, "", "staff-face", 120)}
    <div class="staff-text">
      <h3 class="staff-name">{esc(name)}</h3>
      <p class="staff-role">{esc(st["title"])}</p>
      <p class="staff-bio">{esc(st["bio"])}</p>
      {recent}
    </div>
  </li>""")
    inner = f"""<h2 class="section-head">Our Mission</h2>
<p>Chaotic News Network was founded last Thursday with one goal: to report the news before it happens, and, where possible, instead of it happening. We are a satire site. Every story, quote, expert, statistic and correction on this website is made up.</p>
<p>Our newsroom runs on three principles: be first, be loud, and if anyone asks, it was Steve.</p>
<h2 class="section-head">Our Standards</h2>
<ol class="standards">
  <li>Every story is checked by at least zero fact-checkers.</li>
  <li>All anonymous sources are named Steve, for consistency.</li>
  <li>We never accept money from advertisers, mostly because none have asked.</li>
  <li>If a headline sounds true, we apologize. That was an accident.</li>
</ol>
<h2 class="section-head" id="staff">Our Staff</h2>
<ul class="staff">
  {"".join(people)}
</ul>
<p>Chaotic News is made by <a href="{MADE_BY_URL}">Chaotic Carter</a>.</p>"""
    return info_page(stories, "about", "About Us", "About Chaotic News",
                     "Unbiased. Unverified. Unhinged. Serving readers since last Thursday.", inner)


def render_contact(stories):
    inner = f"""<h2 class="section-head">Send Us a Tip</h2>
<p>Seen something chaotic? The fastest way to reach the newsroom is a message to <a href="{X_URL}" rel="me">@{X_HANDLE} on X</a>. Our tips desk reads every message, usually out loud, usually to each other.</p>
<h2 class="section-head">Departments</h2>
<ul class="dept">
  <li><strong>Newsroom:</strong> open 24 hours a day, closed for lunch 23 of them.</li>
  <li><strong>Corrections:</strong> please see our <a href="corrections.html">Corrections page</a>. Short version: no.</li>
  <li><strong>Advertising:</strong> our ads are fake. If you want to buy one, that is also fake.</li>
  <li><strong>Customer service:</strong> transferred to Steve. Please hold. The hold music is a fax machine.</li>
</ul>
<h2 class="section-head">Mailing Address</h2>
<p>Chaotic News Network, Third Basement Down, The Group Chat, Somewhere Online. Please do not mail us anything. We will lose it.</p>"""
    return info_page(stories, "contact", "Contact", "Contact Chaotic News",
                     "We would love to hear from you. Within reason. Not right now, though.", inner)


def render_corrections(stories):
    inner = """<h2 class="section-head">Corrections Policy</h2>
<p class="big-claim">We have never been wrong.</p>
<p>Chaotic News holds itself to the highest standard of accuracy, which is why we have never published a correction. Below is a complete list of every mistake we have ever made.</p>
<h2 class="section-head">Recent Corrections</h2>
<ol class="corrections">
  <li><strong>Nov 2:</strong> An earlier version of every story was too short. Chaotic News regrets nothing, but we made them longer anyway.</li>
  <li><strong>Nov 1:</strong> A previous story said Steve from Microsoft works at Microsoft. He does not. Neither do any of the other Steves.</li>
  <li><strong>Oct 31:</strong> We incorrectly reported that Big D Randy\u2019s name crashed one AI. It crashed four. We apologize to the other three.</li>
  <li><strong>Oct 30:</strong> We were not wrong about anything. This line is here so the list looks official.</li>
</ol>
<p class="fine">Spotted an error? <a href="contact.html">Contact us</a>, and our Corrections Desk will look at it, laugh, and file it under \u201cnot an error.\u201d</p>"""
    return info_page(stories, "corrections", "Corrections", "Corrections",
                     "Accountability is important to us. That is why we have this page.", inner)



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


SITE_JS = ("// Chaotic News: today's date, 'Updated 12 min ago' times, the fake newsletter button.\n"
           "// Local file, no trackers. Written by tools/add_story.py (SITE_JS).\n"
           '(function () {\n'
           '  var t = document.getElementById("today");\n'
           '  if (t && Date.prototype.toLocaleDateString) {\n'
           '    var d = new Date();\n'
           '    t.textContent = d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });\n'
           '    t.setAttribute("datetime", d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"));\n'
           '  }\n'
           '  function ago(iso) {\n'
           '    var m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);\n'
           '    if (isNaN(m)) return null;\n'
           '    if (m < 1) return "just now";\n'
           '    if (m < 60) return m + " min ago";\n'
           '    var h = Math.floor(m / 60);\n'
           '    if (h < 24) return h + (h === 1 ? " hour ago" : " hours ago");\n'
           '    var dd = Math.floor(h / 24);\n'
           '    return dd + (dd === 1 ? " day ago" : " days ago");\n'
           '  }\n'
           '  document.querySelectorAll("time[data-ago]").forEach(function (el) {\n'
           '    var a = ago(el.getAttribute("datetime"));\n'
           '    if (a) el.textContent = el.getAttribute("data-ago") + " " + a;\n'
           '  });\n'
           '  document.querySelectorAll("[data-nl]").forEach(function (b) {\n'
           '    b.addEventListener("click", function () {\n'
           '      var box = b.closest(".newsletter");\n'
           '      var st = box && box.querySelector(".nl-status");\n'
           '      if (st) st.textContent = b.getAttribute("data-nl");\n'
           '    });\n'
           '  });\n'
           '})();\n')

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
    (ROOT / "about.html").write_text(render_about(stories), encoding="utf-8")
    (ROOT / "contact.html").write_text(render_contact(stories), encoding="utf-8")
    (ROOT / "corrections.html").write_text(render_corrections(stories), encoding="utf-8")
    (ROOT / "feed.xml").write_text(render_feed(stories), encoding="utf-8")
    (ROOT / "share.js").write_text(SHARE_JS, encoding="utf-8")
    (ROOT / "site.js").write_text(SITE_JS, encoding="utf-8")
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
