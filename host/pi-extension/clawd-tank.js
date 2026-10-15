// Clawd Tank extension for Pi (gentle-shell).
//
// Copied to <agent-dir>/extensions/clawd-tank.js by hooks.install_pi_hooks().
// It forwards Pi lifecycle and tool events to the Clawd Tank daemon by running
// the notify command with the agent argument "pi" and the raw payload on stdin.
// Permission prompts wait for the pet's decision and block the tool call on deny.
// Everything here is fire-and-forget and must never throw into Pi.

import { spawn } from "node:child_process"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const COMMAND_FILE = join(dirname(fileURLToPath(import.meta.url)), "clawd-tank.command")
const PERMISSION_WAIT_MS = 22000
const TOOLS_NEEDING_APPROVAL = new Set(["bash", "write", "edit"])

let cachedCommand
function notifyCommand() {
  if (cachedCommand !== undefined) return cachedCommand
  try {
    cachedCommand = readFileSync(COMMAND_FILE, "utf8").trim() || null
  } catch {
    cachedCommand = null
  }
  return cachedCommand
}

// Runs the notify command with `payload` on stdin. Resolves with stdout (only
// collected when `wait` is true) and never rejects.
function send(payload, wait = false) {
  return new Promise((resolve) => {
    try {
      const command = notifyCommand()
      if (!command) return resolve("")
      const child = spawn(`${command} pi`, {
        shell: true,
        windowsHide: true,
        stdio: ["pipe", wait ? "pipe" : "ignore", "ignore"],
      })
      let out = ""
      const timer = setTimeout(() => {
        try { child.kill() } catch {}
        resolve("")
      }, wait ? PERMISSION_WAIT_MS : 5000)
      if (wait) child.stdout.on("data", (d) => { out += d })
      child.on("error", () => { clearTimeout(timer); resolve("") })
      child.on("close", () => {
        clearTimeout(timer)
        resolve(out)
      })
      child.stdin.on("error", () => {})
      child.stdin.end(JSON.stringify(payload))
    } catch {
      resolve("")
    }
  })
}

function base(event, ctx) {
  return {
    type: event,
    sessionID: ctx?.sessionManager?.getSessionId?.() || ctx?.sessionManager?.getSessionFile?.() || "",
    directory: ctx?.cwd || "",
  }
}

export default function (pi) {
  const forward = (event, extra = {}) => (evt, ctx) => {
    send({ ...base(event, ctx), ...extra }).catch(() => {})
  }

  pi.on("session_start", forward("session_start"))
  pi.on("agent_start", forward("agent_start"))
  pi.on("turn_end", forward("turn_end"))
  pi.on("session_shutdown", forward("session_shutdown"))

  pi.on("tool_call", async (evt, ctx) => {
    try {
      const tool = evt.toolName || ""
      if (!TOOLS_NEEDING_APPROVAL.has(tool)) {
        await send({ ...base("tool_call", ctx), tool })
        return undefined
      }
      const out = await send({ ...base("permission", ctx), tool, args: evt.input }, true)
      let decision = "none"
      try { decision = JSON.parse(out).decision || "none" } catch {}
      if (decision === "deny") {
        return { block: true, reason: "Denied from the Clawd Tank pet" }
      }
      return undefined
    } catch {
      return undefined
    }
  })

  pi.on("tool_result", (evt, ctx) => {
    send({ ...base("tool_result", ctx), tool: evt.toolName || "" }).catch(() => {})
  })
}
