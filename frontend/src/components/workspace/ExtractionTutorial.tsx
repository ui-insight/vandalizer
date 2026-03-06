import { useEffect, useRef } from 'react'
import * as d3 from 'd3'

const FIELDS = [
  { label: 'Award Amount', value: '$125,000' },
  { label: 'PI Name', value: 'Dr. J. Smith' },
  { label: 'End Date', value: 'Dec 31, 2025' },
]

const LOOP_MS = 4800

export function ExtractionTutorial() {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    const el = svgRef.current
    if (!el) return

    const svg = d3.select(el)
    svg.selectAll('*').remove()

    // Layout constants
    const DOC_X = 10, DOC_Y = 20, DOC_W = 115, DOC_H = 158
    const RES_X = 240, RES_Y = 20, RES_W = 140, RES_H = 44
    const ARROW_X1 = DOC_X + DOC_W + 5
    const ARROW_X2 = RES_X - 5
    const ARROW_Y = DOC_Y + DOC_H / 2
    const MID_X = (ARROW_X1 + ARROW_X2) / 2

    // ── Defs ────────────────────────────────────────────────
    const defs = svg.append('defs')
    defs.append('marker')
      .attr('id', 'arrow-tip')
      .attr('viewBox', '0 0 10 10')
      .attr('refX', 9).attr('refY', 5)
      .attr('markerWidth', 6).attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,0 L10,5 L0,10 Z')
      .attr('fill', 'var(--highlight-color, #eab308)')

    // ── Document card ────────────────────────────────────────
    const docG = svg.append('g')

    docG.append('rect')
      .attr('x', DOC_X).attr('y', DOC_Y)
      .attr('width', DOC_W).attr('height', DOC_H)
      .attr('rx', 7)
      .attr('fill', '#f8fafc')
      .attr('stroke', '#e2e8f0').attr('stroke-width', 1.5)

    // Dog-ear corner fold
    const fold = 14
    docG.append('path')
      .attr('d', `M ${DOC_X + DOC_W - fold} ${DOC_Y} L ${DOC_X + DOC_W} ${DOC_Y + fold} L ${DOC_X + DOC_W - fold} ${DOC_Y + fold} Z`)
      .attr('fill', '#e2e8f0')

    docG.append('text')
      .attr('x', DOC_X + 10).attr('y', DOC_Y + 16)
      .attr('font-size', 7.5).attr('font-weight', 700)
      .attr('fill', '#94a3b8').attr('letter-spacing', 1)
      .text('DOCUMENT')

    // Text line stubs
    const lineGap = 14
    const lineStartY = DOC_Y + 27
    const lineWidths = [88, 72, 55, 80, 62, 90, 50, 75, 60]
    lineWidths.forEach((w, i) => {
      docG.append('rect')
        .attr('x', DOC_X + 10)
        .attr('y', lineStartY + i * lineGap)
        .attr('width', w).attr('height', 5)
        .attr('rx', 2.5)
        .attr('fill', '#cbd5e1')
    })

    // Scan highlight — sweeps across a band of lines
    const SCAN_LINE_START = 1
    const SCAN_LINE_END = 4
    const scan = docG.append('rect')
      .attr('x', DOC_X + 6)
      .attr('y', lineStartY + SCAN_LINE_START * lineGap - 4)
      .attr('width', DOC_W - 12).attr('height', 14)
      .attr('rx', 3)
      .attr('fill', 'var(--highlight-color, #eab308)')
      .attr('opacity', 0)

    // ── Arrow ────────────────────────────────────────────────
    const arrowPath = svg.append('path')
      .attr('d', `M ${ARROW_X1},${ARROW_Y} C ${MID_X - 8},${ARROW_Y} ${MID_X + 8},${ARROW_Y} ${ARROW_X2},${ARROW_Y}`)
      .attr('fill', 'none')
      .attr('stroke', 'var(--highlight-color, #eab308)')
      .attr('stroke-width', 2)
      .attr('marker-end', 'url(#arrow-tip)')

    const pathLen = (arrowPath.node() as SVGPathElement).getTotalLength()
    arrowPath.attr('stroke-dasharray', pathLen).attr('stroke-dashoffset', pathLen)

    // ── AI bubble ────────────────────────────────────────────
    const bubble = svg.append('g')
      .attr('transform', `translate(${MID_X}, ${ARROW_Y})`)
      .attr('opacity', 0)

    bubble.append('circle')
      .attr('r', 15)
      .attr('fill', 'white')
      .attr('stroke', 'var(--highlight-color, #eab308)').attr('stroke-width', 1.5)

    bubble.append('text')
      .attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
      .attr('font-size', 10).attr('font-weight', 700)
      .attr('fill', 'var(--highlight-color, #eab308)')
      .text('AI')

    // ── Result cards ─────────────────────────────────────────
    const fieldGroups = FIELDS.map((f, i) => {
      const g = svg.append('g')
        .attr('transform', `translate(${RES_X}, ${RES_Y + i * (RES_H + 10)})`)
        .attr('opacity', 0)

      g.append('rect')
        .attr('width', RES_W).attr('height', RES_H)
        .attr('rx', 6)
        .attr('fill', 'white')
        .attr('stroke', '#e2e8f0').attr('stroke-width', 1.5)

      g.append('text')
        .attr('x', 10).attr('y', 16)
        .attr('font-size', 8).attr('font-weight', 600)
        .attr('fill', '#9ca3af').attr('letter-spacing', 0.5)
        .text(f.label.toUpperCase())

      g.append('text')
        .attr('x', 10).attr('y', 33)
        .attr('font-size', 13).attr('font-weight', 600)
        .attr('fill', '#111827')
        .text(f.value)

      return g
    })

    // ── Animation loop ───────────────────────────────────────
    let tid: ReturnType<typeof setTimeout>

    function loop() {
      // Reset all animated elements
      scan.interrupt().attr('opacity', 0)
        .attr('y', lineStartY + SCAN_LINE_START * lineGap - 4)
      arrowPath.interrupt().attr('stroke-dashoffset', pathLen)
      bubble.interrupt().attr('opacity', 0)
      fieldGroups.forEach(g => g.interrupt().attr('opacity', 0))

      // 1. Scan line fades in then sweeps down (t=200–900ms)
      scan
        .transition().delay(200).duration(200).attr('opacity', 0.3)
        .transition().duration(500).ease(d3.easeLinear)
        .attr('y', lineStartY + SCAN_LINE_END * lineGap - 4)

      // 2. Arrow draws left-to-right (t=700–1300ms)
      arrowPath
        .transition().delay(700).duration(600)
        .ease(d3.easeCubicInOut)
        .attr('stroke-dashoffset', 0)

      // 3. AI bubble pops in at arrow midpoint (t=900ms)
      bubble
        .transition().delay(900).duration(220)
        .ease(d3.easeBackOut.overshoot(2))
        .attr('opacity', 1)

      // 4. Result cards appear staggered (t=1400ms+)
      fieldGroups.forEach((g, i) => {
        g.transition().delay(1400 + i * 380).duration(260)
          .ease(d3.easeBackOut)
          .attr('opacity', 1)
      })

      // 5. Fade everything out before next loop
      const fadeAt = 1400 + FIELDS.length * 380 + 850
      scan.transition().delay(fadeAt).duration(350).attr('opacity', 0)
      arrowPath.transition().delay(fadeAt).duration(350).attr('stroke-dashoffset', pathLen)
      bubble.transition().delay(fadeAt).duration(350).attr('opacity', 0)
      fieldGroups.forEach(g => g.transition().delay(fadeAt).duration(350).attr('opacity', 0))

      tid = setTimeout(loop, LOOP_MS)
    }

    loop()

    return () => {
      clearTimeout(tid)
      svg.selectAll('*').interrupt()
    }
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '24px 16px 8px' }}>
      <svg
        ref={svgRef}
        width={390}
        height={200}
        style={{ overflow: 'visible', maxWidth: '100%' }}
      />
      <p style={{ fontSize: 13, color: '#6b7280', marginTop: 8, textAlign: 'center', maxWidth: 300 }}>
        Add fields below and run an extraction to pull structured data from your documents
      </p>
    </div>
  )
}
