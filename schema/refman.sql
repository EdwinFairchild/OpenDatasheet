-- refman D1 schema. Apply with:
--   npx wrangler d1 execute refman --file schema/refman.sql --local
--   npx wrangler d1 execute refman --file schema/refman.sql --remote

CREATE TABLE IF NOT EXISTS docs (
  doc_id        TEXT PRIMARY KEY,
  title         TEXT NOT NULL,
  rev           TEXT NOT NULL,
  pdf_sha256    TEXT NOT NULL,
  pages         INTEGER NOT NULL,
  section_count INTEGER NOT NULL,
  tree_json     TEXT NOT NULL,
  ingested_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sections (
  doc_id     TEXT NOT NULL,
  id         TEXT NOT NULL,
  title      TEXT NOT NULL,
  page_start INTEGER NOT NULL,
  page_end   INTEGER NOT NULL,
  body       TEXT NOT NULL,
  PRIMARY KEY (doc_id, id)
);

-- Standalone FTS table (NOT content= external-content; standalone is simpler and
-- import-order independent; the duplicated text is an accepted cost).
-- tokenchars '_' makes FDCAN_NBTP / RCC_CFGR1-style tokens single tokens — the
-- whole lexical-first bet depends on it. Do not change the tokenizer.
CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(
  doc_id UNINDEXED,
  id     UNINDEXED,
  title,
  body,
  tokenize = "unicode61 tokenchars '_'"
);
