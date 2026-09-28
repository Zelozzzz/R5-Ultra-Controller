/* Dorsal's page. Python (webui.py) pushes state with dorsal.state(...) and
   the LED color with dorsal.frame(...); clicks go back through
   window.pywebview.api. The page keeps only what's being edited (the macro
   editor, a text field) and otherwise draws exactly what the state says. */
"use strict";

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const PRESET_COLORS = ["#FF0000", "#FF6A00", "#FFD000", "#00FF66", "#00D5FF", "#0055FF", "#8B3DFF", "#FF2D95", "#FFFFFF"];
const BUTTON_NAMES = { 1: "Left click", 2: "Right click", 3: "Wheel click", 4: "Back", 5: "Forward" };
// Where each button's callout ends, as fractions of the mouse's outline, and which side its label is on.
const CALLOUTS = [[1, "left", .30, .10], [3, "left", .50, .21], [5, "left", .02, .37],
                  [4, "left", .02, .48], [2, "right", .70, .10], [0, "right", .97, .56]];

let S = null;               // the latest state from Python
let A = null;               // assets: backdrop, mouse layers, probe names, step kinds
let tab = "home";
const ui = {
  stage: 0, button: 4, bindingFor: null, readFor: null, draft: null,
  macro: { steps: [], id: null, name: "Untitled macro", saved: null, sel: null },
  profileSel: null, slotSeen: null, noticeSeen: new Set(),
  trafficSeq: 0, trafficPaused: false, trafficLines: [], logLen: -1,
  dragging: new Set(), timers: {}, views: {},
};

// talking to Python

async function call(name, ...args) {
  const api = window.pywebview && window.pywebview.api;
  if (!api || !api[name]) return undefined;
  try {
    const r = await api[name](...args);
    if (r && r.ok === false) { toast(r.error, "err"); return undefined; }
    return r ? r.value : undefined;
  } catch (e) {
    toast(String(e.message || e), "err");
    return undefined;
  }
}
async function attempt(name, ...args) {          // like call, but says whether it worked
  const api = window.pywebview && window.pywebview.api;
  if (!api) return { ok: false };
  const r = await api[name](...args);
  if (r && r.ok === false) toast(r.error, "err");
  return r || { ok: false };
}

window.addEventListener("error", (e) => { console.error(e.message); });

// dialogs and toasts

function toast(text, tone = "") {
  const t = document.createElement("div");
  t.className = `toast glass ${tone ? "c-" + tone : ""}`;
  t.textContent = text;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3800);
}

function dialog({ title, text = "", input = null, buttons = [{ label: "OK", value: true, primary: true }], html = "" }) {
  return new Promise((resolve) => {
    const m = $("#dialog"), scrim = $("#scrim");
    m.innerHTML = `<h2>${esc(title)}</h2>${text ? `<p>${esc(text).replace(/\n/g, "<br>")}</p>` : ""}${html}
      ${input !== null ? `<input class="input" id="dlg-input" spellcheck="false" value="${esc(input)}">` : ""}
      <div class="buttons">${buttons.map((b, i) => `<button class="btn ${b.primary ? "primary" : ""}" data-i="${i}">${esc(b.label)}</button>`).join("")}</div>`;
    m.hidden = scrim.hidden = false;
    const field = $("#dlg-input", m);
    const done = (value) => {
      m.hidden = true; m.innerHTML = "";
      scrim.hidden = $("#modal").hidden;          // keep the scrim if the firmware window is still open
      document.removeEventListener("keydown", key, true); resolve(value);
    };
    const key = (e) => {
      if (e.key === "Escape") { e.preventDefault(); done(null); }
      if (e.key === "Enter" && field) { e.preventDefault(); done(field.value); }
    };
    document.addEventListener("keydown", key, true);
    $$("button[data-i]", m).forEach((b) => b.onclick = () => {
      const v = buttons[+b.dataset.i].value;
      done(field && v === true ? field.value : v);
    });
    if (field) { field.focus(); field.select(); } else $("button.primary", m)?.focus();
  });
}
const confirmBox = (title, text, yes = "OK") =>
  dialog({ title, text, buttons: [{ label: "Cancel", value: false }, { label: yes, value: true, primary: true }] });
const promptBox = (title, text, value = "") =>
  dialog({ title, text, input: value, buttons: [{ label: "Cancel", value: null }, { label: "OK", value: true, primary: true }] });

// the LED preview

function frame(r, g, b, level) {
  const peak = Math.max(r, g, b);
  const strength = peak ? Math.pow(peak / 255, .6) * level : 0;
  const k = peak ? 255 / peak : 0;
  // An LED looks brighter than its raw color: lift the channels a little toward
  // white so deep colors (pure blue especially) still read as light, not shadow.
  const lift = (c) => Math.round(c * k + (255 - c * k) * .16);
  const root = document.documentElement.style;
  root.setProperty("--led", `${lift(r)}, ${lift(g)}, ${lift(b)}`);
  root.setProperty("--led-strength", strength.toFixed(3));
}

function buildArt() {
  $$("[data-art]").forEach((el) => {
    if (!A.mouse) { el.innerHTML = ""; return; }
    const m = A.mouse;
    el.innerHTML = `<img class="base" src="${m.base}" draggable="false" alt="">
      <div class="bloom" style="-webkit-mask-image:url(${m.glow});mask-image:url(${m.glow})"></div>
      <div class="glow" style="-webkit-mask-image:url(${m.glow});mask-image:url(${m.glow})"></div>
      <div class="core" style="-webkit-mask-image:url(${m.core});mask-image:url(${m.core})"></div>`;
  });
}

// controls

function rangeFill(input) {
  const pct = (input.value - input.min) / (input.max - input.min) * 100;
  input.style.setProperty("--pct", `${pct}%`);
}
function trackDrag(input) {
  input.addEventListener("pointerdown", () => ui.dragging.add(input.id));
  const up = () => setTimeout(() => ui.dragging.delete(input.id), 250);
  input.addEventListener("pointerup", up);
  input.addEventListener("change", up);
}
function setRange(input, value) {
  if (ui.dragging.has(input.id)) return;
  if (+input.value !== value) input.value = value;
  rangeFill(input);
}
function throttle(key, ms, fn) {           // at most one call per `ms`, always ending on the last value
  const t = ui.timers[key] || (ui.timers[key] = { last: 0, pending: null });
  const run = () => { t.last = performance.now(); t.pending = null; fn(); };
  clearTimeout(t.pending);
  const wait = ms - (performance.now() - t.last);
  if (wait <= 0) run(); else t.pending = setTimeout(run, wait);
}

const dpiFrac = (v) => Math.log(Math.max(S.dpi_min, v) / S.dpi_min) / Math.log(S.dpi_max / S.dpi_min);
function dpiFromFrac(f) {
  const v = S.dpi_min * Math.pow(S.dpi_max / S.dpi_min, f);
  const step = v < 5000 ? 50 : v < 20000 ? 100 : 500;
  return Math.max(S.dpi_min, Math.min(S.dpi_max, Math.round(v / step) * step));
}

function notched(host, values, current, onPick, labels = values) {
  const n = values.length;
  const key = JSON.stringify([values, current]);
  if (host.dataset.key === key) return;
  host.dataset.key = key;
  const idx = Math.max(0, values.indexOf(current));
  host.innerHTML = `<div class="track"></div><div class="fill" style="width:${n > 1 ? idx / (n - 1) * 100 : 0}%"></div>` +
    values.map((v, i) => `<div class="notch ${v === current ? "on" : ""}" style="left:${n > 1 ? i / (n - 1) * 100 : 50}%"><span>${esc(labels[i])}</span><i></i></div>`).join("");
  host.onpointerdown = (e) => {
    const pick = (ev) => {
      const r = host.getBoundingClientRect();
      const f = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width));
      const v = values[Math.round(f * (n - 1))];
      if (v !== S[host.dataset.setting]) onPick(v);
    };
    pick(e);
    host.setPointerCapture(e.pointerId);
    host.onpointermove = pick;
    host.onpointerup = () => { host.onpointermove = null; };
  };
}

// callouts around a mouse picture

function layoutCallouts(host, art, onClick, selected = null, withLabels = false) {
  if (!A || !A.mouse || !S) { host.innerHTML = ""; return; }
  const box = A.mouse.box;
  const hr = host.getBoundingClientRect(), box0 = art.getBoundingClientRect();
  if (!box0.width) return;
  // Where the photo really is inside its box (it's centered, never stretched).
  const ratio = 520 / 840;
  const w = Math.min(box0.width, box0.height * ratio), h = w / ratio;
  const ar = { left: box0.left + (box0.width - w) / 2, top: box0.top + (box0.height - h) / 2, width: w, height: h };
  const pad = 22;
  let html = "";
  for (const [code, side, fx, fy] of CALLOUTS) {
    const px = ar.left - hr.left + (box[0] + (box[2] - box[0]) * fx) * ar.width;
    const py = ar.top - hr.top + (box[1] + (box[3] - box[1]) * fy) * ar.height;
    const b = code ? S.bindings.find((x) => x.code === code) : null;
    const label = code === 0 ? "DPI" : b && b.label ? b.label : BUTTON_NAMES[code];
    const remapped = b && b.label && b.label !== BUTTON_NAMES[code];
    const x0 = side === "left" ? pad : px, x1 = side === "left" ? px : hr.width - pad;
    const cls = `callout ${remapped ? "remapped" : ""} ${selected === code ? "on" : ""}`;
    // Buttons page: the button's name, plus what it does when that isn't its default.
    const name = withLabels && code ? BUTTON_NAMES[code] + (remapped ? ` → ${label}` : "") : label;
    const sub = "";
    html += `<div class="${cls}" data-code="${code}" style="left:${x0}px;top:${py - 30}px;width:${x1 - x0}px;height:34px">
      <div class="line" style="left:0;right:0;top:30px"></div>
      <div class="pin" style="left:${side === "left" ? x1 - x0 : 0}px;top:30px"></div>
      <span class="name" style="${side === "left" ? "left:0" : "right:0"};top:10px;bottom:auto">${esc(name)}</span>${sub}</div>`;
  }
  host.innerHTML = html;
  $$(".callout", host).forEach((c) => {
    const code = +c.dataset.code;
    if (code) c.onclick = () => onClick(code); else c.style.pointerEvents = "none";
  });
}

// rendering

