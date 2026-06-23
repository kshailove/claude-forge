import { useEffect, useRef } from 'react'

// Module-level constants
const PARTICLE_COUNT_DESKTOP = 70
const PARTICLE_COUNT_MOBILE = 35
const MAX_DISTANCE = 140
const NODE_COLOR = 'rgba(255, 200, 100, 0.7)'
const EDGE_COLOR_PREFIX = 'rgba(255, 200, 100, '
const GLOW_COLOR = 'rgba(255, 180, 80, 0.4)'
const GLOW_BLUR = 8
const VELOCITY_BASE = 0.4
const VELOCITY_DAMPING = 0.99
const MOUSE_REPULSION_RADIUS = 100
const MOUSE_REPULSION_FORCE = 0.3

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
}

export default function NetworkCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rafRef = useRef<number>(0)
  const mouseRef = useRef<{ x: number; y: number }>({ x: -9999, y: -9999 })

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Reduced motion check — before any RAF
    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (motionQuery.matches) {
      canvas.width = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
      ctx.fillStyle = 'oklch(0.08 0 0)'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      return
    }

    const isMobile =
      window.matchMedia('(hover: none)').matches ||
      window.innerWidth < 768 ||
      navigator.maxTouchPoints > 0
    const PARTICLE_COUNT = isMobile ? PARTICLE_COUNT_MOBILE : PARTICLE_COUNT_DESKTOP
    const disableShadow = isMobile

    let particles: Particle[] = []

    const init = () => {
      canvas.width = canvas.offsetWidth
      canvas.height = canvas.offsetHeight

      particles = Array.from({ length: PARTICLE_COUNT }, () => ({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * VELOCITY_BASE * 2,
        vy: (Math.random() - 0.5) * VELOCITY_BASE * 2,
        radius: Math.random() * 2 + 1.5,
      }))
    }

    const update = () => {
      const { x: mx, y: my } = mouseRef.current

      for (const p of particles) {
        // Mouse repulsion
        const dx = p.x - mx
        const dy = p.y - my
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < MOUSE_REPULSION_RADIUS && dist > 0) {
          const force = (MOUSE_REPULSION_RADIUS - dist) / MOUSE_REPULSION_RADIUS
          p.vx += (dx / dist) * force * MOUSE_REPULSION_FORCE
          p.vy += (dy / dist) * force * MOUSE_REPULSION_FORCE
        }

        // Velocity damping
        p.vx *= VELOCITY_DAMPING
        p.vy *= VELOCITY_DAMPING

        // Clamp velocity
        const speed = Math.sqrt(p.vx * p.vx + p.vy * p.vy)
        const maxSpeed = VELOCITY_BASE * 3
        if (speed > maxSpeed) {
          p.vx = (p.vx / speed) * maxSpeed
          p.vy = (p.vy / speed) * maxSpeed
        }

        // Move
        p.x += p.vx
        p.y += p.vy

        // Bounce off walls
        if (p.x < 0) { p.x = 0; p.vx *= -1 }
        if (p.x > canvas.width) { p.x = canvas.width; p.vx *= -1 }
        if (p.y < 0) { p.y = 0; p.vy *= -1 }
        if (p.y > canvas.height) { p.y = canvas.height; p.vy *= -1 }
      }
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      // Draw edges
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x
          const dy = particles[i].y - particles[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)

          if (dist < MAX_DISTANCE) {
            const alpha = (1 - dist / MAX_DISTANCE) * 0.4
            ctx.beginPath()
            ctx.strokeStyle = EDGE_COLOR_PREFIX + alpha + ')'
            ctx.lineWidth = 0.5
            ctx.moveTo(particles[i].x, particles[i].y)
            ctx.lineTo(particles[j].x, particles[j].y)
            ctx.stroke()
          }
        }
      }

      // Draw nodes
      for (const p of particles) {
        ctx.beginPath()

        if (!disableShadow) {
          ctx.shadowBlur = GLOW_BLUR
          ctx.shadowColor = GLOW_COLOR
        }

        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
        ctx.fillStyle = NODE_COLOR
        ctx.fill()

        if (!disableShadow) {
          ctx.shadowBlur = 0
        }
      }
    }

    const loop = () => {
      update()
      draw()
      rafRef.current = requestAnimationFrame(loop)
    }

    const onMouse = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      mouseRef.current = {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      }
    }

    const onMouseLeave = () => {
      mouseRef.current = { x: -9999, y: -9999 }
    }

    init()
    rafRef.current = requestAnimationFrame(loop)

    window.addEventListener('resize', init)
    canvas.addEventListener('mousemove', onMouse)
    canvas.addEventListener('mouseleave', onMouseLeave)

    return () => {
      cancelAnimationFrame(rafRef.current)
      window.removeEventListener('resize', init)
      canvas.removeEventListener('mousemove', onMouse)
      canvas.removeEventListener('mouseleave', onMouseLeave)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none"
      aria-hidden="true"
    />
  )
}
