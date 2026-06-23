# Kumar Shailove — Portfolio Website

Personal portfolio website for Kumar Shailove, VP of Engineering and AI Transformation Leader.

## Tech Stack

- **Framework**: React 19 + TypeScript + Vite 6
- **Styling**: Tailwind CSS v4 (CSS-first, `@theme {}` block)
- **Animation**: Motion v12 (`motion/react`)
- **Smooth Scroll**: Lenis 1.3 (`lenis/react`, `autoRaf: false`)
- **Fonts**: Instrument Serif (Google Fonts CDN) + Geist Mono (npm)
- **Canvas**: Hand-rolled particle network (`NetworkCanvas.tsx`)
- **Deployment**: Vercel

## Development

```bash
# Install dependencies
npm install

# Start dev server
npm run dev

# Open http://localhost:5173
```

## Build

```bash
npm run build
# Output in dist/
```

## Deploy to Vercel

1. Push this directory to a GitHub repository
2. Connect the repository to Vercel
3. Vercel auto-detects Vite — no build config needed
4. The `vercel.json` file sets CSP headers including `frame-src https://*.hf.space` for the chatbot iframe

```bash
# Or deploy directly via Vercel CLI
npx vercel
```

## Chatbot Setup (HuggingFace Spaces)

The chatbot runs as a separate service on HuggingFace Spaces. See `../chatbot/` for files to upload.

1. Create a HuggingFace Space (SDK: Gradio, visibility: Public)
2. Upload `../chatbot/app.py`, `../chatbot/requirements.txt`, `../chatbot/knowledge_base.md`
3. In Space Settings → Secrets, add: `ANTHROPIC_API_KEY = <your key>`
4. The Space URL will be `https://<hf-username>-<space-slug>.hf.space`
5. Update `CHATBOT_SPACE_URL` in `src/App.tsx` with your Space URL

## Profile Photo

Place a photo at `public/images/profile.jpg` (or `.webp`). The About section shows a placeholder with initials "KS" if the file is absent.

## Project Structure

```
src/
├── App.tsx                    # Root: Lenis + Motion RAF wiring
├── main.tsx                   # React root mount + font imports
├── index.css                  # Tailwind v4 + @theme design tokens
├── content/                   # All site copy (no strings in JSX)
│   ├── hero.ts
│   ├── about.ts
│   ├── philosophy.ts
│   ├── timeline.ts
│   ├── hiver.ts
│   ├── contact.ts
│   └── nav.ts
├── components/
│   ├── NavigationBar.tsx      # Scroll-spy nav, hidden until hero scroll
│   ├── HeroSection.tsx        # Full-viewport hero with canvas
│   ├── NetworkCanvas.tsx      # Hand-rolled particle network
│   ├── AboutSection.tsx       # Career narrative + photo
│   ├── PhilosophySection.tsx  # 3-column philosophy grid
│   ├── PhilosophyCard.tsx     # Single pillar card
│   ├── ExperienceSection.tsx  # 8-role timeline
│   ├── TimelineItem.tsx       # Single timeline entry
│   ├── HiverSection.tsx       # 7 transformations grid
│   ├── TransformationCard.tsx # Single transformation card
│   ├── ContactSection.tsx     # Email, LinkedIn, Topmate links
│   └── ChatbotWidget.tsx      # FAB + deferred iframe chatbot
└── hooks/
    └── useScrollAnimation.ts  # Reusable whileInView reveal hook
```

## Deployment Steps
To go live, do these three things in order:

1. Add your photo
projects/mywebsite/code/public/images/profile.jpg

2. Deploy the chatbot
- Create a HuggingFace Space (SDK: Gradio, Runtime: CPU Basic)
- Upload the 3 files from projects/mywebsite/chatbot/
- Add ANTHROPIC_API_KEY as a Space Secret
- Update CHATBOT_SPACE_URL in projects/mywebsite/code/src/App.tsx with your Space URL

3. Deploy to Vercel
cd projects/mywebsite/code
npx vercel --prod

When you're ready for V2 — custom domain, testimonials section, or any content tweaks — just say the word.