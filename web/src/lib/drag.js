// Slide-down-to-dismiss for bottom sheets. iOS-style rules: a clearly
// vertical downward pull grabs the sheet ONLY when the scrollable area under
// the finger is at the top of its scroll (otherwise the pull is just
// scrolling); past a threshold on release it dismisses, else it springs back.
//
// Dismissal hands off to the component's out:slideDown transition: the drag
// records how far the sheet already travelled in node.dataset.dragY and calls
// onClose, and slideDown (anim.js) picks the ride up from there - no jump.
export function dragDismiss(node, { onClose }) {
  let startX = 0;
  let startY = 0;
  let dy = 0;
  let mode = null; // null = undecided, 'drag' = ours, 'ignore' = native scroll
  let scroller = null;

  // The nearest scrollable between the touch and the sheet root (or the root
  // itself, for sheets that scroll whole). null = nothing scrollable here.
  function findScroller(el) {
    while (el && el !== node) {
      if (el.scrollHeight > el.clientHeight + 1) {
        const oy = getComputedStyle(el).overflowY;
        if (oy === 'auto' || oy === 'scroll') return el;
      }
      el = el.parentElement;
    }
    return node.scrollHeight > node.clientHeight + 1 ? node : null;
  }

  function onStart(e) {
    if (e.touches.length !== 1) return;
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    dy = 0;
    mode = null;
    scroller = findScroller(e.target);
  }

  function onMove(e) {
    const t = e.touches[0];
    const moveX = t.clientX - startX;
    const moveY = t.clientY - startY;
    if (mode === null) {
      if (Math.abs(moveX) < 8 && Math.abs(moveY) < 8) return; // not yet a gesture
      mode = (moveY > Math.abs(moveX) && (!scroller || scroller.scrollTop <= 0))
        ? 'drag' : 'ignore';
    }
    if (mode !== 'drag') return;
    dy = Math.max(0, t.clientY - startY);
    e.preventDefault(); // ours now - no scroll, no rubber-band
    node.style.transition = '';
    node.style.transform = `translateY(${dy}px)`;
  }

  function onEnd() {
    if (mode !== 'drag') return;
    mode = null;
    if (dy > 110) {
      node.dataset.dragY = String((dy / node.offsetHeight) * 100);
      onClose();
    } else if (dy > 0) {
      node.style.transition = 'transform 0.25s cubic-bezier(0.22, 1, 0.36, 1)';
      node.style.transform = '';
      setTimeout(() => { node.style.transition = ''; }, 260);
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
