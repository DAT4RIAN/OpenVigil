# Page Crafting — Brand-Register Implementation Layer

The **implementation** counterpart to `hero-engines.md`, exactly as `chart-crafting.md` is to `dataviz.md`. Where `hero-engines.md` decides *which engine* and `design-dna.md` lays the substrate, this file is **the hand-work in between** — the specific CSS and JS moves that separate a page a designer made from a page a model generated.

> **When to load:** any brand-register build, at the point where you stop choosing and start writing. Also load it for the `animate` / `depth` / `redesign` verbs — most "make it feel less generic" complaints are answered by one recipe in here, not by a new engine.

> **Register boundary.** Two sections here are **universal** and apply to product/dashboard work as much as to brand: **§0 (the motion gate)** and **§1.A (canvas DPR)** — a blurry chart or a dashboard that animates with no reduced-motion terminal state is broken in exactly the same way a landing page is. Everything else in this file is **brand grammar**: photographic scrims, geometric hero collages, generative layouts, exploded views, full-page engines. **Do not pour them into a dashboard** — that's `product-ui.md`'s job, and a dashboard with a Ken Burns hero is a dashboard someone has to *use* every day.

> **The one rule that makes a brand page not look cheap:** the effect is **motivated by the material**, never bolted on. A photo that fades into a card because a `mask-image` gradient dissolves it is composition. A photo with a translucent `<div>` laid over it is a sticker. The recipes below are all of the first kind — they change how the material behaves, not what sits on top of it.

---

## 0. The Motion Gate — read this before writing a single line of animation

This is §0 because it is the **most-violated rule in the corpus**. Across 71 shipped showcase pages, the authors' own audit records two systemic defects: *"Canvas 未做 DPR 适配"* and *"无 prefers-reduced-motion 完整支持 — Canvas 动画未完全停止."* Exactly one page gates motion correctly. Product-register pages don't have this problem, because `chart-crafting.md` §6 hands them a terminal-state recipe. This section is that recipe for brand.

**Read both probes once, at the top of the script. Then branch per effect.**

```js
const REDUCE = matchMedia('(prefers-reduced-motion: reduce)').matches;
const FINE   = matchMedia('(hover:hover) and (pointer:fine)').matches;
```

- **`REDUCE`** gates *everything that moves* — canvas loops, GSAP reveals, counters, marquees, the hero engine itself.
- **`FINE`** gates *everything that depends on a pointer* — magnetic buttons, cursor followers, hover-expand accordions, tilt. Without it these fire on touch devices where they can't work, and the user gets a stuck or half-applied transform.

**Every animation ships its terminal state.** The branch is not `if (!REDUCE) animate()` — that leaves the element at its *initial* (usually invisible) state. It is:

```js
if (REDUCE) el.classList.add('is-visible');       // final state, applied instantly
else gsap.to(el, { opacity: 1, y: 0, ... });      // the animation that would have reached it
```

A reveal that starts at `opacity: 0` and is gated off without a terminal state is **an invisible page**, not a calm one. This is the single most common way reduced-motion support ships broken.

**Canvas loops must actually stop.** The seductive-but-fragile version — seen in the corpus — is:

```js
if (reduce) { t = 0; frame(); cancelAnimationFrame(raf); } else frame();   // ✗ fragile
```

It happens to work only because `frame()` assigns `raf` before returning. Don't depend on statement order. Render one frame and never schedule another:

```js
function frame() {
  draw(t);
  if (!REDUCE) { t += 0.016; raf = requestAnimationFrame(frame); }   // ✓ the guard lives inside
}
frame();   // reduced-motion → draws a single composed still, then stops
```

The still frame must be **composed, not empty** — pick a `t` where the visual reads well (`t = 0` is often the degenerate flat state; `t = 2.5` may be the one that looks designed).

**CSS backstop**, always paired with the JS gates — it catches transitions you forgot:

```css
@media (prefers-reduced-motion: reduce) {
  * { animation-duration: .001ms !important; transition-duration: .001ms !important; }
}
```

**Pre-flight:** open the page with reduced-motion forced on. Every section must be **visible, composed, and readable**. If anything is blank, the gate is wrong.

---

## 1. Canvas Craft — the three moves that stop it looking like a demo

### 1.A DPR adaptation (mandatory — the corpus's other systemic defect)

