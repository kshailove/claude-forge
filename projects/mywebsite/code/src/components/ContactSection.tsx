import { motion } from 'motion/react'
import { useScrollAnimation } from '../hooks/useScrollAnimation'
import { contactContent } from '../content/contact'

export default function ContactSection() {
  const anim = useScrollAnimation()

  return (
    <motion.section
      id="contact"
      className="py-24 md:py-32 px-6 md:px-12 bg-[var(--color-surface)]"
      {...anim}
    >
      <div className="max-w-7xl mx-auto">
        <div className="max-w-3xl">
          <p className="font-mono text-xs text-[var(--color-accent)] uppercase tracking-widest mb-4">
            Contact
          </p>
          <h2 className="font-serif text-4xl md:text-5xl lg:text-6xl text-[var(--color-text)] leading-tight mb-6">
            {contactContent.heading}
          </h2>
          <p className="font-sans text-base md:text-lg text-[var(--color-muted)] leading-relaxed mb-12">
            {contactContent.subheading}
          </p>

          <div className="flex flex-col sm:flex-row gap-4 flex-wrap">
            {/* Email CTA */}
            <a
              href={`mailto:${contactContent.email}`}
              className="inline-flex items-center gap-3 px-8 py-4 bg-[var(--color-accent)] text-[var(--color-bg)] font-mono text-sm font-medium rounded-full hover:opacity-90 transition-opacity focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M2 4h12v8a1 1 0 01-1 1H3a1 1 0 01-1-1V4z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
                <path d="M2 4l6 5 6-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              {contactContent.emailLabel}
            </a>

            {/* LinkedIn */}
            <a
              href={contactContent.linkedinUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-3 px-8 py-4 border border-white/20 text-[var(--color-text)] font-mono text-sm rounded-full hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                <path d="M13.632 13.635h-2.37V9.922c0-.886-.018-2.025-1.234-2.025-1.235 0-1.424.964-1.424 1.96v3.778h-2.37V5.998h2.273v1.043h.032c.317-.6 1.09-1.233 2.244-1.233 2.4 0 2.843 1.58 2.843 3.637v4.19zM2.967 4.955A1.375 1.375 0 011.59 3.578a1.375 1.375 0 112.75 0 1.375 1.375 0 01-1.373 1.377zm1.187 8.68H1.78V5.998h2.374v7.637zM14.816 0H1.18C.528 0 0 .515 0 1.149v13.702C0 15.486.528 16 1.18 16h13.635c.652 0 1.185-.514 1.185-1.149V1.149C16 .515 15.467 0 14.815 0h.001z"/>
              </svg>
              {contactContent.linkedinLabel}
            </a>

            {/* GitHub */}
            <a
              href={contactContent.githubUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-3 px-8 py-4 border border-white/20 text-[var(--color-text)] font-mono text-sm rounded-full hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
              </svg>
              {contactContent.githubLabel}
            </a>

            {/* Topmate */}
            <a
              href={contactContent.topmateUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-3 px-8 py-4 border border-white/20 text-[var(--color-text)] font-mono text-sm rounded-full hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <circle cx="8" cy="5" r="3" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M2 14c0-3.314 2.686-6 6-6s6 2.686 6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
              {contactContent.topmateLabel}
            </a>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-24 pt-8 border-t border-white/10">
          <p className="font-mono text-xs text-[var(--color-muted)]">
            © 2026 Kumar Shailove. Built with React, Motion, and Lenis.
          </p>
        </div>
      </div>
    </motion.section>
  )
}
