#!/usr/bin/env python3
"""Structural analysis of Audiotec Fischer DSP PC-Tool 6 setup files (.pct6).

The .pct6 container is proprietary and undocumented. This tool does not decode
tune settings; it characterises the payload so we can tell what kind of
container we are dealing with (plain, compressed, or encrypted) and track that
answer as new sample files arrive.

    ./pct6_analyze.py tune.pct6              # structural report
    ./pct6_analyze.py --codecs tune.pct6     # + decompressor brute force
    ./pct6_analyze.py --diff a.pct6 b.pct6   # differential analysis
"""

import argparse
import bz2
import collections
import gzip
import lzma
import math
import zlib

MAGIC = b"AT"


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def entropy(data):
    if not data:
        return 0.0
    counts = collections.Counter(data)
    return -sum(
        (c / len(data)) * math.log2(c / len(data)) for c in counts.values()
    )


def chi_square(data):
    """Chi-square against a uniform byte distribution (df=255)."""
    counts = collections.Counter(data)
    expected = len(data) / 256
    return sum((counts.get(b, 0) - expected) ** 2 / expected for b in range(256))


def header_report(data, path):
    print(f"=== {path}")
    print(f"size            {len(data)} bytes")
    print(f"magic           {data[:2]!r} {'(ok)' if data[:2] == MAGIC else '(UNEXPECTED)'}")
    print(f"first 16 bytes  {data[:16].hex(' ')}")
    print(f"last 16 bytes   {data[-16:].hex(' ')}")
    print(f"size % 16       {len(data) % 16}  (0 is consistent with 128-bit block cipher)")


def distribution_report(data, window=512):
    h = entropy(data)
    chi = chi_square(data)
    print(f"\n-- byte distribution")
    print(f"entropy         {h:.4f} bits/byte (max 8.0)")
    print(f"chi-square      {chi:.1f} (df=255; uniform random ~255 +/- 22)")
    print(f"distinct bytes  {len(set(data))}/256")
    print(f"per-{window}-byte window entropy:")
    for off in range(0, len(data), window):
        chunk = data[off : off + window]
        print(f"  {off:6d} len={len(chunk):4d}  H={entropy(chunk):.3f}")


def ngram_report(data, sizes=(4, 8, 12, 16)):
    """Exact repeated n-grams.

    Encryption of any quality yields none of these. Their presence, and the
    spacing between them, is the strongest signal about the payload.
    """
    print(f"\n-- repeated n-grams (encrypted data should have none for n>=8)")
    for n in sizes:
        counts = collections.Counter(
            data[i : i + n] for i in range(len(data) - n + 1)
        )
        repeats = sorted(
            ((c, g) for g, c in counts.items() if c > 1), reverse=True
        )
        expected = (len(data) ** 2 / 2) / (256.0**n)
        print(f"  n={n:2d}: {len(repeats):3d} repeated (chance expectation {expected:.4g})")
        for count, gram in repeats[:3]:
            offs = [
                i for i in range(len(data) - n + 1) if data[i : i + n] == gram
            ]
            deltas = [offs[i + 1] - offs[i] for i in range(len(offs) - 1)]
            print(f"       x{count} {gram.hex()} at {offs[:6]} spacing {deltas[:5]}")


def bit_autocorrelation(data, max_shift=256, top=10):
    """Bit-level self-similarity.

    A repeated symbol in a Huffman-coded bitstream shows up as a peak at
    lcm(code_length, 8) bits, which is how a compressed bitstream can be
    distinguished from ciphertext.
    """
    bits = [(byte >> i) & 1 for byte in data for i in range(7, -1, -1)]
    n = len(bits)
    scores = []
    for shift in range(1, max_shift + 1):
        matches = sum(1 for i in range(n - shift) if bits[i] == bits[i + shift])
        scores.append((matches / (n - shift), shift))
    sigma = 0.5 / math.sqrt(n)
    print(f"\n-- bit autocorrelation (0.5 = random, 1 sigma = {sigma:.4f})")
    for score, shift in sorted(scores, reverse=True)[:top]:
        z = (score - 0.5) / sigma
        print(f"  shift {shift:4d} bits ({shift / 8:6.2f} bytes): {score:.4f}  {z:+.1f} sigma")


def _shift_bits(data, bits):
    """Drop `bits` leading bits, LSB-first, so raw deflate can be probed at
    non-byte-aligned starts."""
    value = int.from_bytes(data, "little") >> bits
    return value.to_bytes(len(data), "little").rstrip(b"\x00") or b"\x00"


