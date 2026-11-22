import { useEffect, useRef } from 'react';

/**
 * SpaceBackground — Futuristic Architectural Telemetry & Obsidian Deep Space Canvas
 * Features:
 * - Velvety Z-Black base with volumetric deep space nebula washes
 * - Fine architectural coordinate grid with precision corner crosshairs & telemetry markings
 * - Dynamic orbital trajectory paths with traversing satellite telemetry nodes
 * - High-velocity collimated light streaks (stealth laser pulses / telemetry beams)
 * - Liquid specular caustic glints (inspired by obsidian liquid reflections)
 * - Subtle silky mouse parallax response
 */
export const SpaceBackground = () => {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    let animId;
    let w = window.innerWidth;
    let h = window.innerHeight;

    let mouseX = w / 2;
    let mouseY = h / 2;
    let targetMouseX = w / 2;
    let targetMouseY = h / 2;

    const handleMouseMove = (e) => {
      targetMouseX = e.clientX;
      targetMouseY = e.clientY;
    };
    window.addEventListener('mousemove', handleMouseMove);

    const resize = () => {
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = w;
      canvas.height = h;
    };
    resize();
    window.addEventListener('resize', resize);

    // 1. Specular Caustic Glints (Ref Image 7: Shimmering liquid obsidian caustic points)
    const GLINT_COUNT = 18;
    const glints = Array.from({ length: GLINT_COUNT }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      size: Math.random() * 2.5 + 1.2,
      phase: Math.random() * Math.PI * 2,
      speed: Math.random() * 0.02 + 0.008,
      maxAlpha: Math.random() * 0.35 + 0.15,
    }));

    // 2. Micro silver dust motes (subtle floating depth particles)
    const MOTE_COUNT = 40;
    const motes = Array.from({ length: MOTE_COUNT }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.12,
      vy: (Math.random() - 0.5) * 0.12,
      size: Math.random() * 0.9 + 0.4,
      alpha: Math.random() * 0.18 + 0.05,
    }));

    // 3. Orbital Telemetry Nodes
    const orbits = [
      { cx: w * 0.35, cy: h * 0.3, rx: 340, ry: 160, angle: 0, speed: 0.003, color: 'rgba(56, 189, 248, 0.7)' },
      { cx: w * 0.75, cy: h * 0.7, rx: 420, ry: 200, angle: Math.PI, speed: -0.0022, color: 'rgba(192, 132, 252, 0.65)' },
    ];

    // 4. Stealth Telemetry Beams / Collimated Light Pulses
    const beams = [];
    let lastBeamTime = 0;

    const spawnBeam = () => {
      const startX = Math.random() * (w * 0.8) + w * 0.2;
      const startY = -40;
      const angle = (Math.PI / 180) * (30 + Math.random() * 12); // ~35 deg downward
      const speed = Math.random() * 16 + 22; // High-velocity telemetry streak
      const length = Math.random() * 140 + 100;
      beams.push({
        x: startX,
        y: startY,
        vx: -Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        length,
        alpha: Math.random() * 0.45 + 0.35,
        life: 1.0,
      });
    };

    let t = 0;

    const render = () => {
      t += 0.01;

      // Smooth mouse damping
      mouseX += (targetMouseX - mouseX) * 0.03;
      mouseY += (targetMouseY - mouseY) * 0.03;
      const offsetX = ((mouseX - w / 2) / (w / 2)) * 12;
      const offsetY = ((mouseY - h / 2) / (h / 2)) * 12;

      // ── Step 1: Deep Obsidian / Z-Black Base ─────────────────
      ctx.fillStyle = '#000000';
      ctx.fillRect(0, 0, w, h);

      // ── Step 2: Volumetric Deep Space Nebulae & Studio Lights ──
      // Top ambient studio highlight
      const topGrad = ctx.createRadialGradient(
        w * 0.5 + offsetX * 1.5,
        h * 0.05 + offsetY * 1.5,
        0,
        w * 0.5,
        h * 0.05,
        Math.max(w, h) * 0.75
      );
      topGrad.addColorStop(0, 'rgba(255, 255, 255, 0.038)');
      topGrad.addColorStop(0.35, 'rgba(200, 215, 240, 0.015)');
      topGrad.addColorStop(0.7, 'rgba(30, 41, 59, 0.025)');
      topGrad.addColorStop(1, 'transparent');
      ctx.fillStyle = topGrad;
      ctx.fillRect(0, 0, w, h);

      // Deep cyan/indigo mesh nebula (subtle bottom-left)
      const leftNebula = ctx.createRadialGradient(
        w * 0.15 + offsetX,
        h * 0.85 + offsetY,
        0,
        w * 0.15,
        h * 0.85,
        Math.max(w, h) * 0.45
      );
      leftNebula.addColorStop(0, 'rgba(14, 165, 233, 0.032)');
      leftNebula.addColorStop(0.5, 'rgba(99, 102, 241, 0.015)');
      leftNebula.addColorStop(1, 'transparent');
      ctx.fillStyle = leftNebula;
      ctx.fillRect(0, 0, w, h);

      // Deep violet/charcoal aura (subtle top-right)
      const rightNebula = ctx.createRadialGradient(
        w * 0.85 - offsetX,
        h * 0.25 - offsetY,
        0,
        w * 0.85,
        h * 0.25,
        Math.max(w, h) * 0.4
      );
      rightNebula.addColorStop(0, 'rgba(168, 85, 247, 0.028)');
      rightNebula.addColorStop(0.6, 'rgba(51, 65, 85, 0.015)');
      rightNebula.addColorStop(1, 'transparent');
      ctx.fillStyle = rightNebula;
      ctx.fillRect(0, 0, w, h);

      // ── Step 3: Architectural Coordinate Grid & Reticles ───────
      const STEP = 80;
      const gridShiftX = offsetX * 0.35;
      const gridShiftY = offsetY * 0.35;

      ctx.lineWidth = 0.5;
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.02)';
      ctx.beginPath();
      for (let x = (gridShiftX % STEP); x < w; x += STEP) {
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
      }
      for (let y = (gridShiftY % STEP); y < h; y += STEP) {
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
      }
      ctx.stroke();

      // Precision Corner Reticles / Crosshairs at every 3rd intersection
      ctx.lineWidth = 0.6;
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.055)';
      const crossSize = 3;
      for (let x = (gridShiftX % (STEP * 3)); x < w; x += STEP * 3) {
        for (let y = (gridShiftY % (STEP * 3)); y < h; y += STEP * 3) {
          ctx.beginPath();
          ctx.moveTo(x - crossSize, y);
          ctx.lineTo(x + crossSize, y);
          ctx.moveTo(x, y - crossSize);
          ctx.lineTo(x, y + crossSize);
          ctx.stroke();
        }
      }

      // ── Step 4: Orbital Trajectory Paths & Traversing Nodes ────
      orbits.forEach(orb => {
        orb.angle += orb.speed;
        const currentCx = orb.cx + offsetX * 0.5;
        const currentCy = orb.cy + offsetY * 0.5;

        // Elliptical Trajectory Arc
        ctx.lineWidth = 0.6;
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)';
        ctx.beginPath();
        ctx.ellipse(currentCx, currentCy, orb.rx, orb.ry, Math.PI / 12, 0, Math.PI * 2);
        ctx.stroke();

        // Traversing Telemetry Waypoint Node
        const nodeX = currentCx + Math.cos(orb.angle) * orb.rx;
        const nodeY = currentCy + Math.sin(orb.angle) * orb.ry;

        // Subtle glow halo
        const halo = ctx.createRadialGradient(nodeX, nodeY, 0, nodeX, nodeY, 12);
        halo.addColorStop(0, orb.color);
        halo.addColorStop(1, 'transparent');
        ctx.fillStyle = halo;
        ctx.beginPath();
        ctx.arc(nodeX, nodeY, 12, 0, Math.PI * 2);
        ctx.fill();

        // Node center
        ctx.fillStyle = '#FFFFFF';
        ctx.beginPath();
        ctx.arc(nodeX, nodeY, 1.4, 0, Math.PI * 2);
        ctx.fill();
      });

      // ── Step 5: Liquid Specular Caustic Glints (twinkling diamonds)
      glints.forEach(g => {
        g.phase += g.speed;
        const alpha = ((Math.sin(g.phase) + 1) / 2) * g.maxAlpha;
        if (alpha > 0.04) {
          ctx.strokeStyle = `rgba(255, 255, 255, ${alpha * 0.8})`;
          ctx.lineWidth = 0.5;
          const gx = g.x + offsetX * 0.2;
          const gy = g.y + offsetY * 0.2;

          // 4-Point Specular Flare
          ctx.beginPath();
          ctx.moveTo(gx - g.size * 2, gy);
          ctx.lineTo(gx + g.size * 2, gy);
          ctx.moveTo(gx, gy - g.size * 2);
          ctx.lineTo(gx, gy + g.size * 2);
          ctx.stroke();

          // Center specular core
          ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
          ctx.fillRect(gx - 0.75, gy - 0.75, 1.5, 1.5);
        }
      });

      // ── Step 6: Stealth Telemetry Laser Streaks / Beams ───────
      if (Date.now() - lastBeamTime > 3200 + Math.random() * 2500) {
        spawnBeam();
        lastBeamTime = Date.now();
      }

      for (let i = beams.length - 1; i >= 0; i--) {
        const b = beams[i];
        b.x += b.vx;
        b.y += b.vy;
        b.life -= 0.016;

        if (b.x < -100 || b.y > h + 100 || b.life <= 0) {
          beams.splice(i, 1);
          continue;
        }

        // Draw precision collimated laser trail
        const trailX = b.x - (b.vx / Math.hypot(b.vx, b.vy)) * b.length;
        const trailY = b.y - (b.vy / Math.hypot(b.vx, b.vy)) * b.length;

        const beamGrad = ctx.createLinearGradient(trailX, trailY, b.x, b.y);
        beamGrad.addColorStop(0, 'rgba(255, 255, 255, 0)');
        beamGrad.addColorStop(0.7, `rgba(200, 225, 255, ${b.alpha * b.life * 0.4})`);
        beamGrad.addColorStop(1, `rgba(255, 255, 255, ${b.alpha * b.life})`);

        ctx.lineWidth = 1.0;
        ctx.strokeStyle = beamGrad;
        ctx.beginPath();
        ctx.moveTo(trailX, trailY);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();

        // Tip pulse
        ctx.fillStyle = `rgba(255, 255, 255, ${b.alpha * b.life})`;
        ctx.fillRect(b.x - 1, b.y - 1, 2, 2);
      }

      // ── Step 7: Slow Micro Dust Particles ─────────────────────
      motes.forEach(m => {
        m.x += m.vx;
        m.y += m.vy;
        if (m.x < 0) m.x = w;
        if (m.x > w) m.x = 0;
        if (m.y < 0) m.y = h;
        if (m.y > h) m.y = 0;

        ctx.fillStyle = `rgba(255, 255, 255, ${m.alpha})`;
        ctx.fillRect(m.x + offsetX * 0.1, m.y + offsetY * 0.1, m.size, m.size);
      });

      animId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', handleMouseMove);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        zIndex: 0,
        pointerEvents: 'none',
      }}
    />
  );
};
