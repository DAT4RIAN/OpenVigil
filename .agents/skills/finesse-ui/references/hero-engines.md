# Hero Engines — The One Spectacular Moment

> **When loaded by a command** (you're iterating, not building from scratch):
> - **`bolder`** — current SPECTACLE is too low. Raise it +2 and step the engine UP one tier (CSS-only → GSAP → Canvas → Three.js/FBO). Add the new engine; keep everything else.
> - **`quieter`** — current SPECTACLE is too high / janky. Lower it −2 and step the engine DOWN (Three.js → GSAP → CSS-only). Simplify or remove; don't rebuild the page.
> - **`animate`** — SPECTACLE is fine; the motion isn't. Add or swap the engine in isolation, motion only. Don't touch palette / layout / copy.
> In all three: change **one** thing, keep the §3 substrate and the soul intact, then re-run the §1.B "spectacle shown" check and reduced-motion fallback. Full build (`craft`) reads the whole file instead.

A finesse page earns its name with **one** technically-ambitious visual engine, done at 100%, usually behind or inside the hero. Pick by soul + SPECTACLE dial. Every skeleton below is vanilla-JS-first (single-file showcase pages), with notes for framework stacks.

**Universal rules for every engine:**
- Mount on a `position: fixed; inset: 0; z-index: 0` canvas; content sits at `z-index: 5+`.
- Progressive enhancement: the page is complete and readable with the engine deleted.
- Animate only `transform`/`opacity` for DOM; for canvas, cap work to hold 60fps.
- `prefers-reduced-motion`: stop the loop on a still frame (or hide + show static hero).
- DPR-adapt every canvas: `canvas.width = innerWidth * devicePixelRatio` (else retina = blurry).
- **Loading libs:** small single-file libs (GSAP core + ScrollTrigger, ~113KB) → **self-host** in `./lib/` and commit; heavy libs with an import tree (Three.js) → **versioned CDN import map**, lazy-loaded. Never reference a `./lib/x.js` with no file behind it. Full recipe in `3d-effects.md` §2.0.

---

## Engine A — Three.js + GLSL (3D depth, particles, bloom)

Use for: astronomy, AI/neural, crypto networks, DNA/science, metaball fluids. Gate on `SPECTACLE ≥ 7`. Lazy-load `three` (~150KB gz).

```js
import * as THREE from 'three';

const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
// Color pipeline — the #1 "why does my WebGL look flat/washed" fix. Three lines, always on.
renderer.outputColorSpace = THREE.SRGBColorSpace;         // r152+ default, but set it explicitly
renderer.toneMapping = THREE.ACESFilmicToneMapping;       // filmic rolloff — lit scenes stop clipping to grey
renderer.toneMappingExposure = 1.0;                        // dial 0.8–1.3 to taste

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(60, innerWidth / innerHeight, 0.1, 2000);
camera.position.z = 600;

// 22k-particle galaxy via BufferGeometry + ShaderMaterial
const COUNT = 22000;
const pos = new Float32Array(COUNT * 3);
for (let i = 0; i < COUNT; i++) {
  const r = Math.pow(Math.random(), 0.6) * 700, a = Math.random() * Math.PI * 2;
  pos[i*3] = Math.cos(a) * r; pos[i*3+1] = (Math.random()-0.5) * 80; pos[i*3+2] = Math.sin(a) * r;
}
const geo = new THREE.BufferGeometry();
geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
const mat = new THREE.ShaderMaterial({
  uniforms: { uTime: { value: 0 }, uColor: { value: new THREE.Color('#5fd4ff') } },
  transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  vertexShader: `uniform float uTime; void main(){ vec3 p=position;
    float a=uTime*0.05; mat2 R=mat2(cos(a),-sin(a),sin(a),cos(a)); p.xz=R*p.xz;
    vec4 mv=modelViewMatrix*vec4(p,1.0); gl_PointSize=2.0*(300.0/-mv.z); gl_Position=projectionMatrix*mv; }`,
  fragmentShader: `uniform vec3 uColor; void main(){ float d=length(gl_PointCoord-0.5);
    if(d>0.5) discard; gl_FragColor=vec4(uColor, 1.0-d*2.0); }`,
});
scene.add(new THREE.Points(geo, mat));

const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
function loop(t) { mat.uniforms.uTime.value = t * 0.001; renderer.render(scene, camera); if (!reduce) requestAnimationFrame(loop); }
requestAnimationFrame(loop);
addEventListener('resize', () => { camera.aspect = innerWidth/innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); });
```
Scroll-couple it (optional): drive `camera.position.z` or `scene.rotation.y` from a GSAP ScrollTrigger `scrub`.

**Bloom — the glow that turns "a field of dots" into an expensive-looking scene.** `AdditiveBlending` alone gives you additive dots; bloom is what makes them *bleed light*. This is the step the engine's name has always promised. Add it only for genuinely luminous souls (galaxies, neural nets, crypto meshes) — bloom on a lit product scene just smears it.

```js
// lazy-loaded alongside `three` — all three addons share the pinned version
const { EffectComposer } = await import('three/addons/postprocessing/EffectComposer.js');
const { RenderPass }     = await import('three/addons/postprocessing/RenderPass.js');
const { UnrealBloomPass }= await import('three/addons/postprocessing/UnrealBloomPass.js');

const composer = new EffectComposer(renderer);
composer.setPixelRatio(Math.min(devicePixelRatio, 2));
composer.addPass(new RenderPass(scene, camera));
composer.addPass(new UnrealBloomPass(
  new THREE.Vector2(innerWidth, innerHeight),
  0.8,   // strength — 0.6–1.1 premium; >1.5 reads as a cheap blur
  0.4,   // radius
  0.85)); // threshold — only the brightest pixels bloom; lower = everything glows = mud
// loop: composer.render() REPLACES renderer.render(scene, camera)
// resize: also composer.setSize(innerWidth, innerHeight)
```
- **GSAP is untouched.** Scroll-scrub still mutates `camera`/uniforms exactly as before — bloom only changes the final render call. The one rule: if the scene is scroll-driven, the scrub `onUpdate` (and the rAF loop) must call `composer.render()`, never the bare `renderer.render()`, or the pass is skipped.
- Keep the DPR cap on the composer too — bloom is a fullscreen multi-pass blur and doubles cheaply into jank at retina resolution.
- Reduced-motion still freezes on one composed frame — render the composer **once**, then stop the loop.

> For a **rendered 3D object** (GLTF product viewer, image-displacement plane) rather than a particle field, see `3d-effects.md` §2 — same Three.js setup, depth-specific recipes.

---

## Engine B — Canvas 2D (particles, fields, real-time data)

Use for: music waveforms, quant K-lines, fire/embers, aurora, flow fields, matrix rain. Light, no deps.

```js
const canvas = document.getElementById('c'), ctx = canvas.getContext('2d');
let W, H, DPR = Math.min(devicePixelRatio, 2);
function resize(){ W=innerWidth; H=innerHeight; canvas.width=W*DPR; canvas.height=H*DPR; ctx.setTransform(DPR,0,0,DPR,0,0); }
resize(); addEventListener('resize', resize);

const N = 180, P = Array.from({length:N}, () => ({ x:Math.random()*W, y:H+Math.random()*H, vy:0.4+Math.random(), r:Math.random()*2+0.5, life:Math.random() }));
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
function frame(){
  ctx.fillStyle = 'rgba(7,4,2,0.18)'; ctx.fillRect(0,0,W,H);     // trail fade, not full clear
  for (const p of P){
    p.y -= p.vy; p.x += Math.sin(p.y*0.02)*0.4; p.life -= 0.004;
    if (p.y < -10 || p.life <= 0){ p.y=H+10; p.x=Math.random()*W; p.life=1; }
    const hue = 15 + p.life*30;                                   // ember red→amber over life
    ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
    ctx.fillStyle = `hsla(${hue},90%,${50+p.life*20}%,${p.life})`;
    ctx.shadowBlur = 12; ctx.shadowColor = `hsl(${hue},90%,55%)`; ctx.fill();
  }
  if (!reduce) requestAnimationFrame(frame);
}
frame();
```
Real-time data variant (K-lines, waveforms): keep a ring buffer, scroll left each frame, recompute the visible min/max for an auto-fitting price scale.

---

## Engine C — WebGL FBO shader (fluid, reaction-diffusion, ray-march)

Use for: fluid dynamics (Navier-Stokes), Gray-Scott Turing patterns, ray-marched SDF scenes, thin-film iridescence. Heavy, GPU-bound, one fullscreen quad. Gate on `SPECTACLE ≥ 8` and only when the soul is genuinely about emergence/physics.

Structure (vanilla WebGL or a thin lib like `regl`/`OGL`):
1. Two float framebuffers (ping-pong): `read` / `write`.
2. **Simulation pass** — fragment shader reads `read`, advects/diffuses/solves, draws into `write`. Swap.
3. **Display pass** — map the final state to color, draw to screen.
4. Mouse injects a "source" (dye/velocity) into the sim each frame.

```glsl
// fragment — advection step (Navier-Stokes dye transport)
uniform sampler2D uState; uniform vec2 uTexel; uniform float uDt, uDissipation;
varying vec2 vUv;
void main(){
  vec2 vel = texture2D(uState, vUv).xy;
  vec2 src = vUv - vel * uDt * uTexel;       // trace back
  gl_FragColor = texture2D(uState, src) * uDissipation;
}
```
Discipline: this is the easiest engine to ship as jank. Profile it; if it dips below 50fps on a mid device, halve the FBO resolution. Always provide a static gradient fallback poster for reduced-motion.

---

## Engine D — GSAP ScrollTrigger (scroll-pinned story, the workhorse)

Use for: scroll-driven narrative, horizontal pan galleries, parallax, reveal stagger. The single most reusable engine; works for nearly every soul at `SPECTACLE 4–7`.

**Reveal stagger** (lightest — prefer this before reaching for pins):
```js
gsap.registerPlugin(ScrollTrigger);
gsap.utils.toArray('.reveal').forEach((el, i) => {
  gsap.from(el, { opacity: 0, y: 34, duration: 0.7, ease: 'power3.out',
    scrollTrigger: { trigger: el, start: 'top 80%', once: true } });
});
```

**Horizontal pan** (pin the wrapper, scrub the track):
```js
const track = document.querySelector('.otrack');
const distance = track.scrollWidth - innerWidth;
gsap.to(track, { x: -distance, ease: 'none',
  scrollTrigger: { trigger: '.pan-wrap', start: 'top top', end: () => `+=${distance}`,
    pin: true, scrub: 1, invalidateOnRefresh: true } });
```

**Sticky-stack** (cards pin and shrink as the next arrives): pin every card except the last at `start: 'top top'`, drive each card's `scale/opacity` from the NEXT card's scrub trigger.

Critical failures to avoid: `start: 'top center'` instead of `'top top'` (fires mid-scroll, looks broken); forgetting `invalidateOnRefresh` (breaks on resize); no `ScrollTrigger.getAll().forEach(t=>t.kill())` cleanup in SPAs.

> Framework note (React/Next): wrap in `useGSAP()` / `gsap.context()` and `ctx.revert()` on unmount. For simple "enter on scroll," prefer Motion's `whileInView` over GSAP — lighter, no plugin. Gate all of it on `useReducedMotion()`.

---

## Engine E — CSS-only (mask, 3D transform, variable font, scroll-timeline)

Use for: dual-layer mouse mask (reveal a second image), CSS 3D cube, variable-font weight/width morph, native scroll-driven animation. Free, best perf, no JS libs. Often the *most* memorable because it's rare.

> Reusable, **component-level** CSS 3D — pointer-tilt cards, flip cards, coverflow, depth-parallax layers — lives in `3d-effects.md` §1 (the `depth` command). This section is the full-bleed hero variant; that one is the in-page, drop-into-a-grid variant.

**Dual-layer mouse mask** (the showcase STUDIO move):
```css
.layer-night { position:absolute; inset:0; background:url(reveal.jpg) center/cover;
  -webkit-mask: radial-gradient(circle 200px at -400px -400px, #000 40%, transparent 72%);
          mask: radial-gradient(circle 200px at -400px -400px, #000 40%, transparent 72%);
  will-change: mask; }
```
```js
addEventListener('pointermove', e => {
  const m = `radial-gradient(circle 220px at ${e.clientX}px ${e.clientY}px, #000 40%, transparent 72%)`;
  night.style.mask = m; night.style.webkitMask = m;
});
```

**Native scroll-driven** (no JS, Chrome/Safari; degrade gracefully elsewhere):
```css
@keyframes rise { from { opacity:0; transform:translateY(40px) } to { opacity:1; transform:none } }
.reveal { animation: rise linear both; animation-timeline: view(); animation-range: entry 0% cover 35%; }
```

**Variable-font morph:** animate `font-variation-settings: 'wght' …, 'wdth' …` on scroll or hover for kinetic typography (needs a variable font like Roboto Flex / Barlow).

**Geometric composition** — the fifth E route, and the one that most reliably produces a page that looks like *nobody else's*. A constructivist/Bauhaus collage built from CSS primitives: `clip-path` triangles, one-sided `border-radius: 999px 0 0 999px` half-capsules, `border`-only rings, nested-grid dot fields, four-`clip-path` pinwheels. Percentage offsets inside an `aspect-ratio` box so the whole composition scales as one unit. Zero assets, zero libraries, and **it cannot look generic because you composed it by hand** — there is no default to fall back to. Full recipe, including the de-synced idle-float parameters that keep it from reading as plastic: `page-crafting.md` §9.

> **Engine E is the highest soul-per-byte tier, not the consolation prize.** `bolder` steps *up* from it by reflex — but a hand-composed geometric hero at SPECTACLE 4 beats a stock particle field at SPECTACLE 7 on every axis that matters. Step up when the brief needs *physics* (fluid, depth, a real 3D object). Don't step up just to look busy.

---

## Engine Scope — hero-only, or full-page?

Orthogonal to *which* engine: **where does it run?** The one-engine rule constrains the count, not the extent, and both scopes are legitimate.

- **Hero-only (the default).** The engine is an entrance. It occupies the first viewport, the page then gets on with its job. Cheapest, safest, and correct whenever the engine is *atmosphere* rather than *argument*.
- **Full-page fixed + per-section scrims.** The canvas is `position: fixed; inset: 0; z-index: 0` and runs the whole scroll; each section sits on a translucent scrim of the page background (`rgba(bg, .55–.90)`), dimming the engine to whatever that section needs. Use it when the engine **is the argument** — the copy is *about* the network, the fluid, the field — so hiding it after 100vh would be throwing away the thesis.

The move that makes the second one work is the **fade band**: the first section below the hero gradients from transparent to the scrim value across its top ~40%, instead of butting a flat scrim against a full-strength hero. Recipe in `page-crafting.md` §10.

Non-negotiable either way: **never run an unscrimmed engine behind body copy.** That's a contrast failure wearing a design decision's clothes. And a full-page engine renders for the entire session — keep the particle count low enough to hold 60fps *while scrolling*, and freeze it to a composed still under `prefers-reduced-motion`.

---

## Extended Motion Vocabulary — Secondary Flourishes (not hero engines)

The five engines above (§ above) are for the **one** full-bleed hero moment. These are smaller, cheap GSAP/CSS techniques for elsewhere on the page — a broader reveal/parallax vocabulary beyond Engine D's basics. They are normal page motion, not a second "hero" — use them freely across a page without violating the one-engine rule. Each still needs a motivated reason and a `prefers-reduced-motion` fallback (§ Engine discipline in SKILL.md §4).

**Split-char / split-word reveal** — wrap each glyph (or word) of a heading in a masked span, animate it up into place with a stagger, instead of fading the whole line at once. A hallmark "premium agency site" heading move; reserve for a handful of key headlines (hero, section leads), not every `<h2>` on the page.
```js
function splitChars(el) {
  Array.from(el.childNodes).forEach((node) => {
    if (node.nodeType === 3) {
      const frag = document.createDocumentFragment();
      [...node.textContent].forEach((ch) => {
        const outer = document.createElement('span'); outer.className = 'char';
        const inner = document.createElement('span'); inner.className = 'char-inner';
        inner.textContent = ch === ' ' ? ' ' : ch;
        outer.appendChild(inner);
        frag.appendChild(outer);
      });
      node.replaceWith(frag);
    } else if (node.nodeType === 1 && node.tagName !== 'BR') {
      splitChars(node); // recurse so a nested span (e.g. a differently-styled second line) splits too
    }
  });
}
```
```css
.char { display:inline-block; overflow:hidden; vertical-align:top; }
.char-inner { display:inline-block; will-change:transform; }
```
```js
gsap.fromTo(headingEl.querySelectorAll('.char-inner'),
  { yPercent: 130, rotate: 6 },
  { yPercent: 0, rotate: 0, duration: .9, ease: 'power4.out', stagger: 0.016,
    scrollTrigger: { trigger: headingEl, start: 'top 85%', once: true } });
