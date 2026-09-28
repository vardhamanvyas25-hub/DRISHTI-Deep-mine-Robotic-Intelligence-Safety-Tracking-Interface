// DRISHTI 6WD Rover Command Center - Core Frontend Engine

let socket = null;
let gasChart = null;
let currentX = 0;
let currentY = 0;
let lastSentX = 0;
let lastSentY = 0;
let driveInterval = null;
let httpFallbackInterval = null;
let isSocketConnected = false;

// 1. Initialize Chart.js
function initGasChart() {
    const canvas = document.getElementById('gasChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const ctx = canvas.getContext('2d');
    gasChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Methane (MQ-4 ADC)',
                    data: [],
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.12)',
                    borderWidth: 2,
                    tension: 0.35,
                    fill: true,
                    pointRadius: 1
                },
                {
                    label: 'Carbon Monoxide (MQ-7 ADC)',
                    data: [],
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.12)',
                    borderWidth: 2,
                    tension: 0.35,
                    fill: true,
                    pointRadius: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 200 },
            scales: {
                x: {
                    display: false
                },
                y: {
                    min: 0,
                    suggestedMax: 2500,
                    grid: { color: 'rgba(255, 255, 255, 0.06)' },
                    ticks: { color: '#94a3b8', font: { family: 'Share Tech Mono', size: 10 } }
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

// 2. Initialize WebSocket & Fallback HTTP
function initCommunication() {
    if (typeof io !== 'undefined') {
        try {
            socket = io();

            socket.on('connect', () => {
                isSocketConnected = true;
                console.log("[SOCKET] Connected to Command Server");
                if (httpFallbackInterval) {
                    clearInterval(httpFallbackInterval);
                    httpFallbackInterval = null;
                }
            });

            socket.on('disconnect', () => {
                isSocketConnected = false;
                console.warn("[SOCKET] Disconnected, switching to HTTP polling fallback");
                startHttpFallback();
            });

            socket.on('telemetry_data', (data) => {
                updateDashboard(data);
            });
        } catch (e) {
            console.warn("[SOCKET] Failed to initialize io, using HTTP fallback:", e);
            startHttpFallback();
        }
    } else {
        startHttpFallback();
    }
}

function startHttpFallback() {
    if (httpFallbackInterval) return;
    httpFallbackInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/status');
            if (res.ok) {
                const data = await res.json();
                updateDashboard(data);
            }
        } catch (err) {
            console.warn("HTTP Polling error:", err);
        }
    }, 300);
}