function renderHeader() {
  const dot = $("#link-dot"), text = $("#link-text");
  dot.className = "dot";
  if (!S.connected) { dot.classList.add("err"); text.textContent = "Not connected"; }
  else if (S.battery && S.battery.asleep) { dot.classList.add("warn"); text.textContent = "Asleep · move the mouse"; }
  else {
    dot.classList.add("ok");
    text.textContent = `${S.link_type === "USB cable" ? "USB cable" : "2.4 GHz"} · Connected`;
  }
  const b = S.battery, bat = $("#battery");
  bat.hidden = !(b && !b.asleep && b.percent != null);
  if (!bat.hidden) {
    $("#battery-pct").innerHTML = `${b.percent}%${b.charging ? '<svg class="ic sm"><use href="#i-bolt"/></svg>' : ""}`;
    const fill = $("#battery-fill");
    fill.style.width = `${Math.max(3, b.percent)}%`;
    fill.style.background = b.percent > 50 ? "var(--ok)" : b.percent > 20 ? "var(--warn)" : "var(--err)";
  }
  $("#profile-label").textContent = `Profile ${S.profile}`;
}

function renderHome() {
  if (!ui.dragging.has("sv") && !ui.dragging.has("hue")) document.documentElement.style.setProperty("--led-hex", S.color);
  syncPicker();
  $$("#presets button").forEach((b) => b.classList.toggle("on", b.dataset.c === S.color && !S.effect));
  setRange($("#brightness"), S.brightness);
  $("#bright-text").textContent = `${Math.round(S.brightness / 255 * 100)}%`;

  const fxKey = JSON.stringify([S.effects.map((e) => e.key), S.effect]);
  const fx = $("#effects");
  if (fx.dataset.key !== fxKey) {
    fx.dataset.key = fxKey;
    const chips = [{ key: null, name: "Static" }, ...S.effects];
    fx.innerHTML = chips.map((e) => `<button class="${S.effect === e.key ? "on" : ""}" data-key="${e.key ?? ""}" title="${esc(e.subtitle || "One steady color")}">${esc(e.name)}</button>`).join("");
    $$("button", fx).forEach((b) => b.onclick = () => {
      const key = b.dataset.key || null;
      if (key === null) { if (S.effect) call("set_effect", null); }
      else if (S.effect !== key) call("set_effect", key);
    });
  }
  $("#rainbow-row").hidden = S.effect !== "rainbow";
  if (S.effect === "rainbow") {
    setRange($("#rainbow-speed"), Math.round((30 - S.rainbow.speed) / 29.5 * 1000));
    $("#rainbow-text").textContent = `${S.rainbow.speed.toFixed(1)} s per cycle`;
  }

  $$(".quick-toggle").forEach((b) => b.classList.toggle("on", !!S[b.dataset.setting]));
  $("#deb-text").textContent = `${S.debounce} ms`;

  // DPI: the stage you're editing is the one the mouse is on
  if (S.active_stage !== ui.lastActive) { ui.lastActive = S.active_stage; ui.stage = S.active_stage - 1; }
  ui.stage = Math.max(0, Math.min(5, ui.stage));
  const dv = $("#dpi-value");
  if (document.activeElement !== dv) dv.value = S.stage_dpis[ui.stage].toLocaleString();
  $("#dpi-stage-of").textContent = `Stage ${ui.stage + 1} of ${S.stage_dpis.length}` + (ui.stage + 1 === S.active_stage ? " · in use" : "");
  $("#dpi-min").textContent = S.dpi_min.toLocaleString();
  $("#dpi-max").textContent = S.dpi_max.toLocaleString();
  setRange($("#dpi"), Math.round(dpiFrac(S.stage_dpis[ui.stage]) * 1000));
  const stages = $("#stages");
  const stKey = JSON.stringify([S.stage_dpis, S.active_stage, ui.stage]);
  if (stages.dataset.key !== stKey) {
    stages.dataset.key = stKey;
    stages.innerHTML = S.stage_dpis.map((v, i) => `<button class="stage-row ${i === ui.stage ? "on" : ""} ${i + 1 === S.active_stage ? "live" : ""}"
        data-i="${i}" title="Click to switch to it, double-click to type a value">
        <span class="stage-n">${i + 1}</span><span class="stage-bar"><i style="width:${(dpiFrac(v) * 100).toFixed(1)}%"></i></span>
        <b>${v.toLocaleString()}</b></button>`).join("");
    $$(".stage-row", stages).forEach((b) => {
      b.onclick = () => goStage(+b.dataset.i);
      b.ondblclick = () => { goStage(+b.dataset.i); dv.focus(); };
    });
  }

  $("#polling").dataset.setting = "polling";
  notched($("#polling"), S.polling_values, S.polling, (v) => call("set_setting", "polling", v));
  $("#polling-note").textContent = S.link_type === "USB cable" ? "Hz · cable max 1000" : "Hz";
  $("#lod").dataset.setting = "lod";
  notched($("#lod"), S.lod_values, S.lod, (v) => call("set_setting", "lod", v));

  const mode = $("#competitive"), busy = S.busy.includes("competitive");
  mode.classList.toggle("enabled", S.competitive === true && !busy);
  mode.classList.toggle("unknown", S.competitive == null || busy);      // not read yet: neither on nor off
  mode.disabled = !S.connected || S.busy.some((b) => ["competitive", "flash", "apply", "studio"].includes(b));
  mode.setAttribute("aria-pressed", S.competitive === true ? "true" : "false");
  mode.setAttribute("aria-label", S.competitive == null ? "Read Competitive Mode" : `Turn Competitive Mode ${S.competitive ? "off" : "on"}`);
  $("#competitive-state").textContent = busy ? "Checking…" : !S.connected ? "Offline" : S.competitive == null ? "Read state" : S.competitive ? "On" : "Off";
  placeCallouts();
}

// clicking a stage switches the mouse to it
function goStage(i) {
  ui.stage = Math.max(0, Math.min(5, i));
  ui.lastActive = ui.stage + 1;
  call("set_active_stage", ui.stage + 1);
  renderHome();
}

function wireDpiField() {
  const field = $("#dpi-value");
  let cancel = false;
  field.onfocus = () => { cancel = false; field.value = String(S.stage_dpis[ui.stage]); field.select(); };
  field.onkeydown = (e) => {
    if (e.key === "Enter") field.blur();
    if (e.key === "Escape") { cancel = true; field.blur(); }
  };
  field.onblur = () => {
    const v = parseInt(field.value.replace(/[,\s]/g, ""), 10);
    if (!cancel && !isNaN(v) && v !== S.stage_dpis[ui.stage]) call("set_stage_dpi", ui.stage, Math.max(S.dpi_min, Math.min(S.dpi_max, v)));
    field.value = S.stage_dpis[ui.stage].toLocaleString();
  };
}

function placeCallouts() {
  if (tab === "home") layoutCallouts($("#home-callouts"), $("#home-art"), (code) => { ui.button = code; showTab("buttons"); });
  if (tab === "buttons") layoutCallouts($("#btn-callouts"), $("#btn-callouts").previousElementSibling, (code) => {
    if (!BUTTON_NAMES[code]) { toast("The DPI button always switches DPI."); return; }
    ui.button = code; renderButtons(true);
  }, ui.button, true);
}

function renderDock() {
  document.body.classList.toggle("home", tab === "home");
  // the bar only shows up when something hasn't been sent to the mouse yet
  const applying = S.busy.includes("apply");
  $(".dock-row").hidden = !S.dirty && !applying;
  $("#status").textContent = S.dirty && !applying ? "Not applied" : "";
  $("#version").textContent = `v${S.version}`;
  $("#dock-read").hidden = tab !== "profiles";
  $("#dock-read").disabled = !S.connected || S.busy.includes("read");
  const btn = $("#apply");
  btn.hidden = !S.dirty && !applying;
  btn.textContent = applying ? "Applying…" : "Apply";
  btn.disabled = applying || !S.connected;
}

// buttons page

// Same layout as the big mouse apps: pick a button on the mouse, pick a
// category on the left, set it up in the middle.
const ASSIGN_CATS = [
  { key: "default", name: "Default", icon: "i-reset" },
  { key: "keyboard", name: "Keyboard function", icon: "i-kbd" },
  { key: "mouse", name: "Mouse function", icon: "i-mouse",
    options: ["Left click", "Right click", "Wheel click", "Back", "Forward", "Scroll up", "Scroll down", "Double click"] },
  { key: "sensitivity", name: "Sensitivity", icon: "i-gauge",
    options: ["DPI up", "DPI down", "DPI cycle", "Lock DPI", "Polling rate cycle", "Lift-off cycle"] },
  { key: "macro", name: "Macro", icon: "i-rec" },
  { key: "profile", name: "Switch profile", icon: "i-layers", options: ["Profile cycle"] },
  { key: "media", name: "Multimedia", icon: "i-play",
    options: ["Play / pause", "Stop", "Next track", "Previous track", "Volume up", "Volume down", "Mute", "Media player"] },
  { key: "windows", name: "Windows shortcuts", icon: "i-grid",
    options: ["Calculator", "My computer", "File explorer", "Email", "Browser home", "Browser refresh"] },
  { key: "disable", name: "Disable", icon: "i-x" },
];
const OPTION_HINTS = {
  "DPI up": "Next DPI stage, stops at the last one", "DPI down": "Previous DPI stage, stops at the first one",
  "DPI cycle": "Next stage, wraps back to the first", "Lock DPI": "Jumps to one fixed DPI",
  "Polling rate cycle": "Steps through the polling rates", "Lift-off cycle": "Steps through the lift-off heights",
  "Profile cycle": "Next onboard profile, wraps around", "Double click": "Two left clicks in one press",
};
const PLAYBACK = [
  ["once", "Play once"], ["times", "Play multiple times"],
  ["toggle", "Toggle continuous playback"], ["hold", "Play while the button is held"],
];

function catFor(action) {
  if (action === "Keyboard shortcut") return "keyboard";
  if (action === "Onboard macro") return "macro";
  if (action === "Disabled") return "disable";
  return (ASSIGN_CATS.find((c) => c.options && c.options.includes(action)) || { key: "mouse" }).key;
}

// the draft is what's picked in the panel; it only goes to the mouse on Save
function draftFrom(b) {
  const code = ui.button, action = b ? b.action : BUTTON_NAMES[code];
  const d = { cat: action === BUTTON_NAMES[code] ? "default" : catFor(action), action,
              shortcut: b && b.shortcut ? b.shortcut : "", slot: b ? b.slot : freeSlot(code),
              macroId: "", repeats: b ? b.repeats : 1, dpi: b ? b.dpi : 800, playback: "once" };
  if (action === "Onboard macro") d.playback = b.mode === "times" ? (b.repeats > 1 ? "times" : "once") : b.mode;
  if (d.repeats < 2) d.repeats = 3;
  return d;
}

// a slot no other button is using, so a new macro doesn't clobber one
function freeSlot(code) {
  const used = S.bindings.filter((b) => b.code !== code && b.action === "Onboard macro").map((b) => b.slot);
  return [1, 2, 3].find((n) => !used.includes(n)) || 1;
}

