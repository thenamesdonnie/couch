// Move a node up to <body> so it renders at the app root, NOT nested inside
// <main> (the scrolled page container). iOS Safari animates transform
// transitions reliably for fixed elements at the root, but SNAPS them for
// fixed elements buried inside the scrolling container - the whole "theme
// sheet slides, card sheets pop" bug. The theme sheet already lives at the
// root and animates; this puts every other sheet in the same place.
//
// "Scroll behind" (dragging the dimmed backdrop scrolled the page underneath)
// is handled in CSS instead of a JS body-scroll lock: touch-action:none on the
// scrim + overscroll-behavior:contain on the sheet. The old position:fixed lock
// worked but jumped the fixed nav bar and left a grey strip in the safe area on
// iOS, so it's gone.
export function portal(node) {
  document.body.appendChild(node);
  return {
    destroy() {
      if (node.parentNode) node.parentNode.removeChild(node);
    },
  };
}
