#!/usr/bin/env python3
"""
Reliable cover enrichment for TelegaBoook.

Strategy:
1) Resume from local JPG / cache
2) Open Library by RU title (rare hits)
3) Translate title RU→EN (gtx) → Open Library (main path)
4) Google Books with exponential backoff (fallback)
5) Wikipedia page image if title is close
6) Download cover locally (SSL verify with unverified fallback)
7) Checkpoint books.json + site/docs mirrors

Keeps SVG covers when nothing reliable is found.
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOKS = ROOT / "data" / "books.json"
OUTS = [
    ROOT / "data" / "books.json",
    ROOT / "site" / "data" / "books.json",
    ROOT / "docs" / "data" / "books.json",
]
CACHE = ROOT / "data" / "cover_cache.json"
PROGRESS = ROOT / "data" / "cover_progress.json"
COVERS = ROOT / "site" / "covers"
COVERS_DOCS = ROOT / "docs" / "covers"

UA = (
    "TelegaBoook/2.0 (https://github.com/puholet-sketch/TelegaBoook; "
    "mailto:226520522+puholet-sketch@users.noreply.github.com)"
)

SSL_VERIFY = ssl.create_default_context()
SSL_UNVERIFIED = ssl._create_unverified_context()

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG"

# High-confidence English aliases for frequent RU titles (Open Library friendly)
TITLE_ALIASES = {
    "кафе на краю земли": [
        "The Cafe on the Edge of the World",
        "Cafe on the Edge of the World",
    ],
    "магия утра": ["The Miracle Morning"],
    "сила привычки": ["The Power of Habit"],
    "атомные привычки": ["Atomic Habits"],
    "нанопривычки": ["Atomic Habits", "Tiny Habits"],
    "поток": ["Flow Mihaly Csikszentmihalyi", "Flow The Psychology of Optimal Experience"],
    "думай медленно решай быстро": ["Thinking Fast and Slow"],
    "богатый папа бедный папа": ["Rich Dad Poor Dad"],
    "7 навыков высокоэффективных людей": ["The 7 Habits of Highly Effective People"],
    "тонкое искусство пофигизма": ["The Subtle Art of Not Giving a F*ck"],
    "сила настоящего": ["The Power of Now"],
    "эго это враг": ["Ego Is the Enemy"],
    "препятствие как путь": ["The Obstacle Is the Way"],
    "как привести дела в порядок": ["Getting Things Done"],
    "миссия выполнима": ["Mission Possible Margulan"],
}


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def http_get(url: str, timeout: int = 35, accept: str = "*/*") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    last_err = None
    for ctx in (SSL_VERIFY, SSL_UNVERIFIED):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
            continue
    raise last_err  # type: ignore


def http_json(url: str) -> dict | list:
    return json.loads(http_get(url, accept="application/json").decode("utf-8", "replace"))


def is_image(data: bytes) -> bool:
    return len(data) >= 4000 and (data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC))


def short_title(title: str) -> str:
    t = re.split(r"[.:•|–—]", title, maxsplit=1)[0].strip()
    return t or title.strip()


def title_tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[A-Za-zА-Яа-яЁё0-9]{3,}", s.lower())}


def similar(a: str, b: str) -> float:
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def translate_ru_en(text: str) -> str | None:
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(
        {"client": "gtx", "sl": "ru", "tl": "en", "dt": "t", "q": text}
    )
    try:
        data = http_json(url)
        out = "".join(part[0] for part in data[0] if part and part[0])
        out = re.sub(r"\s+", " ", out).strip()
        return out or None
    except Exception:
        return None


def ol_search(query: str, mode: str = "q") -> list[dict]:
    params = {mode: query, "limit": 8}
    url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)
    data = http_json(url)
    return list(data.get("docs") or [])


def pick_ol_doc(docs: list[dict], en_title: str) -> dict | None:
    scored = []
    for d in docs:
        if not d.get("cover_i"):
            continue
        score = 0.0
        score += min(float(d.get("edition_count") or 0), 50) / 50.0
        score += similar(en_title, d.get("title") or "") * 2.0
        if d.get("author_name"):
            score += 0.15
        scored.append((score, d))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    best_score, best = scored[0]
    # Avoid obviously wrong matches when translation is weak
    if best_score < 0.25 and similar(en_title, best.get("title") or "") < 0.15:
        return None
    return best


def gb_search(title: str) -> dict | None:
    url = "https://www.googleapis.com/books/v1/volumes?" + urllib.parse.urlencode(
        {"q": title, "maxResults": 4}
    )
    data = http_json(url)
    for item in data.get("items") or []:
        vi = item.get("volumeInfo") or {}
        imgs = vi.get("imageLinks") or {}
        cover = imgs.get("thumbnail") or imgs.get("smallThumbnail")
        if not cover:
            continue
        cover = cover.replace("http://", "https://")
        cover = re.sub(r"zoom=\d", "zoom=2", cover)
        authors = vi.get("authors") or []
        return {
            "cover_url": cover,
            "author": ", ".join(authors) if authors else None,
            "source": "google_books",
            "matched_title": vi.get("title"),
        }
    return None


def wiki_cover(title: str) -> dict | None:
    short = short_title(title)
    url = "https://ru.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "opensearch", "search": short, "limit": 3, "format": "json"}
    )
    try:
        os_ = http_json(url)
    except Exception:
        return None
    if not isinstance(os_, list) or len(os_) < 2:
        return None
    for cand in os_[1]:
        if similar(short, cand) < 0.2 and short.lower() not in cand.lower():
            continue
        qurl = "https://ru.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
            {
                "action": "query",
                "prop": "pageimages",
                "piprop": "thumbnail|original",
                "pithumbsize": 600,
                "titles": cand,
                "format": "json",
            }
        )
        try:
            q = http_json(qurl)
            pages = ((q.get("query") or {}).get("pages") or {}).values()
            for page in pages:
                thumb = page.get("original") or page.get("thumbnail") or {}
                src = thumb.get("source")
                if src and "wikimedia" in src:
                    return {"cover_url": src, "source": "wikipedia", "matched_title": cand}
        except Exception:
            continue
    return None


def download_cover(url: str, number: int) -> str | None:
    try:
        data = http_get(url)
    except Exception:
        return None
    if not is_image(data):
        return None
    ext = ".png" if data.startswith(PNG_MAGIC) else ".jpg"
    name = f"{number:04d}{ext}"
    (COVERS / name).write_bytes(data)
    (COVERS_DOCS / name).write_bytes(data)
    return f"covers/{name}"


def has_local_cover(number: int) -> str | None:
    for ext in (".jpg", ".jpeg", ".png"):
        p = COVERS / f"{number:04d}{ext}"
        if p.exists() and p.stat().st_size >= 4000:
            # mirror to docs
            dest = COVERS_DOCS / p.name
            if not dest.exists() or dest.stat().st_size != p.stat().st_size:
                dest.write_bytes(p.read_bytes())
            return f"covers/{p.name}"
    return None


def resolve_cover(book: dict, cache: dict) -> dict:
    number = book["number"]
    title = book.get("title") or ""
    key = str(number)

    local = has_local_cover(number)
    if local:
        prev = cache.get(key) or {}
        return {
            **prev,
            "ok": True,
            "cover": local,
            "source": prev.get("source") or "local",
            "author": prev.get("author"),
        }

    cached = cache.get(key) or {}
    if cached.get("ok") and cached.get("cover_url") and not cached.get("failed"):
        local2 = download_cover(cached["cover_url"], number)
        if local2:
            cached["cover"] = local2
            cached["ok"] = True
            return cached

    candidates: list[dict] = []

    # 1) OL direct RU
    for q in {title, short_title(title)}:
        try:
            docs = ol_search(q, "q")
            doc = pick_ol_doc(docs, q)
            if doc:
                candidates.append(
                    {
                        "cover_url": f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg",
                        "author": ", ".join((doc.get("author_name") or [])[:3]) or None,
                        "source": "openlibrary_ru",
                        "matched_title": doc.get("title"),
                        "score": similar(q, doc.get("title") or ""),
                    }
                )
        except Exception:
            pass
        time.sleep(0.35)

    # 2) Alias / translate → OL
    en = None
    en_queries: list[str] = []
    alias_key = short_title(title).lower()
    for a in TITLE_ALIASES.get(alias_key, []):
        en_queries.append(a)
    try:
        en = translate_ru_en(short_title(title))
    except Exception:
        en = None
    time.sleep(0.45)
    if en:
        en_queries.extend([en, short_title(en)])
        # Common machine-translation misfires
        low = en.lower()
        if "morning" in low and "магия" in title.lower():
            en_queries.append("The Miracle Morning")
        if "cafe" in low and "edge" not in low and "end" in low:
            en_queries.append("The Cafe on the Edge of the World")

    seen_q: set[str] = set()
    for q in en_queries:
        qn = q.strip()
        if not qn or qn.lower() in seen_q:
            continue
        seen_q.add(qn.lower())
        for mode in ("title", "q"):
            try:
                docs = ol_search(qn, mode)
                doc = pick_ol_doc(docs, qn)
                if doc:
                    candidates.append(
                        {
                            "cover_url": f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg",
                            "author": ", ".join((doc.get("author_name") or [])[:3]) or None,
                            "source": f"openlibrary_en:{mode}",
                            "matched_title": doc.get("title"),
                            "score": similar(qn, doc.get("title") or "") + 0.35,
                        }
                    )
            except Exception:
                pass
            time.sleep(0.35)

    # Try Open Library candidates first (most reliable when present)
    if candidates:
        candidates.sort(key=lambda c: -float(c.get("score") or 0))
        for cand in candidates[:4]:
            local_path = download_cover(cand["cover_url"], number)
            if local_path:
                return {
                    "ok": True,
                    "cover": local_path,
                    "cover_url": cand["cover_url"],
                    "author": cand.get("author"),
                    "source": cand.get("source"),
                    "matched_title": cand.get("matched_title"),
                    "en_title": en,
                }
            time.sleep(0.25)

    # 3) Google Books (optional; ignore 429 and continue)
    gb_429 = False
    for q in (title, short_title(title), en or ""):
        if not q:
            continue
        try:
            hit = gb_search(q)
            if hit:
                local_path = download_cover(hit["cover_url"], number)
                if local_path:
                    return {
                        "ok": True,
                        "cover": local_path,
                        "cover_url": hit["cover_url"],
                        "author": hit.get("author"),
                        "source": "google_books",
                        "matched_title": hit.get("matched_title"),
                        "en_title": en,
                    }
        except urllib.error.HTTPError as e:
            if e.code == 429:
                gb_429 = True
                break
        except Exception:
            pass
        time.sleep(0.9)

    # 4) Wikipedia page image
    try:
        wh = wiki_cover(title)
        if wh:
            local_path = download_cover(wh["cover_url"], number)
            if local_path:
                return {
                    "ok": True,
                    "cover": local_path,
                    "cover_url": wh["cover_url"],
                    "author": None,
                    "source": "wikipedia",
                    "matched_title": wh.get("matched_title"),
                    "en_title": en,
                }
    except Exception:
        pass

    if gb_429:
        return {"ok": False, "retry_later": True, "error": "gb_429_no_other_source", "en_title": en}
    return {"ok": False, "failed": True, "error": "no_candidates", "en_title": en}


def write_books(books: list[dict]) -> None:
    books_sorted = sorted(
        books, key=lambda b: (-(b.get("likes") or 0), -(b.get("comments") or 0), b.get("number") or 0)
    )
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_channel": "https://web.telegram.org/a/#-1001167188175",
        "count": len(books_sorted),
        "sort": ["likes_desc", "comments_desc"],
        "books": books_sorted,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def main():
    COVERS.mkdir(parents=True, exist_ok=True)
    COVERS_DOCS.mkdir(parents=True, exist_ok=True)

    payload = load_json(BOOKS, {"books": []})
    books = payload.get("books") or []
    cache = load_json(CACHE, {})
    progress = {"done": 0, "ok": 0, "fail": 0, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}

    by_num = {b["number"]: b for b in books}

    for i, book in enumerate(books, 1):
        number = book["number"]
        key = str(number)
        print(f"[{i}/{len(books)}] #{number} {book.get('title', '')[:48]}", flush=True)

        # already good?
        local = has_local_cover(number)
        if local:
            book["cover"] = local
            cache[key] = {**(cache.get(key) or {}), "ok": True, "cover": local, "source": "local"}
            progress["done"] += 1
            progress["ok"] += 1
            print("  keep local", local, flush=True)
            continue

        result = resolve_cover(book, cache)

        cache[key] = {**(cache.get(key) or {}), **result}
        if result.get("ok") and result.get("cover"):
            book["cover"] = result["cover"]
            if result.get("author") and book.get("author") in ("Автор уточняется", "Автор не указан", None, ""):
                book["author"] = result["author"]
            progress["ok"] += 1
            print(f"  OK {result.get('source')} → {result.get('cover')}", flush=True)
        else:
            progress["fail"] += 1
            print(f"  FAIL {result.get('error')} en={result.get('en_title')}", flush=True)
            # Soft pause if Google is hot — do not abort the run
            if result.get("retry_later"):
                time.sleep(8)

        progress["done"] += 1
        progress["ok_total"] = progress["ok"]
        progress["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")

        if i % 10 == 0:
            # sync list from by_num mutations
            write_books(list(by_num.values()))
            save_json(CACHE, cache)
            save_json(PROGRESS, progress)
            print("  checkpoint", progress, flush=True)

        time.sleep(0.55)

    write_books(list(by_num.values()))
    save_json(CACHE, cache)
    progress["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_json(PROGRESS, progress)
    print("DONE", progress, flush=True)


if __name__ == "__main__":
    main()
