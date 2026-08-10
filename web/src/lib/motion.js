// Motion helpers. Every animation here moves only transform and opacity, the
// two things the compositor runs off the main thread - the lesson from rota,
// where animating heights re-laid-out the list every frame and lagged. Nothing
// animates layout, box-shadow or backdrop-filter.
//
// These honour the OS "Reduce Motion" setting: moving transitions become a
// near-instant opacity change, while ambient loops are handled in app.css.
import { cubicOut } from 'svelte/easing';
import { motionDuration } from './reduced-motion.js';

// A bottom sheet sliding up. transform + opacity only.
export function sheet(node, { duration = 280 } = {}) {
  const actualDuration = motionDuration(duration);
  return {
    duration: actualDuration,
    easing: cubicOut,
    css: (t) => actualDuration === 1
      ? `opacity: ${t};`
      : `transform: translateY(${(1 - t) * 100}%); opacity: ${t};`,
  };
}

// A scrim (or anything) fading. opacity only.
export function fade(node, { duration = 200 } = {}) {
  return { duration: motionDuration(duration), css: (t) => `opacity: ${t}` };
}

// A card/list item rising a touch as it appears. transform + opacity.
export function rise(node, { duration = 260, y = 10, delay = 0 } = {}) {
  const actualDuration = motionDuration(duration);
  return {
    duration: actualDuration,
    delay,
    easing: cubicOut,
    css: (t) => actualDuration === 1
      ? `opacity: ${t};`
      : `transform: translateY(${(1 - t) * y}px); opacity: ${t};`,
  };
}
