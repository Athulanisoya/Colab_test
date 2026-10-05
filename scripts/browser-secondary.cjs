/* Real secondary browser workflows, using the running local demo services.
   PLAYWRIGHT_MODULE and BROWSER_EXECUTABLE can point to existing installations. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs');
const assert=require('assert/strict');
const output='output/browser';
fs.mkdirSync(output,{recursive:true});
const results=[],errors=[];
const stamp=`Browser secondary ${Date.now()}`;
async function savePledge(page){await page.getByRole('dialog').getByRole('button',{name:'Continue donation',exact:true}).click();await page.getByRole('dialog').getByLabel('Transfer / delivery reference').waitFor();await page.getByRole('dialog').getByRole('button',{name:'Close dialog',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});}
async function main(){
  const browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_EXECUTABLE||undefined});
  let lastPage;
  async function settled(page){await page.waitForFunction(()=>[...document.querySelectorAll('main .loading')].every(el=>el.getClientRects().length===0));}
  async function workspace(role){const context=await browser.newContext({viewport:{width:1440,height:1000}});const page=await context.newPage();lastPage=page;page.on('pageerror',e=>errors.push(e.message));await page.goto('http://127.0.0.1:5173');await page.getByLabel('Email address').fill(`${role}@resq.local`);await page.getByLabel('Password',{exact:true}).fill('ResqDemo!2026');await page.getByRole('button',{name:'Sign in',exact:true}).last().click();await page.getByRole('navigation',{name:'Main navigation'}).waitFor();await settled(page);return page;}
  async function open(page,path){lastPage=page;await page.goto(`http://127.0.0.1:5173/#/${path}`);await page.locator('main h1').waitFor();await settled(page);assert.equal(await page.locator('main [role="alert"]').count(),0,`${path} should load without errors`);}
  async function data(page,path){return page.evaluate(async(path)=>{const session=JSON.parse(sessionStorage.getItem('resq-session-v1'));const response=await fetch(`/api${path}`,{headers:{Authorization:`Bearer ${session.access_token}`}});if(!response.ok)throw new Error(`Read failed (${response.status})`);return response.json();},path);}
  async function mutate(page,path,body){return page.evaluate(async({path,body})=>{const session=JSON.parse(sessionStorage.getItem('resq-session-v1'));const response=await fetch(`/api${path}`,{method:'POST',headers:{Authorization:`Bearer ${session.access_token}`,'Content-Type':'application/json'},body:JSON.stringify(body)});const value=await response.json();if(!response.ok)throw new Error(`Fixture setup failed (${response.status}): ${JSON.stringify(value)}`);return value;},{path,body});}
  async function noModalError(page){assert.equal(await page.getByRole('dialog').locator('[role="alert"]').count(),0,'Form should not show an error');}
  async function saveModal(page,caption='Save changes'){const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:caption,exact:true}).click();await dialog.waitFor({state:'hidden'});await settled(page);}
  try{
    const citizen=await workspace('citizen'),admin=await workspace('admin');
    // Each run owns a fresh investigation case; existing demo cases are not reset.
    const investigationCase=await mutate(citizen,'/incidents',{message:`${stamp}: Water entered the home in Ranni. Four people need help.`,location:'Ranni',district:'Pathanamthitta',people_affected:4,help_required:['Water']});
    const investigationId=investigationCase.id;
    const investigationTeam=(await data(admin,'/teams/available')).find(t=>t.team_type==='investigation');
    assert.ok(investigationTeam,'An investigation team is available for this isolated case');
    await mutate(admin,`/incidents/${investigationId}/review`,{verified:false,note:'Synthetic browser case requires field verification.'});
    await mutate(admin,'/teams/assign',{incident_id:investigationId,team_id:investigationTeam.id,note:'Synthetic investigation fixture.'});
    await open(citizen,'relief');
    await citizen.getByRole('button',{name:'Request supplies',exact:true}).click();
    let dialog=citizen.getByRole('dialog');
    const waterCatalog=(await data(citizen,'/relief/catalog')).find(row=>row.item==='Water');
    await dialog.getByLabel('Available supply item').selectOption(String(waterCatalog.inventory_id));
    await dialog.getByLabel('Quantity',{exact:true}).fill('3');
    await dialog.getByLabel('Delivery location / landmark').fill('Aluva — local demonstration');
    await dialog.getByLabel('Related report (optional)').selectOption('3');
    await dialog.getByLabel('Additional note').fill(stamp);
    await saveModal(citizen,'Submit request');
    const request=(await data(citizen,'/relief/my')).find(r=>r.note===stamp);
    assert.ok(request,'Relief request persisted');
    await open(admin,'relief');
    const stock=(await data(admin,'/relief/inventory')).find(i=>i.item==='Water');
    await admin.locator('.relief-request').filter({hasText:stamp}).getByRole('button',{name:'Record distribution',exact:false}).click();
    dialog=admin.getByRole('dialog');
    await dialog.getByLabel('Inventory item').selectOption(String(stock.id));
    await dialog.getByLabel('Quantity distributed').fill('3');
    await dialog.getByLabel('Additional note').fill('Allocated by the browser verification coordinator.');
    await saveModal(admin,'Record distribution');
    const nextStock=(await data(admin,'/relief/inventory')).find(i=>i.id===stock.id);
    const fulfilled=(await data(citizen,'/relief/my')).find(r=>r.id===request.id);
    assert.equal(nextStock.quantity,stock.quantity-3);
    assert.equal(fulfilled.status,'fulfilled');
    assert.equal(fulfilled.distributions[0].quantity,3);
    await admin.screenshot({path:`${output}/relief-distribution.png`,fullPage:true});
    results.push({case:'citizen relief request and admin stock distribution',passed:true,request_id:request.id,stock_decrement:3});

    await open(citizen,'donations');
    let campaign=citizen.locator('.campaign-card').first();
    await campaign.getByRole('button',{name:'Donate money or supplies',exact:false}).click();
    dialog=citizen.getByRole('dialog');
    await dialog.getByLabel('Donation amount (₹)').fill('750');
    await dialog.getByLabel('Coordination note (optional)').fill(`${stamp} money`);
    await savePledge(citizen);
    campaign=citizen.locator('.campaign-card').first();
    await campaign.getByRole('button',{name:'Make a support pledge',exact:false}).click();
    dialog=citizen.getByRole('dialog');
    await dialog.getByRole('button',{name:'Donate supplies',exact:true}).click();
    await dialog.getByLabel('Item',{exact:true}).fill('Food');
    await dialog.getByLabel('Quantity',{exact:true}).fill('8');
    await dialog.getByLabel('Coordination note (optional)').fill(`${stamp} supplies`);
    await savePledge(citizen);
    const pledges=(await data(citizen,'/donations/my')).filter(p=>p.note.startsWith(stamp));
    assert.ok(pledges.some(p=>p.kind==='money'&&p.amount===750));
    assert.ok(pledges.some(p=>p.kind==='supplies'&&p.items[0].quantity===8));
    await citizen.screenshot({path:`${output}/support-pledges.png`,fullPage:true});
    results.push({case:'citizen money and supply pledges without payment',passed:true});

    await open(admin,'alerts');
    await admin.getByRole('button',{name:'Create alert',exact:true}).click();
    dialog=admin.getByRole('dialog');
    await dialog.getByLabel('Alert title').fill(`${stamp} alert`);
    await dialog.getByLabel('Severity').selectOption('moderate');
    await dialog.getByLabel('Alert message').fill('Synthetic browser verification alert. This is not an official warning.');
    await dialog.getByLabel('Location',{exact:true}).fill('Aluva');
    await dialog.getByLabel('District').selectOption('Ernakulam');
    await saveModal(admin);
    let createdAlert=(await data(admin,'/admin/alerts')).find(a=>a.title===`${stamp} alert`);
    assert.ok(createdAlert&&createdAlert.active);
    await admin.getByRole('button',{name:`Edit ${stamp} alert`,exact:true}).click();
    dialog=admin.getByRole('dialog');
    await dialog.getByRole('checkbox',{name:'Active',exact:true}).uncheck();
    await saveModal(admin);
    createdAlert=(await data(admin,'/admin/alerts')).find(a=>a.id===createdAlert.id);
    assert.equal(createdAlert.active,false);
    await admin.getByRole('checkbox',{name:'Include inactive alerts'}).check();
    await admin.getByRole('heading',{name:`${stamp} alert`,exact:true}).waitFor();
    results.push({case:'admin creates and expires a flood alert; inactive remains manageable',passed:true});

    const shelter=await workspace('shelter');
    await open(shelter,'shelters');
    const beforeShelters=await data(shelter,'/shelters');
    const own=beforeShelters.find(s=>s.name==='Demo · Chengannur Community Hall');
    const other=beforeShelters.find(s=>s.name==='Demo · Aluva School Shelter');
    await shelter.getByRole('button',{name:`Edit ${own.name}`,exact:true}).click();
    dialog=shelter.getByRole('dialog');
    assert.equal(await dialog.getByLabel('Total capacity').count(),0,'Shelter team cannot alter capacity');
    await dialog.getByLabel('Current occupancy').fill(String(own.occupied+1));
    await saveModal(shelter);
    const afterShelters=await data(shelter,'/shelters');
    assert.equal(afterShelters.find(s=>s.id===own.id).occupied,own.occupied+1);
    assert.equal(afterShelters.find(s=>s.id===other.id).occupied,other.occupied);
    assert.equal(await shelter.getByRole('button',{name:`Edit ${other.name}`,exact:true}).count(),0);
    await shelter.screenshot({path:`${output}/shelter-occupancy.png`,fullPage:true});
    results.push({case:'shelter team updates own occupancy; unrelated shelter protected',passed:true});

    const investigation=await workspace('investigation');
    await open(investigation,`incident/${investigationId}`);
    await investigation.getByText('Submit an investigation report',{exact:true}).click();
    await investigation.getByLabel('Verified findings').fill(`${stamp}: water has entered the home in Ranni. Four people need verified rescue assistance.`);
    await investigation.getByLabel('People observed at location').fill('4');
    await investigation.getByLabel('Required supplies / assistance').fill('Rescue, Water');
    await investigation.getByRole('checkbox',{name:'Incident confirmed at location'}).check();
    await investigation.getByRole('button',{name:'Submit findings',exact:true}).click();
    await investigation.getByRole('heading',{name:'Field investigation',exact:true}).waitFor();
    assert.ok((await data(investigation,`/investigation/${investigationId}/reports`)).some(f=>f.findings.startsWith(stamp)&&f.people_affected===4));
    await open(admin,`incident/${investigationId}`);
    await admin.getByRole('heading',{name:'Field investigation',exact:true}).waitFor();
    await admin.getByLabel('Operational note').fill('Confirmed the field investigation. Rescue assignment is now justified.');
    await admin.getByRole('button',{name:'Verify report',exact:true}).click();
    await admin.locator('.section-heading .badge').getByText('Under Review',{exact:true}).waitFor();
    await admin.getByLabel('Operational note').fill('Reassign the confirmed incident to the available rescue team.');
    const options=await admin.getByLabel('Assign a response team').locator('option').allTextContents();
    const rescueOption=options.find(v=>v.includes('Rescue'));
    assert.ok(rescueOption,'Rescue is available after the main workflow test');
    await admin.getByLabel('Assign a response team').selectOption({label:rescueOption});
    await admin.getByRole('button',{name:'Assign team',exact:true}).click();
    await admin.getByRole('heading',{name:'Response team',exact:true}).waitFor();
    const updated=await data(admin,`/incidents/${investigationId}`);
    assert.equal(updated.assignment.team_type,'rescue');
    assert.equal(updated.status,'team_assigned');
    assert.equal(updated.verified,true);
    await admin.screenshot({path:`${output}/investigation-reassignment.png`,fullPage:true});
    results.push({case:'investigation findings return to admin review and rescue reassignment',passed:true,incident_id:investigationId});
    const pastTasks=await data(investigation,'/teams/history');
    assert.ok(pastTasks.some(task=>task.incident_id===investigationId),'The investigator retains their own past task summary');
    const rescue=await workspace('rescue');
    await open(rescue,`incident/${investigationId}`);
    for(const caption of ['Accept task','Mark En Route','Mark In Progress','Mark Resolved']){
      await rescue.getByLabel('Operational note').fill(`${stamp}: synthetic rescue progress.`);
      await rescue.getByRole('button',{name:caption,exact:false}).click();
      await rescue.getByRole('button',{name:caption,exact:false}).waitFor({state:'hidden'});
    }
    await open(admin,`incident/${investigationId}`);
    await admin.getByLabel('Operational note').fill('Synthetic investigation and rescue checks completed.');
    await admin.getByRole('button',{name:'Close case',exact:true}).click();
    await admin.getByRole('button',{name:'Close case',exact:true}).waitFor({state:'hidden'});
    assert.equal((await data(admin,`/incidents/${investigationId}`)).status,'closed');
    results.push({case:'reassigned case closes; released investigator retains private task history',passed:true});

    await citizen.getByRole('button',{name:'Open safety assistant',exact:true}).click();
    const assistant=citizen.getByRole('dialog',{name:'ResQ safety assistant'});
    await assistant.getByLabel('Message the safety assistant').fill('Why should I avoid walking through floodwater?');
    await assistant.getByRole('button',{name:'Send message',exact:true}).click();
    await assistant.locator('.chat-sources a').first().waitFor({timeout:210000});
    const href=await assistant.locator('.chat-sources a').first().getAttribute('href');
    assert.match(href,/^https:\/\//);
    assert.ok((await assistant.locator('.chat-message.assistant').textContent()).includes('completed'));
    await citizen.screenshot({path:`${output}/gemma-assistant.png`,fullPage:true});
    results.push({case:'real Gemma assistant produces grounded answer with source anchors',passed:true});
    assert.deepEqual(errors,[],'No uncaught browser errors');
  }catch(error){if(lastPage)await lastPage.screenshot({path:`${output}/secondary-failure.png`,fullPage:true}).catch(()=>{});throw error;}
  finally{fs.writeFileSync(`${output}/secondary-results.json`,JSON.stringify({results,errors},null,2));await browser.close();}
  console.log(JSON.stringify({results,errors},null,2));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
