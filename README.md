# tales-blockcodec-doc

**The Tales block codec, documented once.** The in-house LZSS that Wolf Team
shipped on the Super Famicom in 1995, used again on the PlayStation in 1997,
still shipping in 2000 — by then not merely the same format but, for 212
bytes, literally the same machine code — still shipping in 2002 on the
PlayStation 2, on a disc that also proves it was never Namco's format at all,
and still shipping in 2003 on a **big-endian** console with its nine-byte
header unturned. In 2004 somebody finally edited it.

→ **[tales-block-codec.md](tales-block-codec.md)** — the specification
→ **[tales_block.py](tales_block.py)** — the reference decoder, both dialects
→ **[decoder_diff.py](decoder_diff.py)** — compare two builds' copies of the routine

For comparisons *across* instruction sets — where byte equality is impossible
by construction — the opcode-sequence tool lives in the PlayStation 2
pipeline, because it needs an ELF reader this repository has no other use for:
[`ps2-talesofdestiny2-doc/tools/decoder_lineage.py`](https://github.com/vs-sr-dev/ps2-talesofdestiny2-doc/blob/main/tools/decoder_lineage.py).
It works between R3000A and R5900, which share a mnemonic vocabulary. It does
**not** generalise to a genuinely different instruction set; the attempt and
its failure are recorded in section 7 and in
[`gc-talesofsymphonia-doc/tools/xarch.py`](https://github.com/vs-sr-dev/gc-talesofsymphonia-doc/blob/main/tools/xarch.py),
which prints its controls unconditionally so the failure is visible. The tool
that *does* generalise is the constant scan: `4078` and `4079` are the packer's,
and they survive PowerPC, where
[`ring_sites.py`](https://github.com/vs-sr-dev/gc-talesofsymphonia-doc/blob/main/tools/ring_sites.py)
finds them.

Each *Tales* title I document produces two things: a repository about that
build, and whatever it taught me about formats that are not specific to it.
The second kind of finding does not belong to any one title, and keeping a
copy of it in every pipeline is a recipe for copies that disagree. This
repository is the single copy. Pipelines link here rather than fork it.

This is documentation only. No ROM, no disc image, no extracted asset. The
decoder operates on an image you supply yourself.

---

## The result that made this worth splitting out

Two games, two years apart, two CPU architectures, and the same nine bytes:

| | Phantasia, Super Famicom 1995 | Destiny, PlayStation 1997 |
|---|---|---|
| Block header | `u8 method, u32 packed, u32 unpacked` | **identical** |
| Method: LZSS | `$81` | `1` |
| Method: LZSS + run | `$83` | `3` |
| Window | 4,096 bytes | 4,096 bytes |
| Control bits | LSB first, `1` = literal | **identical** |
| Match length | 3–18 | 3–18 |
| Short run | `n + 3`, range **4–18**, 2-byte token | **identical** |
| Long run | `b0 + 19`, range **19–274**, 3-byte token | **identical** |

`+3` and `+19` are the tell. On the Super Famicom they are an artefact of the
`MVN` block-move instruction, which transfers `A + 1` bytes and is used to
propagate a fill byte from `X` to `X+1` — so the register always holds two
less than the count. The PlayStation code has no `MVN`, writes its fill with
an ordinary store loop, and has no reason to be off by two. It is off by two
anyway.

A compressor written from scratch for MIPS in 1997 does not choose 19 as the
base of its long run length. It chooses 19 because the packer that produced
the data was the same packer.

## The result that carried it across a console generation

*Tales of Destiny 2*, PlayStation 2, 2002, decoded by the reference decoder
with **no PlayStation 2 branch added**: 9,469 blocks found, **9,469 exact**,
329 MB → 1,413 MB. Same header, same method bytes, same nibble order, same
3,840-byte preloaded ring, same `RING − 18` / `RING − 17` cursors.

The decoder could not be the same *object* this time — the Emotion Engine is
an R5900 — so the question became whether it was the same *source*. It is:

| Pair | Identical words | Longest identical run | Opcode sequence |
|---|---:|---:|---:|
| Destiny 1997 ↔ Eternia 2000 *(control)* | 69 / 140 | **53 words / 212 bytes** | **95.7%** |
| Destiny 1997 ↔ Destiny 2 2002 | 0 | 0 | 51.4% |
| Eternia 2000 ↔ Destiny 2 2002 | 0 | 0 | 49.3% |

Zero identical bytes, half the opcode sequence, and everything a compiler does
not get to choose held constant: the immediate `4078`, the ring in `a3`, the
256-iteration pattern fill unrolled by exactly eight. The control row
reproduces this repository's own 212-byte result by a different method, which
is what makes the zeros meaningful.
[`reports/ps2-lineage.txt`](reports/ps2-lineage.txt),
[`reports/ps2-census.txt`](reports/ps2-census.txt).

## The result that carried it across a byte order

*Tales of Symphonia*, GameCube, 2003. Every machine this format had touched was
little-endian; the Gekko is not. The GameCube also supplies its own
decompression and its own loader, which is the reading under which the 2003
Game Boy Advance rebuild of *Phantasia* had been allowed to drop the format.

`main.dol` carries the decoder **four times** — two routines, each linked twice,
byte for byte identical over 1,616 and 1,332 bytes — as PowerPC. `4078` and
`4079` appear as `subfic`, `cmpwi` and `addi` immediates, at the same three
offsets inside each routine. `ori r0, r0, 0xFF00`; the ring cursor masked with
`rlwinm r10, r10, 0, 20, 31`; the length in the low nibble of the second token
byte; the copy loop unrolled by exactly eight. **487 of 487 blocks on each of
the two discs decode to their declared lengths under `tales_block.py` with no
new dialect and no GameCube branch.**

And the field most likely to have produced a third dialect did not:

```
01 1e 21 00 00 e4 3c 00 00
   little-endian: method 1, packed 8478, unpacked 15588   <- decodes
   big-endian:    method 1, packed 505479168, unpacked 3829137408
```

The archive holding these blocks counts its members with a big-endian word four
bytes away. The header is still little-endian, because the decoder assembles
each size one `lbz` at a time and never had a reason to care — which section 1
of the specification said, three years of pipelines before anyone looked at a
GameCube.

## The result that finally broke the chain

*Tales of Symphonia*, PlayStation 2, 2004 — the same R5900 as *Tales of
Destiny 2* in 2002, so byte equality is available and is the strong test. It
returns nothing:

| Pair | CPUs | Identical words | Longest identical run, any alignment |
|---|---|---:|---:|
| Destiny 1997 ↔ Eternia 2000 | R3000A ↔ R3000A | 69 / 140 | **212 bytes** |
| **Destiny 2 2002 ↔ Symphonia 2004** | **R5900 ↔ R5900** | **1 / 180** | **6 bytes** |

Part of that is a change of compiler. The rest is not, because a compiler does
not change a constant. Every build from 1997 to 2003 clears the dictionary with
an inline byte loop bounded by **4,078**; the 2004 build calls a quadword
`bzero` with **4,080** — 4,078 rounded up to a multiple of sixteen so the
Emotion Engine's 128-bit `sq` can be used.

Seven years of "the same source, recompiled" end here. And the GameCube build a
year *earlier* still clears the dictionary the 2002 way, so it is 2004 that
departs, not 2003.

## The first direct measurement of the packer

The packer has never left anything in a shipped image but its output. In 2003
and 2004 it produced that output **twice from the same input**: eighteen
character-model files appear under the same names on the GameCube discs and in
the PlayStation 2 port, and the census reports identical block counts and
identical unpacked lengths for all eighteen.

| | blocks | packed | unpacked |
|---|---:|---:|---:|
| 2003, GameCube | 132 | 1,001,069 | 1,906,392 |
| 2004, PlayStation 2 | 132 | **1,025,520** | 1,906,392 |

Every one of the eighteen is **larger** in 2004, by +0.72% to +3.88%. None is
smaller; none is the same. The block boundaries did not move, so the
segmentation logic is untouched; the match search is not. In the same year
somebody edited the decoder.

## The result that showed whose format it was

The same 2002 disc carries a second, unrelated game — a promotional build of
Namco's *Venus & Braves*, which shipped eight months later. Across 933,840
instruction words its executable contains **no `4078` immediate at all**, and
its data is stored plain.

Two teams. One disc. One console. One year. One of them used the compressor.

Before this, the boundary was stated as "Wolf Team's own titles". It can now
be stated more sharply: the format belonged to the ***Tales* codebase**, not
to the company, not to the console, and not to the series name.

## The result that settled it

*Tales of Eternia*, three years after *Destiny*, does not merely use the same
format. It contains **the same compiled routine**:

| Routine | Eternia, 2000 | Destiny, 1997 | Identical prefix |
|---|---|---|---|
| method 1 | `0x80023504` | `0x80150BB0` | **53 words / 212 bytes** |
| method 3 | `0x80023690` | `0x80150D4C` | **50 words / 200 bytes** |

That prefix is the entire dictionary setup — the zero loop, both 256-iteration
pattern loops, `RING − 18` and `RING − 17` — and it contains no `lui`/`addiu`
address pairs, so nothing in it could differ merely because the code was linked
elsewhere. Identical bytes there are identical compiler output from identical
source. After the prologue the two builds diverge in register allocation only.

Section 8 of the specification used to ask whether a third dialect existed and
named *Eternia* as the title that would answer it. The answer is no.
[`reports/decoder-identity.txt`](reports/decoder-identity.txt).

What did change between 1995 and 1997, and it is the interesting half: the
PlayStation decoder builds a **4,096-byte ring preloaded with 3,840 bytes of
synthetic `(i, 0x00)` / `(i, 0xFF)` pairs** before it reads a single token — a
standing guess that the data will be 4bpp tile rows and `0xFF`-padded tables,
so that the packer can back-reference them for free. There is nothing like it
in the 1995 decoder.

And it is used — but not the way you would expect. Instrumenting all 20,085
compressed blocks on *Eternia*'s first disc, **72.9% of the packer's reads of
the untouched dictionary come from the plain zeroed tail below the cursor**,
from 36 distinct addresses; the two synthetic halves take 27% between them,
spread over 2,001 addresses. Every block reads the preload at least once, and
not one reads a byte the decoder never initialised. See section 4.

And the boundary is as informative as the match: the **2003 Game Boy Advance
rebuild of the same game does not use this format at all**, but the platform's
stock BIOS `LZ77UnComp`. The codec followed the codebase, not the series — as
the *Venus & Braves* result above makes sharper still.

---

## Verification

`tales_block.py` is one ring machine with a dialect switch. It was checked
against all four title pipelines' own decoders, which were written
independently and work differently — the Super Famicom one addresses the output
buffer, the PlayStation ones a ring — and on the 2002 PlayStation 2 disc it
*is* the decoder, used with no modification at all.

| Check | Result |
|---|---|
| 2002 PlayStation 2 corpus, unmodified reference decoder | **9,469 / 9,469** blocks exact, 329 MB → 1,413 MB, [`reports/ps2-census.txt`](reports/ps2-census.txt) |
| 2003 GameCube corpus, unmodified reference decoder, **big-endian machine** | **487 / 487** blocks exact on each of two discs, 79.7 MB → 143.4 MB, [`reports/gc-census.txt`](reports/gc-census.txt) |
| 2002 decoder against 2004, on one CPU | 1 identical word in 180, longest identical run **6 bytes** at any alignment, [`reports/gc-lineage.txt`](reports/gc-lineage.txt) |
| 2002 decoder against 1997 and 2000, instruction by instruction | 0 identical words, ~50% opcode sequence; control reproduces 212 bytes, [`reports/ps2-lineage.txt`](reports/ps2-lineage.txt) |
| Self-test, no image needed — the two dialects' run arithmetic | 4–18 and 19–274 **agree across dialects**, [`reports/selftest.txt`](reports/selftest.txt) |
| Exhaustive scan of the 6 MiB Super Famicom image | **1,089 blocks**, 115 `$81` + 974 `$83`, every one decoding to its declared length |
| Byte-for-byte against `top_lzss.py` | **1,089 / 1,089 identical** |
| Byte-for-byte against `tod_codec.py` | **397 / 397 identical** on a sampled sweep of the 1997 disc |
| Byte-for-byte against `ps1-talesofeternia-doc/tools/verify.py` | **20,085 / 20,085 identical** across the whole 2000 corpus |
| 1997 PlayStation corpus, decoder substituted | **6,638 / 6,638** blocks, byte totals unchanged |
| 2000 PlayStation corpus, decoder substituted | **21,054** blocks, 204.7 MB → 485.9 MB; 21,049 exact and five that overrun by one byte, enumerated |
| Preloaded-dictionary reads, 2000 corpus | 1,039,128 reads traced by ring address; **zero** at or above the cursor |

Reports: [`reports/ps2-census.txt`](reports/ps2-census.txt),
[`reports/ps2-lineage.txt`](reports/ps2-lineage.txt),
[`reports/census.txt`](reports/census.txt),
[`reports/cross-check.txt`](reports/cross-check.txt),
[`reports/decoder-identity.txt`](reports/decoder-identity.txt),
[`reports/selftest.txt`](reports/selftest.txt).

---

## Using it

```sh
python tales_block.py --selftest

# a single block, dialect detected from the method byte
python tales_block.py "Tales of Phantasia (Japan).sfc" 0x33BA66 -o spc.bin
python tales_block.py MC.D 0 -o mc.bin

# every block in an image
python tales_block.py "Tales of Phantasia (Japan).sfc" --scan --dialect snes

# is this build's decoder the same code as that build's?
python decoder_diff.py SLPS_030.50 0x80023504 SLPS_011.00 0x80150BB0
```

As a module:

```python
import tales_block
data = tales_block.unpack(buf, offset)                  # dialect sniffed
data = tales_block.unpack(buf, offset, tales_block.PSX) # or forced
hits = tales_block.scan(buf, tales_block.SNES)
```

Dependency-free Python 3, one file, no imports beyond `sys`.

---

## Titles it is drawn from

| Title | Platform | Year | Uses it | Pipeline |
|---|---|---|---|---|
| Tales of Phantasia | Super Famicom | 1995 | **yes**, `$81` / `$83` | [snes-talesofphantasia-doc](https://github.com/vs-sr-dev/snes-talesofphantasia-doc) |
| Tales of Destiny | PlayStation | 1997 | **yes**, methods 1 / 3 | [ps1-talesofdestiny-doc](https://github.com/vs-sr-dev/ps1-talesofdestiny-doc) |
| Tales of Eternia | PlayStation | 2000 | **yes**, methods 0 / 1 / 3 — same object code | [ps1-talesofeternia-doc](https://github.com/vs-sr-dev/ps1-talesofeternia-doc) |
| **Tales of Destiny 2** | **PlayStation 2** | **2002** | **yes**, methods 0 / 1 / 3 — same source, recompiled | [ps2-talesofdestiny2-doc](https://github.com/vs-sr-dev/ps2-talesofdestiny2-doc) |
| Venus & Braves | PlayStation 2 | 2003 | no — no decoder, on the *Destiny 2* disc | [ps2-talesofdestiny2-doc](https://github.com/vs-sr-dev/ps2-talesofdestiny2-doc) |
| **Tales of Symphonia** | **GameCube** | **2003** | **yes**, methods 1 / 3 — **on PowerPC**, header still little-endian | [gc-talesofsymphonia-doc](https://github.com/vs-sr-dev/gc-talesofsymphonia-doc) |
| **Tales of Symphonia** | **PlayStation 2** | **2004** | **yes** — same source, **edited** | [gc-talesofsymphonia-doc](https://github.com/vs-sr-dev/gc-talesofsymphonia-doc) |
| Tales of Phantasia | Game Boy Advance | 2003 | no — GBA BIOS `LZ77UnComp` | [snes-talesofphantasia-doc](https://github.com/vs-sr-dev/snes-talesofphantasia-doc) |
| Tales of Berseria | PC | 2017 | no — zlib inside the TL engine | [pc-talesofberseria-doc](https://github.com/vs-sr-dev/pc-talesofberseria-doc) |

Addresses, block counts and per-title verification live in those
repositories. This one holds only what is true of the format regardless of
which game you found it in.

Four titles is a lineage. Section 6 named the PlayStation 2 in advance as the
test that would either widen the boundary by a console generation or place the
break at 2000/2002. **It widened.** The codec crossed to the PlayStation 2
unchanged, and the same disc that proved it also supplied the negative control
that says whose format it was.

What is still untested is the 2005 PSP port of *Eternia* and the 2006
PlayStation 2 remake of *Destiny*. The remake is the interesting one: by then
the studio had been renamed, and if the codec is still in it, it outlived the
team's own identity.

---

## Licence

Documentation: [CC BY 4.0](LICENSE-DOCS). `tales_block.py`: [MIT](LICENSE).

*Tales of Phantasia*, *Tales of Destiny*, *Tales of Eternia*, *Tales of
Destiny 2* and *Venus & Braves* are trademarks of BANDAI NAMCO Entertainment.
This project is unaffiliated with and unendorsed by Bandai Namco, Namco Tales
Studio, Wolf Team, Nintendo or Sony Interactive Entertainment.
