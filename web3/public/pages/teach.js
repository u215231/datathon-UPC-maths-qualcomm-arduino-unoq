/* Teach: the coach. The adaptive trainer and the hint ladder of coach/ (routes under /api/coach/),
   with the owl as the coach's face:
   - a wrong answer never shows the solution; the owl asks a guiding question instead;
   - the ladder is instant: similar easier problem, method, the owl's idea, solution;
   - "the owl's idea" is the board's own solution put into words when it's ready
     (coach/grounded.py writes it in the background), and the page waits for it kindly when not. */
import { esc, renderRichText } from "/pages/rich.js";

const T = {
  cat: { start_title: "Hola! Comencem?", start_lead: "Digue'm com et dius i tria un nivell. Si l'encertes a la primera, pujaràs de nivell.",
    name: "El teu nom", level: "Per quin nivell vols començar?", go: "Comença", ladder_title: "Escala de pistes",
    next: "Següent problema", keys: "Tecles: A–E respon · P pista · N següent", progress_title: "El progrés de", your_level: "El teu nivell ara",
    how_title: "Com funciona", how_text: "Si t'equivoques, no et diem la resposta. Puges una escala de pistes: primer un problema semblant més fàcil, després el mètode, després la idea del mussol, i només al final la solució. Tot funciona dins del mussol, sense internet.",
    grade: ["5è de primària", "6è de primària", "1r d'ESO", "2n d'ESO", "3r d'ESO", "4t d'ESO", "1r de batxillerat", "2n de batxillerat"],
    lvl: "Nivell", hint_btn: "Dona'm una pista", solution_btn: "Mostra la solució", no_more: "No hi ha més pistes",
    say_start: "Hola! Soc el mussol. T'ajudaré a pensar, però la resposta la trobaràs tu.",
    say_problem: "Llegeix amb calma i tria una resposta. Si t'encalles, demana'm una pista.",
    say_right: "Correcte! Molt ben pensat.", say_right_hints: "Correcte! Ho has aconseguit amb les pistes.",
    say_wrong: "Encara no. Pensa-hi:", say_wrong_again: "Tampoc és aquesta. Vols una pista?",
    say_hint: "Aquí tens una pista. Prova-ho de nou!", say_solution: "Aquesta era difícil. El proper serà una mica més fàcil.",
    say_thinking: "Deixa'm pensar…", say_asked: "He respost la teva pregunta a sota.", say_idea: "Ja tinc la meva idea! Mira a sota.",
    say_warm_right: "Molt bé! Ara torna al problema de dalt amb la mateixa idea.",
    r_similar: "Problema semblant", r_method: "Mètode", r_model: "La idea del mussol", r_solution: "Solució",
    h_similar: "Prova primer aquest problema: s'assembla i és més fàcil", h_method: "El mètode",
    h_board: "La idea del mussol", n_board: "El mussol ha resolt aquest problema tot sol i ha comprovat la resposta. Aquí t'explica com, però explicant-se es pot equivocar: comprova-ho tu.",
    h_model: "Una idea del model del mussol", n_model: "Ho ha escrit el model petit del mussol: es pot equivocar. Comprova-ho tu.",
    h_strategy: "El primer pas", h_solution: "La solució",
    still: "El mussol encara està pensant la seva pròpia idea…", no_idea: "Aquesta vegada el mussol no ha trobat una idea millor.",
    warm_wrong: "No és aquesta. Prova una altra opció.",
    solution_is: "La resposta correcta és", confirm: "Segur que vols veure la solució? El següent problema serà més fàcil.",
    ask_label: "O pregunta al mussol amb les teves paraules (triga uns 20 segons)", ask_btn: "Pregunta",
    h_ask: "El mussol respon", h_replaced: "El mètode",
    ask_replaced: "La resposta del model no ha passat les nostres comprovacions (calculava o donava el resultat), així que et donem el mètode.",
    tried: "Fets", solved: "Resolts", first: "A la primera", hints: "Pistes", problems: "problemes al banc M3Kang", sim: "semblança",
    leave: "Canvia d'estudiant" },
  eng: { start_title: "Hi! Shall we start?", start_lead: "Tell me your name and pick a level. Get one right first time and you move up a level.",
    name: "Your name", level: "Which level do you want to start at?", go: "Start", ladder_title: "Hint ladder",
    next: "Next problem", keys: "Keys: A–E answer · P hint · N next", progress_title: "Progress of", your_level: "Your level now",
    how_title: "How it works", how_text: "If you get it wrong, we don't tell you the answer. You climb a ladder of hints: first a similar, easier problem, then the method, then the owl's idea, and only at the end the solution. Everything runs inside the owl, with no internet.",
    grade: ["Grade 5", "Grade 6", "Grade 7", "Grade 8", "Grade 9", "Grade 10", "Grade 11", "Grade 12"],
    lvl: "Level", hint_btn: "Give me a hint", solution_btn: "Show the solution", no_more: "No more hints",
    say_start: "Hi! I'm the owl. I'll help you think, but you will find the answer.",
    say_problem: "Read it calmly and pick an answer. If you get stuck, ask me for a hint.",
    say_right: "Correct! Great thinking.", say_right_hints: "Correct! You got there with the hints.",
    say_wrong: "Not yet. Think about this:", say_wrong_again: "Not that one either. Would you like a hint?",
    say_hint: "Here is a hint. Try again!", say_solution: "That was a hard one. The next one will be a bit easier.",
    say_thinking: "Let me think…", say_asked: "I answered your question below.", say_idea: "I have my own idea now! Look below.",
    say_warm_right: "Well done! Now go back to the problem above with the same idea.",
    r_similar: "Similar problem", r_method: "Method", r_model: "The owl's idea", r_solution: "Solution",
    h_similar: "First try this problem: it's similar, and easier", h_method: "The method",
    h_board: "The owl's idea", n_board: "The owl solved this problem by itself and checked its answer. Here it tells you how, but it can explain badly: check it yourself.",
    h_model: "An idea from the owl's model", n_model: "The owl's small model wrote this: it can be wrong. Check it yourself.",
    h_strategy: "The first step", h_solution: "The solution",
    still: "The owl is still thinking about its own idea…", no_idea: "This time the owl didn't find a better idea.",
    warm_wrong: "Not this one. Try another option.",
    solution_is: "The correct answer is", confirm: "Are you sure you want to see the solution? The next problem will be easier.",
    ask_label: "Or ask the owl in your own words (it takes about 20 seconds)", ask_btn: "Ask",
    h_ask: "The owl answers", h_replaced: "The method",
    ask_replaced: "The model's reply didn't pass our checks (it calculated, or gave the result), so here is the method instead.",
    tried: "Done", solved: "Solved", first: "First try", hints: "Hints", problems: "problems in the M3Kang bank", sim: "similarity",
    leave: "Change student" },
};

