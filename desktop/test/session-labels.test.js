const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { labelSessions } = require("../session-labels");

test("a user label changes only the selected agent/project, preserving source data", (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "clawdy-labels-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "labels.json");
  fs.writeFileSync(file, JSON.stringify({ claude: { opencode: "Terminal · permisos de OpenCode" } }));
  const sessions = [{ agent: "claude", project: "opencode", state: "working" },
    { agent: "opencode", project: "opencode", state: "thinking" }];
  const labeled = labelSessions(sessions, file);
  assert.equal(labeled[0].project, "Terminal · permisos de OpenCode");
  assert.equal(labeled[0].agent, "claude");
  assert.deepEqual(labeled[1], sessions[1]);
  assert.equal(sessions[0].project, "opencode");
  fs.writeFileSync(file, "invalid json");
  assert.deepEqual(labelSessions(sessions, file), sessions);
});
