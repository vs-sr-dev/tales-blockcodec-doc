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
| **Tales of Rebirth** | **PlayStation 2** | **2004** | **this format**, methods 1 / 3 — a *different* source again, on both CPUs |
| **Tales of Tactics** | **i-appli (DoJa)** | **2004** | **no** — a Java application; deflate, twice, both the platform's |
| **Tales of Legendia** | **PlayStation 2** | **2005** | **this format**, one method — the *same engine*, an **unrelated source**, and a **new envelope** |
| **Tales of the Abyss** | **PlayStation 2** | **2005** | **this format**, methods 1 / 3 — the **1997 source again**, recompiled, and the nine-byte header back |
| **Tales of the Tempest** | **Nintendo DS** | **2006** | **no** — and neither is anything else; the data is stored raw |
| **Tales of Innocence** | **Nintendo DS** | **2007** | **no** — the *control*: another team, same platform, and it compresses in the **platform's own** `LZ77` |
| **Tales of Symphonia: Ratatosk no Kishi** | **Wii** | **2008** | **no** — the direct sequel to the 2003 build, **same instruction set**, from **inside the line** |
| **Tales of Vesperia** | **Xbox 360** | **2008** | **this format**, methods 0 / 1 / 3 — the **1997 shape again**, six weeks after the build above, on a **third compiler**, beside XCompress |
| **Tales of Hearts** | **Nintendo DS** | **2008** | **no** — two cartridges, one build, five months after the build above; the container `FPS4` crossed and the codec did not |
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

### By late 2004 there was more than one copy of the source

The 2004 result above had to be hedged, because `SLPS_254.00` carries a
`.comment` reading `MW MIPS C Compiler (2.4.1.01)` and `SLPS_251.72` carries no
compiler string at all, and a change of toolchain explains a lot of drift by
itself. *Tales of Rebirth* removes the hedge, because it supplies the control
that was missing.

Same studio, same R5900, and **three months** after Symphonia's PlayStation 2
port — that disc's volume is stamped 2004-08-17 and Rebirth's 2004-11-17. Taking
932 contiguous bytes of Rebirth's decoder (its shared `ring_init` plus both
method cores) and searching *whole executables* for the longest identical run at
any alignment:

| Rebirth's decoder against | longest identical run |
|---|---:|
| Symphonia, PlayStation 2, 2004 | **17 bytes** |
| Destiny 2, PlayStation 2, 2002 | 13 bytes |
| Eternia, PlayStation, 2000 | 12 bytes |
| Destiny, PlayStation, 1997 | 9 bytes |

and then the same measurement, same needle length, on **932 bytes of Rebirth's
own C runtime** taken from the same executable:

| Rebirth's C runtime against | longest identical run |
|---|---:|
| Symphonia, PlayStation 2, 2004 | **276 bytes** |
| Destiny 2, PlayStation 2, 2002 | **288 bytes** |
| Eternia, PlayStation, 2000 | 13 bytes |
| Destiny, PlayStation, 1997 | 13 bytes |

All three PlayStation 2 titles link the same C runtime objects byte for byte.
Byte equality was therefore not merely available in principle, it is
*demonstrated* between exactly the pair of files whose decoders share nothing.
Two executables that agree for 276 bytes of `memset` and string code agree for
seventeen bytes of decoder. The toolchain cannot be doing that.

And the constant says the same thing a third way. Every build from 1997 to 2003
clears the ring with an inline byte loop bounded by 4,078. Symphonia 2004 calls a
hand-written quadword `bzero` with 4,080. Rebirth 2004 calls the **ordinary C
library `memset`** with **4,079**, out of a routine neither of the others has —
a factored `ring_init` that both method variants share, which is why it has to
clear enough for the higher of the two cursors rather than the lower:

```
2002, inline                     2004 Symphonia, bespoke bzero
  addiu a0, zero, 4078             addiu a1, zero, 4080
  sb    zero, 0(v1)                jal   0x001DF090
  slt   v0, t1, a0                        srl a1, a1, 4
  bne   v0, zero, ...                     sq  zero, 0(a0)

2004 Rebirth, library memset
  addiu sp, sp, -32
  daddu a1, zero, zero        ; fill 0
  addiu a2, zero, 4079        ; length
  jal   0x001BFC34            ; generic memset, with a byte fallback
  daddu s0, a0, zero
```

**`4080` does not appear in Rebirth's executable at all** — one `andi` mask over
204,024 instruction words, and nothing else. The signature this document named
as "the source fingerprint, independent of the compiler" is absent from a build
three months later at the same studio on the same CPU.

The I/O processor tells the same story. Rebirth puts the decoder *back* on the
IOP, which 2004 Symphonia had dropped; `BOOT.IRX` and 2002's `FILESYS.IRX` are
both R3000A, so byte equality was available there too, and the longest identical
run between them is **47 bytes against a control of 46** — the module boilerplate
any two IRX files share, and nothing more.

So the 2004 finding needs restating. It is not *the source was edited once in
2004*. It is that **by 2004 there was no longer one copy of the source to
edit**: three PlayStation 2 builds inside thirty months clear the same array
three different ways with three different constants through three different
mechanisms, while every bit of the on-disc format stays put and the reference
decoder reads all of them without a branch. Each title had its own copy. What
they still had in common was the format and the packer.

