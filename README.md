# Chaotic News Network

Unbiased. Unverified. Unhinged.

**Chaotic News is satire. All stories are made up.** No real news, no real scams, nobody should send anyone a gift card.

Live: https://2three1y.github.io/chaoticnews/

Follow on X: https://x.com/ChaoticNewsHQ (the link is in every page's header and footer, set by `X_HANDLE` in `tools/add_story.py`)

- Front page: `index.html`
- All stories: `stories/index.html` (newest first, plus sections)
- Every story: `stories/<slug>.html`
- Story list for scripts: `stories.json`
- RSS feed (for auto-posting): `feed.xml`

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

No installs needed, just Python 3.9 or newer.

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
- `author` defaults to "Chaotic News Network Staff". Optional: `author_title`, `featured`, `dateline`, `correction`.
- Use `##` for subheads (each page already has its one main heading, the title).

### Story format (JSON)

The same fields work as a `.json` file, with the story text in `body` (Markdown):

```
{"title": "...", "dek": "...", "section": "Scams", "author": "Penny Popup", "body": "First paragraph.\n\n## Subhead\n\nMore."}
```

### Daily stories

A daily job can write two story files and run `python3 tools/add_story.py a.md b.md`, then commit. Rules for every story: clearly made up, no real people in anything but obviously silly harmless ways, no explicit stuff, nothing that could pass for real news about a real tragedy.

## Accessibility

Every page has a skip link, one main heading, headings in order, the story inside `main` and `article`, real links, and readable dates. No scripts, trackers or outside files.

Co-written with Tab
