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
PARSER_VERSION = 5

_fetch_locks = {}
_locks_guard = threading.Lock()


def _meta_key(book):
    return f"book:{book}:meta"


def _chapter_key(book, i):
    return f"book:{book}:ch:{i}"


def _strip_gutenberg_boilerplate(text):
    # Gutenberg plain-text files use \r\n line endings; every regex below
    # assumes bare \n, so normalize FIRST (this bit us in parser v4: the
    # two-line chapter pattern could never match \n\r\n).
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    start = re.search(r"\*\*\* ?START OF (?:THE|THIS) PROJECT GUTENBERG.*?\*\*\*", text)
    if start:
        text = text[start.end():]
    end = re.search(r"\*\*\* ?END OF (?:THE|THIS) PROJECT GUTENBERG.*", text)
    if end:
        text = text[: end.start()]
    return text.strip()


# Chapter headings across these eight books: "CHAPTER I.", "Chapter 1",
# "ADVENTURE I.", or a bare roman numeral line like "I. A SCANDAL IN BOHEMIA".
# The bare-numeral form forbids dots in the title tail so an initials
# signature like "L.F.B." (which is all roman-numeral letters!) can't match.
_HEADING_RE = re.compile(
    r"^(?:(?:CHAPTER|Chapter|ADVENTURE|Adventure|STORY|Story)\s+[IVXLCivxlc\d]+\.?[^\n]{0,80}"
    r"|(?=[IVXLC]{0,6}[IVX])[IVXLC]+\.\s{0,3}[A-Z][A-Za-z0-9'’&,;:\- ]{2,78}"
    r"| {0,3}\d{1,2}\. {1,3}[A-Z][A-Za-z0-9'’&,;:\- ]{2,70})$",
    re.M,
)

# A bare heading like "Chapter I" / "CHAPTER XII." with no title of its own;
# some editions put the title on the next line instead.
_BARE_HEADING_RE = re.compile(
    r"(?:CHAPTER|Chapter|ADVENTURE|Adventure|STORY|Story)\s+[IVXLCivxlc\d]+\.?"
)
# The next-line title: capitalized, short, and followed by a blank line
# (hard-wrapped body lines are never followed by a blank line mid-sentence).
_NEXT_LINE_TITLE_RE = re.compile(
    r"\n*([A-Z“\"'][^\n]{1,78}[^\s.!?…])\n\s*\n"
)

# Two-line chapter headings (Treasure Island's edition): a line holding ONLY
# the chapter number — digits or a roman numeral (a lone "I" is safe here:
# it must sit alone between blank lines with a capitalized title line right
# after, which prose and poems don't do) — then blank line(s), then the
# title. Only tried when the one-line patterns find nothing.
_TWO_LINE_RE = re.compile(
    r"\n\n(\d{1,2}|[IVXLC]{1,7})\n+([A-Z“\"'][^\n]{2,70})\n"
)

# Part dividers ("PART ONE--The Old Buccaneer") that sit between chapters in
# the body text; scrubbed from chapter bodies so they don't dangle at the
# end of the preceding chapter.
_PART_LINE_RE = re.compile(
    r"^\s*(?:PART|Part)\s+(?:ONE|TWO|THREE|FOUR|FIVE|SIX|[IVXLC\d]+)[^\n]{0,40}$"
)

# Looser patterns for scrubbing table-of-contents listings out of front
# matter (and out of Part-fallback text): numbered entries, PART dividers,
# and dot-leader lines ending in a page number.
_TOC_LINE_RE = re.compile(
    r"^\s*(?:Contents|CONTENTS|Table of Contents"
    r"|(?:PART|Part)\s+(?:ONE|TWO|THREE|FOUR|FIVE|SIX|[IVXLC\d]+)[^\n]{0,40}"
    r"|(?:CHAPTER|Chapter|ADVENTURE|Adventure|STORY|Story)?\s*[IVXLC\d]+\.?\s+\S[^\n]{0,80}"
    r"|[^\n]{0,80}(?:\.\s+){3,}\.?\s*\d{1,4})\s*$"
)

PART_WORDS = 1800  # fallback segment size when no chapter structure is found


def _unwrap(text):
    """Gutenberg plain text is hard-wrapped at ~70 columns. Rejoin lines
    within each paragraph (blank lines still separate paragraphs) so the
    reader reflows naturally on any screen width — EXCEPT mostly-indented
    blocks (verse, songs, letters, signs), whose line breaks are the point;
    those keep them (the frontend renders \\n inside a paragraph)."""
    out = []
    for p in re.split(r"\n\s*\n", text):
        if not p.strip():
            continue
        lines = [ln for ln in p.split("\n") if ln.strip()]
        if sum(1 for ln in lines if ln.startswith("  ")) > len(lines) // 2:
            out.append("\n".join(ln.strip() for ln in lines))
        else:
            out.append(re.sub(r"\s*\n\s*", " ", p).strip())
    return "\n\n".join(out)


_CH_NUM_RE = re.compile(
    r"(?:chapter|adventure|story)?\s*([ivxlc]+|\d+)\b", re.IGNORECASE
)


def _heading_key(heading):
    """'Chapter IV. The Road…' -> 'iv' — the chapter's number token, used to
    spot a table-of-contents entry duplicating a real heading later on."""
    m = _CH_NUM_RE.match(heading.strip().lower())
    return m.group(1) if m else None


