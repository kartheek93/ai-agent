import { useEffect, useRef } from "react";

const PARTICLE_COUNT = 120;
const GRID_COLS = 24;
const GRID_ROWS = 14;

function rand(min, max) { return Math.random() * (max - min) + min; }

export default function SpaceBackground() {
    const canvasRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        let raf;
        let W = 0, H = 0;

        function resize() {
            W = canvas.width = window.innerWidth;
            H = canvas.height = window.innerHeight;
        }
        resize();
        window.addEventListener("resize", resize);

        // Particles (stars)
        const particles = Array.from({ length: PARTICLE_COUNT }, () => ({
            x: rand(0, 1),
            y: rand(0, 1),
            r: rand(0.5, 2.2),
            speed: rand(0.00005, 0.00018),
            opacity: rand(0.3, 1),
            phase: rand(0, Math.PI * 2),
            twinkleSpeed: rand(0.005, 0.02),
        }));

        // Floating orbs
        const orbs = Array.from({ length: 5 }, (_, i) => ({
            x: rand(0.1, 0.9),
            y: rand(0.1, 0.9),
            radius: rand(60, 180),
            speedX: rand(-0.00006, 0.00006),
            speedY: rand(-0.00004, 0.00004),
            hue: [210, 220, 195, 240, 205][i],
        }));

        // Robot grid nodes
        const nodes = [];
        const cw = 1 / GRID_COLS;
        const ch = 1 / GRID_ROWS;
        for (let c = 0; c <= GRID_COLS; c++) {
            for (let r = 0; r <= GRID_ROWS; r++) {
                nodes.push({
                    bx: (c + 0.5) * cw,
                    by: (r + 0.5) * ch,
                    ox: rand(-cw * 0.3, cw * 0.3),
                    oy: rand(-ch * 0.3, ch * 0.3),
                    phase: rand(0, Math.PI * 2),
                    speed: rand(0.003, 0.008),
                    active: Math.random() < 0.3,
                    pulsePhase: rand(0, Math.PI * 2),
                });
            }
        }

        let t = 0;

        function draw() {
            t++;
            ctx.clearRect(0, 0, W, H);

            // Deep space gradient background
            const bg = ctx.createLinearGradient(0, 0, 0, H);
            bg.addColorStop(0, "#020614");
            bg.addColorStop(0.5, "#050a1e");
            bg.addColorStop(1, "#030810");
            ctx.fillStyle = bg;
            ctx.fillRect(0, 0, W, H);

            // Floating orbs (nebulae)
            for (const orb of orbs) {
                orb.x += orb.speedX;
                orb.y += orb.speedY;
                if (orb.x < 0 || orb.x > 1) orb.speedX *= -1;
                if (orb.y < 0 || orb.y > 1) orb.speedY *= -1;
                const grd = ctx.createRadialGradient(
                    orb.x * W, orb.y * H, 0,
                    orb.x * W, orb.y * H, orb.radius
                );
                grd.addColorStop(0, `hsla(${orb.hue},80%,60%,0.06)`);
                grd.addColorStop(0.5, `hsla(${orb.hue},70%,45%,0.03)`);
                grd.addColorStop(1, "transparent");
                ctx.fillStyle = grd;
                ctx.beginPath();
                ctx.arc(orb.x * W, orb.y * H, orb.radius, 0, Math.PI * 2);
                ctx.fill();
            }

            // Grid lines (circuit board / robot aesthetic)
            ctx.strokeStyle = "rgba(99,179,237,0.04)";
            ctx.lineWidth = 1;
            const gcw = W / GRID_COLS;
            const gch = H / GRID_ROWS;
            for (let c = 0; c <= GRID_COLS; c++) {
                ctx.beginPath();
                ctx.moveTo(c * gcw, 0);
                ctx.lineTo(c * gcw, H);
                ctx.stroke();
            }
            for (let r = 0; r <= GRID_ROWS; r++) {
                ctx.beginPath();
                ctx.moveTo(0, r * gch);
                ctx.lineTo(W, r * gch);
                ctx.stroke();
            }

            // Grid nodes + connections
            for (const node of nodes) {
                node.pulsePhase += node.speed;
                const px = (node.bx + node.ox * Math.sin(node.pulsePhase)) * W;
                const py = (node.by + node.oy * Math.cos(node.pulsePhase * 0.7)) * H;
                node._px = px;
                node._py = py;
            }
            // Draw connections between nearby nodes
            for (let i = 0; i < nodes.length; i++) {
                if (!nodes[i].active) continue;
                for (let j = i + 1; j < nodes.length; j++) {
                    if (!nodes[j].active) continue;
                    const dx = nodes[i]._px - nodes[j]._px;
                    const dy = nodes[i]._py - nodes[j]._py;
                    const dist = Math.sqrt(dx * dx + dy * dy);
                    if (dist < 180) {
                        const alpha = (1 - dist / 180) * 0.12;
                        ctx.strokeStyle = `rgba(99,179,237,${alpha})`;
                        ctx.lineWidth = 0.7;
                        ctx.beginPath();
                        ctx.moveTo(nodes[i]._px, nodes[i]._py);
                        ctx.lineTo(nodes[j]._px, nodes[j]._py);
                        ctx.stroke();
                    }
                }
            }
            for (const node of nodes) {
                if (!node.active || !node._px) continue;
                const pulse = 0.5 + 0.5 * Math.sin(node.pulsePhase * 2);
                ctx.beginPath();
                ctx.arc(node._px, node._py, 1.5 + pulse * 1.2, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(99,179,237,${0.4 + pulse * 0.35})`;
                ctx.fill();

                // Glow
                const g = ctx.createRadialGradient(node._px, node._py, 0, node._px, node._py, 8);
                g.addColorStop(0, `rgba(99,179,237,${0.15 * pulse})`);
                g.addColorStop(1, "transparent");
                ctx.fillStyle = g;
                ctx.beginPath();
                ctx.arc(node._px, node._py, 8, 0, Math.PI * 2);
                ctx.fill();
            }

            // Stars / particles
            for (const p of particles) {
                p.x += p.speed;
                if (p.x > 1) { p.x = 0; p.y = rand(0, 1); }
                p.phase += p.twinkleSpeed;
                const twinkle = 0.5 + 0.5 * Math.sin(p.phase);
                const alpha = p.opacity * (0.4 + twinkle * 0.6);
                ctx.beginPath();
                ctx.arc(p.x * W, p.y * H, p.r, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(200,220,255,${alpha})`;
                ctx.fill();
            }

            // Vertical scan line
            const scanX = ((t * 0.4) % (W + 120)) - 60;
            const scanGrad = ctx.createLinearGradient(scanX - 40, 0, scanX + 40, 0);
            scanGrad.addColorStop(0, "transparent");
            scanGrad.addColorStop(0.5, "rgba(99,179,237,0.04)");
            scanGrad.addColorStop(1, "transparent");
            ctx.fillStyle = scanGrad;
            ctx.fillRect(scanX - 40, 0, 80, H);

            raf = requestAnimationFrame(draw);
        }

        draw();
        return () => {
            cancelAnimationFrame(raf);
            window.removeEventListener("resize", resize);
        };
    }, []);

    return (
        <canvas
            ref={canvasRef}
            className="fixed inset-0 z-0 pointer-events-none"
            style={{ display: "block" }}
        />
    );
}
