import assert from 'node:assert/strict'
import { createReview } from './harness.mjs'
import { workflow } from './fixtures.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(8000)
const types=['Extraction','Prompt','Formatter','AddDocument','AddWebsite','CrawlerNode','ResearchNode','KnowledgeBaseQuery','APINode','DocumentRenderer','FormFiller','DataExport','Approval']
const labels={Extraction:'Extract fields',Prompt:'Prompt',Formatter:'Format output',AddDocument:'Add document',AddWebsite:'Read a web page',CrawlerNode:'Crawl a website',ResearchNode:'Deep analysis',KnowledgeBaseQuery:'Ask a knowledge base',APINode:'Call an API',DocumentRenderer:'Create a document',FormFiller:'Fill a form',DataExport:'Export data',Approval:'Request approval'}
let design={...workflow,steps:[{id:'step-1',name:'Review proposal',data:{},is_output:true,tasks:types.map((name,i)=>({id:'task-'+i,name,data:name==='KnowledgeBaseQuery'?{mode:'answer'}:{}}))}]}
await page.route('**/api/workflows/workflow-1',async r=>{if(['PUT','PATCH'].includes(r.request().method()))design={...design,...r.request().postDataJSON()};await r.fulfill({json:design})})
await page.route('**/api/credentials',r=>r.fulfill({json:[]}))
await page.route('**/api/teams/team-1/members',r=>r.fulfill({json:[]}))
await page.route('**/api/workflows/workflow-1/versions',r=>r.fulfill({json:{versions:[],unsaved_changes:false,can_manage:true}}))
async function shot(id){console.log('CAPTURE',id);await review.capture(id)}
try{
 await page.goto(review.baseURL+'/?mode=library&workflow=workflow-1');await page.getByRole('tab',{name:'Design',exact:true}).waitFor();await shot('builder-design')
 await page.getByRole('button',{name:'Open step: Review proposal',exact:true}).click();await shot('builder-step')
 const step=page.getByRole('region',{name:'Edit step: Review proposal',exact:true})
 for(const tab of ['Input','Output']){await step.getByRole('tab',{name:tab,exact:true}).click();await shot('step-'+tab.toLowerCase())}
 await step.getByRole('tab',{name:'Tasks',exact:true}).click()
 await step.getByRole('button',{name:'ADD A TASK',exact:true}).click();await shot('task-picker');await page.getByRole('searchbox',{name:'Search tasks'}).fill('document');assert.ok(await page.locator('.workflow-task-option').count()>1);await shot('task-picker-search');await page.getByRole('searchbox',{name:'Search tasks'}).fill('no-match-xyz');await shot('task-picker-empty');await page.getByRole('button',{name:'Clear filters'}).click()
 await page.keyboard.press('Escape')
 for(const name of types){
  await step.getByRole('button',{name:'Edit task: '+labels[name],exact:true}).click();await shot('task-'+name)
  if(name==='AddDocument'){await page.getByRole('button',{name:'Choose document',exact:true}).click();const picker=page.getByRole('dialog',{name:'Choose a document'});await picker.getByRole('radio').first().check();await shot('task-document-picker');await picker.getByRole('button',{name:'Use document'}).click();await shot('task-document-selected')}
  if(name==='Formatter'){await page.getByRole('button',{name:'JSON',exact:true}).click();assert.match(await page.getByRole('textbox',{name:'Format template'}).inputValue(),/Return only valid JSON/);await shot('task-Formatter-starter')}
  if(name==='APINode'){await page.getByText('Headers & request body · optional',{exact:true}).click();await shot('task-APINode-details')}
  if(name==='FormFiller'){await page.getByRole('radio',{name:'Fillable PDF form',exact:true}).click();await shot('task-FormFiller-pdf')}
  if(name==='Prompt'){const editor=page.getByRole('region',{name:'Edit task: Prompt',exact:true});await editor.getByRole('button',{name:'Advanced',exact:true}).click();await shot('task-advanced')}
  await page.keyboard.press('Escape')
 }
 await page.keyboard.press('Escape')
 for(const name of ['Inputs & outputs','Advanced','Versions','History']){await page.getByRole('tablist',{name:'Workflow editor sections'}).getByRole('tab',{name,exact:true}).click();await shot('workflow-'+name.toLowerCase())}
 await page.goto(review.baseURL+'/?tab=library');await page.getByRole('button',{name:'New',exact:true}).click();await shot('library-new-menu');await page.getByText('New Workflow',{exact:true}).click();await shot('new-workflow-dialog')
 await page.goto(review.baseURL+'/?mode=library&workflow=workflow-1');await page.getByRole('tab',{name:'Inputs & outputs',exact:true}).click();await page.getByRole('button',{name:'Output Configuration Not saved to the library',exact:true}).click();await shot('workflow-output-configuration')
 await page.setViewportSize({width:390,height:844});await page.getByRole('tab',{name:'Design',exact:true}).click();await shot('workflow-design-390')
 await page.getByRole('button',{name:'Open step: Review proposal',exact:true}).click();await step.getByRole('button',{name:'ADD A TASK',exact:true}).click();await shot('task-picker-390');await page.keyboard.press('Escape')
 for(const name of ['Prompt','APINode','Approval']){await step.getByRole('button',{name:'Edit task: '+labels[name],exact:true}).click();await shot('task-'+name+'-390');await page.keyboard.press('Escape')}

}finally{await review.flush();await review.browser.close()}
