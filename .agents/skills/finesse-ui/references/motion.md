# Motion — Routes, Not One Engine

> **When loaded by the `animate` command** (you're adding or re-cutting motion on a page that already stands): change the **beats**, not the soul or the substrate. Re-run §0's gate and §4's budget, then check the page still reads with every animation stripped. A full build (`craft`) reads this whenever the brief mentions motion, "炫酷", "动效", or the page is `brand` register.

Motion decisions have **two axes**, and conflating them is why AI pages all move the same way:

| Axis | The question | Where it's answered |
|---|---|---|
| **EFFECT** — what the viewer sees | 长廊？粒子？逐字？重排？ | §2, the catalogue |
| **ROUTE** — how it's built | CSS？原生滚动？GSAP？WebGL？ | §1, the six routes |

**The same effect can run on three different routes at wildly different cost.** "Elements arrive as you scroll" is four lines of CSS or 60KB of GSAP — identical output, 60KB apart. A page that reaches for the heavy route every time isn't more capable, it's more expensive and slower, and it will still look like everyone else's.

> **The failure this file exists to prevent.** Ask an AI for 「一个好看炫酷有动效的首页」 and you get a WebGL particle hero with fade-up sections beneath it — every time, from every model. Not because it's right, but because it's the effect with the most complete recipe in reach. **Range is the fix**: many effects, many routes, and a rotation that makes repeats visible.

---

## 0. THE GATE — run before writing a single keyframe

Four checks. All mandatory, all cheap, and the last two are where pages actually die.

1. **Motivated.** Every beat needs a one-sentence reason: hierarchy, comprehension, feedback, state, or identity. 「它看起来很酷」 is not a reason. Write the sentence; if you can't, cut the beat.
2. **Survives removal.** Strip every animation — the page must be readable, complete and navigable. Motion is enhancement, never structure. A page whose content only appears after a scroll trigger is broken, not animated.
3. **Has a terminal state.** `prefers-reduced-motion: reduce` is not "turn it off". It's **a composed still** — the frame you'd have picked as the screenshot. Design it at the same time as the beat, not after (§1's route table gives each route's still form).
4. **60fps or simplify.** Animate `transform` and `opacity`. Everything else (`width`, `top`, `filter`, `box-shadow`) recomposites — measure before shipping it. Below ~50fps on a mid-range device: cut count, cut resolution, or cut the beat.

```js
// The probe pattern — read once at the top, branch per effect.
const RM   = matchMedia('(prefers-reduced-motion: reduce)').matches;
const FINE = matchMedia('(hover: hover) and (pointer: fine)').matches;
// if (RM) → set final state;  else → animate
// Gate pointer-driven effects behind FINE so they never fire on touch.
```
```css
/* CSS backstop — always ship alongside the JS branch, never instead of it */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
}
```

> **The backstop is a floor, not a fallback.** It stops motion; it does not compose a still. A hero whose content is `opacity: 0` until an animation runs will be *permanently invisible* under the backstop. Every animated element must be authored in its **final** state and animated *from* elsewhere, or given an explicit reduced-motion terminal rule.

---

## 1. THE SIX ROUTES

| Route | Weight | Owns | Still form under reduced-motion | Dies by |
|---|---|---|---|---|
| **R1 · CSS transition / keyframes** | 0 | state change, micro-interaction, entrance, ambient loop | the end state, already authored | trying to sequence — no timeline, no scrub, `animation-delay` chains are unmaintainable |
| **R2 · Native scroll-driven** (`animation-timeline`) | 0 | parallax, progress, per-item arrival, sticky reveal | the mid-progress frame | no `pin`, no cross-element orchestration; needs a graceful no-support path |
| **R3 · View Transitions + WAAPI** | 0 | list add/remove, filter re-sort, route change, expand/collapse | instant swap, no tween | the un-transitioned fallback is forgotten, so old browsers get a hard flash |
| **R4 · GSAP + ScrollTrigger** | ~60KB | pinned narrative, horizontal track, scrub, `containerAnimation` | `scrollTrigger` killed, tweens set to end | used for work R1/R2 do free — the single most common over-reach |
| **R5 · Canvas / WebGL / GLSL** | 100–160KB | particles, fields, fluid, material, post-processing | one rendered frame, then stop the loop | DOM is gone: text unselectable, images unindexable, nothing lazy-loads |
| **R6 · Zero-dep CSS 3D space** | 0 | a camera moving through a scene of DOM panels | camera parked at its best composition | painter's algorithm — see §5 |

**Route selection order.** Start at R1 and stop at the first route that can do the job. Every step down costs weight, and no viewer has ever thanked a page for its bundle size. The one legitimate reason to skip ahead: the effect genuinely requires what only that route has (`pin` → R4; per-pixel material → R5).

**R5's real cost isn't KB, it's the DOM.** Once content becomes a texture it stops being content — unselectable, unindexable, unreadable to a screen reader, no `loading="lazy"`. **When the "3D" thing is photographs and text, R6 beats R5** even though R5 is the more powerful renderer. Reach for R5 when the subject is a *material* (fluid, smoke, iridescence, a rendered object), not when it's a gallery.

---

## 2. THE EFFECT CATALOGUE — ten families

**Pick a family from the brief's content, not from what looks impressive.** Each family lists its variants (the rotation pool), its default route, and — the important column — **its slop form**, the version that's been shipped so many times it now reads as an AI tell.

### 2.1 Spatial · camera moves through a scene
*The viewer is inside something and it moves around them.*

| Variant | Shape | Camera |
|---|---|---|
| 长廊 corridor | linear along −Z, walls both sides, recycled | walks forward forever |
| 星球 sphere | panels on the inside of a sphere, latitude rings | starts at the centre, pulls out through the shell |
| 圆环 orbit | single ring, items facing inward | drag to spin, inertia |
| 隧道 tunnel | cylinder wall, dense | dives through, banking |
| 螺旋 helix | spiral staircase of panels | descends and rotates |
| 书架 shelf-wall | flat grid on one plane | pans laterally, dollies to a pick |
| 蜂巢 hive | hex packing on a curved surface | slow orbit, cell lights on focus |
| 井 shaft | vertical well | rises, items pass at eye level |

**Default route: R6.** SPECTACLE 7–9. Needs 12+ items of real content to justify itself.
**Slop form:** an infinite tunnel of glowing wireframe hexagons in WebGL. It carries nothing — no content lives on those walls.
**Dies by:** panel overlap at similar depth → painter's algorithm flips the order → flicker (§5).

### 2.2 Particle · field
*Many small things obeying one rule.*
Variants: 星云 nebula · 网络图 node graph · DNA helix · 流场 flow field · 磁力线 field lines · 噪声漂移 noise drift · 文字聚散 text-form particles · 星轨 star trails.
**Default route: R5 (Canvas 2D for 2D fields, Three.js for depth).** SPECTACLE 6–9.
**Slop form:** the connected-dot constellation with lines drawn between neighbours, cursor repelling them. This one specific effect is the single most-shipped AI hero on the web.
**Dies by:** DPR not handled → blurry on retina; particle count tuned on a dev machine → 20fps on a laptop.

### 2.3 Fluid · material
*A surface with physics or optics.*
Variants: Navier-Stokes 流体 · 反应扩散 · 虹彩/油膜 · 熔融金属 · 墨水扩散 · 波纹 · 光线步进 SDF · 玻璃折射.
**Default route: R5 (WebGL FBO, multi-pass).** SPECTACLE 8–10, and it must be the *only* effect on the page.
**Slop form:** the purple-to-cyan animated mesh gradient blob. It says "AI startup" and nothing else.
**Dies by:** running full-resolution multi-pass on a phone; no still frame authored, so reduced-motion gets a black rectangle.

### 2.4 Scroll narrative
*Scroll position drives a story rather than just position.*
Variants: 章节 pin + 换幕 · 横向轨 horizontal track · 缩放推进 zoom-through · 图层剥离 layer peel · 序列帧 image sequence · 进度轨 progress rail · 文字接力 baton text.
**Default route: R2 for single-element arrival and parallax; R4 the moment you need `pin` or cross-element scrub.** SPECTACLE 5–8.
**Slop form:** every section fades up 24px on entry, forever, all the way down the page. It's not motion design, it's a default.
**Dies by:** hijacking scroll velocity — users lose their place and leave. Never retime the scroll itself; drive animations *from* it.

### 2.5 Typographic
*The type is the moving thing.*
Variants: 逐字揭开 split-char reveal · 可变字重波 weight wave · 大字遮罩 masked display · 字距呼吸 tracking breath · 跑马灯 marquee · 数字滚动 odometer · 换词 word cycler · 描边转填充 outline-to-fill.
**Default route: R1 (+ R2 for scroll-linked, R4 only for staggered scrub).** SPECTACLE 4–7. Cheapest real craft on this list.
**Slop form:** the typewriter effect on a headline, cursor blinking.
**Dies by:** splitting every `<h2>` on the page — the move stops reading as deliberate at the third one. Reserve for 1–3 headlines. **CJK splits by character, not word** — there's no whitespace to split on.

### 2.6 Image transform
*The photographs themselves are the effect.*
Variants: 位移扭曲 displacement · 遮罩溶解 mask dissolve · 拼贴重排 tile shuffle · 裁切滑移 crop slide · 色彩分离 channel split · 双图对比 compare wipe · 缩略图展开 thumb-to-full · 视差裁切 parallax crop.
**Default route: R1/R2 for masks and crops (`clip-path`, `mask-image` animate free); R5 only for true per-pixel displacement.** SPECTACLE 5–8.
**Slop form:** every image greyscale until hover, then colour.
**Dies by:** applying it to images that aren't good enough to deserve it. This family amplifies the source material in both directions.

### 2.7 Geometric construction
*Something assembles itself out of primitives.*
Variants: SVG 描边绘制 stroke draw · 图元拼装 primitive assembly · 网格坍缩 grid collapse · 等距堆叠 isometric stack · 分形展开 fractal unfold · 线框成形 wireframe build · 图表自绘 chart draw-in.
**Default route: R1 + SVG (`stroke-dashoffset`, `clip-path`); R2 to scrub it to scroll.** SPECTACLE 4–7.
**Slop form:** a rotating wireframe globe with arcs between cities.
**Dies by:** nothing — this family is the most under-used one here and the safest place to spend a beat. `stroke-dashoffset` draw-in costs four lines and reads as real craft.

### 2.8 Physics · inertia
*Motion that has weight and overshoot.*
Variants: 磁吸 magnetic pull · 弹簧回弹 spring settle · 拖拽甩动 drag & fling · 平滑惯性 smooth inertia · 卡片堆叠 card deck · 摆动 pendulum · 橡皮筋 rubber-band bounds.
**Default route: R1 with a spring-shaped `cubic-bezier`; R4 (`quickTo`) when it must track a pointer every frame.** SPECTACLE 3–6.
**Slop form:** a custom cursor — a dot with a laggy ring chasing it.
**Dies by:** shipping on touch (gate behind `FINE`), or applying to every link until it reads as jitter rather than as weight.

### 2.9 State transition
*Something changed, and the change is legible.*
Variants: 列表增删 list add/remove · 筛选重排 filter re-sort · 路由切换 route change · 展开塌陷 expand/collapse · 排序动画 sort · 标签页滑动 tab slide · 骨架到内容 skeleton-to-content · 乐观更新 optimistic commit.
**Default route: R3.** SPECTACLE 2–5.
**Slop form:** none — this family is chronically *absent*, which is its own failure.
**Dies by:** never being built. **This is the only motion family that belongs in `product` register**, and it's where a dashboard stops feeling like a page refresh. `product-ui.md` pages should have R3 and nothing else.

### 2.10 Atmosphere
*Not an event — a condition the page is in.*
Variants: 颗粒 grain · 扫描线 scanlines · 辉光 bloom/glow pulse · 渐晕 vignette breath · 光标跟随光源 cursor light · 呼吸背景 ambient drift · 噪声叠层 noise overlay · 色温漂移 temperature drift.
**Default route: R1 (+ one inline SVG `feTurbulence` for grain — see the recipe below).** SPECTACLE 2–5.
**Slop form:** a full-screen animated gradient mesh behind everything.
**Dies by:** animating the grain (expensive, and it reads as noise-on-noise). **Freeze grain, animate nothing in this layer above 0.06 opacity.**

```css
/* Grain — the one atmosphere primitive worth memorising. Zero assets, zero JS. */
body::before {
  content: ''; position: fixed; inset: 0; z-index: 999; pointer-events: none;
  opacity: .04; mix-blend-mode: overlay; background-size: 180px 180px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}
```

---

## 3. EFFECT → ROUTE — the lookup

Read the brief's phrasing in the left column; take the **cheapest** route that satisfies it.

| What the brief asks for | R1 | R2 | R3 | R4 | R5 | R6 | Take |
|---|:-:|:-:|:-:|:-:|:-:|:-:|---|
| 往下滚，元素依次归位 | ○ | **●** | | ○ | | | R2 — four lines, zero JS |
| 首屏进来的入场动画 | **●** | | | ○ | | | R1 + stagger delay |
| 视差 / 远近层次 | | **●** | | ○ | ○ | ○ | R2 |
| 滚动时钉住一屏讲故事 | | | | **●** | | | R4 — only route with `pin` |
| 横向滚动的作品轨 | | ○ | | **●** | | | R4 (`containerAnimation` for per-card) |
| 筛选后卡片自己重排 | | | **●** | ○ | | | R3 — `view-transition-name` + 4 lines |
| 列表增删有动画 | ○ | | **●** | | | | R3 |
| 卡片跟着鼠标倾斜 | **●** | | | ○ | | | R1 (`3d-effects.md` §1.B) |
| 标题逐字出现 | **●** | ○ | | ○ | | | R1; R4 only if scrubbed |
| 数字滚动到位 | **●** | | ○ | | | | R1 or a 10-line WAAPI counter |
| 图片划过去像水波散开 | | | | | **●** | | R5 — genuine per-pixel work |
| 图片遮罩溶解 / 裁切滑移 | **●** | ○ | | | | | R1 — `clip-path` animates free |
| 粒子 / 星云 / 网络图 | | | | | **●** | | R5 |
| 流体 / 材质 / 光线步进 | | | | | **●** | | R5, and nothing else on the page |
| 走进去 / 穿过去 / 沉浸 | | ○ | | | ○ | **●** | R6 when it carries photos or text |
| 一个可旋转的产品模型 | | | | | **●** | | R5 (GLTF viewer) |
| SVG 线条自己画出来 | **●** | ○ | | | | | R1 — `stroke-dashoffset` |
| 页面之间切换有过渡 | | | **●** | | | | R3 — cross-document View Transitions |
| 颗粒 / 扫描线 / 氛围 | **●** | | | | | | R1 |

● = take this · ○ = also possible, costs more

**Two rules that fall out of this table.** A brief that lands on R1/R2/R3 rows only → **the page ships zero JS libraries**, and that is a better page, not a lesser one. A brief that lands on R5 → that's your one heavy beat; everything else on the page drops to R1/R2/R3.

---

## 4. COMPOSITION — a page is a few beats, not one engine

The old model was "one hero engine, done at 100%." That's still true *for the heavy routes* — but it left the rest of the page with no motion vocabulary at all, which is why AI pages have a spectacular hero and generic fade-ups beneath it.

**The model is a beat sheet.** Four beats, each from a **different** family, each on the cheapest route that does it:

```
首屏    what greets them                 → the page's one signature effect
滚动    what rewards moving down         → usually R2, cheap
交互    what responds to them            → R1 or R3, small
收尾    what closes it                   → R1, quiet
静止版  what all of it becomes under reduced-motion
```

**Budget, and it is a hard ceiling:**

| | Limit | Why |
|---|---|---|
| Heavy beats (R4/R5/R6) | **1** per page | Two spectacles compete and both lose. This is the old one-engine rule, preserved. |
| Total beats | **4**, five with a reason | Past this it reads as a showreel; the content stops being the subject. |
| Distinct families | **each beat a different one** (§2) | Two beats from one family is a repeat, not a composition. |
| Marquee | **1** | Unchanged. |

**Rotation is enforced, not narrated.** Before choosing the signature effect, read `.finesse/log.json` (`divergence.md` §4) and **pick a different §2 family than last run**. Ten families with 8 variants each is ~80 signature effects — there is no excuse for two consecutive pages both opening with particles. Write the family and variant into the log at §8.

**Say it in the Design Read.** Motion is a decision the user can veto in ten seconds, and right now it's invisible to them until the page is built. Add a `Motion:` block to §0.B — one line per beat, **in plain language with the route named for you, not for them**:

```
Motion —— 整页四拍：
  首屏    一条走不到头的长廊，两边挂你的作品，镜头一直往前
  滚动    往下滚长廊减速停住，一张画自己转正飞到眼前
  作品区  筛选切换时卡片自己重排，不是整块刷新
  收尾    联系方式逐字浮起
  静止版  长廊定格在构图最好的一帧，其余全停
```

Route labels (`R6`, `animation-timeline`, `View Transitions`) are **internal coordinates** — they never appear in anything the user reads (`plain-words.md`). What he reads is the picture.

> **This is also how 「好看 / 炫酷 / 高级」 gets answered.** Those words select nothing — every model maps them to the same particle hero. Don't ask him to be more specific; **assert a beat sheet in pictures and give him two structurally different alternates to veto** (`SKILL.md` §0.B). 「你想要能拖着转的，不是自己往前走的」 is a question he can answer in one word; 「你想要什么风格的动效」 is not.

---

## 5. ROUTE SKELETONS

> Paste-ready mount/teardown code per route. **R1/R2/R3 and R6 land here next** (steps 2–3 of the build-out); R4 and R5 already have full skeletons — don't duplicate them:
> - **R4 · GSAP** → `hero-engines.md` Engine D, plus the secondary vocabulary (split-char, magnetic, curtain wipe, scan-line, per-card fly-in)
> - **R5 · Canvas / WebGL / GLSL** → `hero-engines.md` Engines A, B, C
> - **Component-level 3D** (tilt, flip, coverflow, depth-parallax) → `3d-effects.md` §1
> - **Phone transitions** (push, hand-written FLIP, sheet) → `h5-mobile.md` §5

### 5.1 R6 · the painter's-algorithm constraints (read before building any spatial scene)

CSS 3D has **no z-buffer**. The browser sorts whole elements by an approximation of depth and paints them in order. Five consequences, each one a page-breaking bug that does not exist in WebGL:

1. **Panels at similar depth that overlap will flicker.** The sort flips between frames. Fix geometrically — space points so overlap is impossible (latitude rings sized by `ring circumference ÷ count`, never a Fibonacci sphere), don't try to fix it with `z-index`.
2. **A child that overflows its parent plane gets painted against a *different* 3D plane** and re-enters the sort fight. Clamp children inside their parent's bounds.
3. **A recycling loop needs one more segment than is visible** — a segment must pass *completely* behind the camera before it can be moved to the front, so one is always idle behind you.
4. **`transform` doesn't accumulate.** To apply a second rotation you must **bake** the first: let the transition run, multiply the increment into a matrix you keep in JS, then reset the element to the baked matrix with no transition. Write the zero-angle start state, **force a reflow (`void el.offsetWidth`)**, then transition — otherwise the browser interpolates the whole matrix instead of the angle and the motion is visibly wrong.
5. **`perspective` relative to scene radius decides whether you're inside or outside.** For a sphere of radius R, `perspective ≈ R × 1.3` puts the camera just inside the shell; much larger and you're looking at a ball from outside.

Full engine, `place()` function table and the choreography beat go in §5.2 (build-out step 3).

---

## 6. CHOOSING FAST

```
Is the moving thing a material (fluid, smoke, particles, a rendered object)?  → R5
Is it a space the viewer travels through, carrying photos or text?            → R6
Does it need pin / scrub / a horizontal track?                                → R4
Is it "something changed" (list, filter, route, expand)?                      → R3
Is it driven by scroll position?                                              → R2
Everything else                                                              → R1
```

Then: one heavy beat maximum, four beats total, each from a different family, a different family than last run, and every one of them with a composed still.
