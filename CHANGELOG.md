# Changelog

## 0.2.0 (2026-11-04)

- **Does it load in Forever?** Every addon report says what its TOC declares: loads in Forever (Interface 1.60.x in the TOC Forever picks: `_Camelot`, `_Forever`, `_Mainline`, plain), not a Forever build (with the version it is for), Forever will not list it (no TOC named after the folder, with the folder name to use), excluded on purpose, or no Interface line. `## Interface-Forever`/`-Camelot`/`-Mainline` win over `## Interface`. Informational: never changes the verdict.
- **One verdict per addon** for a folder or zip that holds several addons (a whole `AddOns` folder): a table (addon · version · verdict · Forever · can do) and the details of each one. The top verdict is the worst of the set; multi-file signals no longer mix across addons. The page takes a folder too ("Choose AddOns folder" or drop it); everything stays in the browser.
- JSON: new `forever` object per report; multi-addon reports have `multi: true`, `summary` and `reports`.
- Tests: fixtures for a Classic-only build, `## Interface-Forever`, and a mixed `AddOns` folder; parity on them; `tests/test_page.py` drives the page in Chromium.

## 0.1.0 (2026-11-04)

First release.

- Scans an addon (zip or folder) without running it: what it **can do** (move gold, send messages, load code...) and **warning signs** (code run from other players' messages, obfuscated code that gets run, replaced money/confirmation functions, names built piece by piece, executables, zip-slip paths, guild disbanding, collecting other players' statistics).
- Web page (one file, nothing uploaded) and command line (`pip install addon-sentry`), with the same engine in Python and JavaScript and parity tests on 8 real addons.
- WeakAuras import strings: `--aura FILE|-` and a paste box on the page. Decodes `!WA:2!`, the 2019-2020 `!` format and pre-2018 strings without running anything, scans every field WeakAuras compiles as code, counts automatic chat actions, and flags code that uses what WeakAuras blocks. Decoders checked against the real Lua libraries and 135 public strings.
- Spanish and English output.