```
Split by **character**, not word — most CJK headings have no whitespace to split on, and character-by-character reads well for Latin type too. For a hero heading visible on load, skip `scrollTrigger` and just play the tween with a short delay after paint instead.

**Magnetic buttons** — a CTA nudges a few px toward the cursor within its own bounds, springs back on pointer-leave. Small and cheap; reserve for 1-2 primary CTAs per page, not every link (it stops reading as deliberate craft once it's on everything).
```js
const moveX = gsap.quickTo(btn, 'x', { duration: .5, ease: 'power3.out' });
const moveY = gsap.quickTo(btn, 'y', { duration: .5, ease: 'power3.out' });
btn.addEventListener('pointermove', (e) => {
  const r = btn.getBoundingClientRect();
  moveX((e.clientX - r.left - r.width / 2) * 0.35);
  moveY((e.clientY - r.top - r.height / 2) * 0.35);
});
btn.addEventListener('pointerleave', () => { moveX(0); moveY(0); });
```
Skip entirely under `prefers-reduced-motion` — this is pure flourish with no content cost if absent.

**Curtain-wipe reveal** — a solid panel scales away (`scaleX`/`scaleY` from 1→0, `transformOrigin` at one edge) to reveal the content underneath, scrubbed to scroll position. Good for a comparison or before/after beat ("here's what's behind this"); don't reach for it as a decorative default on ordinary sections.
```css
.wipe { position:absolute; inset:0; z-index:2; background:var(--bg); pointer-events:none; transform-origin:right center; }
```
```js
gsap.fromTo(wipeEl, { scaleX: 1 }, { scaleX: 0, ease: 'none', transformOrigin: 'right center',
  scrollTrigger: { trigger: sectionEl, start: 'top 65%', end: 'top 15%', scrub: true } });
