export interface HiverTransformation {
  id: string
  number: string
  title: string
  detail: string
}

export const hiverIntro =
  'When I joined Hiver as VP Engineering in 2021, the engineering organization was operating in reactive mode — shipping features under pressure, accumulating technical debt, and struggling to connect engineering work to business outcomes. Over four years, I drove seven signature transformations.'

export const hiverTransformations: HiverTransformation[] = [
  {
    id: 't1',
    number: '01',
    title: 'Engineering Chaos → Predictable Execution',
    detail:
      'Introduced engineering rhythms, planning processes, and delivery frameworks that converted unpredictable shipping cycles into consistent, forecasted delivery. Engineering became a system, not a series of heroic efforts.',
  },
  {
    id: 't2',
    number: '02',
    title: 'Excellence Through Principles',
    detail:
      'Defined and embedded engineering principles — explicit standards for code quality, system design, incident response, and technical decision-making — so excellence became the default, not the exception.',
  },
  {
    id: 't3',
    number: '03',
    title: 'Platform Engineering as Strategic Leverage',
    detail:
      'Built a platform engineering capability from scratch, creating internal developer platforms that multiplied engineering velocity across all product teams. Developer experience became a competitive advantage.',
  },
  {
    id: 't4',
    number: '04',
    title: 'Engineering Economics',
    detail:
      'Introduced cloud cost visibility, unit economics thinking, and FinOps practices into the engineering organization. Cloud infrastructure went from an uncontrolled cost center to an optimized, business-aligned investment.',
  },
  {
    id: 't5',
    number: '05',
    title: 'Security as Engineering Capability',
    detail:
      'Built security engineering from the ground up — not as a compliance checkbox, but as an engineering discipline embedded into how teams design, build, and operate systems.',
  },
  {
    id: 't6',
    number: '06',
    title: 'AI-Native Engineering',
    detail:
      'Redesigned engineering workflows around AI tooling — from AI-assisted code review and automated testing to AI-native product features. Positioned Hiver\'s engineering org to operate at AI pace, not human pace.',
  },
  {
    id: 't7',
    number: '07',
    title: 'Building Leaders Who Build Leaders',
    detail:
      'Invested systematically in engineering leadership development — coaching, structured feedback, and deliberate exposure to increasing scope — creating a pipeline of leaders capable of driving the next phase of growth.',
  },
]
