// Hidden Electron QA harness for the real activity panel and local aggregate data.
const { app, BrowserWindow } = require('electron');
const fs = require('node:fs/promises');
const path = require('node:path');
const { readAgentUsage } = require('../agent-usage');
const output = path.join(__dirname, '../../artifacts/usage-panels');
app.setPath('userData', path.join(output, 'electron-profile'));
app.whenReady().then(async () => {
  await fs.mkdir(output, { recursive: true });
  const window = new BrowserWindow({ width: 480, height: 720, show: false, frame: false,
    webPreferences: { contextIsolation: true, backgroundThrottling: false } });
  await window.loadFile(path.join(__dirname, '../renderer/dashboard.html'));
  const bootstrap = `globalThis.clawdyPanel = { onSnapshot() {}, resizeToContent() {}, close() {} };`;
  // Load the production renderer after supplying the same panel bridge as preload.
  await window.webContents.executeJavaScript(bootstrap);
  await window.webContents.executeJavaScript(await fs.readFile(path.join(__dirname, '../renderer/dashboard.js'), 'utf8'));
  for (const agent of ['opencode', 'antigravity']) {
    const usage = await readAgentUsage(agent);
    if (usage.status !== 'ready') throw new Error(`${agent}: ${usage.status}`);
    const snapshot = { agent, usage, linked: true, sessions: [], products: [] };
    await window.webContents.executeJavaScript(`render(${JSON.stringify(snapshot)});`);
    for (const period of ['all', 'day', 'month']) {
      await window.webContents.executeJavaScript(`document.getElementById('period-${period}').click();`);
      const height = await window.webContents.executeJavaScript(`Math.ceil(document.querySelector('.panel').getBoundingClientRect().height)`);
      window.setContentSize(480, height);
      await window.webContents.executeJavaScript('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
      const screenshot = await window.webContents.capturePage();
      await fs.writeFile(path.join(output, `${agent}-${period}.png`), screenshot.toPNG());
      const fits = await window.webContents.executeJavaScript('document.documentElement.scrollWidth <= window.innerWidth');
      if (!fits) throw new Error(`${agent}: content overflows`);
      console.log(`${agent}/${period}: ${height}px, no horizontal overflow`);
    }
  }
  window.destroy();
  app.quit();
}).catch(error => { console.error(error.message); app.exit(1); });
