import { useEffect, useRef } from 'react'
import * as d3 from 'd3'

const FILES = [
  { name: 'research_proposal.pdf', meta: '24 pages' },
  { name: 'budget_report.pdf', meta: '8 pages' },
  { name: 'IRB_approval.pdf', meta: '3 pages' },
]

const LOOP_MS = 4500

export function FileBrowserTutorial({ highlighted }: { highlighted?: boolean }) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    const el = svgRef.current
    if (!el) return

    const svg = d3.select(el)
    svg.selectAll('*').remove()

    // Layout
    const UPL_X = 10, UPL_Y = 20, UPL_W = 105, UPL_H = 145
    const UPL_CX = UPL_X + UPL_W / 2
    const UPL_CY = UPL_Y + UPL_H / 2
    const LIST_X = 218, LIST_Y = 20, LIST_W = 152, LIST_H = 145
    const ARROW_X1 = UPL_X + UPL_W + 5
    const ARROW_X2 = LIST_X - 5
    const ARROW_Y = UPL_Y + UPL_H / 2
    const MID_X = (ARROW_X1 + ARROW_X2) / 2

    // ── Defs ────────────────────────────────────────────────
    const defs = svg.append('defs')
    defs.append('marker')
      .attr('id', 'fb-arrow-tip')
      .attr('viewBox', '0 0 10 10')
      .attr('refX', 9).attr('refY', 5)
      .attr('markerWidth', 6).attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path').attr('d', 'M0,0 L10,5 L0,10 Z')
      .attr('fill', 'var(--highlight-color, #eab308)')

    // ── Upload zone ─────────────────────────────────────────
    svg.append('rect')
      .attr('class', 'upl-border')
      .attr('x', UPL_X).attr('y', UPL_Y)
      .attr('width', UPL_W).attr('height', UPL_H)
      .attr('rx', 8)
      .attr('fill', 'none')
      .attr('stroke', '#94a3b8')
      .attr('stroke-width', 1.5)
      .attr('stroke-dasharray', '6 4')

    svg.append('circle')
      .attr('cx', UPL_CX).attr('cy', UPL_CY - 10)
      .attr('r', 22)
      .attr('fill', 'color-mix(in srgb, var(--highlight-color, #eab308) 10%, white)')
      .attr('stroke', 'var(--highlight-color, #eab308)')
      .attr('stroke-width', 1.5)

    // Animated upload arrow symbol
    const uploadSymbol = svg.append('g')
      .attr('transform', `translate(${UPL_CX}, ${UPL_CY - 10})`)

    uploadSymbol.append('path')
      .attr('d', 'M0,9 L0,-3 M-6,3 L0,-9 L6,3')
      .attr('fill', 'none')
      .attr('stroke', 'var(--highlight-color, #eab308)')
      .attr('stroke-width', 2)
      .attr('stroke-linecap', 'round')
      .attr('stroke-linejoin', 'round')

    svg.append('text')
      .attr('class', 'upl-label')
      .attr('x', UPL_CX).attr('y', UPL_Y + UPL_H - 18)
      .attr('text-anchor', 'middle')
      .attr('font-size', 8).attr('font-weight', 700)
      .attr('fill', '#94a3b8').attr('letter-spacing', 1)
      .text('DRAG FILES HERE')

    // ── Arrow ────────────────────────────────────────────────
    const arrowPath = svg.append('path')
      .attr('d', `M ${ARROW_X1},${ARROW_Y} C ${MID_X - 8},${ARROW_Y} ${MID_X + 8},${ARROW_Y} ${ARROW_X2},${ARROW_Y}`)
      .attr('fill', 'none')
      .attr('stroke', 'var(--highlight-color, #eab308)')
      .attr('stroke-width', 2)
      .attr('marker-end', 'url(#fb-arrow-tip)')

    const pathLen = (arrowPath.node() as SVGPathElement).getTotalLength()
    arrowPath.attr('stroke-dasharray', pathLen).attr('stroke-dashoffset', pathLen)

    // ── File list panel ──────────────────────────────────────
    svg.append('rect')
      .attr('x', LIST_X).attr('y', LIST_Y)
      .attr('width', LIST_W).attr('height', LIST_H)
      .attr('rx', 7)
      .attr('fill', 'white')
      .attr('stroke', '#e2e8f0').attr('stroke-width', 1.5)

    svg.append('text')
      .attr('x', LIST_X + 12).attr('y', LIST_Y + 16)
      .attr('font-size', 7.5).attr('font-weight', 700)
      .attr('fill', '#94a3b8').attr('letter-spacing', 1)
      .text('FILES')

    svg.append('line')
      .attr('x1', LIST_X + 1).attr('y1', LIST_Y + 22)
      .attr('x2', LIST_X + LIST_W - 1).attr('y2', LIST_Y + 22)
      .attr('stroke', '#e2e8f0').attr('stroke-width', 1)

    // File rows
    const ROW_H = 34, ROW_GAP = 5, ROW_START_Y = LIST_Y + 27
    const fileGroups = FILES.map((f, i) => {
      const gy = ROW_START_Y + i * (ROW_H + ROW_GAP)
      const g = svg.append('g')
        .attr('transform', `translate(${LIST_X}, ${gy})`)
        .attr('opacity', 0)

      g.append('rect')
        .attr('x', 6).attr('width', LIST_W - 12).attr('height', ROW_H)
        .attr('rx', 5)
        .attr('fill', '#f8fafc')
        .attr('stroke', '#e2e8f0').attr('stroke-width', 1)

      // Tiny file icon
      g.append('rect')
        .attr('x', 14).attr('y', 9)
        .attr('width', 10).attr('height', 13)
        .attr('rx', 1.5).attr('fill', '#e2e8f0')
      g.append('path')
        .attr('d', 'M21,9 L24,12 L21,12 Z')
        .attr('fill', '#cbd5e1')

      g.append('text')
        .attr('x', 30).attr('y', 19)
        .attr('font-size', 10).attr('font-weight', 500)
        .attr('fill', '#374151').text(f.name)

      g.append('text')
        .attr('x', 30).attr('y', 30)
        .attr('font-size', 8.5).attr('fill', '#9ca3af').text(f.meta)

      return g
    })

    // ── Animation loop ───────────────────────────────────────
    let tid: ReturnType<typeof setTimeout>

    function loop() {
      uploadSymbol.interrupt()
        .attr('transform', `translate(${UPL_CX}, ${UPL_CY - 10})`)
      arrowPath.interrupt().attr('stroke-dashoffset', pathLen)
      fileGroups.forEach(g => g.interrupt().attr('opacity', 0))

      // 1. Upload arrow bounces up (0–600ms)
      uploadSymbol
        .transition().duration(300).ease(d3.easeQuadOut)
        .attr('transform', `translate(${UPL_CX}, ${UPL_CY - 18})`)
        .transition().duration(300).ease(d3.easeQuadIn)
        .attr('transform', `translate(${UPL_CX}, ${UPL_CY - 10})`)

      // 2. Arrow draws (700–1200ms)
      arrowPath
        .transition().delay(700).duration(500)
        .ease(d3.easeCubicInOut)
        .attr('stroke-dashoffset', 0)

      // 3. File rows appear staggered (1300–2000ms)
      fileGroups.forEach((g, i) => {
        g.transition().delay(1300 + i * 320).duration(260)
          .ease(d3.easeBackOut)
          .attr('opacity', 1)
      })

      // 4. Fade dynamic elements (3100–3500ms)
      arrowPath.transition().delay(3100).duration(400).attr('stroke-dashoffset', pathLen)
      fileGroups.forEach(g => g.transition().delay(3100).duration(400).attr('opacity', 0))

      tid = setTimeout(loop, LOOP_MS)
    }

    loop()

    return () => {
      clearTimeout(tid)
      svg.selectAll('*').interrupt()
    }
  }, [])

  // Toggle highlight on the upload zone when files are dragged over the panel
  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    const svg = d3.select(el)
    const hl = 'var(--highlight-color, #eab308)'
    svg.select('.upl-border')
      .attr('stroke', highlighted ? hl : '#94a3b8')
      .attr('stroke-width', highlighted ? 2.5 : 1.5)
      .attr('fill', highlighted ? 'color-mix(in srgb, var(--highlight-color, #eab308) 6%, white)' : 'none')
    svg.select('.upl-label')
      .attr('fill', highlighted ? hl : '#94a3b8')
      .text(highlighted ? 'DROP FILES HERE' : 'DRAG FILES HERE')
  }, [highlighted])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '20px 16px 8px' }}>
      <svg
        ref={svgRef}
        width={385}
        height={185}
        style={{ overflow: 'visible', maxWidth: '100%' }}
      />
      <p style={{ fontSize: 13, color: '#6b7280', marginTop: 8, textAlign: 'center', maxWidth: 300 }}>
        Upload PDFs, Word docs, or spreadsheets using the Add button above
      </p>
    </div>
  )
}
