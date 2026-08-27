# The Tales block codec

The in-house LZSS that Wolf Team shipped on the Super Famicom in 1995 and that
turned up again, essentially unchanged, on the PlayStation in 1997.

This document is the format. It is written to be read once in order and
grepped afterwards, and it is deliberately title-agnostic: addresses, block
counts and per-game verification live in the title pipelines listed in the
[README](README.md), not here.

`tales_block.py` in this repository is the reference decoder. It implements
everything below as one machine with a dialect switch, and reproduces both
titles' own independently written decoders byte for byte
([`reports/cross-check.txt`](reports/cross-check.txt)).

---

## 1. The block header

Nine bytes, identical on both machines.

| Offset | Size | Field |
|---|---|---|
| `+0` | u8 | method |
| `+1` | u32 LE | packed size — the number of stream bytes that follow the header |
| `+5` | u32 LE | unpacked size |
| `+9` | — | stream begins |

**The compressed paths are driven only by the packed size.** Neither decoder
reads `+5` on a compressed block; the loop runs until the input is exhausted.
Treat `+5` as metadata written by the packer — useful, and on both discs
examined so far correct, but not authoritative.

The Super Famicom decoder loads each size with a 16-bit `LDA` and never reads
the upper half, so on that platform the fields are effectively u16 with two
zero bytes after them. The PlayStation decoder assembles all four bytes, one
`lbu` at a time, because a container can place a block at any alignment.

### Method bytes

| Method | Dialect | Meaning |
|---|---|---|
| `$81` | Super Famicom | LZSS |
| `$83` | Super Famicom | LZSS + run escape |
| anything else | Super Famicom | stored |
| `1` | PlayStation | LZSS |
| `3` | PlayStation | LZSS + run escape |
| `0` | PlayStation | stored |
| anything else | PlayStation | error, returns −1 |

The low bits agree: `$81` ↔ `1`, `$83` ↔ `3`. The Super Famicom values carry
bit 7 set and the PlayStation values do not, and the PlayStation dispatcher
gained an explicit error case where the older one fell through to the stored
path.

---

## 2. The token stream

Byte-aligned. Identical in both dialects apart from one nibble.

### Control bits

A control byte is fetched whenever the shift register runs dry, and its bits
are consumed **least-significant first**.

| Bit | Meaning |
|---|---|
| `1` | copy one literal byte |
| `0` | a two-byte token follows |

The PlayStation implementation makes the register 16 bits wide and refills it
as `flags = byte | 0xFF00`, using the eight set bits in the high half as the
counter — after eight shifts bit 8 goes clear and the next byte is fetched.
The Super Famicom implementation keeps a separate bit count. The behaviour is
the same.

### The two-byte token

```
b0 = the low eight bits of the reference
b1 = the length code and the reference's top four bits, in some order
```

and the order is the one thing the two dialects disagree about:

| | Super Famicom | PlayStation |
|---|---|---|
| length code | `b1 >> 4` | `b1 & 0x0F` |
| reference top nibble | `b1 & 0x0F` | `b1 >> 4` |
| reference means | **distance backwards** from the current output position | **absolute index** into the ring |
| match length | `length_code + 3`, i.e. 3–18 | `length_code + 3`, i.e. 3–18 |

Both are the same mechanism. A ring that mirrors the last 4,096 output bytes
makes an absolute index `r` and a distance `d` interchangeable —
`r = (cursor − d) mod 4096` — so a single ring machine decodes both, which is
what `tales_block.py` does. The Super Famicom version computes the distance
directly because on that machine the destination is a 32 KiB WRAM buffer the
block-move instruction can address; the PlayStation version keeps a real ring
because its destination may be anywhere in a 2 MB address space.

Matches are copied one byte at a time and written back into the dictionary as
they go, so a match may legitimately overlap the cursor and re-read what it
has just written. That is the usual LZSS self-referential run and it is how
both dialects express a short repeat that the run escape cannot reach.

---

