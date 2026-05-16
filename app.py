import os
import io
import time
import threading
import requests
from flask import Flask, request, jsonify, render_template_string, send_file
from flask_cors import CORS
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
app = Flask(__name__)
CORS(app)
 
# Configurable thermal stream URL (set in Railway → Variables).
# Leave empty to show the placeholder; set to a public HTTPS MJPEG URL
# (e.g. Cloudflare Tunnel) when streaming is live.
STREAM_URL = os.environ.get("STREAM_URL", "")
 
# =============================================================================
# Telegram Alert Configuration
# =============================================================================
# Set these via Railway environment variables for safety. Falls back to inline
# placeholders if env vars are missing (replace these for local testing only).
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8794551563:AAGamUQsdlFB0WXKD9yVDtWJXZgqSPIdzvY")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "1188970668")
ALERT_TEMP_THRESHOLD = 50.0       # °C
ALERT_COOLDOWN_SEC   = 300        # 5 minutes between alerts
_last_alert_ts = 0.0
_alert_lock = threading.Lock()
def send_telegram_alert(temp_object, temp_air, humidity, pressure):
    """Send a Telegram message when surface heat exceeds threshold."""
    global _last_alert_ts
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("REPLACE"):
        print("[Telegram] Token not configured; skipping alert.")
        return False
    with _alert_lock:
        now = time.time()
        if now - _last_alert_ts < ALERT_COOLDOWN_SEC:
            return False
        _last_alert_ts = now
    msg = (
        "⚠️ *Solar Panel Alert*\n\n"
        f"🔥 Surface Temp: *{temp_object:.2f} °C*\n"
        f"🌡️ Air Temp: {temp_air:.2f} °C\n"
        f"💧 Humidity: {humidity:.1f} %\n"
        f"🔵 Pressure: {pressure:.2f} hPa\n"
        f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Threshold: {ALERT_TEMP_THRESHOLD} °C exceeded — inspect panel A-001."
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown"
        }, timeout=8)
        ok = r.status_code == 200
        print(f"[Telegram] Alert sent: {ok}")
        return ok
    except Exception as e:
        print(f"[Telegram] Failed: {e}")
        return False
