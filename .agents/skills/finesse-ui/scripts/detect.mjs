#!/usr/bin/env node
// finesse — local slop / spectacle detector.
// No network, no deps. Scans HTML/CSS/JS files for cheapness tells and the
// finesse-specific "spectacle claimed but not shown" failure.
//
// Usage:
//   node detect.mjs [--json] [--strict] <file ...>
//   node detect.mjs --json skills/finesse-ui/examples/*.html
//
// Exit code: 0 by default — ALWAYS, even when P0 findings exist. Findings are
// DATA carried in the report (the JSON `p0` count), not a tool failure. A
// non-zero exit reads to an agent as "this tool is broken" and it abandons the
// tool entirely, falling back to eyeballing — so the default path never does
// that. Pass --strict to make a P0 finding block with exit 1 (for CI / git
// hooks / humans who want a hard gate). The `audit` command (references/audit.md)
// consumes the --json output and decides for itself; it does not need exit codes.

import { existsSync, readFileSync } from 'node:fs';
import { basename, dirname, resolve } from 'node:path';

const args = process.argv.slice(2);
const asJson = args.includes('--json');
const strict = args.includes('--strict');
const files = args.filter((a) => a !== '--json' && a !== '--strict');

// What the regex layer canNOT see. A clean run means "no regex-detectable slop",
// NOT "this page is good" — these taste/structure/runtime tells need a human eye
// (or the Playwright runtime pass in preflight.md §C). Surfaced in every report so
// a green result never reads as license to skip the visual audit.
const NOT_COVERED = [
  'default-category aesthetic (the vibe, not just token names — beige+brass craft, AI purple-glow)',
  'div-based fake screenshots / fake dashboards',
  'identical / generic card grids (icon + title + text × N)',
  'zero imagery on an image-implied brief (food / hotel / fashion / travel)',
  'glassmorphism / AI-purple-glow used as decoration',
  'layout-family repetition (§5) and whether the soul is actually distinct',
  'whether the engine RENDERS real pixels (needs the Playwright runtime pass, not a grep)',
  'mobile-floor M3/M4 — clickable text wrapping to two lines, long-word overflow at 320px (needs a rendered page at 320, not a grep)',
  'root-relative asset paths (`/img/x.png`) — dead-ref only resolves file-relative ones; a broken `/…` link needs the real serving root',
];

if (files.length === 0) {
  // Guidance, not an error. Never teach the agent to abandon the tool.
  const note = 'usage: node detect.mjs [--json] [--strict] <file ...>';
  if (asJson) console.log(JSON.stringify({ p0: 0, files: [], notCovered: NOT_COVERED, note }, null, 2));
  else console.log(note);
  process.exit(0);
}

// ---- helpers ---------------------------------------------------------------

// Find 1-based line number of a regex match index.
function lineOf(text, index) {
  let line = 1;
  for (let i = 0; i < index && i < text.length; i++) if (text[i] === '\n') line++;
  return line;
}

// Collect every match of a global regex as {line, text}.
function matches(text, re) {
  const out = [];
  let m;
  const r = new RegExp(re.source, re.flags.includes('g') ? re.flags : re.flags + 'g');
  while ((m = r.exec(text)) !== null) {
    out.push({ line: lineOf(text, m.index), text: m[0].slice(0, 80).replace(/\s+/g, ' ').trim() });
    if (m.index === r.lastIndex) r.lastIndex++; // zero-width guard
  }
  return out;
}

// Remove comment bodies (HTML, CSS-block, JS-line) so copy-rules don't fire on
// notes/labels inside comments. Replace with same-length whitespace to keep line
// numbers stable.
function stripComments(text) {
  return text
    .replace(/<!--[\s\S]*?-->/g, (m) => m.replace(/[^\n]/g, ' '))
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m, p1) => p1 + m.slice(p1.length).replace(/./g, ' '));
}

// Innermost `{ ... }` blocks — i.e. CSS declaration blocks, not @media wrappers.
// Several mobile-floor rules are about two declarations CO-OCCURRING in one rule
// (uppercase + tight leading; sticky + top:0), which a flat regex can't express.
function ruleBlocks(text) {
  const out = [];
  const re = /\{([^{}]*)\}/g;
  let m;
  while ((m = re.exec(text)) !== null) out.push({ index: m.index, body: m[1] });
  return out;
}