def _front_matter(text):
    """Everything before the first real chapter: author's introduction,
    dedication, etc. The Contents listing is scrubbed (the app's chapter nav
    IS the table of contents): everything from a Contents heading onward is
    cut — the listing is always the last thing before chapter one — and any
    stray ToC-shaped lines go too. What remains becomes an 'Introduction'
    chapter if it's substantial, else it's dropped."""
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        ln = lines[i]
        if re.match(r"^\s*(?:Contents|CONTENTS|Table of Contents)\s*$", ln):
            # Eat the listing that follows: blanks, ToC-shaped lines, and
            # short title fragments — until real prose resumes (some
            # editions put an introduction AFTER the Contents).
            i += 1
            while i < len(lines) and (not lines[i].strip()
                                      or _TOC_LINE_RE.match(lines[i])
                                      or len(lines[i].strip()) < 60):
                i += 1
            continue
        if (not _TOC_LINE_RE.match(ln)
                and not ln.strip().startswith("Produced by")
                and ln.strip().lower() != "by"):
            out.append(ln)
        i += 1
    body = _unwrap("\n".join(out))
    if len(body) < 500:
        return None
    return {"title": "Introduction", "text": body}


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

    def _cluster_filter(ms):
        # ToC entries come packed tightly; a heading followed by another
        # within 500 chars is a listing line, not a chapter. The FINAL
        # match is always kept — a short closing chapter near EOF is real
        # (Oz's 'Home Again' is only ~480 chars from the end).
        kept = []
        for i, m in enumerate(ms):
            if i + 1 == len(ms) or ms[i + 1].start() - m.start() >= 500:
                kept.append(m)
        return kept

    boundaries = _cluster_filter(matches)
    heading_of = lambda m: m.group(0)
    if len(boundaries) < 3:
        # One-line headings failed — try the two-line form ("1" \n title).
        matches = list(_TWO_LINE_RE.finditer(text))
        boundaries = _cluster_filter(matches)
        heading_of = lambda m: f"Chapter {m.group(1)}. {m.group(2).strip()}"
    # ToC-tail dedupe: when only a FEW chapter numbers appear twice, the
    # early copies are stray table-of-contents entries — keep the LAST
    # occurrence. But when MOST numbers repeat, the book's parts restart
    # their numbering (Twenty Thousand Leagues) and every heading is real,
    # so skip the dedupe entirely.
    keys = [_heading_key(heading_of(m)) for m in boundaries]
    counts = {}
    for k in keys:
        if k is not None:
            counts[k] = counts.get(k, 0) + 1
    dup_instances = sum(c for c in counts.values() if c > 1)
    if 0 < dup_instances <= len(boundaries) // 2:
        last_seen = {k: i for i, (m, k) in enumerate(zip(boundaries, keys))
                     if k is not None}
        boundaries = [m for i, (m, k) in enumerate(zip(boundaries, keys))
                      if k is None or last_seen[k] == i]
    if len(boundaries) >= 3:
        chapters = []
        front = _front_matter(text[: boundaries[0].start()])
        if front:
            chapters.append(front)
        for i, m in enumerate(boundaries[:60]):
            end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(text)
            title = re.sub(r"\s+", " ", heading_of(m)).strip()
            body_start = m.end()
            if _BARE_HEADING_RE.fullmatch(title):
                # "Chapter I" with the real title on the following line(s)
                # (Tarzan, Twenty Thousand Leagues, Around the World) —
                # fold it in. Single mixed-case line, or an ALL-CAPS block
                # of up to 3 wrapped lines; both must end at a blank line,
                # which body prose never does mid-sentence.
                seg = text[m.end():m.end() + 320]
                tm = _NEXT_LINE_TITLE_RE.match(seg)
                picked = tm.group(1).strip() if tm else None
                if not picked:
                    bm = re.match(r"\n+((?:[^\n]{2,79}\n){1,3})\s*\n", seg)
                    if bm:
                        blk = " ".join(bm.group(1).split())
                        if blk == blk.upper() and any(c.isalpha() for c in blk):
                            picked, tm = blk, bm
                if picked:
                    title = f"{title.rstrip('.')}. {picked}"
                    body_start = m.end() + tm.end()
            raw = text[body_start:end]
            raw = "\n".join(ln for ln in raw.split("\n")
                            if not _PART_LINE_RE.match(ln))
            body = _unwrap(raw)
            if len(body) > 200:
                chapters.append({"title": title, "text": body})
        if len(chapters) >= 3:
            return chapters
    # Fallback: evenly sized parts, split at PARAGRAPH boundaries so books
    # without detectable chapters still read as normal prose. ToC listings
    # are scrubbed first (dot-leader lines are never prose).
    clean = "\n".join(ln for ln in text.split("\n") if not _TOC_LINE_RE.match(ln))
    paras = [p for p in _unwrap(clean).split("\n\n") if p.strip()]
    chapters, cur, count = [], [], 0
    for p in paras:
        cur.append(p)
        count += len(p.split())
        if count >= PART_WORDS:
            chapters.append({"title": f"Part {len(chapters) + 1}",
                             "text": "\n\n".join(cur)})
            cur, count = [], 0
    if cur:
        tail = "\n\n".join(cur)
        if chapters and count < PART_WORDS // 3:
            chapters[-1]["text"] += "\n\n" + tail  # fold a short tail in
        elif len(tail) > 200:
            chapters.append({"title": f"Part {len(chapters) + 1}", "text": tail})
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
