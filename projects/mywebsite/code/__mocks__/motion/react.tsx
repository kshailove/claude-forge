import React from 'react'
import { vi } from 'vitest'

const motion = new Proxy({} as any, {
  get: (_target: any, tag: string) => {
    return React.forwardRef(({ children, ...props }: any, ref: any) =>
      React.createElement(tag as any, { ...props, ref }, children)
    )
  }
})

export { motion }
export const AnimatePresence = ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children)
export const useScroll = vi.fn(() => ({ scrollY: { get: vi.fn(() => 0), on: vi.fn(), off: vi.fn() } }))
export const useTransform = vi.fn((_source: any, _input: any, output: number[]) => output[0])
export const useReducedMotion = vi.fn(() => false)
export const useInView = vi.fn(() => true)
export const frame = { update: vi.fn() }
export const cancelFrame = vi.fn()
