# Missing Test Input Files

The following XML definitions in `src/main/db/` do not yet have sample input files for regression testing and screenshot capture.

In MAME, `.hi` files are saved under `hiscore/<rom>.hi` (by the `hiscore` plugin) and NVRAM files are saved under `nvram/<rom>/`.

## Arcade (51)

| ROM | Game Title | Expected MAME File | Expected Size |
| --- | --- | --- | --- |
| `3stoogesa` | The Three Stooges In Brides Is Brides (set 2) | `nvram/3stoogesa/nvram` | 4096 bytes |
| `altair` | Altair | `nvram/altair/nvram` | 256 bytes |
| `asterock` | Asterock | `hiscore/asterock.hi` | 53/54 bytes |
| `batsugun` |  | `hiscore/batsugun.hi` | 164 bytes |
| `batsuguna` |  | `hiscore/batsuguna.hi` | 164 bytes |
| `batsugunb` |  | `hiscore/batsugunb.hi` | 164 bytes |
| `batsugunb1` |  | `hiscore/batsugunb1.hi` | 164 bytes |
| `batsugunc` |  | `hiscore/batsugunc.hi` | 164 bytes |
| `bublboblp` |  | `hiscore/bublboblp.hi` | 73 bytes |
| `ckongs` |  | `hiscore/ckongs.hi` | 173 bytes |
| `cninjau` |  | `hiscore/cninjau.hi` | 175 bytes |
| `cyberbal2p` | Cyberball 2072 (2 player) | `hiscore/cyberbal2p.hi` | 200 bytes |
| `deadeye` |  | `hiscore/deadeye.hi` | 7 bytes |
| `ffighta` | Final Fight (USA, set 1) | `hiscore/ffighta.hi` | 63 bytes |
| `ffightu` | Final Fight (USA, set 1) | `hiscore/ffightu.hi` | 61 bytes |
| `forgottnu` | Forgotten Worlds | `hiscore/forgottnu.hi` | 84 bytes |
| `forgottnua` | Forgotten Worlds | `hiscore/forgottnua.hi` | 84 bytes |
| `forgottnuaa` | Forgotten Worlds | `hiscore/forgottnuaa.hi` | 84 bytes |
| `forgottnuc` | Forgotten Worlds | `hiscore/forgottnuc.hi` | 84 bytes |
| `forgottnue` | Forgotten Worlds | `hiscore/forgottnue.hi` | 84 bytes |
| `galaga3` | Galaga 3 (GP3 rev. D) | `hiscore/galaga3.hi` | 171 bytes |
| `griffon` |  | `hiscore/griffon.hi` | 9 bytes |
| `hatris` | Hatris | `hiscore/hatris.hi` | 120 bytes or 118 bytes |
| `jdredd` | Judge Dredd (Midway) | `nvram/jdredd/nvram` | 2080 bytes |
| `joemac` |  | `hiscore/joemac.hi` | 175 bytes |
| `jrpacmbl` | Jr. Pac-Man (Pengo hardware) | `hiscore/jrpacmbl.hi` | 10 bytes |
| `ldrun4` | Lode Runner | `hiscore/ldrun4.hi` | 203 bytes |
| `lostwrld` | Forgotten Worlds | `hiscore/lostwrld.hi` | 84 bytes |
| `lostwrldo` | Forgotten Worlds | `hiscore/lostwrldo.hi` | 84 bytes |
| `meteorts` | Meteorites | `hiscore/meteorts.hi` | 53/54 bytes |
| `mplanetsuk` | Mad Planets (uk) | `nvram/mplanetsuk/nvram` | 4096 bytes |
| `panic` | Space Panic | `hiscore/panic.hi` | 19 bytes |
| `primrage` | Primal Rage | `hiscore/primrage.hi` | 113 bytes |
| `rampage2` | Rampage | `nvram/rampage2/nvram` | 2048 bytes |
| `raycris` |  | `hiscore/raycris.hi` | 336 bytes |
| `raystorm` |  | `hiscore/raystorm.hi` | 120 bytes |
| `samesame2` |  | `hiscore/samesame2.hi` | 438 bytes |
| `sboblbobla` |  | `hiscore/sboblbobla.hi` | 94 bytes |
| `searthin` |  | `hiscore/searthin.hi` | 2 bytes |
| `shadoww` |  | `hiscore/shadoww.hi` | 209 bytes |
| `sisv` |  | `hiscore/sisv.hi` | 2 bytes |
| `soulclbr` | Soul Calibur | `hiscore/soulclbr.hi` | 359 bytes |
| `spcewars` |  | `hiscore/spcewars.hi` | 42 bytes |
| `starcas` |  | `hiscore/starcas.hi` | 4 bytes |
| `stdragon` |  | `hiscore/stdragon.hi` | 124 bytes |
| `tinstar` |  | `hiscore/tinstar.hi` | 3 bytes |
| `tn` |  | `hiscore/tn.hi` | 160 bytes |
| `trophyh` | Trophy Hunting - Bear & Moose | `nvram/trophyh/trophyh` | 65536 bytes |
| `turkhunt` | Turkey Hunting USA | `nvram/turkhunt/turkhunt` | 65536 bytes |
| `wexpress` |  | `hiscore/wexpress.hi` | 80 bytes or 83 bytes |
| `wschamp` | Wing Shooting Championship | `nvram/wschamp/wschamp` | 65536 bytes |

## Console / Computer (2)

| ID | Title | Expected File | Expected Size |
| --- | --- | --- | --- |
| `psu_spdpunks` | Speed Punks | `nvram/psu_spdpunks/SCUS-94563` | 8192 bytes |
| `snes_tetrisdru` | Tetris & Dr. Mario | `hiscore/snes_tetrisdru.hi` | 70 bytes |
