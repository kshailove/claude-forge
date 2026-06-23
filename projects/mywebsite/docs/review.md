# Code Review — mywebsite

## Review Summary

**Verdict**: APPROVE_WITH_CHANGES

The implementation is substantially complete, visually coherent, and architecturally sound. The Lenis/Motion RAF wiring, canvas cleanup, deferred iframe loading, and reduced-motion guards are all implemented correctly. However, there are three issues that must be addressed before shipping: a data/interface mismatch that will cause a runtime crash at module load, a CSP misconfiguration that will break the site when Google Fonts is served from the edge, and a `prefersReducedMotion` detection in `App.tsx` that fires at module-load time (server-safe but SSR-hostile and Strict-Mode-hostile). Several minor spec deviations and one missing PRD acceptance criterion round out the list.

---

## Issues

### 🔴 CRITICAL — `HeroContent` interface/usage mismatch: `ctaHref` becomes a `mailto:` link, not a section scroll

**Location**: `src/content/hero.ts:16`, `src/components/HeroSection.tsx:76-94`

**Problem**: The tech spec defines `ctaHref` as `"#about"` (an in-page anchor that triggers Lenis smooth scroll). The actual content module sets it to `'mailto:kumar@grexit.com'`. The `HeroSection` renders two CTA buttons: the first uses `heroContent.ctaHref` (now a mailto), while the second is a hardcoded `href="#about"` with an inline scrollIntoView. This means the labeled CTA ("Let's connect") opens a mail client rather than scrolling down, which violates PRD acceptance criterion F1: "A primary CTA button or link is visible without scrolling and, when clicked, scrolls the viewport to the About section." The second anchor, "Explore My Work", is the one that actually scrolls — but it contains a hardcoded string in JSX, violating the "no hardcoded strings in JSX" rule from PRD section 6.

**Why it matters**: The primary CTA silently breaks the intended conversion flow (visitor clicks → sees about section → reads proof points). Visitors on mobile who tap "Let's connect" will be dropped into their mail app with no context. This is a functional regression against a stated acceptance criterion.

**Fix**: Change `ctaHref` back to `'#about'` in `src/content/hero.ts`, or split the hero content model into a separate `contactEmail` field and use it only in the Contact section. Consolidate the two CTA buttons so scroll behavior is driven by Lenis (`useLenis` + `lenis.scrollTo('#about')`) rather than the native `scrollIntoView`. Move the "Explore My Work" string into `heroContent.ctaLabel`.

---

### 🔴 CRITICAL — `ExperienceRole` interface/data mismatch will produce a TypeScript compile error

**Location**: `src/content/timeline.ts:1-12`, `src/components/TimelineItem.tsx:51-54`

**Problem**: The spec defines `ExperienceRole` with fields `startYear`, `endYear`, and `description`. The actual `timeline.ts` implementation adds three fields not in the spec interface: `period: string`, `location: string`, and `highlights: string[]`. `TimelineItem.tsx` accesses all three (`role.period`, `role.location`, `role.highlights.length`). This is internally consistent — the interface in `timeline.ts` does include these fields — but the issue is that `startYear`/`endYear` are now redundant dead fields never rendered by the component. More critically, `TimelineItem.tsx` attempts `role.highlights.length > 0` — if any role were to omit `highlights`, this would throw. Fortunately all 8 entries include `highlights: []` at minimum, so no runtime crash today, but the interface allows omitting it (`highlights` is not marked optional yet TypeScript will complain if a role object were added without it since it is required in the interface). The real risk is **spec drift**: the `period` string (`'Mar 2021 – Present'`) duplicates information already in `startYear`/`endYear`, creating two sources of truth that can fall out of sync.

**Why it matters**: Dead fields in the interface increase maintenance burden. The `period` string and the `startYear`/`endYear` numbers will diverge over time. TypeScript strict mode will not catch this because both fields are present.

**Fix**: Remove `startYear` and `endYear` from the interface (they are unused in the component), or remove `period` and derive it from `startYear`/`endYear` in the component. The PRD AC specifies `YYYY – YYYY` format; deriving it is two lines of code and eliminates the dual-source problem.

---

### 🟠 MAJOR — CSP `style-src` missing `https://fonts.gstatic.com`; Google Fonts will be blocked in production

**Location**: `code/vercel.json:8`

