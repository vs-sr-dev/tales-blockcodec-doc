# tales-blockcodec-doc

**The Tales block codec, documented once.** The in-house LZSS that Wolf Team
shipped on the Super Famicom in 1995, used again on the PlayStation in 1997,
still shipping in 2000 — by then not merely the same format but, for 212
bytes, literally the same machine code — still shipping in 2002 on the
PlayStation 2, on a disc that also proves it was never Namco's format at all,
and still shipping in 2003 on a **big-endian** console with its nine-byte
header unturned. By 2004 there was more than one copy of the source — and the
format still did not move. By 2005 there was a build with no copy of the source
at all, which had the algorithm to the constant and wrapped it in a header of
its own — and the format inside that header still did not move. Four months
later another 2005 build turned up **with** the source, recompiled from the one
copy of it nobody had edited, and put the nine-byte header back exactly as it
was in 1997. In 2006 a *Tales* game shipped on a Nintendo cartridge without it,
without the platform's own decompressor, and without any compressor at all —
on a medium two fifths of which it left empty. In 2007 a second one shipped on
the same machine, from another studio, without it and without the platform's
decompressor either — but with 16.9 MB compressed into 32.1 MB in the
platform's own `LZ77`, 1,344 archives of its own design, two middleware stacks
and 3.2% of the cartridge left empty. **The machine is not the boundary.** And
in 2008 the direct sequel to the 2003 GameCube build shipped on the Wii, from
inside the line that carried the codec, on the same processor family — without
it, and without anything of Nintendo's in its place, while wrapping 813 MB of
its assets in the *same envelope with the same compressor's signature* as its
prequel — which turned the boundary question into a date. Six weeks after that
disc was mastered, the same studio line shipped *Tales of Vesperia* on the Xbox
360 **with the codec**, in the 1997 shape, decoding **8,255 blocks of 8,255** —
beside 6,128 streams of Microsoft's own XCompress, dispatched from the same
entry point by one comparison on four bytes — and **without** the envelope or
the compressor signature its Wii sibling kept. Five months after that, *Tales
of Hearts* shipped on the Nintendo DS as **two cartridges on one day**, one
build with two sets of films, carrying the project number **after** *Vesperia*'s
— **without the codec**, and with *Vesperia*'s own container `FPS4`, header for
header and field mask for field mask, byte order turned round to suit the
machine. **The codebase is the boundary, there is no date, the thing that
varies is the packer — and the container travels on its own.** Eighteen months
after *Hearts*, *Tales of Graces* put the codec back on the Wii and settled
that the 2008 zero had been about one project rather than the machine, the
line or the compiler. And in 2011 *Tales of Xillia* shipped on the PlayStation
3 — the first build inside the gap between that disc and 2017, on the first
machine here with **two instruction sets in one executable** — carrying the
line's project number `TO11` as the root C++ namespace of the whole game, the
`TL` engine namespace with one class name identical to the 2009 build's, and
**no codec at all**: zero of the five constants over 3,685,471 PowerPC
instruction words *and* over eight embedded SPU modules, and **0 blocks in
213,683 payloads and 9,043,008,773 bytes**. What it compresses with instead is
**LZMA**, in a thirty-one-byte envelope of the studio's own, on 28,867 of
28,867 compressed members of a container with 151,862 of them. **Being inside
the codebase stopped predicting the answer.** That build also closed a claim
this corpus had carried at *Consistent* since 2009: seven of the nine `TL`
class names *Tales of Berseria* (2017) publishes are on the 2011 disc, its
container files are `FILEHEADER.TOFHDB` and `TLFILE.TLDAT` under those exact
names, and the project numbers run unbroken from `TO11` to `TO13` — so **the
engine is one codebase from the Wii in 2009 to the PC in 2017, and the engine
and the codec are separable.**

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
finds them. It does **not** survive a change of *machine*: on a JVM target
there are no wide immediate fields and a constant may be a `CONSTANT_Integer`,
a `sipush` operand, or computed and never present at all, so the scan has to
become a parse. Section 7 carries that variant, and the parser it needs is
[`classfile.py`](https://github.com/vs-sr-dev/keitai-talesoftactics-doc/blob/main/tools/classfile.py).

And it does not survive ARM unchanged either, for a reason that is pure
arithmetic: an ARM data-processing immediate is 8 bits rotated by an even
amount, so **4078 and 4079 cannot be encoded at all** and reach the code as
words in the literal pool, while **4080 can** (`0xFF ror #28`). On that one
machine the corpus's three constants split across two different searches, and a
single-pass scan's silence is not a negative. Section 7 carries the two-pass
variant and
[`ring_sites.py`](https://github.com/vs-sr-dev/nds-talesofthetempest-doc/blob/main/tools/ring_sites.py)
now covers MIPS, PowerPC and ARM/THUMB in one file.

The **SPU** splits them a third way, and the eighteenth build is where that had
to be written down. Its RI10 form — `ai`, `ahi`, `andi`, `ori`, `ceqi` — carries
a signed ten-bit field reaching only -512 to 511, so **none of the five fits**;
they reach `il` and `iohl` (16 bits) and `ila` (18). And `lqd`/`stqd` carry a
ten-bit displacement **scaled by sixteen**, which reaches **4080 and nothing
else of the five** — which matters, because 4080 is 4078 rounded up to a
multiple of sixteen, exactly the edit the 2004 PlayStation 2 build made for a
quadword store, and the SPU has nothing but quadword stores.
[`ring_sites.py --spu`](https://github.com/vs-sr-dev/ps3-talesofxillia-doc/blob/main/tools/ring_sites.py)
runs three passes and prints all three denominators, and it carries a
`--selftest` from its first day.

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

## The result that showed the source had forked

*Tales of Symphonia*'s 2004 PlayStation 2 port shares six bytes with the 2002
build on the same CPU, and this repository attributed part of that to a change
of compiler because there was no way to separate the two. *Tales of Rebirth*
separates them. Same studio, same R5900, **three months later** — Symphonia's
volume is stamped 2004-08-17 and Rebirth's 2004-11-17 — and the same
measurement run twice on the same pair of files, once on the decoder and once on
932 bytes of the C runtime taken from the same executable:

| Rebirth's 932-byte needle | vs Symphonia 2004 | vs Destiny 2 2002 |
|---|---:|---:|
| the **decoder** | **17 bytes** | 13 bytes |
| the **C runtime** | **276 bytes** | **288 bytes** |

All three PlayStation 2 titles link the same runtime objects byte for byte. Byte
equality was not merely possible, it is *demonstrated between exactly the files
whose decoders share nothing*. The toolchain is excluded by measurement.

And the constant agrees. 1997–2003 clear the dictionary with an inline byte loop
bounded by **4078**; Symphonia 2004 calls a bespoke quadword `bzero` with
**4080**; Rebirth 2004 calls the ordinary library `memset` with **4079**, from a
factored `ring_init` that neither of the others has — and **`4080` appears
nowhere in its executable**. Three builds in thirty months, three ways to clear
one array.

The format did not notice. **2,851 of 2,851** blocks on Rebirth's disc decode
under the unmodified reference decoder, at three levels of container nesting,
285 MB → 1,061 MB. A fork of the code did not fork the format — which makes the
packer, still invisible after nine years, the only thing in this lineage that
provably never forked.
[ps2-talesofrebirth-doc](https://github.com/vs-sr-dev/ps2-talesofrebirth-doc).

## The first direct measurement of the packer

The packer has never left anything in a shipped image but its output. In 2003
and 2004 it produced that output **twice from the same input**: nineteen
character-model files appear under the same names on the GameCube discs and in
the PlayStation 2 port, and the census reports identical block counts and
identical unpacked lengths for all nineteen.

| | blocks | packed | unpacked |
|---|---:|---:|---:|
| 2003, GameCube | 134 | 1,017,110 | 1,944,112 |
| 2004, PlayStation 2 | 134 | **1,042,397** | 1,944,112 |

Every one of the nineteen is **larger** in 2004, by +0.72% to +5.21%. None is
smaller; none is the same. The block boundaries did not move, so the
segmentation logic is untouched; the match search is not. In the same year
somebody edited the decoder.

## The result that separated the format from the code

*Tales of Legendia*, PlayStation 2, 2005 — eight months after *Rebirth*, same
studio, same R5900, so byte equality is available and is the strong test. It
returns the noise floor, and this time the noise floor is labelled:

| Legendia's 872-byte decoder against | Longest identical run |
|---|---:|
| Symphonia, PlayStation 2, 2004 | **21 bytes** |
| Rebirth, PlayStation 2, 2004 | **20 bytes** |
| **Venus & Braves, 2003 — *no decoder in it at all*** | **20 bytes** |

Against **2,420 contiguous identical bytes** of C runtime between Legendia and
Symphonia, both stamping `MW MIPS C Compiler (2.4.1.01)`. Same compiler, 2,420
bytes of agreement in the library, twenty-one in the decoder.

And it is the first build to change the *envelope*. Ten years of nine-byte
headers — `u8` method, `u32` packed, `u32` unpacked — become sixteen bytes with
**no method byte**, no run escape, and no synthetic dictionary preload. Inside
that envelope nothing moved: same ring, same mask, same `RING − 18` cursor, same
`| 0xFF00` refill, same nibble order, same `+3`. **4,508 of 4,508 members decode
under the unmodified reference decoder**, 1,176,881,049 → 2,098,653,952 bytes.

Somebody in 2005 had this format's specification exactly and did not have its
source, and the packer that fed them still produced a stream every earlier
decoder's algorithm reads. Which is the sharpest statement of the thing this
repository exists to record: the format and the code that implements it are
two different objects, and only one of them has ever been stable.
[ps2-talesoflegendia-doc](https://github.com/vs-sr-dev/ps2-talesoflegendia-doc).

## The result that put the code back

*Tales of the Abyss*, PlayStation 2, stamped 2005-11-25 — four months and two
days after Legendia, same studio, same R5900, same stamped compiler. It was
opened as a three-way test with no preferred answer, and it came back the way
the previous result made least likely.

| Abyss's 872-byte decoder against | Longest identical run |
|---|---:|
| **Symphonia, PlayStation 2, 2004** | **69 bytes** |
| Legendia, PlayStation 2, 2005 | 18 bytes |
| Rebirth, PlayStation 2, 2004 | 14 bytes |
| **Venus & Braves, 2003 — *no decoder in it at all*** | **14 bytes** |

with **632 contiguous identical bytes** of C runtime against Symphonia *and*
632 against Legendia, all three stamping `MW MIPS C Compiler (2.4.1.01)`. Byte
equality was equally available against both neighbours; one of them gave 69
bytes and the other gave the noise floor.

And the sharper half: `SLPS_254.00` carries this codec **four times**, in two
pairs that share 2 identical words in 276 with each other. Abyss scores **4
bytes** against the quadword-`bzero` pair with **4080** — the pair this
repository's 2004 headline is about — and **69 bytes, 31 identical words in
200** against the other one, the copy in the same file that still clears the
ring the 1997 way and still writes the synthetic preload. One of Symphonia's
two copies has descendants; the other does not.

The envelope reverted with it. Legendia's sixteen-byte `CPS` chunk is absent
from 4.36 GB (seven hits for `CPS ` / `CPS\0`, against a chance rate of about one
each, all seven located inside video and audio payload), and section 1 is back
complete: methods 0/1/3 used directly, a 4,096-byte ring rebuilt on the stack,
both preload loops, the run escape with its `+19`. **47,513 of 47,513 blocks
decode** under the unmodified reference decoder, 1,069,278,379 → 2,643,327,828.

So the codebase was carrying two things at once — a source file that kept being
compiled, and a specification good enough to re-implement from. Three edits of
that file are on record and none of them propagated.
[ps2-talesoftheabyss-doc](https://github.com/vs-sr-dev/ps2-talesoftheabyss-doc).

## The result that had room for the format and used nothing at all

*Tales of the Tempest*, Nintendo DS, 2006 — the eleventh build, the sixth
platform, and the first that is not a console C build by the studio line that
carried the codec. It was opened expecting one of three answers and gave a
fourth. (The twelfth build, *Tales of Innocence*, is its control and is
described further down; it gave a fifth.)

The scan had to be rebuilt before it could be run. An ARM data-processing
immediate is an 8-bit value rotated right by an even amount, so:

| Constant | Encodable as an ARM immediate |
|---|---|
| 4070, 4071, **4078**, **4079** | **no** — literal-pool words only |
| **4080** | **yes** — `0xFF ror #28` |

The two cursors this repository has scanned for since 2002 are unrepresentable
on this machine. With both passes run — immediate fields, and literal-pool
words cross-referenced against every PC-relative load — the answer is a zero
with denominators under it:

| | ARM9 | ARM7 |
|---|---:|---:|
| ARM data-processing immediates | 85,036 | 11,969 |
| THUMB instructions carrying a literal | 53,575 | 4,034 |
| 4-byte-aligned words | 387,310 | 41,384 |
| **4078 / 4079 / 4070 / 4071, either form** | **0** | **0** |

All six `4080` sites were disassembled. **Four are entries of a 4,096-scaled
cosine table** compiled as 446 constant-returning stubs behind a computed
branch, in which `round(4096 · cos 5°) = 4080`. And the reference decoder, run
blind over **9,055 payloads and 256,548,562 bytes** in both dialects, returns
**zero blocks** where its control on the 1995 cartridge returns 1,089 in the
same invocation.

What replaced it is the interesting half. The 2003 Game Boy Advance rebuild
said the platform's own decompression takes the format's place; this build says
nothing does.

| | |
|---|---|
| BIOS decompression wrappers linked | 6 on each processor |
| **Call sites for any of them** | **0**, out of 21,462 + 3,785 resolved branch targets |
| Files beginning with a BIOS-format stream | **0 of 4,712** |
| Embedded `LZ77` streams found in 91,303 candidate offsets | **0** |
| The whole cartridge through `deflate` | **52.6%** — palettes 9.3%, bitmaps 16.1% |
| Cartridge unused | **41.3%** — 52.8 MB of `0x00`, then exactly 2.5 MiB of `0xFF` |

A build with room for a compressor, on a platform that supplies six of them for
free, wrote and called neither. That is a third kind of negative: not a codec
replaced, and not a codebase with nothing to inherit.

And it is the first result here that **cannot settle what it tests**. Every
previous control held something fixed — *Venus & Braves* changed the team and
kept the disc; *Tales of Tactics* changed the machine and kept the publisher
and the month. This one changes the machine and the team together, and no
second Nintendo DS image was available to run the identical probes over. Its
zero is compatible with the boundary being the platform or the team, and the
cartridge does not even name its own developer.
[nds-talesofthetempest-doc](https://github.com/vs-sr-dev/nds-talesofthetempest-doc).

## The result that was opened to test another result

*Tales of Innocence*, Nintendo DS, 2007 — the twelfth build, and the first here
opened as a **control** rather than as a title. The eleventh changed the machine
and the developer in one step and could not say which of them its zero was
about; this one holds the publisher, the platform and the series fixed and
changes the developer again, to Alfa System, a third studio outside the line.
Four outcomes were possible and none was assumed.

**On the codec it agrees, and its zero is the cleaner of the two.** Five modules
— an ARM9, an ARM7 and three overlays, none compressed, checked from the overlay
flags, the module parameters and the `BLZ` footer independently:

| | total across five modules |
|---|---:|
| ARM data-processing immediates | 78,489 |
| THUMB instructions carrying a literal | 140,305 |
| 4-byte-aligned words | 554,020 |
| PC-relative loads resolved, to distinct targets | 27,469 → 22,262 |
| **4078 / 4079 / 4070 / 4071 / 4080, either encoding** | **0** |

Not one of the five constants anywhere, where Tempest had six `4080` sites to
disassemble. Zero `orr rX,rX,#0xFF00` refills, zero 4,096-byte stack rings, and
the ARM/THUMB trap fired again and was caught again — 22 THUMB `add #19` in one
overlay, all 22 ARM words read at even offsets. The unmodified reference decoder
finds **0 blocks in 23,083 payloads and 657,419,133 bytes**, both dialects, with
the 1995 cartridge's 1,089 printed in the same run. The twelve BIOS
decompression wrappers have **zero callers over 40,411 resolved branch
targets**, counted across the module boundary as well as within it, and no
wrapper address occurs as a data word.

**And then it compresses.**

| | *Tempest*, 2006 | *Innocence*, 2007 |
|---|---|---|
| files in a BIOS compression format | **0 of 4,712** | **106 of 6,378** — 102 `LZ77`, 16.9 MB → 32.1 MB |
| a container | none | **1,344 `EZBIND` archives, 9,646 members** |
| cartridge unused | 41.3% | **3.2%** |
| media share | 13.22% | **51.40%**, 2.81 hours of voice |
| middleware | Actimagine `VX` | Actimagine **Mobiclip**, plus nine **CRI** components |
| names its developer | nowhere | credits text, boot logo, 1,047 RTTI class names |

So a *Tales* cartridge on the Nintendo DS can have a full compression pipeline,
and one does — in a format the platform itself defines, which nothing on the
cartridge calls the platform to decode. **The machine is excluded as the
explanation for the eleventh build's zero.** What survives is the codebase, and
it survives with a caveat the corpus should state rather than assume: both DS
developers are outside the line that carried the codec, so two zeros from two
outsiders are as consistent with *the codebase never shipped a DS title* as with
*the boundary is the codebase*. Separating those needs a DS build from the line
itself, and there is not one.

Three things it added to the toolbox rather than to the argument: the first
cartridge here with **overlays**, so branch resolution had to cross a module
boundary; the first with a **container**, so every per-file pass had to learn to
descend or silently measure a fifth of the data; and the first with a **positive
control for the BIOS decompressors** — one animation shipped five times over,
once per format, beside the original, which found a wrong Huffman leaf mask, a
lost tree alignment and two mislabelled filter type bytes in tooling that had
never been checked.
[nds-talesofinnocence-doc](https://github.com/vs-sr-dev/nds-talesofinnocence-doc).

## The result that closed the boundary

*Tales of Symphonia: Ratatosk no Kishi*, Wii, 26 June 2008 — the thirteenth
build, the seventh platform, and the one the twelfth asked for by name. Its own
open questions said: two zeros from two studios outside the line are as
consistent with *the boundary is the codebase* as with *that codebase never
shipped a Nintendo title*, and separating them needs a Nintendo build **from**
the line, and there is not one.

There is one, and it is unusually well conditioned. It is the **direct sequel**
to the 2003 GameCube *Tales of Symphonia* — this repository's only PowerPC
positive, which carries the decoder four times and decodes 487 of 487 blocks —
on the **same processor family**, Gekko and Broadway both being PowerPC 750
derivatives, both builds Metrowerks, both executables Nintendo `.dol` files. So
for the first time here **the strong byte test runs across a change of
console**, and the question is not *is it the same source* but *is it the same
object*.

The codec is not there, and the scan that says so is a complete search on this
machine — PowerPC encodes all five constants directly, which is exactly how the
2003 build spells them:

| | Wii 2008 | GameCube 2003, the same scan |
|---|---:|---:|
| instruction words scanned, all images | **637,871** | 383,328 |
| relocatable modules to scan | **none exist** | eight |
| **4078 / 4079** | **0 / 0** | **6 / 6** |
| `ori rX, rX, 0xFF00` refills | **0** | **14** |
| fingerprint clusters | **0** | **4** — one per decoder copy |
| genuine blocks, both dialects, whole disc | **0** in 4,286,322,608 bytes | 487 of 487 |

and the byte test, with controls that had to be built because this repository's
standing one, `VENUS.ELF`, is MIPS and would have measured the architecture:

| 872 bytes of the 2003 decoder, whole-file, any alignment | Run |
|---|---:|
| GameCube 2003 — the instrument on itself | **872** |
| **Wii 2008** | **10 bytes** |
| *The Last Story*, Wii 2011 | 12 bytes |
| *FF Crystal Chronicles: The Crystal Bearers*, Wii 2009 | 10 bytes |
| the 2008 disc's own apploader | 7 bytes |

**Byte equality was available and is demonstrated.** The two executables share
**835 contiguous identical bytes** of `OSSaveFPUContext` that neither control
image contains, and 12,143 bytes across 96 regions of at least 64 bytes — none
of which touches either 2003 decoder copy. 835 bytes of library against 10 of
decoder is the 2004 measurement's shape, run across a console generation.

So *"the codebase never shipped a Nintendo title"* is false by measurement: it
shipped two, and the first carries the codec four times. **The boundary is the
*Tales* console codebase, and for the first time no alternative stands beside
it.**

**And the packer crossed where the decoder did not.** Both releases wrap their
compressed assets in a fake Microsoft Cabinet, and the compressed stream behind
that header carries `5b 80 80 8d` at offset `+8` in **545 of 545** payloads in
2003 and **1,506 of 1,506** in 2008, with the four bytes in front uniformly
random in both. Section 8 calls the packer the only thing in this lineage that
provably never forked; this is a third sighting, five years after the second,
and it says the studio kept its container and its compressor and dropped its own
LZSS somewhere in the thirty-one months after *Tales of the Abyss*.
[wii-talesofsymphoniadotnw-doc](https://github.com/vs-sr-dev/wii-talesofsymphoniadotnw-doc).

## The result that took the date away

*Tales of Vesperia*, Xbox 360, 7 August 2008 — the fourteenth build, the eighth
platform, and the first one **inside** the interval the thirteenth created. That
build had turned the boundary question into a date: last confirmed appearance
25 November 2005, first confirmed absence from the line 26 June 2008, nothing
in between.

This disc's volume is stamped **2008-06-20**, six days before *Ratatosk* shipped
and forty-eight before this game did. Its executable is stamped 2008-06-19. It
carries the codec.

The scan is a complete search on this machine and it had to be run on a
decrypted image, because an Xbox 360 executable is AES-128-CBC encrypted and a
constant scan over the shipped `.xex` returns zero and looks exactly like a
clean negative:

| | Wii 2008 | GameCube 2003 | **Xbox 360 2008** |
|---|---:|---:|---:|
| instruction words scanned | 637,871 | 383,328 | **3,989,504** |
| **4078 / 4079** | **0 / 0** | 6 / 6 | **2 / 2** |
| 4070 / 4071 / **4080** | 0 / 0 / 20 | 0 / 0 / 25 | 0 / 0 / **0** |
| sites, and where | — | 12 in four routines | **4 in two, at +5, +53, +103, +151** |
| blocks decoding to their declared length | **0** in 4.29 GB | 487 of 487 | **8,255 of 8,255** |

and it is the 1997 shape everywhere the shape can differ: inline ring clear
bounded by 4078 and 4079, **both** synthetic preload loops, `ori rX, rY,
0xFF00`, `rlwinm … 0, 20, 31`, the low-nibble length and the high-nibble
reference, the `+3`, the run escape with its `+19`, the ring rebuilt on the
stack, and the nine-byte header with methods **0, 1 and 3 used directly** whose
sizes are still assembled **little-endian on a big-endian machine** — for the
third time, and for the reason section 1 gave before anyone had opened a
GameCube.

**The strong test was architecturally available and practically was not, and
reporting that is the result.** Both builds are PowerPC, so `prefix_scan.py`
ran and 872 bytes of the 2003 decoder scored **10** here — the same as two
unrelated Xbox 360 titles. But the control this corpus insists on comes back
no:

| `common_run.py`, executable sections, controls subtracted | Longest identical run |
|---|---:|
| GameCube 2003 ↔ Wii 2008 — both Metrowerks | **835 bytes** |
| **GameCube 2003 ↔ Xbox 360 2008** — Metrowerks vs MSVC | **28 bytes** |
| **Xbox 360 2008 ↔ *Eternal Sonata* 2007** — both MSVC | **304 bytes** |
| the two decoders in that last pair, `prefix_scan.py` | **17 bytes** |

Twenty-eight bytes, eleven distinct byte values, a `li rD, N ; b` jump-table
stanza: nothing longer survives between those two toolchains anywhere, so the
ten is quoted against an unavailable test and says nothing. Run where the
control succeeds, the same instrument is decisive the other way — 304 bytes of
shared library against 17 of decoder is the 2004 measurement's shape, and it
settles that this decoder is shared with nothing on the platform.

**And the two halves of the Wii result come apart.** That build kept the
container and the compressor and dropped the LZSS. This one **kept the LZSS and
dropped the container**: `MSCF` returns two hits against a chance rate of 1.82
on a 7.84 GB medium, both located and both inside high-entropy payload, and
`5b 80 80 8d` is nowhere. The assets sit in `FPS4` instead — 4,126 archives,
11,063 members, a field mask selecting which of four per-entry fields exist,
and the packer's own Shift-JIS working directory (`../Release/共通/UI.svo`)
left in the header. So the packer this repository called *the only thing in the
lineage that provably never forked* is, on these two discs, the thing that
varies.

**The platform's own compressor is here too, and one routine dispatches both.**
6,128 bare XCompress streams — 3.33 GB expanding to 11.67 GB — beside the 7,859
codec blocks, and `0x820D5570` chooses with one `lwz` and one `cmplw` against
`0x0FF512EE`. Its 4,272-byte stack frame is sized for the codec's ring and is
allocated on the XCompress path too, which does not need one. 65 call sites out
of 23,150 resolved branch targets; `memcpy` has 870.

**Two corrections to section 7 came out of the controls rather than the
target.** The structural probe scored **zero refills on a build containing two**,
because Metrowerks writes `ori r0, r0, 0xFF00` and MSVC writes
`ori r31, r11, 0xFF00`; both spellings are now counted. And *Eternal Sonata*
(Xbox 360, 2007, tri-Crescendo, published by Namco Bandai), run as a negative
control, turned out to carry a 4,096-byte-ring LZSS with the cursor at **4078**,
the `+3` and the same nibble layout — because those are the canonical 1989 LZSS
reference implementation's constants, not this codebase's. It is not this
format: no synthetic preload, no `| 0xFF00` refill, no nine-byte header, no run
escape. The scan finds *an* LZSS; the fingerprint cluster identifies *which*.
[xbox360-talesofvesperia-doc](https://github.com/vs-sr-dev/xbox360-talesofvesperia-doc).

## The result that came with its own control

*Tales of Hearts*, Nintendo DS, 18 December 2008 — the fifteenth build, the
third cartridge on this machine, and the first to ship as **two cartridges on
one day**: an Anime Movie Edition and a CG Movie Edition.

That is a control this corpus has never had, and it is free. Running the
identical container descent over both images and comparing payload by payload,
**28,662 of 28,679 distinct payloads are byte-identical**. Seventeen differ and
every one of them is the film or a structure that moves because of it — the
nine movies, a fifty-byte build note in Shift-JIS saying which edition's assets
are in the tree, the ROM header, the banner, the file allocation table, two
alignment regions, the tail, and `arm9.bin`, whose plaintext differs only in
regenerated secure-area filler, **eight `BLX` offsets into it**, and one byte of
its own packed length. One build. Every measurement stated twice by identity.

**The codec is not there, and step zero is why that is worth saying.** This
document has put *decompress the modules first* at the head of the DS checklist
since 2006 with a standing note that it had never yet prevented a false
negative. **Thirty-two of these thirty-three modules are `BLZ`-packed** — the
ARM9 and all thirty-one overlays — 1,620,780 bytes becoming 2,852,064 bytes of
plaintext code. And the decompressor, never executed in two previous DS
pipelines because neither cartridge had a packed module, **was wrong twice**:
a match token's two bytes assembled in the wrong order, and a copy not clamped
to the end of the encoded region. Both fail in the direction of *this module is
not packed*. The repair has a control that was on the cartridge all along —
the overlay table states each overlay's plaintext length — and **31 of 31**
agree.

Over the plaintext:

| | ARM9 | ARM7 | 31 overlays | **total** |
|---|---:|---:|---:|---:|
| ARM data-processing immediates | 45,111 | 11,911 | 144,405 | **201,427** |
| THUMB instructions carrying a literal | 26,436 | 5,253 | 74,630 | **106,319** |
| 4-byte-aligned words | 186,366 | 39,882 | 486,768 | **713,016** |
| distinct PC-relative load targets | 7,175 | 1,800 | 18,158 | **27,133** |
| **4078 / 4079 / 4070 / 4071** | **0** | **0** | **0** | **0** |
| 4080, all seven disassembled | 3 imm + 4 words | 0 | 0 | 7 |

Four of the seven are entries of a 4,096-scaled cosine table — **96 of 96
surrounding aligned words** are `round(4096 · cos θ)` to within one, which is
*Tales of the Tempest*'s finding on a second cartridge in a different shape.
Zero fingerprint clusters. Zero genuine ARM `add #19` against 67 THUMB decodes
of ARM words, the third cartridge to show that trap. And **0 blocks in 47,195
payloads and 376,083,362 bytes** on each cartridge, against the 1995
cartridge's **1,089** in the same run.

**What crossed instead was the container.** `FPS4` is the archive on the
*Vesperia* disc, big-endian, with a 0x1C header and a field mask saying which of
four per-entry fields exist. It is here five months later on ARM,
**little-endian**, with the same header and the same mask semantics — 2,492
archives read against 2,493 magic hits. The byte order is the machine's and the
structure is the line's, which is the nine-byte block header's own behaviour in
reverse.

So of the three things this corpus tracks — the codec, the packer's envelope,
the container — each has now been seen crossing a console generation without the
others. Between 2003 and the 2008 Wii disc the envelope and its compressor
crossed and the codec did not; between *Vesperia* and these cartridges the
container crossed and the codec did not.

**And the platform's formats are here without the platform's code.** 5,280 BIOS
streams *inside the containers*, 61,737,814 bytes becoming 123,245,746 — against
**zero callers** of all six linked decompression wrappers over **43,946**
resolved branch targets, with `CpuSet` at one and `Stop/Sleep` at seven so the
instrument is shown to find callers where there are callers. At the file level
the figure is 11 of 5,145, and quoting that would have described a different
cartridge.

**What it cannot say is who built it.** The developer is named **nowhere**, in
ASCII, Shift-JIS or UTF-16LE, and the build was compiled with RTTI off — five
C++ names in 2,852,064 bytes and all five the standard library's. What it
carries is the tag **`TO9`**, in six file names, in a file extension of its own,
and in a debug overlay's version banner four bytes from the build date
`Nov 19 2008`. `TO7` is *Tales of the Abyss* and `TO8` is *Tales of Vesperia*.
That is a number in the right place in a known sequence, and no hand attached to
it. Section 8 records the difference rather than spending it.
[nds-talesofhearts-doc](https://github.com/vs-sr-dev/nds-talesofhearts-doc).

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

## The result that put a negative back in its place

The thirteenth build, *Tales of Symphonia: Ratatosk no Kishi* (Wii, 26 June
2008), was this corpus's strongest negative: the Nintendo title from inside
the studio line, on the same processor family as the only PowerPC positive,
and it carried nothing. Its zero was compatible with three readings — the
machine, the line, or that one project — and no build could separate them.

**The sixteenth build separates them.** *Tales of Graces* (Wii, 10 December
2009) is the same console, the same line and the same compiler, eighteen months
later, and it carries the codec twice: one `4078` and one `4079` over 1,205,688
PowerPC instruction words, the Metrowerks ring clear reaching 4,078 as
`509 x 8 + 6`, both synthetic preload loops, `ori r9, r7, 0xFF00`, the
twelve-bit mask, the high nibble placed by `rlwimi`, the run escape with its
`+19` in the second copy, and **1,318 blocks** decoding to their declared
length — all of them in the `psx` dialect and **1,162 of them decoding to an
`FPS4` archive**.

Both sides being Metrowerks PowerPC `.dol` files, the byte test has a
denominator. 872 bytes of the 2003 GameCube decoder score **138** in it against
**10** in *Ratatosk*, 12 and 10 in two unrelated Wii titles and 7 in its own
apploader — symmetric in both directions, floor 7 to 8 — and the whole-file
search that was never told where to look ranks the decoder **first through
eighth** of the 77 regions the two builds share.

So the machine is excluded, the line is excluded and the compiler is excluded.
The 2008 zero is a fact about the 2008 project.

Three other things move with it. The `MSCF` envelope that the 2003 and 2008
discs both wear returns **zero hits on 4.29 GB**. `FPS4` — which neither Wii
build's predecessor had — arrives, 4,832 archives, big-endian. And the build
**names its developer**, which no build of this line in this corpus had done:
`take_njd@namco-talesstudio.co.jp`, in the support block of a complete in-house
*Character Parts Editor* shipped on the retail disc.

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
| 2004 *Rebirth* corpus, unmodified reference decoder | **2,851 / 2,851** blocks exact across three nesting levels, 284.9 MB → 1,061.5 MB, [`reports/rebirth-lineage.txt`](reports/rebirth-lineage.txt) |
| 2002 decoder against 2004 *Symphonia*, on one CPU | 1 identical word in 180, longest identical run **6 bytes** at any alignment, [`reports/gc-lineage.txt`](reports/gc-lineage.txt) |
| 2004 *Rebirth* decoder against 2004 *Symphonia*, whole executables | **17 bytes**; the same-length C-runtime control from the same file scores **276**, [`reports/rebirth-lineage.txt`](reports/rebirth-lineage.txt) |
| 2005 *Legendia* corpus, unmodified reference decoder, **new sixteen-byte envelope** | **4,508 / 4,508** blocks exact, 1,176.9 MB → 2,098.7 MB, [ps2-talesoflegendia-doc](https://github.com/vs-sr-dev/ps2-talesoflegendia-doc) |
| 2005 *Legendia* decoder against its neighbours, on one CPU | **21 bytes** vs Symphonia; the no-decoder control *Venus & Braves* scores **20**, and the C-runtime control **2,420** |
| 2005 *Abyss* corpus, unmodified reference decoder, **nine-byte header restored** | **47,513 / 47,513** blocks exact, 1,069.3 MB → 2,643.3 MB, [ps2-talesoftheabyss-doc](https://github.com/vs-sr-dev/ps2-talesoftheabyss-doc) |
| 2005 *Abyss* decoder against its neighbours, on one CPU | **69 bytes** vs Symphonia's *unedited* pair and **4** vs its edited one; the no-decoder control scores **14**, *Legendia* **18**, and the C-runtime control **632** against both |
| 2006 *Tempest* corpus, unmodified reference decoder, **on ARM** | **0 blocks** in 9,055 payloads and 256,548,562 bytes, both dialects; the control in the same run returns **1,089** on the 1995 cartridge, [nds-talesofthetempest-doc](https://github.com/vs-sr-dev/nds-talesofthetempest-doc) |
| 2006 *Tempest* constant scan, both ARM encodings, both processors | **0** × 4078 / 4079 / 4070 / 4071 against 85,036 + 11,969 immediates and 387,310 + 41,384 words; all six 4080 sites read |
| 2007 *Innocence* constant scan, both ARM encodings, **five modules** | **0** × 4078 / 4079 / 4070 / 4071 **and 4080** against **78,489** ARM immediates, **140,305** THUMB literals, **554,020** aligned words and **27,469** resolved PC-relative loads, [nds-talesofinnocence-doc](https://github.com/vs-sr-dev/nds-talesofinnocence-doc) |
| 2007 *Innocence* corpus, unmodified reference decoder, **through its container** | **0 blocks** in **23,083 payloads and 657,419,133 bytes**, both dialects — every FAT file, every `EZBIND` member and every BIOS stream decompressed; the control in the same run returns **1,089** on the 1995 cartridge, [nds-talesofinnocence-doc](https://github.com/vs-sr-dev/nds-talesofinnocence-doc) |
| 2007 *Innocence* BIOS decompressors, against the cartridge's own five-format benchmark | **5 / 5** decode byte-for-byte to the original animation beside them — and finding that fixed a wrong Huffman leaf mask, a lost tree alignment, and both difference-filter type bytes |
| 2008 *Ratatosk no Kishi* constant scan, **PowerPC**, every image on the disc | **0** × 4078 / 4079 / 4070 / 4071 over **637,871** instruction words, on a machine that encodes all four in one instruction and where the 2003 prequel spells six of each; all twenty `4080` sites disassembled and read, [wii-talesofsymphoniadotnw-doc](https://github.com/vs-sr-dev/wii-talesofsymphoniadotnw-doc) |
| 2008 *Ratatosk no Kishi* corpus, unmodified reference decoder, **4.29 GB** | **0 genuine blocks** in **54,022 payloads and 4,286,322,608 bytes**, both dialects — every file, every `THP` frame, every `MSCF` payload, every `U8` node and every gap; the control in the same run returns **1,089**, and the ten chance survivors are enumerated and read |
| 2003 GameCube decoder against the 2008 Wii sequel, **one instruction set, two consoles** | **10 bytes**; two unrelated Wii titles score **10** and **12** and the disc's own apploader **7**, while the same two executables share **835** contiguous bytes of SDK code no control has |
| 2008 *Vesperia* constant scan, **PowerPC, MSVC, decrypted image** | **2** × 4078 and **2** × 4079 in one pair of routines out of **3,989,504** instruction words; **0** × 4070 / 4071 / 4080, [xbox360-talesofvesperia-doc](https://github.com/vs-sr-dev/xbox360-talesofvesperia-doc) |
| 2008 *Vesperia* corpus, unmodified reference decoder, **through four levels of container** | **8,255 / 8,255** blocks exact, 337,852,435 → 775,930,739, across XDVDFS files, `FPS4` archives, nested `FPS4` and block plaintexts; the control in the same tooling returns **1,089** |
| 2003 GameCube decoder against the 2008 Xbox 360 build, **one instruction set, two compilers** | **10 bytes** — and the whole-image control finds a ceiling of **28**, so the ten is quoted against an unavailable test and means nothing |
| 2008 *Vesperia* decoder against three unrelated Xbox 360 titles, **byte equality demonstrated** | **17 / 17 / 16** bytes, while *Vesperia* and *Eternal Sonata* share **304** contiguous bytes of code no tri-Ace title has |
| 2011 *Xillia* constant scan, **PowerPC, PS3 SDK compiler, decrypted SELF** | **0** x 4078 / 4070 / 4071 over **3,685,471** instruction words; four 4079 and eighteen 4080 sites all disassembled and all innocent, [ps3-talesofxillia-doc](https://github.com/vs-sr-dev/ps3-talesofxillia-doc) |
| 2011 *Xillia* constant scan, **SPU, eight embedded modules** | **0** x all five in every encoding that can hold them, against **4,400** RI16, **481** RI18, **7,935** quadword displacements and **218,352** aligned words -- the first second-instruction-set scan in this corpus |
| 2011 *Xillia* corpus, unmodified reference decoder, **9.04 GB** | **0 blocks** in **213,683 payloads and 9,043,008,773 bytes**, both dialects, `undescended` **0** -- every container member, every Bink frame and every gap; the control in the same session returns **1,089** |
| 2009 Wii decoder against the 2011 PlayStation 3 build, **two PowerPC word sizes** | **8 bytes**, against a same-file control of **20** -- and the whole-image ceiling is **96 bytes of six distinct values**, `li r3,0 ; blr` twelve times, so the test has no denominator and the eight is not quoted as evidence |
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
[`reports/rebirth-lineage.txt`](reports/rebirth-lineage.txt),
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
| **Tales of Rebirth** | **PlayStation 2** | **2004** | **yes**, methods 1 / 3 — a **different source**, on both CPUs | [ps2-talesofrebirth-doc](https://github.com/vs-sr-dev/ps2-talesofrebirth-doc) |
| **Tales of Tactics** | **i-appli (DoJa)** | **2004** | **no** — a Java application; deflate twice, both the platform's | [keitai-talesoftactics-doc](https://github.com/vs-sr-dev/keitai-talesoftactics-doc) |
| **Tales of Legendia** | **PlayStation 2** | **2005** | **yes** — the same engine from an **unrelated source**, in a **new envelope** | [ps2-talesoflegendia-doc](https://github.com/vs-sr-dev/ps2-talesoflegendia-doc) |
| **Tales of the Abyss** | **PlayStation 2** | **2005** | **yes**, methods 1 / 3 — the **1997 source again**, recompiled, nine-byte header back | [ps2-talesoftheabyss-doc](https://github.com/vs-sr-dev/ps2-talesoftheabyss-doc) |
| **Tales of the Tempest** | **Nintendo DS** | **2006** | **no** — and no other compressor either; the data is raw | [nds-talesofthetempest-doc](https://github.com/vs-sr-dev/nds-talesofthetempest-doc) |
| **Tales of Innocence** | **Nintendo DS** | **2007** | **no** — the **control**: another studio, same platform, and it compresses in the platform's own `LZ77` | [nds-talesofinnocence-doc](https://github.com/vs-sr-dev/nds-talesofinnocence-doc) |
| **Ratatosk no Kishi** | **Wii** | **2008** | **no** — the direct sequel to the 2003 build, **same ISA**, **from inside the line** | [wii-talesofsymphoniadotnw-doc](https://github.com/vs-sr-dev/wii-talesofsymphoniadotnw-doc) |
| **Tales of Vesperia** | **Xbox 360** | **2008** | **yes**, methods 0 / 1 / 3 — the **1997 shape**, on a third compiler, beside XCompress | [xbox360-talesofvesperia-doc](https://github.com/vs-sr-dev/xbox360-talesofvesperia-doc) |
| **Tales of Hearts** | **Nintendo DS** | **2008** | **no** — two cartridges, one build, five months after the build above; **`FPS4` crossed and the codec did not** | [nds-talesofhearts-doc](https://github.com/vs-sr-dev/nds-talesofhearts-doc) |
| **Tales of Graces** | **Wii** | **2009** | **yes**, methods 0 / 1 / 3 — the **1997 shape again**, on the machine the 2008 build dropped it on; 138 bytes shared with the 2003 decoder | [wii-talesofgraces-doc](https://github.com/vs-sr-dev/wii-talesofgraces-doc) |
| **Tales of Xillia** | **PlayStation 3** | **2011** | **no** — inside the 2009-2017 gap, on the first target here with **two instruction sets**; carries the `TL` engine and the tag `TO11`, and compresses with **LZMA** in an envelope of its own | [ps3-talesofxillia-doc](https://github.com/vs-sr-dev/ps3-talesofxillia-doc) |
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

Six titles later the question has inverted. It is no longer whether the format
survives a new machine — it has survived four, both byte orders and nine years —
but whether it survives the *code* being forked. *Tales of Rebirth* is the first
build that answers that, and it does: the decoder is demonstrably not the same
source as any neighbour's, and the format is bit-identical anyway.

And the eighth build asks the last version of the question: not whether the
format survives a new machine or a forked source, but where it stops. *Tales of
Tactics* is a *Tales* title built the day *Tales of Rebirth* was released, by
the same publisher, that names the leads of five titles which use the format —
and contains no trace of it across 971,959 bytes and 6,286 integer constants,
because it is a Java application and had nothing to inherit. The boundary is the
console C codebase, and it is a boundary of inheritance rather than of choice.
That build also forced the first real revision of the section 7 checklist: the
`4078` constant scan cannot run on a virtual machine at all, and section 7 now
carries the variant that can.

The ninth build changes what the question is. *Tales of Legendia* (2005) is
the first that has the format without having the code — 21 shared bytes against
2,420 of shared runtime, and a sixteen-byte envelope nobody had used before —
so the codec was propagating inside the studio as a specification, not as a
file. That is a weaker kind of inheritance than this repository had been
describing, and it is the kind that can outlive any particular team.

The tenth puts the other kind back. *Tales of the Abyss* (2005), four months and
two days after Legendia, restores the nine-byte header complete and shares
**69 bytes** with *Symphonia*'s PlayStation 2 port — against **14** for the
no-decoder control and **18** for Legendia, with **632** bytes of shared C
runtime against both neighbours. And it descends from a specific one of the two
unrelated copies *Symphonia* carries: **4 bytes** against the quadword-`bzero`
pair this repository built its 2004 headline on, **69** against the copy in the
same file that nobody edited. So the codebase was carrying both a source file
that kept being compiled and a specification good enough to re-implement from.
Three edits of that source are now on record and **none of them propagated**.

The eleventh asks the question the corpus had never been able to ask — does the
codec cross to a different *team*? — and cannot answer it, which is worth as
much as an answer would have been. *Tales of the Tempest* (Nintendo DS, 2006)
has no codec, no BIOS decompression and no compression of any kind, on a
cartridge 41.3% of which is empty. But it changed the machine and the team in
one step, and no second Nintendo DS image was available as a control, so its
zero fits either boundary. What it did settle is a tooling question: the
constant scan is about a machine, not about a format, and on ARM it had to
become two scans before it could say anything at all.

The twelfth is that control, and it is the first build here opened to test
another build rather than itself. *Tales of Innocence* (Nintendo DS, 2007) holds
the publisher, the platform and the series fixed and changes the developer
again — Alfa System, a third studio outside the line. It returns the same zero
on the codec, and a cleaner one: not a single 4078, 4079, 4070, 4071 **or 4080**
in either ARM encoding across five modules, 78,489 ARM immediates, 140,305 THUMB
literals and 554,020 aligned words. Its twelve BIOS decompression wrappers have
zero callers over 40,411 resolved branch targets.

And then it compresses — 102 files as BIOS `LZ77`, 16.9 MB becoming 32.1 MB;
1,344 archives of its own; CRI for audio and Actimagine's Mobiclip for video;
51.4% of the cartridge media and 3.2% of it empty. **So the Nintendo DS is not
where the codec stops**, and Tempest's raw data is a fact about Tempest. What
survives is the codebase, and the corpus now has to say why: both DS developers
are outside the line that carried the codec, so two zeros from two outsiders are
equally consistent with the boundary being the codebase and with the codebase
never having shipped a DS title at all. That distinction is limited by what was
made, not by what was measured.

The control also came with a benchmark nobody had before. Somebody at Alfa
System compressed one animation five different ways, kept every candidate and
the original, and shipped the lot — and running it found that this corpus's DS
Huffman decoder had a wrong leaf mask and a lost tree alignment, and that both
difference filters were one type byte low. Every DS census this corpus had
quoted was measured with instruments nothing had ever checked.

The thirteenth is the control the twelfth asked for, and it is not on the
Nintendo DS at all. *Tales of Symphonia: Ratatosk no Kishi* (Wii, 2008) is the
direct sequel to the 2003 GameCube build — same studio line, same PowerPC 750
family, a Nintendo console, five years later — and it carries no codec, on a
disc where the constant scan is a complete search and the strong byte test is
available for the first time across a console generation. **10 bytes of shared
decoder against 835 of shared SDK code**, with two unrelated Wii titles scoring
10 and 12. So the reading that the codebase had simply never shipped a Nintendo
title is dead, the boundary is the *Tales* console codebase with nothing
standing beside it, and the three Nintendo zeros are three separate facts rather
than one unexplained pattern.

What that build leaves is a **date** rather than a platform. The codec's last
confirmed appearance is *Tales of the Abyss*, 25 November 2005; its first
confirmed absence from the line is 26 June 2008. In between, the line kept its
own container and its own compressor — `5b 80 80 8d` sits at offset `+8` of
2,051 of 2,051 compressed payloads across the 2003 and 2008 discs — and stopped
carrying the LZSS the container used to hold. What is still untested is the 2005
PSP port of *Eternia*, the 2006 PlayStation 2 remake of *Destiny*, *Radiant
Mythology* (PSP, 2006) and *Vesperia* (Xbox 360, 2008): every one of them falls
inside those thirty-one months. The remake is the interesting one: by then the
studio had been renamed, and if the codec is still in it, it outlived the team's
own identity.

---

## Licence

Documentation: [CC BY 4.0](LICENSE-DOCS). `tales_block.py`: [MIT](LICENSE).

*Tales of Phantasia*, *Tales of Destiny*, *Tales of Eternia*, *Tales of
Destiny 2*, *Tales of Symphonia*, *Tales of Rebirth*, *Tales of Legendia*,
*Tales of the Abyss*, *Tales of the Tempest* and *Venus & Braves* are
trademarks of BANDAI NAMCO Entertainment.
This project is unaffiliated with and unendorsed by Bandai Namco, Namco Tales
Studio, Wolf Team, Nintendo or Sony Interactive Entertainment.
