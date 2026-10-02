const $ = (s) => document.querySelector(s);
const api = async (path, opts = {}) => {
  // Bei FormData (Datei-Upload) setzt der Browser Content-Type inkl. Boundary selbst — nicht überschreiben.
  const headers = opts.body instanceof FormData ? opts.headers : { "Content-Type": "application/json", ...opts.headers };
  const r = await fetch(path, { ...opts, headers });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail) || r.statusText);
  }
  return r.json();
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = (sec) => (isFinite(sec) ? `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}` : "");

// Stil-Karten, nach Art gruppiert; der Würfel mischt daraus einen Stil
const STYLE_GROUPS = {
  genre: ["trip hop", "downtempo", "dub", "deep house", "techno", "drum and bass", "post-rock", "neo-soul", "dark ambient", "boom bap", "orchestral",
    "pop", "rock", "hip hop", "electronic", "lo-fi", "jazz", "ambient", "synthwave", "acoustic", "cinematic"],
  vocals: ["female vocals", "male vocals"],
  instr: ["piano", "guitar", "808 bass"],
  mood: ["upbeat", "melancholic", "dreamy"],
};
const STYLE_TAGS = [...STYLE_GROUPS.genre, ...STYLE_GROUPS.vocals, ...STYLE_GROUPS.instr, ...STYLE_GROUPS.mood];
const SECTIONS = ["[intro]", "[verse]", "[pre-chorus]", "[chorus]", "[bridge]", "[outro]", "[instrumental]"];

let songs = [];
let currentId = null;
let onlyFav = false;       // Favoriten-Filter der Bibliothek
let editingId = null;   // id des Songs, dessen Titel gerade bearbeitet wird

// Erstellungszeit anzeigen, bis ein Song zum ersten Mal abgespielt wurde (danach dauerhaft ausgeblendet)
let played = new Set();
try { played = new Set(JSON.parse(localStorage.getItem("played") || "[]")); } catch {}
const markPlayed = (id) => { played.add(id); try { localStorage.setItem("played", JSON.stringify([...played])); } catch {} };
const genTime = (s) => { const t = (Date.parse(s.finished_at) - Date.parse(s.created_at)) / 1000; return isFinite(t) && t >= 0 ? fmt(t) : null; };

// Würfel: zufälliger Prompt (Stimmung, Szene, Detail); der Stil bleibt deine Wahl
const R = {
  mood: ["dark", "dreamy", "melancholic", "hypnotic", "warm", "tense", "nostalgic", "euphoric", "lonely", "mysterious", "hopeful", "gritty", "serene", "haunting"],
  scene: ["a late night drive through a neon city", "a rainy afternoon in an empty café", "walking through fog at dawn", "an abandoned space station",
    "a quiet forest after snowfall", "a crowded market at sunset", "floating above the clouds", "a smoky club after midnight", "a desert road at sunrise",
    "an old arcade at closing time", "a lighthouse during a storm", "the last train home", "a rooftop above a sleeping city", "an underwater research lab"],
  detail: ["slow and spacious", "building gradually", "with a steady pulse", "sparse and minimal", "with swelling strings", "slightly dusty and worn",
    "with a soft melodic hook", "with a hypnotic repeating motif", "with deep warm bass", "with distant echoing textures"],
};
const pick = (a) => a[Math.floor(Math.random() * a.length)];
const randomPrompt = () => `${pick(R.mood)}, ${pick(R.scene)}, ${pick(R.detail)}`;

