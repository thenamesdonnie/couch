// Entrance animation, the iOS-reliable way: set the START state inline, let it
// paint ONE frame, THEN add the transition and flip to the END state. A CSS
// `animation:` on a just-inserted element frequently doesn't fire on iOS Safari
// (every keyframe attempt "popped" for Donnie); a transition triggered a frame
// AFTER insertion does. And it animates OPACITY, which his phone provably
// animates (the loading skeletons), with a small transform slide on top.
//
// The real fix for "theme sheet slides, card sheets pop" lives in portal.js:
// iOS snaps transform transitions on fixed elements nested inside the scrolled
// page container, so every sheet is portalled up to <body> first. freezeOverflow
// is kept as belt-and-braces: a sheet that is its own scroll container
// (overflow:auto) can also have its transform ignored, so we pin it to hidden
// for the length of the slide and hand scrolling back when it ends.
function run(node, from, to, dur, opts = {}) {
  if (opts.freezeOverflow) node.style.overflow = 'hidden';
  for (const k in from) node.style[k] = from[k];
  node.style.willChange = Object.keys(to).join(', ');
  requestAnimationFrame(() => requestAnimationFrame(() => {
    node.style.transition = Object.keys(to)
      .map((k) => `${k.replace(/[A-Z]/g, (m) => '-' + m.toLowerCase())} ${dur}`)
      .join(', ');
    for (const k in to) node.style[k] = to[k];
  }));
  // transitionend BUBBLES - a child fading in (e.g. a poster image via
  // use:fadeimg) would otherwise fire this and rip out the slide before it
  // plays. Only clean up on our own transition ending.
  const onEnd = (e) => {
    if (e.target !== node) return;
    node.removeEventListener('transitionend', onEnd);
    node.style.transition = '';
    node.style.willChange = '';
    if (opts.freezeOverflow) node.style.overflow = '';
    for (const k in to) node.style[k] = '';
  };
  node.addEventListener('transitionend', onEnd);
}

// A true bottom-sheet entrance: the sheet starts fully below the bottom edge
// (translateY 100% of its own height) and rides up to rest. The scrim's fadeIn
// dims the backdrop; the sheet itself stays opaque, the way an iOS sheet does.
export function slideUp(node) {
  run(node,
    { transform: 'translateY(100%)' },
    { transform: 'translateY(0)' },
    '0.34s cubic-bezier(0.22, 1, 0.36, 1)',
    { freezeOverflow: true });
}

export function fadeIn(node) {
  run(node, { opacity: '0' }, { opacity: '1' }, '0.22s ease');
}

// Exit animations are Svelte `out:` transitions (JS-driven per frame, so they
// run reliably on iOS and Svelte holds the unmount until they finish). The
// entrance stays on the use:slideUp/use:fadeIn actions above - proven working -
// and these only add the dismissal: the sheet rides back down, the scrim fades.
import { cubicOut } from 'svelte/easing';

export function slideDown(node) {
  // A drag-dismiss (lib/drag.js) records how far the sheet already travelled;
  // ride out from there rather than snapping back to the top first.
  const from = Math.min(parseFloat(node.dataset.dragY || '0') || 0, 100);
  delete node.dataset.dragY;
  return {
    duration: 280 * (1 - from / 100),
    easing: cubicOut,
    tick: (t) => {
      node.style.overflow = 'hidden';
      node.style.transform = `translateY(${from + (1 - t) * (100 - from)}%)`;
    },
  };
}

export function fadeOut(node) {
  return {
    duration: 260,
    easing: cubicOut,
    tick: (t) => { node.style.opacity = `${t}`; },
  };
}
