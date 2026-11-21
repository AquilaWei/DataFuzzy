// Runs in ACE Portal's own page (the MAIN world) so it can reach its Ext JS 3 components: the
// weekly grid "time_grid" and the "Edit Therapist Time" window a grid cell opens. It never
// clicks Save; the user does, after checking what was filled in.
//
// content.js asks with window.postMessage({theranoteAce: "request", id, op, args}) and gets
// {theranoteAce: "reply", id, ok, value | error}. When the window it filled closes, this posts
// {theranoteAce: "closed", saved} on its own.
(() => {
  "use strict";
  const DAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
  const SECTIONS = {direct: "Direct", group: "Group", indirect: "Indirect"};

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function until(test, what, ms = 5000) {
    for (const end = Date.now() + ms; Date.now() < end; await sleep(100)) {
      const value = test();
      if (value) return value;
    }
    throw new Error(`ACE did not show ${what} in time`);
  }

  const norm = (text) => String(text ?? "").replace(/<[^>]*>/g, "").trim().toLowerCase();

  function grid() {
    const g = window.Ext && Ext.getCmp("time_grid");
    if (!g) throw new Error("This page has no time grid: open Therapist's Accountability first");
    return g;
  }

  // "Monday 11/9" for each day column the grid shows.
  function week() {
    return grid().getColumnModel().config
      .filter((c) => /_id$/.test(c.dataIndex) && DAYS.includes(c.dataIndex.slice(0, -3)))
      .map((c) => norm(c.header));
  }

  // A whole name as one string: TheraNote's family name is optional, so "Cole Crudup" may be all
  // in its given name while ACE splits it.
  const fullName = (first, last) => norm(`${first} ${last}`).replace(/\s+/g, " ");

  // The grid row and column of a student's day; `matches` is how many rows have the name. A
  // student with no family name in TheraNote is found by the first name alone when only one
  // student in the grid has it.
  async function locate({first, last, date}) {
    if (activeEditWindow()) throw new Error("A time entry window is still open: save or cancel it first");
    const other = windowTitles();
    if (other) throw new Error(`ACE 還開著 ${other} 視窗，請先關掉它`);
    await gridReady();
    const g = grid();
    const store = g.getStore();
    const name = fullName(first, last);
    const find = (test) => {
      const found = [];
      store.each((r, i) => { if (test(r)) found.push(i); });
      return found;
    };
    let rows = find((r) => fullName(r.get("student_name_first"), r.get("student_name_last")) === name);
    if (!rows.length && !norm(last)) rows = find((r) => norm(r.get("student_name_first")) === name);
    const day = DAYS[new Date(`${date}T12:00:00`).getDay()];
    const col = g.getColumnModel().findColumnIndex(`${day}_id`);
    const record = rows.length === 1 ? store.getAt(rows[0]) : null;
    const partial = typeof store.getTotalCount === "function" && store.getTotalCount() > store.getCount();
    return {matches: rows.length, row: rows[0] ?? -1, col, partial,
      maAccess: record ? norm(record.get("ma_access")) === "yes" : null};
  }

  // Every Ext window now showing, the frontmost first.
  function shownWindows() {
    const found = [];
    Ext.WindowMgr.each((w) => { if (w.isVisible && w.isVisible() && !w.isDestroyed) found.push(w); });
    const front = Ext.WindowMgr.getActive();
    return found.sort((a, b) => (b === front) - (a === front));
  }

  // The "Edit Therapist Time" window, wherever it is in the stack of windows: the one holding the
  // Direct Time section (or titled so, while its sections are still being built).
  function activeEditWindow() {
    const sections = Ext.getCmp("TimeEntryTimeRowContainer_Direct");
    return shownWindows().find((w) => (sections && w.findById && w.findById("TimeEntryTimeRowContainer_Direct"))
      || /therapist time/i.test(norm(w.title))) || null;
  }

  // What windows are open, by title, for a message when the time entry window is not found.
  const windowTitles = () => shownWindows().map((w) => `「${norm(w.title) || "?"}」`).join("、");

  function entryRows(section) {
    const box = Ext.getCmp(`TimeEntryTimeRowContainer_${SECTIONS[section]}`);
    return box.items.getRange().filter((r) => r.combo_BillingCode);
  }

  // Opens the cell's "Edit Therapist Time" window; says which sections already have entries.
  // With `watch`, posts {theranoteAce: "closed", saved: false} when the window closes again, so
  // the panel knows a window it opened to look at is gone.
  async function open({row, col, watch = false}) {
    if (activeEditWindow()) throw new Error("A time entry window is already open: save or cancel it first");
    const g = grid();
    g.getView().focusCell(row, col);
    const cell = g.getView().getCell(row, col);
    for (const type of ["mousedown", "mouseup", "click"]) {
      cell.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
    }
    const w = await until(activeEditWindow, "the time entry window").catch(() => {
      const open = windowTitles();
      throw new Error(open ? `ACE 開了 ${open}，但認不出是 Edit Therapist Time 視窗：請按 Cancel 關掉它`
        : "點了格子，但 ACE 沒有打開 Edit Therapist Time 視窗");
    });
    await until(() => Ext.getCmp("TimeEntryTimeRowContainer_Direct") && w.findById("TimeEntryTimeRowContainer_Direct"),
      "the Direct Time section");
    await sleep(500); // its sections load their entries after it shows
    if (watch) {
      w.on("hide", () => window.postMessage({theranoteAce: "closed", saved: false}, location.origin), null, {single: true});
    }
    return Object.fromEntries(Object.keys(SECTIONS).map((s) => [s, entryRows(s).length]));
  }

  function press(button) {
    if (button.handler) button.handler.call(button.scope || button, button, Ext.EventObject);
    else button.fireEvent("click", button, Ext.EventObject);
  }

  // A new empty entry row in `section`: the section's own add button when it has no row yet,
  // else the last row's.
  async function addRow(section) {
    const before = entryRows(section);
    let button = before.length ? before[before.length - 1].btn_Add : null;
    if (!button) {
      Ext.getCmp(`TimeEntryTimeRowContainer_${SECTIONS[section]}`).cascade((c) => {
        if (!button && c.getXType && c.getXType() === "button" && c.iconCls === "btn_icon_add") button = c;
      });
    }
    if (!button) throw new Error(`no add button under ${SECTIONS[section]} Time`);
    press(button);
    return until(() => entryRows(section).find((r) => !before.includes(r)), `a new ${SECTIONS[section]} Time row`);
  }

  // Letters and digits only, so "No-Show" finds ACE's "No Show".
  const key = (text) => norm(text).replace(/[^a-z0-9]/g, "");

  function pick(combo, display, label) {
    const field = combo.displayField;
    const index = combo.store.findBy((r) => key(r.get(field)) === key(display));
    if (index < 0) throw new Error(`${label} has no choice "${display}"`);
    const record = combo.store.getAt(index);
    combo.setValue(record.get(combo.valueField));
    combo.fireEvent("select", combo, record, index);
  }

  function put(field, value) {
    const old = field.getValue();
    field.setValue(value);
    field.fireEvent("change", field, value, old);
  }

  async function fillRow(entry, row) {
    pick(entry.combo_BillingCode, row.type, "Billing code");
    await sleep(400); // the fields a type asks for show after it is picked
    const notes = [];
    if (row.minutes != null) {
      if (entry.combo_Units.disabled) notes.push(`${row.type}: ACE takes no minutes here`);
      else put(entry.combo_Units, String(row.minutes));
    }
    if (row.group) {
      pick(entry.combo_GroupId, row.group.replace(/^group\s+/i, ""), "Group");
      put(entry.group_size, String(row.group_size));
    }
    if (row.start) put(entry.fld_time_start, row.start);
    if (row.end) put(entry.fld_time_end, row.end);
    if (row.comments_on_log) {
      const box = entry.textfield_CommentContainer;
      if (box && box.hidden && entry.btn_Comment) press(entry.btn_Comment);
      put(entry.textfield_Comment, row.comments_on_log);
    }
    if (row.data_towards_goals) put(entry.textfield_DataTowardsGoals, row.data_towards_goals);
    if (row.deficit) pick(entry.underlying_deficits, row.deficit, "Underlying Deficits Addressed");
    return notes;
  }

  // Presses Yes or OK on an Ext message box ACE shows, e.g. to confirm removing an entry.
  function confirmMessageBox() {
    const box = Ext.Msg && Ext.Msg.isVisible() ? Ext.Msg.getDialog() : null;
    const yes = box && (box.buttons || []).find((b) => !b.hidden && /^(yes|ok)$/i.test(norm(b.text)));
    if (yes) press(yes);
  }

  // Removes every entry the open window has, for TheraNote's to replace them. ACE deletes them
  // only when the user saves; Cancel keeps them.
  async function clear() {
    if (!activeEditWindow()) throw new Error("No time entry window is open");
    for (const section of Object.keys(SECTIONS)) {
      for (const entry of entryRows(section).reverse()) {
        const remove = entry.btn_Remove;
        if (!remove || remove.hidden || remove.disabled) {
          throw new Error(`ACE does not let a ${SECTIONS[section]} Time entry be removed (it may be approved): `
            + "press Cancel and enter this cell by hand");
        }
        press(remove);
        await until(() => { confirmMessageBox(); return !entryRows(section).includes(entry); },
          `the ${SECTIONS[section]} Time entry removed`);
      }
    }
    return true;
  }

  // The window's Cancel button: an Ext button found by its text. ACE keeps it in the window's
  // bottom toolbar; the button bar and the items are looked through as well.
  function cancelButton(w) {
    const isCancel = (b) => b && /^cancel$/i.test(norm(b.text));
    const bars = [w.getBottomToolbar && w.getBottomToolbar(), w.fbar, w.getTopToolbar && w.getTopToolbar()];
    for (const bar of bars) {
      const found = bar && bar.items && bar.items.getRange().find(isCancel);
      if (found) return found;
    }
    const found = (w.buttons || []).find(isCancel);
    if (found) return found;
    let match = null;
    w.cascade((c) => { if (!match && c.getXType && c.getXType() === "button" && isCancel(c)) match = c; });
    return match;
  }

  // Closes the open window without saving, as its Cancel button does (which only hides it), and waits until it is
  // gone and the grid is back, so the next cell can be looked up in it.
  async function cancel() {
    const w = activeEditWindow();
    if (!w) return false;
    const button = cancelButton(w);
    if (button) press(button);
    await until(() => { confirmMessageBox(); return !w.isVisible() || w.isDestroyed; }, "the time entry window closed", 3000)
      .catch(() => w.hide()); // never close(): it destroys the one window ACE reuses for every cell
    await until(() => !activeEditWindow(), "the time entry window closed");
    await gridReady();
    return true;
  }

  // Waits while the grid reloads (ACE may reload it when a window closes) and has no rows yet.
  async function gridReady() {
    await until(() => {
      const g = grid();
      const mask = g.loadMask && g.loadMask.el && g.loadMask.el.isMasked && g.loadMask.el.isMasked();
      return !mask && g.getStore().getCount() > 0;
    }, "the student list", 8000);
    return true;
  }

  let watching = null;

  // After the window this filled closes: saved if ACE then says so.
  function watchClose(w) {
    if (watching) return;
    watching = w;
    const closed = async () => {
      if (watching !== w) return; // hide and destroy both fire on close
      watching = null;
      let saved = false;
      for (let i = 0; i < 30 && !saved; i++, await sleep(100)) {
        saved = /time entries saved/i.test(document.body.innerText);
      }
      window.postMessage({theranoteAce: "closed", saved}, location.origin);
    };
    w.on("hide", closed, null, {single: true});
    w.on("destroy", closed, null, {single: true});
  }

  async function fill({rows}) {
    const w = activeEditWindow();
    if (!w) throw new Error("No time entry window is open");
    const notes = [];
    for (const row of rows) {
      const entry = await addRow(row.section);
      notes.push(...(await fillRow(entry, row)));
    }
    watchClose(w);
    return notes;
  }

  // --- checking what a cell already has ----------------------------------------------

  // The text a combo shows for its value.
  function shown(combo) {
    if (!combo || !combo.store) return "";
    const value = combo.getValue();
    const index = combo.store.findBy((r) => String(r.get(combo.valueField)) === String(value));
    return index >= 0 ? String(combo.store.getAt(index).get(combo.displayField)) : String(combo.getRawValue() || "");
  }
  const raw = (field) => (field && field.getRawValue ? String(field.getRawValue() ?? "") : "");

  // The entries of the open window, in the shape of the file's rows.
  function readEntries() {
    const entries = [];
    for (const section of Object.keys(SECTIONS)) {
      for (const entry of entryRows(section)) {
        const isGroup = section === "group";
        entries.push({section, type: shown(entry.combo_BillingCode), minutes: raw(entry.combo_Units),
          start: raw(entry.fld_time_start), end: raw(entry.fld_time_end),
          group: isGroup ? String(entry.combo_GroupId.getValue() ?? "") : "",
          group_size: isGroup ? raw(entry.group_size) : "",
          comments_on_log: raw(entry.textfield_Comment), data_towards_goals: raw(entry.textfield_DataTowardsGoals),
          deficit: shown(entry.underlying_deficits)});
      }
    }
    return entries;
  }

  const text = (value) => String(value ?? "").replace(/\r\n?/g, "\n").replace(/\s+/g, " ").trim().toLowerCase();
  const number = (value) => (String(value ?? "").trim() === "" ? null : Number(value));

  // What differs between the file's rows and a cell's entries, as short notes; [] when they
  // agree. A row's empty field is not compared; each row is matched to an entry of its section
  // and type, by start time when there are several.
  function compare(rows, entries) {
    const notes = [];
    const left = [...entries];
    for (const row of rows) {
      const label = `${SECTIONS[row.section]} ${row.type}`;
      const same = left.filter((e) => e.section === row.section && key(e.type) === key(row.type));
      const entry = same.find((e) => text(e.start) === text(row.start)) || same[0];
      if (!entry) { notes.push(`ACE 沒有 ${label}`); continue; }
      left.splice(left.indexOf(entry), 1);
      const differs = (name, ours, theirs) => notes.push(`${label} ${name}：ACE「${theirs || "空白"}」、檔案「${ours}」`);
      if (row.minutes != null && number(entry.minutes) !== row.minutes) differs("Minutes", row.minutes, entry.minutes);
      for (const [field, name] of [["start", "Start"], ["end", "End"], ["comments_on_log", "Comments on Log"],
        ["data_towards_goals", "Data Towards Goals"], ["deficit", "Underlying Deficits"]]) {
        if (row[field] && text(entry[field]) !== text(row[field])) differs(name, row[field], entry[field]);
      }
      if (row.group) {
        const group = row.group.replace(/^group\s+/i, "");
        if (text(entry.group) !== text(group)) differs("Group", group, entry.group);
        if (number(entry.group_size) !== row.group_size) differs("Group Size", row.group_size, entry.group_size);
      }
    }
    for (const entry of left) notes.push(`ACE 多了 ${SECTIONS[entry.section]} ${entry.type}`);
    return notes;
  }

  // Whether a cell already has entries and whether they are the file's: {state: "empty" |
  // "same" | "different" | "unknown", notes}. A cell with entries is opened to read them and
  // closed again with Cancel, changing nothing.
  async function scan(cell) {
    const spot = await locate(cell);
    if (spot.matches !== 1) return {state: "unknown", notes: [], matches: spot.matches};
    const g = grid();
    const day = DAYS[new Date(`${cell.date}T12:00:00`).getDay()];
    const id = g.getStore().getAt(spot.row).get(`${day}_id`);
    const shownText = norm((g.getView().getCell(spot.row, spot.col) || {}).innerText);
    if (!id && !shownText) return {state: "empty", notes: []};
    const counts = await open(spot);
    let entries;
    try {
      entries = counts.direct + counts.group + counts.indirect ? readEntries() : [];
    } finally {
      await cancel();
    }
    if (!entries.length) return {state: "empty", notes: []};
    const notes = compare(cell.rows, entries);
    return {state: notes.length ? "different" : "same", notes};
  }

  const OPS = {week, locate, open, clear, cancel, fill, scan};

  window.addEventListener("message", async (event) => {
    const msg = event.data;
    if (event.source !== window || !msg || msg.theranoteAce !== "request" || !OPS[msg.op]) return;
    try {
      const value = await OPS[msg.op](msg.args || {});
      window.postMessage({theranoteAce: "reply", id: msg.id, ok: true, value}, location.origin);
    } catch (error) {
      window.postMessage({theranoteAce: "reply", id: msg.id, ok: false, error: String(error.message || error)}, location.origin);
    }
  });
})();
