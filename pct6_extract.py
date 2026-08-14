#!/usr/bin/env python3
"""Decode Audiotec Fischer DSP PC-Tool 6 setup files (.pct6) and report the
per-output tune settings, including the speaker each output is assigned to on
PC-Tool's Digital Routing page (see OUTPUT_CHANNEL_NAMES below).

Container format:

    file = XOR(qCompress(utf-8 XML), key)

where qCompress is Qt's format - a 4-byte big-endian uncompressed length
followed by a zlib stream - and the XOR key is one of a small set of ASCII
literals. PC-Tool tries the variants in this order, so this decoder does too:

    (none)     no compression
    (none)     compression only
    b"ATFV6"   V6 obfuscation
    b"ATFV6P"  V6 keypass obfuscation
    b"ATF"     AFPX legacy obfuscation

    ./pct6_extract.py tune.pct6              # per-output report
    ./pct6_extract.py --all tune.pct6        # including outputs not yet tuned
    ./pct6_extract.py --xml tune.pct6        # dump the decoded XML
    ./pct6_extract.py --json tune.pct6       # machine-readable settings
"""

import argparse
import json
import math
import os
import struct
import sys
import xml.etree.ElementTree as ET
import zlib

# Ordered exactly as PC-Tool 6 tries them.
KEYS = [None, b"ATFV6", b"ATFV6P", b"ATF"]

MODE_NAMES = {
    None: "compression only (no obfuscation)",
    b"ATFV6": "V6 obfuscation",
    b"ATFV6P": "V6 keypass obfuscation",
    b"ATF": "AFPX legacy obfuscation",
}

# <Fil T="..."> filter kind. Odd = lowpass, even = highpass, in the same order
# as the "Characteristic" list in the crossover UI (Butterworth, Bessel,
# Tschebyc., Linkwitz); 17 is the parametric peaking band used by the EQ.
FILTER_TYPES = {
    1: ("unused", "unused band"),
    9: ("lowpass", "Lowpass Butterworth"),
    10: ("highpass", "Highpass Butterworth"),
    11: ("lowpass", "Lowpass Bessel"),
    12: ("highpass", "Highpass Bessel"),
    13: ("lowpass", "Lowpass Tschebyscheff"),
    14: ("highpass", "Highpass Tschebyscheff"),
    15: ("lowpass", "Lowpass Linkwitz"),
    16: ("highpass", "Highpass Linkwitz"),
    17: ("peak", "Peak (parametric EQ)"),
}

# <OC>/<IC> CN attribute -> the channel's assigned name, which for an output is
# the speaker type picked in PC-Tool's Digital Routing page ("Front L High",
# "Front R Mid", "Pass Through 3", ...).
#
# Outputs and inputs use SEPARATE id spaces - the same CN means different things
# in <OC> and <IC> (CN="38" is Subwoofer R on an output, Digital In L on an
# input), so never resolve one against the other's table.
#
# The ids below are NOT the order PC-Tool lists these in its UI - the two agree
# only up to 28. Line Out 1-8 hold 29-36, which pushes Subwoofer L/R out to
# 37/38, and Pass Through splits across two disjoint runs (1-6 at 39-44, 7-12 at
# 50-55) despite being contiguous on screen. Transcribing the displayed order
# mislabels everything from 29 up on outputs, and most of the input list.
#
# Input id 9 is unused - the input list jumps Front R Low (8) to
# Front Center Full (10).