function renderButtons(force = false) {
  if (![1, 2, 3, 4, 5].includes(ui.button)) ui.button = 4;
  const code = ui.button, b = S.bindings.find((x) => x.code === code);
  const editKey = `${S.profile}:${code}:${b && b.label}:${b && b.action}:${b && b.mode}`;
  if (ui.bindingFor !== editKey) { ui.bindingFor = editKey; ui.draft = draftFrom(b); force = true; }
  const d = ui.draft, locked = code === 1;
  $("#assign-button").textContent = BUTTON_NAMES[code];
  $("#assign-profile").textContent = S.profile;
  $("#assign-now").textContent = b && b.label ? `now: ${b.label}` : "";

  const cats = $("#assign-cats");
  const catKey = JSON.stringify([d.cat, locked]);
  if (cats.dataset.key !== catKey) {
    cats.dataset.key = catKey;
    cats.innerHTML = ASSIGN_CATS.map((c) => `<button class="cat ${c.key === d.cat ? "on" : ""}" data-cat="${c.key}" ${locked ? "disabled" : ""}>
      <svg class="ic"><use href="#${c.icon}"/></svg><span>${esc(c.name)}</span></button>`).join("");
    $$(".cat", cats).forEach((el) => el.onclick = () => pickCat(el.dataset.cat));
  }
  $("#assign-title").textContent = (ASSIGN_CATS.find((c) => c.key === d.cat) || {}).name || "";

  const body = $("#assign-body");
  const bodyKey = JSON.stringify([d.cat, d.action, d.playback, d.macroId, d.slot, S.macros.map((m) => [m.id, m.name]), locked, code]);
  if (force || body.dataset.key !== bodyKey) { body.dataset.key = bodyKey; body.innerHTML = assignBody(d, locked); wireAssignBody(); }

  const busy = S.busy.includes("studio");
  const changed = JSON.stringify(d) !== JSON.stringify(draftFrom(b));
  $("#assign-save").disabled = busy || locked || !S.connected;
  $("#assign-save").textContent = busy ? "Saving…" : "Save to mouse";
  $("#assign-cancel").disabled = !changed;
  $("#binding-read").disabled = busy || !S.connected;
  $("#assign-note").textContent = locked ? "Left click stays left click, so you can't lock yourself out."
    : !S.connected ? "Plug in the mouse or dongle to save." : "";
  placeCallouts();
}

function pickCat(key) {
  const d = ui.draft, cat = ASSIGN_CATS.find((c) => c.key === key);
  d.cat = key;
  if (key === "default") d.action = BUTTON_NAMES[ui.button];
  else if (key === "keyboard") d.action = "Keyboard shortcut";
  else if (key === "macro") d.action = "Onboard macro";
  else if (key === "disable") d.action = "Disabled";
  else if (!cat.options.includes(d.action)) d.action = cat.options[0];
  renderButtons(true);
}

function radio(value, label, on, hint = "") {
  return `<button class="opt ${on ? "on" : ""}" data-val="${esc(value)}"><i></i><span>${esc(label)}${hint ? `<small>${esc(hint)}</small>` : ""}</span></button>`;
}

function assignBody(d, locked) {
  const name = BUTTON_NAMES[ui.button];
  if (locked) return `<p class="assign-empty">Pick another button on the mouse.</p>`;
  if (d.cat === "default") return `<p class="assign-empty">${esc(name)} goes back to being ${esc(name.toLowerCase())}.</p>`;
  if (d.cat === "disable") return `<p class="assign-empty">${esc(name)} won't do anything. Handy for a button you keep hitting by accident.</p>`;
  if (d.cat === "keyboard") return `<label class="field-label">Press the keys you want</label>
    <input class="input key-capture" id="assign-keys" value="${esc(d.shortcut)}" placeholder="Click here, then press a key or combo" spellcheck="false" readonly>
    <p class="note">One key, plus Ctrl, Shift, Alt or Win if you want. Like Ctrl+Shift+S, Alt+Tab or F6.</p>`;
  if (d.cat === "macro") {
    const own = S.macros.map((m) => `<option value="${esc(m.id)}" ${m.id === d.macroId ? "selected" : ""}>${esc(m.name)}</option>`).join("");
    return `<label class="field-label">Assign macro</label>
      <select class="select" id="assign-macro">
        <option value="" ${d.macroId ? "" : "selected"}>Whatever's in slot ${d.slot} already</option>${own}
      </select>
      ${S.macros.length ? "" : `<p class="note">No macros yet. <a href="#" id="assign-make">Make one on the Macros tab.</a></p>`}
      <label class="field-label">Onboard slot</label>
      <div class="segmented slot-seg" id="assign-slot">${[1, 2, 3].map((n) => `<button class="${d.slot === n ? "on" : ""}" data-val="${n}">Slot ${n}</button>`).join("")}</div>
      <p class="note">The mouse keeps 3 macros, shared by every profile.${d.macroId ? ` Saving puts this one in slot ${d.slot}.` : ""}</p>
      <label class="field-label">Playback option</label>
      <div class="opts" id="assign-playback">${PLAYBACK.map(([v, l]) => radio(v, l, d.playback === v)).join("")}</div>
      <div class="row gap repeat-row" ${d.playback === "times" ? "" : "hidden"}>
        <label class="field-label">Times</label><input class="input narrow" id="assign-repeats" value="${d.repeats}" inputmode="numeric">
      </div>`;
  }
  const cat = ASSIGN_CATS.find((c) => c.key === d.cat);
  return `<div class="opts" id="assign-opts">${cat.options.map((o) => radio(o, o, d.action === o, OPTION_HINTS[o])).join("")}</div>
    ${d.action === "Lock DPI" ? `<div class="row gap repeat-row"><label class="field-label">DPI</label>
      <input class="input narrow" id="assign-dpi" value="${d.dpi}" inputmode="numeric"></div>` : ""}`;
}

function wireAssignBody() {
  const d = ui.draft;
  $$("#assign-opts .opt").forEach((el) => el.onclick = () => { d.action = el.dataset.val; renderButtons(); });
  $$("#assign-playback .opt").forEach((el) => el.onclick = () => { d.playback = el.dataset.val; renderButtons(); });
  $$("#assign-slot button").forEach((el) => el.onclick = () => { d.slot = +el.dataset.val; renderButtons(); });
  const sel = $("#assign-macro"); if (sel) sel.onchange = () => { d.macroId = sel.value; renderButtons(); };
  const rep = $("#assign-repeats"); if (rep) rep.oninput = () => { d.repeats = parseInt(rep.value, 10) || 0; renderButtons(); };
  const dpi = $("#assign-dpi"); if (dpi) dpi.oninput = () => { d.dpi = parseInt(dpi.value.replace(/[,\s]/g, ""), 10) || 0; renderButtons(); };
  const make = $("#assign-make"); if (make) make.onclick = (e) => { e.preventDefault(); showTab("macros"); };
  const keys = $("#assign-keys");
  if (keys) keys.onkeydown = (e) => {
    e.preventDefault();
    if (["Control", "Shift", "Alt", "Meta"].includes(e.key)) return;
    const k = e.code === "Escape" ? "Esc" : keyName(e.code);
    if (!k) { toast("The mouse can't send that key."); return; }
    const mods = [e.ctrlKey && "Ctrl", e.shiftKey && "Shift", e.altKey && "Alt", e.metaKey && "Win"].filter(Boolean);
    d.shortcut = keys.value = [...mods, k].join("+");
    renderButtons();
  };
}

async function saveAssignment() {
  const d = ui.draft, code = ui.button;
  if (d.cat === "keyboard" && !d.shortcut) { toast("Click the box and press a key first."); return; }
  const mode = d.playback === "once" ? "times" : d.playback;
  const repeats = d.playback === "times" ? d.repeats : 1;
  if (d.cat === "macro") {
    if (d.playback === "times" && !(repeats >= 1 && repeats <= 255)) { toast("Times has to be 1 to 255.", "warn"); return; }
    const m = S.macros.find((x) => x.id === d.macroId);
    const others = S.bindings.filter((b) => b.code !== code && b.action === "Onboard macro" && b.slot === d.slot).map((b) => b.name);
    if (m && !(await confirmBox("Put macro on the mouse", `“${m.name}” goes into slot ${d.slot}, replacing what's there.` +
        (others.length ? `\n\n${others.join(" and ")} also play slot ${d.slot}, so they'll run this too.` : ""), "Save"))) return;
  }
  call("write_binding", code, d.action, d.shortcut, d.slot, repeats, mode, d.macroId || null, d.dpi);
}

// macros page

const macroDoc = () => JSON.stringify({ name: $("#macro-name").value, steps: ui.macro.steps });
function macroDirty() {
  const m = ui.macro;
  if (!m.steps.length && m.saved === null) return false;
  return macroDoc() !== m.saved;
}
async function discardOk() {
  if (!macroDirty()) return true;
  return confirmBox("Unsaved macro", "Discard the unsaved macro edits?", "Discard");
}
function loadMacro(doc, id = null) {
  ui.macro.steps = (doc.steps || []).map((s) => ({ kind: s.kind, value: s.value }));
  ui.macro.id = id; ui.macro.sel = null;
  $("#macro-name").value = doc.name || "Untitled macro";
  ui.macro.saved = id ? macroDoc() : null;
  renderMacro();
  renderMacroLibrary();
}
function renderMacroLibrary() {
  const sel = $("#macro-library");
  const query = $("#macro-search").value.trim().toLowerCase();
  const key = JSON.stringify([S.macros.map((m) => [m.id, m.name, m.steps.length]), ui.macro.id, query]);
  if (sel.dataset.key === key) return;
  sel.dataset.key = key;
  sel.innerHTML = `<option value="">New macro</option>` + S.macros.map((m, i) => `<option value="${esc(m.id)}">${i + 1}. ${esc(m.name)}</option>`).join("");
  sel.value = ui.macro.id || "";
  const matches = S.macros.filter((m) => m.name.toLowerCase().includes(query));
  $("#macro-library-list").innerHTML = matches.length ? matches.map((m) =>
    `<button class="macro-library-item ${m.id === ui.macro.id ? "on" : ""}" data-id="${esc(m.id)}" aria-pressed="${m.id === ui.macro.id}"><span><b>${esc(m.name)}</b><small>${m.steps.length} step${m.steps.length === 1 ? "" : "s"}</small></span></button>`).join("") :
    `<p class="empty">${query ? "No matching macros." : "Your library starts here.<br>Create a macro or import one."}</p>`;
  $$(".macro-library-item").forEach((b) => b.onclick = () => {
    sel.value = b.dataset.id; sel.dispatchEvent(new Event("change"));
  });
}
async function renderMacro() {
  const m = ui.macro, table = $("#macro-table");
  let elapsed = 0;
  const rows = m.steps.map((s, i) => {
    if (s.kind === "Delay") elapsed += +s.value;
    return `<div class="tr ${i === m.sel ? "on" : ""}" data-i="${i}"><span class="muted">${String(i + 1).padStart(2, "0")}</span>
      <span>${esc(s.kind)}</span><span>${esc(s.kind === "Delay" ? `${s.value} ms` : s.value)}</span><span class="muted">${elapsed.toLocaleString()} ms</span></div>`;
  });
  table.innerHTML = `<div class="tr th"><span>#</span><span>Action</span><span>Value</span><span>Elapsed</span></div>` +
    (rows.length ? rows.join("") : `<div class="empty big"><span class="empty-icon"><svg class="ic"><use href="#i-kbd"/></svg></span>
      <b>No steps yet</b><span>Record what you type, or add a shortcut like Ctrl+C.</span>
      <span class="empty-actions"><button class="btn primary sm" data-proxy="macro-record">Record keys</button>
      <button class="btn sm" data-proxy="macro-shortcut">Add shortcut</button></span></div>`);
  $$("[data-proxy]", table).forEach((b) => b.onclick = () => $(`#${b.dataset.proxy}`).click());
  $$(".tr[data-i]", table).forEach((r) => r.onclick = () => {
    m.sel = +r.dataset.i;
    const s = m.steps[m.sel];
    $("#step-kind").value = s.kind; $("#step-value").value = s.value;
    renderMacro();
  });
  if (m.sel !== null) table.querySelector(`.tr[data-i="${m.sel}"]`)?.scrollIntoView({ block: "nearest" });
  $("#macro-stats").textContent = `${m.steps.length} / 256 steps · ${elapsed.toLocaleString()} ms`;
  call("set_unsaved", macroDirty());
  const check = await call("macro_check", m.steps);
  const fb = $("#macro-feedback");
  if (check) { fb.textContent = check.text; fb.className = `note ${check.ok ? "c-ok" : ""}`; }
}
async function editorStep() {
  return attempt("macro_step", $("#step-kind").value, $("#step-value").value);
}