// ---------------------------------------------------------------- Formular
const form = $("#genForm");
function addChips(el, items, onClick) {
  el.innerHTML = items.map((t) => `<span class="chip">${esc(t)}</span>`).join("");
  el.querySelectorAll(".chip").forEach((c, i) => c.addEventListener("click", () => onClick(items[i])));
}
addChips($("#tagChips"), STYLE_TAGS, (t) => {
  const f = form.style;
  f.value = f.value.trim() ? `${f.value.trim().replace(/,$/, "")}, ${t}` : t;
});
addChips($("#sectionChips"), SECTIONS, (t) => {
  if (t === "[instrumental]") { form.instrumental.checked = true; syncLyrics(); return; }   // zurück zu ohne Gesang
  const f = form.lyrics, pos = f.selectionStart ?? f.value.length;
  const before = f.value.slice(0, pos), ins = (before && !before.endsWith("\n") ? "\n\n" : "") + t + "\n";
  f.value = before + ins + f.value.slice(pos);
  f.focus(); f.selectionStart = f.selectionEnd = pos + ins.length;
});
// Bubble-Slider: Füllstand + Wert im Knopf (BPM ganz links = Auto)
const SLIDER_FMT = { dur: (v) => fmt(v), int: (v) => String(v), temp: (v) => v.toFixed(2), bpm: (v, min) => (v <= min ? ["AUTO", true] : String(v)) };
function updateSlider(box) {
  const inp = box.querySelector("input"), min = +inp.min, max = +inp.max, v = +inp.value;
  box.style.setProperty("--p", (v - min) / (max - min));
  const out = SLIDER_FMT[box.dataset.fmt](v, min), span = box.querySelector(".knob span");
  span.textContent = Array.isArray(out) ? out[0] : out;
  span.classList.toggle("small", Array.isArray(out));
  if (inp.name === "variants") $("#genBtn").textContent = v > 1 ? `${v}× GENERIEREN` : "GENERIEREN";
}
const showDur = () => document.querySelectorAll(".slider").forEach(updateSlider);
document.querySelectorAll(".slider").forEach((b) => { b.querySelector("input").addEventListener("input", () => updateSlider(b)); updateSlider(b); });
// Lyrics: eingeklappt; bei Instrumental steht "[Instrumental]" im Feld, Klick ins Feld schaltet Instrumental aus
let lyricsStash = "";
function syncLyrics() {
  const on = form.instrumental.checked, f = form.lyrics;
  if (on) { if (f.value !== "[Instrumental]") lyricsStash = f.value; f.value = "[Instrumental]"; }
  else if (f.value === "[Instrumental]") f.value = lyricsStash;
  f.classList.toggle("dim", on);
  $("#lyricsHint").textContent = on ? "[Instrumental]" : f.value.trim() ? "eigene Lyrics" : "Modell schreibt selbst";
}
const TITLE = {
  adj: ["Midnight", "Velvet", "Neon", "Silent", "Golden", "Hollow", "Electric", "Faded", "Distant", "Crimson", "Slow", "Lunar", "Paper", "Glass", "Amber"],
  noun: ["Static", "Horizon", "Rain", "Echoes", "Signal", "Drift", "Skyline", "Mirror", "Ember", "Tide", "Orbit", "Harbor", "Afterglow", "Motel", "Garden"],
};
// ein bis zwei Genres, ein Instrument, eine Stimmung; Gesang nur, wenn der Song nicht instrumental ist
const randomStyle = () => {
  const parts = [pick(STYLE_GROUPS.genre)];
  if (Math.random() < 0.6) {
    let second;
    do second = pick(STYLE_GROUPS.genre); while (second === parts[0]);
    parts.push(second);
  }
  parts.push(pick(STYLE_GROUPS.instr), pick(STYLE_GROUPS.mood));
  if (!form.instrumental.checked) parts.push(pick(STYLE_GROUPS.vocals));
  return parts.join(", ");
};
const randomTitle = () => `${pick(TITLE.adj)} ${pick(TITLE.noun)}`;
function rollAnim(btn) { btn.classList.remove("roll"); void btn.offsetWidth; btn.classList.add("roll"); }
function rollDice(btn, field, gen) { field.value = gen(); rollAnim(btn); }
$("#diceBtn").addEventListener("click", (e) => { rollDice(e.currentTarget, form.prompt, randomPrompt); updateLyricsDice(); });
$("#titleDice").addEventListener("click", (e) => rollDice(e.currentTarget, form.title, randomTitle));
$("#styleDice").addEventListener("click", (e) => rollDice(e.currentTarget, form.style, randomStyle));

