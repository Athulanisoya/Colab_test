/* Real browser workflow check. Set PLAYWRIGHT_MODULE to a Playwright package path.
   Set BROWSER_EXECUTABLE if using an existing Chromium browser installation. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const assert = require('assert/strict');
const output = 'output/browser';
fs.mkdirSync(output, {recursive: true});
const results = [];
const errors = [];

async function main() {
  const browser = await chromium.launch({headless:true, executablePath:process.env.BROWSER_EXECUTABLE || undefined});
  const contexts = [];
  async function workspace(role) {
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    contexts.push(context);
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:5173');
    await page.getByLabel('Email address').fill(`${role}@resq.local`);
    await page.getByLabel('Password',{exact:true}).fill('ResqDemo!2026');
    await page.getByRole('button',{name:'Sign in',exact:true}).last().click();
    await page.getByRole('navigation',{name:'Main navigation'}).waitFor();
    await page.waitForFunction(()=>document.querySelectorAll('main .loading').length===0);
    return page;
  }
  try {
    const citizen = await workspace('citizen');
    await citizen.screenshot({path:`${output}/citizen-dashboard.png`,fullPage:true});
    await citizen.getByRole('button',{name:'Report an incident',exact:true}).first().click();
    await citizen.getByLabel('What is happening? *').fill('Browser verification: water entered our house in Chengannur. Two children are trapped inside and need rescue.');
    await citizen.getByLabel('Location / nearest landmark (optional)').fill('Chengannur');
    await citizen.getByLabel('District (if known)').selectOption('Alappuzha');
    await citizen.getByLabel('People affected (if known)').fill('4');
    await citizen.getByRole('checkbox',{name:'Rescue',exact:true}).check();
    await citizen.getByRole('button',{name:'Submit report',exact:true}).click();
    await citizen.getByRole('heading',{name:'Incident details',exact:true}).waitFor();
    const incidentId = citizen.url().split('incident/')[1];
    assert.match(incidentId,/^\d+$/);
    results.push({case:'citizen submits report',passed:true,incidentId});
    const admin = await workspace('admin');
    await admin.screenshot({path:`${output}/admin-dashboard.png`,fullPage:true});
    await admin.goto(`http://127.0.0.1:5173/#/incident/${incidentId}`);
    await admin.getByRole('heading',{name:'Incident details',exact:true}).waitFor();
    await admin.getByLabel('Operational note').fill('Verified by telephone for browser demonstration.');
    await admin.getByRole('button',{name:'Verify report',exact:true}).click();
    await admin.locator('.section-heading .badge').getByText('Under Review',{exact:true}).waitFor();
    await admin.getByLabel('Operational note').waitFor();
    await admin.getByLabel('Operational note').fill('Assign available rescue team for the confirmed request.');
    const select = admin.getByLabel('Assign a response team');
    const options = await select.locator('option').allTextContents();
    const rescueLabel = options.find(value=>value.includes('Rescue'));
    assert.ok(rescueLabel,'Available rescue team');
    await select.selectOption({label:rescueLabel});
    await admin.getByRole('button',{name:'Assign team',exact:true}).click();
    await admin.getByRole('heading',{name:'Response team',exact:true}).waitFor();
    results.push({case:'admin verifies and assigns rescue',passed:true});
    const rescue = await workspace('rescue');
    await rescue.goto(`http://127.0.0.1:5173/#/incident/${incidentId}`);
    for(const [caption,note] of [['Accept task','Accepted the assigned rescue task.'],['Mark En Route','Departed for the reported location.'],['Mark In Progress','Reached the site; assistance is in progress.'],['Mark Resolved','Family assisted and safe for this demo.']]) {
      await rescue.getByLabel('Operational note').fill(note);
      await rescue.getByRole('button',{name:caption,exact:false}).click();
      await rescue.getByRole('button',{name:caption,exact:false}).waitFor({state:'hidden'});
    }
    await rescue.screenshot({path:`${output}/response-team.png`,fullPage:true});
    results.push({case:'assigned team progresses and resolves',passed:true});
    await admin.reload();
    await admin.getByLabel('Operational note').fill('Citizen confirmed that assistance was received. Closing the demo case.');
    await admin.getByRole('button',{name:'Close case',exact:true}).click();
    await admin.getByRole('button',{name:'Close case',exact:true}).waitFor({state:'hidden'});
    await citizen.reload();
    await citizen.getByRole('heading',{name:'Incident details',exact:true}).waitFor();
    assert.ok(await citizen.locator('.timeline').getByText('Closed',{exact:true}).count());
    // The actual model path must complete inside the persisted application flow.
    const analysisBadge = citizen.locator('.analysis-status .badge');
    await analysisBadge.getByText('Completed',{exact:true}).waitFor({timeout:210000});
    await citizen.screenshot({path:`${output}/closed-report.png`,fullPage:true});
    results.push({case:'citizen sees closure and real Gemma analysis',passed:true});
    for(const page of [citizen,admin,rescue]) {
      const paths = page===admin ? ['alerts','teams','shelters','relief','donations','news','users','reports','audit'] : ['alerts','shelters','relief','news','safety'];
      for(const path of paths) {
        await page.goto(`http://127.0.0.1:5173/#/${path}`);
        await page.locator('main h1').waitFor();
        await page.waitForFunction(()=>document.querySelectorAll('main .loading').length===0);
        assert.equal(await page.locator('main [role="alert"]').count(),0,`${path} API/renderer errors`);
      }
    }
    results.push({case:'role-specific navigation and data pages',passed:true});
    const mobile = await browser.newContext({viewport:{width:390,height:844}});
    contexts.push(mobile);
    const mobilePage=await mobile.newPage();
    await mobilePage.goto('http://127.0.0.1:5173');
    await mobilePage.getByLabel('Email address').fill('citizen@resq.local');
    await mobilePage.getByRole('button',{name:'Sign in',exact:true}).last().click();
    await mobilePage.locator('#main-content').waitFor();
    await mobilePage.getByRole('heading',{name:'Welcome, Anu.',exact:true}).waitFor();
    await mobilePage.waitForFunction(()=>document.querySelectorAll('main .loading').length===0);
    await mobilePage.screenshot({path:`${output}/mobile.png`,fullPage:true});
    assert.ok(await mobilePage.evaluate(()=>document.documentElement.scrollWidth <= innerWidth+1),'Mobile page does not overflow');
    results.push({case:'mobile layout',passed:true});
    assert.deepEqual(errors,[],'No uncaught browser errors');
  } finally {
    fs.writeFileSync(`${output}/results.json`,JSON.stringify({results,errors},null,2));
    await browser.close();
  }
  console.log(JSON.stringify({results,errors},null,2));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
