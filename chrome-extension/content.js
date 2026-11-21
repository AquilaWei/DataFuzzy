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
  const STATUS = {todo: "待填", filling: "填寫中", saved: "已存", skipped: "跳過", problem: "要手動",
    done: "已完成", check: "需確認"};
  const WAITING = ["todo", "check"]; // the cells still to go through, one by one

  let state = null; // {file: {...}, status: [..per cell], notes: [..per cell], current: index}
  let scanning = false;

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

  // The extension was reloaded or updated while this page stayed open: this copy of the panel
  // can no longer reach it.
  const STALE = "TheraNote 擴充功能已更新或重新載入，請重新整理這個 ACE 頁面（⌘R）再繼續。";
  const stale = (error) => /context invalidated/i.test(String(error && error.message));

  // chrome.storage.session, once the background worker has let this page use it (it may not
  // have started yet after the browser starts).
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

  // Keeps the progress; a failure is shown, never thrown.
  async function save() {
    try {
      await session((s) => (state ? s.set({[KEY]: state}) : s.remove(KEY)));
    } catch (error) {
      $("msg").dataset.keep = "1";
      say(stale(error) || error.message === STALE ? STALE : `進度沒能保存：${error.message}`, true);
    }
  }

  function openFile(text) {
    const file = JSON.parse(text);
    if (file.format !== FORMAT) throw new Error(`這不是 TheraNote 的 ACE 填寫檔（${FORMAT}）`);
    state = {file, status: file.cells.map((c) => (c.problems.length ? "problem" : "todo")),
      notes: file.cells.map(() => []), current: 0};
    state.current = nextTodo(0);
  }

  function nextTodo(from) {
    const i = state.status.findIndex((s, i) => i >= from && WAITING.includes(s));
    return i >= 0 ? i : state.status.findIndex((s) => WAITING.includes(s));
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
    header{display:flex;align-items:center;gap:8px;padding:8px 10px;background:#0f6e72;color:#fff;font-weight:600;
      cursor:move;user-select:none;touch-action:none}
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
    .badge.done{background:#d7f0dc;color:#1b5e20}.badge.check{background:#ffe2c2;color:#8a4500}
    .notes{margin:4px 0;padding-left:16px;color:#8a4500}
    .choice{background:#fff4ce;color:#5c4400;display:flex;flex-direction:column;gap:6px}
    .hidden{display:none}
  </style>
  <div class="panel">
    <header id="drag" title="拖曳移動面板"><span>TheraNote → ACE</span><button id="close" title="關閉（點工具列的圖示再打開）">✕</button></header>
    <div class="body" id="body">
      <div class="msg" id="msg"></div>
      <div class="actions">
        <button class="act" id="pick">選擇填寫檔…</button>
        <button class="act" id="scan" title="打開 ACE 裡已經有資料的格子，和填寫檔比對（按 Cancel 關閉，不改任何資料）">掃描 ACE</button>
        <button class="act" id="clear">清除</button>
        <input type="file" id="file" accept=".json,application/json" class="hidden">
      </div>
      <div class="msg choice hidden" id="choice"></div>
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
    $("clear").disabled = !has || scanning;
    $("scan").disabled = !has || scanning;
    $("pick").disabled = scanning;
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
    const left = state.status.filter((s) => WAITING.includes(s)).length;
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
    const notes = (state.notes && state.notes[state.current]) || [];
    if (status === "check" && notes.length) {
      const head = document.createElement("div");
      head.textContent = "ACE 已經有資料，但和檔案不同：";
      const diff = document.createElement("ul");
      diff.className = "notes";
      for (const note of notes) {
        const li = document.createElement("li");
        li.textContent = note;
        diff.append(li);
      }
      box.append(head, diff);
    }
    for (const p of cell.problems) {
      const note = document.createElement("div");
      note.className = "msg error";
      note.textContent = PROBLEMS[p] || p;
      box.append(note);
    }
    const actions = document.createElement("div");
    actions.className = "actions";
    const fill = button("填這一格", "primary", () => fillCurrent());
    fill.disabled = scanning || status === "filling" || cell.problems.length > 0;
    const skip = button(status === "skipped" ? "改回待填" : "跳過", "", () => {
      state.status[state.current] = status === "skipped" ? "todo" : "skipped";
      if (status !== "skipped") state.current = nextTodo(state.current + 1);
      save(); render();
    });
    skip.disabled = scanning || status === "filling";
    actions.append(fill, skip);
    box.append(actions);
  }

  // Asks in the panel, above the cells, and resolves with the key of the button pressed.
  function choose(text, options) {
    return new Promise((resolve) => {
      const box = $("choice");
      const question = document.createElement("div");
      question.textContent = text;
      const actions = document.createElement("div");
      actions.className = "actions";
      for (const [key, label] of options) {
        actions.append(button(label, key === options[0][0] ? "primary" : "", () => {
          box.replaceChildren();
          box.classList.add("hidden");
          resolve(key);
        }));
      }
      box.replaceChildren(question, actions);
      box.classList.remove("hidden");
    });
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
          : spot.partial ? `ACE 清單這一頁找不到 ${cell.first} ${cell.last}，請翻到這位學生所在的那一頁再按一次。`
          : `ACE 清單找不到 ${cell.first} ${cell.last}（可能被篩選掉，或 ACE 上的名字拼法不同），請手動填。`);
      }
      const billsMa = cell.rows.some((r) => r.type === "MA ACCESS Billing");
      const maNote = spot.maAccess !== null && spot.maAccess !== billsMa && cell.rows.length
        ? `注意：ACE 的 MA Access 是「${spot.maAccess ? "Yes" : "No"}」，和 TheraNote 的 MA billing 設定不同。` : "";
      state.status[i] = "filling";
      render();
      const existing = await ask("open", spot);
      const count = existing.direct + existing.group + existing.indirect;
      if (count) {
        const choice = await choose(`ACE 這一格已經有 ${count} 筆資料（Direct ${existing.direct}、Group ${existing.group}、`
          + `Indirect ${existing.indirect}）。要取代成 TheraNote 的資料，還是跳過這一格？`,
        [["replace", "取代"], ["skip", "跳過"]]);
        if (choice === "skip") {
          await ask("cancel");
          state.status[i] = "skipped";
          state.current = nextTodo(i + 1);
          $("msg").dataset.keep = "1";
          say("已跳過這一格，ACE 原本的資料沒有動。");
          save(); render();
          return;
        }
        await ask("clear");
      }
      save();
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

  // On the user's word only (the 掃描 ACE button), never on loading a file. Each cell ACE already has entries in is opened, compared with
  // the file and closed again with Cancel. The same entries mark it done, other entries mark it
  // for checking (with what differs), and an empty cell stays as it was.
  async function scanAll() {
    if (!state || scanning) return;
    scanning = true;
    let done = 0, check = 0, failed = 0;
    try {
      const week = await ask("week");
      if (!week.length || !week[0].endsWith(` ${monthDay(state.file.week[0])}`)) {
        throw new Error(`ACE 現在顯示的週（${week[0] || "?"}）不是檔案的週（${state.file.week[0]} 起），請先切換週次再按「掃描 ACE」。`);
      }
      const cells = state.file.cells;
      for (let i = 0; i < cells.length; i++) {
        if (!["todo", "check", "problem", "skipped"].includes(state.status[i])) continue;
        say(`掃描 ACE 已有的資料… ${i + 1}／${cells.length}`);
        try {
          const result = await ask("scan", cells[i]);
          if (result.state === "same") { state.status[i] = "done"; state.notes[i] = []; done++; }
          else if (result.state === "different" && state.status[i] !== "problem") {
            state.status[i] = "check"; state.notes[i] = result.notes; check++;
          }
        } catch (error) {
          failed++;
          await ask("cancel").catch(() => {});
        }
      }
      state.current = nextTodo(0);
      $("msg").dataset.keep = "1";
      const left = state.status.filter((s) => WAITING.includes(s)).length;
      say(`掃描完成：${done} 格和 ACE 一致（已完成），${check} 格 ACE 有資料但不同（需確認），還有 ${left} 格要一個個處理。`
        + (failed ? `\n${failed} 格沒能掃描，照原本的狀態。` : ""));
    } catch (error) {
      $("msg").dataset.keep = "1";
      say(error.message, true);
    } finally {
      scanning = false;
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
      $("msg").dataset.keep = "1";
      say(`已載入 ${state.file.cells.length} 格。按「掃描 ACE」先比對 ACE 已有的資料，或選一格按「填這一格」。`);
      render();
    } catch (error) {
      say(error.message, true);
    }
  });
  $("scan").addEventListener("click", () => scanAll());
  $("clear").addEventListener("click", async () => {
    if (!confirm("清除載入的填寫檔和進度？（ACE 裡已存的資料不受影響）")) return;
    state = null;
    await save();
    render();
  });
  const show = (on) => { host.style.display = on ? "block" : "none"; if (on) keepInView(); };

  // The panel is moved by its header and stays where it was left (per browser, in
  // chrome.storage.local), always kept within the window.
  const POSITION = "theranoteAcePosition";
  function place(left, top) {
    const width = host.offsetWidth || 320, height = host.offsetHeight || 60;
    left = Math.min(Math.max(0, left), Math.max(0, window.innerWidth - width));
    top = Math.min(Math.max(0, top), Math.max(0, window.innerHeight - Math.min(height, 40)));
    Object.assign(host.style, {left: `${left}px`, top: `${top}px`, right: "auto"});
    return {left, top};
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
      .catch(() => {}); // only the remembered position is lost
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
    if (state) {
      state.status = state.status.map((s) => (s === "filling" ? "todo" : s)); // reloaded mid-fill
      state.notes = state.notes || state.file.cells.map(() => []);
    }
    render();
  }, (error) => {
    render();
    $("msg").dataset.keep = "1";
    say(stale(error) || error.message === STALE ? STALE : `讀不到先前的進度（${error.message}），請重新選擇填寫檔。`, true);
  });
})();
