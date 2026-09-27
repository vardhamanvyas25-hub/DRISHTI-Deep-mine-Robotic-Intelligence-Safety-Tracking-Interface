async function sendCmd(commandName) {
    try {
        await fetch('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: commandName })
        });
    } catch (err) {
        console.error("Control Command Error:", err);
    }
}

async function fetchStatus() {
    try {
        const response = await fetch('/api/status');
        if (!response.ok) return;
        const data = await response.json();
        
        // Render Telemetry
        if (data.telemetry) {
            const t = data.telemetry;
            document.getElementById('val-mq4').innerText = `${t.methane} %`;
            document.getElementById('val-mq7').innerText = `${t.co} PPM`;
            document.getElementById('val-dht').innerText = `${t.temp}°C / ${t.humidity}%`;
            document.getElementById('val-bmp').innerText = `${t.pressure} hPa`;
            document.getElementById('val-mic').innerText = `${t.noise} dB`;
            document.getElementById('val-volt').innerText = `${t.voltage} V`;
            document.getElementById('bat-val').innerText = `${t.battery}%`;
        }

        // Render Hazard Class
        if (data.hazard) {
            const scoreEl = document.getElementById('hazard-score');
            const classEl = document.getElementById('hazard-class');
            scoreEl.innerText = data.hazard.score;
            classEl.innerText = data.hazard.class;

            if (data.hazard.score >= 70) {
                scoreEl.style.color = "var(--accent-red)";
                classEl.style.color = "var(--accent-red)";
            } else if (data.hazard.score >= 40) {
                scoreEl.style.color = "var(--accent-orange)";
                classEl.style.color = "var(--accent-orange)";
            } else {
                scoreEl.style.color = "var(--accent-green)";
                classEl.style.color = "var(--accent-green)";
            }
        }

        // Render YOLO Detections
        const listEl = document.getElementById('detection-list');
        if (data.yolo_detections && data.yolo_detections.length > 0) {
            listEl.innerHTML = data.yolo_detections.map(d => `
                <div class="detection-item">
                    <span>${d.class.toUpperCase()}</span>
                    <span style="color:var(--accent-cyan);">${Math.round(d.confidence * 100)}%</span>
                </div>
            `).join('');
        } else {
            listEl.innerHTML = `<div style="font-size:0.75rem; color:var(--text-muted); text-align:center; padding-top:10px;">No targets detected</div>`;
        }

    } catch (err) {
        console.warn("Telemetry Polling Error:", err);
    }
}

// Arrow Key Driver Bindings
window.addEventListener('keydown', (e) => {
    if (e.repeat) return;
    if (e.key === 'ArrowUp') { sendCmd('FORWARD'); flashBtn('btn-up'); }
    else if (e.key === 'ArrowDown') { sendCmd('BACKWARD'); flashBtn('btn-down'); }
    else if (e.key === 'ArrowLeft') { sendCmd('LEFT'); flashBtn('btn-left'); }
    else if (e.key === 'ArrowRight') { sendCmd('RIGHT'); flashBtn('btn-right'); }
    else if (e.key === ' ') { sendCmd('STOP'); flashBtn('btn-stop-center'); }
});

function flashBtn(id) {
    const btn = document.getElementById(id);
    if (btn) {
        btn.classList.add('active');
        setTimeout(() => btn.classList.remove('active'), 200);
    }
}

// Poll telemetry every 400ms
setInterval(fetchStatus, 400);
fetchStatus();