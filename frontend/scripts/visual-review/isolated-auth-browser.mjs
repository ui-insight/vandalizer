import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { execFileSync } from 'node:child_process'
import { createReview } from './harness.mjs'
const run='/private/tmp/vandalizer-ra8-backend'
const {password}=JSON.parse(await readFile(resolve(run,'runtime.json'),'utf8'))
const state=JSON.parse(await readFile(resolve(run,'collaboration-state.json'),'utf8'))
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:'http://127.0.0.1:5181',isolatedBackend:true}),{page,context}=review
page.setDefaultTimeout(20000)
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': axe');console.log('Captured '+id)}
try{
 await page.setViewportSize({width:390,height:700})
 await page.goto(review.baseURL+'/?mode=projects&project='+state.project.uuid)
 const email=page.getByRole('textbox',{name:'Email',exact:true}),secret=page.getByLabel('Password',{exact:true})
 await email.fill('ra8-owner@example.test');await secret.fill('IncorrectQaPassword9');await page.getByRole('button',{name:'Sign in',exact:true}).last().click();await page.getByRole('alert').waitFor();assert.equal(await email.inputValue(),'ra8-owner@example.test');await shot('live-sign-in-failed-retained')
 await secret.fill(password);await page.getByRole('button',{name:'Sign in',exact:true}).last().click();await page.getByRole('button',{name:'Manage project',exact:true}).waitFor();await page.getByText(state.project.title,{exact:true}).first().waitFor();await shot('live-sign-in-project-return')
 await context.clearCookies();await page.goto(review.baseURL+'/account');await email.waitFor();assert.equal(new URL(page.url()).searchParams.get('next'),'/account');await shot('live-ended-session-return-path')
 await page.goto(review.baseURL+'/reset-password?token=expired-qa-token');await page.getByLabel('New password',{exact:true}).fill(password);await page.getByLabel('Confirm new password',{exact:true}).fill(password);await page.getByRole('button',{name:'Reset Password',exact:true}).click();await page.getByRole('alert').waitFor();await shot('live-reset-expired-recovery');await page.getByRole('link',{name:'Request a new reset link'}).click()
 await page.getByRole('textbox',{name:'Email address'}).fill('ra8-outsider@example.test');await page.getByRole('button',{name:'Send Reset Link'}).click();await page.getByRole('heading',{name:'Check your email'}).waitFor();await shot('live-reset-email-requested')
 // Parse the newest locally captured email without exposing its token in logs/evidence.
 const token=execFileSync('backend/.venv/bin/python',['-c',`from pathlib import Path
from email import policy
from email.parser import BytesParser
import re
for path in sorted(Path('${run}/mail').glob('*.eml'),key=lambda p:p.stat().st_mtime,reverse=True):
 m=BytesParser(policy=policy.default).parsebytes(path.read_bytes())
 if 'ra8-outsider@example.test' not in str(m.get('To','')): continue
 for part in m.walk():
  if part.get_content_type() in ('text/plain','text/html'):
   found=re.search(r'reset-password\\?token=([A-Za-z0-9_-]+)',part.get_content())
   if found: print(found.group(1)); raise SystemExit
raise SystemExit(1)`],{encoding:'utf8'}).trim()
 await page.goto(review.baseURL+'/reset-password?token='+token);await page.getByLabel('New password',{exact:true}).fill(password);await page.getByLabel('Confirm new password',{exact:true}).fill(password);await page.getByRole('button',{name:'Reset Password',exact:true}).click();await page.getByRole('heading',{name:'Password reset!'}).waitFor();await shot('live-reset-accepted');await page.getByRole('link',{name:'Sign In',exact:true}).click();await page.getByRole('textbox',{name:'Email',exact:true}).fill('ra8-outsider@example.test');await page.getByLabel('Password',{exact:true}).fill(password);await page.getByRole('button',{name:'SIGN IN',exact:true}).click();await page.getByRole('navigation',{name:'Workspace navigation'}).waitFor();await shot('live-reset-sign-in')
 assert.deepEqual(review.errors,[]);review.observations.push('Real password auth, reset link from local SMTP, intended project return, and missing-session redirect. Session token expiry/refresh and reset invalidation separately checked via real APIs. No SSO provider is configured in this isolated environment.')
}catch(error){await review.capture('isolated-auth-browser-blocked',String(error));throw error}finally{await review.flush();await review.browser.close()}
