import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { chromium } from 'playwright'

const origin = (process.env.WALKTHROUGH_ORIGIN || 'http://127.0.0.1:5173').replace(/\/$/, '')
const outputPath = resolve(process.cwd(), 'public/videos/vandalizer-5-walkthrough.mp4')
const posterPath = resolve(process.cwd(), 'public/videos/vandalizer-5-walkthrough-poster.jpg')
const recordingDir = mkdtempSync(join(tmpdir(), 'vandalizer-v5-walkthrough-'))

mkdirSync(dirname(outputPath), { recursive: true })

function runFfmpeg(args) {
  const result = spawnSync('ffmpeg', args, { stdio: 'inherit' })
  if (result.status !== 0) throw new Error(`ffmpeg failed with exit code ${result.status ?? 'unknown'}`)
}

async function setCaption(page, eyebrow, copy) {
  await page.evaluate(({ eyebrow: nextEyebrow, copy: nextCopy }) => {
    const caption = document.getElementById('v5-walkthrough-caption')
    if (!caption) throw new Error('Walkthrough caption was not mounted')
    caption.classList.remove('is-visible')
    window.setTimeout(() => {
      caption.querySelector('[data-eyebrow]')?.replaceChildren(nextEyebrow)
      caption.querySelector('[data-copy]')?.replaceChildren(nextCopy)
      caption.classList.add('is-visible')
    }, 180)
  }, { eyebrow, copy })
  await page.waitForTimeout(300)
}

async function scrollTo(page, selector, offset = 56) {
  await page.evaluate(async ({ targetSelector, topOffset }) => {
    const target = document.querySelector(targetSelector)
    if (!target) throw new Error(`Missing walkthrough target: ${targetSelector}`)

    const start = window.scrollY
    const end = Math.max(0, target.getBoundingClientRect().top + window.scrollY - topOffset)
    const duration = 900
    const startedAt = performance.now()

    await new Promise((resolveScroll) => {
      const step = (now) => {
        const progress = Math.min(1, (now - startedAt) / duration)
        const eased = 1 - Math.pow(1 - progress, 4)
        window.scrollTo(0, start + (end - start) * eased)
        if (progress < 1) window.requestAnimationFrame(step)
        else resolveScroll()
      }
      window.requestAnimationFrame(step)
    })
  }, { targetSelector: selector, topOffset: offset })
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
    recordVideo: { dir: recordingDir, size: { width: 1280, height: 720 } },
  })
  const page = await context.newPage()
  const video = page.video()

  try {
    await page.goto(`${origin}/landing`, { waitUntil: 'domcontentloaded' })
    await page.locator('#main-content').waitFor({ state: 'visible', timeout: 12000 })
    await page.waitForTimeout(900)
    await page.evaluate(() => {
      document.querySelector('.launch-video-section')?.setAttribute('style', 'display: none !important')

      const style = document.createElement('style')
      style.textContent = `
        #v5-walkthrough-caption {
          position: fixed;
          z-index: 200;
          left: 48px;
          bottom: 44px;
          width: min(500px, calc(100vw - 96px));
          padding: 17px 20px 18px;
          border: 1px solid rgba(255,255,255,.18);
          border-radius: 17px;
          background: rgba(10,10,11,.76);
          box-shadow: 0 16px 50px rgba(0,0,0,.32);
          backdrop-filter: blur(16px);
          color: #f4f4f5;
          opacity: 0;
          transform: translateY(9px);
          transition: opacity 180ms ease, transform 180ms ease;
          pointer-events: none;
        }
        #v5-walkthrough-caption.is-visible { opacity: 1; transform: translateY(0); }
        #v5-walkthrough-caption [data-eyebrow] {
          display: block;
          margin-bottom: 5px;
          color: #facc15;
          font: 700 10px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
          letter-spacing: .15em;
          text-transform: uppercase;
        }
        #v5-walkthrough-caption [data-copy] {
          display: block;
          font: 600 18px/1.28 Inter, Public Sans, system-ui, sans-serif;
          letter-spacing: -.025em;
        }
      `
      document.head.append(style)

      const caption = document.createElement('aside')
      caption.id = 'v5-walkthrough-caption'
      caption.innerHTML = '<span data-eyebrow></span><span data-copy></span>'
      document.body.append(caption)
    })

    await setCaption(page, 'Vandalizer 5.0', 'Everything your office can do. Now, you just ask.')
    await page.waitForTimeout(3700)

    await scrollTo(page, '.launch-product-shadow', 76)
    await setCaption(page, 'Project-scoped agent', 'Give the agent a bounded job, then watch every step surface in chat.')
    await page.waitForTimeout(4200)

    await scrollTo(page, '#agent')
    await setCaption(page, 'Natural-language tools', 'Find, know, extract, run, and verify—without leaving the conversation.')
    await page.waitForTimeout(4000)

    await scrollTo(page, '#projects')
    await setCaption(page, 'Projects', 'Every file, trusted tool, and teammate stays in the context of the work.')
    await page.waitForTimeout(4000)

    await scrollTo(page, '#trust')
    await setCaption(page, 'Trust layer', 'Citations, quality signals, and test cases make the answer reviewable.')
    await page.waitForTimeout(4000)

    await scrollTo(page, '.launch-control-section')
    await setCaption(page, 'Human control', 'The agent prepares the work. Your team stays at the approval gate.')
    await page.waitForTimeout(4300)

    await scrollTo(page, '#demo')
    await setCaption(page, 'Vandalizer 5.0', 'Built for the work that needs to be right.')
    await page.waitForTimeout(3300)
  } finally {
    await context.close()
    await browser.close()
  }

  if (!video) throw new Error('Playwright did not create a video recording')
  const recordingPath = await video.path()
  if (!existsSync(recordingPath)) throw new Error(`Recording was not written: ${recordingPath}`)

  runFfmpeg([
    '-y', '-i', recordingPath,
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', outputPath,
  ])
  runFfmpeg(['-y', '-ss', '00:00:16', '-i', outputPath, '-frames:v', '1', '-q:v', '2', posterPath])

  console.log(`Created ${outputPath}`)
  console.log(`Created ${posterPath}`)
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