const API = "/api/coach";
const SESSION = "coach-student";  // who is practising, so the page survives a visit to another section

function saved() {
  try { return JSON.parse(sessionStorage.getItem(SESSION) || "null"); } catch { return null; }
}
function remember(value) {
  try {
    if (value) sessionStorage.setItem(SESSION, JSON.stringify(value));
    else sessionStorage.removeItem(SESSION);
  } catch { /* the page works without it */ }
}

export function mount(root) {
  const $ = (id) => root.querySelector(`#${id}`);
  const App = window.App, Owl = window.Owl;
  const owl = Owl.mount($("teach-owl"));
  let name = "", current = null, warm = null, done = false, rungs = 0, info = null, asking = false, wrongs = 0;
  let alive = true, poll = 0, sayKey = "say_start", sayExtra = "";
  const t = (key) => T[App.lang][key];

  async function api(path, body) {
    const response = await fetch(API + path, body
      ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      : {});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || response.statusText);
    return data;
  }

  /* The owl's speech bubble: a line of ours (by key, so it follows the language), then a hint text. */
  function say(key, extra = "") {
    sayKey = key; sayExtra = extra;
    $("say").innerHTML = esc(t(key)) + (extra ? `<small>${esc(extra)}</small>` : "");
  }

  function texts() {
    const chosen = $("level").value || "2";
    $("level").innerHTML = t("grade").map((g, i) => `<option value="${i}">${t("lvl")} ${i} · ${esc(g)}</option>`).join("");
    $("level").value = chosen;
    $("bank").textContent = info ? `${info.problems} ${t("problems")}` : "";
    $("who").textContent = name;
    say(sayKey, sayExtra);
    if (current) { steps(); hintButton(); meta(); }
  }

  function optionButtons(box, problem, onPick) {
    box.innerHTML = "ABCDE".split("").map((l) =>
      `<button data-l="${l}"><b>${l}</b><span>${renderRichText(problem.options[l], true)}</span></button>`).join("");
    box.onclick = (e) => { const b = e.target.closest("button"); if (b && !b.disabled) onPick(b.dataset.l).catch(alertError); };
  }

  function mark(box, letter, correct) {
    box.querySelectorAll("button").forEach((b) => {
      if (b.dataset.l === letter) { b.classList.add(correct ? "right-one" : "wrong-one"); b.disabled = true; }
      else if (correct) { b.disabled = true; b.classList.add("dim"); }
    });
  }

  // "12. A farmer has..." -> "A farmer has...": the number in the test paper means nothing here
  const body = (text) => renderRichText(String(text).replace(/^\s*\d{1,2}\s*[.)]\s+/, ""));

  function meta() {
    $("p-level").textContent = `${t("lvl")} ${current.level} · ${t("grade")[current.level]}`;
  }

  function show(problem) {
    clearInterval(poll);
    current = problem; warm = null; done = false; rungs = 0; wrongs = 0;
    $("start").classList.add("hidden");
    ["problem", "ladder", "progress"].forEach((id) => $(id).classList.remove("hidden"));
    meta();
    $("p-topic").textContent = problem.topic_name;
    $("p-text").innerHTML = body(problem.text);
    optionButtons($("p-options"), problem, answer);
    $("hints").innerHTML = ""; $("question").value = ""; $("ask-note").textContent = "";
    $("ask-box").classList.toggle("hidden", !(info && info.coach));
    say("say_problem"); Owl.set("idle");
    steps(); hintButton(); progress();
    window.scrollTo({ top: 0 });
  }

  function steps() {
    $("steps").innerHTML = current.ladder.map((r, i) => `<li class="${i < rungs ? "done" : ""}">${esc(t("r_" + r))}</li>`).join("");
  }

  function hintButton() {
    if (!current) return;
    const left = current.ladder.length - rungs, button = $("hint");
    button.disabled = done || left <= 0;
    button.textContent = left <= 0 ? t("no_more") : left === 1 ? t("solution_btn") : t("hint_btn");
    $("ask").disabled = done || asking; $("question").disabled = done || asking;
  }

  function hintBox(kind, title, note) {
    const box = document.createElement("div");
    box.className = "hint " + kind;
    box.innerHTML = `<h3>${esc(title)}</h3>${note ? `<div class="note">${esc(note)}</div>` : ""}<div class="body"></div>`;
    $("hints").append(box);
    setTimeout(() => box.scrollIntoView({ behavior: "smooth", block: "nearest" }), 30);
    return box;
  }

  async function ask() {
    const question = $("question").value.trim();
    if (!current || done || asking || question.length < 3) { $("question").focus(); return; }
    asking = true; hintButton(); say("say_thinking"); Owl.set("thinking");
    try {
      const r = await api("/ask", { name, id: current.id, question });
      if (!alive) return;
      const box = hintBox(r.replaced ? "" : "board", r.replaced ? `${t("h_replaced")} · ${r.topic}` : `${t("h_ask")} (${r.seconds} s)`,
        r.replaced ? t("ask_replaced") : t("n_model"));
      box.querySelector(".body").innerHTML = `<div class="q"></div><div class="a"></div>`;
      box.querySelector(".q").textContent = "« " + question + " »";
      box.querySelector(".a").textContent = r.text;
      $("question").value = ""; $("ask-note").textContent = "";
      say("say_asked"); Owl.set("hint", { ms: 8000 });
    } catch (error) { if (alive) { $("ask-note").textContent = error.message; Owl.set("idle"); say("say_problem"); } }
    if (!alive) return;
    asking = false; hintButton(); progress();
  }

  async function answer(letter) {
    if (done) return;
    const r = await api("/answer", { name, id: current.id, choice: letter });
    if (!alive) return;
    mark($("p-options"), letter, r.correct);
    if (r.correct) {
      done = true; clearInterval(poll);
      root.querySelectorAll(".thinking-strip").forEach((strip) => strip.remove());
      say(rungs || r.wrong.length ? "say_right_hints" : "say_right");
      Owl.set("correct", { ms: 7000 }); owl.celebrate();
    } else {
      wrongs += 1;
      if (wrongs === 1 && r.nudge) say("say_wrong", r.nudge); else say("say_wrong_again");
      Owl.set("wrong", { ms: 6000 });
    }
    hintButton(); progress();
  }

  async function warmAnswer(letter) {
    if (!warm || warm.done) return;
    const r = await api("/answer", { name, id: warm.problem.id, choice: letter });
    if (!alive || !warm) return;
    mark(warm.box, letter, r.correct); warm.done = r.correct;
    warm.verdict.textContent = r.correct ? t("say_warm_right") : t("warm_wrong");
    warm.verdict.className = "verdict " + (r.correct ? "ok" : "bad");
    Owl.set(r.correct ? "correct" : "wrong", { ms: r.correct ? 5000 : 4000 });
    if (r.correct) say("say_warm_right");
  }

  /* The owl's own idea wasn't ready when the student reached its rung: ask now and then, and add it when it is. */
  function waitForIdea(box, shown) {
    const strip = document.createElement("div");
    strip.className = "thinking-strip";
    strip.innerHTML = `<span class="dots"><i></i><i></i><i></i></span><span></span>`;
    strip.lastChild.textContent = t("still");
    box.append(strip);
    const id = current.id;
    let tries = 0;
    clearInterval(poll);
    poll = setInterval(async () => {
      if (!alive || !current || current.id !== id || done || ++tries > 150) { clearInterval(poll); strip.remove(); return; }
      let g;
      try { g = await api(`/grounded?name=${encodeURIComponent(name)}&id=${encodeURIComponent(id)}`); } catch { return; }
      if (!alive || !current || current.id !== id) return;
      if (g.status === "thinking") return;
      clearInterval(poll); strip.remove();
      if (g.text && shown !== "board") {
        const idea = hintBox("board", t("h_board"), t("n_board"));
        idea.querySelector(".body").textContent = g.text;
        say("say_idea"); Owl.set("hint", { ms: 8000 });
      } else if (!g.text) {
        const none = document.createElement("div"); none.className = "note"; none.textContent = t("no_idea");
        box.append(none);
      }
    }, 3000);
  }

  async function hint() {
    if (!current || done || rungs >= current.ladder.length) return;
    if (current.ladder.length - rungs === 1 && !confirm(t("confirm"))) return;
    const h = await api("/hint", { name, id: current.id });
    if (!alive) return;
    rungs = current.ladder.indexOf(h.type) + 1;
    if (h.type === "similar") {
      const box = hintBox("", t("h_similar"));
      box.querySelector(".body").innerHTML = `<div class="meta"><span class="pill">${esc(t("lvl"))} ${h.problem.level}</span><span class="pill sun">${esc(h.problem.topic_name)}</span><span class="pill">${esc(t("sim"))} ${Math.round(h.similarity * 100)}%</span></div><div class="text"></div><div class="options"></div><div class="verdict"></div>`;
      box.querySelector(".text").innerHTML = body(h.problem.text);
      warm = { problem: h.problem, box: box.querySelector(".options"), verdict: box.querySelector(".verdict"), done: false };
      optionButtons(warm.box, h.problem, warmAnswer);
    } else if (h.type === "solution") {
      done = true; warm = null; clearInterval(poll);
      root.querySelectorAll(".thinking-strip").forEach((strip) => strip.remove());
      const box = hintBox("solution", t("h_solution"));
      box.querySelector(".body").innerHTML = `${esc(t("solution_is"))} <b>${esc(h.label)}) ${renderRichText(h.value, true)}</b>`;
      $("p-options").querySelectorAll("button").forEach((b) => { b.disabled = true; if (b.dataset.l === h.label) b.classList.add("right-one"); else b.classList.add("dim"); });
    } else if (h.type === "model") {
      const source = ["board", "model", "strategy"].includes(h.source) ? h.source : "model";
      const box = hintBox(source === "board" ? "board" : "", t("h_" + source), source === "strategy" ? "" : t("n_" + source));
      box.querySelector(".body").textContent = h.text;
      if (h.thinking) waitForIdea(box, source);
    } else {
      const box = hintBox("", `${t("h_method")}${h.topic ? " · " + h.topic : ""}`);
      box.querySelector(".body").textContent = h.text;
    }
    if (h.type === "solution") { say("say_solution"); Owl.set("idle"); }
    else { say("say_hint"); Owl.set("hint", { ms: 8000 }); }
    steps(); hintButton(); progress();
  }

  async function next() {
    if (!current) return;
    const r = await api("/next", { name });
    if (alive) show(r.problem);
  }

  async function progress() {
    try {
      const p = await api("/progress?name=" + encodeURIComponent(name));
      if (!alive) return;
      $("track").innerHTML = [0, 1, 2, 3, 4, 5, 6, 7].map((l) => `<div class="${l === p.level ? "on" : l < p.level ? "below" : ""}">${l}</div>`).join("");
      $("stats").innerHTML = [["tried", p.tried], ["solved", p.solved], ["first", p.first_try], ["hints", p.hints]]
        .map(([k, v]) => `<div><b>${v}</b><span>${esc(t(k))}</span></div>`).join("");
      $("topics").innerHTML = p.topics.map((x) => `<tr><td>${esc(x.topic)}</td><td>${x.solved}/${x.tried}</td></tr>`).join("");
    } catch { /* the panel keeps its last numbers */ }
  }

  async function begin(level) {
    const r = await api("/start", { name, language: App.lang, level });
    if (!alive) return;
    remember({ name });
    texts();
    show(r.problem);
  }

  async function start() {
    name = $("name").value.trim(); $("start-error").textContent = "";
    if (!name) { $("name").focus(); return; }
    try { await begin(Number($("level").value)); }
    catch (error) { name = ""; $("start-error").textContent = error.message; }
  }

  function leave() {
    remember(null); clearInterval(poll);
    name = ""; current = null; warm = null; done = false; rungs = 0;
    ["problem", "ladder", "progress"].forEach((id) => $(id).classList.add("hidden"));
    $("start").classList.remove("hidden");
    $("name").value = ""; say("say_start"); Owl.set("idle");
    texts(); $("name").focus();
  }

  function alertError(error) {
    if (alive) $("ask-note").textContent = error.message;
  }

  $("go").onclick = start;
  $("hint").onclick = () => hint().catch(alertError);
  $("next").onclick = () => next().catch(alertError);
  $("leave").onclick = leave;
  $("name").addEventListener("keydown", (e) => { if (e.key === "Enter") start(); });
  $("ask").onclick = ask;
  $("question").addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
  $("question").addEventListener("focus", () => { if (Owl.state === "idle") Owl.set("listening", { ms: 15000 }); });

  function onKeydown(e) {
    if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName) || e.ctrlKey || e.metaKey || e.altKey || !current) return;
    const k = e.key.toUpperCase();
    if ("ABCDE".includes(k) && k.length === 1) (warm && !warm.done ? warmAnswer(k) : answer(k)).catch(alertError);
    else if (k === "P" || k === "H") hint().catch(alertError);
    else if (k === "N") next().catch(alertError);
  }
  document.addEventListener("keydown", onKeydown);

  // Texts follow the language. A problem on screen is in the student's language, so switching
  // while practising gives a new problem in the new language, at the same level.
  const stopTexts = App.texts(root, T, () => {
    texts();
    if (current && current.language !== App.lang) {
      api("/progress?name=" + encodeURIComponent(name)).then((p) => begin(p.level)).catch(alertError);
    }
  });

  (async function init() {
    try { info = await api("/info"); } catch { info = null; }
    if (!alive) return;
    texts();
    // Coming back from another section: carry on at the level the student had reached
    const student = saved();
    if (student && student.name) {
      try {
        const p = await api("/progress?name=" + encodeURIComponent(student.name));
        if (!alive) return;
        name = student.name;
        await begin(p.level);
      } catch { name = ""; remember(null); texts(); }
    }
  })();

  return () => {
    alive = false; clearInterval(poll); stopTexts();
    document.removeEventListener("keydown", onKeydown);
  };
}
