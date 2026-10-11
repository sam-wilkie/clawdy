// daemon-bridge.js — makes the Electron pet speak the SAME TCP protocol the
// SDL2 simulator does, so the existing daemon connects to it WITHOUT any change.
//
// Role swap vs the SDL2 sim: identical. The simulator is a TCP *server*
// (`--listen <port>`), and the daemon is the *client* that connects to it and
// pushes newline-delimited JSON commands. This module reproduces that server.
//
// Commands we care about for animations (sent by the daemon → protocol.py):
//   {"action":"set_sessions","anims":[...],"ids":[...],"subagents":N}
//   {"action":"set_status","status":"idle|thinking|working_1|confused|..."}
//   {"action":"set_usage",...}  {"action":"add"/"dismiss"/"clear"}
//   {"action":"permission_request",...}  {"action":"permission_clear",...}
//   {"action":"set_window"/"show_window"/"hide_window"}
//   {"action":"read_config"}  (must reply with a JSON line)
//
// We forward every parsed command to a callback (the main process maps it to
// the renderer). read_config gets a minimal reply so the daemon's 2s wait
// resolves instead of timing out.

const net = require("net");

const SIM_DEFAULT_PORT = 19872;

/**
 * @param {(cmd: object) => void} onCommand  called for each JSON command line
 * @param {number} [port]
 * @returns {{ server: net.Server, close: () => void }}
 */
function startBridge(onCommand, port = SIM_DEFAULT_PORT, onLink = () => {}) {
  let socket = null;

  const server = net.createServer((conn) => {
    // One daemon connection at a time, like the sim.
    socket = conn;
    onLink(true);
    conn.setEncoding("utf8");
    let buf = "";

    conn.on("data", (chunk) => {
      buf += chunk;
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (!line) continue;
        let cmd;
        try {
          cmd = JSON.parse(line);
        } catch {
          continue; // drop malformed lines, like the sim does
        }
        // The daemon blocks up to 2s on read_config; answer with an empty
        // config so it proceeds (the pet has no device config to report).
        if (cmd && cmd.action === "read_config") {
          try {
            conn.write(JSON.stringify({ sleep_timeout: 0 }) + "\n");
          } catch { /* ignore */ }
          continue;
        }
        try {
          onCommand(cmd);
        } catch (e) {
          // A bad command must never kill the connection.
          console.error("[bridge] onCommand failed:", e);
        }
      }
    });

    conn.on("error", () => { /* daemon dropped; wait for reconnect */ });
    conn.on("close", () => { if (socket === conn) { socket = null; onLink(false); } });
  });

  server.on("error", (e) => {
    console.error("[bridge] server error:", e && e.message);
  });

  server.listen(port, "127.0.0.1", () => {
    console.log(`[bridge] listening on 127.0.0.1:${port} (sim-compatible)`);
  });

  return {
    server,
    // Send an event back to the daemon (e.g. a permission decision).
    sendEvent: (obj) => {
      if (socket && !socket.destroyed) {
        try { socket.write(JSON.stringify(obj) + "\n"); } catch { /* ignore */ }
      }
    },
    close: () => { try { server.close(); } catch { /* ignore */ } },
  };
}

module.exports = { startBridge, SIM_DEFAULT_PORT };