// ---- generic slop rules ----------------------------------------------------
// Each rule: {id, severity, label, fix, find(text) -> [{line,text}]}

const RULES = [
  {
    id: 'gradient-text',
    severity: 'P1',
    label: 'Gradient text (background-clip:text + gradient)',
    fix: 'typeset / soul',
    find: (t) => {
      // a block that has background-clip:text near a linear/radial-gradient
      const out = [];
      const re = /-?webkit-background-clip\s*:\s*text|background-clip\s*:\s*text/gi;
      let m;
      while ((m = re.exec(t)) !== null) {
        const window = t.slice(Math.max(0, m.index - 240), m.index + 240);
        if (/(linear|radial|conic)-gradient/i.test(window)) {
          out.push({ line: lineOf(t, m.index), text: m[0] });
        }
      }
      return out;
    },
  },
  {
    id: 'side-stripe',
    severity: 'P1',
    label: 'Side-stripe border (border-left/right > 1px as colored accent)',
    fix: 'redesign',
    find: (t) =>
      matches(t, /border-(left|right)\s*:\s*(?:[2-9]|\d{2,})px[^;]*/gi).filter(
        (h) => !/transparent/i.test(h.text)
      ),
  },
  {
    id: 'em-dash',
    severity: 'P2',
    label: 'Em-dash / "--" as a prose flourish (kinetic pause / dramatic aside)',
    fix: 'clarify',
    // Only flag the real tell: an em-dash between two lowercase prose words
    // ("workflow — seamlessly"). Skip structured labels where it's a legitimate
    // separator: number—label ("001 — ENGINE"), CAPS—CAPS ("NEXT — ISSUE 08"),
    // role—name bylines, and CJK labels. Also catch literal " -- " in prose.
    // Scan comment-stripped copy so notes/CSS don't fire.
    find: (t) => matches(stripComments(t), /[a-z]{2,}\s*—\s*[a-z]{2,}|[a-z]{2,}\s--\s[a-z]{2,}/g),
  },
  {
    id: 'numbered-scaffold',
    severity: 'P2',
    label: 'Numbered section scaffolding (01 · / 02 · / 03 ·)',
    fix: 'redesign',
    find: (t) => matches(t, /\b0[1-9]\s*[·.\-/]\s*[A-Z][a-z]/g),
  },
  {
    id: 'default-palette-token',
    severity: 'P2',
    label: 'Default-category palette token name (--cream/--sand/--paper…)',
    fix: 'soul',
    find: (t) =>
      matches(t, /--(cream|sand|paper|parchment|bone|flour|linen|wheat|biscuit|ivory)\b/gi),
  },
  {
    id: 'pure-bw',
    severity: 'P2',
    label: 'Pure #fff / #000 (untinted neutral)',
    fix: 'soul',
    find: (t) => matches(t, /#fff(?:fff)?\b|#000(?:000)?\b/gi),
  },
  {
    id: 'hard-333-border',
    severity: 'P2',
    label: 'Hard #333-ish border instead of translucent',
    fix: 'soul',
    find: (t) => matches(t, /border[^;{]*:\s*[^;]*#(?:333|444|222|ccc|ddd)\b[^;]*/gi),
  },
  {
    id: 'fake-precise-number',
    severity: 'P2',
    label: 'Fake-precise metric (e.g. 4.1×, 92.7%) — verify it has a source',
    fix: 'clarify',
    find: (t) => matches(t, />\s*\d{1,3}\.\d+\s*(?:×|x|%)\s*</g),
  },
  {
    // mobile-floor.md M1. `hidden` makes the element a scroll container, which
    // severs position:sticky/fixed for every descendant — the page stops
    // scrolling sideways and the sticky nav dies with it. `clip` doesn't.
    id: 'overflow-x-hidden',
    severity: 'P1',
    label: 'overflow-x:hidden at root on a page using position:sticky (use `clip`)',
    fix: 'mobile-floor M1',
    find: (t) => {
      // Gate on sticky. `hidden` on an ancestor makes a scroll container, which
      // breaks position:sticky descendants — that is the whole harm. Without a
      // sticky on the page there is nothing to break, and firing anyway would be
      // a false positive on ~3 of every 4 pages. (position:fixed is NOT affected
      // by overflow — only by a transform/filter/will-change containing block —
      // so it deliberately does not gate this rule.)
      if (!/position\s*:\s*sticky/i.test(t)) return [];
      const out = [];
      for (const b of ruleBlocks(t)) {
        if (!/overflow(-x)?\s*:\s*hidden/i.test(b.body)) continue;
        // only the root selectors matter; a hidden overflow on a card is fine
        const sel = t.slice(Math.max(0, b.index - 120), b.index);
        if (/(^|[\s,}>])(html|body)\s*(,[^{]*)?$/i.test(sel)) {
          out.push({ line: lineOf(t, b.index), text: 'html/body overflow-x:hidden + sticky on page' });
        }
      }
      return out;
    },
  },
  {
    // mobile-floor.md M6. All-caps has no descenders, so cap-tops collide with
    // the line above once the heading wraps. Unitless values only — `1.2em`
    // and `120%` are not display leading and shouldn't fire.
    id: 'uppercase-tight-leading',
    severity: 'P1',
    label: 'text-transform:uppercase with line-height < 1.0 (cap-collision on wrap)',
    fix: 'mobile-floor M6',
    find: (t) => {
      const out = [];
      for (const b of ruleBlocks(t)) {
        if (!/text-transform\s*:\s*uppercase/i.test(b.body)) continue;
        const lh = b.body.match(/line-height\s*:\s*(0?\.\d+|\d(?:\.\d+)?)\s*(?:;|$)/i);
        if (lh && parseFloat(lh[1]) < 1) {
          out.push({ line: lineOf(t, b.index), text: `uppercase + line-height:${lh[1]}` });
        }
      }
      return out;
    },
  },
  {
    id: 'transition-all',
    severity: 'P2',
    label: 'transition: all (name the properties — `all` animates layout props too)',
    fix: 'animate',
    find: (t) => matches(t, /transition\s*:\s*all\b[^;]*|\btransition-all\b/gi),
  },
];

// ---- finesse-specific: spectacle claimed vs shown --------------------------
// Look for a stated SPECTACLE value (in comments / Design Read / data-attr).
function spectacleCheck(text) {
  const claim = text.match(/SPECTACLE\s*[=:]\s*(\d{1,2})/i);
  if (!claim) return null;
  const value = parseInt(claim[1], 10);
  const line = lineOf(text, claim.index);
  // Evidence of a real engine.
  const enginePatterns = [
    /\bthree(?:\.min)?\.js\b|\bTHREE\b|from\s+['"]three['"]/,
    /\bgetContext\(\s*['"](?:webgl2?|2d)['"]/,
    /\bgsap\b|ScrollTrigger/,
    /requestAnimationFrame/,
    /\bnew\s+OffscreenCanvas\b/,
    /animation-timeline\s*:/i,
  ];
  const hasEngine = enginePatterns.some((re) => re.test(text));
  if (value >= 7 && !hasEngine) {
    return {
      id: 'spectacle-not-shown',
      severity: 'P0',
      label: `SPECTACLE ${value} claimed but no engine found (three/canvas/gsap/rAF/CSS-timeline)`,
      fix: 'animate / bolder',
      hits: [{ line, text: `claimed SPECTACLE=${value}` }],
    };
  }
  return null;
}

// Reduced-motion fallback presence. Only continuous/scroll-driven motion gates a
// P0 — rAF loops, gsap/ScrollTrigger, or @keyframes (which often run infinitely).
// A bare hover `transition:` or one-shot `animation:` does NOT require the media
// query, so it must not trigger a false P0.
function reducedMotionCheck(text) {
  const hasContinuousMotion =
    /requestAnimationFrame|gsap|ScrollTrigger|@keyframes|animation-timeline\s*:/.test(text);
  const hasFallback = /prefers-reduced-motion/.test(text);
  if (hasContinuousMotion && !hasFallback) {
    return {
      id: 'no-reduced-motion',
      severity: 'P0',
      label: 'Continuous motion (rAF/gsap/@keyframes) but no prefers-reduced-motion fallback',
      fix: 'animate',
      hits: [{ line: 0, text: 'no @media (prefers-reduced-motion)' }],
    };
  }
  return null;
}

// Eyebrow density: count eyebrows *in the markup*, not uppercase rules in the CSS.
//
// An eyebrow is an INSTANCE: a short label element sitting immediately above a
// heading. The old heuristic counted CSS *rules* (`letter-spacing` × `uppercase`)
// and over-reported badly on any page with rich metadata — spec labels, dial
// ticks, nav chips, stat captions and table headers all carry uppercase+tracking,
// and none of them are eyebrows. A watch or hardware page would light up red
// while a page with one shared `.eyebrow` class used on six sections passed.
// False positives are expensive: they train you to ignore the check.
//
// So: find each <h1>/<h2>, look at the markup immediately before it, and count a
// short label element if one is sitting there. A tracked label that is NOT above
// a heading is metadata (or is itself the section's title) — not an eyebrow.
function eyebrowCheck(text) {
  const sections = (text.match(/<section\b/gi) || []).length || 1;
  const cap = Math.ceil(sections / 3);

  const headings = [...text.matchAll(/<h[12]\b/gi)].map((m) => m.index);
  let count = 0;
  for (const at of headings) {
    // the ~240 chars of markup right before the heading, comments stripped
    const before = text.slice(Math.max(0, at - 240), at).replace(/<!--[\s\S]*?-->/g, '');
    // …ending in a short, self-contained label element (inner text ≤ 40 chars)
    const label = /<(div|span|p|small)\b[^>]*>(?:(?!<\/?(?:div|span|p|small|h[12])\b)[\s\S]){1,40}<\/\1>\s*$/i;
    if (label.test(before.trimEnd())) count++;
  }

  if (count > cap && count >= 3) {
    return {
      id: 'eyebrow-overuse',
      severity: 'P1',
      label: `Eyebrow above ${count} of ${sections} sections (cap ${cap} = ceil(sections/3))`,
      fix: 'typeset',
      hits: [{ line: 0, text: `${count} label-above-heading instances` }],
    };
  }
  return null;
}

// The five-axis build stamp (divergence.md §4.2). It's the fallback memory for
// rotation when `.finesse/log.json` is absent — a page copied out of its project
// still carries its own coordinates. P2, not P1: a missing stamp doesn't break
// the page, it breaks the NEXT build's ability to rotate off this one. Component
// artifacts stamp differently (component-scope.md §5) and are exempt.
function stampCheck(text) {
  if (/\/\*\s*finesse\s*[·|]/i.test(text)) return null;
  return {
    id: 'missing-stamp',
    severity: 'P2',
    label: 'No /* finesse · … */ build stamp — next run has nothing to rotate against',
    fix: 'divergence §4.2',
    hits: [{ line: 0, text: 'no five-axis stamp in CSS' }],
  };
}

// mobile-floor.md M2. A bare `1fr` is `minmax(auto, 1fr)`, and `auto` floors the
// track at the content's max-content width — a 1600px image makes a 1600px
// minimum track. Only fires when the file actually contains an image.
function bareFrTrackCheck(text) {
  // Replaced elements only. `background-image` deliberately does NOT gate this:
  // a background contributes nothing to intrinsic size, so it can't blow out a
  // track — including it fired on ~a third of pages for no reason.
  if (!/<img\b|<picture\b|<video\b/i.test(text)) return null;
  // A global `img { max-width: 100% }` doesn't fully remove the max-content
  // floor, but in practice it defuses the common single-column case.
  if (/(?:^|[\s,}])(?:img|picture|video)[^{]*\{[^}]*max-width\s*:\s*100%/i.test(text)) return null;
  const hits = matches(text, /grid-template-(?:columns|rows)\s*:\s*[^;}]+/gi).filter((h) => {
    // blank out minmax(...) — any explicit minimum is fine, only bare 1fr is not
    const stripped = h.text.replace(/minmax\s*\([^)]*\)/gi, 'MM');
    return /(?:^|[\s(,:])1fr\b/.test(stripped);
  });
  if (!hits.length) return null;
  return {
    id: 'bare-1fr-track',
    severity: 'P2',
    // P2, not P1: file-level correlation only. The grep knows the page has
    // images and has bare `1fr` tracks; it cannot know they're the SAME track.
    // Confirm which track holds the image before changing anything.
    label: `Bare \`1fr\` track(s) on a page with images — confirm whether an image sits in one, then use \`minmax(0,1fr)\``,
    fix: 'mobile-floor M2',
    total: hits.length,
    hits: hits.slice(0, 8),
  };
}

// mobile-floor.md M5. Two elements pinned at top:0 occupy the same strip and the
// deeper-in-DOM one paints over the nav.
function dualStickyCheck(text) {
  const hits = [];
  for (const b of ruleBlocks(text)) {
    if (!/position\s*:\s*sticky/i.test(b.body)) continue;
    if (/(?:^|[;\s])top\s*:\s*0(?:px|rem|em|%)?\s*(?:;|$)/i.test(b.body)) {
      hits.push({ line: lineOf(text, b.index), text: 'sticky + top:0' });
    }
  }
  if (hits.length < 2) return null;
  return {
    id: 'dual-sticky-top0',
    severity: 'P1',
    label: `${hits.length} elements sticky at top:0 — they overlap; offset all but the nav by --nav-h`,
    fix: 'mobile-floor M5',
    hits: hits.slice(0, 8),
  };
}

// anti-cheap.md — mid-build token improvisation. Counts OPAQUE colour literals
// outside the token block. Deliberately ignores rgba()/hsla(): finesse REQUIRES
// inline translucent values for borders and tinted shadows (SKILL §3), so
// counting them would fight the skill's own rule. Threshold, not zero-tolerance
// — a hand-tuned gradient or an SVG fill is legitimate; a scatter across
// component rules means the palette stopped being a system somewhere.
const COLOR_LITERAL_THRESHOLD = 30;
function inlineColorCheck(text) {
  const stripped = stripComments(text).replace(
    /(?::root|\[data-theme[^\]]*\]|@theme)[^{]*\{[^{}]*\}/gi,
    (m) => m.replace(/[^\n]/g, ' ')
  );
  const hits = matches(stripped, /#[0-9a-f]{6}\b|#[0-9a-f]{3}\b|\boklch\([^)]*\)/gi);
  if (hits.length <= COLOR_LITERAL_THRESHOLD) return null;
  return {
    id: 'inline-color-literal',
    severity: 'P2',
    label: `${hits.length} opaque colour literals outside :root (>${COLOR_LITERAL_THRESHOLD}) — lift them into named tokens`,
    fix: 'soul',
    total: hits.length,
    hits: hits.slice(0, 8),
  };
}

// preflight.md Gate 1. The page references a local file that isn't there — a
// `<link>` to a stylesheet that was never written, an `<img>` to a missing asset.
// This is the one failure that makes every OTHER check in this file vacuous: a
// page whose stylesheet 404s renders as unstyled Times New Roman, and it will
// pass the grain check, the pure-#fff check and the eyebrow count all the same,
// because none of those rules ever fire on a file that doesn't exist. It is also
// the classic truncated-build tell — the HTML got written, the run ended before
// the CSS did, and nothing downstream noticed. P0, always.
const SKIP_REF = /^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i; // http:, data:, mailto:, tel:, //cdn, #anchor
function deadLocalRefCheck(text, file) {
  const base = dirname(resolve(file));
  const hits = [];
  const seen = new Set();
  const re =
    /(?:\b(?:href|src|poster)\s*=\s*["']([^"']+)["'])|(?:\burl\(\s*["']?([^"')]+)["']?\s*\))/gi;
  let m;
  while ((m = re.exec(text)) !== null) {
    const raw = (m[1] ?? m[2] ?? '').trim();
    if (!raw) continue;
    // Decode BEFORE the skip test. finesse's own grain layer is an inline
    // `url("data:image/svg+xml,…filter='url(%23n)'…")` — the outer ref is skipped
    // as a data: URI, but the regex also matches the *inner* `url(%23n)`, and
    // `%23n` is `#n`, an SVG fragment, not a file. Testing the raw form misses it.
    let ref = raw;
    try {
      ref = decodeURIComponent(raw);
    } catch {
      /* malformed escape — fall through with the raw form */
    }
    if (SKIP_REF.test(ref)) continue;
    if (ref.startsWith('/')) continue; // root-relative — see NOT_COVERED
    if (/[{}$<>]/.test(ref)) continue; // {{tpl}}, ${expr}, <placeholder>
    const path = ref.split(/[?#]/)[0];
    if (!path) continue;
    if (existsSync(resolve(base, path))) continue;
    if (seen.has(path)) continue;
    seen.add(path);
    hits.push({ line: lineOf(text, m.index), text: path });
  }
  if (!hits.length) return null;
  const css = hits.some((h) => /\.css($|[?#])/i.test(h.text));
  return {
    id: 'dead-local-ref',
    severity: 'P0',
    label:
      `${hits.length} local file reference(s) point at nothing on disk` +
      (css ? ' — including a stylesheet, so the page renders unstyled' : '') +
      ': ' +
      hits.slice(0, 4).map((h) => h.text).join(', '),
    fix: 'write the missing file (or fix the path) before delivery',
    total: hits.length,
    hits: hits.slice(0, 8),
  };
}

// ---- run -------------------------------------------------------------------

const report = [];
let p0Count = 0;

for (const file of files) {
  let text;
  try {
    text = readFileSync(file, 'utf8');
  } catch (e) {
    report.push({ file, error: String(e.message || e), findings: [] });
    continue;
  }

  const findings = [];
  for (const rule of RULES) {
    const hits = rule.find(text);
    if (hits.length) {
      findings.push({ id: rule.id, severity: rule.severity, label: rule.label, fix: rule.fix, count: hits.length, hits: hits.slice(0, 8) });
    }
  }
  for (const fn of [
    spectacleCheck,
    reducedMotionCheck,
    eyebrowCheck,
    stampCheck,
    bareFrTrackCheck,
    dualStickyCheck,
    inlineColorCheck,
  ]) {
    const f = fn(text);
    // `total` when the check truncated its own hit list, else the list length.
    // (Reading .hits.length after a slice(0,8) silently reports every finding as
    // exactly 8 — the count must come from before the truncation.)
    if (f) findings.push({ ...f, count: f.total ?? f.hits.length });
  }
  // Needs the file's own path to resolve relative refs, so it can't join the
  // text-only list above.
  const dead = deadLocalRefCheck(text, file);
  if (dead) findings.push({ ...dead, count: dead.total ?? dead.hits.length });

  findings.sort((a, b) => severityRank(a.severity) - severityRank(b.severity));
  p0Count += findings.filter((f) => f.severity === 'P0').length;
  report.push({ file, findings });
}

function severityRank(s) {
  return { P0: 0, P1: 1, P2: 2 }[s] ?? 3;
}

// ---- output ----------------------------------------------------------------

if (asJson) {
  console.log(JSON.stringify({ p0: p0Count, files: report, notCovered: NOT_COVERED }, null, 2));
} else {
  for (const { file, findings, error } of report) {
    const name = basename(file);
    if (error) {
      console.log(`\n✗ ${name} — read error: ${error}`);
      continue;
    }
    if (!findings.length) {
      console.log(`\n✓ ${name} — no regex-detectable slop (visual audit still required)`);
      continue;
    }
    console.log(`\n● ${name} — ${findings.length} finding(s)`);
    for (const f of findings) {
      const where = f.hits.map((h) => (h.line ? `L${h.line}` : '')).filter(Boolean).join(', ');
      console.log(`  [${f.severity}] ${f.label}${f.count > 1 ? ` ×${f.count}` : ''}${where ? `  (${where})` : ''}`);
      console.log(`        → fix with \`${f.fix}\``);
    }
  }
  console.log(`\n${p0Count ? `✗ ${p0Count} P0 finding(s) — ships broken` : '✓ no P0 findings'}`);
  console.log(`\nRegex layer only — still needs a human/Playwright pass for:`);
  for (const c of NOT_COVERED) console.log(`  · ${c}`);
}

// See the exit-code note at the top: default is always 0 so the agent never reads
// a finding as a tool malfunction. Only --strict turns a P0 into a blocking exit.
process.exit(strict && p0Count ? 1 : 0);