An unadapted canvas is visibly soft on every retina screen. Size the buffer by DPR, keep the CSS box in CSS pixels:

```js
let W, H, DPR;
function size() {
  DPR = Math.min(2, devicePixelRatio || 1);          // cap at 2 — 3x costs 2.25x the fill rate for no visible gain
  W = c.width  = innerWidth  * DPR;
  H = c.height = innerHeight * DPR;
  c.style.width  = innerWidth  + 'px';
  c.style.height = innerHeight + 'px';
}
size();
addEventListener('resize', size);
```

Everything you draw is now in **device pixels** — so every size constant (radii, line widths, amplitudes) must be multiplied by `DPR`, and every input read from the DOM (mouse coords) must be too. Forgetting this is why a DPR-adapted canvas often looks *right but tiny*.

### 1.B Cyclic palette interpolation — color by position, not by `createLinearGradient`

When each mark needs its own color as a function of index or angle (a 72-bar spectrum ring, particles along a path), a canvas gradient can't help you — it paints a shape, not a lookup. Pre-parse the palette once, then interpolate with wraparound:

```js
const palette = ['#ffb020', '#ff5f8a', '#b355ff', '#22e5c9'];
const rgbPal  = palette.map(hex => { const n = parseInt(hex.slice(1), 16); return [n>>16 & 255, n>>8 & 255, n & 255]; });

function paletteColor(t, alpha) {                      // t is any real number; wraps
  const n = rgbPal.length;
  const f = ((t % 1) + 1) % 1 * n;                     // normalize into [0, n)
  const i = Math.floor(f) % n, j = (i + 1) % n, k = f - Math.floor(f);
  const a = rgbPal[i], b = rgbPal[j];
  return `rgba(${(a[0] + (b[0]-a[0])*k)|0},${(a[1] + (b[1]-a[1])*k)|0},${(a[2] + (b[2]-a[2])*k)|0},${alpha})`;
}
```

`paletteColor(i / BARS, .8)` now gives every bar its own hue on a **closed loop** — the last bar meets the first with no seam. This is what makes a radial spectrum read as one object rather than a gradient sliced into pieces.

> **Color-lock note:** a multi-hue canvas palette is a deliberate exception to §3's one-accent rule, and it only works when the *page chrome* stays monochrome. In the corpus this is used as an argument — a graphite/amber product page whose canvas blooms in four neons, because "the sound is colorful, the machine is grey." If you can't say that sentence about your page, use one accent.

### 1.C Gaussian amplitude envelope — give a procedural wave a focal point

A sine wave drawn at constant amplitude across the viewport reads as fake, because nothing in the physical world oscillates uniformly to its edges. Multiply the amplitude by a Gaussian centered on the focal point:

```js
for (let px = 0; px < W; px += 6 * DPR) {
  const d   = (px - cx) / (W * 0.5);                  // -1 … +1 across the canvas
  const amp = Math.exp(-d*d * 2.2) * 120 * DPR * w.scale;   // peaks at center, decays to nothing
  const y   = cy + Math.sin(px * w.freq/DPR + t * w.speed) * amp * .42
                 + Math.sin(px * w.freq*2.4/DPR - t * w.speed*1.4) * amp * .2;  // 2nd harmonic = organic
  px === 0 ? x.moveTo(px, y) : x.lineTo(px, y);
}
```

Two lessons generalize beyond waveforms: **an envelope makes procedural motion look intentional**, and **a second harmonic at a non-integer ratio and opposite drift makes it look alive**. A single sine is a screensaver.

---

## 2. Image Composition — making photography behave like design

### 2.A `mask-image` — dissolve a photo into the layout, without cutting it out

The cheapest route from a stock photo to something that reads as *art-directed* — and it needs no PNG cutout, no overlay div, no Photoshop.

```css
.card .photo {
  position: absolute; right: 0; top: 0; width: 62%; height: 100%;
  object-fit: cover;
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 42%);
          mask-image: linear-gradient(90deg, transparent, #000 42%);
}
```

The image bleeds off the card's right edge and **dissolves into the card's own background** on the left, so text can sit over the dissolved half with no scrim. Because the mask is a gradient on the *element*, it composites correctly over any background — unlike a `linear-gradient` overlay div, which has to hardcode the backdrop color and breaks the moment the card is re-themed.

