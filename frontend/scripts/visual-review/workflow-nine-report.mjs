import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { readFile, writeFile, access } from 'node:fs/promises'
import { resolve } from 'node:path'
const root=resolve('../artifacts/visual-review/agentic-chat-nine')
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'})
const page=await browser.newPage({viewport:{width:1440,height:1000}})
try{
 await page.goto('file://'+root+'/index.html')
 const localLinks=await page.locator('a').evaluateAll(nodes=>nodes.map(a=>a.getAttribute('href')))
 for(const link of localLinks)await access(resolve(root,link))
 await page.locator('img').evaluateAll(images=>images.forEach(img=>img.loading='eager'))
 await page.waitForFunction(()=>[...document.images].every(i=>i.complete&&i.naturalWidth>0))
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true)
 await page.screenshot({path:root+'/report-preview.png'})
 await page.setViewportSize({width:390,height:844})
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true)
 await page.screenshot({path:root+'/report-preview-mobile.png'})
 const verification=JSON.parse(await readFile(root+'/verification.json','utf8'))
 verification.report={localLinks:localLinks.length,images:await page.locator('img').count(),desktopOverflow:false,mobileOverflow:false}
 await writeFile(root+'/verification.json',JSON.stringify(verification,null,2))
 console.log(JSON.stringify(verification.report))
}finally{await browser.close()}
