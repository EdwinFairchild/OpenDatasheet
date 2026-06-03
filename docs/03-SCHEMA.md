# 03: Schema

This document defines the OpenDatasheet JSON format: a **common core**, a set of composable **capability profiles**, and an **extension mechanism**. Read `02-PRINCIPLES.md` first.

All examples use a fictional vendor (ACME) so nothing is copied from a real datasheet. Values are illustrative.

---

## 0. The model

A **part document** describes one part. Its shape is:

```
part document
├── envelope            (metadata: spec version, conformance, authority)
├── part                (identity: MPN, manufacturer, revision, packages, documents, errata)
├── core blocks         (things almost every embedded part has)
│   ├── pinout
│   ├── electrical
│   ├── timing
│   ├── limits
│   └── sections        (prose, entity-linked)
├── profiles            (device-class structure   ONE OR MORE; this is the extensibility spine)
│   ├── register-map    (MCUs, MPUs, register-interface ICs, digital sensors)
│   ├── sensor          (measurands, ranges, conversions)
│   ├── power           (regulators/converters)  ← example of a future profile
│   └── …               (add a profile to support a new device class)
└── extensions          (namespaced, for fields not yet in the spec)
```

The mental model, restated: **a part is not a type; it is a core that carries one or more profiles.** A microcontroller has `register-map`. A digital temperature sensor has `register-map` **and** `sensor`. A buck converter has `power`.

---

## 1. Envelope and identity

```json
{
  "$schema": "https://opendatasheet.org/schema/v0.1/part.schema.json",
  "spec_version": "0.1",
  "type": "part",
  "conformance": {
    "tiers": [1, 2],
    "profiles": ["register-map", "sensor"],
    "authority": "manufacturer-certified"
  },
  "part": {
    "mpn": "ACME-IMU6",
    "manufacturer": "ACME Semiconductor",
    "family": "ACME-IMU6",
    "revision": "rev-B",
    "lifecycle": "active",
    "packages": ["LGA14"],
    "documents": [
      { "id": "ACME-DS-IMU6", "kind": "datasheet", "rev": "3",
        "url": "https://acme.example/docs/acme-ds-imu6-r3.pdf" }
    ],
    "errata": [
      { "id": "ACME-ES-IMU6-01", "rev": "2", "ref": "./acme-imu6-errata.json" }
    ]
  }
}
```

- `conformance.profiles` MUST list every profile present. This is what the discovery layer (`04`) reports so an agent knows which queries make sense.
- `conformance.authority` MUST be `manufacturer-certified` or `community-provisional`.
- `lifecycle`: one of `preview`, `active`, `nrnd` (not recommended for new designs), `obsolete`.
- `documents[].kind`: `datasheet`, `reference-manual`, `errata`, `app-note`, `programming-spec`, `user-guide`.

---

## 2. The provenance object (required at every leaf)

```json
{ "doc": "ACME-DS-IMU6", "section": "7.2", "rev": "3" }
```

`doc` references a `part.documents[].id`. Every value-bearing leaf in core blocks and profiles MUST carry one. No provenance → not conformant.

---

## 3. Core blocks

These exist because nearly every embedded part has them, regardless of device class.

### 3.1 Pinout (per package)

```json
{
  "package": "LGA14",
  "pins": [
    {
      "number": "1",
      "name": "SCL",
      "type": "io",
      "default": "I2C_SCL",
      "alt_functions": [
        { "signal": "SPI_SCK", "interface": "SPI" }
      ],
      "provenance": { "doc": "ACME-DS-IMU6", "section": "3.1", "rev": "3" }
    }
  ]
}
```

`type`: `io`, `power`, `ground`, `analog`, `reset`, `clock`, `nc`.

### 3.2 Electrical: conditions mandatory

```json
{
  "parameter": "I_dd_active",
  "symbol": "I_DD",
  "description": "Active supply current, accel + gyro on",
  "values": [
    { "min": null, "typ": 0.9, "max": 1.2, "unit": "mA",
      "conditions": { "vdd_v": 3.3, "temp_c": 25 } }
  ],
  "provenance": { "doc": "ACME-DS-IMU6", "section": "6.1", "rev": "3" }
}
```