# =============================================================================
# Sensor State
# =============================================================================
latest_data = {
    "temp_bme": 0.0,
    "humidity": 0.0,
    "pressure": 0.0,
    "temp_object": 0.0,
    "temp_ambient": 0.0,
    "timestamp": "No data yet"
}
HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Drone IoT Solar Monitor</title>
<style>*{margin:0;padding:0;box-sizing:border-box}html{scroll-behavior:smooth}body{font-family:'Segoe UI',sans-serif;background:#f8fafc}.nav{background:#fff;padding:12px 24px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e2e8f0;position:sticky;top:0;z-index:100}.nav-title{font-size:14px;font-weight:600;color:#1e293b}.live{display:flex;align-items:center;gap:5px;font-size:10px;color:#16a34a;background:#f0fdf4;padding:4px 10px;border-radius:20px;border:1px solid #bbf7d0}.dot{width:6px;height:6px;background:#22c55e;border-radius:50%;animation:blink 1.4s infinite}@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}.hero{position:relative;height:350px;overflow:hidden;background:#020c1e}.hero canvas{position:absolute;inset:0;width:100%;height:100%}.hero-text{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:20px}.hero-badge{display:inline-flex;align-items:center;gap:6px;background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.3);border-radius:20px;padding:4px 14px;font-size:10px;color:#4ade80;margin-bottom:14px}.hero-h1{font-size:28px;font-weight:700;color:#fff;line-height:1.2;margin-bottom:8px}.accent{background:linear-gradient(90deg,#38bdf8,#34d399);-webkit-background-clip:text;-webkit-text-fill-color:transparent}.hero-p{font-size:12px;color:rgba(255,255,255,.5);max-width:380px;line-height:1.7;margin-bottom:18px}.btns{display:flex;gap:10px}.btn-a{background:linear-gradient(135deg,#2563eb,#0ea5e9);color:#fff;border:none;padding:10px 22px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:6px}.btn-a:hover{filter:brightness(1.1)}.btn-b{background:rgba(255,255,255,.1);color:#fff;border:1px solid rgba(255,255,255,.2);padding:10px 22px;border-radius:8px;font-size:12px;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:6px}.btn-b:hover{background:rgba(255,255,255,.18)}.hud-l{position:absolute;top:16px;left:16px;display:flex;flex-direction:column;gap:7px}.hud-r{position:absolute;top:16px;right:16px;display:flex;flex-direction:column;gap:7px;align-items:flex-end}.hcard{background:rgba(2,12,30,.85);border:1px solid rgba(37,99,235,.3);border-radius:10px;padding:8px 13px;min-width:120px;backdrop-filter:blur(8px)}.hc-lbl{font-size:9px;color:#475569;font-weight:600;letter-spacing:.5px;text-transform:uppercase;margin-bottom:3px}.hc-val{font-size:20px;font-weight:700;line-height:1}.hc-unit{font-size:9px;color:#1e3a5f;margin-top:1px}.hbar{height:2px;background:#0a1830;border-radius:1px;margin-top:6px;overflow:hidden}.hbf{height:100%;border-radius:1px;transition:width .6s}.c1{color:#60a5fa}.c2{color:#2dd4bf}.c3{color:#fbbf24}.c4{color:#f87171}.f1{background:linear-gradient(90deg,#2563eb,#60a5fa)}.f2{background:linear-gradient(90deg,#0d9488,#2dd4bf)}.f3{background:linear-gradient(90deg,#d97706,#fbbf24)}.f4{background:linear-gradient(90deg,#dc2626,#f87171)}.f5{background:linear-gradient(90deg,#16a34a,#4ade80)}.stats{display:grid;grid-template-columns:repeat(2,1fr);background:#fff;border-bottom:1px solid #e2e8f0}.stat{padding:16px 20px;border-left:1px solid #e2e8f0;display:flex;align-items:center;gap:12px}.stat:last-child{border-left:none}.si{width:42px;height:42px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0}.si1{background:#eff6ff}.si2{background:#fff1f2}.si3{background:#fffbeb}.si4{background:#f0fdf4}.st-lbl{font-size:10px;color:#94a3b8;margin-bottom:3px;font-weight:500}.st-val{font-size:22px;font-weight:700;line-height:1}.st-sub{font-size:9px;color:#cbd5e1;margin-top:2px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:14px}.card{background:#fff;border-radius:12px;padding:16px;border:1px solid #e2e8f0}.card-full{grid-column:span 2}.card-title{font-size:12px;font-weight:600;color:#1e293b;margin-bottom:12px;display:flex;align-items:center;gap:6px;justify-content:space-between}.title-l{display:flex;align-items:center;gap:6px}.title-bar{width:3px;height:14px;border-radius:2px;background:linear-gradient(#2563eb,#38bdf8);flex-shrink:0}.live-chip{display:inline-flex;align-items:center;gap:5px;background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;border-radius:20px;padding:2px 8px;font-size:9px;font-weight:700;letter-spacing:.3px}.demo-chip{display:inline-flex;align-items:center;gap:5px;background:#f1f5f9;color:#64748b;border:1px solid #cbd5e1;border-radius:20px;padding:2px 8px;font-size:9px;font-weight:700;letter-spacing:.3px}.sen-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.sc{border-radius:10px;padding:12px;position:relative;overflow:hidden}.sc::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}.sc1{background:#f8faff}.sc1::before{background:linear-gradient(90deg,#2563eb,#60a5fa)}.sc2{background:#f0fdf9}.sc2::before{background:linear-gradient(90deg,#0d9488,#2dd4bf)}.sc3{background:#fffdf0}.sc3::before{background:linear-gradient(90deg,#d97706,#fbbf24)}.sc4{background:#fff8f8}.sc4::before{background:linear-gradient(90deg,#dc2626,#f87171)}.sc5{background:#f0fdf4}.sc5::before{background:linear-gradient(90deg,#16a34a,#4ade80)}.sc-lbl{font-size:9px;color:#94a3b8;font-weight:600;text-transform:uppercase;letter-spacing:.4px;margin-bottom:5px}.sc-val{font-size:24px;font-weight:700;line-height:1}.sc-unit{font-size:9px;color:#cbd5e1;margin-top:2px}.sc-bar{height:3px;background:#e2e8f0;border-radius:2px;margin-top:8px;overflow:hidden}.sc-fill{height:100%;border-radius:2px;transition:width .6s}.pmap{display:grid;grid-template-columns:repeat(13,1fr);gap:4px;margin:10px 0}.pc{height:18px;border-radius:4px;cursor:pointer;transition:transform .15s;position:relative}.pc:hover{transform:scale(1.3);z-index:5}.ok{background:#22c55e}.warn{background:#f97316}.crit{background:#ef4444;animation:pr 2s infinite}.pc.demo{opacity:.55}.pc.live-cell{outline:2.5px solid #16a34a;outline-offset:2px;box-shadow:0 0 14px rgba(34,197,94,.85),0 0 4px rgba(34,197,94,.6) inset;animation:livePulse 1.6s infinite;z-index:3}@keyframes livePulse{0%,100%{box-shadow:0 0 14px rgba(34,197,94,.85),0 0 4px rgba(34,197,94,.6) inset}50%{box-shadow:0 0 22px rgba(34,197,94,1),0 0 6px rgba(34,197,94,.8) inset}}@keyframes pr{0%,100%{opacity:1}50%{opacity:.6}}.legend{display:flex;gap:14px;font-size:10px;color:#64748b;flex-wrap:wrap;margin-top:10px}.ld{width:10px;height:10px;border-radius:3px;display:inline-block;margin-right:4px;vertical-align:middle}.ld.live{outline:1.5px solid #16a34a;outline-offset:1px;background:#22c55e}.notice{background:linear-gradient(90deg,#f0fdf4,#ecfdf5);border:1px solid #bbf7d0;border-radius:8px;padding:10px 12px;margin-top:10px;display:flex;align-items:center;gap:10px;font-size:10.5px;color:#166534;line-height:1.5}.notice-i{width:22px;height:22px;background:#dcfce7;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:11px}table{width:100%;border-collapse:collapse;font-size:11px}th{padding:9px 14px;text-align:left;color:#94a3b8;font-weight:600;font-size:10px;text-transform:uppercase;background:#f8fafc;border-bottom:1px solid #e2e8f0}td{padding:9px 14px;border-bottom:1px solid #f8fafc;color:#334155}tr:hover td{background:#f8fafc}tr.live-row td{background:#f0fdf4!important;font-weight:600}tr.live-row td:first-child{position:relative}tr.live-row td:first-child::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:#16a34a}.badge{padding:3px 10px;border-radius:20px;font-size:10px;font-weight:600}.bok{background:#dcfce7;color:#15803d}.bwarn{background:#ffedd5;color:#c2410c}.bcrit{background:#fee2e2;color:#b91c1c}.live-tag{background:#16a34a;color:#fff;padding:2px 7px;border-radius:10px;font-size:8.5px;font-weight:700;margin-left:6px;letter-spacing:.4px}.demo-tag{background:#e2e8f0;color:#64748b;padding:2px 7px;border-radius:10px;font-size:8.5px;font-weight:700;margin-left:6px;letter-spacing:.4px}.tcam{background:linear-gradient(135deg,#0f172a,#1e293b);color:#fff;border-radius:12px;padding:18px;margin:0 14px 14px;border:1px solid #334155;display:grid;grid-template-columns:200px 1fr;gap:18px;align-items:center}.tcam-img{aspect-ratio:4/3;background:radial-gradient(ellipse at center,#7c2d12 0%,#1e1b4b 60%,#020617 100%);border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:42px;border:1px solid #334155;position:relative;overflow:hidden}.tcam-img::after{content:'';position:absolute;inset:0;background:repeating-linear-gradient(0deg,rgba(255,255,255,.04) 0,rgba(255,255,255,.04) 1px,transparent 1px,transparent 4px);pointer-events:none}.tcam-img img{width:100%;height:100%;object-fit:cover;border-radius:8px;display:block;position:relative;z-index:1}.tcam-h{font-size:14px;font-weight:700;margin-bottom:4px;display:flex;align-items:center;gap:8px}.tcam-status{display:inline-flex;align-items:center;gap:5px;background:rgba(251,146,60,.15);color:#fb923c;border:1px solid rgba(251,146,60,.3);border-radius:20px;padding:2px 8px;font-size:9.5px;font-weight:700}.tcam-status.live{background:rgba(34,197,94,.15);color:#4ade80;border-color:rgba(34,197,94,.35)}.tcam-status.offline{background:rgba(239,68,68,.15);color:#f87171;border-color:rgba(239,68,68,.35)}.tcam-p{font-size:11px;color:#94a3b8;line-height:1.6;margin-bottom:8px}.tcam-list{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}.tcam-tag{background:rgba(56,189,248,.1);color:#7dd3fc;border:1px solid rgba(56,189,248,.25);font-size:9.5px;padding:3px 9px;border-radius:5px}.footer{background:#fff;padding:10px 24px;border-top:1px solid #e2e8f0;display:flex;align-items:center;gap:8px}.fd{width:6px;height:6px;background:#22c55e;border-radius:50%;animation:blink 1.4s infinite}.ft{font-size:10px;color:#94a3b8}.fr{margin-left:auto;font-size:10px;color:#cbd5e1}.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%) translateY(80px);background:#16a34a;color:#fff;padding:10px 18px;border-radius:8px;font-size:12px;font-weight:600;box-shadow:0 8px 24px rgba(0,0,0,.18);transition:transform .35s;z-index:200;pointer-events:none}.toast.show{transform:translateX(-50%) translateY(0)}</style></head>
<body>
<div class="nav"><div style="display:flex;align-items:center;gap:8px"><div style="width:32px;height:32px;background:linear-gradient(135deg,#2563eb,#0ea5e9);border-radius:8px;display:flex;align-items:center;justify-content:center"><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M3 9l4-4 5 3 5-3 4 4-3 5 3 5-4 4-5-3-5 3-4-4 3-5z" stroke="#fff" stroke-width="1.8" fill="none"/><circle cx="12" cy="14" r="2.5" fill="#fff"/></svg></div><div><div class="nav-title">Drone IoT · Solar Monitor</div><div style="font-size:10px;color:#94a3b8">Advanced Thermal Detection System</div></div></div><div class="live"><div class="dot"></div>Live Feed Active</div><div style="font-size:11px;color:#94a3b8" id="clock">--:--:--</div></div>
<div class="hero">
<canvas id="cv"></canvas>
<div class="hud-l"><div class="hcard"><div class="hc-lbl">Air Temperature</div><div class="hc-val c1" id="h1">--</div><div class="hc-unit">°C</div><div class="hbar"><div class="hbf f1" id="hb1" style="width:0%"></div></div></div></div>
<div class="hud-r"><div class="hcard" style="text-align:right"><div class="hc-lbl">Surface Temp</div><div class="hc-val c4" id="h3">--</div><div class="hc-unit">°C</div><div class="hbar"><div class="hbf f4" id="hb3" style="width:0%"></div></div></div><div class="hcard" style="text-align:right"><div class="hc-lbl">Pressure</div><div class="hc-val c3" id="h4">--</div><div class="hc-unit">hPa</div><div class="hbar"><div class="hbf f3" id="hb4" style="width:80%"></div></div></div></div>
<div class="hero-text"><div class="hero-badge"><div class="dot"></div>Live Drone Surveillance</div><div class="hero-h1">Drone + IoT<br><span class="accent">Solar Panel Monitoring</span></div><div class="hero-p">Advanced thermal monitoring with live hotspot detection. Real-time drone surveillance combined with IoT sensors.</div><div class="btns"><a class="btn-a" href="#dashboard">↓ View Live Dashboard</a><a class="btn-b" href="/api/report.pdf" target="_blank" rel="noopener">⚡ Thermal Reports</a></div></div>
</div>
<div class="stats"><div class="stat"><div class="si si1">⚡</div><div><div class="st-lbl">Total Panels</div><div class="st-val" style="color:#2563eb">125</div><div class="st-sub"><span style="color:#16a34a;font-weight:700">1 Live</span> · <span style="color:#94a3b8">124 Demo</span></div></div></div><div class="stat"><div class="si si2">⚠️</div><div><div class="st-lbl">Critical Alerts</div><div class="st-val" style="color:#dc2626" id="nalerts">--</div><div class="st-sub">Need inspection</div></div></div></div>
<div class="grid" id="dashboard">
<div class="card"><div class="card-title"><div class="title-l"><div class="title-bar"></div>Live Sensor Readings</div><span class="live-chip"><span class="dot"></span>ESP32 LIVE</span></div><div class="sen-grid"><div class="sc sc1"><div class="sc-lbl">🌡️ Air Temp</div><div class="sc-val" style="color:#2563eb" id="s1">--</div><div class="sc-unit">°C</div><div class="sc-bar"><div class="sc-fill f1" id="sb1" style="width:0%"></div></div></div><div class="sc sc3"><div class="sc-lbl">🔵 Pressure</div><div class="sc-val" style="color:#d97706" id="s3">--</div><div class="sc-unit">hPa</div><div class="sc-bar"><div class="sc-fill f3" style="width:80%"></div></div></div><div class="sc sc4"><div class="sc-lbl">🔥 Surface Temp</div><div class="sc-val" style="color:#dc2626" id="s4">--</div><div class="sc-unit">°C</div><div class="sc-bar"><div class="sc-fill f4" id="sb4" style="width:0%"></div></div></div><div class="sc sc5"><div class="sc-lbl">📡 Ambient Temperature</div><div class="sc-val" style="color:#16a34a" id="s5">--</div><div class="sc-unit">°C</div><div class="sc-bar"><div class="sc-fill f5" style="width:60%"></div></div></div></div></div>
<div class="card"><div class="card-title"><div class="title-l"><div class="title-bar"></div>Interactive Panel Map</div><span style="font-size:9.5px;color:#94a3b8">A-001 = <span style="color:#16a34a;font-weight:700">LIVE</span></span></div><div class="pmap" id="pmap"></div><div class="legend"><span><span class="ld live"></span>Live Sensor</span><span><span class="ld" style="background:#22c55e"></span>Optimal</span><span><span class="ld" style="background:#f97316"></span>Monitor</span><span><span class="ld" style="background:#ef4444"></span>Critical</span><span style="color:#94a3b8;margin-left:auto">Demo panels @ 55% opacity</span></div><div class="notice"><div class="notice-i">ℹ</div><div><strong>Hybrid Demo Mode:</strong> Panel <strong style="color:#16a34a">A-001</strong> shows real-time data from the connected ESP32 sensor. The remaining 124 panels are simulated to demonstrate the system's scalability across a full solar farm deployment.</div></div></div>
<div class="card card-full"><div class="card-title"><div class="title-l"><div class="title-bar"></div>Panel Status Table</div><span style="display:flex;gap:10px;align-items:center"><span style="font-size:9.5px;color:#94a3b8">Top results · Live row highlighted</span><a href="/api/report.pdf" target="_blank" rel="noopener" style="font-size:10px;background:#0f172a;color:#fff;padding:5px 12px;border-radius:6px;text-decoration:none;font-weight:600">⬇ Export PDF</a></span></div><table><thead><tr><th>Panel ID</th><th>T_min °C</th><th>T_max °C</th><th>ΔT °C</th><th>Status</th><th>Source</th><th>Recommendation</th></tr></thead><tbody id="tbody"></tbody></table></div>
</div>
<div class="tcam"><div class="tcam-img" id="thermalImgWrap"><img id="thermalStream" alt="TC001 Live Thermal Stream" style="display:none"><span id="thermalPlaceholder" style="position:relative;z-index:1">📷</span></div><div><div class="tcam-h">TC001 Thermal Camera <span class="tcam-status" id="thermalStatus"><span id="thermalStatusDot" style="width:6px;height:6px;border-radius:50%;background:#fb923c"></span><span id="thermalStatusText">Pending STREAM_URL</span></span></div><div class="tcam-p" id="thermalText">High-resolution thermal imaging will stream here once the TC001 camera is connected via Raspberry Pi. Live video, hotspot detection overlays, and recording controls will replace this placeholder.</div><div class="tcam-list"><span class="tcam-tag">256×192 Resolution</span><span class="tcam-tag">-20°C → 550°C Range</span><span class="tcam-tag">25Hz Refresh</span><span class="tcam-tag">USB-C → Raspberry Pi</span></div></div></div>
<div class="footer"><div class="fd"></div><div class="ft">Connected · Updates every 3s · Railway Cloud · ESP32 WiFi</div><div class="fr">Telegram alerts active · PDF reports ready</div></div>
<div class="toast" id="toast">Saved</div>
<script>
const cv=document.getElementById('cv'),ctx=cv.getContext('2d');
let T=0;
function rsz(){cv.width=cv.offsetWidth;cv.height=cv.offsetHeight}
rsz();window.addEventListener('resize',rsz);
const stars=Array.from({length:100},()=>({x:Math.random(),y:Math.random(),r:Math.random()*.9+.2,o:Math.random()*.5+.25}));
const pts=[];
function addP(x,y){if(pts.length<80)pts.push({x,y,vx:(Math.random()-.5)*1.5,vy:-Math.random()*.7-.3,life:1,r:1+Math.random()})}
function draw(){
const W=cv.width,H=cv.height;ctx.clearRect(0,0,W,H);
const bg=ctx.createLinearGradient(0,0,W,H);bg.addColorStop(0,'#020c1e');bg.addColorStop(.5,'#041428');bg.addColorStop(1,'#021a0e');ctx.fillStyle=bg;ctx.fillRect(0,0,W,H);
stars.forEach(s=>{ctx.beginPath();ctx.arc(s.x*W,s.y*H*.7,s.r,0,Math.PI*2);ctx.fillStyle=`rgba(180,210,255,${s.o+Math.sin(T*1.5+s.x*10)*.07})`;ctx.fill();});
ctx.save();ctx.globalAlpha=.15;
for(let r=0;r<5;r++)for(let c=0;c<10;c++){const px=W*.02+c*(W*.095),py=H*.72+r*26;const grd=ctx.createLinearGradient(px,py,px,py+20);grd.addColorStop(0,'#fbbf24');grd.addColorStop(1,'#1d4e8f');ctx.fillStyle=grd;ctx.beginPath();ctx.roundRect(px,py,W*.082,20,2);ctx.fill();ctx.strokeStyle='#0a2040';ctx.lineWidth=.5;ctx.stroke();}
ctx.restore();
ctx.save();ctx.globalAlpha=.09;ctx.strokeStyle='#1a5fd4';ctx.lineWidth=.5;
const gY=H*.68;for(let i=-14;i<=14;i++){ctx.beginPath();ctx.moveTo(W/2+i*36-(T*10%36),gY);ctx.lineTo(W/2+i*240,H+20);ctx.stroke();}
for(let j=0;j<7;j++){const p=j/6;ctx.beginPath();ctx.moveTo(W/2-p*220,gY+p*(H-gY+20));ctx.lineTo(W/2+p*220,gY+p*(H-gY+20));ctx.stroke();}ctx.restore();
const dx=W/2+Math.sin(T*.55)*22,dy=H*.4+Math.sin(T*.42)*13;
ctx.save();ctx.globalAlpha=.06+Math.abs(Math.sin(T*.5))*.05;const bm=ctx.createRadialGradient(dx,dy+16,0,dx,dy+16,150);bm.addColorStop(0,'#ef4444');bm.addColorStop(1,'transparent');ctx.fillStyle=bm;ctx.beginPath();ctx.moveTo(dx,dy+16);ctx.lineTo(dx-55,dy+150);ctx.lineTo(dx+55,dy+150);ctx.closePath();ctx.fill();ctx.restore();
const sg=.38+Math.abs(Math.sin(T*.65))*.32;ctx.save();ctx.globalAlpha=sg;ctx.fillStyle='#fbbf24';ctx.beginPath();ctx.roundRect(dx-74,dy-8,50,14,2);ctx.fill();ctx.beginPath();ctx.roundRect(dx+24,dy-8,50,14,2);ctx.fill();ctx.strokeStyle='#78350f';ctx.lineWidth=.6;for(let i=1;i<4;i++){ctx.beginPath();ctx.moveTo(dx-74+i*12.5,dy-8);ctx.lineTo(dx-74+i*12.5,dy+6);ctx.stroke();ctx.beginPath();ctx.moveTo(dx+24+i*12.5,dy-8);ctx.lineTo(dx+24+i*12.5,dy+6);ctx.stroke();}ctx.restore();
[[-1,-1],[1,-1],[-1,1],[1,1]].forEach(([sx,sy])=>{ctx.strokeStyle='rgba(100,160,255,.3)';ctx.lineWidth=2.5;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(dx,dy);ctx.lineTo(dx+sx*38,dy+sy*22);ctx.stroke();});
[[-38,-22],[38,-22],[-38,22],[38,22]].forEach(([ox,oy],i)=>{const mx=dx+ox,my=dy+oy;ctx.beginPath();ctx.arc(mx,my,7,0,Math.PI*2);ctx.fillStyle='#0a1e38';ctx.fill();ctx.strokeStyle='rgba(96,165,250,.5)';ctx.lineWidth=1;ctx.stroke();ctx.save();ctx.translate(mx,my);ctx.rotate(T*10*(i%2?1:-1));ctx.globalAlpha=.55;ctx.strokeStyle='#93c5fd';ctx.lineWidth=2.5;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-20,0);ctx.lineTo(20,0);ctx.stroke();ctx.beginPath();ctx.moveTo(0,-20);ctx.lineTo(0,20);ctx.stroke();ctx.restore();if(Math.random()<.2)addP(mx+(Math.random()-.5)*32,my+(Math.random()-.5)*32);});
for(let i=pts.length-1;i>=0;i--){const p=pts[i];p.x+=p.vx;p.y+=p.vy;p.life-=.025;if(p.life<=0){pts.splice(i,1);continue;}ctx.beginPath();ctx.arc(p.x,p.y,p.r*p.life,0,Math.PI*2);ctx.fillStyle=`rgba(96,165,250,${p.life*.35})`;ctx.fill();}
ctx.save();ctx.translate(dx,dy);ctx.rotate(Math.sin(T*.28)*.04);ctx.fillStyle='#1e3a6e';ctx.beginPath();ctx.roundRect(-16,-12,32,24,6);ctx.fill();ctx.strokeStyle='rgba(96,165,250,.4)';ctx.lineWidth=1;ctx.stroke();ctx.fillStyle='#060f1e';ctx.beginPath();ctx.arc(0,17,8,0,Math.PI*2);ctx.fill();ctx.strokeStyle='rgba(37,99,235,.6)';ctx.lineWidth=1;ctx.stroke();ctx.fillStyle='#2563eb';ctx.beginPath();ctx.arc(0,17,5,0,Math.PI*2);ctx.fill();ctx.fillStyle='#93c5fd';ctx.beginPath();ctx.arc(0,17,2.5,0,Math.PI*2);ctx.fill();ctx.fillStyle=`rgba(0,255,136,${.55+Math.sin(T*3)*.45})`;ctx.beginPath();ctx.arc(0,-10,2.5,0,Math.PI*2);ctx.fill();ctx.restore();
T+=.016;requestAnimationFrame(draw);}
draw();
// Panel A-001 = LIVE (real ESP32 data). Others = Simulated demo panels.
const panels=Array.from({length:125},(_,i)=>{
  if(i===0){return{id:'A-001',dt:0,tmin:0,tmax:0,hum:0,isLive:true};}
  const dt=+(Math.random()*22+1).toFixed(1);
  const tmin=+(44+Math.random()*10).toFixed(1);
  return{id:`A-${String(i+1).padStart(3,'0')}`,dt,tmin,tmax:+(tmin+dt).toFixed(1),hum:+(35+Math.random()*25).toFixed(1),isLive:false};
});
const pmap=document.getElementById('pmap');
const cellEls=[];
panels.forEach((p,idx)=>{
  const el=document.createElement('div');
  cellEls.push(el);
  if(p.isLive){
    el.className='pc ok live-cell';
    el.title=`${p.id} · LIVE ESP32`;
  }else{
    const s=p.dt<10?'ok':p.dt<15?'warn':'crit';
    el.className=`pc ${s} demo`;
    el.title=`${p.id} · DEMO · DT ${p.dt}C`;
  }
  pmap.appendChild(el);
});
function statusFor(dt){return dt<10?'ok':dt<15?'warn':'crit';}
function labelFor(s){return s==='ok'?'Optimal':s==='warn'?'Monitor':'Critical';}
function recoFor(s){return s==='ok'?'Operating normally':s==='warn'?'Monitor closely':'Replace panel';}
function renderTable(){
  const live=panels[0];
  const others=panels.slice(1).sort((a,b)=>b.dt-a.dt).slice(0,6);
  const rows=[live,...others];
  const tbody=document.getElementById('tbody');
  tbody.innerHTML='';
  rows.forEach(p=>{
    const s=statusFor(p.dt);
    const tag=p.isLive?'<span class="live-tag">● LIVE</span>':'<span class="demo-tag">DEMO</span>';
    const src=p.isLive?'<span style="color:#16a34a;font-weight:700">ESP32</span>':'<span style="color:#94a3b8">Simulated</span>';
    const tr=document.createElement('tr');
    if(p.isLive)tr.className='live-row';
    tr.innerHTML=`<td><strong>${p.id}</strong>${tag}</td><td>${p.tmin}</td><td>${p.tmax}</td><td><strong>${p.dt}</strong></td><td><span class="badge b${s}">${labelFor(s)}</span></td><td>${src}</td><td style="color:#94a3b8">${recoFor(s)}</td>`;
    tbody.appendChild(tr);
  });
}
function refreshStats(){
  document.getElementById('nalerts').textContent=panels.filter(p=>p.dt>=15).length;
}
renderTable();refreshStats();
setInterval(()=>document.getElementById('clock').textContent=new Date().toTimeString().slice(0,8),1000);
async function fetchData(){
  try{
    const r=await fetch('/api/data');
    const d=await r.json();
    document.getElementById('h1').textContent=d.temp_bme;
    document.getElementById('h3').textContent=d.temp_object;
    document.getElementById('h4').textContent=d.pressure;
    document.getElementById('hb1').style.width=(d.temp_bme/50*100)+'%';
    document.getElementById('hb3').style.width=(d.temp_object/50*100)+'%';
    document.getElementById('s1').textContent=d.temp_bme;
    document.getElementById('s3').textContent=d.pressure;
    document.getElementById('s4').textContent=d.temp_object;
    document.getElementById('s5').textContent=d.temp_ambient;
    document.getElementById('sb1').style.width=(d.temp_bme/50*100)+'%';
    document.getElementById('sb4').style.width=(d.temp_object/50*100)+'%';
    const tair=parseFloat(d.temp_bme)||0;
    const tobj=parseFloat(d.temp_object)||0;
    const hum=parseFloat(d.humidity)||0;
    const dt=Math.max(0,+(tobj-tair).toFixed(2));
    panels[0].tmin=+tair.toFixed(2);
    panels[0].tmax=+tobj.toFixed(2);
    panels[0].dt=dt;
    panels[0].hum=hum;
    const live=cellEls[0];
    const s=statusFor(dt);
    live.className=`pc ${s} live-cell`;
    live.title=`A-001 · LIVE ESP32 · DT ${dt}C`;
    renderTable();refreshStats();
  }catch(e){}
}
fetchData();setInterval(fetchData,3000);
// Toast on PDF download click
document.querySelectorAll('a[href="/api/report.pdf"]').forEach(a=>{
  a.addEventListener('click',()=>{
    const t=document.getElementById('toast');
    t.textContent='📄 Generating PDF report...';
    t.classList.add('show');
    setTimeout(()=>t.classList.remove('show'),2200);
  });
});
// =============================================================================
// TC001 Thermal Camera Live Stream Handler
// =============================================================================
// STREAM_URL is injected from the Flask backend (env var on Railway).
// When set, attempt to load the MJPEG stream and update the status badge.
// On error, fall back gracefully to an "Offline" placeholder.
const STREAM_URL = "{{ stream_url }}";
const thermalImg = document.getElementById('thermalStream');
const thermalPlaceholder = document.getElementById('thermalPlaceholder');
const thermalStatus = document.getElementById('thermalStatus');
const thermalStatusDot = document.getElementById('thermalStatusDot');
const thermalStatusText = document.getElementById('thermalStatusText');
const thermalText = document.getElementById('thermalText');
if (STREAM_URL) {
  // MJPEG over Cloudflare can briefly disconnect, buffer, or fire an error event
  // even while the direct /video link is reachable. Keep the visual state stable
  // and retry with a cache-buster instead of instantly hiding the stream.
  let thermalRetryTimer = null;
  let thermalErrorCount = 0;

  function setThermalLive() {
    thermalImg.style.display = 'block';
    thermalPlaceholder.style.display = 'none';
    thermalStatus.classList.remove('offline');
    thermalStatus.classList.add('live');
    thermalStatusDot.style.background = '#22c55e';
    thermalStatusText.textContent = 'Live Stream';
    thermalText.textContent = 'Live TC001 thermal stream is connected through Raspberry Pi and secure tunnel.';
  }

  function setThermalReconnecting() {
    thermalImg.style.display = 'block';
    thermalPlaceholder.style.display = 'none';
    thermalStatus.classList.remove('offline');
    thermalStatus.classList.add('live');
    thermalStatusDot.style.background = '#fbbf24';
    thermalStatusText.textContent = 'Reconnecting...';
    thermalText.textContent = 'Thermal stream is reconnecting. Keep Raspberry Pi camera and Cloudflare tunnel running.';
  }

  function setThermalOffline() {
    thermalImg.style.display = 'none';
    thermalPlaceholder.style.display = 'inline-block';
    thermalPlaceholder.textContent = '⚠️';
    thermalStatus.classList.remove('live');
    thermalStatus.classList.add('offline');
    thermalStatusDot.style.background = '#ef4444';
    thermalStatusText.textContent = 'Stream Offline';
    thermalText.textContent = 'Thermal stream URL is configured, but the camera stream is currently unreachable.';
  }

  function streamUrlWithCacheBust() {
    const sep = STREAM_URL.includes('?') ? '&' : '?';
    return STREAM_URL + sep + 't=' + Date.now();
  }

  setThermalLive();
  thermalImg.src = streamUrlWithCacheBust();

  thermalImg.onload = () => {
    thermalErrorCount = 0;
    setThermalLive();
  };

  thermalImg.onerror = () => {
    thermalErrorCount += 1;

    if (thermalErrorCount < 5) {
      setThermalReconnecting();
    } else {
      setThermalOffline();
    }

    if (thermalRetryTimer) return;
    thermalRetryTimer = setTimeout(() => {
      thermalRetryTimer = null;
      thermalImg.src = streamUrlWithCacheBust();
    }, 2500);
  };
} else {
  thermalStatusText.textContent = 'Pending STREAM_URL';
}
</script></body></html>"""
# =============================================================================
# Routes
# =============================================================================
@app.route('/')
def index():
    return render_template_string(HTML, stream_url=STREAM_URL)
@app.route('/data', methods=['POST'])
def receive():
    global latest_data
    d = request.get_json()
    if not d:
        return jsonify({"status": "error"}), 400
    latest_data = d
    latest_data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"Data: {latest_data}")
    # Trigger Telegram alert if surface heat exceeds threshold
    try:
        temp_obj = float(latest_data.get("temp_object", 0))
        if temp_obj > ALERT_TEMP_THRESHOLD:
            send_telegram_alert(
                temp_obj,
                float(latest_data.get("temp_bme", 0)),
                float(latest_data.get("humidity", 0)),
                float(latest_data.get("pressure", 0))
            )
    except Exception as e:
        print(f"[Alert check] {e}")
    return jsonify({"status": "ok"}), 200
@app.route('/api/data')
def send():
    return jsonify(latest_data)
@app.route('/api/test-alert')
def test_alert():
    """Manual test endpoint to verify Telegram is configured correctly."""
    ok = send_telegram_alert(99.0, 30.0, 0.0, 1013.0)
    return jsonify({"sent": ok}), (200 if ok else 500)
@app.route('/api/report.pdf')
def report_pdf():
    """Generate and stream a PDF thermal report based on the latest sensor data."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Drone IoT Thermal Report"
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleX', parent=styles['Heading1'],
        fontSize=22, textColor=colors.HexColor('#0f172a'),
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'Sub', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#64748b'),
        spaceAfter=18
    )
    section_style = ParagraphStyle(
        'Sec', parent=styles['Heading2'],
        fontSize=13, textColor=colors.HexColor('#0f172a'),
        spaceBefore=12, spaceAfter=6
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#334155'),
        leading=15
    )
    story = []
    story.append(Paragraph("Drone IoT · Solar Panel Thermal Report", title_style))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · "
        f"Source: ESP32 + BMP280 + MLX90614",
        subtitle_style
    ))
    story.append(Paragraph("Live Sensor Snapshot (Panel A-001)", section_style))
    sensor_data = [
        ["Metric", "Value", "Unit"],
        ["Air Temperature",  f"{latest_data.get('temp_bme', 0):.2f}",     "°C"],
        ["Surface Temperature", f"{latest_data.get('temp_object', 0):.2f}",  "°C"],
        ["Ambient Temperature", f"{latest_data.get('temp_ambient', 0):.2f}", "°C"],
        ["Humidity",         f"{latest_data.get('humidity', 0):.1f}",     "%"],
        ["Pressure",         f"{latest_data.get('pressure', 0):.2f}",     "hPa"],
        ["Last Update",      str(latest_data.get('timestamp', '-')),      "-"],
    ]
    t = Table(sensor_data, colWidths=[5.5*cm, 5.5*cm, 3*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
        ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0, 0), (-1, 0), 10),
        ('FONTSIZE',   (0, 1), (-1, -1), 10),
        ('GRID',       (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    # Status assessment
    try:
        dt = max(0.0, float(latest_data.get('temp_object', 0)) - float(latest_data.get('temp_bme', 0)))
    except Exception:
        dt = 0.0
    if dt < 10:
        status_text, status_color = "OPTIMAL", "#16a34a"
        recommendation = "Panel is operating normally. Continue routine monitoring."
    elif dt < 15:
        status_text, status_color = "MONITOR", "#d97706"
        recommendation = "Slight temperature differential. Schedule a follow-up scan."
    else:
        status_text, status_color = "CRITICAL", "#dc2626"
        recommendation = "Replace or service this panel — abnormal heat detected."
    story.append(Spacer(1, 14))
    story.append(Paragraph("Diagnostic Assessment", section_style))
    story.append(Paragraph(
        f"ΔT (Surface − Air): <b>{dt:.2f} °C</b><br/>"
        f"Status: <font color='{status_color}'><b>{status_text}</b></font><br/>"
        f"Recommendation: {recommendation}",
        body_style
    ))
    story.append(Spacer(1, 16))
    story.append(Paragraph("System Notes", section_style))
    story.append(Paragraph(
        "• This report reflects the most recent reading from the live sensor (Panel A-001).<br/>"
        "• The dashboard simulates an additional 124 panels to demonstrate scalability.<br/>"
        "• Telegram alerts trigger automatically when surface heat exceeds "
        f"{ALERT_TEMP_THRESHOLD:.0f} °C.<br/>"
        "• TC001 thermal camera integration is pending Raspberry Pi connectivity.",
        body_style
    ))
    doc.build(story)
    buf.seek(0)
    fname = f"thermal_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=fname)
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
