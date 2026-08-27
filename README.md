# tales-blockcodec-doc

**The Tales block codec, documented once.** The in-house LZSS that Wolf Team
shipped on the Super Famicom in 1995, used again on the PlayStation in 1997,
and was still shipping in 2000 — by then not merely the same format but, for
212 bytes, literally the same machine code.

→ **[tales-block-codec.md](tales-block-codec.md)** — the specification
→ **[tales_block.py](tales_block.py)** — the reference decoder, both dialects
→ **[decoder_diff.py](decoder_diff.py)** — compare two builds' copies of the routine

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
stock BIOS `LZ77UnComp`. The codec followed the team, not the series.

---

## Verification

`tales_block.py` is one ring machine with a dialect switch. It was checked
against all three title pipelines' own decoders, which were written
independently and work differently — the Super Famicom one addresses the output
buffer, the PlayStation ones a ring.

| Check | Result |
|---|---|
| Self-test, no image needed — the two dialects' run arithmetic | 4–18 and 19–274 **agree across dialects**, [`reports/selftest.txt`](reports/selftest.txt) |
| Exhaustive scan of the 6 MiB Super Famicom image | **1,089 blocks**, 115 `$81` + 974 `$83`, every one decoding to its declared length |
| Byte-for-byte against `top_lzss.py` | **1,089 / 1,089 identical** |
| Byte-for-byte against `tod_codec.py` | **397 / 397 identical** on a sampled sweep of the 1997 disc |
| Byte-for-byte against `ps1-talesofeternia-doc/tools/verify.py` | **20,085 / 20,085 identical** across the whole 2000 corpus |
| 1997 PlayStation corpus, decoder substituted | **6,638 / 6,638** blocks, byte totals unchanged |
| 2000 PlayStation corpus, decoder substituted | **21,054** blocks, 204.7 MB → 485.9 MB; 21,049 exact and five that overrun by one byte, enumerated |
| Preloaded-dictionary reads, 2000 corpus | 1,039,128 reads traced by ring address; **zero** at or above the cursor |

Reports: [`reports/census.txt`](reports/census.txt),
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
| Tales of Phantasia | Game Boy Advance | 2003 | no — GBA BIOS `LZ77UnComp` | [snes-talesofphantasia-doc](https://github.com/vs-sr-dev/snes-talesofphantasia-doc) |
| Tales of Berseria | PC | 2017 | no — zlib inside the TL engine | [pc-talesofberseria-doc](https://github.com/vs-sr-dev/pc-talesofberseria-doc) |

Addresses, block counts and per-title verification live in those
repositories. This one holds only what is true of the format regardless of
which game you found it in.

Three titles is a family. The boundary section 6 draws — *Wolf Team's own
titles, on platforms where they wrote the decompressor themselves* — has now
survived a test it named in advance, and inside that boundary the code turns
out not to have evolved at all: it was recompiled.

What is still untested is the PlayStation 2 era — *Tales of Destiny 2* (2002)
and the *Destiny* remake (2006) — and the 2005 PSP port of *Eternia*. If the
codec is there, the boundary widens by a console generation. If it is not, the
break is 2000/2002 and the cause is probably the one that killed it on the Game
Boy Advance: a platform that supplies its own decompression.

---

## Licence

Documentation: [CC BY 4.0](LICENSE-DOCS). `tales_block.py`: [MIT](LICENSE).

*Tales of Phantasia*, *Tales of Destiny* and *Tales of Eternia* are trademarks
of BANDAI NAMCO Entertainment. This project is unaffiliated with and unendorsed
by Bandai Namco, Wolf Team, Nintendo or Sony Interactive Entertainment.