```

**Scan-line sweep** — a thin glowing bar sweeps across a data/chart block as the user scrolls through it, tying a "measurement" motif to a stats or results section.
```js
gsap.fromTo(scanLineEl, { left: '0%' }, { left: '100%', ease: 'none',
  scrollTrigger: { trigger: chartWrapEl, start: 'top 85%', end: 'bottom 55%', scrub: true } });
```

**Per-card fly-in inside a horizontal-pin track** — the Horizontal pan pattern above moves the *whole* track; to also animate individual cards in as they slide into view, point GSAP's `containerAnimation` option at the pin tween so each card gets its own ScrollTrigger scrubbed by horizontal position instead of vertical scroll:
```js
const panTween = gsap.to(track, { x: () => -getDistance(), ease: 'none',
  scrollTrigger: { trigger: wrapEl, start: 'top top', end: () => `+=${getDistance()}`, pin: true, scrub: 1 } });
gsap.utils.toArray('.card').forEach((card) => {
  gsap.fromTo(card, { autoAlpha: 0, y: 90, scale: .9 }, { autoAlpha: 1, y: 0, scale: 1,
    scrollTrigger: { containerAnimation: panTween.scrollTrigger.animation,
      trigger: card, start: 'left 92%', end: 'left 55%', scrub: 0.6 } });
});
```

---

## Brand Technique: Inline Typography Images

A high-soul brand move: embed a small image or short video clip directly inside a headline as a visual punctuation mark. Removes the need for a separate image row; the image becomes part of the typographic rhythm.

```html
<h1 class="inline-headline">
  Where
  <span class="inline-img" aria-hidden="true">
    <img src="your-image.jpg" alt="" />
  </span>
  craft meets code
