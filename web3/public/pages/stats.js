/* Stats: the numbers we measured, from /data/stats.json (edit that file to update the page). */
import { esc } from "/pages/rich.js";

const T = {
  eng: {
    title: "How often is the owl right?",
    lead: "Correct answers on the organisers' practice set: {r} rows ({p} problems, each in English and Catalan). Guessing gets {c}%.",
    k_ours: "What we shipped", k_other: "Other things we tried", k_chance: "Guessing (chance)",
    chance: "chance {c}%", board: "on the board", laptop: "on a laptop",
    t_mean: "average time per problem", t_mean_s: "on the board, limit {l} s",
    t_max: "slowest problem", t_max_s: "{o} of {r} over the limit",
    t_prog: "program answers that were right", t_prog_s: "on the board, when the result matches an option ({a} of {b} on a laptop)",
    t_ft: "memorised, but no better on new problems", t_ft_s: "fine-tuning learned the bank by heart and stayed at chance on unseen problems",
    honest_h: "What the owl wants you to know",
    honest: [
      "The model inside the owl is tiny (0.8 billion parameters). On its own it is barely better than guessing.",
      "Our best step was to let it write a small Python program and run it. When the program's result matches an option, it is usually right.",
      "Balancing the letters across a whole test added a few points on the board ({n}% to {s}%).",
      "Bigger models did not help inside the 60-second limit: they were slower, not smarter.",
      "A set of {r} rows is small: a few points up or down can be luck.",
    ],
    updated: "Numbers updated {d}.",
  },
  cat: {
    title: "Quantes vegades l'encerta el mussol?",
    lead: "Respostes correctes al conjunt de pràctica dels organitzadors: {r} files ({p} problemes, cadascun en anglès i en català). A l'atzar s'encerta el {c}%.",
    k_ours: "El que hem lliurat", k_other: "Altres coses que hem provat", k_chance: "A l'atzar",
    chance: "atzar {c}%", board: "a la placa", laptop: "en un portàtil",
    t_mean: "temps mitjà per problema", t_mean_s: "a la placa, límit {l} s",
    t_max: "el problema més lent", t_max_s: "{o} de {r} per sobre del límit",
    t_prog: "respostes del programa que eren correctes", t_prog_s: "a la placa, quan el resultat coincideix amb una opció ({a} de {b} en un portàtil)",
    t_ft: "memoritzats, però no millor amb problemes nous", t_ft_s: "l'ajust fi va aprendre el banc de memòria i es va quedar a l'atzar amb problemes no vistos",
    honest_h: "El que el mussol vol que sàpigues",
    honest: [
      "El model que hi ha dins del mussol és molt petit (0,8 mil milions de paràmetres). Tot sol, amb prou feines supera l'atzar.",
      "El nostre millor pas va ser deixar-li escriure un petit programa en Python i executar-lo. Quan el resultat del programa coincideix amb una opció, normalment és correcte.",
      "Equilibrar les lletres en tota una prova va afegir uns quants punts a la placa (del {n}% al {s}%).",
      "Els models més grans no van ajudar dins del límit de 60 segons: eren més lents, no més llestos.",
      "Un conjunt de {r} files és petit: uns quants punts amunt o avall poden ser sort.",
    ],
    updated: "Nombres actualitzats el {d}.",
  },
};