Variations worth knowing:
- **Bottom fade into a section** — `mask-image: linear-gradient(180deg, #000 60%, transparent)`.
- **Vignette an image into a page** — `mask-image: radial-gradient(ellipse at center, #000 55%, transparent)`.
- **Feather a hard-edged canvas/engine** at the hero's bottom boundary so it doesn't end on a line.

Always ship the `-webkit-` prefix; Safari still needs it.

### 2.B The Photographic Hero — a scrim stack, not one black overlay

When the brief *needs* a real photo behind the headline (a venue, a stage, a hotel, a product in situ — `anti-cheap.md` calls zero imagery on an image-implied brief a bug), the failure mode is always the same: text over a busy photo, contrast failing somewhere in the frame, "fixed" by dropping a flat `rgba(0,0,0,.5)` sheet over the whole thing — which kills the photo you paid for.

A scrim **stack** darkens only where the text is, and leaves the image alone where it isn't:

```css
.hero-bg img {
  width: 100%; height: 100%; object-fit: cover;
  object-position: 50% 32%;                       /* aim the crop at the subject, not the center */
  filter: saturate(1.22) contrast(1.12) brightness(1.08);
  transform: scale(1.06);                         /* headroom for the Ken Burns drift */
}

.hero-scrim {
  position: absolute; inset: 0; z-index: 1;
  background:
    /* 1 · vertical: lift the middle, crush the bottom so the hero dissolves into the page */
    linear-gradient(180deg, rgba(8,9,10,.5) 0%, rgba(8,9,10,.2) 24%,
                            rgba(8,9,10,.4) 58%, rgba(8,9,10,.9) 90%, var(--bg) 100%),
    /* 2 · diagonal: darken the copy side only — the photo stays open on the other */
    linear-gradient(100deg, rgba(8,9,10,.88) 0%, rgba(8,9,10,.5) 32%, rgba(8,9,10,.1) 60%);
}

.hero-glow {                                       /* 3 · brand color bled into the photograph */
  position: absolute; inset: 0; z-index: 1; pointer-events: none;
  background:
    radial-gradient(60% 45% at 82% 15%, rgba(198,255,61,.14), transparent 60%),
    radial-gradient(55% 50% at  8% 90%, rgba(198,255,61,.08), transparent 65%);
}
```

Four things are doing work here, and each is worth stealing separately:

- **The diagonal scrim (`100deg`)** is the one people miss. Copy sits left; the photo's subject sits right; a *vertical-only* gradient has to darken both to protect one. The diagonal buys contrast where the text is and spends none where the image sells.
- **The bottom stop lands on `var(--bg)`, not on transparent** — the hero *becomes* the page instead of ending on a visible seam.
- **The color glow** is what stops a stock photo feeling borrowed: two low-alpha radial washes in the brand accent, and the photograph now belongs to this page's palette.
- **`object-position` is art direction.** `50% 32%` puts the subject on the upper third. Never leave a hero photo at the default center crop and hope.

Motion on top — a slow Ken Burns and a raking light sweep, both **decorative, both gated**:

```css
.hero-bg img { animation: kenBurns 26s ease-in-out infinite alternate; }
@keyframes kenBurns {
  0%   { transform: scale(1.06) translate3d(0, 0, 0) }
  100% { transform: scale(1.17) translate3d(-1.5%, -1%, 0) }
}

@media (prefers-reduced-motion: reduce) {
  .hero-bg img { animation: none; transform: scale(1.06) }   /* ← terminal state kept, not reset to 1 */
  .hero-scan   { animation: none; opacity: 0 }
}
```

Note the reduced-motion block keeps `scale(1.06)` rather than dropping to `scale(1)`. The composition was designed at 1.06; resetting to 1 re-crops the hero and shifts the subject. **A gated animation must land on the frame you designed, not on the CSS default** (§0).

**Verify contrast on the actual photo, in the actual crop** — not on the average color. WCAG AA (4.5:1 body, 3:1 large) is measured against the brightest pixel the glyph overlaps. If the headline crosses a stage light, it fails there even if it passes everywhere else. Add a text-level `text-shadow: 0 8px 60px rgba(0,0,0,.6)` as the last resort, not the first.

---

## 3. Container Queries — protect text inside an element whose width isn't the viewport's business

