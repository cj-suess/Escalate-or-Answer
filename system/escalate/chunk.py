"""Step 2: split each page into heading-scoped chunks of at most max_words."""
import re

from .common import CHUNKS_FILE, PAGES_FILE, load_config, read_jsonl, write_jsonl


def _sections(text):
    """Yield (heading, body) pairs split on Markdown headings."""
    heading, buf = "", []
    for line in text.splitlines():
        m = re.match(r"^#{2,6}\s+(.*)", line)
        if m:
            if "".join(buf).strip():
                yield heading, "\n".join(buf).strip()
            heading, buf = m.group(1).strip(), []
        else:
            buf.append(line)
    if "".join(buf).strip():
        yield heading, "\n".join(buf).strip()


def _pack(body, max_words):
    """Pack paragraphs (blank-line separated; code blocks kept whole) into pieces of <= max_words."""
    paras = re.split(r"\n\s*\n", body)
    pieces, cur = [], []
    for p in paras:
        words = len(p.split())
        if cur and sum(len(x.split()) for x in cur) + words > max_words:
            pieces.append("\n\n".join(cur))
            cur = []
        cur.append(p)
    if cur:
        pieces.append("\n\n".join(cur))
    return pieces


def run():
    cfg = load_config()["chunking"]
    chunks = []
    for page in read_jsonl(PAGES_FILE):
        n = 0
        for heading, body in _sections(page["text"]):
            for piece in _pack(body, cfg["max_words"]):
                if len(piece.split()) < cfg["min_words"]:
                    continue
                chunks.append({
                    "chunk_id": f"{page['page_id']}-c{n:02d}",
                    "page_id": page["page_id"],
                    "url": page["url"],
                    "path": page["path"],
                    "section": page["section"],
                    "title": page["title"],
                    "updated": page["updated"],
                    "heading": heading,
                    "text": piece,
                })
                n += 1
    write_jsonl(CHUNKS_FILE, chunks)
    print(f"chunks: {len(chunks)} -> {CHUNKS_FILE}")
