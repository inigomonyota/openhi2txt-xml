<!--
  Modified for the openhi2txt project on 2026-08-02.
  This repository is derived from GreatStoneEx/hi2txt-xml.
-->

# openhi2txt-xml

Game-specific XML definitions used by **openhi2txt** to extract high-score tables from MAME `.hi`, NVRAM, EEPROM, and other persistent files.

![Score extraction](scores.png)

## Introduction

MAME stores high-score data in several ways. Depending on the game, scores may be found in:

- `.hi` files created by MAME's hiscore plugin
- NVRAM files written directly by the emulated game
- EEPROM, save RAM, or other persistent files within a game's NVRAM directory

The XML definitions in this repository describe how to convert that binary data into human-readable or machine-readable high-score tables.

Each game definition contains:

- a **structure** describing how values are extracted and decoded from the binary input
- an **output** describing how those values are arranged and displayed

The definitions may specify details such as:

- binary offsets and field sizes
- integer, hexadecimal, BCD, and text decoding
- character mappings
- byte, nibble, and bit transformations
- loops and indexed table rows
- sorting, filtering, formatting, and calculated fields
- multiple tables or multiple persistent input files

The goal is to allow frontends, launchers, leaderboard systems, websites, and other third-party software to read high scores without requiring game-specific parsing code in the application itself.

Scoring is the heart of the Arcade World!

## About openhi2txt

