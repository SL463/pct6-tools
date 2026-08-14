# pct6-tools

An independent decoder for **Audiotec Fischer DSP PC-Tool 6** setup
files (`.pct6`) — the tune format used by HELIX, BRAX and MATCH ACO-based
car-audio DSPs. Turns a `.pct6` file into plain, documented JSON: gain,
delay, polarity, crossover, full parametric-EQ settings and the assigned
speaker (`Front L High`, `Front R Mid`, `Subwoofer 1`, …) for every input
and output.

The format, and exactly what each field means, is documented in
[FINDINGS.md](FINDINGS.md).

Not affiliated with or endorsed by Audiotec Fischer. Product names are the
trademarks of their respective owners.

## Install

No dependencies beyond the Python 3 standard library.

```sh
git clone https://github.com/sl463/pct6-tools
cd pct6-tools
./pct6_extract.py tune.pct6
```

## Usage

```sh
./pct6_extract.py tune.pct6              # per-output settings report
./pct6_extract.py --all tune.pct6        # every output, including ones not yet tuned
./pct6_extract.py --xml tune.pct6        # decoded XML, as PC-Tool wrote it
./pct6_extract.py --json tune.pct6       # machine-readable, schema-conformant JSON
```

```sh
./pct6_analyze.py tune.pct6              # structural/statistical report on an undecodable file
./pct6_analyze.py --codecs tune.pct6     # decompressor brute force
./pct6_analyze.py --diff a.pct6 b.pct6   # differential analysis between two saves
```

`--json` output is self-describing — it carries its own `$schema` pointer, so
any consumer knows exactly which schema version it conforms to without being
told out of band:

```json
{
  "$schema": "https://raw.githubusercontent.com/sl463/pct6-tools/main/schema/v1/pct6-tune.schema.json",
  "source_file": "tune.pct6",
  "decoder": "pct6_extract.py v1.0.0",
  "container_mode": "V6 obfuscation",
  ...
}
```

## Schema

The canonical schema lives at [`schema/v1/pct6-tune.schema.json`](schema/v1/pct6-tune.schema.json)
and is published at a stable URL — reference it directly, don't copy it:

```
https://raw.githubusercontent.com/sl463/pct6-tools/main/schema/v1/pct6-tune.schema.json
```

**Versioning:** `v1` is additive-only — existing fields keep their meaning
forever, and new optional fields may be added without notice. A breaking
change gets a `v2` schema alongside `v1`, never an edit in place. It is safe
to hardcode the `v1` URL above in another project indefinitely.

**Validate a decoded file against it:**

```sh
pip install jsonschema
python3 -c "
import json, urllib.request, jsonschema
schema = json.load(urllib.request.urlopen(
    'https://raw.githubusercontent.com/sl463/pct6-tools/main/schema/v1/pct6-tune.schema.json'))
data = json.load(open('tune.pct6.json'))
jsonschema.validate(data, schema)
print('valid')
"
```

**From JavaScript/TypeScript** (e.g. with [ajv](https://ajv.js.org/)):

```js
import Ajv from "ajv";
const schema = await (await fetch(
  "https://raw.githubusercontent.com/sl463/pct6-tools/main/schema/v1/pct6-tune.schema.json"
)).json();
const validate = new Ajv().compile(schema);
if (!validate(tuneData)) console.error(validate.errors);
```

**Generating types** — the schema is a standard JSON Schema 2020-12 document,
so it works with the usual codegen tools, e.g.
[`quicktype`](https://quicktype.io/) or
[`json-schema-to-typescript`](https://github.com/bcherny/json-schema-to-typescript)
pointed at the URL above.

## Speaker names

Each channel's `CN` attribute indexes PC-Tool's channel-name list, so the
speaker type selected on the **Digital Routing** page is read straight out of
the file rather than guessed from crossover points:

```
Out  Speaker                Gain                Delay   Pol   EQ  Highpass
 16  Front L Mid           -5.0dB   100 ( 1.04 ms  35.7 cm)     +   28  201 Hz -12 dB/oct Linkwitz
 17  Front L High          -4.5dB   192 ( 2.00 ms  68.6 cm)   INV   29  3100 Hz -24 dB/oct Linkwitz
 24  Subwoofer 1           +0.0dB     0 ( 0.00 ms   0.0 cm)     +    7  -
```

In `--json` this is the `channel_name` field alongside the raw `channel_id`.

Outputs and inputs use **separate id spaces** - the same `CN` is `Subwoofer R`
on an output and `Digital In L` on an input - and the stored id is not the
channel's position in PC-Tool's list. Both tables, and how they were recovered,
are in [FINDINGS.md](FINDINGS.md).

Both tables carry **every type PC-Tool defines** — 57 output, 77 input — not
just the ones a given tune uses; they are enumerated in full in
[FINDINGS.md](FINDINGS.md).

An output can have a speaker assigned without being tuned yet (a Pass Through,
or a rear fill you haven't dialled in). Those are skipped by the default report
since they carry no settings; `--all` lists every output with its assignment.

## Open questions

One field is still inferred rather than read directly from the file — the delay
unit. See "Open questions" in [FINDINGS.md](FINDINGS.md) for what's known and
how to pin it down further.

## License

MIT — see [LICENSE](LICENSE).
