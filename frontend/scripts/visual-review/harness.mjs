import { chromium } from 'playwright'
import { mkdir, writeFile, readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import { installFixtures } from './fixtures.mjs'

export async function createReview({output='artifacts/visual-review',baseURL='http://127.0.0.1:5173',resetStorage=true}={}) {
 const root=execFileSync('git',['rev-parse','--show-toplevel'],{encoding:'utf8'}).trim();
 const paths=execFileSync('git',['ls-files','--cached','--others','--exclude-standard','-z','frontend/src','frontend/scripts/visual-review','backend/app'],{cwd:root,encoding:'utf8'}).split('\0').filter(Boolean).sort();
 const hash=createHash('sha256');
 for(const path of paths){hash.update(path+'\0');try{hash.update(await readFile(resolve(root,path)))}catch{hash.update('[deleted]')}}
 const sourceFingerprint=hash.digest('hex');
 const fixtureFingerprint=createHash('sha256').update(await readFile(new URL('./fixtures.mjs',import.meta.url))).digest('hex');
 const buildMode=process.env.REVIEW_BUILD || 'development';
 const out=resolve(output); await mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,...(process.env.REVIEW_CHROMIUM?{executablePath:process.env.REVIEW_CHROMIUM}:{})});
 const context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1,reducedMotion:'reduce'});
 const state={empty:false,first:false}, unmatched=new Set(), captures=[], errors=[], observations=[];
 await installFixtures(context,state,unmatched);
 // Every navigation starts from the same layout and scope. Interactions within
 // a scenario retain state; separate scenarios cannot inherit a project or KB.
 await context.addInitScript(reset=>{if(reset){localStorage.clear();sessionStorage.clear()}localStorage.setItem('vandalizer:first-run-tour-dismissed','1')},resetStorage);
 const page=await context.newPage(); page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE ERROR',e.message)});
 page.on('console',m=>{if(m.type()==='error')console.error('CONSOLE',m.text())});
 page.on('requestfailed',r=>console.error('REQUEST FAILED',r.url(),r.failure()));
 async function capture(id,note='') {
  await page.waitForTimeout(450);
  await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:resolve(out,`${id}.png`),fullPage:true,animations:'disabled'});
  const snapshot=await page.locator('body').ariaSnapshot();
  await writeFile(resolve(out,`${id}.txt`),snapshot);
  const metrics=await page.evaluate(()=>({viewport:{width:innerWidth,height:innerHeight},pageWidth:document.documentElement.scrollWidth,smallText:[...document.querySelectorAll('button,input,label,p,span')].filter(e=>e.getBoundingClientRect().width&&parseFloat(getComputedStyle(e).fontSize)<12).length}));
  await page.addScriptTag({path:createRequire(import.meta.url).resolve('axe-core/axe.min.js')});
  const a11y=await page.evaluate(async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,description:v.description,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))});
  await writeFile(resolve(out,`${id}.axe.json`),JSON.stringify(a11y,null,2));
  captures.push({id,note,url:page.url(),...metrics});
  await flush();
  return snapshot;
 }
 async function flush() {await writeFile(resolve(out,'manifest.json'),JSON.stringify({capturedAt:new Date().toISOString(),sourceFingerprint,fixtureFingerprint,buildMode,workingTree:execFileSync('git',['status','--short'],{encoding:'utf8'}).trim(),commit:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),baseURL,browserVersion:browser.version(),mode:'synthetic API fixtures; current source served locally; no backend or model execution',captures,unmatched:[...unmatched],errors,observations},null,2))}
 return {browser,context,page,state,unmatched,captures,errors,observations,out,capture,flush,baseURL};
}
