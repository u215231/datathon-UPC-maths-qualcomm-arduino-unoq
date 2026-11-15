/* Reason: show Uino a problem (a picture, typed text, or a practice problem) and watch it
   answer inside the 60-second limit. The server runs copilot.pipeline.solve, the same function
   predict.py calls for the graded run, and returns how the answer was found. */
import { api, esc, renderRichText } from "/pages/rich.js";

const T = {
  eng: {
    title: "Show Uino a problem",
    drop_title: "Drop a picture of the problem here", drop_ok: "",
    drop_no: "Uino can't read pictures yet. Type the problem below.",
    reading: "Reading the picture…", read_ok: "Check the text, then press Solve.",
    read_fail: "Uino couldn't read this picture. Type the problem below.",
    text_label: "The problem", text_ph: "Type or paste the problem here",
    pick_label: "Or pick a practice problem", pick_none: "Choose a problem…", random: "Surprise me",
    solve: "Solve it!", clear: "Start again", seconds_left: "seconds left",
    say_idle: "Give me a problem and I'll show you how I think.", say_wait: "One moment, I'm finishing another thought…",
    say_think: "I'm thinking…",
    live: "Uino is writing a program…",
    say_done_code: "Done! My program's result matches one of the options.", say_done_letter: "Done! This time I went with my best guess.",
    say_error: "Something went wrong. Is the model running?",
    answer_is: "Uino's answer", in_time: "{s} s", too_slow: "{s} s: too slow",
    key_ok: "✓ Correct", key_bad: "✗ Wrong: the answer is {k}", say_right: "I got it right!", say_wrong: "Oh no, I got this one wrong.",
    how_title: "How Uino found it",
    how_code: "It wrote a program and got {v}. That is option {a}.",
    how_letter: "It chose the letter it finds most likely.",
    how_letter_code: "Its program didn't help ({r}), so it chose the letter it finds most likely.",
    how_fallback: "It ran out of time or the model didn't answer ({r}), so it gave its fallback letter.",
    program: "The program Uino wrote", level: "Level",
    reasons: { "no option matches": "its result matched no option", "timeout": "the program took too long", "crash": "the program crashed",
      "no output": "the program printed nothing", "not a number": "the result wasn't a number", "no time left": "no time was left",
      "syntax or unsafe": "the program had a mistake or wasn't safe to run", "empty": "there was no program", "no text options": "the options are pictures" },
  },
  cat: {
    title: "Ensenya un problema a Uino",
    drop_title: "Deixa aquí una foto del problema", drop_ok: "",
    drop_no: "Uino encara no sap llegir fotos. Escriu el problema a sota.",
    reading: "Llegint la foto…", read_ok: "Comprova el text i prem Resol.",
    read_fail: "Uino no ha pogut llegir aquesta foto. Escriu el problema a sota.",
    text_label: "El problema", text_ph: "Escriu o enganxa aquí el problema",
    pick_label: "O tria un problema de pràctica", pick_none: "Tria un problema…", random: "Sorprèn-me",
    solve: "Resol-lo!", clear: "Torna a començar", seconds_left: "segons queden",
    say_idle: "Dona'm un problema i t'ensenyaré com penso.", say_wait: "Un moment, estic acabant un altre pensament…",
    say_think: "Estic pensant…",
    live: "Uino està escrivint un programa…",
    say_done_code: "Fet! El resultat del meu programa coincideix amb una de les opcions.", say_done_letter: "Fet! Aquesta vegada he triat la meva millor aposta.",
    say_error: "Alguna cosa ha fallat. El model està en marxa?",
    answer_is: "La resposta d'Uino", in_time: "{s} s", too_slow: "{s} s: massa lent",
    key_ok: "✓ Correcte", key_bad: "✗ Incorrecte: la resposta és {k}", say_right: "L'he encertat!", say_wrong: "Oh no, aquesta l'he fallat.",
    how_title: "Com l'ha trobat Uino",
    how_code: "Ha escrit un programa i ha obtingut {v}. És l'opció {a}.",
    how_letter: "Ha triat la lletra que troba més probable.",
    how_letter_code: "El seu programa no ha ajudat ({r}), així que ha triat la lletra que troba més probable.",
    how_fallback: "S'ha quedat sense temps o el model no ha respost ({r}), així que ha donat la lletra de reserva.",
    program: "El programa que ha escrit Uino", level: "Nivell",
    reasons: { "no option matches": "el resultat no coincidia amb cap opció", "timeout": "el programa trigava massa", "crash": "el programa ha fallat",
      "no output": "el programa no ha escrit res", "not a number": "el resultat no era un nombre", "no time left": "no quedava temps",
      "syntax or unsafe": "el programa tenia un error o no era segur", "empty": "no hi havia programa", "no text options": "les opcions són imatges" },
  },
};

const LETTERS = ["A", "B", "C", "D", "E"];