The case `@media` **cannot** solve: a flex accordion (filmstrip, resizable panels, hover-expand cards) where a panel's width is determined by a *sibling's* hover state, not by the viewport. At 1600px wide, a collapsed panel can be 64px. A media query sees 1600px and keeps the full label — which then clips.

```css
.panel { container-type: inline-size; }               /* each panel is its own query context */

@container (max-width: 170px) { .panel-name  { display: none } .idx-total { display: none } }
@container (max-width: 110px) { .panel-tag   { display: none } .panel-num { font-size: 17px } }
@container (max-width:  64px) { .panel-idx   { font-size: 9px } .panel-num { font-size: 14px } }
```

The expand itself is one line of CSS plus one line of JS — no width math:

```css
.panel { flex: 1 1 0; transition: flex-grow .7s cubic-bezier(.2,.8,.2,1); }
```
```js
if (FINE) panel.addEventListener('pointerenter', () => panel.style.flexGrow = 6);  // siblings stay at 1
```

**Shed content in tiers, in this order: label → tag → shrink the number.** Never let text clip, and never let it wrap to two lines inside a 64px column. Gate the hover behind `FINE` (§0) and give touch a different layout family entirely — a horizontal filmstrip becomes a vertical stack, not a squeezed filmstrip:

```css
@media (hover: none), (pointer: coarse) {
  .filmstrip { flex-direction: column; }
  .panel     { flex: 0 0 150px; }
}
```

---

## 4. Nav Contrast Over Alternating Sections — scroll-spy, not `mix-blend-mode`

A page that alternates light and dark sections (any lookbook, any editorial) breaks a fixed nav: white text vanishes on cream, ink text vanishes on charcoal.

`mix-blend-mode: difference` is the reflex, and it's **wrong here** — over mid-tone photography or a mid-grey section it produces muddy inverted color rather than clean contrast. It works on *high-contrast* backgrounds (black/white type over stark imagery, e.g. a brutal-typographic page) and nowhere else.

The controllable version — mark the dark sections, probe them on scroll, toggle a class:

```js
const nav = document.getElementById('mainNav');
const darkSections = document.querySelectorAll('.brand-statement, .collection, .footer');

function update() {
  let onDark = false;
  darkSections.forEach(s => {
    const r = s.getBoundingClientRect();
    if (r.top < 80 && r.bottom > 0) onDark = true;   // 80 ≈ nav height: is a dark band under the nav?
  });
  nav.classList.toggle('on-dark',  onDark);
  nav.classList.toggle('scrolled', scrollY > 60);
}
addEventListener('scroll', update, { passive: true });
update();                                            // fire once — deep-links and reloads land mid-page
```

```css
.nav        { color: var(--ink);   transition: color .5s ease, background .3s ease; }
.nav.on-dark{ color: var(--cream); }
```

The `transition: color .5s` is what makes it read as *designed* rather than as a flicker — the nav **fades** across the boundary instead of snapping. Pair with `{ passive: true }` so the scroll listener never blocks.

---

## 5. Scroll Choreography

### 5.A Sticky Horizontal Pin — zero dependencies

`hero-engines.md` gives the GSAP `containerAnimation` version. This is the ~30-line native one, for pages that don't otherwise need GSAP (in the corpus, the entire fashion-lookbook page ships with **no library at all**).

The trick: make the section as tall as the track's horizontal overflow, stick the viewport inside it, and map scroll progress to `translateX`.

```css
.h-section  { position: relative; }                  /* height is set in JS */
.h-viewport { position: sticky; top: 0; height: 100vh; overflow: hidden; }
.h-track    { display: flex; align-items: flex-end; gap: 40px; width: max-content; }
```

```js
function measure() {
  sectionTop  = section.getBoundingClientRect().top + scrollY;
  const overflowW = track.scrollWidth - innerWidth;
  section.style.height = (overflowW > 0 ? innerHeight + overflowW : innerHeight) + 'px';
}
measure();
addEventListener('resize', measure);
addEventListener('load',   measure);                 // fonts/images settle → scrollWidth changes

function onScroll() {
  const maxScroll = section.offsetHeight - innerHeight;
  if (maxScroll <= 0) return;                        // track fits — no pin, no transform
  const p = Math.min(Math.max((scrollY - sectionTop) / maxScroll, 0), 1);
  const overflowW = track.scrollWidth - innerWidth;

  viewport.style.transform = `translateX(${-p * overflowW}px)`;
  fill.style.transform     = `scaleX(${p})`;                            // progress bar
  counter.textContent = String(Math.min(Math.floor(p * items.length), items.length - 1) + 1)
                          .padStart(2,'0') + ' / ' + String(items.length).padStart(2,'0');
}
addEventListener('scroll', onScroll, { passive: true });
```

