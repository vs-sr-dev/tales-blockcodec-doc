# The Tales block codec

The in-house LZSS that Wolf Team shipped on the Super Famicom in 1995, used
again on the PlayStation in 1997, and was still shipping in 2000 — by then not
merely the same format but, for 212 bytes, literally the same machine code.

This document is the format. It is written to be read once in order and
grepped afterwards, and it is deliberately title-agnostic: addresses, block
counts and per-game verification live in the title pipelines listed in the
[README](README.md), not here.

`tales_block.py` in this repository is the reference decoder. It implements
everything below as one machine with a dialect switch, and reproduces all three
titles' own independently written decoders byte for byte
([`reports/cross-check.txt`](reports/cross-check.txt)).
`decoder_diff.py` compares two shipped builds' copies of the routine
instruction by instruction
([`reports/decoder-identity.txt`](reports/decoder-identity.txt)).

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
referenced them would decode differently on every call; across all three titles
no block does, and the 2000 corpus was instrumented to prove it — see below.

### What the preload buys

Measured on the two corpora, the ratio moves a long way:

| | Blocks | Packed | Unpacked | Ratio |
|---|---|---|---|---|
| Super Famicom 1995, no preload | 1,089 | 2,032,803 | 3,758,965 | **1.85×** |
| PlayStation 1997, preloaded | 6,638 | 148,665,346 | 464,839,924 | **3.13×** |
| PlayStation 2000, preloaded | 21,054 | 204,680,311 | 485,931,846 | **2.37×** |

That comparison is not clean — the data is different, the assets are bigger
and more repetitive on a disc — so read it as an order of magnitude, not a
measurement of the preload alone. The 2000 disc makes that point sharply: it
uses the identical dictionary and lands *below* the 1997 disc, because half its
largest archive is the same eight images repeated and re-compressing an already
compressed block gains nothing. Ratios measure corpora, not codecs.

### What the packer actually reaches

Ratios are indirect. *Tales of Eternia* is large enough to measure the
question directly: decode every block while recording, for each of the 4,096
ring addresses, whether it was read **before anything in that block had
written to it** — a genuine read of the preload rather than of the block's own
output. Over all 20,085 compressed blocks on its first disc:

| Region | Range | Reads | Share | Distinct addresses used |
|---|---|---:|---:|---|
| `(i, 0x00)` pairs | `0x0000`–`0x07FF` | 204,808 | 19.7% | 1,297 of 2,048 |
| `(i, 0xFF)` pairs | `0x0800`–`0x0EFF` | 76,819 | 7.4% | 704 of 1,792 |
| zeroed tail, below the cursor | `0x0F00`–cursor | 757,501 | 72.9% | **36** of 256 |
| at or above the cursor | cursor–`0x0FFF` | **0** | — | — |

Three things fall out of that.

**Every block reads the preload at least once.** Not one of the 20,085 is
self-contained.

**Three quarters of the traffic is the plain zeroed tail**, from 36 distinct
addresses clustered immediately below the cursor. That is the packer emitting a
short run of zeros at the head of a block, and it needs no synthetic table at
all — only a ring that starts cleared. The single most valuable property of the
dictionary is the `sb zero` loop, not the two pattern loops.

**The synthetic halves are used, and unevenly.** Together they take 27% of the
reads but spread over 2,001 distinct addresses, so the packer is genuinely
matching against them rather than hitting one lucky offset. The `(i, 0x00)`
half does about two and a half times the work of the `(i, 0xFF)` half.

And a caveat that only shows up when you separate the corpus by content type:
for **TIM images specifically**, deleting the entire `(i, 0xFF)` half changes
nothing. A negative control over 707 image blocks decodes 658 of them to a
structurally valid TIM with the correct preload and 658 with the `0xFF` half
blanked — identical — while an empty ring decodes 113 and a cursor at zero
decodes 566. Pixel data never happens to match the `0xFF` pattern; the tables
and padded structures elsewhere in the corpus do.

### Nothing reads what is not initialised

The bytes at and above the write cursor are whatever the stack held. A block
that referenced them would decode differently on every call, which would make
the format non-deterministic in a way no length check could detect.

Across *Tales of Eternia*'s 20,085 compressed blocks, **zero reads land at or
above the cursor.** The same was true of the *Tales of Destiny* corpus. Two
discs and 26,723 blocks later, the uninitialised window is still untouched.

---

## 5. The stored path

Every dialect has one, it was broken in 1997, and it was working again by 2000.

**Super Famicom, 1995.** Any method byte that is not `$81` or `$83` falls
through to a copy that takes its count from `+5` and its source from `+9`. It
is used, rarely — three blocks on the cartridge, all payloads the packer could
not shrink.

**PlayStation, 1997.** Method `0` reaches a byte copy that is handed the
**packed** size as its count and the pointer to the **block header** as its
source, because the dispatcher never advances it past `+9`. It would emit the
nine header bytes in front of the data.

Nothing on that disc exercises it. Across 6,638 blocks, not one has method `0`.
The path exists because the format it was ported from had one, and nothing
tested the port because the packer had stopped emitting stored blocks.

**PlayStation, 2000.** The pointer is right:

