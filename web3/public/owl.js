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

  // Each eye: a white oval, a dark pupil with a glint, and an eyelid that comes down over it.
  const eye = (side, x) => `
    <g class="owl-eye owl-eye-${side}" transform="translate(${x} 90)">
      <ellipse class="owl-white" rx="16" ry="20"/>
      <g class="owl-pupil"><ellipse rx="10.5" ry="14"/><circle class="owl-glint" cx="-3.5" cy="-7" r="3.2"/></g>
      <g clip-path="url(#owl-eye-clip)"><rect class="owl-lid" x="-18" y="-22" width="36" height="44"/></g>
      <path class="owl-shut" d="M-12 3 H12"/>
      <path class="owl-smile" d="M-12 6 Q0 -8 12 6"/>
      <ellipse class="owl-eye-line" rx="16" ry="20"/>
    </g>`;

  const SVG = `
  <svg class="owl-svg" viewBox="0 0 200 212" role="img" aria-label="Owl">
    <defs><clipPath id="owl-eye-clip"><ellipse rx="16" ry="20"/></clipPath></defs>
    <g class="owl-body">
      <path class="owl-coat" d="M100 44 C146 44 170 78 164 120 C182 150 176 198 100 198 C24 198 18 150 36 120 C30 78 54 44 100 44Z"/>
      <path class="owl-wing" d="M50 126 C34 156 52 190 92 180 M150 126 C162 150 158 172 146 184"/>
      <path class="owl-ticks" d="M112 150 q5 7 10 0 q5 7 10 0 q5 7 10 0 M118 164 q5 7 10 0 q5 7 10 0"/>
      <g class="owl-feet">
        <ellipse cx="58" cy="196" rx="7" ry="11"/><ellipse cx="72" cy="198" rx="8" ry="12"/><ellipse cx="86" cy="196" rx="7" ry="11"/>
        <ellipse cx="114" cy="196" rx="7" ry="11"/><ellipse cx="128" cy="198" rx="8" ry="12"/><ellipse cx="142" cy="196" rx="7" ry="11"/>
      </g>
      <g class="owl-head">
        <path class="owl-mask" d="M100 70 C84 54 44 58 38 88 C34 112 58 126 78 122 C90 120 96 110 100 104 C104 110 110 120 122 122 C142 126 166 112 162 88 C156 58 116 54 100 70Z"/>
        <path class="owl-cap" d="M38 72 C34 56 31 40 30 18 C36 34 48 44 64 44 C78 30 122 30 136 44 C152 44 164 34 170 18 C169 40 166 56 162 72 C140 54 60 54 38 72Z"/>
        ${eye("l", 72)}${eye("r", 128)}
        <path class="owl-beak" d="M91 98 Q100 92 109 98 Q108 114 100 122 Q92 114 91 98Z"/>
      </g>
    </g>
    <g class="owl-zzz"><text x="150" y="44">z</text><text x="164" y="28">z</text><text x="178" y="12">z</text></g>
    <g class="owl-dots"><circle cx="150" cy="30" r="4"/><circle cx="164" cy="22" r="5"/><circle cx="181" cy="12" r="6.5"/></g>
    <g class="owl-bulb" transform="translate(172 26)">
      <path class="owl-bulb-glass" d="M0 -16 C10 -16 15 -9 15 -2 C15 5 9 8 8 14 H-8 C-9 8 -15 5 -15 -2 C-15 -9 -10 -16 0 -16Z"/>
      <path class="owl-bulb-base" d="M-7 18 H7 M-5 22 H5"/>
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
