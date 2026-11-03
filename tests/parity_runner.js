// Runs the JavaScript engine on zips and prints {zip: {es: report, en: report}} as JSON.
const fs = require("fs");
const path = require("path");
const S = require(path.join(__dirname, "..", "web", "sentry.js"));
const rules = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "web", "rules.json"), "utf8"));
const engine = S.make(rules);
(async () => {
  const out = {};
  for (const file of process.argv.slice(2)) {
    const buf = fs.readFileSync(file);
    try {
      out[file] = { es: await engine.scanZip(buf, path.basename(file), "es"), en: await engine.scanZip(buf, path.basename(file), "en") };
    } catch (e) {
      out[file] = { error: e.message };
    }
  }
  process.stdout.write(JSON.stringify(out));
})();
