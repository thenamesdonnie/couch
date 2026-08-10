// Slide-down-to-dismiss for bottom sheets. iOS-style rules: a clearly
// vertical downward pull grabs the sheet ONLY when the scrollable area under
// the finger is at the top of its scroll (otherwise the pull is just
// scrolling); past a threshold on release it dismisses, else it springs back.
//
// Dismissal hands off to the component's out:slideDown transition: the drag
// records how far the sheet already travelled in node.dataset.dragY and calls
// onClose, and slideDown (anim.js) picks the ride up from there - no jump.
// touch-action must be PRE-set correctly (iOS ignores changes mid-gesture):
// keep it matched to whether the element can actually scroll right now, so an
// underfilled list never grants the browser a vertical pan that chains to the
// page behind the sheet. Re-evaluated on resize and content changes.
import { motionDuration } from './reduced-motion.js';
export function panYIfScrollable(node) {
  const apply = () => {
    node.style.touchAction = node.scrollHeight > node.clientHeight + 1 ? 'pan-y' : 'none';
  };
  apply();
  const ro = new ResizeObserver(apply);
  ro.observe(node);
  const mo = new MutationObserver(apply);
  mo.observe(node, { childList: true, subtree: true });
  return { destroy() { ro.disconnect(); mo.disconnect(); } };
}

export function dragDismiss(node, { onClose }) {
  let startX = 0;
  let startY = 0;
  let dy = 0;
  let mode = null; // null = undecided, 'drag' = ours, 'ignore' = native scroll
  let scroller = null;
  let raf = 0;

  // Buttery-follow rules: the transform write happens at most once per display
  // frame (rAF), not once per touch event, and the sheet is promoted to its
  // own compositor layer (will-change) the moment the drag starts, so iOS
  // moves an already-rasterised layer instead of repainting mid-gesture.
  function applyFrame() {
    raf = 0;
    node.style.transform = `translateY(${dy}px)`;
  }

  // The nearest scrollable (in the given axis) between the touch and the
  // sheet root, or the root itself. null = nothing here scrolls that way.
  function findScroller(el, horizontal = false) {
    while (el && el !== node) {
      const room = horizontal
        ? el.scrollWidth > el.clientWidth + 1
        : el.scrollHeight > el.clientHeight + 1;
      if (room) {
        const o = getComputedStyle(el)[horizontal ? 'overflowX' : 'overflowY'];
        if (o === 'auto' || o === 'scroll') return el;
      }
      el = el.parentElement;
    }
    if (!horizontal && node.scrollHeight > node.clientHeight + 1) return node;
    return null;
  }

  let startTarget = null;

  function onStart(e) {
    if (e.touches.length !== 1) return;
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    dy = 0;
    mode = null;
    startTarget = e.target;
    scroller = findScroller(e.target);
  }

  function onMove(e) {
    const t = e.touches[0];
    const moveX = t.clientX - startX;
    const moveY = t.clientY - startY;
    if (mode === null) {
      if (Math.abs(moveX) < 8 && Math.abs(moveY) < 8) return; // not yet a gesture
      if (moveY > Math.abs(moveX) && (!scroller || scroller.scrollTop <= 0)) {
        mode = 'drag';
        node.style.transition = '';
        node.style.willChange = 'transform';
      } else if (Math.abs(moveX) > Math.abs(moveY)) {
        // horizontal: hands off only if something here scrolls horizontally
        // (season pills row); otherwise consume so nothing behind moves.
        mode = findScroller(startTarget, true) ? 'ignore' : 'block';
      } else {
        // vertical with no dismissal claim: native only if a scroller exists,
        // else consume it - an underfilled episode list must not pan the page.
        mode = scroller ? 'ignore' : 'block';
      }
    }
    if (mode === 'block') { e.preventDefault(); return; }
    if (mode !== 'drag') return;
    dy = Math.max(0, t.clientY - startY);
    e.preventDefault(); // ours now - no scroll, no rubber-band
    if (!raf) raf = requestAnimationFrame(applyFrame);
  }

  function onEnd() {
    if (mode !== 'drag') return;
    mode = null;
    if (raf) { cancelAnimationFrame(raf); raf = 0; }
    node.style.transform = `translateY(${dy}px)`; // land on the final position
    if (dy > 110) {
      node.dataset.dragY = String((dy / node.offsetHeight) * 100);
      onClose();
    } else if (dy > 0) {
      const duration = motionDuration(250);
      node.style.transition = `transform ${duration}ms cubic-bezier(0.22, 1, 0.36, 1)`;
      node.style.transform = '';
      setTimeout(() => { node.style.transition = ''; node.style.willChange = ''; }, duration + 10);
    } else {
      node.style.willChange = '';
    }
  }

  node.addEventListener('touchstart', onStart, { passive: true });
  node.addEventListener('touchmove', onMove, { passive: false });
  node.addEventListener('touchend', onEnd);
  node.addEventListener('touchcancel', onEnd);
  return {
    destroy() {
      node.removeEventListener('touchstart', onStart);
      node.removeEventListener('touchmove', onMove);
      node.removeEventListener('touchend', onEnd);
      node.removeEventListener('touchcancel', onEnd);
    },
  };
}