`conditions` is an open object; common keys: `vdd_v`, `temp_c` (scalar or `[min,max]`), `load_pf`, `freq_hz`, `mode`, `note`. Unconditional values MUST still include `"conditions": {}`.

### 3.3 Timing: diagrams as data (WaveDrom)

```json
{
  "diagram_id": "i2c_write",
  "title": "I²C write timing",
  "parameters": [
    { "symbol": "t_SU_DAT", "description": "Data setup time",
      "min": 100, "typ": null, "max": null, "unit": "ns",
      "edge": { "from": "SDA_valid", "to": "SCL_rising" },
      "conditions": {} }
  ],
  "waveform": {
    "signal": [
      { "name": "SCL", "wave": "0.1.0.1" },
      { "name": "SDA", "wave": "x.=.=.x", "data": ["A6", "A5"] }
    ]
  },
  "provenance": { "doc": "ACME-DS-IMU6", "section": "6.3", "rev": "3" }
}
```

### 3.4 Limits (safety envelope)

```json
{
  "absolute_maximum": [
    { "parameter": "V_DD", "max": 4.0, "unit": "V",
      "provenance": { "doc": "ACME-DS-IMU6", "section": "5.1", "rev": "3" } }
  ],
  "recommended_operating": [
    { "parameter": "V_DD", "min": 1.7, "typ": 3.3, "max": 3.6, "unit": "V",
      "provenance": { "doc": "ACME-DS-IMU6", "section": "5.2", "rev": "3" } }
  ]
}
```

Exists so `check_constraints` (see `04`) can reject an out-of-spec configuration.

### 3.5 Sections (prose, entity-linked): Tier 3

```json
{
  "id": "sec-7-sensor-overview",
  "title": "Sensor functional description",
  "doc": "ACME-DS-IMU6",
  "section": "7",
  "rev": "3",
  "entities": ["sensor.accel", "register-map.CONFIG.FS_SEL"],
  "text": "Plain or lightly-marked content of the section …",
  "xrefs": [
    { "label": "see 8.4", "target": "register-map.peripherals[name=CONFIG]" }
  ]
}
```

`entities` lets an agent ask for prose concerning a specific register field or measurand. `xrefs` resolve "see section X" to a real target instead of a dead page number.

---

## 4. Profiles

A part includes a `profiles` object; each key is a profile name and its value is that profile's content.

```json
{
  "profiles": {
    "register-map": { /* §4.1 */ },
    "sensor": { /* §4.2 */ }
  }
}
```

### 4.1 Profile: `register-map`

For MCUs, MPUs, and **any** part with a programmable register interface, including most digital sensors. A superset of CMSIS-SVD: an SVD `<peripheral>`/`<register>`/`<field>`/`<enumeratedValue>` maps 1:1, so an importer is mechanical.

```json
{
  "peripherals": [
    {
      "name": "CONFIG",
      "description": "Configuration registers",
      "base_address": "0x10",
      "registers": [
        {
          "name": "ACCEL_CFG",
          "description": "Accelerometer configuration",
          "offset": "0x1C",
          "size": 8,
          "reset_value": "0x00",
          "access": "read-write",
          "fields": [
            {
              "name": "FS_SEL",
              "description": "Accelerometer full-scale range select",
              "bit_offset": 3,
              "bit_width": 2,
              "access": "read-write",
              "enum": [
                { "value": 0, "name": "FS_2G",  "description": "±2 g" },
                { "value": 1, "name": "FS_4G",  "description": "±4 g" },
                { "value": 2, "name": "FS_8G",  "description": "±8 g" },
                { "value": 3, "name": "FS_16G", "description": "±16 g" }
              ],
              "provenance": { "doc": "ACME-DS-IMU6", "section": "8.4", "rev": "3" }
            }
          ]
        }
      ]
    }
  ],
  "memory_map": []
}
```

`access` (register or field) MUST be one of: `read-write`, `read-only`, `write-only`, `read-writeOnce`, `writeOnce`, `w1c`, `w0c`, `rs`, `rc`. Getting these right is what stops an agent treating a clear-on-read status bit as a normal RW field.

