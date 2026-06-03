# 05: Roadmap

## Phases

### Phase 0: Spec foundation *(this doc set)*
The schema, principles, MCP interface, and a handful of reference part documents. Deliverable: a stable-enough `v0.1` to encode real parts against and a folder an agent can read to understand the mission.

### Phase 1: The MVP demo
The thinnest slice that makes someone say "why doesn't every vendor ship this." Scope discipline is the main failure mode; resist building a catalog, an auth layer, or twelve tools.

1. **Write 2 part documents** that prove the profile model: one MCU (`register-map`) and one digital sensor (`register-map` + `sensor`, with a cross-profile `selected_by` link). Two parts, not a catalog.
2. **Stand up the MCP server** with ~6 tools: `list_parts`, `describe_part`, `get_register`, `get_peripheral`, `query_electrical`, `get_conversion`. It is a lookup over the JSON files plus a resolver for errata overlays and `selected_by` links, genuinely small.
3. **Prove it with no UI:** point Claude Desktop or the MCP Inspector at the server and ask the demo questions. *This is already a live proof of the core idea.* It de-risks everything before any front-end work.
4. **(Optional) VS Code extension** with a webview that renders by *type*: register → bit-field strip + enum table; electrical → min/typ/max with a conditions badge; sensor conversion → formula + resolved sensitivity; each with a **citation footer**. The visual rendering is where the demo lands emotionally.

**Bias the demo toward contrast.** The wow is not "an MCP server returns JSON"; a vendor already does that. The wow is *an exact, cited fact the agent could not have reliably pulled from the PDF*: a bit-field enum, or a conditional value ("sensitivity at ±8 g," "max SCK at 1.8 V vs 3.3 V"). Lead with the questions PDF extraction fumbles.

### Phase 2: Bootstrap coverage
Solve the cold-start problem the way OpenStreetMap/Wikidata did.

- **`svd2opendatasheet`** importer, the cheapest on-ramp; turns any existing SVD into a Tier-1 `register-map` profile for free.
- **AI-assisted extraction** pipeline: PDF → draft JSON, marked `community-provisional`, with enums and access types flagged for human review (where extraction is weakest). Coverage first; certification later.

### Phase 3: Vendor pilot
Get one dev-experience-forward vendor to publish **one flagship part** at Tier 1 over an MCP endpoint, alongside any catalog endpoint they already run. Measure support-ticket deflection and agent success rate on that part. One part, one metric, one quarter.

### Phase 4: Governance & expansion
- **Extension registry** and a promotion path (`extensions.*` → profile/core).
- **Conformance test suite** + validators (`schema/v0.1/`).
- **New profiles**: `power`, RF/microwave, interface/transceiver, analog/mixed-signal.
- **Naming**: settle the project name after the schema stabilizes.

## Success metrics

- **Agent accuracy**: % of part-specific factual questions answered correctly *with a citation*, structured-query vs PDF-RAG baseline.
- **Time-to-driver**: minutes for an agent to bring up a working peripheral/sensor driver from zero.
- **Coverage**: number of parts at Tier 1+, split by authority (`manufacturer-certified` vs `community-provisional`).
- **Adoption**: vendors serving at least one part over an OpenDatasheet MCP endpoint.

## Open questions

- **`target` path grammar**: a restricted JSONPath subset vs a bespoke selector; needs a formal grammar and conformance tests.
- **Units**: adopt a controlled vocabulary (UCUM?) vs free-string `unit`. Free-string for now; tighten before 1.0.
- **Profile boundaries**: where does `sensor` end and a future `analog` begin? Op-amps, PMICs, and mixed-signal parts need more parametric structure than v0.1 defines.
- **Spec versioning**: semver on `spec_version`; define the deprecation/promotion policy before 1.0.
- **Identifier stability across silicon revisions**: how renames are versioned so cross-refs and cached tool calls survive.
