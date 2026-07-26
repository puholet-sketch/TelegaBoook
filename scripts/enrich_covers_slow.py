#!/usr/bin/env python3
"""Slow Google Books cover/author enricher (avoids 429). Run after cooldown."""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOKS = ROOT / "data" / "books.json"
OUT_SITE = ROOT / "site" / "data" / "books.json"
CACHE = ROOT / "data" / "enrich_cache.json"
COVERS = ROOT / "site" / "covers"
UA = "TelegaBoook/1.0 (educational catalog)"


def http_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def http_bytes(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            return data if len(data) > 2500 else None
    except Exception:
        return None


def gb_lookup(title: str) -> dict:
    q = urllib.parse.quote(title)
    url = f"https://www.googleapis.com/books/v1/volumes?q={q}&maxResults=3"
    data = http_json(url)
    for item in data.get("items") or []:
        vi = item.get("volumeInfo") or {}
        imgs = vi.get("imageLinks") or {}
        cover = imgs.get("thumbnail") or imgs.get("smallThumbnail")
        if cover:
            cover = cover.replace("http://", "https://")
            cover = re.sub(r"zoom=\d", "zoom=2", cover)
        authors = vi.get("authors") or []
        desc = vi.get("description") or ""
        if cover or authors or desc:
            return {"cover": cover, "author": ", ".join(authors) if authors else None, "desc": desc}
    return {}


def main():
    payload = json.loads(BOOKS.read_text(encoding="utf-8"))
    books = payload["books"]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    for i, book in enumerate(books, 1):
        key = str(book["number"])
        # skip if already has raster cover
        if book.get("cover", "").endswith((".jpg", ".jpeg", ".png")) or (
            book.get("cover", "").startswith("http") and "openlibrary" in book.get("cover", "")
        ):
            print(f"[{i}/{len(books)}] skip #{book['number']}", flush=True)
            continue
        print(f"[{i}/{len(books)}] GB #{book['number']} {book['title'][:40]}", flush=True)
        try:
            hit = gb_lookup(book["title"])
        except Exception as e:
            print("  wait/429", e, flush=True)
            time.sleep(20)
            continue
        time.sleep(2.8)
        if not hit:
            continue
        if hit.get("author") and book.get("author") in ("Автор уточняется", "Автор не указан"):
            book["author"] = hit["author"]
        if hit.get("desc") and len(hit["desc"]) > 80:
            desc = re.sub(r"<[^>]+>", "", hit["desc"])
            desc = re.sub(r"\s+", " ", desc).strip()
            book["takeaway"] = desc[:420].rsplit(" ", 1)[0] + ("…" if len(desc) > 420 else "")
        if hit.get("cover"):
            dest = COVERS / f"{book['number']:04d}.jpg"
            data = http_bytes(hit["cover"])
            if data:
                dest.write_bytes(data)
                book["cover"] = f"covers/{book['number']:04d}.jpg"
            else:
                book["cover"] = hit["cover"]
        cache[key] = {**cache.get(key, {}), **book, "ok": True}
        if i % 8 == 0:
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
            payload["books"] = books
            payload["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            BOOKS.write_text(text, encoding="utf-8")
            OUT_SITE.write_text(text, encoding="utf-8")
            print("  checkpoint saved", flush=True)

    books.sort(key=lambda b: (-b["likes"], -b["comments"], b["number"]))
    payload["books"] = books
    payload["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    BOOKS.write_text(text, encoding="utf-8")
    OUT_SITE.write_text(text, encoding="utf-8")
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print("done")


if __name__ == "__main__":
    main()