Repeated registers/peripherals use a `dim` block:
```json
{ "name": "DATA%s", "dim": 6, "dim_index": "0-5", "offset": "0x3B", "dim_increment": "0x01", "...": "..." }
```

### 4.2 Profile: `sensor`

For anything that measures a physical quantity. The killer field is `conversion`, how to turn a raw register/ADC reading into a physical value, which is exactly what an agent needs and what PDFs bury in prose.

```json
{
  "measurands": [
    {
      "id": "accel",
      "quantity": "acceleration",
      "axes": ["x", "y", "z"],
      "unit": "g",
      "ranges": [
        {
          "name": "FS_2G",
          "full_scale": 2, "unit": "g",
          "sensitivity": { "value": 16384, "unit": "LSB/g" },
          "selected_by": { "field": "register-map.peripherals[name=CONFIG].registers[name=ACCEL_CFG].fields[name=FS_SEL]", "value": "FS_2G" }
        },
        {
          "name": "FS_16G",
          "full_scale": 16, "unit": "g",
          "sensitivity": { "value": 2048, "unit": "LSB/g" },
          "selected_by": { "field": "register-map.peripherals[name=CONFIG].registers[name=ACCEL_CFG].fields[name=FS_SEL]", "value": "FS_16G" }
        }
      ],
      "output": {
        "interface": "register",
        "registers": ["register-map.peripherals[name=CONFIG].registers[name=DATA0]"],
        "format": "int16", "endianness": "big"
      },
      "conversion": {
        "formula": "value_g = raw / sensitivity_LSB_per_g",
        "note": "sensitivity depends on the selected FS_SEL range; resolve via measurands.ranges[].selected_by"
      },
      "accuracy": [
        { "parameter": "zero_g_offset", "max": 50, "unit": "mg",
          "conditions": { "temp_c": 25 },
          "provenance": { "doc": "ACME-DS-IMU6", "section": "6.2", "rev": "3" } }
      ],
      "sample_rate": [
        { "min": 4, "max": 8000, "unit": "Hz", "conditions": {},
          "provenance": { "doc": "ACME-DS-IMU6", "section": "7.3", "rev": "3" } }
      ],
      "provenance": { "doc": "ACME-DS-IMU6", "section": "7.1", "rev": "3" }
    }
  ]
}
```

**Note the cross-profile link.** `ranges[].selected_by` and `output.registers` point into the `register-map` profile by path. This is principle #2 in action: the profiles are not two glued-together formats; the sensor's behavior is *linked* to the registers that control it. An agent answering "what's the accel sensitivity if I set ±8 g?" follows the link from the register field to the matching range.

`measurands[].quantity` is an open string with a recommended controlled vocabulary (`temperature`, `pressure`, `acceleration`, `angular_rate`, `magnetic_field`, `humidity`, `illuminance`, `current`, `voltage`, …). A new quantity needs no schema change.

### 4.3 Profile: `power` (sketch: example of adding a class)

Included only to show how cheaply a new device class slots in. Not fully specified in v0.1.

```json
{
  "topology": "buck",
  "v_in":  [{ "min": 4.0, "max": 18.0, "unit": "V", "conditions": {}, "provenance": { "...": "..." } }],
  "v_out": [{ "min": 0.8, "max": 5.5, "unit": "V", "conditions": {}, "provenance": { "...": "..." } }],
  "i_out_max": [{ "max": 3.0, "unit": "A", "conditions": { "v_in_v": 12, "temp_c": 25 }, "provenance": { "...": "..." } }],
  "efficiency": [
    { "value": 92, "unit": "%", "conditions": { "v_in_v": 12, "v_out_v": 3.3, "i_out_a": 1.5 }, "provenance": { "...": "..." } }
  ],
  "switching_freq": [{ "typ": 500, "unit": "kHz", "conditions": {}, "provenance": { "...": "..." } }]
}
```

To add `power`, you write this profile spec and a JSON Schema fragment. The core, and every other profile, is untouched. That is the whole extensibility story.

---

## 5. Extensions

Any object MAY carry an `extensions` key, namespaced, for fields not yet in the spec:

