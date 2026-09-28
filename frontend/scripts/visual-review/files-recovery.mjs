import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { docs, folders } from './fixtures.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
await review.context.route('**/api/files/download?*',route=>route.fulfill({contentType:'text/plain',body:'Synthetic document'}))
const {page}=review; page.setDefaultTimeout(14000)
let entries, directories, fail='', writes=[]
await page.route('**/api/documents/list*',route=>{if(fail==='list')return route.fulfill({status:503,json:{detail:'Folder unavailable'}});const folder=new URL(route.request().url()).searchParams.get('folder');return route.fulfill({json:{documents:entries.filter(d=>(d.folder||null)===(folder||null)),folders:directories.filter(f=>(f.parent_id||null)===(folder||null))}})})
await page.route('**/api/documents/search?*',route=>{if(fail==='search')return route.fulfill({status:503,json:{detail:'Search unavailable'}});const q=new URL(route.request().url()).searchParams.get('q')||'';const items=entries.filter(d=>d.title.toLowerCase().includes(q.toLowerCase()));return route.fulfill({json:{items,total:items.length}})})
await page.route('**/api/folders/all',route=> fail==='folders'?route.fulfill({status:503,json:{detail:'Destinations unavailable'}}):route.fulfill({json:directories}))
await page.route('**/api/folders/breadcrumbs/*',route=>{const uuid=route.request().url().split('/').at(-1);return route.fulfill({json:directories.filter(f=>f.uuid===uuid)})})
await page.route('**/api/files/rename',route=>{const body=route.request().postDataJSON();writes.push({type:'rename',...body});if(fail==='rename')return route.fulfill({status:503,json:{detail:'Rename unavailable'}});entries.find(d=>d.uuid===body.uuid).title=body.newName;return route.fulfill({json:{ok:true}})})
await page.route('**/api/files/move',route=>{const body=route.request().postDataJSON();writes.push({type:'move',...body});if(fail==='move'&&body.fileUUID==='doc-1')return route.fulfill({status:503,json:{detail:'Move unavailable'}});entries.find(d=>d.uuid===body.fileUUID).folder=body.folderID==='0'?null:body.folderID;return route.fulfill({json:{ok:true}})})
await page.route('**/api/folders/create',route=>{const body=route.request().postDataJSON();writes.push({type:'create',...body});if(fail==='create')return route.fulfill({status:503,json:{detail:'Create unavailable'}});const added={...folders[0],uuid:'folder-new',id:'folder-new',title:body.name,path:body.name,parent_id:body.parent_id==='0'?'':body.parent_id};directories.push(added);return route.fulfill({json:added})})
await page.route('**/api/folders/*/move',route=>{const id=route.request().url().split('/').at(-2),body=route.request().postDataJSON();writes.push({type:'folder-move',id,...body});if(fail==='folder-move')return route.fulfill({status:503,json:{detail:'Folder move unavailable'}});const folder=directories.find(f=>f.uuid===id);folder.parent_id=body.parent_id==='0'?'':body.parent_id;return route.fulfill({json:folder})})
async function shot(id,target){if(target)await target.scrollIntoViewIfNeeded();await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${id}: overflow`);assert.deepEqual(JSON.parse(await readFile(resolve(review.out,`${id}.axe.json`),'utf8')),[],`${id}: accessibility`);console.log(`Captured ${id}`)}
try{
 for(const [width,height]of[[320,568],[768,600],[1440,900]]){
  entries=structuredClone(docs);directories=structuredClone(folders);fail='list';writes=[]
  await page.setViewportSize({width,height});await page.goto(review.baseURL+'/?mode=files')
  await page.getByRole('button',{name:'Retry folder',exact:true}).waitFor();await shot(`files-load-error-${width}`,page.getByRole('button',{name:'Retry folder',exact:true}))
  fail='';await page.getByRole('button',{name:'Retry folder',exact:true}).click()
  const original=page.getByRole('row',{name:'Document: Proposal narrative.pdf',exact:true});await original.waitFor()
  await original.getByRole('button',{name:'More options',exact:true}).click();await page.getByRole('menuitem',{name:'Rename',exact:true}).click()
  const rename=page.getByRole('dialog',{name:'Rename',exact:true});await rename.getByRole('textbox').fill('Proposal narrative – revised and ready for review.pdf')
  fail='rename';await rename.getByRole('button',{name:'Rename',exact:true}).click();await rename.getByRole('alert').waitFor();await shot(`files-rename-error-${width}`)
  fail='';await rename.getByRole('button',{name:'Rename',exact:true}).click();await rename.waitFor({state:'hidden'});assert.deepEqual(writes[0],writes[1])
  await page.getByRole('checkbox',{name:'Select Proposal narrative – revised and ready for review.pdf',exact:true}).check();await page.getByRole('checkbox',{name:'Select Budget justification.docx',exact:true}).check()
  fail='folders';await page.getByRole('button',{name:'Move',exact:true}).click();const move=page.getByRole('dialog',{name:'Move files',exact:true})
  await move.getByRole('button',{name:'Retry folders',exact:true}).waitFor();await shot(`files-move-destinations-error-${width}`)
  fail='';await move.getByRole('button',{name:'Retry folders',exact:true}).click();await move.getByRole('button',{name:'FY2027 proposals',exact:true}).waitFor()
  fail='move';await move.getByRole('button',{name:'FY2027 proposals',exact:true}).click()
  const remaining=page.getByRole('dialog',{name:'Move file',exact:true});await remaining.getByRole('alert').filter({hasText:'1 moved; 1 could not be moved'}).waitFor();await shot(`files-partial-move-${width}`)
  fail='';await remaining.getByRole('button',{name:'FY2027 proposals',exact:true}).click();await remaining.waitFor({state:'hidden'})
  assert.deepEqual(writes.filter(w=>w.type==='move').map(w=>w.fileUUID),['doc-0','doc-1','doc-1'])
  await page.getByRole('row',{name:'Folder: FY2027 proposals',exact:true}).click()
  await page.getByRole('row',{name:'Document: Budget justification.docx',exact:true}).waitFor();await shot(`files-moved-destination-${width}`)
  await page.getByRole('button',{name:'Name',exact:true}).click();await page.getByRole('checkbox',{name:'Select Budget justification.docx',exact:true}).check()
  await page.getByRole('button',{name:'Search files',exact:true}).click();const search=page.getByPlaceholder('Search files and content...');await search.fill('Budget')
  await page.getByRole('row',{name:'Document: Budget justification.docx',exact:true}).focus();await page.keyboard.press('Enter')
  await page.getByText('Synthetic review document.',{exact:false}).waitFor()
  await page.getByRole('button',{name:'Close document',exact:true}).click()
  assert.equal(await search.inputValue(),'Budget')
  assert.equal(await page.getByRole('checkbox',{name:'Select Budget justification.docx',exact:true}).isChecked(),true)
  assert.equal(await page.getByRole('columnheader',{name:/Name/}).getAttribute('aria-sort'),'ascending')
  await shot(`files-return-from-document-${width}`)
  fail='search';await search.fill('no-such-document')
  await page.getByRole('button',{name:'Retry search',exact:true}).waitFor();await shot(`files-content-search-error-${width}`)
  fail='';await page.getByRole('button',{name:'Retry search',exact:true}).click()
  await page.getByText(/No files or folders match/).waitFor();await shot(`files-no-search-results-${width}`)
  await page.getByRole('button',{name:'Close search',exact:true}).click();assert.equal(await page.getByRole('checkbox',{name:'Select Budget justification.docx',exact:true}).isChecked(),true)
  await page.getByRole('complementary',{name:'Documents',exact:true}).getByRole('button',{name:'Add',exact:true}).click();await page.getByRole('menuitem',{name:'New Folder',exact:true}).click()
  const create=page.getByRole('dialog',{name:'New Folder',exact:true});await create.getByRole('textbox').fill('Empty review folder');fail='create';await create.getByRole('button',{name:'Create',exact:true}).click();await create.getByRole('alert').waitFor();await shot(`files-create-folder-error-${width}`)
  fail='';await create.getByRole('button',{name:'Create',exact:true}).click();await create.waitFor({state:'hidden'});assert.deepEqual(writes.filter(w=>w.type==='create').map(w=>w.parent_id),['folder-1','folder-1'])
  await page.getByRole('row',{name:'Folder: Empty review folder',exact:true}).getByRole('button',{name:'More options',exact:true}).click();await page.getByRole('menuitem',{name:'Move to…',exact:true}).click()
  const folderMove=page.getByRole('dialog',{name:'Move folder',exact:true});fail='folder-move';await folderMove.getByRole('button',{name:'Top level',exact:true}).click();await folderMove.getByRole('alert').waitFor();await shot(`files-folder-move-error-${width}`)
  fail='';await folderMove.getByRole('button',{name:'Top level',exact:true}).click();await folderMove.waitFor({state:'hidden'});assert.deepEqual(writes.filter(w=>w.type==='folder-move').map(w=>w.parent_id),['0','0'])
  await page.getByRole('button',{name:'Home',exact:true}).click()
  await page.getByRole('row',{name:'Folder: Empty review folder',exact:true}).click();await page.getByText(/This folder is empty/).waitFor();await shot(`files-empty-folder-${width}`)
  await page.getByRole('button',{name:'Home',exact:true}).click();await page.getByRole('row',{name:'Folder: FY2027 proposals',exact:true}).waitFor()
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
}catch(error){await review.capture('files-recovery-blocked',String(error));throw error}
finally{await review.flush();await review.browser.close()}
