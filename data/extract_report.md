# Extract report — «Книги на миллион | бизнес блог»

- **Source:** https://web.telegram.org/a/#-1001167188175
- **Updated:** 2026-07-26 (continued pass to newest)
- **Output:** `data/raw_posts.json`

## Counts

| Metric | Value |
|---|---|
| Book posts kept (`Книга #N - …`) | **484** |
| Number range | 1 … **487** |
| Added in continue pass | **57** (`#431` … `#487`) |
| Missing numbers | **28, 125, 138** |
| Skipped «Моя N…» (this pass) | **18** |
| With likes | 484 |
| With comments (incl. audio-neighbor map) | **227** |

## Method

1. MCP browser: open channel, click **Go to bottom** (real UI click) to reach newest.
2. CDP `Runtime.evaluate` on `.message-list-item` (text, reactions, views, date, message id, comments).
3. Scroll **up** from newest until overlap with prior extract (`#430` and below).
4. Merge into existing `raw_posts.json` by book number / `message_id`.
5. Comment counts: from post itself or neighboring audio posts mentioning `Книга #N`.
6. Skip titles matching `/Моя\s+\d+/i`.

## Blockers / gaps

- Numbers **28, 125, 138** still absent in history (likely skipped/deleted).
- Some newest posts still have `comments: null` if no comments UI was visible on the text card or linked audio.
- Author field is heuristic and often `null`.

## Sample (newest)

- `#482` «Миссия выполнима 2.0. Счастье как система» — likes 396, comments 129.
- `#487` «Беседы с Богом. Необычный диалог. Книга 2» — likes 97.
