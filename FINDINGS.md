# .pct6 format — decoded

**Bottom line: solved.** `ScottTuneFullMeasure.pct6` decodes to a 63,763-byte
UTF-8 XML document carrying gain, delay, polarity, crossover and full
parametric-EQ settings for every input and output. `pct6_extract.py`
implements the decoder and prints a per-output report.

## Container format

```
file bytes = XOR( qCompress(utf8(xml)), key )
```

`qCompress` is Qt's own container: a 4-byte **big-endian** uncompressed-length
prefix followed by a raw zlib stream. `key` is one of a small set of ASCII
literals, repeated (XOR-stream) across the whole compressed blob. PC-Tool tries
the variants in this order, so a decoder should too:

| Key | Variant |
| --- | --- |
| *(none)* | no compression |
| *(none)* | compression only |
| `ATFV6` | V6 obfuscation |
| `ATFV6P` | V6 keypass obfuscation |
| `ATF` | AFPX legacy obfuscation |

The sample file uses the `ATFV6` key ("V6 obfuscation").

The statistical profile of a `.pct6` matches this exactly, and `pct6_analyze.py`
will show it on any file: no standard cipher (files carry real, non-chance exact
repeats) but no standard compressed container at a byte-aligned offset either,
because a fixed-length XOR key sits between the file and the zlib stream and
zlib's own header bytes get folded into that XOR. The 5-byte periodicity that
bit autocorrelation measures is literally `len("ATFV6") == 5` — which is how the
key length announces itself, and how an unfamiliar variant can be triaged.

## XML structure

Root element `<ATF>`, attributes carry file-level metadata (`V` = PC-Tool
version, `D` = timestamp, `Dev` = device id, `FN` = original save path, `INS`
/ `OUTS` = input/output counts). Children:

| Element | Count | Content |
| --- | --- | --- |
| `<OC>` | 26 | One per **output channel**: gain, delay, polarity, 30 filter slots, enable flags |
| `<IC>` | 12 | One per **input channel**: same filter/gain shape, fewer slots |
| `<Route>` | 1 | Input→output routing matrix (`<R>` rows of `G<n>` gain coefficients) |
| `<DCM>` | 1 | Device configuration memory — raw register-style values |
| `<ABP>` | 1 | Auto bass boost/loudness parameters |
| `<STX>` | 1 | Single attribute, unexplored |
| `<MCV2>` | 1 | ~50 device/power-management attributes (thermal, priority, timing) |
| `<UN>` | 1 | Empty/reserved |
| `<ATFCOND>` | 1 | CONDUCTOR (external volume knob) configuration |

### `<OC>` / `<IC>` shape

```xml
<OC DG="3" CE="1" Finit="30" MT="1" GD="0" CINV="1" ON="17" EqBy="0" LG="3" CN="3">
  <Fil F="3100.00" G="-24" I="0" FilBBR="0" FilBy="0" Q="0.7" T="15"/>
  ... 30 <Fil> slots total ...
  <Vol L="0.5956621435290105" T="15"/>
  <T PM="2" P="0" T="192"/>
</OC>
```

| Attribute | Meaning |
| --- | --- |
| `ON` / `CN` | output number / **channel name id** — see "Channel names" below |
| `CE` | channel enabled |
| `CINV` | polarity inverted |
| `EqBy` | whole-channel EQ bypass |
| `DG` / `LG` | delay group / link group |
| `<Vol L=…>` | **gain, stored as a linear multiplier** — dB = `20·log10(L)` |
| `<T PM=… T=…>` | `T` is the **raw delay value** |
| `<Fil>` | one filter slot — see below |

### `<Fil>` — filter slot

```xml
<Fil F="123.00" G="-16.1" I="0" FilBBR="0" FilBy="0" Q="1.222" T="17"/>
```

| Attribute | Meaning |
| --- | --- |
| `F` | frequency, Hz |
| `G` | gain (peaking bands, dB) or crossover slope (dB/oct) |
| `Q` | Q factor |
| `FilBy` | this slot bypassed |
| `T` | **filter type**, see enum below |

Each `<OC>` carries exactly 30 `<Fil>` slots: a fixed pair of crossover slots
(lowpass + highpass, always present, `bypassed`/`G=0` when unused) plus up to
28 parametric peaking bands. Untouched peaking slots default to `T="1"`,
`G="0"`, `Q="4.3"` — filtered out by `pct6_extract.py` as "not actually set."

