/* Home: a short landing page for students. */
const T = {
  eng: {
    title: "Meet the owl that helps you think.",
    lead: "Practise Kangaroo maths problems with a coach that gives you hints, never the answer. It all runs inside a small 3D-printed owl, with no internet.",
    go: "Start practising", offline: "Works offline",
    teach_h: "Teach", teach_p: "Solve problems at your level. Stuck? Climb the hint ladder, one step at a time.",
    reason_h: "Reason", reason_p: "Show the owl a problem and watch it find an answer in under 60 seconds.",
    stats_h: "Stats", stats_p: "How often is the owl right? The numbers we measured, with nothing hidden.",
    inside_h: "What is inside the owl?",
    inside_p: "An Arduino UNO Q board with 4 GB of memory and a small language model (Qwen3.5 0.8B). Its LED matrix is the owl's eyes: they blink, think, wink when there is a hint, and close when the owl falls asleep.",
  },
  cat: {
    title: "Et presentem el mussol que t'ajuda a pensar.",
    lead: "Practica problemes de les proves Cangur amb un entrenador que et dona pistes, mai la resposta. Tot funciona dins d'un petit mussol imprès en 3D, sense internet.",
    go: "Comença a practicar", offline: "Funciona sense internet",
    teach_h: "Aprèn", teach_p: "Resol problemes del teu nivell. T'has encallat? Puja l'escala de pistes, graó a graó.",
    reason_h: "Raona", reason_p: "Ensenya un problema al mussol i mira com troba una resposta en menys de 60 segons.",
    stats_h: "Resultats", stats_p: "Quantes vegades l'encerta el mussol? Els nombres que hem mesurat, sense amagar res.",
    inside_h: "Què hi ha dins del mussol?",
    inside_p: "Una placa Arduino UNO Q amb 4 GB de memòria i un model de llenguatge petit (Qwen3.5 0.8B). La matriu de LEDs són els ulls del mussol: parpellegen, pensen, piquen l'ullet quan hi ha una pista i es tanquen quan el mussol s'adorm.",
  },
};

// The two idle eyes of owl_eyes/eyes.py, on the board's 8 x 13 LED matrix
const EYES = [".............", ".####..####..", "#....##....#.", "#.##.##.##.#.", "#.##.##.##.#.", "#....##....#.", ".####..####..", "............."];

export function mount(root) {
  window.Owl.mount(root.querySelector("#home-owl"));
  const leds = root.querySelector(".leds");
  leds.innerHTML = EYES.map((row, r) => [...row].map((c, x) =>
    `<rect class="${c === "#" ? "on" : ""}" x="${68 + x * 5.2}" y="${27 + r * 5.2}" width="3.6" height="3.6" rx="1"/>`).join("")).join("");
  return window.App.texts(root, T);
}
