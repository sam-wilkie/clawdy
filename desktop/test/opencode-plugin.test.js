const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

test("OpenCode v2 setup forwards resumed prompts and tools, filters children and unloads", async (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "clawdy-opencode-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const output = path.join(dir, "events.jsonl");
  const recorder = path.join(dir, "record.cjs");
  fs.writeFileSync(recorder, `const fs=require('fs');let raw='';process.stdin.on('data',d=>raw+=d);process.stdin.on('end',()=>fs.appendFileSync(${JSON.stringify(output)},JSON.stringify({agent:process.argv[2],...JSON.parse(raw)})+'\\n'));`);
  fs.writeFileSync(path.join(dir, "clawd-tank.command"), `"${process.execPath}" "${recorder}"`);
  const moduleFile = path.join(dir, "plugin.mjs");
  fs.copyFileSync(path.join(__dirname, "../../host/opencode-plugin/clawd-tank-opencode.js"), moduleFile);
  const { default: plugin, ClawdTankPlugin } = await import(pathToFileURL(moduleFile).href);
  let heartbeat;
  let timerCleared = false;
  t.mock.method(global, "setInterval", callback => { heartbeat = callback; return { unref() {} }; });
  t.mock.method(global, "clearInterval", () => { timerCleared = true; });
  assert.equal(typeof ClawdTankPlugin, "function");
  const hooks = new Map();
  let subscriptionSignal;
  let streamDone;
  const streamed = new Promise(resolve => { streamDone = resolve; });
  const context = {
    location: { directory: "C:/projects/real-opencode" },
    session: { async hook(name, handler) { hooks.set(`session/${name}`, handler); } },
    tool: { async hook(name, handler) { hooks.set(`tool/${name}`, handler); } },
    event: { async *subscribe({ signal }) {
      subscriptionSignal = signal;
      yield { type: "session.created", data: { sessionID: "child", parentID: "parent" } };
      yield { type: "session.created", data: { sessionID: "new" } };
      yield { type: "session.updated", data: { sessionID: "new" } };
      yield { type: "session.idle", data: { sessionID: "new" } };
      streamDone();
    } },
  };
  const unload = await plugin.setup(context);
  await streamed;
  await hooks.get("session/prompt")({ sessionID: "restored" });
  await hooks.get("tool/execute.before")({ sessionID: "restored", tool: "bash" });
  await hooks.get("tool/execute.after")({ sessionID: "restored", tool: "bash" });
  await hooks.get("tool/execute.before")({ sessionID: "child", tool: "bash" });
  const rows = fs.readFileSync(output, "utf8").trim().split("\n").map(JSON.parse);
  assert.deepEqual(rows.map(row => row.type), ["session.created", "session.idle", "chat.message", "tool.execute.before", "tool.execute.after"]);
  assert.ok(rows.every(row => row.agent === "opencode" && row.directory === context.location.directory));
  assert.ok(!rows.some(row => row.sessionID === "child"));
  await heartbeat();
  const refreshed = fs.readFileSync(output, "utf8").trim().split("\n").map(JSON.parse).filter(row => row.type === "session.heartbeat");
  assert.deepEqual(refreshed.map(row => [row.sessionID, row.state]), [["new", "waiting"], ["restored", "working"]]);
  unload();
  assert.equal(subscriptionSignal.aborted, true);
  assert.equal(timerCleared, true);
  await heartbeat();
  assert.equal(fs.readFileSync(output, "utf8").trim().split("\n").length, 7);
});
