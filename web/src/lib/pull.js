// Pull-to-refresh on the page scroller. Only transform moves (compositor), and
// it engages only at the very top pulling down, so normal scrolling and the
// bottom rubber-band are untouched. Touch only - desktop never sees it.
const THRESHOLD = 72;
const MAX = 120;

export function pullToRefresh(node, opts = {}) {
  let startY = 0;
  let dist = 0;
  let active = false;
  let refreshing = false;

  const atTop = () => (document.scrollingElement?.scrollTop ?? window.scrollY) <= 0;
  const damp = (d) => Math.min(d * 0.5, MAX);

  function start(e) {
    if (refreshing || !atTop()) return;
    // Don't hijack gestures that begin on an interactive surface (the remote's
    // touch pad, the Screen viewport) - those own their own vertical drags.
    if (e.target.closest?.('[data-nopull]')) return;
    startY = e.touches[0].clientY;
    active = true;
  }

  function move(e) {
    if (!active) return;
    const dy = e.touches[0].clientY - startY;
    if (dy <= 0 || !atTop()) { reset(); return; }
    e.preventDefault(); // take over the top overscroll while pulling
    dist = damp(dy);
    node.style.transform = `translateY(${dist}px)`;
    opts.onPull?.(dist / THRESHOLD);
  }

  async function end() {
    if (!active) return;
    active = false;
    if (dist >= THRESHOLD) {
      refreshing = true;
      opts.onRefresh?.(true);
      node.style.transition = 'transform 0.24s ease';
      node.style.transform = 'translateY(52px)';
      try { await Promise.resolve(opts.refresh?.()); } catch { /* ignore */ }
      await new Promise((r) => setTimeout(r, 550)); // let the spinner read
    }
    settle();
  }

  function settle() {
    node.style.transition = 'transform 0.28s ease';
    node.style.transform = 'translateY(0)';
    dist = 0;
    refreshing = false;
    opts.onRefresh?.(false);
    opts.onPull?.(0);
    // Clear the transform entirely once it settles. Leaving even translateY(0)
    // makes <main> a containing block for the fixed popup sheets inside it, so
    // they'd anchor to the scrolled page instead of the viewport (off-screen).
    setTimeout(() => { node.style.transition = ''; node.style.transform = ''; }, 300);
  }

  function reset() {
    active = false;
    if (dist) settle();
  }

  node.addEventListener('touchstart', start, { passive: true });
  node.addEventListener('touchmove', move, { passive: false });
  node.addEventListener('touchend', end);
  node.addEventListener('touchcancel', reset);

  return {
    destroy() {
      node.removeEventListener('touchstart', start);
      node.removeEventListener('touchmove', move);
      node.removeEventListener('touchend', end);
      node.removeEventListener('touchcancel', reset);
    },
  };
}
