import { motion } from 'motion/react'
import type { ExperienceRole } from '../content/timeline'

interface TimelineItemProps {
  role: ExperienceRole
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

export default function TimelineItem({ role, index }: TimelineItemProps) {
  return (
    <motion.li
      variants={itemVariants}
      className="relative pl-8 pb-8"
      aria-label={`Role ${index + 1}: ${role.title} at ${role.company}`}
    >
      {/* Timeline dot */}
      <span className="absolute left-0 top-2 w-3 h-3 rounded-full bg-[var(--color-accent)] ring-4 ring-[var(--color-bg)] shrink-0" />

      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          {role.isHighlighted ? (
            <a
              href="#hiver"
              onClick={(e) => {
                e.preventDefault()
                document.getElementById('hiver')?.scrollIntoView({ behavior: 'smooth' })
              }}
              className="font-serif text-xl text-[var(--color-accent)] hover:underline"
            >
              {role.company}
            </a>
          ) : (
            <span className="font-serif text-xl text-[var(--color-text)]">{role.company}</span>
          )}
          <span className="font-mono text-xs text-[var(--color-muted)] bg-white/5 px-2 py-0.5 rounded">
            {role.period}
          </span>
        </div>

        <p className="font-sans text-sm text-[var(--color-muted)] font-medium">{role.title}</p>
        <p className="font-mono text-xs text-[var(--color-muted)]/70">{role.location}</p>
        <p className="font-sans text-sm text-[var(--color-muted)] leading-relaxed mt-1">
          {role.description}
        </p>

        {role.highlights.length > 0 && (
          <ul className="mt-2 flex flex-col gap-1 list-none p-0 m-0">
            {role.highlights.map((h, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-[var(--color-accent)] mt-0.5 shrink-0 text-xs">›</span>
                <span className="font-mono text-xs text-[var(--color-muted)]">{h}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </motion.li>
  )
}
