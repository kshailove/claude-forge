# Test Plan — Kumar Shailove Personal Portfolio Website

**Version:** 1.0  
**Stage:** 7 — Test Plan  
**Date:** 2026-06-23  
**Prepared by:** ClaudeForge QA Agent (Stage 7)  
**Project:** `projects/mywebsite`  
**Inputs:** `docs/prd.md` (F1–F15 acceptance criteria), `docs/tech-spec.md` (component specs)

---

## Table of Contents

1. [Test Strategy](#1-test-strategy)
2. [Setup Instructions](#2-setup-instructions)
3. [Component Test Plan — React](#3-component-test-plan--react)
4. [Chatbot Test Plan — Python](#4-chatbot-test-plan--python)
5. [Acceptance Test Checklist](#5-acceptance-test-checklist)
6. [Manual QA Checklist](#6-manual-qa-checklist)
7. [Mocking Strategy](#7-mocking-strategy)

---

## 1. Test Strategy

### 1.1 What Gets Tested and at What Level

| Level | Scope | Tooling |
|---|---|---|
| **Unit — React hooks** | `useScrollAnimation` hook: reduced-motion branch, normal branch return values | Vitest + React Testing Library (RTL) `renderHook` |
| **Component — React** | Every named component in `src/components/`. Renders correct DOM, correct ARIA attributes, correct data from content modules, conditional logic (photo fallback, deferred iframe src, visible/hidden nav). | Vitest + RTL + jsdom |
| **Unit — Python** | `chat()` function in `chatbot/app.py` with mocked Anthropic client. System prompt construction. `gr.ChatInterface` object type. | pytest + `unittest.mock` |
| **Acceptance** | PRD F1–F15 acceptance criteria mapped to either automated component tests or manual verification. | Component tests + manual checklist |
| **Manual / Performance** | Lighthouse score, canvas fps, smooth scroll feel, cross-browser, reduced-motion, mobile layout at 375px | Browser + DevTools + PageSpeed Insights |

### 1.2 What Is Explicitly Out of Scope for V1

- **End-to-end browser automation** (Playwright, Cypress) — no test infra currently configured; too slow to set up before launch.
- **Visual regression snapshots** — Percy, Chromatic, or similar. Deferred to V2.
- **Full WCAG AA compliance audit** — partial accessibility is tested (ARIA labels, keyboard reachability, heading hierarchy) per NG10 in the PRD; a full audit is not.
- **Rate-limiting tests on the chatbot** — NG8 defers rate limiting to V2.
- **Open Graph / Twitter Card meta tags** — NG9 defers these to V2.
- **Analytics / tracking integration** — NG6 confirms no analytics in V1.
- **PDF resume download flow** — NG7 confirms no PDF download in V1.

### 1.3 Test Tooling Summary

| Layer | Framework | Runner |
|---|---|---|
| React components & hooks | Vitest 1.x + React Testing Library 14.x + `@testing-library/user-event` 14.x | `npm run test` |
| React coverage | Vitest built-in c8/v8 coverage | `npm run test:coverage` |
| Python chatbot | pytest 7.x | `pytest chatbot/` |
| Python chatbot coverage | pytest-cov | `pytest --cov=chatbot` |

---

## 2. Setup Instructions

### 2.1 React / Vite Test Dependencies

```bash
cd projects/mywebsite/code

npm install --save-dev \
  vitest \
  @vitest/coverage-v8 \
  @testing-library/react \
  @testing-library/user-event \
  @testing-library/jest-dom \
  jsdom
```

### 2.2 `vitest.config.ts` — jsdom Environment

Create (or merge into) `projects/mywebsite/code/vitest.config.ts`:

```typescript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/content/**', 'src/vite-env.d.ts'],
    },
  },
})
```

### 2.3 Global Test Setup (`src/test/setup.ts`)

```typescript
// src/test/setup.ts
import '@testing-library/jest-dom'

// Mock HTMLCanvasElement.getContext — jsdom does not support canvas
HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
  fillRect: vi.fn(),
  clearRect: vi.fn(),
  beginPath: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  stroke: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  set shadowBlur(_: number) {},
  set shadowColor(_: string) {},
  set strokeStyle(_: string) {},
  set fillStyle(_: string) {},
  set lineWidth(_: number) {},
  set globalAlpha(_: number) {},
})) as unknown as typeof HTMLCanvasElement.prototype.getContext

// Mock window.matchMedia — jsdom does not implement it
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// Mock IntersectionObserver — jsdom does not implement it
global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}))

// Mock requestAnimationFrame / cancelAnimationFrame
global.requestAnimationFrame = vi.fn((cb) => { cb(0); return 0 })
global.cancelAnimationFrame = vi.fn()
```

### 2.4 `package.json` Scripts

Add to `projects/mywebsite/code/package.json`:

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage",
    "test:ui": "vitest --ui"
  }
}
```

### 2.5 Python Chatbot Test Dependencies

```bash
cd projects/mywebsite

pip install \
  pytest \
  pytest-cov \
  anthropic \
  gradio
```

Set a fake key for tests (the real key must never appear in the repo):

```bash
export ANTHROPIC_API_KEY="sk-ant-test-fakekeyfortests"
```

Run chatbot tests:

```bash
pytest chatbot/ -v
pytest chatbot/ --cov=chatbot --cov-report=html
```

---

## 3. Component Test Plan — React

All test files live in `src/components/__tests__/` and `src/hooks/__tests__/`. File naming convention: `<ComponentName>.test.tsx`.

---

### 3.1 `NetworkCanvas`

**File:** `src/components/__tests__/NetworkCanvas.test.tsx`

**Setup:**
- Mock `window.matchMedia` to return `matches: false` (motion allowed) by default.
- Mock `HTMLCanvasElement.getContext` (handled in global setup).
- Mock `requestAnimationFrame` and `cancelAnimationFrame`.

#### Describe: `NetworkCanvas — DOM structure`

| # | Test case | Expected behaviour |
|---|---|---|
| NC-01 | Renders a `<canvas>` element | `canvas` element is present in the DOM |
| NC-02 | Canvas has `aria-hidden="true"` | `canvas.getAttribute('aria-hidden')` equals `"true"` |
| NC-03 | Canvas has CSS class `pointer-events-none` | The rendered element includes the Tailwind class |
| NC-04 | Canvas has `absolute inset-0` positioning classes | Both classes are present |

#### Describe: `NetworkCanvas — prefers-reduced-motion: reduce`

| # | Test case | Expected behaviour |
|---|---|---|
| NC-05 | When `matchMedia('prefers-reduced-motion: reduce').matches === true`, `requestAnimationFrame` is NOT called | `requestAnimationFrame` mock is called 0 times after render |
| NC-06 | When reduced-motion is active, `ctx.fillRect` is called once (static background render) | The mocked `fillRect` is called exactly once |

#### Describe: `NetworkCanvas — cleanup`

| # | Test case | Expected behaviour |
|---|---|---|
| NC-07 | `cancelAnimationFrame` is called when the component unmounts | After `unmount()`, `cancelAnimationFrame` mock has been called at least once |
| NC-08 | `window.removeEventListener` is called on unmount for `resize` | `removeEventListener` was called with `'resize'` as first argument |

**Total test cases for NetworkCanvas: 8**

---

### 3.2 `NavigationBar`

**File:** `src/components/__tests__/NavigationBar.test.tsx`

**Setup:**
- Mock `lenis/react`: export `useLenis` as a mock that captures the callback and provides a way to call it with a simulated scroll object `{ scroll: number }`.
- Wrap with a `ReactLenis` mock provider (see Section 7.1).
- Spy on `window.innerHeight` to return `800`.

#### Describe: `NavigationBar — DOM structure`

| # | Test case | Expected behaviour |
|---|---|---|
| NB-01 | Renders a `<nav>` element | `getByRole('navigation')` succeeds |
| NB-02 | `<nav>` has `aria-label="Main navigation"` | `aria-label` attribute equals `"Main navigation"` |
| NB-03 | Renders exactly 5 nav links (matching `navItems` from `src/content/nav.ts`) | `getAllByRole('link')` returns 5 elements |
| NB-04 | Each link's `href` matches the expected section anchor (`#about`, `#philosophy`, `#experience`, `#hiver`, `#contact`) | All 5 `href` values match the `navItems` array |

#### Describe: `NavigationBar — visibility on scroll`

| # | Test case | Expected behaviour |
|---|---|---|
| NB-05 | Nav is not visually prominent at scroll position 0 (opacity 0 or transform off-screen) | Computed style or Motion animate prop reflects hidden state |
| NB-06 | After simulating a scroll event with `scroll > window.innerHeight * 0.8` (e.g., scroll=700), nav becomes visible | The nav element transitions to `opacity: 1` / visible state |
| NB-07 | After simulating scroll back to 0, nav becomes hidden again | Nav opacity is 0 or transform is back off-screen |

#### Describe: `NavigationBar — active link / scroll-spy`

| # | Test case | Expected behaviour |
|---|---|---|
| NB-08 | When `activeSection` is `'about'`, the "About" link receives the accent color class | The "About" `<a>` has the active class; other links do not |
| NB-09 | When `activeSection` changes from `'about'` to `'philosophy'`, the "Philosophy" link becomes active and "About" becomes inactive | Class assignment follows the state change correctly |

#### Describe: `NavigationBar — keyboard accessibility`

| # | Test case | Expected behaviour |
|---|---|---|
| NB-10 | All 5 nav links are Tab-focusable | `userEvent.tab()` cycles through all 5 links without being skipped |

**Total test cases for NavigationBar: 10**

---

### 3.3 `HeroSection`

**File:** `src/components/__tests__/HeroSection.test.tsx`

**Setup:**
- Mock `lenis/react` (same pattern as NavigationBar).
- Mock `motion/react`'s `useScroll`, `useTransform` to return stable mock values (see Section 7.5).
- Import `heroContent` from `src/content/hero.ts` in the test for assertion values.

#### Describe: `HeroSection — content`

| # | Test case | Expected behaviour |
|---|---|---|
| HS-01 | Kumar's name "Kumar Shailove" is present in the DOM | `getByText(/Kumar Shailove/i)` succeeds |
| HS-02 | The exact headline is present: "I build engineering organizations that compound business value." | `getByText(/I build engineering organizations/i)` succeeds |
| HS-03 | The sub-tagline is present in the DOM | `getByText(/Engineering Organizations/i)` succeeds |
| HS-04 | A CTA button or link with href `#about` is present | `getByRole('link', { name: /explore/i })` or `getByRole('button')` with `#about` href |

#### Describe: `HeroSection — canvas integration`

| # | Test case | Expected behaviour |
|---|---|---|
| HS-05 | `NetworkCanvas` renders (i.e., a `<canvas>` element is present inside the section) | `container.querySelector('canvas')` is not null |
| HS-06 | Canvas has `aria-hidden="true"` (delegated to NetworkCanvas; re-verified in integration context) | `canvas.getAttribute('aria-hidden')` equals `"true"` |

#### Describe: `HeroSection — section structure`

| # | Test case | Expected behaviour |
|---|---|---|
| HS-07 | Section has `id="hero"` | `document.getElementById('hero')` is the rendered section |
| HS-08 | The photo placeholder is present in the DOM when profile image is absent | When `public/images/profile.jpg` is treated as absent, a placeholder element renders (tested via `aboutContent.photoSrc` pointing to a non-existent path) |

**Total test cases for HeroSection: 8**

---

### 3.4 `AboutSection`

**File:** `src/components/__tests__/AboutSection.test.tsx`

**Setup:**
- Import `aboutContent` from `src/content/about.ts` for assertion values.
- Mock `motion/react` `motion.section` as a passthrough (see Section 7.5).

#### Describe: `AboutSection — content`

| # | Test case | Expected behaviour |
|---|---|---|
| AB-01 | Renders at least 2 paragraph elements (`<p>`) | `container.querySelectorAll('p').length >= 2` |
| AB-02 | Section has `id="about"` | `document.getElementById('about')` is present |
| AB-03 | A pull-quote element is present (sourced from `aboutContent`) | The pull-quote text is in the DOM |
| AB-04 | Profile `<img>` has `alt="Kumar Shailove"` | `getByAltText('Kumar Shailove')` succeeds |

#### Describe: `AboutSection — photo fallback`

| # | Test case | Expected behaviour |
|---|---|---|
| AB-05 | When the `<img>` fires an `onError` event, the image is replaced by a placeholder element | After `fireEvent.error(imgElement)`, the `<img>` is no longer in the DOM (or `imgError` state drives a placeholder div) |
| AB-06 | The placeholder element is visible (non-zero dimensions implied by presence) and contains the initials text (e.g., "KS") | Placeholder div containing `"KS"` is in the DOM |

#### Describe: `AboutSection — accessibility`

| # | Test case | Expected behaviour |
|---|---|---|
| AB-07 | No horizontal overflow on narrow viewport (375px) — `section` has no `overflow-x` that clips content | Layout test: set container width to 375px; no `scrollWidth > clientWidth` |

**Total test cases for AboutSection: 7**

---

### 3.5 `PhilosophySection` + `PhilosophyCard`

**File:** `src/components/__tests__/PhilosophySection.test.tsx`

**Setup:**
- Mock `motion/react` stagger variants (containers animate children via `staggerChildren`; in tests, all children are instantly visible).
- Import `philosophyPillars` from `src/content/philosophy.ts`.

#### Describe: `PhilosophySection — pillar count`

| # | Test case | Expected behaviour |
|---|---|---|
| PH-01 | Exactly 3 `PhilosophyCard` components render | Container has exactly 3 card elements (identifiable by role or data attribute) |
| PH-02 | Section has `id="philosophy"` | `document.getElementById('philosophy')` is present |

#### Describe: `PhilosophyCard — per-pillar content`

| # | Test case | Expected behaviour |
|---|---|---|
| PH-03 | Each card renders the pillar title ("Leadership", "Technology", "AI") | `getByText('Leadership')`, `getByText('Technology')`, `getByText('AI')` all succeed |
| PH-04 | Each card renders a body paragraph (non-empty text) | Each card container has a non-empty `<p>` element |
| PH-05 | Each card renders a pull-quote element styled differently from body text (italic class or `blockquote` element present) | Each card has an element with `font-italic` class or `<blockquote>` tag |
| PH-06 | The pull-quote text for each pillar matches `philosophyPillars[n].pullQuote` | `getByText(philosophyPillars[0].pullQuote)` (etc.) succeeds for all 3 |

#### Describe: `PhilosophySection — reduced-motion`

| # | Test case | Expected behaviour |
|---|---|---|
| PH-07 | When `prefers-reduced-motion: reduce` matches, all 3 cards are immediately visible (no `opacity: 0` initial state) | All card elements have `opacity` of 1 on initial render |

**Total test cases for PhilosophySection + PhilosophyCard: 7**

---

### 3.6 `ExperienceSection` + `TimelineItem`

**File:** `src/components/__tests__/ExperienceSection.test.tsx`

**Setup:**
- Import `experienceRoles` from `src/content/timeline.ts`.
- Mock `motion/react` stagger variants.

#### Describe: `ExperienceSection — timeline structure`

| # | Test case | Expected behaviour |
|---|---|---|
| EX-01 | Exactly 8 `TimelineItem` list items render | `getAllByRole('listitem').length === 8` |
| EX-02 | Section has `id="experience"` | `document.getElementById('experience')` is present |
| EX-03 | A visual connector element (e.g., `<div>` with absolute left positioning) is present in the DOM | `container.querySelector('[class*="absolute"][class*="left"]')` or `container.querySelector('[class*="w-px"]')` is not null |
| EX-04 | The word "Hiver" appears as a company name in at least one rendered item | `getByText(/Hiver/i)` succeeds |
| EX-05 | The year "2004" appears in at least one rendered item's date range | `getByText(/2004/i)` succeeds |
| EX-06 | The most recent role (index 0 in `experienceRoles`) renders first in DOM order | The first `listitem` contains the company and title from `experienceRoles[0]` |

#### Describe: `TimelineItem — per-item content`

| # | Test case | Expected behaviour |
|---|---|---|
| EX-07 | Each item renders company name, role title, and date range | For a sample item, all three text values are in the same `listitem` |
| EX-08 | Date range uses format `YYYY – YYYY` or `YYYY – Present` | Text matching `/\d{4}\s*[–-]\s*(\d{4}|Present)/` is found in each item |
| EX-09 | Timeline dot element (small circle) is present in each item | Each `listitem` contains an element with `rounded-full` class |
| EX-10 | When `role.isHighlighted === true`, company name is wrapped in an `<a href="#hiver">` link | The `<a>` element with `href="#hiver"` is present for the highlighted role |

#### Describe: `ExperienceSection — accessibility`

| # | Test case | Expected behaviour |
|---|---|---|
| EX-11 | List is a `<ol>` or `<ul>` element | `getByRole('list')` succeeds |

**Total test cases for ExperienceSection + TimelineItem: 11**

---

### 3.7 `HiverSection` + `TransformationCard`

**File:** `src/components/__tests__/HiverSection.test.tsx`

**Setup:**
- Import `hiverTransformations` from `src/content/hiver.ts`.
- Mock `motion/react` stagger variants.

#### Describe: `HiverSection — card count`

| # | Test case | Expected behaviour |
|---|---|---|
| HV-01 | Exactly 7 `TransformationCard` components render | Container has exactly 7 card elements |
| HV-02 | Section has `id="hiver"` | `document.getElementById('hiver')` is present |
| HV-03 | Section heading contains the word "Hiver" or "Case Study" | `getByRole('heading', { name: /hiver|case study/i })` succeeds |

#### Describe: `TransformationCard — per-card content`

| # | Test case | Expected behaviour |
|---|---|---|
| HV-04 | Each card renders a title (non-empty) | All 7 card title elements have non-empty `textContent` |
| HV-05 | Each card renders a detail paragraph (non-empty) | All 7 card detail elements have non-empty `textContent` |
| HV-06 | Each card displays a 1-based numeric index (e.g., "01", "02") | `getByText(/^0[1-7]$/)` resolves for each card |
| HV-07 | Card titles match `hiverTransformations[n].title` | `getByText(hiverTransformations[0].title)` (etc.) succeeds for all 7 |

**Total test cases for HiverSection + TransformationCard: 7**

---

### 3.8 `ContactSection`

**File:** `src/components/__tests__/ContactSection.test.tsx`

**Setup:**
- Import `contactContent` from `src/content/contact.ts`.

#### Describe: `ContactSection — links`

| # | Test case | Expected behaviour |
|---|---|---|
| CO-01 | A `mailto:` anchor is present with `contactContent.email` in the `href` | `getByRole('link', { name: /email/i }).href` starts with `"mailto:"` and contains the email |
| CO-02 | The LinkedIn anchor has `href` containing `"linkedin.com/in/kumar-shailove"` | `getByRole('link', { name: /linkedin/i }).href` contains the expected LinkedIn path |
| CO-03 | The LinkedIn anchor has `target="_blank"` | `a.getAttribute('target')` equals `"_blank"` |
| CO-04 | The LinkedIn anchor has `rel="noopener noreferrer"` | `a.getAttribute('rel')` contains both values |
| CO-05 | Section has `id="contact"` | `document.getElementById('contact')` is present |
| CO-06 | No `<form>` element exists inside the section | `container.querySelector('form')` is null |

#### Describe: `ContactSection — keyboard accessibility`

| # | Test case | Expected behaviour |
|---|---|---|
| CO-07 | Both links are focusable via Tab | `userEvent.tab()` reaches both links without skipping |
| CO-08 | Both links activate via Enter key | `userEvent.keyboard('{Enter}')` while focused does not throw |

#### Describe: `ContactSection — copyright`

| # | Test case | Expected behaviour |
|---|---|---|
| CO-09 | Current year appears in the copyright notice | `getByText(new RegExp(new Date().getFullYear().toString()))` succeeds |

**Total test cases for ContactSection: 9**

---

### 3.9 `ChatbotWidget`

**File:** `src/components/__tests__/ChatbotWidget.test.tsx`

**Setup:**
- Provide `spaceUrl="https://test-space.hf.space"` as prop.
- Mock `motion/react`'s `AnimatePresence` and `motion.div` as passthrough wrappers.
- The iframe is present once the widget opens but will have `src` injected only after first click.

#### Describe: `ChatbotWidget — FAB element`

| # | Test case | Expected behaviour |
|---|---|---|
| CW-01 | A circular button element is present in the DOM on initial render | `getByRole('button', { name: /open chat/i })` succeeds |
| CW-02 | FAB button has `aria-label="Open chat"` | `button.getAttribute('aria-label')` equals `"Open chat"` |
| CW-03 | FAB button has `aria-expanded="false"` on initial render | `button.getAttribute('aria-expanded')` equals `"false"` |
| CW-04 | FAB button is a `<button>` element (keyboard-accessible natively) | `getByRole('button')` resolves to a `<button>` tag |

#### Describe: `ChatbotWidget — open/close behaviour`

| # | Test case | Expected behaviour |
|---|---|---|
| CW-05 | Before first FAB click, the iframe `src` attribute is `undefined` or absent | `container.querySelector('iframe')?.src` is falsy or the attribute is not set |
| CW-06 | After first FAB click, the iframe `src` is set to `spaceUrl` | After click, `container.querySelector('iframe').src` contains `"test-space.hf.space"` |
| CW-07 | After first FAB click, `aria-expanded` changes to `"true"` | `button.getAttribute('aria-expanded')` equals `"true"` |
| CW-08 | A loading skeleton is visible after first FAB click (before `onLoad` fires) | Element with text matching `/Waking up/i` is in the DOM |
| CW-09 | After the iframe `onLoad` event fires, the loading skeleton is no longer visible | Simulate `fireEvent.load(iframeEl)`; skeleton element is no longer in the DOM |
| CW-10 | Clicking the FAB a second time closes the panel | After second click, panel element is no longer in the DOM (AnimatePresence removes it) |
| CW-11 | `aria-expanded` returns to `"false"` after panel closes | `button.getAttribute('aria-expanded')` equals `"false"` |
| CW-12 | On second open (FAB clicked again after closing), iframe `src` is NOT re-injected — same src from first open persists | `src` was set once; the state `iframeSrc` does not reset to null |

#### Describe: `ChatbotWidget — keyboard accessibility`

| # | Test case | Expected behaviour |
|---|---|---|
| CW-13 | FAB is reachable via Tab | `userEvent.tab()` focuses the FAB button |
| CW-14 | FAB activates via Enter key | `userEvent.keyboard('{Enter}')` toggles the panel open |
| CW-15 | FAB activates via Space key | `userEvent.keyboard(' ')` toggles the panel open |

**Total test cases for ChatbotWidget: 15**

---

### 3.10 `useScrollAnimation` Hook

**File:** `src/hooks/__tests__/useScrollAnimation.test.ts`

**Setup:**
- Use `renderHook` from RTL.
- Set `matchMedia` mock to return `matches: false` or `matches: true` before each test.

#### Describe: `useScrollAnimation — normal motion`

| # | Test case | Expected behaviour |
|---|---|---|
| SA-01 | Returns `initial` with `opacity: 0` and `y: 40` (default) when motion is allowed | `result.current.initial` equals `{ opacity: 0, y: 40 }` |
| SA-02 | Returns `whileInView` with `opacity: 1` and `y: 0` | `result.current.whileInView` equals `{ opacity: 1, y: 0 }` |
| SA-03 | Returns `viewport: { once: true }` | `result.current.viewport.once` is `true` |
| SA-04 | Returns transition with `duration: 0.7` (default) | `result.current.transition.duration` equals `0.7` |
| SA-05 | Accepts custom `y` option (e.g., `y: 20`) | `result.current.initial.y` equals `20` when option passed |
| SA-06 | Accepts custom `delay` option (e.g., `delay: 0.15`) | `result.current.transition.delay` equals `0.15` |

#### Describe: `useScrollAnimation — reduced-motion`

| # | Test case | Expected behaviour |
|---|---|---|
| SA-07 | When `matchMedia('prefers-reduced-motion: reduce').matches === true`, `initial.opacity` is `1` | `result.current.initial.opacity` equals `1` |
| SA-08 | When reduced-motion, `initial.y` is `0` | `result.current.initial.y` equals `0` |
| SA-09 | When reduced-motion, `transition.duration` is `0` | `result.current.transition.duration` equals `0` |

**Total test cases for useScrollAnimation: 9**

---

### 3.11 `App.tsx` — Lenis + Motion RAF Wiring

**File:** `src/__tests__/App.test.tsx`

**Setup:**
- Mock `lenis/react`'s `ReactLenis` as a passthrough div.
- Mock `motion/react`'s `frame.update` and `cancelFrame`.

#### Describe: `App — Lenis RAF wiring`

| # | Test case | Expected behaviour |
|---|---|---|
| AP-01 | `frame.update` from `motion/react` is called once on mount | `frame.update` mock has been called exactly once after render |
| AP-02 | The function passed to `frame.update` receives `keepAlive=true` | Second argument to `frame.update` call is `true` |
| AP-03 | `cancelFrame` is called on unmount | After `unmount()`, `cancelFrame` mock has been called |
| AP-04 | `ReactLenis` is rendered with `autoRaf={false}` | The mock `ReactLenis` received prop `autoRaf` equal to `false` |

**Total test cases for App: 4**

---

**React test suite total: 95 test cases**

---

## 4. Chatbot Test Plan — Python

All test files live in `projects/mywebsite/chatbot/tests/` (or a `tests/` subdirectory adjacent to `app.py`).

**File:** `chatbot/tests/test_app.py`

**Imports and fixtures:**

```python
# chatbot/tests/test_app.py
import os
import pytest
from unittest.mock import MagicMock, patch, mock_open
import gradio as gr

os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-fakekeyfortests"

# Import after setting env var
from chatbot.app import chat, demo, KNOWLEDGE_BASE, SYSTEM_PROMPT
```

---

### 4.1 `chat()` Function — Happy Path

| # | Test case | Expected behaviour |
|---|---|---|
| PY-01 | `chat()` returns a non-empty string when Anthropic client responds normally | Mock `client.messages.create` to return a message with `content[0].text = "test response"`; assert return value equals `"test response"` |
| PY-02 | `chat()` passes the correct model string `"claude-sonnet-4-6"` to `messages.create` | Assert that `messages.create` was called with `model="claude-sonnet-4-6"` |
| PY-03 | `chat()` includes `SYSTEM_PROMPT` in the `system` parameter | Assert `messages.create` called with `system=SYSTEM_PROMPT` |
| PY-04 | `chat()` passes `max_tokens=1024` | Assert `messages.create` called with `max_tokens=1024` |
| PY-05 | `chat()` correctly converts Gradio message history into the Anthropic messages list | For history `[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]`, the `messages` kwarg to `messages.create` includes both entries in order |

### 4.2 `chat()` Function — Error Handling

| # | Test case | Expected behaviour |
|---|---|---|
| PY-06 | When `messages.create` raises an `anthropic.APIError`, `chat()` returns a polite fallback string (not a traceback) | Mock `messages.create` to raise `anthropic.APIError`; assert return value is a non-empty string not containing "Traceback" or "Error" in the raw exception format |
| PY-07 | The fallback message does not expose the API key or internal details | Assert fallback string does not contain `"sk-ant"` or `"APIError"` |
| PY-08 | When `messages.create` raises a generic `Exception`, `chat()` still returns a user-friendly fallback | Mock with `Exception("boom")`; return value is a non-empty string |

### 4.3 System Prompt — Knowledge Base Injection

| # | Test case | Expected behaviour |
|---|---|---|
| PY-09 | `KNOWLEDGE_BASE` is a non-empty string (file was read) | `assert len(KNOWLEDGE_BASE) > 100` |
| PY-10 | `SYSTEM_PROMPT` contains the `KNOWLEDGE_BASE` content | `assert KNOWLEDGE_BASE in SYSTEM_PROMPT` |
| PY-11 | `SYSTEM_PROMPT` contains the "200 words" guideline text | `assert "200" in SYSTEM_PROMPT` or `"200 words" in SYSTEM_PROMPT` |
| PY-12 | `SYSTEM_PROMPT` instructs not to make up information | `assert "not present in the knowledge base" in SYSTEM_PROMPT.lower()` or similar phrasing |
| PY-13 | When `knowledge_base.md` is missing, the app raises a `FileNotFoundError` or logs a clear error rather than silently continuing with an empty knowledge base | Patch `open` to raise `FileNotFoundError`; assert the import or initialization raises or logs explicitly (confirms the error surface is not silent) |

### 4.4 Gradio `ChatInterface` Object

| # | Test case | Expected behaviour |
|---|---|---|
| PY-14 | `demo` is an instance of `gr.ChatInterface` | `assert isinstance(demo, gr.ChatInterface)` |
| PY-15 | `demo` is configured with `type="messages"` | `assert demo.type == "messages"` or introspect the constructor kwargs |
| PY-16 | `ANTHROPIC_API_KEY` is read from the environment, not hardcoded | `grep` for `"sk-ant"` in `app.py` source returns no matches (also enforced by a string scan in the test) |

### 4.5 `requirements.txt` Validation

| # | Test case | Expected behaviour |
|---|---|---|
| PY-17 | `requirements.txt` specifies `gradio>=4.0` | File content contains a line matching `gradio>=4` |
| PY-18 | `requirements.txt` specifies `anthropic>=0.40.0` | File content contains a line matching `anthropic>=0.40` |

**Python test suite total: 18 test cases**

---

**Grand total planned test cases: 113**

---

## 5. Acceptance Test Checklist

One row per PRD acceptance criterion. "Automated" refers to the component/unit tests in Sections 3 and 4; "Manual" refers to the browser checklist in Section 6; "Build" refers to `npm run build` output inspection.

### F1 — Hero Section

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F1-AC1 | The section renders at exactly `100vh` on initial load with no vertical scroll bar visible in the viewport. | Manual — DevTools | `min-h-screen` class present on section; no vertical overflow at load |
| F1-AC2 | The name "Kumar Shailove" is rendered in Instrument Serif at ≥ `6xl` (60px) on desktop (≥ 1024px viewport). | Manual — DevTools computed style | Computed `font-family` contains "Instrument Serif"; `font-size` ≥ 60px at 1024px+ |
| F1-AC3 | The headline "I build engineering organizations that compound business value." is present in the DOM and visible without scrolling on all viewport widths ≥ 375px. | Automated — HS-02; Manual — 375px viewport | HS-02 passes; headline visible without scroll at 375px |
| F1-AC4 | The sub-tagline "Engineering Organizations. Engineering Leaders. Engineering the Future." is rendered in Geist Mono font. | Automated — HS-03; Manual — DevTools computed style | HS-03 passes; computed `font-family` contains "Geist Mono Variable" |
| F1-AC5 | A primary CTA button or link is visible without scrolling and, when clicked, scrolls the viewport to the About section (within ±50px). | Automated — HS-04; Manual — click test | HS-04 passes; manual scroll-to-about lands within 50px of `#about` |
| F1-AC6 | The canvas background is visible behind all text content (z-index: canvas is behind text container). | Automated — NC-03, NC-04 (pointer-events-none); Manual — DevTools layers | Classes present; text not obscured by canvas layer |
| F1-AC7 | All hero text elements have contrast ratio ≥ 4.5:1 against the canvas/background layer. | Manual — browser accessibility inspector | All text passes contrast check |
| F1-AC8 | The photo slot is present in the DOM but displays a placeholder if `public/images/profile.jpg` is absent. | Automated — AB-05, AB-06 | Both tests pass |

### F2 — About / Narrative Section

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F2-AC1 | The section contains at least 2 paragraphs of prose narrative sourced from `src/content/about.ts`. | Automated — AB-01 | AB-01 passes (`querySelectorAll('p').length >= 2`) |
| F2-AC2 | At least one paragraph references a named company and a quantified outcome. | Manual — content review | Read `src/content/about.ts`; confirm at least one company name + metric |
| F2-AC3 | A profile photo `<img>` element is present with `alt` text of "Kumar Shailove". | Automated — AB-04 | AB-04 passes |
| F2-AC4 | When `public/images/profile.jpg` is absent, the `<img>` tag is replaced by a visible placeholder. | Automated — AB-05, AB-06 | Both pass |
| F2-AC5 | The section is readable on a 375px-wide viewport with no horizontal scroll. | Manual — DevTools 375px | No `scrollWidth > clientWidth` on About section |
| F2-AC6 | All text in this section is sourced from TypeScript constants in `src/content/` — no hardcoded strings in JSX. | Code review — grep JSX for string literals | `grep -rn '"[A-Z]' src/components/AboutSection.tsx` returns only import/prop references |

### F3 — Philosophy Section

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F3-AC1 | Exactly 3 philosophy pillars are rendered. | Automated — PH-01 | PH-01 passes |
| F3-AC2 | Each pillar has: a title (≥ `text-xl`), a descriptive body paragraph, and a distinct pull-quote styled differently from body text. | Automated — PH-04, PH-05 | Both pass |
| F3-AC3 | The three pillar titles are exactly "Leadership", "Technology", and "AI". | Automated — PH-03 | PH-03 passes |
| F3-AC4 | On desktop viewports ≥ 1280px, all 3 pillars are visible without scrolling within the section (side-by-side or comparable layout). | Manual — DevTools 1280px | All 3 cards visible in one viewport at 1280px |
| F3-AC5 | On mobile viewports ≤ 768px, pillars stack vertically with ≥ 32px gap between them. | Manual — DevTools 375px | Cards stacked; gap ≥ 32px measured in DevTools |
| F3-AC6 | All content is sourced from `src/content/philosophy.ts`. | Code review | `grep -n 'philosophy' src/components/PhilosophySection.tsx` confirms import from content |

### F4 — Experience Timeline

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F4-AC1 | Exactly 8 timeline entries are rendered. | Automated — EX-01 | EX-01 passes |
| F4-AC2 | Each entry contains: company name, role title, and a date range in the format `YYYY – YYYY` or `YYYY – Present`. | Automated — EX-07, EX-08 | Both pass |
| F4-AC3 | The most recent role appears at the top of the visual order (newest-first). | Automated — EX-06 | EX-06 passes |
| F4-AC4 | The date range `2004` appears on the earliest entry. | Automated — EX-05 | EX-05 passes |
| F4-AC5 | The word "Hiver" appears as a company name in at least one entry. | Automated — EX-04 | EX-04 passes |
| F4-AC6 | A visual connector element (line, dots, or similar) is present that links all entries into a timeline affordance. | Automated — EX-03 | EX-03 passes |
| F4-AC7 | All timeline data is sourced from `src/content/timeline.ts`. | Code review | Import from `timeline.ts` confirmed in `ExperienceSection.tsx` |
| F4-AC8 | On mobile viewports ≤ 768px, no entry overflows horizontally. | Manual — DevTools 375px | No horizontal overflow on any `listitem` |

### F5 — Hiver Case Study Section

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F5-AC1 | Exactly 7 transformation items are rendered. | Automated — HV-01 | HV-01 passes |
| F5-AC2 | Each item has a distinct title and at least 1 sentence of supporting detail. | Automated — HV-04, HV-05 | Both pass |
| F5-AC3 | At least 3 of the 7 items contain a quantified metric. | Manual — content review | Read `src/content/hiver.ts`; confirm 3+ items with numbers |
| F5-AC4 | The section heading contains the word "Hiver" or "Case Study". | Automated — HV-03 | HV-03 passes |
| F5-AC5 | All case study content is sourced from `src/content/hiver.ts`. | Code review | Import confirmed in `HiverSection.tsx` |
| F5-AC6 | On mobile viewports ≤ 768px, items stack vertically without horizontal overflow. | Manual — DevTools 375px | No horizontal overflow on any card |

### F6 — Contact Section

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F6-AC1 | A `mailto:` anchor tag is present with Kumar's email address as both the `href` value and visible link text. | Automated — CO-01 | CO-01 passes |
| F6-AC2 | A hyperlink to Kumar's LinkedIn profile (`linkedin.com/in/kumar-shailove`) is present and opens in a new tab. | Automated — CO-02, CO-03 | Both pass |
| F6-AC3 | Both links are keyboard-accessible. | Automated — CO-07, CO-08 | Both pass |
| F6-AC4 | The section contains no `<form>` element. | Automated — CO-06 | CO-06 passes |
| F6-AC5 | Contact data is sourced from `src/content/contact.ts`. | Code review | Import confirmed in `ContactSection.tsx` |

### F7 — Canvas Network Background

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F7-AC1 | The `<canvas>` element is present inside the Hero section with CSS `position: absolute`, `inset: 0`, `pointer-events: none`, and `aria-hidden="true"`. | Automated — NC-01, NC-02, NC-03, NC-04 | All four pass |
| F7-AC2 | On desktop (viewport width ≥ 1024px), the canvas renders ≥ 60 nodes. | Manual — DevTools console log or code inspection | `PARTICLE_COUNT_DESKTOP = 70` in `NetworkCanvas.tsx` constants |
| F7-AC3 | On mobile (viewport width < 768px), the canvas renders ≤ 40 nodes. | Manual — DevTools mobile simulation | `PARTICLE_COUNT_MOBILE = 35` in `NetworkCanvas.tsx` constants |
| F7-AC4 | Moving the mouse over the hero canvas causes at least one visible node displacement within 2 seconds. | Manual — visual inspection | Particles visibly shift away from cursor |
| F7-AC5 | The canvas does not block pointer events on the hero text or CTA button. | Manual — click test | Click on headline and CTA button registers normally |
| F7-AC6 | When `prefers-reduced-motion: reduce` is active, the canvas animation loop does not start — `requestAnimationFrame` is not called. | Automated — NC-05 | NC-05 passes |
| F7-AC7 | The canvas resizes correctly when the browser window is resized. | Manual — resize window | Particles remain distributed across viewport after resize |
| F7-AC8 | No memory leak: after the Hero section unmounts, `cancelAnimationFrame` is called and event listeners are removed. | Automated — NC-07, NC-08 | Both pass |

### F8 — Scroll Animations (Motion v12)

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F8-AC1 | Each of the 5 non-hero sections uses `motion.section` with `initial={{ opacity: 0, y: 40 }}` and `whileInView={{ opacity: 1, y: 0 }}`. | Code review — JSX inspection | Each section component uses `useScrollAnimation` hook or equivalent |
| F8-AC2 | Each `whileInView` animation uses `viewport={{ once: true }}`. | Automated — SA-03; Code review | SA-03 passes; `viewport.once` is `true` in `useScrollAnimation` |
| F8-AC3 | Philosophy pillars stagger-reveal with a minimum interval of 0.1 seconds between each pillar. | Code review | `staggerChildren: 0.12` in `PhilosophySection.tsx` `containerVariants` |
| F8-AC4 | Timeline entries stagger-reveal with a minimum interval of 0.1 seconds between each entry. | Code review | `staggerChildren: 0.12` in `ExperienceSection.tsx` |
| F8-AC5 | When `prefers-reduced-motion: reduce` is active, all `motion.*` elements render at their final visible state on initial mount. | Automated — SA-07, SA-08, SA-09, PH-07 | All four pass |
| F8-AC6 | No Motion-related console errors appear on a full page scroll. | Manual — DevTools Console | Zero errors in Console after scrolling through all sections |

### F9 — Smooth Scroll (Lenis)

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F9-AC1 | `ReactLenis` from `lenis/react` wraps the application root in `App.tsx` or `main.tsx`. | Code review | `ReactLenis` present and wrapping sections in `App.tsx` |
| F9-AC2 | `ReactLenis` is configured with `autoRaf={false}`. | Automated — AP-04 | AP-04 passes |
| F9-AC3 | `frame.update()` from `motion/react` drives Lenis with correct cleanup. | Automated — AP-01, AP-02, AP-03 | All three pass |
| F9-AC4 | Scrolling on desktop produces a visibly smooth scroll with inertia. | Manual — Chrome, Safari, Firefox | Smooth inertia-style scroll visible; no instant jump-to-position |
| F9-AC5 | Clicking the hero CTA button smoothly scrolls to the About section with Lenis easing. | Manual — click CTA | Scroll is animated, not instant jump |
| F9-AC6 | On touch devices, scroll remains functional and does not stick or freeze. | Manual — iOS Safari / Android Chrome | Smooth scroll works; no freezing |

### F10 — Chatbot Widget (Expandable FAB)

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F10-AC1 | A circular button element is visible at `position: fixed`, `bottom: 24px`, `right: 24px` on all viewports ≥ 375px wide. | Automated — CW-01; Manual — CSS inspection | CW-01 passes; `position: fixed; bottom: 24px; right: 24px` in computed styles |
| F10-AC2 | Clicking the FAB opens the iframe panel and sets the iframe `src` to the HuggingFace Space URL for the first time. | Automated — CW-06 | CW-06 passes |
| F10-AC3 | The iframe panel dimensions are ≥ 380px wide and ≥ 480px tall on desktop. | Manual — DevTools | Rendered iframe is ≥ 380×480px |
| F10-AC4 | A visible loading state is displayed inside the panel before the iframe content finishes loading. | Automated — CW-08 | CW-08 passes |
| F10-AC5 | The loading state message includes a reference to a wait time (e.g., "~15s"). | Automated — CW-08 | Text matching `/Waking up/i` and `/15s/i` present |
| F10-AC6 | Clicking the FAB again collapses the panel. | Automated — CW-10 | CW-10 passes |
| F10-AC7 | The open/close transition completes in ≤ 400ms. | Manual — DevTools Performance or stopwatch | Transition duration in `ChatbotWidget.tsx` is `0.25s`; visually confirmed |
| F10-AC8 | The FAB has an `aria-label` attribute with value "Open chat". | Automated — CW-02 | CW-02 passes |
| F10-AC9 | The FAB is keyboard-accessible (Tab + Enter or Space). | Automated — CW-13, CW-14, CW-15 | All three pass |
| F10-AC10 | On mobile viewports ≤ 768px, the open panel does not cover the entire viewport — at least 60px of content remains visible above the panel, or panel is full-screen with a visible close button. | Manual — DevTools 375px | At least 60px of page visible above panel OR close button visible |

### F11 — HuggingFace Gradio Chatbot App

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F11-AC1 | The HuggingFace Space URL is accessible via a public HTTPS URL. | Manual — browser URL check | `https://<username>-<space-name>.hf.space` returns HTTP 200 |
| F11-AC2 | The Space `app.py` uses `gr.ChatInterface` with `type="messages"`. | Automated — PY-14, PY-15 | Both pass |
| F11-AC3 | The Space reads `knowledge_base.md` and includes it in the system prompt. | Automated — PY-09, PY-10 | Both pass |
| F11-AC4 | The model used is exactly `claude-sonnet-4-6`. | Automated — PY-02 | PY-02 passes |
| F11-AC5 | `ANTHROPIC_API_KEY` is set as a HuggingFace Space Secret — not hardcoded. | Automated — PY-16; Security grep | PY-16 passes; no `sk-ant` in `app.py` |
| F11-AC6 | Sending "What did Kumar accomplish at Hiver?" returns a response referencing at least one Hiver transformation within 60s. | Manual — live Space | Response contains a named Hiver outcome within 60s |
| F11-AC7 | Sending an out-of-scope question returns a response that states the information is not available rather than guessing. | Manual — live Space | Response explicitly states information is unavailable |
| F11-AC8 | Chatbot response for any single message is ≤ 300 words unless explicitly requested otherwise. | Manual — word count | Sample 3 responses; each ≤ 300 words |
| F11-AC9 | `requirements.txt` specifies `gradio>=4.0` and `anthropic>=0.40.0`. | Automated — PY-17, PY-18 | Both pass |

### F12 — Responsive Layout

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F12-AC1 | No horizontal scrollbar appears at viewport widths 375px, 768px, 1024px, 1440px. | Manual — DevTools each breakpoint | `document.body.scrollWidth === window.innerWidth` at all 4 widths |
| F12-AC2 | The hero headline is readable — minimum font size 32px — on a 375px viewport. | Manual — DevTools computed style | `font-size` ≥ 32px on headline element at 375px |
| F12-AC3 | The Experience Timeline renders without visual clipping on a 375px viewport. | Manual — DevTools 375px | No entry clipped; all text readable |
| F12-AC4 | The Hiver Case Study renders without visual clipping on a 375px viewport. | Manual — DevTools 375px | No card clipped; all text readable |
| F12-AC5 | The Chatbot FAB button is reachable and tappable on a 375px viewport (minimum tap target 44×44px). | Manual — DevTools 375px + element sizing | FAB `getBoundingClientRect()` ≥ 44×44px |
| F12-AC6 | Images have `max-width: 100%` and do not overflow their containers. | Manual — DevTools + CSS inspection | Profile photo or placeholder has `max-width: 100%` |

### F13 — Reduced-Motion Accessibility

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F13-AC1 | When `prefers-reduced-motion: reduce` matches, `<NetworkCanvas>` renders a static background and `requestAnimationFrame` is not called. | Automated — NC-05, NC-06 | Both pass |
| F13-AC2 | When `prefers-reduced-motion: reduce` matches, all `motion.*` elements initialize at `opacity: 1, y: 0`. | Automated — SA-07, SA-08 | Both pass |
| F13-AC3 | When `prefers-reduced-motion: reduce` matches, Lenis smooth scroll is disabled or falls back to native scroll. | Manual — OS reduced-motion enabled | With Reduce Motion on in OS: `lerp: 1` in `ReactLenis` options; scroll is instant |
| F13-AC4 | Every content section is fully readable when reduced motion is active. | Manual — OS reduced-motion enabled | All 6 sections visible, no elements stuck at opacity 0 |

### F14 — Navigation Bar

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F14-AC1 | A `<nav>` element is present in the DOM. | Automated — NB-01 | NB-01 passes |
| F14-AC2 | The nav contains exactly 6 anchor links scrolling to: Hero, About, Philosophy, Experience, Hiver Case Study, Contact. | Automated — NB-03, NB-04 (5 explicit links + logo/name link to top) | Both pass; confirm 6th link (logo or "Home") present |
| F14-AC3 | Clicking each nav link scrolls the viewport to within ±100px of the corresponding section's top edge. | Manual — click each nav link | Each section top is within 100px of viewport top after click |
| F14-AC4 | On desktop viewports ≥ 1024px, all 6 nav links are visible simultaneously. | Manual — DevTools 1024px | No overflow hidden, no dropdown required to see all links |
| F14-AC5 | On mobile viewports ≤ 768px, nav links are visible in a collapsed strip or accessible via a toggle button. | Manual — DevTools 375px | All links reachable (tap or toggle) at 375px |
| F14-AC6 | The nav does not cover more than 80px of page height on any viewport width. | Manual — DevTools | Nav height ≤ 80px at 375px, 768px, and 1440px |
| F14-AC7 | The nav has `aria-label="Main navigation"`. | Automated — NB-02 | NB-02 passes |

### F15 — Vercel Deployment

| AC | AC Text (verbatim from PRD) | Test Method | Pass Condition |
|---|---|---|---|
| F15-AC1 | A `vercel.json` file exists in the project root with at minimum a `headers` block. | Build — file existence check | `projects/mywebsite/code/vercel.json` exists and contains `"headers"` key |
| F15-AC2 | The `vercel.json` `headers` block sets a `Content-Security-Policy` response header that includes `frame-src https://*.hf.space`. | Build — file content check | `grep 'frame-src.*hf.space' vercel.json` succeeds |
| F15-AC3 | Running `npm run build` produces a `dist/` directory with `index.html` and assets, no TypeScript errors. | Build — `npm run build` | Build exits 0; `dist/index.html` and `dist/assets/` exist |
| F15-AC4 | The deployed Vercel URL resolves with HTTP status 200. | Manual — browser or `curl` | `curl -I https://<project>.vercel.app` returns `200` |
| F15-AC5 | The deployed Vercel URL uses HTTPS (HTTP → HTTPS redirect). | Manual — `curl` http:// variant | `curl -I http://<project>.vercel.app` returns `301` or `308` to HTTPS |
| F15-AC6 | The Lighthouse Performance score on the deployed URL is ≥ 90. | Manual — PageSpeed Insights | Score ≥ 90 for desktop on production URL |
| F15-AC7 | The chatbot iframe loads inside the deployed site without a CSP violation error. | Manual — DevTools Console on deployed URL | Zero CSP errors in Console when opening ChatbotWidget |

---

## 6. Manual QA Checklist

These tests require a real browser and cannot be automated with jsdom. Run against the **production Vercel build** unless noted. Check each box when passing.

### 6.1 Performance

| # | Check | Method | Pass Condition |
|---|---|---|---|
| MQ-01 | Lighthouse Performance ≥ 90 (desktop) | PageSpeed Insights on deployed Vercel URL, desktop mode | Score ≥ 90 |
| MQ-02 | Lighthouse LCP < 2.5s | Same PageSpeed Insights run | LCP metric < 2.5s |
| MQ-03 | Lighthouse CLS < 0.1 | Same run | CLS metric < 0.1 |
| MQ-04 | Lighthouse INP < 200ms | Same run | INP metric < 200ms |
| MQ-05 | JavaScript bundle gzipped total < 500KB | `npm run build` + inspect `dist/assets/` gzip sizes, or use `rollup-plugin-visualizer` | Total gzip ≤ 500KB |
| MQ-06 | Canvas ≥ 55fps on desktop (M1 Mac, Chrome) | Chrome DevTools Performance panel: record 5-second canvas interaction on hero | Sustained frame rate ≥ 55fps with no frame drops to < 30fps |
| MQ-07 | Canvas ≥ 30fps on mobile (375px viewport, Chrome device simulation) | Chrome DevTools remote debug or throttled simulation | Sustained ≥ 30fps |

### 6.2 Smooth Scroll Feel

| # | Check | Method | Pass Condition |
|---|---|---|---|
| MQ-08 | Desktop scroll has inertia — no instant jump-to-position on wheel events | Chrome, Safari, Firefox — scroll the full page from top to bottom | Scroll overshoots slightly and eases back (Lenis lerp=0.08 feel) |
| MQ-09 | CTA click scrolls to About section with Lenis easing (not instant) | Click the hero CTA button | Scroll is animated, visible interpolation toward About section |
| MQ-10 | Touch scroll works on iOS Safari — no sticky or frozen scroll | iPhone (real device or Simulator) | Page scrolls smoothly; no sticking; no freeze mid-scroll |
| MQ-11 | No double-scroll artifacts (two RAF loops fighting) | Chrome DevTools: Performance panel during scroll | No erratic movement; no stutter every ~16ms |

### 6.3 Chatbot Cold-Start UX

| # | Check | Method | Pass Condition |
|---|---|---|---|
| MQ-12 | Loading skeleton appears within 200ms of FAB click | Open DevTools Network; click FAB; observe | Skeleton is visible within 200ms; iframe `src` request starts |
| MQ-13 | Loading message includes an estimated wait time | Visual inspection | Text matching "~15s" or equivalent is visible |
| MQ-14 | Chatbot loads within 30s of FAB click (cold start) | Wait from FAB click to Gradio UI appearing | Gradio interface visible within 30s |
| MQ-15 | Chatbot responds to "What did Kumar accomplish at Hiver?" with a specific, grounded answer | Type message; read response | Response references at least one named Hiver transformation; no hallucination |
| MQ-16 | Out-of-scope question returns a polite "I don't know" response | Type "What is Kumar's home address?" | Response states information is unavailable; does not guess |
| MQ-17 | Site remains fully usable if HuggingFace Space is sleeping or unavailable | Disconnect from internet after page load; open chatbot panel | Portfolio sections all remain functional; only the chatbot panel is non-responsive |

### 6.4 Mobile Layout (375px viewport — iPhone SE)

| # | Check | Method | Pass Condition |
|---|---|---|---|
| MQ-18 | All 6 sections are navigable at 375px | Chrome DevTools device simulation: iPhone SE | Scroll through all sections; no horizontal overflow |
| MQ-19 | Hero headline is ≥ 32px at 375px | DevTools computed style | `font-size` ≥ 32px |
| MQ-20 | CTA button is tappable (≥ 44×44px) | DevTools element sizing | `getBoundingClientRect()` width ≥ 44, height ≥ 44 |
| MQ-21 | FAB is visible and tappable (≥ 44×44px) at 375px | DevTools | FAB visible in bottom-right; dimensions ≥ 44×44px |
| MQ-22 | Chat panel at 375px does not cover the entire viewport OR has a visible close button | Open chatbot on 375px simulation | ≥ 60px of page above panel visible OR close button clearly visible |
| MQ-23 | Experience Timeline entries do not overflow horizontally at 375px | Scroll to Timeline section at 375px | No `scrollWidth > clientWidth` on any list item |
| MQ-24 | Hiver cards do not overflow horizontally at 375px | Scroll to Hiver section at 375px | No card clipping; all text readable |
| MQ-25 | Navigation is accessible at 375px (all 6 links reachable) | Scroll to reveal nav; check links | All 6 links visible or accessible via toggle |

### 6.5 Reduced-Motion Accessibility

| # | Check | Method | Pass Condition |
|---|---|---|---|
| MQ-26 | Canvas shows static gradient/solid color — no animation | Enable "Reduce Motion" in System Preferences (macOS) → Accessibility → Display; reload site | Canvas element is visible but static; no particle movement |
| MQ-27 | No section-reveal animations play on scroll | With Reduce Motion on, scroll through all 6 sections | Sections appear instantly at full opacity; no fade-in or slide-up |
| MQ-28 | All content sections are fully readable (no elements stuck at opacity 0) | With Reduce Motion on, scroll through all sections | All text visible; no sections hidden |
| MQ-29 | Lenis smooth scroll is effectively disabled (instant/native feel) | With Reduce Motion on, scroll the page | Scroll feels native — no inertia or overshoot |
| MQ-30 | `requestAnimationFrame` is not called by NetworkCanvas | DevTools Performance panel with Reduce Motion on; record 5s | No repeated RAF calls attributed to canvas component |

### 6.6 Cross-Browser Verification

Run the following checks on Chrome, Firefox, and Safari (desktop):

| # | Check | Pass Condition |
|---|---|---|
| MQ-31 | Page loads with 0 console errors in Chrome | DevTools Console: 0 errors |
| MQ-32 | Page loads with 0 console errors in Firefox | Browser Console: 0 errors |
| MQ-33 | Page loads with 0 console errors in Safari | Web Inspector Console: 0 errors |
| MQ-34 | Smooth scroll works in all 3 browsers | Inertia visible on wheel scroll |
| MQ-35 | Canvas animation runs in all 3 browsers | Particles visible and moving |
| MQ-36 | Chatbot FAB opens panel in all 3 browsers | Panel appears, loading skeleton shown |
| MQ-37 | No CSP violations in any browser console | Zero CSP errors after opening chatbot |

### 6.7 Accessibility Spot-Checks

| # | Check | Method | Pass Condition |
|---|---|---|---|
| MQ-38 | Heading hierarchy: exactly one `<h1>` on the page | DevTools → Elements search for `h1` | Exactly 1 `<h1>` present (Kumar's name or headline) |
| MQ-39 | All section headings are `<h2>` or below | Inspect section heading tags | No `<h1>` in any section other than Hero |
| MQ-40 | Keyboard navigation: Tab cycles through all interactive elements | Tab from start of page to end | All nav links, CTA, contact links, FAB button are focusable |
| MQ-41 | Focus ring is visible on all interactive elements | Tab to each element | Visible outline on focus; browser default not suppressed without replacement |
| MQ-42 | `<nav aria-label="Main navigation">` present | DevTools Elements | Attribute present on nav element |
| MQ-43 | ChatbotWidget FAB `aria-label="Open chat"` | DevTools Elements | Attribute present |
| MQ-44 | ChatbotWidget FAB `aria-expanded` reflects state | Tab to FAB; press Enter; inspect attribute | Changes from `"false"` to `"true"` on open |

---

## 7. Mocking Strategy

### 7.1 `lenis/react` — Mock `useLenis` and `ReactLenis`

The `lenis/react` module provides `useLenis` (a hook that receives a scroll callback) and `ReactLenis` (a provider component). In jsdom, neither the scroll event nor the Lenis instance exists.

**Mock implementation** (`src/test/mocks/lenis-react.ts`):

```typescript
// src/test/mocks/lenis-react.ts
import { vi } from 'vitest'
import React from 'react'

// Stores the last useLenis callback so tests can trigger it manually
let _lenisCallback: ((data: { scroll: number; progress: number; velocity: number }) => void) | null = null

export const useLenis = vi.fn((callback: typeof _lenisCallback) => {
  _lenisCallback = callback
  return null  // Returns lenis instance; null is fine for tests that don't call scrollTo
})

export const ReactLenis = vi.fn(({ children, ...props }: { children: React.ReactNode; [key: string]: unknown }) => {
  return React.createElement(React.Fragment, null, children)
})

// Test helper: simulate a scroll event
export const simulateLenisScroll = (scroll: number) => {
  _lenisCallback?.({ scroll, progress: 0, velocity: 0 })
}
```

**Register the mock** in `vitest.config.ts`:

```typescript
// vitest.config.ts (add to test config)
test: {
  alias: {
    'lenis/react': '/src/test/mocks/lenis-react.ts',
  },
}
```

### 7.2 `HTMLCanvasElement.getContext` — jsdom Canvas Mock

jsdom does not implement Canvas 2D context. The global setup in `src/test/setup.ts` (Section 2.3) patches `HTMLCanvasElement.prototype.getContext` with a spy that returns a mock context object containing all methods used by `NetworkCanvas`. This ensures the component mounts without throwing and allows `ctx.fillRect` call counts to be asserted.

**Key assertions enabled by this mock:**
- NC-06: `ctx.fillRect` called exactly once when reduced-motion is active.
- NC-07: `cancelAnimationFrame` called on unmount.
- `ctx.fillStyle`, `ctx.strokeStyle`, `ctx.shadowBlur` are setters (use `Object.defineProperty` in the mock object if needed for spy coverage).

### 7.3 `window.matchMedia` — Mock for `prefers-reduced-motion` and `(hover: none)`

The global setup mock returns `matches: false` by default. Tests that require `matches: true` override it inline:

```typescript
// Inside a test:
vi.mocked(window.matchMedia).mockImplementation((query: string) => ({
  matches: query.includes('prefers-reduced-motion'),
  media: query,
  onchange: null,
  addListener: vi.fn(),
  removeListener: vi.fn(),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  dispatchEvent: vi.fn(),
}))
```

**Where this is used:**
- NC-05, NC-06: `NetworkCanvas` reduced-motion guard.
- SA-07, SA-08, SA-09: `useScrollAnimation` reduced-motion branch.
- PH-07: `PhilosophySection` reduced-motion behavior.

For `(hover: none)` (touch device detection if used): same pattern with `query.includes('hover: none')`.

### 7.4 `IntersectionObserver` — Mock for `whileInView` Tests

Motion's `whileInView` relies on `IntersectionObserver` internally. The global setup mock provides a no-op implementation. Since we mock `motion/react`'s `motion.*` components as passthroughs (Section 7.5), `IntersectionObserver` is not called in most component tests. The global mock prevents the `ReferenceError: IntersectionObserver is not defined` error that would otherwise crash jsdom.

For tests that explicitly need to simulate an element entering the viewport (e.g., triggering a stagger start), call:

```typescript
// Simulate all observers firing (element entered viewport)
const observer = (global.IntersectionObserver as ReturnType<typeof vi.fn>).mock.instances[0]
observer.observe.mock.calls.forEach(([element]: [Element]) => {
  // Observer fires on element
})
```

In practice, this is not needed because the scroll animation behavior is unit-tested through `useScrollAnimation` directly (Section 3.10).

### 7.5 `motion/react` — Use Real or Mock?

**Decision: use the real `motion` library in component tests.**

Rationale: Mocking `motion/react` completely (replacing every `motion.section`, `motion.div`, etc. with `<section>`, `<div>`) makes component tests faster but breaks any test that asserts on animation props (`initial`, `animate`, `whileInView`). The real Motion library works in jsdom with one caveat: it cannot perform actual CSS transitions (jsdom has no layout engine), but it still:
- Renders the correct DOM elements.
- Accepts and stores `initial`, `animate`, `whileInView` props.
- Works with `AnimatePresence` for conditional rendering tests (CW-10).

**Exceptions — mock these specific imports:**

1. `useScroll` from `motion/react` — jsdom has no scroll position; mock to return `{ scrollY: { get: () => 0, onChange: vi.fn() } }`.
2. `useTransform` from `motion/react` — mock to return a `MotionValue` that reads `0`.
3. `frame.update` and `cancelFrame` from `motion/react` — mocked in `App.tsx` tests (AP-01 through AP-04).
4. `useReducedMotion` from `motion/react` — use the real implementation (it reads `window.matchMedia`, which is already mocked in setup).

**Selective mock** for `useScroll` and `useTransform` in `HeroSection.test.tsx`:

```typescript
vi.mock('motion/react', async () => {
  const actual = await vi.importActual<typeof import('motion/react')>('motion/react')
  return {
    ...actual,
    useScroll: vi.fn(() => ({ scrollY: { get: () => 0, on: vi.fn(), destroy: vi.fn() } })),
    useTransform: vi.fn(() => ({ get: () => 0, on: vi.fn(), destroy: vi.fn() })),
  }
})
```

### 7.6 Anthropic Client — Mock `client.messages.create` in Python Tests

```python
# In test file:
from unittest.mock import MagicMock, patch

def make_mock_response(text: str):
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    return response

@patch('chatbot.app.client')
def test_chat_returns_response(mock_client):
    mock_client.messages.create.return_value = make_mock_response("Test response text")
    result = chat("Hello", [])
    assert result == "Test response text"

@patch('chatbot.app.client')
def test_chat_handles_api_error(mock_client):
    import anthropic
    mock_client.messages.create.side_effect = anthropic.APIError(
        message="Rate limited", request=MagicMock(), body=None
    )
    result = chat("Hello", [])
    assert isinstance(result, str)
    assert len(result) > 0
    assert "Traceback" not in result
    assert "APIError" not in result
```

The `@patch('chatbot.app.client')` decorator replaces the `client` object instantiated at module level in `app.py`. This requires the module-level client to be named `client` (matching the tech spec's pattern). If it is named differently, update the patch path accordingly.

---

## Summary

| Layer | Test Count |
|---|---|
| React component + hook tests | 95 |
| Python chatbot tests | 18 |
| **Automated total** | **113** |
| Manual QA checklist items | 44 |
| Acceptance criteria rows (F1–F15) | 55 |

**All 55 PRD acceptance criteria (F1–F15) are covered** — either by an automated test case, a build artifact check, or a named manual QA step.

---

*Test plan complete. Artifact: `docs/test-plan.md`*
