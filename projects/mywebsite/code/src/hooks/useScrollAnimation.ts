import { useReducedMotion } from 'motion/react'

interface ScrollAnimationOptions {
  delay?: number
  duration?: number
  y?: number
}

interface ScrollAnimationResult {
  initial: { opacity: number; y: number }
  whileInView: { opacity: number; y: number }
  viewport: { once: boolean; margin: string }
  transition: { duration: number; delay: number; ease: [number, number, number, number] }
}

export function useScrollAnimation(options?: ScrollAnimationOptions): ScrollAnimationResult {
  const prefersReducedMotion = useReducedMotion()
  const { delay = 0, duration = 0.7, y = 40 } = options ?? {}

  if (prefersReducedMotion) {
    return {
      initial: { opacity: 1, y: 0 },
      whileInView: { opacity: 1, y: 0 },
      viewport: { once: true, margin: '-100px' },
      transition: { duration: 0, delay: 0, ease: [0, 0, 1, 1] },
    }
  }

  return {
    initial: { opacity: 0, y },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, margin: '-100px' },
    transition: { duration, delay, ease: [0.25, 0.46, 0.45, 0.94] },
  }
}