const KEY_NAMES = {
  ControlLeft: "Ctrl", ControlRight: "RightCtrl", ShiftLeft: "Shift", ShiftRight: "RightShift", AltLeft: "Alt", AltRight: "RightAlt",
  MetaLeft: "Win", MetaRight: "RightWin", Enter: "Enter", NumpadEnter: "Enter", Backspace: "Backspace", Tab: "Tab", Space: "Space",
  Minus: "-", Equal: "=", BracketLeft: "[", BracketRight: "]", Backslash: "\\", Semicolon: ";", Quote: "'", Backquote: "`",
  Comma: ",", Period: ".", Slash: "/", CapsLock: "CapsLock", PrintScreen: "PrintScreen", ScrollLock: "ScrollLock", Pause: "Pause",
  Insert: "Insert", Home: "Home", PageUp: "PageUp", Delete: "Delete", End: "End", PageDown: "PageDown",
  ArrowRight: "Right", ArrowLeft: "Left", ArrowDown: "Down", ArrowUp: "Up",
};
function keyName(code) {
  if (KEY_NAMES[code]) return KEY_NAMES[code];
  let m = /^Key([A-Z])$/.exec(code); if (m) return m[1];
  m = /^(?:Digit|Numpad)([0-9])$/.exec(code); if (m) return m[1];
  m = /^F([0-9]{1,2})$/.exec(code); if (m && +m[1] <= 12) return code;
  return null;
}
function recordMacro() {
  return new Promise((resolve) => {
    const events = [];
    let active = false;
    const m = $("#modal"), scrim = $("#scrim");
    m.innerHTML = `<h2>Record a key sequence</h2>
      <p>Press Start, then type. Timing is recorded. F8 stops and adds the keys; Escape cancels. Keys typed in other apps are never captured.</p>
      <div class="record-status" id="rec-status">Ready</div>
      <div class="buttons"><button class="btn" id="rec-cancel">Cancel</button><button class="btn" id="rec-stop">Stop &amp; add</button>
      <button class="btn primary" id="rec-start"><svg class="ic sm rec"><use href="#i-rec"/></svg>Start</button></div>`;
    m.hidden = scrim.hidden = false;
    const status = $("#rec-status");
    const finish = (keep) => {
      document.removeEventListener("keydown", down, true);
      document.removeEventListener("keyup", up, true);
      m.hidden = scrim.hidden = true; m.innerHTML = "";
      resolve(keep ? events : null);
    };
    const feed = (e, isDown) => {
      e.preventDefault(); e.stopPropagation();
      if (e.code === "Escape") { if (isDown) finish(false); return; }
      if (e.code === "F8") { if (isDown) finish(true); return; }
      if (!active || e.repeat) return;
      const name = keyName(e.code);
      if (!name) return;
      events.push([name, isDown, e.timeStamp / 1000]);
      status.textContent = `Recording · ${events.length} key events`;
    };
    const down = (e) => feed(e, true), up = (e) => feed(e, false);
    document.addEventListener("keydown", down, true);
    document.addEventListener("keyup", up, true);
    $("#rec-start").onclick = (e) => { active = true; e.currentTarget.disabled = true; e.currentTarget.blur(); status.textContent = "Recording · type your sequence"; };
    $("#rec-stop").onclick = () => finish(true);
    $("#rec-cancel").onclick = () => finish(false);
  });
}

// profiles page

const pollText = (v) => `${String(v).replace(" Hz", "")} Hz`;

function setupFacts(p) {
  return `<div class="setup-hero"><span class="setup-color big" style="background:${esc(p.color)}"></span>${dpiBars(p.dpis, true)}</div>
    <dl class="stat-rows setup-rows">
      <dt>DPI stages</dt><dd>${p.dpis.map((v) => v.toLocaleString()).join(" · ")}</dd>
      <dt>Polling rate</dt><dd>${esc(pollText(p.polling))}</dd>
      <dt>Lift-off</dt><dd>${esc(p.lod)}</dd>
      <dt>Color</dt><dd class="mono">${esc(p.color)}</dd>
    </dl>`;
}

function renderProfiles() {
  const sel = S.profiles.some((p) => p.id === ui.setupSel) ? ui.setupSel : null;
  ui.setupSel = sel;
  const list = $("#profile-cards");
  const key = JSON.stringify([S.profiles, ui.loadedSetup, sel]);
  if (list.dataset.key !== key) {
    list.dataset.key = key;
    $("#profile-count").textContent = S.profiles.length || "";
    list.innerHTML = `<button class="list-item new ${sel ? "" : "on"}" data-id="">
        <span class="item-icon"><svg class="ic sm"><use href="#i-plus"/></svg></span>
        <span class="item-text"><b>Save current setup</b><small>What's on Home right now</small></span></button>` +
      S.profiles.map((p) => `<button class="list-item ${p.id === sel ? "on" : ""}" data-id="${esc(p.id)}">
        <span class="setup-color" style="background:${esc(p.color)}"></span>
        <span class="item-text"><b>${esc(p.name)}</b><small>${esc(pollText(p.polling))} · ${esc(p.lod)} lift-off</small></span>
        ${p.id === ui.loadedSetup ? '<span class="badge on">loaded</span>' : ""}</button>`).join("");
    $$(".list-item", list).forEach((b) => b.onclick = () => { ui.setupSel = b.dataset.id || null; ui.renaming = null; renderProfiles(); });
  }

  const d = $("#setup-detail"), p = sel && S.profiles.find((x) => x.id === sel);
  const dkey = JSON.stringify([sel, p, ui.loadedSetup, ui.renaming]);
  if (d.dataset.key !== dkey) {
    d.dataset.key = dkey;
    if (!p) {
      d.innerHTML = `<div class="pane-head"><h3 class="pane-title">Save what's on Home</h3></div>
        <div class="pane-body"><p class="sub">DPI stages, polling rate, lift-off, sensor options and lighting, saved on this PC.
          Make one for each game and load it whenever you switch.</p><div id="setup-now"></div></div>
        <div class="pane-foot"><input class="input grow" id="profile-name" placeholder="Name it, like Valorant or Desktop" maxlength="64" spellcheck="false">
          <button class="btn primary" id="profile-save">Save setup</button></div>`;
      $("#profile-save").onclick = saveSetup;
      $("#profile-name").onkeydown = (e) => { if (e.key === "Enter") saveSetup(); };
    } else {
      d.innerHTML = `<div class="pane-head">
          ${ui.renaming === p.id ? `<input class="input setup-rename" value="${esc(p.name)}" maxlength="64" spellcheck="false">`
                                 : `<h3 class="pane-title setup-name" title="Double-click to rename">${esc(p.name)}</h3>`}
          ${p.id === ui.loadedSetup ? '<span class="badge on">loaded</span>' : ""}<span class="grow"></span>
          <button class="btn quiet sm" data-act="rename">Rename</button></div>
        <div class="pane-body">${setupFacts(p)}</div>
        <div class="pane-foot">
          <button class="btn quiet danger" data-act="delete">Delete</button>
          <button class="btn quiet" data-act="export">Export</button><span class="grow"></span>
          <button class="btn" data-act="update" title="Replace it with what's on Home now">Update from Home</button>
          <button class="btn primary" data-act="load">Load</button></div>`;
      d.querySelector(".setup-name")?.addEventListener("dblclick", () => { ui.renaming = p.id; renderProfiles(); });
      const field = d.querySelector(".setup-rename");
      if (field) {
        field.focus(); field.select();
        let done = false;
        const finish = (save) => {
          if (done) return; done = true; ui.renaming = null;
          if (save && field.value.trim() && field.value.trim() !== p.name) call("rename_profile", p.id, field.value.trim());
          else renderProfiles();
        };
        field.onkeydown = (e) => { if (e.key === "Enter") finish(true); if (e.key === "Escape") finish(false); };
        field.onblur = () => finish(true);
      }
      $$("button[data-act]", d).forEach((b) => b.onclick = async () => {
        const act = b.dataset.act;
        if (act === "rename") { ui.renaming = p.id; renderProfiles(); }
        if (act === "load") { await call("load_profile", p.id); ui.loadedSetup = p.id; renderProfiles(); }
        if (act === "update" && await confirmBox("Update setup", `Replace “${p.name}” with what's on Home right now?`, "Update"))
          call("save_profile", p.name, p.id);
        if (act === "export") call("export_profile", p.id);
        if (act === "delete" && await confirmBox("Delete setup", `Delete “${p.name}” from this PC?`, "Delete")) {
          if (ui.loadedSetup === p.id) ui.loadedSetup = null;
          ui.setupSel = null;
          call("delete_profile", p.id);
        }
      });
    }
  }
  if (!p) setHtml($("#setup-now"), setupFacts({ color: S.color, dpis: S.stage_dpis, polling: S.polling, lod: S.lod }));
}

