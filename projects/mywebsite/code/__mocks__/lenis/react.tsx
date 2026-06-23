import { vi } from 'vitest'
import React from 'react'

export const ReactLenis = ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children)
export const useLenis = vi.fn(() => ({
  scrollTo: vi.fn(),
  on: vi.fn(),
  off: vi.fn(),
}))
