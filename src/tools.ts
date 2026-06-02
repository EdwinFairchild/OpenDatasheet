// Tool definitions. Each tool has a name, a description (the LLM reads this to
// decide when to call it; keep them specific), a JSON Schema for its arguments
// (this is what MCP tool discovery exposes), and a run() that does the lookup.

import {
  listMpns,
  getRawPart,
  getResolvedPart,
  getErrataOverlays,
  resolvePath,
  errataFor,
  conditionMatches,
  profile,
} from "./lib";

export type Tool = {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  run: (args: Record<string, any>) => unknown;
};

function fail(msg: string): never {
  throw new Error(msg);
}

const str = (description: string) => ({ type: "string", description });

export const TOOLS: Tool[] = [
  {
    name: "list_parts",
    description:
      "List the parts this server knows about. Returns each part's MPN, family, lifecycle, capability profiles, and conformance tiers. Call this first to discover which parts are available.",
    inputSchema: {
      type: "object",
      properties: {
        query: str("Optional case-insensitive substring to filter by MPN or family."),
        manufacturer: str("Optional manufacturer filter."),
        family: str("Optional family filter."),
      },
    },
    run: (a) => {
      const q = (a.query ?? "").toString().toLowerCase();
      const parts = listMpns()
        .map((mpn) => getRawPart(mpn))
        .filter((p): p is any => !!p)
        .filter((p) => (a.manufacturer ? p.part.manufacturer === a.manufacturer : true))
        .filter((p) => (a.family ? p.part.family === a.family : true))
        .filter((p) => (q ? `${p.part.mpn} ${p.part.family}`.toLowerCase().includes(q) : true))
        .map((p) => ({
          mpn: p.part.mpn,
          family: p.part.family,
          manufacturer: p.part.manufacturer,
          lifecycle: p.part.lifecycle,
          profiles: p.conformance?.profiles ?? [],
          tiers: p.conformance?.tiers ?? [],
        }));
      return { count: parts.length, parts };
    },
  },

  {
    name: "describe_part",
    description:
      "Describe one part: identity, documents, capability profiles, tiers, authority, and a CAPABILITY INDEX of everything queryable on it (peripheral names, measurand IDs, electrical parameter symbols, timing diagram IDs, packages). Call this after list_parts and before any leaf query so you know which profiles and names are valid.",
    inputSchema: {
      type: "object",
      required: ["mpn"],
      properties: { mpn: str("Manufacturer part number, e.g. ACME-IMU6.") },
    },
    run: (a) => {
      const res = getResolvedPart(a.mpn) ?? fail(`Unknown part: ${a.mpn}. Try list_parts.`);
      const part = res.part;
      const profiles: string[] = part.conformance?.profiles ?? [];
      const rm = profile(part, "register-map");
      const sensor = profile(part, "sensor");

      const suggested: string[] = ["query_electrical", "get_timing", "get_pin_functions", "get_errata", "check_constraints"];
      if (rm) suggested.unshift("get_peripheral", "get_register");
      if (sensor) suggested.unshift("get_measurands", "get_conversion");

      return {
        mpn: part.part.mpn,
        manufacturer: part.part.manufacturer,
        family: part.part.family,
        revision: part.part.revision,
        lifecycle: part.part.lifecycle,
        packages: part.part.packages ?? [],
        documents: part.part.documents ?? [],
        profiles,
        tiers: part.conformance?.tiers ?? [],
        authority: part.conformance?.authority ?? "unknown",
        capability_index: {
          peripherals: rm ? (rm.peripherals ?? []).map((p: any) => p.name) : [],
          measurands: sensor ? (sensor.measurands ?? []).map((m: any) => ({ id: m.id, quantity: m.quantity, unit: m.unit })) : [],
          electrical_parameters: (part.electrical ?? []).map((e: any) => e.symbol ?? e.parameter),
          timing_diagrams: (part.timing ?? []).map((t: any) => t.diagram_id),
          packages: part.part.packages ?? [],
        },
        suggested_tools: suggested,
        errata_count: getErrataOverlays(a.mpn).reduce((n, o) => n + (o.overrides?.length ?? 0), 0),
      };
    },
  },

  {
    name: "get_peripheral",
    description:
      "List the registers of one peripheral (register-map profile): each register's name, offset, access, and description. Use get_register for the full bit-field breakdown. Requires the 'register-map' profile.",
    inputSchema: {
      type: "object",
      required: ["mpn", "peripheral"],
      properties: {
        mpn: str("Manufacturer part number."),
        peripheral: str("Peripheral name from describe_part, e.g. SPI1 or CONFIG."),
      },
    },
    run: (a) => {
      const res = getResolvedPart(a.mpn) ?? fail(`Unknown part: ${a.mpn}.`);
      const rm = profile(res.part, "register-map") ?? fail(`Part ${a.mpn} has no 'register-map' profile.`);
      const p =
        (rm.peripherals ?? []).find((x: any) => x.name === a.peripheral) ??
        fail(`Peripheral '${a.peripheral}' not found. Available: ${(rm.peripherals ?? []).map((x: any) => x.name).join(", ")}`);
      return {
        name: p.name,
        description: p.description,
        base_address: p.base_address,
        interrupts: p.interrupts ?? [],
        registers: (p.registers ?? []).map((r: any) => ({
          name: r.name,
          offset: r.offset,
          access: r.access,
          description: r.description,
        })),
      };
    },
  },

  {
    name: "get_register",
    description:
      "Return the full breakdown of one register: every bit-field with its bit position, width, access type, reset value, and enumerated values, each with a source citation. Errata are applied automatically. Requires the 'register-map' profile.",
    inputSchema: {
      type: "object",
      required: ["mpn", "peripheral", "register"],
      properties: {
        mpn: str("Manufacturer part number."),
        peripheral: str("Peripheral name, e.g. SPI1."),
        register: str("Register name, e.g. CR1."),
      },
    },
    run: (a) => {
      const res = getResolvedPart(a.mpn) ?? fail(`Unknown part: ${a.mpn}.`);
      const rm = profile(res.part, "register-map") ?? fail(`Part ${a.mpn} has no 'register-map' profile.`);
      const p =
        (rm.peripherals ?? []).find((x: any) => x.name === a.peripheral) ??
        fail(`Peripheral '${a.peripheral}' not found.`);
      const r =
        (p.registers ?? []).find((x: any) => x.name === a.register) ??
        fail(`Register '${a.register}' not found in ${a.peripheral}. Available: ${(p.registers ?? []).map((x: any) => x.name).join(", ")}`);
      return {
        peripheral: p.name,
        register: r,
        errata: errataFor(res.appliedErrata, a.register),
      };
    },
  },

  {
    name: "query_electrical",
    description:
      "Look up an electrical parameter (e.g. f_SCK, I_DD) and return min/typ/max values WITH their conditions (supply voltage, temperature, load). If you pass conditions, the matching row(s) are returned first. Every value carries a citation.",
    inputSchema: {
      type: "object",
      required: ["mpn", "parameter"],
      properties: {
        mpn: str("Manufacturer part number."),
        parameter: str("Parameter symbol or name from describe_part, e.g. f_SCK or f_SCK_max."),
        conditions: {
          type: "object",
          description: 'Optional conditions to match, e.g. { "vdd_v": 1.8, "temp_c": 25 }.',
        },
      },
    },
    run: (a) => {
      const res = getResolvedPart(a.mpn) ?? fail(`Unknown part: ${a.mpn}.`);
      const e =
        (res.part.electrical ?? []).find((x: any) => x.symbol === a.parameter || x.parameter === a.parameter) ??
        fail(`Electrical parameter '${a.parameter}' not found. Available: ${(res.part.electrical ?? []).map((x: any) => x.symbol ?? x.parameter).join(", ")}`);
      const all = e.values ?? [];
      const matched = a.conditions ? all.filter((v: any) => conditionMatches(v.conditions, a.conditions)) : all;
      return {
        parameter: e.parameter,
        symbol: e.symbol,
        description: e.description,
        matched,
        all_rows: all,
        provenance: e.provenance,
        errata: errataFor(res.appliedErrata, e.symbol ?? e.parameter),
      };
    },
  },

  {
    name: "get_measurands",
    description:
      "List what a sensor measures (sensor profile): each measurand's physical quantity, axes, unit, full-scale ranges with sensitivity, sample rate, and accuracy. Errata are applied automatically (e.g. a corrected max sample rate). Requires the 'sensor' profile.",
    inputSchema: {
      type: "object",
      required: ["mpn"],
      properties: { mpn: str("Manufacturer part number, e.g. ACME-IMU6.") },
    },
    run: (a) => {
      const res = getResolvedPart(a.mpn) ?? fail(`Unknown part: ${a.mpn}.`);
      const s = profile(res.part, "sensor") ?? fail(`Part ${a.mpn} has no 'sensor' profile.`);
      return {
        measurands: (s.measurands ?? []).map((m: any) => ({
          id: m.id,
          quantity: m.quantity,
          axes: m.axes,
          unit: m.unit,
          ranges: (m.ranges ?? []).map((r: any) => ({
            name: r.name,
            full_scale: r.full_scale,
            unit: r.unit,
            sensitivity: r.sensitivity,
          })),
          sample_rate: m.sample_rate,
          accuracy: m.accuracy,
          conversion: m.conversion,
          provenance: m.provenance,
        })),
        errata: res.appliedErrata,
      };
    },
  },

  {
    name: "get_conversion",
    description:
      "Explain how to turn a raw sensor reading into a physical value for one measurand: the formula, the sensitivity for the selected full-scale range, AND the register field that selects that range (the cross-profile link). Requires the 'sensor' profile.",
    inputSchema: {
      type: "object",
      required: ["mpn", "measurand"],
      properties: {
        mpn: str("Manufacturer part number."),
        measurand: str("Measurand id from get_measurands, e.g. accel."),
        range: str("Optional range name, e.g. FS_8G. If omitted, all ranges are returned."),
      },
    },
    run: (a) => {
      const res = getResolvedPart(a.mpn) ?? fail(`Unknown part: ${a.mpn}.`);
      const s = profile(res.part, "sensor") ?? fail(`Part ${a.mpn} has no 'sensor' profile.`);
      const m =
        (s.measurands ?? []).find((x: any) => x.id === a.measurand) ??
        fail(`Measurand '${a.measurand}' not found. Available: ${(s.measurands ?? []).map((x: any) => x.id).join(", ")}`);

      const ranges = a.range ? (m.ranges ?? []).filter((r: any) => r.name === a.range) : (m.ranges ?? []);
      if (a.range && ranges.length === 0) {
        fail(`Range '${a.range}' not found. Available: ${(m.ranges ?? []).map((r: any) => r.name).join(", ")}`);
      }

      const resolvedRanges = ranges.map((r: any) => {
        let controlling: any = null;
        const path = r.selected_by?.field;
        if (path) {
          const hit = resolvePath(res.part, path);
          const field = hit?.value;
          if (field) {
            const enumMatch = (field.enum ?? []).find((en: any) => en.name === r.selected_by.value);
            controlling = {
              field_path: path,
              field_name: field.name,
              set_to: r.selected_by.value,
              raw_value: enumMatch?.value,
              bit_offset: field.bit_offset,
              bit_width: field.bit_width,
            };
          }
        }
        return { range: r.name, full_scale: r.full_scale, sensitivity: r.sensitivity, selected_by: controlling };
      });

      return {
        measurand: m.id,
        quantity: m.quantity,
        unit: m.unit,
        formula: m.conversion?.formula,
        note: m.conversion?.note,
        output: m.output,
        ranges: resolvedRanges,
        provenance: m.provenance,
      };
    },
  },

  {
    name: "get_timing",
    description:
      "Return a timing diagram as data: its timing parameters (setup/hold/etc. with conditions) and the waveform in WaveDrom JSON. Use describe_part to find diagram IDs.",
    inputSchema: {
      type: "object",
      required: ["mpn", "diagram_id"],
      properties: {
        mpn: str("Manufacturer part number."),
        diagram_id: str("Timing diagram id, e.g. spi_master_timing."),
      },
    },
    run: (a) => {
      const res = getResolvedPart(a.mpn) ?? fail(`Unknown part: ${a.mpn}.`);
      const t =
        (res.part.timing ?? []).find((x: any) => x.diagram_id === a.diagram_id) ??
        fail(`Timing diagram '${a.diagram_id}' not found. Available: ${(res.part.timing ?? []).map((x: any) => x.diagram_id).join(", ")}`);
      return t;
    },
  },

  {
    name: "get_pin_functions",
    description:
      "Return a pin's type and its alternate-function mux for a given package. Use describe_part for available packages.",
    inputSchema: {
      type: "object",
      required: ["mpn", "package", "pin"],
      properties: {
        mpn: str("Manufacturer part number."),
        package: str("Package name, e.g. LQFP48."),
        pin: str("Pin number or name, e.g. 23 or PA5."),
      },
    },
    run: (a) => {
      const res = getResolvedPart(a.mpn) ?? fail(`Unknown part: ${a.mpn}.`);
      const pkg =
        (res.part.pinout ?? []).find((x: any) => x.package === a.package) ??
        fail(`Package '${a.package}' not found. Available: ${(res.part.pinout ?? []).map((x: any) => x.package).join(", ")}`);
      const pin =
        (pkg.pins ?? []).find((x: any) => String(x.number) === String(a.pin) || x.name === a.pin) ??
        fail(`Pin '${a.pin}' not found in package ${a.package}.`);
      return pin;
    },
  },

  {
    name: "get_errata",
    description:
      "Return the known errata for a part: each correction's target, the issue, the effect (replace/constraint/etc.), and a citation. Note: get_register, query_electrical and get_measurands already apply these automatically.",
    inputSchema: {
      type: "object",
      required: ["mpn"],
      properties: {
        mpn: str("Manufacturer part number."),
        revision: str("Optional silicon revision filter, e.g. rev-B."),
      },
    },
    run: (a) => {
      const overlays = getErrataOverlays(a.mpn);
      const filtered = a.revision ? overlays.filter((o) => o.applies_to?.revision === a.revision) : overlays;
      const overrides = filtered.flatMap((o) =>
        (o.overrides ?? []).map((ov: any) => ({
          applies_to: o.applies_to,
          target: ov.target,
          issue: ov.issue,
          effect: ov.effect,
          value: ov.value,
          constraint: ov.constraint,
          provenance: ov.provenance,
        }))
      );
      return { mpn: a.mpn, count: overrides.length, overrides };
    },
  },

  {
    name: "check_constraints",
    description:
      "Validate a proposed configuration against the part's absolute-maximum / recommended-operating limits and its errata constraints. Pass operating conditions and/or register-field settings. Returns violations and warnings, each with a citation. Use this before trusting a generated configuration.",
    inputSchema: {
      type: "object",
      required: ["mpn", "config"],
      properties: {
        mpn: str("Manufacturer part number."),
        config: {
          type: "object",
          description:
            'Proposed configuration. Recognized keys: vdd_v (number), temp_c (number), mode (string), and fields (object of { "FIELD_NAME": "ENUM_NAME" }). Example: { "vdd_v": 3.3, "temp_c": 80, "mode": "master", "fields": { "BR": "DIV2" } }.',
        },
      },
    },
    run: (a) => {
      const res = getResolvedPart(a.mpn) ?? fail(`Unknown part: ${a.mpn}.`);
      const cfg = a.config ?? {};
      const violations: any[] = [];
      const warnings: any[] = [];
      const limits = res.part.limits ?? {};

      // Supply voltage vs absolute maximum and recommended operating.
      if (typeof cfg.vdd_v === "number") {
        for (const am of limits.absolute_maximum ?? []) {
          if ((am.parameter === "V_DD" || am.parameter === "VDD") && typeof am.max === "number" && cfg.vdd_v > am.max) {
            violations.push({ kind: "absolute_maximum", parameter: am.parameter, limit_max: am.max, unit: am.unit, given: cfg.vdd_v, provenance: am.provenance });
          }
        }
        for (const ro of limits.recommended_operating ?? []) {
          if (ro.parameter === "V_DD" || ro.parameter === "VDD") {
            if ((typeof ro.max === "number" && cfg.vdd_v > ro.max) || (typeof ro.min === "number" && cfg.vdd_v < ro.min)) {
              warnings.push({ kind: "outside_recommended_operating", parameter: ro.parameter, min: ro.min, max: ro.max, unit: ro.unit, given: cfg.vdd_v, provenance: ro.provenance });
            }
          }
        }
      }

      // Errata constraints, e.g. a field value disallowed above a temperature.
      for (const e of res.appliedErrata) {
        if (e.effect !== "constraint" || !e.constraint) continue;
        const c: any = e.constraint;
        const when = c.when ?? {};
        const fieldSettings = cfg.fields ?? {};
        const valueMatches = when.value ? Object.values(fieldSettings).includes(when.value) : true;
        const modeMatches = when.mode ? cfg.mode === when.mode : true;
        const tempViolates = typeof c.max_temp_c === "number" && typeof cfg.temp_c === "number" && cfg.temp_c > c.max_temp_c;
        if (valueMatches && modeMatches && tempViolates) {
          violations.push({
            kind: "errata_constraint",
            issue: e.issue,
            constraint: c,
            given: { temp_c: cfg.temp_c, mode: cfg.mode, fields: fieldSettings },
            provenance: e.provenance,
          });
        }
      }

      return { mpn: a.mpn, ok: violations.length === 0, violations, warnings, checked: cfg };
    },
  },
];
