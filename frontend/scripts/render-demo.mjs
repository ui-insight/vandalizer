import { spawnSync } from 'node:child_process'
import { createHash, randomBytes } from 'node:crypto'
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, join, resolve } from 'node:path'
import { chromium } from 'playwright'

const frontendRoot = resolve(process.cwd())
const repositoryRoot = resolve(frontendRoot, '..')
const recipesDirectory = resolve(frontendRoot, 'demos/recipes')

function fail(message) {
  throw new Error(message)
}

function hashFile(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

function seconds(value) {
  return Number.isFinite(value) && value > 0
}

function run(command, args) {
  const result = spawnSync(command, args, { stdio: 'inherit' })
  if (result.status !== 0) fail(`${command} failed with exit code ${result.status ?? 'unknown'}`)
}

function interpolate(template, values) {
  return template.replace(/{{(\w+)}}/g, (_, key) => values[key] ?? fail(`Missing template value: ${key}`))
}

function parseArgs(args) {
  return {
    recipeId: args.find((arg) => !arg.startsWith('--')),
    check: args.includes('--check'),
    renderOnly: args.includes('--render-only'),
    skipVoice: args.includes('--skip-voice'),
  }
}

function recipePath(recipeId) {
  return resolve(recipesDirectory, `${recipeId}.json`)
}

function readRecipe(recipeId) {
  const path = recipePath(recipeId)
  if (!existsSync(path)) fail(`Unknown demo recipe: ${recipeId}`)
  return { path, recipe: JSON.parse(readFileSync(path, 'utf8')) }
}

function validateRecipe(recipe, path) {
  if (recipe.schemaVersion !== 1 || !recipe.id || !recipe.capture || !recipe.edit || !recipe.voiceover || !recipe.output) {
    fail(`${basename(path)} does not satisfy demo recipe schema v1`)
  }
  const source = resolve(repositoryRoot, recipe.capture.sourceDocument?.path || '')
  const logo = resolve(repositoryRoot, recipe.edit.intro?.logoPath || '')
  const voiceover = resolve(repositoryRoot, recipe.voiceover.scriptPath || '')
  if (!existsSync(source) || hashFile(source) !== recipe.capture.sourceDocument.sha256) fail(`${recipe.id}: source document checksum does not match recipe`)
  if (!existsSync(logo) || hashFile(logo) !== recipe.edit.intro.logoSha256) fail(`${recipe.id}: brand logo checksum does not match recipe`)
  if (!existsSync(voiceover) || !readFileSync(voiceover, 'utf8').trim()) fail(`${recipe.id}: voice-over script is missing or empty`)
  if (!recipe.edit.segments?.length || !recipe.edit.segments.every((segment) => segment.marker && seconds(segment.durationSeconds))) fail(`${recipe.id}: edit segments are invalid`)
  if (!seconds(recipe.edit.intro.durationSeconds) || !seconds(recipe.edit.intro.crossFadeSeconds)) fail(`${recipe.id}: intro timing is invalid`)
  return { source, logo, voiceover }
}

function outputs(recipe) {
  const directory = resolve(repositoryRoot, recipe.output.directory)
  mkdirSync(directory, { recursive: true })
  const prefix = join(directory, recipe.id)
  return {
    directory,
    raw: `${prefix}.raw.mp4`,
    timeline: `${prefix}.timeline.json`,
    paced: `${prefix}.paced.mp4`,
    intro: `${prefix}.intro.mp4`,
    voice: `${prefix}.voice.mp3`,
    final: `${prefix}.mp4`,
    poster: `${prefix}-poster.jpg`,
  }
}

async function waitForDocument(page, uuid, timeoutSeconds) {
  const deadline = Date.now() + timeoutSeconds * 1000
  while (Date.now() < deadline) {
    const status = await page.evaluate(async (documentUuid) => {
      const response = await fetch(`/api/documents/poll_status?docid=${encodeURIComponent(documentUuid)}`)
      return response.ok ? response.json() : { requestFailed: response.status }
    }, uuid)
    if (status.error_message) fail(`The uploaded document could not be prepared: ${status.error_message}`)
    if (status.complete || status.raw_text) return
    await page.waitForTimeout(1000)
  }
  fail('The uploaded document did not become ready before the recipe timeout')
}

async function waitForAgent(page, timeouts, allowAlreadyComplete = false) {
  const send = page.getByLabel('Send message')
  const alert = page.getByRole('alert')
  if (allowAlreadyComplete && await send.isVisible().catch(() => false)) return
  await page.getByLabel('Stop response').waitFor({ state: 'visible', timeout: timeouts.agentFirstTokenSeconds * 1000 })
  const outcome = await Promise.race([
    send.waitFor({ state: 'visible', timeout: timeouts.agentCompletionSeconds * 1000 }).then(() => 'complete'),
    alert.waitFor({ state: 'visible', timeout: timeouts.agentCompletionSeconds * 1000 }).then(() => 'error'),
  ])
  if (outcome === 'error') fail(`Agent response failed: ${await alert.innerText()}`)
}

async function setCaption(page, caption) {
  await page.evaluate(({ eyebrow, copy }) => {
    const element = document.getElementById('product-demo-caption')
    if (!element) throw new Error('Demo caption was not mounted')
    element.classList.remove('is-visible')
    window.setTimeout(() => {
      element.querySelector('[data-eyebrow]')?.replaceChildren(eyebrow)
      element.querySelector('[data-copy]')?.replaceChildren(copy)
      element.classList.add('is-visible')
    }, 180)
  }, caption)
  await page.waitForTimeout(360)
}

async function mountCaption(page, railWidth) {
  await page.evaluate((rightInset) => {
    const style = document.createElement('style')
    style.textContent = `#product-demo-caption{position:fixed;z-index:200;right:${rightInset}px;bottom:0;left:48px;padding:11px 60px 12px;border-top:1px solid rgba(255,255,255,.18);background:rgba(16,16,16,.92);box-shadow:0 -10px 30px rgba(0,0,0,.22);backdrop-filter:blur(14px);color:#f4f4f5;opacity:0;transform:translateY(100%);transition:opacity 180ms ease,transform 180ms ease;pointer-events:none;text-align:center}#product-demo-caption.is-visible{opacity:1;transform:translateY(0)}#product-demo-caption [data-eyebrow]{display:block;margin-bottom:4px;color:#facc15;font:700 10px/1.2 ui-monospace,monospace;letter-spacing:.15em;text-transform:uppercase}#product-demo-caption [data-copy]{display:block;font:600 16px/1.25 Inter,Public Sans,system-ui,sans-serif;letter-spacing:-.02em}`
    document.head.append(style)
    const caption = document.createElement('aside')
    caption.id = 'product-demo-caption'
    caption.innerHTML = '<span data-eyebrow></span><span data-copy></span>'
    document.body.append(caption)
  }, railWidth)
}

async function capture(recipe, source, output) {
  const origin = (process.env.DEMO_ORIGIN || 'http://127.0.0.1').replace(/\/$/, '')
  const runTag = process.env.DEMO_RUN_TAG || `${new Date().toISOString().replace(/[^0-9]/g, '').slice(0, 14)}-${randomBytes(3).toString('hex')}`
  const account = recipe.capture.recordingAccount
  const userId = `${account.userIdPrefix}-${runTag}`
  const email = `${userId}@${account.emailDomain}`
  const password = process.env.DEMO_ACCOUNT_PASSWORD || `demo-${randomBytes(18).toString('base64url')}`
  const register = await fetch(`${origin}/api/auth/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: userId, email, password, name: account.displayName, role_segment: recipe.capture.roleSegment }) })
  if (!register.ok) fail(`Could not create isolated demo account (${register.status})`)

  const recordingDirectory = mkdtempSync(join(tmpdir(), `vandalizer-${recipe.id}-`))
  const authPath = join(recordingDirectory, 'auth.json')
  const browser = await chromium.launch({ headless: true })
  const viewport = recipe.capture.viewport
  const bootstrap = await browser.newContext({ viewport })
  const login = await bootstrap.newPage()
  await login.goto(`${origin}/login`, { waitUntil: 'domcontentloaded' })
  await login.getByPlaceholder('Email').fill(email)
  await login.getByPlaceholder('Password').fill(password)
  await login.getByRole('button', { name: 'SIGN IN' }).click()
  await login.waitForURL((url) => url.pathname !== '/login', { timeout: 15000 })
  await bootstrap.storageState({ path: authPath })
  await bootstrap.close()

  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, storageState: authPath, recordVideo: { dir: recordingDirectory, size: viewport } })
  if (recipe.capture.ui.dismissFirstRunTour) await context.addInitScript(() => window.localStorage.setItem('vandalizer:first-run-tour-dismissed', '1'))
  const page = await context.newPage()
  const video = page.video()
  const startedAt = Date.now()
  const markers = {}
  const mark = (name) => { markers[name] = Number(((Date.now() - startedAt) / 1000).toFixed(3)) }
  const { captions, pacing, milestones, timeouts } = recipe.capture

  try {
    await page.goto(`${origin}${recipe.capture.path}`, { waitUntil: 'domcontentloaded' })
    const rail = page.locator('button[title="Collapse"], button[title="Expand"]')
    await rail.waitFor({ state: 'visible', timeout: 15000 })
    if (recipe.capture.ui.collapseActivityRail && await rail.getAttribute('title') === 'Collapse') await rail.click()
    await mountCaption(page, recipe.capture.ui.activityRailWidth)

    mark('orientation')
    await setCaption(page, captions.orientation)
    await page.waitForTimeout(pacing.orientationSeconds * 1000)
    await setCaption(page, captions.source)
    await page.waitForTimeout(pacing.sourcePromptSeconds * 1000)
    const uploaded = page.waitForResponse((response) => response.url().includes('/api/files/upload') && response.request().method() === 'POST')
    await page.getByLabel('Upload a document').setInputFiles(source)
    const response = await uploaded
    if (!response.ok) fail(`Document upload failed (${response.status()})`)
    const payload = await response.json()
    if (!payload.uuid) fail('Document upload did not return a UUID')
    await waitForDocument(page, payload.uuid, timeouts.documentReadySeconds)
    await setCaption(page, captions.sourceAttached)
    await page.waitForTimeout(pacing.sourceAttachedSeconds * 1000)

    mark('request')
    await setCaption(page, captions.request)
    await page.waitForTimeout(pacing.requestPreludeSeconds * 1000)
    await page.getByLabel('Message input').pressSequentially(interpolate(recipe.capture.request, { extractionName: recipe.capture.extractionName }), { delay: pacing.typeDelayMilliseconds })
    await page.waitForTimeout(pacing.requestReadSeconds * 1000)
    const send = page.getByLabel('Send message')
    await send.hover()
    await page.waitForTimeout(pacing.sendHoverSeconds * 1000)
    await send.click()
    mark('submitted')
    await setCaption(page, captions.proposal)
    await waitForAgent(page, timeouts)
    mark('proposalReady')
    await page.waitForTimeout(pacing.proposalReadSeconds * 1000)

    await setCaption(page, captions.approval)
    mark('approval')
    const confirm = page.getByRole('button', { name: milestones.confirmationButton })
    await confirm.waitFor({ state: 'visible', timeout: 15000 })
    await confirm.hover()
    await page.waitForTimeout(pacing.approvalHoverSeconds * 1000)
    await confirm.click()
    mark('approved')
    await setCaption(page, captions.extraction)
    await page.getByText(milestones.buildingExtractionText, { exact: false }).waitFor({ state: 'visible', timeout: timeouts.agentCompletionSeconds * 1000 })
    mark('buildingStarted')
    await page.getByText(milestones.fieldsDiscoveredText, { exact: false }).waitFor({ state: 'visible', timeout: timeouts.agentCompletionSeconds * 1000 })
    mark('fieldsDiscovered')
    await waitForAgent(page, timeouts, true)
    mark('resultReady')
    await page.waitForTimeout(pacing.resultReadSeconds * 1000)
    await setCaption(page, captions.conclusion)
    await page.waitForTimeout(pacing.conclusionSeconds * 1000)
  } finally {
    await context.close()
    await browser.close()
  }
  if (!video) fail('Playwright did not create a recording')
  const recording = await video.path()
  if (!existsSync(recording)) fail('The recorded video was not written')
  run('ffmpeg', ['-y', '-i', recording, '-c:v', 'libx264', '-preset', 'medium', '-crf', '23', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', output.raw])
  const manifest = { recipeId: recipe.id, schemaVersion: recipe.schemaVersion, capturedAt: new Date().toISOString(), origin, rawVideo: output.raw, markers, sourceDocument: recipe.capture.sourceDocument }
  writeFileSync(output.timeline, `${JSON.stringify(manifest, null, 2)}\n`)
  return manifest
}

async function synthesize(recipe, voicePath) {
  const key = process.env.MINDROUTER_API_KEY
  if (!key) fail('Set MINDROUTER_API_KEY to synthesize this demo’s voice-over')
  const response = await fetch(recipe.voiceover.endpoint, { method: 'POST', headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ model: recipe.voiceover.model, input: readFileSync(resolve(repositoryRoot, recipe.voiceover.scriptPath), 'utf8').trim(), voice: recipe.voiceover.voice, response_format: recipe.voiceover.responseFormat, speed: recipe.voiceover.speed }) })
  if (!response.ok) fail(`Voice synthesis failed (${response.status})`)
  writeFileSync(voicePath, Buffer.from(await response.arrayBuffer()))
}

function renderPaced(recipe, raw, timeline, paced) {
  const filters = recipe.edit.segments.map((segment, index) => {
    const start = timeline.markers[segment.marker]
    if (!Number.isFinite(start)) fail(`Run timeline is missing marker: ${segment.marker}`)
    return `[0:v]trim=start=${start}:end=${start + segment.durationSeconds},setpts=PTS-STARTPTS[v${index}]`
  })
  const inputs = recipe.edit.segments.map((_, index) => `[v${index}]`).join('')
  filters.push(`${inputs}concat=n=${recipe.edit.segments.length}:v=1:a=0,format=yuv420p[v]`)
  run('ffmpeg', ['-y', '-i', raw, '-filter_complex', filters.join(';'), '-map', '[v]', '-c:v', 'libx264', '-crf', '20', '-preset', 'medium', '-movflags', '+faststart', paced])
}

function renderIntro(recipe, logo, introPath) {
  const config = recipe.edit.intro
  run('ffmpeg', ['-y', '-f', 'lavfi', '-i', `color=c=${config.background}:s=1280x720:d=${config.durationSeconds}`, '-loop', '1', '-i', logo, '-filter_complex', `[1:v]scale=${config.logoWidthPixels}:-1,format=rgba,fade=t=in:st=0:d=${config.fadeInSeconds}:alpha=1,fade=t=out:st=${config.fadeOutStartSeconds}:d=${config.fadeOutSeconds}:alpha=1[logo];[0:v][logo]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p[v]`, '-map', '[v]', '-t', String(config.durationSeconds), '-r', '25', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', introPath])
}

function renderFinal(recipe, output, hasVoice) {
  const intro = recipe.edit.intro
  const videoFilter = `[0:v][1:v]xfade=transition=fade:duration=${intro.crossFadeSeconds}:offset=${intro.durationSeconds - intro.crossFadeSeconds},tpad=stop_mode=clone:stop_duration=6,format=yuv420p[v]`
  const args = ['-y', '-i', output.intro, '-i', output.paced]
  if (hasVoice) args.push('-i', output.voice, '-filter_complex', `${videoFilter};[2:a]adelay=${Math.round(intro.voiceDelaySeconds * 1000)}:all=1[a]`, '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-crf', '20', '-preset', 'medium', '-movflags', '+faststart', '-c:a', 'aac', '-b:a', '128k', '-shortest', output.final)
  else args.push('-filter_complex', videoFilter, '-map', '[v]', '-c:v', 'libx264', '-crf', '20', '-preset', 'medium', '-movflags', '+faststart', output.final)
  run('ffmpeg', args)
  run('ffmpeg', ['-y', '-ss', String(recipe.output.posterTimeSeconds), '-i', output.final, '-frames:v', '1', '-q:v', '2', output.poster])
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  if (args.check) {
    const ids = readdirSync(recipesDirectory).filter((file) => file.endsWith('.json')).map((file) => file.slice(0, -5))
    ids.forEach((id) => { const { path, recipe } = readRecipe(id); validateRecipe(recipe, path); console.log(`✓ ${id}`) })
    return
  }
  if (!args.recipeId) fail('Usage: npm run demo:render -- <recipe-id> [--render-only] [--skip-voice]')
  const { path, recipe } = readRecipe(args.recipeId)
  const assets = validateRecipe(recipe, path)
  const output = outputs(recipe)
  const timeline = args.renderOnly ? JSON.parse(readFileSync(output.timeline, 'utf8')) : await capture(recipe, assets.source, output)
  if (args.renderOnly && !existsSync(output.raw)) fail('No raw recording exists for --render-only')
  renderPaced(recipe, output.raw, timeline, output.paced)
  renderIntro(recipe, assets.logo, output.intro)
  if (!args.skipVoice && (!args.renderOnly || !existsSync(output.voice))) await synthesize(recipe, output.voice)
  renderFinal(recipe, output, !args.skipVoice)
  console.log(`Created ${output.final}`)
}

main().catch((error) => { console.error(error instanceof Error ? error.message : error); process.exitCode = 1 })