[openhi2txt](https://github.com/inigomonyota/openhi2txt) is an independently developed replacement for the original hi2txt extraction engine.

It is intended to remain compatible with existing XML definitions written for the original hi2txt format while adding support for:

- additional binary transformations
- more flexible input-file discovery
- multiple tables and persistent data sources
- stricter definition selection and validation
- data layouts that cannot be represented by the original engine

This repository is maintained separately from the openhi2txt engine because the definition database and the extraction engine have different development cycles.

New games and revisions to existing games can be added without requiring changes to the engine.

## Compatibility

openhi2txt is intended to remain compatible with existing XML definitions written for the original hi2txt format.

This repository may also contain definitions using openhi2txt-specific extensions. These extensions are used only when a game's data cannot be accurately represented using the original XML syntax.

Definitions that use only the original syntax may remain usable with the original Java or C# hi2txt engines. Definitions using openhi2txt extensions require openhi2txt.

The openhi2txt XML format is therefore intended to be a backward-compatible superset of the original format:

```text
hi2txt XML definitions ⊂ openhi2txt XML definitions
```

Existing attribute meanings and default behavior should not change when openhi2txt extensions are absent.

## Setup

A definition release contains `hi2txt.zip` and may also include:

- `hi2txt_defaults.zip`, containing default high-score output files
- a version or changelog file identifying the release

### Using with openhi2txt

Place `hi2txt.zip` in a convenient location and pass it to openhi2txt using the `--defs` option.

For example:

```text
openhi2txt --defs hi2txt.zip --mame-root <path> --game <name>
```

Definitions may also be used directly from the unpacked `src/main/db` directory during development and testing.

A typical installation may look like:

```text
openhi2txt/
├── openhi2txt.exe
├── hi2txt.zip
└── mame/
    ├── hiscore/
    └── nvram/
```

The exact command-line options and supported directory layouts are documented in the [openhi2txt repository](https://github.com/inigomonyota/openhi2txt).

### Using with the original hi2txt engine

Definitions that use only the original hi2txt XML syntax may still be used with the original Java or C# hi2txt engines.

For those engines, the release files are normally placed in the directory containing the hi2txt executable, replacing the older bundled definition archives when appropriate.

Definitions using openhi2txt-specific extensions may not be readable by the original hi2txt engines.

### Development setup

Clone the repository and use the unpacked definitions from:

```text
src/main/db/
```

New or modified definitions should be tested against representative `.hi`, NVRAM, EEPROM, or save files before being committed.

The repository may provide its own scripts or GitHub Actions workflows for:

- XML and DTD validation
- openhi2txt regression testing
- comparison with expected output
- packaging `hi2txt.zip`

## Repository layout

Game definitions and the DTD are stored in:

```text
src/main/db/
```

Default high-score output files are stored in:

```text
src/main/db_defaults/
```

The canonical openhi2txt regression corpus is stored under:

```text
src/test/
├── hiscore.dat
├── input/
│   ├── hi/
│   ├── nvram/
│   ├── diff/
│   └── roms/
└── oracle/
```

There is one undated text/XML baseline per tested game. The bundled `hiscore.dat` is a snapshot of the current file from the official MAME repository.

### Creating compact CHD regression fixtures

`tests/create_chd_fixture.py` creates a compact parent-CHD/DIF pair for a
DIF-backed definition. It reads the definition's real `offset` and `length`
attributes, extracts only those logical byte ranges from the real parent and
merged disks, preserves their absolute offsets in sparse synthetic raw images,
and uses MAME's `chdman` to create the fixture pair.

Set the two machine-specific tool paths once:

```powershell
$env:MAME_ROOT = "E:\path\to\mame"
$env:CHDMAN = "C:\path\to\chdman.exe"
```

The game name is then the only required argument:

```powershell
python tests/create_chd_fixture.py kinst
```

The generated files are placed in the production-shaped test layout:

```text
src/test/input/roms/kinst/kinst.chd
src/test/input/diff/kinst.dif
```

The complete real CHD, complete real DIF, and temporary raw images are never
copied into the repository; only the XML-selected logical byte ranges are
retained inside the compact fixture pair. Existing fixture files are preserved
unless `--force` is supplied.

### Adding normal `.hi` and NVRAM regression fixtures

`tests/create_regression_fixture.py` copies the files referenced by a game's
definition from a real MAME installation and creates both canonical oracle
formats with OpenHi2txt. Configure the machine-specific paths once:

```powershell
$env:MAME_ROOT = "E:\path\to\mame"
$env:OPENHI2TXT = "C:\path\to\openhi2txt.exe"
```

The game name is then the only required argument:

```powershell
python tests/create_regression_fixture.py hangon
```

The script follows `sameas` definitions, copies every available `.hi` or NVRAM
file referenced by the effective structures, and writes:

```text
src/test/input/hi/hangon.hi
src/test/oracle/hangon.txt
src/test/oracle/hangon.xml
```

For NVRAM definitions, referenced files retain their path beneath
`src/test/input/nvram/<game>/`. Existing fixtures and oracles are preserved
unless `--force` is supplied. The command also checks for
`src/main/db_defaults/<game>.xml`: an existing default must be well-formed and
have the same table IDs and columns as the generated XML oracle, while a
missing default produces a visible review reminder. Defaults remain
repository-owned data and are never generated or interpreted by OpenHi2txt.
Both generated oracle files should be reviewed before committing them.

## Technologies

- XML
- DTD
- Git
- GitHub
- openhi2txt

The original repository included Gradle-based testing and packaging tools. This fork may use its own validation, regression-testing, and packaging workflow instead.

Gradle is not required to use the XML definitions with openhi2txt.

## Contributing

Contributions are welcome, including:

- definitions for unsupported games
- corrections to existing definitions
- support for additional game revisions or clones
- improved character sets and decoding profiles
- test files and expected output
- documentation corrections
- proposals for general-purpose XML extensions

A useful contribution should include as much supporting information as possible:

- the MAME game name
- the source `.hi`, NVRAM, EEPROM, or save file
- a screenshot of the in-game high-score table
- the expected extracted output
- notes about offsets, encoding, or transformations
- whether the definition requires an openhi2txt extension

Problems involving missing or corrupt `.hi` or NVRAM files may originate in MAME, its hiscore plugin, or `hiscore.dat` rather than in the XML definition itself.

## Testing

This repository uses a dependency-free Python regression runner instead of Gradle. GitHub Actions builds the current `openhi2txt` `main` branch with CMake, then compares every stored text and XML baseline with fresh converter output.

The baselines belong to openhi2txt itself. They were generated by openhi2txt using the latest available input fixture for each game and the current official MAME `hiscore.dat`; they do not preserve output compatibility with the original Java or C# hi2txt engines.

To run the full suite locally, build openhi2txt first and run this command from the repository root:

```text
python tests/run_regressions.py --executable <path-to-openhi2txt>
```

To focus on one or more games, repeat `--game`:

```text
python tests/run_regressions.py --executable <path-to-openhi2txt> --game galaga88
```

A regression test should ideally verify:

- that the XML parses successfully
- that the correct input file is selected
- that fields are decoded correctly
- that sorting and filtering produce the expected rows
- that generated output matches the stored expected result

GitHub Actions runs these tests automatically on pushes and pull requests. A manual run may target a different openhi2txt branch, tag, or commit.

## Original project

This repository is derived from:

**GreatStoneEx/hi2txt-xml**

The original project established the XML-based hi2txt definition format and assembled a large database of game-specific descriptions.

The original repository described these files as the game-specific data used by the Java hi2txt engine and its C# port.

Existing copyright notices, license notices, attribution, and contributor history are retained.

## Original contributors

The original project credited the following people for contributing XML definitions:

- Thomas B.
- Samuli T.
- Jason P.
- Piergiorgio G.
- William L.

Additional contributors to this fork should be credited through Git history and may also be listed here.

## Inspiration

The original hi2txt project took inspiration from the defunct [HiToText](https://sourceforge.net/projects/hitotext/) project and its [alternate repository](https://github.com/Fyrecrypts/HiToText).

HiToText relied on game-specific processing implemented directly in the engine. The hi2txt XML format moved that knowledge into external descriptive files, making it possible to support additional games without recompiling the extraction engine.

openhi2txt continues that approach while extending the descriptive format where necessary.

## License

This repository is distributed under the **GNU General Public License version 2**.

See [LICENSE](LICENSE) for the complete license text.

This fork retains the licensing and attribution of the original `hi2txt-xml` repository. Modified files should include a notice identifying that they were changed and the date of the modification.

![License](https://img.shields.io/badge/license-GPL--2.0-blue.svg)
