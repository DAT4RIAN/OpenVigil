# Asset Sourcing — Where the Imagery Actually Comes From

`anti-cheap.md` bans zero imagery where the page has an image slot, but doesn't say where the pictures come from. Most briefs arrive with **no real assets attached**. This file is the decision protocol for getting real imagery into the page without silently fabricating it, silently spending the user's generation budget, or silently pulling from the network.

> The core rule, regardless of path: **name what you're about to fetch or generate, then wait for a go-ahead, before you do it.** Never ship a page where the images appeared with no accountable source. Path B (downloading/hotlinking free stock resources) gets this treatment **especially** — it's pulling from the open network into the user's project, so it is a stop-and-confirm step, not an FYI-then-proceed. This mirrors the harness-level rule that external fetches / uploads / spend get flagged, not auto-run.

---

## 0. When This File Fires — and the two ways it gets it wrong

**Fire it at the Design Read (`SKILL.md` §0.B), the moment the page has anywhere a picture would carry it.** Not at delivery, and not off a category checklist.

The trigger is **the skeleton you're about to build, not the industry**:

| Register | Slots that count |
|---|---|
| brand | photographic hero, lookbook/gallery rail, "the work" thumbnails, atelier/about band, texture plates |
| product | empty states, avatar rows, onboarding scenes, the one non-card centerpiece (`product-ui.md` §1.5), annotated-photo hotspot surfaces |
| commerce | PDP gallery, PLP card images, colorway swatch shots, size/material details |
| h5 | cover screen, morph B campaign art, morph C report scenes, morph D product shots, morph F's full-bleed ambient scene |

Food/hotel/fashion/travel/product briefs are the *obvious* cases — they are not the boundary. **A dashboard's empty state deserves the question as much as a hotel hero does.**

### The two failure modes are symmetric — avoid both, not just one

1. **Silent gradient.** The slot exists, nobody said the word "image", and it ships filled with a CSS blob. The user never learned that photography was available in this session, so he never asked. That is the failure this file's *early* trigger prevents.
2. **Silent spend.** You inferred the brief wanted pictures and generated four of them, or pulled six off Unsplash into his project — billed, fetched, and never authorized. That is the failure the *gate below* prevents, and it is not the lesser of the two.

> **The resolution is the same sentence for both: raise it, then wait.** Naming the slots is an **offer**, and an offer is answered by the user, not by you. "The brief clearly implies imagery" is a reason to **ask**, never a reason to proceed — an implication is your reading of his intent, and his intent is the one thing you cannot infer on his behalf when the action costs money or reaches the open network. State count + subjects + source in one line, stop, and let him answer.

---

## 1. Check What's Actually Available First

Before picking a path, look at what the current session can do — this skill runs across different harnesses (Claude Code, Codex, Cursor, Copilot) and their capabilities differ:

1. **Does the user already have real assets?** Ask once, early, if the brief implies specific real subjects (an actual restaurant's dishes, an actual product line, an actual team's headshots) — generic stock cannot substitute for a *specific real thing*. If they have a folder/CMS/DAM, use that before reaching for anything below.
2. **Is an image-generation tool available in this session?** (a native image-gen tool, an MCP image tool, etc.) → **Path A**.
3. **No generation, but network fetch is available** (WebFetch, a browser tool, curl) → **Path B**.
4. **Neither** → **Path C**, the generative-placeholder fallback — and say so explicitly.

Don't guess capability — check the actual tool list for this session before committing to a path.

### 1.1 Listed ≠ usable — verify before you promise it

**A tool appearing in the list is not proof it will run.** The generator may need a credential the environment doesn't have; the network may be sandboxed off. If you name Path A at the Design Read on the strength of the listing alone, you are making a promise on the user's behalf that the environment may refuse — and you'll discover it *after* he said yes, which is the worst moment to renegotiate.

**So before the `Images:` line names a source, spend one cheap call proving it.** A `--help`, a credential check, a single small fetch — whatever costs seconds rather than image-generation budget. If it fails, that path is **not available** for §1's purposes; drop to the next one and say which, in the same breath: *"image generation is installed but has no API key here, so these would be real Unsplash photos instead — ok?"*

