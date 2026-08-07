"""The Reading Room's bookshelf: public-domain classics, fetched once from
Project Gutenberg, split into chapters, and cached forever in the kv store.

All eight titles were published in 1930 or earlier and are public domain in
the US — no restrictions on hosting the text. The Project Gutenberg
header/footer boilerplate is stripped (their trademark license applies only
when their branding is kept); the bare text is unrestricted.
"""
import re
import threading

import requests

from . import storage

BOOKS = {
    "treasure-island": {
        "title": "Treasure Island", "author": "Robert Louis Stevenson",
        "emoji": "🏴‍☠️", "gutenberg_id": 120},
    "call-of-the-wild": {
        "title": "The Call of the Wild", "author": "Jack London",
        "emoji": "🐺", "gutenberg_id": 215},
    "wizard-of-oz": {
        "title": "The Wonderful Wizard of Oz", "author": "L. Frank Baum",
        "emoji": "🦁", "gutenberg_id": 55},
    "alice-in-wonderland": {
        "title": "Alice's Adventures in Wonderland", "author": "Lewis Carroll",
        "emoji": "🐇", "gutenberg_id": 11},
    "tarzan": {
        "title": "Tarzan of the Apes", "author": "Edgar Rice Burroughs",
        "emoji": "🦍", "gutenberg_id": 78},
    "sherlock-holmes": {
        "title": "The Adventures of Sherlock Holmes", "author": "Arthur Conan Doyle",
        "emoji": "🔍", "gutenberg_id": 1661},
    "twenty-thousand-leagues": {
        "title": "Twenty Thousand Leagues Under the Sea", "author": "Jules Verne",
        "emoji": "🐙", "gutenberg_id": 164},
    "around-the-world": {
        "title": "Around the World in Eighty Days", "author": "Jules Verne",
        "emoji": "🎈", "gutenberg_id": 103},
}

# Bump to invalidate every cached book and re-parse on next open (the meta
# record carries this; a mismatch is treated as a cache miss).
PARSER_VERSION = 2

_fetch_locks = {}
_locks_guard = threading.Lock()


def _meta_key(book):
    return f"book:{book}:meta"


def _chapter_key(book, i):
    return f"book:{book}:ch:{i}"


def _strip_gutenberg_boilerplate(text):
    start = re.search(r"\*\*\* ?START OF (?:THE|THIS) PROJECT GUTENBERG.*?\*\*\*", text)
    if start:
        text = text[start.end():]
    end = re.search(r"\*\*\* ?END OF (?:THE|THIS) PROJECT GUTENBERG.*", text)
    if end:
        text = text[: end.start()]
    return text.strip()


# Chapter headings across these eight books: "CHAPTER I.", "Chapter 1",
# "ADVENTURE I.", or a bare roman numeral line like "I. A SCANDAL IN BOHEMIA".
_HEADING_RE = re.compile(
    r"^(?:(?:CHAPTER|Chapter|ADVENTURE|Adventure|STORY|Story)\s+[IVXLCivxlc\d]+\.?[^\n]{0,80}"
    r"|[IVXLC]+\.\s{0,3}[A-Z][^\n]{0,80})$",
    re.M,
)

PART_WORDS = 1800  # fallback segment size when no chapter structure is found


def _unwrap(text):
    """Gutenberg plain text is hard-wrapped at ~70 columns. Rejoin lines
    within each paragraph (blank lines still separate paragraphs) so the
    reader reflows naturally on any screen width."""
    paragraphs = re.split(r"\n\s*\n", text)
    return "\n\n".join(
        re.sub(r"\s*\n\s*", " ", p).strip() for p in paragraphs if p.strip()
    )


_CH_NUM_RE = re.compile(
    r"(?:chapter|adventure|story)?\s*([ivxlc]+|\d+)\b", re.IGNORECASE
)


def _heading_key(heading):
    """'Chapter IV. The Road…' -> 'iv' — the chapter's number token, used to
    spot a table-of-contents entry duplicating a real heading later on."""
    m = _CH_NUM_RE.match(heading.strip().lower())
    return m.group(1) if m else None


