// Print only normalized usage fields for diagnostics.
const { readAgentUsage } = require("../agent-usage");
(async () => {
  const agents = process.argv.slice(2);
  for (const agent of agents.length ? agents : ["claude", "kiro", "opencode", "antigravity"]) {
    const usage = await readAgentUsage(agent);
    console.log(JSON.stringify({ agent, ...usage }));
    if (usage.status !== "ready") process.exitCode = 1;
  }
})();
