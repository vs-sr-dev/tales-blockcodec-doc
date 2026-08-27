#!/usr/bin/env python3
"""Reference decoder for the Tales block codec, in both of its known dialects.

One nine-byte header, one token grammar, one run escape, two addressing
conventions.  See tales-block-codec.md for the specification and the evidence.

    +0  u8   method
    +1  u32  packed size    the number of stream bytes that follow the header
    +5  u32  unpacked size   advisory; neither compressed path reads it
    +9       stream

    method   dialect       meaning
    ----------------------------------------------------------------
    $80..    snes          stored (any byte that is not $81 or $83)
    $81      snes          LZSS
    $83      snes          LZSS + run escape
    0        psx           stored
    1        psx           LZSS
    3        psx           LZSS + run escape

Usage:
    python tales_block.py IMAGE OFFSET [-o OUT] [--dialect snes|psx|auto]
    python tales_block.py IMAGE --scan  [--dialect snes|psx|auto]
    python tales_block.py --selftest
"""

import sys

RING = 4096

SNES, PSX = 'snes', 'psx'

METHODS = {
    SNES: {0x81: 'lzss', 0x83: 'run'},
    PSX:  {0x00: 'stored', 0x01: 'lzss', 0x03: 'run'},
}


class BlockError(Exception):
    pass


# --------------------------------------------------------------------------
# the dictionary


def preload(dialect):
    """The ring as the decoder leaves it before the first token.

    The PlayStation decoder seeds 3,840 bytes of alternating (i, 0x00) and
    (i, 0xFF) pairs so that 4bpp tile rows and 0xFF-padded tables can be
    matched without spending literals on them first.  The Super Famicom
    decoder has no ring at all -- it reads the output buffer directly -- which
    is modelled here as an empty ring, and is equivalent because a distance
    can never reach behind the start of the output.
    """
    r = bytearray(RING)
    if dialect != PSX:
        return r
    p = 0
    for i in range(256):                    # 0x0000-0x07FF
        r[p:p + 8] = bytes((i, 0, i, 0, i, 0, i, 0))
        p += 8
    for i in range(256):                    # 0x0800-0x0EFF
        r[p:p + 7] = bytes((i, 255, i, 255, i, 255, i))
        p += 7
    return r


def cursor_start(dialect, kind):
    """Where the write cursor begins.

    Textbook LZSS starts at N - F, F being the longest encodable match: 18 for
    the plain variant, 17 for the one that spends the all-ones length code on
    a run escape.  The Super Famicom decoder addresses the output rather than a
    ring, so it effectively starts at zero.
    """
    if dialect != PSX:
        return 0
    return RING - (17 if kind == 'run' else 18)


# --------------------------------------------------------------------------
# the token stream


def header(buf, off=0):
    if off + 9 > len(buf):
        raise BlockError('truncated header at %d' % off)
    method = buf[off]
    packed = int.from_bytes(buf[off + 1:off + 5], 'little')
    unpacked = int.from_bytes(buf[off + 5:off + 9], 'little')
    return method, packed, unpacked


def classify(method, dialect):
    """'stored' | 'lzss' | 'run' for this method byte in this dialect."""
    table = METHODS[dialect]
    if method in table:
        return table[method]
    if dialect == SNES:
        return 'stored'
    raise BlockError('method %d is not defined in the %s dialect'
                     % (method, dialect))


def sniff(buf, off=0):
    """Guess the dialect from the method byte alone."""
    m = buf[off] if off < len(buf) else None
    if m in (0x81, 0x83):
        return SNES
    if m in (0x00, 0x01, 0x03):
        return PSX
    raise BlockError('0x%02X is not a method byte in either dialect' % (m or 0))


def unpack_stream(src, dialect, kind):
    """Decode one raw token stream.  Returns bytes."""
    ring = preload(dialect)
    pos = cursor_start(dialect, kind)
    out = bytearray()
    i, n = 0, len(src)
    flags = 0
    bits = 0

    def emit(c):
        nonlocal pos
        ring[pos] = c
        pos = (pos + 1) & (RING - 1)
        out.append(c)

    while i < n:
        if bits == 0:
            flags = src[i]
            i += 1
            bits = 8
            if i > n:
                break
        bit = flags & 1
        flags >>= 1
        bits -= 1

        if bit:                                     # literal
            if i >= n:
                break
            emit(src[i])
            i += 1
            continue

        if i + 1 >= n:
            break
        b0, b1 = src[i], src[i + 1]
        i += 2

        # The two dialects split the second token byte the opposite way round.
        if dialect == SNES:
            length_code = b1 >> 4
            other = b1 & 0x0F
            source = (pos - (b0 | (other << 8))) & (RING - 1)
        else:
            length_code = b1 & 0x0F
            other = b1 >> 4
            source = b0 | (other << 8)

        if kind == 'run' and length_code == 0x0F:    # the run escape
            if other:
                count, value = other + 3, b0        # 2-byte token, 4..18
            else:
                if i >= n:
                    break
                count, value = b0 + 19, src[i]      # 3-byte token, 19..274
                i += 1
            for _ in range(count):
                emit(value)
            continue

        for k in range(length_code + 3):            # back-reference, 3..18
            emit(ring[(source + k) & (RING - 1)])

    return bytes(out)


def unpack(buf, off=0, dialect=None):
    """Decode the block at off, header included."""
    if dialect in (None, 'auto'):
        dialect = sniff(buf, off)
    method, packed, unpacked = header(buf, off)
    kind = classify(method, dialect)
    if kind == 'stored':
        return bytes(buf[off + 9:off + 9 + unpacked])
    return unpack_stream(buf[off + 9:off + 9 + packed], dialect, kind)


