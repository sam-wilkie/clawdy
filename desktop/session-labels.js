// User labels affect display only; agent identity and source project stay intact.
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

function labelSessions(sessions, file = path.join(os.homedir(), ".clawd-tank", "session-labels.json")) {
  let labels;
  try { labels = JSON.parse(fs.readFileSync(file, "utf8")); } catch { return sessions; }
  return sessions.map((session) => {
    const label = labels?.[session.agent]?.[session.project];
    return typeof label === "string" && label.trim()
      ? { ...session, project: label.trim() } : session;
  });
}

module.exports = { labelSessions };
