# Chaotic News Network

Unbiased. Unverified. Unhinged.

**Chaotic News is satire. Every joke is made up.** Reply stories start from real news (told accurately, with sources); everything else is made up. No no real scams, nobody should send anyone a gift card.

Live: https://2three1y.github.io/chaoticnews/

Live on X: https://x.com/ChaoticNewsHQ (the link is in every page's header and footer, set by `X_HANDLE` in `tools/add_story.py`)

- Front page: `index.html`
- All stories: `stories/index.html` (newest first, plus sections)
- Section pages: `section/breaking.html`, `section/tech.html`, `section/gaming.html`, `section/scams.html`, `section/beats.html`, `section/weather.html` (the section tabs in the nav bar)
- Story pictures: `images/<slug>.jpg` (1280x720; set `image:` and `image_alt:` in the story's front matter; alt text is required)
- Every story list on the site is a numbered list (`<ol>`), and every story shows a topic label like "Tech · Nov 2"
- Every story: `stories/<slug>.html`
- Story list for scripts: `stories.json`
- RSS feed (for auto-posting): `feed.xml`
- Link-preview card images: `cards/site.png`, `cards/section/<section>.png`, `cards/stories/<slug>.png`

## Adding stories

Stories are written in `content/<slug>.md`. Everything else (story pages, the front page, the stories index, `stories.json` and `feed.xml`) is built from that folder by one script, so don't edit those by hand.

Add one or more new stories:

```
python3 tools/add_story.py new-story.md another-story.md
```

That copies each story into `content/`, then rebuilds the whole site. The newest story becomes the front page lead and the ticker headline, and lands at the top of the RSS feed. Then commit and push; GitHub Pages does the rest.

Other commands:

```
python3 tools/add_story.py --rebuild           # rebuild everything from content/
python3 tools/add_story.py --replace fixed.md  # overwrite a story with the same title/slug
```

Python 3.9 or newer. Drawing the link-preview card images also needs Pillow (`pip install pillow`); without it the pages still build and keep the cards already in `cards/`.

### Story format (Markdown)

```
---
title: Local Printer Declares Independence
dek: One short sentence or two that sums up the story.
section: Tech
date: 2026-11-01T09:00:00-04:00
author: Dex Voltage
author_title: Tech Desk
featured: true
---
First paragraph of the story.

## A subhead

More paragraphs. **Bold**, *italic* and [links](https://example.com) work.

> "A pull quote," said a made-up person.

- bullet lists work too
```

- `title`, `dek` and `section` are required. Sections: Breaking, Tech, Scams, Beats, Weather.
- `date` is optional (defaults to now, Eastern time). `slug` is optional (made from the title).
- `author` defaults to "Chaotic News Network Staff". Optional: `author_title`, `featured`, `dateline`, `correction`, `updated` (a later date/time, shown as the story's "Updated" line).
- Pictures: `image` (a path inside the repo, for example `images/printer.png`) and `image_alt` (what the picture shows, for VoiceOver). If `image` is set without `image_alt`, the build stops with an error. Without an `image`, each story gets an original title-card graphic for its section, which already has alt text. Only use pictures we made or are allowed to use, no photos of real people.
- Use `##` for subheads (each page already has its one main heading, the title).

### Reply stories (real news, chaotic voice)

When @ChaoticNewsHQ replies to a post on X, the reply can become a story: our reply is the headline, the real news is told accurately but in a funny voice, and the made-up part sits under its own "Our Take (This Part Is Made Up)" subhead. Add these fields to the front matter:

```
x_post: https://x.com/ChaoticNewsHQ/status/...   (our reply; it gets embedded)
x_post_text: GAMING DESK: the reply's exact words
x_post_date: November 3, 2026
x_replied_to: IGN
x_replied_to_url: https://x.com/IGN/status/...
source_url: https://... (the real article)
source_title: The article's title
source_outlet: IGN
```

`source2_url`, `source2_title` and `source2_outlet` are optional. A reply story gets a "Reply Story" note instead of "all stories are made up", our post embedded with X's standard blockquote (it reads as a plain link if X's script doesn't load), and a "Where the Real News Came From" list. No real tragedies, layoffs or punching down. These run shorter (250 to 400 words).

### Story format (JSON)

The same fields work as a `.json` file, with the story text in `body` (Markdown):

```
{"title": "...", "dek": "...", "section": "Scams", "author": "Penny Popup", "body": "First paragraph.\n\n## Subhead\n\nMore."}
```

### Daily stories

A daily job can write two story files and run `python3 tools/add_story.py a.md b.md`, then commit. Rules for every story: clearly made up, no real people in anything but obviously silly harmless ways, no explicit stuff, nothing that could pass for real news about a real tragedy.

## Design

The look is a TV news network site, all original: a "CN" logo bug, a black masthead with the "Live on X" pill, section tabs, a red BREAKING bar with the four newest headlines (plain links, nothing moves), a lead story, story cards, Most Read and More Top Stories. Story art is drawn as SVG by `tools/add_story.py` (`svg_art`), so no photos or outside images are used. Styles are in `style.css`; `share.js` powers the Copy link and Share buttons on story pages (they stay hidden if the browser can't do it).

## Social cards (link previews)

Every page carries Open Graph and X card tags, so a link shows a big preview card on X, Mastodon and the rest of the fediverse, Bluesky, Nostr apps, Discord, iMessage, WhatsApp, Facebook, Reddit, LinkedIn, Telegram and Slack (they all read Open Graph). Each page has a canonical URL, a description ending in "Satire.", and a 1200x630 PNG card with alt text (`og:image:alt`, `twitter:image:alt`).

The cards are drawn on every build by `tools/social_cards.py` (Pillow, no internet): the CN logo, the section colours, the headline, and a yellow SATIRE tag plus "Satire · every story is made up" on the card itself, so a screenshot of a card can't pass as real news. One card per story, one per section, and a site card for the front page and the stories index. New stories get theirs automatically. The same script draws `favicon.ico`, `favicon-32.png` and `apple-touch-icon.png`.

No Mastodon account yet. When there is one, put its profile URL in `FEDIVERSE_PROFILE` (and `@name@server` in `FEDIVERSE_CREATOR`) in `tools/add_story.py` and rebuild.

## Accessibility

Every page has a skip link, one main heading, headings in order, header/nav/main/footer landmarks, the story inside `article`, real links and buttons, visible focus, alt text on every graphic (the logo reads "Chaotic News"), and readable dates. Story pages have one status message ("Link copied."). The only script is the local `share.js`; no trackers or outside files.

Co-written with Tab
