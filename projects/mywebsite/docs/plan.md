# Stage 2 Project Plan — Kumar Shailove Personal Portfolio Website

**Date:** 2026-06-23
**Prepared by:** ClaudeForge Plan Agent (Stage 2)
**Project:** `projects/mywebsite`
**Inputs:** `docs/research.md`, `projects/mywebsite/brief.md`

---

## 1. Project Goals

### Primary Goal

Ship a single-page personal portfolio website that establishes Kumar Shailove as a credible VP Engineering / CTO / fractional CTO candidate in the eyes of founders and boards — communicating strategic depth, technical sophistication, and a coherent leadership philosophy within the first 10 seconds of arrival.

### Measurable Success Metrics

| Metric | Target | How Measured |
|--------|--------|--------------|
| Time-to-meaningful-content | < 2s on broadband | Lighthouse Performance score ≥ 90 |
| Core Web Vitals | LCP < 2.5s, CLS < 0.1, INP < 200ms | Lighthouse / PageSpeed Insights |
| Mobile usability | All sections navigable on 375px+ viewport | Manual QA on iOS Safari + Chrome Android |
| Animation accessibility | Reduced-motion mode: static, no broken layout | Manual + `prefers-reduced-motion` media query check |
| Chatbot cold-start UX | User sees loading feedback within 200ms of opening widget | Visual inspection |
| Canvas frame rate | ≥ 55fps on M1 Mac in Chrome | Chrome DevTools Performance panel |
| Zero console errors | Clean console on first load | Manual check in 3 browsers |
| Deployed URL live | kumarshailove.com (or equivalent) resolves with HTTPS | Curl / browser check |

---

## 2. Scope

### In Scope — V1

- **Vite + React 19 + TypeScript** single-page application scaffolded with `npm create vite@latest`
- **Six page sections** (in scroll order):
  1. Hero — full-viewport, canvas background, headline + tagline, name + CTA
  2. About / Narrative — career arc in prose, profile photo placeholder
  3. Philosophy — 3 leadership pillars with quoted text
  4. Experience Timeline — 8 career roles (2004–present), Quark → Adobe → Expedia → Armor5 / Digital Guardian → InMobi → Hiver
  5. Hiver Case Study — 7 signature transformations from the Executive Narrative
  6. Contact — simple contact prompt (email / LinkedIn links); no form backend
- **Canvas network background** — hand-rolled `<NetworkCanvas>` component, ~100 lines, hero section only, mouse repulsion, mobile-reduced particle count
- **Lenis smooth scroll** — `ReactLenis` with `autoRaf: false`, driven by Motion's `frame.update()` — wired at project start
- **Motion v12 animations** — `whileInView` scroll reveals, stagger children for timeline + philosophy pillars, parallax depth on hero canvas
- **Tailwind CSS v4** — `@tailwindcss/vite` plugin, `@theme {}` token system, no `tailwind.config.js`
- **Typography** — Instrument Serif (Google Fonts, regular + italic only) for headings; Geist Mono (`@fontsource-variable/geist-mono`) for labels, roles, metadata
- **Chatbot widget** — bottom-right expandable FAB; iframe embeds HuggingFace Space; deferred `src` injection on open; loading skeleton with estimated wait message
- **HuggingFace Space** — `app.py` (Gradio `ChatInterface` + Anthropic SDK + `claude-sonnet-4-6`), `requirements.txt`, `knowledge_base.md` populated from Executive Narrative
- **All text as TypeScript constants** — `src/content/` directory; zero hardcoded strings in component JSX
- **Custom hooks** — `useLenis` (scroll event subscription), `useScrollAnimation` (wraps `useInView` / `whileInView` patterns)
- **Responsive layout** — mobile-first, functional from 375px; tablet + desktop breakpoints
- **Reduced-motion support** — static gradient fallback for canvas; no scroll-triggered reveals that block content
- **Deployment** — static site deploy to Vercel (primary) or Netlify; custom domain setup instructions
- **Git commits** after each pipeline stage artifact

### Out of Scope — V1

- Testimonials / recommendations section (explicitly deferred per brief)
- Contact form with server-side email delivery
- Blog or writing section
- Analytics / tracking integration
- CMS or headless content layer
- Password-protected sections
- Dark/light mode toggle (dark-only in V1)
- PDF resume download
- Internationalization
- Social graph meta tags (Open Graph, Twitter Card) — V2 polish
- Rate limiting on the Gradio chatbot endpoint
- HuggingFace Space upgrade to paid tier (warm instance)
- Automated accessibility audit (WCAG AA full compliance)

