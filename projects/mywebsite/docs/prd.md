# Product Requirements Document — Kumar Shailove Personal Portfolio Website

**Version:** 1.0  
**Stage:** 3 — PRD  
**Date:** 2026-06-23  
**Prepared by:** ClaudeForge PRD Agent (Stage 3)  
**Project:** `projects/mywebsite`  
**Inputs:** `projects/mywebsite/brief.md`, `projects/mywebsite/docs/research.md`, `projects/mywebsite/docs/plan.md`

---

## Table of Contents

1. [Overview](#1-overview)
2. [Goals & Non-Goals](#2-goals--non-goals)
3. [User Personas](#3-user-personas)
4. [Features](#4-features)
5. [Key User Flows](#5-key-user-flows)
6. [Data Requirements](#6-data-requirements)
7. [Non-Functional Requirements](#7-non-functional-requirements)
8. [Open Questions for the Spec Stage](#8-open-questions-for-the-spec-stage)

---

## 1. Overview

Kumar Shailove is a senior technology executive (CEO, CPO, CRO experience spanning 2004–present) who needs a personal portfolio website that communicates executive presence, technical sophistication, and a coherent leadership philosophy to founders, boards, and technical leaders considering him for VP Engineering, CTO, or fractional CTO engagements.

The site is a dark-themed, single-page React application with six content sections, ambient canvas animation, scroll-driven Motion animations, Lenis smooth scroll, and an expandable chatbot widget in the bottom-right corner backed by a HuggingFace Spaces Gradio application powered by `claude-sonnet-4-6`.

The site must load fast, look authoritative, and let any visitor — whether they have 90 seconds or 4 minutes — leave with a clear, confident impression of who Kumar is and what he has delivered.

---

## 2. Goals & Non-Goals

### Goals

- **G1 — Executive presence in <10 seconds.** A first-time visitor landing on the hero must immediately read Kumar as an operating-partner-caliber executive, not a mid-level manager.
- **G2 — Evidence of results, not just roles.** Every section must carry at least one concrete, quantified proof point from Kumar's career that a founder or board member would find memorable.
- **G3 — Technical credibility signal.** The site itself (code quality, animation, performance) must serve as a portfolio artifact. A technical co-evaluator who reads a production build should find nothing sloppy.
- **G4 — Zero-friction chatbot entry.** Visitors who want to go deeper must be able to open a chatbot widget and ask a direct question without leaving the page.
- **G5 — Live, shareable URL within the first deployment.** The site deploys to Vercel (`*.vercel.app`) and is accessible via HTTPS on any device within V1.

### Non-Goals (V1)

- **NG1** — No testimonials section. Explicitly deferred to V2.
- **NG2** — No custom domain. Site deploys to `*.vercel.app`.
- **NG3** — No contact form or email backend. Contact section provides email and LinkedIn links only.
- **NG4** — No light mode toggle. Dark theme only.
- **NG5** — No blog, writing, or long-form content section.
- **NG6** — No analytics or tracking integration.
- **NG7** — No PDF resume download.
- **NG8** — No rate limiting on the Gradio chatbot endpoint (deferred to V2).
- **NG9** — No Open Graph or Twitter Card meta tags (deferred to V2).
- **NG10** — No full WCAG AA compliance audit (reduced-motion and semantic HTML are in scope; full audit is not).

---

## 3. User Personas

Three personas are defined and used to drive feature prioritization and acceptance criteria. Full persona detail is in `projects/mywebsite/docs/plan.md` Section 3.

| # | Name | Role | Time Budget | Primary Job-to-be-Done |
|---|------|------|-------------|------------------------|
| P1 | Priya | Series B SaaS founder evaluating Kumar for VP Eng | 5–10 min | Validate strategic depth, confirm results at scale, find a way to follow up |
| P2 | Michael | Operating partner at growth-equity fund | 4 min max | Rapidly assess operating-partner caliber, extract 2–3 proof points, save for follow-up |
| P3 | Alex | Current CTO of the hiring company | 5–8 min | Confirm peer-level technical philosophy, probe chatbot, verify the site itself is technically clean |

---

## 4. Features

---

### F1: Hero Section

**Priority:** Must-have

**Description:**  
Full-viewport opening section. Canvas particle network occupies the entire background. The section contains Kumar's full name in large Instrument Serif italic, the primary headline, the sub-tagline in Geist Mono, and a primary CTA button that scrolls the user to the About section. The section occupies exactly 100vh and is the first thing every visitor sees.

**User Story:**  
As Priya (P1), I want to immediately read a confident, specific claim about Kumar's value so that I can decide in the first 10 seconds whether this is worth my time.

**Acceptance Criteria:**
- [ ] The section renders at exactly `100vh` on initial load with no vertical scroll bar visible in the viewport.
- [ ] The name "Kumar Shailove" is rendered in Instrument Serif at ≥ `6xl` (60px) on desktop (≥ 1024px viewport).
- [ ] The headline "I build engineering organizations that compound business value." is present in the DOM and visible without scrolling on all viewport widths ≥ 375px.
- [ ] The sub-tagline "Engineering Organizations. Engineering Leaders. Engineering the Future." is rendered in Geist Mono font (verified by computed font-family in DevTools).
- [ ] A primary CTA button or link is visible without scrolling and, when clicked, scrolls the viewport to the About section (within ±50px of the About section's top edge).
- [ ] The canvas background is visible behind all text content (verified by z-index: canvas is behind text container).
- [ ] All hero text elements have sufficient contrast — text color has a contrast ratio ≥ 4.5:1 against the canvas/background layer (measured with the browser's accessibility inspector).
- [ ] The photo slot is present in the DOM but displays a placeholder (gray block or initials) if `public/images/profile.jpg` is absent.

---

### F2: About / Narrative Section

**Priority:** Must-have

**Description:**  
Multi-paragraph prose section narrating Kumar's career arc: from his early engineering roots through his executive roles at InMobi and Hiver. Includes a profile photo (or placeholder). The narrative establishes the "compound business value" thesis with concrete context.

**User Story:**  
As Michael (P2), I want to read a concise career narrative with specific company names and outcomes so that I can form an opinion about Kumar's operating-partner caliber within 90 seconds.

**Acceptance Criteria:**
- [ ] The section contains at least 2 paragraphs of prose narrative sourced from `src/content/about.ts`.
- [ ] At least one paragraph references a named company and a quantified outcome (e.g., a revenue figure, team size, or percentage change) from the Executive Narrative.
- [ ] A profile photo `<img>` element is present with `alt` text of "Kumar Shailove".
- [ ] When `public/images/profile.jpg` is absent, the `<img>` tag is replaced by a visible placeholder element of the same dimensions (not a broken-image icon).
- [ ] The section is readable on a 375px-wide viewport with no horizontal scroll.
- [ ] All text in this section is sourced from TypeScript constants in `src/content/` — no hardcoded strings in JSX.

---

### F3: Philosophy Section

**Priority:** Must-have

**Description:**  
Three philosophy pillars — Leadership, Technology, AI — each with a short title, a descriptive paragraph, and a pull-quote. Arranged in a grid or column layout that presents all three pillars without requiring scrolling past the section boundary on desktop (≥ 1280px).

**User Story:**  
As Alex (P3), I want to read Kumar's stated philosophy on leadership, technology, and AI so that I can judge whether his thinking is peer-level or generic.

**Acceptance Criteria:**
- [ ] Exactly 3 philosophy pillars are rendered.
- [ ] Each pillar has: a title (≥ `text-xl`), a descriptive body paragraph, and a distinct pull-quote styled differently from body text (e.g., italic, larger font, or decorative quotation mark).
- [ ] The three pillar titles are exactly "Leadership", "Technology", and "AI" (or the exact equivalents from the Executive Narrative).
- [ ] On desktop viewports ≥ 1280px, all 3 pillars are visible without scrolling within the section (side-by-side or comparable layout).
- [ ] On mobile viewports ≤ 768px, pillars stack vertically with ≥ 32px gap between them.
- [ ] All content is sourced from `src/content/philosophy.ts`.

---

### F4: Experience Timeline

**Priority:** Must-have

**Description:**  
Chronological timeline of Kumar's 8 career roles from 2004 to present. Each entry shows: company name, role title, date range, and 1–2 lines of context. Entries are ordered newest-first (most recent at the top). A visual timeline indicator (line, dot, or similar) connects entries.

**User Story:**  
As Priya (P1), I want to scan Kumar's career trajectory quickly so that I can confirm the seniority level and progression match what I need for my VP Eng hire.

**Acceptance Criteria:**
- [ ] Exactly 8 timeline entries are rendered.
- [ ] Each entry contains: company name, role title, and a date range in the format `YYYY – YYYY` or `YYYY – Present`.
- [ ] The most recent role appears at the top of the visual order (newest-first).
- [ ] The date range `2004` appears on the earliest entry.
- [ ] The word "Hiver" appears as a company name in at least one entry.
- [ ] A visual connector element (line, dots, or similar) is present that links all entries into a timeline affordance — the element is present in the DOM.
- [ ] All timeline data is sourced from `src/content/timeline.ts` — no hardcoded strings in JSX.
- [ ] On mobile viewports ≤ 768px, no entry overflows horizontally.

---

### F5: Hiver Case Study Section

**Priority:** Must-have

**Description:**  
Dedicated section highlighting Kumar's 7 signature transformations at Hiver. Each transformation is a distinct item with a short title and 1–3 sentences of specific outcome. This section exists to give Priya and Michael the "at-scale" proof points they need.

**User Story:**  
As Michael (P2), I want to read specific, numbered outcomes from Kumar's most recent operating role so that I can extract 2–3 memorable proof points to share with my portfolio company's founding team.

**Acceptance Criteria:**
- [ ] Exactly 7 transformation items are rendered.
- [ ] Each item has a distinct title and at least 1 sentence of supporting detail.
- [ ] At least 3 of the 7 items contain a quantified metric (number, percentage, or named program) from the Executive Narrative.
- [ ] The section heading contains the word "Hiver" or "Case Study".
- [ ] All case study content is sourced from `src/content/hiver.ts`.
- [ ] On mobile viewports ≤ 768px, items stack vertically without horizontal overflow.

---

### F6: Contact Section

**Priority:** Must-have

**Description:**  
Minimal section at the bottom of the page with a short invitation to connect and two links: a `mailto:` link to Kumar's email address and a link to his LinkedIn profile. No form, no backend.

**User Story:**  
As Priya (P1), I want a direct, frictionless way to contact Kumar so that I can initiate a conversation without leaving the page to search for his contact information.

**Acceptance Criteria:**
- [ ] A `mailto:` anchor tag is present with Kumar's email address as both the `href` value and the visible link text (or an explicit label).
- [ ] A hyperlink to Kumar's LinkedIn profile (`linkedin.com/in/kumar-shailove`) is present and opens in a new tab (`target="_blank"`).
- [ ] Both links are keyboard-accessible (focusable and activatable via Tab + Enter).
- [ ] The section contains no `<form>` element.
- [ ] Contact data (email, LinkedIn URL) is sourced from `src/content/contact.ts`.

---

### F7: Canvas Network Background

**Priority:** Must-have

**Description:**  
A hand-rolled `<NetworkCanvas>` React component (~100 lines of TypeScript) that renders an animated particle network on an HTML `<canvas>` element positioned as the Hero section's background. 60–100 nodes drift slowly; edges are drawn between nodes within 140px; mouse cursor creates a repulsion force. On mobile, particle count is reduced to 30–40 and `shadowBlur` is disabled.

**User Story:**  
As Alex (P3), I want the site's visual treatment to demonstrate technical craft so that I develop confidence that Kumar can attract and hold high-caliber engineers.

**Acceptance Criteria:**
- [ ] The `<canvas>` element is present inside the Hero section with CSS `position: absolute`, `inset: 0`, `pointer-events: none`, and `aria-hidden="true"`.
- [ ] On desktop (viewport width ≥ 1024px), the canvas renders ≥ 60 nodes.
- [ ] On mobile (viewport width < 768px), the canvas renders ≤ 40 nodes.
- [ ] Moving the mouse over the hero canvas causes at least one visible node displacement within 2 seconds of a sustained mouse movement (verified visually).
- [ ] The canvas does not block pointer events on the hero text or CTA button (clicks on the headline and CTA button register correctly).
- [ ] When `prefers-reduced-motion: reduce` is active, the canvas animation loop does not start — a static dark background or gradient is shown instead (verified by checking that `requestAnimationFrame` is not called when media query matches).
- [ ] The canvas resizes correctly when the browser window is resized — nodes remain distributed across the new viewport dimensions (verified by resizing the browser window and observing no orphaned nodes clustered in a corner).
- [ ] No memory leak: after the Hero section unmounts, `cancelAnimationFrame` is called and event listeners are removed (verified by checking DevTools performance timeline for growing memory).

---

### F8: Scroll Animations (Motion v12)

**Priority:** Must-have

**Description:**  
All six content sections animate into view as the user scrolls using Motion v12's `whileInView` pattern. The About, Philosophy, Timeline, Hiver, and Contact sections each fade in and slide up from `y: 40` to `y: 0`. Philosophy pillars and timeline entries stagger-reveal sequentially. The hero canvas parallax shifts at a fraction of the scroll speed.

**User Story:**  
As Alex (P3), I want the scroll experience to feel polished and intentional so that I perceive the site as technically well-built.

**Acceptance Criteria:**
- [ ] Each of the 5 non-hero sections (About, Philosophy, Experience, Hiver, Contact) uses `motion.section` (or `motion.div`) with `initial={{ opacity: 0, y: 40 }}` and `whileInView={{ opacity: 1, y: 0 }}` (verified by inspecting component JSX).
- [ ] Each `whileInView` animation uses `viewport={{ once: true }}` so the animation does not repeat on scroll-back.
- [ ] Philosophy pillars stagger-reveal with a minimum interval of 0.1 seconds between each pillar appearing.
- [ ] Timeline entries stagger-reveal with a minimum interval of 0.1 seconds between each entry appearing.
- [ ] When `prefers-reduced-motion: reduce` is active, all `motion.*` elements render at their final visible state (`opacity: 1`, `y: 0`) on initial mount — no animation plays.
- [ ] No Motion-related console errors appear in the browser console on a full page scroll.

---

### F9: Smooth Scroll (Lenis)

**Priority:** Must-have

**Description:**  
The entire page uses Lenis smooth scroll via the `ReactLenis` component wrapping the application root. Lenis is initialized with `autoRaf: false` and driven by Motion's `frame.update()` to prevent conflicting `requestAnimationFrame` loops. Scroll interpolation factor (lerp) is 0.08 for a premium, liquid feel.

**User Story:**  
As Priya (P1), I want the page scroll to feel premium and responsive so that the site reads as a high-quality production rather than a template.

**Acceptance Criteria:**
- [ ] `ReactLenis` from `lenis/react` wraps the application root in `App.tsx` or `main.tsx`.
- [ ] `ReactLenis` is configured with `autoRaf={false}`.
- [ ] A `frame.update()` call from `motion/react` drives Lenis — `autoRaf: false` is set and `frame.update(lenis.raf, true)` is used in a `useEffect` with correct cleanup (verified by inspecting the Lenis integration code).
- [ ] Scrolling on a desktop browser (Chrome, Safari, Firefox) produces a visibly smooth scroll with inertia — no instant jump-to-position on wheel events.
- [ ] Clicking the hero CTA button smoothly scrolls to the About section with Lenis easing (not a native instant jump).
- [ ] On touch devices, scroll remains functional and does not stick or freeze.

---

### F10: Chatbot Widget (Expandable FAB)

**Priority:** Must-have

**Description:**  
A fixed-position circular button (FAB) in the bottom-right corner of the viewport. Clicking the FAB opens an iframe panel showing the HuggingFace Gradio chatbot. The iframe `src` is injected only when the user clicks to open (deferred loading). While the Space wakes up, a visible loading skeleton is displayed with the message "Waking up AI assistant (~15s)…" or equivalent. Clicking the FAB again collapses the panel. The panel opens/closes with a Motion `AnimatePresence` transition.

**User Story:**  
As Alex (P3), I want to interact with Kumar's chatbot to probe his ideas so that I can assess how well-articulated his philosophy is under direct questioning.

**Acceptance Criteria:**
- [ ] A circular button element is visible at `position: fixed`, `bottom: 24px`, `right: 24px` on all viewports ≥ 375px wide.
- [ ] Clicking the FAB opens the iframe panel and sets the iframe `src` to the HuggingFace Space URL for the first time (verified by observing that the iframe `src` attribute is absent or empty until the first click).
- [ ] The iframe panel dimensions are ≥ 380px wide and ≥ 480px tall on desktop.
- [ ] A visible loading state (skeleton, spinner, or loading message) is displayed inside the panel before the iframe content finishes loading.
- [ ] The loading state message includes a reference to a wait time (e.g., "~15s", "~20s", or similar).
- [ ] Clicking the FAB again collapses the panel — the panel element is no longer visible in the viewport.
- [ ] The open/close transition completes in ≤ 400ms (measured from click to animation end).
- [ ] The FAB has an `aria-label` attribute with value "Open chat" (or equivalent descriptive text) for screen reader accessibility.
- [ ] The FAB is keyboard-accessible: it receives focus via Tab and activates via Enter or Space.
- [ ] On mobile viewports ≤ 768px, the open panel does not cover the entire viewport — at least 60px of page content remains visible above the panel, or the panel is full-screen with a visible close button.

---

### F11: HuggingFace Gradio Chatbot App

**Priority:** Must-have

**Description:**  
A Python Gradio `ChatInterface` application deployed as a public HuggingFace Space. The app uses the Anthropic Python SDK to call `claude-sonnet-4-6`. A `knowledge_base.md` file is injected into the system prompt. The app responds to questions about Kumar's career, philosophy, and achievements. The chatbot does not hallucinate — it states when information is outside the knowledge base.

**User Story:**  
As Priya (P1), I want to ask the chatbot a specific question about Kumar's experience managing distributed teams so that I can get a nuanced answer without waiting for an email reply.

**Acceptance Criteria:**
- [ ] The HuggingFace Space URL is accessible via a public HTTPS URL of the form `https://<username>-<space-name>.hf.space`.
- [ ] The Space `app.py` uses `gr.ChatInterface` with `type="messages"` (not deprecated `tuples` format).
- [ ] The Space reads `knowledge_base.md` from the Space root directory and includes it in the system prompt.
- [ ] The model used is exactly `claude-sonnet-4-6` (verified in `app.py`).
- [ ] `ANTHROPIC_API_KEY` is set as a HuggingFace Space Secret — the key is not hardcoded in `app.py` or committed to any repository.
- [ ] Sending the message "What did Kumar accomplish at Hiver?" returns a response that references at least one specific Hiver transformation within 60 seconds (accounts for cold-start time).
- [ ] Sending a question about a topic not in the knowledge base (e.g., "What is Kumar's home address?") returns a response that explicitly states the information is not available rather than guessing.
- [ ] The chatbot response for any single message is ≤ 300 words unless the question explicitly requests a detailed breakdown.
- [ ] The Space `requirements.txt` specifies `gradio>=4.0` and `anthropic>=0.40.0`.

---

### F12: Responsive Layout

**Priority:** Must-have

**Description:**  
The site is functional and visually complete on all viewport widths from 375px (iPhone SE) to 1920px (large desktop). No section overflows horizontally. Typography scales appropriately across breakpoints.

**User Story:**  
As Michael (P2), I want to read the site on my phone while traveling so that I can evaluate Kumar between meetings.

**Acceptance Criteria:**
- [ ] No horizontal scrollbar appears on any section at viewport widths of 375px, 768px, 1024px, and 1440px (verified by setting each viewport width in DevTools and checking `document.body.scrollWidth === window.innerWidth`).
- [ ] The hero headline is readable — minimum font size 32px — on a 375px viewport.
- [ ] The Experience Timeline renders without visual clipping on a 375px viewport.
- [ ] The Hiver Case Study renders without visual clipping on a 375px viewport.
- [ ] The Chatbot FAB button is reachable and tappable on a 375px viewport (minimum tap target 44×44px per Apple HIG guidelines).
- [ ] Images (including the profile photo placeholder) have `max-width: 100%` and do not overflow their containers.

---

### F13: Reduced-Motion Accessibility

**Priority:** Must-have

**Description:**  
When the visitor's operating system has "Reduce Motion" enabled (`prefers-reduced-motion: reduce`), all canvas animations stop, all Motion scroll-reveals render at their final state on mount, and no parallax is applied. The site remains fully readable and navigable.

**User Story:**  
As any visitor with vestibular sensitivity, I want to browse the site without motion-triggered discomfort so that I can evaluate Kumar's background without physical side effects.

**Acceptance Criteria:**
- [ ] When `prefers-reduced-motion: reduce` matches, the `<NetworkCanvas>` component renders a static non-animated background (gradient or solid color) — `requestAnimationFrame` is not called (verified by checking `prefers-reduced-motion` in the component's `useEffect` before starting the animation loop).
- [ ] When `prefers-reduced-motion: reduce` matches, all `motion.*` elements are initialized at their final visible state — `opacity: 1`, `y: 0` — on mount rather than playing an entrance animation.
- [ ] When `prefers-reduced-motion: reduce` matches, Lenis smooth scroll is either disabled or falls back to native scroll behavior.
- [ ] Every content section is fully readable (all text visible, no elements stuck at opacity 0) when reduced motion is active.

---

### F14: Navigation Bar

**Priority:** Must-have

**Description:**  
A navigation bar containing links to each of the six sections. On desktop, links are displayed horizontally. On mobile, a hamburger menu or compact layout is used. The nav either: (A) stays fixed/sticky at the top at all times, or (B) is hidden on load and fades in after the user scrolls past the hero section. The exact behavior is resolved in the spec stage (Open Question OQ4).

**User Story:**  
As Michael (P2), I want to jump directly to the Hiver Case Study section without scrolling through every section so that I can reach the evidence quickly within my 4-minute window.

**Acceptance Criteria:**
- [ ] A `<nav>` element is present in the DOM.
- [ ] The nav contains exactly 6 anchor links, each scrolling to one of: Hero, About, Philosophy, Experience, Hiver Case Study, Contact.
- [ ] Clicking each nav link scrolls the viewport to within ±100px of the corresponding section's top edge.
- [ ] On desktop viewports ≥ 1024px, all 6 nav links are visible simultaneously without a dropdown or overflow.
- [ ] On mobile viewports ≤ 768px, nav links are either visible in a collapsed horizontal strip or accessible via a toggle button (hamburger). At minimum, tapping the toggle reveals all 6 links.
- [ ] The nav does not cover more than 80px of page height on any viewport width.
- [ ] The nav has `aria-label="Main navigation"` for screen reader accessibility.

---

### F15: Vercel Deployment

**Priority:** Must-have

**Description:**  
The site is deployed as a static build to Vercel. A `vercel.json` file in the project root configures HTTPS, sets the `Content-Security-Policy` header to include `frame-src https://*.hf.space`, and ensures the build output directory is correct. The deployed URL is a `*.vercel.app` domain.

**User Story:**  
As Kumar, I want the site live at a shareable HTTPS URL so that I can send it to recruiters and founders immediately after V1 sign-off.

**Acceptance Criteria:**
- [ ] A `vercel.json` file exists in the project root with at minimum a `headers` block.
- [ ] The `vercel.json` `headers` block sets a `Content-Security-Policy` response header that includes `frame-src https://*.hf.space`.
- [ ] Running `npm run build` produces a `dist/` directory containing `index.html` and all static assets with no build errors or TypeScript errors.
- [ ] The deployed Vercel URL resolves with HTTP status 200 and serves the portfolio site.
- [ ] The deployed Vercel URL uses HTTPS (HTTP → HTTPS redirect is in place).
- [ ] The Lighthouse Performance score on the deployed URL is ≥ 90 (measured using PageSpeed Insights or Lighthouse CI against the production Vercel URL).
- [ ] The chatbot iframe loads inside the deployed site without a CSP violation error in the browser console.

---

## 5. Key User Flows

### Flow 1 — First-Time Visitor (Landing → Scrolling → Chatbot)

1. Visitor arrives at the `*.vercel.app` URL, likely from a LinkedIn message or email.
2. The Hero section loads in < 2.5 seconds (LCP). The canvas particle network is visible. Kumar's name and headline are immediately readable.
3. The visitor reads the headline — "I build engineering organizations that compound business value." — and the sub-tagline.
4. The visitor clicks the CTA or begins scrolling. Lenis smooth scroll gives the page a premium liquid feel.
5. As the visitor enters the About section, the section fades in from `y: 40`. The profile photo (or placeholder) and narrative prose are visible.
6. The visitor continues scrolling through Philosophy (pillars stagger in), Experience Timeline (entries stagger in), and Hiver Case Study.
7. At some point the visitor notices the chat FAB in the bottom-right corner.
8. The visitor clicks the FAB. The panel expands with a Motion animation. The iframe `src` is injected and the loading state reads "Waking up AI assistant (~15s)…".
9. After 10–30 seconds (cold start), the Gradio interface appears. The visitor types "What did Kumar accomplish at Hiver?" and receives a grounded, specific answer.
10. The visitor scrolls to Contact and finds the email + LinkedIn links.

**Success criteria:** Visitor completes the flow without any broken visual elements, console errors, or a hung chatbot (the loading message correctly sets expectations).

---

### Flow 2 — Returning Visitor / Quick Evaluation

1. Michael (P2) opens the URL he bookmarked 3 days ago. The site loads instantly from Vercel CDN.
2. Michael clicks the "Hiver Case Study" or "Experience" nav link and jumps directly to that section.
3. He reads the 7 transformations and identifies 2–3 proof points with concrete numbers.
4. He copies the URL from the browser address bar to share with a colleague.

**Success criteria:** Nav links work, section jump lands within ±100px of the section, no wait for animation to complete before content is readable (animations use `once: true` so already-scrolled-past sections are visible immediately).

---

### Flow 3 — Mobile Visitor

1. Alex (P3) opens the URL on an iPhone (375px viewport, iOS Safari).
2. The Hero section fits in the viewport — headline text is ≥ 32px, CTA button is tappable (≥ 44px tap target).
3. The canvas renders with ≤ 40 particles and no `shadowBlur`. Frame rate stays ≥ 30fps.
4. Alex scrolls through all sections — no horizontal overflow, no broken layouts.
5. Alex taps the chat FAB — it is reachable in the bottom-right corner without obstructing navigation.
6. The chat panel opens. On a 375px screen, the panel is visually clear (either full-screen with a close button, or sized to not cover the nav bar).

**Success criteria:** All content is legible and reachable; chatbot FAB is accessible; no horizontal scrollbar; canvas renders without performance degradation visible to the user.

---

## 6. Data Requirements

| Section / Feature | Data Needed | Source | Format |
|---|---|---|---|
| Hero | Headline, sub-tagline, Kumar's name | `src/content/hero.ts` | TypeScript string constants |
| About | 2–3 prose paragraphs, profile photo | `src/content/about.ts`, `public/images/profile.jpg` | String constants; JPG/WebP image (placeholder in V1) |
| Philosophy | 3 pillar titles, body text, pull-quotes | `src/content/philosophy.ts` | Array of pillar objects `{ title, body, quote }` |
| Experience Timeline | 8 roles: company, title, start year, end year (or "Present"), 1–2 line description | `src/content/timeline.ts` | Array of role objects `{ company, title, start, end, description }` |
| Hiver Case Study | 7 transformation items: short title, 1–3 sentence detail with metric | `src/content/hiver.ts` | Array of item objects `{ title, detail }` |
| Contact | Email address, LinkedIn profile URL | `src/content/contact.ts` | String constants |
| Navigation | 6 section names and their scroll targets (element IDs) | `src/content/nav.ts` | Array of `{ label, href }` |
| Canvas | Node count (desktop/mobile), edge distance threshold, color constants | `src/components/NetworkCanvas.tsx` (inline constants) | TypeScript constants at top of component file |
| Chatbot | Career narrative, philosophy pillars, Hiver transformations, FAQ answers | `projects/mywebsite/huggingface-space/knowledge_base.md` | Markdown document injected as system prompt context |
| Chatbot (model) | `claude-sonnet-4-6` | `projects/mywebsite/huggingface-space/app.py` | Hardcoded model string in `client.messages.create()` |
| Chatbot (API key) | `ANTHROPIC_API_KEY` | HuggingFace Space Secrets UI (not in repo) | Environment variable |
| Deployment | CSP header allowing `*.hf.space` | `vercel.json` | JSON config |

**Notes:**
- All text that appears in the DOM must be sourced from `src/content/` TypeScript modules — no strings hardcoded in JSX.
- The Executive Narrative PDF (`projects/mywebsite/`) is the canonical source for all content; the spec agent must extract and structure this content into the TypeScript constant files and `knowledge_base.md`.
- The profile photo is Kumar's responsibility to place at `public/images/profile.jpg` or `public/images/profile.webp`. The implementation must handle its absence gracefully with a visible placeholder.

---

## 7. Non-Functional Requirements

### 7.1 Performance

| Requirement | Target | Measurement Method |
|---|---|---|
| Lighthouse Performance score (desktop) | ≥ 90 | PageSpeed Insights on production Vercel URL |
| Largest Contentful Paint (LCP) | < 2.5s | Lighthouse / PageSpeed Insights |
| Cumulative Layout Shift (CLS) | < 0.1 | Lighthouse / PageSpeed Insights |
| Interaction to Next Paint (INP) | < 200ms | Lighthouse / PageSpeed Insights |
| JavaScript bundle (gzipped, all chunks) | < 500KB total | `npm run build` output + `vite-bundle-visualizer` or `rollup-plugin-visualizer` |
| Canvas frame rate (Hero, desktop, M1 Mac + Chrome) | ≥ 55fps sustained | Chrome DevTools Performance panel, record 5-second canvas interaction |
| Canvas frame rate (mobile, mid-range Android, Chrome) | ≥ 30fps sustained | Chrome DevTools remote debug or Lighthouse mobile simulation |
| Time to first meaningful paint (visual hero content) | < 2s on 4G connection | Lighthouse mobile throttled simulation |

### 7.2 Accessibility

| Requirement | Detail |
|---|---|
| Reduced-motion canvas | When `prefers-reduced-motion: reduce` matches, `requestAnimationFrame` is never called; a static background is shown |
| Reduced-motion animations | All `motion.*` elements initialize at their final visible state; no entrance animation plays |
| Semantic HTML | Each section uses a `<section>` element with an `id` matching the nav's scroll target |
| Heading hierarchy | `<h1>` is used exactly once (Kumar's name or headline in the Hero); subsequent section titles use `<h2>` |
| Canvas accessibility | `<canvas>` has `aria-hidden="true"` — it is a decorative element only |
| Image alt text | Profile photo `<img>` has `alt="Kumar Shailove"` |
| Keyboard navigation | All interactive elements (nav links, CTA button, chatbot FAB, contact links) are reachable and activatable via keyboard Tab / Enter / Space |
| Focus indicators | Focused elements have a visible outline — the browser default focus ring is not suppressed without a replacement |
| Nav landmark | `<nav>` element has `aria-label="Main navigation"` |
| Chatbot FAB | `<button>` has `aria-label="Open chat"` (or equivalent); `aria-expanded` reflects open/closed state |

### 7.3 Reliability

| Requirement | Detail |
|---|---|
| Chatbot cold-start UX | When the HuggingFace Space is sleeping, the widget displays a loading skeleton within 200ms of the FAB click. The loading message includes an estimated wait time. The iframe load does not time out the portfolio page. |
| No broken links | All anchor tags in the DOM (`mailto:`, LinkedIn, nav section anchors) resolve or navigate correctly. No `href="#"` stubs in production. |
| No console errors on load | The browser console contains 0 errors and 0 failed network requests on initial page load in Chrome, Safari, and Firefox. |
| Static site resilience | The deployed Vercel URL continues to serve the site even if the HuggingFace Space is unavailable — the portfolio itself does not depend on the chatbot backend. |
| Canvas cleanup | `cancelAnimationFrame` and `removeEventListener` are called in `useEffect` cleanup to prevent memory leaks on component unmount. |

### 7.4 Security

| Requirement | Detail |
|---|---|
| API key not in repository | `ANTHROPIC_API_KEY` must never appear in any committed file — not in `.env`, `app.py`, or any other tracked file. It is set only in HuggingFace Space Secrets via the UI. |
| CSP for iframe | The Vercel deployment sets a `Content-Security-Policy` response header with `frame-src https://*.hf.space`. This is defined in `vercel.json`. |
| No third-party scripts (portfolio side) | The portfolio site loads no external JavaScript files except Google Fonts (preconnect links) — all JS is bundled by Vite. This limits the XSS surface. |
| API spending cap | The Anthropic API key used for the HuggingFace Space must have a monthly spending cap configured in the Anthropic console to limit exposure from chatbot abuse. |

---

## 8. Open Questions for the Spec Stage

The following decisions are unresolved and must be specified before implementation begins. The spec agent is responsible for making each decision explicitly.

### OQ1 — Exact Color Tokens

The five `@theme {}` color tokens must be finalized with exact `oklch()` values. Candidates from research:

| Token | Candidate Value | Notes |
|---|---|---|
| `--color-bg` | `oklch(0.08 0 0)` | Near-black background |
| `--color-surface` | `oklch(0.12 0 0)` | Cards, elevated surfaces |
| `--color-text` | `oklch(0.95 0 0)` | Primary body text |
| `--color-muted` | `oklch(0.55 0 0)` | Secondary labels, captions |
| `--color-accent` | `oklch(0.75 0.15 60)` | Amber-gold; hover states, canvas nodes, CTA |

The spec must also define the canvas `NODE_COLOR`, `EDGE_COLOR`, and `GLOW_COLOR` constants. **Decision required by spec agent.**

### OQ2 — Animation Choreography Specifics

The spec must define exact values for all animation parameters:

- Hero section element entry order and per-element delay (name → headline → tagline → CTA)
- `whileInView` transition duration (candidate: 0.7s) and easing cubic-bezier (candidate: `[0.25, 0.46, 0.45, 0.94]`)
- Stagger interval for philosophy pillars (candidate: 0.15s)
- Stagger interval for timeline entries (candidate: 0.1s)
- Hero canvas parallax ratio (how far the canvas moves per pixel of scroll — candidate: 0.3)

**Decision required by spec agent.**

### OQ3 — Chatbot Persona and Knowledge Base Scope

The spec must decide:

- The chatbot's display name / handle in the widget header (e.g., "Ask about Kumar", "KS AI", or no branding — just the Gradio default title)
- Which sections of the Executive Narrative are included in `knowledge_base.md` (full document vs. curated sections to control token cost per request)
- The 3–5 example prompts pre-populated in the Gradio `ChatInterface` `examples` parameter
- Maximum response length guideline for the system prompt (candidate: ≤ 200 words)
- Whether the Gradio `Soft` theme is used or a custom CSS override is applied to match the portfolio's dark palette

**Decision required by spec agent; some sub-decisions may require input from Kumar (chatbot name, example questions).**

### OQ4 — Navigation Bar Behavior

Two options are viable; spec must choose one and define the implementation detail:

- **Option A — Sticky from load:** Nav is `position: sticky; top: 0` or `position: fixed; top: 0` and visible at all times. Simpler. Always accessible.
- **Option B — Hidden-until-scroll:** Nav is `position: fixed`, starts at `opacity: 0; transform: translateY(-100%)`, fades in after scroll passes the hero section's bottom edge. Scroll threshold to define (candidate: `window.scrollY > window.innerHeight * 0.8`). The reference site (searchpankaj.com) likely uses this pattern.

**Decision required by spec agent.**

### OQ5 — Deployment Domain

V1 deploys to `*.vercel.app`. The spec must confirm:

- The exact Vercel project name to use (which determines the `*.vercel.app` subdomain)
- Whether `vercel.json` includes a redirect rule or just headers
- Whether a custom domain will be added in V1 (current decision: no; confirm this is still the case)

**Decision required by spec agent; Kumar must confirm the domain decision.**

---

*PRD complete. Artifact: `projects/mywebsite/docs/prd.md`*
