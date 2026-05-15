// ─── FAQ TOGGLE ────────────────────────────────────────────────────────────────
function toggleFaq(el) {
  const item = el.parentElement;
  const wasOpen = item.classList.contains('open');
  document.querySelectorAll('.faq-item').forEach(i => i.classList.remove('open'));
  if (!wasOpen) item.classList.add('open');
}

// ─── MODAL ─────────────────────────────────────────────────────────────────────
function openModal(id) {
  const m = document.getElementById(id);
  if (m) { m.classList.add('open'); document.body.style.overflow = 'hidden'; }
}
function closeModal(id) {
  const m = document.getElementById(id);
  if (m) { m.classList.remove('open'); document.body.style.overflow = ''; }
}
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('open');
    document.body.style.overflow = '';
  }
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(m => {
      m.classList.remove('open');
      document.body.style.overflow = '';
    });
  }
});

// ─── TOAST ─────────────────────────────────────────────────────────────────────
function showToast(msg, type = 'success') {
  let t = document.getElementById('_toast');
  if (!t) {
    t = document.createElement('div');
    t.id = '_toast';
    t.className = 'toast';
    document.body.appendChild(t);
  }
  t.className = `toast ${type} show`;
  t.textContent = msg;
  setTimeout(() => t.classList.remove('show'), 3000);
}

// ─── FAVORITE TOGGLE ───────────────────────────────────────────────────────────
async function toggleFavorite(startupId, btn) {
  try {
    const res = await fetch(`/favorites/toggle/${startupId}`, { method: 'POST' });
    if (res.status === 401) { window.location.href = '/login'; return; }
    const data = await res.json();
    if (data.favorited) {
      btn.classList.add('active');
      btn.textContent = '♥ В избранном';
      showToast('Добавлено в избранное');
    } else {
      btn.classList.remove('active');
      btn.textContent = '♡ В избранное';
      showToast('Удалено из избранного');
    }
  } catch (e) { showToast('Ошибка', 'error'); }
}

// ─── DEAL WEBSOCKET CHAT ────────────────────────────────────────────────────────
function initDealChat(dealId, currentUserId, token) {
  const messagesEl = document.getElementById('chat-messages');
  const inputEl = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send');
  if (!messagesEl || !inputEl) return;

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/ws/deal/${dealId}?token=${token}`);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    appendMessage(data, currentUserId);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  };
  ws.onerror = () => showToast('Ошибка соединения', 'error');
  ws.onclose = () => showToast('Соединение закрыто', 'error');

  function send() {
    const text = inputEl.value.trim();
    if (!text || ws.readyState !== WebSocket.OPEN) return;
    ws.send(text);
    inputEl.value = '';
    inputEl.style.height = 'auto';
  }

  sendBtn && sendBtn.addEventListener('click', send);
  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });
  inputEl.addEventListener('input', () => {
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
  });

  // Scroll to bottom on load
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function appendMessage(data, currentUserId) {
  const messagesEl = document.getElementById('chat-messages');
  const div = document.createElement('div');
  if (data.type === 'system') {
    div.className = 'msg system-msg';
    div.innerHTML = `<div class="msg-bubble">${escHtml(data.body)}</div>`;
  } else {
    const isOwn = data.sender_id == currentUserId;
    div.className = `msg ${isOwn ? 'own' : 'other'}`;
    div.innerHTML = `
      ${!isOwn ? `<div class="msg-sender">${escHtml(data.sender)}</div>` : ''}
      <div class="msg-bubble">${escHtml(data.body)}</div>
      <div class="msg-time">${escHtml(data.time || '')}</div>
    `;
  }
  messagesEl.appendChild(div);
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ─── FILE INPUT LABEL ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('input[type=file]').forEach(input => {
    input.addEventListener('change', () => {
      const label = input.closest('.upload-form')?.querySelector('.upload-label span');
      if (label && input.files[0]) label.textContent = input.files[0].name;
    });
  });
});
