(function () {
  const btn = document.getElementById("pub-menu-btn");
  const nav = document.getElementById("pub-nav");
  if (!btn || !nav) return;
  btn.addEventListener("click", () => {
    const open = nav.classList.toggle("is-open");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  });
})();
