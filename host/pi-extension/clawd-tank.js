// Clawd Tank extension for Pi (gentle-shell).
//
// Copied to <agent-dir>/extensions/clawd-tank.js by hooks.install_pi_hooks().
// It forwards Pi lifecycle and tool events to the Clawd Tank daemon by running
// the notify command with the agent argument "pi" and the raw payload on stdin.
// Pi runs tools without approval, so the extension only reports them; it never
// asks the pet for permission (that popped a bubble on every bash/write/edit).
// Everything here is fire-and-forget and must never throw into Pi.

import { spawn } from "node:child_process"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const COMMAND_FILE = join(dirname(fileURLToPath(import.meta.url)), "clawd-tank.command")

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

// Runs the notify command with `payload` on stdin. Never rejects.
function send(payload) {
  return new Promise((resolve) => {
    try {
      const command = notifyCommand()
      if (!command) return resolve()
      const child = spawn(`${command} pi`, {
        shell: true,
        windowsHide: true,
        stdio: ["pipe", "ignore", "ignore"],
      })
      const timer = setTimeout(() => {
        try { child.kill() } catch {}
        resolve()
      }, 5000)
      child.on("error", () => { clearTimeout(timer); resolve() })
      child.on("close", () => { clearTimeout(timer); resolve() })
      child.stdin.on("error", () => {})
      child.stdin.end(JSON.stringify(payload))
    } catch {
      resolve()
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

  pi.on("tool_call", (evt, ctx) => {
    send({ ...base("tool_call", ctx), tool: evt.toolName || "" }).catch(() => {})
  })

  pi.on("tool_result", (evt, ctx) => {
    send({ ...base("tool_result", ctx), tool: evt.toolName || "" }).catch(() => {})
  })
}