### Deferred — V2+

- Testimonials section (once Kumar collects written recommendations)
- Blog / writing section
- Light mode / theme toggle
- Open Graph + Twitter Card meta for social sharing
- Contact form with email delivery (Resend or Formspree)
- Rate limiting / referrer check on Gradio chatbot
- HuggingFace Spaces upgrade to prevent cold starts ($0.05/hr CPU Upgrade)
- Portfolio analytics (Plausible or Fathom — privacy-first)

---

## 3. User Personas

### Persona 1 — The Evaluating Founder

**Name:** Priya, 38, B2B SaaS founder (Series B, 80 employees)
**Goal:** Considering Kumar for VP Engineering role. Needs to validate strategic depth, leadership credibility, and fit with a scaling org.
**Jobs to be done on this site:**
- Form a quick gut impression of executive presence (first 10 seconds)
- Read enough about past results to trust the "compound value" claim
- Skim the timeline to confirm the right seniority trajectory
- Explore the Hiver case study to see what "at scale" actually looks like
- Contact or ask the chatbot a pointed question ("Has Kumar managed distributed teams?")

**Friction points to avoid:** Dense walls of text, unclear career progression, no concrete metrics, chatbot that fails or times out immediately.

---

### Persona 2 — The Board-Level Evaluator

**Name:** Michael, 52, Operating Partner at a growth-equity fund
**Goal:** Evaluating Kumar as fractional CTO or board-level advisor for a portfolio company. Has 4 minutes. Reads fast.
**Jobs to be done:**
- Rapidly assess whether Kumar is operating-partner caliber or mid-manager caliber
- Confirm domain relevance (SaaS, B2B, India-US orgs)
- Extract 2–3 memorable proof points to share with the founding team
- Save or bookmark for follow-up

**Friction points to avoid:** Slow initial load, animations that delay access to content, missing concrete outcomes (e.g., "grew from X to Y").

---

### Persona 3 — The Technical Co-Evaluator

**Name:** Alex, 34, current CTO of the company hiring Kumar
**Goal:** Assessing whether Kumar is a peer-level technical leader or a "pure manager." Wants evidence of technical philosophy, not just org charts.
**Jobs to be done:**
- Confirm technical credibility through the Philosophy section and Experience details
- Look for signals about how Kumar thinks about engineering culture, AI, and tooling
- Play with the chatbot to see how Kumar's ideas are articulated
- Check that the site itself is technically well-made (a portfolio site that is sloppy undermines the pitch)

**Friction points to avoid:** Philosophy section that reads as generic MBA content, chatbot that gives hallucinated or off-brand answers, broken animations or console errors that a technical eye would catch.

---

## 4. Milestones

Effort estimates are in developer-days (one developer, focused work). These assume the implementer is familiar with React + TypeScript but not necessarily with Motion v12 / Lenis / Tailwind v4 specifically.

### M1 — Foundation (3–4 days)

**Goal:** Working dev environment with all integrations wired correctly. No real content yet.

| Task | Effort |
|------|--------|
| Scaffold Vite + React 19 + TypeScript project | 0.5d |
| Install + configure Tailwind CSS v4 (`@tailwindcss/vite`, `@theme {}` token block) | 0.5d |
| Install Motion v12, Lenis; wire `ReactLenis` with `autoRaf: false` + `frame.update()` driven by Motion | 1d |
| Load fonts (Instrument Serif via Google Fonts, Geist Mono via `@fontsource-variable/geist-mono`) | 0.5d |
| Build `<NetworkCanvas>` component with mouse repulsion + mobile fallback | 1d |
| Stub all 6 section components (empty shells, correct file structure) | 0.25d |
| Populate `src/content/` with all text constants from Executive Narrative | 0.5d |
| Verify: smooth scroll works, canvas renders, fonts load, no console errors | 0.25d |

**Milestone gate:** `npm run dev` loads a dark page, canvas animates in the hero area, scroll is smooth, fonts render correctly.

---

### M2 — Core Sections (4–5 days)

**Goal:** All six sections built with real content. Functional on desktop. No polish animations yet.

