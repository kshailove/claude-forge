import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ChatbotWidget from '../../components/ChatbotWidget'

const TEST_URL = 'https://example.com/chatbot'

describe('ChatbotWidget', () => {
  it('renders the FAB open button initially', () => {
    render(<ChatbotWidget spaceUrl={TEST_URL} />)
    const btn = screen.getByRole('button', { name: /open chat/i })
    expect(btn).toBeInTheDocument()
  })

  it('FAB button has aria-expanded false initially', () => {
    render(<ChatbotWidget spaceUrl={TEST_URL} />)
    const btn = screen.getByRole('button', { name: /open chat/i })
    expect(btn).toHaveAttribute('aria-expanded', 'false')
  })

  it('chat panel is not visible before opening', () => {
    render(<ChatbotWidget spaceUrl={TEST_URL} />)
    expect(screen.queryByText('Ask about Kumar')).not.toBeInTheDocument()
  })

  it('opens the chat panel when FAB is clicked', () => {
    render(<ChatbotWidget spaceUrl={TEST_URL} />)
    const openBtn = screen.getByRole('button', { name: /open chat/i })
    fireEvent.click(openBtn)
    expect(screen.getByText('Ask about Kumar')).toBeInTheDocument()
  })

  it('FAB button changes label to "Close chat" when open', () => {
    render(<ChatbotWidget spaceUrl={TEST_URL} />)
    const openBtn = screen.getByRole('button', { name: /open chat/i })
    fireEvent.click(openBtn)
    // After open, FAB should now be labeled "Close chat"
    const closeBtns = screen.getAllByRole('button', { name: /close chat/i })
    expect(closeBtns.length).toBeGreaterThanOrEqual(1)
  })

  it('iframe src is null until widget is opened', () => {
    render(<ChatbotWidget spaceUrl={TEST_URL} />)
    // Before opening, the iframe should exist but have no src
    const iframe = document.querySelector('iframe')
    if (iframe) {
      expect(iframe.getAttribute('src')).toBeNull()
    }
    // If iframe isn't rendered at all before open, that's also valid
  })

  it('iframe src is set to spaceUrl after opening', () => {
    render(<ChatbotWidget spaceUrl={TEST_URL} />)
    const openBtn = screen.getByRole('button', { name: /open chat/i })
    fireEvent.click(openBtn)
    const iframe = document.querySelector('iframe')
    expect(iframe).toBeInTheDocument()
    expect(iframe?.getAttribute('src')).toBe(TEST_URL)
  })

  it('closes the chat panel when close button in header is clicked', () => {
    render(<ChatbotWidget spaceUrl={TEST_URL} />)
    const openBtn = screen.getByRole('button', { name: /open chat/i })
    fireEvent.click(openBtn)
    // Panel is open - find the header close button
    const closeBtns = screen.getAllByRole('button', { name: /close chat/i })
    // Click the first one (header close button)
    fireEvent.click(closeBtns[0])
    expect(screen.queryByText('Ask about Kumar')).not.toBeInTheDocument()
  })

  it('shows loading skeleton while iframe is loading', () => {
    render(<ChatbotWidget spaceUrl={TEST_URL} />)
    const openBtn = screen.getByRole('button', { name: /open chat/i })
    fireEvent.click(openBtn)
    // Loading text should be visible since iframe hasn't loaded
    expect(screen.getByText('Waking up AI assistant')).toBeInTheDocument()
  })

  it('iframe has correct title attribute', () => {
    render(<ChatbotWidget spaceUrl={TEST_URL} />)
    const openBtn = screen.getByRole('button', { name: /open chat/i })
    fireEvent.click(openBtn)
    const iframe = screen.getByTitle("Chat with Kumar's AI assistant")
    expect(iframe).toBeInTheDocument()
  })
})
