// The panel on KeepCurrent (mykeepcurrent.com), shown and hidden by the toolbar button: load a
// TheraNote fill-in file, whose "visits" are the pre-school students' charts, then go through
// them one by one. On the dashboard, "開始" finds each student's Create Service History link;
// each chart's form is then opened and filled in, and the panel stops there for the user to
// tick the Routines, check and press Save themselves; nothing is saved without them. Once saved,
// the next chart's form is opened. The file and the progress stay in chrome.storage.session, in
// memory only, until "清除" or the browser quits.
(() => {
  "use strict";
  const FORMAT = "theranote-ace/2";
  const KEY = "theranoteKc";
  const SUBMITTED = "theranoteKcSubmitted"; // sessionStorage: the chart whose form was sent
  const MATCH = TheraNoteKcMatch; // kc-match.js
  const PROBLEMS = {no_english: "還沒有英文 comment", no_times: "缺開始／結束時間"};
  const STATUS = {todo: "待填", filling: "填寫中", saved: "已存", skipped: "跳過", problem: "要手動"};
  const TITLE = "Occupational Therapist";
  const STRATEGIES = ["Verbal/Visual Redirection", "Verbal/Visual Prompting"];
  // The routine and strategy tick boxes beside the IEP goals, as KeepCurrent names them: never
  // taken for goals.
  const NOT_GOALS = new Set(["Play with Objects", "Gross Motor", "Pretend Play", "Toileting Routine",
    "Hand-washing Routine", "Transition Time", "Eating Related", "Computer", "Reading with Books",
    "Songs and Rhymes", "Fine Motor", "Large Group", "Small Group", "Free Choice", "Other",
    "Establish Routines", "Increase Opportunities", "Turn-taking", "Expect More", "Descriptive Talking",
    "Prompt/Fade", "Waiting", "Request/Model", "Directive Talking", "Imitate", "Hand over Hand",
    "Verbal/Visual Redirection", "Verbal/Visual Prompting", "Errorless Teaching"].map((n) => n.toLowerCase().replace(/\s+/g, "")));

  let state = null; // {file, status: [..per visit], notes: [..per visit], current, links: {key: url}}

  // --- state -------------------------------------------------------------------------

  const STALE = "TheraNote 擴充功能已更新或重新載入，請重新整理這個 KeepCurrent 頁面（⌘R）再繼續。";
  const stale = (error) => /context invalidated/i.test(String(error && error.message));

  async function session(use) {
    try {
      return await use(chrome.storage.session);
    } catch (error) {
      if (stale(error)) throw new Error(STALE);
      await chrome.runtime.sendMessage({theranoteAce: "allow"}); // wakes the worker, which allows it
      return use(chrome.storage.session);
    }
  }

  async function load() {
    state = (await session((s) => s.get(KEY)))[KEY] || null;
  }

  async function save() {
    try {
      await session((s) => (state ? s.set({[KEY]: state}) : s.remove(KEY)));
    } catch (error) {
      keep();
      say(stale(error) || error.message === STALE ? STALE : `進度沒能保存：${error.message}`, true);
    }
  }

  function openFile(text) {
    const file = JSON.parse(text);
    if (file.format !== FORMAT || !Array.isArray(file.visits)) {
      throw new Error(`這不是新版的 TheraNote 填寫檔（${FORMAT}），請在 TheraNote 重新按「ACE 填寫檔」存一次。`);
    }
    state = {file, status: file.visits.map((v) => (v.problems.length ? "problem" : "todo")),
      notes: file.visits.map(() => []), current: 0, links: null};
    state.current = nextTodo(0);
  }

  function nextTodo(from) {
    const i = state.status.findIndex((s, i) => i >= from && s === "todo");
    return i >= 0 ? i : state.status.findIndex((s) => s === "todo");
  }

  // "todd|dree": a student as both TheraNote and KeepCurrent's "Todd, Dree A." name them.
  const letters = (s) => String(s).toLowerCase().replace(/[^a-z]+/g, " ").trim();
  const nameKey = (first, last) => `${letters(last)}|${letters(first).split(" ")[0]}`;
  const monthDay = (iso) => iso.split("-").slice(1).map(Number).join("/");
  const clock = (hhmm) => {
    if (!hhmm) return "";
    const [h, m] = hhmm.split(":").map(Number);
    return `${(h + 11) % 12 + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
  };

  // --- pages -------------------------------------------------------------------------

  const onDashboard = () => /\/Dashboard/i.test(location.pathname);
  const onCreate = () => /\/IepSession\/Create/i.test(location.pathname);
  const personId = (url) => new URL(url, location.href).searchParams.get("studentPersonId");

  // Name key -> Create Service History link, from the dashboard's rows ("Todd, Dree (08/17/2022)");
  // a name found on more than one row maps to null.
  function dashboardLinks() {
    const links = {};
    for (const a of document.querySelectorAll("a[href]")) {
      if (!/IepSession\/Create/i.test(a.getAttribute("href"))) continue;
      const row = a.closest("tr") || a.parentElement;
      const name = [...row.querySelectorAll("a")].map((x) => x.textContent.trim())
        .find((t) => /^[^,(]+,[^,(]+\(/.test(t));
      if (!name) continue;
      const [last, first] = name.replace(/\(.*$/, "").split(",");
      const key = nameKey(first, last);
      links[key] = key in links ? null : a.href;
    }
    return links;
  }

  function linkOf(visit) {
    const link = state.links && state.links[nameKey(visit.first, visit.last)];
    return link || null;
  }

  // Opens the current chart's form, or says why it cannot.
  function openCurrent(lead = "") {
    const visit = state.file.visits[state.current];
    if (!visit) return;
    if (!state.links) {
      keep();
      say(`${lead}請先打開 KeepCurrent 的 Dashboard，再按「開始」。`, true);
      return;
    }
    const link = linkOf(visit);
    if (!link) {
      const twice = state.links[nameKey(visit.first, visit.last)] === null;
      state.status[state.current] = "problem";
      state.notes[state.current] = [twice ? `Dashboard 有不只一位 ${visit.first} ${visit.last}，請手動填。`
        : `Dashboard 找不到 ${visit.first} ${visit.last}（名字拼法可能不同），請手動填。`];
      advance(state.current, lead);
      return;
    }
    state.status[state.current] = "filling";
    save().then(() => {
      if (onCreate() && personId(location.href) === personId(link)) fillPage();
      else location.href = link;
    });
  }

  // After a chart is done with: the next one still to fill is opened.
  function advance(from, lead) {
    state.current = nextTodo(from + 1);
    save();
    if (state.current < 0) {
      keep();
      say(`${lead}全部處理完了。填完請刪除下載的填寫檔。`);
      render();
      return;
    }
    render();
    keep();
    say(`${lead}\n正在打開下一筆…`);
    setTimeout(() => openCurrent(lead), 800);
  }

  // --- the form ----------------------------------------------------------------------

  const squash = (s) => String(s).toLowerCase().replace(/\s+/g, "");
  const textOf = (el) => (el ? el.textContent.replace(/\s+/g, " ").trim() : "");

  // The field labelled `label` (exactly, ignoring case and spaces): the label's `for` target,
  // or the first field after the label in its box.
  function field(label, selector = "input, select, textarea") {
    for (const l of document.querySelectorAll("label")) {
      if (squash(textOf(l)) !== squash(label)) continue;
      const target = l.htmlFor && document.getElementById(l.htmlFor);
      if (target && target.matches(selector)) return target;
      for (let box = l.parentElement; box && box !== document.body; box = box.parentElement) {
        const found = [...box.querySelectorAll(selector)].find(
          (f) => l.compareDocumentPosition(f) & Node.DOCUMENT_POSITION_FOLLOWING && f.type !== "hidden");
        if (found) return found;
      }
    }
    return null;
  }

  // Sets a field's value as typing it would, so the page's own scripts (the end time) follow.
  function setValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
      : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    el.dispatchEvent(new Event("input", {bubbles: true}));
    el.dispatchEvent(new Event("change", {bubbles: true}));
  }

  // Picks the option of `select` whose text is `text` or begins with it (ignoring case and
  // spaces), or one `test` accepts; returns its text, or "" when there is none.
  function choose(select, text, test = null) {
    const want = squash(text);
    const options = [...select.options];
    const option = test ? options.find((o) => test(o.textContent.trim()))
      : options.find((o) => squash(o.textContent) === want) || options.find((o) => squash(o.textContent).startsWith(want));
    if (!option) return "";
    setValue(select, option.value);
    return option.textContent.trim();
  }

  function tick(box) {
    if (!box.checked) box.click();
  }

  // The text of a tick box's own block: the largest box around it holding no other tick box.
  function boxText(box) {
    let el = box;
    while (el.parentElement && el.parentElement.querySelectorAll("input[type=checkbox]").length === 1) {
      el = el.parentElement;
    }
    return (el.innerText || el.textContent).replace(/\s+/g, " ").trim(); // innerText keeps the lines apart
  }

  // The element whose own text begins with `text`.
  function heading(text) {
    const want = squash(text);
    return [...document.querySelectorAll("label, h1, h2, h3, h4, h5, div, span, p, legend")]
      .find((el) => squash([...el.childNodes].filter((n) => n.nodeType === Node.TEXT_NODE)
        .map((n) => n.textContent).join("")).startsWith(want));
  }

  // The IEP goal tick boxes: those after "Outcome/Goals from IEP…" and before "Description of
  // Activity", leaving out the routines and strategies beside them.
  function goalBoxes() {
    const start = heading("Outcome/Goals from IEP");
    if (!start) return [];
    const end = heading("Description of Activity");
    const routines = heading("Routines"), strategies = heading("Strategies");
    // A column headed Routines or Strategies, unless it holds the goals as well.
    const inColumn = (box, head) => head && head.parentElement && head.parentElement.contains(box)
      && !head.parentElement.contains(start);
    return [...document.querySelectorAll("input[type=checkbox]")].filter((box) =>
      start.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING
      && (!end || box.compareDocumentPosition(end) & Node.DOCUMENT_POSITION_FOLLOWING)
      && !inColumn(box, routines) && !inColumn(box, strategies) && !NOT_GOALS.has(squash(boxText(box))));
  }

  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function until(find, ms = 6000) {
    for (let waited = 0; waited < ms; waited += 200) {
      const found = find();
      if (found) return found;
      await wait(200);
    }
    return null;
  }

  // Fills the open form with the current chart and says what was done and what is left.
  async function fillPage() {
    const i = state.current;
    const visit = state.file.visits[i];
    const done = [], missing = [], goalNotes = [];
    const title = textOf([...document.querySelectorAll("h1, h2, h3, .page-title")]
      .find((h) => /create service history/i.test(h.textContent))) || document.title;
    if (!letters(title).includes(letters(visit.first).split(" ")[0]) || !letters(title).includes(letters(visit.last))) {
      state.status[i] = "todo";
      save(); render();
      keep();
      say(`這一頁不是 ${visit.first} ${visit.last} 的表單（${title}），沒有填。`, true);
      return;
    }
    state.status[i] = "filling";
    save(); render();
    keep();
    say("填寫中…");
    const set = (label, value, shown = value) => {
      const el = field(label);
      if (!el) { missing.push(label); return; }
      setValue(el, value);
      done.push(`${label}：${shown}`);
    };
    const pick = (label, text, test) => {
      const el = field(label, "select");
      const chosen = el && choose(el, text, test);
      if (chosen) done.push(`${label}：${chosen}`);
      else missing.push(`${label}（${text}）`);
      return chosen;
    };

    const date = field("Session Date");
    if (!date) missing.push("Session Date");
    else {
      const [y, m, d] = visit.date.split("-");
      setValue(date, date.type === "date" ? visit.date : `${m}/${d}/${y}`);
      done.push(`Session Date：${m}/${d}/${y}`);
    }
    const type = pick("Service Application Type", visit.application_type);
    pick("Session Type", visit.mode);
    set("Title", TITLE);
    set("Direct Time (Minutes)", String(visit.minutes));
    const start = field("Start Time");
    if (start && visit.start) {
      setValue(start, start.type === "time" ? visit.start : clock(visit.start));
      done.push(`Start Time：${clock(visit.start)}`);
    } else if (visit.start) missing.push("Start Time");

    // The session note: always included; its fields appear once it is.
    const note = [...document.querySelectorAll("label, button")].find((el) => /include session note/i.test(textOf(el)));
    const noteBox = note && (note.querySelector("input[type=checkbox]") || (note.htmlFor && document.getElementById(note.htmlFor)));
    if (!note) missing.push("Include Session Note");
    else if (noteBox ? !noteBox.checked : !/active|checked/.test(note.className)) {
      (noteBox || note).click();
    }
    const description = await until(() => field("Description of Goals and Activities", "textarea"));
    if (note) done.push("Include Session Note：打勾");

    if (!description) missing.push("Description of Goals and Activities");
    else setValue(description, visit.direct ? visit.comment : (type || visit.application_type));
    if (description) done.push(`Description of Goals and Activities：${visit.direct ? "英文 comment" : (type || visit.application_type)}`);

    if (visit.direct) {
      const boxes = goalBoxes();
      const texts = boxes.map(boxText);
      for (const m of MATCH.matchGoals(visit.goals, texts, [visit.first, visit.last])) {
        const head = m.goal.length > 50 ? `${m.goal.slice(0, 50)}…` : m.goal;
        if (m.tick) {
          tick(boxes[m.option]);
          goalNotes.push(`✓ ${head} → ${texts[m.option].slice(0, 40)}…（${Math.round(m.score * 100)}%）`);
        } else if (m.best >= 0) {
          goalNotes.push(`需確認：${head} 可能是「${texts[m.best].slice(0, 40)}…」（${Math.round(m.score * 100)}%），沒有勾`);
        } else {
          goalNotes.push(`找不到對應目標：${head}`);
        }
      }
      if (!boxes.length && visit.goals.length) missing.push("Outcome/Goals from IEP 的勾選框");
      for (const name of STRATEGIES) {
        const box = [...document.querySelectorAll("input[type=checkbox]")].find((b) => squash(boxText(b)) === squash(name));
        if (box) { tick(box); done.push(`Strategies：${name}`); } else missing.push(`Strategies：${name}`);
      }
      pick("Student Progress", "PR - Progressing", (t) => /^pr\b/i.test(t));
    }

    state.notes[i] = [...goalNotes, ...missing.map((m) => `沒填到：${m}`)];
    state.filled = done;
    save(); render();
    keep();
    say([visit.direct ? "已填好。請勾 Routines（和需要的 Treatment Keys），檢查後按 Save。"
      : "已填好。請檢查後按 Save。", "存檔後會自動打開下一筆；不存就按「跳過」。"].join("\n"), missing.length > 0);
  }

  // The user pressed Save: the next page says whether it took.
  document.addEventListener("submit", () => {
    if (state && state.status[state.current] === "filling") sessionStorage.setItem(SUBMITTED, String(state.current));
  }, true);

  function afterSubmit() {
    const sent = sessionStorage.getItem(SUBMITTED);
    if (sent === null || !state) return false;
    sessionStorage.removeItem(SUBMITTED);
    const i = Number(sent);
    const refused = onCreate() && document.querySelector(
      ".validation-summary-errors, .field-validation-error:not(:empty), .alert-danger");
    if (refused) {
      keep();
      say("KeepCurrent 沒有存：頁面上有錯誤訊息，請修正後再按 Save。", true);
      return true;
    }
    state.status[i] = "saved";
    advance(i, "已存。");
    return true;
  }

  // --- panel -------------------------------------------------------------------------

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;top:120px;right:12px;z-index:2147483000;display:none;";
  const root = host.attachShadow({mode: "closed"});
  root.innerHTML = `<style>
    :host{all:initial}
    .panel{width:340px;max-height:75vh;display:flex;flex-direction:column;font:13px/1.4 -apple-system,system-ui,sans-serif;
      color:#1d2327;background:#fff;border:1px solid #c7ced3;border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.18);overflow:hidden}
    header{display:flex;align-items:center;gap:8px;padding:8px 10px;background:#4f7d1f;color:#fff;font-weight:600;
      cursor:move;user-select:none;touch-action:none}
    header span{flex:1}
    header button{background:none;border:none;color:#fff;cursor:pointer;font-size:14px}
    .body{padding:10px;overflow:auto;display:flex;flex-direction:column;gap:8px}
    .msg{padding:6px 8px;border-radius:6px;background:#f0f6e8;white-space:pre-line}
    .msg.error{background:#fdecea;color:#8a1c12}
    .current{border:1px solid #d7dde1;border-radius:8px;padding:8px}
    .current h3{margin:0 0 4px;font-size:14px}
    .rows,.notes{margin:4px 0;padding-left:16px}
    .rows li,.notes li{margin:2px 0}
    .notes{color:#8a4500}
    .actions{display:flex;gap:6px;flex-wrap:wrap}
    button.act{padding:5px 10px;border-radius:6px;border:1px solid #c7ced3;background:#fff;cursor:pointer;font:inherit}
    button.primary{background:#4f7d1f;border-color:#4f7d1f;color:#fff}
    button:disabled{opacity:.5;cursor:default}
    ul.cells{list-style:none;margin:0;padding:0;border-top:1px solid #eee}
    ul.cells li{display:flex;gap:6px;padding:4px 2px;border-bottom:1px solid #eee;cursor:pointer}
    ul.cells li.on{background:#f0f6e8}
    ul.cells .who{flex:1}
    .badge{font-size:11px;padding:1px 6px;border-radius:9px;background:#e8eaed;white-space:nowrap}
    .badge.saved{background:#d7f0dc;color:#1b5e20}.badge.problem{background:#fdecea;color:#8a1c12}
    .badge.filling{background:#fff4ce;color:#7a5b00}
    .hidden{display:none}
  </style>
  <div class="panel">
    <header id="drag" title="拖曳移動面板"><span>TheraNote → KeepCurrent</span><button id="close" title="關閉（點工具列的圖示再打開）">✕</button></header>
    <div class="body">
      <div class="msg" id="msg"></div>
      <div class="actions">
        <button class="act" id="pick">選擇填寫檔…</button>
        <button class="act primary" id="start" title="在 Dashboard 找出每位學生的表單，從第一筆開始填">開始</button>
        <button class="act" id="clear">清除</button>
        <input type="file" id="file" accept=".json,application/json" class="hidden">
      </div>
      <div class="current hidden" id="current"></div>
      <ul class="cells" id="cells"></ul>
    </div>
  </div>`;
  const $ = (id) => root.getElementById(id);

  function say(text, error = false) {
    $("msg").textContent = text;
    $("msg").className = error ? "msg error" : "msg";
  }
  const keep = () => { $("msg").dataset.keep = "1"; };

  function button(text, kind, onClick) {
    const b = document.createElement("button");
    b.className = `act ${kind}`;
    b.textContent = text;
    b.addEventListener("click", onClick);
    return b;
  }

  function list(items, cls) {
    const ul = document.createElement("ul");
    ul.className = cls;
    for (const text of items) {
      const li = document.createElement("li");
      li.textContent = text;
      ul.append(li);
    }
    return ul;
  }

  function render() {
    const has = Boolean(state);
    $("clear").disabled = !has;
    $("start").disabled = !has;
    $("start").textContent = has && state.links ? "繼續" : "開始";
    $("cells").replaceChildren();
    $("current").classList.toggle("hidden", !has || state.current < 0);
    if (!has) {
      say("在 TheraNote 按「ACE 填寫檔」存檔（Pre-School 學生的病歷會一起存進去），再到這裡選擇它。");
      return;
    }
    state.file.visits.forEach((visit, i) => {
      const li = document.createElement("li");
      li.className = i === state.current ? "on" : "";
      const who = document.createElement("span");
      who.className = "who";
      who.textContent = `${monthDay(visit.date)} ${clock(visit.start)} ${visit.first} ${visit.last} · ${visit.application_type}`;
      const badge = document.createElement("span");
      badge.className = `badge ${state.status[i]}`;
      badge.textContent = STATUS[state.status[i]];
      li.append(who, badge);
      li.addEventListener("click", () => { state.current = i; save(); render(); });
      $("cells").append(li);
    });
    if (state.current >= 0) renderCurrent(state.file.visits[state.current], state.status[state.current]);
    const left = state.status.filter((s) => s === "todo").length;
    if (!$("msg").dataset.keep) {
      say(!state.file.visits.length ? "這個檔案沒有 Pre-School 學生的病歷。"
        : left ? `還有 ${left} 筆待填。` : "全部處理完了。填完請刪除下載的填寫檔。");
    }
    delete $("msg").dataset.keep;
  }

  function renderCurrent(visit, status) {
    const box = $("current");
    box.replaceChildren();
    const title = document.createElement("h3");
    title.textContent = `${visit.first} ${visit.last} · ${visit.date}`;
    const rows = [`${visit.application_type} · ${visit.mode}`,
      `${clock(visit.start) || "沒有開始時間"} · Direct Time ${visit.minutes} 分`];
    if (visit.direct) rows.push(`勾選目標：${visit.goals.length} 個`);
    box.append(title, list(status === "filling" && state.filled ? state.filled : rows, "rows"));
    const notes = (state.notes && state.notes[state.current]) || [];
    if (notes.length) box.append(list(notes, "notes"));
    for (const p of visit.problems) {
      const note = document.createElement("div");
      note.className = "msg error";
      note.textContent = PROBLEMS[p] || p;
      box.append(note);
    }
    const actions = document.createElement("div");
    actions.className = "actions";
    if (status === "filling" && onCreate()) {
      actions.append(button("重新填這頁", "", () => fillPage()));
    } else if (status !== "saved") {
      const fill = button("打開並填這一筆", "primary", () => openCurrent());
      fill.disabled = visit.problems.length > 0 || !state.links;
      actions.append(fill);
    }
    if (status === "filling") {
      actions.append(button("已存，下一筆", "", () => { state.status[state.current] = "saved"; advance(state.current, "已存。"); }));
    }
    actions.append(button(status === "skipped" || status === "saved" ? "改回待填" : "跳過", "", () => {
      const i = state.current;
      if (status === "skipped" || status === "saved") { state.status[i] = "todo"; save(); render(); return; }
      state.status[i] = "skipped";
      advance(i, "已跳過。");
    }));
    box.append(actions);
  }

  // --- wiring ------------------------------------------------------------------------

  $("pick").addEventListener("click", () => $("file").click());
  $("file").addEventListener("change", async () => {
    const f = $("file").files[0];
    $("file").value = "";
    if (!f) return;
    try {
      openFile(await f.text());
      await save();
      keep();
      say(`已載入 ${state.file.visits.length} 筆 Pre-School 病歷。到 Dashboard 按「開始」。`);
      render();
    } catch (error) {
      say(error.message, true);
    }
  });
  $("start").addEventListener("click", () => {
    if (!state) return;
    if (onDashboard()) {
      state.links = dashboardLinks();
      const found = Object.values(state.links).filter(Boolean).length;
      if (!found) {
        state.links = null;
        keep();
        say("Dashboard 上找不到任何「Create Service History」連結。", true);
        render();
        return;
      }
    }
    if (state.current < 0) state.current = nextTodo(0);
    if (state.current < 0) { keep(); say("沒有待填的病歷了。"); render(); return; }
    openCurrent();
    render();
  });
  $("clear").addEventListener("click", async () => {
    if (!confirm("清除載入的填寫檔和進度？（KeepCurrent 裡已存的資料不受影響）")) return;
    state = null;
    sessionStorage.removeItem(SUBMITTED);
    await save();
    render();
  });

  const show = (on) => { host.style.display = on ? "block" : "none"; if (on) keepInView(); };
  const POSITION = "theranoteKcPosition";
  function place(left, top) {
    const width = host.offsetWidth || 340, height = host.offsetHeight || 60;
    left = Math.min(Math.max(0, left), Math.max(0, window.innerWidth - width));
    top = Math.min(Math.max(0, top), Math.max(0, window.innerHeight - Math.min(height, 40)));
    Object.assign(host.style, {left: `${left}px`, top: `${top}px`, right: "auto"});
  }
  function keepInView() {
    if (host.style.left) place(parseFloat(host.style.left), parseFloat(host.style.top));
  }
  let dragging = null;
  $("drag").addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.target.closest("button")) return;
    const box = host.getBoundingClientRect();
    dragging = {dx: event.clientX - box.left, dy: event.clientY - box.top};
    $("drag").setPointerCapture(event.pointerId);
    event.preventDefault();
  });
  $("drag").addEventListener("pointermove", (event) => {
    if (dragging) place(event.clientX - dragging.dx, event.clientY - dragging.dy);
  });
  const drop = () => {
    if (!dragging) return;
    dragging = null;
    chrome.storage.local.set({[POSITION]: {left: parseFloat(host.style.left), top: parseFloat(host.style.top)}})
      .catch(() => {});
  };
  $("drag").addEventListener("pointerup", drop);
  $("drag").addEventListener("pointercancel", drop);
  window.addEventListener("resize", keepInView);
  chrome.storage.local.get(POSITION).then((saved) => {
    if (saved[POSITION]) place(saved[POSITION].left, saved[POSITION].top);
  }).catch(() => {});
  $("close").addEventListener("click", () => show(false));
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.theranoteAce === "toggle") show(host.style.display === "none");
  });

  document.documentElement.append(host);
  load().then(() => {
    render();
    if (!state) return;
    // While going through the charts, the panel stays open from page to page.
    if (state.status.includes("filling") || sessionStorage.getItem(SUBMITTED) !== null) show(true);
    if (afterSubmit()) { render(); return; }
    const i = state.current;
    if (i >= 0 && state.status[i] === "filling" && onCreate()) {
      const link = linkOf(state.file.visits[i]);
      if (link && personId(link) === personId(location.href)) fillPage();
      else { state.status[i] = "todo"; save(); render(); }
    }
  }, (error) => {
    render();
    keep();
    say(stale(error) || error.message === STALE ? STALE : `讀不到先前的進度（${error.message}），請重新選擇填寫檔。`, true);
  });
})();
