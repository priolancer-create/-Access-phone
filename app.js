"use strict";
const tg = window.Telegram?.WebApp;
const $ = id => document.getElementById(id);
const video = $("video"), canvas = $("canvas"), preview = $("preview");

const I18N = {
  bn: {
    title: "Camera Capture", subtitle: "আপনার নিয়ন্ত্রণে, আপনার সম্মতিতে",
    notice_h: "ক্যামেরা ও রিপোর্টের অনুমতি",
    notice_p: "Open Camera চাপলে ব্রাউজার Permission চাইবে। ছবি Preview করে Submit করলে ছবি আপনার নিজের Telegram চ্যাটে যাবে। IP/GPS নেওয়া হয় না।",
    cam_off: "ক্যামেরা বন্ধ",
    consent: "আমি ক্যামেরা চালু, ছবি তোলা এবং নিচে দেখানো তথ্য আমার Telegram চ্যাটে পাঠাতে সম্মতি দিচ্ছি।",
    b_start: "Open Camera", b_take: "Take Photo", b_retake: "Retake", b_stop: "Stop Camera", b_submit: "Submit Photo & Report",
    what_h: "কোন তথ্য যাবে? (দেখুন ও নিয়ন্ত্রণ করুন)",
    detail_toggle: "ডিভাইস/ব্রাউজার রিপোর্ট অন্তর্ভুক্ত করুন",
    what_p: "নিচে Submit-এর আগে হুবহু যা যাবে তা দেখানো হয়। বন্ধ করলে শুধু ছবির তথ্য যাবে।",
    no_photo_yet: "ছবি তোলার পর এখানে দেখা যাবে।",
    footer: "ক্যামেরা বন্ধ করতে Stop Camera চাপুন বা পেজ বন্ধ করুন। সার্ভারে ছবি EXIF/GPS মুছে পাঠানো হয়।",
    quota: "আজকের বাকি সীমা: {n}",
    need_consent: "আগে সম্মতির ঘরে টিক দিন।", need_https: "HTTPS ও Camera API প্রয়োজন।",
    cam_on: "ক্যামেরা চালু। Take Photo চাপুন।", cam_denied: "ক্যামেরা Permission পাওয়া যায়নি।",
    cam_stopped: "ক্যামেরা বন্ধ।", cam_idle: "নিষ্ক্রিয়তার কারণে ক্যামেরা বন্ধ করা হয়েছে।",
    preview_hint: "Preview দেখুন। Submit করলে ছবি ও রিপোর্ট যাবে।", retake_hint: "আবার ছবি তুলুন।",
    fail_photo: "ছবি তৈরি করা যায়নি।", need_both: "ছবি ও সম্মতি প্রয়োজন।",
    need_tg: "Telegram Bot-এর Open Camera বাটন দিয়ে খুলুন।", sending: "ছবি ও রিপোর্ট পাঠানো হচ্ছে…",
    sent: "ছবি ও রিপোর্ট Telegram-এ পাঠানো হয়েছে।", failed: "পাঠানো যায়নি: ", net: "নেটওয়ার্ক ত্রুটি।",
    front: "সামনের", back: "পেছনের",
  },
  en: {
    title: "Camera Capture", subtitle: "Under your control, with your consent",
    notice_h: "Camera & report permission",
    notice_p: "Tapping Open Camera makes the browser ask for permission. After you preview and submit, the photo goes to your own Telegram chat. No IP/GPS is collected.",
    cam_off: "Camera off",
    consent: "I consent to starting the camera, taking a photo and sending the information shown below to my Telegram chat.",
    b_start: "Open Camera", b_take: "Take Photo", b_retake: "Retake", b_stop: "Stop Camera", b_submit: "Submit Photo & Report",
    what_h: "What will be sent? (view & control)",
    detail_toggle: "Include device/browser report",
    what_p: "Below is exactly what will be sent before you submit. Turn this off to send image info only.",
    no_photo_yet: "Appears here after you take a photo.",
    footer: "Tap Stop Camera or close the page to stop. The server strips EXIF/GPS from the photo.",
    quota: "Remaining today: {n}",
    need_consent: "Please tick the consent box first.", need_https: "HTTPS and Camera API are required.",
    cam_on: "Camera on. Tap Take Photo.", cam_denied: "Camera permission was not granted.",
    cam_stopped: "Camera stopped.", cam_idle: "Camera stopped due to inactivity.",
    preview_hint: "Check the preview. Submit sends the photo and report.", retake_hint: "Take another photo.",
    fail_photo: "Could not create the photo.", need_both: "A photo and consent are required.",
    need_tg: "Open this via the bot's Open Camera button.", sending: "Sending photo and report…",
    sent: "Photo and report sent to Telegram.", failed: "Failed: ", net: "Network error.",
    front: "front", back: "back",
  },
};