| Task | Effort |
|------|--------|
| Hero section — headline, tagline, name, canvas background, CTA button | 1d |
| About / Narrative section — prose layout, profile photo placeholder slot | 0.75d |
| Philosophy section — 3-pillar layout with quoted text | 0.5d |
| Experience Timeline — 8 roles, date range, company, title, 1–2 lines each | 1d |
| Hiver Case Study — 7 transformation cards / list with metrics | 0.75d |
| Contact section — email + LinkedIn links, minimal layout | 0.5d |
| Navigation — sticky or hidden-on-scroll nav bar with section anchors | 0.5d |
| Mobile layout QA pass (375px, 768px breakpoints) | 0.5d |

**Milestone gate:** All sections visible with real text, mobile-responsive, no layout breaks.

---

### M3 — Polish + Chatbot (3–4 days)

**Goal:** Scroll animations live, chatbot embedded and working, visual design locked.

| Task | Effort |
|------|--------|
| Scroll reveal animations — `whileInView` on all sections | 0.75d |
| Stagger children — timeline entries + philosophy pillars | 0.5d |
| Hero parallax — canvas background moves at 0.3× scroll speed | 0.25d |
| `prefers-reduced-motion` audit — static fallbacks for all animations | 0.5d |
| Build HuggingFace Space — `app.py`, `requirements.txt`, `knowledge_base.md` | 1d |
| Build `<ChatbotWidget>` — FAB, expand/collapse, iframe with deferred src, loading skeleton | 0.75d |
| Visual QA pass — typography scale, spacing, color tokens, line heights | 0.5d |

**Milestone gate:** Animations work, chatbot loads and responds (accepting cold-start latency), full design sign-off.

---

### M4 — Deploy (1–2 days)

**Goal:** Site live at production URL, chatbot live on HuggingFace.

| Task | Effort |
|------|--------|
| Production Vite build — `npm run build`, verify output | 0.25d |
| Deploy to Vercel (or Netlify) — connect repo, set build config | 0.25d |
| Custom domain setup + HTTPS verification | 0.5d |
| Set Vercel `frame-src` CSP header to allow `*.hf.space` | 0.25d |
| Deploy HuggingFace Space — push files, set `ANTHROPIC_API_KEY` secret | 0.5d |
| Smoke test: open site on mobile + desktop, test chatbot cold start, verify all anchors | 0.25d |

**Milestone gate:** Live URL, chatbot responds, no broken links, Lighthouse score ≥ 90.

---

**Total estimated effort:** 11–15 developer-days

---

## 5. Key Decisions for the Spec Stage

The spec agent must make the following decisions explicitly before implementation begins. These are left open here because they require either aesthetic judgment or external input that belongs in the spec, not the plan.

### Decision 1 — Color Palette (Exact Tokens)

The research recommends a dark editorial palette with an amber-gold accent (`oklch(0.75 0.15 60)`). The spec must confirm or replace all five `@theme {}` color tokens:
- `--color-bg` (background)
- `--color-surface` (cards, elevated surfaces)
- `--color-text` (primary body text)
- `--color-muted` (secondary labels, captions)
- `--color-accent` (hover states, canvas node color, CTA button)

The spec should also define the canvas node color and edge color as constants in the `NetworkCanvas` component spec.

### Decision 2 — Animation Choreography Specifics

The spec must define:
- Entry delay for hero headline vs. tagline vs. CTA (stagger timing)
- Duration and easing curve for `whileInView` section reveals (research suggests 0.7s, `[0.25, 0.46, 0.45, 0.94]`)
- Stagger interval for timeline items (0.1s vs. 0.15s)
- Parallax ratio for hero canvas (how fast it moves relative to scroll)
- Whether the nav bar fades in on scroll-past-hero or is always visible

### Decision 3 — Chatbot Persona & Knowledge Base Scope

The spec must define:
- The chatbot's name / handle displayed in the widget (e.g., "Ask Kumar's AI", "KS Assistant", unnamed)
- Exactly which sections of the Executive Narrative are included in `knowledge_base.md` (full document vs. curated excerpts to control token cost)
- The 3–5 example questions pre-populated in the Gradio interface
- Response length guideline (research suggests ≤ 200 words — confirm)
- Whether the widget has a custom header/skin or uses Gradio's default `Soft` theme

### Decision 4 — Deployment Target & Domain

The spec must confirm:
- Primary deployment platform (Vercel preferred, Netlify as fallback — same outcome, different CI config)
- Domain name (does Kumar own `kumarshailove.com`? Is there an alternate?)
- Whether a `vercel.json` / `netlify.toml` with CSP headers is included in the repo

