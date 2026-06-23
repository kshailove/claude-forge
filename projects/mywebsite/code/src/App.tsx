import { useEffect, useRef } from 'react'
import { ReactLenis, type LenisRef } from 'lenis/react'
import { frame, cancelFrame } from 'motion/react'
import NavigationBar from './components/NavigationBar'
import HeroSection from './components/HeroSection'
import AboutSection from './components/AboutSection'
import PhilosophySection from './components/PhilosophySection'
import ExperienceSection from './components/ExperienceSection'
import HiverSection from './components/HiverSection'
import ContactSection from './components/ContactSection'
import ChatbotWidget from './components/ChatbotWidget'

// Detect reduced motion for Lenis options
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

// HuggingFace Space URL — update once the Space is created
const CHATBOT_SPACE_URL = 'https://kumarshailove-portfolio-chat.hf.space'

export default function App() {
  const lenisRef = useRef<LenisRef>(null)

  useEffect(() => {
    function update(data: { timestamp: number }) {
      lenisRef.current?.lenis?.raf(data.timestamp)
    }

    // frame.update(callback, keepAlive=true) — keeps calling even when no animations are running
    // This is necessary for Lenis to remain active at all times
    frame.update(update, true)

    return () => cancelFrame(update)
  }, [])

  return (
    <ReactLenis
      ref={lenisRef}
      root
      autoRaf={false}
      options={{
        lerp: prefersReducedMotion ? 1 : 0.08,
        duration: prefersReducedMotion ? 0 : 1.2,
        syncTouch: true,
      }}
    >
      <NavigationBar />
      <main>
        <HeroSection />
        <AboutSection />
        <PhilosophySection />
        <ExperienceSection />
        <HiverSection />
        <ContactSection />
      </main>
      <ChatbotWidget spaceUrl={CHATBOT_SPACE_URL} />
    </ReactLenis>
  )
}
