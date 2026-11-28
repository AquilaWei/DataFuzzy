// Matching TheraNote's IEP goals to the goal tick boxes of KeepCurrent's Create Service History
// form. Both come from the same IEP, so their words mostly agree: each pair is scored by the
// words they share, and a goal is ticked only when the match is clear. Plain functions, no page:
// keepcurrent.js uses them, and the tests run them as they are.
var TheraNoteKcMatch = (() => {
  "use strict";
  const TICK = 0.6; // this alike or more: ticked
  const ASK = 0.35; // this alike or more, but under TICK: left for the user, naming the likeliest
  const PRONOUNS = new Set(["he", "she", "they", "his", "her", "hers", "their", "him", "them"]);

  // Lower case words without punctuation; the student's names and pronouns all read "student",
  // so a goal written with the name matches one written with "he" or "she".
  function words(text, names = []) {
    const own = new Set(names.map((n) => String(n).toLowerCase()).filter(Boolean));
    return String(text).toLowerCase().replace(/[^a-z0-9%]+/g, " ").trim().split(" ").filter(Boolean)
      .map((w) => (own.has(w) || PRONOUNS.has(w) ? "student" : w));
  }

  function normalize(text, names = []) {
    return words(text, names).join(" ");
  }

  // How alike two texts are, 0 to 1: the Dice coefficient of their sets of words; 1 when one
  // holds the whole of the other (of some length, so a short title alone is not enough).
  function similarity(a, b, names = []) {
    const x = normalize(a, names), y = normalize(b, names);
    if (!x || !y) return 0;
    const shorter = x.length <= y.length ? x : y, longer = shorter === x ? y : x;
    if (shorter.length >= 25 && longer.includes(shorter)) return 1;
    const sx = new Set(x.split(" ")), sy = new Set(y.split(" "));
    let shared = 0;
    for (const w of sx) if (sy.has(w)) shared++;
    return (2 * shared) / (sx.size + sy.size);
  }

  // For each of TheraNote's `goals`, its match among the page's `options` (their texts), each
  // option used once, the most alike pairs first:
  //   {goal, option: index or -1, score, tick: bool, best: index of the likeliest option or -1}
  // `tick` is true for a clear match (TICK or more); under ASK there is no likely option.
  function matchGoals(goals, options, names = []) {
    const pairs = [];
    goals.forEach((g, gi) => options.forEach((o, oi) => pairs.push({gi, oi, score: similarity(g, o, names)})));
    pairs.sort((p, q) => q.score - p.score || p.gi - q.gi || p.oi - q.oi);
    const result = goals.map((goal) => ({goal, option: -1, score: 0, tick: false, best: -1}));
    const usedGoal = new Set(), usedOption = new Set();
    for (const p of pairs) {
      if (usedGoal.has(p.gi) || usedOption.has(p.oi) || p.score < ASK) continue;
      usedGoal.add(p.gi);
      usedOption.add(p.oi);
      const tick = p.score >= TICK;
      result[p.gi] = {goal: goals[p.gi], option: tick ? p.oi : -1, score: p.score, tick, best: p.oi};
    }
    return result;
  }

  return {TICK, ASK, normalize, similarity, matchGoals};
})();

if (typeof module !== "undefined") module.exports = TheraNoteKcMatch;