- **`measure()` on `load`, not just `DOMContentLoaded`** — web fonts change `scrollWidth`, and a pin measured pre-font will drift.
- **The progress bar and counter are not decoration.** A pinned section hijacks the scroll; without a visible progress signal the user doesn't know how long they're trapped. Ship them.
- **Give the track rhythm.** Uniform tiles make a horizontal rail feel like a carousel widget. Vary the item heights (`62vh / 48vh / 68vh / 54vh …`) and bottom-align them (`align-items: flex-end`) — the ragged top edge is what makes it read as a lookbook spread.
- **Reduced-motion:** don't pin. Let the track become a normal vertical stack or a native `overflow-x: auto` rail.

### 5.B Exploded View — scrub a product apart to explain it

The honest alternative to the fake-dashboard/fake-screenshot tell (`anti-cheap.md`): if the brief is a **physical or layered product** (hardware, a device, a system with components), scrub it into its parts as the user scrolls. The page teaches the object instead of asserting adjectives about it.

Declare the parts as data — each with its destination offset, rotation, and its own accent — then bind **one** timeline to a scrub:

```js
const PARTS = [
  { label: 'Optical array',  color: '#ff2d8e', x: -260, y: -130, rot: -22, scale: .92 },
  { label: 'Sensor ring',    color: '#22e3ff', x:  260, y:  -80, rot:  18, scale: .90 },
  { label: 'Bone-conduction',color: '#c6ff3a', x: -230, y:  150, rot:  14, scale: .86 },
  { label: 'Adaptive optics',color: '#8b5cf6', x:  220, y:  170, rot: -16, scale: .86 },
  { label: 'Solid-state cell',color:'#ff7a1a', x:    0, y: -250, rot:   8, scale: .80 },
];

const tl = gsap.timeline({
  scrollTrigger: { trigger: '.core-wrap', start: 'top top', end: 'bottom bottom', scrub: 1 }
});
PARTS.forEach((p, i) => {
  tl.to(shards[i], { x: p.x, y: p.y, rotation: p.rot, scale: p.scale, ease: 'none' }, 0);
  tl.to(labels[i], { opacity: 1, ease: 'none' }, .15);   // labels arrive after the parts start moving
});
```

- **All parts start at 0 on the timeline** (the third argument) so they separate *together* — staggering the explosion makes it read as a list, not as a machine coming apart.
- **`ease: 'none'` under a scrub.** The user's scroll *is* the easing curve; any other ease fights the finger.
- **A part per accent is the one licensed exception to the color lock** (§3) — a colorway/component page is *about* the parts being distinguishable. The page chrome stays monochrome; only the exploded parts carry hue.
- **Labels are the point.** An exploded view with no callouts is a screensaver. Fade each label in slightly after its part starts moving.

### 5.C Colorway Pin + Snap — a discrete stepper, not a smear

For a finite set of variants (colorways, editions, plans), pin the section and snap between whole panels so the user always lands *on* one:

```js
gsap.to(track, {
  y: () => -(panels - 1) * innerHeight, ease: 'none',
  scrollTrigger: {
    trigger: '.colorways', pin: true, scrub: 1, invalidateOnRefresh: true,
    end: () => '+=' + (panels - 1) * innerHeight,
    snap: { snapTo: 1 / (panels - 1), duration: .4, ease: 'power1.inOut' },   // ← lands on a panel, never between
    onUpdate: self => {
      const idx = Math.round(self.progress * (panels - 1));
      dots.forEach((d, i) => d.classList.toggle('on', i === idx));            // dots are the state readout
    }
  }
});
```

**The reduced-motion branch removes the pin entirely** — this is the pattern to copy for *any* pinned section:

```js
if (REDUCE) {
  sticky.style.position = 'static';    // un-pin
  sticky.style.height   = 'auto';      // let the panels stack and flow
  return;                              // never build the ScrollTrigger at all
}
```