> **Codex specifically, two traps.** ① The bundled `imagegen` skill calls the OpenAI Image API through the Python SDK and **requires `OPENAI_API_KEY`** — a Codex/ChatGPT sign-in does **not** satisfy it. Being able to generate images in the Codex app proves nothing about the CLI agent. ② Codex sandboxes often ship with **network disabled by default**, so your own `curl` failing is weak evidence: **the agent having no network does not mean the user's browser has none.** Hotlinked Unsplash URLs still resolve fine when the page is opened. Don't demote Path B because *you* couldn't reach the CDN — wire the URLs, and say at delivery that those images load over the network.

### 1.2 If a path fails mid-build, re-enter this list — never skip a rung

The check above is a *pre*-flight, and pre-flights are sometimes wrong. When the path you committed to turns out unusable once you're actually building on it — no credential, a refused install, a blocked host — **return to §1 and re-run from the next step down.** Take the next path that qualifies, not the last one on the list.

**Falling from A straight to C is the failure this rule exists to stop.** It is the tempting move: generation is out, so you reach for something you can draw yourself, and hand-authored SVG blobs arrive dressed as a design decision. They are not — they are `anti-cheap.md`'s banned "hero = text + gradient blob" with extra steps, and Path B (real photographs, one line of URL each) was sitting right there, unattempted.

**Whatever you land on, the drop gets said out loud** — one line naming the path you left, why, and where you are now. A silent downgrade turns an approved plan into a different deliverable, which is Gate 0's failure in `preflight.md`.

---

## 2. Path A — Generate

Generation costs real time/compute and produces something that must not be mistaken for a real photograph of a real place/product/person if it isn't one.

- **Propose the shot list before generating.** One line per image: subject, framing (close-up / wide / detail), lighting mood, aspect ratio. Tie the lighting/color language to the page's **locked accent** (`design-dna.md`'s color-lock) so every generated image reads as one shoot, not five stock photos from different photographers.
- **Get a go-ahead on the list, not on each image.** One batch confirmation covers the whole page ("I'll generate 4 images: hero product shot, 2 detail crops, 1 lifestyle/context shot — all warm-lit, shallow depth of field, matching the amber accent. Proceed?"). Re-confirm only if the count or subject changes significantly mid-build.
- **Alt text stays honest.** Describe what's depicted; don't caption a generated image as if it were a specific real photographer's work or a specific real location unless the brief actually says so.
- **Never generate identifiable real people** (a real named founder, a real customer) — generate anonymous/stylized subjects, or ask for a real photo instead.

## 3. Path B — Real Stock Photography (hotlink, don't scrape)

This skill's own shipped examples already do this: `nova-brutal-typographic.html` and `offscreen-editorial.html` hotlink specific, deliberately-picked photos directly from `images.unsplash.com/photo-{id}?w=&h=&fit=crop&q=`. That's the pattern — reuse it, don't reinvent it.

- **Use the direct CDN, not a randomizer.** `images.unsplash.com/photo-{specific-id}` (or Pexels' equivalent direct image CDN) is a real, stable asset URL you deliberately picked. A "random image" redirect endpoint is not — it changes on every load/cache-bust and has been deprecated/rate-limited before. Never wire a page to an endpoint that returns a *different* image tomorrow than it does today.
- **Pick specific photos, don't blind-hotlink a search.** Search by the mood/subject the brief implies, open/verify a handful of specific candidates, and pick the ones that match the persona's color grade and composition needs (crop-ability for the layout, room for text overlay, correct orientation).
- **Stop and get explicit authorization before wiring any of them in — one batch ask, not per-image nagging.** State the source (Unsplash/Pexels) and the specific picks in one line, then **wait for the user's go-ahead** before the URLs are wired into the page — e.g. "Using 3 real Unsplash photos for the hero + 2 gallery slots (moody, low-key food photography to match the persona) — proceed?" Downloading/hotlinking free stock resources is pulling from the open network into the user's project; treat it like any other external fetch that needs a yes first, not a courtesy heads-up you plow ahead of.
- **License discipline.** Unsplash License and Pexels License both permit free commercial use without attribution — but that's specific to those two; don't assume every "free image site" carries the same terms. Check the specific source's license before use; when in doubt, prefer Unsplash/Pexels over an unfamiliar site.
- **Don't imply endorsement.** A stock photo of a person is not that person endorsing the (often fictional) brand — fine for mood/lifestyle imagery, not fine as a fake "customer testimonial" headshot presented as real.
- **Real alt text**, matching what's actually depicted (see `commerce-ui.md` §1 for the PDP-specific version of this rule).
- **If hotlinking turns out to be slow or unreliable once actually wired in** — a request hangs, takes far longer than a normal image fetch (tens of seconds instead of near-instant), or times out during your own verification pass — **stop and ask the user** whether to keep the hotlinked URLs as-is or download those same specific picks into the project locally instead. This is a build-blocking judgment call, not yours to make silently either direction: don't quietly switch to local download without saying so, and don't quietly leave slow/broken hotlinks in place and call the page done. State what you observed in one line ("the hotlinked Unsplash images are taking 50+ seconds to load in this environment — download the same 6 picks into `images/` locally instead, or leave them hotlinked?") and wait for the answer, the same way the initial source/pick authorization above requires a go-ahead.

## 4. Path C — No Generation, No Network: Generative Placeholder

When neither A nor B is available, **say so explicitly** — don't silently ship a gradient blob and call it done (that's the exact "hero = text + gradient blob" tell `anti-cheap.md` already bans). Instead:

- Reach for a **generative CSS/Canvas texture as a stand-in**, per the documented techniques in `style-personas.md` / `inspiration-catalog.md` (halftone/riso simulation, duotone gradient over a generative pattern, particle/fluid fields tied to the hero engine). These read as intentional design, not as a missing-image apology.
- **Flag it as a substitute, not a solution.** One line to the user: "No image source available in this session — using a generative [technique] in place of real photography for now; swap in real imagery before shipping to production." Never let this fallback quietly become the permanent state of an image-implied brief.

---

## 5. Universal Rules (all three paths)

- **Style-lock across the page.** Whichever path, every image on one page shares one color grade / lighting language / crop logic — mixing a warm generated hero with a cool stock gallery reads as cheap, same failure mode as breaking the accent lock in `design-dna.md`.
- **Never fabricate provenance.** Don't caption/attribute an image in a way that misrepresents where it came from (generated vs. real; stock vs. brand-owned).
- **Performance still applies.** Responsive images, `srcset`/`sizes`, WebP/AVIF, lazy-load below the fold — this is unchanged by source (`preflight.md` §7).
- **One confirmation ask per page, not per image.** The goal is accountability, not friction — ask once, in one line covering the whole page's image needs, and wait for the answer before fetching/generating any of it.
- **An unanswered ask is a "no", not a "probably yes".** If you raised the slots and the user redirected onto something else without addressing them, build the page with the slots composed but unfilled (Path C, disclosed) and re-raise once at delivery. Do **not** read silence, enthusiasm about the design, or a generic "looks great, go ahead" on a different question as authorization to spend or fetch. The only yes that counts is a yes to *this* question.

## 6. Quick Decision Table

| Session has | Path | Gate before acting |
|---|---|---|
| **Any** of the above, and the page has an image slot | — | **name the slots at the Design Read** (`SKILL.md` §0.B `Images:`), before the layout is written — an offer, not a green light |
| Image-gen tool, **verified runnable** (§1.1) | A — generate | shot list (count + one-line prompt each) — **wait for go-ahead** |
| Image-gen tool listed but **not runnable** (missing key/credential, refused install) | Not A — drop to B, then C (§1.2) | say which path you left and why, in the same line that offers the new one |
| Path A/B failed **after** the user already approved it | Re-enter §1 from the next step down (§1.2) | **name the drop out loud** — a silent downgrade fails `preflight.md` Gate 0 |
| Network fetch, no image-gen | B — real stock, hotlinked by specific ID | source + picks, one line — **wait for go-ahead** (downloading into the user's project is an external-fetch action, treat it as one) |
| Neither | C — generative CSS/Canvas placeholder | explicit "this is a stand-in" disclosure |
| User has real assets for a specific real subject | Use those, skip A/B/C | n/a — always preferred over stock/generated when the brief needs a *specific* real thing |
| Path B hotlinks prove slow/unreliable mid-build | Stay on B or fall back to local download | **ask the user which** — don't silently pick either |