// 3. Update Dashboard View Elements
function updateDashboard(payload) {
    if (!payload) return;

    const t = payload.telemetry || payload;
    const hazard = payload.hazard || {};
    const detections = payload.yolo_detections || [];
    const thermal = payload.thermal_stats || {};
    const motors = payload.motors || {};

    // --- Connection & COM Port Status ---
    const linkDot = document.getElementById('link-dot');
    const linkText = document.getElementById('link-status-text');
    const hwBanner = document.getElementById('hw-alert-banner');
    const hwAlertText = document.getElementById('hw-alert-text');

    if (t.connected) {
        linkDot.style.background = '#10b981';
        linkDot.style.boxShadow = '0 0 10px #10b981';
        linkText.textContent = `ESP32 HARDWARE LINKED (${t.port || 'COM3'})`;
        linkText.style.color = '#10b981';
        if (hwBanner) hwBanner.style.display = 'none';
    } else if (t.port_status === 'BUSY_LOCKED') {
        linkDot.style.background = '#f59e0b';
        linkDot.style.boxShadow = '0 0 10px #f59e0b';
        linkText.textContent = `COM3 BUSY (SIMULATION ACTIVE)`;
        linkText.style.color = '#f59e0b';
        if (hwBanner) {
            hwBanner.style.display = 'flex';
            if (t.status_message) hwAlertText.textContent = t.status_message;
        }
    } else {
        linkDot.style.background = '#00f2fe';
        linkDot.style.boxShadow = '0 0 10px #00f2fe';
        linkText.textContent = `SIMULATION ACTIVE (${t.port || 'AUTO'})`;
        linkText.style.color = '#00f2fe';
        if (hwBanner) hwBanner.style.display = 'none';
    }

    // --- Battery Monitor ---
    const battVolts = t.battery_v !== undefined ? t.battery_v : 12.0;
    const battPct = t.battery_pct !== undefined ? t.battery_pct : 85;
    const batFill = document.getElementById('bat-fill');
    const batPctText = document.getElementById('bat-pct-text');
    const batVoltText = document.getElementById('bat-volt-text');
    const valBatteryVolts = document.getElementById('val-battery-volts');
    const valBatterySub = document.getElementById('val-battery-sub');

    if (batFill) batFill.style.width = `${battPct}%`;
    if (batPctText) batPctText.textContent = `${battPct}%`;
    if (batVoltText) batVoltText.textContent = `${battVolts.toFixed(1)}V`;
    if (valBatteryVolts) valBatteryVolts.textContent = battVolts.toFixed(2);
    if (valBatterySub) valBatterySub.textContent = `${battPct}%`;

    // Color shift based on battery
    const batColor = battVolts < 11.0 ? '#ef4444' : (battVolts < 11.6 ? '#f59e0b' : '#10b981');
    if (batFill) batFill.style.background = batColor;
    if (batPctText) batPctText.style.color = batColor;

    // --- Sensor Values ---
    const mq4 = t.mq4_raw !== undefined ? t.mq4_raw : (t.mq4 || 0);
    const mq7 = t.mq7_raw !== undefined ? t.mq7_raw : (t.mq7 || 0);
    const temp = t.temp_c !== undefined ? t.temp_c : (t.temp_dht || 0);
    const hum = t.humidity_pct !== undefined ? t.humidity_pct : (t.hum_dht || 0);
    const press = t.pressure_hpa !== undefined ? t.pressure_hpa : (t.press_bmp || 0);

    const elMq4 = document.getElementById('val-mq4');
    const elMq7 = document.getElementById('val-mq7');
    const elTemp = document.getElementById('val-temp');
    const elHum = document.getElementById('val-humidity');
    const elPress = document.getElementById('val-pressure');
    const elAlt = document.getElementById('val-altitude');

    if (elMq4) elMq4.textContent = mq4;
    if (elMq7) elMq7.textContent = mq7;
    if (elTemp) elTemp.textContent = temp.toFixed(1);
    if (elHum) elHum.textContent = hum.toFixed(1);
    if (elPress) elPress.textContent = press.toFixed(1);

    // Calculate approximate altitude from barometric formula
    if (elAlt && press > 300) {
        const alt = 44330.0 * (1.0 - Math.pow(press / 1013.25, 1.0 / 5.255));
        elAlt.textContent = `${alt.toFixed(1)} m`;
    }

    // Bar fills (0-4095 scale)
    const barMq4 = document.getElementById('bar-mq4');
    const barMq7 = document.getElementById('bar-mq7');
    if (barMq4) barMq4.style.width = `${Math.min(100, (mq4 / 3000) * 100)}%`;
    if (barMq7) barMq7.style.width = `${Math.min(100, (mq7 / 2500) * 100)}%`;

    // Hazard badges on tiles
    const badgeMq4 = document.getElementById('badge-mq4');
    const badgeMq7 = document.getElementById('badge-mq7');
    const tileMq4 = document.getElementById('tile-mq4');
    const tileMq7 = document.getElementById('tile-mq7');

    if (badgeMq4) {
        if (mq4 > 1800) {
            badgeMq4.textContent = 'DANGER';
            badgeMq4.className = 'tile-badge badge-orange';
            if (tileMq4) tileMq4.classList.add('hazard-alert-tile');
        } else if (mq4 > 1100) {
            badgeMq4.textContent = 'WARNING';
            badgeMq4.className = 'tile-badge badge-yellow';
            if (tileMq4) tileMq4.classList.remove('hazard-alert-tile');
        } else {
            badgeMq4.textContent = 'NORMAL';
            badgeMq4.className = 'tile-badge badge-green';
            if (tileMq4) tileMq4.classList.remove('hazard-alert-tile');
        }
    }

    if (badgeMq7) {
        if (mq7 > 1500) {
            badgeMq7.textContent = 'DANGER';
            badgeMq7.className = 'tile-badge badge-orange';
            if (tileMq7) tileMq7.classList.add('hazard-alert-tile');
        } else if (mq7 > 900) {
            badgeMq7.textContent = 'WARNING';
            badgeMq7.className = 'tile-badge badge-yellow';
            if (tileMq7) tileMq7.classList.remove('hazard-alert-tile');
        } else {
            badgeMq7.textContent = 'NORMAL';
            badgeMq7.className = 'tile-badge badge-green';
            if (tileMq7) tileMq7.classList.remove('hazard-alert-tile');
        }
    }

    // Rover Status & Packets
    const elPackets = document.getElementById('val-packets');
    const elAge = document.getElementById('val-age');
    const elRoverState = document.getElementById('val-rover-state');
    if (elPackets) elPackets.textContent = t.packets_received || 0;
    if (elAge) elAge.textContent = `${(t.telemetry_age || 0).toFixed(1)}s`;
    if (elRoverState) elRoverState.textContent = t.rover_state || 'READY';

    // --- Hazard Matrix ---
    const scoreVal = hazard.score !== undefined ? hazard.score : 10;
    const scoreClass = hazard.class || 'SAFE OPERATIONAL';
    const scoreColor = hazard.color || '#10b981';

    const elScore = document.getElementById('hazard-score');
    const elClass = document.getElementById('hazard-class-text');
    const elSub = document.getElementById('hazard-sub-text');
    const circle = document.querySelector('.hazard-score-circle');

    if (elScore) elScore.textContent = scoreVal;
    if (elClass) {
        elClass.textContent = scoreClass;
        elClass.style.color = scoreColor;
    }
    if (circle) {
        circle.style.borderColor = scoreColor;
        circle.style.boxShadow = `0 0 16px ${scoreColor}44`;
        if (elScore) elScore.style.color = scoreColor;
    }
    if (elSub) {
        if (scoreVal >= 70) elSub.textContent = 'CRITICAL: Multiple high-risk environmental thresholds breached!';
        else if (scoreVal >= 40) elSub.textContent = 'ELEVATED: Elevated toxic gas or thermal levels recorded.';
        else elSub.textContent = 'All sensor parameters within baseline safety limits.';
    }

    // --- YOLO Detections List ---
    const detList = document.getElementById('detections-list');
    const detCount = document.getElementById('yolo-count-badge');
    if (detCount) detCount.textContent = `DETECTIONS: ${detections.length}`;

    if (detList) {
        if (detections.length > 0) {
            detList.innerHTML = detections.map(d => `
                <div class="detection-pill">
                    <span>${d.class.toUpperCase()}</span>
                    <span style="color:var(--cyan); font-family:var(--font-mono);">${Math.round(d.confidence * 100)}%</span>
                </div>
            `).join('');
        } else {
            detList.innerHTML = `<div class="empty-detections">No hazards or survivors detected in FOV.</div>`;
        }
    }

    // --- Thermal Camera Stats ---
    const thSpotHud = document.getElementById('thermal-spot-hud');
    const thTag = document.getElementById('thermal-hotspot-tag');
    if (thermal.max_temp !== undefined) {
        if (thSpotHud) {
            thSpotHud.textContent = `MAX: ${thermal.max_temp}°C | AVG: ${thermal.avg_temp}°C | MIN: ${thermal.min_temp}°C`;
        }
        if (thTag) {
            thTag.textContent = `HOTSPOT: ${thermal.max_temp}°C [${thermal.hotspot || 'MID'}]`;
            thTag.className = thermal.max_temp > 45 ? 'badge badge-orange' : 'badge badge-subtle';
        }
    }

    // --- Motor Telemetry ---
    const elLeftSpeed = document.getElementById('drive-left-pct');
    const elRightSpeed = document.getElementById('drive-right-pct');
    const elMotorState = document.getElementById('val-motor-state');
    if (motors.left_speed !== undefined) {
        if (elLeftSpeed) elLeftSpeed.textContent = `${motors.left_speed}%`;
        if (elRightSpeed) elRightSpeed.textContent = `${motors.right_speed}%`;
        if (elMotorState) {
            if (motors.is_estop) elMotorState.textContent = 'E-STOPPED';
            else if (motors.is_stopped) elMotorState.textContent = 'STOPPED';
            else elMotorState.textContent = `DRIVING (${motors.left_speed > 0 ? 'FWD' : 'REV'})`;
        }
    }

    // --- Rolling Gas Chart ---
    if (gasChart) {
        const timeLabel = new Date().toLocaleTimeString();
        if (gasChart.data.labels.length > 24) {
            gasChart.data.labels.shift();
            gasChart.data.datasets[0].data.shift();
            gasChart.data.datasets[1].data.shift();
        }
        gasChart.data.labels.push(timeLabel);
        gasChart.data.datasets[0].data.push(mq4);
        gasChart.data.datasets[1].data.push(mq7);
        gasChart.update();
    }
}

