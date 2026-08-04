// Motion helpers. Every animation here moves only transform and opacity, the
// two things the compositor runs off the main thread - the lesson from rota,
// where animating heights re-laid-out the list every frame and lagged. Nothing
// animates layout, box-shadow or backdrop-filter.
//
// These run regardless of the OS "Reduce Motion" setting: Donnie asked for the
// sheet animations explicitly even though his phone has Reduce Motion on. Only
// the looping/ambient animations (skeleton pulse, spinner) still respect it.
import { cubicOut } from 'svelte/easing';

// A bottom sheet sliding up. transform + opacity only.
export function sheet(node, { duration = 280 } = {}) {
  return {
    duration,
    easing: cubicOut,
    css: (t) => `transform: translateY(${(1 - t) * 100}%); opacity: ${t};`,
  };
}

// A scrim (or anything) fading. opacity only.
export function fade(node, { duration = 200 } = {}) {
  return { duration, css: (t) => `opacity: ${t}` };
}

// A card/list item rising a touch as it appears. transform + opacity.
export function rise(node, { duration = 260, y = 10, delay = 0 } = {}) {
  return {
    duration,
    delay,
    easing: cubicOut,
    css: (t) => `transform: translateY(${(1 - t) * y}px); opacity: ${t};`,
  };
}
