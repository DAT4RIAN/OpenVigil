# Pre-Flight Check

Run before saying "done." Merges the promise check, the substrate check, the cheapness scan, the spectacle verification, and the accessibility gates. Failing any **hard rule** is shipping broken work — fix before delivery. Soft rules are judgment calls; if you skip one, say why.

---

## Gate 0. Promise Kept (hard — run this first, before anything below)

Every check in §A–§I asks *"does this page follow the rules?"* None of them asks **"is this the page the user agreed to?"** Those are different questions, and only the second one can fail silently: a page can pass every rule in this file while having quietly become something the user never approved. Long builds drift — a moving hero degrades into a static image, a dark theme lightens section by section, an engine gets stubbed out when it wouldn't run and never gets restored. Nothing downstream notices, because a static image has perfect contrast and zero jank.

**Paste the `You'll see:` line from the §0.B Design Read back in, and check it item by item against the built page.**

```
Gate 0 — Promise kept
  ✅ near-black page
  ❌ slow-drifting star dust  →  shipped as a static background image  →  P0
  ✅ very large headline over it
  ✅ galaxy rotates on scroll
```

- [ ] **Every clause of `You'll see:` is verifiably present.** Not "an equivalent effect" — the thing described. Any miss is **P0**: the user confirmed *that* sentence, and shipping something else is shipping work he did not approve.
- [ ] **A clause that could not be built was renegotiated, not silently dropped.** If the engine wouldn't hold 60fps and you fell back to a still frame, that is a legitimate call (§1.B says so) — but it changes what the user agreed to, so it gets said out loud at delivery, not buried.
- [ ] **`Not right?` was answered.** If the user picked ① or ②, the built page reflects that pick, not the original assertion.

> This generalizes §1.B. "Spectacle claimed, spectacle shown" is the same test applied to one dial — and it is finesse's signature audit precisely because claimed-vs-shipped is the failure that rule-checking cannot see. `You'll see:` is the *whole* claim, so it gets the same treatment.

---

## Gate 1. It Actually Renders (hard — run this second, before §A)

Every check in §A–§I asks *"is this page well-made?"* — and every one of them **passes vacuously on a page that never rendered**. A `<link>` pointing at a stylesheet that was never written produces unstyled Times New Roman: no grain to be missing, no `#fff` to be banned, no eyebrow to over-count. The taste layer cannot see a file that isn't there. So the file-existence check runs before the taste layer, not inside it.

**This is also the truncated-build tell.** The HTML gets written, the run ends before the CSS does, and nothing downstream notices — the most common way a long build ships broken. `.finesse/log.json` will even be there, correctly recording a build that doesn't exist on screen.

**Resolve the detector first.** The path is **not** relative to the user's project unless the skill was vendored into it — under Codex it lives in `~/.codex/skills/`, under Claude Code in `~/.claude/skills/` or the plugin dir. Resolve it once, reuse `$DETECT` for the rest of this file:

```bash
for p in skills/finesse-ui .claude/skills/finesse-ui \
         "$HOME/.claude/skills/finesse-ui" "$HOME/.codex/skills/finesse-ui"; do
  [ -f "$p/scripts/detect.mjs" ] && DETECT="$p/scripts/detect.mjs" && break
done
node "$DETECT" --json <every built file>
```

- [ ] **Every local `href` / `src` / `url()` resolves to a file that exists.** A `P0 dead-local-ref` is a hard fail — write the missing file or fix the path. The detector resolves file-relative refs and skips `http(s):` / `data:` / `#anchor` / `mailto:`; **root-relative `/img/x.png` it cannot judge** (it has no serving root), so check those by hand.
- [ ] **The detector was found and ran.** If `$DETECT` resolved to nothing, say so and check the refs by hand — an unrun detector is not a pass, and silently skipping it is how M1/M2/M5/M6 go unchecked for an entire project.
- [ ] **Every file the page needs was actually written.** Walk your own build list: stylesheet, script, each asset. A file you *planned* and a file that exists on disk are different things, and only one of them renders.
- [ ] **Told him it hasn't been opened.** The checks above are static and catch the expensive failures for free; whether it *looks* right is one second of his time. **Don't drive a browser to find out — say 「我没打开看」 and let him look.** Only if he asks.

---

## A. Direction & Soul (hard)

