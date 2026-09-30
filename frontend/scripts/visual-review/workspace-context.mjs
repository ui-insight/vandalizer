import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { project } from './fixtures.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page,state}=review
page.setDefaultTimeout(15000)
const projectTitle='Regional research proposal — community partnerships and supporting evidence'
await page.route('**/api/projects/project-1',route=>route.fulfill({json:{...project,title:projectTitle}}))
await page.route('**/api/library/items/*/touch',route=>route.fulfill({json:{ok:true}}))
const nav=name=>page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('button',{name,exact:true})
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
async function openLibrary(width){if(width<768)await page.getByRole('button',{name:'Open Library panel',exact:true}).click();else await page.getByRole('button',{name:/^(?:Open )?Library(?: panel)?$/}).click()}
try{
 for(const [width,height] of [[320,568],[768,600],[1440,900]]){
  await page.setViewportSize({width,height});await page.goto(review.baseURL+'/?project=project-1&mode=files')
  const context=page.getByRole('region',{name:'Active project'})
  await context.getByText(projectTitle,{exact:true}).waitFor()
  assert.equal(await nav('Files').getAttribute('aria-current'),'page')
  await openLibrary(width)
  await page.getByRole('button',{name:'Open Proposal readiness review',exact:true}).click()
  const location=page.getByRole('navigation',{name:'Tool location'})
  await location.getByRole('button',{name:'Back to Library',exact:true}).waitFor()
  assert.match(await location.innerText(),/Workflow/)
  assert.equal(await context.getByText(projectTitle,{exact:true}).isVisible(),true)
  const box=await context.boundingBox();assert.ok(box&&box.x>=0&&box.x+box.width<=width,'Project context must fit with an editor open')
  await shot(`workspace-project-library-tool-${width}`)
  await location.getByRole('button',{name:'Back to Library',exact:true}).click()
  await page.getByText('Tools you own or have saved.',{exact:true}).scrollIntoViewIfNeeded()
  assert.equal(await page.getByRole('group',{name:'Library views'}).getByRole('button',{name:'Mine',exact:true}).getAttribute('aria-pressed'),'true')
  await shot(`workspace-library-mine-scope-${width}`)
  await page.getByRole('group',{name:'Library views'}).getByRole('button',{name:'Team',exact:true}).click()
  await page.getByText('Tools owned by or shared with your team.',{exact:true}).waitFor()
  await shot(`workspace-library-team-scope-${width}`)
  await page.getByRole('group',{name:'Library views'}).getByRole('button',{name:'Explore',exact:true}).click()
  await page.getByText('Shared with everyone. Save an item to Mine.',{exact:true}).waitFor()
  await shot(`workspace-library-explore-location-${width}`)
  await nav('Knowledge').click()
  if(width<768){const source=page.getByRole('button',{name:'Knowledge panel',exact:true});if(await source.getAttribute('aria-pressed')==='false')await source.click()}
  assert.equal(await nav('Knowledge').getAttribute('aria-current'),'page')
  await page.getByRole('tab',{name:'Mine',exact:true}).waitFor()
  await page.getByText('Knowledge bases you own or have saved.',{exact:true}).waitFor()
  await shot(`workspace-knowledge-mine-scope-${width}`)
  await page.getByRole('button',{name:'Show all',exact:true}).click()
  await page.getByRole('tabpanel',{name:'Mine',exact:true}).getByRole('button',{name:'Research administration policies',exact:true}).click()
  await page.getByRole('tab',{name:/^Sources \(/}).waitFor()
  await shot(`workspace-project-knowledge-open-${width}`)
  await page.getByRole('button',{name:'Back to knowledge bases',exact:true}).click()
  await page.getByRole('tab',{name:'Team',exact:true}).click()
  await page.getByText('Knowledge bases owned by or shared with your team.',{exact:true}).waitFor()
  await shot(`workspace-knowledge-team-scope-${width}`)
  await page.getByRole('tab',{name:'Explore',exact:true}).click()
  await page.getByRole('region',{name:'Workspace source panel',exact:true}).getByText('Shared with everyone. Save an item to Mine.',{exact:true}).waitFor()
  await shot(`workspace-knowledge-explore-location-${width}`)
  await nav('Chat').click()
  await page.getByRole('button',{name:/^(?:Open )?Assistant(?: panel)?$/}).click()
  await page.getByText('Ask about this project',{exact:true}).waitFor()
  await page.getByText('Project sources',{exact:true}).waitFor()
  assert.equal(await page.getByText(projectTitle,{exact:true}).filter({visible:true}).count(),1)
  const sendBox=await page.getByRole('button',{name:'Send message',exact:true}).boundingBox()
  assert.ok(sendBox&&sendBox.y>=0&&sendBox.y+sendBox.height<=height,'Send must fit without scrolling away the project context')
  await shot(`workspace-project-chat-context-${width}`)
  await context.getByRole('button',{name:'Exit',exact:true}).click()
  await page.getByRole('textbox',{name:'Message input'}).waitFor()
  assert.equal(await page.getByRole('region',{name:'Active project'}).count(),0)
  assert.equal(await nav('Chat').getAttribute('aria-current'),'page')
  state.chatChunks=[{kind:'tool_call',tool_name:'create_workflow',tool_call_id:'context-workflow',args:{name:'Proposal readiness review'},content:''},{kind:'tool_result',tool_name:'create_workflow',tool_call_id:'context-workflow',content:{workflow_id:'workflow-1',name:'Proposal readiness review',steps_created:1}}]
  await page.getByRole('textbox',{name:'Message input'}).fill('Create the proposal review workflow')
  await page.getByRole('button',{name:'Send message',exact:true}).click()
  await page.getByRole('button',{name:'Open workflow',exact:true}).click()
  await location.getByRole('button',{name:'Back to Assistant',exact:true}).waitFor()
  await shot(`workspace-assistant-tool-location-${width}`)
  await location.getByRole('button',{name:'Back to Assistant',exact:true}).click()
  await page.getByRole('button',{name:'Open workflow',exact:true}).waitFor()
  await shot(`workspace-assistant-return-${width}`)
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Library/Assistant tool origin and return, active section, full project context with tool open and scope exit; consistent Mine/Team/Explore explanations at 320/768/1440px. Synthetic data and tool responses; no workflow creation/execution or sharing performed.')
}catch(error){await page.screenshot({path:resolve(review.out,'workspace-context-blocked.png')});throw error}
finally{await review.flush();await review.browser.close()}
