export interface PhilosophyPillar {
  id: string
  title: string
  pullQuote: string
  body: string
}

export const philosophyPillars: PhilosophyPillar[] = [
  {
    id: 'leadership',
    title: 'Leadership Philosophy',
    pullQuote:
      'Great engineering organizations are not built by exceptional individuals. They are built by exceptional systems that enable ordinary people to achieve extraordinary outcomes together.',
    body: 'I believe in building engineering operating systems — clear principles, predictable rituals, and decision frameworks that make the right behavior the default behavior. Leadership is not about being the smartest person in the room. It is about designing the room so the right decisions happen without you.',
  },
  {
    id: 'technology',
    title: 'Technology Philosophy',
    pullQuote:
      'Technology should never be optimized for technical elegance alone. It should be optimized to create durable business leverage.',
    body: 'Every architectural decision is a business decision. Platform investments, technical debt choices, infrastructure tradeoffs — all of these have a return on investment that engineering leaders must quantify, communicate, and optimize. I bring an engineering economics lens to every technology choice.',
  },
  {
    id: 'ai',
    title: 'AI Philosophy',
    pullQuote:
      'Artificial Intelligence is not the next engineering tool. It is the next engineering operating model.',
    body: 'AI changes not just what engineers build, but how engineering organizations operate. The teams that win in the next decade will be those that redesign their workflows, decision processes, and organizational structures around AI-native execution — not those that bolt AI onto existing ways of working.',
  },
]
