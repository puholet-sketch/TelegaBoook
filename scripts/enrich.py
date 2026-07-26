#!/usr/bin/env python3
"""Enrich books via Open Library + Wikipedia (gentle, sequential)."""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_posts.json"
CACHE = ROOT / "data" / "enrich_cache.json"
OUT = ROOT / "data" / "books.json"
OUT_SITE = ROOT / "site" / "data" / "books.json"
COVERS = ROOT / "site" / "covers"
UA = "TelegaBoook/1.0 (catalog; educational)"

SKIP_TITLE = re.compile(r"^Моя\s+\d+", re.I)
PAREN_AUTHOR = re.compile(r"\(([^)]+)\)\s*$")


def http_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def http_bytes(url: str, timeout: int = 30) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            if len(data) < 2500:
                return None
            return data
    except Exception:
        return None


def load_cache() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_title(title: str) -> str:
    t = PAREN_AUTHOR.sub("", title).strip(" .–—-")
    return re.sub(r"\s+", " ", t)


def author_from_title(title: str) -> str | None:
    m = PAREN_AUTHOR.search(title)
    if not m:
        return None
    a = m.group(1).strip()
    return a if len(a) > 2 and not a.isdigit() else None


def is_weak(entry: dict | None) -> bool:
    if not entry or not entry.get("ok"):
        return True
    # Re-fetch if we only have fallback takeaway and no remote cover
    take = entry.get("takeaway") or ""
    cover = entry.get("cover") or ""
    weak_take = take.startswith("Краткий разбор книги") or take.startswith("Главные идеи книги")
    weak_cover = cover.endswith("_placeholder.svg")
    weak_author = (entry.get("author") or "") in ("Автор не указан", "Автор уточняется", "")
    return weak_take and weak_cover and weak_author


def search_open_library(title: str) -> dict:
    q = urllib.parse.quote(title)
    # Prefer title search, then general q
    for url in (
        f"https://openlibrary.org/search.json?title={q}&limit=5",
        f"https://openlibrary.org/search.json?q={q}&limit=5",
    ):
        try:
            data = http_json(url)
        except Exception:
            time.sleep(1.2)
            continue
        docs = data.get("docs") or []
        if not docs:
            continue
        # Prefer docs with cover and author
        docs = sorted(
            docs,
            key=lambda d: (
                0 if d.get("cover_i") else 1,
                0 if d.get("author_name") else 1,
                -(d.get("edition_count") or 0),
            ),
        )
        doc = docs[0]
        authors = doc.get("author_name") or []
        cover_id = doc.get("cover_i")
        cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None
        isbn = None
        for cand in doc.get("isbn") or []:
            if cand:
                isbn = cand
                break
        if not cover_url and isbn:
            cover_url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
        return {
            "author": ", ".join(authors[:3]) if authors else None,
            "cover_url": cover_url,
            "isbn": isbn,
            "info_link": f"https://openlibrary.org{doc['key']}" if doc.get("key") else None,
            "ol_title": doc.get("title"),
        }
    return {}


def wiki_summary(title: str) -> str | None:
    # Try shorter cores for long Russian subtitles
    variants = [title]
    if "." in title:
        variants.append(title.split(".")[0].strip())
    if ":" in title:
        variants.append(title.split(":")[0].strip())
    for lang in ("ru", "en"):
        for v in variants:
            slug = urllib.parse.quote(v.replace(" ", "_"))
            url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{slug}"
            try:
                data = http_json(url)
            except Exception:
                continue
            if data.get("type") == "disambiguation":
                continue
            extract = (data.get("extract") or "").strip()
            if extract and len(extract) > 60:
                return extract
    return None


def shorten_takeaway(text: str, limit: int = 430) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?…])\s+", text)
    out = ""
    for p in parts:
        if not p:
            continue
        if len(out) + len(p) + 1 > limit:
            break
        out = (out + " " + p).strip()
        if len(out) > 160 and out.count(".") >= 2:
            break
    if not out:
        out = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return out


def download_cover(url: str, book_number: int) -> str | None:
    """Try local mirror; always keep remote as fallback in caller."""
    if not url:
        return None
    dest = COVERS / f"{book_number:04d}.jpg"
    if dest.exists() and dest.stat().st_size > 2500:
        return f"covers/{book_number:04d}.jpg"
    data = http_bytes(url)
    if not data:
        return None
    dest.write_bytes(data)
    return f"covers/{book_number:04d}.jpg"