let lastVectorTime = 0;
function sendDriveVector(x, y) {
    currentX = Math.round(x);
    currentY = Math.round(y);
    const now = Date.now();
    const isStopping = (currentX === 0 && currentY === 0);

    // Send immediately on stop (0,0) or every 75ms during movement
    if (isStopping || (now - lastVectorTime >= 75)) {
        lastVectorTime = now;
        if (isSocketConnected && socket) {
            socket.emit('drive_cmd', { x: currentX, y: currentY });
        } else {
            fetch('/api/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ x: currentX, y: currentY })
            }).catch(() => {});
        }
    }
}

function sendDirectionCmd(cmdName, speed = 80) {
    if (isSocketConnected && socket) {
        socket.emit('command', { cmd: cmdName, speed: speed });
    } else {
        fetch('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: cmdName, speed: speed })
        }).catch(() => {});
    }
}

function triggerEmergencyStop() {
    if (isSocketConnected && socket) {
        socket.emit('e_stop');
    } else {
        fetch('/api/stop', { method: 'POST' }).catch(() => {});
    }
    const btn = document.getElementById('estop-btn');
    if (btn) {
        btn.style.transform = 'scale(0.92)';
        setTimeout(() => btn.style.transform = 'scale(1)', 150);
    }
}

// 5. Virtual Joystick Setup
function setupJoystick() {
    const zone = document.getElementById('joystick-zone');
    if (!zone) return;

    if (typeof nipplejs !== 'undefined') {
        try {
            const manager = nipplejs.create({
                zone: zone,
                mode: 'static',
                position: { left: '50%', top: '50%' },
                color: '#00f2fe',
                size: 90
            });

            manager.on('move', (evt, data) => {
                if (data.direction) {
                    const speed = Math.min(data.distance * 2.2, 100);
                    const rad = data.angle.radian;
                    const x = Math.cos(rad) * speed;
                    const y = Math.sin(rad) * speed;
                    sendDriveVector(x, y);
                }
            });

            manager.on('end', () => {
                sendDriveVector(0, 0);
            });
            return;
        } catch (e) {
            console.warn("NippleJS error, using pointer fallback", e);
        }
    }

    // Native pointer fallback if NippleJS fails
    let isDragging = false;
    zone.addEventListener('pointerdown', (e) => {
        isDragging = true;
        zone.setPointerCapture(e.pointerId);
    });

    zone.addEventListener('pointermove', (e) => {
        if (!isDragging) return;
        const rect = zone.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        let dx = (e.clientX - cx) / (rect.width / 2);
        let dy = -(e.clientY - cy) / (rect.height / 2);
        dx = Math.max(-1, Math.min(1, dx));
        dy = Math.max(-1, Math.min(1, dy));
        sendDriveVector(dx * 90, dy * 90);
    });

    const stopDrag = () => {
        if (isDragging) {
            isDragging = false;
            sendDriveVector(0, 0);
        }
    };
    zone.addEventListener('pointerup', stopDrag);
    zone.addEventListener('pointercancel', stopDrag);
}