def _split_chapters(text):
    """Split into (title, body) chapters.

    Two table-of-contents defenses: ToC lines cluster tightly, so a heading
    followed by another within 500 chars is skipped — and the LAST couple of
    ToC entries escape that (the front matter after them is long), so any
    boundary whose chapter number reappears in a LATER boundary is dropped
    too (the real chapter heading wins; the ToC stray and any front matter
    it would have swallowed disappear). Books that defeat the heading
    heuristics fall back to fixed-size 'Part N' segments — reading still
    works, just without fancy chapter titles."""
    matches = list(_HEADING_RE.finditer(text))
    boundaries = []
    for i, m in enumerate(matches):
        nxt = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        if nxt - m.start() >= 500:
            boundaries.append(m)
    # Keep only the LAST occurrence of each chapter number.
    last_seen = {}
    for i, m in enumerate(boundaries):
        key = _heading_key(m.group(0))
        if key is not None:
            last_seen[key] = i
    boundaries = [m for i, m in enumerate(boundaries)
                  if _heading_key(m.group(0)) is None
                  or last_seen[_heading_key(m.group(0))] == i]
    if len(boundaries) >= 3:
        chapters = []
        for i, m in enumerate(boundaries[:60]):
            end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(text)
            title = re.sub(r"\s+", " ", m.group(0)).strip()
            body = _unwrap(text[m.end():end])
            if len(body) > 200:
                chapters.append({"title": title, "text": body})
        if len(chapters) >= 3:
            return chapters
    # Fallback: evenly sized parts (word-joined, so already unwrapped).
    words = text.split()
    chapters = []
    for i in range(0, len(words), PART_WORDS):
        chunk = " ".join(words[i:i + PART_WORDS])
        if len(chunk) > 200:
            chapters.append({"title": f"Part {len(chapters) + 1}", "text": chunk})
    return chapters


def _fetch_and_cache(book):
    info = BOOKS[book]
    url = f"https://www.gutenberg.org/cache/epub/{info['gutenberg_id']}/pg{info['gutenberg_id']}.txt"
    resp = requests.get(url, timeout=60, headers={"User-Agent": "summer-quest-reading-room"})
    resp.raise_for_status()
    resp.encoding = "utf-8"
    text = _strip_gutenberg_boilerplate(resp.text)
    chapters = _split_chapters(text)
    if not chapters:
        raise ValueError(f"could not extract chapters for {book}")
    for i, ch in enumerate(chapters):
        storage.set_json(_chapter_key(book, i), ch)
    meta = {"chapters": len(chapters), "titles": [c["title"] for c in chapters],
            "parser": PARSER_VERSION}
    storage.set_json(_meta_key(book), meta)
    return meta


def get_meta(book, fetch=False):
    """Cached chapter metadata; with fetch=True, downloads the book on a
    cache miss. A meta record from an older parser version counts as a miss,
    so parser fixes automatically re-fetch and re-parse on next open."""
    if book not in BOOKS:
        raise KeyError(book)
    meta = storage.get_json(_meta_key(book))
    if meta and meta.get("parser") != PARSER_VERSION:
        meta = None
    if meta or not fetch:
        return meta
    with _locks_guard:
        lock = _fetch_locks.setdefault(book, threading.Lock())
    with lock:
        # Re-check inside the lock WITH the version validation — a stale
        # v1 record must trigger the re-fetch, not satisfy it.
        meta = storage.get_json(_meta_key(book))
        if meta and meta.get("parser") == PARSER_VERSION:
            return meta
        return _fetch_and_cache(book)


def get_chapter(book, i):
    """(chapter dict, total chapters) — fetches the book on first access."""
    meta = get_meta(book, fetch=True)
    if not 0 <= i < meta["chapters"]:
        raise IndexError(i)
    ch = storage.get_json(_chapter_key(book, i))
    if ch is None:  # cache half-wiped somehow — re-fetch the whole book
        storage.store.delete(_meta_key(book))
        meta = get_meta(book, fetch=True)
        ch = storage.get_json(_chapter_key(book, i))
    return ch, meta["chapters"]