let lang = (tg?.initDataUnsafe?.user?.language_code || "bn").toLowerCase().startsWith("bn") ? "bn" : "en";
const L = k => I18N[lang][k] ?? k;
let stream = null, blob = null, metadata = null, facing = "user", timerSec = 0, torchOn = false;
let idleTimer = null, counting = false, maxSide = 2048, remaining = null, lastStatusKey = "";

function setStatus(key, raw) { lastStatusKey = key || ""; $("status").textContent = raw ?? (key ? L(key) : ""); }
function applyI18n() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i]").forEach(el => {
    if (el.id === "metaPreview" && metadata) return;
    el.textContent = L(el.dataset.i);
  });
  $("lang").textContent = lang === "bn" ? "EN" : "বাং";
  if (lastStatusKey) setStatus(lastStatusKey);
  renderQuota();
}
function renderQuota() { $("quota").textContent = remaining == null ? "" : L("quota").replace("{n}", remaining); }
const haptic = t => { try { tg?.HapticFeedback?.notificationOccurred(t); } catch {} };

if (tg) { tg.ready(); tg.expand(); try { tg.setHeaderColor("#071b17"); tg.setBackgroundColor("#071b17"); } catch {} }

// ---- camera
function resetIdle() {
  clearTimeout(idleTimer);
  if (stream) idleTimer = setTimeout(() => { stopCamera(); $("start").disabled = false; setStatus("cam_idle"); }, 120000);
}
function stopStream() { stream?.getTracks().forEach(t => t.stop()); stream = null; video.srcObject = null; }
function stopCamera() {
  clearTimeout(idleTimer); stopStream(); torchOn = false;
  video.hidden = true; $("placeholder").hidden = !preview.hidden;
  ["stop", "take"].forEach(i => $(i).disabled = true);
  ["switch", "torch", "timer"].forEach(i => $(i).hidden = true);
}
async function startCamera() {
  stopStream();
  stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: { facingMode: { ideal: facing }, width: { ideal: 1440 }, height: { ideal: 1920 } },
  });
  const track = stream.getVideoTracks()[0];
  const real = track.getSettings?.().facingMode;
  video.classList.toggle("mirror", (real || facing) === "user");
  video.srcObject = stream; video.hidden = false; preview.hidden = true; $("placeholder").hidden = true;
  await video.play();
  $("torch").hidden = !track.getCapabilities?.().torch;
  $("switch").hidden = false; $("timer").hidden = false;
  $("take").disabled = false; $("stop").disabled = false; $("start").disabled = true;
  resetIdle();
}
$("start").onclick = async () => {
  if (!$("consent").checked) return setStatus("need_consent");
  if (!navigator.mediaDevices?.getUserMedia) return setStatus("need_https");
  try { await startCamera(); setStatus("cam_on"); } catch { setStatus("cam_denied"); }
};
$("switch").onclick = async () => {
  facing = facing === "user" ? "environment" : "user";
  try { await startCamera(); } catch { facing = facing === "user" ? "environment" : "user"; setStatus("cam_denied"); }
};
$("torch").onclick = async () => {
  try { torchOn = !torchOn; await stream.getVideoTracks()[0].applyConstraints({ advanced: [{ torch: torchOn }] }); }
  catch { torchOn = false; }
  resetIdle();
};
$("timer").onclick = () => { timerSec = timerSec === 0 ? 3 : timerSec === 3 ? 10 : 0; $("timer").textContent = `⏱ ${timerSec}s`; resetIdle(); };
$("stop").onclick = () => { stopCamera(); $("start").disabled = false; setStatus("cam_stopped"); };

// ---- capture
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function getMetadata(b, w, h) {
  const full = $("detail").checked;
  const settings = stream?.getVideoTracks()[0]?.getSettings?.() || {};
  const base = {
    capturedAt: new Date().toISOString(), cameraFacing: settings.facingMode || facing,
    imageWidth: w, imageHeight: h, imageType: b.type, imageSize: b.size,
  };
  if (!full) return base;
  let batteryLevel = null, batteryCharging = null;
  if (navigator.getBattery) {
    try { const x = await navigator.getBattery(); batteryLevel = Math.round(x.level * 100) + "%"; batteryCharging = x.charging; } catch {}
  }
  return {
    ...base,
    screenWidth: screen.width, screenHeight: screen.height, viewportWidth: innerWidth, viewportHeight: innerHeight,
    pixelRatio: devicePixelRatio || 1, language: navigator.language || null,
    languages: [...(navigator.languages || [])].slice(0, 5),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
    platform: navigator.userAgentData?.platform || navigator.platform || null,
    userAgent: navigator.userAgent || null, hardwareConcurrency: navigator.hardwareConcurrency || null,
    deviceMemory: navigator.deviceMemory || null, batteryLevel, batteryCharging,
  };
}
const showMeta = () => { $("metaPreview").textContent = metadata ? JSON.stringify(metadata, null, 2) : L("no_photo_yet"); };

