import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import {createReview} from './harness.mjs'
const lessons=JSON.parse(await readFile(new URL('../../../backend/certification-data/lessons.json',import.meta.url),'utf8'))
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL||'http://127.0.0.1:5291'})
const {page,state}=review
try {
 const lesson=lessons.ai_literacy.lessons[2]
 state.chatChunks=[{kind:'tool_call',tool_name:'get_certification_lesson',tool_call_id:'lesson',content:'',args:{}},{kind:'tool_result',tool_name:'get_certification_lesson',tool_call_id:'lesson',content:{module_id:'ai_literacy',module_title:'AI Literacy',lesson_number:3,lesson_count:9,...lesson}},{kind:'text',content:'Try the practice check.'}]
 await page.goto(review.baseURL)
 await page.getByRole('textbox',{name:'Message input'}).fill('Teach me.')
 await page.getByRole('button',{name:'Send message',exact:true}).click()
 await page.getByText('Try the practice check.',{exact:true}).waitFor()
 const option=page.getByRole('radio',{name:lesson.knowledge_check.options[0].text,exact:true})
 await option.scrollIntoViewIfNeeded()
 await option.click()
 assert.equal(await option.isChecked(),true,'Pointer selection must survive transcript capture handlers')
 assert.equal(await page.getByRole('button',{name:'Check answer',exact:true}).isEnabled(),true)
 await option.press('Space')
 assert.equal(await option.isChecked(),true,'Keyboard selection must remain usable')
 await review.capture('practice-interaction')
 assert.equal(await option.isChecked(),true)
} finally {await review.flush();await review.browser.close()}
