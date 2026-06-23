import '@testing-library/jest-dom'
import { vi } from 'vitest'

HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
  clearRect: vi.fn(),
  beginPath: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  stroke: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  fillRect: vi.fn(),
  shadowBlur: 0,
  shadowColor: '',
  strokeStyle: '',
  fillStyle: '',
  lineWidth: 0,
})) as any

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
})) as any

global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
})) as any

// Limit requestAnimationFrame to avoid infinite loops in canvas components
let rafCallCount = 0
const RAF_MAX_CALLS = 3
global.requestAnimationFrame = vi.fn((cb) => {
  if (rafCallCount < RAF_MAX_CALLS) {
    rafCallCount++
    cb(0)
  }
  return rafCallCount
}) as any
global.cancelAnimationFrame = vi.fn()

// Reset raf call count between tests
beforeEach(() => {
  rafCallCount = 0
})