- [ ] **Design Read** was committed (industry · soul · register · SPECTACLE · engine) **and the `You'll see:` line was written in plain observable terms** — no `SPECTACLE=n`, no `scrimmed sections`, no library names in the sentence the user was asked to confirm (§0.C.1, `plain-words.md`).
- [ ] **Anti-default named** — the lazy aesthetic for this brief was identified and beaten.
- [ ] **Rotation was read and stated** — `.finesse/log.json` (or a `/* finesse ·` CSS stamp) was read at §0, the rotation was stated to the user **as a plain sentence** (not axis letters), and this build differs from the last on **≥3 of 5 axes** (`divergence.md` §4). The five-axis coordinates themselves live in the log and the stamp, not in the user-facing line.
- [ ] **Build recorded** — the five-axis stamp is the first non-empty line of the CSS, and an entry was prepended to `.finesse/log.json` (trimmed to 20). *An unrecorded build is one the next run collides with.* Component-scope builds skip both by design.
- [ ] **One soul, one accent, locked** across every section. No drift, no second accent unless duotone-by-design.
- [ ] **Theme locked** — no warm-paper section inside a dark page (unless deliberate one-time switch).
- [ ] Page matches its **register** (brand = bold/spectacle; if it's really product-UI, finesse is the wrong tool).

## B. Premium Substrate (hard)

- [ ] **Grain** layer present (`opacity .02–.05`).
- [ ] **No pure `#fff`/`#000`**; neutrals tinted toward brand hue.
- [ ] **Translucent borders** only; no hard `#333` lines; shadows hue-tinted (not pure black on light bg).
- [ ] **Display type tension** — `clamp()` size, negative tracking, weight contrast against light body. Line-height **`.86–.95` for mixed case**; **`1.0` floor (`1.02–1.08` recommended) whenever `text-transform: uppercase` is on** — all-caps has no descenders, so tight leading collides cap-tops with the line above the moment the heading wraps, which on a phone it always does (`mobile-floor.md` M6).
- [ ] **Tokens hold to the end** — every colour and `font-family` in the artifact references a named token; no literal `#hex` / `oklch()` / `rgb()` outside the `:root` block. The colour lock is the decision; this is what enforces it 400 lines in.
- [ ] **Layered z-index** depth (engine · grain · vignette · content).

## C. Spectacle (hard if SPECTACLE ≥ 7)

- [ ] **Spectacle shown, not claimed** — a real working engine exists.
- [ ] **60fps on a mid-range device** (not the dev machine). Below 50fps → simplified.
- [ ] **Canvas DPR-adapted** (retina not blurry).
- [ ] **Progressive enhancement** — page is complete and readable with the engine removed.
- [ ] **`prefers-reduced-motion`** freezes the engine to a still frame / static hero.
- [ ] **Motivated motion** — every animation has a one-sentence reason. ≤1 marquee.

### C.1 The beat sheet (hard on any page that moves — `motion.md`)

Gate C above checks **the hero engine**. These check **the page's motion as a whole**, and they fail on pages that pass everything above.

- [ ] **No route over-reach** — nothing uses a heavy route for work a cheap one does. Grep the failure directly: a bundled GSAP whose only tweens are entrance fades or scroll parallax (→ R1/R2, delete the 60KB); a Canvas that draws a static gradient (→ CSS); a Three.js scene whose content is photographs (→ R6).
- [ ] **Budget held** — **≤1 heavy beat** (R4/R5/R6), ≤4 beats total, and **no two beats from the same §2 family**. Two scroll-narrative beats is a repeat, not a composition.
- [ ] **Every beat has a composed still**, not just the global reduced-motion backstop. Check the specific killer: any element authored at `opacity: 0` / `transform: translateY(...)` awaiting a trigger is **permanently invisible** under the backstop — it must be authored in its final state and animated *from* elsewhere.
- [ ] **Pointer-driven beats gated behind `FINE`** (`hover: hover and pointer: fine`) so magnetic buttons, tilts and cursor followers never fire on touch.
- [ ] **`product` register carries R3 and nothing else** — a dashboard with a hero engine is a category error; a dashboard where filtering hard-refreshes the table is the opposite one.
- [ ] **Rotation honoured** — the signature beat's §2 family differs from the last run's (`.finesse/log.json`), and the family+variant is written back at §8.

### Verifying spectacle — don't trust your own claim, prove it

A page that *claims* SPECTACLE 8 but ships a white hero is broken, not plain. Verify in two passes:

1. **Static (always):** run the detector (`$DETECT`, resolved per Gate 1) — it greps for a real engine and the reduced-motion fallback, and fails on "claimed-not-shown":
   ```bash
   node "$DETECT" --json <target>
   ```
   A `P0 spectacle-not-shown` or `P0 no-reduced-motion` in the output (`p0 > 0`) is a hard fail — fix before shipping. The script always exits 0 (findings live in the JSON); add `--strict` if you want it to block with a non-zero exit in a git hook / CI. If the script isn't present, fall back to the by-hand checks above — don't treat its absence as a pass.
2. **Runtime — hand it to him in one line, don't go look yourself.** The grep proves the code exists, not that it renders. Close that gap by *telling him where to look*, not by driving a browser:

   ```
   我没打开看。你扫一眼：hero 画出来没有（不是白屏），
   开「减弱动态效果」刷新后是不是定格在一张构图。
   ```

   Screenshot only if he asks. **And never claim a pass you didn't run** — 「静态检查通过，没打开看」 is a complete delivery line; 「已验证渲染正常」 after a grep is not.

## D. Layout Discipline (hard)

- [ ] **Hero fits the viewport** — headline ≤2 lines, subtext ≤20 words, CTA visible without scroll. Max 4 text elements.
- [ ] **Nav** single line, ≤80px tall.
- [ ] **Eyebrow count ≤ ceil(sections/3).**
- [ ] **≥4 layout families** on a long page; no family more than twice; ≤2 consecutive image+text zigzags.
- [ ] **Mobile collapse** declared per multi-column section. `min-h-dvh` over `100vh`.

### D.1 The mobile floor (hard) — test at 320 · 375 · 414 · 768

Not "narrow the window until it looks off" — those four widths. Causes and fixes: `mobile-floor.md`.

> **h5 register: run `h5-mobile.md` §10 instead of this section.** A phone-only page has no width range to survive, so most of D.1 doesn't apply — M1/M4/M6 still hold inside the frame, but M2 and M5 largely evaporate (one column, one bottom bar). Its gate list is a different set of failures: `viewport-fit=cover` present; `env(safe-area-inset-*)` on the status bar, bottom bar, sheets **and** the scroll container's bottom padding; `body` locked with a child scrolling; every hit area ≥44px with an `:active` state and no tap flash; nothing cut off at `height: 640px`; ambient motion layers **removed** rather than frozen under reduced motion.

- [ ] **M1** — `overflow-x: clip` on **both** `html` and `body`. Not `hidden` (it creates a scroll container and kills every sticky/fixed descendant — the "I fixed the scroll and broke the nav" bug).
- [ ] **M2** — every grid track that can hold an image is `minmax(0, 1fr)`, not bare `1fr`; flex children that can hold one have `min-width: 0`.
- [ ] **M3** — no button, nav link, footer link, tab, breadcrumb, or CTA wraps to two lines at **any** width from 320 up. Shorten the label first.
- [ ] **M4** — display headings carry `overflow-wrap: anywhere; min-width: 0`.
- [ ] **M5** — exactly one sticky element at `top: 0`; every other sticky offset by `--nav-h`, with `--z-nav` above `--z-sticky`.
- [ ] **M6** — nothing has both `text-transform: uppercase` and `line-height < 1.0` (see §B).
- [ ] Ran `node "$DETECT" --json <target>` (Gate 1) — it catches M1/M2/M5/M6. **M3 and M4 it cannot see**; open the page at 320px and read it.

## E. Cheapness Scan (hard)

- [ ] No em-dashes in copy. No div-based fake screenshots. No gradient-text/glass/AI-purple as default.
- [ ] **No re-drawn environment chrome** — no hand-built browser bar (URL pill + traffic lights), phone bezel, IDE frame, or terminal window. Real screenshot in a `<figure>`, or no chrome at all. (Distinct from fake screenshots: a *real* screenshot inside a *drawn* MacBook bezel still fails.)
- [ ] No fake-precise numbers without a source. No banned beige+brass default palette.
- [ ] No identical card grids. No numbered `01·02·03` unless a real sequence.
- [ ] **Real imagery in every slot the built page has for one** — hero photograph, gallery/lookbook rail, PDP shot, H5 cover or scene, empty state, avatar row. Judged off the skeleton, not the industry; food/hotel/fashion/travel/product are the obvious cases, not the boundary. Sourced per `asset-sourcing.md` (generate/stock/placeholder), not a silent gradient-blob substitute.
- [ ] **Every image on the page has an answer to "who said yes to this?"** — the slots were named at the Design Read (`SKILL.md` §0.B `Images:`) and the user approved the count + source. Nothing was generated, downloaded, or hotlinked off your own inference that the brief implied it. A page that quietly spent the user's generation budget fails this check as hard as one that quietly shipped gradients.
- [ ] Real SVG logos (not text wordmarks) on any "trusted by" wall.
- [ ] Fonts chosen with a reason — not a blind reach for Inter/Fraunces/Instrument Serif.

## F. Copy Self-Audit (hard)

- [ ] Re-read every visible string. No broken grammar, unclear referents, or AI-cute wordplay.
- [ ] One copy register per page. Quotes ≤3 lines with full attribution.
- [ ] One label per CTA intent across nav/hero/footer.

## G. Accessibility (hard)

- [ ] Contrast WCAG AA — body ≥4.5:1, large ≥3:1. Includes **buttons over photos** (scrim/stroke), placeholders, helper/error text, focus rings.
- [ ] Visible focus state on every interactive element; keyboard-reachable nav + CTAs.
- [ ] Button text fits one line at **every width from 320 up** — not just desktop, which is the width where the problem never happens (`mobile-floor.md` M3).
- [ ] Touch targets ≥44px. Form labels above inputs (never placeholder-as-label).

## H. Performance (soft)

- [ ] Animate only `transform`/`opacity`. `will-change` sparingly.
- [ ] Heavy engines lazy-loaded. Responsive images (WebP/AVIF, `srcset`). CLS < 0.1.

---

### The four ship-tests (from overdrive thinking)

1. **wow** — would someone who hasn't seen it react?
2. **removal** — if you delete the engine, is the experience clearly worse?
3. **device** — still smooth on a phone / Chromebook?
4. **context** — does this spectacle actually serve *this* brand and audience, or is it showing off?

If "removal" or "context" fails, the spectacle is decoration, not finesse. Cut or rework it.

---

## I. Strategic Omissions (soft — but separate a prototype from a real deliverable)

These don't affect visual output but are what get noticed after launch:

- [ ] **Custom 404 page** — a framework default is not acceptable for a brand page.
- [ ] **Legal links** (Privacy Policy, Terms of Service) in the footer — required for any real launch.
- [ ] **Skip-to-content link** (`<a href="#main" class="sr-only focus:not-sr-only">`) for keyboard users — satisfies WCAG 2.4.1.
- [ ] **"Back" navigation** — every page is reachable from at least one other page. No dead ends in user flows.
- [ ] **No placeholder data left** ("Jane Doe", lorem ipsum, `email@example.com`) in shipped output.
- [ ] **Form validation wired** — client-side on blur, errors state cause + fix ("Password needs 8+ chars", not "Invalid").

---

## J. Self-Grading Loop (run last, before saying "done")

Generate 5 sharp questions about your specific output, then answer each with concrete evidence from the code/copy you wrote — not a generic "yes." If any answer reveals a failure, fix it before shipping.

**Template — fill in with your actual output:**

1. **Engine check:** "Did I ship a working `[engine type]`, or is there a gradient blob/placeholder where the hero should be?" → [evidence]
2. **Soul check:** "Is the soul I picked (`[persona name]`) actually visible in the palette, typeface, and motion — or did I drift back to a generic aesthetic?" → [evidence]
3. **HARD BAN sweep:** "Does the copy contain any em-dashes? Are there any eyebrow labels on more than 1-in-3 sections? Any fake numbers?" → [evidence]
4. **Substrate check:** "Did I apply grain, type tension (negative tracking + weight contrast), and translucent borders to every section — or just the hero?" → [evidence]
5. **Dial honesty:** "Is the page I built actually `SPECTACLE=[n]` and `DENSITY=[n]`, or did I under-deliver on what I committed to?" → [evidence]

**A "yes" with no evidence = unverified = fail.** Re-read the output, quote the specific line or value that proves it.
