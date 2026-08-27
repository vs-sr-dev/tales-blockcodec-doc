# The Tales block codec

The in-house LZSS that Wolf Team shipped on the Super Famicom in 1995, used
again on the PlayStation in 1997, still shipping in 2000 — by then not merely
the same format but, for 212 bytes, literally the same machine code — and
still shipping in 2002, on the PlayStation 2, unchanged.

This document is the format. It is written to be read once in order and
grepped afterwards, and it is deliberately title-agnostic: addresses, block
counts and per-game verification live in the title pipelines listed in the
[README](README.md), not here.

`tales_block.py` in this repository is the reference decoder. It implements
everything below as one machine with a dialect switch, and reproduces all four
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
| **Tales of Destiny 2** | **PlayStation 2** | **2002** | **this format**, methods 0 / 1 / 3 — the *same source*, recompiled |
| Venus & Braves | PlayStation 2 | 2003 | **no** — no decoder, on the same disc as Destiny 2 |
| Tales of Phantasia | Game Boy Advance | 2003 | **no** — GBA BIOS `LZ77UnComp` / `RLUnComp` |
| **Tales of Symphonia** | **GameCube** | **2003** | **this format**, methods 1 / 3 — on a *big-endian* machine |
| **Tales of Symphonia** | **PlayStation 2** | **2004** | **this format** — the same source, *edited* |
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

### The 2002 build is not the same object, and could not be

*Tales of Destiny 2* carries the format onto the PlayStation 2 with nothing
changed: same header, same method bytes, same nibble order, same preloaded
ring, same `RING − 18` / `RING − 17` cursors, and **9,469 of 9,469 blocks**
decode to their declared lengths under `tales_block.py` with no new dialect
([`reports/ps2-census.txt`](reports/ps2-census.txt)).

Byte equality was not available this time. The Emotion Engine is an R5900 and
its compiler is not the R3000A's, so the question has to change from *is it
the same object* to *is it the same source*. Comparing 140 words from each
build's method-1 routine:

| Pair | Identical words | Longest identical run | Opcode sequence |
|---|---:|---:|---:|
| Destiny 1997 ↔ Eternia 2000 | 69 / 140 | **53 words / 212 bytes** | **95.7%** |
| Destiny 1997 ↔ Destiny 2 2002 | 0 | 0 | 51.4% |
| Eternia 2000 ↔ Destiny 2 2002 | 0 | 0 | 49.3% |

The first row is the control: it reproduces this document's own headline
number by a different method, so the zeros below it are a measurement rather
than a failure of the tooling.

What survived is everything a compiler does not choose. The 2002 routine loads
`4078` as an immediate, takes the ring base in `a3`, and unrolls the
256-iteration pattern fill by exactly eight stores — all three the same as
1997 and 2000. What differs is register allocation, scheduling, and the R5900
compiler's habit of emitting `daddu` for a move where the R3000A compiler
emits `addu`. That is a recompile.

The 2002 disc also carries a **second** copy, in the `FILESYSTEM` I/O
processor module. The IOP is an R3000A, so byte equality *was* available
there — and it did not happen either: 1 identical word in 140, 30.0% opcode
similarity with the PlayStation builds. `FILESYS.IRX` is a relocatable module,
so the ring base is a global reloaded on every store rather than held in a
register, and the routine dispatches on internal kinds 2 and 4 rather than the
on-disc method bytes 1 and 3. The same algorithm, compiled twice more, under
two different sets of constraints.

[`reports/ps2-lineage.txt`](reports/ps2-lineage.txt).

### The 2003 build is big-endian, and the header did not turn round

*Tales of Symphonia* on the GameCube is the first time this format met a
machine that stores its words the other way up, and the first time it met a
console with its own decompression and its own opinions about loading — which
is the reading under which the 2003 Game Boy Advance rebuild had been allowed
to drop it.

It did not drop it. `main.dol` carries the decoder **four times** — two
routines, each linked twice, byte for byte identical — as PowerPC, with `4078`
and `4079` appearing as `subfic`, `cmpwi` and `addi` immediates. Everything
the source chose is unchanged: the control register refilled as
`ori r0, r0, 0xFF00`, the ring cursor masked with `rlwinm r10, r10, 0, 20, 31`
(that is `& 0x0FFF`), the length in the low nibble of the second token byte and
the reference's top bits in the high nibble, the synthetic `(i, 0x00)` and
`(i, 0xFF)` preload, and the copy loop unrolled by exactly eight. **487 of 487
blocks on each of the two discs decode to their declared lengths under
`tales_block.py` with no new dialect.**

