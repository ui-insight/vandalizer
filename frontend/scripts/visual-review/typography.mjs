import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import {resolve} from 'node:path'
import {createReview} from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page,state}=review
try {
 for(const [width,height] of [[320,568],[768,600],[1440,900]]) {
  await page.setViewportSize({width,height})
  for(const status of ['ok','warning','compact','blocked']) {
   const percent=status==='ok'?50:status==='warning'?75:status==='compact'?94:100
   state.chatChunks=[{kind:'text',content:'Review complete. The source remains available.'},{kind:'context_meter',meter:{estimated_tokens:percent*1000,context_window:100000,state:status,percent_until_compact:status==='warning'?10:0}}]
   await page.goto(review.baseURL+'/?mode=chat')
   await page.getByRole('textbox',{name:'Message input'}).fill('Review this source.')
   await page.getByRole('button',{name:'Send message'}).click()
   const meter=page.getByRole('button',{name:`Context usage: ${percent}%`,exact:true})
   await meter.waitFor()
   assert.equal(await meter.evaluate(e=>{const r=e.getBoundingClientRect(),l=e.querySelector('span').getBoundingClientRect();return r.width>=44&&r.height>=44&&l.left>=r.left&&l.right<=r.right&&l.bottom<=r.bottom&&parseFloat(getComputedStyle(e.querySelector('span')).fontSize)>=12}),true)
   const id=`typography-context-${status}-${width}`
   await review.capture(id)
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))
   assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[])
   console.log('Captured '+id)
  }
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Context utilization percentages remain legible within a 44px control at 50%, 75%, 94% and 100%; backend warning states retain their meaning. Chat responses and usage are synthetic.')
}finally{await review.flush();await review.browser.close()}
