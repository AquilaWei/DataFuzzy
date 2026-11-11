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

  // The grid row and column of a student's day; `matches` is how many rows have the name.
  function locate({first, last, date}) {
    const g = grid();
    const store = g.getStore();
    const rows = [];
    store.each((r, i) => {
      if (norm(r.get("student_name_first")) === norm(first) && norm(r.get("student_name_last")) === norm(last)) rows.push(i);
    });
    const day = DAYS[new Date(`${date}T12:00:00`).getDay()];
    const col = g.getColumnModel().findColumnIndex(`${day}_id`);
    const record = rows.length === 1 ? store.getAt(rows[0]) : null;
    return {matches: rows.length, row: rows[0] ?? -1, col, maAccess: record ? norm(record.get("ma_access")) === "yes" : null};
  }

  function activeEditWindow() {
    const w = Ext.WindowMgr.getActive();
    return w && w.isVisible() && Ext.getCmp("TimeEntryTimeRowContainer_Direct") && w.findById("TimeEntryTimeRowContainer_Direct") ? w : null;
  }

  function entryRows(section) {
    const box = Ext.getCmp(`TimeEntryTimeRowContainer_${SECTIONS[section]}`);
    return box.items.getRange().filter((r) => r.combo_BillingCode);
  }

  // Opens the cell's "Edit Therapist Time" window; says which sections already have entries.
  async function open({row, col}) {
    if (activeEditWindow()) throw new Error("A time entry window is already open: save or cancel it first");
    const g = grid();
    g.getView().focusCell(row, col);
    const cell = g.getView().getCell(row, col);
    for (const type of ["mousedown", "mouseup", "click"]) {
      cell.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
    }
    const w = await until(activeEditWindow, "the time entry window");
    await sleep(500); // its sections load their entries after it shows
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

  const OPS = {week, locate, open, fill};

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