## 3. The run escape

Present only in the `$83` / method-3 variant, which spends the all-ones length
code on it. In the plain variant that code is an ordinary match of 18 bytes.

Let `n` be the *other* nibble of `b1` — the one that is not the length code.

| Condition | Emits | Token | Range |
|---|---|---|---|
| length code is all-ones, `n != 0` | `b0`, **n + 3** times | 2 bytes | 4 – 18 |
| length code is all-ones, `n == 0` | the next stream byte, **b0 + 19** times | 3 bytes | 19 – 274 |

The two forms are contiguous with no redundant encoding, and the run is
written into the dictionary as well as the output so later matches can reach
it.

### Why 3 and 19

Because of an instruction that only one of the two machines has.

The Super Famicom routine stores the fill byte once at `X`, sets the move
source to `X` and the destination to `X+1`, and lets a single `MVN` propagate
it forward. `MVN` transfers `A + 1` bytes, so the register always holds two
less than the number of bytes written — and the encoder's constant is
therefore two below the natural one. Short runs start at 4 with `n = 1`; long
runs start at 19 with `b0 = 0`.

The PlayStation routine has no `MVN`, writes its fill with an ordinary store
loop, and has no reason at all to be off by two. It is off by two anyway.

That is the strongest single piece of evidence that these are one format and
not two convergent designs. A compressor written from scratch for MIPS in 1997
does not pick 19 as the base of its long run length. It picks 19 because the
packer that produced the data was the same packer.

`tales_block.py --selftest` checks this without needing either image: it
decodes the same run counts through both dialects and asserts they agree
across the whole 4–18 and 19–274 range
([`reports/selftest.txt`](reports/selftest.txt)).

---

## 4. The dictionary

This is where the PlayStation version is genuinely new.

### Super Famicom

There is no dictionary. References are distances into the output buffer, and a
distance can never reach behind the start of the output, so there is nothing
to initialise.

### PlayStation

A 4,096-byte ring, rebuilt on the stack **on every call**, and it does not
start empty:

```
ring[0x0000 .. 0x07FF]   for i in 0..255:  i, 0x00, i, 0x00, i, 0x00, i, 0x00
ring[0x0800 .. 0x0EFF]   for i in 0..255:  i, 0xFF, i, 0xFF, i, 0xFF, i
ring[0x0F00 .. cursor-1]  zero
ring[cursor .. 0x0FFF]    left as whatever was on the stack
```

3,840 bytes of synthetic dictionary, installed before the first token is read.
It is a guess about what the data will look like: a 4bpp tile row where one
nibble is a colour index and the other is zero reads as `(i, 0x00)`, and a
table of small 16-bit values padded with `0xFF` reads as `(i, 0xFF)`. Both
patterns are matchable for free, without the packer spending literals to seed
them.

The write cursor starts at `4096 − F`, where `F` is the longest match the
variant can encode — the textbook LZSS `r = N − F`:

| Variant | Longest match | Cursor start | Bytes left undefined |
|---|---|---|---|
| method 1 | 18 | 4078 | 18 |
| method 3 | 17 (the escape takes the top code) | 4079 | 17 |

The bytes at and above the cursor are never initialised. A block that
referenced them would decode differently on every call; across both titles no
block does.

### What the preload buys

Measured on the two corpora, the ratio moves a long way:

| | Blocks | Packed | Unpacked | Ratio |
|---|---|---|---|---|
| Super Famicom, no preload | 1,089 | 2,032,803 | 3,758,965 | **1.85×** |
| PlayStation, preloaded | 6,638 | 148,665,346 | 464,839,924 | **3.13×** |

That comparison is not clean — the data is different, the assets are bigger
and more repetitive on a disc — so read it as an order of magnitude, not a
measurement of the preload alone. But the preload is the only change to the
dictionary between the two, and it is the change the team made.

---

## 5. The stored path

Both dialects have one, and only the older one works.