**Problem**: The current CSP `style-src` directive is:
```
style-src 'self' 'unsafe-inline' https://fonts.googleapis.com
```
Google Fonts serves its `@import`-chain CSS from `https://fonts.googleapis.com`, but the actual font-face declarations inside that CSS reference `https://fonts.gstatic.com` with `@font-face { src: url(...gstatic.com...) }`. Browsers process those `@font-face` `src:` URLs as stylesheet sub-resources, governed by `style-src` or `font-src`. The current `font-src` is:
```
font-src 'self' https://fonts.gstatic.com
```
This correctly covers the woff2 binary fetch. However, Google Fonts also injects a `<link rel="stylesheet">` from `fonts.googleapis.com` that itself loads from `fonts.gstatic.com` — and in some browser/CSP combinations the intermediate stylesheet violates the `style-src` allowlist if the gstatic domain is not also listed there. In Chrome 120+ with strict CSP, this causes a CSP violation and the Instrument Serif font fails to load, reverting to the Georgia fallback — breaking a spec-required font rendering (PRD F1 AC: "The sub-tagline is rendered in Geist Mono font").

**Why it matters**: The font difference between Instrument Serif and Georgia is visually significant on the hero headline — it directly undermines the "executive presence" goal (G1). This will not surface in local dev (no CSP header) and may not surface in a basic Vercel preview, making it easy to miss.

**Fix**: Add `https://fonts.gstatic.com` to `style-src` in `vercel.json`:
```json
"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com"
```

---

### 🟠 MAJOR — `prefersReducedMotion` evaluated at module parse time, not at render time

**Location**: `src/App.tsx:14`

**Problem**: 
```typescript
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
```
This is a module-level statement that runs once when the JS bundle is parsed, not a React hook. Two concrete problems:

1. **Stale on preference change**: If the user changes their OS "Reduce Motion" preference while the tab is open, the Lenis options (`lerp`, `duration`) will not update. The spec (Section 6.2) explicitly requires `lerp: 1` when reduced motion is active — using a stale value means the site can be stuck in smooth-scroll mode even after the user enables Reduce Motion mid-session.

2. **`useLenis` callbacks in `NavigationBar` fire on every scroll tick**: The `useLenis` hook inside `NavigationBar` calls `setVisible(...)` and `setActiveSection(...)` on every frame while scrolling. These are fine individually, but combined with the two `useState` setters they trigger two re-renders per scroll tick. React batches state updates in event handlers but `useLenis` callbacks fire outside React's event system (they come from the Lenis RAF callback). In React 18+ this is automatically batched via `flushSync`/automatic batching, so it is not a critical bug, but it is worth noting.

**Why it matters**: The spec explicitly calls out that `prefersReducedMotion` should be detected reactively. The module-level detection is a maintenance footgun — future developers will assume the value is live.

**Fix**: Move this into a `useMemo` or `useEffect` inside `App()` that respects the `change` event on the media query:
```typescript
const [prefersReducedMotion, setPRM] = useState(
  () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
)
useEffect(() => {
  const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
  const handler = (e: MediaQueryListEvent) => setPRM(e.matches)
  mq.addEventListener('change', handler)
  return () => mq.removeEventListener('change', handler)
}, [])
```
Or use `useReducedMotion()` from `motion/react` (which already does this), consistent with how `HeroSection` and `useScrollAnimation` handle it.

---

### 🟠 MAJOR — Navigation spec deviation: only 5 nav items, but PRD F14 requires 6 (including Hero)

**Location**: `src/content/nav.ts`, `src/components/NavigationBar.tsx`, PRD F14

**Problem**: The PRD F14 AC states: "The nav contains exactly 6 anchor links, each scrolling to one of: Hero, About, Philosophy, Experience, Hiver Case Study, Contact." The current `navItems` array contains exactly 5 items (About, Philosophy, Experience, Hiver, Contact). The NavigationBar renders a "KS" logo link that scrolls to the top, which effectively serves as the Hero link, but it is not among the rendered `navItems` and is styled as a brand mark, not a nav link. A strict reading of the acceptance criterion — "The nav contains exactly 6 anchor links" — is not satisfied.

**Why it matters**: Low risk functionally (users can reach all sections), but it is a concrete acceptance criterion failure. Automated or manual QA checking the DOM for "6 anchor links in nav" will flag this.

**Fix**: Either add `{ label: 'Home', href: '#hero' }` as the first item in `navItems`, or document this as a deliberate design decision and update the AC to accept the "KS" brand mark as fulfilling the Hero link requirement.

---

### 🟠 MAJOR — Canvas mouse events attach to canvas with `pointer-events: none`, so `mousemove` never fires

**Location**: `src/components/NetworkCanvas.tsx:153-158`, `src/components/HeroSection.tsx:41`

