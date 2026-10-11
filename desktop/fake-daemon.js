// fake-daemon.js — stands in for the real daemon to verify the pet's TCP bridge.
//
// It connects to the pet (which listens on 127.0.0.1:19872 like the SDL2 sim)
// and sends the SAME newline-delimited JSON commands protocol.py produces:
//   {"action":"set_sessions","anims":[...],"ids":[...],"subagents":N}
//
// Run the pet first (pnpm start), then: node fake-daemon.js
// You should see the pet's debug label cycle through the state names.

const net = require("net");

const PORT = Number(process.env.CLAWDY_PORT) || 19872;
const HOST = "127.0.0.1";

// A short script of states, like a real Claude session would drive.
// Covers every animation the pet now supports.
const SCRIPT = [
  { anims: ["wake"], ids: ["s1"], subagents: 0 },
  { anims: ["thinking"], ids: ["s1"], subagents: 0 },
  { anims: ["typing"], ids: ["s1"], subagents: 0 },
  { anims: ["building"], ids: ["s1"], subagents: 0 },
  { anims: ["debugger"], ids: ["s1"], subagents: 0 },
  { anims: ["conducting"], ids: ["s1"], subagents: 2 },
  { anims: ["beacon"], ids: ["s1"], subagents: 0 },
  { anims: ["sweeping"], ids: ["s1"], subagents: 0 },
  { anims: ["confused"], ids: ["s1"], subagents: 0 },
  { anims: ["dizzy"], ids: ["s1"], subagents: 0 },
  { anims: ["hat_mishap"], ids: ["s1"], subagents: 0 },
  { anims: ["notification"], ids: ["s1"], subagents: 0 },
  { anims: ["waiting_reply"], ids: ["s1"], subagents: 0 },
  { anims: ["low_battery"], ids: ["s1"], subagents: 0 },
  { anims: ["happy"], ids: ["s1"], subagents: 0 },
  { anims: ["sleeping"], ids: ["s1"], subagents: 0 },
  { anims: ["idle"], ids: ["s1"], subagents: 0 },
];

const sock = net.createConnection({ host: HOST, port: PORT }, () => {
  console.log(`[fake-daemon] connected to pet at ${HOST}:${PORT}`);

  // Optional: `node fake-daemon.js <state>` holds a single state so you can
  // watch one animation's full loop (some loops are up to 12s long).
  // `node fake-daemon.js scenario` walks the pet-side states:
  // walking, idea, typing, grooving, juggling, error, happy, going_away, then disconnects.
  const only = process.argv[2];
  if (only === "scenario") {
    const S = (anims, ids, subagents = 0) => ({ action: "set_sessions", anims, ids, subagents });
    const steps = [
      [0,     S(["idle"], ["1"])],                 // first session, no walk-in (first message)
      [1200,  S(["idle", "idle"], ["1", "2"])],    // session 2 arrives -> walking
      [3000,  S(["thinking", "idle"], ["1", "2"])],// new prompt -> idea, then thinking
      [5200,  S(["typing", "idle"], ["1", "2"])],
      [6400,  S(["conducting", "idle"], ["1", "2"], 1)], // 1 subagent -> grooving
      [8000,  S(["conducting", "idle"], ["1", "2"], 2)], // 2 subagents -> juggling
      [9600,  S(["dizzy", "idle"], ["1", "2"])],   // API error -> error
      [11200, S(["happy", "idle"], ["1", "2"])],   // turn ends -> happy
      [11250, S(["idle", "idle"], ["1", "2"])],
      [13600, S(["cool", "idle"], ["1", "2"])],    // all tests passed -> cool
      [13650, S(["idle", "idle"], ["1", "2"])],
      [19000, S(["idle"], ["1"])],                 // session 2 ends -> going_away
    ];
    for (const [t, p] of steps) {
      setTimeout(() => { sock.write(JSON.stringify(p) + "\n"); console.log(`[fake-daemon] t=${t} ${p.anims.join(",")}`); }, t);
    }
    setTimeout(() => { console.log("[fake-daemon] disconnecting"); sock.end(); }, 22800);
    return;
  }
  if (only) {
    const payload = { action: "set_sessions", anims: [only], ids: ["s1"], subagents: 0 };
    sock.write(JSON.stringify(payload) + "\n");
    console.log(`[fake-daemon] holding state: ${only} (Ctrl+C to stop)`);
    return; // keep the connection open, do not cycle
  }

  // Each state is held long enough to see even the 12s loops breathe.
  const HOLD_MS = 5000;
  let i = 0;
  const tick = () => {
    if (i >= SCRIPT.length) {
      console.log("[fake-daemon] script done; closing in 1s");
      setTimeout(() => sock.end(), 1000);
      return;
    }
    const payload = { action: "set_sessions", ...SCRIPT[i] };
    sock.write(JSON.stringify(payload) + "\n");
    console.log(`[fake-daemon] sent: ${SCRIPT[i].anims[0]}`);
    i++;
    setTimeout(tick, HOLD_MS);
  };
  setTimeout(tick, 500);
});

sock.setEncoding("utf8");
sock.on("data", (d) => console.log("[fake-daemon] recv:", d.trim()));
sock.on("error", (e) => console.error("[fake-daemon] error:", e.message,
  "\n(is the pet running? start it with: pnpm start)"));
sock.on("close", () => console.log("[fake-daemon] closed"));
