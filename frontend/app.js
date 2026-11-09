/*
  LuậtAI frontend — vanilla JS, no build step required.
  Được FastAPI phục vụ cùng origin, nên API_BASE_URL là đường dẫn tương đối.
  Backend contract used by this UI is documented in README.md.
*/

const API_BASE_URL = '/api'; // Backend FastAPI chạy cùng origin

const state = {
  page: 'chat',
  authMode: 'login',
  user: JSON.parse(localStorage.getItem('legalai_user') || 'null'),
  token: localStorage.getItem('legalai_token') || '',
  conversations: [],
  currentMessages: [],
  users: [],
  documents: [],
  loading: false,
};

function saveAuth() {
  if (state.user) localStorage.setItem('legalai_user', JSON.stringify(state.user));
  else localStorage.removeItem('legalai_user');
  if (state.token) localStorage.setItem('legalai_token', state.token);
  else localStorage.removeItem('legalai_token');
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function toast(message, kind = 'info') {
  const root = document.getElementById('toast-root');
  const el = document.createElement('div');
  el.style.cssText = `position:fixed;right:18px;bottom:18px;z-index:60;padding:12px 15px;border-radius:12px;background:#fff;border:1px solid var(--border);box-shadow:var(--shadow);font-size:12px;max-width:340px;${kind === 'error' ? 'border-left:4px solid var(--danger);' : kind === 'success' ? 'border-left:4px solid var(--success);' : ''}`;
  el.textContent = message;
  root.appendChild(el);
  setTimeout(() => el.remove(), 2800);
}

function logout() {
  state.user = null; state.token = ''; state.currentMessages = []; state.conversations = [];
  state.users = []; state.documents = []; state.page = 'chat';
  saveAuth(); render();
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  } catch (_) {
    throw new Error('Không kết nối được máy chủ. Vui lòng kiểm tra mạng và thử lại.');
  }
  if (!response.ok) {
    let body = {};
    try { body = await response.json(); } catch (_) {}
    // Token hết hạn / tài khoản bị khóa -> đăng xuất (trừ khi đang gọi login)
    if ((response.status === 401 || response.status === 403) && state.token && !path.startsWith('/auth/login')) {
      if (response.status === 401 || body.detail === 'Tài khoản đã bị khóa') logout();
    }
    let message = body.detail || body.message || `HTTP ${response.status}`;
    // Lỗi validate của FastAPI (422) trả về mảng
    if (Array.isArray(message)) message = message.map(e => String(e.msg || '').replace(/^Value error,\s*/, '')).join('; ');
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

async function login(name, password) {
  const data = await api('/auth/login', { method: 'POST', body: JSON.stringify({ identifier: name, password }) });
  state.user = data.user;
  state.token = data.token;
  saveAuth();
  return data.user;
}

async function register(name, email, password) {
  const data = await api('/auth/register', { method: 'POST', body: JSON.stringify({ name, email, password }) });
  state.user = data.user;
  state.token = data.token;
  saveAuth();
  return data.user;
}

async function askQuestion(content) {
  return api('/questions', { method: 'POST', body: JSON.stringify({ content }) });
}

async function getHistory() {
  return api('/history');
}

async function getAdminUsers() {
  return api('/admin/users');
}

async function getAdminDocuments() {
  return api('/admin/documents');
}

async function changePassword(currentPassword, newPassword) {
  return api('/auth/change-password', { method: 'POST', body: JSON.stringify({ currentPassword, newPassword }) });
}

async function uploadDocument(file, meta) {
  const form = new FormData();
  form.append('file', file);
  form.append('title', meta.title || file.name);
  form.append('type', meta.type || 'Văn bản');
  form.append('agency', meta.agency || '');
  form.append('issueDate', meta.issueDate || '');
  return api('/admin/documents', { method: 'POST', body: form });
}

function render() {
  const root = document.getElementById('app');
  if (!state.user) root.innerHTML = renderAuth();
  else root.innerHTML = renderApp();
  bindEvents();
}

function renderAuth() {
  const isLogin = state.authMode === 'login';
  return `
    <div class="auth-screen">
      <div class="card auth-box">
        <div class="auth-logo">
          <div class="brand-mark">L</div>
          <div><div class="brand-title">LuậtAI</div><div class="brand-subtitle">AI + RAG Legal Q&A</div></div>
        </div>
        <h1>${isLogin ? 'Đăng nhập' : 'Tạo tài khoản'}</h1>
        <p>${isLogin ? 'Truy cập hệ thống hỏi đáp pháp luật và lịch sử hội thoại.' : 'Tạo tài khoản người dùng để bắt đầu tra cứu pháp luật.'}</p>
        <form id="auth-form" class="auth-form">
          <div class="field"><label>${isLogin ? 'Tên đăng nhập hoặc Email' : 'Họ và tên'}</label><input name="name" required placeholder="${isLogin ? 'Nguyễn Văn A hoặc email...' : 'Nguyễn Văn A'}" /></div>
          ${!isLogin ? `<div class="field"><label>Email</label><input type="email" name="email" required placeholder="you@example.com" /></div>` : ''}
          <div class="field"><label>Mật khẩu</label><input type="password" name="password" required ${isLogin ? '' : 'minlength="8"'} placeholder="${isLogin ? '••••••••' : 'Tối thiểu 8 ký tự'}" /></div>
          <button class="btn btn-primary" type="submit">${isLogin ? 'Đăng nhập' : 'Đăng ký'}</button>
        </form>
        <div class="auth-switch">${isLogin ? 'Chưa có tài khoản?' : 'Đã có tài khoản?'} <span class="link" id="auth-switch">${isLogin ? 'Đăng ký' : 'Đăng nhập'}</span></div>
      </div>
    </div>`;
}

function renderApp() {
  const admin = state.user.role === 'ADMIN';
  return `
    <div class="app-shell">
      <aside class="sidebar">
        <div class="brand">
          <div class="brand-mark">L</div>
          <div><div class="brand-title">LuậtAI</div><div class="brand-subtitle">AI + RAG Legal Q&A</div></div>
        </div>
        <nav class="nav">
          <button class="${state.page === 'chat' ? 'active' : ''}" data-page="chat"><span class="icon">💬</span> Hỏi đáp</button>
          <button class="${state.page === 'history' ? 'active' : ''}" data-page="history"><span class="icon">🕘</span> Lịch sử</button>
          ${admin ? `<button class="${state.page === 'users' ? 'active' : ''}" data-page="users"><span class="icon">👥</span> Người dùng</button>
          <button class="${state.page === 'documents' ? 'active' : ''}" data-page="documents"><span class="icon">📚</span> Văn bản</button>` : ''}
        </nav>
        <div class="sidebar-bottom">
          <div class="user-mini">
            <div class="avatar">${escapeHtml((state.user.name || 'U').slice(0,1).toUpperCase())}</div>
            <div><div class="name">${escapeHtml(state.user.name)}</div><div class="role">${admin ? 'Quản trị viên' : 'Người dùng'}</div></div>
          </div>
          <button class="btn btn-ghost" style="width:100%;color:#cbd7ea;border-color:rgba(255,255,255,.12);margin-bottom:8px" id="change-password">Đổi mật khẩu</button>
          <button class="btn btn-ghost" style="width:100%;color:#cbd7ea;border-color:rgba(255,255,255,.12)" id="logout">Đăng xuất</button>
        </div>
      </aside>
      <main class="main">
        <header class="topbar">
          <div class="topbar-title">${pageTitle()}</div>
          <div class="topbar-actions"><button class="btn btn-sm" id="new-chat">Cuộc hội thoại mới</button></div>
        </header>
        <div class="container">${pageContent()}</div>
      </main>
    </div>`;
}

function pageTitle() {
  return ({ chat: 'Hỏi đáp pháp luật', history: 'Lịch sử hội thoại', users: 'Quản lý người dùng', documents: 'Quản lý văn bản pháp luật' }[state.page] || 'LuậtAI');
}

function pageContent() {
  if (state.page === 'history') return renderHistory();
  if (state.page === 'users' && state.user.role === 'ADMIN') return renderUsers();
  if (state.page === 'documents' && state.user.role === 'ADMIN') return renderDocuments();
  return renderChat();
}

function renderChat() {
  const messages = state.currentMessages.length ? state.currentMessages : [{ role: 'assistant', content: 'Xin chào! Tôi là trợ lý hỏi đáp pháp luật. Hãy nhập câu hỏi để hệ thống tìm kiếm nguồn pháp luật liên quan và tạo câu trả lời bằng AI + RAG.' }];
  return `
    <section class="hero">
      <h1>Tra cứu pháp luật bằng AI + RAG</h1>
      <p>Đặt câu hỏi bằng ngôn ngữ tự nhiên. Hệ thống sẽ truy xuất các văn bản pháp luật liên quan, tạo context và sử dụng mô hình AI để hỗ trợ trả lời.</p>
      <div class="hero-note"><span class="pill">🔎 Semantic Search</span><span class="pill">🧠 RAG</span><span class="pill">📄 Nguồn tài liệu</span></div>
    </section>

    <div class="stats">
      <div class="card stat"><div class="stat-label">Câu hỏi phiên này</div><div class="stat-value">${state.currentMessages.filter(m=>m.role==='user').length}</div></div>
      <div class="card stat"><div class="stat-label">Nguồn đã truy xuất</div><div class="stat-value">${state.currentMessages.reduce((n,m)=>n+(m.sources?.length||0),0)}</div></div>
      <div class="card stat"><div class="stat-label">Mô hình</div><div class="stat-value" style="font-size:18px">AI API</div></div>
      <div class="card stat"><div class="stat-label">Vector Store</div><div class="stat-value" style="font-size:18px">Vector DB</div></div>
    </div>

    <div class="chat-layout">
      <section class="card chat-card">
        <div class="chat-stream" id="chat-stream">${messages.map(renderMessage).join('')}</div>
        <div class="composer">
          <textarea id="question-input" placeholder="Ví dụ: Người lao động nghỉ phép năm được quy định như thế nào?" maxlength="4000"></textarea>
          <div class="composer-row"><div class="composer-hint">Không nhập thông tin bí mật hoặc dữ liệu cá nhân nhạy cảm.</div><button class="btn btn-primary" id="send-question">Gửi câu hỏi ↗</button></div>
        </div>
      </section>
      <aside class="card side-card">
        <div class="section-head"><div><h3 style="margin:0;font-size:15px">Câu hỏi gợi ý</h3><div class="section-subtitle">Bấm để đưa nhanh vào ô nhập.</div></div></div>
        <div class="side-list">
          ${['Thời gian thử việc tối đa là bao lâu?', 'Điều kiện để đơn phương chấm dứt hợp đồng lao động?', 'Quy định về quyền thừa kế theo pháp luật?', 'Khi nào người điều khiển xe bị xử phạt?'].map(q => `<button class="side-item suggestion" data-q="${escapeHtml(q)}"><div class="side-item-title">${escapeHtml(q)}</div></button>`).join('')}
        </div>
      </aside>
    </div>`;
}

function renderMessage(m) {
  return `<div class="msg ${m.role === 'user' ? 'user' : 'assistant'}">
    <div class="bubble">${escapeHtml(m.content)}</div>
    ${m.sources?.length ? `<div class="sources">${m.sources.map(s => `<button class="source-chip source-btn" data-source='${escapeHtml(JSON.stringify(s))}'>📄 ${escapeHtml(s.title)} · ${escapeHtml(s.article || '')}</button>`).join('')}</div>` : ''}
    <div class="msg-meta">${m.role === 'user' ? 'Bạn' : 'LuậtAI'} · ${new Date(m.createdAt || Date.now()).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'})}</div>
  </div>`;
}

function renderHistory() {
  const items = state.conversations.length ? state.conversations : [];
  return `<div class="section-head"><div><h2 class="section-title">Lịch sử hội thoại</h2><p class="section-subtitle">Lưu lại câu hỏi và câu trả lời để xem lại sau.</p></div></div>
  <section class="card"><div class="table-wrap"><table><thead><tr><th>Thời gian</th><th>Câu hỏi</th><th>Trạng thái</th><th></th></tr></thead><tbody>
  ${items.length ? items.map((x,i)=>`<tr><td>${escapeHtml(new Date(x.question?.createdAt || Date.now()).toLocaleString('vi-VN'))}</td><td style="max-width:540px;white-space:normal">${escapeHtml(x.question?.content || '')}</td><td><span class="status on">Đã xử lý</span></td><td><button class="btn btn-sm history-open" data-index="${i}">Xem</button></td></tr>`).join('') : `<tr><td colspan="4"><div class="empty"><div><strong>Chưa có lịch sử</strong>Hãy đặt câu hỏi đầu tiên.</div></div></td></tr>`}
  </tbody></table></div></section>`;
}

function renderUsers() {
  return `<div class="section-head"><div><h2 class="section-title">Quản lý người dùng</h2><p class="section-subtitle">Xem danh sách, vai trò và trạng thái tài khoản.</p></div><button class="btn" id="refresh-users">Làm mới</button></div>
  <section class="card"><div class="table-wrap"><table><thead><tr><th>Họ tên</th><th>Email</th><th>Vai trò</th><th>Trạng thái</th><th>Ngày tạo</th><th></th></tr></thead><tbody>
  ${state.users.map(u=>`<tr><td>${escapeHtml(u.name)}</td><td>${escapeHtml(u.email)}</td><td>${escapeHtml(u.role)}</td><td><span class="status ${u.status ? 'on':'off'}">${u.status ? 'Hoạt động':'Đã khóa'}</span></td><td>${escapeHtml(u.createdAt)}</td><td><button class="btn btn-sm toggle-user" data-id="${escapeHtml(u.id)}">${u.status ? 'Khóa':'Mở khóa'}</button></td></tr>`).join('')}
  </tbody></table></div></section>`;
}

function renderDocuments() {
  return `<div class="section-head"><div><h2 class="section-title">Văn bản pháp luật & dữ liệu RAG</h2><p class="section-subtitle">Tải văn bản lên để hệ thống đọc, chunking, tạo embedding và lưu vào Vector DB.</p></div><button class="btn" id="refresh-docs">Làm mới</button></div>
  <div class="grid-2">
    <section class="card" style="padding:18px">
      <h3 style="margin-top:0">Cập nhật văn bản</h3>
      <form id="upload-form" class="form-grid">
        <div class="field full"><label>File văn bản</label><input type="file" name="file" accept=".pdf,.docx,.txt,.md" required /></div>
        <div class="field"><label>Tiêu đề</label><input name="title" placeholder="Tự động lấy tên file nếu bỏ trống" /></div>
        <div class="field"><label>Loại văn bản</label><select name="type"><option>Luật</option><option>Bộ luật</option><option>Nghị định</option><option>Thông tư</option><option>Khác</option></select></div>
        <div class="field"><label>Cơ quan ban hành</label><input name="agency" placeholder="Ví dụ: Quốc hội" /></div>
        <div class="field"><label>Ngày ban hành</label><input type="date" name="issueDate" /></div>
        <div class="field full"><button class="btn btn-primary" type="submit">Tải lên & cập nhật RAG</button></div>
      </form>
      <div class="demo-box" style="margin-top:16px"><b>Quy trình:</b> Upload → đọc văn bản → làm sạch → chia chunk → tạo embedding → lưu Vector DB → sẵn sàng truy xuất.</div>
    </section>
    <section class="card" style="padding:18px">
      <h3 style="margin-top:0">Tóm tắt kho dữ liệu</h3>
      <div class="stat" style="box-shadow:none;padding:6px 0"><div class="stat-label">Số văn bản</div><div class="stat-value">${state.documents.length}</div></div>
      <p class="section-subtitle">Danh sách dưới đây là metadata lấy từ backend. Số chunk/embedding được backend cập nhật sau pipeline RAG.</p>
    </section>
  </div>
  <section class="card" style="margin-top:18px"><div class="table-wrap"><table><thead><tr><th>Tài liệu</th><th>Loại</th><th>Cơ quan</th><th>Ngày ban hành</th><th>Chunks</th></tr></thead><tbody>
  ${state.documents.map(d=>`<tr><td>${escapeHtml(d.title)}</td><td>${escapeHtml(d.type)}</td><td>${escapeHtml(d.agency)}</td><td>${escapeHtml(d.issueDate)}</td><td>${escapeHtml(d.chunks)}</td></tr>`).join('')}
  </tbody></table></div></section>`;
}

function bindEvents() {
  document.querySelectorAll('[data-page]').forEach(btn => btn.addEventListener('click', async () => {
    state.page = btn.dataset.page;
    try {
      if (state.page === 'users') state.users = await getAdminUsers();
      if (state.page === 'documents') state.documents = await getAdminDocuments();
      if (state.page === 'history') state.conversations = await getHistory();
    } catch (err) { toast(err.message, 'error'); }
    render();
  }));

  document.getElementById('logout')?.addEventListener('click', logout);

  document.getElementById('change-password')?.addEventListener('click', openChangePassword);

  document.getElementById('auth-switch')?.addEventListener('click', () => {
    state.authMode = state.authMode === 'login' ? 'register' : 'login'; render();
  });

  document.getElementById('auth-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    if (state.loading) return;
    const form = e.currentTarget;
    const fd = new FormData(form);
    try {
      state.loading = true;
      if (state.authMode === 'login') await login(fd.get('name'), fd.get('password'));
      else await register(fd.get('name'), fd.get('email'), fd.get('password'));
      state.page = 'chat'; state.currentMessages = []; state.conversations = [];
      toast(state.authMode === 'login' ? 'Đăng nhập thành công.' : 'Tạo tài khoản thành công.', 'success'); render();
    } catch (err) { 
      toast(err.message, 'error');
      if (err.message.includes('bị khóa')) {
        const inputs = form.querySelectorAll('input, button');
        inputs.forEach(input => {
          input.disabled = true;
          input.style.opacity = '0.5';
          input.style.cursor = 'not-allowed';
        });
      }
    }
    finally { state.loading = false; }
  });

  document.getElementById('new-chat')?.addEventListener('click', () => { state.currentMessages = []; state.page = 'chat'; render(); });

  document.querySelectorAll('.suggestion').forEach(btn => btn.addEventListener('click', () => {
    const input = document.getElementById('question-input'); if (input) { input.value = btn.dataset.q; input.focus(); }
  }));

  document.getElementById('send-question')?.addEventListener('click', sendQuestion);
  document.getElementById('question-input')?.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') sendQuestion(); });

  document.querySelectorAll('.source-btn').forEach(btn => btn.addEventListener('click', () => {
    const s = JSON.parse(btn.dataset.source);
    openModal(`Nguồn tài liệu`, `<div class="source-detail"><h3>${escapeHtml(s.title)}</h3><p><b>Điều:</b> ${escapeHtml(s.article || '—')}</p><p>${escapeHtml(s.excerpt || '')}</p></div>`);
  }));

  document.querySelectorAll('.history-open').forEach(btn => btn.addEventListener('click', () => {
    const item = state.conversations[Number(btn.dataset.index)];
    state.currentMessages = [
      { role: 'user', content: item.question.content, createdAt: item.question.createdAt },
      { role: 'assistant', content: item.answer.content, createdAt: item.answer.createdAt, sources: item.answer.sources || [] }
    ];
    state.page = 'chat'; render();
  }));

  document.getElementById('refresh-users')?.addEventListener('click', async () => { try { state.users = await getAdminUsers(); render(); } catch (err) { toast(err.message, 'error'); } });
  document.getElementById('refresh-docs')?.addEventListener('click', async () => { try { state.documents = await getAdminDocuments(); render(); } catch (err) { toast(err.message, 'error'); } });

  document.querySelectorAll('.toggle-user').forEach(btn => btn.addEventListener('click', async () => {
    const user = state.users.find(x => x.id === btn.dataset.id); if (!user) return;
    user.status = !user.status;
    try { await api(`/admin/users/${encodeURIComponent(user.id)}/status`, { method: 'PATCH', body: JSON.stringify({ status: user.status }) }); render(); toast('Đã cập nhật.', 'success'); }
    catch (err) { user.status = !user.status; toast(err.message, 'error'); }
  }));

  document.getElementById('upload-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    if (state.loading) return;
    const form = e.currentTarget;
    const fd = new FormData(form); const file = fd.get('file');
    const btn = form.querySelector('button[type="submit"]');
    try {
      state.loading = true;
      if (btn) { btn.disabled = true; btn.textContent = 'Đang xử lý...'; }
      const res = await uploadDocument(file, { title: fd.get('title'), type: fd.get('type'), agency: fd.get('agency'), issueDate: fd.get('issueDate') });
      state.documents = await getAdminDocuments(); render(); toast(res?.message || 'Đã cập nhật văn bản vào pipeline RAG.', 'success');
    } catch (err) {
      toast(err.message, 'error');
      if (btn) { btn.disabled = false; btn.textContent = 'Tải lên & cập nhật RAG'; }
    } finally { state.loading = false; }
  });
}

