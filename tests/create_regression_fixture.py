#!/usr/bin/env python3
"""Copy normal score inputs and create text/XML regression oracles."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InputFile:
    source: Path
    destination: Path
    explicit: bool


@dataclass(frozen=True)
class TableShape:
    table_id: str
    columns: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy the .hi/NVRAM files referenced by a definition and generate "
            "its canonical text and XML regression outputs."
        )
    )
    parser.add_argument("game", help="MAME short name, for example hangon")
    parser.add_argument(
        "--mame-root",
        type=Path,
        default=os.environ.get("MAME_ROOT"),
        help="source MAME root (default: MAME_ROOT environment variable)",
    )
    parser.add_argument(
        "--executable",
        type=Path,
        default=os.environ.get("OPENHI2TXT") or shutil.which("openhi2txt"),
        help="openhi2txt executable (default: OPENHI2TXT or PATH)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="openhi2txt-xml root (default: inferred from this script)",
    )
    parser.add_argument(
        "--fixture-root",
        type=Path,
        help="fixture MAME root (default: <repo>/src/test/input)",
    )
    parser.add_argument(
        "--oracle-root",
        type=Path,
        help="oracle directory (default: <repo>/src/test/oracle)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace existing copied inputs and oracle files",
    )
    return parser.parse_args()


def load_structure_file_kinds(db_root: Path, game: str) -> tuple[Path, list[str]]:
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
        structures = root.findall("structure")
        if structures:
            kinds: list[str] = []
            seen: set[str] = set()
            for structure in structures:
                kind = (structure.get("file") or ".hi").strip()
                normalized = kind.casefold()
                if normalized not in seen:
                    seen.add(normalized)
                    kinds.append(kind)
            return xml_path, kinds

        sameas = root.find("sameas")
        if sameas is None:
            raise ValueError(f"{xml_path.name} has no structure or sameas target")
        target = (sameas.get("id") or sameas.text or "").strip()
        if not target:
            raise ValueError(f"{xml_path.name} has an empty sameas target")
        current = target

    raise ValueError(f"sameas chain exceeds 16 definitions while resolving {game}")


def referenced_inputs(
    mame_root: Path,
    fixture_root: Path,
    game: str,
    kinds: list[str],
) -> list[InputFile]:
    inputs: list[InputFile] = []
    for kind in kinds:
        normalized = kind.casefold()
        if normalized == "dif":
            raise ValueError(
                "DIF-backed definitions use tests/create_chd_fixture.py instead"
            )
        if normalized in {".hi", "hi"}:
            inputs.append(
                InputFile(
                    source=mame_root / "hiscore" / f"{game}.hi",
                    destination=fixture_root / "hi" / f"{game}.hi",
                    explicit=True,
                )
            )
        elif kind.startswith("."):
            inputs.append(
                InputFile(
                    source=mame_root / "hiscore" / f"{game}{kind}",
                    destination=fixture_root / "hi" / f"{game}{kind}",
                    explicit=True,
                )
            )
        else:
            inputs.append(
                InputFile(
                    source=mame_root / "nvram" / game / kind,
                    destination=fixture_root / "nvram" / game / kind,
                    explicit=False,
                )
            )
    return inputs


def copy_available_inputs(
    inputs: list[InputFile], force: bool
) -> tuple[list[InputFile], Path | None]:
    available = [item for item in inputs if item.source.is_file()]
    if not available:
        searched = "\n  ".join(str(item.source) for item in inputs)
        raise FileNotFoundError(f"none of the referenced input files exist:\n  {searched}")

    existing = [item.destination for item in available if item.destination.exists()]
    if existing and not force:
        raise FileExistsError(
            "fixture input already exists; use --force to replace: "
            + ", ".join(str(path) for path in existing)
        )

    explicit_input: Path | None = None
    for item in available:
        item.destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item.source, item.destination)
        if explicit_input is None and item.explicit:
            explicit_input = item.destination
    return available, explicit_input


def run_openhi2txt(
    executable: Path,
    repo_root: Path,
    fixture_root: Path,
    game: str,
    explicit_input: Path | None,
    xml_output: bool,
    include_debug: bool = True,
) -> str:
    command = [str(executable)]
    if xml_output:
        command.append("-xml")
    command.extend(
        [
            "-hiscoredat",
            str(repo_root / "src" / "test" / "hiscore.dat"),
            "-descr",
            str(repo_root / "src" / "main" / "db"),
            "--mame-root",
            str(fixture_root),
            "--game",
            game,
            "-rd" if include_debug else "-r",
            "-notrace",
        ]
    )
    if explicit_input is not None:
        command.append(str(explicit_input))

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"openhi2txt exited with {completed.returncode}:\n{completed.stderr.strip()}"
        )
    if completed.stderr.strip():
        raise RuntimeError(f"openhi2txt reported an error:\n{completed.stderr.strip()}")
    output = completed.stdout.strip()
    if not output:
        raise RuntimeError("openhi2txt produced empty output")
    return output + "\n"


def write_oracles(
    executable: Path,
    repo_root: Path,
    fixture_root: Path,
    oracle_root: Path,
    game: str,
    explicit_input: Path | None,
    force: bool,
) -> tuple[Path, Path]:
    text_path = oracle_root / f"{game}.txt"
    xml_path = oracle_root / f"{game}.xml"
    existing = [path for path in (text_path, xml_path) if path.exists()]
    if existing and not force:
        raise FileExistsError(
            "oracle already exists; use --force to replace: "
            + ", ".join(str(path) for path in existing)
        )

    text = run_openhi2txt(
        executable, repo_root, fixture_root, game, explicit_input, False
    )
    xml = run_openhi2txt(
        executable, repo_root, fixture_root, game, explicit_input, True
    )
    oracle_root.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text, encoding="utf-8", newline="\n")
    xml_path.write_text(xml, encoding="utf-8", newline="\n")
    return text_path, xml_path


def shape_from_root(root: ET.Element, description: str) -> tuple[TableShape, ...]:
    if root.tag != "hi2txt":
        raise ValueError(f"{description} has unexpected root element {root.tag!r}")
    return tuple(
        TableShape(
            table_id=table.get("id") or "",
            columns=tuple((column.text or "") for column in table.findall("col")),
        )
        for table in root.findall("table")
    )


def rendered_file_shape(path: Path) -> tuple[TableShape, ...]:
    return shape_from_root(ET.parse(path).getroot(), str(path))


def check_default(
    executable: Path,
    repo_root: Path,
    fixture_root: Path,
    game: str,
    explicit_input: Path | None,
) -> str:
    default_path = repo_root / "src" / "main" / "db_defaults" / f"{game}.xml"
    if not default_path.is_file():
        return f"Default: missing ({default_path}); review whether one should be added"

    normal_xml = run_openhi2txt(
        executable,
        repo_root,
        fixture_root,
        game,
        explicit_input,
        xml_output=True,
        include_debug=False,
    )
    normal_shape = shape_from_root(ET.fromstring(normal_xml), "normal OpenHi2txt output")
    default_shape = rendered_file_shape(default_path)
    if default_shape != normal_shape:
        raise ValueError(
            f"default table/column shape differs from normal OpenHi2txt output:\n"
            f"  default: {default_shape}\n"
            f"  output:  {normal_shape}"
        )
    return f"Default: compatible ({default_path})"


def main() -> int:
    args = parse_args()
    if args.mame_root is None:
        print("error: provide --mame-root or set MAME_ROOT", file=sys.stderr)
        return 2
    if not args.mame_root.is_dir():
        print(f"error: MAME root not found: {args.mame_root}", file=sys.stderr)
        return 2
    if args.executable is None:
        print(
            "error: provide --executable, set OPENHI2TXT, or put openhi2txt on PATH",
            file=sys.stderr,
        )
        return 2
    if not args.executable.is_file():
        print(f"error: openhi2txt executable not found: {args.executable}", file=sys.stderr)
        return 2

    repo_root = args.repo_root.resolve()
    fixture_root = (args.fixture_root or repo_root / "src" / "test" / "input").resolve()
    oracle_root = (args.oracle_root or repo_root / "src" / "test" / "oracle").resolve()
    try:
        definition, kinds = load_structure_file_kinds(
            repo_root / "src" / "main" / "db", args.game
        )
        inputs = referenced_inputs(args.mame_root.resolve(), fixture_root, args.game, kinds)
        copied, explicit_input = copy_available_inputs(inputs, args.force)
        text_path, xml_path = write_oracles(
            args.executable.resolve(),
            repo_root,
            fixture_root,
            oracle_root,
            args.game,
            explicit_input,
            args.force,
        )
        default_status = check_default(
            args.executable.resolve(),
            repo_root,
            fixture_root,
            args.game,
            explicit_input,
        )
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError, ET.ParseError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"Definition: {definition}")
    for item in copied:
        print(f"Input: {item.source} -> {item.destination}")
    print(f"Text oracle: {text_path}")
    print(f"XML oracle: {xml_path}")
    print(default_status)
    print("Review both oracle files before committing them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
