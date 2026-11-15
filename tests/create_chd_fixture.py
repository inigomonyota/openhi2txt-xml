#!/usr/bin/env python3
"""Create a compact parent-CHD/DIF regression fixture from a real MAME disk."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


DEFAULT_HUNK_SIZE = 4096
MAX_LOGICAL_SIZE_WITHOUT_CONFIRMATION = 1024 * 1024 * 1024
SECTOR_SIZE = 512


@dataclass(frozen=True, order=True)
class ByteRange:
    offset: int
    length: int

    @property
    def end(self) -> int:
        return self.offset + self.length


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a compact synthetic CHD/DIF pair containing the real logical "
            "byte ranges selected by a game's DIF-backed XML structures."
        )
    )
    parser.add_argument("game", help="MAME short name, for example kinst")
    parser.add_argument(
        "--mame-root",
        type=Path,
        default=os.environ.get("MAME_ROOT"),
        help="real MAME root (default: MAME_ROOT environment variable)",
    )
    parser.add_argument(
        "--chdman",
        type=Path,
        default=os.environ.get("CHDMAN") or shutil.which("chdman"),
        help="path to chdman (default: CHDMAN or PATH)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="openhi2txt-xml root (default: inferred from this script)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="fixture MAME root (default: <repo>/src/test/input)",
    )
    parser.add_argument(
        "--hunk-size",
        type=int,
        default=DEFAULT_HUNK_SIZE,
        help=f"synthetic CHD hunk size (default: {DEFAULT_HUNK_SIZE})",
    )
    parser.add_argument(
        "--compression",
        default="zlib",
        help="chdman compression codec (default: zlib)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing fixture pair",
    )
    parser.add_argument(
        "--allow-large",
        action="store_true",
        help="allow a synthetic logical disk larger than 1 GiB",
    )
    parser.add_argument(
        "--keep-work",
        type=Path,
        help="keep intermediate files in this directory instead of a temporary directory",
    )
    return parser.parse_args()


def parse_number(text: str, description: str) -> int:
    try:
        value = int(text, 0)
    except ValueError as error:
        raise ValueError(f"invalid {description}: {text!r}") from error
    if value < 0:
        raise ValueError(f"{description} must not be negative: {text!r}")
    return value


def load_dif_ranges(db_root: Path, game: str) -> tuple[Path, list[ByteRange]]:
    visited: set[str] = set()
    current = game
    for _ in range(16):
        if current in visited:
            raise ValueError(f"sameas cycle while resolving {game}: {current}")
        visited.add(current)

        xml_path = db_root / f"{current}.xml"
        if not xml_path.is_file():
            raise FileNotFoundError(f"definition not found: {xml_path}")
        root = ET.parse(xml_path).getroot()

        ranges: list[ByteRange] = []
        for structure in root.findall("structure"):
            if structure.get("file", ".hi").casefold() != "dif":
                continue
            offset_text = structure.get("offset")
            length_text = structure.get("length")
            if offset_text is None or length_text is None:
                raise ValueError(
                    f"{xml_path.name}: a file='dif' structure requires offset and length"
                )
            offset = parse_number(offset_text, "structure offset")
            length = parse_number(length_text, "structure length")
            if length == 0:
                raise ValueError(f"{xml_path.name}: structure length must be positive")
            ranges.append(ByteRange(offset, length))

        if ranges:
            return xml_path, merge_ranges(ranges)

        sameas = root.find("sameas")
        if sameas is None:
            raise ValueError(f"{xml_path.name} has no DIF-backed structure")
        target = (sameas.get("id") or sameas.text or "").strip()
        if not target:
            raise ValueError(f"{xml_path.name} has an empty sameas target")
        current = target

    raise ValueError(f"sameas chain exceeds 16 definitions while resolving {game}")


def merge_ranges(ranges: list[ByteRange]) -> list[ByteRange]:
    merged: list[ByteRange] = []
    for current in sorted(ranges):
        if not merged or current.offset > merged[-1].end:
            merged.append(current)
            continue
        previous = merged[-1]
        merged[-1] = ByteRange(previous.offset, max(previous.end, current.end) - previous.offset)
    return merged


def chd_candidates(mame_root: Path, game: str) -> list[Path]:
    roms = mame_root / "roms"
    game_dir = roms / game
    conventional = game_dir / f"{game}.chd"
    candidates: list[Path] = []
    if conventional.is_file():
        candidates.append(conventional)
    if game_dir.is_dir():
        candidates.extend(
            path
            for path in sorted(game_dir.iterdir(), key=lambda item: item.name.casefold())
            if path.is_file()
            and path.suffix.casefold() == ".chd"
            and path != conventional
        )
    flat = roms / f"{game}.chd"
    if flat.is_file() and flat not in candidates:
        candidates.append(flat)
    return candidates


def resolve_source_files(mame_root: Path, game: str) -> tuple[Path, list[Path]]:
    candidates = chd_candidates(mame_root, game)
    if not candidates:
        raise FileNotFoundError(f"no parent CHD candidates found for {game}")

    diff_dir = mame_root / "diff"
    conventional = diff_dir / f"{game}.dif"
    if conventional.is_file():
        return conventional, candidates

    for candidate in candidates:
        disk_named = diff_dir / f"{candidate.stem}.dif"
        if disk_named.is_file():
            return disk_named, candidates
    raise FileNotFoundError(f"no DIF found for {game} or its CHD filenames")


def run_chdman(chdman: Path, arguments: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [str(chdman), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"chdman {' '.join(arguments)} failed:\n{detail}")
    return completed


def extract_range(
    chdman: Path,
    source: Path,
    destination: Path,
    byte_range: ByteRange,
    parent: Path | None = None,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        "extractraw",
        "-i",
        str(source),
        "-o",
        str(destination),
        "-isb",
        str(byte_range.offset),
        "-ib",
        str(byte_range.length),
        "-f",
    ]
    if parent is not None:
        arguments.extend(["-ip", str(parent)])
    return run_chdman(chdman, arguments, check=check)


def identify_parent(
    chdman: Path,
    overlay: Path,
    candidates: list[Path],
    probe_range: ByteRange,
    work: Path,
) -> Path:
    probe = work / "parent-probe.bin"
    failures: list[str] = []
    for candidate in candidates:
        completed = extract_range(
            chdman,
            overlay,
            probe,
            probe_range,
            candidate,
            check=False,
        )
        if completed.returncode == 0:
            probe.unlink(missing_ok=True)
            return candidate
        failures.append(candidate.name)
        probe.unlink(missing_ok=True)
    raise RuntimeError(
        "none of the CHD candidates matched the DIF parent identity: "
        + ", ".join(failures)
    )


def create_sparse_raw(path: Path, logical_size: int) -> None:
    with path.open("wb") as output:
        output.truncate(logical_size)


def insert_window(raw_path: Path, byte_range: ByteRange, window_path: Path) -> None:
    data = window_path.read_bytes()
    if len(data) != byte_range.length:
        raise RuntimeError(
            f"chdman extracted {len(data)} bytes; expected {byte_range.length}"
        )
    with raw_path.open("r+b") as output:
        output.seek(byte_range.offset)
        output.write(data)


def round_up(value: int, multiple: int) -> int:
    return ((value + multiple - 1) // multiple) * multiple


def make_fixture(args: argparse.Namespace, work: Path) -> None:
    repo_root = args.repo_root.resolve()
    mame_root = args.mame_root.resolve()
    chdman = args.chdman.resolve()
    output_root = (args.output_root or repo_root / "src" / "test" / "input").resolve()

    definition, ranges = load_dif_ranges(repo_root / "src" / "main" / "db", args.game)
    overlay, candidates = resolve_source_files(mame_root, args.game)
    parent = identify_parent(chdman, overlay, candidates, ranges[0], work)

    logical_size = round_up(max(item.end for item in ranges), SECTOR_SIZE)
    if logical_size > MAX_LOGICAL_SIZE_WITHOUT_CONFIRMATION and not args.allow_large:
        raise ValueError(
            f"synthetic logical size would be {logical_size:,} bytes; "
            "inspect the XML offset and repeat with --allow-large"
        )
    if args.hunk_size < 16 or args.hunk_size > 1024 * 1024:
        raise ValueError("--hunk-size must be between 16 and 1048576 bytes")
    if args.hunk_size % SECTOR_SIZE:
        raise ValueError("--hunk-size must be a multiple of 512 for createhd")

    synthetic_parent = work / "synthetic-parent.raw"
    synthetic_merged = work / "synthetic-merged.raw"
    create_sparse_raw(synthetic_parent, logical_size)
    create_sparse_raw(synthetic_merged, logical_size)

    for index, byte_range in enumerate(ranges):
        parent_window = work / f"parent-{index}.bin"
        merged_window = work / f"merged-{index}.bin"
        extract_range(chdman, parent, parent_window, byte_range)
        extract_range(chdman, overlay, merged_window, byte_range, parent)
        insert_window(synthetic_parent, byte_range, parent_window)
        insert_window(synthetic_merged, byte_range, merged_window)

    parent_output = output_root / "roms" / args.game / parent.name
    overlay_output = output_root / "diff" / overlay.name
    if not args.force:
        existing = [path for path in (parent_output, overlay_output) if path.exists()]
        if existing:
            raise FileExistsError(
                "fixture output already exists; use --force to replace: "
                + ", ".join(str(path) for path in existing)
            )
    parent_output.parent.mkdir(parents=True, exist_ok=True)
    overlay_output.parent.mkdir(parents=True, exist_ok=True)

    sectors = logical_size // SECTOR_SIZE
    common = ["-hs", str(args.hunk_size), "-c", args.compression]
    force = ["-f"] if args.force else []
    run_chdman(
        chdman,
        [
            "createhd",
            "-i",
            str(synthetic_parent),
            "-o",
            str(parent_output),
            "-chs",
            f"1,1,{sectors}",
            *common,
            *force,
        ],
    )
    run_chdman(
        chdman,
        [
            "createhd",
            "-i",
            str(synthetic_merged),
            "-o",
            str(overlay_output),
            "-op",
            str(parent_output),
            *common,
            *force,
        ],
    )

    for index, byte_range in enumerate(ranges):
        fixture_parent_window = work / f"fixture-parent-{index}.bin"
        fixture_merged_window = work / f"fixture-merged-{index}.bin"
        extract_range(chdman, parent_output, fixture_parent_window, byte_range)
        extract_range(
            chdman,
            overlay_output,
            fixture_merged_window,
            byte_range,
            parent_output,
        )
        if fixture_parent_window.read_bytes() != (work / f"parent-{index}.bin").read_bytes():
            raise RuntimeError(f"fixture parent differs in range {index}")
        if fixture_merged_window.read_bytes() != (work / f"merged-{index}.bin").read_bytes():
            raise RuntimeError(f"fixture overlay differs in range {index}")

    print(f"Definition: {definition}")
    print("Ranges: " + ", ".join(f"0x{item.offset:X}+0x{item.length:X}" for item in ranges))
    print(f"Source parent: {parent}")
    print(f"Source overlay: {overlay}")
    print(f"Logical size: {logical_size:,} bytes")
    print(f"Fixture parent: {parent_output} ({parent_output.stat().st_size:,} bytes)")
    print(f"Fixture overlay: {overlay_output} ({overlay_output.stat().st_size:,} bytes)")
    print("Verified: every XML-selected parent and merged byte range matches the source disks")


def main() -> int:
    args = parse_args()
    if args.mame_root is None:
        print("error: provide --mame-root or set MAME_ROOT", file=sys.stderr)
        return 2
    if not args.mame_root.is_dir():
        print(f"error: MAME root not found: {args.mame_root}", file=sys.stderr)
        return 2
    if args.chdman is None:
        print("error: provide --chdman, set CHDMAN, or put chdman on PATH", file=sys.stderr)
        return 2
    if not args.chdman.is_file():
        print(f"error: chdman not found: {args.chdman}", file=sys.stderr)
        return 2

    try:
        if args.keep_work:
            work = args.keep_work.resolve()
            work.mkdir(parents=True, exist_ok=True)
            make_fixture(args, work)
        else:
            with tempfile.TemporaryDirectory(prefix=f"{args.game}-chd-fixture-") as temporary:
                make_fixture(args, Path(temporary))
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError, ET.ParseError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
