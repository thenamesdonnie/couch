// Fade an image in once it has decoded, so posters resolve smoothly instead of
// popping in. The element reserves its space via aspect-ratio already, so this
// only touches opacity - no layout shift, compositor-friendly.
export function fadeimg(node) {
  node.style.opacity = '0';
  node.style.transition = 'opacity 0.28s ease';
  const show = () => { node.style.opacity = '1'; };
  if (node.complete && node.naturalWidth) show();
  else {
    node.addEventListener('load', show, { once: true });
    node.addEventListener('error', show, { once: true });
  }
  return { destroy() { node.removeEventListener('load', show); } };
}

// Warm the browser cache for a list of image urls, so they are already decoded
// by the time their tab is opened. Fire and forget; failures are ignored.
const warmed = new Set();
export function preload(urls) {
  for (const url of urls) {
    if (!url || warmed.has(url)) continue;
    warmed.add(url);
    const img = new Image();
    img.decoding = 'async';
    img.src = url;
  }
}

// Await a set of images being fully loaded AND decoded, so a sheet can hold
// until its poster/backdrop are ready and open complete instead of popping
// them in. Resolves on a timeout regardless, so a slow image never blocks the
// open indefinitely.
export function decodeImages(urls, timeoutMs = 700) {
  const jobs = urls.filter(Boolean).map(
    (url) =>
      new Promise((resolve) => {
        const img = new Image();
        img.decoding = 'async';
        img.onload = resolve;
        img.onerror = resolve;
        img.src = url;
        if (img.decode) img.decode().then(resolve, () => {});
      }),
  );
  return Promise.race([
    Promise.all(jobs),
    new Promise((resolve) => setTimeout(resolve, timeoutMs)),
  ]);
}