**Super Famicom.** Any method byte that is not `$81` or `$83` falls through to
a copy that takes its count from `+5` and its source from `+9`. It is used,
rarely — three blocks on the 1995 cartridge, all payloads the packer could not
shrink.

**PlayStation.** Method `0` reaches a byte copy that is handed the **packed**
size as its count and the pointer to the **block header** as its source,
because the dispatcher never advances it past `+9`. It would emit the nine
header bytes in front of the data.

It has never been exercised. Across 6,638 blocks on the 1997 disc, not one has
method `0`. The path exists because the format it was ported from had one, and
nothing tested the port because the packer had stopped emitting stored blocks.

`tales_block.py` implements the sane reading — count from `+5`, source from
`+9` — for both dialects, and documents the discrepancy rather than
reproducing it.

---

## 6. Where the format is, and is not

| Title | Platform | Year | Codec |
|---|---|---|---|
| Tales of Phantasia | Super Famicom | 1995 | **this format**, `$81` / `$83` |
| Tales of Destiny | PlayStation | 1997 | **this format**, methods 1 / 3 |
| Tales of Phantasia | Game Boy Advance | 2003 | **no** — GBA BIOS `LZ77UnComp` / `RLUnComp` |
| Tales of Berseria | PC | 2017 | **no** — zlib inside the TL engine's own container |

The 2003 Game Boy Advance rebuild of *Phantasia* is the useful negative
result. It is the same title, eight years later, and it uses the platform's
stock BIOS decompression services throughout — the format did not travel with
the game. It travelled with the team, for as long as the team was writing its
own packer.

*Berseria* is a different lineage entirely: BANDAI NAMCO Studios' TL engine, a
2013-era middleware stack, zlib, and an obfuscated container. The series name
is the only thing it shares with the two above.

So the current boundary of this format is: **Wolf Team's own titles, on
platforms where they wrote the decompressor themselves.** Anything that
narrows or widens that boundary is worth adding here.

---

## 7. Reading a new title

If you are opening a *Tales* game and want to know in a few minutes whether it
uses this format:

1. **Look for the header shape.** Scan for bytes where `+0` is one of
   `$81 $83 00 01 03`, `+1..+4` is a plausible size, `+5..+8` is a larger
   plausible size, and `+9 + packed` stays inside the file. On a 6 MiB image
   that filter alone leaves a few thousand candidates.
2. **Decode them.** `python tales_block.py IMAGE --scan --dialect snes` (or
   `psx`) does exactly this and keeps only the offsets whose output length
   matches the header's own claim. False positives essentially do not survive
   that test: on the 1995 cartridge the scan returns 1,089 blocks and every
   one of them is real.
3. **If the header shape is there but nothing decodes**, check the nibble
   order first — that is the one field the two known dialects disagree on, and
   a third dialect would most plausibly differ there too.
4. **If it decodes but comes out short**, check the dictionary. Try the
   preload and the empty ring, and try both cursor starts. Lengths alone
   cannot distinguish these; decode a block that should be a known container
   or image format and see which variant produces a parseable one.

That last point is worth stating separately, because it cost real time on the
PlayStation side. **A wrong dictionary still produces the right length.** A
back-reference copies the same number of bytes whatever it copies, so a
decoder with a garbage ring sails through a length check. The only test that
works is a semantic one: decode, and ask whether the result is still a
structure the platform recognises.

---

## 8. Open

* **Is there a third dialect?** The two known ones differ in nibble order and
  dictionary. A later Wolf Team title — *Tales of Eternia* on PlayStation, the
  PlayStation 2 remakes — would either extend the table in section 6 or draw
  the boundary more sharply.
* **What produced the blocks?** Everything here is about the decoders. The
  packer, which is where the shared constants actually live, has left no trace
  in either shipped image beyond its output.
* **Why the nibble swap?** No functional reason has been found. It costs
  nothing either way and it is the sort of thing that changes when code is
  rewritten from a description rather than ported line by line — which, if
  true, would say something about how the format travelled.