### Channel names (`CN`) — the Digital Routing speaker assignment

`CN` on `<OC>`/`<IC>` is not an opaque channel id: it names the channel, and for
an output that name is exactly the speaker type picked on the **Digital Routing**
page (`Front L High`, `Front R Mid`, `Pass Through 3`, …).

Two things make this easy to get wrong, and both were got wrong here first.

**1. Outputs and inputs use separate id spaces.** The same `CN` means different
things in `<OC>` and `<IC>` — `CN="38"` is `Subwoofer R` on an output and
`Digital In L` on an input. There is one id table per direction, below.

**2. The id is not the channel's position in PC-Tool's dropdown.** The two
orders differ, and they agree only up to id 28, which is exactly why a partial
check passes and then silently diverges. The dropdown interleaves groups that
the id space keeps apart: `Line Out 1–8` hold ids 29–36, which pushes
`Subwoofer L/R` out to 37/38, and `Pass Through` — contiguous in the dropdown —
splits across two disjoint id runs, 1–6 at 39–44 and 7–12 at 50–55. Reading the
displayed order as if it were the id decodes `Subwoofer 1` as `Rear Fill Low`.

Use the tables below rather than any ordering seen in the UI.

**Output ids** (`<OC>`) — all 57, contiguous 0–56:

| id | name | id | name | id | name |
| --- | --- | --- | --- | --- | --- |
| 0 | Not assigned | 19 | Rear L Low | 38 | Subwoofer R |
| 1 | Front L Full | 20 | Rear R Low | 39 | Pass Through 1 |
| 2 | Front R Full | 21 | Rear Fill Full | 40 | Pass Through 2 |
| 3 | Front L High | 22 | Rear Fill High | 41 | Pass Through 3 |
| 4 | Front R High | 23 | Rear Fill Low | 42 | Pass Through 4 |
| 5 | Front L Mid | 24 | Rear Sum | 43 | Pass Through 5 |
| 6 | Front R Mid | 25 | Subwoofer 1 | 44 | Pass Through 6 |
| 7 | Front L Low | 26 | Subwoofer 2 | 45 | Bridge Mode |
| 8 | Front R Low | 27 | Subwoofer 3 | 46 | Surround L Full |
| 9 | Front Center Full | 28 | Subwoofer 4 | 47 | Surround R Full |
| 10 | Front Center High | 29 | Line Out 1 | 48 | Front Subwoofer L |
| 11 | Front Center Low | 30 | Line Out 2 | 49 | Front Subwoofer R |
| 12 | F Sum | 31 | Line Out 3 | 50 | Pass Through 7 |
| 13 | Rear L Full | 32 | Line Out 4 | 51 | Pass Through 8 |
| 14 | Rear R Full | 33 | Line Out 5 | 52 | Pass Through 9 |
| 15 | Rear L High | 34 | Line Out 6 | 53 | Pass Through 10 |
| 16 | Rear R High | 35 | Line Out 7 | 54 | Pass Through 11 |
| 17 | Rear L Mid | 36 | Line Out 8 | 55 | Pass Through 12 |
| 18 | Rear R Mid | 37 | Subwoofer L | 56 | User defined Name |

**Input ids** (`<IC>`) — all 77, 0–77. Id 9 is unused: the list jumps
`Front R Low` (8) straight to `Front Center Full` (10).

