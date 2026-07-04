// refman: reference-manual sections served from D1. One query layer, two skins:
// the GET /refman/* routes here and the refman_* MCP tools in tools.ts both call
// the exported query functions. Doc ids (RM0456) are opaque data — no vendor
// logic anywhere (RULE 0).

export interface Env {
  REFMAN_DB: D1Database;
}

// Section text is served in fixed-size character pages so one read stays a
// bounded tool result; long chapters take a `page` parameter.
const TEXT_PAGE_CHARS = 12_000;

// Thrown by the query layer for client errors; carries the HTTP status the
// route skin should use. The MCP skin surfaces just the message.
export class RefmanError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

type TreeNode = {
  id: string;
  title: string;
  page_start: number;
  page_end: number;
  children: TreeNode[];
};

async function docRow(env: Env, doc: string): Promise<any> {
  const row = await env.REFMAN_DB.prepare(
    "SELECT doc_id, title, rev, pages, section_count, tree_json FROM docs WHERE doc_id = ?1"
  )
    .bind(doc)
    .first();
  if (!row) {
    const all = await env.REFMAN_DB.prepare("SELECT doc_id FROM docs ORDER BY doc_id").all();
    const available = (all.results ?? []).map((r: any) => r.doc_id).join(", ") || "(none)";
    throw new RefmanError(`unknown doc: ${doc}. Available: ${available}`, 404);
  }
  return row;
}

export async function refmanIndex(env: Env): Promise<object> {
  const res = await env.REFMAN_DB.prepare(
    "SELECT doc_id, title, rev, pages, section_count FROM docs ORDER BY doc_id"
  ).all();
  return { docs: res.results ?? [] };
}

export async function refmanToc(env: Env, doc: string, depth: number): Promise<object> {
  const d = Math.min(6, Math.max(1, Number.isFinite(depth) ? Math.trunc(depth) : 2));
  const row = await docRow(env, doc);
  const prune = (nodes: TreeNode[], level: number): TreeNode[] =>
    nodes.map((n) => ({
      ...n,
      children: level < d ? prune(n.children ?? [], level + 1) : [],
    }));
  return { doc: row.doc_id, rev: row.rev, tree: prune(JSON.parse(row.tree_json), 1) };
}

// Numeric-aware section-id order: 11.10 sorts after 11.9.
function idCompare(a: string, b: string): number {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (d !== 0) return d;
  }
  return 0;
}

export async function refmanSection(env: Env, doc: string, id: string, page: number): Promise<object> {
  const meta = await docRow(env, doc);
  const row = await env.REFMAN_DB.prepare(
    "SELECT id, title, page_start, page_end, body FROM sections WHERE doc_id = ?1 AND id = ?2"
  )
    .bind(doc, id)
    .first<any>();
  if (!row) throw new RefmanError(`unknown section: ${id} in ${doc}. Try /refman/${doc}/toc`, 404);

  const body: string = row.body ?? "";
  const pageCount = Math.max(1, Math.ceil(body.length / TEXT_PAGE_CHARS));
  const p = Number.isFinite(page) ? Math.trunc(page) : 1;
  if (p < 1 || p > pageCount) {
    throw new RefmanError(`page ${p} out of range for ${doc} §${id} (page_count ${pageCount})`, 400);
  }

  // Direct children only: '11.8.%' without a further dot. The trailing dot in
  // the prefix keeps 11.80.* from matching 11.8.*.
  const kids = await env.REFMAN_DB.prepare(
    "SELECT id, title FROM sections WHERE doc_id = ?1 AND id LIKE ?2 AND id NOT LIKE ?3"
  )
    .bind(doc, `${id}.%`, `${id}.%.%`)
    .all();
  const children = ((kids.results ?? []) as { id: string; title: string }[]).sort((a, b) =>
    idCompare(a.id, b.id)
  );

  return {
    doc: meta.doc_id,
    id: row.id,
    title: row.title,
    rev: meta.rev,
    page_start: row.page_start,
    page_end: row.page_end,
    page: p,
    page_count: pageCount,
    children,
    text: body.slice((p - 1) * TEXT_PAGE_CHARS, p * TEXT_PAGE_CHARS),
  };
}