And the **nine-byte header stayed little-endian**:

```
01 1e 21 00 00 e4 3c 00 00
   little-endian: method 1, packed 8478, unpacked 15588   <- decodes
   big-endian:    method 1, packed 505479168, unpacked 3829137408
```

The container around it *is* big-endian — the archive holding these blocks
counts its members with a big-endian `u32`, four bytes away. Section 1 above
explains why, and it was written before anyone looked at a GameCube: the
PlayStation decoder assembles all four bytes one `lbu` at a time, because a
container can place a block at any alignment. Code that reads a `u32` byte by
byte and shifts them together has no endianness of its own; it has whatever its
constants say. Ported to a big-endian machine it goes on reading little-endian
sizes, and nothing reports an error. The packer never had to be told about the
GameCube, and was not.

This was the field on which a third dialect was most likely to appear. It did
not. Two dialects, six builds, four consoles, nine years, both byte orders, and
the split is still 1995/1997.

### The 2004 build is the first one somebody edited

*Tales of Symphonia*'s PlayStation 2 port runs on the same R5900 as *Tales of
Destiny 2* did two years earlier, so byte equality is available again — and it
is the first time in this corpus that the strong test has been run on two
builds of the same CPU and returned nothing:

| Pair | CPUs | Identical words | Longest identical run, any alignment |
|---|---|---:|---:|
| Destiny 1997 ↔ Eternia 2000 | R3000A ↔ R3000A | 69 / 140 | **212 bytes** |
| **Destiny 2 2002 ↔ Symphonia 2004** | **R5900 ↔ R5900** | **1 / 180** | **6 bytes** |

Part of that is a change of toolchain: `SLPS_254.00` carries a `.comment`
section reading `MW MIPS C Compiler (2.4.1.01)` and `SLPS_251.72` carries no
compiler string at all.

The rest is not, because a compiler does not change a constant. Every build
from 1997 to 2003 clears the dictionary with an inline byte loop bounded by
**4,078**. The 2004 build calls a subroutine with **4,080**:

```
2002:  addiu a0, zero, 4078      2004:  addiu a1, zero, 4080
       sb    zero, 0(v1)                jal   0x001DF090
       slt   v0, t1, a0                 ...
       bne   v0, zero, ...       0x001DF090:  srl a1, a1, 4
                                              sq  zero, 0(a0)   ; R5900 quadword
                                              addiu a0, a0, 16
```

4,080 is 4,078 rounded up to a multiple of sixteen, so that the Emotion
Engine's 128-bit store can be used. It clears two bytes the older code did not,
harmlessly, both being inside the 4,096-byte ring. That is a hand edit to the
decoder's source, made for this CPU — and the GameCube build a year *earlier*
still clears the dictionary the 2002 way, so it is 2004 that departs, not 2003.

