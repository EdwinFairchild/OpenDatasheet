// Data registry + resolvers.
//
// Part documents are plain JSON, imported at build time. To add a part: drop a
// new .json file in /data, import it here, and register it in PARTS (and ERRATA
// if it has an errata overlay). Then redeploy. That's the whole workflow.

import m0 from "../data/acme-m0.json";
import m0Errata from "../data/acme-m0-errata.json";
import imu6 from "../data/acme-imu6.json";
import imu6Errata from "../data/acme-imu6-errata.json";
import g474 from "../data/stm32g474re.json";

// Part shapes are loose (`any`) on purpose for this MVP. Real types can be
// generated from the JSON Schema later; keeping it loose here means adding a
// part never requires touching TypeScript types.
export type Part = any;
export type Errata = any;

const PARTS: Record<string, Part> = {
  "ACME-M0": m0 as Part,
  "ACME-IMU6": imu6 as Part,
  "STM32G474RE": g474 as Part,
};

const ERRATA: Record<string, Errata[]> = {
  "ACME-M0": [m0Errata as Errata],
  "ACME-IMU6": [imu6Errata as Errata],
};

export function listMpns(): string[] {
  return Object.keys(PARTS);
}

export function getRawPart(mpn: string): Part | undefined {
  return PARTS[mpn];
}

export function getErrataOverlays(mpn: string): Errata[] {
  return ERRATA[mpn] ?? [];
}

// ---------------------------------------------------------------------------
// Static raw-file map (for the GET /parts/{file}.json route in index.ts).
//
// The BluePill harness fetches whole documents by name, not via MCP. It uses
// TWO kinds of name under /parts/, so the map covers both:
//   - "<MPN>.json"          → the part document   (harness requests by MPN)
//   - "<errata-file>.json"  → the errata overlay  (harness reads part.errata[].ref,
//                                                   takes the basename, fetches that)
// Keyed in lowercase so the lookup is case-insensitive: a request for
// "/parts/ACME-IMU6.json" and "/parts/acme-imu6.json" both resolve.
// ---------------------------------------------------------------------------
const STATIC_FILES: Record<string, unknown> = (() => {
  const out: Record<string, unknown> = {};
  // Part documents, keyed by "<mpn>.json".
  for (const mpn of listMpns()) {
    const part = getRawPart(mpn);
    if (part) out[`${mpn}.json`.toLowerCase()] = part;
  }
  // Errata overlays, keyed by the filename basename of each part's errata ref,
  // so they resolve under the same origin the harness fetched the part from.
  for (const mpn of listMpns()) {
    const part: any = getRawPart(mpn);
    const overlays = getErrataOverlays(mpn);
    const refs = (part?.part?.errata ?? []).map((e: any) => e.ref);
    refs.forEach((ref: string, i: number) => {
      if (ref && overlays[i]) {
        const base = ref.split("/").pop()!; // "./acme-imu6-errata.json" → "acme-imu6-errata.json"
        out[base.toLowerCase()] = overlays[i];
      }
    });
  }
  return out;
})();

// Look up a raw document by its requested /parts/ filename (case-insensitive).
// Returns undefined for unknown names so the route can answer 404.
export function getStaticFile(name: string): unknown | undefined {
  return STATIC_FILES[name.toLowerCase()];
}

// Catalog for the GET /parts/index.json discovery route. One row per part
// (errata overlays excluded), with just enough to let a consumer find a part by
// MPN/family/manufacturer and then fetch the full document. This is what lets
// the BluePill harness answer "what STM32G4 parts exist here?" without knowing
// the exact MPN, across many configured sources, with no blind fan-out.
export function getCatalog(): Array<{
  mpn: string;
  family?: string;
  manufacturer?: string;
  profiles: string[];
}> {
  return listMpns().map((mpn) => {
    const part: any = getRawPart(mpn);
    return {
      mpn,
      family: part?.part?.family,
      manufacturer: part?.part?.manufacturer,
      profiles: part?.conformance?.profiles ?? [],
    };
  });
}

export function profile(part: Part, name: string): any {
  return part?.profiles?.[name];
}

// Plain-JSON deep clone (no Dates/functions in our data, so this is safe and
// avoids depending on structuredClone being in the TS lib set).
function clone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x));
}

// ---------------------------------------------------------------------------
// Path resolver
//
// Supports the restricted path syntax used in the schema:
//   - dotted keys:                  part.electrical
//   - attribute selectors:          peripherals[name=SPI1]  / measurands[id=accel] / [symbol=f_SCK]
//   - numeric indices:              sample_rate[0]
//
// If the first segment isn't a key of root but IS a key of root.profiles,
// resolution descends into profiles first. This handles profile-relative paths
// (e.g. "register-map.peripherals[name=CONFIG]...") used by cross-profile links,
// as well as root-rooted paths (e.g. "profiles.sensor...") used by errata.
// ---------------------------------------------------------------------------

