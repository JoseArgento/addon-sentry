# Changelog

## Unreleased

- WeakAuras import strings: `addon-sentry --aura FILE|-` and a paste box on the page. Decodes `!WA:2!` (LibDeflate + LibSerialize), `!` (LibDeflate + AceSerializer) and pre-2018 strings (LibCompress LZW/Huffman + AceSerializer) without running anything, then scans every field WeakAuras compiles as code.
- New signal `AURA_BLOCKED`: aura code that uses something WeakAuras blocks in its sandbox.
- Automatic chat actions in auras (whisper, guild, raid...) count as "sends chat messages".
- Decoder tests against the real Lua libraries (optional, needs `lupa`); fixtures made by `tools/make_aura_fixtures.py`.

## 0.1.0 (2026-11-03)

First release.

- Python engine and CLI (`addon-sentry file.zip|folder`), Spanish and English.
- Browser page (`dist/index.html`) with a JavaScript port of the engine; the zip never leaves the device.
- Signals: remote code execution through chat or addon messages, obfuscated loaders, Blizzard money/confirmation overrides while moving gold, built API names, guild disbanding, profiling other players, executables, zip slip, encrypted and nested archives.
- Only code the game loads counts; inline "ignore" comments in scanned code are not honoured.
- Parity test: both engines must give identical reports on the same zips.
