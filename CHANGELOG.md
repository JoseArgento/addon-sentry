# Changelog

## 0.1.0 (2026-11-04)

First release.

- Scans an addon (zip or folder) without running it: what it **can do** (move gold, send messages, load code...) and **warning signs** (code run from other players' messages, obfuscated code that gets run, replaced money/confirmation functions, names built piece by piece, executables, zip-slip paths, guild disbanding, collecting other players' statistics).
- Web page (one file, nothing uploaded) and command line (`pip install addon-sentry`), with the same engine in Python and JavaScript and parity tests on 8 real addons.
- WeakAuras import strings: `--aura FILE|-` and a paste box on the page. Decodes `!WA:2!`, the 2019-2020 `!` format and pre-2018 strings without running anything, scans every field WeakAuras compiles as code, counts automatic chat actions, and flags code that uses what WeakAuras blocks. Decoders checked against the real Lua libraries and 135 public strings.
- Spanish and English output.
