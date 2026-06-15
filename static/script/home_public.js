(function () {
  const toggle = document.getElementById("home-nav-toggle");
  const nav = document.getElementById("home-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  const segmentRoot = document.querySelector("[data-home-segment]");
  if (!segmentRoot) return;

  const tabs = segmentRoot.querySelectorAll('[role="tab"]');
  const panels = segmentRoot.querySelectorAll('[role="tabpanel"]');

  const ativar = (id) => {
    tabs.forEach((tab) => {
      const on = tab.getAttribute("data-segment") === id;
      tab.setAttribute("aria-selected", on ? "true" : "false");
      tab.classList.toggle("is-active", on);
    });
    panels.forEach((panel) => {
      const on = panel.getAttribute("data-segment-panel") === id;
      panel.hidden = !on;
    });
    if (history.replaceState) {
      history.replaceState(null, "", `#comecar-${id}`);
    }
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => ativar(tab.getAttribute("data-segment")));
  });

  document.querySelectorAll("[data-segment-go]").forEach((el) => {
    el.addEventListener("click", (e) => {
      const id = el.getAttribute("data-segment-go");
      if (!id) return;
      e.preventDefault();
      ativar(id);
      segmentRoot.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  const hash = (location.hash || "").replace("#comecar-", "");
  if (hash === "vendedor" || hash === "fornecedor") {
    ativar(hash);
  }
})();
