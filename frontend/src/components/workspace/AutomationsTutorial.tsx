import { useEffect, useRef } from 'react'
import * as d3 from 'd3'

const ACTIONS = [
  { label: 'Run Extraction', color: '#3b82f6' },
  { label: 'Notify Team', color: '#8b5cf6' },
  { label: 'Archive File', color: '#10b981' },
]

const LOOP_MS = 4500

export function AutomationsTutorial() {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    const el = svgRef.current
    if (!el) return

    const svg = d3.select(el)
    svg.selectAll('*').remove()

    // Layout
    const TRIG_X = 10, TRIG_Y = 25, TRIG_W = 105, TRIG_H = 135
    const TRIG_CX = TRIG_X + TRIG_W / 2
    const ACT_X = 218, ACT_Y = 22, ACT_W = 155, ACT_H = 40, ACT_GAP = 7
    const ARROW_X1 = TRIG_X + TRIG_W + 5
    const ARROW_X2 = ACT_X - 5
    const ARROW_Y = TRIG_Y + TRIG_H / 2
    const MID_X = (ARROW_X1 + ARROW_X2) / 2

    // ── Defs ────────────────────────────────────────────────
    const defs = svg.append('defs')
    defs.append('marker')
      .attr('id', 'auto-arrow-tip')
      .attr('viewBox', '0 0 10 10')
      .attr('refX', 9).attr('refY', 5)
      .attr('markerWidth', 6).attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path').attr('d', 'M0,0 L10,5 L0,10 Z')
      .attr('fill', 'var(--highlight-color, #eab308)')

    // ── Trigger card ─────────────────────────────────────────
    const trigCard = svg.append('rect')
      .attr('x', TRIG_X).attr('y', TRIG_Y)
      .attr('width', TRIG_W).attr('height', TRIG_H)
      .attr('rx', 8)
      .attr('fill', '#fafafa')
      .attr('stroke', '#e2e8f0').attr('stroke-width', 1.5)

    // Pulse ring behind the trigger card
    const ripple = svg.append('rect')
      .attr('x', TRIG_X - 4).attr('y', TRIG_Y - 4)
      .attr('width', TRIG_W + 8).attr('height', TRIG_H + 8)
      .attr('rx', 12)
      .attr('fill', 'none')
      .attr('stroke', 'var(--highlight-color, #eab308)')
      .attr('stroke-width', 2).attr('opacity', 0)

    // Zap icon circle
    svg.append('circle')
      .attr('cx', TRIG_CX).attr('cy', TRIG_Y + 38)
      .attr('r', 20)
      .attr('fill', 'color-mix(in srgb, var(--highlight-color, #eab308) 12%, white)')
      .attr('stroke', 'var(--highlight-color, #eab308)').attr('stroke-width', 1.5)

    // Lightning bolt path centered in the circle
    const bx = TRIG_CX, by = TRIG_Y + 38
    svg.append('path')
      .attr('d', `M ${bx + 3},${by - 12} L ${bx - 3},${by} L ${bx + 1},${by} L ${bx - 3},${by + 12} L ${bx + 3},${by + 1} L ${bx - 1},${by + 1} Z`)
      .attr('fill', 'var(--highlight-color, #eab308)')

    svg.append('text')
      .attr('x', TRIG_CX).attr('y', TRIG_Y + 72)
      .attr('text-anchor', 'middle')
      .attr('font-size', 7.5).attr('font-weight', 700)
      .attr('fill', '#94a3b8').attr('letter-spacing', 1)
      .text('TRIGGER')

    svg.append('text')
      .attr('x', TRIG_CX).attr('y', TRIG_Y + 90)
      .attr('text-anchor', 'middle')
      .attr('font-size', 11.5).attr('font-weight', 600)
      .attr('fill', '#374151').text('File Uploaded')

    svg.append('text')
      .attr('x', TRIG_CX).attr('y', TRIG_Y + 107)
      .attr('text-anchor', 'middle')
      .attr('font-size', 9.5).attr('fill', '#9ca3af')
      .text('to watched folder')

    // ── Arrow ────────────────────────────────────────────────
    const arrowPath = svg.append('path')
      .attr('d', `M ${ARROW_X1},${ARROW_Y} C ${MID_X - 8},${ARROW_Y} ${MID_X + 8},${ARROW_Y} ${ARROW_X2},${ARROW_Y}`)
      .attr('fill', 'none')
      .attr('stroke', 'var(--highlight-color, #eab308)')
      .attr('stroke-width', 2)
      .attr('marker-end', 'url(#auto-arrow-tip)')

    const pathLen = (arrowPath.node() as SVGPathElement).getTotalLength()
    arrowPath.attr('stroke-dasharray', pathLen).attr('stroke-dashoffset', pathLen)

    // ── Action step cards ─────────────────────────────────────
    const actionGroups = ACTIONS.map((a, i) => {
      const gy = ACT_Y + i * (ACT_H + ACT_GAP)
      const g = svg.append('g')
        .attr('transform', `translate(${ACT_X}, ${gy})`)
        .attr('opacity', 0)

      g.append('rect')
        .attr('width', ACT_W).attr('height', ACT_H)
        .attr('rx', 6).attr('fill', 'white')
        .attr('stroke', '#e2e8f0').attr('stroke-width', 1.5)

      // Numbered dot
      g.append('circle')
        .attr('cx', 18).attr('cy', ACT_H / 2).attr('r', 10)
        .attr('fill', a.color).attr('opacity', 0.12)
      g.append('text')
        .attr('x', 18).attr('y', ACT_H / 2 + 4)
        .attr('text-anchor', 'middle')
        .attr('font-size', 9).attr('font-weight', 700)
        .attr('fill', a.color).text(i + 1)

      g.append('text')
        .attr('x', 34).attr('y', ACT_H / 2 + 4)
        .attr('font-size', 11.5).attr('font-weight', 600)
        .attr('fill', '#374151').text(a.label)

      return g
    })

    // ── Animation loop ───────────────────────────────────────
    let tid: ReturnType<typeof setTimeout>

    function loop() {
      ripple.interrupt().attr('opacity', 0)
      trigCard.interrupt().attr('stroke', '#e2e8f0').attr('stroke-width', 1.5)
      arrowPath.interrupt().attr('stroke-dashoffset', pathLen)
      actionGroups.forEach(g => g.interrupt().attr('opacity', 0))

      // 1. Trigger pulse (0–700ms)
      ripple
        .transition().delay(100).duration(350).attr('opacity', 0.5)
        .transition().duration(350).attr('opacity', 0)
      trigCard
        .transition().delay(100).duration(350)
        .attr('stroke', 'var(--highlight-color, #eab308)').attr('stroke-width', 2)
        .transition().duration(350)
        .attr('stroke', '#e2e8f0').attr('stroke-width', 1.5)

      // 2. Arrow draws (800–1300ms)
      arrowPath
        .transition().delay(800).duration(500)
        .ease(d3.easeCubicInOut)
        .attr('stroke-dashoffset', 0)

      // 3. Action cards staggered (1400–2100ms)
      actionGroups.forEach((g, i) => {
        g.transition().delay(1400 + i * 330).duration(260)
          .ease(d3.easeBackOut)
          .attr('opacity', 1)
      })

      // 4. Fade out (3100–3500ms)
      arrowPath.transition().delay(3100).duration(400).attr('stroke-dashoffset', pathLen)
      actionGroups.forEach(g => g.transition().delay(3100).duration(400).attr('opacity', 0))

      tid = setTimeout(loop, LOOP_MS)
    }

    loop()

    return () => {
      clearTimeout(tid)
      svg.selectAll('*').interrupt()
    }
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '20px 16px 8px' }}>
      <svg
        ref={svgRef}
        width={385}
        height={185}
        style={{ overflow: 'visible', maxWidth: '100%' }}
      />
      <p style={{ fontSize: 13, color: '#6b7280', marginTop: 8, textAlign: 'center', maxWidth: 300 }}>
        Create automations to trigger workflows automatically when files arrive or events occur
      </p>
    </div>
  )
}