// 6. Keyboard Control Handlers
const activeKeys = {};

window.addEventListener('keydown', (e) => {
    if (e.repeat) return;
    const k = e.key.toLowerCase();

    if (['w', 'a', 's', 'd', ' ', 'arrowup', 'arrowleft', 'arrowdown', 'arrowright'].includes(k)) {
        e.preventDefault();
        activeKeys[k] = true;
        handleKeyMovement();
    }
});

window.addEventListener('keyup', (e) => {
    const k = e.key.toLowerCase();
    if (['w', 'a', 's', 'd', ' ', 'arrowup', 'arrowleft', 'arrowdown', 'arrowright'].includes(k)) {
        e.preventDefault();
        delete activeKeys[k];
        handleKeyMovement();
    }
});

function handleKeyMovement() {
    let x = 0;
    let y = 0;

    // Reset button states
    ['key-w', 'key-a', 'key-s', 'key-d', 'key-space', 'btn-up', 'btn-down', 'btn-left', 'btn-right', 'btn-stop-center'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.remove('key-pressed');
    });

    if (activeKeys[' '] || activeKeys['space']) {
        triggerEmergencyStop();
        highlightKey('key-space');
        highlightKey('btn-stop-center');
        return;
    }

    if (activeKeys['w'] || activeKeys['arrowup']) {
        y += 85;
        highlightKey('key-w');
        highlightKey('btn-up');
    }
    if (activeKeys['s'] || activeKeys['arrowdown']) {
        y -= 85;
        highlightKey('key-s');
        highlightKey('btn-down');
    }
    if (activeKeys['a'] || activeKeys['arrowleft']) {
        x -= 75;
        highlightKey('key-a');
        highlightKey('btn-left');
    }
    if (activeKeys['d'] || activeKeys['arrowright']) {
        x += 75;
        highlightKey('key-d');
        highlightKey('btn-right');
    }

    sendDriveVector(x, y);
}