```
80023930  addu  a0, s1, zero        ; destination
80023934  jal   0x80076E7C          ; memcpy
80023938  addiu a1, s0, 9           ; source = block + 9   <-- past the header
```

and the path is live: **969 blocks** of the 21,054 on disc 1 of
*Tales of Eternia* use method `0`. All of them sit in one archive, all at the
same container slot, and all are tiny — 16, 24 or 28 bytes — which is the
packer declining to spend a token stream on a payload that cannot shrink.

The count is still taken from `+1`, the packed size, rather than from `+5`.
For a stored block those are the same number, and on that disc they always are:
`packed == unpacked` in all 969.

So the discrepancy documented here for three years turns out to be a
1997-build-specific defect, not a property of the format, and the format's own
stored path works exactly as the Super Famicom one does.

`tales_block.py` implements the sane reading — count from `+5`, source from
`+9` — for every dialect, which agrees with the 1995 and 2000 code and differs
from the 1997 code only where the 1997 code is wrong.

---

## 6. Where the format is, and is not

| Title | Platform | Year | Codec |
|---|---|---|---|
| Tales of Phantasia | Super Famicom | 1995 | **this format**, `$81` / `$83` |
| Tales of Destiny | PlayStation | 1997 | **this format**, methods 1 / 3 |
| Tales of Eternia | PlayStation | 2000 | **this format**, methods 0 / 1 / 3 — and the *same object code* |
| Tales of Phantasia | Game Boy Advance | 2003 | **no** — GBA BIOS `LZ77UnComp` / `RLUnComp` |
| Tales of Berseria | PC | 2017 | **no** — zlib inside the TL engine's own container |

### The 2000 build is not a reimplementation

*Tales of Eternia* does not merely use this format; it contains the same
compiled routine. Set its two decompressors beside *Tales of Destiny*'s:

| Routine | Eternia, 2000 | Destiny, 1997 | Identical prefix |
|---|---|---|---|
| method 1 | `0x80023504` | `0x80150BB0` | **53 words / 212 bytes** |
| method 3 | `0x80023690` | `0x80150D4C` | **50 words / 200 bytes** |

That prefix is the whole of the dictionary setup — the zero loop, both
256-iteration pattern loops, `RING − 18` and `RING − 17`. It contains no
`lui`/`addiu` address pairs, so nothing in it could differ merely because the
code was linked somewhere else; identical bytes there mean identical compiler
output from identical source.

After the prologue the two builds diverge in **register allocation only** —
Destiny's method-3 routine holds its flag register in `t5` where Eternia's uses
`t4`, and Destiny has one extra `addu` in the refill path. Over the whole
140-word window, 49% of method 1 and 36% of method 3 still match word for word.

Reproduce it with
`python decoder_diff.py ETERNIA.EXE 0x80023504 DESTINY.EXE 0x80150BB0`
([`reports/decoder-identity.txt`](reports/decoder-identity.txt)).

The 2003 Game Boy Advance rebuild of *Phantasia* is the useful negative
result. It is the same title, eight years later, and it uses the platform's
stock BIOS decompression services throughout — the format did not travel with
the game. It travelled with the team, for as long as the team was writing its
own packer.

*Berseria* is a different lineage entirely: BANDAI NAMCO Studios' TL engine, a
2013-era middleware stack, zlib, and an obfuscated container. The series name
is the only thing it shares with the two above.

So the current boundary of this format is: **Wolf Team's own titles, on
platforms where they wrote the decompressor themselves** — and inside that
boundary the code did not evolve, it was recompiled. Anything that narrows or
widens the boundary is worth adding here.

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
   a third dialect would most plausibly differ there too. (Three titles in,
   there is still no third dialect: the 2000 PlayStation build uses the 1997
   one unchanged.)
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

* **~~Is there a third dialect?~~** *Answered, no.* This question named
  *Tales of Eternia* as the title that would settle it. It does: the 2000
  PlayStation build has the same two dialects, the same nibble order, the same
  preload and 212 bytes of the same object code. The remaining candidates are
  the PlayStation 2 titles — *Tales of Destiny 2* (2002) and the *Destiny*
  remake (2006) — and the 2005 PSP port of *Eternia*.
* **What produced the blocks?** Everything here is about the decoders. The
  packer, which is where the shared constants actually live, has left no trace
  in any shipped image beyond its output. Three corpora now show its habits —
  it emits stored blocks below roughly 30 bytes (2000 only), it never expands,
  and on five blocks out of 21,054 it overshoots a trailing run by exactly one
  byte — but the tool itself remains invisible.
* **Why the nibble swap?** No functional reason has been found. It costs
  nothing either way and it is the sort of thing that changes when code is
  rewritten from a description rather than ported line by line — which, if
  true, would say something about how the format travelled. The 2000 build
  makes this *more* interesting, not less: between 1997 and 2000 the source
  was clearly still on hand and still compiling, so whatever happened between
  1995 and 1997 happened once and then stopped happening.
* **Why does one packer setting differ per archive?** On the 2000 disc, two of
  the four archives were packed with the run escape enabled and two with it
  disabled, and six blocks out of 14,200 in one archive went the other way —
  the texture pages of three consecutive maps. The dispatcher does not care,
  so nothing ever forced the settings to agree.