# --------------------------------------------------------------------------
# finding blocks


def plausible(buf, off, dialect):
    if off + 9 > len(buf):
        return False
    method = buf[off]
    if method not in METHODS[dialect] or METHODS[dialect][method] == 'stored':
        return False
    packed = int.from_bytes(buf[off + 1:off + 5], 'little')
    unpacked = int.from_bytes(buf[off + 5:off + 9], 'little')
    # The Super Famicom decoder loads each size with a 16-bit LDA and never
    # reads the upper half; the PlayStation one assembles all four bytes.
    cap = 0xFFFF if dialect == SNES else 0xFFFFFF
    if not 16 <= packed <= cap or not 16 <= unpacked <= cap:
        return False
    if unpacked < packed:                  # the packer never emits expansion
        return False
    return off + 9 + packed <= len(buf)


def scan(buf, dialect, step=1):
    """Every offset whose block decodes to its own declared length."""
    hits = []
    for off in range(0, len(buf) - 9, step):
        if not plausible(buf, off, dialect):
            continue
        _, packed, unpacked = header(buf, off)
        try:
            out = unpack(buf, off, dialect)
        except BlockError:
            continue
        if len(out) == unpacked:
            hits.append((off, buf[off], packed, unpacked))
    return hits


# --------------------------------------------------------------------------
# self-test: the format's own arithmetic, with no image required


SELFTEST = [
    # (dialect, kind, stream, expected)
    # eight literals, then a short run of the last one
    (PSX, 'run', bytes([0xFF]) + b'ABCDEFGH', b'ABCDEFGH'),
    (SNES, 'run', bytes([0xFF]) + b'ABCDEFGH', b'ABCDEFGH'),
    # PSX short run: b1 low nibble $F escapes, high nibble 1 -> 1+3 = 4 copies
    (PSX, 'run', bytes([0x00, 0x5A, 0x1F]), b'\x5a' * 4),
    # SNES short run: b1 high nibble $F escapes, low nibble 1 -> 4 copies
    (SNES, 'run', bytes([0x00, 0x5A, 0xF1]), b'\x5a' * 4),
    # PSX long run: high nibble 0 -> count = b0 + 19, value from the stream
    (PSX, 'run', bytes([0x00, 0x00, 0x0F, 0x77]), b'\x77' * 19),
    # SNES long run: b1 == $F0 -> count = b0 + 19, value from the stream
    (SNES, 'run', bytes([0x00, 0x00, 0xF0, 0x77]), b'\x77' * 19),
    # plain variant: length code $F is a match of 18, not an escape
    (PSX, 'lzss', bytes([0x01]) + b'Z' + bytes([0x00, 0xFF, 0x0F]), None),
]


def selftest():
    ok = True
    for dialect, kind, stream, expect in SELFTEST:
        got = unpack_stream(stream, dialect, kind)
        if expect is None:
            print('  %-4s %-6s -> %d bytes' % (dialect, kind, len(got)))
            continue
        good = got == expect
        ok &= good
        print('  %-4s %-6s -> %-22r %s'
              % (dialect, kind, got[:22], 'ok' if good else 'FAILED, want %r' % expect))
    # the two dialects must agree on the run ranges
    for n in range(1, 16):
        a = unpack_stream(bytes([0x00, 0x5A, (n << 4) | 0x0F]), PSX, 'run')
        b = unpack_stream(bytes([0x00, 0x5A, 0xF0 | n]), SNES, 'run')
        if a != b or len(a) != n + 3:
            print('  short-run mismatch at n=%d: %d vs %d' % (n, len(a), len(b)))
            ok = False
    print('  short runs 4..18 agree across dialects')
    for v in (0, 1, 255):
        a = unpack_stream(bytes([0x00, v, 0x0F, 0x77]), PSX, 'run')
        b = unpack_stream(bytes([0x00, v, 0xF0, 0x77]), SNES, 'run')
        if a != b or len(a) != v + 19:
            print('  long-run mismatch at b0=%d' % v)
            ok = False
    print('  long runs 19..274 agree across dialects')
    print('selftest %s' % ('passed' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv):
    if '--selftest' in argv:
        return selftest()
    path = argv[0]
    buf = open(path, 'rb').read()
    dialect = argv[argv.index('--dialect') + 1] if '--dialect' in argv else 'auto'

    if '--scan' in argv:
        if dialect == 'auto':
            sys.exit('--scan needs an explicit --dialect')
        hits = scan(buf, dialect)
        print('# offset     method  packed    unpacked   ratio')
        for off, m, p, u in hits:
            print('0x%08X   0x%02X  %8d  %9d   %.2fx' % (off, m, p, u, u / p))
        print('\n# %d blocks, %d packed -> %d unpacked'
              % (len(hits), sum(h[2] for h in hits), sum(h[3] for h in hits)))
        return 0

    off = int(argv[1], 0)
    if dialect == 'auto':
        dialect = sniff(buf, off)
    method, packed, unpacked = header(buf, off)
    out = unpack(buf, off, dialect)
    sys.stderr.write('%s  method 0x%02X (%s)  packed %d  unpacked %d  produced %d  [%s]\n'
                     % (dialect, method, classify(method, dialect), packed,
                        unpacked, len(out),
                        'exact' if len(out) == unpacked
                        else '%+d' % (len(out) - unpacked)))
    if '-o' in argv:
        open(argv[argv.index('-o') + 1], 'wb').write(out)
    else:
        sys.stdout.buffer.write(out)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
