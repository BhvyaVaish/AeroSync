const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const audioDir = path.resolve('aerosync-video/assets/audio');
if (!fs.existsSync(audioDir)) fs.mkdirSync(audioDir, { recursive: true });

console.log('Generating cinematic cyberpunk synth soundtrack (45s)...');
const bgmPath = path.join(audioDir, 'soundtrack.mp3');
// 45s layered ambient cyberpunk drone
const bgmCmd = `ffmpeg -y -f lavfi -i "sine=frequency=55:duration=45[sub];sine=frequency=110:duration=45[low];sine=frequency=220:duration=45[mid];[sub][low][mid]amix=inputs=3:weights=0.5 0.3 0.2,afade=t=in:ss=0:d=0.8,afade=t=out:st=42.5:d=2.5,lowpass=f=1200,volume=0.8" -c:a libmp3lame -q:a 2 "${bgmPath}"`;
execSync(bgmCmd, { stdio: 'inherit' });
console.log('Generated soundtrack.mp3');

// sfx_whoosh.mp3 (0.5s)
const whooshPath = path.join(audioDir, 'sfx_whoosh.mp3');
const whooshCmd = `ffmpeg -y -f lavfi -i "anoisesrc=d=0.5:c=pink:r=44100,bandpass=f=800:width_type=h:w=600,afade=t=in:ss=0:d=0.2,afade=t=out:st=0.25:d=0.25,volume=0.9" -c:a libmp3lame "${whooshPath}"`;
execSync(whooshCmd, { stdio: 'inherit' });
console.log('Generated sfx_whoosh.mp3');

// sfx_click.mp3 (0.15s)
const clickPath = path.join(audioDir, 'sfx_click.mp3');
const clickCmd = `ffmpeg -y -f lavfi -i "sine=frequency=1800:duration=0.08,afade=t=out:st=0.01:d=0.07,volume=0.8" -c:a libmp3lame "${clickPath}"`;
execSync(clickCmd, { stdio: 'inherit' });
console.log('Generated sfx_click.mp3');

// sfx_lock.mp3 (0.4s)
const lockPath = path.join(audioDir, 'sfx_lock.mp3');
const lockCmd = `ffmpeg -y -f lavfi -i "sine=frequency=520:duration=0.35,afade=t=out:st=0.15:d=0.2,volume=0.8" -c:a libmp3lame "${lockPath}"`;
execSync(lockCmd, { stdio: 'inherit' });
console.log('Generated sfx_lock.mp3');

// sfx_beam.mp3 (0.8s)
const beamPath = path.join(audioDir, 'sfx_beam.mp3');
const beamCmd = `ffmpeg -y -f lavfi -i "sine=frequency=320:duration=0.8,afade=t=in:ss=0:d=0.05,afade=t=out:st=0.4:d=0.4,tremolo=f=12:d=0.6,volume=0.8" -c:a libmp3lame "${beamPath}"`;
execSync(beamCmd, { stdio: 'inherit' });
console.log('Generated sfx_beam.mp3');

console.log('All audio assets synthesized successfully!');
