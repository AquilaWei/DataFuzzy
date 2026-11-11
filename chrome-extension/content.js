// The panel at the right of ACE Portal, shown and hidden by the toolbar button: load a
// TheraNote ACE fill-in file, then fill its cells one at a time. Each fill stops with ACE's own
// window open for the user to check and save (or cancel); nothing is saved without them. The
// file and the progress stay in chrome.storage.session, in memory only, until "Clear" or the
// browser quits.
(() => {
  "use strict";
  const FORMAT = "theranote-ace/1";
  const KEY = "theranoteAce";
  const PROBLEMS = {
    manual_type: "Consult：ACE 沒有對應類型，請手動填",
    no_english: "還沒有英文記錄或追蹤",
    no_times: "缺開始／結束時間",
    no_group: "Group 病歷缺開始時間，無法分組",
  };
  const STATUS = {todo: "待填", filling: "填寫中", saved: "已存", skipped: "跳過", problem: "要手動"};

  let state = null; // {file: {...}, status: [..per cell], current: index}

  // --- talking to page.js ----------------------------------------------------------

  let nextId = 1;
  const waiting = new Map();
  window.addEventListener("message", (event) => {
    const msg = event.data;
    if (event.source !== window || !msg) return;
    if (msg.theranoteAce === "reply" && waiting.has(msg.id)) {
      const {resolve, reject} = waiting.get(msg.id);
      waiting.delete(msg.id);
      msg.ok ? resolve(msg.value) : reject(new Error(msg.error));
    } else if (msg.theranoteAce === "closed") {
      windowClosed(msg.saved);
    }
  });

  function ask(op, args) {
    const id = nextId++;
    return new Promise((resolve, reject) => {
      waiting.set(id, {resolve, reject});
      window.postMessage({theranoteAce: "request", id, op, args}, location.origin);
    });
  }

  // --- state -------------------------------------------------------------------------

  async function load() {
    state = (await chrome.storage.session.get(KEY))[KEY] || null;
  }

  function save() {
    return state ? chrome.storage.session.set({[KEY]: state}) : chrome.storage.session.remove(KEY);
  }

  function openFile(text) {
    const file = JSON.parse(text);
    if (file.format !== FORMAT) throw new Error(`這不是 TheraNote 的 ACE 填寫檔（${FORMAT}）`);
    state = {file, status: file.cells.map((c) => (c.problems.length ? "problem" : "todo")), current: 0};
    state.current = nextTodo(0);
  }

  function nextTodo(from) {
    const i = state.status.findIndex((s, i) => i >= from && s === "todo");
    return i >= 0 ? i : state.status.findIndex((s) => s === "todo");
  }

  // "11/9" for the file's first day, to compare with ACE's "monday 11/9".
  function monthDay(iso) {
    const [, m, d] = iso.split("-").map(Number);
    return `${m}/${d}`;
  }

  // --- panel -------------------------------------------------------------------------

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;top:120px;right:12px;z-index:2147483000;display:none;"; // until the toolbar button
  const root = host.attachShadow({mode: "closed"});
  root.innerHTML = `<style>
    :host{all:initial}
    .panel{width:320px;max-height:70vh;display:flex;flex-direction:column;font:13px/1.4 -apple-system,system-ui,sans-serif;
      color:#1d2327;background:#fff;border:1px solid #c7ced3;border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.18);overflow:hidden}
    header{display:flex;align-items:center;gap:8px;padding:8px 10px;background:#0f6e72;color:#fff;font-weight:600}
    header span{flex:1}
    header button{background:none;border:none;color:#fff;cursor:pointer;font-size:14px}
    .body{padding:10px;overflow:auto;display:flex;flex-direction:column;gap:8px}
    .msg{padding:6px 8px;border-radius:6px;background:#eef6f6;white-space:pre-line}
    .msg.error{background:#fdecea;color:#8a1c12}
    .current{border:1px solid #d7dde1;border-radius:8px;padding:8px}
    .current h3{margin:0 0 4px;font-size:14px}
    .rows{margin:4px 0;padding-left:16px}
    .rows li{margin:2px 0}
    .actions{display:flex;gap:6px;flex-wrap:wrap}
    button.act{padding:5px 10px;border-radius:6px;border:1px solid #c7ced3;background:#fff;cursor:pointer;font:inherit}
    button.primary{background:#0f6e72;border-color:#0f6e72;color:#fff}
    button:disabled{opacity:.5;cursor:default}
    ul.cells{list-style:none;margin:0;padding:0;border-top:1px solid #eee}
    ul.cells li{display:flex;gap:6px;padding:4px 2px;border-bottom:1px solid #eee;cursor:pointer}
    ul.cells li.on{background:#eef6f6}
    ul.cells .who{flex:1}
    .badge{font-size:11px;padding:1px 6px;border-radius:9px;background:#e8eaed;white-space:nowrap}
    .badge.saved{background:#d7f0dc;color:#1b5e20}.badge.problem{background:#fdecea;color:#8a1c12}
    .badge.filling{background:#fff4ce;color:#7a5b00}
    .hidden{display:none}
  </style>
  <div class="panel">
    <header><span>TheraNote → ACE</span><button id="close" title="關閉（點工具列的圖示再打開）">✕</button></header>
    <div class="body" id="body">
      <div class="msg" id="msg"></div>
      <div class="actions">
        <button class="act" id="pick">選擇填寫檔…</button>
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

  function rowText(row) {
    const parts = [row.section === "direct" ? "Direct" : row.section === "group" ? "Group" : "Indirect", row.type];
    if (row.minutes != null) parts.push(`${row.minutes} 分`);
    if (row.start) parts.push(`${row.start}–${row.end}`);
    if (row.group) parts.push(`${row.group}／${row.group_size} 人`);
    return parts.join(" · ");
  }

  function render() {
    const has = Boolean(state);
    $("clear").disabled = !has;
    $("cells").replaceChildren();
    $("current").classList.toggle("hidden", !has || state.current < 0);
    if (!has) {
      say("在 TheraNote 按「ACE 填寫檔」存一週的檔案，再到這裡選擇它。");
      return;
    }
    state.file.cells.forEach((cell, i) => {
      const li = document.createElement("li");
      li.className = i === state.current ? "on" : "";
      const who = document.createElement("span");
      who.className = "who";
      who.textContent = `${monthDay(cell.date)} ${cell.first} ${cell.last}`;
      const badge = document.createElement("span");
      badge.className = `badge ${state.status[i]}`;
      badge.textContent = STATUS[state.status[i]];
      li.append(who, badge);
      li.addEventListener("click", () => { state.current = i; save(); render(); });
      $("cells").append(li);
    });
    if (state.current >= 0) renderCurrent(state.file.cells[state.current], state.status[state.current]);
    const left = state.status.filter((s) => s === "todo").length;
    if (!$("msg").dataset.keep) say(left ? `還有 ${left} 格待填。` : "全部處理完了。填完請刪除下載的填寫檔。");
    delete $("msg").dataset.keep;
  }

  function renderCurrent(cell, status) {
    const box = $("current");
    box.replaceChildren();
    const title = document.createElement("h3");
    title.textContent = `${cell.first} ${cell.last} · ${cell.date}`;
    const list = document.createElement("ul");
    list.className = "rows";
    for (const row of cell.rows) {
      const li = document.createElement("li");
      li.textContent = rowText(row);
      list.append(li);
    }
    box.append(title, list);
    for (const p of cell.problems) {
      const note = document.createElement("div");
      note.className = "msg error";
      note.textContent = PROBLEMS[p] || p;
      box.append(note);
    }
    const actions = document.createElement("div");
    actions.className = "actions";
    const fill = button("填這一格", "primary", () => fillCurrent());
    fill.disabled = status === "filling" || cell.problems.length > 0;
    const skip = button(status === "skipped" ? "改回待填" : "跳過", "", () => {
      state.status[state.current] = status === "skipped" ? "todo" : "skipped";
      if (status !== "skipped") state.current = nextTodo(state.current + 1);
      save(); render();
    });
    skip.disabled = status === "filling";
    actions.append(fill, skip);
    box.append(actions);
  }

  function button(text, kind, onClick) {
    const b = document.createElement("button");
    b.className = `act ${kind}`;
    b.textContent = text;
    b.addEventListener("click", onClick);
    return b;
  }

  // --- filling -----------------------------------------------------------------------

  async function fillCurrent() {
    const i = state.current;
    const cell = state.file.cells[i];
    try {
      const week = await ask("week");
      if (!week.length || !week[0].endsWith(` ${monthDay(state.file.week[0])}`)) {
        throw new Error(`ACE 現在顯示的週（${week[0] || "?"}）不是檔案的週（${state.file.week[0]} 起），請先切換週次。`);
      }
      const spot = await ask("locate", cell);
      if (spot.matches !== 1) {
        throw new Error(spot.matches ? `ACE 清單有 ${spot.matches} 位 ${cell.first} ${cell.last}，請手動填。`
          : `ACE 清單找不到 ${cell.first} ${cell.last}（可能被篩選掉），請手動填。`);
      }
      const billsMa = cell.rows.some((r) => r.type === "MA ACCESS Billing");
      const maNote = spot.maAccess !== null && spot.maAccess !== billsMa && cell.rows.length
        ? `注意：ACE 的 MA Access 是「${spot.maAccess ? "Yes" : "No"}」，和 TheraNote 的 MA billing 設定不同。` : "";
      const existing = await ask("open", spot);
      const count = existing.direct + existing.group + existing.indirect;
      if (count && !confirm(`ACE 這一格已經有 ${count} 筆資料。要在後面再加上 TheraNote 的資料嗎？`)) {
        state.status[i] = "todo";
        throw new Error("這一格已有資料，沒有填。ACE 視窗還開著，請按 Cancel 關掉。");
      }
      state.status[i] = "filling";
      save(); render();
      const notes = await ask("fill", {rows: cell.rows});
      $("msg").dataset.keep = "1";
      say(["已填好。請在 ACE 視窗檢查，沒問題就按 Save Changes；按 Cancel 會標記為跳過。", maNote, ...notes]
        .filter(Boolean).join("\n"));
      render();
    } catch (error) {
      if (state.status[i] === "filling") state.status[i] = "todo";
      $("msg").dataset.keep = "1";
      say(error.message, true);
      save(); render();
    }
  }

  function windowClosed(saved) {
    if (!state) return;
    const i = state.status.indexOf("filling");
    if (i < 0) return;
    state.status[i] = saved ? "saved" : "skipped";
    state.current = nextTodo(i + 1);
    $("msg").dataset.keep = "1";
    say(saved ? "已存。下一格準備好了，按「填這一格」繼續。" : "視窗關閉但沒有看到「Time entries saved.」，這格標記為跳過。", !saved);
    save(); render();
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
      render();
    } catch (error) {
      say(error.message, true);
    }
  });
  $("clear").addEventListener("click", async () => {
    if (!confirm("清除載入的填寫檔和進度？（ACE 裡已存的資料不受影響）")) return;
    state = null;
    await save();
    render();
  });
  const show = (on) => { host.style.display = on ? "block" : "none"; };
  $("close").addEventListener("click", () => show(false));
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.theranoteAce === "toggle") show(host.style.display === "none");
  });

  document.documentElement.append(host);
  load().then(() => {
    if (state) state.status = state.status.map((s) => (s === "filling" ? "todo" : s)); // reloaded mid-fill
    render();
  });
})();
