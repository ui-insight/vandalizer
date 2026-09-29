import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
page.setDefaultTimeout(12000)
async function shot(id) {
  await review.capture(id)
  assert.ok(review.captures.at(-1).pageWidth <= review.captures.at(-1).viewport.width, id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
async function withinViewport(locator) {
  const box = await locator.boundingBox()
  assert.ok(box && box.y >= 0 && box.y + box.height <= (await page.viewportSize()).height, 'Action is outside viewport')
}
try {
  for (const [width,height] of [[320,568],[768,500],[1440,900]]) {
    state.first = true
    await page.setViewportSize({width,height})
    await page.goto(review.baseURL + '/?mode=chat')
    await page.getByRole('heading', {name:'What would you like to get done?'}).waitFor()
    assert.equal(await page.getByRole('dialog').count(), 0)
    const conversation = page.getByRole('region', {name:'Conversation',exact:true})
    const start = page.getByRole('button', {name:'Start a conversation',exact:true})
    // First task is above the fold; the sample disclosure takes at most one
    // conversation viewport to reach, even on the narrow, short device.
    const firstRect = await start.boundingBox(), regionRect = await conversation.boundingBox()
    assert.ok(firstRect.y + firstRect.height <= regionRect.y + regionRect.height, 'First action needs scrolling')
    await shot('onboarding-first-actions-' + width)
    await start.click()
    assert.equal(await page.getByRole('textbox',{name:'Message input'}).evaluate(e => e === document.activeElement), true)
    const demo = page.getByText('Try a sample document demo', {exact:true})
    await demo.scrollIntoViewIfNeeded()
    assert.ok(await conversation.evaluate(e => e.scrollTop <= e.clientHeight), 'Demo requires more than one viewport to find')
    await demo.click()
    const run = page.getByRole('button',{name:'Run sample demo',exact:true})
    await run.scrollIntoViewIfNeeded(); await withinViewport(run)
    await shot('onboarding-demo-action-' + width)
    await page.getByText('Linked evidence',{exact:true}).scrollIntoViewIfNeeded()
    await shot('onboarding-demo-evidence-' + width)
    await demo.click()
    const trigger = page.getByRole('button',{name:'Take a quick tour',exact:true})
    await trigger.focus(); await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog')
    await dialog.waitFor()
    await page.waitForFunction(() => document.activeElement.id === 'first-run-tour-title')
    await page.keyboard.press('Shift+Tab')
    assert.equal(await dialog.getByRole('button',{name:'Dismiss tour',exact:true}).evaluate(e=>e===document.activeElement),true)
    await page.keyboard.press('Shift+Tab')
    assert.equal(await dialog.getByRole('button',{name:'Next',exact:true}).evaluate(e=>e===document.activeElement),true)
    for (let i=0;i<8;i++) {
      await page.keyboard.press('Tab')
      assert.equal(await dialog.evaluate(e=>e.contains(document.activeElement)),true)
    }
    for (let step=0;step<4;step++) {
      const action = dialog.getByRole('button',{name: step===3 ? 'Get started' : 'Next',exact:true})
      await withinViewport(action)
      await shot(`onboarding-tour-${step + 1}-${width}`)
      if (step<3) await action.click()
    }
    await dialog.getByRole('button',{name:'Back',exact:true}).click()
    await dialog.getByRole('heading',{name:'Review what will run'}).waitFor()
    await page.keyboard.press('Escape'); await dialog.waitFor({state:'hidden'})
    assert.equal(await trigger.evaluate(e=>e===document.activeElement),true)
    await trigger.click(); await dialog.getByRole('heading',{name:'Welcome to Vandalizer 5.0'}).waitFor()
    await dialog.getByRole('button',{name:'Skip tour'}).click()
    await page.waitForFunction(() => document.activeElement?.textContent === 'Take a quick tour')
    await trigger.click()
    for(let step=0;step<3;step++) await dialog.getByRole('button',{name:'Next',exact:true}).click()
    await dialog.getByRole('button',{name:'Get started'}).click()
    await dialog.waitFor({state:'hidden'})
    await page.reload(); await start.waitFor()
    assert.equal(await page.getByRole('dialog').count(),0)
    await shot('onboarding-dismissed-reload-' + width)
    // A selected KB keeps contextual guidance, without the first-session home.
    await page.getByRole('button',{name:'Choose a knowledge base',exact:true}).click()
    const picker = page.getByRole('dialog',{name:'Attach knowledge bases'})
    await picker.getByRole('button',{name:'Research administration policies',exact:true}).click()
    await picker.getByRole('button',{name:'Attach',exact:true}).click()
    assert.equal(await page.getByRole('heading',{name:'What would you like to get done?'}).count(),0)
    await shot('onboarding-scoped-knowledge-' + width)
    state.first = false
    await page.goto(review.baseURL + '/?mode=chat')
    await trigger.waitFor()
    assert.equal(await page.getByRole('dialog').count(),0)
    await trigger.scrollIntoViewIfNeeded(); await shot('onboarding-returning-' + width)
    await trigger.click(); await dialog.getByRole('button',{name:'Dismiss tour'}).click()
    await page.waitForFunction(() => document.activeElement?.textContent === 'Take a quick tour')
  }
  review.observations.push('First-session action reachability, sample demo and evidence, optional tour all steps/Back/Skip/finish/Escape, focus containment and restoration, reload without interruptions, scoped KB guidance and returning users at 320/768-short/1440. Fixture API; no live demo execution or assistive-technology device certification.')
  assert.deepEqual(review.errors,[]); assert.deepEqual([...review.unmatched],[])
} catch(error) { await review.capture('onboarding-tour-blocked',String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
