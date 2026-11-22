const puppeteer = require('D:/npm-cache/_npx/b0784ff36a4b2f01/node_modules/puppeteer-core');
const fs = require('fs');
const path = require('path');

const TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5MDI4MGY0MC1jZGVmLTQ0OWEtOTU0OS05MWJmNGI5OTYyYjMiLCJ0eXBlIjoiYWNjZXNzIiwiaWF0IjoxNzk0OTk0Njg3LCJleHAiOjE3OTUwODEwODd9.jRLle_7tyu7CpDUfTKEy5S_6a6zZKgGnHHNAlS1rvK4';

async function main() {
  const outDir = path.resolve('aerosync-video/assets/ui');
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true,
    defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 2 },
    args: ['--window-size=1920,1080', '--no-sandbox']
  });

  const page = await browser.newPage();
  await page.evaluateOnNewDocument((token) => {
    localStorage.setItem('aerosync_token', token);
  }, TOKEN);

  await page.goto('http://localhost:5173/');
  await page.waitForSelector('.navbar', { timeout: 10000 });
  await new Promise(r => setTimeout(r, 1500));

  // 1. Dashboard
  await page.screenshot({ path: path.join(outDir, '01_dashboard.png') });
  console.log('Saved 01_dashboard.png');

  // 2. Selective Beam Modal
  const beamBtn = await page.evaluateHandle(() => {
    return Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Selective Beam'));
  });
  if (beamBtn && beamBtn.asElement()) {
    await beamBtn.asElement().click();
    await new Promise(r => setTimeout(r, 1000));
    await page.screenshot({ path: path.join(outDir, '02_selective_beam_modal.png') });
    console.log('Saved 02_selective_beam_modal.png');
    // close modal
    const closeBtn = await page.$('.modal-close, button[aria-label=\"Close\"], .modal-overlay');
    if (closeBtn) await closeBtn.click();
    else await page.keyboard.press('Escape');
    await new Promise(r => setTimeout(r, 600));
  }

  // 3. Walkthrough Guide Modal
  const guideBtn = await page.evaluateHandle(() => {
    return Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Walkthrough Guide'));
  });
  if (guideBtn && guideBtn.asElement()) {
    await guideBtn.asElement().click();
    await new Promise(r => setTimeout(r, 1000));
    await page.screenshot({ path: path.join(outDir, '03_walkthrough_modal.png') });
    console.log('Saved 03_walkthrough_modal.png');
    const closeBtn = await page.$('.modal-close, button[aria-label=\"Close\"], .modal-overlay');
    if (closeBtn) await closeBtn.click();
    else await page.keyboard.press('Escape');
    await new Promise(r => setTimeout(r, 600));
  }

  // 4. Camera HUD
  const camBtn = await page.evaluateHandle(() => {
    return Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Camera Sensor') || b.querySelector('svg.lucide-camera'));
  });
  if (camBtn && camBtn.asElement()) {
    await camBtn.asElement().click();
    await new Promise(r => setTimeout(r, 1500));
    await page.screenshot({ path: path.join(outDir, '04_camera_hud.png') });
    console.log('Saved 04_camera_hud.png');
    // close camera
    await camBtn.asElement().click();
    await new Promise(r => setTimeout(r, 600));
  }

  // 5. Constellations
  const constLink = await page.evaluateHandle(() => {
    return Array.from(document.querySelectorAll('a')).find(a => a.textContent.includes('Constellations'));
  });
  if (constLink && constLink.asElement()) {
    await constLink.asElement().click();
    await new Promise(r => setTimeout(r, 1200));
    await page.screenshot({ path: path.join(outDir, '05_constellations.png') });
    console.log('Saved 05_constellations.png');
  }

  // 6. Devices
  const devLink = await page.evaluateHandle(() => {
    return Array.from(document.querySelectorAll('a')).find(a => a.textContent.includes('Devices'));
  });
  if (devLink && devLink.asElement()) {
    await devLink.asElement().click();
    await new Promise(r => setTimeout(r, 1200));
    await page.screenshot({ path: path.join(outDir, '06_devices.png') });
    console.log('Saved 06_devices.png');
  }

  // 7. Armed State (Fist Host A trigger) on Dashboard
  await page.goto('http://localhost:5173/');
  await page.waitForSelector('.navbar', { timeout: 10000 });
  await new Promise(r => setTimeout(r, 1000));
  await page.evaluate(() => {
    // Dispatch armed event
    window.dispatchEvent(new CustomEvent('aerosync:gesture', {
      detail: { gesture: 'fist', isSelective: false }
    }));
  });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(outDir, '07_armed_state.png') });
  console.log('Saved 07_armed_state.png');

  // 8. Close-up crops of high-impact sections for zoom-throughs
  await page.screenshot({
    path: path.join(outDir, '08_deque_card.png'),
    clip: { x: 380, y: 350, width: 1160, height: 180 }
  });
  console.log('Saved 08_deque_card.png');

  await page.screenshot({
    path: path.join(outDir, '09_gesture_status_card.png'),
    clip: { x: 380, y: 190, width: 1160, height: 140 }
  });
  console.log('Saved 09_gesture_status_card.png');

  await browser.close();
  console.log('ALL_SCREENS_CAPTURED_SUCCESSFULLY');
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
