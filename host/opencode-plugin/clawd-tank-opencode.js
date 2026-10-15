// Margarita Tank plugin for OpenCode.
//
// Copied to <opencode config>/plugins/clawd-tank.js by hooks.install_opencode_hooks().
// It forwards OpenCode lifecycle events to the Clawd Tank daemon by running the
// same notify command the Claude Code / Codex / Kiro hooks use, with the agent
// argument "opencode" and the raw payload on stdin. The notify script translates
// it (see clawd_tank_daemon/opencode_protocol.py) and sends it to the daemon.
//
// The notify command line is read from "clawd-tank.command" next to this file,
// written by the installer (it differs between a source run and a packaged build).
// Everything here is fire-and-forget and must never throw into OpenCode.

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

// Runs the notify command with `payload` on stdin. Resolves with stdout (only
// collected when `wait` is true) and never rejects.
function send(payload, wait = false) {
  return new Promise((resolve) => {
    try {
      const command = notifyCommand()
      if (!command) return resolve("")
      const child = spawn(`${command} opencode`, {
        shell: true,
        windowsHide: true,
        stdio: ["pipe", wait ? "pipe" : "ignore", "ignore"],
      })
      let out = ""
      // Permission waits end when the bridge answers or the host cancels it.
      const timer = wait ? null : setTimeout(() => {
        try { child.kill() } catch {}
        resolve("")
      }, 5000)
      if (wait) child.stdout.on("data", (d) => { out += d })
      child.on("error", () => { clearTimeout(timer); resolve("") })
      child.on("close", () => {
        if (timer) clearTimeout(timer)
        resolve(out)
      })
      child.stdin.on("error", () => {})
      child.stdin.end(JSON.stringify(payload))
    } catch {
      resolve("")
    }
  })
}

export const ClawdTankPlugin = async ({ directory }) => {
  const dir = directory || ""
  return {
    event: async ({ event }) => {
      try {
        const info = (event && event.properties && event.properties.info) || {}
        if (event.type === "session.created" || event.type === "session.deleted") {
          await send({ type: event.type, sessionID: info.id, directory: info.directory || dir })
        }
      } catch {}
    },

    "tool.execute.before": async (input) => {
      try {
        await send({ type: "tool.execute.before", sessionID: input.sessionID, tool: input.tool, directory: dir })
      } catch {}
    },

    "tool.execute.after": async (input) => {
      try {
        await send({ type: "tool.execute.after", sessionID: input.sessionID, tool: input.tool, directory: dir })
      } catch {}
    },

    "experimental.session.compacting": async (input) => {
      try {
        await send({ type: "experimental.session.compacting", sessionID: input.sessionID, directory: dir })
      } catch {}
    },

    // Desk approval: the pet answers Allow / Deny. No answer leaves OpenCode's
    // own prompt untouched.
    "permission.ask": async (input, output) => {
      try {
        const stdout = await send(
          {
            type: "permission.ask",
            sessionID: input.sessionID,
            tool: input.type,
            args: input.metadata,
            directory: dir,
          },
          true,
        )
        const line = stdout.split("\n").find((l) => l.trim())
        const behavior = line && JSON.parse(line)?.hookSpecificOutput?.decision?.behavior
        if (behavior === "allow" || behavior === "deny") output.status = behavior
      } catch {}
    },
  }
}

// OpenCode 2 uses a setup object, location.directory, scoped hooks and a
// public event subscription. Keep the named v1 export for older hosts.
async function setup(ctx) {
  const directory = ctx.location?.directory || ""
  const controller = new AbortController()
  const children = new Set()
  const known = new Set()
  const snapshots = new Map()
  const forward = (type, input) => {
    const sessionID = input?.sessionID
    if (!sessionID || children.has(sessionID)) return Promise.resolve()
    if (type !== "session.deleted") known.add(sessionID)
    if (type === "session.deleted") snapshots.delete(sessionID)
    else if (type === "chat.message") snapshots.set(sessionID, { state: "thinking" })
    else if (type.startsWith("tool.execute.")) snapshots.set(sessionID, { state: "working", tool: input.tool })
    else if (type === "session.idle") snapshots.set(sessionID, { state: "waiting" })
    else if (!snapshots.has(sessionID)) snapshots.set(sessionID, { state: "registered" })
    return send({ type, sessionID, directory, tool: input.tool })
  }
  await ctx.session.hook("prompt", (event) => forward("chat.message", event))
  await ctx.tool.hook("execute.before", (event) => forward("tool.execute.before", event))
  await ctx.tool.hook("execute.after", (event) => forward("tool.execute.after", event))
  await ctx.session.hook("compaction", (event) => forward("experimental.session.compacting", event))
  void (async () => {
    try {
      for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
        if (controller.signal.aborted) break
        const data = event.data || {}
        const sid = data.sessionID
        if (!sid) continue
        if (event.type === "session.created" && data.parentID) {
          children.add(sid)
          snapshots.delete(sid)
          continue
        }
        if (children.has(sid)) {
          if (event.type === "session.deleted") children.delete(sid)
          continue
        }
        if (event.type === "session.created" || event.type === "session.updated") {
          if (!known.has(sid)) {
            known.add(sid)
            await forward("session.created", data)
          }
        } else if (event.type === "session.deleted") {
          known.delete(sid)
          await forward("session.deleted", data)
        } else if (event.type === "session.idle") {
          await forward("session.idle", data)
        } else if (event.type === "session.status" && data.status?.type === "idle") {
          await forward("session.idle", data)
        }
      }
    } catch {
      // Closing/unloading the host aborts its event stream.
    }
  })()
  // A quiet conversation is still open. Refresh only sessions observed by this
  // plugin, and resend their snapshot so a restarted daemon can recover them.
  let refreshing = false
  const timer = setInterval(async () => {
    if (refreshing || controller.signal.aborted) return
    refreshing = true
    try {
      for (const [sessionID, snapshot] of snapshots) {
        if (controller.signal.aborted) break
        await send({ type: "session.heartbeat", sessionID, directory, ...snapshot })
      }
    } finally { refreshing = false }
  }, 30000)
  timer.unref?.()
  return () => { clearInterval(timer); controller.abort() }
}

export default { id: "clawd-tank", setup }
