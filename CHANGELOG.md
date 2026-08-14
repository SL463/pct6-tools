# Changelog

## 1.2.0

- **Corrected the channel-name mapping.** 1.1.0 resolved `CN` by an entry's
  position in PC-Tool's list; the file actually stores an explicit id that each
  entry carries separately, and the two only coincide below id 29. Outputs and
  inputs also turn out to use entirely separate id spaces. The result is two
  tables, `OUTPUT_CHANNEL_NAMES` and `INPUT_CHANNEL_NAMES`.

  What changes in practice: outputs on ids 29+ were wrong - `Pass Through 1-4`
  had been reported as `HEC L/R`, `MEC L/R` - and most input names were wrong,
  e.g. `Digital In L/R` reported as `AUX2 R`/`HEC L`. Front-stage and subwoofer
  outputs (ids 1-28) are unaffected. See "Channel names" in FINDINGS.md.
- New `--all` flag lists every output, including ones with a speaker assigned
  but no settings dialled in yet. The default report notes how many there are.
- Both channel tables are complete - all 57 output and 77 input types - and were
  verified id by id against PC-Tool's own tables; the sample tune exercises only 19 and 12
  of them respectively, so nothing about them is derived from that file.
  FINDINGS.md now enumerates both in full rather than as collapsed id ranges.
- `tests/test_channel_types.py` pins completeness (counts, contiguity, the id-9
  input gap) and the landmark ids where stored id and list position diverge, so
  a future edit can't silently drop or renumber a type.

## 1.1.0

- `pct6_extract.py` now resolves each channel's `CN` attribute to its assigned
  speaker name — the type selected on PC-Tool's Digital Routing page
  (`Front L High`, `Front R Mid`, `Subwoofer 1`, `Not assigned`, …). The
  77-entry mapping is documented under "Channel names" in FINDINGS.md. Shown as a `Speaker` column in the report and as the
  new `channel_name` field in `--json`.
- `schema/v1` gains the optional `channel_name` property (additive, so existing
  consumers and previously decoded files stay valid).
- FINDINGS.md documents a pitfall confirmed against PC-Tool's UI: the Digital
  Routing dropdown lists channels in a different order than their stored ids,
  agreeing only for the low ids, so decoding against the displayed order turns
  `Subwoofer 1` into `Rear Fill Low`.
- FINDINGS.md: channel role/side labels are no longer an open question. The
  sample-file table there is corrected — outputs 20 and 22 had been inferred as
  "Tweeter R" and "Midrange R" but are `Front R Mid` and `Front R Low`.

## 1.0.0

Initial release.

- `pct6_extract.py` — decodes `.pct6` files (container format: `XOR(qCompress(UTF-8 XML), key)`)
  into a per-output settings report, raw decoded XML, or schema-conformant JSON.
- `pct6_analyze.py` — structural/statistical triage for a `.pct6` variant that
  doesn't decode yet (entropy, repeated n-grams, bit autocorrelation, codec
  brute force, differential diff between two saves).
- `schema/v1/pct6-tune.schema.json` — JSON Schema (2020-12) for the decoded
  JSON, published at a stable URL. See the README for the versioning
  guarantee.