// Lyrics-Würfel: lässt das Modell bei der Generierung eigene Lyrics schreiben (kein Text hier, nur "auto"),
// geht nur mit vorhandenem Prompt, weil das Modell sonst nichts hat, worüber es schreiben kann.
const lyricsDice = $("#lyricsDice");
const updateLyricsDice = () => { lyricsDice.disabled = !form.prompt.value.trim(); $("#diceNote").hidden = !lyricsDice.disabled; };
updateLyricsDice();
form.prompt.addEventListener("input", updateLyricsDice);
lyricsDice.addEventListener("click", (e) => {
  e.preventDefault(); e.stopPropagation();   // <summary> soll dabei nicht auf-/zuklappen
  if (lyricsDice.disabled) return;
  form.instrumental.checked = false; lyricsStash = ""; form.lyrics.value = "";
  syncLyrics(); $("#lyricsBox").open = true;
  rollAnim(e.currentTarget);
});
form.instrumental.addEventListener("change", () => { syncLyrics(); if (!form.instrumental.checked) $("#lyricsBox").open = true; });
form.lyrics.addEventListener("focus", () => { if (form.instrumental.checked) { form.instrumental.checked = false; syncLyrics(); } });
form.lyrics.addEventListener("input", syncLyrics);
syncLyrics();

function readForm() {
  const d = Object.fromEntries(new FormData(form));
  const num = (k, def) => (d[k] === "" || d[k] == null ? def : Number(d[k]));
  return {
    title: d.title || "", prompt: d.prompt || "", style: d.style || "", lyrics: form.instrumental.checked ? "" : d.lyrics || "", instrumental: form.instrumental.checked, keep_caption: form.keep_caption.checked,
    duration: Number(form.duration.value), bpm: Number(form.bpm.value) <= Number(form.bpm.min) ? 0 : Number(form.bpm.value), keyscale: d.keyscale || "", timesignature: d.timesignature || "",
    seed: num("seed", -1), variants: num("variants", 1),
    inference_steps: Number(form.inference_steps.value), lm_temperature: Number(form.lm_temperature.value),
  };
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!form.prompt.value.trim() && !form.style.value.trim()) { form.prompt.focus(); return; }
  try {
    await api("/api/generate", { method: "POST", body: JSON.stringify(readForm()) });
    refresh();
  } catch (err) { alert("Fehler: " + err.message); }
});