async function saveSetup() {
  const field = $("#profile-name"), name = field.value.trim();
  if (!name) { field.focus(); toast("Give the setup a name first."); return; }
  const existing = S.profiles.find((p) => p.name.toLowerCase() === name.toLowerCase());
  if (existing && !(await confirmBox("Replace setup", `You already have “${existing.name}”. Replace it with what's on Home now?`, "Replace"))) return;
  const id = await call("save_profile", name, existing ? existing.id : null);
  if (id) { ui.loadedSetup = id; ui.setupSel = id; renderProfiles(); }
}

// Little tab strips inside a pane: show the view that matches, remember which.
function wireViews(nav, views, key, onShow) {
  const show = (name) => {
    ui.views[key] = name;
    $$("button", nav).forEach((b) => b.classList.toggle("on", b.dataset.view === name));
    $$(views).forEach((v) => { v.hidden = v.dataset.view !== name; });
    if (onShow) onShow(name);
  };
  $$("button", nav).forEach((b) => b.onclick = () => show(b.dataset.view));
  show(ui.views[key] || $("button", nav).dataset.view);
}

// Six DPI stages as a small bar chart (log scale, like the DPI slider).
function dpiBars(dpis, labels = false) {
  const lo = Math.log(100), hi = Math.log(Math.max(12800, ...dpis));
  return `<span class="dpi-bars ${labels ? "labeled" : ""}">` + dpis.map((v) => {
    const h = 18 + 82 * (Math.log(Math.max(100, v)) - lo) / (hi - lo);
    return `<i style="--h:${h.toFixed(0)}%">${labels ? `<small>${v >= 1000 ? (v / 1000).toFixed(v % 1000 ? 1 : 0) + "k" : v}</small>` : ""}</i>`;
  }).join("") + `</span>` + (labels ? "" : `<span class="dpi-text">${dpis.join(" · ")}</span>`);
}

// diagnostics page

function dl(rows) {
  return rows.map(([k, v, tone]) => `<dt>${esc(k)}</dt><dd class="${tone ? "c-" + tone : ""}">${esc(v)}</dd>`).join("");
}
function setHtml(el, html) { if (el.innerHTML !== html) el.innerHTML = html; }

function renderDiagnostics() {
  const b = S.battery;
  const d = S.diagnostic;
  const q = S.link_test;
  const setRo = (id, value, detail, tone = "") => {
    const el = $(`#ro-${id}`); el.textContent = value; el.className = tone ? `c-${tone}` : "";
    $(`#ro-${id}-d`).textContent = detail;
  };
  setRo("link", q ? `${q.answered} / ${q.sent}` : "—",
        q ? `${q.no_mouse} receiver-only · ${q.lost} other misses` : "No command test yet");
  setRo("latency", q && q.median != null ? `${q.median.toFixed(2)} ms` : "—",
        q && q.p95 != null ? `p95 ${q.p95.toFixed(2)} ms · settings channel` : "Run a timed command test");
  setRo("battery", b && !b.asleep && b.percent != null ? `${b.percent}%` : "—",
        b && b.charging ? "device reports charging" : "latest device charge report");
  setRo("firmware", d?.details?.["Mouse firmware"] || "—", "Version readback cannot identify the LED patch");
  setHtml($("#device-rows"), dl([
    ["Interface", S.connected ? "R5 Ultra detected" : "Not found"],
    ["Current connection", S.link_type || "—"],
    ["Tested profile", d ? String(d.profile) : "Not tested"],
    ...Object.entries(d?.details || {}),
  ]));
  const hb = $("#health-run");
  hb.disabled = S.busy.some(b => ["health", "flash", "apply", "studio", "link", "input-start"].includes(b));
  hb.textContent = S.busy.includes("health") ? "Reading device…" : d ? "Run again" : "Run diagnostics";
  $("#diagnostic-summary").textContent = S.busy.includes("health") ? "Reading settings and timing 30 commands. Lighting may pause briefly during the read burst."
    : d?.stale ? "This result belongs to an earlier connection or profile. Run again for current evidence."
    : "Read the device, check its configuration and time 30 command responses.";
  $("#diagnostic-stamp").textContent = d ? `${new Date(d.finished_at).toLocaleString()} · ${d.duration_s.toFixed(2)} s · ${d.connection || "offline"}`
    : "No diagnostic run yet. Nothing has been marked as passed.";
  const labels = {match: "Matches", different: "Different", unavailable: "Unavailable", read: "Read"};
  setHtml($("#readback-rows"), d?.settings?.length ? d.settings.map(r => `<tr><th scope="row">${esc(r.name)}</th><td>${esc(r.observed)}</td><td>${esc(r.editor)}</td><td><span class="result ${r.status}">${labels[r.status]}</span></td></tr>`).join("")
    : '<tr><td colspan="4" class="empty">Run diagnostics to read the configuration from your mouse.</td></tr>');
  const marks = { ok: "i-check", warn: "i-alert", fail: "i-x" };
  setHtml($("#health-list"), S.health.map((c) => `<div class="check ${c.status}"><span class="mark"><svg class="ic sm"><use href="#${marks[c.status] || "i-alert"}"/></svg></span>
    <div><b>${esc(c.title)}</b>${c.detail ? `<p>${esc(c.detail)}</p>` : ""}</div></div>`).join(""));

  const r = S.link_test;
  const tone = r ? ({ good: "ok", ok: "warn" }[r.verdict] || "err") : "";
  setHtml($("#link-rows"), dl([
    ["Answered", r ? `${r.answered} of ${r.sent}` : "—", tone],
    ["Receiver-only responses", r ? r.no_mouse : "—"],
    ["Other misses", r ? r.lost : "—"],
    ["Average reply", r && r.avg != null ? `${r.avg.toFixed(1)} ms` : "—"],
    ["95th percentile", r && r.p95 != null ? `${r.p95.toFixed(1)} ms` : "—"],
    ["Reply-time standard deviation", r && r.jitter != null ? `± ${r.jitter.toFixed(1)} ms` : "—"],
  ]));
  const running = S.link_progress !== null;
  $("#link-bar").style.width = `${Math.round((running ? S.link_progress : r ? 1 : 0) * 100)}%`;
  $("#link-run").disabled = !running && (!S.connected || S.busy.some(b => ["health", "flash", "apply", "studio", "input-start"].includes(b)));
  $("#link-run").textContent = running ? "Stop" : r ? "Run again" : "Run test";
  $("#link-verdict").textContent = running ? "Testing…" : r ? r.text : "";
  $("#link-verdict").className = `note ${!running && tone ? "c-" + tone : ""}`;
  if (r && $("#link-chart").dataset.key !== String(r.latencies.length) + r.avg) {
    $("#link-chart").dataset.key = String(r.latencies.length) + r.avg;
    chart($("#link-chart"), r.latencies, null, "ms");
  }
  if (!r) chart($("#link-chart"), [], null, "ms");

  const bat = S.battery;
  const rows = [];
  if (!bat || bat.asleep || bat.percent == null) rows.push(["Charge", "—"]);
  else rows.push(["Charge", `${bat.percent}%${bat.charging ? " · charging" : ""}`, bat.percent > 50 ? "ok" : bat.percent > 20 ? "warn" : "err"]);
  let note;
  if (bat && bat.charging) { rows.push(["Drain", "—"], ["Time left", "charging"]); note = "Estimates start again once the mouse is off the charger."; }
  else if (!bat || bat.rate == null) {
    rows.push(["Drain", "measuring…"], ["Time left", "measuring…"]);
    note = "Dorsal needs to see the charge drop by 3% (at least half an hour) before it can estimate. Readings are kept between sessions.";
  } else {
    rows.push(["Drain", `${bat.rate.toFixed(1)}% per hour`], ["Time left", bat.left || "—"]);
    note = "Averaged over your recent use. Remaining time is an estimate, not a device measurement. Voltage and current are not reported by the mouse.";
  }
  setHtml($("#battery-rows"), dl(rows));
  $("#battery-note").textContent = note;
  $("#probe-result").textContent = S.probe_result || "Read-only: probes never change a setting.";
  $("#probe-run").disabled = S.busy.includes("probe") || !S.connected;
}

async function pollDiagnostics() {
  if (tab !== "diagnostics" || ui.diagnosticsPending) return;
  ui.diagnosticsPending = true;
  try {
  if (!ui.trafficPaused) {
    const entries = await call("traffic", ui.trafficSeq);
    if (entries && entries.length) {
      ui.trafficSeq = entries[entries.length - 1].seq;
      const hideFx = $("#traffic-hidefx").checked;
      const counts = ui.trafficCounts || (ui.trafficCounts = { tx: 0, ok: 0, nomouse: 0, crossed: 0, bad: 0 });
      for (const e of entries) {
        counts.tx++;
        const bucket = { accepted: "ok", "no mouse": "nomouse", mismatch: "crossed", sent: null }[e.status];
        if (bucket === undefined) counts.bad++; else if (bucket) counts[bucket]++;
        if (hideFx && (e.name === "Set light effect" || e.name === "Set DPI stage colors") && e.status === "sent") continue;
        let line = `<span class="t">${e.time}</span>  <span class="tx">TX</span> <span class="n">${esc(e.name.padEnd(24))}</span> ${esc(e.tx)}`;
        if (e.status !== "sent") {
          const tone = { accepted: "ok", "no mouse": "warn", mismatch: "warn" }[e.status] || "err";
          line += `\n${" ".repeat(14)}<span class="${tone}">RX ${esc(e.reply.padEnd(24))}</span> ${esc(e.rx)}${e.ms != null ? `   ${e.ms} ms` : ""}`;
        }
        ui.trafficLines.push(line);
      }
      if (ui.trafficLines.length > 600) ui.trafficLines.splice(0, ui.trafficLines.length - 600);
      const t = $("#traffic");
      const atBottom = t.scrollTop + t.clientHeight >= t.scrollHeight - 30;
      t.innerHTML = ui.trafficLines.join("\n");
      if (atBottom) t.scrollTop = t.scrollHeight;
      $("#traffic-counts").textContent = `${counts.tx.toLocaleString()} sent · ${counts.ok.toLocaleString()} OK · ${counts.nomouse} no mouse · ${counts.crossed} crossed · ${counts.bad} failed`;
    }
  }
  const v = await call("input_view");
  if (v) renderInput(v);
  } finally { ui.diagnosticsPending = false; }
}

