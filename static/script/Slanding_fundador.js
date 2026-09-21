(function () {
  "use strict";
  const el = document.getElementById("ff-count-restantes");
  if (!el) return;
  const target = Number(el.textContent || 0);
  if (!Number.isFinite(target) || target < 0) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  let n = 0;
  const steps = Math.max(12, Math.min(28, target * 2 || 12));
  const tick = () => {
    n += 1;
    const v = Math.round((target * n) / steps);
    el.textContent = String(Math.min(target, v));
    if (n < steps) requestAnimationFrame(tick);
  };
  el.textContent = "0";
  requestAnimationFrame(tick);
})();