</h1>
```

```css
.inline-img {
  display: inline-block;
  vertical-align: middle;
  width: clamp(60px, 8vw, 140px);
  height: .85em;               /* match the cap height, not the line-height */
  border-radius: 999px;
  overflow: hidden;
  position: relative;
  top: -.05em;                 /* optical lift to align with cap line */
}
.inline-img img { width: 100%; height: 100%; object-fit: cover; }
```

**Rules:**
- Gate on `SOUL ≥ 8` — it's a strong personality statement; wrong at lower soul values.
- Image must be a narrow portrait crop or square — wide landscape crops break the text rhythm.
- Font must be at display size (`clamp(56px, 9vw, 140px)+`); the technique collapses at body sizes.
- Best for: agency heroes, portfolio headlines, editorial product announcements, fashion/culture pages.
- Provide `@media (prefers-reduced-motion: reduce)` — freeze any video variant to a still frame.

---

## Framework Integration Checklist

When embedding a hero engine inside a component framework, follow these rules to prevent memory leaks, stale animations, and broken reduced-motion gates.

### React / Next.js

```js
// GSAP — wrap in useGSAP() so cleanup is automatic on unmount
import { useGSAP } from '@gsap/react';
useGSAP(() => {
  gsap.from('.hero-text', { opacity: 0, y: 40, duration: 1, ease: 'power3.out' });
  ScrollTrigger.create({ trigger: '.section', start: 'top 80%', onEnter: () => {} });
  // ctx.revert() is called automatically on unmount — all ScrollTriggers killed
}, { scope: containerRef });