Disabling the *animation* while leaving the pin in place produces a section that traps the scroll and never advances. **Un-pin, don't un-animate.** `invalidateOnRefresh: true` is required or the `innerHeight` math goes stale on resize / device rotation.

---

## 6. `clip-path: inset()` Wipe — a reveal with more material than fade-up

`opacity: 0 → 1` + `translateY` is the default reveal, and it is fine, and it is everywhere. A curtain wipe costs the same and reads as film rather than as a web page:

```css
.card           { clip-path: inset(0 0 100% 0); transition: clip-path 1.1s cubic-bezier(.16,1,.3,1); }
.card.revealed  { clip-path: inset(0 0 0% 0); }

.card:nth-child(2) { transition-delay: .2s }         /* stagger in CSS — no JS timeline needed */
.card:nth-child(3) { transition-delay: .4s }
```

```js
new IntersectionObserver((es, o) => es.forEach(e => {
  if (!e.isIntersecting) return;
  e.target.classList.add('revealed');
  o.unobserve(e.target);                              // reveal once; never re-hide on scroll-up
}), { threshold: .2 }).observe(card);
```

`cubic-bezier(.16, 1, .3, 1)` is the *expo-out* curve — it starts fast and settles slowly, which is what makes a wipe feel like weight rather than like a progress bar. Under `REDUCE`, add `.revealed` immediately (§0).

The stagger lives in CSS, so the whole effect is one observer and two rules. Reach for a GSAP timeline only when the stagger needs to be data-driven.

---

## 7. Hand-Written FLIP — a lightbox that grows out of its thumbnail

FLIP (First · Last · Invert · Play) without the GSAP Flip plugin. The thumbnail's on-screen rect is the *first* frame; the target rect is the *last*; you play the inverse.

```js
function openLightbox(srcEl) {
  const first = srcEl.getBoundingClientRect();        // F
  const last  = targetRectFor(srcEl);                 // L — where the big frame will land

  frame.style.transformOrigin = 'top left';
  gsap.fromTo(frame,
    { x: first.left - last.left,                      // I — invert: pretend it's still the thumbnail
      y: first.top  - last.top,
      scaleX: first.width  / last.width,
      scaleY: first.height / last.height },
    { x: 0, y: 0, scaleX: 1, scaleY: 1,               // P — play to identity
      duration: .62, ease: 'power3.inOut' });
}
```

- **`transform-origin: top left`** is not optional — the rect math is corner-based, and a centered origin will make the frame drift.
- **Animate `transform` only.** Never animate `width`/`height`/`top`/`left`: that's layout on every frame, and it will jank.
- **Recompute on `resize`** — a cached `baseRect` is stale the moment the viewport changes.
- **Non-uniform scale (`scaleX ≠ scaleY`) distorts the image mid-flight.** Accept it for a short duration (it reads as a whip), or letterbox the target to the source's aspect ratio if the distortion is visible.
- **Reduced-motion:** skip the FLIP, fade the lightbox in.

Ship the keyboard contract with it: `Esc` closes, `←`/`→` navigate, focus is trapped in the frame and restored to the thumbnail on close. A lightbox without it is a trap for keyboard users.

---

## 8. Generative Layout — let an algorithm compose the grid

