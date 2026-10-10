import assert from 'node:assert/strict'

// Traverse with real keyboard events. Do not use locator.focus(), click(), or
// scrollIntoView() to make an otherwise unreachable action pass this check.
export function keyboardJourney(review) {
  const { page } = review
  const steps = []
  review.observations.push({ keyboardOnlyActions: steps, actualScreenReader: false })
  async function record(key) {
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    const value = await page.evaluate(() => {
      const el = document.activeElement, r = el.getBoundingClientRect(), style = getComputedStyle(el)
      const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
      return { name: el.getAttribute('aria-label') || [...el.labels || []].map(label => label.textContent.trim()).join(' ') || el.textContent.trim().slice(0, 120),
        tag: el.tagName, type: el.type, inCourse: !!el.closest('[data-cert-panel],.cert-chat-card'),
        focusVisible: el.matches(':focus-visible'), unobscured: !!hit && (hit === el || el.contains(hit)),
        top: r.top, bottom: r.bottom, viewportHeight: innerHeight,
        outline: style.outlineStyle, outlineWidth: style.outlineWidth, shadow: style.boxShadow }
    })
    steps.push({ key, ...value })
    if (value.inCourse) assert.ok(value.focusVisible && value.unobscured, `Keyboard focus must be visible: ${JSON.stringify(value)}`)
  }
  async function reach(target) {
    await target.waitFor({ state: 'visible' })
    const radio = await target.evaluate(el => el.matches('input[type=radio]'))
    for (let index = 0; index < 150; index++) {
      if (await target.evaluate(el => el === document.activeElement)) return
      if (radio && await target.evaluate(el => {
        const active = document.activeElement
        return active instanceof HTMLInputElement && active.type === 'radio' && el.name && active.name === el.name && active.form === el.form
      })) {
        await page.keyboard.press('ArrowDown')
        await record('ArrowDown')
      } else {
        await page.keyboard.press('Tab')
        await record('Tab')
      }
    }
    assert.fail(`Keyboard could not reach ${await target.evaluate(el => el.getAttribute('aria-label') || [...el.labels || []].map(label => label.textContent.trim()).join(' ') || el.textContent.trim())} within 150 steps`)
  }
  async function activate(target) {
    await reach(target)
    const key = await target.evaluate(el => el.matches('input[type=radio],input[type=checkbox]') ? 'Space' : 'Enter')
    const activated = await target.evaluate(el => el.getAttribute('aria-label') || el.textContent.trim().slice(0, 120))
    await page.keyboard.press(key)
    steps.push({ activated, key })
  }
  return { reach, activate, steps }
}
