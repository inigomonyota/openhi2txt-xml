#!/usr/bin/env python3
"""Capture and auto-select MAME high-score screenshots for openhi2txt-xml."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

LUA_TEMPLATE = """\
local next_snap = {start}
local stop_at = {duration}
local step = {interval}
emu.register_frame_done(function()
    local t = emu.time()
    if t >= next_snap then
        manager.machine.video:snapshot()
        next_snap = next_snap + step
        if next_snap > stop_at then
            manager.machine:exit()
        end
    end
end)
"""

OCR_PS_SCRIPT = r"""
param([string]$ListFile)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapTransform, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapInterpolationMode, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.ExifOrientationMode, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.ColorManagementMode, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType=WindowsRuntime]

function Await($WinRtTask, $ResultType) {
    $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq "AsTask" -and $_.GetParameters().Count -eq 1 -and $_.IsGenericMethod })[0].MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$results = @{}
foreach ($p in Get-Content -LiteralPath $ListFile -Encoding UTF8) {
    if (-not $p) { continue }
    try {
        $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($p)) ([Windows.Storage.StorageFile])
        $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $t = [Windows.Graphics.Imaging.BitmapTransform]::new()
        $t.ScaledWidth = [uint32]($decoder.PixelWidth * 3)
        $t.ScaledHeight = [uint32]($decoder.PixelHeight * 3)
        $t.InterpolationMode = [Windows.Graphics.Imaging.BitmapInterpolationMode]::NearestNeighbor
        $bitmap = Await ($decoder.GetSoftwareBitmapAsync($decoder.BitmapPixelFormat, $decoder.BitmapAlphaMode, $t, [Windows.Graphics.Imaging.ExifOrientationMode]::IgnoreExifOrientation, [Windows.Graphics.Imaging.ColorManagementMode]::DoNotColorManage)) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $res = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $results[$p] = $res.Text
        $bitmap.Dispose()
        $stream.Dispose()
    } catch {
        $results[$p] = ""
    }
}
$results | ConvertTo-Json -Compress
"""


def parse_args() -> argparse.Namespace:
    default_mame = os.environ.get("MAME_ROOT") or r"E:\mame-openhi2txt"
    parser = argparse.ArgumentParser(
        description="Capture MAME high-score screenshots into src/test/screenshots/."
    )
    parser.add_argument(
        "--mame-root",
        type=Path,
        default=Path(default_mame),
        help=f"MAME installation directory (default: {default_mame})",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="openhi2txt-xml repository root",
    )
    parser.add_argument(
        "--game",
        action="append",
        default=[],
        help="game short name to capture (repeatable)",
    )
    parser.add_argument(
        "--missing",
        action="store_true",
        help="select all oracle games that do not yet have screenshots",
    )
    parser.add_argument(
        "--candidates",
        action="store_true",
        help="select games that have candidate frames (<game>/) but no matched <game>.png",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="print screenshot coverage summary and exit",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="launch windowed MAME for manual F12 capture instead of headless auto-attract",
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="skip automatic Windows OCR high-score frame selection",
    )
    parser.add_argument(
        "--keep-all",
        action="store_true",
        help="keep all deduplicated attract-mode frames even after selecting <game>.png",
    )
    parser.add_argument(
        "--start",
        type=float,
        default=6.0,
        help="emulated seconds before first auto snapshot (default: 6.0)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=3.0,
        help="emulated seconds between auto snapshots (default: 3.0)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="total emulated seconds per game in auto mode (default: 60.0)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=4,
        help="parallel MAME workers in auto mode (default: 4)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="maximum number of games to process (0 = no limit)",
    )
    parser.add_argument(
        "--reocr",
        action="store_true",
        help="re-run 3x upscaled OCR on existing candidate folders without launching MAME",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="delete candidate frames below --min-score (and empty candidate folders)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=3,
        help="minimum OCR score to keep a candidate frame when using --prune (default: 3)",
    )
    parser.add_argument(
        "--top-fallback",
        action="store_true",
        help="promote a top-of-screen HI-SCORE match when no full table frame is found",
    )
    parser.add_argument(
        "--table-duration",
        type=float,
        default=0.0,
        help="if > 0, re-run games whose XML has a multi-row table for this many emulated seconds when no table was found",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-capture even if screenshots already exist for the game",
    )
    return parser.parse_args()


def has_screenshot(snap_root: Path, game: str) -> bool:
    if (snap_root / f"{game}.png").is_file():
        return True
    gdir = snap_root / game
    return gdir.is_dir() and any(gdir.glob("*.png"))


def deduplicate_snaps(game_dir: Path, min_bytes: int = 500) -> list[Path]:
    if not game_dir.is_dir():
        return []
    seen_hashes: set[str] = set()
    kept: list[Path] = []
    for png in sorted(game_dir.glob("*.png")):
        data = png.read_bytes()
        if len(data) < min_bytes:
            png.unlink()
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen_hashes:
            png.unlink()
            continue
        seen_hashes.add(digest)
        kept.append(png)
    return kept


def extract_oracle_tokens(oracle_txt: Path) -> tuple[set[str], set[str]]:
    """Return (numeric_scores, name_or_label_tokens) from an oracle .txt file."""
    if not oracle_txt.is_file():
        return set(), set()
    nums: set[str] = set()
    words: set[str] = set()
    for line in oracle_txt.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        for cell in s.split("|"):
            c = cell.strip()
            digits = c.replace(",", "").replace(".", "")
            if digits.isdigit() and len(digits) >= 3 and int(digits) > 0:
                nums.add(digits)
            elif len(c) >= 3 and any(ch.isalpha() for ch in c):
                words.add(c.upper())
    return nums, words


def extract_oracle_tables(oracle_root: Path, game: str) -> list[tuple[str, set[str], set[str]]]:
    """Return per-table (table_id, numeric_scores, word_tokens) from oracle XML."""
    xml_path = oracle_root / f"{game}.xml"
    if not xml_path.is_file():
        nums, words = extract_oracle_tokens(oracle_root / f"{game}.txt")
        return [("default", nums, words)] if (nums or words) else []
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        nums, words = extract_oracle_tokens(oracle_root / f"{game}.txt")
        return [("default", nums, words)] if (nums or words) else []

    tables: list[tuple[str, set[str], set[str]]] = []
    for idx, table in enumerate(root.findall("table"), 1):
        tid = (table.get("id") or f"table_{idx}").strip()
        nums: set[str] = set()
        words: set[str] = set()
        for tok in re.split(r"[^A-Za-z0-9]+", tid):
            if len(tok) >= 3 and any(ch.isalpha() for ch in tok):
                words.add(tok.upper())
        for row in table.findall("row"):
            for cell in row.findall("cell"):
                c = (cell.text or "").strip()
                digits = c.replace(",", "").replace(".", "")
                if digits.isdigit() and len(digits) >= 3 and int(digits) > 0:
                    nums.add(digits)
                elif len(c) >= 3 and any(ch.isalpha() for ch in c):
                    words.add(c.upper())
        if nums or words:
            tables.append((tid, nums, words))
    if not tables:
        f_nums: set[str] = set()
        f_words: set[str] = set()
        for field in root.findall("field"):
            c = (field.text or "").strip()
            digits = c.replace(",", "").replace(".", "")
            if digits.isdigit() and len(digits) >= 3 and int(digits) > 0:
                f_nums.add(digits)
            elif len(c) >= 3 and any(ch.isalpha() for ch in c):
                f_words.add(c.upper())
        if f_nums or f_words:
            tables.append(("field", f_nums, f_words))
        else:
            nums, words = extract_oracle_tokens(oracle_root / f"{game}.txt")
            if nums or words:
                tables.append(("default", nums, words))
    return tables


def extract_top_info(oracle_root: Path, game: str) -> tuple[bool, set[str], set[str]]:
    """Return (has_multi_row_table, top_nums, top_words) from oracle XML/txt."""
    xml_path = oracle_root / f"{game}.xml"
    has_table = False
    top_nums: set[str] = set()
    top_words: set[str] = set()
    if xml_path.is_file():
        try:
            root = ET.parse(xml_path).getroot()
            xml_tables = root.findall("table")
            has_table = len(xml_tables) > 1 or any(
                len(t.findall("row")) >= 2 for t in xml_tables
            )
            first_row = xml_tables[0].find("row") if xml_tables else None
            if first_row is not None:
                for cell in first_row.findall("cell"):
                    c = (cell.text or "").strip()
                    digits = c.replace(",", "").replace(".", "")
                    if digits.isdigit() and len(digits) >= 3 and int(digits) > 0:
                        top_nums.add(digits)
                    elif len(c) >= 3 and any(ch.isalpha() for ch in c):
                        top_words.add(c.upper())
            elif not xml_tables:
                for field in root.findall("field"):
                    c = (field.text or "").strip()
                    digits = c.replace(",", "").replace(".", "")
                    if digits.isdigit() and len(digits) >= 3 and int(digits) > 0:
                        top_nums.add(digits)
                    elif len(c) >= 3 and any(ch.isalpha() for ch in c):
                        top_words.add(c.upper())
            return has_table, top_nums, top_words
        except ET.ParseError:
            pass

    txt_path = oracle_root / f"{game}.txt"
    if txt_path.is_file():
        rows = [
            ln.strip()
            for ln in txt_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip() and not ln.strip().startswith("#") and "|" in ln
        ]
        # Exclude header row
        data_rows = [r for r in rows[1:]] if len(rows) > 1 else []
        has_table = len(data_rows) >= 2
        if data_rows:
            for cell in data_rows[0].split("|"):
                c = cell.strip()
                digits = c.replace(",", "").replace(".", "")
                if digits.isdigit() and len(digits) >= 3 and int(digits) > 0:
                    top_nums.add(digits)
                elif len(c) >= 3 and any(ch.isalpha() for ch in c):
                    top_words.add(c.upper())
    return has_table, top_nums, top_words


def slugify_table_id(tid: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", tid.lower()).strip("_")
    return slug[:40] or "table"


def ocr_images(paths: list[Path]) -> dict[str, str]:
    if not paths:
        return {}
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as psf:
        psf.write(OCR_PS_SCRIPT)
        ps_path = Path(psf.name)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as lsf:
        lsf.write("\n".join(str(p.resolve()) for p in paths) + "\n")
        list_path = Path(lsf.name)
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps_path), str(list_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return {}
        return json.loads(proc.stdout.strip())
    except Exception:
        return {}
    finally:
        ps_path.unlink(missing_ok=True)
        list_path.unlink(missing_ok=True)


def score_ocr_text(text: str, nums: set[str], words: set[str]) -> tuple[int, int]:
    norm = text.upper().replace(",", "").replace(" ", "")
    raw_up = text.upper()
    score = 0
    hits = 0
    for n in nums:
        if n in norm:
            score += 3
            hits += 1
    for w in words:
        if w in raw_up:
            score += 2
            hits += 1
    for kw in ("SCORE", "RANK", "HIGH", "BEST", "TOP", "RECORD"):
        if kw in raw_up:
            score += 1
    return score, hits


def find_top_score_frame(
    pngs: list[Path],
    ocr_map: dict[str, str],
    top_nums: set[str],
    top_words: set[str],
) -> tuple[Path | None, int]:
    """Return (best_png, score) matching rank-1 top score + HUD keyword/name."""
    if not top_nums:
        return None, 0
    best_p: Path | None = None
    best_sc = 0
    for p in pngs:
        txt = ocr_map.get(str(p.resolve()), "")
        norm = txt.upper().replace(",", "").replace(" ", "")
        raw_up = txt.upper()
        word_hit = any(w in raw_up for w in top_words)
        num_hits = sum(
            1 for n in top_nums if n in norm and (len(n) >= 4 or word_hit)
        )
        kw_hits = sum(
            1
            for kw in ("SCORE", "RANK", "HIGH", "BEST", "TOP", "RECORD", "1ST")
            if kw in raw_up
        )
        if num_hits > 0 and (kw_hits > 0 or word_hit):
            sc = num_hits * 3 + (2 if word_hit else 0) + kw_hits
            if sc > best_sc:
                best_sc = sc
                best_p = p
    return best_p, best_sc


def select_best_screenshot(
    game: str,
    pngs: list[Path],
    oracle_root: Path,
    snap_root: Path,
    keep_all: bool,
    prune_below: int | None = None,
    allow_top_fallback: bool = False,
) -> tuple[bool, int, int, str]:
    if not pngs:
        return False, 0, 0, ""
    has_table, top_nums, top_words = extract_top_info(oracle_root, game)
    tables = extract_oracle_tables(oracle_root, game)
    ocr_map = ocr_images(pngs)
    if not ocr_map:
        return False, 0, len(pngs), "XML has table" if has_table else ""

    # Multi-table handling: score each frame per <table>
    if len(tables) > 1:
        selected: list[tuple[str, Path, int]] = []
        best_overall = 0
        per_png_max: dict[Path, int] = {p: 0 for p in pngs}
        for tid, nums, words in tables:
            best_t_png = None
            best_t_score = -1
            best_t_hits = 0
            for p in pngs:
                sc, hits = score_ocr_text(ocr_map.get(str(p.resolve()), ""), nums, words)
                if sc > per_png_max[p]:
                    per_png_max[p] = sc
                if sc > best_t_score:
                    best_t_score = sc
                    best_t_hits = hits
                    best_t_png = p
            if best_t_score > best_overall:
                best_overall = best_t_score
            if best_t_png is not None and (best_t_score >= 6 or (best_t_score >= 5 and best_t_hits >= 2)):
                selected.append((tid, best_t_png, best_t_score))

        unique_pngs = {p for _, p, _ in selected}
        if len(unique_pngs) == 1:
            only_png = next(iter(unique_pngs))
            shutil.copy2(only_png, snap_root / f"{game}.png")
            if not keep_all:
                shutil.rmtree(snap_root / game, ignore_errors=True)
            return True, best_overall, 1, ""
        if len(unique_pngs) > 1:
            gdir = snap_root / game
            staged: list[tuple[str, bytes]] = []
            seen_data: set[Path] = set()
            for idx, (tid, p, _) in enumerate(selected, 1):
                if p in seen_data:
                    continue
                seen_data.add(p)
                staged.append((f"{idx:02d}_{slugify_table_id(tid)}.png", p.read_bytes()))
            if not keep_all:
                for p in pngs:
                    p.unlink(missing_ok=True)
            gdir.mkdir(parents=True, exist_ok=True)
            for fname, data in staged:
                (gdir / fname).write_bytes(data)
            return True, best_overall, len(staged), "multi-table"

        if allow_top_fallback:
            top_p, top_sc = find_top_score_frame(pngs, ocr_map, top_nums, top_words)
            if top_p is not None:
                shutil.copy2(top_p, snap_root / f"{game}.png")
                if not keep_all:
                    shutil.rmtree(snap_root / game, ignore_errors=True)
                return True, max(best_overall, top_sc), 1, "top-only; XML has table"

        kept = len(pngs)
        if prune_below is not None:
            kept = 0
            for p, sc in per_png_max.items():
                if sc < prune_below:
                    p.unlink(missing_ok=True)
                else:
                    kept += 1
            if kept == 0:
                shutil.rmtree(snap_root / game, ignore_errors=True)
        return False, best_overall, kept, "XML has table"

    # Single-table / field-only handling
    _, nums, words = tables[0] if tables else ("default", set(), set())
    # Top-score-only games (1-2 oracle values) only need score + keyword (>= 4);
    # multi-row tables require >= 2 oracle value hits (score >= 5) or >= 6.
    is_top_only = (len(nums) + len(words)) <= 2
    best_png = None
    best_score = -1
    best_hits = 0
    scores: dict[Path, int] = {}
    for p in pngs:
        txt = ocr_map.get(str(p.resolve()), "")
        sc, hits = score_ocr_text(txt, nums, words)
        scores[p] = sc
        if sc > best_score:
            best_score = sc
            best_hits = hits
            best_png = p

    promoted = best_png is not None and (
        (is_top_only and best_score >= 4)
        or (not is_top_only and (best_score >= 6 or (best_score >= 5 and best_hits >= 2)))
    )
    if promoted:
        target = snap_root / f"{game}.png"
        shutil.copy2(best_png, target)
        if not keep_all:
            shutil.rmtree(snap_root / game, ignore_errors=True)
        return True, best_score, 1, ""

    if allow_top_fallback:
        top_p, top_sc = find_top_score_frame(pngs, ocr_map, top_nums, top_words)
        if top_p is not None:
            shutil.copy2(top_p, snap_root / f"{game}.png")
            if not keep_all:
                shutil.rmtree(snap_root / game, ignore_errors=True)
            note = "top-only; XML has table" if has_table else "top-only"
            return True, max(best_score, top_sc), 1, note

    kept = len(pngs)
    if prune_below is not None:
        kept = 0
        for p, sc in scores.items():
            if sc < prune_below:
                p.unlink(missing_ok=True)
            else:
                kept += 1
        if kept == 0:
            shutil.rmtree(snap_root / game, ignore_errors=True)
    return False, best_score, kept, "XML has table" if has_table else ""


def capture_auto(
    mame_exe: Path,
    mame_root: Path,
    snap_root: Path,
    lua_path: Path,
    game: str,
    timeout_sec: int,
) -> tuple[str, list[Path], str]:
    game_dir = snap_root / game
    if game_dir.is_dir():
        shutil.rmtree(game_dir)

    cmd = [
        str(mame_exe),
        game,
        "-video",
        "none",
        "-sound",
        "none",
        "-skip_gameinfo",
        "-nothrottle",
        "-snapshot_directory",
        str(snap_root),
        "-autoboot_script",
        str(lua_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(mame_root),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        kept = deduplicate_snaps(game_dir)
        return game, kept, "timeout"

    kept = deduplicate_snaps(game_dir)
    if proc.returncode != 0 and not kept:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        return game, [], err[-1] if err else f"rc={proc.returncode}"
    return game, kept, "ok"


def capture_interactive(
    mame_exe: Path,
    mame_root: Path,
    snap_root: Path,
    game: str,
) -> int:
    cmd = [
        str(mame_exe),
        game,
        "-window",
        "-sound",
        "none",
        "-skip_gameinfo",
        "-snapshot_directory",
        str(snap_root),
    ]
    subprocess.run(cmd, cwd=str(mame_root))
    return len(deduplicate_snaps(snap_root / game, min_bytes=0))


def main() -> int:
    args = parse_args()
    mame_exe = args.mame_root / "mame.exe"
    if not mame_exe.is_file():
        print(f"error: mame.exe not found at {mame_exe}", file=sys.stderr)
        return 1

    oracle_root = args.repo_root / "src" / "test" / "oracle"
    snap_root = args.repo_root / "src" / "test" / "screenshots"
    snap_root.mkdir(parents=True, exist_ok=True)

    oracle_games = sorted({p.stem for p in oracle_root.glob("*.txt")})
    with_snap = [g for g in oracle_games if has_screenshot(snap_root, g)]
    missing_snap = [g for g in oracle_games if not has_screenshot(snap_root, g)]

    if args.status:
        exact = sum(1 for g in oracle_games if (snap_root / f"{g}.png").is_file())
        print(f"Oracle games:      {len(oracle_games)}")
        print(f"Matched (<g>.png): {exact}")
        print(f"With any snaps:    {len(with_snap)}")
        print(f"Missing:           {len(missing_snap)}")
        return 0

    if args.reocr or args.prune:
        cand_games = sorted(
            d.name
            for d in snap_root.iterdir()
            if d.is_dir() and not (snap_root / f"{d.name}.png").is_file()
        )
        if args.game:
            cand_games = [g for g in cand_games if g in set(args.game)]
        if args.limit > 0:
            cand_games = cand_games[: args.limit]
        prune_below = args.min_score if args.prune else None
        action = f"Pruning (< {args.min_score})" if args.prune else "Re-running 3x upscaled OCR"
        print(f"{action} on {len(cand_games)} candidate folder(s)...")
        matched_cnt, kept_dirs, removed_dirs, kept_frames = 0, 0, 0, 0
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
            futs = [
                ex.submit(
                    select_best_screenshot,
                    g,
                    sorted((snap_root / g).glob("*.png")),
                    oracle_root,
                    snap_root,
                    args.keep_all,
                    prune_below,
                    args.top_fallback,
                )
                for g in cand_games
            ]
            for g, fut in zip(cand_games, futs):
                matched, score, kept, note = fut.result()
                suffix = f" [{note}]" if note else ""
                if matched:
                    matched_cnt += 1
                    print(f"  MATCHED    {g}.png (ocr_score={score}){suffix}")
                elif kept == 0:
                    removed_dirs += 1
                else:
                    kept_dirs += 1
                    kept_frames += kept
        print(
            f"Summary: {matched_cnt} matched (<game>.png), "
            f"{kept_dirs} candidate dirs kept ({kept_frames} frames), "
            f"{removed_dirs} empty/non-matching dirs removed"
        )
        return 0

    if args.game:
        targets = args.game
    elif args.candidates:
        targets = sorted(
            d.name
            for d in snap_root.iterdir()
            if d.is_dir()
            and not (snap_root / f"{d.name}.png").is_file()
            and not any(d.glob("[0-9][0-9]_*.png"))
        )
    elif args.missing:
        targets = missing_snap
    else:
        print("Specify --game <name>, --missing, --candidates, or --status", file=sys.stderr)
        return 2

    if not args.force and not args.candidates:
        targets = [g for g in targets if not has_screenshot(snap_root, g)]

    if args.limit > 0:
        targets = targets[: args.limit]

    if not targets:
        print("No games to capture.")
        return 0

    if args.interactive:
        print(f"Interactive capture for {len(targets)} game(s). Press F12 to snap, Esc to advance.")
        for i, g in enumerate(targets, 1):
            print(f"[{i}/{len(targets)}] {g}...")
            kept = capture_interactive(mame_exe, args.mame_root, snap_root, g)
            print(f"  kept {kept} screenshot(s)")
        return 0

    def run_capture_batch(batch_targets: list[str], dur: float, allow_top: bool) -> tuple[int, list[str], int, list[tuple[str, list[Path], int, str]]]:
        lua_text = LUA_TEMPLATE.format(
            start=args.start, interval=args.interval, duration=dur
        )
        with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False, encoding="utf-8") as tf:
            tf.write(lua_text)
            lua_path = Path(tf.name)
        m_cnt, f_cnt = 0, 0
        retry_table: list[str] = []
        unmatched: list[tuple[str, list[Path], int, str]] = []
        try:
            with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
                futs = [
                    ex.submit(
                        capture_auto,
                        mame_exe,
                        args.mame_root,
                        snap_root,
                        lua_path,
                        g,
                        max(60, int(dur * 2)),
                    )
                    for g in batch_targets
                ]
                for fut in as_completed(futs):
                    g, pngs, status = fut.result()
                    if not pngs:
                        f_cnt += 1
                        print(f"  FAIL       {g}: 0 screenshots ({status})")
                        continue
                    if args.no_ocr:
                        unmatched.append((g, pngs, 0, ""))
                        print(f"  CAPTURED   {g}: {len(pngs)} frame(s)")
                        continue
                    matched, score, _, note = select_best_screenshot(
                        g, pngs, oracle_root, snap_root, args.keep_all,
                        allow_top_fallback=allow_top,
                    )
                    if matched:
                        m_cnt += 1
                        suffix = f" [{note}]" if note else ""
                        print(f"  MATCHED    {g}.png (ocr_score={score}, from {len(pngs)} frames){suffix}")
                    elif args.table_duration > dur and note == "XML has table":
                        retry_table.append(g)
                    else:
                        unmatched.append((g, pngs, score, note))
                        suffix = f" [{note}]" if note else ""
                        print(f"  CANDIDATES {g}/: {len(pngs)} frame(s) (best ocr_score={score}){suffix}")
        finally:
            lua_path.unlink(missing_ok=True)
        return m_cnt, retry_table, f_cnt, unmatched

    print(f"Auto-capturing {len(targets)} game(s) with {args.jobs} worker(s) (duration={args.duration}s, interval={args.interval}s)...")
    # If --table-duration is set, defer top-only fallback until after the longer pass
    defer_top = args.table_duration > args.duration
    matched_cnt, retry_table, failed_cnt, unmatched = run_capture_batch(
        targets, args.duration, allow_top=(args.top_fallback and not defer_top)
    )
    unverified_cnt = len(unmatched)

    if retry_table and not args.no_ocr:
        print(f"\nRe-capturing {len(retry_table)} whole-table game(s) with longer duration ({args.table_duration}s)...")
        m2, _, f2, u2 = run_capture_batch(
            retry_table, args.table_duration, allow_top=args.top_fallback
        )
        matched_cnt += m2
        failed_cnt += f2
        unverified_cnt += len(u2)

    print(
        f"Summary: {matched_cnt} matched (<game>.png), "
        f"{unverified_cnt} with candidate frames, {failed_cnt} failed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
