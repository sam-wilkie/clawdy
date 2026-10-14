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

// A one-product set_sessions as the daemon sends it to the pet: products[].bg is
// the number of subagents running (omitted when 0), anim is the main agent's.
function P(anim, bg, count = 1, exhausted = false) {
  const product = { agent: "claude", count, anim };
  if (bg) product.bg = bg;
  if (exhausted) product.exhausted = true;
  return { action: "set_sessions", products: [product], anims: [anim], ids: ["s1"], subagents: bg };
}

// A short script of states, like a real Claude session would drive.
// Covers every animation the pet now supports.
const SCRIPT = [
  { anims: ["wake"], ids: ["s1"], subagents: 0 },
  { anims: ["thinking"], ids: ["s1"], subagents: 0 },
  { anims: ["typing"], ids: ["s1"], subagents: 0 },
  { anims: ["building"], ids: ["s1"], subagents: 0 },
  { anims: ["debugger"], ids: ["s1"], subagents: 0 },
  // Main agent dispatches the Agent tool: conducting (no subagent running yet).
  P("conducting", 0),
  // 2 subagents now work in the background: conducting for ~4s, then grooving.
  P("conducting", 2),
  // The main agent runs its own tool while subagents work: its animation wins.
  P("typing", 2),
  { anims: ["beacon"], ids: ["s1"], subagents: 0 },
  { anims: ["sweeping"], ids: ["s1"], subagents: 0 },
  { anims: ["confused"], ids: ["s1"], subagents: 0 },
  { anims: ["dizzy"], ids: ["s1"], subagents: 0 },
  { anims: ["hat_mishap"], ids: ["s1"], subagents: 0 },
  { anims: ["notification"], ids: ["s1"], subagents: 0 },
  { anims: ["waiting_reply"], ids: ["s1"], subagents: 0 },
  { anims: ["low_battery"], ids: ["s1"], subagents: 0 },
  P("low_battery", 0, 1, true),   // credits exhausted -> no_credits (broke crab)
  { anims: ["happy"], ids: ["s1"], subagents: 0 },
  { anims: ["sleeping"], ids: ["s1"], subagents: 0 },
  { anims: ["idle"], ids: ["s1"], subagents: 0 },
];

