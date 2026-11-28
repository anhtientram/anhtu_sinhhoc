// Bảo vệ nội dung bài giảng, chống sao chép & khoá F12/DevTools
// (Chỉ Quản trị viên ở chế độ quản trị bình thường mới được miễn trừ)

let _isAdmin = false;
let _initialized = false;
let _toastFn = null;
let _lastWarnAt = 0;
let _devtoolsTimer = null;

function isEditableTarget(el) {
  if (!el || typeof el.closest !== "function") return false;
  const tag = (el.tagName || "").toUpperCase();
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return Boolean(el.closest('[contenteditable="true"]'));
}

function warnBlocked(msg) {
  if (typeof _toastFn !== "function") return;
  const now = Date.now();
  if (now - _lastWarnAt < 3000) return;
  _lastWarnAt = now;
  _toastFn(msg, "info");
}

function ensureDevtoolsOverlay(show) {
  if (typeof document === "undefined") return;
  const existing = document.getElementById("sh12-devtools-blocker");
  if (!show || _isAdmin) {
    if (existing) existing.remove();
    return;
  }
  if (existing) return;

  const overlay = document.createElement("div");
  overlay.id = "sh12-devtools-blocker";
  overlay.className = "sh12-devtools-blocker";
  overlay.innerHTML = `
    <div class="sh12-devtools-card" role="alertdialog" aria-modal="true">
      <div class="sh12-devtools-icon">🔒</div>
      <h3>Nội dung được bảo vệ bản quyền</h3>
      <p>Vui lòng đóng công cụ nhà phát triển (F12 / DevTools) để tiếp tục học tập. Chỉ Quản trị viên mới được phép mở kiểm tra mã nguồn.</p>
    </div>
  `;
  document.body.appendChild(overlay);
}

function checkDevtoolsOpen() {
  if (_isAdmin || typeof window === "undefined" || typeof document === "undefined") {
    ensureDevtoolsOverlay(false);
    return;
  }
  if (document.visibilityState !== "visible") return;
  const dpr = window.devicePixelRatio || 1;
  if (Math.abs(dpr - Math.round(dpr)) >= 0.01) {
    ensureDevtoolsOverlay(false);
    return;
  }
  const widthDiff = (window.outerWidth || 0) - (window.innerWidth || 0);
  const heightDiff = (window.outerHeight || 0) - (window.innerHeight || 0);
  const opened =
    (widthDiff > 260 && (window.innerWidth || 0) > 320) ||
    (heightDiff > 260 && (window.innerHeight || 0) > 320);
  ensureDevtoolsOverlay(opened);
}

function syncBodyProtection() {
  if (typeof document === "undefined") return;
  if (_isAdmin) {
    document.body.classList.remove("sh12-protected");
    ensureDevtoolsOverlay(false);
    if (_devtoolsTimer) {
      clearInterval(_devtoolsTimer);
      _devtoolsTimer = null;
    }
    return;
  }
  document.body.classList.add("sh12-protected");
  if (!_devtoolsTimer && typeof window !== "undefined") {
    _devtoolsTimer = setInterval(checkDevtoolsOpen, 1200);
  }
  checkDevtoolsOpen();
}

export function setContentGuardAdmin(isAdminUnrestricted) {
  _isAdmin = Boolean(isAdminUnrestricted);
  syncBodyProtection();
}

export function initContentGuard(showToast) {
  _toastFn = showToast;
  if (_initialized || typeof document === "undefined") {
    syncBodyProtection();
    return;
  }
  _initialized = true;

  document.addEventListener(
    "contextmenu",
    (e) => {
      if (_isAdmin) return;
      e.preventDefault();
      warnBlocked("Chuột phải đã bị khoá để bảo vệ nội dung bài giảng.");
    },
    true
  );

  const handleClipboardBlock = (e) => {
    if (_isAdmin) return;
    e.preventDefault();
    try {
      e.clipboardData?.setData("text/plain", "");
    } catch {}
    warnBlocked("Nội dung được bảo vệ bản quyền — chỉ Quản trị viên mới được sao chép.");
  };

  document.addEventListener("copy", handleClipboardBlock, true);
  document.addEventListener("cut", handleClipboardBlock, true);

  document.addEventListener(
    "selectstart",
    (e) => {
      if (_isAdmin) return;
      if (isEditableTarget(e.target)) return;
      e.preventDefault();
    },
    true
  );

  document.addEventListener(
    "dragstart",
    (e) => {
      if (_isAdmin) return;
      e.preventDefault();
    },
    true
  );

  document.addEventListener(
    "keydown",
    (e) => {
      if (_isAdmin) return;
      const k = String(e.key || "").toLowerCase();
      const mod = Boolean(e.ctrlKey || e.metaKey);

      const isF12 = e.key === "F12" || e.keyCode === 123;
      const isDevTools =
        (mod && e.shiftKey && (k === "i" || k === "j" || k === "c" || k === "k")) ||
        (Boolean(e.metaKey && e.altKey) && (k === "i" || k === "j" || k === "c" || k === "u"));
      const isSourceSavePrint = mod && (k === "u" || k === "s" || k === "p");
      const isCopy = mod && k === "c";
      const isCutOrSelectAll = mod && (k === "a" || k === "x") && !isEditableTarget(e.target);

      if (isF12 || isDevTools || isSourceSavePrint || isCopy || isCutOrSelectAll) {
        e.preventDefault();
        e.stopPropagation();
        warnBlocked("Chỉ Quản trị viên mới được phép sử dụng phím tắt này.");
      }
    },
    true
  );

  syncBodyProtection();
}
