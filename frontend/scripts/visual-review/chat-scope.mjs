import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { kb } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
page.setDefaultTimeout(10000)
const choices = [kb, { ...kb, uuid: 'kb-2', title: 'Sponsor award conditions and reporting requirements' }]
let fail = false
await page.route('**/api/knowledge/list/v2?*', route => fail ? route.fulfill({status:503,json:{detail:'Knowledge temporarily unavailable'}}) : route.fulfill({json:{items:choices,total:choices.length}}))
await page.route('**/api/knowledge/kb-2', route => route.fulfill({json:choices[1]}))
async function shot(id) { await review.capture(id); assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${id}: overflow`); assert.deepEqual(JSON.parse(await readFile(resolve(review.out,`${id}.axe.json`),'utf8')),[],`${id}: accessibility`); console.log(`Captured ${id}`) }
async function send(text, expected) { state.chatChunks=[{kind:'text',content:`Response to: ${text}`}]; await page.getByRole('textbox',{name:'Message input'}).fill(text); await page.getByRole('button',{name:'Send message'}).click(); await page.getByText(`Response to: ${text}`,{exact:true}).waitFor(); assert.deepEqual(state.lastChat.knowledge_base_uuids,expected) }
try {
  for (const [width,height] of [[320,568],[768,600],[1440,900]]) {
    await page.setViewportSize({width,height})
    await page.goto(review.baseURL+'/?mode=chat')
    await page.getByRole('textbox',{name:'Message input'}).fill('Preserve my scope draft')
    await page.getByRole('button',{name:'Add',exact:true}).click()
    fail=true; await page.getByRole('menuitem',{name:'Add Knowledge Base',exact:true}).click()
    await page.getByRole('button',{name:'Retry knowledge bases',exact:true}).waitFor()
    await shot(`chat-kb-picker-error-${width}`)
    fail=false; await page.getByRole('button',{name:'Retry knowledge bases',exact:true}).click()
    const picker=page.getByRole('dialog',{name:'Attach knowledge bases',exact:true})
    await picker.getByRole('button',{name:kb.title,exact:true}).click()
    await picker.getByRole('button',{name:choices[1].title,exact:true}).click()
    await shot(`chat-kb-picker-selected-${width}`)
    await picker.getByRole('button',{name:'Attach 2',exact:true}).click()
    assert.equal(await page.getByRole('textbox',{name:'Message input'}).inputValue(),'Preserve my scope draft')
    await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('button',{name:'Files',exact:true}).click()
    await page.getByRole('checkbox',{name:'Select Proposal narrative.pdf',exact:true}).check()
    await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('button',{name:'Chat',exact:true}).click()
    assert.equal(await page.getByRole('textbox',{name:'Message input'}).inputValue(),'Preserve my scope draft')
    await send('Compare both knowledge bases',['kb-1','kb-2'])
    assert.deepEqual(state.lastChat.document_uuids,['doc-0'])
    await shot(`chat-kb-multiple-${width}`)
    await page.getByRole('button',{name:`Detach knowledge base: ${kb.title}`,exact:true}).click()
    await send('Use only the remaining source',['kb-2'])
    assert.deepEqual(state.lastChat.document_uuids,['doc-0'])
    await shot(`chat-kb-detached-${width}`)
    await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('button',{name:'Knowledge',exact:true}).click()
    await page.getByRole('tabpanel',{name:'Mine'}).getByRole('button',{name:'Chat',exact:true}).first().click()
    await send('Start with the original knowledge base',['kb-1'])
    assert.deepEqual(state.lastChat.document_uuids,[])
    await shot(`chat-kb-replaced-${width}`)
    await page.getByRole('textbox',{name:'Message input'}).fill('Discard this draft in a deliberate new chat')
    if (await page.getByRole('button',{name:'Open activity',exact:true}).isVisible()) await page.getByRole('button',{name:'Open activity',exact:true}).click()
    const newChat=page.getByRole('button',{name:'New chat',exact:true}); await newChat.focus(); await page.keyboard.press('Enter')
    // Close the activity overlay using its backdrop/Escape pathway before composing.
    await page.keyboard.press('Escape')
    assert.equal(await page.getByRole('textbox',{name:'Message input'}).inputValue(),'')
    assert.equal(await page.getByRole('button',{name:'Copy message'}).count(),0)
    await page.getByRole('button',{name:`Detach knowledge base: ${kb.title}`,exact:true}).waitFor()
    await shot(`chat-new-conversation-scope-${width}`)
  }
  assert.deepEqual(review.errors,[]); assert.deepEqual([...review.unmatched],[])
} catch(error) { await review.capture('chat-scope-blocked',String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
