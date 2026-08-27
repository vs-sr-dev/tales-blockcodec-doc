#!/usr/bin/env python3
"""Compare two builds' copies of the block decoder, instruction by instruction.

The claim that two shipped games contain *the same* decompressor rather than
two implementations of one format is only worth making if it can be checked.
This does the checking: given two PlayStation executables and the virtual
address of the same routine in each, it reports how long the identical prefix
is and where the first difference falls.

The ring-preload prologue is the part that matters.  It contains no `lui` /
`addiu` address pairs, so nothing in it can differ merely because the code was
linked at a different address -- an identical prefix there is identical
compiler output from identical source, not an artefact of relocation.

    python decoder_diff.py A.EXE 0x80023504 B.EXE 0x80150BB0 [--words 140]

The load address of each executable is read from its PS-EXE header, so no
addresses need to be supplied beyond the two routine entries.

Known pairs:

    Tales of Eternia SLPS_030.50  0x80023504   method 1
    Tales of Destiny SLPS_011.00  0x80150BB0   method 1

    Tales of Eternia SLPS_030.50  0x80023690   method 3
    Tales of Destiny SLPS_011.00  0x80150D4C   method 3
"""

import struct
import sys

HEADER = 0x800


def load(path):
    """(bytes, text virtual address) for a PS-EXE."""
    b = open(path, 'rb').read()
    if b[:8] != b'PS-X EXE':
        raise SystemExit('%s is not a PS-EXE' % path)
    text_va = struct.unpack_from('<I', b, 0x18)[0]
    return b, text_va


def words(buf, text_va, va, n):
    o = va - text_va + HEADER
    if o < 0 or o + 4 * n > len(buf):
        raise SystemExit('0x%08X is outside %d bytes of text' % (va, len(buf)))
    return struct.unpack_from('<%dI' % n, buf, o)


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 1
    n = int(argv[argv.index('--words') + 1]) if '--words' in argv else 140
    pa, va_a, pb, va_b = argv[0], int(argv[1], 0), argv[2], int(argv[3], 0)

    ba, ta = load(pa)
    bb, tb = load(pb)
    wa = words(ba, ta, va_a, n)
    wb = words(bb, tb, va_b, n)

    k = 0
    while k < n and wa[k] == wb[k]:
        k += 1

    print('A  %s   text at 0x%08X, routine at 0x%08X' % (pa, ta, va_a))
    print('B  %s   text at 0x%08X, routine at 0x%08X' % (pb, tb, va_b))
    print()
    print('identical prefix: %d words (%d bytes)' % (k, k * 4))
    print('  A 0x%08X .. 0x%08X' % (va_a, va_a + k * 4 - 4))
    print('  B 0x%08X .. 0x%08X' % (va_b, va_b + k * 4 - 4))
    if k == n:
        print('  (the whole compared window is identical)')
        return 0

    print('\nfirst 12 differences after that:')
    shown = 0
    for i in range(k, n):
        if wa[i] == wb[i]:
            continue
        print('  +0x%03X   A %08X @ 0x%08X     B %08X @ 0x%08X'
              % (i * 4, wa[i], va_a + i * 4, wb[i], va_b + i * 4))
        shown += 1
        if shown >= 12:
            break

    same = sum(1 for i in range(n) if wa[i] == wb[i])
    print('\nover the whole %d-word window: %d identical, %d differing (%.0f%%)'
          % (n, same, n - same, 100.0 * same / n))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