| id | name | id | name | id | name |
| --- | --- | --- | --- | --- | --- |
| 0 | Not assigned | 27 | Subwoofer 2 | 53 | Opt. Sub 8 |
| 1 | Front L Full | 28 | Subwoofer 3 | 54 | AUX L |
| 2 | Front R Full | 29 | Subwoofer 4 | 55 | AUX R |
| 3 | Front L High | 30 | Line In 1 | 56 | HEC L |
| 4 | Front R High | 31 | Line In 2 | 57 | HEC R |
| 5 | Front L Mid | 32 | Line In 3 | 58 | MEC L |
| 6 | Front R Mid | 33 | Line In 4 | 59 | MEC R |
| 7 | Front L Low | 34 | Line In 5 | 60 | Front MID |
| 8 | Front R Low | 35 | Line In 6 | 61 | Front SIDE |
| 10 | Front Center Full | 36 | Line In 7 | 62 | Rear MID |
| 11 | Front Center High | 37 | Line In 8 | 63 | Rear SIDE |
| 12 | Front Center Low | 38 | Digital In L | 64 | AUX2 L |
| 13 | F Sum | 39 | Digital In R | 65 | AUX2 R |
| 14 | Rear L Full | 40 | Opt. In 3 | 66 | ASD Front Left |
| 15 | Rear R Full | 41 | Opt. In 4 | 67 | ASD Front Right |
| 16 | Rear L High | 42 | Opt. In 5 | 68 | ASD Rear Left |
| 17 | Rear R High | 43 | Opt. In 6 | 69 | ASD Rear Right |
| 18 | Rear L Mid | 44 | Opt. In 7 | 70 | Subwoofer L |
| 19 | Rear R Mid | 45 | Opt. In 8 | 71 | Subwoofer R |
| 20 | Rear L Low | 46 | Opt. Sub 1 | 72 | Surround L Full |
| 21 | Rear R Low | 47 | Opt. Sub 2 | 73 | Surround R Full |
| 22 | Rear Fill Full | 48 | Opt. Sub 3 | 74 | Front Subwoofer L |
| 23 | Rear Fill High | 49 | Opt. Sub 4 | 75 | Front Subwoofer R |
| 24 | Rear Fill Low | 50 | Opt. Sub 5 | 76 | USB L |
| 25 | R Sum | 51 | Opt. Sub 6 | 77 | USB R |
| 26 | Subwoofer 1 | 52 | Opt. Sub 7 |  |  |

Both tables are in `pct6_extract.py` as `OUTPUT_CHANNEL_NAMES` and
`INPUT_CHANNEL_NAMES`.

The sample file corroborates them throughout. Its eight configured outputs are
three symmetric front pairs plus a sub pair, each name matching that channel's
crossover; the unused outputs read `Not assigned` (`CN="0"`); the twelve
untouched factory-default outputs read as a canonical layout (Front L/R, Rear
L/R, Center, Rear Fill, Pass Through 1–4, Subwoofer 1/2); and all twelve inputs
read as a textbook source set — Front L/R, Rear L/R, Center, Rear Fill,
Subwoofer 1/2, Digital In L/R, AUX L/R.

### Filter-type enum (`T`)

The values line up with the `Characteristic` choices the crossover UI offers
(Butterworth, Bessel, Tschebyscheff, Linkwitz-Riley, plus the parametric band),
and are confirmed against which ones appear in a crossover slot vs. a peaking
slot in the sample file:

| `T` | Meaning |
| --- | --- |
| 1 | unused / flat |
| 9 / 10 | Butterworth lowpass / highpass |
| 11 / 12 | Bessel lowpass / highpass |
| 13 / 14 | Tschebyscheff lowpass / highpass |
| 15 / 16 | Linkwitz-Riley lowpass / highpass |
| 17 | Peak (parametric EQ band) |

Slope is stored as `G` on the crossover slot in dB/oct (e.g. `-24` = 4th-order
LR24), not as a separate order field.

### Delay

`<T … T="raw">` is an integer with no unit attribute anywhere in the XML.
ACO-based DSPs run their internal pipeline at 96 kHz; read as **samples at
96 kHz**, `raw / 96000 * 1000` gives ms and `raw / 96000 * 34300` gives cm
(speed of sound 343 m/s). Nothing in the file states the unit, so this
conversion is inferred from the platform's known sample rate rather than read
from the data — flagged as an open question below.

## Decoded sample: `ScottTuneFullMeasure.pct6`

PC-Tool 6.03.04, device id 22, saved 2026-08-13 11:50, from
`ScottTune-FullMeasure.pct6`. 12 inputs / 26 outputs declared; 8 outputs carry
non-default settings — a stereo 3-way front stage plus stereo subs:

