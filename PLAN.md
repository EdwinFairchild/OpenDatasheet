# Implementation plan — static part-file serving

**For the agent picking this up:** read `src/index.ts`, `src/lib.ts`, and `src/tools.ts`
first. This plan adds **one capability** to the worker. It does **not** rewrite the
existing MCP server — that stays exactly as it is.

---

## Why this change exists

The worker today speaks **only MCP** (JSON-RPC 2.0 over `POST /`). Every `GET`
path returns the same server banner. None of the 11 MCP tools return a *whole
part document* — they return narrow query results (`get_register`,
`query_electrical`, a capability index from `describe_part`, etc.).

A new consumer — the **BluePill harness** — needs to **fetch the entire part
JSON, cache it on disk, and resolve queries locally and offline**. It is a
consumer of the *data format*, not an MCP client. It cannot use the MCP surface:
there is no "give me the whole part" tool, and it doesn't want a live RPC round
trip per query.

So we add a **static raw-file route** alongside MCP. One dataset, two bindings:

```
data/*.json  ─┬─►  MCP tools/call   (POST /)        → Claude Desktop, Cursor, live-query agents
              └─►  GET /parts/{file}.json           → BluePill fetcher (fetch once, cache, own, offline)
```

This is the OpenDatasheet thesis in `docs/00-MISSION.md`: *"MCP is the first
binding, not the only one — the same data can be a file on disk."*

---

## What the BluePill fetcher actually requests

This is the load-bearing detail. Get it wrong and the harness silently fails to
cache. The harness fetcher does exactly this (see
`BluePill/stm32_harness/parts/fetch.py`):

1. `GET {origin}/parts/{MPN}.json`
   where `{MPN}` is the **manufacturer part number**, e.g. `ACME-IMU6`
   — **not** the data filename (`acme-imu6.json`).
2. Parses the returned JSON, reads `part.errata[].ref` (e.g. `"./acme-imu6-errata.json"`),
   takes the **basename** of each ref, and for each:
   `GET {origin}/parts/{ref-basename}`
   e.g. `GET {origin}/parts/acme-imu6-errata.json`.

So the route must resolve **two kinds of name** under `/parts/`:

| Request | Resolves to | Match rule |
|---|---|---|
| `/parts/ACME-IMU6.json` | `data/acme-imu6.json` | strip `.json`, match against each part doc's `part.mpn` **case-insensitively** |
| `/parts/acme-imu6-errata.json` | `data/acme-imu6-errata.json` | match the literal data filename (these are errata overlays; they have no `mpn`) |

The mismatch between **filename** (`acme-imu6.json`) and **MPN**
(`ACME-IMU6`) is the #1 place a naive implementation breaks. The harness will
request the MPN; do not assume the URL path equals the filename.

> Note: the part documents reference errata with relative refs like
> `"./acme-imu6-errata.json"`. **Keep those refs as-is** — the harness resolves
> the basename against the same `/parts/` origin, so the server serving them by
> filename is exactly what's needed. Do not rewrite refs to absolute URLs.

---

## The change

**File:** `src/index.ts` — add a `GET /parts/...` branch **before** the existing
GET banner logic, leaving `POST /` (MCP) and the OPTIONS/CORS handling untouched.

**Data access:** reuse what `src/lib.ts` already imports. `lib.ts` imports the
four `data/*.json` files at build time and exposes `getRawPart(mpn)`,
`listMpns()`, `getErrataOverlays(mpn)`. For the static route you need raw bytes
by *requested name*, so add a small resolver in `lib.ts` (keeps `index.ts` thin
and matches the existing "domain logic lives in lib.ts" split):

```ts
// src/lib.ts — add alongside the existing exports.
//
// Build a name→document map covering BOTH lookup keys the harness uses:
//   - "<MPN>.json"        (case-insensitive) → the part document
//   - "<errata-file>.json"                    → the errata overlay, by its data filename
//
// Import the errata docs as named modules (m0Errata, imu6Errata already imported
// at the top of lib.ts) and the parts (m0, imu6). Key the map in lowercase.

const STATIC_FILES: Record<string, unknown> = (() => {
  const out: Record<string, unknown> = {};
  // parts, keyed by "<mpn>.json"
  for (const mpn of listMpns()) {
    const part = getRawPart(mpn);
    if (part) out[`${mpn}.json`.toLowerCase()] = part;
  }
  // errata overlays, keyed by their referenced filename basename
  // (read each part's part.errata[].ref to learn the expected filename)
  for (const mpn of listMpns()) {
    const part: any = getRawPart(mpn);
    const overlays = getErrataOverlays(mpn);
    const refs = (part?.part?.errata ?? []).map((e: any) => e.ref);
    refs.forEach((ref: string, i: number) => {
      if (ref && overlays[i]) {
        const base = ref.split("/").pop()!;          // "./acme-imu6-errata.json" → "acme-imu6-errata.json"
        out[base.toLowerCase()] = overlays[i];
      }
    });
  }
  return out;
})();

export function getStaticFile(name: string): unknown | undefined {
  return STATIC_FILES[name.toLowerCase()];
}
```