export function mount(root) {
  const $ = (id) => root.querySelector(`#${id}`);
  const App = window.App;
  window.Owl.mount($("stats-owl"));
  let data = null, alive = true, drawn = false;
  const fmt = (text, values) => String(text).replace(/\{(\w)\}/g, (_, k) => values[k] ?? "");

  function chart() {
    const en = App.lang === "eng", t = T[App.lang];
    const bars = [...data.bars].sort((a, b) => a.accuracy - b.accuracy);
    const narrow = root.clientWidth < 640;
    const W = narrow ? 420 : 920, labelW = narrow ? 0 : 330, row = narrow ? 62 : 46, top = 30;
    const x0 = labelW + 4, plotW = W - x0 - 56, max = 40;
    const x = (v) => x0 + (v / max) * plotW;
    const H = top + bars.length * row + 26;
    const chance = data.set.chance;
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t.title)}">`;
    for (let v = 0; v <= max; v += 10) {
      svg += `<line class="grid" x1="${x(v)}" x2="${x(v)}" y1="${top - 6}" y2="${H - 22}"/><text class="tick" x="${x(v)}" y="${H - 6}" text-anchor="middle">${v}%</text>`;
    }
    bars.forEach((bar, i) => {
      const y = top + i * row, h = narrow ? 22 : 26, by = narrow ? y + 26 : y + 6;
      const name = esc(en ? bar.en : bar.ca), note = esc((en ? bar.note_en : bar.note_ca) || "");
      const where = bar.where === "laptop" ? t.laptop : t.board;
      if (narrow) svg += `<text class="name" x="${x0}" y="${y + 16}">${name} <tspan class="tag">· ${esc(where)}</tspan></text>`;
      else svg += `<text class="name" x="${labelW - 10}" y="${y + (note ? 18 : 24)}" text-anchor="end">${name}</text>` +
        (note ? `<text class="sub" x="${labelW - 10}" y="${y + 34}" text-anchor="end">${note}</text>` : "");
      svg += `<rect class="bar ${bar.shipped ? "ours" : ""}" x="${x0}" y="${by}" width="${x(bar.accuracy) - x0}" height="${h}" rx="6" style="animation-delay:${i * 60}ms"/>` +
        `<text class="val" x="${x(bar.accuracy) + 8}" y="${by + h / 2 + 6}">${bar.accuracy}%</text>` +
        (narrow ? "" : `<text class="tag" x="${x(bar.accuracy) + 52}" y="${by + h / 2 + 5}">${esc(where)}</text>`);
    });
    svg += `<line class="chance" x1="${x(chance)}" x2="${x(chance)}" y1="${top - 14}" y2="${H - 22}"/>` +
      `<text class="chance-label" x="${x(chance) + 6}" y="${top - 12}">${esc(fmt(t.chance, { c: chance }))}</text></svg>`;
    $("chart").innerHTML = svg;
    $("chart").classList.toggle("grow", !drawn);  // the bars grow once, not on every resize
    drawn = true;
  }

  function render() {
    if (!data) return;
    const t = T[App.lang], s = data.set, time = data.timing, match = data.program_match, ft = data.finetune.memorised;
    root.querySelector('[data-t="lead"]').textContent = fmt(t.lead, { r: s.rows, p: s.problems, c: s.chance });
    chart();
    const tile = (big, title, sub) => `<div class="tile"><b>${big}</b><span>${esc(title)}</span><em>${esc(sub)}</em></div>`;
    $("tiles").innerHTML =
      tile(`${time.mean_s}<small> s</small>`, t.t_mean, fmt(t.t_mean_s, { l: time.limit_s })) +
      tile(`${time.max_s}<small> s</small>`, t.t_max, fmt(t.t_max_s, { o: time.over_limit, r: s.rows })) +
      tile(`${match.board[0]}<small> / ${match.board[1]}</small>`, t.t_prog, fmt(t.t_prog_s, { a: match.laptop[0], b: match.laptop[1] })) +
      tile(`${ft[0]}<small> / ${ft[1]}</small>`, t.t_ft, t.t_ft_s);
    const before = data.bars.find((b) => b.id === "shipped_no_balance"), shipped = data.bars.find((b) => b.id === "shipped_board");
    $("honest").innerHTML = t.honest.map((line) =>
      `<li>${esc(fmt(line, { n: before?.accuracy, s: shipped?.accuracy, r: s.rows }))}</li>`).join("");
    $("updated").textContent = fmt(t.updated, { d: data.updated });
  }

  const stopTexts = App.texts(root, T, render);
  const onResize = () => { if (data) chart(); };
  window.addEventListener("resize", onResize);
  fetch("/data/stats.json", { cache: "no-store" }).then((r) => r.json()).then((json) => {
    if (alive) { data = json; render(); }
  }).catch((error) => { $("chart").textContent = String(error); });

  return () => { alive = false; stopTexts(); window.removeEventListener("resize", onResize); };
}