OUTPUT_CHANNEL_NAMES = {
    0: "Not assigned",
    1: "Front L Full",
    2: "Front R Full",
    3: "Front L High",
    4: "Front R High",
    5: "Front L Mid",
    6: "Front R Mid",
    7: "Front L Low",
    8: "Front R Low",
    9: "Front Center Full",
    10: "Front Center High",
    11: "Front Center Low",
    12: "F Sum",
    13: "Rear L Full",
    14: "Rear R Full",
    15: "Rear L High",
    16: "Rear R High",
    17: "Rear L Mid",
    18: "Rear R Mid",
    19: "Rear L Low",
    20: "Rear R Low",
    21: "Rear Fill Full",
    22: "Rear Fill High",
    23: "Rear Fill Low",
    24: "Rear Sum",
    25: "Subwoofer 1",
    26: "Subwoofer 2",
    27: "Subwoofer 3",
    28: "Subwoofer 4",
    29: "Line Out 1",
    30: "Line Out 2",
    31: "Line Out 3",
    32: "Line Out 4",
    33: "Line Out 5",
    34: "Line Out 6",
    35: "Line Out 7",
    36: "Line Out 8",
    37: "Subwoofer L",
    38: "Subwoofer R",
    39: "Pass Through 1",
    40: "Pass Through 2",
    41: "Pass Through 3",
    42: "Pass Through 4",
    43: "Pass Through 5",
    44: "Pass Through 6",
    45: "Bridge Mode",
    46: "Surround L Full",
    47: "Surround R Full",
    48: "Front Subwoofer L",
    49: "Front Subwoofer R",
    50: "Pass Through 7",
    51: "Pass Through 8",
    52: "Pass Through 9",
    53: "Pass Through 10",
    54: "Pass Through 11",
    55: "Pass Through 12",
    56: "User defined Name",
}

INPUT_CHANNEL_NAMES = {
    0: "Not assigned",
    1: "Front L Full",
    2: "Front R Full",
    3: "Front L High",
    4: "Front R High",
    5: "Front L Mid",
    6: "Front R Mid",
    7: "Front L Low",
    8: "Front R Low",
    10: "Front Center Full",
    11: "Front Center High",
    12: "Front Center Low",
    13: "F Sum",
    14: "Rear L Full",
    15: "Rear R Full",
    16: "Rear L High",
    17: "Rear R High",
    18: "Rear L Mid",
    19: "Rear R Mid",
    20: "Rear L Low",
    21: "Rear R Low",
    22: "Rear Fill Full",
    23: "Rear Fill High",
    24: "Rear Fill Low",
    25: "R Sum",
    26: "Subwoofer 1",
    27: "Subwoofer 2",
    28: "Subwoofer 3",
    29: "Subwoofer 4",
    30: "Line In 1",
    31: "Line In 2",
    32: "Line In 3",
    33: "Line In 4",
    34: "Line In 5",
    35: "Line In 6",
    36: "Line In 7",
    37: "Line In 8",
    38: "Digital In L",
    39: "Digital In R",
    40: "Opt. In 3",
    41: "Opt. In 4",
    42: "Opt. In 5",
    43: "Opt. In 6",
    44: "Opt. In 7",
    45: "Opt. In 8",
    46: "Opt. Sub 1",
    47: "Opt. Sub 2",
    48: "Opt. Sub 3",
    49: "Opt. Sub 4",
    50: "Opt. Sub 5",
    51: "Opt. Sub 6",
    52: "Opt. Sub 7",
    53: "Opt. Sub 8",
    54: "AUX L",
    55: "AUX R",
    56: "HEC L",
    57: "HEC R",
    58: "MEC L",
    59: "MEC R",
    60: "Front MID",
    61: "Front SIDE",
    62: "Rear MID",
    63: "Rear SIDE",
    64: "AUX2 L",
    65: "AUX2 R",
    66: "ASD Front Left",
    67: "ASD Front Right",
    68: "ASD Rear Left",
    69: "ASD Rear Right",
    70: "Subwoofer L",
    71: "Subwoofer R",
    72: "Surround L Full",
    73: "Surround R Full",
    74: "Front Subwoofer L",
    75: "Front Subwoofer R",
    76: "USB L",
    77: "USB R",
}

SAMPLE_RATE = 96000.0  # ACO DSPs run 96 kHz natively
SPEED_OF_SOUND_CM_S = 34300.0

TOOL_VERSION = "1.2.0"
# v1 is additive-only: new optional fields may appear, existing ones won't
# change meaning or disappear. A breaking change gets a v2 path alongside it,
# never a v1 edit in place - so pinning to this URL is safe indefinitely.
SCHEMA_URL = "https://raw.githubusercontent.com/sl463/pct6-tools/main/schema/v1/pct6-tune.schema.json"