```ts
// src/index.ts — inside fetch(), in the GET branch, BEFORE the banner response.
// (Keep OPTIONS/CORS and POST/MCP exactly as they are.)

if (method === "GET") {
  const url = new URL(request.url);
  const m = url.pathname.match(/^\/parts\/(.+\.json)$/i);
  if (m) {
    const doc = getStaticFile(m[1]);
    if (doc === undefined) {
      return json({ error: `Unknown part file: ${m[1]}` }, 404);
    }
    return json(doc, 200, {
      // long cache: part docs are immutable per revision
      "cache-control": "public, max-age=86400",
    });
  }
  // ... existing accept:text/event-stream 405 + banner logic unchanged ...
}
```

`json()` already exists in `index.ts` and already applies CORS — reuse it; do
not hand-roll a `Response`.

---

## Acceptance criteria

All against the deployed worker (or `wrangler dev`):

1. `GET /parts/ACME-IMU6.json` → **200**, `content-type: application/json`, body is
   the full IMU6 part document (has `part.mpn == "ACME-IMU6"`, `profiles`,
   `electrical`, etc.) — **not** the server banner.
2. `GET /parts/acme-imu6.json` (lowercase, filename form) → **200**, same document
   (case-insensitive MPN match must also accept the filename spelling).
3. `GET /parts/acme-imu6-errata.json` → **200**, the errata overlay
   (`type == "errata"`, has `overrides`).
4. `GET /parts/ACME-M0.json` and `GET /parts/acme-m0-errata.json` → **200**.
5. `GET /parts/NOPE-9000.json` → **404** with a JSON error body (not the banner,
   not a 200).
6. `GET /` (no `/parts/` path) → **unchanged** banner JSON.
7. `POST /` MCP flows (`initialize`, `tools/list`, `tools/call`) → **unchanged**;
   re-run any existing MCP smoke test.
8. CORS headers present on the new route (reuse `json()` so `Access-Control-*`
   come for free).
9. **End-to-end with the harness:** in a BluePill checkout, set
   `datasheet.origin` to the deployed worker URL and run
   `bluepill parts fetch ACME-IMU6` — it should fetch the part **and** its errata
   overlay into the cache, and a subsequent `datasheet(op="errata", mpn="ACME-IMU6")`
   should show the corrected sample-rate (`8000 → 4000`). This proves the
   filename↔MPN bridge and the errata-by-basename path both work.

---

## Explicitly out of scope

- **Rewriting or replacing the MCP server.** It stays. This is purely additive.
- ~~A parts index endpoint~~ — **SHIPPED.** `GET /parts/index.json` returns
  `{parts: [{mpn, family, manufacturer, profiles}, …]}` via `getCatalog()` in
  `lib.ts`; the harness's `op="search"` aggregates it across origins so a user
  can find a part by family without knowing the exact MPN. Deployed and live.
- **Auth / rate limiting / write endpoints.** Read-only public static files,
  same posture as the existing MCP server.
- **Changing the part/errata JSON or their relative `ref` fields.** Serve the
  existing `data/*.json` verbatim.
- **A `.part` extension or any non-JSON format.** The contract is the JSON
  data format; the extension stays `.json`.

---

## How the harness consumes this (context, not work)

For the agent's mental model — the BluePill side is **already built** and needs
no changes once this route ships:

- `datasheet.origin` (default `https://opendatasheet.org`) → point it at this
  worker to fetch unbundled parts.
- Resolution precedence in the harness: project-local `parts/*.json` → bundled
  `seed/` → **lazy fetch from `origin` into cache** → offline forever after.
- The harness bundles ACME-IMU6 and ACME-M0 as seed already, so fetch is only
  exercised for parts *not* in the seed — test criterion #9 uses a seeded part
  only to keep the data identical; for a true fetch test, request an MPN the
  harness doesn't seed and confirm it lands in the cache.
