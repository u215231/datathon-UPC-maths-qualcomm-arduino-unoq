/* The owl on the page. It is drawn here as inline SVG (no image files: the board is offline),
   and its eyes follow the same states as the LED matrix inside the 3D-printed owl
   (owl_eyes/eyes.py): idle (blinks), sleeping (eyes closed, after a quiet while), thinking,
   hint, correct, wrong, listening.

     const owl = Owl.mount(element);     // draw an owl inside the element
     Owl.set("thinking");                // every owl on the page changes
     Owl.set("correct", { ms: 7000 });   // ... and goes back to idle by itself
     Owl.set("sleeping", { led: true }); // also tell the LED matrix (POST /api/eyes)

   The styles and animations are in layout.css (.owl ...). */
(function () {
  const STATES = ["idle", "sleeping", "thinking", "hint", "correct", "wrong", "listening"];
  const SLEEP_AFTER = 90000;  // ms without a key or a pointer before the owl falls asleep
  let state = "idle", backTimer = 0, sleepTimer = 0;

  const eye = (side, x) => `
    <g class="owl-eye owl-eye-${side}" transform="translate(${x} 86)">
      <circle class="owl-lens" r="31"/>
      <g class="owl-eye-open"><circle class="owl-ring" r="17"/><circle class="owl-pupil" r="7.5"/></g>
      <circle class="owl-spin" r="17" pathLength="100"/>
      <path class="owl-lid owl-lid-sleep" d="M-16 1 Q0 17 16 1"/>
      <path class="owl-lid owl-lid-happy" d="M-17 9 Q0 -17 17 9"/>
      <path class="owl-lid owl-lid-wink" d="M-15 5 Q0 -9 15 5"/>
      <circle class="owl-rim" r="31"/>
    </g>`;

  const SVG = `
  <svg class="owl-svg" viewBox="0 0 200 214" role="img" aria-label="Owl">
    <ellipse class="owl-shadow" cx="100" cy="205" rx="58" ry="7"/>
    <g class="owl-body">
      <path class="owl-wing owl-wing-l" d="M30 104 C8 124 10 160 34 174 C40 150 40 126 30 104Z"/>
      <path class="owl-wing owl-wing-r" d="M170 104 C192 124 190 160 166 174 C160 150 160 126 170 104Z"/>
      <path class="owl-feet" d="M70 196 q8 -10 16 0 q8 -10 16 0 M98 196 q8 -10 16 0 q8 -10 16 0" />
      <path class="owl-tuft" d="M44 44 L38 8 L78 28Z M156 44 L162 8 L122 28Z"/>
      <path class="owl-coat" d="M100 20 C150 20 176 62 176 116 C176 170 144 200 100 200 C56 200 24 170 24 116 C24 62 50 20 100 20Z"/>
      <ellipse class="owl-belly" cx="100" cy="154" rx="46" ry="40"/>
      <path class="owl-feathers" d="M82 140 q6 7 12 0 M106 140 q6 7 12 0 M70 156 q6 7 12 0 M94 156 q6 7 12 0 M118 156 q6 7 12 0 M82 172 q6 7 12 0 M106 172 q6 7 12 0"/>
      <g class="owl-head">
        <circle class="owl-face" cx="66" cy="86" r="38"/><circle class="owl-face" cx="134" cy="86" r="38"/>
        <path class="owl-bridge" d="M94 80 Q100 74 106 80"/>
        ${eye("l", 66)}${eye("r", 134)}
        <path class="owl-brow owl-brow-l" d="M40 50 L84 42"/>
        <path class="owl-brow owl-brow-r" d="M160 50 L116 42"/>
        <path class="owl-beak" d="M91 108 Q100 102 109 108 L100 124Z"/>
      </g>
    </g>
    <g class="owl-zzz"><text x="150" y="40">z</text><text x="166" y="24">z</text><text x="180" y="10">z</text></g>
    <g class="owl-bulb" transform="translate(168 22)">
      <path class="owl-rays" d="M0 -22 V-28 M16 -16 L20 -20 M-16 -16 L-20 -20 M22 0 H28 M-22 0 H-28"/>
      <path class="owl-bulb-glass" d="M0 -16 C10 -16 15 -9 15 -2 C15 5 9 8 8 14 H-8 C-9 8 -15 5 -15 -2 C-15 -9 -10 -16 0 -16Z"/>
      <path class="owl-bulb-base" d="M-7 17 H7 M-5 21 H5"/>
    </g>
    <g class="owl-sparks">
      <path d="M22 30 l4 10 l10 4 l-10 4 l-4 10 l-4 -10 l-10 -4 l10 -4Z"/>
      <path d="M182 56 l3 7 l7 3 l-7 3 l-3 7 l-3 -7 l-7 -3 l7 -3Z"/>
      <path d="M100 0 l3 7 l7 3 l-7 3 l-3 7 l-3 -7 l-7 -3 l7 -3Z"/>
    </g>
  </svg>`;

  function paint() {
    document.querySelectorAll(".owl").forEach((el) => { el.dataset.state = state; });
  }

  function tellBoard(name) {
    try {
      fetch("/api/eyes", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: name }) }).catch(() => {});
    } catch { /* the LED matrix is optional */ }
  }

  function armSleep() {
    clearTimeout(sleepTimer);
    sleepTimer = setTimeout(() => { if (state === "idle") set("sleeping", { led: true }); }, SLEEP_AFTER);
  }

  function set(name, options = {}) {
    if (!STATES.includes(name)) return;
    clearTimeout(backTimer);
    state = name;
    paint();
    if (options.led) tellBoard(name);
    if (options.ms) backTimer = setTimeout(() => set("idle"), options.ms);
    armSleep();
  }

  function wake() {
    if (state === "sleeping") set("idle", { led: true });
    else armSleep();
  }

  /* A burst of paper shapes from the owl: only when motion is welcome. */
  function celebrate(host) {
    if (!host || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const burst = document.createElement("div");
    burst.className = "owl-burst";
    for (let i = 0; i < 18; i++) {
      const bit = document.createElement("i");
      const angle = (i / 18) * Math.PI * 2 + Math.random() * .3;
      const far = 70 + Math.random() * 70;
      bit.style.setProperty("--x", `${Math.cos(angle) * far}px`);
      bit.style.setProperty("--y", `${Math.sin(angle) * far - 30}px`);
      bit.style.setProperty("--r", `${Math.random() * 540 - 270}deg`);
      bit.dataset.c = String(i % 4);
      burst.appendChild(bit);
    }
    host.appendChild(burst);
    setTimeout(() => burst.remove(), 1400);
  }

  function mount(host, options = {}) {
    host.classList.add("owl");
    if (options.size) host.style.setProperty("--owl-size", options.size);
    host.innerHTML = SVG;
    host.dataset.state = state;
    return { el: host, celebrate: () => celebrate(host) };
  }

  ["pointerdown", "keydown", "pointermove"].forEach((type) =>
    document.addEventListener(type, wake, { passive: true }));
  armSleep();

  window.Owl = { mount, set, celebrate, get state() { return state; } };
})();