The strongest answer to "identical card grids" (`anti-cheap.md`'s headline offender) is a layout **no one placed by hand**. A recursive guillotine split subdivides a rectangle into `n` non-overlapping leaves — every load is a new composition, and none of them are a 3-column grid.

```js
function generateLayout(n) {
  const MIN_W = 16, MIN_H = 15;                       // hard floor, in % — no slivers
  let rects = [{ x:0, y:0, w:100, h:100 }];

  while (rects.length < n) {
    rects.sort((a, b) => (b.w * b.h) - (a.w * a.h));  // bias toward splitting the biggest
    const r = rects.shift();

    const canV = r.w >= MIN_W * 2, canH = r.h >= MIN_H * 2;
    if (!canV && !canH) { rects.push(r); break; }     // nothing splittable within the floor

    // wide rects prefer a vertical cut, tall ones horizontal — but not deterministically
    const preferV = r.w > r.h ? Math.random() < .72 : Math.random() < .28;
    const vertical = canV && (preferV || !canH);

    const minRatio = vertical ? MIN_W / r.w : MIN_H / r.h;
    const ratio    = minRatio + Math.random() * (1 - 2 * minRatio);   // never closer than the floor

    if (vertical) {
      const w1 = r.w * ratio;
      rects.push({ ...r, w: w1 }, { ...r, x: r.x + w1, w: r.w - w1 });
    } else {
      const h1 = r.h * ratio;
      rects.push({ ...r, h: h1 }, { ...r, y: r.y + h1, h: r.h - h1 });
    }
  }
  return rects;                                       // → position: absolute; left/top/width/height in %
}
```

The two constraints are what make it *design* rather than noise:
- **`MIN_W`/`MIN_H` floor** — without it the recursion produces unusable slivers. The floor is set by the smallest thing that must fit (a caption bar, a plate number).
- **Aspect-aware split preference** (`.72 / .28`) — cutting a wide rect vertically keeps children near-square. Split purely at random and everything drifts toward extreme ratios.

Generate **lazily, per section, on `IntersectionObserver`** — don't compute six walls at load. Offer a visible `RECOMPOSE` control if the algorithm is part of the story; the honesty of "this was computed, watch" is the whole point. Below ~720px, **abandon it** for a vertical stack — a guillotine split of a phone screen is just a column with extra steps.

---

## 9. CSS-Only Geometric Composition — a hero with no image, no canvas, no 3D

The sixth `hero-engines.md` Engine-E route, and the highest soul-per-byte in the whole corpus: a Bauhaus/constructivist collage assembled from primitives. Zero assets, zero libraries, and it cannot look like anyone else's page because you composed it.

Every shape is `position: absolute` with **percentage** offsets inside an `aspect-ratio` box, so the entire composition scales as one unit:

```css
.geo   { position: relative; aspect-ratio: 1/.94; width: 100%; max-width: 560px; }
.shape { position: absolute; transform-origin: center; }

.tri        { clip-path: polygon(50% 0, 100% 100%, 0 100%); }         /* triangle */
.tri-1      { top: 4%;  left: 0;   width: 24%; aspect-ratio: 1; background: var(--orange) }
.half-pill  { right: 0; top: 2%;   width: 36%; height: 94%;
              border-radius: 999px 0 0 999px; background: var(--purple) }   /* half capsule */
.disc       { bottom: 2%; left: 44%; width: 26%; aspect-ratio: 1;
              border-radius: 50%; background: var(--teal) }
.ring       { bottom: -2%; left: -1%; width: 20%; aspect-ratio: 1;
              border-radius: 50%; border: 11px solid var(--ink); background: transparent }
.dotgrid    { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16% }
.dotgrid span { border-radius: 50%; aspect-ratio: 1; background: var(--ink) }
```

The vocabulary is small and complete: **triangle** (`clip-path`), **half-capsule** (one-sided `border-radius: 999px`), **disc**, **ring** (`border`, transparent fill), **dot grid** (nested `grid`), **quarter-pinwheel** (four `clip-path: polygon(50% 50%, …)` in a rounded square).

Motion, in two layers — and **the parameters must be de-synced or it reads as plastic**:

```js
gsap.from('.shape', { scale: .6, opacity: 0, duration: .9,
                      ease: 'back.out(1.6)', stagger: { each: .06, from: 'random' } });

shapes.forEach((el, i) => {                           // idle float — every shape on its own clock
  gsap.to(el, { y: `+=${6 + (i % 3) * 4}`,
                duration: 2.4 + (i % 4) * .3,         // 2.4 / 2.7 / 3.0 / 3.3s — never one period
                repeat: -1, yoyo: true, ease: 'sine.inOut' });
});
```

Derive per-shape parameters from the index (`i % 3`, `i % 4`) so nothing shares a period. Shapes breathing in unison is the exact tell you're trying to avoid. Add pointer parallax by depth tier (`depth = 10 + (i % 4) * 6`) behind the `FINE` gate, and kill both loops under `REDUCE`.

---

## 10. Engine Scope — hero-only, or the whole page?

`hero-engines.md` mandates *one* engine. It does not say the engine has to stay in the hero. There is a second, legitimate scope:

**Full-page fixed engine + per-section scrims.** The canvas is `position: fixed; inset: 0; z-index: 0` and runs the entire scroll. Each content section then sits on a translucent scrim of the page background, dimming the engine to whatever that section needs:

```css
#engine     { position: fixed; inset: 0; z-index: 0 }
.content    { position: relative; z-index: 5 }

.hero       { background: transparent }                         /* engine at 100% */
.manifesto  { background: linear-gradient(180deg, rgba(7,6,10,.40), rgba(7,6,10,.86) 40%) }  /* the fade band */
.specs      { background: rgba(7,6,10,.86) }                    /* engine reduced to texture */
.band       { background: rgba(7,6,10,.90) }
.cta        { background: rgba(7,6,10,.55) }                    /* let it breathe back in */
```

The **fade band** on the first section after the hero is what sells it — a hard `rgba(bg,.86)` edge directly under a full-strength hero reads as a mistake. Gradient from transparent to the scrim value across the section's top 40%.

Use this when the engine *is* the argument (a neural network, a field, a fluid) and the copy is talking about it. Use hero-only when the engine is an entrance and the page then gets on with its job. **Never** run an unscrimmed engine behind body copy — that's a contrast failure, not a design choice.

Cost is real: a full-page engine renders for the whole session. Keep the particle count low enough that it holds 60fps *while* the user scrolls, and freeze it to a still under `REDUCE` (§0).

---

## 11. Procedural 3D That Means Something — the Fibonacci → KNN → traversal recipe

The default Three.js particle sphere is `Math.random()` points in a ball, drifting. It looks like every other one. This recipe produces a structure that reads as a *network* — nodes, real edges, and signals travelling along them — and every step has a reason.

**1 · Distribute nodes evenly** with the Fibonacci sphere (no clustering at the poles, unlike naive spherical rand):

```js
const y     = 1 - (i / (N - 1)) * 2;                  // 1 → -1
const r     = Math.sqrt(Math.max(0, 1 - y*y));
const theta = Math.PI * (3 - Math.sqrt(5)) * i;       // the golden angle
```

**2 · Break the perfect sphere.** A geometrically perfect shell is itself an AI tell. Perturb each radius deterministically:

```js
const noise = .6 + hash(i) * .55 + Math.sin(i * .7) * .12;
nodes.push(new THREE.Vector3(Math.cos(theta)*r, y, Math.sin(theta)*r).multiplyScalar(noise * 3.4));
```

**3 · Build edges by K-nearest-neighbour** (K = 3). Brute-force O(N²) is fine up to ~500 nodes and runs once. De-dupe with a `Set` keyed on `min(i,j):max(i,j)` — otherwise every edge is drawn twice. → one `THREE.LineSegments`, dim.

**4 · Send signals along the edges.** This is the step that turns decoration into meaning: pick a random edge, `lerp` a point from one end to the other, and pulse its brightness with `sin(π·t)` so it eases in and out instead of popping.

```js
const p = new THREE.Vector3().lerpVectors(edge.a, edge.b, t);
const brightness = Math.sin(Math.PI * t);             // 0 → 1 → 0 over the traversal
```

Keep a **fixed pool** of ~26 travellers in one `BufferGeometry` with `DynamicDrawUsage` position/color attributes, recycling a slot when its `t` passes 1. Never allocate geometry per particle per frame.

**5 · Depth cues:** a far starfield (~2 600 points) plus `FogExp2` so the network has a *back*. Without fog, a 3D point cloud renders flat.

The soft round sprite is generated, not loaded — `createRadialGradient` on a small 2D canvas → `CanvasTexture`, ~4 stops. No texture file, no request.

---

## 12. Pre-Flight Additions for Brand Pages

On top of `preflight.md`:

- [ ] Reduced-motion forced on → **every section visible and composed**, canvas shows a designed still, no blank reveals (§0).
- [ ] Touch device → no stuck hover states; hover-dependent layouts have a **different layout family**, not a squeezed one (§0, §3).
- [ ] Canvas buffer is DPR-scaled and every drawing constant is multiplied by `DPR` (§1.A).
- [ ] Fixed nav is legible over **every** section it crosses — verified by scrolling, not by assumption (§4).
- [ ] Pinned horizontal sections show progress (bar or counter) and release cleanly at both ends (§5).
- [ ] No layout family appears more than twice; if the page has a card grid, ask whether §8 or a list-row/asymmetric-grid should replace it.
- [ ] Every reveal has a terminal state that is reachable **without** the animation running.