function highlightKey(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('key-pressed');
}

// 7. Serial Port Selector
async function loadAvailablePorts() {
    try {
        const res = await fetch('/api/ports');
        if (!res.ok) return;
        const data = await res.json();
        const select = document.getElementById('com-port-select');
        if (!select) return;

        const currentVal = select.value;
        select.innerHTML = '<option value="AUTO">AUTO (Scanning)</option>';

        if (data.available_ports && data.available_ports.length > 0) {
            data.available_ports.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.device;
                opt.textContent = `${p.device} (${p.description || 'Serial'})`;
                select.appendChild(opt);
            });
        }

        if (data.active_port) {
            select.value = data.active_port;
        } else if (currentVal) {
            select.value = currentVal;
        }
    } catch (e) {
        console.warn("Could not load serial ports:", e);
    }
}

async function selectPort(portName) {
    try {
        await fetch('/api/select-port', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ port: portName })
        });
        console.log(`[PORT] Switched port target to: ${portName}`);
    } catch (e) {
        console.error("Error setting port:", e);
    }
}

// 8. Colormap Switcher
async function setColormap(mode) {
    document.querySelectorAll('.cmap-btn').forEach(btn => btn.classList.remove('active'));
    const activeBtn = document.getElementById(mode === 'INFERNO' ? 'btn-inferno' : 'btn-jet');
    if (activeBtn) activeBtn.classList.add('active');

    try {
        await fetch('/api/colormap', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        });
    } catch (e) {
        console.warn("Colormap change error:", e);
    }
}

// 9. Fullscreen Toggle
function toggleFullscreen(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;
    if (!document.fullscreenElement) {
        el.requestFullscreen().catch(err => {
            console.warn(`Fullscreen error: ${err.message}`);
        });
    } else {
        document.exitFullscreen();
    }
}

// 10. Bootstrap Everything on Page Load
document.addEventListener('DOMContentLoaded', () => {
    initGasChart();
    initCommunication();
    setupJoystick();
    loadAvailablePorts();

    // Attach Event Listeners
    const estopBtn = document.getElementById('estop-btn');
    if (estopBtn) estopBtn.addEventListener('click', triggerEmergencyStop);

    const portSelect = document.getElementById('com-port-select');
    if (portSelect) {
        portSelect.addEventListener('change', (e) => {
            selectPort(e.target.value);
        });
    }

    const refreshBtn = document.getElementById('btn-refresh-ports');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            loadAvailablePorts();
        });
    }
});