function openChangePassword() {
  openModal('Đổi mật khẩu', `
    <form id="change-password-form" class="auth-form">
      <div class="field"><label>Mật khẩu hiện tại</label><input type="password" name="current" required autocomplete="current-password" /></div>
      <div class="field"><label>Mật khẩu mới</label><input type="password" name="next" required minlength="8" autocomplete="new-password" placeholder="Tối thiểu 8 ký tự" /></div>
      <div class="field"><label>Nhập lại mật khẩu mới</label><input type="password" name="confirm" required minlength="8" autocomplete="new-password" /></div>
      <button class="btn btn-primary" type="submit">Cập nhật mật khẩu</button>
    </form>`);
  const form = document.getElementById('change-password-form');
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(form);
    if (fd.get('next') !== fd.get('confirm')) { toast('Mật khẩu nhập lại không khớp.', 'error'); return; }
    try {
      await changePassword(fd.get('current'), fd.get('next'));
      form.closest('.modal-backdrop')?.remove();
      toast('Đã đổi mật khẩu.', 'success');
    } catch (err) { toast(err.message, 'error'); }
  });
}

async function sendQuestion() {
  const input = document.getElementById('question-input');
  if (!input || !input.value.trim() || state.loading) return;
  const content = input.value.trim();
  input.value = '';
  state.currentMessages.push({ role: 'user', content, createdAt: new Date().toISOString() });
  render();
  try {
    state.loading = true;
    const result = await askQuestion(content);
    state.currentMessages.push({ role: 'assistant', content: result.answer.content, sources: result.answer.sources, createdAt: result.answer.createdAt });
    state.conversations.unshift(result);
    toast('Đã nhận câu trả lời.', 'success');
  } catch (err) {
    state.currentMessages.push({ role: 'assistant', content: `Không thể xử lý câu hỏi: ${err.message}`, createdAt: new Date().toISOString() });
    toast(err.message, 'error');
  } finally { state.loading = false; render(); }
}

function openModal(title, body) {
  const root = document.createElement('div');
  root.className = 'modal-backdrop';
  root.innerHTML = `<div class="modal"><div class="modal-head"><strong>${escapeHtml(title)}</strong><button class="btn btn-sm modal-close">Đóng</button></div><div class="modal-body">${body}</div></div>`;
  root.addEventListener('click', e => { if (e.target === root || e.target.closest('.modal-close')) root.remove(); });
  document.body.appendChild(root);
}

if (state.user) {
  state.page = 'chat';
  // Xác thực lại phiên với server (token có thể đã hết hạn hoặc tài khoản bị khóa)
  api('/auth/me').then(user => { state.user = user; saveAuth(); render(); }).catch(() => {});
}
render();