def xor(data, key):
    if key is None:
        return data
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def decode(data):
    """Return (xml_bytes, mode_description). Raises ValueError if no variant fits."""
    for key in KEYS:
        blob = xor(data, key)
        try:
            expected = struct.unpack(">I", blob[:4])[0]
            out = zlib.decompress(blob[4:])
        except Exception:
            continue
        if len(out) != expected:
            continue
        return out, MODE_NAMES[key]
    # Last resort: the file may be plain XML ("No compression used").
    if data.lstrip()[:1] == b"<":
        return data, "no compression"
    raise ValueError("failed to detect format")


def db(linear):
    """Linear amplitude -> dB."""
    if linear <= 0:
        return float("-inf")
    return 20.0 * math.log10(linear)


def delay_ms(raw):
    return raw / SAMPLE_RATE * 1000.0


def delay_cm(raw):
    return raw / SAMPLE_RATE * SPEED_OF_SOUND_CM_S


def parse_filter(fil):
    t = int(fil.get("T", "0"))
    kind, label = FILTER_TYPES.get(t, ("unknown", f"unknown type {t}"))
    return {
        "type_id": t,
        "kind": kind,
        "label": label,
        "freq_hz": float(fil.get("F", "0")),
        # For peaking bands G is gain in dB; for crossovers it is the slope in dB/oct.
        "gain_db": float(fil.get("G", "0")),
        "q": float(fil.get("Q", "0")),
        "bypassed": fil.get("FilBy") == "1",
    }


def parse_channel(el, role):
    """role is "output" (<OC>, indexed by ON) or "input" (<IC>, indexed by IN) -
    the two elements share the <Fil>/<Vol>/<T> shape but carry different index
    and enable attributes, so the caller must say which it is."""
    fils = [parse_filter(f) for f in el if f.tag == "Fil"]
    vol = el.find("Vol")
    time = el.find("T")
    level = float(vol.get("L")) if vol is not None else 1.0
    raw_delay = int(time.get("T", "0")) if time is not None else 0
    eq = [
        f for f in fils
        if f["kind"] == "peak" and not f["bypassed"]
        and (f["gain_db"] != 0.0 or f["q"] != 4.3)
    ]
    index_attr = "ON" if role == "output" else "IN"
    channel_id = int(el.get("CN", "-1"))
    return {
        "role": role,
        "index": int(el.get(index_attr, "-1")),
        "channel_id": channel_id,
        "channel_name": (OUTPUT_CHANNEL_NAMES if role == "output"
                         else INPUT_CHANNEL_NAMES).get(channel_id),
        # <IC> has no CE (enable) attribute of its own - inputs are enabled
        # whenever they're wired up in <Route>, not flagged per-channel here.
        "enabled": (el.get("CE") == "1") if role == "output" else None,
        "eq_bypassed": el.get("EqBy") == "1",
        "polarity_inverted": el.get("CINV") == "1",
        # <IC> carries no delay/link group of its own.
        "delay_group": el.get("DG") if role == "output" else None,
        "link_group": el.get("LG") if role == "output" else None,
        "gain_db": db(level),
        "gain_linear": level,
        "delay_raw": raw_delay,
        "delay_ms": delay_ms(raw_delay),
        "delay_cm": delay_cm(raw_delay),
        # A crossover slot is only in circuit when it is not bypassed and its
        # slope (stored in G, as dB/oct) is non-zero.
        "highpass": next(
            (f for f in fils if f["kind"] == "highpass" and not f["bypassed"]
             and f["gain_db"] != 0.0), None
        ),
        "lowpass": next(
            (f for f in fils if f["kind"] == "lowpass" and not f["bypassed"]
             and f["gain_db"] != 0.0), None
        ),
        "eq_bands": eq,
        "eq_band_count": len(eq),
        # Every XML attribute verbatim, so nothing this parser doesn't yet
        # understand (HPi/LPi/Finit/MT/... - default-filter and mode indices
        # that don't bear on EQ/crossover/delay/gain) is silently dropped.
        "raw_attrib": dict(el.attrib),
    }