The 2004 build also drops the I/O processor copy that 2002 carried: neither
`IOPRP300.IMG` nor `IRXARC.BIN` contains a `4078` immediate anywhere. And it
carries two *differently compiled* copies on the main CPU — 1,104 + 768 bytes
against 1,520 + 1,176, with 2 identical words out of 276 — where the GameCube's
two copies are byte for byte the same. See
[gc-talesofsymphonia-doc](https://github.com/vs-sr-dev/gc-talesofsymphonia-doc).

### The boundary tested on a single disc

The *Tales of Destiny 2* disc is the sharpest negative control this
document has. It carries a second, unrelated game: a promo build of Namco's
*Venus & Braves*, same company, same console, released eight months later.

Across 933,840 instruction words `VENUS.ELF` has **no `4078` immediate at
all**, and its single `4079` is a page-rounding constant in an allocator. No
zero loop, no ×8 pattern fill, no decoder — and its data needs none, being a
virtual CD image of plain stored members.

Two teams, one disc, one console, one year, and only one of them used the
compressor. The format did not belong to the company or to the platform. It
belonged to the *Tales* codebase.

The 2003 Game Boy Advance rebuild of *Phantasia* is the useful negative
result. It is the same title, eight years later, and it uses the platform's
stock BIOS decompression services throughout — the format did not travel with
the game. It travelled with the team, for as long as the team was writing its
own packer.

*Berseria* is a different lineage entirely: BANDAI NAMCO Studios' TL engine, a
2013-era middleware stack, zlib, and an obfuscated container. The series name
is the only thing it shares with the two above.

So the current boundary of this format is: **the *Tales* codebase itself**,
for as long as that codebase carried its own decompressor — and inside that
boundary the code did not evolve. From 1997 to 2000 it was recompiled to the
same bytes; from 2000 to 2002 it was recompiled to a different CPU. The
boundary is not the company (Namco shipped *Venus & Braves* without it), not
the console (both PlayStation 2 games are on one disc), and not the series
name (*Berseria* shares only that). Anything that narrows or widens it is
worth adding here.

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
   a third dialect would most plausibly differ there too. (Five titles in,
   there is still no third dialect: 2000, 2002, 2003 and 2004 all use the 1997
   one unchanged.)
   **Do not try byte-swapping the header on a big-endian machine.** The 2003
   GameCube build is big-endian throughout — its archives count their members
   with big-endian words — and its nine-byte block headers are still
   little-endian, because the decoder assembles each size one byte at a time
   and never had a reason to care. Section 6.
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

### Finding the decoder, rather than the data

There is a shortcut worth knowing, and it worked first try on the PlayStation
2. **Scan the executable for the immediates 4078 and 4079.** They are
`RING − 18` and `RING − 17`, they appear as `addiu`/`slti` immediates in every
PlayStation-dialect decoder found so far, and no other part of a game has a
reason to load 4,078. On *Tales of Destiny 2* that filter returned seven sites
across two files and both decoders were within a hundred bytes of one of them.

**It survives a change of instruction set.** On PowerPC the constant appears
in the low half of a D-form word instead of an I-type one — as `subfic`,
`cmpwi` and `addi` — and the word is stored big-endian, but the constant is
the packer's and does not move. On *Tales of Symphonia*'s GameCube build the
filter returned twelve sites in four routines, and the *offsets within each
routine were the same three*: `+17`, `+21`, `+216` words. A tool that does both
instruction sets is
[`ring_sites.py`](https://github.com/vs-sr-dev/gc-talesofsymphonia-doc/blob/main/tools/ring_sites.py).

It cuts the other way just as well. The absence of `4078` across a whole
executable is strong evidence the decoder is not there, which is how *Venus &
Braves* was ruled out without decoding anything — and how the 2004 build's two
I/O processor images were ruled out in 2004.

### What does *not* work: comparing routines across instruction sets

The opcode-sequence measure in this repository's own tooling works because
R3000A and R5900 share a mnemonic vocabulary. Across a real change of
instruction set it does not. Mapping every instruction to what it *does* —
load a byte, store a byte, add a constant, shift, compare, branch — and
comparing those sequences scores the genuine GameCube/PlayStation 2 decoder
pair at **16.5%**, and an arbitrary unrelated routine from the same executable
at **16.5%** and **18.5%**. The measurement has no discriminating power, and
the tool that produced it is published with that stated and with its controls
printed unconditionally. Use the constants, the structure and a decode census
instead. See
[gc-talesofsymphonia-doc](https://github.com/vs-sr-dev/gc-talesofsymphonia-doc).

---

## 8. Open

* **~~Is there a third dialect?~~** *Answered, no — three times.* The question
  first named *Tales of Eternia* as the title that would settle it, and the
  2000 build turned out to share 212 bytes of object code with 1997. It then
  named the PlayStation 2 as the remaining risk, and *Tales of Destiny 2*
  (2002) settled that too. The last plausible place for one was a machine of
  the opposite byte order, and *Tales of Symphonia* (GameCube, 2003) is that
  machine: the decoder is there four times as PowerPC, the nibble order is
  unchanged, and **the nine-byte header is still little-endian**. Two dialects,
  six builds, four consoles, both byte orders, nine years, and the split is
  still 1995/1997. What is left to test is the 2005 PSP port of *Eternia* and
  the 2006 PlayStation 2 remake of *Destiny*.
* **~~Was the source ever edited after 1997?~~** *Answered, yes — once, in
  2004.* Every build from 1997 to 2003 clears the dictionary with an inline
  byte loop bounded by 4,078. *Tales of Symphonia*'s PlayStation 2 port (2004)
  calls a quadword `bzero` with 4,080 instead — 4,078 rounded up to a multiple
  of sixteen so the Emotion Engine's 128-bit store can be used. On the same CPU
  as the 2002 build, two years apart, the longest identical byte run at any
  alignment between the two decoders is **six bytes**, against 212 for the
  1997/2000 pair. Some of that is a change of compiler; the constant is not.
  Section 6.
* **~~What produced the blocks?~~** *Still invisible, but it has now been
  caught running twice.* *Tales of Symphonia* shipped on the GameCube in 2003
  and on the PlayStation 2 in 2004, and nineteen character-model files carry
  codec blocks under the same name on both. For **every one of them** the block
  count and the total unpacked length are identical — so the packer was handed
  the same input and cut it at the same places — and **every one is larger in
  2004**, by between +0.72% and +5.21%:

  | | blocks | packed | unpacked |
  |---|---:|---:|---:|
  | 2003, GameCube | 134 | 1,017,110 | 1,944,112 |
  | 2004, PlayStation 2 | 134 | **1,042,397** | 1,944,112 |

  Not one file is smaller and not one is the same. The segmentation logic did
  not change between the two runs; the match search did, and it got worse. The
  tool was still on hand in 2004, still being run, and no longer quite the same
  tool — in the same year somebody edited the decoder. See
  [gc-talesofsymphonia-doc](https://github.com/vs-sr-dev/gc-talesofsymphonia-doc)
  and [`reports/repack.txt`](reports/repack.txt).

* **What produced the blocks?** Everything else here is about the decoders. The
  packer, which is where the shared constants actually live, has left no trace
  in any shipped image beyond its output. Four corpora now show its habits —
  it emits stored blocks below roughly 30 bytes (2000 only), it never expands,
  and on five blocks out of 21,054 it overshoots a trailing run by exactly one
  byte — but the tool itself remains invisible. The 2003 GameCube corpus adds
  one more habit and it is a large one: **its blocks are up to thirty times
  bigger.** The largest block in the four titles to 2002 is around 30 KB; the
  largest on the GameCube disc is **1,007,213 packed bytes**, and 251 blocks in
  one file average 310 KB. The 24-bit size field always allowed it, so nothing
  forced the old ceiling. Whatever drives the packer changed between 2002 and
  2003. The 2002 disc adds one habit
  and removes another: the run escape is now overwhelmingly the default
  (8,040 of 8,142 blocks inside its bundles are method 3), and tiny members
  are no longer wrapped in a method-0 header at all — they are simply left raw
  with no header, which the 2000 packer never did.
* **Why the nibble swap?** No functional reason has been found. It costs
  nothing either way and it is the sort of thing that changes when code is
  rewritten from a description rather than ported line by line — which, if
  true, would say something about how the format travelled. The 2000 build
  makes this *more* interesting, not less: between 1997 and 2000 the source
  was clearly still on hand and still compiling, so whatever happened between
  1995 and 1997 happened once and then stopped happening. 2002 extends that
  by another two years and another CPU — the source was still on hand, still
  compiling, and still nobody touched the nibble order.
* **Why does one packer setting differ per archive?** On the 2000 disc, two of
  the four archives were packed with the run escape enabled and two with it
  disabled, and six blocks out of 14,200 in one archive went the other way —
  the texture pages of three consecutive maps. The dispatcher does not care,
  so nothing ever forced the settings to agree. The 2002 disc does the same
  thing within a *single* archive: method 0 is 19 of 1,327 top-level members
  of `FILE.FPB` but only 2 of the 8,142 members nested inside its bundles.
* **Two copies on one disc, compiled differently.** *Tales of Destiny 2* ships
  the decoder twice, once per CPU, and the I/O processor copy shares almost
  nothing with the Emotion Engine copy even at the opcode level (24.3%). It
  also renumbers the methods internally, dispatching on 2 and 4 instead of 1
  and 3 — the only place in four titles where the on-disc method byte is not
  used directly. Whether that is a second hand-port or the same source under
  a different build configuration is unresolved. Both 2003 and 2004 ship two
  copies as well, and they disagree about what that means: the GameCube's two
  are **byte for byte identical** over 1,616 and 1,332 bytes, which is a linker
  pulling one object in twice, while the 2004 PlayStation 2's two are not even
  the same length — 1,104 + 768 against 1,520 + 1,176, with 2 identical words
  out of 276 — the second far more heavily unrolled than the first.
* **Where the decoder runs.** In 2002 it ran on both processors. In 2004
  neither I/O processor image contains a `4078` immediate at all: decompression
  moved entirely onto the main CPU while the I/O processor took up CRI's `ROFS`
  reader. Whether that was a decision about the codec or a consequence of
  changing file system middleware is not answerable from the discs.
* **Comparing across instruction sets.** The opcode-sequence method that
  carried the 2002 result works because R3000A and R5900 share a mnemonic
  vocabulary. Section 7 records the attempt to generalise it to PowerPC and its
  failure — the real pair scores no better than an unrelated routine. Something
  that survives a change of instruction set would be worth having; comparing
  basic-block structure, or the sequence of loop trip counts and constants
  rather than instructions, has not been tried.
