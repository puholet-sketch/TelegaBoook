#!/usr/bin/env python3
"""Build site catalog from raw posts + optional enrich_cache overlays."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_posts.json"
CACHE = ROOT / "data" / "enrich_cache.json"
OUT = ROOT / "data" / "books.json"
OUT_SITE = ROOT / "site" / "data" / "books.json"
OUT_DOCS = ROOT / "docs" / "data" / "books.json"
COVERS = ROOT / "site" / "covers"
COVERS_DOCS = ROOT / "docs" / "covers"

SKIP = re.compile(r"^Моя\s+\d+", re.I)
PAREN = re.compile(r"\(([^)]+)\)\s*$")
# Only proper-name shaped matches: «от Имя Фамилия» / «автор Джон Доу»
AUTHOR_FROM = re.compile(
    r"(?:^|[.\s])(?:от|автор(?:а|ы)?)\s+"
    r"([А-ЯЁA-Z][а-яёa-z\-]+(?:\s+[А-ЯЁA-Z][а-яёa-z\-]+){1,2})"
)
BOILER = [
    r"Зачем ты тут\?.*?(?=\n\n|\Z)",
    r"Неудобно слушать\?.*?(?=\n\n|\Z)",
    r"Выжимка самого главного.*?(?=\n\n|\Z)",
    r"Главные выводы из книги.*?(?=\n\n|\Z)",
    r"Слушай аудио подкаст.*?(?=\n\n|\Z)",
    r"Книжный блог.*",
    r"Подпишись, это первый шаг.*",
    r"Хотите свою книгу\?.*",
    r"5 уроков харизмы.*",
    r"52 привычки.*",
    r"Как я сделал голос.*",
    r"Где скачать.*",
    r"​​+",
]

PALETTE = [
    ("#0F6B5C", "#163D36"),
    ("#1F4E79", "#122C45"),
    ("#8B3A2A", "#4A1F18"),
    ("#5C4B8A", "#2E2448"),
    ("#3D5A40", "#1F2E21"),
    ("#7A4E2D", "#3D2616"),
    ("#2F4858", "#15232C"),
    ("#6B2D5B", "#36152E"),
]


def clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", PAREN.sub("", title).strip(" .–—-"))


def looks_like_person(name: str) -> bool:
    parts = name.split()
    if len(parts) < 2 or len(parts) > 3:
        return False
    if any(len(p) < 2 for p in parts):
        return False
    # reject common non-name openings
    stop = {
        "том", "том,", "как", "что", "это", "для", "при", "без", "все", "всё",
        "своей", "своего", "жизни", "книги", "автор", "герой", "страсти",
    }
    if parts[0].lower() in stop:
        return False
    return all(p[0].isupper() for p in parts)


def author_of(post: dict) -> str:
    title = post.get("title") or ""
    m = PAREN.search(title)
    if m and looks_like_person(m.group(1).strip()):
        return m.group(1).strip()
    if m and 3 < len(m.group(1).strip()) < 40 and m.group(1)[0].isupper():
        # allow single famous names in parentheses too
        cand = m.group(1).strip()
        if " " in cand or cand.isalpha():
            return cand
    text = post.get("text") or ""
    for m in AUTHOR_FROM.finditer(text):
        name = m.group(1).strip(" .,:;")
        if looks_like_person(name):
            return name
    return "Автор уточняется"


def takeaway_of(post: dict, title: str) -> str:
    text = post.get("text") or ""
    # drop first title line
    lines = [ln.strip() for ln in text.splitlines()]
    body = "\n".join(ln for ln in lines if not re.match(r"^Книга\s*#\d+", ln, re.I) and not ln.startswith("#"))
    for pat in BOILER:
        body = re.sub(pat, " ", body, flags=re.I | re.S)
    body = re.sub(r"\s+", " ", body).strip(" -–—")
    # keep 1–3 sentences
    parts = re.split(r"(?<=[.!?…])\s+", body)
    parts = [p for p in parts if len(p) > 35 and "подкаст" not in p.lower()]
    out = " ".join(parts[:3]).strip()
    if len(out) > 420:
        out = out[:417].rsplit(" ", 1)[0] + "…"
    if len(out) < 50:
        out = (
            f"Ключевые идеи книги «{title}» — смысл, привычки и практические шаги. "
            "Краткий разбор в духе канала «Книги на миллион»."
        )
    return out


def make_svg_cover(number: int, title: str, author: str) -> str:
    c1, c2 = PALETTE[number % len(PALETTE)]
    safe_title = (
        title.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    safe_author = (
        author.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    # wrap title roughly
    words = safe_title.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) > 18 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    lines = lines[:6]
    title_svg = ""
    y = 210
    for i, ln in enumerate(lines):
        title_svg += f'<text x="40" y="{y + i * 34}" fill="#F7F1E5" font-family="Georgia, serif" font-size="26" font-weight="700">{ln}</text>\n'
    fname = f"{number:04d}.svg"
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600" viewBox="0 0 400 600">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{c1}"/>
      <stop offset="100%" stop-color="{c2}"/>
    </linearGradient>
  </defs>
  <rect width="400" height="600" fill="url(#g)"/>
  <rect x="22" y="22" width="356" height="556" fill="none" stroke="#E8C47A" stroke-width="2" opacity="0.55"/>
  <text x="40" y="78" fill="#E8C47A" font-family="Arial, sans-serif" font-size="14" letter-spacing="3">КНИГА #{number}</text>
  {title_svg}
  <text x="40" y="520" fill="#D9CDB5" font-family="Arial, sans-serif" font-size="15">{safe_author[:42]}</text>
  <text x="40" y="552" fill="#E8C47A" font-family="Arial, sans-serif" font-size="12" letter-spacing="2">TELEGA BOOK</text>
</svg>
'''
    (COVERS / fname).write_text(svg, encoding="utf-8")
    (COVERS_DOCS / fname).write_text(svg, encoding="utf-8")
    return f"covers/{fname}"


def main():
    COVERS.mkdir(parents=True, exist_ok=True)
    COVERS_DOCS.mkdir(parents=True, exist_ok=True)
    posts = json.loads(RAW.read_text(encoding="utf-8"))
    cache = {}
    if CACHE.exists():
        cache = json.loads(CACHE.read_text(encoding="utf-8"))

    books = []
    for post in posts:
        if SKIP.search(post.get("title") or ""):
            continue
        title = clean_title(post["title"])
        author = author_of(post)
        takeaway = takeaway_of(post, title)
        cover = make_svg_cover(post["number"], title, author)

        overlay = cache.get(str(post["number"])) or {}
        # Prefer enriched remote/local photo cover if present
        if overlay.get("cover") and "placeholder" not in overlay["cover"] and not overlay["cover"].endswith(".svg"):
            cover = overlay["cover"]
        elif overlay.get("cover_remote"):
            cover = overlay["cover_remote"]
        if overlay.get("author") and overlay["author"] not in ("Автор уточняется", "Автор не указан"):
            author = overlay["author"]
        if overlay.get("takeaway") and not overlay["takeaway"].startswith("Разбор «") and not overlay["takeaway"].startswith("Краткий разбор"):
            takeaway = overlay["takeaway"]

        likes = int(post.get("likes") or 0)
        comments = int(post.get("comments") or 0)
        views = int(post.get("views") or 0)
        # Guard against scraper glitches (views / aggregates mistaken for comments)
        if comments > 2500 or (likes and comments > likes * 20) or (views and comments > views):
            comments = 0

        books.append(
            {
                "number": post["number"],
                "title": title,
                "title_raw": post["title"],
                "author": author,
                "takeaway": takeaway,
                "cover": cover,
                "likes": likes,
                "comments": comments,
                "views": views,
                "date": post.get("date"),
                "message_id": post.get("message_id"),
                "hashtag": None,
            }
        )

    books.sort(key=lambda b: (-b["likes"], -b["comments"], b["number"]))
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_channel": "https://web.telegram.org/a/#-1001167188175",
        "count": len(books),
        "sort": ["likes_desc", "comments_desc"],
        "books": books,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    OUT.write_text(text, encoding="utf-8")
    for dest in (OUT_SITE, OUT_DOCS):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    print(f"books={len(books)} covers={len(list(COVERS.glob('*.svg')))}")


if __name__ == "__main__":
    main()