const sock = net.createConnection({ host: HOST, port: PORT }, () => {
  console.log(`[fake-daemon] connected to pet at ${HOST}:${PORT}`);

  // Optional: `node fake-daemon.js <state>` holds a single state so you can
  // watch one animation's full loop (some loops are up to 12s long).
  // `node fake-daemon.js scenario` walks the pet-side states:
  // walking, idea, typing, conducting -> grooving (subagents working), error, happy,
  // going_away, then disconnects.
  const only = process.argv[2];

  // `node fake-daemon.js mochi` shows Mochi, the default pet, for the agents with
  // no art of their own (kiro, opencode, antigravity), each in a different state,
  // and rotates the states every 6 s so every animation can be watched. Ctrl+C ends.
  if (only === "mochi") {
    const AGENTS = ["kiro", "opencode", "antigravity"];
    const SHOW = ["idle", "thinking", "typing", "building", "debugger", "beacon", "wizard", "sweeping",
      "waiting_reply", "alert", "cool", "happy", "hat_mishap", "low_battery", "error", "sleeping"];
    let step = 0;
    const send = () => {
      const products = AGENTS.map((agent, k) => ({ agent, count: 1, anim: SHOW[(step + 5 * k) % SHOW.length] }));
      sock.write(JSON.stringify({ action: "set_sessions", products, anims: products.map((p) => p.anim),
        ids: AGENTS, subagents: 0 }) + "\n");
      console.log("[fake-daemon] mochi:", products.map((p) => `${p.agent}=${p.anim}`).join("  "));
      step += 1;
    };
    send();
    setInterval(send, 6000);
    return;
  }

  // `node fake-daemon.js perm` exercises the permission bubble: show a product,
  // then send a permission_request and print any permission_decision reply.
  if (only === "perm") {
    sock.write(JSON.stringify({ action: "set_sessions",
      products: [{ agent: "claude", count: 1, anim: "building" }],
      anims: ["building"], ids: ["1"], subagents: 0 }) + "\n");
    setTimeout(() => {
      const req = {
        action: "permission_request",   // the real daemon keys it by "action"
        id: "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",   // 32 hex
        nonce: "0011223344556677",                  // 16 hex
        agent: "claude",
        project: "Clawdy",
        tool: "Bash",
        summary: "rm -rf ./build && cmake --build .",
      };
      sock.write(JSON.stringify(req) + "\n");
      console.log("[fake-daemon] sent permission_request", req.id.slice(0, 8));
    }, 1500);
    // keep open to receive the decision; it is printed by the sock 'data' handler
    setTimeout(() => { console.log("[fake-daemon] (still waiting for a decision; Ctrl+C to stop)"); }, 20000);
    return;
  }

  // `node fake-daemon.js multi` exercises Phase 3: multiple products, each a
  // separate window, with xN badges, products arriving and leaving.
  if (only === "multi") {
    const P = (products) => ({ action: "set_sessions", products,
      // keep anims/ids present so a pre-Phase-3 reader still gets something
      anims: products.map((p) => p.anim), ids: products.map((_, i) => String(i + 1)),
      subagents: 0 });
    const steps = [
      [0,     P([{ agent: "claude", count: 1, anim: "typing" }])],
      [2500,  P([{ agent: "claude", count: 2, anim: "building" },
                 { agent: "codex", count: 1, anim: "thinking" }])],
      [5000,  P([{ agent: "claude", count: 3, anim: "building" },
                 { agent: "codex", count: 1, anim: "typing" },
                 { agent: "kiro", count: 1, anim: "debugger" }])],
      [8000,  P([{ agent: "claude", count: 1, anim: "idle" },
                 { agent: "kiro", count: 2, anim: "building" }])],   // codex leaves
      [11000, P([{ agent: "kiro", count: 1, anim: "idle" }])],       // claude leaves
    ];
    for (const [t, p] of steps) {
      setTimeout(() => {
        sock.write(JSON.stringify(p) + "\n");
        console.log(`[fake-daemon] t=${t} products: ${p.products.map((x) => x.agent + "x" + x.count + ":" + x.anim).join(", ")}`);
      }, t);
    }
    setTimeout(() => { console.log("[fake-daemon] disconnecting"); sock.end(); }, 14000);
    return;
  }

  if (only === "scenario") {
    const S = (anims, ids, subagents = 0) => ({ action: "set_sessions", anims, ids, subagents });
    const steps = [
      [0,     S(["idle"], ["1"])],                 // first session, no walk-in (first message)
      [1200,  S(["idle", "idle"], ["1", "2"])],    // session 2 arrives -> walking
      [3000,  S(["thinking", "idle"], ["1", "2"])],// new prompt -> idea, then thinking
      [5200,  S(["typing", "idle"], ["1", "2"])],
      [6400,  { ...P("conducting", 0, 2), anims: ["conducting", "idle"], ids: ["1", "2"] }], // Agent dispatch -> conducting
      [7600,  { ...P("conducting", 2, 2), anims: ["conducting", "idle"], ids: ["1", "2"] }], // subagents running -> ~4s conducting, then grooving
      [13000, { ...P("typing", 2, 2), anims: ["typing", "idle"], ids: ["1", "2"] }],         // main agent's own tool wins over grooving
      [14000, { ...P("low_battery", 0, 2, true), anims: ["low_battery", "idle"], ids: ["1", "2"] }], // credits exhausted -> no_credits
      [15000, S(["dizzy", "idle"], ["1", "2"])],   // API error -> error
      [16600, S(["happy", "idle"], ["1", "2"])],   // turn ends -> happy
      [16650, S(["idle", "idle"], ["1", "2"])],
      [19000, S(["cool", "idle"], ["1", "2"])],    // all tests passed -> cool
      [19050, S(["idle", "idle"], ["1", "2"])],
      [24400, S(["idle"], ["1"])],                 // session 2 ends -> going_away
    ];
    for (const [t, p] of steps) {
      setTimeout(() => { sock.write(JSON.stringify(p) + "\n"); console.log(`[fake-daemon] t=${t} ${p.anims.join(",")}`); }, t);
    }
    setTimeout(() => { console.log("[fake-daemon] disconnecting"); sock.end(); }, 28200);
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
