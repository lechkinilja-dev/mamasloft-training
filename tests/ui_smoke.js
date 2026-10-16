const { chromium } = require('playwright-core');
const fs = require('fs');

const modules = JSON.parse(fs.readFileSync('docs/content.json', 'utf8'));

async function mock(page) {
  await page.route('https://script.google.com/**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ ok: true, name: 'Илья', role: 'admin' }),
  }));
  await page.route('**/academy-api/rpc', async route => {
    const body = JSON.parse(route.request().postData() || '{}');
    let result = { ok: true };
    if (body.route === 'content_get') result = { ok: true, modules };
    if (body.route === 'progress_get') result = { ok: true, progress: {} };
    if (body.route === 'admin_content_get') result = { ok: true, modules, meta: { version: 1 } };
    if (body.route === 'admin_data') result = { ok: true, modules, users: [{ name: 'Илья' }], progress: {} };
    if (body.route === 'admin_mutate') result = { ok: true, modules, meta: { version: 2 } };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(result) });
  });
}

async function login(page, url) {
  await page.goto(url);
  await page.locator('#pin, #pin-input').fill('111111');
  await page.locator('#login, #login-btn').click();
}

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
  for (const profile of [
    { name: 'desktop', viewport: { width: 1440, height: 1000 } },
    { name: 'mobile', viewport: { width: 390, height: 844 }, isMobile: true },
  ]) {
    const context = await browser.newContext(profile);
    const page = await context.newPage();
    await mock(page);
    await login(page, 'http://127.0.0.1:8099/admin.html');
    await page.locator('.topic-card').first().waitFor();
    if (await page.locator('.topic-card').count() !== 8) throw new Error(`${profile.name}: expected 8 topic cards`);
    if (await page.getByText('IVA Design: ткани сезона осень–зима', { exact: true }).count() !== 1) throw new Error(`${profile.name}: IVA topic missing`);
    const ivaCard = page.locator('.topic-card').filter({ hasText: 'IVA Design: ткани сезона осень–зима' });
    await ivaCard.getByText('Изменить').click();
    await page.locator('#editor-modal.open').waitFor();
    if (await page.locator('.question').count() !== 10) throw new Error(`${profile.name}: expected 10 editable questions`);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    if (overflow) throw new Error(`${profile.name}: horizontal overflow`);
    await page.screenshot({ path: `/private/tmp/academy-admin-${profile.name}.png`, fullPage: false });
    await context.close();
  }

  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true });
  const page = await context.newPage();
  await mock(page);
  await login(page, 'http://127.0.0.1:8099/');
  await page.locator('.module-card').first().waitFor();
  if (await page.locator('.module-card').count() !== 8) throw new Error('student: expected 8 published topics');
  await page.getByText('IVA Design: ткани сезона осень–зима', { exact: true }).click();
  await page.locator('#lecture-body').getByText('Арктика', { exact: true }).waitFor();
  await page.getByRole('button', { name: /Тест/ }).click();
  if (await page.locator('.qdot').count() !== 10) throw new Error('student: expected 10 quiz dots');
  await page.screenshot({ path: '/private/tmp/academy-student-mobile.png', fullPage: false });
  await context.close();
  await browser.close();
  console.log('UI smoke passed: desktop + mobile admin, mobile student');
})().catch(error => { console.error(error.message); process.exit(1); });
