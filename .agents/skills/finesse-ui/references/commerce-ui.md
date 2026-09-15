# Commerce UI — PDP, PLP, Cart, Checkout

The **commerce** register: a hybrid of brand and product. A product detail page (PDP) sells the vibe of *one* item and can reach for soul (§2 in SKILL.md); a listing/category page (PLP), cart, and checkout serve a task — compare, filter, complete a purchase — and behave like the **product** register (density up, spectacle down). Route each page on its own job; don't apply one register to the whole flow. See SKILL.md §0.A for the PDP-vs-PLP call.

> Inherits the **substrate** (`design-dna.md`) and the **cheapness blacklist** (`anti-cheap.md`) either way. A PDP still earns its soul; a checkout still never looks cheap — it just earns trust instead of spectacle.

---

## 1. Product Detail Page (PDP)

**Canonical layout:** gallery (left / top on mobile) + info column (right / below) — sticky info column on desktop once page scrolls past the fold.

- **Gallery:** thumbnail rail + main image; zoom on hover (desktop) or pinch/tap (mobile); video and 360°/AR view are additions, never replacements for static images. Every image has real alt text (material, angle, "worn by model" — not "product-image-3").
  - **A PDP is the one page that cannot exist without pictures, so settle the source before you build the gallery, not after.** Say how many shots the layout wants and where they'd come from, in the Design Read (`SKILL.md` §0.B `Images:`), then follow `asset-sourcing.md` — and note the one case it treats as special: a **specific real product** cannot be represented by generated or stock imagery. Ask whether the user has the real shots first; generating a plausible-looking photo of a real SKU misrepresents the merchandise, which is a §6 problem, not just a sourcing one. As everywhere, naming the shots is an offer — wait for the yes before generating or downloading anything.