function renderInput(v) {
  $("#input-toggle").textContent = v.starting ? "Reading settings…" : v.running ? `Stop · ${Math.max(0, Math.ceil(v.duration - v.elapsed))} s left` : "Capture 15 seconds";
  $("#input-toggle").disabled = v.starting || (!v.running && (!S.connected || S.busy.some(b => ["health", "link", "flash", "apply", "studio"].includes(b))));
  $("#input-hint").textContent = v.error ? v.error : v.hint ? v.hint : v.running ? (v.events ? `Listening · ${v.events.toLocaleString()} reports received` : "Listening… move the R5 Ultra.")
    : "Move the mouse in fast circles, then click each button.";
  const p = v.polling;
  const tp = $("#tile-polling");
  if (!p) { tp.textContent = v.running ? "…" : "Idle"; tp.className = ""; $("#tile-polling-d").textContent = `Need at least 1 second of continuous movement. ${v.configured ? `Mouse reported ${v.configured.toLocaleString()} Hz.` : "Polling setting not read yet."}`; }
  else {
    tp.textContent = `${Math.round(p.avg).toLocaleString()} Hz`;
    // "unverified" = polling setting couldn't be read, so no color judgement
    tp.className = { good: "c-ok", limited: "c-warn", mismatch: "c-warn", unverified: "" }[p.verdict] ?? "c-err";
    $("#tile-polling-d").textContent = `Peak ${Math.round(p.peak).toLocaleString()} Hz across ${v.samples} movement windows. ${p.text}`;
  }
  $("#tile-speed").textContent = v.ips ? `${Math.round(v.ips)} IPS` : v.running ? "…" : "Idle";
  $("#tile-speed-d").textContent = v.dpi ? `Estimated from relative counts and ${v.dpi.toLocaleString()} DPI read at capture start (stage ${v.stage}).` : "Speed requires a readable DPI stage with equal X/Y sensitivity.";
  const used = Object.entries(v.buttons);
  const chatter = used.reduce((n, [, c]) => n + c[1], 0);
  $("#tile-clicks").textContent = used.length ? `${chatter} rapid` : v.running ? "…" : "Idle";
  $("#tile-clicks").className = used.length ? (chatter ? "c-warn" : "") : "";
  $("#tile-clicks-d").textContent = used.map(([k, c]) => `${k} ${c[0]}${c[1] ? ` (${c[1]} rapid)` : ""}`).join("  ·  ") || "Click each button a few times.";
  $("#input-session").textContent = v.running || v.events ? `${v.elapsed.toFixed(1)} s · ${v.events.toLocaleString()} events · ${v.samples.toLocaleString()} windows` : "Ready to capture";
  const st = v.intervals;
  $("#input-intervals").textContent = st?.count ? `Arrival intervals   Median ${st.median.toFixed(3)} ms · P95 ${st.p95.toFixed(3)} ms · P99 ${st.p99.toFixed(3)} ms · ${st.pauses.toLocaleString()} pauses`
                                         : "Move the mouse to collect interval measurements.";
  chart($("#input-chart"), v.window_hz, v.configured, "Hz");
}

