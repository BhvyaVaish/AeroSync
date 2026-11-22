const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const snapDir = path.resolve('aerosync-video/renders/snapshots');
if (!fs.existsSync(snapDir)) fs.mkdirSync(snapDir, { recursive: true });

const times = [2, 8, 13, 18, 22, 26, 31, 36, 42];
times.forEach(t => {
  const out = path.join(snapDir, `frame_${t}s.png`);
  const cmd = `ffmpeg -y -ss ${t} -i "aerosync-video/renders/aerosync_launch_45s.mp4" -vframes 1 -q:v 2 "${out}"`;
  execSync(cmd, { stdio: 'inherit' });
  console.log(`Extracted frame at ${t}s`);
});

console.log('All review frames extracted successfully!');