function fillForm(s) {
  const p = s.params;
  form.title.value = s.title || "";
  form.style.value = p.style ?? p.caption;   // ältere Songs haben nur einen Text
  form.prompt.value = p.prompt ?? ""; updateLyricsDice();
  form.instrumental.checked = p.lyrics === "[Instrumental]";
  form.keep_caption.checked = true;   // Prompt wörtlich ist fest die Vorgabe
  lyricsStash = ""; form.lyrics.value = form.instrumental.checked ? "" : p.lyrics || "";
  syncLyrics(); $("#lyricsBox").open = !form.instrumental.checked && !!(p.lyrics || "").trim();
  form.duration.value = p.duration || 90;
  form.bpm.value = p.bpm || form.bpm.min;
  form.inference_steps.value = p.inference_steps || 50;
  form.lm_temperature.value = p.lm_temperature ?? 0.85;   // ältere Songs liefen mit der Modell-Vorgabe
  showDur();
  for (const k of ["keyscale", "timesignature"])
    form[k].value = p[k] || "";
  form.seed.value = p.seed;
  form.variants.value = 1; showDur();
  form.querySelector("details").open = true;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ---------------------------------------------------------------- Song-Upload (Analyse)
// Geheime Dropzone: das Logo. Unauffällig, bis man draufzeigt, zieht oder es gerade etwas tut.
const dz = $("#dropzone"), bubble = $("#dzBubble"), fileInput = $("#fileInput");
let dzHideTimer = null;
function dzState(cls, text) {
  clearTimeout(dzHideTimer);
  dz.className = "logo-wrap" + (cls ? ` ${cls}` : "");
  bubble.textContent = text || "";
  bubble.classList.toggle("show", !!text);
  if (cls === "ok") dzHideTimer = setTimeout(() => { dz.className = "logo-wrap"; bubble.classList.remove("show"); }, 4000);
}
async function analyzeFile(file) {
  if (!file) return;
  dzState("busy", `Analysiere „${file.name}“ …`);
  const body = new FormData(); body.append("audio", file);
  try {
    const r = await api("/api/analyze", { method: "POST", body });
    form.prompt.value = r.caption || "";
    form.style.value = "";
    form.title.value = randomTitle();
    updateLyricsDice();
    // Nur echter Text außerhalb von [Strukturmarkern] zählt als Gesang — sonst schreibt das
    // Modell manchmal Dinge wie "[Acoustic guitar intro]" gefolgt von "[Instrumental]".
    const hasVocals = (r.lyrics || "").replace(/\[[^\]]*\]/g, "").trim().length > 0;
    if (hasVocals) {
      // Song hat Gesang: nicht den transkribierten Text übernehmen, sondern wie beim Lyrics-Würfel
      // das Modell bei der Generierung selbst welche schreiben lassen (Prompt ist ja gerade gesetzt).
      form.instrumental.checked = false; lyricsStash = ""; form.lyrics.value = "";
      $("#lyricsBox").open = true;
    } else { form.instrumental.checked = true; }
    syncLyrics();
    if (r.bpm) { form.bpm.value = r.bpm; }
    if (r.duration) form.duration.value = Math.min(+form.duration.max, Math.max(+form.duration.min, Math.round(r.duration / 5) * 5));
    showDur();
    form.keyscale.value = r.keyscale || "";
    form.timesignature.value = r.timesignature || "";
    dzState("ok", `„${file.name}“ analysiert — Stil übernommen.`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (err) {
    dzState("err", `Fehler: ${err.message}`);
  }
}
dz.addEventListener("click", () => fileInput.click());
dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
fileInput.addEventListener("change", () => analyzeFile(fileInput.files[0]));
["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
["dragleave", "dragend"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("drag"); analyzeFile(e.dataTransfer.files[0]); });

// ---------------------------------------------------------------- Bibliothek
async function refresh() {
  const q = new URLSearchParams({ q: $("#search").value, favorites: onlyFav });
  songs = await api("/api/songs?" + q);
  if (!editingId) render();   // während des Umbenennens nicht neu zeichnen, sonst verliert das Feld den Fokus
  const qu = await api("/api/queue");
  const busy = qu.running.length || qu.queued;
  clearTimeout(refresh.t);
  refresh.t = setTimeout(refresh, busy ? 1500 : 8000);
}

function render() {
  const lib = $("#library");
  if (!songs.length) { lib.innerHTML = `<div class="empty">Noch leer</div>`; return; }
  // Varianten desselben Prompts in Entstehungsreihenfolge mit A, B, C … kennzeichnen
  const groups = {};
  songs.forEach((s) => (groups[s.group_id] ??= []).push(s));
  const letter = {};
  Object.values(groups).forEach((arr) => {
    if (arr.length < 2) return;
    [...arr].reverse().forEach((s, i) => (letter[s.id] = String.fromCharCode(65 + i)));
  });

  lib.innerHTML = songs.map((s, i) => {
    const m = s.result_meta || {}, p = s.params || {};
    const newGroup = i > 0 && songs[i - 1].group_id !== s.group_id;
    const title = (s.title || s.caption.split(",").slice(0, 3).join(",")) + (letter[s.id] ? ` ${letter[s.id]}` : "");
    const meta = [
      m.bpm && `${m.bpm}BPM`,
      p.inference_steps ? `${p.inference_steps}IT` : null,
      p.lm_temperature != null ? `${(+p.lm_temperature).toFixed(1)}VAR` : null,
      m.keyscale, m.duration && fmt(m.duration),
    ].filter(Boolean).join(" · ");
    const playing = s.id === currentId && ws?.isPlaying();
    let left, state = "";
    if (s.status === "done") left = `<button class="aktion round" data-a="play" aria-label="Abspielen">${playing ? "❚❚" : "▶"}</button>`;
    else if (s.status === "error") left = `<div class="slot err" title="${esc(s.message)}">!</div>`;
    else if (s.status === "running") left = `<div class="slot run">♪</div>`;
    else left = `<div class="slot">${s.status === "cancelled" ? "✕" : "…"}</div>`;
    if (s.status === "running") state = `<div class="s run">${esc(s.message || "0:00")}</div><div class="mini-bar"></div>`;
    if (s.status === "queued") state = `<div class="s">Wartet</div>`;
    if (s.status === "cancelled") state = `<div class="s">Abgebrochen</div>`;
    if (s.status === "error") state = `<div class="s err" title="${esc(s.message)}">Fehler · ${esc(shortErr(s.message))}</div>`;
    if (s.status === "done" && !played.has(s.id)) { const t = genTime(s); if (t) state = `<div class="s took">Erstellt in ${t}</div>`; }
    const actions = [
      s.status === "done" && `<button class="sek icon ${s.favorite ? "on" : ""}" data-a="fav" title="Favorit">${s.favorite ? "★" : "☆"}</button>`,
      s.status === "done" && `<a class="download icon fmt" href="${s.url}?download=1" title="Download">${s.file.endsWith(".wav") ? "WAV" : "MP3"}</a>`,
      `<button class="sek icon" data-a="more" title="Weitere Variante (neuer Seed)">＋</button>`,
      `<button class="sek icon" data-a="reuse" title="Einstellungen ins Formular übernehmen"><svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true"><path d="M12 3l7 7h-4v10h-6V10H5l7-7z"/></svg></button>`,
      ["error", "cancelled"].includes(s.status) && `<button class="sek icon" data-a="retry" title="Erneut versuchen">↻</button>`,
      s.status !== "running" && `<button class="sek icon del" data-a="del" title="${s.status === "queued" ? "Abbrechen" : "Löschen"}">✕</button>`,
    ].filter(Boolean).join("");
    return `<div class="song ${s.id === currentId ? "playing" : ""}${newGroup ? " new-group" : ""}" data-id="${s.id}">
      ${left}
      <div style="min-width:0">${s.id === editingId
        ? `<input class="t-edit" data-id="${s.id}" value="${esc(s.title || "")}" placeholder="${esc(s.caption.split(",").slice(0, 3).join(","))}">`
        : `<div class="t" data-a="rename" title="Klicken zum Umbenennen">${esc(title)}</div>`
      }<div class="m" title="IT = Iterationen · VAR = Varianz">${esc(meta)}</div>${state}</div>
      <div class="actions">${actions}</div></div>`;
  }).join("");
  // Symbolknöpfe: Tooltip auch als Name für Screenreader
  lib.querySelectorAll("button[title]:not([aria-label]), a[title]:not([aria-label])")
    .forEach((el) => el.setAttribute("aria-label", el.title));
}
function shortErr(msg = "") {
  if (/nicht erreichbar/i.test(msg)) return "Server offline";
  if (/Codes/i.test(msg)) return "Keine Codes";
  if (/Zeitüberschreitung/i.test(msg)) return "Timeout";
  return "Details im Tooltip";
}

$("#library").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-a]");
  if (!btn) return;
  const id = btn.closest(".song").dataset.id, s = songs.find((x) => x.id === id);
  const a = btn.dataset.a;
  if (a === "play") return play(s);
  if (a === "rename") { editingId = id; render(); const inp = $(`.t-edit[data-id="${id}"]`); inp?.focus(); inp?.select(); return; }
  if (a === "fav") await api(`/api/songs/${id}`, { method: "PATCH", body: JSON.stringify({ favorite: !s.favorite }) });
  if (a === "reuse") return fillForm(s);
  if (a === "retry") await api(`/api/songs/${id}/retry`, { method: "POST" });
  if (a === "more") {
    const p = s.params;
    await api("/api/generate", { method: "POST", body: JSON.stringify({ ...p, instrumental: false, keep_caption: p.use_cot_caption !== true, title: s.title || "", seed: -1, variants: 1, group_id: s.group_id }) });
  }
  if (a === "del") {
    if (s.status !== "queued" && !confirm("Song löschen?")) return;
    await api(`/api/songs/${id}`, { method: "DELETE" }).catch((err) => alert(err.message));
  }
  refresh();
});
async function commitRename(inp) {
  const id = inp.dataset.id;
  if (editingId !== id) return;   // per Escape schon abgebrochen
  editingId = null;
  const s = songs.find((x) => x.id === id), title = inp.value.trim();
  if (s && title !== (s.title || "")) await api(`/api/songs/${id}`, { method: "PATCH", body: JSON.stringify({ title }) });
  refresh();
}
$("#library").addEventListener("focusout", (e) => { const inp = e.target.closest(".t-edit"); if (inp) commitRename(inp); });
$("#library").addEventListener("keydown", (e) => {
  const inp = e.target.closest(".t-edit");
  if (!inp) return;
  if (e.key === "Enter") { e.preventDefault(); inp.blur(); }
  if (e.key === "Escape") { e.preventDefault(); editingId = null; render(); }
});
$("#search").addEventListener("input", () => { clearTimeout(refresh.s); refresh.s = setTimeout(refresh, 250); });
$("#onlyFav").addEventListener("click", (e) => {
  onlyFav = !onlyFav;
  e.currentTarget.setAttribute("aria-pressed", onlyFav);
  e.currentTarget.textContent = onlyFav ? "★" : "☆";
  refresh();
});