def extract(path):
    raw = open(path, "rb").read()
    xml_bytes, mode = decode(raw)
    root = ET.fromstring(xml_bytes)
    outputs = [parse_channel(c, "output") for c in root if c.tag == "OC"]
    inputs = [parse_channel(c, "input") for c in root if c.tag == "IC"]
    return {
        "$schema": SCHEMA_URL,
        "source_file": os.path.basename(path),
        "decoder": f"pct6_extract.py v{TOOL_VERSION}",
        "container_mode": mode,
        "xml_bytes": len(xml_bytes),
        "meta": dict(root.attrib),
        "outputs": outputs,
        "inputs": inputs,
    }, xml_bytes


def xover_str(f):
    if f is None:
        return "-"
    return f"{f['freq_hz']:g} Hz {f['gain_db']:g} dB/oct {f['label'].split()[-1]}"


def speaker_str(ch):
    """Assigned speaker/channel name, falling back to the raw CN for an id this
    build of PC-Tool doesn't have a name for."""
    return ch["channel_name"] or f"CN {ch['channel_id']}"


def report(data, show_all=False):
    meta = data["meta"]
    print(f"Container   : {data['container_mode']}, {data['xml_bytes']} bytes of XML")
    print(f"PC-Tool     : {meta.get('V')}   device id {meta.get('Dev')}")
    print(f"Saved       : {meta.get('D')}")
    print(f"Source file : {meta.get('FN')}")
    print(f"Channels    : {meta.get('INS')} inputs / {meta.get('OUTS')} outputs")

    configured = [o for o in data["outputs"]
                  if o["eq_band_count"] or o["highpass"] or o["lowpass"]
                  or o["delay_raw"] or abs(o["gain_db"]) > 1e-9]
    print(f"\n{len(configured)} of {len(data['outputs'])} outputs carry settings")

    # An output can have a speaker assigned without being dialled in yet. That
    # assignment is real and worth surfacing, so count it either way and show it
    # in full under --all.
    pending = [o for o in data["outputs"]
               if o not in configured and o["channel_id"] != 0]
    if show_all:
        active = data["outputs"]
        if pending:
            print(f"{len(pending)} more are assigned but not yet configured")
    else:
        active = configured
        if pending:
            print(f"({len(pending)} more have a speaker assigned but no settings "
                  f"yet - use --all to list them)")
    print()

    hdr = (f"{'Out':>3}  {'Speaker':<18}  {'Gain':>7}  {'Delay':>19}  {'Pol':>4}  {'EQ':>3}  "
           f"{'Highpass':<28} {'Lowpass':<28}")
    print(hdr)
    print("-" * len(hdr))
    for o in active:
        delay = f"{o['delay_raw']:4d} ({o['delay_ms']:5.2f} ms {o['delay_cm']:5.1f} cm)"
        pol = "INV" if o["polarity_inverted"] else "+"
        print(f"{o['index']:>3}  {speaker_str(o):<18}  {o['gain_db']:+6.1f}dB  {delay:>19}  {pol:>4}  "
              f"{o['eq_band_count']:>3}  {xover_str(o['highpass']):<28} {xover_str(o['lowpass']):<28}")

    for o in active:
        if not o["eq_bands"]:
            continue
        print(f"\n--- Output {o['index']} ({speaker_str(o)}): {o['eq_band_count']} EQ bands")
        print(f"    {'#':>2}  {'Freq':>9}  {'Gain':>7}  {'Q':>6}")
        for i, f in enumerate(o["eq_bands"], 1):
            print(f"    {i:>2}  {f['freq_hz']:>8.0f}  {f['gain_db']:>+6.1f}  {f['q']:>6.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--xml", action="store_true", help="write the decoded XML to stdout")
    ap.add_argument("--json", action="store_true", help="write parsed settings as JSON")
    ap.add_argument("--all", action="store_true",
                    help="list every output, including ones with a speaker assigned "
                         "but no settings dialled in yet")
    args = ap.parse_args()

    try:
        data, xml_bytes = extract(args.file)
    except ValueError as exc:
        sys.exit(f"error: {exc}")

    if args.xml:
        sys.stdout.buffer.write(xml_bytes)
    elif args.json:
        json.dump(data, sys.stdout, indent=2)
    else:
        report(data, show_all=args.all)


if __name__ == "__main__":
    main()
