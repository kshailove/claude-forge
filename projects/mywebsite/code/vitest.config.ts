import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
  resolve: {
    alias: {
      'lenis/react': '/Users/kumarshailove/gh.kumarshailove/claude-forge/projects/mywebsite/code/__mocks__/lenis/react.tsx',
      'motion/react': '/Users/kumarshailove/gh.kumarshailove/claude-forge/projects/mywebsite/code/__mocks__/motion/react.tsx',
    }
  }
})
