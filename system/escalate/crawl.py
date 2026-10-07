"""Step 1: freeze a snapshot of the SNA documentation site.

Breadth-first crawl of same-site HTML pages. For each page we keep the title,
the "Updated on" date, the section (first URL segment) and the main content
converted to light Markdown (headings, lists, code, tables), discarding the
navigation and sidebar.
"""
import collections
import datetime
import hashlib
import re
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup, NavigableString

from .common import PAGES_FILE, SNAPSHOT, SNAPSHOT_META, load_config, norm_space, read_jsonl, write_json, write_jsonl

HTML_DIR = SNAPSHOT / "html"
MANIFEST = SNAPSHOT / "SNAPSHOT_MANIFEST.json"

SKIP_EXT = re.compile(r"\.(png|jpe?g|gif|svg|ico|css|js|pdf|zip|gz|tar|php|xml|txt)$", re.I)


def _canonical(url):
    p = urllib.parse.urlsplit(url)
    path = p.path or "/"
    if not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
        path += "/"
    return urllib.parse.urlunsplit((p.scheme, p.netloc, path, "", ""))


def _md(node):
    """Convert a content node to light Markdown."""
    out = []

    def walk(n, depth=0):
        if isinstance(n, NavigableString):
            out.append(str(n))
            return
        name = n.name
        if name in ("script", "style", "nav"):
            return
        if name in ("h1", "h2", "h3", "h4", "h5"):
            level = int(name[1])
            out.append(f"\n\n{'#' * max(level, 2)} {norm_space(n.get_text(' '))}\n\n")
            return
        if name == "pre":
            out.append("\n\n```\n" + n.get_text().strip("\n") + "\n```\n\n")
            return
        if name == "code":
            out.append("`" + n.get_text() + "`")
            return
        if name == "table":
            rows = []
            for tr in n.find_all("tr"):
                cells = [norm_space(c.get_text(" ")) for c in tr.find_all(["th", "td"])]
                if cells:
                    rows.append("| " + " | ".join(cells) + " |")
            if rows:
                out.append("\n\n" + "\n".join(rows) + "\n\n")
            return
        if name == "li":
            out.append("\n" + "  " * depth + "- ")
            for c in n.children:
                walk(c, depth + 1)
            return
        if name in ("p", "div", "ul", "ol", "br", "section"):
            out.append("\n")
        for c in n.children:
            walk(c, depth)
        if name in ("p", "div", "ul", "ol"):
            out.append("\n")

    walk(node)
    text = "".join(out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_date(text):
    m = re.search(r"Updated on (\d{1,2} \w{3} \d{4})", text)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1), "%d %b %Y").date().isoformat()
    except ValueError:
        return None


def parse_page(url, html):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("div.col-lg-9") or soup.body
    title_el = main.find("h2")
    title = norm_space(title_el.get_text(" ")) if title_el else (soup.title.get_text() if soup.title else url)
    content_el = main.select_one("div.content") or main
    meta = main.select_one("p.post-meta")
    path = urllib.parse.urlsplit(url).path.strip("/")
    return {
        "url": url,
        "path": "/" + path + ("/" if path else ""),
        "section": path.split("/")[0] if path else "home",
        "title": title,
        "updated": _parse_date(meta.get_text(" ") if meta else ""),
        "text": _md(content_el),
    }


def run(force=False):
    """Crawl and freeze. Refuses to overwrite an existing snapshot unless force=True
    (runbook Section 2 freeze policy: a re-crawl is a new snapshot version)."""
    if PAGES_FILE.exists() and not force:
        print(f"snapshot already frozen at {PAGES_FILE}; not re-crawling. "
              "Use `python -m escalate crawl --force` to create a new snapshot version.")
        return
    cfg = load_config()["corpus"]
    base = _canonical(cfg["base_url"])
    host = urllib.parse.urlsplit(base).netloc
    session = requests.Session()
    session.headers["User-Agent"] = cfg["user_agent"]
    queue, seen, pages, raw = collections.deque([base]), set(), [], {}
    while queue and len(pages) < cfg["max_pages"]:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        path = urllib.parse.urlsplit(url).path
        if SKIP_EXT.search(path) or any(path.startswith(p) for p in cfg["exclude_prefixes"]):
            continue
        try:
            r = session.get(url, timeout=20)
        except requests.RequestException as e:
            print(f"  skip {url}: {e}")
            continue
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
            continue
        page = parse_page(url, r.text)
        if page["text"]:
            raw[page["url"]] = (r.content, datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))
            pages.append(page)
            print(f"  [{len(pages):3d}] {page['path']}  ({len(page['text'].split())} words, updated {page['updated']})")
        for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
            link = _canonical(urllib.parse.urljoin(url, a["href"]))
            if urllib.parse.urlsplit(link).netloc == host and link not in seen:
                queue.append(link)
        time.sleep(cfg["delay_seconds"])
    pages.sort(key=lambda p: p["path"])
    for i, p in enumerate(pages):
        p["page_id"] = f"p{i:03d}"
    write_jsonl(PAGES_FILE, pages)
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    for f in HTML_DIR.glob("*.html"):
        f.unlink()
    manifest = []
    for p in pages:
        content, retrieved = raw[p["url"]]
        (HTML_DIR / f"{p['page_id']}.html").write_bytes(content)
        manifest.append({"page_id": p["page_id"], "url": p["url"], "section": p["section"], "retrieved_utc": retrieved,
                         "sha256_html": hashlib.sha256(content).hexdigest(),
                         "sha256_text": hashlib.sha256(p["text"].encode("utf-8")).hexdigest(),
                         "html_file": f"data/snapshot/html/{p['page_id']}.html"})
    write_json(MANIFEST, {"pages": manifest})
    digest = hashlib.sha256("".join(p["url"] + p["text"] for p in pages).encode("utf-8")).hexdigest()
    write_json(SNAPSHOT_META, {
        "base_url": base,
        "crawled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "pages": len(pages),
        "words": sum(len(p["text"].split()) for p in pages),
        "content_sha256": digest,
    })
    print(f"snapshot: {len(pages)} pages -> {PAGES_FILE}")


def verify():
    """Re-hash every frozen page against SNAPSHOT_MANIFEST.json (runbook Section 2, last step)."""
    import json
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))["pages"]
    texts = {p["page_id"]: p["text"] for p in read_jsonl(PAGES_FILE)}
    bad = []
    for m in man:
        html = (HTML_DIR / f"{m['page_id']}.html").read_bytes()
        if hashlib.sha256(html).hexdigest() != m["sha256_html"]:
            bad.append((m["page_id"], "html"))
        if hashlib.sha256(texts[m["page_id"]].encode("utf-8")).hexdigest() != m["sha256_text"]:
            bad.append((m["page_id"], "text"))
    print(f"verified {len(man)} pages against {MANIFEST.name}: " + ("all hashes match" if not bad else f"MISMATCH {bad}"))
    return not bad
