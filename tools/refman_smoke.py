#!/usr/bin/env python3
"""
refman_smoke.py -- one-shot smoke test of an ingested reference manual.

Local mode (default): starts its own `wrangler dev`, runs the checks, kills it.
Run it AFTER `wrangler d1 execute ... --local` (don't import while a dev server
is running -- they share the local DB).

    python3 tools/refman_smoke.py RM0440
    python3 tools/refman_smoke.py RM0440 --q RCC_CR
    python3 tools/refman_smoke.py RM0456 --origin https://opendatasheet-mcp.opendatasheet.workers.dev

Checks: doc in index -> toc -> read one real section -> search returns a hit.
Exit 0 = all pass; non-zero with a FAIL line otherwise. No dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request


def get(url: str) -> dict:
    # explicit UA: Cloudflare 403s urllib's default on the public worker
    req = urllib.request.Request(url, headers={"User-Agent": "refman-smoke/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def pick_section(tree: list[dict]) -> dict:
    """A mid-document child section -- deep enough to prove real content."""
    mid = tree[len(tree) // 2]
    for node in (mid, *tree):
        kids = node.get("children") or []
        if kids:
            return kids[0]
    return mid


def pick_query(section_title: str) -> str:
    """Longest word of a real section title -- guaranteed to be in the doc."""
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", section_title)
    return max(words, key=len) if words else section_title.split()[0]


def run_checks(origin: str, doc: str, query: str | None) -> None:
    idx = get(f"{origin}/refman/index.json")
    row = next((d for d in idx.get("docs", []) if d.get("doc_id") == doc), None)
    if not row:
        fail(f"{doc} not in {origin}/refman/index.json "
             f"(has: {[d.get('doc_id') for d in idx.get('docs', [])]})")
    print(f"ok  index: {doc} rev {row['rev']} -- {row['title']!r}, "
          f"{row['pages']} pp, {row['section_count']} sections")

    toc = get(f"{origin}/refman/{doc}/toc?depth=2")
    tree = toc.get("tree") or []
    if not tree:
        fail("toc tree is empty")
    print(f"ok  toc: {len(tree)} top-level chapters")

    sec = pick_section(tree)
    body = get(f"{origin}/refman/{doc}/section/{urllib.parse.quote(sec['id'])}")
    if not (body.get("text") or "").strip():
        fail(f"section {sec['id']} has empty text")
    print(f"ok  read: §{body['id']} {body['title']!r} "
          f"pp.{body['page_start']}-{body['page_end']} "
          f"({len(body['text'])} chars, page 1/{body['page_count']})")

    q = query or pick_query(sec["title"])
    res = get(f"{origin}/refman/{doc}/search?q={urllib.parse.quote(q)}&limit=3")
    hits = res.get("hits") or []
    if not hits:
        fail(f"search {q!r} returned no hits")
    h = hits[0]
    print(f"ok  search {q!r}: §{h['id']} {h['title']!r} pp.{h['page_start']}-{h['page_end']}")
    print(f"\nPASS: {doc} looks healthy on {origin}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Smoke-test an ingested refman doc.")
    ap.add_argument("doc", help="document id, e.g. RM0440")
    ap.add_argument("--q", help="search query (default: derived from a section title)")
    ap.add_argument("--origin", help="test this origin instead of starting wrangler dev")
    ap.add_argument("--port", type=int, default=8799)
    args = ap.parse_args()

    if args.origin:
        run_checks(args.origin.rstrip("/"), args.doc, args.q)
        return

    origin = f"http://localhost:{args.port}"
    dev = subprocess.Popen(
        ["npx", "wrangler", "dev", "--port", str(args.port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # own process group: kills workerd children too
    )
    try:
        deadline = time.time() + 60
        while True:
            try:
                urllib.request.urlopen(origin, timeout=2)
                break
            except Exception:
                if dev.poll() is not None:
                    fail("wrangler dev exited early (is another dev server running?)")
                if time.time() > deadline:
                    fail("wrangler dev did not become ready in 60s")
                time.sleep(1)
        run_checks(origin, args.doc, args.q)
    finally:
        os.killpg(os.getpgid(dev.pid), signal.SIGTERM)


if __name__ == "__main__":
    main()