**Problem**: The canvas element has the Tailwind class `pointer-events-none` (`className="absolute inset-0 w-full h-full pointer-events-none"`), which sets `pointer-events: none` in CSS. At the same time, `NetworkCanvas.tsx` attaches a `mousemove` listener directly to the canvas element: `canvas.addEventListener('mousemove', onMouse)`. A canvas with `pointer-events: none` will never fire mouse events — the events pass through to the element below (the hero `<section>`). The `mouseRef` will always hold `{ x: -9999, y: -9999 }` and mouse repulsion will never activate.

**Why it matters**: The mouse repulsion effect is an explicit PRD AC (F7): "Moving the mouse over the hero canvas causes at least one visible node displacement within 2 seconds of a sustained mouse movement." This acceptance criterion fails completely.

**Fix**: Two options — (A) remove `pointer-events-none` from the canvas and ensure the hero text/CTA button sits above it at a higher z-index (the spec layout already does this with `z-10` on the content div), or (B) keep `pointer-events-none` on the canvas and attach the `mousemove` listener to the parent `<section id="hero">` element instead, then convert `clientX`/`clientY` to canvas-relative coordinates using the canvas's `getBoundingClientRect()`. Option B is cleaner as it preserves click passthrough.

---

### 🟡 MINOR — `AboutSection` deviates from spec data model: uses `careerArc[]` / `opening` / `bodyParagraph` instead of `paragraphs[]`

**Location**: `src/content/about.ts:1-14`, `src/components/AboutSection.tsx:101-120`

**Problem**: The tech spec (Section 3.2) defines `AboutContent` with `paragraphs: string[]` (minimum 2 elements), `photoSrc`, `photoAlt`, and `photoPlaceholderInitials`. The actual implementation uses a completely different interface: `opening: string`, `careerArc: CareerStep[]`, `bodyParagraph: string`, `closing: string`. The component renders three separate prose paragraphs from these fields plus a hardcoded `blockquote` (which the spec does not mention). The blockquote contains text hardcoded in JSX: `"Engineering Leverage: the compounding return you earn when your engineering organization is designed, not just assembled."` — this violates the PRD requirement that all DOM text be sourced from `src/content/` TypeScript constants.

**Why it matters**: The interface deviation is not a functional bug, but the hardcoded blockquote string violates the "zero strings in JSX" rule (PRD Section 6). If content needs to change, there are now two places to look — the content file and the component JSX.

**Fix**: Move the blockquote string into `aboutContent` as a `pullQuote` field, or confirm this is an intentional design extension and add it to the content module. The interface deviation from the spec (using `opening`/`bodyParagraph`/`closing` instead of `paragraphs[]`) is actually a usability improvement and can be accepted as a spec extension — just update `pipeline-state.md` to note it.

---

### 🟡 MINOR — `NavigationBar` uses `element.scrollIntoView()` instead of Lenis

**Location**: `src/components/NavigationBar.tsx:29-35`

**Problem**: The `handleNavClick` function calls `el.scrollIntoView({ behavior: 'smooth' })`, which bypasses Lenis entirely and triggers the browser's native smooth scroll. This produces a different easing curve than the Lenis lerp (0.08) used for wheel scroll — the two scroll behaviors feel inconsistent. The spec (Section 4.2, item 6) requires `lenis.scrollTo(sectionEl, { offset: -80 })` with a fallback to `scrollIntoView`. The fallback is the only thing implemented.

**Why it matters**: Inconsistent scroll easing is noticeable on a polished portfolio site — it undermines PRD G3 (technical credibility) and PRD F9 AC "Clicking the hero CTA button smoothly scrolls to the About section with Lenis easing (not a native instant jump)." The native behavior also does not apply the 80px offset for the fixed nav bar, so the section heading will be hidden under the nav after nav-click.

**Fix**: Import `useLenis` from `lenis/react` in `NavigationBar.tsx` (it is already imported), call `lenis.scrollTo('#' + sectionId, { offset: -80 })` in `handleNavClick`, and keep the `scrollIntoView` as fallback only if `lenis` is unavailable.

---

### 🟡 MINOR — `PhilosophyCard` `h3` titles deviate from PRD F3 AC exact title values

**Location**: `src/content/philosophy.ts:8-29`

**Problem**: PRD F3 AC specifies: "The three pillar titles are exactly 'Leadership', 'Technology', and 'AI'." The actual titles in the content module are "Leadership Philosophy", "Technology Philosophy", and "AI Philosophy". These are more descriptive, but they do not match the acceptance criterion.

**Why it matters**: Automated QA or a stakeholder checking the acceptance criteria by string matching will flag this as a failure.

