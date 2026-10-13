// Diagnostics: print only normalized quota fields, never account credentials.
const { readCodexUsage } = require("../codex-usage");
readCodexUsage().then((usage) => {
  console.log(JSON.stringify(usage, null, 2));
  if (usage.status !== "ready") process.exitCode = 1;
});
