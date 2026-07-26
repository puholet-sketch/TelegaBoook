#!/usr/bin/env python3
"""Fast bootstrap books.json from raw_posts (placeholders until enrich finishes)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_posts.json"
OUTS = [ROOT / "data" / "books.json", ROOT / "site" / "data" / "books.json"]
SKIP = re.compile(r"^Моя\s+\d+", re.I)
PAREN = re.compile(r"\(([^)]+)\)\s*$")


def clean_title(title: str) -> str:
    return PAREN.sub("", title).strip(" .–—-")


def author_of(p: dict) -> str:
    if p.get("author"):
        return p["author"]
    m = PAREN.search(p.get("title") or "")
    return m.group(1).strip() if m else "Автор уточняется"


def takeaway(p: dict) -> str:
    title = clean_title(p["title"])
    return (
        f"Главные идеи книги «{title}» — в духе разборов канала «Книги на миллион»: "
        "смысл, привычки и практические шаги без воды. Полное краткое описание подтянется из открытых источников."
    )


def main():
    posts = json.loads(RAW.read_text(encoding="utf-8"))
    books = []
    for p in posts:
        if SKIP.search(p.get("title") or ""):
            continue
        books.append(
            {
                "number": p["number"],
                "title": clean_title(p["title"]),
                "title_raw": p["title"],
                "author": author_of(p),
                "takeaway": takeaway(p),
                "cover": "covers/_placeholder.svg",
                "likes": p.get("likes") or 0,
                "comments": p.get("comments") or 0,
                "views": p.get("views") or 0,
                "date": p.get("date"),
                "message_id": p.get("message_id"),
                "bootstrap": True,
            }
        )
    books.sort(key=lambda b: (-b["likes"], -b["comments"], b["number"]))
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_channel": "https://web.telegram.org/a/#-1001167188175",
        "count": len(books),
        "sort": ["likes_desc", "comments_desc"],
        "books": books,
        "note": "bootstrap placeholders; run scripts/enrich.py for covers & real takeaways",
    }
    for out in OUTS:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", out)


if __name__ == "__main__":
    main()
