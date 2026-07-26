# TelegaBoook

Красивый каталог книг из Telegram-канала [«Книги на миллион»](https://web.telegram.org/a/#-1001167188175).

## Что внутри

- Название, автор, краткий вывод (из открытых источников)
- Обложки из Open Library / Google Books (не из постов Telegram)
- Сортировка по лайкам и комментариям
- Исключены посты вида «Моя N… книга»

## Структура

- `data/raw_posts.json` — сырые посты из канала
- `data/books.json` — обогащённый каталог для сайта
- `site/` — статический сайт (GitHub Pages)
- `scripts/enrich.py` — обогащение обложками и описаниями

## Локально

```bash
# обогатить каталог (нужен интернет)
python scripts/enrich.py

# открыть сайт
# достаточно любого static server из папки site/
npx --yes serve site
```

## GitHub

- Репозиторий: https://github.com/puholet-sketch/TelegaBoook
- Сайт: https://puholet-sketch.github.io/TelegaBoook/
- Публикация: GitHub Pages из папки `docs/`

### Обновление каталога

```bash
python scripts/build_catalog.py
# опционально, медленно (после cooldown API):
python scripts/enrich_covers_slow.py
```
