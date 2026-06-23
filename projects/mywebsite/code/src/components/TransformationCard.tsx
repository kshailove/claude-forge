import { motion } from 'motion/react'
import type { HiverTransformation } from '../content/hiver'

interface TransformationCardProps {
  transformation: HiverTransformation
  index: number
}

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  show: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.6,
      ease: [0.25, 0.46, 0.45, 0.94] as [number, number, number, number],
    },
  },
}

export default function TransformationCard({ transformation, index }: TransformationCardProps) {
  return (
    <motion.div
      variants={itemVariants}
      className="bg-[var(--color-bg)] rounded-2xl p-6 border border-white/5 flex flex-col gap-4 hover:border-[var(--color-accent)]/30 transition-colors duration-300"
      aria-label={`Transformation ${index}: ${transformation.title}`}
    >
      <span className="font-mono text-[var(--color-accent)] text-sm tabular-nums">
        {transformation.number}
      </span>
      <h3 className="font-serif text-xl text-[var(--color-text)] leading-snug">
        {transformation.title}
      </h3>
      <p className="font-sans text-sm text-[var(--color-muted)] leading-relaxed">
        {transformation.detail}
      </p>
    </motion.div>
  )
}