async function doCapture() {
  if (!stream || !video.videoWidth || counting) return;
  if (timerSec) {
    counting = true; $("take").disabled = true; $("count").hidden = false;
    for (let i = timerSec; i > 0; i--) { $("count").textContent = i; await sleep(1000); }
    $("count").hidden = true; counting = false;
    if (!stream) return;
  }
  const vw = video.videoWidth, vh = video.videoHeight, s = Math.min(1, maxSide / Math.max(vw, vh));
  canvas.width = Math.round(vw * s); canvas.height = Math.round(vh * s);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  canvas.toBlob(async b => {
    if (!b) { $("take").disabled = false; return setStatus("fail_photo"); }
    blob = b; metadata = await getMetadata(b, canvas.width, canvas.height); showMeta();
    if (preview.src) URL.revokeObjectURL(preview.src);
    preview.src = URL.createObjectURL(b); preview.hidden = false; video.hidden = true;
    ["switch", "torch", "timer"].forEach(i => $(i).hidden = true);
    $("take").disabled = true; $("retake").disabled = false; $("submit").disabled = false;
    haptic("success"); setStatus("preview_hint"); resetIdle();
  }, "image/jpeg", 0.88);
}
$("take").onclick = doCapture;
$("retake").onclick = () => {
  blob = null; metadata = null; showMeta(); preview.hidden = true; video.hidden = false;
  $("take").disabled = false; $("retake").disabled = true; $("submit").disabled = true;
  if (stream) { $("switch").hidden = false; $("timer").hidden = false; $("torch").hidden = !stream.getVideoTracks()[0].getCapabilities?.().torch; }
  setStatus("retake_hint"); resetIdle();
};
$("detail").onchange = async () => {
  if (!blob) return;
  metadata = await getMetadata(blob, canvas.width, canvas.height); showMeta();
};

// ---- upload
function upload(fd) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", "/api/capture");
    x.setRequestHeader("X-Telegram-Init-Data", tg.initData);
    x.upload.onprogress = e => { if (e.lengthComputable) { $("progress").hidden = false; $("progress").value = (e.loaded / e.total) * 100; } };
    x.onload = () => {
      let j = {}; try { j = JSON.parse(x.responseText); } catch {}
      if (x.status >= 200 && x.status < 300) resolve(j);
      else reject(new Error(typeof j.detail === "string" ? j.detail : "HTTP " + x.status));
    };
    x.onerror = () => reject(new Error(L("net")));
    x.send(fd);
  });
}
$("submit").onclick = async () => {
  if (!blob || !metadata || !$("consent").checked) return setStatus("need_both");
  if (!tg?.initData) return setStatus("need_tg");
  $("submit").disabled = true; $("retake").disabled = true; setStatus("sending");
  const fd = new FormData();
  fd.append("photo", blob, "capture.jpg"); fd.append("metadata", JSON.stringify(metadata));
  try {
    await upload(fd);
    haptic("success"); setStatus("sent"); stopCamera(); preview.hidden = true;
    setTimeout(() => tg.close(), 600);
  } catch (e) {
    haptic("error"); setStatus("failed", L("failed") + e.message);
    $("submit").disabled = false; $("retake").disabled = false; $("progress").hidden = true;
  }
};

// ---- misc
$("lang").onclick = () => { lang = lang === "bn" ? "en" : "bn"; applyI18n(); showMeta(); };
addEventListener("pagehide", stopCamera);
document.addEventListener("visibilitychange", () => { if (document.hidden && stream && !blob) { stopCamera(); $("start").disabled = false; } });

(async function init() {
  applyI18n();
  if (!tg?.initData) return;
  try {
    const r = await fetch("/api/config", { headers: { "X-Telegram-Init-Data": tg.initData } });
    if (!r.ok) return;
    const c = await r.json();
    lang = c.lang === "en" ? "en" : "bn"; $("detail").checked = !!c.detailed;
    maxSide = c.maxSide || maxSide; remaining = c.remaining; applyI18n();
  } catch {}
})();