One thing did survive intact, and it is the odd one. In 2002 the *Destiny 2*
I/O-processor copy was the only place in four titles where the on-disc method
byte was not used directly — it dispatched on internal kinds **2 and 4** instead
of 1 and 3. On Rebirth **both** copies do that, on both processors: the header
state machine reads the method byte, adds one, and compares against 2 and 4. A
quirk that existed in one routine on one processor in 2002 is the convention on
both processors in late 2004.
[ps2-talesofrebirth-doc](https://github.com/vs-sr-dev/ps2-talesofrebirth-doc).

### The 2005 build separates the format from the code

*Tales of Legendia* is the ninth build and the first on which two things that
had always moved together come apart: the format is here in full and the source
is not, and the *container around the format* has changed for the first time
since 1995.

The shortcut works, and it answers with the oldest constant. One `4078` in
`SLPS_255.33`, and it is `ring_init`: an inline byte loop unrolled by eight,
ring base `0x004A0AE0`, mask 4095, cursor at `RING − 18`. That is the 1997–2003
mechanism, so the count is now four builds and four ways to clear one array:

| Build | Year | Mechanism | Constant |
|---|---|---|---|
| Destiny, Eternia, Destiny 2, Symphonia GC | 1997–2003 | inline byte loop | **4078** |
| Symphonia, PlayStation 2 | 2004 | bespoke quadword `bzero` | **4080** |
| Rebirth | 2004 | library `memset`, from a factored `ring_init` | **4079** |
| **Legendia** | **2005** | **inline byte loop** | **4078** |

But it did not get there by inheriting anything. 872 bytes of Legendia's decoder,
searched at any alignment through whole executables:

| Legendia's **decoder** against | Longest identical run |
|---|---:|
| Symphonia, PlayStation 2, 2004 | **21 bytes** |
| Rebirth, PlayStation 2, 2004 | **20 bytes** |
| Destiny 2, PlayStation 2, 2002 | 16 bytes |
| **Venus & Braves, 2003 — *the negative control*** | **20 bytes** |

The last row is what makes the others readable, and it cost one extra argument.
`VENUS.ELF` is this document's own demonstration of an executable with no
decoder in it at all. Legendia's decoder resembles its nearest sibling exactly
as much as a file containing no decoder does.

And byte equality was available, demonstrated twice. 872 bytes of Legendia's
*own C runtime*, same needle length, same tool, saturates against Symphonia —
widening the needle until the answer stops growing gives **2,420 contiguous
identical bytes**. Both executables carry `.comment` reading
`MW MIPS C Compiler (2.4.1.01)`, so this is not a toolchain difference being
mistaken for a source difference: it is the same stamped compiler, 2,420 bytes
of agreement in the library, and twenty-one in the decoder. Separately,
Rebirth's own 932-byte runtime needle scores **276** against Legendia — the
same figure it scores against Symphonia — so **four PlayStation 2 titles across
thirty-five months link the same runtime objects byte for byte**.

What changed is the envelope. Every build from 1995 to 2004 wraps its data in
the nine-byte header of section 1, whose first byte is the method. Legendia
does not:

```
1995-2004                       2005
+0  u8  method                  +0x00  "CPS "
+1  u32 packed                  +0x04  u32 packed, including the header
+5  u32 unpacked                +0x08  u32 unpacked
                                +0x0C  u32 zero, on every member
+9  stream                      +0x10  stream
```

Sixteen bytes and **no method byte at all**, so the dispatch this document has
described for nine years has nowhere to live. There is no run escape — no `+19`
anywhere in the routine — and a stored member is recognised instead by
`packed − 16 == unpacked`, which holds to the byte on 3,353 of them.

Two more things are gone from the decoder and one of them matters to the packer.
The routine is a **resumable state machine**, keeping cursor, mask, control
register, saved token byte and a `0..3` state word in five `gp`-relative
globals so it can be handed a partial buffer and called again; nothing else in
this corpus is built that way. And `ring_init` **does not write the synthetic
preload**. It clears 4,078 bytes and returns — no 256-iteration pattern loops,
no `(i, 0x00)` and `(i, 0xFF)` pairs. Section 4 measured that preload being read
by every one of Eternia's 20,085 blocks; here it does not exist, which means the
*packer* stopped emitting references into it as well, or nothing would decode.

Everything else is untouched, and it is checkable: 4,096-byte ring, `& 0x0FFF`,
control bits LSB first with `1` = literal, refill as `byte | 0xFF00`, the
twelve-bit reference with its high four bits in the *high* nibble of the second
token byte, `length = nibble + 3` over 3 to 18, and the loop driven by the packed
size. **4,508 of 4,508 members decode to their declared length**, 1,176,881,049
packed to 2,098,653,952 unpacked — 3,078 in the six `AFS` archives and 1,430
more inside a gigabyte-sized file nothing on the disc refers to.

So the reading this document has carried since 2004 needs one clause added. It
was: by then there was no longer one copy of the *source*, and the format did not
notice. Legendia says the format did not need the source at all. Somebody in 2005
had the algorithm exactly — every constant, every nibble, the `+3` — and did not
have the file, and built a different container around it, and the packer that
fed it still produced a stream the reference decoder reads without a branch.
[ps2-talesoflegendia-doc](https://github.com/vs-sr-dev/ps2-talesoflegendia-doc).

### Four months later the source file turns up again

*Tales of the Abyss* is the tenth build, it is stamped **2005-11-25**, four
months and two days after *Legendia*, and it exists to test whether the code
still travelled anywhere. It does.

The envelope goes first, because it is the cheapest question and it does not
depend on a compiler. Legendia's sixteen-byte `CPS` chunk is **not on this
disc**: `CPS ` and `CPS\0` together return seven hits across 4,357,816,320
bytes against a chance rate of about one each, and all seven were located and
sit inside Sofdec or ADX payload. What is there is section 1, complete — `+0`
method, `+1` packed size assembled from four `lbu`s, `+5` unpacked size read by
a separate getter, methods **0, 1 and 3 used directly**, a 4,096-byte ring
rebuilt on the stack on every call, **both** synthetic preload loops, and the
run escape with its `+3` and its `+19`. **47,513 of 47,513 blocks decode** to
their declared length under the unmodified reference decoder, 1,069,278,379
packed to 2,643,327,828 unpacked.

And the bytes:

| Abyss's **decoder**, 872 bytes, against | Longest identical run |
|---|---:|
| **Symphonia, PlayStation 2, 2004** | **69 bytes** |
| Legendia, PlayStation 2, 2005 | 18 bytes |
| Rebirth, PlayStation 2, 2004 | 14 bytes |
| Destiny 2, PlayStation 2, 2002 | 12 bytes |
| ***Venus & Braves*, 2003 — the negative control** | **14 bytes** |

with the same needle length from Abyss's own C runtime returning **632** against
Symphonia *and* **632** against Legendia — saturated, checked by widening the
needle to 8 KB — and all three executables stamping `MW MIPS C Compiler
(2.4.1.01)`. Byte equality was equally available against both neighbours. Only
one of them gave any.

The sharper half is *which* copy. `SLPS_254.00` carries this codec **four
times**, in two pairs which this document already records as sharing 2 identical
words in 276 with each other. The pair at `0x001C93D0` is the one the 2004
headline above is about — the quadword `bzero` with **4080**. Abyss scores
**4 bytes** and one identical word against it. The pair at `0x00242C5C` is the
other one, the copy in the same file that still clears the ring the 1997 way and
still writes the preload, and Abyss scores **31 identical words in 200, a
68-byte run, 56.5% same opcode**, diverging on register allocation and nothing
else:

```
Abyss   0x00122288  sb    zero, 0(v1)     Symphonia  0x00242CC0  sb    zero, 0(v1)
Abyss   0x0012228C  daddu t7, zero, zero  Symphonia  0x00242CC4  daddu t4, zero, zero
```

Their dispatchers say it again. Both allocate `addiu sp, sp, -4144`, both put
the ring at `sp + 16`, both read the five header bytes with individual `lbu`s in
nearly the same order, and 10 of 44 words are identical in a routine that is
mostly `jal` targets and branch offsets. Two differences of substance: Symphonia
tests method **2** before 3, 1 and 0 and routes it to the error target, where
Abyss tests 3, 1, 0 and falls through; and Symphonia inlines the stored copy
where Abyss calls the SDK's quadword `memcpy`. Both advance the source past `+9`,
so both are the fixed version of the 1997 defect.

So the reading this document adopted after Legendia has to be narrowed rather
than repeated. It was: the codebase propagated the codec **as knowledge, not as a
file**. That was built on one observation and the tenth build contradicts it.
What the corpus can now say is that the codebase carried **both** — a source file
that kept being compiled, and a specification good enough to re-implement from
when somebody did not have the file. The shape at ten builds is:

* a **1997 source** reaching 2005 intact, via Symphonia's second pair and then
  Abyss: inline clear, synthetic preload, nine-byte header, methods 0/1/3;
* **three edits of it that went nowhere** — Symphonia's own 4080 quadword `bzero`
  (2004), Rebirth's 4079 library `memset` (2004), Legendia's resumable state
  machine and `CPS` envelope (2005);
* and a **format** all of them agree on to the bit.

Legendia is not the rule. It is one of at least three forks that did not
propagate, and the only one of the three written from a description rather than
from the file.

One more thing this build carries that no other in the corpus does. It is not a
clean disc: 109 members of its sound-effect archive are prefixed **`tor_`**,
*Tales of Rebirth*'s project tag, and all **105** of their distinct names —
`no_se_mp_steps04`, `no_se_bt_mag_rise1` and the rest — are present on Rebirth's
own disc image, whose effect table reads `no_se_mp_steps00 … no_se_mp_steps12`.
The audio was re-encoded rather than copied: no body needle and no ADX header
from any of the 109 appears in that image. Rebirth was the first clean disc and
Legendia the second; three in a row was going to be a policy and it is not.
[ps2-talesoftheabyss-doc](https://github.com/vs-sr-dev/ps2-talesoftheabyss-doc).

### The eleventh build changes what a negative can look like

*Tales of the Tempest* (Nintendo DS, 2006) is the first title here that is not
a console C build by the studio line, and the first on a Nintendo handheld
since the 2003 Game Boy Advance rebuild. It was opened expecting one of three
answers and it gave a fourth.

**The scan had to be rebuilt before it could be run.** Every architecture this
document had met carried its constants in an immediate field inside a
fixed-width instruction word. ARM does not, or not always: a data-processing
immediate is an 8-bit value rotated right by an even amount, so

| | |
|---|---|
| 4070, 4071, 4078, 4079 | **cannot be encoded at all** |
| **4080** | **can** — `0xFF ror #28` |

The two cursors this document has scanned for since 2002 are *unrepresentable*
as ARM immediates and reach the code as 32-bit words in the literal pool,
loaded with `ldr rX, [pc, #offset]`. The 2004 constant is representable. So the
three constants of this corpus behave in two different ways on one machine, and
a single-pass scan sees at most one of them. Section 7 carries the two-pass
variant.

**And a step comes before the scan on this platform.** A DS `arm9.bin` is
normally compressed by the Nintendo linker's backwards LZ, and a constant scan
over a compressed module returns zero and looks exactly like a clean negative.
On this cartridge neither module is compressed and there are no overlays at
all, checked from the module parameters and from the `BLZ` footer
independently — but the check has to happen first, every time.

With both in place the answer is unambiguous, and it is quoted against its
denominators:

| | ARM9 | ARM7 |
|---|---:|---:|
| ARM data-processing immediates | 85,036 | 11,969 |
| THUMB instructions carrying a literal | 53,575 | 4,034 |
| 4-byte-aligned words | 387,310 | 41,384 |
| PC-relative loads resolved | 31,817 | 2,703 |
| **4078 / 4079 / 4070 / 4071, either form** | **0** | **0** |
| 4080 | 5 immediates + 1 unreferenced word | 0 |

All six `4080` sites were disassembled. One is not an instruction. One is a
field in a static struct that nothing loads. **Four are entries of a
4,096-scaled cosine table**, compiled as 446 eight-byte stubs — `mov r0,#K ;
bx lr` — behind a table of branches, in which the first 91 stubs are
`round(4096 * cos t)` for t = 0 to 90 degrees to within one, and
**`round(4096 * cos 5 deg) = 4080`**. The structural probe agrees: zero
`orr rX,rX,#0xFF00`, zero ARM `add #19`, zero 4,096-byte stack frames, and no
three fingerprints inside 200 instructions of each other. And the reference
decoder, run blind over **9,055 payloads and 256,548,562 bytes** in both
dialects, returns **zero blocks** where its control on the 1995 cartridge
returns 1,089 in the same invocation.

**What is there instead is nothing.** The 2003 Game Boy Advance result was that
the platform's own decompression took the format's place; repeating it here
would have meant finding `LZ77UnComp` doing the work. Both modules link the
NitroSDK's system-call wrappers, all six decompression services included — and
every branch in both images was resolved, 21,462 targets in the ARM9 and 3,785
in the ARM7, and **not one of the twelve decompression wrappers has a call
site**, where `CpuSet` has one and `Stop/Sleep` has seven. **Zero of 4,712
files** begins with a BIOS-format stream; 91,303 candidate offsets inside them
yield **zero** embedded `LZ77` streams; and the cartridge as a whole
**deflates to 52.6%**, its 739 palettes to 9.3% and its 243 bitmaps to 16.1%.

The data is stored raw, and it cost nothing to store it that way: **41.3% of
the cartridge is unused** — 52.8 MB of `0x00` and then exactly 2.5 MiB of
`0xFF`. The only two codecs present are Actimagine's video middleware and the
DS sound hardware's own ADPCM, and the SDK's component list names both:
`[SDK+Actimagine:VX]`, `[SDK+NINTENDO:BACKUP]`.

So this is a third kind of negative. *Venus & Braves* had a decoder-shaped hole
and plain stored data. The Game Boy Advance rebuild swapped one decompressor
for the platform's. *Tales of Tactics* had nothing to inherit. This build had
room for a compressor, a platform that supplies six of them for free, and
wrote and called neither.

**And it cannot separate two variables, which is worth recording as plainly as
the result.** The machine changed and the team changed at the same time, and no
second Nintendo DS image was available to run the identical probes over — where
*Tales of Tactics* was quoted against three sibling i-appli. The cartridge does
not even name its own developer: no company string in either executable, no
symbol table, no source path in code, and one project-shaped tag (`NT_DS1`)
that survived only inside a 3ds Max intermediate file nobody converted. On this
evidence "the codec does not cross to this platform" and "the codec does not
cross to this team" are the same statement.
[nds-talesofthetempest-doc](https://github.com/vs-sr-dev/nds-talesofthetempest-doc).

### The twelfth build is a control, and it excludes a platform

*Tales of Innocence* (Nintendo DS, 2007) exists in this corpus for one reason:
the eleventh build changed two variables at once and could not say which of them
its zero was about. This is the control the previous section asked for, in the
first of the three forms it listed — **same publisher, same platform, one year
later, a different developer**, Alfa System, a third studio outside the Wolf
Team / Namco Tales Studio line and unrelated to Tempest's.

Four outcomes were possible and none was assumed: the codec is there; the BIOS
takes its place; nothing takes its place, as on Tempest; or something third
does. The answer is the fourth, and it is the most informative of them.

**On the codec the two DS cartridges agree, and the second zero is the cleaner
one.** Across five modules — the ARM9, the ARM7 and three overlays, none of
them compressed, checked from the overlay flags, the module parameters and the
`BLZ` footer independently — the scan finds nothing:

| | ARM9 | ARM7 | ovl 0 | ovl 1 | ovl 2 | total |
|---|---:|---:|---:|---:|---:|---:|
| ARM data-processing immediates | 22,568 | 11,882 | 22,350 | 18,419 | 3,270 | **78,489** |
| THUMB instructions with a literal | 43,310 | 5,253 | 56,540 | 30,972 | 4,230 | **140,305** |
| 4-byte-aligned words | 169,238 | 39,790 | 178,200 | 144,328 | 22,464 | **554,020** |
| PC-relative loads resolved | 10,268 | 2,293 | 6,247 | 8,037 | 624 | **27,469** |
| **4078 / 4079 / 4070 / 4071 / 4080** | **0** | **0** | **0** | **0** | **0** | **0** |

Not one of the five constants in either encoding anywhere, where Tempest had
five `4080` immediates and one unreferenced `4080` word to disassemble. Zero
`orr rX,rX,#0xFF00` refills, zero 4,096-byte stack rings, and the ARM/THUMB trap
fired again and was caught again: overlay 2 reports 22 THUMB `add #19` and all
22 are ARM words read at even offsets — `mov r3,r3,lsl rN`, the bit-consume step
of the video decoder, repeated all through it. The genuine ARM count is zero, as
it was on Tempest, where the same idiom produced 24.

Its twelve BIOS decompression wrappers have **zero callers** too, over **40,411
distinct branch targets** resolved across all five modules — including across
the module boundary, which is a measurement Tempest could not make because it
had no overlays. No wrapper address occurs as a data word anywhere either, so
not through a function pointer. And the unmodified reference decoder returns
**0 blocks in 23,083 payloads and 657,419,133 bytes**, both dialects, with the
1995 cartridge's 1,089 in the same invocation.

**On everything else they disagree, and that is the point.**

| | *Tempest*, 2006 | *Innocence*, 2007 |
|---|---|---|
| files in a BIOS compression format | **0 of 4,712** | **106 of 6,378** — 102 `LZ77`, 16,901,069 → 32,116,356 |
| a container | none | **1,344 `EZBIND` archives, 9,646 members, 60,416,314 bytes** |
| the image through deflate | 52.6% | 73.5% |
| already-compressed containers / raw ones, deflated | — | **91.27% / 52.23%** |
| cartridge unused | 41.3% | **3.2%**, all `0xFF` |
| media share | 13.22% | **51.40%**, 2.81 hours of voice |
| middleware | Actimagine `VX` | Actimagine **Mobiclip**, plus **nine CRI components** |
| names its developer | nowhere | credits text, boot logo, and 1,047 RTTI class names |

So a *Tales* cartridge on the Nintendo DS can compress, does compress, and
compresses in a format the platform itself defines — while buying audio from
CRI and video from Actimagine and writing an archive format of its own,
`EZBIND`, named by its ARM9's own `cEzArchiveWrapper`. **The reading that the
platform forbids it is dead**, and it is dead by measurement rather than by
argument.

What is not settled is stated in the same breath: both DS developers are
outside the studio line, so *the codec travels with that codebase* survives this
control untouched. Narrowing that further needs a Nintendo DS title **from**
that line, and there is not one.

Three things this build adds to the toolbox rather than to the argument. It is
the first cartridge in the corpus with **overlays**, so `bios_calls.py` had to
learn to resolve one image's branches against another's wrapper table. It is
the first with a **container**, so the blind decode, the internal-name harvest
and the format census all had to descend through it — unextended, the name
harvest reads 1,516 of 6,664 Nitro payloads and reports the number as if it were
all of them. And it is the first with a **positive control for the BIOS
decompressors**: one 6,736-byte animation shipped five times over, once per
format, beside the original, which found two real defects in this corpus's DS
decompressor and is described in section 7.
[nds-talesofinnocence-doc](https://github.com/vs-sr-dev/nds-talesofinnocence-doc).

### The thirteenth build is the control the twelfth asked for

*Tales of Symphonia: Ratatosk no Kishi* (Wii, 26 June 2008) exists in this
document for one reason, and the previous section wrote the reason down: two
zeros from two studios outside the line are compatible with *the boundary is the
codebase* and equally compatible with *that codebase never shipped a Nintendo
title*, and separating them needs a Nintendo build from the line itself.

This is that build, and it is better conditioned than the corpus had any right
to expect. It is the **direct sequel** to the 2003 GameCube *Tales of
Symphonia* — the only PowerPC positive here, which carries the decoder four
times in `main.dol` and decodes 487 of 487 blocks on each of two discs. It runs
on the **same processor family**: the Gekko and the Broadway are both PowerPC
750 derivatives. Both builds are Metrowerks. Both executables are Nintendo
`.dol` files. So for the first time in this corpus **the strong byte test is
available across a change of console**, and the question is not *is it the same
source* but *is it the same object*.

Four outcomes were possible and none was assumed: the codec descends from the
2003 copy; the codec is there as a fourth fork; the codec is gone and
Nintendo's own decompression is called in its place, repeating the 2003 Game
Boy Advance result on a much bigger machine; or the codec is gone and
middleware took over.

**It is none of the four. The codec is not there, and neither is anything
else's.**

The constant scan first, and on this machine it is a complete search — unlike
ARM, PowerPC encodes all five constants directly in a D-form immediate, which
is exactly how the 2003 build spells them:

| | Wii 2008 | GameCube 2003, the same scan |
|---|---:|---:|
| instruction words scanned, all images | **637,871** | 383,328 |
| relocatable modules to scan | **none exist** | eight |
| **4078** | **0** | 6 |
| **4079** | **0** | 6 |
| 4070 / 4071 | 0 | 0 |
| 4080 | 20, all disassembled | 25, all innocent |

Twelve sites in four routines at `+17`, `+21` and `+216` words in 2003; not one
of them in 2008. All twenty `4080` sites were read, as section 7 requires:
twelve are a 16-bit alpha counter clamped at 4,080 and then shifted right by
four — `li r0, 255` four instructions later is what settles it, `4080 = 255 << 4`
— and eight are `addi rX, rY, 4080`, a structure member's offset, immediately
before a call.

The structural probe agrees, and it was calibrated on the positive first:

| Fingerprint | Wii 2008 | **GameCube 2003, the control** |
|---|---:|---:|
| `ori rX, rX, 0xFF00` refill | **0** | **14** |
| `rlwinm rA,rS,4,20,23`, the high-nibble extract | **0** | **4** |
| clusters carrying two or more fingerprints within 200 instructions | **0** | **4** |

The control's four clusters are inside its four decoder copies, one each, found
without the probe being told where they are.

**And then the measurement this corpus has wanted since 2003.** 872 bytes of
the 2003 decoder at `0x8005D088`, searched at any alignment through whole
executables:

| Haystack | Longest identical run |
|---|---:|
| GameCube 2003 — the instrument on itself | **872** |
| **Wii 2008** | **10 bytes** |
| *The Last Story*, Wii 2011 — negative control | 12 bytes |
| *FF Crystal Chronicles: The Crystal Bearers*, Wii 2009 — negative control | 10 bytes |
| the 2008 disc's own apploader — negative control | 7 bytes |

The controls had to be **built**, and that is a note for section 7: this
document's standing negative control, `VENUS.ELF`, is MIPS, and against a
PowerPC needle it measures the architecture rather than the absence. Two
unrelated Wii titles and the disc's own apploader took its place.

**Byte equality was available and is demonstrated**, and finding it needed a
new instrument too, because there was no known shared routine to take a needle
from. Taking the longest identical run between the two builds' whole text
sections gives 1,275 bytes — and it is worthless, because *Crystal Bearers*
contains the same 1,275 bytes of Nintendo boot code. Subtracting the control
and repeating the search:

| | GameCube 2003 ↔ Wii 2008 |
|---|---:|
| plain | 1,275 bytes — SDK boot, also in both controls |
| excluding *Crystal Bearers* | **835 bytes** |
| excluding *Crystal Bearers* **and** *The Last Story* | **835 bytes** |
| every shared region of at least 64 bytes | **96 regions, 12,143 bytes, 0.79%** |

The 835-byte region is `OSSaveFPUContext` — 106 distinct byte values, `mfspr
r5, spr920` to test paired-single enable and then thirty-two `psq_l` pairs —
compiled in 2003 and again in 2008 to identical bytes. **Not one of the 96
shared regions touches either decoder copy**; the nearest ends 480 bytes before
the second copy's prologue, which confirms the `prefix_scan` result by a tool
that was not told where to look.

```
   835 bytes of library code identical
    10 bytes of decoder
```

That is the shape of the 2004 result — 276 of runtime against 17 of decoder —
run across a console generation.

The blind decode agrees over the largest medium this corpus has opened.
**Zero genuine blocks in 54,022 payloads and 4,286,322,608 bytes**, both
dialects, at every offset, with the 1995 cartridge's **1,089** returned by the
same tool in the same run — and ten chance survivors, seventeen to 260 packed
bytes each, all decoded and read, all of them ordinary data whose first nine
bytes happen to parse. On a 4.29 GB medium a few were expected; on a cartridge
none ever were, and the difference is the denominator rather than the format.

**What is *not* there is as informative as what is.** The 2003 Game Boy Advance
rebuild's lesson — a platform that supplies its own decompression gets used —
could not repeat, because **the Wii supplies none**. `RVL_SDK` has no
decompression service: no `LZ77UnComp`, no `svc` wrapper table, nothing the
loader decompresses on the way in. `Yaz0`, `Yay0` and the `LZ77` header are
conventions Nintendo's own titles implement in their own code. Both halves were
counted anyway and reported separately, as section 7 requires: **zero** of those
magics at offset 0 of 54,022 payloads, and **zero** in the executable as a
string or as a `lis`/`ori` immediate pair over 576,928 instruction words and
5,427 resolved branch targets. One caveat is owed and is stated in the pipeline:
that executable does not name `bres`, `RSTM` or `U8` either and demonstrably
reads all three, so on this platform the code-side zero is the weaker half.

**And the packer crossed.** This is the half that turns a negative into a
result. Both releases wrap their compressed assets in the fake Microsoft
Cabinet the 2003 pipeline documented — an `MSCF` header no cabinet reader can
open, used for its file entry's name, length and MS-DOS timestamp — and the
compressed stream behind that header carries a four-byte constant:

| | GameCube 2003 | Wii 2008 |
|---|---:|---:|
| archives | 545 | 1,506 |
| payloads whose bytes `+8`…`+11` are `5b 80 80 8d` | **545 of 545** | **1,506 of 1,506** |
| bytes `+0`…`+3`, distinct values | 223–229 of 256 | 255–256 of 256 |

Four constant bytes behind four uniformly random ones, in 2,051 payloads
written five years apart on two consoles. That is a compressor's preamble.
Section 8 calls the packer the only thing in this lineage that provably did not
fork and records it caught running twice; this is a third sighting, and it is
the one that separates the two halves cleanly. **The envelope and its
compressor crossed the console generation. The block codec did not.**

Nothing else did. **0 of 13,391 files** are byte-identical to a 2003 file,
**0 of 734** `MSCF` member names are shared, and `top2` — the 2003 project
name, which survived into the 2004 PlayStation 2 port's name table — is absent
from all 4.29 GB. Of 71,353 internal names harvested from the 595 MB that is
searchable, the cast of *this* game is everywhere, as a direct sequel's would
be, and there is not one name from any other title in the series: `rutee`,
`dimlos`, `cress`, `stahn`, `reid`, `veigue`, `senel`, `luke` all return zero.

The disc is the largest here by a wide margin — 4,699,979,776 bytes, 13,386
files, **17 h 42 m of audio and 20 m 23 s of video, 70.10% media**, against
*Abyss*'s 61.66% and 13.60 hours — and it buys no middleware at all, where the
2004 port ran CRI's `ROFS` and *Innocence* licensed nine CRI components. It also
does not name its developer anywhere in ASCII or Shift-JIS, was compiled with
RTTI off, and ships its credits as video, so *who* made it is not answerable
from the image.
[wii-talesofsymphoniadotnw-doc](https://github.com/vs-sr-dev/wii-talesofsymphoniadotnw-doc).

### The fourteenth build is inside the gap, and it closes it from the far end

The section above ends by turning the boundary question into a date: the last
confirmed appearance of the codec was *Tales of the Abyss*, 25 November 2005,
the first confirmed absence from the line itself was 26 June 2008, and nothing
in this corpus covered the thirty-one months between them.

*Tales of Vesperia* (Xbox 360, 7 August 2008) is inside that interval and at
the far edge of it. Its disc image is stamped **2008-06-20** — six days before
*Ratatosk no Kishi* shipped — and its executable's PE header is stamped
2008-06-19. **It carries the codec.**

**A step comes before the scan on this platform, and it is the third time this
document has had to write one down.** An Xbox 360 executable is AES-128-CBC
encrypted and may be LZX-compressed, and a constant scan over the shipped
`.xex` returns zero and looks exactly like a clean negative — the Nintendo DS
`BLZ` trap on a different machine. This one decrypts under the retail key and
uses the XEX `basic` scheme, which is not compression but a run-length
description of the address space; the recovered image is 15,958,016 bytes and
is the *memory* image, so a file offset in it is an RVA.

With that done the scan is a complete search, because PowerPC encodes all five
constants in a D-form immediate:

| | Wii 2008 | GameCube 2003 | **Xbox 360 2008** |
|---|---:|---:|---:|
| instruction words scanned | 637,871 | 383,328 | **3,989,504** |
| **4078** | 0 | 6 | **2** |
| **4079** | 0 | 6 | **2** |
| 4070 / 4071 | 0 | 0 | **0** |
| 4080 | 20, all innocent | 25, all innocent | **0** |
| sites in one routine | — | 12 in four | **4 in two, at +5, +53, +103, +151** |

Zero `4080` sites in four million instruction words is worth a sentence of its
own, because this document has twice had to disassemble twenty-five and twenty
innocent ones. There are none here, and the code says why: the ring clear is an
inline byte loop bounded by the cursor itself, so the multiple-of-sixteen
rounding that produced 4080 in 2004 never arises.

**And it is the 1997 shape, in every place the shape can differ.** The routines
at `0x820D51C0` and `0x820D5348` clear the ring with an inline byte loop
bounded by **4078** and **4079**; write **both** synthetic preload loops,
unrolled by eight, with `li r9, 255` for the second; refill the control
register with `ori r31, r11, 0xFF00`; mask the cursor with
`rlwinm r10, r9, 0, 20, 31`; take the length from the low nibble of the second
token byte and the reference's high bits from the high nibble; add the `+3`;
and carry the run escape with its `+19` and its long form. The ring is rebuilt
**on the stack** on every call, in a 4,272-byte frame.

The dispatcher is section 1 of this document, byte for byte:

```
0x820D5640  lbz  r11, 4(r31)     ; the packed size, assembled one lbz at a time
0x820D5644  lbz  r10, 3(r31)     ; from bytes 4, 3, 2, 1 -- little-endian
   ...
0x820D5658  lbz  r11, 0(r31)     ; the method byte
0x820D5660  cmplwi r11, 1
0x820D5670  blt  cr6, ...        ; method 0 -> the SDK's memcpy
0x820D5674  beq  cr6, ...        ; method 1 -> 0x820D51C0
0x820D5678  cmplwi r11, 3
0x820D567C  beq  cr6, ...        ; method 3 -> 0x820D5348
0x820D5680  li   r3, -1          ; anything else -> error
```

**The nine-byte header is still little-endian on a big-endian machine**, for
the third time and for the reason section 1 gave before anyone had looked at a
GameCube. Methods 0, 1 and 3 are used directly. The unpacked size is read at
`+5` by a separate getter. And **8,255 of 8,255 blocks decode** to their
declared length under `tales_block.py` unmodified — 337,852,435 packed into
775,930,739, with the 1995 cartridge's 1,089 returned by the same tool.

**The strong byte test is architecturally available and practically is not, and
saying so is the result.** Both builds are PowerPC, so `prefix_scan.py` ran:
872 bytes of the 2003 decoder score **10** here, which is what two unrelated
Xbox 360 titles score. But the control this document requires — *was byte
equality available?* — comes back no. `common_run.py` between the whole 2003
`main.dol` and the whole decrypted PE, with two unrelated Xbox 360 images
subtracted, finds a ceiling of **28 bytes**: eleven distinct byte values, a
`li rD, N ; b` jump-table stanza. Metrowerks against Microsoft Visual C++, and
Nintendo's SDK against Microsoft's, share nothing longer anywhere. On the Wii
the same tool found 835 contiguous bytes and a 10-byte decoder result therefore
meant something; here it does not.

Run where it does work, the instrument is decisive the other way. This disc and
*Eternal Sonata* — both Xbox 360, both MSVC, both published by Namco Bandai —
share **304 contiguous bytes** of code that two tri-Ace titles do not, while
their decoders share **17**, the same figure this decoder scores against
*Infinite Undiscovery*. So the tool finds shared code where there is shared
code, and there is none in any decoder on the platform.

The descent therefore has to be read off the constants and the structure, and
there it is unanimous. Set against the ways this document records of clearing
one array:

| Build | Year | Mechanism | Constant | Preload | Header | Run escape |
|---|---|---|---|---|---|---|
| 1997–2003 | | inline byte loop | 4078 | both loops | nine bytes | yes |
| Symphonia PS2 | 2004 | quadword `bzero` | 4080 | both loops | nine bytes | yes |
| Rebirth | 2004 | library `memset` | 4079 | both loops | nine bytes | yes |
| Legendia | 2005 | inline byte loop | 4078 | **none** | **`CPS `, sixteen** | **none** |
| Abyss | 2005 | inline byte loop | 4078 | both loops | nine bytes | yes |
| **Vesperia** | **2008** | **inline byte loop** | **4078 / 4079** | **both loops** | **nine bytes** | **yes** |

Six independent choices, and this build makes *Abyss*'s every time. The three
edits this document records as having gone nowhere went nowhere here either.

**What it does to the previous section is to take the date away again, in a
useful direction.** *Ratatosk* was mastered six days before this disc, from the
same studio line, and carries no compressor of its own and no platform one
either. This one carries both. There was no line-wide decision to drop anything
in the thirty-one months; two projects in one quarter simply made different
choices. The question stops being *when did the line drop the codec* and becomes
*why did one 2008 project drop it while its sibling kept it* — which is a
smaller question, and a different kind.

**The platform's own compressor is here too, and the same routine dispatches
both.** This is the first build since the 2003 Game Boy Advance rebuild where
"what does the platform give you for free" has a real answer: the XDK supplies
`XMemCompress`, LZX with a 128 KB window. The disc carries **6,128** bare
XCompress streams — 3.33 GB expanding to 11.67 GB — beside the 7,859 codec
blocks, and `0x820D5570` chooses between them with one `lwz` and one `cmplw`
against XCompress's magic `0x0FF512EE`, falling through to the nine-byte
dispatcher when it does not match. That routine allocates its 4,272-byte frame
— sized for the codec's ring — on **both** paths, including the one that does
not need a ring, so Microsoft's decompressor was grafted into a routine that
already existed. Sixty-five call sites reach it out of 23,150 resolved branch
targets; the SDK's `memcpy` has 870, so the instrument finds callers where
there are callers.

**And the packer did not cross this time.** The fake Microsoft Cabinet that
carried `5b 80 80 8d` at `+8` in 2,051 of 2,051 payloads across 2003 and the
Wii build is **not on this disc**: `MSCF` returns two hits against a chance rate
of 1.82 on a 7.84 GB medium, both were located, and both sit inside
high-entropy payload. The container is `FPS4` — big-endian, 4,126 archives, a
**field mask** that says which of four per-entry fields are present, 32-byte
names, and the packer's own working directory left in the header in Shift-JIS
(`../Release/共通/UI.svo`). So of the two things the previous section said
crossed the generation together, the envelope and its compressor, neither
reached this disc — and the LZSS that did not cross to the Wii did.

Two more things this build supplies, and one of them is a correction.

**The negative controls talked back.** Four Xbox 360 PowerPC executables were
run as controls — *Infinite Undiscovery*, *Eternal Sonata*, *Resonance of
Fate*, *Star Ocean: The Last Hope* — and *Eternal Sonata* (2007, tri-Crescendo,
published by Namco Bandai) is not clean. It carries a 4,096-byte-ring LZSS of
its own: `memset(ring, 0, 4096)`, a cursor at **4078**, `& 0x0FFF`, the length
in the low nibble, the reference's high bits in the high nibble, `+3`. It is
**not this format** — no synthetic preload, no `| 0xFF00` refill, no nine-byte
header, no run escape, and 17 shared bytes against 304 of shared library — but
it is the counterexample section 7's shortcut has never had.

Those constants are the canonical 1989 LZSS reference implementation's:
`N = 4096`, `F = 18`, `THRESHOLD = 2`, and a cursor initialised to `N − F` =
**4078**, with the match position's high bits in the high nibble of the second
token byte and the length in the low nibble. That is the most copied compressor
source in existence. Nothing this document has published depends on the
constant alone — the 1997↔2000 identity is 212 bytes of object code, the 2004
fork is 17 against 276 of runtime, the 2005 descent is 69 bytes and 31
identical words — but the *checklist* has recommended the constant as a
shortcut for six builds, and on a large MSVC binary it returns two to seven
hits by itself. Section 7 now says what the constant finds and what identifies
which one it found.

**And the structural probe scored zero on a true positive until it was fixed.**
It was calibrated on the 2003 Metrowerks build, which writes the control refill
in place — `ori r0, r0, 0xFF00`. Microsoft Visual C++ allocates a separate
destination and writes `ori r31, r11, 0xFF00`. A probe requiring `rA == rS`
therefore finds **no refills in a build that plainly contains two**. Both
spellings are now counted and both feed the cluster pass; with that, the probe
finds this decoder without being told where it is — one cluster carrying two or
more distinct fingerprints in 1,080,715 words, against zero in three of the
four controls.

Nothing crossed at the asset level in either direction. **0 of 11,154 payloads**
are byte-identical to anything on the Wii disc six weeks earlier and **0 of
11,133 member names** are shared with its 13,116; against the 2003 GameCube
disc the figures are 0 and 1, and the one is `04.dat`. Of **106,605** internal
names harvested from 4.68 GB, `rutee`, `dimlos`, `emil`, `marta` and `lloyd`
all return zero, where *Ratatosk*'s equivalent figure was zero out of 71,353.
Total reconstruction is this line's normal practice, not something that happened
once.

One last difference, and it answers a question the previous build recorded as
unanswerable. *Ratatosk* was compiled with RTTI off, names its developer
nowhere in either alphabet, and ships its credits as video. This build was
compiled with RTTI **on**, carries **445 demangled C++ class names**, and its
title metadata names both companies in Japanese:
`株式会社バンダイナムコゲームス` and **`株式会社ナムコ・テイルズスタジオ`**.
Whether a build names itself is a property of its build settings, and this line
in mid-2008 did.
[xbox360-talesofvesperia-doc](https://github.com/vs-sr-dev/xbox360-talesofvesperia-doc).

### The fifteenth build is two cartridges, and the container crossed instead

*Tales of Hearts* (Nintendo DS, 18 December 2008) shipped as **two** cartridges
on one day — an Anime Movie Edition and a CG Movie Edition — and it is the
third Nintendo DS title in this corpus and the first carrying the project
number after *Vesperia*'s. It does not carry the codec, and what it does carry
takes a clause out of the previous section rather than adding one.

**Step zero finally bit.** Section 7 has made *decompress the modules first*
the opening act on this platform since the eleventh build, with the standing
note that the step had never yet prevented a false negative and that this was
known only because it was run every time. On these cartridges **thirty-two of
the thirty-three modules are `BLZ`-packed** — the ARM9 and all thirty-one
overlays — so 1,620,780 bytes on the cartridge become 2,852,064 bytes of
plaintext code, and a scan of the shipped image would have returned the same
zero over the wrong bytes.

Worse, and this is the part worth carrying forward: **the decompressor was
wrong in two ways and had never been executed.** Written for *Tempest*, which
has no overlays, and carried to *Innocence*, whose three are stored plain, it
assembled a match token's two bytes in the wrong order and did not clamp the
copy to the end of the encoded region. Both defects fail in the direction of
*this module is not packed*. The repair has a positive control that was on the
cartridge all along and that section 7 now recommends looking for: **the
overlay table states each overlay's plaintext length**, written by the Nintendo
linker, and **31 of 31 overlays decompress to exactly their declared length**.

With that done the scan is a complete search in both of the encodings ARM has,
and the answer is a clean negative quoted against its denominators:

| | ARM9 | ARM7 | 31 overlays | **total** |
|---|---:|---:|---:|---:|
| ARM data-processing immediates | 45,111 | 11,911 | 144,405 | **201,427** |
| THUMB instructions carrying a literal | 26,436 | 5,253 | 74,630 | **106,319** |
| 4-byte-aligned words | 186,366 | 39,882 | 486,768 | **713,016** |
| distinct PC-relative load targets | 7,175 | 1,800 | 18,158 | **27,133** |
| **4078 / 4079 / 4070 / 4071, either form** | **0** | **0** | **0** | **0** |
| 4080 | 3 immediates + 4 words | 0 | 0 | 7 |

The overlays hold 71% of the ARM immediates and 70% of the THUMB literals, so a
scan of `arm9.bin` alone covers under a third of the code — the same proportion
*Innocence* recorded, and the reason the scanner now has a directory mode with a
totals row.

All seven `4080` sites were disassembled, as section 7 requires. One is a
structure member's offset before a call, the shape *Ratatosk* found eight times.
One is `add r0,r5,#4080 ; add r0,r0,#61440` — `4080 + 61440 = 65520 = −16 mod
2**16` — a range check split across two immediates because ARM cannot encode
65,520 in one, which is a way for this constant to appear that no other machine
in the corpus offers. One is a four-field unpack of a single word with masks
`0xFF00000` / `0xFF000` / `0xFF0` / `0xF`, which is the nearest thing on either
cartridge to looking like the codec and is four fields where the codec has two.
And **the remaining four are entries of a 4,096-scaled cosine table**, none of
them the target of any PC-relative load, with **96 of 96 surrounding aligned
words** equal to `round(4096 · cos θ)` to within one — *Tales of the Tempest*'s
finding on a second cartridge, stored as a plain array there rather than as the
446 compiled stubs Tempest carried.

The structural probe agrees, with one row that has to be read rather than
counted. It reports **eight** `orr rX, rY, #0xFF00` — the control-register
refill, the fingerprint this document calls load-bearing — and all eight are
`orrgt`, each following a `cmp` against 127 or 255 and each followed by
`lsl #16 ; asr #16`. **They are sign extensions**, and section 7 now carries the
discriminators. Zero fingerprint clusters over 713,016 words. And the ARM/THUMB
trap fired for the third time: **0 genuine ARM `add #19`, 67 THUMB, and all 67
inside ARM words** — `mov r3,r3,lsl r7` and `movs r3,r3,lsl r5`, the video
decoder's bit-consume step, exactly as on *Innocence*, which reported 22 where
Tempest reported 24.

And the blind decode, through a descent five levels deep whose top level is the
*executable*: **0 blocks in 47,195 payloads and 376,083,362 bytes** on each
cartridge, both dialects, at every offset, with the 1995 cartridge's **1,089**
returned by the same unmodified decoder in the same invocation.

**Two cartridges are an internal control, and this is the first time the corpus
has had one.** Running the identical container descent over both images and
comparing payload by payload: **28,662 of 28,679 distinct payloads are
byte-identical**. Seventeen differ, and every one is the film or a structure
that moves because of it — the nine movies, a fifty-byte Shift-JIS build note
saying which edition's assets are in the tree, the ROM header, the banner, the
file allocation table, two alignment regions, the tail, and `arm9.bin`, whose
plaintext differs only in regenerated secure-area filler, **eight `BLX` offsets
into it**, and one byte of its own packed length. Those eight addresses are
independently the eight call sites the BIOS-caller census reports. The two
cartridges run the same code, so every measurement on one is a measurement on
both.

**What is there instead is the platform's compression without the platform's
code, and the studio's container.** 5,280 BIOS-format streams *inside the
containers*, 61,737,814 bytes becoming 123,245,746 — against **zero callers** of
all six linked decompression wrappers over **43,946** resolved branch targets,
across the module boundary, with `CpuSet` at one caller and `Stop/Sleep` at
seven so the instrument is shown to find callers where there are callers. The
software routine that must therefore exist was not found, which is the second
time that probe has failed on a build that demonstrably contains its target.

The file-level figure is 11 of 5,145, and quoting it would have been the error:
this build compresses inside its containers rather than at the file level, so a
census that stops at the Nitro file system reports a build that barely
compresses instead of one whose asset pipeline is compressed throughout.

**And the container is `FPS4`.** The same container as the Xbox 360 *Tales of
Vesperia*, mastered five months earlier: same 0x1C header, same field mask
selecting which of four per-entry fields exist, same 32-byte names — and
**little-endian here where it is big-endian there**. The byte order is the
machine's and the structure is the line's, which is the nine-byte block
header's own behaviour in reverse. 2,492 archives read against 2,493 magic hits
on the raw image, so the descent is complete and not merely deep. A second
container, `V154`, holds 1,508 objects behind the project's own `.ds3`
extension.

So the shape this document adopted after the fourteenth build needs one thing
added rather than changed. It was: the codec persists and the packer varies.
These cartridges add a third thing that persists — **the container's
structure** — and it persisted across a change of machine, of byte order and of
processor family in five months, while the compressor it was built to hold did
not travel with it.

**What it cannot settle is who built it, and that has to be said in the same
breath as the rest.** The cartridge names its developer **nowhere**, in ASCII,
Shift-JIS or UTF-16LE — `テイルズスタジオ` zero, `株式会社` zero,
`アルファ・システム` zero, `Dimps` zero — and it was compiled with RTTI off, so
there are five C++ names in 2,852,064 bytes of plaintext and all five are the
standard library's. The publisher is named once, in the banner, in UTF-16.

What it does carry is a project number. **`TO9`** is in six file names, in a
file extension of its own (`.to9moh`, 101 members) and in a debug overlay's
version banner four bytes from the build date `Nov 19 2008` — and `TO7` is
*Tales of the Abyss*'s tag and `TO8` is *Tales of Vesperia*'s, both of them
line builds that carry the codec. That is the whole of the lineage evidence: a
number in the right place in a known sequence, and no hand attached to it.
[nds-talesofhearts-doc](https://github.com/vs-sr-dev/nds-talesofhearts-doc).

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

### The boundary tested off the console entirely

*Tales of Tactics* is the first title here that is not a console game: an NTT
DoCoMo i-appli, DoJa-3.0, built **16 December 2004** — the day *Tales of
Rebirth* was released. It is a Java application, so the question changes shape
before it can even be asked, and the answer is a clean negative with a large
measurement behind it.

| | class files | bytecode | instructions | integer constants | `4078` | `4079` |
|---|---:|---:|---:|---:|---:|---:|
| *Tales of Tactics* | 3 | 132,205 | 76,283 | 6,286 | **0** | **0** |
| three sibling i-appli, as control | 8 | 358,949 | 185,526 | 31,650 | **0** | **0** |
| **combined** | **11** | **491,154** | **261,809** | **37,936** | **0** | **0** |

`0xFF00` and `0x0FFF` are absent too, no 4,096-element ring is allocated, and
no structural fingerprint of the format — nibble-pair token, control-register
refill, `+3` / `+19` run escape — appears anywhere. The unmodified reference
decoder was then handed **35 payloads and 971,959 bytes** of that package in
both dialects, and **2,470,639 bytes** across the four titles, and returned
**zero blocks**.

What is there instead is **deflate, twice, and the application wrote neither
layer**: the JAR itself, and then each downloaded data file served as its own
single-entry JAR and inflated on the device by the platform's
`com.nttdocomo.util.JarInflater`. There is no application-layer codec at all.

This is a different kind of negative from the two already here. The 2003 Game
Boy Advance rebuild said the format travelled with the team and not the title;
*Venus & Braves* said it belonged to the *Tales* codebase and not to the
company or the console. This one says that **the codebase itself was the
boundary all along**, because a title built in the same month by the same
publisher, on a machine with no C and no console runtime, had nothing to
inherit. Nothing was dropped. There was nothing to drop.

Two details make it a sharper control than it might have been. First, the
studio's crossover roster in that build names the male and female lead of
*Phantasia* 1995, *Destiny* 1997, *Eternia* 2000, *Destiny 2* 2002 and
*Symphonia* 2003 — exactly the five positive results above, in order — so the
two projects were demonstrably aware of each other while sharing no code.
Second, the three sibling i-appli used as controls are **obfuscated** to
single-letter class names while *Tales of Tactics* is not, so the negative does
not rest on one build's tooling.
[keitai-talesoftactics-doc](https://github.com/vs-sr-dev/keitai-talesoftactics-doc).

So the current boundary of this format is: **the *Tales* codebase itself**,
for as long as that codebase carried its own decompressor — and inside that
boundary the code did not evolve. From 1997 to 2000 it was recompiled to the
same bytes; from 2000 to 2002 it was recompiled to a different CPU. The
boundary is not the company (Namco shipped *Venus & Braves* without it), not
the console (both PlayStation 2 games are on one disc), and not the series
name (*Berseria* shares only that). Anything that narrows or widens it is
worth adding here.

What the eleventh build adds is a **limit on what a single negative can say**.
*Venus & Braves* changed the team and held the disc, the console and the year
fixed. *Tales of Tactics* changed the machine and the language and held the
publisher and the month fixed. *Tales of the Tempest* changes **the machine and
the team together**, so its zero is compatible with the boundary being either
one. The corpus needs a Nintendo DS control — a title from the same publisher
and a different developer, or from the same developer and a different series —
before this build can narrow anything. Until then it widens the *evidence* and
not the *statement*.

**The twelfth build is that control, and it is the first of those two forms.**
*Tales of Innocence* (Nintendo DS, 2007) holds the publisher, the platform and
the series and changes the developer, and it returns the same zero on the codec
while compressing 16.9 MB into 32.1 MB in the *platform's own* `LZ77`, filling
96.8% of its cartridge and shipping 1,344 archives of its own. The machine is
therefore excluded, and Tempest's raw data becomes a fact about Tempest. The
statement narrows for the first time since 2005.

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
2. **Scan the executable for the immediates 4078, 4079 and 4080.** The first
two are `RING − 18` and `RING − 17`; the third is 4,078 rounded up to a
multiple of sixteen. Until 2004 only 4078 was needed, because every build
cleared the ring with an inline loop bounded by it. Since then the constant has
not been stable — Symphonia's PlayStation 2 port uses 4080, Rebirth 4079, and
Legendia 2005 and Abyss 2005 go back to 4078 — so ask for all three at once and
**print the immediate for every hit**, because which one answers tells you which
mechanism the build uses and therefore which copy of the source it descends from.
No other part of a game has a reason to load 4,078.
On *Tales of Destiny 2* that filter returned seven sites across two files and
both decoders were within a hundred bytes of one of them.

**Ask for 4070 and 4071 too.** Where the ring clear is an inline loop unrolled
by eight, those are its bound and the 4078/4079 hit is the *cursor*, more than a
hundred words further down the routine. See the checklist below, step 2.

**It survives a change of instruction set — but not always in the same
field.** On PowerPC the constant appears in the low half of a D-form word
instead of an I-type one — as `subfic`, `cmpwi` and `addi` — and the word is
stored big-endian, but the constant is the packer's and does not move. On
*Tales of Symphonia*'s GameCube build the filter returned twelve sites in four
routines, and the *offsets within each routine were the same three*: `+17`,
`+21`, `+216` words. A tool that does both instruction sets is
[`ring_sites.py`](https://github.com/vs-sr-dev/gc-talesofsymphonia-doc/blob/main/tools/ring_sites.py).

**On ARM it survives as data rather than as an operand,** because 4078 and 4079
are not encodable there at all and a compiler puts them in the literal pool.
That is a different search, not a harder one, and the section below carries it.
`4080` *is* encodable on ARM, so the three constants split. Do not read a
single-pass ARM scan's silence as a negative.

It cuts the other way just as well. The absence of `4078` across a whole
executable is strong evidence the decoder is not there, which is how *Venus &
Braves* was ruled out without decoding anything — and how the 2004 build's two
I/O processor images were ruled out in 2004. On *Tales of Rebirth* it returned
eight sites in the main executable and five in `BOOT.IRX`, and **none at all** in
`IOPRP300.IMG`, which is nineteen stock Sony modules.

### When the constant is there and the blocks are not

Steps 1 and 2 assume the nine-byte header is the thing to look for, and for
eight builds it was. On the ninth it is not, and the failure is silent: *Tales
of Legendia* (PlayStation 2, 2005) contains the decoder — one `4078`, the ring,
the mask, the `+3`, all of it — and a scan for the header shape over its data
returns **zero blocks in both dialects**, because the game wraps its streams in
a *sixteen*-byte container of its own with no method byte in it.

So the two halves of the check can disagree, and when they do, **the constant
scan is the one to believe**. The header scan can only find an envelope it
already knows; the constant is in the code and the code is what you are asking
about.

The order that works:

1. **Run the constant scan first**, not second. It is cheaper than a decode
   sweep and it fails in the informative direction: no 4078/4079/4080 anywhere
   means no decoder, and that is the strong negative that ruled out *Venus &
   Braves* and the 2004 I/O processor images.
2. **Ask for 4070 and 4071 as well.** This is the tenth build's correction and
   it costs one more command. The scan finds `RING − 18` and `RING − 17`, which
   are the *cursor*; on a build whose ring clear is an inline loop **unrolled by
   eight** the loop bound is 4071 or 4070 instead, and the cursor is set far
   below it. On *Tales of the Abyss* the 4078/4079 hits land at **+135 and +139
   words** into their routines; `--imm 4070,4071` puts them at +10 and +11. See
   step 3, which stops working when the hit is 139 words in.
   The two constants say something else as well, and it is a *toolchain*
   signature rather than a source one: *Destiny 2* (2002, no compiler string)
   clears the ring one `sb` at a time with 4078, while *Symphonia*'s second
   pair, *Legendia* and *Abyss* — all three stamping `MW MIPS C Compiler
   (2.4.1.01)` — unroll it by eight. Legendia shares 18 bytes with Abyss's
   decoder and unrolls it identically, so the unroll is the compiler's. Do not
   read 4070/4071 as a packer constant; 4078 and 4079 are still the only ones
   that are.
3. **Disassemble the hit before scanning any data.** Forty instructions from the
   *top of the routine* is enough to read off the ring base, the mask, the
   initial cursor and the token shape, and to see whether the routine takes a
   *block* or takes `(source, destination, length)`. If it takes the latter
   there is no nine-byte header on that disc and the header scan will return
   zero however long you run it. Forty instructions around a *hit* is not the
   same thing once the hit can be 139 words in — walk back to the prologue
   first.
4. **Then find the envelope by looking at what calls the routine**, or — faster
   — by looking at what the container's members actually start with. Legendia's
   answered itself: its archive members are named `*.cps` and they begin
   `CPS `.
5. **Do not stop the census at the member level.** A member can be a *flat run*
   of blocks with no container header of its own — one block after another, each
   starting on a sector boundary so the loader can seek to one without reading
   the ones in front of it. On *Tales of the Abyss* twenty-seven members are
   built that way and they hold **46,345 of the disc's 47,513 blocks**, which is
   97.5% of them and 545 MB of packed data. The failure is silent and it looks
   like success: `F0.PKF` is 37,951,488 bytes, its first nine bytes are a
   perfectly valid header, and a member-level census decodes 163,176 bytes,
   matches the declared length, and reports one block. Walk from the first
   block, align each next offset up to the sector, and accept the run only if
   the walk reaches the end of the member — which is what stops an ordinary
   file whose first byte happens to be 1 or 3 from being mistaken for one.
6. **Do not treat the preload as given.** Every PlayStation-family build from
   1997 to 2004 fills the ring with 3,840 synthetic bytes before reading a
   token. Legendia's `ring_init` clears 4,078 bytes and returns. Since section 4
   also warns that a wrong dictionary still produces the *right length*, the
   only way to tell which variant a disc uses is to decode something that ought
   to be a recognisable structure and look at it. On Legendia the empty ring
   produces a parseable index table whose length the disc's own size table
   agrees with; the preloaded ring does not.

The general lesson is worth stating apart from the title that produced it. This
document's own section 6 has always separated "the format" from "the code",
and the checklist quietly conflated them by making the on-disc header the test
for both. **A build can have the algorithm without the source and without the
container.** Ask the code first.

### When the target is ARM, the constant scan becomes two scans

The shortcut assumes a machine that carries constants in immediate fields
inside fixed-width instruction words. MIPS and PowerPC both do, and that is
why it generalised across a byte order without anyone having to think about
it. ARM is fixed-width too, and it still breaks the assumption, for a reason
that is pure arithmetic:

**An ARM data-processing immediate is an 8-bit value rotated right by an even
amount.** Nine significant bits do not fit. So

| Constant | Encodable as an ARM immediate? |
|---|---|
| 4070 (`0xFE6`) | **no** |
| 4071 (`0xFE7`) | **no** |
| **4078 (`0xFEE`)** | **no** |
| **4079 (`0xFEF`)** | **no** |
| **4080 (`0xFF0`)** | **yes — `0xFF ror #28`** |

The two constants this document calls the packer's cannot be written as ARM
immediates at all. A compiler emits them as 32-bit words in the **literal
pool** — raw data between routines — loaded with `ldr rX, [pc, #offset]`. The
2004 constant *can* be written as an immediate. So on this one machine the
three constants are found by two different searches and a hit in one means
something different from a hit in the other. In THUMB nothing helps: `mov rd,
#imm8` reaches 255, so all five are literal-pool words there too.

Two further ARM-specific facts belong in the same paragraph, because they
change what the *structural* probe of step 3 can see:

* `orr rX, rX, #0xFF00` **is** encodable (`0xFF ror #24`), so the control
  register's refill would appear as a plain immediate and a probe will find it
  -- **and so will a sign extension, which is the same instruction.** This is
  the fifteenth build's correction and it is not cosmetic: a compiler widening
  a signed byte or a signed 9-bit field to a halfword emits

  ```
  cmp    rX, #127          (or #255)
  orrgt  rX, rX, #0xFF00
  movgt  rX, rX, lsl #16
  movgt  rX, rX, asr #16
  ```

  and *Tales of Hearts* carries eight of them in one routine that unpacks
  packed coordinate pairs. The discriminators are **the condition code** --
  this format's refill is unconditional -- and **the neighbouring `cmp`**,
  which the format does not have because its refill follows a byte load. A
  probe that counts the bare instruction reports eight refills on a build with
  none, which is the mirror of the Xbox 360 failure: there the probe missed two
  real ones, here it would invent eight;
* `and rX, rY, #0x0FFF` is **not**, so the ring mask appears as a literal-pool
  4095, or as `lsl #20` followed by `lsr #20`, and all three forms have to be
  counted;
* `4096` **is** encodable (`1 ror #20`), so a 4,096-byte ring on the stack or
  passed to an allocator stays visible.

**The variant that works on ARM:**

0. **Decompress the module first.** On a Nintendo DS the `arm9.bin` and every
   overlay are normally packed with `BLZ`, the linker's backwards LZ, and a
   scan of a compressed module returns zero and looks exactly like a clean
   negative. The overlay table says per overlay whether it is compressed; the
   ARM9 says so in its module parameters (`compressed_static_end`), and the
   `BLZ` footer says so independently. Check both, scan all of them, and say
   which were compressed.

   **The fifteenth build is where this stopped being a precaution.** *Tales of
   Hearts* (Nintendo DS, 2008) packs **thirty-two of its thirty-three modules**
   -- the ARM9 and all thirty-one overlays -- turning 1,620,780 bytes on the
   cartridge into 2,852,064 bytes of plaintext code. Scanned as shipped it
   returns the same zero it returns in plaintext, over 43% fewer bytes and the
   wrong ones.

   **And check the decompressor before believing it, because ours was wrong.**
   It had never been executed: *Tempest* has no overlays, *Innocence*'s three
   are stored plain, and the routine went two pipelines without running once.
   Two defects, both of which fail in the direction of *this module is not
   packed*: the two bytes of a match token were assembled in the wrong order --
   walking a backwards stream, the byte at the *higher* address is the one a
   forward reader sees first -- and the copy was not clamped to the end of the
   encoded region.

   **The positive control for it is free and it is on the cartridge.** The
   overlay table states each overlay's *plaintext* length in its `ram_size`
   field, written by the Nintendo linker and by nothing of ours, so a correct
   decompressor has to reproduce it. On *Tales of Hearts*, **31 of 31**. Any DS
   target with overlays supplies the same check; run it.

   **Scan the overlays, and resolve branches across the module boundary.**
   Tempest had none, so *resolve every branch in the image* was a complete
   search. Innocence has three, they all load at one address, and 71% of its
   ARM data-processing immediates and 69% of its THUMB literals are in them or
   in the ARM7 -- so a scan of `arm9.bin` alone covers under a third of the
   code. Worse, the SDK's `svc` wrappers are linked **once**, into the ARM9, so
   an overlay that called one would branch across the module boundary and leave
   no call site the single-image count can see. Count one wrapper table against
   every image's branches:
   [`bios_calls.py --also FILE@VA`](https://github.com/vs-sr-dev/nds-talesofinnocence-doc/blob/main/tools/bios_calls.py).
1. **Scan the immediate fields** — every ARM data-processing instruction with
   `I = 1`, decoded and rotated; every THUMB instruction carrying a literal.
   Print the count of instructions scanned, not only the count of hits.
2. **Scan the literal pool** — every 4-byte-aligned `u32` equal to a wanted
   constant. A raw word match is weak on its own, so **cross-reference each hit
   against every PC-relative load in the image**: a word some `ldr` points at is
   a constant, and a word nothing points at is data. Print the number of loads
   resolved and the number of distinct targets.
3. **Read every near-miss, and check every THUMB hit against the ARM word that
   contains it.** This is the ARM-specific trap and it is not optional. On a
   mixed ARM/THUMB image a THUMB-only probe invents fingerprints out of ARM
   code: on *Tales of the Tempest* the probe reported 24 THUMB `add #19`, and
   all 24 are ARM words at even offsets — `0xE5CA3013` is
   `strb r3, [r10, #19]`, `0xEB003613` is a `bl`, `0x00003013` is data. The
   genuine ARM count was zero. A tool that prints the containing word for every
   THUMB hit makes this a two-second check instead of a false positive.
4. **Expect the innocent hits to be trigonometry.** `4080` is
   `round(4096 * cos 5 deg)`, and a fixed-point engine that scales its sine and
   cosine tables by 4,096 will carry it. On this cartridge four of the five
   `4080` immediates are entries of exactly that table, compiled as 446
   constant-returning stubs behind a computed branch. That is not a coincidence
   to be dismissed; it is the reason 4080 is a weaker signal than 4078 on any
   machine, and on ARM it is the *only* one of the five that a naive immediate
   scan can find.

A tool that does all four is
[`ring_sites.py`](https://github.com/vs-sr-dev/nds-talesofthetempest-doc/blob/main/tools/ring_sites.py),
which now covers MIPS, PowerPC and ARM/THUMB in one file; the structural half
is
[`struct_probe.py`](https://github.com/vs-sr-dev/nds-talesofthetempest-doc/blob/main/tools/struct_probe.py)
and the near-miss reader is
[`nearmiss.py`](https://github.com/vs-sr-dev/nds-talesofthetempest-doc/blob/main/tools/nearmiss.py).

### Sweep per member, not per image

A blind decode over a whole image in one buffer is not the same test as a blind
decode over each of its files, and it is worse. `plausible()` bounds a
candidate by whether its declared stream fits inside the buffer it sits in.
Inside a 64 KB file that rejects nearly everything for free; inside a 134 MB
image it rejects almost nothing, so the sweep spends its whole time decoding
garbage the per-file pass would have discarded, and it can fail to finish at
all.

Sweep each member at every offset, and then sweep the **complement** — the
header, the tables, the alignment slack between members, the unused tail — as
its own set of payloads. Every byte is covered exactly once and the cost is
what it should be. On *Tales of the Tempest* that is 4,712 files plus 3,954
gap regions plus the nested containers: **9,055 payloads, 256,548,562 bytes,
both dialects, zero blocks**, with the 1995 cartridge's 1,089 printed in the
same run as the control.

**And "per member" has to mean per *container* member, not per file, the moment
the target has a container.** On *Tales of Innocence* two thirds of the data is
inside 1,344 `EZBIND` archives and a hundred of those are inside a BIOS `LZ77`
stream, so a per-file sweep covers the archives as opaque blobs and their 9,646
members never get their own bound. The same applies to every other per-file
pass: the Nitro internal-name harvest that produced Tempest's `stan` / `dimlos`
result reads 1,516 of that cartridge's 6,664 Nitro payloads if it is not taught
to descend, and reports its 936 names as though they were the corpus. **A tool
written for a flat file system fails silently on a nested one, in the direction
of a clean-looking negative** -- and it fails silently on a *directory tree*
too: `os.listdir` over a root with 156 subdirectories measures zero files and
says so in the words a real zero uses.

The same argument applies to sweeping for a *platform's* compressed streams,
and there it comes with a second caveat worth stating rather than glossing:
**most of the BIOS formats cannot be ruled out by decoding at all.** `RLE` and
the two difference filters accept any byte sequence; a small Huffman tree walks
arbitrary bits happily; `LZ11`'s four-byte token reaches 65,808 output bytes,
so no ratio bound constrains it. `LZ77` is the one that discriminates, because
it rejects a back-reference before the start of the output *and* its geometry
caps the ratio at 18 / 2.125 = 8.47x. Sweep that one and report the others by
header count, with the reason.

**And check the decompressors themselves against something, because two of them
were wrong.** A DS decompressor written for a cartridge that contains no
compressed stream is never exercised, and both of its failure modes read exactly
like a clean negative. *Tales of Innocence* supplied the corpus's first positive
control — one 6,736-byte animation in `/motion/alb000/` shipped **five times
over**, once per format, beside the original — and it found two defects that had
been silent since the tool was written:

* **the difference-filter type bytes were one place low.** The DS header is
  `0x80 | width_code`, and the width code is 1 for 8-bit and 2 for 16-bit, so
  the two filters are **`0x81` and `0x82`** and **`0x80` is not a stream type at
  all**. This is not cosmetic: 2,444 CRI audio files on that cartridge begin
  `0x80 0x00`, so a census reported 2,444 "Diff8" files that were nothing of the
  kind.
* **the Huffman walk was wrong twice.** The leaf mask must be `0x80 >> bit` --
  bit 7 flags the zero-child and bit 6 the one-child -- and the child address
  must be computed from the *node's own address*,
  `(a & ~1) + (n & 0x3F) * 2 + 2 + bit`, not from an index relative to the tree,
  because the tree always starts at an odd address with the tree-size byte in
  front of it. Both failures come out as `tree overrun`.

All five formats now decode to the original byte for byte
([`ndscomp.py --verify`](https://github.com/vs-sr-dev/nds-talesofinnocence-doc/blob/main/tools/ndscomp.py)).
If a target has such a benchmark on it, run it before quoting any BIOS-format
census; if it does not, quote the census knowing it has never been checked.

**"The BIOS format" and "the BIOS service" are two different findings, and a
build can have one without the other.** On *Tales of Innocence* 102 files are
valid BIOS `LZ77` streams -- each decoding and consuming its whole file, 16.9 MB
becoming 32.1 MB -- while all twelve decompression wrappers have zero callers
over 40,411 resolved branch targets, no `svc` is an instruction outside the
wrapper table, and no wrapper address appears as a data word. Somebody
reimplemented the platform's format in software, and a five-family fingerprint
probe over all five modules did not find the routine. Report the two halves
separately: the census answers *what format is the data in*, the branch count
answers *does this build call the BIOS*, and they are allowed to disagree.
[`lzprobe.py`](https://github.com/vs-sr-dev/nds-talesofinnocence-doc/blob/main/tools/lzprobe.py)
is the probe, published with its denominators and with the fact that it failed.

### What the constant finds, and what identifies which one it found

This section has recommended the `4078` scan as a shortcut since the second
build, on the strength of one sentence: *no other part of a game has a reason
to load 4,078.* The fourteenth build supplied the counterexample, out of its
own negative controls, and the sentence needs replacing rather than defending.

**4078 is not this codebase's constant. It is LZSS's.** The canonical 1989
reference implementation of LZSS — the most copied compressor source in
existence — uses a 4,096-byte ring, an 18-byte maximum match and a
three-byte minimum, initialises its cursor to `N − F` = **4078**, and packs the
match position's high bits into the **high** nibble of the second token byte
with the length in the low nibble. Every one of those is also true of this
format, because this format is that implementation with three things added.

*Eternal Sonata* (Xbox 360, 2007, tri-Crescendo, published by Namco Bandai) was
run as a negative control against *Tales of Vesperia* and is not clean. It
carries `memset(ring, 0, 4096)`, a cursor at 4078, `& 0x0FFF`, the low-nibble
length, the high-nibble reference and the `+3` — and it is **not this format**.
The three things this format adds are all absent from it:

* the **synthetic preload** — 3,840 bytes of `(i, 0x00)` and `(i, 0xFF)` pairs,
  which section 4 measured *Eternia* reading 1,039,128 times. The canonical
  implementation fills its ring with spaces; *Eternal Sonata* fills it with
  zeros and returns;
* the **`| 0xFF00` control refill**, which is how this format's decoders know
  when eight tokens are spent. *Eternal Sonata* keeps a byte-wide mask and a
  separate counter in a struct;
* the **nine-byte header with its method dispatch, and the run escape**.
  *Eternal Sonata* is a resumable state machine producing one byte per call and
  dispatching on an internal mode field.

And the bytes agree: 872 bytes of the *Vesperia* decoder score **17** against
it, which is what they score against an unrelated tri-Ace title, while the two
executables share 304 contiguous bytes elsewhere.

**Nothing this document has published depends on the constant alone.** The
1997↔2000 identity is 212 bytes of object code; the 2004 fork is 17 bytes
against 276 of shared runtime; the 2005 *Abyss* descent is 69 bytes and 31
identical words in 200. Those results stand. What has to change is the
shortcut's advertised strength:

1. **A `4078` hit means an LZSS is present**, not that *this* LZSS is present.
   On a large Microsoft Visual C++ binary the constant returns two to seven
   hits by itself, scattered across unrelated routines — four Xbox 360 control
   executables returned 7, 5, 2 and 4.
2. **What identifies the format is the fingerprint cluster**, which is what
   step 3 has always said to look at and which is now the load-bearing step
   rather than the confirming one: the refill, the twelve-bit mask and the
   high-nibble extract inside one window, plus the preload and the header.
3. **The absence of 4078 is still a strong negative** and that half is
   untouched. An executable with no 4078, 4079, 4070 or 4071 anywhere does not
   contain this decoder, and that is how *Venus & Braves*, the 2004 I/O
   processor images and *Ratatosk no Kishi* were ruled out.

In short the scan is a *filter*, not a test, and it always was; six builds went
by without a target that made the difference visible.

### When the executable is encrypted

Step zero has now been needed on three platforms and the failure mode is the
same each time: a constant scan over a module that is not plaintext returns
zero and is indistinguishable from a clean negative.

| Platform | What is in the way | How to tell |
|---|---|---|
| Nintendo DS | `BLZ`, the linker's backwards LZ, on `arm9.bin` and every overlay | the overlay table, the module parameters, and the `BLZ` footer, checked independently |
| Wii | nothing — partitions are AES but `WIA`/`RVZ` hand back plaintext | the partition should begin with its own game id and carry `0x5D1C9EA3` at `+0x18` |
| **Xbox 360** | **AES-128-CBC always, and LZX often** | the XEX header states both; the recovered image must begin `MZ` |

On the Xbox 360 the wrapper is `XEX2` and getting at the PE takes three steps:
recover the session key by decrypting the security info's key with the console
key (retail or the all-zero devkit one — try both and see which yields `MZ`);
decrypt from `pe_data_offset` with AES-128-CBC and a zero IV; then decompress.
The compression field distinguishes two schemes and only one of them is
compression: `normal` is hash-linked blocks of LZX, and `basic` is a run-length
description of the address space, a list of (data length, zero length) pairs.
*Tales of Vesperia* is retail-keyed and `basic`.

**And the recovered image is the *memory* image, which changes what an offset
means.** A file offset in it is an RVA, and a virtual address is that RVA plus
the image base. Two of this corpus's tools fell into that: `prefix_scan.py`
mapped a `0x82…` address past the end of the file, produced an empty needle,
and printed a table of zeros that reads exactly like a real negative;
`common_run.py` read a PE's first bytes as a Nintendo `.dol` section table and
compared a few hundred bytes instead of four megabytes. Both now recognise a
flat PE. A tool that silently compares the wrong bytes is worse than one that
fails.

An AES implementation in the standard library there is not, on any of these
platforms, so it has to be carried: `xex.py` in the Xbox 360 pipeline has one,
and the console key is not a secret — it is in every emulator, because it has
to be.

### The structural probe is calibrated on a compiler, not on a machine

`struct_probe.py` was written against the 2003 GameCube build and lists the
fingerprints as that build spells them. One of them is spelled differently by a
different compiler on the same instruction set, and the fourteenth build is
where that was found:

```
Metrowerks   ori r0,  r0,  0xFF00      the refill, in place
MSVC         ori r31, r11, 0xFF00      a separate destination
```

A probe that requires `rA == rS` scores **zero refills on a build that plainly
contains two**, which is a false negative on a true positive — the worst thing
a probe of this kind can do. Both spellings are now counted separately and both
feed the co-occurrence pass. The fingerprint is the constant and the operation;
the register allocation is the compiler's.

The general form of this is worth stating because it will recur: **a structural
probe is calibrated against one toolchain's idiom, and a new toolchain is a new
calibration.** Run it against a known positive built with the *same* compiler
before believing a zero, and if there is no such positive, say so.

**On ARM there is no such positive anywhere in this corpus**, and the fifteenth
build is where that had to be written down rather than worked around. Three DS
cartridges have now been probed and none of them contains the format, so every
ARM zero this document quotes rests on a probe that has never been shown to
find a real one. Two things are worth doing instead of nothing, and *Tales of
Hearts* does both:

* **do not require `rd == rn`** on the refill, which is the Xbox 360 lesson
  applied before it is needed rather than after;
* **self-test the detectors**: hand-assemble every fingerprint in every form
  the probe looks for and check that each one fires. Seven of seven do on the
  ARM probe.

That demonstrates the detectors work. It does **not** demonstrate that an ARM
compiler would spell a real decoder the way they expect, and the report has to
print that sentence above the numbers rather than after them.

### The byte test's noise floor is a property of the platform

This document quotes a noise floor of six to eight bytes for `prefix_scan.py`,
measured on MIPS executables of one to four megabytes. On Xbox 360 PowerPC,
between unrelated executables of eight to thirteen megabytes, it is **sixteen
to seventeen**:

| 872 bytes of the *Vesperia* decoder against | Run |
|---|---:|
| *Eternal Sonata* — unrelated | **17** |
| *Infinite Undiscovery* — unrelated | **17** |
| *Star Ocean: The Last Hope* — unrelated | 16 |
| *Resonance of Fate* — unrelated | 11 |
| the same image's own `.rdata` + `.pdata` | 5 |

Two of the "controls" score within one byte of each other, and in the other
direction the winning run against two different files lands at the *same offset
in the needle*, which is what a generic instruction pattern does. Quote a byte
result against the floor measured on that platform with images of that size,
not against the corpus's default.

### And the toolchain can make the strong test unavailable

The whole-image control of the section above — *was byte equality available at
all?* — has always come back yes, and the fourteenth build is the first where
it comes back no.

| Pair | Same ISA | Same compiler | Longest shared run, controls subtracted |
|---|---|---|---:|
| GameCube 2003 ↔ Wii 2008 | yes | yes, Metrowerks | **835 bytes** (`OSSaveFPUContext`) |
| **GameCube 2003 ↔ Xbox 360 2008** | **yes** | **no** — Metrowerks vs MSVC | **28 bytes** |
| Xbox 360 2008 ↔ *Eternal Sonata* 2007 | yes | yes, MSVC | **304 bytes** |

Twenty-eight bytes, eleven distinct byte values, and the run is a
`li rD, N ; b` jump-table stanza. A ten-byte decoder result quoted against that
ceiling is not evidence of anything, and the honest report says so rather than
reporting the ten. **When the control fails, the directed measurement has no
denominator and must not be quoted as one** — the descent has to be argued from
the constants and the structure instead, or left open.

### Descending a container that has a field mask

Section 7 already says a tool written for a flat file system fails silently on
a nested one, in the direction of a clean-looking negative. The fourteenth
build adds a sharper version: **a tool written for one entry layout fails
silently on another layout of the same container.**

The `FPS4` archive on that disc states an entry size *and a field mask*, and
the mask says which of four per-entry fields are present, stored in bit order.
Two masks occur on one disc:

```
0x000F   offset, padded size, exact size, name    every .svo
0x008D   offset, exact size, name                 lib_data/syspack.dat
```

A reader that assumes the first reads the second's name as its size, reports
members of 1,398,362,964 bytes inside a 10,292-byte file, raises no error, and
would have had that archive counted as 40,760,677% full. Read the mask.

**And a mask with no size field in it does not mean the sizes are missing.**
The fifteenth build carries the same container on a different machine and adds
a third mask:

```
0x0003   offset, padded size                     8-byte entries
0x0001   offset only                             4-byte entries
```

On `0x0001` each member runs from its own offset to the next entry's, and the
last entry is a terminator whose offset is the archive's length -- the same
convention `0x000F` uses for its final entry. A reader that requires an
explicit size finds **no members at all** and reports the archive as
unreadable: on *Tales of Hearts* that was **1,904 nested archives** before the
reader learned the implicit form. The Xbox 360 trap reads a missing field as a
present one and fails towards absurd sizes, which is loud; this one reads a
present field as missing and fails towards *fewer payloads*, which on a census
is a clean-looking zero. The second is the more dangerous of the two.

**The container may also be split across two files, and then the offsets are
not into the file you are holding.** Seventeen archives on those cartridges are
an index whose entries point into a separate payload file beside it -- `m.b`
carries 1,521 entries and no payload, `m.dat` is 65 MB and has no directory --
and the same split recurs *inside*, where a member named `X.B` indexes its
sibling `X.MAPBIN`. Do not infer the pairing from the naming: try each
candidate and keep the one for which **every** entry lands inside it, so the
archive verifies the pairing rather than the reader assuming it. 422 pairs at
the file level and 405 inside, on one cartridge.

The same disc is also the corpus's deepest nest — XDVDFS file, `FPS4`, nested
`FPS4`, and the nine-byte block *whose plaintext is another `FPS4`* — and the
descent has to run all four or the census reports 162 payloads on a disc with
11,063 members. Where the container's members are themselves compressed and
decompressing all of them does not finish in a session, sweep them **through
the container's own chunk table** rather than as one blob, and say how many
were descended into and how many were not.

### When the target is a virtual machine, the constant scan does not run

The `4078` scan assumes a machine whose constants live in immediate fields
inside fixed-width instruction words. That assumption held across MIPS and
PowerPC, bent on ARM in the way the previous section describes, and fails
completely on a JVM target — for a reason worth naming, because the *Tales*
line reached Java in 2004 and again in 2020.

On the JVM an integer constant reaches the code three different ways, and a
byte scan sees at most one of them:

| Delivery | Encoding | Found by a raw scan for 4078? |
|---|---|---|
| `CONSTANT_Integer` in the constant pool, loaded by `ldc` / `ldc_w` | a 5-byte pool entry at an arbitrary file offset | only by accident |
| `sipush` | opcode `0x11` + **signed 16-bit** operand — 4,078 fits | only by accident |
| `bipush` | opcode `0x10` + **signed 8-bit** — 4,078 does **not** fit | never |
| computed, e.g. `sipush 4096; bipush 18; isub` | the constant never exists | never |

And bytecode is not scannable in the first place: it is unaligned, `tableswitch`
pads to a four-byte boundary, and the constant pool interleaves `Utf8` payloads
with everything else, so any fixed pattern matches by chance.

**So on a Java target the scan has to become a parse.** The variant that works:

1. **Parse the class file properly** — constant pool, fields, methods,
   attributes — and walk each method's `Code` with a full opcode length table
   so operands can be read. A parser in the Python standard library is about
   400 lines and needs no decompiler, which keeps the numbers reproducible:
   [`classfile.py`](https://github.com/vs-sr-dev/keitai-talesoftactics-doc/blob/main/tools/classfile.py).
2. **Look for 4078 and 4079 in all three delivery paths at once** — pool
   integers, `sipush` operands, `ldc` targets — and report the *denominator*.
   "Zero hits" means nothing without "out of how many constants".
3. **Then stop relying on the constant, because it can be computed.** Look for
   the structures instead, which a compiler cannot rewrite away: a
   **4,096-element array allocation**, the control-register refill `x | 0xFF00`,
   the ring mask `x & 0x0FFF`, `>> 4` adjacent to `& 0x0F`, and the run escape's
   `+3` and `+19`. These are the same fingerprints section 3 describes; only
   their encoding changes.
4. **Investigate every near-miss rather than dismissing it.** On *Tales of
   Tactics* the scan returned two `sipush 4096` and two `sipush 274` — both
   codec constants — and both were innocent: a 4 KB stream read buffer and a
   drawing coordinate. A negative is only worth quoting if the positives inside
   it were read.
5. **Then run the reference decoder blind anyway**, over every payload: the
   archive as shipped, every member inflated, every nested container, and every
   member of those. It costs nothing and it is the only test that does not
   depend on having guessed the right fingerprint.
   [`blind_decode.py`](https://github.com/vs-sr-dev/keitai-talesoftactics-doc/blob/main/tools/blind_decode.py).

The same reasoning applies to any bytecode target, and the analogous first
question for a non-console build is always **which decompressor the platform
already provides** — because that is what a small team will use. On DoJa it is
`com.nttdocomo.util.JarInflater`; on the GBA it was the BIOS `LZ77UnComp`.
Finding the platform's own decompressor called by name is faster than proving
a custom one absent, and it usually settles the question first.

**But "linked" is not "called", and the difference is one measurement.** On the
Nintendo DS the SDK links a table of `svc #N ; bx lr` wrappers into every
build, decompression services included, whether or not anything uses them —
so their presence says only that the library was linked. Resolve every branch
in the image and count the callers of each wrapper. On *Tales of the Tempest*
that is 21,462 distinct branch targets in the ARM9 and 3,785 in the ARM7, with
**zero** callers for all twelve decompression wrappers and one for `CpuSet`,
seven for `Stop/Sleep` — so the instrument is shown to find callers where there
are callers. The answer to "which decompressor does the platform provide" can
be "six, and it calls none of them".

### Control with a sibling build, not only with the runtime

The C-runtime control above works between two builds of one program. Off the
console there may be no shared runtime to compare — but there is usually a
sibling. Running the identical probes over other titles from the same publisher
on the same platform turns "this build does not use the format" into "this
platform line does not use the format", which is a much stronger statement and
costs one extra command. On *Tales of Tactics* three sibling i-appli were
measured this way; the negative held across all four, and two of the three
turned out to be obfuscated where the documented title is not, which also rules
out the tooling as an explanation.

**And when there is no sibling, say so and stop there.** *Tales of the Tempest*
(Nintendo DS, 2006) changed the machine and the team in one step and no second
DS image was available to run the identical probes over. Its zero is therefore
compatible with the boundary being the platform *or* the team, and neither
reading is available from that cartridge alone. A negative with two variables
in it is still worth publishing — with the two variables named in the same
sentence as the number.

### Comparing two builds: search the whole file, and control with the runtime

Two refinements, both learned in 2004 and both cheap.

**Search the whole executable, not a window.** Aligning two known addresses and
comparing them — what `decoder_diff.py` and `decoder_lineage.py` do — answers a
narrower question than it looks like. It cannot tell "recompiled and moved" from
"not present", and it cannot find a shared prefix that ended up inside some other
routine. Take *N* bytes of A and find the longest run of them appearing
**anywhere** in B, at any alignment, without being told where to look. A rolling
hash with a binary search on the length does this on a four-megabyte executable
in under a second. The instrument is validated by the control this document
already has: handed only 1997's decoder address and the whole of 2000's
executable, it must return **212**, and it does.
[`prefix_scan.py`](https://github.com/vs-sr-dev/ps2-talesofrebirth-doc/blob/main/tools/prefix_scan.py).

**Control with the C runtime, not with a random routine.** A negative byte
result is worth much more if you can show byte equality was available at all.
Take a needle *of the same length* from the two builds' shared C library —
`memset`, `strlen`, the SIMD string routines — and run the identical
measurement. If the runtime matches for hundreds of bytes and the decoder
matches for tens, the toolchain is excluded by measurement rather than by
argument. This is the test that turned the 2004 result from "part toolchain,
part edit" into "the source had forked": 276 and 288 bytes of runtime against 17
of decoder, between the same pairs of files.

Do this *before* reaching for `.comment`. A compiler string is a good
explanation when it is present, but it is absent in three of the four
PlayStation-family executables here, and the runtime control works regardless.

### The negative control has to be the same instruction set

The whole-file byte comparison of the previous section rests on a number that
says what "not present" scores. Since 2003 that number has come from
`VENUS.ELF` — a PlayStation 2 executable this document has demonstrated
contains no decoder at all — and it has been quoted as 14, 18 and 20 bytes
against needles from four different builds.

**It cannot be quoted against a needle that is not MIPS.** Run a PowerPC
routine against `VENUS.ELF` and the answer measures how much two unrelated
instruction sets happen to share at the byte level, which is a fact about
encodings and not about the routine. The thirteenth build had to build its own,
and the pattern generalises:

* **two unrelated titles on the same machine**, from publishers with no
  connection to this line. *Tales of Symphonia: Ratatosk no Kishi* used *The
  Last Story* (Wii, 2011) and *Final Fantasy Crystal Chronicles: The Crystal
  Bearers* (Wii, 2009), which scored **12** and **10** bytes against the 2003
  GameCube decoder;
* **and something from the target image itself that provably has no decoder** —
  there, the disc's own apploader, which is Nintendo's code and scored **7**.

Three controls, one of them from inside the image being examined, and the build
under test scored 10. Quote a byte result only against controls in the same
instruction set, and say which they are.

### Finding the runtime control when you do not know where it is

The C-runtime control of the previous section assumes you can name a routine
both builds link — `memset`, `strlen`, the SIMD string code. That worked on
four PlayStation 2 titles because they share a stamped compiler and an obvious
library. It does not work when the two builds are five years and one console
apart and nothing in either names a library routine.

**Take the longest identical run between the two whole images instead**, and
subtract what a stranger also has. The instrument is the same rolling hash with
a binary search on the length, run with the whole of A as the needle; the
subtraction is one extra argument. Between the 2003 GameCube and 2008 Wii
builds of *Symphonia*:

| | Longest identical run |
|---|---:|
| plain | **1,275 bytes** — and worthless |
| excluding one unrelated Wii title | **835 bytes** |
| excluding two | **835 bytes** |

The plain answer is worthless in a way that is worth spelling out, because it
would have been quoted: the 1,275 bytes are Nintendo's boot and exception code,
22 distinct byte values in 1,275, present in every Wii and GameCube executable
ever built. The 835 bytes that survive the subtraction are
`OSSaveFPUContext`, 106 distinct byte values, one object file compiled twice
five years apart to identical bytes.

Two refinements come with it. **Compare executable sections only** — a data
section's long runs of zeros and shared SDK tables are not evidence about a
compiler, and they win the search every time. And **print the byte histogram of
the winning run**, so a run that is all one value is visible as such instead of
being quoted as a result.
[`common_run.py`](https://github.com/vs-sr-dev/wii-talesofsymphoniadotnw-doc/blob/main/tools/common_run.py),
which also enumerates *every* shared region above a length rather than only the
longest — 96 regions and 12,143 bytes on that pair, none of them touching
either decoder copy, which confirms the directed result by a tool that was
never told where to look.

### On a four-gigabyte medium the denominators invert

Every count in this document has been quoted against a chance rate, and on a
cartridge the rate is small enough that the practice can look like a formality.
On a DVD it is the whole reading.

A four-byte needle occurs by chance about once per 4 GB of uniform data. On
*Tales of Innocence*'s 128 MB cartridge that is **0.031** expected hits, so a
single hit is worth locating and a zero is strong. On a 4.29 GB Wii partition it
is **1.00**, so a single hit means nothing and **a zero is weak**. The same
number carries opposite weight on the two media and the number does not say so.

Two consequences, both of which cost real work on the thirteenth build:

* **read the hits, always, because the uniform model is wrong about text.**
  That build's sweep returned `tor_` — *Tales of Rebirth*'s project tag, which
  on the *Abyss* disc prefixed 109 leftover sound effects — **3,865 times**
  against a chance rate of 1.00. Every one of the 3,865 is inside the word
  `vector_`. The model underestimates because names are not uniform, and only
  reading them tells you which kind of hit you have.
* **and a blind decode over billions of bytes will produce survivors.** The
  filter needs a method byte of 1 or 3, sizes in range, and a stream decoding to
  exactly its declared length — and over 4.29 GB of structured binary that
  happens. Ten did on that disc, all seventeen to 260 packed bytes, all isolated,
  all decoded and read, all ordinary data. Real blocks come in families: 487 in
  twenty-two files in 2003, 47,513 on *Abyss*. **Report the survivors, read
  them, and say why they are not a population** — a census that reports "0" on a
  medium where "0" is not the expected noise floor is hiding a step.

### When the container hands you the plaintext

A Wii partition is AES-128-CBC with a SHA-1 hash block interleaved every
0x8000 bytes, keyed from a title key the ticket carries encrypted. Reading its
file system out of an `.iso` means implementing AES, which no pipeline here has
a dependency for.

It was not needed, and the reason is a property of the *container* rather than
of the disc: **WIA and RVZ store Wii partition data decrypted and hash-free**,
rebuilding both on output — 0x7C00 of plaintext per sector, with one partition
entry naming the sector range and the group range. The file system is easier to
reach from the compressed container than from the image it expands to.

That is a claim about a format, so check it on the file in hand before building
on it: the plaintext each partition hands back should begin with its own
six-character game id and carry `0x5D1C9EA3` at `+0x18`. If it does, nothing is
being read through a cipher.

Two traps came with it and both fail silently:

* **a raw-data entry aligns down to a Wii sector, 0x8000, not to the
  container's chunk.** A reader that aligns to the chunk places the first
  partition's ticket over the partition table, and the disc then appears to have
  no partitions at all.
* **a partition group's data begins with exception lists**, one per 2 MiB
  sub-chunk and at least one, each a `u16` count followed by that many
  `(u16, SHA-1)` records — and the block is padded to four bytes when the group
  is stored uncompressed and not when it is compressed. Skip the wrong number of
  bytes and every offset in the partition is wrong by two.

[`wiirvz.py`](https://github.com/vs-sr-dev/wii-talesofsymphoniadotnw-doc/blob/main/tools/wiirvz.py).
And a Wii FST is a GameCube FST with the DOL offset, the FST offset and every
*file* offset divided by four; lengths and directory records are not shifted.
Getting that wrong produces a file system whose every entry points at plausible
rubbish a quarter of the way into the partition, with no error anywhere.

### Sweeping a movie is not sweeping a disc

Section 7 already says to sweep per member rather than per image, because
`plausible()` bounds a candidate by the buffer it sits in. On a 128 MB
cartridge that is a speed argument. On a 4.29 GB partition holding a
495,249,696-byte video file it is the difference between finishing and not:
taken as one buffer that movie sweeps at 156 KB/s and its declared packed sizes
reach 16 MB, so each attempt decodes megabytes before failing.

**Descend into the media container too.** A Nintendo `THP` states its frame
count and its first frame's size, and every frame states the next one's, so the
walk is four lines and turns five movies into 36,677 payloads of about 50 KB.
The same applies to any container whose members are individually seekable —
and the rule that decides it is not "is this an archive" but "is the
plausibility bound doing any work inside this buffer".

Where a payload genuinely cannot be split — a compressed stream in an
unidentified format, or a gap — sweep it in **overlapping windows** and say so:
the thirteenth build used 8 MiB windows with 4 MiB of overlap and named every
payload it did that to, because a block longer than the overlap could fall
across a seam. The largest block anywhere in this corpus is 3,864,151 packed
bytes, which fits.

### What a build says about itself is not what a build linked

On a Nintendo DS the `[SDK+VENDOR:COMPONENT]` strings are the cheapest thing to
read and this document has treated them as the licence list. They are not.

*Tales of Hearts* carries **two** tags — `[SDK+NINTENDO:BACKUP]` and
`[SDK+Actimagine:Mobiclip SDK V1.0.2]` — and **eight CRI components** that name
and version and date themselves in the same ARM9 (`ADXT/NITRO Ver.10.62`,
`AHX/NITRO Ver.1.85`, `NITROCI`, `MFCI`, `ADXNITRO`, `ADXCS`, `NITRORNA`,
`CRI CRW:STD`), a CRI file-system layer whose functions are `nitroCiOpen` and
`nitroCiReqRd`, CRI's entire error-message table, and `(c)CRI` **8,912 times**
across the cartridge. Not one `[SDK+CRI:…]`. *Tales of Innocence* licensed nine
CRI components and tagged them; this build licensed eight and tagged none.

So the tag list says what a build *tagged*. Quote it as that, and then read the
version strings, which are in the modules and are therefore behind `BLZ` --
which is why this is a section 7 item and not a footnote: on that cartridge the
shipped image shows **two fragments of one string** where the plaintext shows
**nine stamps**.

### `__DATE__` has two shapes and a pattern that wants one finds neither

The C preprocessor writes `Mmm dd yyyy` and pads the day with a *space* only
when it is a single digit:

```
Jan  1 2008        two spaces
Nov 19 2008        one space
```

This corpus's date scanner required two, so it matched the first shape and
missed the second. On *Tales of Hearts* that is the difference between zero
compiler dates and one, and the one — `Nov 19 2008`, four bytes from the
project tag in a debug overlay's version banner — is the only date either
cartridge carries about itself.

The general form is the one section 7 keeps rediscovering: **a pattern that
fails silently returns the answer a clean negative returns.** The check is to
run the scanner over something known to contain the thing, and on a DS target
the middleware supplies it for free -- CRI stamps `Build: Aug 26 2008 16:33:56`
into the ARM9 and any date scanner that cannot see that is broken.

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
  unchanged, and **the nine-byte header is still little-endian**. And the
  strongest test of all has now been run: *Tales of Rebirth* (2004) is the first
  title here whose decoder demonstrably does **not** descend from the same source
  file as its neighbour's, and it still produces **2,851 of 2,851** blocks the
  unmodified reference decoder reads. A fork of the code did not fork the format.
  Two dialects, seven builds, four consoles, both byte orders, nine years, and
  the split is still 1995/1997. The eighth build tested, *Tales of Tactics*
  (i-appli, 2004), is the first that does not contain the format at all — and it
  could not have, being a Java application — so it adds no dialect and removes
  no doubt. The ninth, *Tales of Legendia* (PlayStation 2, 2005), is the first
  that changes the **envelope** — sixteen bytes and no method byte, so the
  dispatch this document describes has nowhere to live — while leaving the token
  stream inside it bit-identical in dialect: same nibble order, same `+3`, same
  ring, 4,508 of 4,508 members read by the unmodified reference decoder. It
  drops the run escape entirely, which is a *narrowing* of the dialect rather
  than a third one, and it drops the synthetic preload, which is the first
  change to the dictionary since 1997. The tenth, *Tales of the Abyss*
  (PlayStation 2, 2005), reverses every one of those changes four months later:
  the nine-byte header is back with methods 0/1/3 used directly, the ring is on
  the stack again, both preload loops are written, the run escape is there with
  its `+19`, and **47,513 of 47,513 blocks decode** — 1,069,278,379 packed to
  2,643,327,828 unpacked. The eleventh, *Tales of the Tempest* (Nintendo DS,
  2006), adds no dialect because it adds no codec: zero `4078` and zero `4079`
  in either of the two encodings ARM has for them, on both processors, and
  **zero blocks in 256,548,562 bytes** under the unmodified reference decoder
  against a control that returns 1,089 in the same run. The twelfth, *Tales of
  Innocence* (Nintendo DS, 2007), adds no dialect either and for the same
  reason, but it is the first build opened as a **control** rather than as a
  title: zero 4078 / 4079 / 4070 / 4071 / 4080 in either ARM encoding across
  five modules, 78,489 ARM immediates, 140,305 THUMB literals and 554,020
  aligned words, and **0 blocks in 23,083 payloads and 657,419,133 bytes** under
  the same unmodified decoder, against the same 1,089-block control. The
  thirteenth, *Tales of Symphonia: Ratatosk no Kishi* (Wii, 2008), adds none
  either, and it is the first build to add none while being **from the line
  itself**: zero 4078 / 4079 / 4070 / 4071 over 637,871 PowerPC instruction
  words, on a machine that encodes all of them in one instruction and on which
  the 2003 prequel spells six of each; and **0 genuine blocks in 54,022
  payloads and 4,286,322,608 bytes** — the largest medium this corpus has swept
  — against the same 1,089. The fourteenth, *Tales of Vesperia* (Xbox 360,
  7 August 2008), is the first build in six that adds no dialect because it
  **has** the format rather than because it lacks it: two 4078 and two 4079 in
  one pair of routines out of **3,989,504** PowerPC instruction words, both
  synthetic preload loops, the `| 0xFF00` refill, the `& 0x0FFF` mask, the run
  escape with its `+19`, the nine-byte header with methods 0/1/3 used directly
  and **its sizes still assembled little-endian on a big-endian machine**, and
  **8,255 of 8,255 blocks** decoding to their declared length under the same
  unmodified decoder — 337,852,435 packed into 775,930,739. It is also the
  first build compiled by a third toolchain, Microsoft Visual C++, and the
  nibble order did not move there either. The fifteenth, *Tales of Hearts*
  (Nintendo DS, 18 December 2008), adds none and is the **third** cartridge on
  that machine to add none: zero 4078 / 4079 / 4070 / 4071 in either ARM
  encoding across **201,427** ARM data-processing immediates, **106,319** THUMB
  literals, **713,016** aligned words and **27,133** distinct PC-relative load
  targets over thirty-three modules **thirty-two of which had to be
  decompressed first**, and **0 blocks in 47,195 payloads and 376,083,362
  bytes** under the same unmodified decoder against the same 1,089-block
  control — on each of the **two cartridges** that shipped that day, which are
  one build and 28,662 byte-identical payloads of 28,679. Two dialects, fifteen
  builds, eight platforms, both byte orders, three compilers, thirteen years,
  and the split is still 1995/1997.
  What is left to test is the 2005 PSP port of *Eternia*, the 2006 PlayStation 2
  remake of *Destiny*, *Radiant Mythology* (PSP, 2006) — and, now that the far
  edge of the 2005-to-2008 interval is closed from inside, the 2009 PlayStation
  3 port of *Vesperia*, which is the next place the codec could stop.
* **~~Was the source ever edited after 1997?~~** *Answered, and then
  re-answered.* The first answer was "yes, once, in 2004". *Tales of Rebirth*,
  three months after *Symphonia*'s PlayStation 2 port and on the same R5900,
  shares **17 bytes** with it — while 932 bytes of the two builds' shared C
  runtime, measured identically, match for **276**. Byte equality was available
  and demonstrated; the decoder did not take it. Rebirth clears the dictionary a
  third way again — a library `memset` with **4,079**, from a factored
  `ring_init` neither other build has — and contains no `4080` anywhere. So the
  answer is not that the source was edited once. It is that **by 2004 there was
  no longer one copy of the source**: three PlayStation 2 builds in thirty
  months, three dictionary clears, three constants, one unchanged on-disc format.
  Section 6. The original 2004 statement follows, unaltered, because it is still
  the correct reading of that pair on its own:

* **~~Was the 2004 Symphonia build edited?~~** *Answered, yes.* Every build
  from 1997 to 2003 clears the dictionary with an inline
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
  in any shipped image beyond its output — and until the fourteenth build it was
  the **only** thing in this lineage that provably did not fork. *Tales of
  Vesperia* (Xbox 360, 2008) withdraws that: its `MSCF` envelope is gone, its
  `5b 80 80 8d` signature is gone, and its assets sit in an `FPS4` container
  instead — six weeks after the Wii build that still had both. So the packer
  varies and the format does not, which is the same shape as the decoders and
  not the exception this document had recorded. The fifteenth build adds the
  other half of that: five months after *Vesperia*, on a Nintendo DS, the
  **container** `FPS4` is there with the same header and the same field-mask
  semantics and the machine's byte order, and the codec is not. So of the three
  things this document tracks — the codec, the packer's envelope, and the
  container — each has now been observed crossing a generation without the
  others. Three habits are new on that
  disc and all three are the packer's: the ceiling moved again, to
  **9,070,491 packed producing 21,050,368** against *Legendia*'s 3,864,151;
  the stored path is down to **one method-0 block in 8,255**; and **one block
  expanded**, which had been zero in populations up to 47,513. Its run-escape
  setting is 6,864 method 3 against 1,390 method 1 — 83.2%, between *Rebirth*'s
  93.5% and *Abyss*'s inverted split. The decoders diverged per title by
  2004 and the format did not move a bit, so something was still normalising the
  output across titles that no longer shared decoder source. Four corpora now show its habits —
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
  The 2004 *Rebirth* disc adds three more. **The stored path is gone entirely**:
  zero method-0 blocks in 2,851, against 21 in 2002 and 969 in 2000, and the
  smallest block on the disc is **59 packed bytes and method 1** — the packer now
  compresses payloads the 2000 version would have stored. **Nothing expanded**:
  zero of 2,851 have packed ≥ unpacked. And **the thirty-fold ceiling held**: the
  largest block is **1,015,400 packed bytes**, next to the GameCube's 1,007,213,
  so whatever lifted the ~30 KB limit between 2002 and 2003 was not a GameCube
  decision and had not reverted eighteen months later on another console. The
  per-archive run-escape setting is per-archive there too, and sharply: 93.5%
  method 3 among top-level members against 58.1% inside `SCPK` bundles, on one
  disc from one packer run.
  The 2005 *Legendia* disc adds the largest change yet, and it is a change to
  the packer's *input contract* rather than to its output. **The synthetic
  preload is gone**: that build's `ring_init` clears 4,078 bytes and writes no
  `(i, 0x00)` / `(i, 0xFF)` pairs, so the packer cannot have emitted a single
  reference into the region section 4 measured Eternia reading 1,039,128 times.
  Both ends changed together, which is one more thing the packer and the
  decoders still agreed about after the decoders stopped sharing code.
  It also **restores the stored path in bulk** — 3,353 raw members, 614.5 MB,
  after *Rebirth* had zero in 2,851 — and it does so categorically rather than
  by size: every one of the 2,957 data members in that disc's battle archive is
  stored, on a disc whose map data compresses to 58.7%. **Nothing expands**, in
  4,508 members, which now holds across every disc examined. The smallest block
  is 56 packed bytes producing 128; the largest is **3,864,151 packed producing
  6,162,880**, nearly four times the 2003 and 2004 ceilings, so whatever lifted
  the ~30 KB limit between 2002 and 2003 has kept lifting.
  The 2005 *Tales of the Abyss* disc undoes Legendia's change to the input
  contract and keeps everything else. **The preload is back in the decoder and
  the packer uses it**: decoding 120 sampled members twice, once with the ring as
  published and once cleared to zeros, changes the output of **105** of them and
  the *length* of **none** — which is section 7's own warning demonstrated rather
  than quoted. **The stored path is gone again**: zero method-0 blocks in
  **47,513**, after Legendia's 3,353 raw members, and the smallest block on the
  disc is 173 packed bytes producing 256, in method 1. **Nothing expands**, in
  47,513. And the per-container run-escape setting is sharper here than anywhere:
  **all 46,345 blocks inside a header-less run are method 1** and 1,155 of the
  1,168 standalone members are method 3, with thirteen exceptions — the same
  shape as the six blocks out of 14,200 that went the other way on the 2000 disc.
  The ceiling came down a little: 2,307,879 packed and 5,115,328 unpacked, under
  Legendia's but still eighty times the 2002 limit.
* **Where is the boundary of the format?** *Narrowed from outside the console
  line, then complicated from inside it.* The boundary was already known not to
  be the company (*Venus & Braves*), the console (both PlayStation 2 games on one
  disc) or the series name (*Berseria*). *Tales of Tactics* appeared to settle
  it: a *Tales* title, same publisher, **built the day Rebirth was released**,
  with no trace of the format across 971,959 bytes and 6,286 integer constants,
  and whose own party table names the leads of the five titles that do contain
  it. The boundary was stated as **the console C codebase**, a boundary of
  *inheritance* rather than choice — a Java application on a phone had nothing
  to inherit.

  *Tales of Legendia* (2005) keeps that statement and takes the mechanism out of
  it. Here is a build that **did** inherit — same series, same console, same
  studio, eight months after *Rebirth* — and what it inherited was not code.
  Its decoder shares **21 bytes** with *Symphonia*'s and **20** with
  *Rebirth*'s, against **20** for an executable that contains no decoder at all,
  while 2,420 contiguous bytes of C runtime are identical between the same pair
  of files and both stamp the same compiler. It then wrapped the format in a
  container that had never existed before: sixteen bytes, no method byte, no run
  escape, no synthetic preload. And 4,508 of 4,508 members decode.

  So "inheritance" has to mean something weaker than it did. What crossed to
  this build was **the specification, not the file**: every constant, the nibble
  order, the `| 0xFF00` refill, the `RING − 18` cursor and the `+3`, reproduced
  exactly by someone who plainly did not have the source and did not keep the
  envelope. The boundary is still the *Tales* console codebase; what the corpus
  can no longer claim is that the codebase propagated the codec by copying code.
  For at least one build it propagated it as knowledge. Section 6.
  [ps2-talesoflegendia-doc](https://github.com/vs-sr-dev/ps2-talesoflegendia-doc),
  [keitai-talesoftactics-doc](https://github.com/vs-sr-dev/keitai-talesoftactics-doc).

  *Tales of the Abyss* (2005), four months and two days after Legendia, restores
  the clause Legendia removed — and it did so by being run as a three-way test with
  no preferred answer. 872 bytes of its decoder score **69** against *Symphonia*'s
  PlayStation 2 port, against **14** for the same `VENUS.ELF` control and **18**
  for Legendia, with **632** contiguous bytes of shared C runtime against both
  neighbours and `MW MIPS C Compiler (2.4.1.01)` stamped in all three files. It
  also puts the nine-byte header back, complete, with methods 0/1/3 used
  directly, the ring on the stack, both preload loops and the run escape — and
  47,513 of 47,513 blocks decode.

  And it descends from a specific one of the two copies *Symphonia* carries. The
  pair at `0x001C93D0`, the quadword `bzero` with **4080** that this document's
  2004 headline is about, scores **4 bytes**. The pair at `0x00242C5C`, which
  still clears the ring the 1997 way and still writes the preload, scores 69 —
  **31 identical words in 200**, diverging on register allocation and nothing
  else.

  So the boundary statement is now: the codebase carried **both**. A source file
  that kept being compiled — 1997 to 2005, through *Symphonia*'s second pair to
  *Abyss* — and a specification good enough that *Legendia* could re-implement it
  exactly without the file. Three edits of that source are on record and **none
  of them propagated**: *Symphonia*'s 4080, *Rebirth*'s 4079, *Legendia*'s state
  machine and `CPS` envelope. Legendia is not the mechanism; it is one fork of
  four, and the only one written from a description.
  [ps2-talesoftheabyss-doc](https://github.com/vs-sr-dev/ps2-talesoftheabyss-doc).

  *Tales of the Tempest* (Nintendo DS, 2006) is the first build to test that
  boundary against **a different team**, and on its own it cannot settle what it
  tests. The twelfth build settles half of it, and the half it settles is worth
  stating before the half it does not.

  **The platform is excluded.** *Tales of Innocence* (Nintendo DS, 2007) is the
  control Tempest's own open questions asked for and did not have: same
  publisher, same platform, same series, one year later, and a **third**
  developer — Alfa System — outside the Wolf Team / Namco Tales Studio line and
  unrelated to Tempest's. It returns the same zero on the codec, and a cleaner
  one: not a single 4078, 4079, 4070, 4071 **or 4080** in either ARM encoding
  across 78,489 ARM data-processing immediates, 140,305 THUMB instructions
  carrying a literal and 554,020 aligned words in five modules, where Tempest
  had six `4080` sites to disassemble. Its twelve BIOS decompression wrappers
  have zero callers over 40,411 resolved branch targets, across the module
  boundary as well as within it.

  And then it compresses. **102 files are BIOS `LZ77` streams, 16,901,069 bytes
  becoming 32,116,356**; two thirds of its data sits in **1,344 `EZBIND`
  archives** of its own design, named by its ARM9's own `cEzArchiveWrapper`; it
  licenses **nine CRI components** and Actimagine's **Mobiclip**; **51.40% of
  the cartridge is media** and **3.2% is unused**, against Tempest's 13.22% and
  41.3%. A *Tales* cartridge on this machine can have a full compression
  pipeline, and one does. So the reading that the Nintendo DS is where the codec
  stops is dead — not argued away, measured away — and Tempest's raw data is a
  fact about Tempest.

  **What survives is the codebase, and the corpus should say why it survives
  rather than treat it as a default.** Both DS developers are outside the line
  that carried the codec from 1995 to 2005, so the twelfth build changes the
  team a second time without ever bringing the *original* team onto this
  machine. Two zeros from two outsiders are consistent with the boundary being
  the codebase and equally consistent with the codebase simply never having
  shipped a DS title. Distinguishing those needs a Nintendo DS build **from**
  the studio line, and there is not one — which means the boundary statement now
  has a shape the corpus has not had before: it is limited by what was made, not
  by what was measured.

  **The thirteenth build closes it, and it closes it from the other side.**
  *Tales of Symphonia: Ratatosk no Kishi* (Wii, 26 June 2008) is the Nintendo
  title from inside the line that the paragraph above says does not exist. It is
  the **direct sequel** to the 2003 GameCube build — this corpus's only PowerPC
  positive, four copies of the decoder in `main.dol`, 487 of 487 blocks — on the
  **same processor family**, from the **same studio line**, five years later.

  It does not carry the codec. Zero `4078` / `4079` / `4070` / `4071` over
  637,871 PowerPC instruction words in every image on the disc, where the 2003
  build has twelve sites in four routines; zero `ori rX, rX, 0xFF00` refills
  where 2003 has fourteen; zero fingerprint clusters where 2003 has four, one
  per decoder copy; and **zero genuine blocks in 54,022 payloads and
  4,286,322,608 bytes**, both dialects, against the 1995 cartridge's 1,089 in
  the same run.

  And because both builds are Metrowerks PowerPC `.dol` files, **the strong test
  ran across a console generation for the first time in this corpus**: 872 bytes
  of the 2003 decoder score **10 bytes** in the 2008 executable — the same as
  *Crystal Bearers* and two less than *The Last Story*, neither of which has any
  connection to this line — while the same two executables share **835
  contiguous identical bytes** of `OSSaveFPUContext` that neither control image
  contains, and 12,143 bytes across 96 regions, **none of which touches either
  decoder copy**.

  So the sentence *"two zeros from two outsiders are equally consistent with the
  codebase never having shipped a Nintendo title"* is false, and it is false by
  measurement. **The codebase shipped two Nintendo titles**, in 2003 and 2008,
  and the first one carries the codec four times. The three zeros on Nintendo
  hardware are no longer one explanation short: the machine was excluded by the
  twelfth build and the alternative is excluded by the thirteenth.

  What replaces it is narrower, and it is about **time** rather than about
  platforms or teams. The codec's last confirmed appearance anywhere is *Tales
  of the Abyss*, 25 November 2005. Its first confirmed absence from the line
  itself is 26 June 2008. In that interval this studio line moved to a new
  console, a new SDK, C++ and Nintendo's middleware — and **kept its own
  container and its own compressor while dropping its own LZSS**. The `MSCF`
  envelope the 2003 discs wear is on 1,506 files here, and the compressed stream
  behind it carries `5b 80 80 8d` at offset `+8` in **2,051 of 2,051 payloads
  across both releases**, with the four bytes in front uniformly random. The
  packer crossed the generation; the decoder did not.

  The boundary is therefore still the *Tales* console codebase, and for the
  first time the corpus can say so without an alternative standing beside it.
  What it cannot say is when inside those thirty-one months the codec was
  dropped, or why a team that kept the container dropped the thing the container
  used to hold. Nothing in this corpus covers the interval; the 2005 PSP port of
  *Eternia*, the 2006 PlayStation 2 remake of *Destiny*, *Radiant Mythology*
  (PSP, 2006) and *Vesperia* (Xbox 360, 2008) all fall inside it.
  [wii-talesofsymphoniadotnw-doc](https://github.com/vs-sr-dev/wii-talesofsymphoniadotnw-doc).

  **The fourteenth build is the last of those four, and it removes the
  interval rather than narrowing it.** *Tales of Vesperia* (Xbox 360) has a
  volume timestamp of **2008-06-20** — six days before *Ratatosk* shipped — and
  a PE timestamp of 2008-06-19, and it carries the codec in the 1997 shape:
  inline ring clear bounded by 4078 and 4079, both synthetic preload loops,
  `ori rX, rY, 0xFF00`, `& 0x0FFF`, the nine-byte header with methods 0/1/3 used
  directly, the run escape with `+3` and `+19`, and **8,255 of 8,255 blocks**
  decoding to their declared length. The codec's last confirmed appearance is
  therefore no longer November 2005 but **June 2008**, and there is no interval
  left in which it might have been dropped, because it had not been dropped when
  the interval ended.

  So the paragraph above has to be restated, and the restatement is smaller in
  a useful way. It is not that *the line* dropped its LZSS somewhere in
  thirty-one months. It is that **two projects from one line, six days apart in
  mastering, made opposite decisions**: one shipped with no compressor of its
  own and none of the platform's, the other shipped with its own *and* the
  platform's, dispatched from a single entry point by one comparison on the
  first four bytes of a buffer. There was no line-wide event to date.

  And the two halves of the 2008 Wii finding come apart. That build kept the
  container and the compressor and dropped the LZSS; this one **kept the LZSS
  and dropped the container**. The `MSCF` envelope returns two hits here against
  a chance rate of 1.82 on a 7.84 GB medium, both located and both inside
  high-entropy payload, and `5b 80 80 8d` is nowhere. What the assets sit in
  instead is `FPS4`: big-endian, 4,126 archives, 11,063 members, a field mask
  selecting which of four per-entry fields exist, 32-byte names, and the
  packer's own Shift-JIS working directory left in the header. So the packer
  this document calls the only thing in the lineage that provably never forked
  is, on the evidence of these two discs, **the thing that varies**, and the
  codec is the thing that persists.

  What is still not answerable is why. The disc offers two observations and
  settles neither: the codec's payloads on it are overwhelmingly *nested `FPS4`
  archives* — 3,086 of 3,095 top-level block streams begin with the control byte
  `0xAF` and the literals `F P S 4` — so it is used for structure rather than
  for bulk, while XCompress takes 3.33 GB to 11.67 GB; and the shared entry
  point allocates its 4,272-byte frame, sized for the codec's ring, on the
  XCompress path too, so Microsoft's decompressor was grafted into a routine
  that already existed rather than the other way round.
  [xbox360-talesofvesperia-doc](https://github.com/vs-sr-dev/xbox360-talesofvesperia-doc).

  **The fifteenth build is the Nintendo DS title from the far end of that
  chain, and it narrows the statement without closing it.** *Tales of Hearts*
  shipped on 18 December 2008, five months after *Vesperia*'s executable was
  stamped, as **two cartridges on one day** — an Anime Movie Edition and a CG
  Movie Edition — and it carries the project tag **`TO9`**, which is the number
  after `TO7` (*Tales of the Abyss*, 2005) and `TO8` (*Tales of Vesperia*,
  2008). Both of those are line builds and both carry the codec.

  It does not. Zero of the four cursor constants in either ARM encoding over
  201,427 immediates, 106,319 THUMB literals, 713,016 aligned words and 27,133
  resolved load targets across thirty-three modules; all seven `4080` sites
  disassembled and innocent, four of them inside a 4,096-scaled cosine table
  whose 96 surrounding words match `round(4096 · cos θ)` to within one; zero
  fingerprint clusters; **0 blocks in 47,195 payloads and 376,083,362 bytes**,
  on each cartridge, against 1,089 in the same run.

  **And the two cartridges are an internal control the corpus has never had.**
  28,662 of 28,679 distinct payloads byte-identical, seventeen differences and
  every one of them the film or a structure that moves because of it. One build,
  two asset sets, and therefore one measurement stated twice rather than two
  measurements.

  What it changes about the boundary is not the platform and not the team. It is
  that **something else from the line crossed the same gap the codec did not**:
  the container. `FPS4` is on the *Vesperia* disc, big-endian, with a 0x1C
  header and a field mask selecting which of four per-entry fields exist; it is
  on these cartridges, little-endian, with the same header and the same mask
  semantics, five months later on a different processor family. The byte order
  is the machine's and the structure is the line's — the nine-byte block
  header's own behaviour, in reverse.

  So the shape at fifteen builds is: **the codec persists, the packer varies,
  and the container persists too.** Two of the three crossed from *Vesperia* to
  this cartridge and the codec is the one that did not, which is the opposite of
  what happened between the 2003 GameCube disc and the 2008 Wii disc, where the
  envelope and its compressor crossed and the codec did not. Both times exactly
  one of {codec, container} made the journey, and it was a different one each
  time.

  **What it cannot do is name the hands, and that has to be said in the same
  breath as the tag.** These cartridges name their developer **nowhere** — not
  in ASCII, not in Shift-JIS, not in UTF-16LE — and were compiled with RTTI off,
  so there are five C++ names in 2,852,064 bytes of plaintext and all five are
  the standard library's. The publisher is named once, in the banner. `TO9` is
  a number in the right place in a known sequence and nothing on the cartridge
  attaches a studio to it.

  So the sentence the twelfth build wrote — *narrowing this further needs a
  Nintendo DS title from that line, and there is not one* — is still not
  answered by a cartridge that says who made it. It is answered by a cartridge
  that carries the line's project number, and the corpus should record the
  difference rather than spend it. What would close it is a build from this line
  with RTTI left on, a text credits file, or any other title carrying `TO9`.
  [nds-talesofhearts-doc](https://github.com/vs-sr-dev/nds-talesofhearts-doc).

  One more thing the control supplies, and it is about instruments rather than
  about the format. Tempest named its developer nowhere — no company string, no
  `.comment`, no symbol table, one project tag surviving inside an unconverted
  3ds Max file. Innocence was built with RTTI left on and carries **1,047 C++
  class names**, among them a 43-class component framework called **`Mappy`** in
  which the platform is a *suffix* (`cMappyComponentDSStandardEntity`), and it
  ships its credits as plain Shift-JIS text naming twenty-nine people under
  `アルファ・システム　スタッフ`. The "outwards" direction that returned
  completely empty on one DS cartridge returns a framework, a container format
  and a staff list on the other. Whether a build names itself is a property of
  its build settings, not of its studio.
  [nds-talesofinnocence-doc](https://github.com/vs-sr-dev/nds-talesofinnocence-doc).

  The original Tempest paragraph follows, unaltered.

  *Tales of the Tempest* (Nintendo DS, 2006) is the first build to test that
  boundary against **a different team**, and it is the first that cannot settle
  what it tests. Every previous control held something fixed: *Venus & Braves*
  changed the team and kept the disc, the console and the year; *Tales of
  Tactics* changed the machine and the language and kept the publisher and the
  month; the Game Boy Advance rebuild changed the machine and kept the title.
  This one changes **the machine and the team together**, so its zero is
  compatible with the boundary being either. And no second Nintendo DS image
  was available to run the identical probes over — the sibling control that
  turned *Tales of Tactics* from "this build" into "this platform line" simply
  did not exist here.

  What it does add is a **new shape of negative** and a **new reason to doubt a
  clean-looking one**. The shape: this build did not replace the codec with the
  platform's decompressor, the way the 2003 Game Boy Advance rebuild did. It
  replaced it with nothing. The DS BIOS offers six decompression services and
  the SDK links wrappers for all of them into both processors; every branch in
  both images was resolved — 21,462 targets and 3,785 — and **not one wrapper
  has a caller**, while `CpuSet` has one and `Stop/Sleep` seven. Zero of 4,712
  files begins with a compressed stream, 91,303 candidate offsets inside them
  yield zero embedded `LZ77`, and the cartridge deflates to 52.6% with 41.3% of
  it unused. A build with room for a compressor, on a platform that supplies
  six for free, wrote and called neither.

  The reason to doubt: on ARM the two constants this document has scanned for
  since 2002 **cannot be encoded as immediates at all**, so a scan written for
  MIPS returns silence on a machine that might well contain them. Section 7
  carries the two-pass variant, and the moral is the one the JVM already taught
  in a different key — *the shortcut is about a machine, not about a format*.
  [nds-talesofthetempest-doc](https://github.com/vs-sr-dev/nds-talesofthetempest-doc).
* **Was the format ever ported to a virtual machine?** Not in the two
  Java-family builds examined. *Tales of Tactics* (i-appli, 2004) and *Tales of
  Crestoria* (Android, 2020) both use only the platform's own decompression. A
  decoder for this format in JVM bytecode would be perhaps sixty lines and a few
  hundred bytes, which the 2004 build — 10,298 bytes under its size cap — could
  plausibly have afforded; there is no evidence anyone considered it. What would
  settle it is a *Tales* keitai title that ships its own container rather than
  one-entry JARs, and none of the four examined does.
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
  *Tales of the Abyss* (2005) resolves half of that. Its decoder shares **4
  bytes** with the 1,104 + 768 pair and **69 bytes / 31 identical words in 200**
  with the 1,520 + 1,176 pair, so the two copies in `SLPS_254.00` are not merely
  different compilations of one file: one of them has descendants and the other
  does not. Which of the two the 2004 game actually *ran* is still unresolved,
  and neither is reachable from the other's dispatcher.
* **~~Why is the ring clear unrolled by eight on some builds?~~** *Answered: the
  compiler.* Four PlayStation 2 builds clear the ring with an inline loop and
  they split by `.comment` rather than by lineage. *Destiny 2* (2002), which
  carries no compiler string, writes one `sb` per iteration with the bound 4078.
  *Symphonia*'s second pair, *Legendia* and *Abyss* — all three stamping
  `MW MIPS C Compiler (2.4.1.01)` — write eight, so the bound is 4071 or 4070 and
  the 4078/4079 that section 7 scans for is the *cursor*, more than a hundred
  words further down. *Legendia* is the decisive row: it shares 18 bytes with
  *Abyss*'s decoder, which is this document's noise floor, and unrolls the same
  loop identically anyway. So 4070 and 4071 identify the toolchain, not the
  packer; 4078 and 4079 remain the only constants that identify the format.
  Section 7.
* **Where the decoder runs.** In 2002 it ran on both processors. In 2004
  *Symphonia*'s two I/O processor images contain no `4078` immediate at all:
  decompression moved entirely onto the main CPU while the I/O processor took up
  CRI's `ROFS` reader. Three months later *Rebirth* puts it back — five sites in
  `BOOT.IRX`, its single custom I/O processor module, and none in the stock Sony
  bundle — and that disc carries no CRI middleware at all. Two data points now,
  pointing the same way: where `ROFS` ran on the I/O processor the codec left it,
  and where the game read its own containers the codec stayed. Whether that is a
  decision about the codec or a consequence of the file system is still not
  answerable from the discs, but it is no longer a single observation. *Tales of
  the Abyss* (2005) is the third data point and it points the same way: it runs
  CRI's `ROFS`, and none of its five I/O processor images carries a 4078 or a
  4079 — the two `4080`s in `IRXARC.BIN` are a hardware register value stored
  beside a `4092` and a buffer size in an argument list, and both were
  disassembled. Three discs with `ROFS`, three with the codec on the main CPU
  only; two discs reading their own containers, two with a copy on the I/O
  processor.
* **Comparing across instruction sets.** The opcode-sequence method that
  carried the 2002 result works because R3000A and R5900 share a mnemonic
  vocabulary. Section 7 records the attempt to generalise it to PowerPC and its
  failure — the real pair scores no better than an unrelated routine. Something
  that survives a change of instruction set would be worth having; comparing
  basic-block structure, or the sequence of loop trip counts and constants
  rather than instructions, has not been tried.
