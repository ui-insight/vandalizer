import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(15000)
const nav=name=>page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('button',{name,exact:true})
async function source(width,name){if(width<768){const b=page.getByRole('button',{name:name+' panel',exact:true});if(await b.getAttribute('aria-pressed')==='false')await b.click()}}
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
async function header(title){const h=page.getByRole('heading',{name:title,exact:true});await h.waitFor();const box=await h.boundingBox();assert.ok(box&&box.width>0);return h.locator('..').locator('..').locator('..')}
try{
 for(const [width,height] of [[320,568],[768,600],[1440,900]]){
  await page.setViewportSize({width,height});await page.goto(review.baseURL+'/?mode=files')
  const files=await header('Files');await shot(`headers-files-${width}`)
  await files.getByRole('button',{name:'Add',exact:true}).click()
  await page.getByRole('menuitem',{name:'Upload Files',exact:true}).waitFor()
  await shot(`headers-file-add-${width}`)
  await files.getByRole('button',{name:'Add',exact:true}).click()
  await page.getByRole('button',{name:'Search files',exact:true}).click()
  await page.getByRole('searchbox',{name:'Search files and content',exact:true}).fill('Proposal')
  await page.getByRole('row',{name:'Document: Proposal narrative.pdf',exact:true}).waitFor()
  await shot(`headers-files-search-${width}`)
  await page.getByRole('button',{name:'Close search',exact:true}).click()
  await nav('Projects').click();await source(width,'Projects');await header('Projects')
  await page.getByRole('textbox',{name:'New project name',exact:true}).fill('Draft research project')
  await shot(`headers-projects-${width}`)
  await nav('Automations').click();await source(width,'Automations');await header('Automations')
  await page.getByRole('textbox',{name:'Filter automations',exact:true}).fill('Proposal')
  await shot(`headers-automations-${width}`)
  await nav('Knowledge').click();await source(width,'Knowledge');await header('Knowledge')
  await page.getByRole('searchbox',{name:'Search...',exact:true}).fill('Research')
  await shot(`headers-knowledge-${width}`)
  if(width<768)await page.getByRole('button',{name:'Open Library panel',exact:true}).click();else await page.getByRole('button',{name:/^(?:Open )?Library(?: panel)?$/}).click()
  const library=await header('Library');
  if(width<768){assert.equal(await page.getByRole('button',{name:/^(?:Open )?Library(?: panel)?$/}).count(),1);assert.equal(await page.getByRole('button',{name:/^(?:Open )?Assistant(?: panel)?$/}).count(),1)}
  await shot(`headers-library-${width}`)
  await library.getByRole('button',{name:'New',exact:true}).click()
  await page.getByRole('button',{name:'New Workflow',exact:true}).waitFor()
  await shot(`headers-library-new-${width}`)
  await library.getByRole('button',{name:'New',exact:true}).click()
  await page.getByRole('group',{name:'Library views'}).getByRole('button',{name:'Explore',exact:true}).click()
  await page.getByRole('heading',{name:'Explore shared tools',exact:true}).waitFor()
  await shot(`headers-explore-${width}`)
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Shared section headings, primary actions, search/filter placement, file Add and Library New menus at 320/768/1440px. Existing task behavior is covered by companion file/Library and navigation-retention regressions. No live API writes.')
}catch(error){await page.screenshot({path:resolve(review.out,'workspace-headers-blocked.png')});throw error}
finally{await review.flush();await review.browser.close()}