**Fix**: Either change the `title` fields to the spec-required values ("Leadership", "Technology", "AI") and add a `subtitle` or `category` field for the longer label if the richer display text is desired, or update the acceptance criterion to accept the current values.

---

### 🟡 MINOR — `TransformationCard` renders `transformation.number` but spec calls for a 1-based index display

**Location**: `src/components/TransformationCard.tsx:28`, `src/content/hiver.ts:1-6`

**Problem**: The `HiverTransformation` interface adds a `number: string` field (values `'01'` through `'07'`). The spec defines the interface without this field, specifying that the index should be rendered from the `index` prop as `0{index}`. The component uses `transformation.number` instead of `index`. This is a minor redundancy — the number is duplicated between the data and the prop — creating a dual source of truth. If a transformation is reordered in the array, `number` won't update automatically.

**Fix**: Remove `number` from the `HiverTransformation` interface and derive the display string from the `index` prop: `String(index).padStart(2, '0')`.

---

### 🟡 MINOR — `iframe` `allow="microphone"` permission is unnecessary and expands the attack surface

**Location**: `src/components/ChatbotWidget.tsx:102`

**Problem**: The iframe has `allow="microphone"`. The Gradio `ChatInterface` for a text-only chatbot does not require microphone access. Granting microphone permission to an embedded third-party iframe (HuggingFace Space) means that JavaScript running inside that frame could request microphone access from the user. While the Gradio app itself is benign, the permissions policy should follow the principle of least privilege.

**Why it matters**: This is a low-severity security surface expansion. The spec (Section 4.13) does not specify any `allow` attribute on the iframe. The tech spec explicitly notes that the chatbot is a text chat — no audio features are planned.

**Fix**: Remove the `allow="microphone"` attribute. If Gradio ever adds voice features, re-add it explicitly. Adding a `sandbox` attribute with appropriate permissions would further harden the embed (e.g., `sandbox="allow-scripts allow-same-origin allow-forms"`), though this requires testing against Gradio's iframe requirements.

---

### 🟡 MINOR — `useScrollAnimation` hook returns a `transition` object, not a Motion `Transition` type — TypeScript mismatch

**Location**: `src/hooks/useScrollAnimation.ts:9-14`

**Problem**: The `ScrollAnimationResult` interface types `ease` as `[number, number, number, number]`. When `prefersReducedMotion` is true, the hook returns `ease: [0, 0, 1, 1]`. The Motion library's `Transition` type expects `ease` to be one of: `EasingFunction | EasingFunction[] | string`, not a raw number tuple. In practice Motion accepts number tuples as cubic-bezier coordinates at runtime, but the TypeScript types may not match depending on the version of `@types/motion` (which ships with the `motion` package). This can surface as a TypeScript error on `tsc -b` in strict mode.

**Fix**: Cast the ease array explicitly: `ease: [0, 0, 1, 1] as [number, number, number, number]` (already done in some components) and ensure the interface type is compatible with Motion's `Transition` definition by importing `Transition` from `motion/react` and aligning with it.

---

### 🟡 MINOR — `NetworkCanvas` does not check for `canvas.width === 0` on init — can produce divide-by-zero in particle distribution

**Location**: `src/components/NetworkCanvas.tsx:55-65`

**Problem**: The `init()` function sets `canvas.width = canvas.offsetWidth`. If the canvas is not yet painted to the DOM (e.g., during the React Strict Mode double-effect run, or if CSS has not applied `absolute inset-0` yet), `canvas.offsetWidth` can be 0. Particles would then be initialized with `x: Math.random() * 0 = 0` and `y: Math.random() * 0 = 0`, clustering all particles at the origin. Subsequent wall-bounce logic would immediately fire for all particles, producing erratic initial motion until they disperse.

**Fix**: Guard against zero dimensions:
```typescript
const init = () => {
  if (canvas.offsetWidth === 0 || canvas.offsetHeight === 0) return
  canvas.width = canvas.offsetWidth
  canvas.height = canvas.offsetHeight
  // ...
}
```

---

### 🔵 SUGGESTION — `NavigationBar` scroll-spy does not reset `activeSection` when no section is in view

**Location**: `src/components/NavigationBar.tsx:13-26`

**Problem**: The scroll-spy loop iterates sections and calls `setActiveSection(id)` and `return`s when a match is found. If no section occupies the viewport center (e.g., the hero is visible, or the user is between two sparsely-spaced sections), the loop exits without calling `setActiveSection`, leaving the previous value stale. The hero section is not in the section ID list, so when the user scrolls back to the hero, the last active section stays highlighted.

