# The Legend of Zelda: Link's Awakening (planning, no code yet)

A planned port of *Link's Awakening* (Switch, 2019) that would run natively on Apple silicon, built the same way as
`games/totk`, `games/by3` and `games/odyssey`. The game's own ARM64 code would run as it is: rewritten ahead of time,
loaded and relocated, with a small Horizon host answering system calls and IPC, and NVN graphics rebuilt on Metal 4.

**This folder holds only planning documents so far.** Nothing builds yet.

You must own the game. Nothing from the game will ever be in this folder. The work folder (`Awakening_build/`, once it
exists) is ignored by git.

## Documents

| File | What it says |
|---|---|
| [LASRECOMP_AUDIT.md](LASRECOMP_AUDIT.md) | How [LASRecomp](https://github.com/peiikai/LASRecomp) differs from this repository, and why it cannot be merged as-is |
| [HARVEST.md](HARVEST.md) | What LASRecomp already found about the game that we can use: patch addresses, the SDK functions it touches, services, movie API, rendering issues. Each item has its source file. |
| [PLAYBOOK.md](PLAYBOOK.md) | The staged plan to build `games/awakening`, modelled on the Odyssey port, with what "done" means for each stage |

## Target

- *Link's Awakening* **1.0.0**, the version LASRecomp supports (base game, no update). Title ID `01006BB00C6F0000`
  (check it against your own dump in stage 1).
- Code modules: **`main` and `sdk` only** (no `subsdk0`), plus `rtld` and `main.npdm`.
- Movies: `.webm` files (VP9 video and Vorbis audio), for example `region_common/movie/opening.webm` and `title.webm`.

## Rules this port follows (see the root CONTRIBUTING.md)

- No CPU emulation, interpreter, JIT or dynamic translation. LASRecomp's ARM64→C translator is **not** used.
- `games/awakening` keeps its own copy of everything it builds with, and never reads `games/totk`, `games/by3` or
  `games/odyssey`. Each copy is listed in `third_party/COPIES.md`, with the folder and commit it came from.
- Every game patch checks the original instruction first and stops with an error if it differs.
- Anything taken from LASRecomp (MIT) is credited in `THIRD_PARTY_NOTICES.md`. Logic is rewritten, not copied file
  for file. LASRecomp says it was written almost entirely by AI, so every address and claim is checked against your
  own dump before use.