def enrich_one(post: dict) -> dict:
    number = post["number"]
    title = post["title"]
    clean = clean_title(title)
    author = post.get("author") or author_from_title(title)

    ol = search_open_library(clean)
    time.sleep(0.55)
    if not author and ol.get("author"):
        author = ol["author"]

    description = wiki_summary(clean) or ""
    time.sleep(0.35)

    takeaway = shorten_takeaway(description)
    if not takeaway:
        takeaway = (
            f"Разбор «{clean}» из канала «Книги на миллион»: "
            "ключевые идеи, привычки и практические выводы за 10–15 минут."
        )

    cover_remote = ol.get("cover_url")
    local = download_cover(cover_remote, number) if cover_remote else None
    # Prefer local file; else hotlink Open Library (open source)
    cover = local or cover_remote or "covers/_placeholder.svg"

    return {
        "ok": True,
        "number": number,
        "title": clean,
        "title_raw": title,
        "author": author or "Автор уточняется",
        "takeaway": takeaway,
        "cover": cover,
        "cover_remote": cover_remote,
        "info_link": ol.get("info_link"),
        "likes": post.get("likes") or 0,
        "dislikes": post.get("dislikes"),
        "comments": post.get("comments") or 0,
        "views": post.get("views") or 0,
        "date": post.get("date"),
        "message_id": post.get("message_id"),
        "hashtag": _hashtag(post.get("text") or ""),
    }


def _hashtag(text: str) -> str | None:
    m = re.search(r"(#[\wа-яё]+)", text, re.I)
    return m.group(1) if m else None


def write_books(books: list[dict]) -> None:
    books = sorted(books, key=lambda b: (-(b.get("likes") or 0), -(b.get("comments") or 0), b.get("number") or 0))
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_channel": "https://web.telegram.org/a/#-1001167188175",
        "count": len(books),
        "sort": ["likes_desc", "comments_desc"],
        "books": books,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    OUT.write_text(text, encoding="utf-8")
    OUT_SITE.parent.mkdir(parents=True, exist_ok=True)
    OUT_SITE.write_text(text, encoding="utf-8")


def main():
    COVERS.mkdir(parents=True, exist_ok=True)
    posts = json.loads(RAW.read_text(encoding="utf-8"))
    posts = [p for p in posts if not SKIP_TITLE.search(p.get("title") or "")]
    posts = sorted(posts, key=lambda x: x["number"])
    cache = load_cache()

    books_by_num: dict[int, dict] = {}
    # Keep any strong cached entries
    for p in posts:
        key = str(p["number"])
        if key in cache and not is_weak(cache[key]):
            books_by_num[p["number"]] = cache[key]

    for i, post in enumerate(posts, 1):
        key = str(post["number"])
        if post["number"] in books_by_num:
            print(f"[{i}/{len(posts)}] keep #{post['number']}", flush=True)
            continue
        print(f"[{i}/{len(posts)}] enrich #{post['number']} {post['title'][:48]}", flush=True)
        try:
            result = enrich_one(post)
        except Exception as e:
            print("  ERR", e, flush=True)
            result = {
                "ok": False,
                "number": post["number"],
                "title": clean_title(post["title"]),
                "title_raw": post["title"],
                "author": post.get("author") or author_from_title(post["title"]) or "Автор уточняется",
                "takeaway": (
                    f"Разбор «{clean_title(post['title'])}» из канала «Книги на миллион»: "
                    "ключевые идеи и практические выводы."
                ),
                "cover": "covers/_placeholder.svg",
                "likes": post.get("likes") or 0,
                "comments": post.get("comments") or 0,
                "views": post.get("views") or 0,
                "date": post.get("date"),
                "message_id": post.get("message_id"),
            }
        cache[key] = result
        books_by_num[post["number"]] = result
        if i % 10 == 0:
            save_cache(cache)
            write_books(list(books_by_num.values()))

    save_cache(cache)
    write_books(list(books_by_num.values()))
    print("Done. books=", len(books_by_num))


if __name__ == "__main__":
    main()