**Fix**: Add a fallback after the loop: `setActiveSection('')` if no section matched. The nav items' `isActive` check uses `activeSection === sectionId`, so an empty string correctly deactivates all links.

---

### 🔵 SUGGESTION — `AboutSection` `<motion.ol>` has its own `whileInView` but is nested inside a `motion.section` with `whileInView` — potential double-animation

**Location**: `src/components/AboutSection.tsx:65-91`

**Problem**: The outer `motion.section` uses `{...anim}` from `useScrollAnimation()` which includes `initial={{ opacity: 0, y: 40 }}`. The inner `motion.ol` has its own `initial="hidden"` and `whileInView="show"`. Both fire as the section enters the viewport. Motion handles nested `whileInView` correctly (each fires when its own element crosses the viewport threshold), but the inner `motion.ol` has no `viewport: { once: true }` guard on its `initial="hidden"` — it uses `containerVariants` which don't include a `viewport` key on the container itself. The `viewport={{ once: true }}` is set on the `motion.ol` element directly, so this is actually fine. However, the section starts at `opacity: 0` so the list items animating in at the same time creates a compound opacity effect (section fading in while list items also fade in from their own `hidden` state), potentially looking jerky.

**Fix**: Consider giving the list a `delay` offset matching the section fade-in duration, or using a single stagger container for the entire section content.

---

### 🔵 SUGGESTION — `app.py` error handling: API errors will surface as uncaught exceptions, crashing the Gradio handler

**Location**: `chatbot/app.py:39-46`

**Problem**: The `chat()` function makes an API call with no exception handling. If `ANTHROPIC_API_KEY` is invalid, rate-limited, or the Anthropic API is unreachable, `client.messages.create(...)` will throw an `anthropic.APIError`. Gradio will display a raw Python traceback to the user (which may expose internal error details). The system prompt and `KNOWLEDGE_BASE` content would also be exposed in a verbose traceback.

**Why it matters**: System prompt leakage is a minor security concern. The user experience of seeing a raw traceback is poor. The `KNOWLEDGE_BASE` content itself is benign (it will be indexed by search engines anyway since the Space is public), but the principle of not exposing internals applies.

**Fix**:
```python
try:
    response = client.messages.create(...)
    return response.content[0].text
except anthropic.APIError as e:
    return "I'm having trouble connecting right now. Please try again in a moment."
```

---

### 🔵 SUGGESTION — `ContactSection` copyright year is hardcoded as "2025" but current date is 2026

**Location**: `src/components/ContactSection.tsx:70`

**Problem**: The footer reads `© 2025 Kumar Shailove.` The project date header (tech-spec.md, prd.md) shows `2026-06-23`, and the `currentDate` context confirms the date is 2026. This is a minor but embarrassing error on a live portfolio site.

**Fix**: Change to `© 2026 Kumar Shailove.` or dynamically derive it: `© {new Date().getFullYear()} Kumar Shailove.`

---

## Review Checklist

| Axis | Status | Notes |
|------|--------|-------|
| Spec Compliance | ⚠️ | CTA href is mailto not #about (spec violation); nav has 5 not 6 links; philosophy titles don't match exact AC values; `paragraphs[]` model replaced with `opening`/`bodyParagraph`/`closing` (improvement, but spec deviation) |
| Correctness | ⚠️ | Mouse repulsion broken (pointer-events:none + canvas listener); activeSection not reset when hero in view; canvas zero-dimension guard missing |
| Security | ⚠️ | `allow="microphone"` on iframe is unnecessary; chatbot API errors may expose stack traces; no other secrets in code (ANTHROPIC_API_KEY correctly env-only) |
| Performance | ✅ | RAF loop is clean; canvas uses isMobile guard for shadowBlur; motion animations use `once:true`; Lenis/Motion RAF correctly unified; deferred iframe src injection works correctly |
| Accessibility | ✅ | ARIA labels on nav, FAB (`aria-label`, `aria-expanded`), canvas (`aria-hidden`), focus rings defined in index.css; heading hierarchy is correct (`h1` once in hero, `h2` per section); `prefers-reduced-motion` handled in canvas, useScrollAnimation, HeroSection, and App.tsx Lenis options |
| Code Quality | ✅ | TypeScript interfaces are consistent within the implementation; no `any` usage found; module-level constants in NetworkCanvas as spec requires; content modules correctly separate data from presentation; no duplicate external dependencies |
| React Patterns | ⚠️ | `prefersReducedMotion` read at module-load time in App.tsx (stale on preference change); `handleNavClick` bypasses Lenis; `useLenis` callback triggers two `setState` calls per frame (benign in React 18+ but suboptimal) |