export function mount(root) {
  const $ = (id) => root.querySelector(`#${id}`);
  const App = window.App, Owl = window.Owl;
  const owl = Owl.mount($("reason-owl"));
  const t = (key, values = {}) => String(T[App.lang][key]).replace(/\{(\w)\}/g, (_, k) => values[k] ?? "");
  let alive = true, info = { ocr: false, time_limit: 60 }, list = [], chosen = "", timer = 0, busy = false;
  let sayKey = "say_idle", last = null, ocrNote = "";

  $("opts").innerHTML = LETTERS.map((l) => `<label><b>${l}</b><input type="text" data-l="${l}" autocomplete="off" aria-label="${l}"></label>`).join("");
  const optionInputs = () => [...root.querySelectorAll("#opts input")];

  function say(key) { sayKey = key; $("r-say").textContent = t(key); }

  function fillPick() {
    const mine = list.filter((p) => p.language === App.lang);
    const shown = mine.length ? mine : list;
    $("pick").innerHTML = `<option value="">${esc(t("pick_none"))}</option>` + shown.map((p) =>
      `<option value="${esc(p.key)}">${esc(t("level"))} ${p.level} · ${esc(p.id.split("_").pop())} · ${esc(p.start)}…</option>`).join("");
    $("pick").value = shown.some((p) => p.key === chosen) ? chosen : "";
    root.querySelector(".practice").classList.toggle("hidden", !list.length);
  }

  function texts() {
    $("drop-note").textContent = t(info.ocr ? "drop_ok" : "drop_no");
    $("ocr-note").textContent = ocrNote ? t(ocrNote) : "";
    $("ocr-note").classList.toggle("hidden", !ocrNote);
    say(sayKey); fillPick();
    if (last) showResult(last);
  }

  function setClock(elapsed, limit) {
    const left = Math.max(0, Math.ceil(limit - elapsed));
    $("clock-n").textContent = left;
    $("clock-run").style.strokeDashoffset = String(Math.min(100, (elapsed / limit) * 100));
    $("clock").classList.toggle("late", elapsed > limit * 0.75 && elapsed <= limit);
    $("clock").classList.toggle("over", elapsed > limit);
  }

  function fill(problem) {
    $("text").value = problem.text || "";
    optionInputs().forEach((input) => { input.value = (problem.options || {})[input.dataset.l] || ""; });
  }

  function showShot(src) {
    $("shot").classList.toggle("hidden", !src);
    if (src) $("shot").src = src;
  }

  async function pick(key) {
    chosen = "";
    if (!key) return;
    const problem = await api("/api/reason/problem?key=" + encodeURIComponent(key));
    if (!alive) return;
    fill(problem); chosen = key; ocrNote = ""; texts();
    showShot(problem.image ? "/api/reason/image/" + encodeURIComponent(key) : "");
    $("result").classList.add("hidden"); last = null; setClock(0, info.time_limit);
  }

  async function readPicture(file) {
    if (!file || !file.type.startsWith("image/")) return;
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result); reader.onerror = reject;
      reader.readAsDataURL(file);
    });
    if (!alive) return;
    chosen = ""; $("pick").value = ""; showShot(dataUrl);
    if (!info.ocr) { ocrNote = "drop_no"; texts(); $("text").focus(); return; }
    ocrNote = "reading"; texts(); Owl.set("thinking");
    try {
      const read = await api("/api/upload-ocr", { image_base64: dataUrl, filename: file.name, language: App.lang });
      if (!alive) return;
      fill(read.problem); ocrNote = "read_ok";
    } catch { ocrNote = "read_fail"; }
    if (!alive) return;
    Owl.set("idle"); texts();
  }

  function showResult(r) {
    last = r;
    const limit = r.limit || info.time_limit;
    $("result").classList.remove("hidden");
    $("r-letter").textContent = r.answer || "?";
    const value = (r.options || {})[r.answer];
    $("r-value").innerHTML = value ? renderRichText(value, true) : "";
    $("r-time").textContent = t(r.seconds > limit ? "too_slow" : "in_time", { s: Number(r.seconds).toFixed(1), l: limit });
    $("r-key").classList.toggle("hidden", r.correct === null || r.correct === undefined);
    $("result").classList.remove("is-ok", "is-bad");
    if (r.correct !== null && r.correct !== undefined) {
      $("r-key").className = "key " + (r.correct ? "ok" : "bad");
      $("result").classList.toggle("is-ok", !!r.correct); $("result").classList.toggle("is-bad", !r.correct);
      $("r-key").textContent = t(r.correct ? "key_ok" : "key_bad", { k: r.label });
    }
    const why = T[App.lang].reasons[r.code_reason] || r.code_reason || r.status;
    const probs = r.probabilities || {};
    const has = Object.keys(probs).length > 0;
    $("r-how").textContent = r.how === "code" ? t("how_code", { v: r.code_value, a: r.answer })
      : !has ? t("how_fallback", { r: r.status })
      : r.program && r.code_reason && r.code_reason !== "ok" ? t("how_letter_code", { r: why }) : t("how_letter");
    const top = r.letter_guess;
    $("r-probs").innerHTML = has && r.how !== "code" ? LETTERS.map((l) => `<div class="prob ${l === top ? "top" : ""}"><b>${l}</b><div><i style="width:${Math.round((probs[l] || 0) * 100)}%"></i></div><span>${Math.round((probs[l] || 0) * 100)}%</span></div>`).join("") : "";
    $("r-program-box").classList.toggle("hidden", !r.program);
    $("r-program-title").textContent = t("program");
    $("r-program").textContent = r.program || "";
    $("r-program-box").open = r.how === "code";
  }

  function finish(job, options) {
    clearInterval(timer); busy = false; $("solve").disabled = false;
    if (job.error || !job.result) {
      say("say_error"); $("error").textContent = job.error || ""; Owl.set("wrong", { ms: 5000 });
      return;
    }
    const r = { ...job.result, options };
    setClock(r.seconds, r.limit || info.time_limit);
    $("clock-n").textContent = Math.max(0, Math.round((r.limit || info.time_limit) - r.seconds));
    showResult(r);
    if (r.correct === true) { say("say_right"); Owl.set("correct", { ms: 7000 }); owl.celebrate(); }
    else if (r.correct === false) { say("say_wrong"); Owl.set("wrong", { ms: 8000 }); }
    else { say(r.how === "code" ? "say_done_code" : "say_done_letter"); Owl.set("hint", { ms: 8000 }); }
    $("result").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function solve() {
    if (busy) return;
    const text = $("text").value.trim();
    const options = Object.fromEntries(optionInputs().map((i) => [i.dataset.l, i.value.trim()]).filter(([, v]) => v));
    $("error").textContent = "";
    if (!text) { $("text").focus(); return; }
    busy = true; $("solve").disabled = true; $("result").classList.add("hidden"); last = null;
    $("live").classList.add("hidden"); $("live-code").textContent = "";
    setClock(0, info.time_limit); say("say_wait"); Owl.set("thinking");
    let job;
    try {
      job = await api("/api/reason/solve", chosen ? { key: chosen } : { problem: { text, options, language: App.lang } });
    } catch (error) {
      busy = false; $("solve").disabled = false; $("error").textContent = error.message; Owl.set("idle"); say("say_idle");
      return;
    }
    const sent = job.problem.options || options;
    let started = 0;
    timer = setInterval(async () => {
      if (!alive) { clearInterval(timer); return; }
      if (started) setClock((Date.now() - started) / 1000, info.time_limit);
      let now;
      try { now = await api("/api/reason/job?id=" + job.id); } catch { return; }
      if (!alive || !busy) return;
      if (now.state === "solving" && !started) { started = Date.now() - now.elapsed * 1000; say("say_think"); }
      if (now.writing) { $("live").classList.remove("hidden"); $("live-title").textContent = t("live"); $("live-code").textContent = now.writing; }
      if (now.state === "done") { $("live").classList.add("hidden"); finish(now, sent); }
    }, 400);
  }

  function clear() {
    chosen = ""; ocrNote = ""; last = null;
    fill({}); showShot(""); $("pick").value = ""; $("result").classList.add("hidden"); $("error").textContent = "";
    setClock(0, info.time_limit); say("say_idle"); texts(); $("text").focus();
  }

  const edited = () => { chosen = ""; $("pick").value = ""; };  // an edited problem is a new one: no answer key
  $("text").addEventListener("input", edited);
  $("opts").addEventListener("input", edited);
  $("pick").onchange = (e) => pick(e.target.value).catch((error) => { $("error").textContent = error.message; });
  $("random").onclick = () => {
    const mine = list.filter((p) => p.language === App.lang);
    const pool = mine.length ? mine : list;
    if (!pool.length) return;
    const one = pool[Math.floor(Math.random() * pool.length)];
    $("pick").value = one.key; pick(one.key).catch(() => {});
  };
  $("solve").onclick = solve;
  $("clear").onclick = clear;
  const drop = $("drop");
  drop.onclick = () => $("file").click();
  drop.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("file").click(); } };
  $("file").onchange = (e) => { readPicture(e.target.files[0]); e.target.value = ""; };
  ["dragenter", "dragover"].forEach((type) => drop.addEventListener(type, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((type) => drop.addEventListener(type, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => readPicture(e.dataTransfer.files[0]));
  const onPaste = (e) => {
    const file = [...(e.clipboardData?.files || [])].find((f) => f.type.startsWith("image/"));
    if (file) { e.preventDefault(); readPicture(file); }
  };
  document.addEventListener("paste", onPaste);

  const stopTexts = App.texts(root, T, texts);
  setClock(0, 60);
  (async function init() {
    try { info = await api("/api/info"); } catch { /* the page still takes typed problems */ }
    try { list = await api("/api/reason/problems"); } catch { list = []; }
    if (!alive) return;
    setClock(0, info.time_limit); texts();
  })();

  return () => {
    alive = false; clearInterval(timer); stopTexts();
    document.removeEventListener("paste", onPaste);
  };
}
