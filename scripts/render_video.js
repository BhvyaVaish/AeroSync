const { spawn } = require('child_process');
const path = require('path');

process.env.TEMP = 'D:\\temp';
process.env.TMP = 'D:\\temp';
process.env.TMPDIR = 'D:\\temp';
process.env.HYPERFRAMES_BROWSER_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
process.env.HYPERFRAMES_EXTRACT_CACHE_DIR = 'D:\\hyperframes-cache';

const cliPath = path.resolve('C:/Users/Bhvya/.gemini/config/skills/hyperframes/scripts/plugin-cli.mjs');
const args = [
  cliPath,
  'render',
  'aerosync-video',
  '--output', 'aerosync-video/renders/aerosync_launch_45s.mp4',
  '--low-memory-mode',
  '--frames-cache-dir', 'D:\\hyperframes-cache'
];

console.log('Spawning HyperFrames render with D:\\temp (602GB free) and local Chrome...');
const child = spawn(process.execPath, args, {
  stdio: 'inherit',
  env: process.env
});

child.on('exit', (code) => {
  console.log('HyperFrames render exited with code:', code);
  process.exit(code || 0);
});