// FTS5 MATCH throws on unbalanced quotes/parens, so never pass raw user text:
// every whitespace token is double-quoted (inner quotes doubled), joined with
// spaces (implicit AND).
function ftsQuery(raw: string): string {
  return raw
    .split(/\s+/)
    .filter((t) => t.length > 0)
    .map((t) => `"${t.replace(/"/g, '""')}"`)
    .join(" ");
}

export async function refmanSearch(env: Env, doc: string, q: string, limit: number): Promise<object> {
  const meta = await docRow(env, doc);
  const query = ftsQuery(q ?? "");
  if (!query) throw new RefmanError("missing/empty q", 400);
  const lim = Math.min(20, Math.max(1, Number.isFinite(limit) ? Math.trunc(limit) : 5));

  // page_start/page_end live on `sections` (the FTS table indexes only
  // title/body), hence the join; snippet/bm25 still address the FTS table.
  // bm25's two leading zeros are the UNINDEXED columns; 5.0 weights title 5x
  // over body (heading boost). SQLite bm25 is lower-is-better, so ORDER BY
  // score ascending already ranks best-first.
  let hits: object[] = [];
  try {
    const res = await env.REFMAN_DB.prepare(
      `SELECT sections_fts.id AS id, sections_fts.title AS title,
              s.page_start AS page_start, s.page_end AS page_end,
              snippet(sections_fts, 3, '', '', ' … ', 32) AS snippet,
              bm25(sections_fts, 0, 0, 5.0, 1.0) AS score
       FROM sections_fts
       JOIN sections s ON s.doc_id = sections_fts.doc_id AND s.id = sections_fts.id
       WHERE sections_fts MATCH ?1 AND sections_fts.doc_id = ?2
       ORDER BY score
       LIMIT ?3`
    )
      .bind(query, doc, lim)
      .all();
    hits = res.results ?? [];
  } catch {
    hits = []; // defensive: a MATCH parse error is "no hits", never a 500
  }
  return { doc: meta.doc_id, hits };
}

// Route skin. Returns null when the path isn't a refman route.
export async function handleRefmanGet(
  url: URL,
  env: Env,
  json: (body: unknown, status?: number, headers?: Record<string, string>) => Response
): Promise<Response | null> {
  const path = url.pathname;
  try {
    if (path === "/refman/index.json") {
      return json(await refmanIndex(env), 200, { "cache-control": "public, max-age=3600" });
    }
    let m = path.match(/^\/refman\/([^/]+)\/toc$/);
    if (m) {
      const depth = Number(url.searchParams.get("depth") ?? "2");
      return json(await refmanToc(env, m[1], depth), 200, { "cache-control": "public, max-age=86400" });
    }
    m = path.match(/^\/refman\/([^/]+)\/section\/([^/]+)$/);
    if (m) {
      const page = Number(url.searchParams.get("page") ?? "1");
      return json(await refmanSection(env, m[1], m[2], page), 200, {
        "cache-control": "public, max-age=86400",
      });
    }
    m = path.match(/^\/refman\/([^/]+)\/search$/);
    if (m) {
      const q = url.searchParams.get("q") ?? "";
      const limit = Number(url.searchParams.get("limit") ?? "5");
      if (!q.trim()) return json({ error: "missing/empty q" }, 400);
      return json(await refmanSearch(env, m[1], q, limit), 200, { "cache-control": "no-store" });
    }
    if (path.startsWith("/refman/")) {
      return json({ error: `unknown refman route: ${path}` }, 404);
    }
    return null;
  } catch (e: any) {
    if (e instanceof RefmanError) return json({ error: e.message }, e.status);
    return json({ error: e?.message ?? String(e) }, 500);
  }
}