function chart(canvas, values, target, unit) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight || +canvas.getAttribute("height");
  if (!w) return;
  if (canvas.width !== Math.round(w * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
  const g = canvas.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  const css = getComputedStyle(document.documentElement);
  const accent = css.getPropertyValue("--accent").trim(), muted = css.getPropertyValue("--muted").trim();
  const left = 4, right = w - 56, top = 12, bottom = h - 18;
  g.font = "11px Segoe UI"; g.fillStyle = muted; g.strokeStyle = "rgba(255,255,255,.14)"; g.lineWidth = 1;
  if (values.length < 2) {
    g.beginPath(); g.moveTo(left, bottom); g.lineTo(right, bottom); g.stroke();
    g.textAlign = "center"; g.font = "13px Segoe UI"; g.fillText("Waiting for measurements", (left + right) / 2, (top + bottom) / 2);
    return;
  }
  const max = Math.max(1, target || 0, ...values) * 1.12;
  const y = (v) => bottom - v / max * (bottom - top);
  g.textAlign = "left";
  for (const f of [0, .5, 1]) {
    const v = max * f;
    g.beginPath(); g.moveTo(left, y(v)); g.lineTo(right, y(v)); g.stroke();
    g.fillText(unit === "Hz" ? Math.round(v).toLocaleString() : v.toFixed(1), right + 8, y(v) + 4);
  }
  if (target) { g.setLineDash([3, 4]); g.strokeStyle = "rgba(255,255,255,.4)"; g.beginPath(); g.moveTo(left, y(target)); g.lineTo(right, y(target)); g.stroke(); g.setLineDash([]); }
  const grad = g.createLinearGradient(0, top, 0, bottom);
  grad.addColorStop(0, accent + "66"); grad.addColorStop(1, accent + "00");
  g.beginPath();
  values.forEach((v, i) => { const x = left + i / (values.length - 1) * (right - left); i ? g.lineTo(x, y(v)) : g.moveTo(x, y(v)); });
  g.strokeStyle = accent; g.lineWidth = 2; g.stroke();
  g.lineTo(right, bottom); g.lineTo(left, bottom); g.closePath(); g.fillStyle = grad; g.fill();
  g.fillStyle = muted; g.textAlign = "right"; g.fillText(`Recent samples · ${unit}`, right, h - 3);
}

// settings page

function renderSettings() {
  $("#set-startup").checked = S.settings.startup;
  $("#set-tray").checked = S.settings.close_to_tray;
  $("#set-tray").disabled = !S.has_tray;
  $$("#theme-seg button").forEach((b) => b.classList.toggle("on", b.dataset.theme === S.settings.theme));
  $("#set-angle").checked = S.angle_snap;
  $("#set-updates").checked = S.settings.check_updates;
  const up = S.update || {};
  $("#update-text").textContent = {
    checking: "Checking GitHub…",
    latest: "You have the newest version.",
    available: `Dorsal ${up.version} is out.`,
    error: "Couldn't reach GitHub. Try again later.",
  }[up.state] || "Not checked yet.";
  $("#update-text").className = up.state === "available" ? "c-ok" : "";
  $("#update-btn").textContent = up.state === "available" ? `Get ${up.version}` : "Check for updates";
  $("#update-btn").className = up.state === "available" ? "btn primary" : "btn";
  $("#update-btn").disabled = up.state === "checking";
  setHtml($("#sleep-seg"), S.sleep_choices.map((m) =>
    `<button data-min="${m}" class="${m === S.sleep_min ? "on" : ""}">${m ? `${m} min` : "Never"}</button>`).join(""));
  setHtml($("#settings-device"), dl([
    ["Connection", S.link_type || "Not connected"],
    ["Firmware", S.firmware || "—"],
  ]));
  $("#mouse-import").hidden = !!(A && A.mouse);
  if (S.log_len !== ui.logLen) {
    ui.logLen = S.log_len;
    call("log").then((lines) => {
      if (!lines) return;
      const log = $("#log");
      log.textContent = lines.join("\n");
      log.scrollTop = log.scrollHeight;
    });
  }
}

// firmware installer

const FW_TITLES = ["Find the official software", "Build and verify the firmware", "Connect the USB cable", "Install"];
function renderFirmware() {
  const f = S.firmware_installer, m = $("#modal");
  if (!f.open) { if (m.dataset.kind === "fw") { m.hidden = $("#scrim").hidden = true; m.dataset.kind = ""; m.innerHTML = ""; } return; }
  if (m.dataset.kind !== "fw") {
    m.dataset.kind = "fw";
    m.innerHTML = `<h2>Install Dorsal firmware</h2>
      <p>Always-on RGB for your R5 Ultra, controlled by Dorsal. Dorsal builds it from your copy of the official software, then installs it over the USB cable.</p>
      <div class="steps4" id="fw-steps"></div>
      <div class="progress" id="fw-progress" hidden><i></i></div>
      <p class="note">Keep the USB cable connected until installation finishes. Dorsal verifies the written image before restarting the mouse.</p>
      <div class="buttons"><button class="btn" id="fw-restore">Restore original firmware</button><span class="grow"></span>
        <button class="btn" id="fw-close">Close</button><button class="btn primary" id="fw-install">Install firmware</button></div>`;
    m.hidden = $("#scrim").hidden = false;
    $("#fw-close").onclick = async () => { const ok = await call("firmware_close"); if (ok === false) toast("Wait until the install finishes: unplugging now leaves the mouse in install mode.", "warn"); };
    $("#fw-install").onclick = async () => {
      if (await confirmBox("Install Dorsal firmware", "Install now? The mouse restarts when it's done.\n\nKeep the cable plugged in until you see “Done”.", "Install"))
        call("firmware_install", false);
    };
    $("#fw-restore").onclick = async () => {
      if (await confirmBox("Restore original firmware", "Put Attack Shark's original firmware back? The LED will go back to only flashing when you change DPI.", "Restore"))
        call("firmware_install", true);
    };
  }
  if (!$("#fw-steps")) { m.dataset.kind = ""; return; }     // rebuilt on the next update
  setHtml($("#fw-steps"), f.steps.map((s, i) => `<div class="step4 ${s.state}"><span class="badge">${s.state === "ok" ? "✓" : i + 1}</span>
      <div><b>${FW_TITLES[i]}</b><p>${esc(s.text)}</p>${i === 0 && f.needs_file ? '<button class="btn" id="fw-choose" style="margin-top:.6rem">Choose file…</button>' : ""}</div></div>`).join(""));
  const choose = $("#fw-choose");
  if (choose) choose.onclick = () => call("firmware_choose");
  $("#fw-progress").hidden = f.progress === null;
  if (f.progress !== null) $("#fw-progress i").style.width = `${Math.round(f.progress * 100)}%`;
  $("#fw-install").disabled = !f.can_install;
  $("#fw-restore").disabled = !f.can_restore;
  $("#fw-close").disabled = f.busy;
}

// notices from Python

async function showNotices() {
  for (const n of S.notices) {
    if (ui.noticeSeen.has(n.id)) continue;
    ui.noticeSeen.add(n.id);
    await dialog({ title: n.title, text: n.text });
    call("take_notice", n.id);
  }
  const slot = S.slot_read;
  if (slot && slot.id !== ui.slotSeen) {
    ui.slotSeen = slot.id;
    loadMacro({ name: slot.name, steps: slot.steps });
  }
}

// tabs

function showTab(name) {
  if (tab === name) return;
  if (tab === "diagnostics" && name !== "diagnostics") call("input_stop");
  tab = name;
  $$(".tab").forEach((t) => t.classList.toggle("on", t.dataset.tab === name));
  moveTabIndicator();
  $$(".page").forEach((p) => p.classList.toggle("on", p.id === `page-${name}`));
  const page = $(`#page-${name}`); page.scrollTop = 0;
  render();
  if (name === "buttons" && S && S.connected && ui.readFor !== S.profile && !S.bindings.some((b) => b.label) && !S.busy.includes("studio")) {
    ui.readFor = S.profile;
    call("read_bindings");       // show what's on the mouse without a click
  }
  if (name === "diagnostics") pollDiagnostics();
  if (name === "macros" && !ui.macroShown) { ui.macroShown = true; renderMacro(); }
}

function render() {
  if (!S) return;
  renderHeader();
  renderDock();
  if (tab === "home") renderHome();
  if (tab === "buttons") renderButtons();
  if (tab === "macros") renderMacroLibrary();
  if (tab === "profiles") renderProfiles();
  if (tab === "diagnostics") renderDiagnostics();
  if (tab === "settings") renderSettings();
  renderFirmware();
  showNotices();
}

// wiring

function wire() {
  $("#macro-search").oninput = renderMacroLibrary;
  const indicator = document.createElement("i");
  indicator.className = "tab-indicator";
  indicator.setAttribute("aria-hidden", "true");
  $("#tabs").appendChild(indicator);
  new ResizeObserver(moveTabIndicator).observe($("#tabs"));
  document.fonts.ready.then(moveTabIndicator);
  $$(".tab").forEach((t) => t.onclick = () => showTab(t.dataset.tab));

  // profile menu
  const menu = $("#profile-menu");
  $("#profile-btn").onclick = (e) => {
    e.stopPropagation();
    menu.innerHTML = [1, 2, 3].map((n) => `<button class="${n === S.profile ? "on" : ""}" data-n="${n}">${n === S.profile ? '<svg class="ic sm"><use href="#i-check"/></svg>' : '<span style="width:1rem"></span>'}Profile ${n}</button>`).join("");
    menu.hidden = !menu.hidden;
    $$("button", menu).forEach((b) => b.onclick = () => { menu.hidden = true; call("set_profile", +b.dataset.n); });
  };
  document.addEventListener("click", () => { menu.hidden = true; });

  // lighting
  $("#presets").innerHTML = PRESET_COLORS.map((c) => `<button data-c="${c}" style="--c:${c}" title="${c}"></button>`).join("");
  $$("#presets button").forEach((b) => b.onclick = () => call("set_color", b.dataset.c));
  const bright = $("#brightness");
  trackDrag(bright);
  bright.oninput = () => { rangeFill(bright); $("#bright-text").textContent = `${Math.round(bright.value / 255 * 100)}%`; throttle("bright", 60, () => call("set_brightness", +bright.value)); };
  const speed = $("#rainbow-speed");
  trackDrag(speed);
  speed.oninput = () => {
    rangeFill(speed);
    const s = Math.round((30 - 29.5 * speed.value / 1000) * 10) / 10;
    $("#rainbow-text").textContent = `${s.toFixed(1)} s per cycle`;
    throttle("speed", 80, () => call("set_rainbow_speed", s));
  };

  // customize
  $$(".quick-toggle").forEach((b) => b.onclick = () => call("set_setting", b.dataset.setting, !S[b.dataset.setting]));
  $("#deb-minus").onclick = () => call("set_setting", "debounce", Math.max(0, S.debounce - 1));
  $("#deb-plus").onclick = () => call("set_setting", "debounce", Math.min(20, S.debounce + 1));

  // performance
  $("#competitive").onclick = () => call("competitive_mode", S.competitive == null ? null : !S.competitive);
  const dpi = $("#dpi");
  trackDrag(dpi);
  dpi.oninput = () => {
    rangeFill(dpi);
    const v = dpiFromFrac(dpi.value / 1000);
    const row = $(`#stages [data-i="${ui.stage}"]`);
    if (row) { $("b", row).textContent = v.toLocaleString(); $(".stage-bar i", row).style.width = `${(dpiFrac(v) * 100).toFixed(1)}%`; }
    $("#dpi-value").value = v.toLocaleString();
    throttle("dpi", 70, () => call("set_stage_dpi", ui.stage, v));
  };

  wireDpiField();

  // dock
  $("#apply").onclick = () => call("apply");
  $("#dock-read").onclick = () => call("read_settings");

  // buttons page
  $("#assign-save").onclick = saveAssignment;
  $("#assign-cancel").onclick = () => { ui.bindingFor = null; renderButtons(true); };
  $("#binding-read").onclick = () => call("read_bindings");

  // macros page
  $("#step-kind").innerHTML = A.kinds.map((k) => `<option>${esc(k)}</option>`).join("");
  $("#step-kind").onchange = () => { $("#step-value").value = { Delay: "100", "Mouse down": "Left", "Mouse up": "Left", Wheel: "Up" }[$("#step-kind").value] || "A"; };
  $("#macro-name").oninput = () => call("set_unsaved", macroDirty());
  $("#macro-library").onchange = async (e) => {
    const id = e.target.value;
    if (!(await discardOk())) { e.target.value = ui.macro.id || ""; return; }
    if (!id) loadMacro({ name: "Untitled macro", steps: [] });
    else { const m = S.macros.find((x) => x.id === id); if (m) loadMacro(m, m.id); }
  };
  $("#macro-new").onclick = async () => { if (await discardOk()) { loadMacro({ name: "Untitled macro", steps: [] }); $("#macro-library").dataset.key = ""; renderMacroLibrary(); $("#macro-name").focus(); $("#macro-name").select(); } };
  $("#macro-import").onclick = async () => {
    if (!(await discardOk())) return;
    const doc = await call("import_macro");
    if (doc) loadMacro(doc, doc.id);
  };
  $("#macro-export").onclick = () => call("export_macro", $("#macro-name").value, ui.macro.steps);
  $("#macro-delete").onclick = async () => {
    if (!ui.macro.id) return;
    if (await confirmBox("Delete macro", "Remove this macro from your library on this PC? Onboard slots are unchanged.", "Delete")) {
      await call("delete_macro", ui.macro.id);
      loadMacro({ name: "Untitled macro", steps: [] });
    }
  };
  $("#step-add").onclick = async () => {
    const m = ui.macro;
    if (m.steps.length >= 256) { toast("This macro has reached the 256-step limit.", "warn"); return; }
    const r = await editorStep();
    if (!r.ok) return;
    const at = m.sel === null ? m.steps.length : m.sel + 1;
    m.steps.splice(at, 0, r.value); m.sel = at; renderMacro();
  };
  $("#step-update").onclick = async () => {
    const m = ui.macro;
    if (m.sel === null) return;
    const r = await editorStep();
    if (r.ok) { m.steps[m.sel] = r.value; renderMacro(); }
  };
  $("#step-remove").onclick = () => {
    const m = ui.macro;
    if (m.sel === null) return;
    m.steps.splice(m.sel, 1);
    m.sel = m.steps.length ? Math.min(m.sel, m.steps.length - 1) : null;
    renderMacro();
  };
  const move = (d) => {
    const m = ui.macro, t = m.sel + d;
    if (m.sel === null || t < 0 || t >= m.steps.length) return;
    [m.steps[m.sel], m.steps[t]] = [m.steps[t], m.steps[m.sel]]; m.sel = t; renderMacro();
  };
  $("#step-up").onclick = () => move(-1);
  $("#step-down").onclick = () => move(1);
  $("#macro-record").onclick = async () => {
    const events = await recordMacro();
    if (!events || !events.length) return;
    const steps = await call("record_steps", events);
    if (!steps) return;
    if (ui.macro.steps.length + steps.length > 256) { toast("The recording would exceed 256 steps. Nothing was added.", "warn"); return; }
    ui.macro.steps.push(...steps); renderMacro();
  };
  $("#macro-shortcut").onclick = async () => {
    const text = await promptBox("Add shortcut", "Shortcut, for example Ctrl+C or Ctrl+Shift+S:", "Ctrl+C");
    if (!text) return;
    const steps = await call("shortcut_steps", text);
    if (!steps) return;
    if (ui.macro.steps.length + steps.length > 256) { toast("This would exceed the 256-step limit.", "warn"); return; }
    ui.macro.steps.push(...steps); ui.macro.sel = ui.macro.steps.length - 1; renderMacro();
  };
  $("#macro-save").onclick = async () => {
    const id = await call("save_macro", $("#macro-name").value, ui.macro.steps, ui.macro.id);
    if (id) { ui.macro.id = id; ui.macro.saved = macroDoc(); renderMacro(); }
  };
  $("#macro-upload").onclick = async () => {
    const slot = +$("#macro-slot").value;
    const check = await call("macro_check", ui.macro.steps);
    if (!check || !check.ok) { toast(check ? check.text || "Add some steps first." : "Add some steps first.", "warn"); return; }
    if (await confirmBox("Upload to mouse", `Replace macro slot ${slot} with this sequence?\nAny buttons using this slot will run the new macro.`, "Upload"))
      call("upload_macro", slot, ui.macro.steps);
  };
  $("#macro-read").onclick = async () => { if (await discardOk()) call("read_macro_slot", +$("#macro-slot").value); };
  document.addEventListener("keydown", (e) => {
    if (tab === "macros" && e.key === "Delete" && document.activeElement === document.body) $("#step-remove").click();
  });

  // profiles page
  $("#profile-import").onclick = () => call("import_profile");

  // tabs inside panes
  wireViews($("#diag-tabs"), ".diag-view", "diag", (name) => {
    $("#diag-title").textContent = $(`#diag-tabs button[data-view="${name}"]`).textContent;
    $("#link-chart").dataset.key = ""; render();
  });
  wireViews($("#settings-nav"), ".settings-body .sec", "settings");
  slideHighlight($("#settings-nav"), "button");
  slideHighlight($("#diag-tabs"), "button");
  slideHighlight($("#assign-cats"), ".cat");

  // diagnostics page
  $("#probe-name").innerHTML = A.probes.map((p) => `<option>${esc(p)}</option>`).join("");
  $("#health-run").onclick = () => call("health");
  $("#report-copy").onclick = () => call("copy_report");
  $("#session-export").onclick = () => call("export_session");
  $("#traffic-pause").onclick = (e) => { ui.trafficPaused = !ui.trafficPaused; e.currentTarget.textContent = ui.trafficPaused ? "Resume" : "Pause"; };
  $("#traffic-clear").onclick = () => { ui.trafficLines = []; $("#traffic").innerHTML = ""; };
  $("#traffic-copy").onclick = () => { call("copy_text", $("#traffic").textContent); toast("HID traffic copied"); };
  $("#probe-run").onclick = () => call("probe", $("#probe-name").value);
  $("#link-run").onclick = () => call("link_test", +$("#link-count").value);
  $("#input-toggle").onclick = async () => { await call("input_toggle"); pollDiagnostics(); };
  $("#input-reset").onclick = async () => { await call("input_reset"); pollDiagnostics(); };
  setInterval(() => { if (tab === "diagnostics") pollDiagnostics(); }, 300);

  // settings page
  $("#set-startup").onchange = (e) => call("set_startup", e.target.checked);
  $("#set-tray").onchange = (e) => call("set_close_to_tray", e.target.checked);
  $$("#theme-seg button").forEach((b) => b.onclick = async () => {
    const theme = b.dataset.theme;
    if (theme === S.settings.theme) return;
    document.documentElement.className = `theme-${theme}`;
    const bd = await call("set_theme", theme);
    if (bd) setBackdrop(bd);
  });
  $("#fw-open").onclick = () => call("firmware_open");
  $("#fw-doc").onclick = () => call("open_doc", "FIRMWARE.md");
  $("#dev-refresh").onclick = () => call("read_settings");
  $("#set-updates").onchange = (e) => call("set_check_updates", e.target.checked);
  $("#update-btn").onclick = () => call((S.update || {}).state === "available" ? "open_update" : "check_updates");
  $("#set-angle").onchange = (e) => call("set_setting", "angle_snap", e.target.checked);
  $("#sleep-seg").onclick = (e) => { const b = e.target.closest("button[data-min]"); if (b) call("set_setting", "sleep_min", +b.dataset.min); };
  $("#mouse-import").onclick = async () => { const m = await call("import_mouse_image"); if (m) { A.mouse = m; buildArt(); placeCallouts(); } };
  $("#profile-reset").onclick = async () => {
    if (await confirmBox("Reset profile", `Reset profile ${S.profile} on the mouse to factory settings?\nIts DPI stages and colors will be lost.`, "Reset")) call("reset_profile");
  };

  window.addEventListener("resize", () => placeCallouts());
}

// color picker, right in the lighting panel

const pick = { h: 0, s: 1, v: 1, hex: null };
function hexToRgb(hex) { const n = parseInt(hex.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function rgbToHex(r, g, b) { return "#" + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("").toUpperCase(); }
function rgbToHsv(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  let h = 0;
  if (d) h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return { h: (h * 60 + 360) % 360, s: max ? d / max : 0, v: max };
}
function hsvToRgb(h, s, v) {
  const f = (n) => { const k = (n + h / 60) % 6; return v - v * s * Math.max(0, Math.min(k, 4 - k, 1)); };
  return [f(5) * 255, f(3) * 255, f(1) * 255];
}
function drawSV() {
  const c = $("#sv"), g = c.getContext("2d"), dpr = window.devicePixelRatio || 1;
  const w = Math.round(c.clientWidth * dpr), h = Math.round(c.clientHeight * dpr);
  if (!w || !h) return;
  if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
  const [r, gg, b] = hsvToRgb(pick.h, 1, 1);
  g.fillStyle = `rgb(${r},${gg},${b})`; g.fillRect(0, 0, c.width, c.height);
  let grad = g.createLinearGradient(0, 0, c.width, 0); grad.addColorStop(0, "#fff"); grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad; g.fillRect(0, 0, c.width, c.height);
  grad = g.createLinearGradient(0, 0, 0, c.height); grad.addColorStop(0, "rgba(0,0,0,0)"); grad.addColorStop(1, "#000");
  g.fillStyle = grad; g.fillRect(0, 0, c.width, c.height);
  const x = pick.s * c.width, y = (1 - pick.v) * c.height;
  g.beginPath(); g.arc(x, y, 7 * dpr, 0, Math.PI * 2); g.lineWidth = 2.5 * dpr; g.strokeStyle = "#fff"; g.stroke();
  g.beginPath(); g.arc(x, y, 8.5 * dpr, 0, Math.PI * 2); g.lineWidth = dpr; g.strokeStyle = "rgba(0,0,0,.45)"; g.stroke();
  if (document.activeElement !== $("#hex-input")) $("#hex-input").value = rgbToHex(...hsvToRgb(pick.h, pick.s, pick.v));
  $("#hue").value = pick.h;
}
// follow the color Python has, unless it's being dragged right now
function syncPicker() {
  if (ui.dragging.has("sv") || ui.dragging.has("hue") || pick.hex === S.color) return;
  pick.hex = S.color;
  const hsv = rgbToHsv(...hexToRgb(S.color));
  if (hsv.s > 0 && hsv.v > 0) pick.h = hsv.h;          // greys keep the hue, so the square doesn't jump to red
  pick.s = hsv.s; pick.v = hsv.v;
  drawSV();
}
function pickColor() {
  const hex = rgbToHex(...hsvToRgb(pick.h, pick.s, pick.v));
  pick.hex = hex;
  drawSV();
  document.documentElement.style.setProperty("--led-hex", hex);
  throttle("color", 80, () => call("set_color", hex));
}
function wirePicker() {
  const sv = $("#sv");
  sv.onpointerdown = (e) => {
    ui.dragging.add("sv");
    const move = (ev) => {
      const r = sv.getBoundingClientRect();
      pick.s = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width));
      pick.v = 1 - Math.max(0, Math.min(1, (ev.clientY - r.top) / r.height));
      pickColor();
    };
    move(e); sv.setPointerCapture(e.pointerId); sv.onpointermove = move;
    sv.onpointerup = () => { sv.onpointermove = null; setTimeout(() => ui.dragging.delete("sv"), 250); };
  };
  const hue = $("#hue");
  trackDrag(hue);
  hue.oninput = () => { pick.h = +hue.value; pickColor(); };
  const field = $("#hex-input");
  field.onkeydown = (e) => { if (e.key === "Enter") field.blur(); };
  field.onchange = () => {
    const v = "#" + field.value.trim().replace(/^#/, "");
    if (/^#[0-9a-f]{6}$/i.test(v)) call("set_color", v.toUpperCase()); else field.value = S.color;
  };
  new ResizeObserver(drawSV).observe(sv);
}

let backdropRequest = 0;
function setBackdrop(name) {
  const request = ++backdropRequest;
  const bd = $("#backdrop");
  const img = new Image();
  img.onload = () => {
    if (request !== backdropRequest) return;
    bd.style.backgroundImage = `url("${name}")`; bd.classList.add("ready");
  };
  img.src = name;
}

// The background drifts a few pixels a second, but CSS redraws it (blur and
// all) at the monitor's full refresh rate: ~40% of a core at 60 Hz, worse at
// 144/240 Hz. Driving the same animations by hand at 24 fps looks identical
// and costs ~5%.
const AMBIENT_FPS = 24;
let ambientTimer = 0;
// Scene time only runs while someone can see it (window up and not covered by
// another window), so after a pause the drift picks up where it stopped.
const ambientClock = { shown: 0, since: null, covered: false };
function ambientVisible() { return !document.hidden && !ambientClock.covered; }
function ambientNow() { return ambientClock.shown + (ambientClock.since === null ? 0 : performance.now() - ambientClock.since); }
function ambientTick() {
  const on = ambientVisible();
  if (on && ambientClock.since === null) ambientClock.since = performance.now();
  if (!on && ambientClock.since !== null) { ambientClock.shown = ambientNow(); ambientClock.since = null; }
}
document.addEventListener("visibilitychange", ambientTick);
function throttleAmbient() {
  clearInterval(ambientTimer);
  const anims = document.getAnimations().filter((a) => a.effect?.target?.closest?.("#ambient, #backdrop"));
  if (!anims.length) return;
  anims.forEach((a) => a.pause());
  const base = anims.map((a) => a.currentTime || 0);
  ambientTick();
  ambientTimer = setInterval(() => {
    if (!ambientVisible()) return;      // nothing changes, so nothing gets drawn
    const dt = ambientNow();
    anims.forEach((a, i) => { a.currentTime = base[i] + dt; });
  }, 1000 / AMBIENT_FPS);
}

// A highlight that slides to the selected item in a sidebar, like the
// underline under the top tabs. Lists that get re-rendered get the same
// element back, placed where it was first so the move still animates.
function slideHighlight(container, itemSel) {
  const bar = document.createElement("i");
  bar.className = "side-slide";
  container.classList.add("has-slide");
  let last = null;
  const place = () => {
    if (!bar.isConnected) {
      container.appendChild(bar);
      if (last) { bar.style.transform = last; void bar.offsetHeight; }
    }
    const on = container.querySelector(`${itemSel}.on`);
    bar.style.opacity = on ? 1 : 0;
    if (!on || !on.offsetHeight) return;          // page not on screen yet
    const jump = !bar.offsetHeight;                // first time it's visible: appear in place
    if (jump) bar.style.transition = "none";
    bar.style.left = `${on.offsetLeft}px`;
    bar.style.width = `${on.offsetWidth}px`;
    bar.style.height = `${on.offsetHeight}px`;
    last = bar.style.transform = `translateY(${on.offsetTop}px)`;
    if (jump) { void bar.offsetHeight; bar.style.transition = ""; }
  };
  new MutationObserver(place).observe(container, { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] });
  new ResizeObserver(place).observe(container);
  place();
  requestAnimationFrame(() => container.classList.add("slide-ready"));   // no slide in from the top on first show
}

// start

function moveTabIndicator() {
  const selected = $(".tab.on"), indicator = $(".tab-indicator");
  if (!selected || !indicator) return;
  indicator.style.width = `${selected.offsetWidth}px`;
  indicator.style.height = `${selected.offsetHeight}px`;
  indicator.style.transform = `translate(${selected.offsetLeft}px, ${selected.offsetTop}px)`;
  $("#tabs").classList.add("has-indicator");
}

window.dorsal = {
  state(s) {
    const first = !S;
    S = s;
    if (first) document.documentElement.className = `theme-${s.settings.theme}`;
    render();
  },
  frame,
  covered(on) { ambientClock.covered = !!on; ambientTick(); },
  async confirmQuit() {
    if (await confirmBox("Unsaved macro", "Discard the unsaved macro edits and quit?", "Quit")) call("quit", true);
  },
};

async function start() {
  const hello = await call("hello");
  if (!hello) { setTimeout(start, 300); return; }
  A = hello;
  document.documentElement.className = `theme-${hello.state.settings.theme}`;
  setBackdrop(hello.backdrop);
  if (hello.ambient) {
    const root = document.documentElement.style;
    root.setProperty("--tex-caustics", `url("${hello.ambient.caustics}")`);
    root.setProperty("--tex-snow-far", `url("${hello.ambient["snow-far"]}")`);
    root.setProperty("--tex-snow-near", `url("${hello.ambient["snow-near"]}")`);
    document.body.classList.add("ambient-ready");
  }
  requestAnimationFrame(throttleAmbient);
  buildArt();
  wire();
  wirePicker();
  S = hello.state;
  render();
  $$("[data-art] img").forEach((img) => img.addEventListener("load", placeCallouts));
}
if (window.pywebview && window.pywebview.api) start();
else window.addEventListener("pywebviewready", start);