// Three.js — lazy-import to keep initial bundle light
useEffect(() => {
  let renderer, rafId;
  import('three').then(THREE => {
    renderer = new THREE.WebGLRenderer({ canvas: canvasRef.current, alpha: true });
    // ... setup scene, camera, loop
    const loop = () => { rafId = requestAnimationFrame(loop); renderer.render(scene, camera); };
    loop();
  });
  return () => { cancelAnimationFrame(rafId); renderer?.dispose(); };
}, []);

// Reduced motion gate (run before starting any loop)
const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
if (prefersReduced) { /* freeze to still frame, skip requestAnimationFrame */ }
```

### Vue 3

```js
import { onMounted, onUnmounted } from 'vue';
let renderer, rafId;

onMounted(() => {
  // setup Three.js / Canvas here
  rafId = requestAnimationFrame(loop);
});

onUnmounted(() => {
  cancelAnimationFrame(rafId);
  renderer?.dispose();
  ScrollTrigger.getAll().forEach(t => t.kill()); // if using GSAP
});
```

### Svelte

```js
import { onMount, onDestroy } from 'svelte';
let rafId;

onMount(() => {
  // setup engine
  rafId = requestAnimationFrame(loop);
});

onDestroy(() => {
  cancelAnimationFrame(rafId);
  // dispose renderer if Three.js was used
});
```

### Common pitfalls (all frameworks)

- Missing `ScrollTrigger.getAll().forEach(t => t.kill())` on unmount causes phantom scroll triggers that fire on other pages in SPAs.
- Missing `renderer.dispose()` on Three.js WebGLRenderer leaks GPU memory — one of the most common performance bugs.
- `window.addEventListener('scroll', ...)` driving animation on every scroll event is a frame-rate killer — use `ScrollTrigger`, `IntersectionObserver`, or CSS `animation-timeline: view()` instead.
- Never start a canvas loop without gating on `prefers-reduced-motion` first. Freeze, don't skip.

---

## Choosing fast

| Soul / SPECTACLE | Engine |
|---|---|
| 3D depth, particles, "cosmic" · 7–10 | A (Three.js) |
| live data, fields, fire, neon · 5–8 | B (Canvas 2D) |
| physics/emergence/fluid · 8–10 | C (WebGL FBO) |
| narrative scroll, gallery, editorial · 4–7 | D (GSAP) |
| interactive reveal, kinetic type, max-perf · 3–6 | E (CSS-only) |

When unsure, **D or E**. They cover most briefs at the lowest risk and never jank.
