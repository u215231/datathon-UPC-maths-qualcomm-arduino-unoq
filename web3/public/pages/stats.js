/* Stats: the numbers we measured, from /data/stats.json (edit that file to update the page). */
import { esc } from "/pages/rich.js";

const T = {
  eng: {
    title: "How often is Uino right?",
    lead: "Right answers out of {r} practice problems. Guessing gets {c}%.",
    k_ours: "Uino", k_other: "Other things we tried", k_chance: "Guessing",
    chance: "guessing {c}%", board: "in Uino", laptop: "on a laptop",
    t_mean: "to answer, on average", t_mean_s: "the limit is {l} s",
    t_max: "for the slowest problem", t_max_s: "none went over the limit",
    t_prog: "of Uino's programs were right", t_prog_s: "it writes a small program for each problem",
    t_right: "right answers", t_right_s: "guessing gets {c}",
  },
  cat: {
    title: "Quantes vegades l'encerta Uino?",
    lead: "Respostes correctes de {r} problemes de pràctica. A l'atzar s'encerta el {c}%.",
    k_ours: "Uino", k_other: "Altres coses que hem provat", k_chance: "A l'atzar",
    chance: "a l'atzar {c}%", board: "dins d'Uino", laptop: "en un portàtil",
    t_mean: "per respondre, de mitjana", t_mean_s: "el límit és {l} s",
    t_max: "per al problema més lent", t_max_s: "cap ha passat del límit",
    t_prog: "dels programes d'Uino eren correctes", t_prog_s: "escriu un petit programa per a cada problema",
    t_right: "respostes correctes", t_right_s: "a l'atzar se n'encerten {c}",
  },
};

export function mount(root) {
  const $ = (id) => root.querySelector(`#${id}`);
  const App = window.App;
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
      svg += `<rect class="bar ${bar.shipped ? "ours" : ""}" x="${x0}" y="${by}" width="${x(bar.accuracy) - x0}" height="${h}" style="animation-delay:${i * 60}ms"/>` +
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
    const t = T[App.lang], s = data.set, time = data.timing, match = data.program_match, right = data.right;
    root.querySelector('[data-t="lead"]').textContent = fmt(t.lead, { r: s.rows, p: s.problems, c: s.chance });
    chart();
    const tile = (big, title, sub) => `<div class="tile"><b>${big}</b><span>${esc(title)}</span><em>${esc(sub)}</em></div>`;
    $("tiles").innerHTML =
      tile(`${right[0]}<small> / ${right[1]}</small>`, t.t_right, fmt(t.t_right_s, { c: s.chance })) +
      tile(`${match.board[0]}<small> / ${match.board[1]}</small>`, t.t_prog, t.t_prog_s) +
      tile(`${time.mean_s}<small> s</small>`, t.t_mean, fmt(t.t_mean_s, { l: time.limit_s })) +
      tile(`${time.max_s}<small> s</small>`, t.t_max, t.t_max_s);
  }

  const stopTexts = App.texts(root, T, render);
  const onResize = () => { if (data) chart(); };
  window.addEventListener("resize", onResize);
  fetch("/data/stats.json", { cache: "no-store" }).then((r) => r.json()).then((json) => {
    if (alive) { data = json; render(); }
  }).catch((error) => { $("chart").textContent = String(error); });

  return () => { alive = false; stopTexts(); window.removeEventListener("resize", onResize); };
}