// ---------------------------------------------------------------- Player
let ws = null;
function initPlayer() {
  const css = getComputedStyle(document.documentElement);
  ws = WaveSurfer.create({
    container: "#waveform", height: 44, barWidth: 2, barGap: 1, barRadius: 2,
    waveColor: css.getPropertyValue("--border").trim() || "#2a2e38",
    progressColor: css.getPropertyValue("--accent2").trim() || "#d1a75c", cursorWidth: 0,
  });
  const upd = () => { $("#pTime").textContent = `${fmt(ws.getCurrentTime())} / ${fmt(ws.getDuration())}`; };
  ws.on("timeupdate", upd); ws.on("ready", upd);
  ws.on("play", () => { $("#playBtn").textContent = "❚❚"; render(); });
  ws.on("pause", () => { $("#playBtn").textContent = "▶"; render(); });
  ws.on("finish", () => { $("#playBtn").textContent = "▶"; render(); });
  $("#playBtn").onclick = () => ws.playPause();
  document.addEventListener("keydown", (e) => {
    if (e.code === "Space" && !["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(e.target.tagName) && currentId) { e.preventDefault(); ws.playPause(); }
  });
}
async function play(s) {
  if (!ws) initPlayer();
  if (currentId === s.id) return ws.playPause();
  if (!played.has(s.id)) { markPlayed(s.id); render(); }
  currentId = s.id;
  $("#player").hidden = false;
  if (!play.ro) {   // Höhe des Players ändert sich, sobald die Wellenform geladen ist
    play.ro = new ResizeObserver(() => document.documentElement.style.setProperty("--player-h", $("#player").offsetHeight + "px"));
    play.ro.observe($("#player"));
  }
  $("#pTitle").textContent = s.title || s.caption;
  $("#pTitle").title = `Seed ${s.seed}` + (s.result_meta?.keyscale ? ` · ${s.result_meta.keyscale}` : "");
  await ws.load(s.url);
  ws.play();
  render();
}

// ---------------------------------------------------------------- Einstellungen & Status
async function checkHealth() {
  const el = $("#status");
  try {
    const h = await api("/api/health");
    el.className = "box small " + (h.ok ? "" : "err");
    el.textContent = h.engine === "mock" ? "Mock" : h.ok ? "" : "Offline";   // bei "alles ok" nichts anzeigen
    el.title = h.error || (h.props ? `Modelle: ${Object.values(h.props.models || {}).flat().join(", ")}` : "Modellserver");
    return h;
  } catch { el.className = "box small err"; el.textContent = "Backend offline"; }
}
const dlg = $("#settingsDlg"), sf = $("#settingsForm");
$("#btnSettings").onclick = async () => {
  const s = await api("/api/settings");
  for (const k of ["engine", "server_url", "lm_url", "timeout_minutes"]) sf[k].value = s[k];
  $("#healthOut").textContent = "";
  $("#healthOut").className = "box small";
  dlg.showModal();
};
const saveSettings = () => api("/api/settings", { method: "PUT", body: JSON.stringify({
  engine: sf.engine.value, server_url: sf.server_url.value.trim(), lm_url: sf.lm_url.value.trim(), timeout_minutes: Number(sf.timeout_minutes.value) || 30 }) });
$("#testBtn").onclick = async () => {
  const out = $("#healthOut");
  out.className = "box small"; out.textContent = "Teste";
  await saveSettings();
  const h = await checkHealth();
  out.className = "box small " + (h?.ok ? "done" : "err");
  out.textContent = h?.ok ? "Verbunden" : "Offline";
  out.title = h?.error || "";
};
dlg.addEventListener("close", async () => { if (dlg.returnValue === "save") { await saveSettings(); checkHealth(); } });

checkHealth();
setInterval(checkHealth, 15000);
refresh();