type Token = { key: string; kind?: "attr" | "index"; attr?: string; val?: string; index?: number };

function parsePath(path: string): Token[] {
  const tokens: Token[] = [];
  for (const seg of path.split(".")) {
    const m = seg.match(/^([^\[]+)(?:\[(.+)\])?$/);
    if (!m) {
      tokens.push({ key: seg });
      continue;
    }
    const key = m[1];
    const inside = m[2];
    if (inside === undefined) {
      tokens.push({ key });
    } else if (/^\d+$/.test(inside)) {
      tokens.push({ key, kind: "index", index: parseInt(inside, 10) });
    } else {
      const eq = inside.indexOf("=");
      tokens.push({ key, kind: "attr", attr: inside.slice(0, eq), val: inside.slice(eq + 1) });
    }
  }
  return tokens;
}

export type Resolved = { parent: any; key: string | number; value: any };

export function resolvePath(root: any, path: string, profilesFallback = true): Resolved | undefined {
  const tokens = parsePath(path);
  let cursor: any = root;
  let parent: any = undefined;
  let key: string | number = "";

  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    let next = cursor?.[t.key];
    if (next === undefined && i === 0 && profilesFallback && cursor?.profiles?.[t.key] !== undefined) {
      next = cursor.profiles[t.key];
    }
    parent = cursor;
    key = t.key;
    cursor = next;
    if (cursor === undefined) return undefined;

    if (t.kind === "index") {
      parent = cursor;
      key = t.index as number;
      cursor = cursor?.[t.index as number];
      if (cursor === undefined) return undefined;
    } else if (t.kind === "attr") {
      if (!Array.isArray(cursor)) return undefined;
      const idx = cursor.findIndex((el: any) => String(el?.[t.attr as string]) === String(t.val));
      if (idx < 0) return undefined;
      parent = cursor;
      key = idx;
      cursor = cursor[idx];
    }
  }
  return { parent, key, value: cursor };
}

// ---------------------------------------------------------------------------
// Errata application
//
// Returns an errata-RESOLVED clone of the part plus a list of what was applied
// (with the original value preserved for `replace`), so a tool can show both the
// corrected value and what it used to be, each with a citation.
// ---------------------------------------------------------------------------

export type AppliedErratum = {
  target: string;
  effect: string;
  issue: string;
  original?: unknown;
  value?: unknown;
  constraint?: unknown;
  provenance?: unknown;
};

export function getResolvedPart(mpn: string): { part: Part; appliedErrata: AppliedErratum[] } | undefined {
  const raw = getRawPart(mpn);
  if (!raw) return undefined;
  const part = clone(raw);
  const applied: AppliedErratum[] = [];

  for (const overlay of ERRATA[mpn] ?? []) {
    for (const ov of overlay.overrides ?? []) {
      const r = resolvePath(part, ov.target, false);
      if (!r) continue;
      if (ov.effect === "replace") {
        const original = r.value;
        r.parent[r.key] = ov.value;
        applied.push({ target: ov.target, effect: "replace", issue: ov.issue, original, value: ov.value, provenance: ov.provenance });
      } else if (ov.effect === "constraint") {
        if (r.value && typeof r.value === "object") {
          (r.value as any)._errata = (r.value as any)._errata ?? [];
          (r.value as any)._errata.push({ effect: "constraint", issue: ov.issue, constraint: ov.constraint, provenance: ov.provenance });
        }
        applied.push({ target: ov.target, effect: "constraint", issue: ov.issue, constraint: ov.constraint, provenance: ov.provenance });
      } else {
        applied.push({ target: ov.target, effect: ov.effect, issue: ov.issue, provenance: ov.provenance });
      }
    }
  }
  return { part, appliedErrata: applied };
}

export function errataFor(applied: AppliedErratum[], needle: string): AppliedErratum[] {
  return applied.filter((a) => a.target.includes(needle));
}

// ---------------------------------------------------------------------------
// Condition matching for query_electrical. A value row "matches" the query if,
// for every key the query specifies that the row also constrains, the values are
// compatible (scalar equality, or within a [min, max] range). Keys the row does
// not constrain are treated as wildcards.
// ---------------------------------------------------------------------------

export function conditionMatches(rowCond: any, query: any): boolean {
  if (!query) return true;
  for (const k of Object.keys(query)) {
    if (rowCond == null || !(k in rowCond)) continue;
    const rv = rowCond[k];
    const qv = query[k];
    if (Array.isArray(rv) && rv.length === 2 && typeof rv[0] === "number" && typeof rv[1] === "number") {
      const q = Number(qv);
      if (Number.isNaN(q)) {
        if (String(rv) !== String(qv)) return false;
      } else if (q < rv[0] || q > rv[1]) {
        return false;
      }
    } else if (String(rv) !== String(qv)) {
      return false;
    }
  }
  return true;
}
