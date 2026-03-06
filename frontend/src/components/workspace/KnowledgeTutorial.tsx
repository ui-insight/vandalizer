import { useEffect, useRef } from 'react'
import * as d3 from 'd3'

const LOOP_MS = 5000

// Stacked doc layers: back → front
const DOC_STACK = [
  { x: 8, y: 30, opacity: 0.4 },
  { x: 16, y: 21, opacity: 0.65 },
  { x: 24, y: 12, opacity: 1 },
]

export function KnowledgeTutorial() {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    const el = svgRef.current
    if (!el) return

    const svg = d3.select(el)
    svg.selectAll('*').remove()

    // Layout
    const DOC_W = 80, DOC_H = 115
    const KB_CX = 170, KB_CY = 90, KB_R = 28
    const CHAT_X = 218, CHAT_Y = 15, CHAT_W = 157, CHAT_H = 158

    const frontDoc = DOC_STACK[2]
    const ARROW1_X1 = frontDoc.x + DOC_W + 4
    const ARROW1_X2 = KB_CX - KB_R - 4
    const ARROW1_Y = frontDoc.y + DOC_H * 0.55
    const ARROW2_X1 = KB_CX + KB_R + 4
    const ARROW2_X2 = CHAT_X - 4
    const ARROW2_Y = KB_CY

    // ── Defs ────────────────────────────────────────────────
    const defs = svg.append('defs')
    defs.append('marker')
      .attr('id', 'kb-arrow-tip')
      .attr('viewBox', '0 0 10 10')
      .attr('refX', 9).attr('refY', 5)
      .attr('markerWidth', 6).attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path').attr('d', 'M0,0 L10,5 L0,10 Z')
      .attr('fill', 'var(--highlight-color, #eab308)')

    // ── Stacked document cards ───────────────────────────────
    const fold = 11
    const docGroups = DOC_STACK.map((d) => {
      const g = svg.append('g').attr('opacity', 0)

      g.append('rect')
        .attr('x', d.x).attr('y', d.y)
        .attr('width', DOC_W).attr('height', DOC_H)
        .attr('rx', 5).attr('fill', '#f8fafc')
        .attr('stroke', '#e2e8f0').attr('stroke-width', 1.5)

      g.append('path')
        .attr('d', `M ${d.x + DOC_W - fold} ${d.y} L ${d.x + DOC_W} ${d.y + fold} L ${d.x + DOC_W - fold} ${d.y + fold} Z`)
        .attr('fill', '#e2e8f0')

      ;[0, 1, 2, 3, 4].forEach((li) => {
        g.append('rect')
          .attr('x', d.x + 9).attr('y', d.y + 20 + li * 14)
          .attr('width', li === 2 ? 36 : 55).attr('height', 5)
          .attr('rx', 2.5).attr('fill', '#cbd5e1')
      })

      return g
    })

    // ── KB circle ────────────────────────────────────────────
    const kbG = svg.append('g').attr('opacity', 0)

    kbG.append('circle')
      .attr('cx', KB_CX).attr('cy', KB_CY).attr('r', KB_R)
      .attr('fill', 'white')
      .attr('stroke', '#e2e8f0').attr('stroke-width', 1.5)

    const kbInner = kbG.append('circle')
      .attr('cx', KB_CX).attr('cy', KB_CY).attr('r', KB_R - 7)
      .attr('fill', 'color-mix(in srgb, var(--highlight-color, #eab308) 12%, white)')
      .attr('stroke', 'var(--highlight-color, #eab308)').attr('stroke-width', 1.5)

    kbG.append('text')
      .attr('x', KB_CX).attr('y', KB_CY + 4)
      .attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
      .attr('font-size', 11).attr('font-weight', 700)
      .attr('fill', 'var(--highlight-color, #eab308)').text('KB')

    // ── Arrows ───────────────────────────────────────────────
    const mid1x = (ARROW1_X1 + ARROW1_X2) / 2

    const arrowPath1 = svg.append('path')
      .attr('d', `M ${ARROW1_X1},${ARROW1_Y} C ${mid1x},${ARROW1_Y} ${mid1x},${ARROW2_Y} ${ARROW1_X2},${ARROW2_Y}`)
      .attr('fill', 'none')
      .attr('stroke', 'var(--highlight-color, #eab308)')
      .attr('stroke-width', 2)
      .attr('marker-end', 'url(#kb-arrow-tip)')

    const pathLen1 = (arrowPath1.node() as SVGPathElement).getTotalLength()
    arrowPath1.attr('stroke-dasharray', pathLen1).attr('stroke-dashoffset', pathLen1)

    const arrowPath2 = svg.append('path')
      .attr('d', `M ${ARROW2_X1},${ARROW2_Y} L ${ARROW2_X2},${ARROW2_Y}`)
      .attr('fill', 'none')
      .attr('stroke', 'var(--highlight-color, #eab308)')
      .attr('stroke-width', 2)
      .attr('marker-end', 'url(#kb-arrow-tip)')

    const pathLen2 = (arrowPath2.node() as SVGPathElement).getTotalLength()
    arrowPath2.attr('stroke-dasharray', pathLen2).attr('stroke-dashoffset', pathLen2)

    // ── Chat panel ───────────────────────────────────────────
    const chatG = svg.append('g').attr('opacity', 0)

    chatG.append('rect')
      .attr('x', CHAT_X).attr('y', CHAT_Y)
      .attr('width', CHAT_W).attr('height', CHAT_H)
      .attr('rx', 7).attr('fill', 'white')
      .attr('stroke', '#e2e8f0').attr('stroke-width', 1.5)

    chatG.append('text')
      .attr('x', CHAT_X + 12).attr('y', CHAT_Y + 16)
      .attr('font-size', 7.5).attr('font-weight', 700)
      .attr('fill', '#94a3b8').attr('letter-spacing', 1)
      .text('CHAT')

    chatG.append('line')
      .attr('x1', CHAT_X + 1).attr('y1', CHAT_Y + 22)
      .attr('x2', CHAT_X + CHAT_W - 1).attr('y2', CHAT_Y + 22)
      .attr('stroke', '#e2e8f0').attr('stroke-width', 1)

    // Question bubble
    chatG.append('rect')
      .attr('x', CHAT_X + 8).attr('y', CHAT_Y + 28)
      .attr('width', CHAT_W - 22).attr('height', 30)
      .attr('rx', 6).attr('fill', '#f3f4f6')

    chatG.append('text')
      .attr('x', CHAT_X + 16).attr('y', CHAT_Y + 47)
      .attr('font-size', 9.5).attr('fill', '#374151')
      .text('What is the total budget?')

    chatG.append('line')
      .attr('x1', CHAT_X + 12).attr('y1', CHAT_Y + 70)
      .attr('x2', CHAT_X + CHAT_W - 12).attr('y2', CHAT_Y + 70)
      .attr('stroke', '#e2e8f0').attr('stroke-width', 1)

    // Answer
    chatG.append('text')
      .attr('x', CHAT_X + 12).attr('y', CHAT_Y + 88)
      .attr('font-size', 8).attr('font-weight', 600)
      .attr('fill', '#9ca3af').attr('letter-spacing', 0.5)
      .text('ANSWER')

    chatG.append('text')
      .attr('x', CHAT_X + 12).attr('y', CHAT_Y + 110)
      .attr('font-size', 15).attr('font-weight', 700)
      .attr('fill', '#111827').text('$2.4M in grants')

    chatG.append('text')
      .attr('x', CHAT_X + 12).attr('y', CHAT_Y + 128)
      .attr('font-size', 9).attr('fill', '#9ca3af')
      .text('across 3 active projects')

    // ── Animation loop ───────────────────────────────────────
    let tid: ReturnType<typeof setTimeout>

    function loop() {
      docGroups.forEach(g => g.interrupt().attr('opacity', 0))
      kbG.interrupt().attr('opacity', 0)
      kbInner.interrupt().attr('r', KB_R - 7)
      arrowPath1.interrupt().attr('stroke-dashoffset', pathLen1)
      arrowPath2.interrupt().attr('stroke-dashoffset', pathLen2)
      chatG.interrupt().attr('opacity', 0)

      // 1. Doc stack builds back-to-front (0–600ms)
      docGroups.forEach((g, i) => {
        g.transition().delay(i * 180).duration(240)
          .ease(d3.easeBackOut)
          .attr('opacity', DOC_STACK[i].opacity)
      })

      // 2. Arrow 1 draws docs → KB (800–1300ms)
      arrowPath1
        .transition().delay(800).duration(500)
        .ease(d3.easeCubicInOut)
        .attr('stroke-dashoffset', 0)

      // 3. KB pops in and pulses (1300–1700ms)
      kbG.transition().delay(1300).duration(220)
        .ease(d3.easeBackOut.overshoot(2))
        .attr('opacity', 1)

      kbInner
        .transition().delay(1300).duration(200).attr('r', KB_R - 3)
        .transition().duration(200).attr('r', KB_R - 7)

      // 4. Arrow 2 draws KB → chat (1800–2200ms)
      arrowPath2
        .transition().delay(1800).duration(400)
        .ease(d3.easeCubicInOut)
        .attr('stroke-dashoffset', 0)

      // 5. Chat panel appears (2300ms)
      chatG.transition().delay(2300).duration(300)
        .ease(d3.easeBackOut)
        .attr('opacity', 1)

      // 6. Fade all dynamic elements (3700–4100ms)
      const fadeAt = 3700
      arrowPath1.transition().delay(fadeAt).duration(400).attr('stroke-dashoffset', pathLen1)
      arrowPath2.transition().delay(fadeAt).duration(400).attr('stroke-dashoffset', pathLen2)
      kbG.transition().delay(fadeAt).duration(400).attr('opacity', 0)
      chatG.transition().delay(fadeAt).duration(400).attr('opacity', 0)
      docGroups.forEach(g => g.transition().delay(fadeAt).duration(400).attr('opacity', 0))

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
        height={190}
        style={{ overflow: 'visible', maxWidth: '100%' }}
      />
      <p style={{ fontSize: 13, color: '#6b7280', marginTop: 8, textAlign: 'center', maxWidth: 300 }}>
        Build a knowledge base from your documents to enable AI-powered chat and search
      </p>
    </div>
  )
}
