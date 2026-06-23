import { useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'

interface ChatbotWidgetProps {
  spaceUrl: string
}

export default function ChatbotWidget({ spaceUrl }: ChatbotWidgetProps) {
  const [open, setOpen] = useState(false)
  const [iframeSrc, setIframeSrc] = useState<string | null>(null)
  const [iframeLoaded, setIframeLoaded] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)

  const handleOpen = () => {
    setOpen(true)
    setIsExpanded(true)
    // Inject src only the first time the widget is opened
    if (iframeSrc === null) {
      setIframeSrc(spaceUrl)
    }
  }

  const handleClose = () => {
    setOpen(false)
    setIsExpanded(false)
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {/* Chat panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="bg-[var(--color-surface)] border border-white/10 rounded-2xl overflow-hidden shadow-2xl shadow-black/50"
            style={{
              width: 'min(400px, calc(100vw - 48px))',
              height: 'min(520px, calc(100svh - 120px))',
            }}
          >
            {/* Panel header */}
            <div className="flex items-center justify-between px-4 py-3 bg-[var(--color-surface)] border-b border-white/10">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-[var(--color-accent)] animate-pulse" />
                <span className="font-mono text-sm text-[var(--color-text)]">Ask about Kumar</span>
              </div>
              <button
                aria-label="Close chat"
                onClick={handleClose}
                className="text-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors p-1 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-accent)]"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              </button>
            </div>

            {/* Iframe container */}
            <div className="relative" style={{ height: 'calc(100% - 49px)' }}>
              {/* Loading skeleton */}
              {open && !iframeLoaded && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-[var(--color-surface)] z-10">
                  <motion.div
                    className="w-10 h-10 rounded-full border-2 border-[var(--color-accent)] border-t-transparent"
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                  />
                  <div className="text-center px-6">
                    <p className="font-mono text-sm text-[var(--color-text)] mb-1">
                      Waking up AI assistant
                    </p>
                    <p className="font-mono text-xs text-[var(--color-muted)]">
                      (~15s on first load)
                    </p>
                  </div>
                  {/* Skeleton bars */}
                  <div className="w-full px-6 flex flex-col gap-2 mt-4">
                    {[0.7, 0.9, 0.6].map((w, i) => (
                      <motion.div
                        key={i}
                        className="h-3 rounded bg-white/10"
                        style={{ width: `${w * 100}%` }}
                        animate={{ opacity: [0.4, 0.8, 0.4] }}
                        transition={{ duration: 1.5, repeat: Infinity, delay: i * 0.2 }}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* The iframe — src only set after first open */}
              <iframe
                src={iframeSrc ?? undefined}
                onLoad={() => setIframeLoaded(true)}
                title="Chat with Kumar's AI assistant"
                className={`w-full h-full border-none transition-opacity duration-300 ${
                  iframeLoaded ? 'opacity-100' : 'opacity-0'
                }`}
                allow="microphone"
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* FAB button */}
      <motion.button
        aria-label={open ? 'Close chat' : 'Open chat'}
        aria-expanded={isExpanded}
        onClick={open ? handleClose : handleOpen}
        className="w-14 h-14 rounded-full bg-[var(--color-accent)] text-[var(--color-bg)] flex items-center justify-center shadow-lg shadow-black/40 hover:opacity-90 transition-opacity focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]"
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
      >
        <AnimatePresence mode="wait">
          {open ? (
            <motion.span
              key="close"
              initial={{ rotate: -90, opacity: 0 }}
              animate={{ rotate: 0, opacity: 1 }}
              exit={{ rotate: 90, opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            </motion.span>
          ) : (
            <motion.span
              key="chat"
              initial={{ rotate: 90, opacity: 0 }}
              animate={{ rotate: 0, opacity: 1 }}
              exit={{ rotate: -90, opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
                <path
                  d="M11 2C6.03 2 2 5.582 2 10c0 1.79.64 3.446 1.726 4.79L2.5 19l4.625-1.207A9.7 9.7 0 0011 18c4.97 0 9-3.582 9-8s-4.03-8-9-8z"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinejoin="round"
                />
                <path
                  d="M7 9.5h8M7 12.5h5"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            </motion.span>
          )}
        </AnimatePresence>
      </motion.button>
    </div>
  )
}
