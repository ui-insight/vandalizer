import { chromium, firefox, webkit } from 'playwright'
import { mkdir, writeFile, readFile, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import { installFixtures } from './fixtures.mjs'

export async function createReview({output='artifacts/visual-review',baseURL='http://127.0.0.1:5173',resetStorage=true,isolatedBackend=false,evidenceMode=null}={}) {
 if(isolatedBackend && baseURL!=='http://127.0.0.1:5181')throw new Error('Live QA is restricted to the isolated local preview');
 const root=execFileSync('git',['rev-parse','--show-toplevel'],{encoding:'utf8'}).trim();
 const paths=execFileSync('git',['ls-files','--cached','--others','--exclude-standard','-z','frontend/src','frontend/scripts/visual-review','backend/app'],{cwd:root,encoding:'utf8'}).split('\0').filter(Boolean).sort();
 const hash=createHash('sha256');
 for(const path of paths){hash.update(path+'\0');try{hash.update(await readFile(resolve(root,path)))}catch{hash.update('[deleted]')}}
 const sourceFingerprint=hash.digest('hex');
 const fixtureFingerprint=createHash('sha256').update(await readFile(new URL('./fixtures.mjs',import.meta.url))).digest('hex');
 const buildMode=process.env.REVIEW_BUILD || 'development';
 const out=resolve(output); await mkdir(out,{recursive:true});
 const browserEngine=process.env.REVIEW_ENGINE || 'chromium';
 const engine={chromium,firefox,webkit}[browserEngine];
 if(!engine)throw new Error('REVIEW_ENGINE must be chromium, firefox or webkit');
 if(browserEngine!=='chromium'&&(process.env.REVIEW_CHROMIUM||process.env.REVIEW_NATIVE_PROFILE_ZOOM==='2'||process.env.REVIEW_BROWSER_ZOOM==='2'))throw new Error('Chrome executable and native-zoom controls require the chromium engine');
 const launchOptions={headless:true,...(process.env.REVIEW_CHROMIUM?{executablePath:process.env.REVIEW_CHROMIUM}:{})};
 const contextOptions={viewport:{width:1440,height:1000},deviceScaleFactor:process.env.REVIEW_ZOOM === '2' ? 2 : 1,reducedMotion:'reduce'};
 let browser,context,zoomWorker;
 const nativeProfileZoom=process.env.REVIEW_NATIVE_PROFILE_ZOOM==='2';
 if(nativeProfileZoom){
  if(process.env.REVIEW_BROWSER_ZOOM==='2'||process.env.REVIEW_ZOOM==='2')throw new Error('Native profile zoom requires unscaled device pixels and no zoom extension');
  // Chrome's own page zoom, in a new disposable profile. The default storage
  // partition key is "x" (hex encoding of an empty relative partition path).
  // https://raw.githubusercontent.com/chromium/chromium/main/chrome/browser/ui/zoom/chrome_zoom_level_prefs.cc
  const temp=await mkdtemp(resolve(tmpdir(),'vandalizer-certification-native-zoom-'));
  await mkdir(resolve(temp,'Default'));
  await writeFile(resolve(temp,'Default','Preferences'),JSON.stringify({partition:{default_zoom_level:{x:Math.log(2)/Math.log(1.2)}}}));
  context=await chromium.launchPersistentContext(temp,{...launchOptions,...contextOptions});
  browser={version:()=>context.browser().version(),close:async()=>{await context.close();await rm(temp,{recursive:true,force:true})}};
 }else if(process.env.REVIEW_BROWSER_ZOOM==='2'){
  // chrome.tabs.setZoom changes desktop browser zoom, unlike DPR or pinch emulation.
  // Requires the full Chromium binary, with an isolated disposable profile.
  const temp=await mkdtemp(resolve(tmpdir(),'vandalizer-ra8-zoom-')),extension=resolve(temp,'extension');
  await mkdir(extension);
  await writeFile(resolve(extension,'manifest.json'),JSON.stringify({manifest_version:3,name:'Local zoom QA',version:'1.0',permissions:['tabs'],background:{service_worker:'background.js'}}));
  await writeFile(resolve(extension,'background.js'),'chrome.runtime.onInstalled.addListener(() => {});');
  context=await chromium.launchPersistentContext(resolve(temp,'profile'),{...launchOptions,...contextOptions,args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`]});
  zoomWorker=context.serviceWorkers()[0]||await context.waitForEvent('serviceworker');
  browser={version:()=>context.browser().version(),close:async()=>{await context.close();await rm(temp,{recursive:true,force:true})}};
 }else{
  browser=await engine.launch(launchOptions);context=await browser.newContext(contextOptions);
 }
 const state={empty:false,first:false}, unmatched=new Set(), captures=[], errors=[], observations=[];
 if(isolatedBackend){
  await context.route('**/*',route=>new URL(route.request().url()).origin===baseURL?route.continue():route.abort());
 }else await installFixtures(context,state,unmatched);
 // Every navigation starts from the same layout and scope. Interactions within
 // a scenario retain state; separate scenarios cannot inherit a project or KB.
 await context.addInitScript(reset=>{if(reset){localStorage.clear();sessionStorage.clear()}localStorage.setItem('vandalizer:first-run-tour-dismissed','1')},resetStorage);
 if(process.env.REVIEW_TEXT_SCALE==='2')await context.addInitScript(()=>document.addEventListener('DOMContentLoaded',()=>{document.documentElement.style.fontSize='32px'}));
 const page=await context.newPage(); page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE ERROR',e.message)});
 const actionTimeout=Number(process.env.REVIEW_ACTION_TIMEOUT_MS || 30000);
 if(!Number.isFinite(actionTimeout)||actionTimeout<1000||actionTimeout>180000)throw new Error('Review action timeout must be between 1000 and 180000 milliseconds');
 page.setDefaultTimeout(actionTimeout);
 page.on('console',m=>{if(m.type()==='error')console.error('CONSOLE',m.text())});
 page.on('requestfailed',r=>console.error('REQUEST FAILED',r.url(),r.failure()));
 async function setBrowserZoom(factor=2){
  if(nativeProfileZoom){
   if(factor!==2)throw new Error('This isolated profile is fixed at native 200% zoom');
   const metrics=await page.evaluate(()=>({dpr:devicePixelRatio,scale:visualViewport.scale,width:innerWidth}));
   if(metrics.dpr!==2||metrics.scale!==1||Math.abs(metrics.width-page.viewportSize().width/2)>1)throw new Error('Native zoom did not produce the expected page reflow');
   return 2;
  }
  if(!zoomWorker)throw new Error('REVIEW_BROWSER_ZOOM=2 requires full Chromium');
  return zoomWorker.evaluate(async({url,factor})=>{const tab=(await chrome.tabs.query({})).find(t=>t.url?.startsWith(new URL(url).origin+'/'));if(!tab)throw new Error('Review tab not found');await chrome.tabs.setZoom(tab.id,factor);return chrome.tabs.getZoom(tab.id)},{url:page.url(),factor});
 }
 async function capture(id,note='') {
  await page.waitForTimeout(450);
  await page.evaluate(()=>document.fonts.ready);
  // Full-page capture uses CSS document bounds as physical clip bounds under
  // native page zoom, cutting off the right/bottom of the visible viewport.
  await page.screenshot({path:resolve(out,`${id}.png`),fullPage:!nativeProfileZoom,animations:'disabled'});
  const png=await readFile(resolve(out,`${id}.png`));
  const screenshotPixels={width:png.readUInt32BE(16),height:png.readUInt32BE(20)};
  if(nativeProfileZoom&&(screenshotPixels.width!==page.viewportSize().width||screenshotPixels.height!==page.viewportSize().height))throw new Error('Native zoom capture must include the entire physical viewport');
  const snapshot=await page.locator('body').ariaSnapshot();
  await writeFile(resolve(out,`${id}.txt`),snapshot);
  // Zero-size text is intentionally replaced by a named sort icon on compact tables.
  const metrics=await page.evaluate(()=>({viewport:{width:innerWidth,height:innerHeight},devicePixelRatio,rootFontSize:getComputedStyle(document.documentElement).fontSize,visualViewportScale:visualViewport.scale,pageWidth:document.documentElement.scrollWidth,smallText:[...document.querySelectorAll('button,input,label,p,span')].filter(e=>e.getBoundingClientRect().width&&parseFloat(getComputedStyle(e).fontSize)>0&&parseFloat(getComputedStyle(e).fontSize)<12).length}));
  if(zoomWorker)metrics.browserZoom=await zoomWorker.evaluate(async url=>{const tab=(await chrome.tabs.query({})).find(t=>t.url?.startsWith(new URL(url).origin+'/'));return chrome.tabs.getZoom(tab.id)},page.url());
  const smallControls = await page.evaluate(() => [...document.querySelectorAll('button,[role=button],[role=menuitem],select,input[type=checkbox],input[type=radio]')].filter(e => {
    const r = e.getBoundingClientRect();
    return !e.disabled && !e.closest('[inert]') && e.checkVisibility({checkVisibilityCSS:true}) && r.width > 0 && r.height > 0 && r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight && (r.width < 24 || r.height < 24);
  }).map(e => ({name:e.getAttribute('aria-label') || e.textContent?.trim().slice(0,80) || e.getAttribute('title') || e.tagName, width:e.getBoundingClientRect().width, height:e.getBoundingClientRect().height})));
  await page.addScriptTag({path:createRequire(import.meta.url).resolve('axe-core/axe.min.js')});
  const a11y=await page.evaluate(async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,description:v.description,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))});
  await writeFile(resolve(out,`${id}.axe.json`),JSON.stringify(a11y,null,2));
  captures.push({id,note,url:page.url(),...metrics,screenshotPixels,smallControls});
  await flush();
  return snapshot;
 }
 async function flush() {await writeFile(resolve(out,'manifest.json'),JSON.stringify({capturedAt:new Date().toISOString(),sourceFingerprint,fixtureFingerprint:isolatedBackend?null:fixtureFingerprint,buildMode,nativeProfileZoom:nativeProfileZoom?2:1,zoomEquivalent:process.env.REVIEW_ZOOM==='2'?2:1,textScale:process.env.REVIEW_TEXT_SCALE==='2'?2:1,reducedMotion:'reduce',workingTree:execFileSync('git',['status','--short'],{encoding:'utf8'}).trim(),commit:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),baseURL,browserEngine,browserVersion:browser.version(),mode:evidenceMode || (isolatedBackend?'Actual isolated local backend; synthetic accounts/data; no production, external delivery or model execution':'synthetic API fixtures; current source served locally; no backend or model execution'),captures,unmatched:[...unmatched],errors,observations},null,2))}
 return {browser,context,page,state,unmatched,captures,errors,observations,out,capture,flush,baseURL,setBrowserZoom};
}
