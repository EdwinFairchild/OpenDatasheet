#!/usr/bin/env python3
"""
refman_ingest.py -- turn a reference-manual PDF into the refman service's data:
a manifest (outline tree), a sections JSONL, and a D1 import SQL file.

The refman service serves *sections*, not pages: the PDF outline gives every
numbered section a title and a start page; each section's text is the page
range up to the next numbered section. Fidelity is page-granular by design --
a section's first/last page may carry a neighbor's tail/head. That is accepted;
do not try to trim at heading boundaries.

    python3 tools/refman_ingest.py datasheets/stm32u575/RM0456.pdf \
        --doc RM0456 --rev 6 \
        --title "STM32U5 series Arm-based 32-bit MCUs reference manual"

Outputs (default --out build/refman/, git-ignored):
    {doc}.manifest.json    doc identity + nested section tree
    {doc}.sections.jsonl   one {id, title, page_start, page_end, text} per line
    {doc}.import.sql       idempotent D1 import (DELETE doc rows, then INSERT)

Hosting ingested vendor text is a licensing decision, so --doc must be a key in
tools/refman_allowlist.json; add docs there deliberately, never ad hoc.

Needs `pypdf` (pip) for the outline and `pdftotext` (poppler-utils) for text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+)$")

# D1 rejects any single SQL statement over 100 KB (SQLITE_TOOBIG), locally and
# remotely, so batching is by statement SIZE, not row count. Values too big for
# one statement (register-map sections reach ~490 KB; a big RM's tree_json is
# ~300 KB) are inserted in chunks: INSERT the head, then `SET col = col || …`
# appends. TEXT_CHUNK is unescaped chars; quote-doubling can at most double it,
# keeping every statement comfortably under MAX_STMT.
MAX_STMT = 90_000
TEXT_CHUNK = 40_000


def die(msg: str) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def check_deps() -> None:
    try:
        import pypdf  # noqa: F401
    except ImportError:
        die("pypdf missing -- install with: pip3 install pypdf")
    if shutil.which("pdftotext") is None:
        die("pdftotext missing -- install with: sudo apt install poppler-utils")


def load_allowlist(tools_dir: Path) -> dict:
    path = tools_dir / "refman_allowlist.json"
    if not path.exists():
        die(f"{path} not found")
    return json.loads(path.read_text())


def walk_outline(reader) -> list[dict]:
    """Flatten the PDF outline into numbered sections, document order.

    Each entry: {id, title, page_start} (page_start 1-based). Entries whose
    titles don't start with a section number (cover, list of tables, legal)
    are skipped, as are entries with broken destinations.
    """
    sections: list[dict] = []

    def visit(items) -> None:
        for item in items:
            if isinstance(item, list):
                visit(item)
                continue
            title = str(getattr(item, "title", "") or "").strip()
            m = SECTION_RE.match(title)
            if not m:
                continue
            try:
                page_idx = reader.get_destination_page_number(item)
            except Exception as e:  # noqa: BLE001 -- broken dest: skip, keep going
                print(f"warning: skipping outline entry {title!r}: {e}", file=sys.stderr)
                continue
            sections.append({"id": m.group(1), "title": m.group(2).strip(), "page_start": page_idx + 1})

    visit(reader.outline)
    return sections


def assign_page_ranges(sections: list[dict], total_pages: int) -> None:
    """[own_start, next_numbered_start) in document order -- ANY numbered entry
    bounds the previous one, so a parent owns only its intro pages. Stored
    1-based inclusive; a section that shares its start page with the next one
    still owns that page (page-granular fidelity)."""
    for i, sec in enumerate(sections):
        if i + 1 < len(sections):
            sec["page_end"] = max(sec["page_start"], sections[i + 1]["page_start"] - 1)
        else:
            sec["page_end"] = total_pages


def extract_text(pdf: Path, page_start: int, page_end: int) -> str:
    out = subprocess.run(
        ["pdftotext", "-layout", "-f", str(page_start), "-l", str(page_end), str(pdf), "-"],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if out.returncode != 0:
        die(f"pdftotext failed on pages {page_start}-{page_end}: {out.stderr.strip()}")
    text = out.stdout.replace("\x00", "").replace("\xa0", " ")
    lines = [ln.rstrip() for ln in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


def validate(sections: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for sec in sections:
        if sec["id"] in seen:
            print(f"warning: duplicate section id {sec['id']} -- keeping the first", file=sys.stderr)
            continue
        seen.add(sec["id"])
        unique.append(sec)
    prev = 0
    for sec in unique:
        if sec["page_start"] < prev:
            die(f"section {sec['id']} page_start {sec['page_start']} decreases (prev {prev})")
        prev = sec["page_start"]
    if len(unique) < 500:
        print(f"warning: only {len(unique)} sections -- reference manuals have thousands", file=sys.stderr)
    return unique


def build_tree(sections: list[dict]) -> list[dict]:
    """Nest by id: 11.8.3 is a child of 11.8. Document order preserved; an
    orphan (parent id absent from the outline) attaches at the root."""
    nodes = {
        s["id"]: {"id": s["id"], "title": s["title"], "page_start": s["page_start"],
                  "page_end": s["page_end"], "children": []}
        for s in sections
    }
    roots: list[dict] = []
    for s in sections:
        node = nodes[s["id"]]
        parent_id = s["id"].rsplit(".", 1)[0] if "." in s["id"] else None
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _chunks(text: str, size: int = TEXT_CHUNK) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def emit_import_sql(doc: str, title: str, rev: str, sha256: str, pages: int,
                    sections: list[dict], tree: list[dict]) -> str:
    """Plain statements, no explicit transaction (D1's HTTP import dislikes
    them); leading DELETEs make re-import idempotent. Every statement stays
    under MAX_STMT (see the D1 note above). The FTS table is populated
    server-side from `sections` in one INSERT..SELECT — no duplicated text in
    the import file."""
    q = sql_quote
    stmts = [
        f"DELETE FROM sections_fts WHERE doc_id={q(doc)};",
        f"DELETE FROM sections WHERE doc_id={q(doc)};",
        f"DELETE FROM docs WHERE doc_id={q(doc)};",
    ]

    tree_chunks = _chunks(json.dumps(tree, separators=(",", ":")))
    stmts.append(
        "INSERT INTO docs (doc_id,title,rev,pdf_sha256,pages,section_count,tree_json,ingested_at) VALUES "
        f"({q(doc)},{q(title)},{q(rev)},{q(sha256)},{pages},{len(sections)},"
        f"{q(tree_chunks[0])},"
        f"{q(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))});"
    )
    stmts.extend(
        f"UPDATE docs SET tree_json = tree_json || {q(c)} WHERE doc_id={q(doc)};"
        for c in tree_chunks[1:]
    )

    head = "INSERT INTO sections (doc_id,id,title,page_start,page_end,body) VALUES\n"
    pending: list[str] = []
    pending_len = len(head)

    def flush() -> None:
        nonlocal pending, pending_len
        if pending:
            stmts.append(head + ",\n".join(pending) + ";")
        pending, pending_len = [], len(head)

    for s in sections:
        prefix = f"({q(doc)},{q(s['id'])},{q(s['title'])},{s['page_start']},{s['page_end']},"
        if len(prefix) + 2 * len(s["text"]) + 8 > MAX_STMT:
            # body too big for any single statement: insert head, append rest
            flush()
            body_chunks = _chunks(s["text"])
            stmts.append(head + prefix + q(body_chunks[0]) + ");")
            stmts.extend(
                f"UPDATE sections SET body = body || {q(c)} "
                f"WHERE doc_id={q(doc)} AND id={q(s['id'])};"
                for c in body_chunks[1:]
            )
            continue
        row = prefix + q(s["text"]) + ")"
        if pending and pending_len + len(row) + 2 > MAX_STMT:
            flush()
        pending.append(row)
        pending_len += len(row) + 2
    flush()

    stmts.append(
        "INSERT INTO sections_fts (doc_id,id,title,body) "
        f"SELECT doc_id, id, title, body FROM sections WHERE doc_id={q(doc)};"
    )
    return "\n".join(stmts) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest a reference-manual PDF for the refman service.")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--doc", required=True, help="document id, e.g. RM0456")
    ap.add_argument("--rev", required=True, help="document revision, e.g. 6")
    ap.add_argument("--title", required=True)
    ap.add_argument("--out", type=Path, default=Path("build/refman"))
    args = ap.parse_args()

    check_deps()
    if not args.pdf.exists():
        die(f"{args.pdf}: no such file")

    allowlist = load_allowlist(Path(__file__).resolve().parent)
    if args.doc not in allowlist:
        die(
            f"{args.doc} is not in refman_allowlist.json -- hosting ingested vendor "
            "text is a licensing decision; add it deliberately."
        )

    from pypdf import PdfReader

    pdf_bytes = args.pdf.read_bytes()
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    reader = PdfReader(args.pdf)
    total_pages = len(reader.pages)
    print(f"{args.pdf.name}: {total_pages} pages, sha256 {sha256[:12]}…")

    sections = walk_outline(reader)
    assign_page_ranges(sections, total_pages)
    sections = validate(sections)
    print(f"outline: {len(sections)} numbered sections")

    for i, sec in enumerate(sections):
        sec["text"] = extract_text(args.pdf, sec["page_start"], sec["page_end"])
        if (i + 1) % 250 == 0:
            print(f"  text: {i + 1}/{len(sections)} sections")

    tree = build_tree(sections)
    args.out.mkdir(parents=True, exist_ok=True)

    manifest = {
        "doc_id": args.doc,
        "title": args.title,
        "rev": args.rev,
        "pdf_sha256": sha256,
        "pages": total_pages,
        "section_count": len(sections),
        "tree": tree,
    }
    manifest_path = args.out / f"{args.doc}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=1) + "\n")

    jsonl_path = args.out / f"{args.doc}.sections.jsonl"
    with jsonl_path.open("w") as f:
        for sec in sections:
            f.write(json.dumps(
                {"id": sec["id"], "title": sec["title"], "page_start": sec["page_start"],
                 "page_end": sec["page_end"], "text": sec["text"]},
                separators=(",", ":"),
            ) + "\n")

    sql_path = args.out / f"{args.doc}.import.sql"
    sql_path.write_text(emit_import_sql(
        args.doc, args.title, args.rev, sha256, total_pages, sections, tree
    ))

    print(f"wrote {manifest_path}")
    print(f"wrote {jsonl_path} ({len(sections)} lines)")
    print(f"wrote {sql_path} ({sql_path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
