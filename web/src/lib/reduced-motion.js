import { readable } from 'svelte/store';

// Keep the operating-system preference live while the remote is open.
export const reducedMotion = readable(false, (set) => {
  if (typeof window === 'undefined') return undefined;
  const query = window.matchMedia('(prefers-reduced-motion: reduce)');
  const update = () => set(query.matches);
  update();
  query.addEventListener('change', update);
  return () => query.removeEventListener('change', update);
});

export function motionDuration(duration) {
  if (typeof window === 'undefined') return duration;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 1 : duration;
}
