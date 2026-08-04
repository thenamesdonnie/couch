<script>
  // A placeholder block that pulses opacity (compositor-only) while real content
  // loads, holding the exact layout so nothing shifts when it arrives.
  let { w = '100%', h = '1em', r = '8px', poster = false } = $props();
</script>

<span class="sk" class:poster style:width={w} style:height={poster ? 'auto' : h} style:border-radius={r}></span>

<style>
  .sk {
    display: block;
    background: var(--raise);
    animation: pulse 1.4s ease-in-out infinite;
  }
  .sk.poster { aspect-ratio: 2 / 3; width: 100%; }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.45; }
  }
  @media (prefers-reduced-motion: reduce) {
    .sk { animation: none; opacity: 0.7; }
  }
</style>