def codec_probe(data, max_offset=64, min_output=100):
    """Brute-force standard decompressors across byte and bit offsets."""
    print(f"\n-- codec probe (offsets 0..{max_offset - 1})")
    hits = []

    for name, fn in (
        ("gzip", gzip.decompress),
        ("bz2", bz2.decompress),
        ("lzma/xz", lzma.decompress),
    ):
        for off in range(max_offset):
            try:
                out = fn(data[off:])
                if len(out) >= min_output:
                    hits.append((name, off, len(out)))
            except Exception:
                pass

    for off in range(max_offset):
        for wbits in (15, -15, 31, 47):
            for bitshift in range(8):
                if bitshift and wbits != -15:
                    continue  # bit alignment only matters for raw deflate
                blob = _shift_bits(data[off:], bitshift) if bitshift else data[off:]
                try:
                    out = zlib.decompressobj(wbits).decompress(blob)
                    if len(out) >= min_output:
                        hits.append((f"deflate wbits={wbits} bit={bitshift}", off, len(out)))
                except Exception:
                    pass

    # LZMA1 raw: every legal lc/lp/pb combination, since a raw stream carries
    # no properties byte of its own.
    for off in (0, 2, 4, 5, 6, 8, 13, 16):
        for props in range(225):
            lc, rem = props % 9, props // 9
            lp, pb = rem % 5, rem // 5
            for dict_size in (1 << 16, 1 << 20, 1 << 24):
                try:
                    out = lzma.LZMADecompressor(
                        format=lzma.FORMAT_RAW,
                        filters=[{
                            "id": lzma.FILTER_LZMA1,
                            "lc": lc, "lp": lp, "pb": pb,
                            "dict_size": dict_size,
                        }],
                    ).decompress(data[off:])
                    if len(out) >= min_output:
                        hits.append((f"lzma1 lc={lc} lp={lp} pb={pb}", off, len(out)))
                except Exception:
                    pass

    for module, name, fn in _optional_codecs():
        for off in range(max_offset):
            try:
                out = fn(data[off:])
                if out and len(out) >= min_output:
                    hits.append((name, off, len(out)))
            except Exception:
                pass
        del module

    if hits:
        for name, off, size in hits:
            print(f"  HIT {name} at offset {off}: {size} bytes")
    else:
        print("  no hits: payload is not any standard compressed container")
    return hits


def _optional_codecs():
    """Codecs probed only when the optional package is installed."""
    codecs = []
    try:
        import lz4.block
        import lz4.frame

        codecs.append((lz4, "lz4.frame", lz4.frame.decompress))
        codecs.append((lz4, "lz4.block", lambda b: lz4.block.decompress(b, uncompressed_size=1 << 20)))
    except ImportError:
        pass
    try:
        import zstandard

        codecs.append((zstandard, "zstd", lambda b: zstandard.ZstdDecompressor().decompressobj().decompress(b)))
    except ImportError:
        pass
    try:
        import brotli

        codecs.append((brotli, "brotli", brotli.decompress))
    except ImportError:
        pass
    return codecs


def diff_report(paths):
    """Compare sample files.

    Localised differences would mean a plain container that can be mapped
    parameter by parameter; whole-file differences mean the payload is
    compressed or encrypted and single-parameter mapping will not work.
    """
    blobs = [(p, read(p)) for p in paths]
    print("=== differential analysis")
    for path, data in blobs:
        print(f"  {path}: {len(data)} bytes")

    base_path, base = blobs[0]
    for path, other in blobs[1:]:
        common = min(len(base), len(other))
        differing = [i for i in range(common) if base[i] != other[i]]
        print(f"\n-- {base_path} vs {path}")
        print(f"  length delta      {len(other) - len(base):+d} bytes")
        if not differing:
            print("  identical over the common prefix")
            continue
        print(f"  differing bytes   {len(differing)}/{common} ({100 * len(differing) / common:.1f}%)")
        print(f"  first difference  offset {differing[0]}")
        print(f"  last difference   offset {differing[-1]}")
        runs = []
        start = prev = differing[0]
        for off in differing[1:]:
            if off != prev + 1:
                runs.append((start, prev))
                start = off
            prev = off
        runs.append((start, prev))
        print(f"  differing runs    {len(runs)}")
        for lo, hi in runs[:10]:
            print(f"    {lo}..{hi} ({hi - lo + 1} bytes)")
        if len(differing) / common > 0.5:
            print("  => whole-file change: payload is compressed or encrypted")
        else:
            print("  => localised change: candidate for direct field mapping")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", metavar="FILE")
    parser.add_argument("--codecs", action="store_true", help="run the decompressor brute force")
    parser.add_argument("--diff", action="store_true", help="compare files instead of profiling them")
    args = parser.parse_args()

    if args.diff:
        if len(args.files) < 2:
            parser.error("--diff needs at least two files")
        diff_report(args.files)
        return

    for path in args.files:
        data = read(path)
        header_report(data, path)
        distribution_report(data)
        ngram_report(data)
        bit_autocorrelation(data)
        if args.codecs:
            codec_probe(data)
        print()


if __name__ == "__main__":
    main()