```json
{
  "name": "FS_SEL",
  "bit_offset": 3,
  "bit_width": 2,
  "access": "read-write",
  "extensions": {
    "acme": { "factory_calibrated": true, "trim_register": "0x4A" }
  }
}
```

Consumers MUST ignore unknown keys, never reject them. Popular extensions SHOULD be promoted into a profile or the core via the registry process (see `05-ROADMAP.md`).

---

## 6. Errata overlay

A separate document overriding the part document by path. Same model regardless of profile.

```json
{
  "$schema": "https://opendatasheet.org/schema/v0.1/errata.schema.json",
  "spec_version": "0.1",
  "type": "errata",
  "applies_to": { "mpn": "ACME-IMU6", "revision": "rev-B" },
  "overrides": [
    {
      "target": "profiles.sensor.measurands[id=accel].sample_rate[0].max",
      "issue": "Max ODR limited to 4 kHz on rev-B silicon",
      "effect": "replace",
      "value": 4000,
      "provenance": { "doc": "ACME-ES-IMU6-01", "section": "2.1", "rev": "2" }
    }
  ]
}
```

`effect`: `replace`, `constraint`, `deprecate`, `note`. Resolvers apply overlays in order and MUST expose both the original and the override (each with provenance) so a discrepancy can be explained. `target` uses a restricted path syntax (dotted keys, `[name=…]`/`[id=…]`/`[symbol=…]` selectors, numeric `[i]`); a formal grammar is an open question in `05`.

---

## 7. Conformance tiers (generalized across device classes)

A part declares `conformance.tiers`. Tier 1's "primary structured profile" depends on the device class.

| Tier | Name | Required content | Example by class |
|---|---|---|---|
| **0** | Navigable PDF | `documents` with stable section IDs, machine-readable TOC/anchors, MPN + rev, errata links, resolved `xrefs` | Any part |
| **1** | Primary structured profile | The structured profile core to the device's use | MCU → `register-map`; sensor → `sensor` (+ `register-map` if digital) |
| **2** | Parametric | `electrical` and/or `timing` with mandatory `conditions`; `limits` | Any part |
| **3** | Semantic | `sections` with `entities` + resolved `xrefs`; structured `waveform`s | Any part |

Tiers are additive but independently shippable. Every tier above 0 requires `provenance` on its leaf values.

---

## 8. JSON Schema skeleton (excerpt)

Full validators live in `schema/v0.1/`. Two leaves to anchor implementations (JSON Schema 2020-12):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://opendatasheet.org/schema/v0.1/defs.schema.json",
  "$defs": {
    "provenance": {
      "type": "object",
      "required": ["doc", "section", "rev"],
      "properties": {
        "doc": { "type": "string" },
        "section": { "type": "string" },
        "rev": { "type": "string" }
      }
    },
    "conditional_value": {
      "type": "object",
      "required": ["unit", "conditions"],
      "properties": {
        "min": { "type": ["number", "null"] },
        "typ": { "type": ["number", "null"] },
        "max": { "type": ["number", "null"] },
        "unit": { "type": "string" },
        "conditions": { "type": "object" },
        "provenance": { "$ref": "#/$defs/provenance" }
      }
    }
  }
}
```

The schema enforces the trust model (provenance required, conditions required), not just the shape. The top-level part document validates the envelope and `part`, requires `conformance.profiles`, and `$ref`s each declared profile's fragment, so adding a profile is adding a fragment, never editing the core.

---

## 9. Mapping from CMSIS-SVD

| SVD | OpenDatasheet (`register-map` profile) |
|---|---|
| `<device>` | `part` |
| `<peripheral>` (baseAddress, interrupt) | `peripherals[]` |
| `<register>` (addressOffset, size, resetValue, access) | `registers[]` (offset, size, reset_value, access) |
| `<field>` (bitOffset/bitWidth, bitRange) | `fields[]` (bit_offset, bit_width) |
| `<enumeratedValue>` | `field.enum[]` |
| `<dim>` / dimIncrement | `dim` / `dim_increment` |

What SVD does not carry (pinout, electrical, timing, limits, sensor data, errata, prose) is exactly what the core blocks and other profiles add.
