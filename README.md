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

[openhi2txt](https://github.com/inigomontoya/openhi2txt) is an independently developed replacement for the original hi2txt extraction engine.

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

The exact command-line options and supported directory layouts are documented in the [openhi2txt repository](https://github.com/inigomontoya/openhi2txt).

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

Test inputs and expected output may be stored under:

```text
src/test/
```

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

Definition changes should be tested against representative binary fixtures and expected output.

A regression test should ideally verify:

- that the XML parses successfully
- that the correct input file is selected
- that fields are decoded correctly
- that sorting and filtering produce the expected rows
- that openhi2txt-specific extensions do not change legacy behavior
- that generated output matches the stored expected result

GitHub Actions may be used to run these tests automatically on pushes and pull requests.

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
