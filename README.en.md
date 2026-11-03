# Addon Sentry

Check a World of Warcraft addon **before you install it**. It reads the addon's Lua code without running it and warns about backdoors, tricks that move your gold, hidden code and files that should not be there.

- **Web page** (`dist/index.html`, one file): drop the zip, it is checked inside the browser and never uploaded.
- **Command line**: `pip install addon-sentry`, then `addon-sentry file.zip` or `addon-sentry folder/` (`--lang en`, `--format json`, `--fail-on high`).

It separates what an addon **can do** (many legitimate addons move gold or send messages) from **warning signs**: code that runs messages from other players, obfuscated code that gets run, Blizzard money/confirmation functions replaced while moving gold, sensitive function names built piece by piece, executables, zip-slip paths, guild disbanding, collecting other players' statistics.

Only code the game loads counts (files listed by `.toc`/`.xml`, including inline XML scripts). The scanner ignores "ignore" comments inside the code it scans. The Python and JavaScript engines are checked against each other on the same zips, including eight popular addons.

It is an automatic pattern check: it cannot prove an addon is safe, and a warning is not proof of bad intent. Not affiliated with Blizzard Entertainment. MIT license.
