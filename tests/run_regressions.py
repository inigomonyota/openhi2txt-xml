#!/usr/bin/env python3
"""Run the canonical openhi2txt golden-file regression suite."""

from __future__ import annotations

import argparse
import difflib
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TestCase:
    oracle: Path
    game: str
    output_format: str

    def label(self) -> str:
        return f"{self.game}.{self.output_format}"


@dataclass(frozen=True)
class TestResult:
    case: TestCase
    returncode: int
    expected: str
    actual: str
    stderr: str

    @property
    def passed(self) -> bool:
        return (
            self.returncode == 0
            and not self.stderr
            and self.actual == self.expected
        )


def parse_args() -> argparse.Namespace:
    default_jobs = min(4, os.cpu_count() or 1)
    parser = argparse.ArgumentParser(
        description="Compare openhi2txt output with its canonical stored baselines."
    )
    parser.add_argument(
        "--executable",
        required=True,
        type=Path,
        help="path to the openhi2txt executable",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="openhi2txt-xml repository root (default: inferred from this script)",
    )
    parser.add_argument(
        "--game",
        action="append",
        default=[],
        help="only test this game; repeat to select more than one",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=default_jobs,
        help=f"number of parallel converter processes (default: {default_jobs})",
    )
    return parser.parse_args()


def discover_cases(repo_root: Path, selected_games: set[str]) -> list[TestCase]:
    oracle_root = repo_root / "src" / "test" / "oracle"
    cases: list[TestCase] = []
    formats_by_game: dict[str, set[str]] = {}
    for oracle in sorted(oracle_root.iterdir()):
        if not oracle.is_file() or oracle.suffix not in {".txt", ".xml"}:
            continue
        game = oracle.stem
        if selected_games and game not in selected_games:
            continue
        output_format = oracle.suffix[1:]
        formats_by_game.setdefault(game, set()).add(output_format)
        cases.append(
            TestCase(
                oracle=oracle,
                game=game,
                output_format=output_format,
            )
        )

    incomplete = sorted(
        game
        for game, formats in formats_by_game.items()
        if formats != {"txt", "xml"}
    )
    if incomplete:
        raise ValueError(
            "games without both text and XML baselines: " + ", ".join(incomplete)
        )
    return cases


def run_case(executable: Path, repo_root: Path, case: TestCase) -> TestResult:
    input_root = repo_root / "src" / "test" / "input"
    input_path = input_root / "hi" / f"{case.game}.hi"
    conventional_dif = input_root / "diff" / f"{case.game}.dif"
    if conventional_dif.is_file():
        input_path = conventional_dif
    else:
        game_chd_dir = input_root / "roms" / case.game
        if game_chd_dir.is_dir():
            for chd in sorted(game_chd_dir.glob("*.chd")):
                disk_named_dif = input_root / "diff" / f"{chd.stem}.dif"
                if disk_named_dif.is_file():
                    input_path = disk_named_dif
                    break

    command = [str(executable)]
    if case.output_format == "xml":
        command.append("-xml")
    command.extend(
        [
            "-hiscoredat",
            str(repo_root / "src" / "test" / "hiscore.dat"),
            "-descr",
            str(repo_root / "src" / "main" / "db"),
            "--mame-root",
            str(input_root),
            "--game",
            case.game,
            "-rd",
            "-notrace",
            str(input_path),
        ]
    )
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return TestResult(
        case=case,
        returncode=completed.returncode,
        expected=case.oracle.read_text(encoding="utf-8").strip(),
        actual=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def escape_annotation(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def print_failure(result: TestResult, repo_root: Path) -> None:
    relative_oracle = result.case.oracle.relative_to(repo_root).as_posix()
    if result.returncode != 0:
        message = f"openhi2txt exited with {result.returncode}"
    elif result.stderr:
        message = "openhi2txt wrote an error"
    else:
        message = "output differs from the canonical baseline"

    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(
            f"::error file={relative_oracle},title=openhi2txt regression::"
            f"{escape_annotation(result.case.label() + ': ' + message)}"
        )

    print(f"\nFAIL {result.case.label()}: {message}")
    if result.stderr:
        print("stderr:")
        print(result.stderr)
    if result.actual != result.expected:
        diff = difflib.unified_diff(
            result.expected.splitlines(),
            result.actual.splitlines(),
            fromfile=f"expected/{result.case.label()}",
            tofile=f"actual/{result.case.label()}",
            lineterm="",
        )
        for index, line in enumerate(diff):
            if index == 120:
                print("... diff truncated after 120 lines")
                break
            print(line)


def write_job_summary(total: int, failures: list[TestResult], elapsed: float) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = [
        "## openhi2txt regression results",
        "",
        "| Result | Count |",
        "| --- | ---: |",
        f"| Passed | {total - len(failures)} |",
        f"| Failed | {len(failures)} |",
        f"| Total | {total} |",
        "",
        f"Completed in {elapsed:.1f} seconds.",
    ]
    if failures:
        lines.extend(["", "### Failures", ""])
        lines.extend(f"- `{result.case.label()}`" for result in failures)
    with open(summary_path, "a", encoding="utf-8") as summary:
        summary.write("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    executable = args.executable.resolve()
    repo_root = args.repo_root.resolve()

    if args.jobs < 1:
        print("error: --jobs must be at least 1", file=sys.stderr)
        return 2
    if not executable.is_file():
        print(f"error: executable not found: {executable}", file=sys.stderr)
        return 2
    if not (repo_root / "src" / "test" / "hiscore.dat").is_file():
        print("error: src/test/hiscore.dat was not found", file=sys.stderr)
        return 2

    try:
        cases = discover_cases(repo_root, set(args.game))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if not cases:
        selection = f" for: {', '.join(args.game)}" if args.game else ""
        print(f"error: no oracle files found{selection}", file=sys.stderr)
        return 2

    print(f"Running {len(cases)} openhi2txt checks with {args.jobs} workers...")
    started = time.monotonic()
    results: list[TestResult] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = [executor.submit(run_case, executable, repo_root, case) for case in cases]
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda result: result.case.label())
    failures = [result for result in results if not result.passed]
    elapsed = time.monotonic() - started
    for result in failures:
        print_failure(result, repo_root)
    write_job_summary(len(results), failures, elapsed)

    passed = len(results) - len(failures)
    print(f"\nResult: {passed}/{len(results)} passed in {elapsed:.1f}s")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
