import { motion } from 'motion/react'
import type { PhilosophyPillar } from '../content/philosophy'

interface PhilosophyCardProps {
  pillar: PhilosophyPillar
}

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  show: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.7,
      ease: [0.25, 0.46, 0.45, 0.94] as [number, number, number, number],
    },
  },
}

export default function PhilosophyCard({ pillar }: PhilosophyCardProps) {
  return (
    <motion.div
      variants={itemVariants}
      className="bg-[var(--color-surface)] rounded-2xl p-8 border border-white/5 flex flex-col gap-6 hover:border-[var(--color-accent)]/30 transition-colors duration-300"
    >
      <h3 className="font-serif text-2xl text-[var(--color-text)]">{pillar.title}</h3>

      <blockquote className="font-serif italic text-lg md:text-xl text-[var(--color-accent)] border-l-2 border-[var(--color-accent)] pl-4 leading-snug">
        "{pillar.pullQuote}"
      </blockquote>

      <p className="font-sans text-sm md:text-base text-[var(--color-muted)] leading-relaxed">
        {pillar.body}
      </p>
    </motion.div>
  )
}