- **Variant selection:** swatches for color (show the actual color, label on hover/focus, never color-only — pair with a name); size as a button grid, not a dropdown, when ≤8 options; out-of-stock variants visible but disabled (strikethrough or dimmed), never removed — removing them hides that a size ever existed.
- **Price block:** current price largest/boldest; if there's a strikethrough original price, both must be real (see §6 dark patterns) and the discount stated as a fact ("20% off", not just implied by the strikethrough).
- **Primary CTA:** one visually dominant "Add to cart" / "Buy now" — if both exist, one is primary and one is secondary, never two equal-weight buttons. Becomes **sticky** (bottom bar on mobile, right column on desktop) once the user scrolls past the original position.
- **Trust stack directly under or beside the CTA:** shipping estimate, return window, and a stock-honesty line ("in stock, ships in 2 days" or a real low-stock count) — see §6 for what's banned here.
- **Below the fold:** specs table (reuse product-ui.md's table alignment rules — numbers right-aligned), reviews (real distribution histogram, not just a rounded average), then cross-sell ("goes with" / "customers also bought") — cross-sell is a recommendation, never a second CTA competing with the primary one.

## 2. Listing / Category Page (PLP)

Product register rules apply directly (`product-ui.md` §1–2 for shell/table thinking) — a PLP is a data table wearing a grid.

- **Grid:** `repeat(auto-fill, minmax(200–260px, 1fr))`; consistent card aspect ratio for images (crop, don't stretch); card shows image, name, price, and one key differentiator (rating or a swatch count) — not the full spec sheet.
- **Filters:** left rail (desktop) / bottom-sheet or top drawer (mobile); show active filter count and a one-click "clear all"; reflect result count live ("142 results"); never a filter that returns zero with no explanation.
- **Sort:** explicit dropdown (relevance / price / rating / newest) — sort silently changing on filter is a bug.
- **Card CTA alignment:** bottom-locked like any card grid (`product-ui.md` §8.A) — price and "add to cart" must line up across a row regardless of name length.
- **Pagination vs infinite scroll:** infinite scroll needs a visible "loaded N of M" and a reachable footer (a "back to top" affordance) — infinite scroll that hides the footer forever is a common complaint, not a feature.
- **Empty / zero-result state:** never a blank grid — "no results for {filters}" + one-click reset, and if possible a "closest matches" fallback.

## 3. Cart

- **Line item:** thumbnail + name + variant (color/size) + quantity stepper + line price + remove — quantity change and price update **without a full page reload**.
- **Persistent summary:** subtotal always visible (sticky on scroll if the cart list is long); shipping/tax shown as "calculated at checkout" if not yet known — never omitted silently.
- **Edit in place:** quantity, variant swap, and remove all happen in the cart; don't force a detour back to the PDP for a simple quantity change.
- **Empty cart:** composed state (not a blank page) — a route back to browsing, optionally recently-viewed items.

## 4. Checkout

- **Steps, not a wall:** shipping → payment → review, each with a visible step indicator and the ability to go back without losing entered data (`product-ui.md` §4 form rules apply throughout — label-above, blur validation, errors-below-with-fix).
- **Guest checkout available** unless there's a specific product reason to require an account; if an account is offered, it's an option after order placement, not a gate before it.
- **Cost transparency by the first form field:** shipping cost, taxes, and any fee must be visible **before** the final payment step, ideally in the persistent order summary from the start of checkout — see §6, "drip pricing."
- **Payment fields:** use native `autocomplete` (`cc-number`, `cc-exp`, `cc-csc`) and `inputmode="numeric"`; card-brand icons only for accepted brands (not a wall of every logo that exists); errors inline per field, not a single toast blaming "payment failed."
- **Order confirmation:** order number, itemized summary, delivery estimate, and a receipt path (email confirmation) stated on-screen — this is the highest-trust moment in the flow, don't undercut it with a bare "Thank you."

## 5. Trust & Conversion Elements (use honestly)

- **Reviews:** real distribution (histogram of 1–5 stars) beats a lone average; verified-purchase tag if the data supports it.
- **Stock/urgency signals:** only ever reflect real inventory or real time windows (see §6 — fabricated versions of these are banned, not just discouraged).
- **Trust badges** (secure checkout, return policy, payment logos): small, below the fold of the CTA, never larger than the CTA itself — they support the purchase decision, they don't replace product information.
- **Comparison table** (for a multi-tier product): reuse `product-ui.md` §8.A pricing-table baseline rule — feature rows must start at the same Y across columns.

---

## 6. Commerce Dark-Pattern Blacklist (add to §6 of SKILL.md)

These are **absolute bans**, not style notes — they erode trust and several are legally actionable in multiple jurisdictions:

- **Fake countdown timers** that reset on refresh or don't correspond to a real deadline. → only real, expiring offers get a countdown.
- **Fabricated low-stock / demand claims** ("only 2 left!", "14 people viewing this") not backed by real data. → show real inventory or omit the signal.
- **Pre-checked add-ons / insurance / upsells** at checkout. → opt-in, unchecked by default.
- **Drip pricing** — hiding shipping/fees/taxes until the last step. → total cost visible from the first checkout screen.
- **Forced account creation** before completing a purchase. → guest checkout, account offered after.
- **Confirmshaming** ("No thanks, I don't like saving money" as the decline option on a popup). → neutral, respectful decline copy.
- **Hidden or buried unsubscribe/cancel** for subscriptions sold on the PDP. → cancellation as easy as signup, findable from account settings.
- **Strikethrough prices with an inflated or never-real "original" price.** → the crossed-out price must have actually been charged.
- **Hard-to-close, action-disguised-as-close popups** (an X that actually adds to cart or opts in). → a close control does only one thing: close.

---

## 7. Commerce Pre-Flight (in addition to the shared §8 and product §10 where applicable)

- [ ] PDP: gallery has real alt text, variant states (in/out of stock) all visible, one primary CTA, sticky CTA on scroll, trust stack honest (no fabricated urgency/stock).
- [ ] PLP: filters reflect live result count with one-click clear, sort is explicit, card CTA alignment locked, zero-result state composed not blank.
- [ ] Cart: quantity/variant edits happen in place with no full reload, subtotal always visible, empty state composed.
- [ ] Checkout: full cost visible before final payment step, guest checkout available, step indicator with back-navigation preserving data, payment fields use correct `autocomplete`/`inputmode`.
- [ ] Every item in §6's dark-pattern blacklist checked absent — this is a hard gate, not a nice-to-have.
- [ ] Still passes the substrate + cheapness blacklist (SKILL.md §3, §6).
