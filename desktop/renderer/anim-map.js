// anim-map.js — pure mapping from the daemon's per-product state to the art the
// pet shows. Kept free of DOM/Electron so `node --test` can exercise it; loaded
// in the renderer as a plain script (global AnimMap) and via require() in tests.
(function (root) {
  // How long 'conducting' (the main agent dispatching the Agent tool) is shown
  // before the pet settles into 'grooving' (the subagents are doing the work).
  const CONDUCT_MS = 4000;

  /**
   * Map the daemon's animation name for a product to the pet's art.
   *
   * @param {string} name      product anim from the daemon (already the product's
   *                           most actionable session; names are shared with
   *                           firmware and unchanged by the subagent feature).
   * @param {number} bg        subagents currently running for this product
   *                           (products[].bg; absent/0 when none).
   * @param {number} conductMs ms the daemon has been reporting 'conducting'
   *                           (Infinity when unknown / not conducting).
   *
   * @param {boolean} exhausted products[].exhausted: a session of this product is
   *                           out of credits and nothing more actionable is
   *                           happening (the daemon already applies that rule).
   *
   * Priority (highest first):
   *   0. 'alert' (a permission request waiting on the user) always wins, then
   *      `exhausted` -> 'no_credits': a hard stop (nothing can run until the
   *      user tops up), so it outranks grooving/conducting/error. The pending
   *      permission is the only thing the user can act on right now.
   *   1. The main agent's own state: alert, error, confused, thinking and every
   *      tool animation (typing/building/debugger/wizard/beacon/sweeping). It is
   *      what the user is waiting on, and a subagent's tool calls never reach it
   *      (the daemon keeps them out of the main state), so there is no flicker.
   *   2. 'conducting' for the first CONDUCT_MS of an Agent dispatch.
   *   3. 'grooving' while bg > 0 and the main agent has nothing of its own to
   *      show: the crab "plays DJ" while subagents work in the background. This
   *      also replaces a long-lived 'conducting' (the Agent tool has no
   *      PostToolUse, so the daemon keeps reporting it until the next event).
   *   4. Otherwise the daemon's name (conducting with bg == 0 is just the
   *      dispatch moment; idle stays idle).
   */
  function mapAnim(name, bg, conductMs, exhausted) {
    if (name === "alert") return "alert";
    if (exhausted) return "no_credits";
    if (name === "dizzy") return "error";
    const n = name || "idle";
    if (!(bg > 0)) return n;
    if (n === "conducting") {
      const elapsed = conductMs === undefined ? Infinity : conductMs;
      return elapsed < CONDUCT_MS ? "conducting" : "grooving";
    }
    if (n === "idle") return "grooving";
    return n;
  }

  const api = { mapAnim, CONDUCT_MS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.AnimMap = api;
})(typeof window !== "undefined" ? window : globalThis);
