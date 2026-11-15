/* Home: a short landing page for students. */
const T = {
  eng: {
    title: "Meet the owl that helps you think.",
    lead: "Practise Kangaroo maths problems with a coach that gives you hints, never the answer.",
    go: "Start practising",
    teach_h: "Teach", teach_p: "Solve problems at your level. Stuck? Ask for a hint.",
    reason_h: "Reason", reason_p: "Show the owl a problem and watch it answer.",
    stats_h: "Stats", stats_p: "How often is the owl right?",
  },
  cat: {
    title: "Et presentem el mussol que t'ajuda a pensar.",
    lead: "Practica problemes de les proves Cangur amb un entrenador que et dona pistes, mai la resposta.",
    go: "Comença a practicar",
    teach_h: "Aprèn", teach_p: "Resol problemes del teu nivell. T'has encallat? Demana una pista.",
    reason_h: "Raona", reason_p: "Ensenya un problema al mussol i mira com respon.",
    stats_h: "Resultats", stats_p: "Quantes vegades l'encerta el mussol?",
  },
};

export function mount(root) {
  window.Owl.mount(root.querySelector("#home-owl"));
  return window.App.texts(root, T);
}