| Out | Speaker (`CN`) | Gain | Delay | Pol | HP | LP | EQ bands |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | Front L Mid (5) | −5.0 dB | 100 (1.04 ms / 35.7 cm) | — | 201 Hz LR12 | 3301 Hz LR24 | 28 |
| 17 | Front L High (3) | −4.5 dB | 192 (2.00 ms / 68.6 cm) | inverted | 3100 Hz LR24 | — | 29 |
| 18 | Front L Low (7) | 0 dB | 175 (1.82 ms / 62.5 cm) | inverted | 70 Hz LR24 | 230 Hz LR24 | 30 |
| 20 | Front R Mid (6) | 0 dB | 0 | — | 200 Hz LR12 | 3301 Hz LR24 | 30 |
| 21 | Front R High (4) | −10.0 dB | 52 (0.54 ms / 18.6 cm) | inverted | 2500 Hz LR24 | — | 28 |
| 22 | Front R Low (8) | 0 dB | 0 | — | 70 Hz LR24 | 300 Hz LR24 | 27 |
| 24 | Subwoofer 1 (25) | 0 dB | 0 | — | — | 80 Hz Butterworth24 | 7 |
| 25 | Subwoofer 2 (26) | 0 dB | 0 | — | — | 80 Hz Butterworth24 | 7 |

Speaker names are read from the file (`CN`), not guessed — a stereo 3-way front
stage plus stereo subs. 186 EQ bands total. Full per-band frequency/gain/Q is in
`pct6_extract.py`'s report or `--json` output.

An earlier revision of this document inferred these roles from crossover ranges
and delay symmetry alone, and got two of them wrong: output 20 was called
"Tweeter R" when `CN="6"` makes it **Front R Mid** (its 200 Hz–3301 Hz passband
agrees, and pairs it with output 16), and output 22 was called "Midrange R" when
`CN="8"` makes it **Front R Low**, pairing with output 18. Reading `CN` removes
the guesswork.

A further 15 outputs carry a speaker assignment but no tuning yet — they hold
default gain/delay and no filters, so the table above (and the default report)
skips them, but the assignment is real and `--all` lists them:

| Out | Speaker (`CN`) |
| --- | --- |
| 0, 1 | Front L / R Full (1, 2) |
| 2, 3, 19, 23 | Rear L / R Full (13, 14) |
| 4 | Front Center Full (9) |
| 5 | Rear Fill Full (21) |
| 6–9, 14 | Pass Through 1–4 (39–42) |
| 10, 11 | Subwoofer 1 / 2 (25, 26) |

Outputs 12, 13 and 15 are `Not assigned` (`CN="0"`). Note `CN` is not unique
across outputs — a channel name can appear on more than one output (outputs 6
and 14 are both `Pass Through 1`, and 10/24 and 11/25 both carry the subwoofer
names), so `ON` is the identifier, not `CN`.

All twelve inputs are assigned: Front L/R Full, Rear L/R Full, Front Center
Full, Rear Fill Full, Subwoofer 1/2, Digital In L/R, AUX L/R.

## Open questions

Nothing here blocks reading the tune; these affect only the confidence of a
few secondary fields.

- **Delay unit.** Assumed samples at 96 kHz (see above). If PC-Tool actually
  stores delay in units of 1/100 ms, every delay value in this doc is too
  large by 4% (96000 vs the ~100000 an exact-hundredths encoding would imply)
  — negligible for tuning purposes either way, but worth pinning down with a
  known-value test file.
- ~~**Channel role/side labels**~~ — **resolved.** `CN` carries the channel's
  assigned name, so the Digital Routing speaker type (`Front L High`,
  `Front R Mid`, `Pass Through 3`, …) is read straight from the file. See
  "Channel names" above. Two things remain open around it:
  - The physical driver fitted to a channel is not in the file — `Front L High`
    tells you the tune's intent, not that the speaker is a 28 mm soft dome.
  - The output list's last entry is `User defined Name` (id 56), which implies
    PC-Tool can store a free-text channel name. No such string appears in this
    sample and no `<OC>` uses id 56, so where the text would live is unknown. A
    file saved after renaming a channel in the UI would settle it.
- **`<Route>`, `<DCM>`, `<MCV2>`, `<ABP>`, `<ATFCOND>`** are parsed structurally
  (attribute dumps) but their individual fields are not yet decoded — they
  don't carry per-output EQ/crossover/delay/gain, so they were out of scope
  here. `pct6_analyze.py --diff` across two saves that differ in one setting is
  the practical way to pin any of them down.

## Tooling

- `pct6_extract.py` — the decoder. `report()` prints the per-output table and
  band lists shown above; `--xml` dumps the decoded XML verbatim; `--json`
  gives the same data machine-readable.
- `pct6_analyze.py` — the earlier structural/statistical toolkit (entropy,
  n-grams, bit autocorrelation, codec brute force, `--diff`). Still useful for
  triaging an unfamiliar `.pct6`/`.afpx` variant before checking it against
  `pct6_extract.py`.
