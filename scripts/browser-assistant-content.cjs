/* Focused verification after the assistant effect repair, including draft and inactive content. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs');
const assert=require('assert/strict');
const results=[],errors=[],stamp=`Content verification ${Date.now()}`;
async function main(){
  const browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_EXECUTABLE||undefined});
  let current;
  async function settled(page){await page.waitForFunction(()=>[...document.querySelectorAll('main .loading')].every(el=>el.getClientRects().length===0));}
  async function login(role){const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();current=page;page.on('pageerror',e=>errors.push(e.message));await page.goto('http://127.0.0.1:5173');await page.getByLabel('Email address').fill(`${role}@resq.local`);await page.getByLabel('Password',{exact:true}).fill('ResqDemo!2026');await page.getByRole('button',{name:'Sign in',exact:true}).last().click();await page.getByRole('navigation',{name:'Main navigation'}).waitFor();await settled(page);return page;}
  async function open(page,path){current=page;await page.goto(`http://127.0.0.1:5173/#/${path}`);await page.locator('main h1').waitFor();await settled(page);assert.equal(await page.locator('main [role="alert"]').count(),0);}
  async function data(page,path){return page.evaluate(async path=>{const session=JSON.parse(sessionStorage.getItem('resq-session-v1'));const response=await fetch(`/api${path}`,{headers:{Authorization:`Bearer ${session.access_token}`}});if(!response.ok)throw new Error(`Read failed (${response.status})`);return response.json();},path);}
  async function save(page){await page.getByRole('dialog').getByRole('button',{name:'Save changes',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});await settled(page);}
  try{
    const citizen=await login('citizen'),admin=await login('admin');
    await open(admin,'news');
    await admin.getByRole('button',{name:'Write an update',exact:true}).click();
    let dialog=admin.getByRole('dialog');
    await dialog.getByLabel('Headline').fill(`${stamp} news`);
    await dialog.getByLabel('News content').fill('Synthetic content used to check coordinator review and publication. This is not a real disaster notice.');
    await dialog.getByLabel('Source',{exact:true}).fill('Browser verification');
    await save(admin);
    await admin.getByRole('heading',{name:`${stamp} news`,exact:true}).waitFor();
    assert.ok((await data(admin,'/admin/news')).some(n=>n.title===`${stamp} news`&&n.published===false));
    assert.equal((await data(citizen,'/news')).some(n=>n.title===`${stamp} news`),false);
    const newsCard=admin.locator('.news-card').filter({hasText:`${stamp} news`});
    await newsCard.getByRole('button',{name:'Verify update',exact:true}).click();
    await newsCard.getByRole('button',{name:'Publish verified update',exact:true}).click();
    await newsCard.getByRole('button',{name:'Return to draft',exact:true}).waitFor();
    assert.ok((await data(citizen,'/news')).some(n=>n.title===`${stamp} news`&&n.published===true));
    results.push({case:'admin saves a private news draft, verifies it, then publishes it to citizens',passed:true});

    await open(admin,'donations');
    await admin.getByRole('button',{name:'Create campaign',exact:true}).click();
    dialog=admin.getByRole('dialog');
    await dialog.getByLabel('Campaign title').fill(`${stamp} campaign`);
    await dialog.getByLabel('Description').fill('Synthetic campaign for checking coordinator management. No payments are collected.');
    await dialog.getByLabel('Donation target (₹)').fill('1000');
    await save(admin);
    await admin.getByRole('button',{name:`Edit ${stamp} campaign`,exact:true}).click();
    await admin.getByRole('dialog').getByRole('checkbox',{name:'Active',exact:true}).uncheck();
    await save(admin);
    assert.ok((await data(admin,'/admin/campaigns')).some(c=>c.title===`${stamp} campaign`&&!c.active));
    assert.equal((await data(citizen,'/donations/campaigns')).some(c=>c.title===`${stamp} campaign`),false);
    await admin.getByRole('button',{name:`Edit ${stamp} campaign`,exact:true}).click();
    await admin.getByRole('dialog').getByRole('checkbox',{name:'Active',exact:true}).check();
    await save(admin);
    assert.ok((await data(citizen,'/donations/campaigns')).some(c=>c.title===`${stamp} campaign`&&c.active));
    await admin.screenshot({path:'output/browser/admin-campaign-management.png',fullPage:true});
    results.push({case:'admin can deactivate and reactivate campaigns while citizens see only active ones',passed:true});

    current=citizen;
    await citizen.getByRole('button',{name:'Open safety assistant',exact:true}).click();
    const assistant=citizen.getByRole('dialog',{name:'ResQ safety assistant'});
    await assistant.getByLabel('Message the safety assistant').fill('Why should I avoid walking through floodwater?');
    await assistant.getByRole('button',{name:'Send message',exact:true}).click();
    await assistant.locator('.chat-sources a').first().waitFor({timeout:210000});
    assert.match(await assistant.locator('.chat-sources a').first().getAttribute('href'),/^https:\/\//);
    assert.ok((await assistant.locator('.chat-message.assistant').textContent()).includes('completed'));
    await citizen.screenshot({path:'output/browser/gemma-assistant.png',fullPage:true});
    await assistant.getByRole('button',{name:'Close assistant',exact:true}).click();
    await citizen.getByRole('button',{name:'Open safety assistant',exact:true}).click();
    await citizen.getByRole('dialog',{name:'ResQ safety assistant'}).getByLabel('Message the safety assistant').waitFor();
    results.push({case:'real Gemma answer has official source anchors; assistant opens/closes without lifecycle errors',passed:true});
    assert.deepEqual(errors,[],'No uncaught browser errors after repair');
  }catch(error){if(current)await current.screenshot({path:'output/browser/assistant-content-failure.png',fullPage:true}).catch(()=>{});throw error;}
  finally{fs.writeFileSync('output/browser/assistant-content-results.json',JSON.stringify({results,errors},null,2));await browser.close();}
  console.log(JSON.stringify({results,errors},null,2));
}
main().catch(e=>{console.error(e);process.exitCode=1;});

