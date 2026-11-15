/* The shared shell: header (brand, navigation, language switch) and footer (about us, logos).
   The router only swaps the middle of the page, so these never reload.

   Language: window.App.lang is "eng" or "cat". A page registers its texts with
   App.texts(root, T): every element with data-t="key" gets T[lang][key], now and whenever the
   student switches language. */
(function () {
  const ICON = {
    home: '<path d="M3 11 L12 3 L21 11 M6 9.5 V20 H18 V9.5"/>',
    teach: '<circle cx="8" cy="11" r="4"/><circle cx="16" cy="11" r="4"/><path d="M5 5 L4 2 L9 4 M19 5 L20 2 L15 4 M11 16 L12 18 L13 16"/>',
    reason: '<path d="M12 3 a6 6 0 0 1 3.5 10.9 V16 H8.5 V13.9 A6 6 0 0 1 12 3Z M9.5 19.5 H14.5 M10.5 22 H13.5"/>',
    stats: '<path d="M4 20 V12 M10 20 V5 M16 20 V9 M22 20 H2"/>',
  };
  const pages = [
    { key: "home", href: "/", en: "Home", ca: "Inici" },
    { key: "teach", href: "/teach", en: "Teach", ca: "Aprèn" },
    { key: "reason", href: "/reason", en: "Reason", ca: "Raona" },
    { key: "stats", href: "/stats", en: "Stats", ca: "Resultats" },
  ];
  const SHELL = {
    eng: { tagline: "Your best friend for the Kangaroo tests!", about: "About us", lang: "Language" },
    cat: { tagline: "El teu millor amic per les proves Cangur!", about: "Qui som", lang: "Idioma" },
  };

  let lang = "eng";
  try {
    lang = localStorage.getItem("owl-lang") || ((navigator.language || "").toLowerCase().startsWith("ca") ? "cat" : "eng");
  } catch { /* private mode: English */ }
  if (lang !== "cat") lang = "eng";
  const listeners = new Set();

  const App = {
    get lang() { return lang; },
    setLang(next) {
      if ((next !== "cat" && next !== "eng") || next === lang) return;
      lang = next;
      try { localStorage.setItem("owl-lang", lang); } catch { /* fine */ }
      render();
      listeners.forEach((fn) => { try { fn(lang); } catch (error) { console.error(error); } });
    },
    /* Call fn(lang) on every switch. Returns a function that stops it. */
    onLang(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    /* Fill data-t texts inside root from T, and keep them in step with the language. */
    texts(root, T, after) {
      const fill = () => {
        root.querySelectorAll("[data-t]").forEach((el) => {
          const value = T[lang][el.dataset.t];
          if (value !== undefined) el.textContent = value;
        });
        root.querySelectorAll("[data-t-placeholder]").forEach((el) => {
          el.placeholder = T[lang][el.dataset.tPlaceholder] || "";
        });
        if (after) after(lang);
      };
      fill();
      return App.onLang(fill);
    },
  };
  window.App = App;

  const headerHost = document.getElementById("site-header");
  const footerHost = document.getElementById("site-footer");
  if (!headerHost || !footerHost) return;
  let active = document.body.dataset.page || "home";

  function render() {
    const s = SHELL[lang];
    document.documentElement.lang = lang === "cat" ? "ca" : "en";
    headerHost.innerHTML = `
      <header class="site-header">
        <div class="site-header-inner">
          <a class="brand" href="/" data-nav>
            <span class="brand-words">
              <span class="brand-title">TIC'S <span>FRIEND</span></span>
              <span class="brand-subtitle">${s.tagline}</span>
            </span>
          </a>
          <nav class="site-nav" aria-label="Main">
            ${pages.map((page, i) => `
              <a href="${page.href}" data-page="${page.key}" data-nav>
                <svg viewBox="0 0 24 24" aria-hidden="true">${ICON[page.key]}</svg>
                <span class="nav-label">${lang === "cat" ? page.ca : page.en}</span>
              </a>`).join("")}
          </nav>
          <div class="lang-switch" role="group" aria-label="${s.lang}">
            <button type="button" data-lang="cat" aria-pressed="${lang === "cat"}">CA</button>
            <button type="button" data-lang="eng" aria-pressed="${lang === "eng"}">EN</button>
          </div>
        </div>
      </header>`;
    headerHost.querySelectorAll("[data-lang]").forEach((button) => {
      button.onclick = () => App.setLang(button.dataset.lang);
    });
    footerHost.innerHTML = `
      <footer class="site-footer">
        <div class="site-footer-inner">
          <div class="footer-about">
            <span class="footer-label">${s.about}</span>
            <span class="footer-team">TIC'S FRIENDS</span>
            <ul class="footer-people">
              <li>Marc Bosch Manzano</li>
              <li>Blanca García Rodríguez</li>
              <li>Darcy Thomas Robertson</li>
              <li>Shuangjie Xia</li>
            </ul>
          </div>
          <div class="footer-logos">
            <img class="logo-cell logo-cell-a" src="/logos/upf.jpg" alt="Universitat Pompeu Fabra">
            <img class="logo-cell logo-cell-b" src="/logos/upc.png" alt="Universitat Politècnica de Catalunya">
            <img class="logo-feature" src="/logos/tic-s-friends.jpeg" alt="TIC's Friends">
            <img class="logo-cell logo-cell-c logo-wide" src="/logos/qualcomm-logo.svg" alt="Qualcomm"
                 onerror="this.onerror=null;this.src='/logos/qualcomm-logo.png'">
            <img class="logo-cell logo-cell-d logo-square" src="/logos/fme.jpg" alt="Facultat de Matemàtiques i Estadística">
          </div>
        </div>
      </footer>`;
    window.Shell.setActive(active);
  }

  window.Shell = {
    setActive(key) {
      active = key;
      document.querySelectorAll(".site-nav a").forEach((link) => {
        const on = link.dataset.page === key;
        link.classList.toggle("active", on);
        if (on) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      });
    },
  };
  render();
})();
