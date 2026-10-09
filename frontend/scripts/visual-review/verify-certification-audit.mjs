import assert from 'node:assert/strict'
import {chromium} from 'playwright'
import {readFile,access} from 'node:fs/promises'
import {resolve} from 'node:path'
import {pathToFileURL,fileURLToPath} from 'node:url'
const path=resolve('../docs/reviews/certification-v5-audit.html'),html=await readFile(path,'utf8')
assert.ok(!html.includes('MISSING EVIDENCE:'))
for(const m of html.matchAll(/(?:href|src)="([^"]+)"/g))if(!m[1].startsWith('#'))await access(fileURLToPath(new URL(m[1],pathToFileURL(path))))
const browser=await chromium.launch({headless:true,executablePath:process.env.REVIEW_CHROMIUM})
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message))
 await page.goto(pathToFileURL(path).href)
 await page.screenshot({path:'../artifacts/visual-review/certification-2026-10-02-completion/report-preview.png'})
 const count=await page.locator('.capture').count()
 await page.getByRole('searchbox',{name:'Filter captured states'}).fill('long-top')
 assert.equal(await page.locator('.capture:visible').count(),4)
 await page.getByRole('searchbox',{name:'Filter captured states'}).fill('')
 assert.equal(await page.locator('.capture:visible').count(),count)
 await page.setViewportSize({width:390,height:844});await page.evaluate(()=>window.scrollTo(0,0))
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))
 await page.screenshot({path:'../artifacts/visual-review/certification-2026-10-02-completion/report-preview-mobile.png'})
 assert.deepEqual(errors,[])
 console.log(JSON.stringify({links:'all local targets exist',captures:count,filter:'passed',mobileOverflow:false,pageErrors:errors}))
}finally{await browser.close()}