### Decision 5 — Navigation Pattern

Two viable options; spec must choose one:
- **Option A (Sticky scroll-spy):** Nav stays visible at top, active section highlighted via scroll position. Simpler, always accessible.
- **Option B (Hidden-until-scroll):** Nav hidden on page load (hero is full-bleed), fades in after scrolling past the hero section. Cleaner hero aesthetic, requires scroll event listener.

The reference site (searchpankaj.com) likely uses Option B given the full-viewport hero pattern. Spec should confirm and provide the scroll threshold value.

---

## 6. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | Lenis + Motion RAF conflict causes scroll jank | Medium | High | Wire `autoRaf: false` + `frame.update()` in M1 before any animation code is written. Do not retrofit. |
| R2 | HuggingFace free tier cold start (10–30s) breaks chatbot UX | High | Medium | Deferred iframe `src` injection on widget open + visible loading skeleton with copy: "Waking up AI assistant (~15s)..." |
| R3 | Canvas `shadowBlur` causes frame drops on mid-range mobile | Medium | Medium | Disable `shadowBlur` on mobile via `window.matchMedia('(hover: none)')`; reduce particle count to 30–40 |
| R4 | Instrument Serif has no bold weight | Certain | Low | Design all headings at ≥ `text-5xl` in regular or italic. Large size provides visual weight without bold. Not a blocker. |
| R5 | Claude API credits exhausted by chatbot abuse | Low | Medium | Set a spending cap on the Anthropic API key; add request counter in `app.py` returning a polite rate-limit message (V1). Full rate limiting deferred to V2. |
| R6 | React Strict Mode double-invoking `useEffect` breaks Lenis | Medium | Medium | Use `ReactLenis` from official `lenis/react` package — it handles cleanup correctly. Do not hand-roll Lenis initialization. |
| R7 | CSP on Vercel blocks the HuggingFace iframe | Medium | High | Add `frame-src https://*.hf.space` to `vercel.json` headers config before deploy. Include this in M4 checklist. |
| R8 | `searchpankaj.com` uses scroll-snap or horizontal layout not replicable | Low | Medium | Design is independently specified based on the confirmed tech stack. Horizontal/snap scroll is explicitly out of scope V1. |

---

## 7. Dependencies & Assumptions

### External Dependencies

| Dependency | Status | Owner | Risk if Missing |
|-----------|--------|-------|----------------|
| HuggingFace account (username: `kumarshailove`) | Assumed exists | Kumar | Cannot deploy chatbot backend |
| Anthropic API key with available credits | Assumed available | Kumar | Chatbot non-functional |
| Custom domain (`kumarshailove.com` or alternate) | Unknown — needs confirmation | Kumar | Site deploys to `*.vercel.app` URL only |
| Profile photograph (high-res, professional) | Not yet provided | Kumar | About section uses placeholder until supplied |
| Executive Narrative PDF (already read) | Available at `projects/mywebsite/` | Kumar | Content exists; all 8 roles + philosophy + Hiver case study extracted |

### Technical Assumptions

- The Vite + React 19 template ships TypeScript strict mode — all components must type-check without `any` escapes in component props
- `@tailwindcss/vite` v4 eliminates the need for PostCSS — no `postcss.config.js` will be created
- `lenis/react` (the official React wrapper) is used — not hand-rolled initialization inside `useEffect`
- Motion v12 import is `from 'motion/react'` — no legacy `framer-motion` imports
- The portfolio is a static site (no server-side rendering, no API routes in the React app) — Vite's `npm run build` output is the deployable artifact
- Gradio `type="messages"` (OpenAI-style message dicts) is used in `ChatInterface` — not the deprecated `tuples` format
- The HuggingFace Space is public (not gated) so the iframe embed works without authentication
- Kumar approves the chatbot persona and knowledge base content before M3 completes

### Content Assumptions

- Hero headline is confirmed: "I build engineering organizations that compound business value."
- Sub-tagline is confirmed: "Engineering Organizations. Engineering Leaders. Engineering the Future."
- All 8 career roles (companies, titles, approximate date ranges) are available in the Executive Narrative
- The 7 Hiver signature transformations are sufficiently documented in the Executive Narrative to populate the case study section without additional input from Kumar
- The 3 philosophy pillar quotes are finalized in the Executive Narrative (Leadership, Technology, AI)
- No legal review of content is required before launch

---

*Plan complete. Artifact: docs/plan.md*
