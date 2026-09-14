// ============================================================
// AURA OTT — Phase 8C.1  app.js
// Authentication-first, user-specific dashboard & analytics
// ============================================================

// ── Runtime config ──────────────────────────────────────────
const APP_CONFIG = window.APP_CONFIG || {};

// ── Application state ───────────────────────────────────────
const state = {
  currentView: 'home',
  user: null,          // null = guest, object = authenticated
  movies: [],
  recommendations: [],
  metrics: null,
  ratingSelection: 3,
  pendingRatingMovie: null,
  currentSearch: '',
  currentGenre: 'all',
  currentSort: 'rating-desc',
  userAnalytics: null,   // cached /api/analytics/me
  history: null,
  watchlist: null,
  chartInstances: {},    // keyed by canvas id → Chart instance
};

// ── DOM references ───────────────────────────────────────────
const ui = {};

function resolveUI() {
  ui.navButtons        = Array.from(document.querySelectorAll('.nav-button[data-view]'));
  ui.pages             = Array.from(document.querySelectorAll('.page'));
  ui.sidebar           = document.getElementById('sidebar');
  ui.sidebarUser       = document.getElementById('sidebar-user');
  ui.sidebarAvatar     = document.getElementById('sidebar-avatar');
  ui.sidebarUserName   = document.getElementById('sidebar-user-name');
  ui.sidebarUserEmail  = document.getElementById('sidebar-user-email');
  ui.sidebarLogoutBtn  = document.getElementById('sidebar-logout-btn');
  ui.mobileToggle      = document.getElementById('mobile-menu-toggle');
  ui.authUserLabel     = document.getElementById('auth-user-label');
  ui.authOpenBtn       = document.getElementById('auth-open-btn');
  ui.authLogoutBtn     = document.getElementById('auth-logout-btn');
  ui.systemStatus      = document.getElementById('system-status');
  ui.statusText        = document.getElementById('status-text');
  // Movie modal
  ui.movieModal        = document.getElementById('movie-modal');
  ui.movieModalContent = document.getElementById('movie-modal-content');
  ui.movieModalClose   = document.getElementById('movie-modal-close');
  // Rating modal
  ui.ratingModal       = document.getElementById('rating-modal');
  ui.ratingModalTitle  = document.getElementById('rating-modal-title');
  ui.ratingFeedback    = document.getElementById('rating-feedback');
  ui.ratingValueDisplay= document.getElementById('rating-value-display');
  ui.starButtons       = Array.from(document.querySelectorAll('.star-button'));
  ui.ratingSubmit      = document.getElementById('rating-submit');
  ui.ratingCancel      = document.getElementById('rating-cancel');
  ui.ratingClose       = document.getElementById('rating-modal-close');
  // Auth modal
  ui.authModal         = document.getElementById('auth-modal');
  ui.authModalTitle    = document.getElementById('auth-modal-title');
  ui.authModalClose    = document.getElementById('auth-modal-close');
  ui.authFeedback      = document.getElementById('auth-feedback');
  ui.loginTab          = document.getElementById('auth-login-tab');
  ui.registerTab       = document.getElementById('auth-register-tab');
  ui.loginForm         = document.getElementById('login-form');
  ui.registerForm      = document.getElementById('register-form');
}

// ── Utilities ────────────────────────────────────────────────
function getApiBase() {
  return String(window.APP_CONFIG?.API_BASE_URL || '').replace(/\/$/, '');
}

function apiFetch(path, options = {}) {
  return fetch(`${getApiBase()}${path}`, { credentials: 'include', ...options });
}

function escapeHtml(v) {
  return String(v ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function formatRating(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(1) : 'N/A';
}

function genreClass(genre) {
  if (!genre) return 'drama';
  return genre.toLowerCase().replace(/[^a-z]+/g, '-').replace(/^-|-$/g, '') || 'drama';
}

function avatarLetter(name) {
  return (name || 'U').charAt(0).toUpperCase();
}

function getTimeGreeting() {
  const hour = new Date().getHours();
  return hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
}

function formatDate(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  } catch (_) { return iso; }
}

function getMovieById(id) {
  const n = Number(id);
  return state.movies.find(m => Number(m.id) === n)
      || state.recommendations.find(m => Number(m.id) === n);
}

// Destroy a Chart.js instance by canvas id to prevent "Canvas already in use" error
function destroyChart(canvasId) {
  if (state.chartInstances[canvasId]) {
    state.chartInstances[canvasId].destroy();
    delete state.chartInstances[canvasId];
  }
}

function registerChart(canvasId, instance) {
  state.chartInstances[canvasId] = instance;
}

function renderGenreBarChart(canvasId, genres) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !window.Chart) return;
  destroyChart(canvasId);
  registerChart(canvasId, new Chart(canvas, {
    type: 'bar',
    data: { labels: genres.map(item => item.genre), datasets: [{ label: 'Ratings', data: genres.map(item => item.count), backgroundColor: '#e07a5f', borderRadius: 4 }] },
    options: { responsive: true, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#64748b' } }, y: { beginAtZero: true, ticks: { precision: 0, color: '#64748b' } } } }
  }));
}

function renderRatingDistChart(canvasId, distribution) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !window.Chart) return;
  destroyChart(canvasId);
  registerChart(canvasId, new Chart(canvas, {
    type: 'bar',
    data: { labels: Object.keys(distribution).map(value => `${value} stars`), datasets: [{ label: 'Ratings', data: Object.values(distribution), backgroundColor: ['#73818b', '#8ca2aa', '#b7c7c7', '#e8a17f', '#ff6b57'], borderRadius: 6 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: context => `${context.raw} ratings` } } }, scales: { x: { ticks: { color: '#dfe7ee' }, grid: { display: false } }, y: { beginAtZero: true, ticks: { precision: 0, color: '#aab8c1' }, grid: { color: 'rgba(218, 230, 238, 0.08)' } } } }
  }));
}

function renderGenreChart(canvasId, genres, horizontal = false) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !window.Chart || !genres?.length) return;
  destroyChart(canvasId);
  registerChart(canvasId, new Chart(canvas, {
    type: 'bar',
    data: { labels: genres.map(item => item.genre), datasets: [{ label: 'Titles', data: genres.map(item => item.count), backgroundColor: '#ff6b57', borderRadius: 6, barThickness: horizontal ? 18 : undefined }] },
    options: { indexAxis: horizontal ? 'y' : 'x', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: context => `${context.raw} titles` } } }, scales: { x: { ticks: { color: '#dfe7ee' }, grid: { display: horizontal ? undefined : false } }, y: { beginAtZero: true, ticks: { precision: 0, color: '#aab8c1' }, grid: { color: 'rgba(218, 230, 238, 0.08)' } } } }
  }));
}

function renderDoughnutChart(canvasId, items, labelKey = 'genre', valueKey = 'count') {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !window.Chart || !items?.length) return;
  destroyChart(canvasId);
  const palette = ['#ff6b57', '#9de7c6', '#f3c969', '#7db7d4', '#cf9de7', '#e58ca3', '#aab8c1'];
  registerChart(canvasId, new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: items.map(item => item[labelKey]),
      datasets: [{ data: items.map(item => Number(item[valueKey]) || 0), backgroundColor: palette, borderColor: '#10151b', borderWidth: 3 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '60%',
      plugins: { legend: { position: 'bottom', labels: { color: '#dfe7ee', padding: 14, boxWidth: 12 } }, tooltip: { callbacks: { label: context => `${context.label}: ${context.raw}` } } },
    },
  }));
}

function renderHistoryChart(canvasId, items) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !window.Chart || !items?.length) return;
  const byDay = {};
  items.slice().reverse().forEach(item => {
    const date = item.timestamp ? new Date(item.timestamp) : null;
    if (!date || Number.isNaN(date.getTime())) return;
    const label = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    byDay[label] = (byDay[label] || 0) + 1;
  });
  const labels = Object.keys(byDay);
  if (!labels.length) return;
  destroyChart(canvasId);
  registerChart(canvasId, new Chart(canvas, {
    type: 'line',
    data: { labels, datasets: [{ label: 'Ratings', data: Object.values(byDay), borderColor: '#ff6b57', backgroundColor: 'rgba(255, 107, 87, 0.14)', fill: true, tension: 0.35, pointBackgroundColor: '#ffb39d', pointBorderColor: '#10151b', pointBorderWidth: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: context => `${context.raw} ratings` } } }, scales: { x: { ticks: { color: '#aab8c1' }, grid: { display: false } }, y: { beginAtZero: true, ticks: { precision: 0, color: '#aab8c1' }, grid: { color: 'rgba(218, 230, 238, 0.08)' } } } }
  }));
}

function renderRatingTrendChart(canvasId, items) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !window.Chart || !items?.length) return;
  const ordered = items.slice().reverse().filter(item => item.timestamp && Number.isFinite(Number(item.rating)));
  if (ordered.length < 2) return;
  let total = 0;
  const points = ordered.map(item => {
    total += Number(item.rating);
    return {
      label: new Date(item.timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
      value: Number((total / (ordered.indexOf(item) + 1)).toFixed(2)),
    };
  });
  destroyChart(canvasId);
  registerChart(canvasId, new Chart(canvas, {
    type: 'line',
    data: { labels: points.map(point => point.label), datasets: [{ label: 'Average rating', data: points.map(point => point.value), borderColor: '#9de7c6', backgroundColor: 'rgba(157, 231, 198, 0.12)', fill: true, tension: 0.35, pointBackgroundColor: '#f3f7f8', pointBorderColor: '#10151b', pointBorderWidth: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: context => `Average ${Number(context.raw).toFixed(2)} / 5` } } }, scales: { x: { ticks: { color: '#aab8c1' }, grid: { display: false } }, y: { min: 1, max: 5, ticks: { color: '#aab8c1' }, grid: { color: 'rgba(218, 230, 238, 0.08)' } } } }
  }));
}

function getAnalyticsSnapshot(analytics, history, watchlist) {
  const validHistory = (history || []).filter(item => item.timestamp && Number.isFinite(Number(item.rating)));
  const activeDays = new Set(validHistory.map(item => new Date(item.timestamp)).filter(date => !Number.isNaN(date.getTime())).map(date => date.toISOString().slice(0, 10))).size;
  const mostCommonRating = Object.entries(analytics?.rating_distribution || {})
    .sort(([, a], [, b]) => Number(b) - Number(a))[0];
  const genreCounts = getGenreCounts(validHistory);
  const genreTotals = {};
  validHistory.forEach(item => {
    const genre = item.genre || 'General';
    genreTotals[genre] = (genreTotals[genre] || 0) + Number(item.rating);
  });
  const highestRatedGenre = Object.entries(genreTotals)
    .map(([genre, total]) => ({ genre, average: total / (genreCounts.find(item => item.genre === genre)?.count || 1) }))
    .sort((a, b) => b.average - a.average)[0]?.genre;
  return { activeDays, mostCommonRating: mostCommonRating?.[0], highestRatedGenre, watchlistGenres: getGenreCounts(watchlist || []) };
}

function renderKpi(label, value, icon, tone = 'coral') {
  return `<div class="stat-card"><i class="fa-solid ${icon} stat-icon icon-${tone}"></i><div><span class="stat-value">${escapeHtml(String(value ?? '—'))}</span><span class="stat-label">${escapeHtml(label)}</span></div></div>`;
}

function renderInsightList(analytics, snapshot) {
  const insights = [];
  const topGenre = analytics.favorite_genres?.[0];
  if (topGenre) insights.push(`Your most rated genre is ${topGenre.genre} with ${topGenre.count} rating${topGenre.count === 1 ? '' : 's'}.`);
  if (analytics.average_rating != null) insights.push(`Your average rating is ${formatRating(analytics.average_rating)} out of 5.`);
  if (snapshot.mostCommonRating) insights.push(`Your most common rating is ${snapshot.mostCommonRating} stars.`);
  if (snapshot.activeDays) insights.push(`You have rating activity across ${snapshot.activeDays} active day${snapshot.activeDays === 1 ? '' : 's'}.`);
  return insights.length ? `<ul class="insight-list">${insights.map(item => `<li><i class="fa-solid fa-arrow-trend-up"></i><span>${escapeHtml(item)}</span></li>`).join('')}</ul>` : renderEmpty('Insights need more activity', 'Rate movies to reveal patterns in your viewing journey.');
}

function appendRatingTrendPanel(page, items) {
  if (!page || !items || items.length < 2) return;
  const layout = page.querySelector('.analytics-layout');
  if (!layout) return;
  layout.insertAdjacentHTML('beforeend', `<section class="section-card chart-panel chart-panel-wide"><div class="section-heading"><div><p class="eyebrow">Trend</p><h4>Your average rating over time</h4></div></div><div class="chart-frame chart-frame-short"><canvas id="analytics-rating-trend" aria-label="Average rating trend" role="img"></canvas></div></section>`);
  renderRatingTrendChart('analytics-rating-trend', items);
}

// Protected views require authentication
const PROTECTED_VIEWS = new Set([
  'dashboard', 'recommendations', 'watchlist', 'history', 'analytics', 'profile', 'settings'
]);

// ── Auth state rendering ─────────────────────────────────────
function renderAuthState() {
  const auth = Boolean(state.user);

  // Show/hide sidebar based on authentication state
  if (ui.sidebar) {
    ui.sidebar.classList.toggle('hidden', !auth);
  }

  // Topbar
  if (auth) {
    ui.authUserLabel.textContent = state.user.username;
    ui.authUserLabel.classList.remove('hidden');
    ui.authOpenBtn.classList.add('hidden');
    ui.authLogoutBtn.classList.remove('hidden');
  } else {
    ui.authUserLabel.classList.add('hidden');
    ui.authOpenBtn.classList.remove('hidden');
    ui.authLogoutBtn.classList.add('hidden');
  }

  // Sidebar user block
  if (auth) {
    ui.sidebarUser.classList.remove('hidden');
    ui.sidebarAvatar.textContent = avatarLetter(state.user.username);
    ui.sidebarUserName.textContent = state.user.username;
    ui.sidebarUserEmail.textContent = state.user.email || '';
    ui.sidebarLogoutBtn.classList.remove('hidden');
  } else {
    ui.sidebarUser.classList.add('hidden');
    ui.sidebarLogoutBtn.classList.add('hidden');
  }
}

// ── Session check ────────────────────────────────────────────
async function checkSession() {
  try {
    const res = await apiFetch('/api/auth/me');
    state.user = res.ok ? (await res.json()).user : null;
  } catch (_) {
    state.user = null;
  }
  renderAuthState();
}

// ── Logout ───────────────────────────────────────────────────
async function performLogout() {
  await apiFetch('/api/auth/logout', { method: 'POST' }).catch(() => null);
  state.user = null;
  state.recommendations = [];
  state.userAnalytics = null;
  if (ui.authUserLabel) ui.authUserLabel.textContent = '';
  if (ui.sidebarUserName) ui.sidebarUserName.textContent = '';
  if (ui.sidebarUserEmail) ui.sidebarUserEmail.textContent = '';
  // Destroy all charts so canvas is clean for next login
  Object.keys(state.chartInstances).forEach(destroyChart);
  renderAuthState();
  setActiveView('home');
}

// ── Status pill ──────────────────────────────────────────────
function updateStatusPill(status) {
  const pill = ui.systemStatus;
  const label = ui.statusText;
  if (status === 'Healthy' || status === 'online') {
    pill.className = 'status-pill status-healthy';
    label.textContent = 'Healthy';
  } else if (status === 'Warning' || status === 'Drifted') {
    pill.className = 'status-pill status-warning';
    label.textContent = status === 'Drifted' ? 'Drift Detected' : 'Warning';
  } else {
    pill.className = 'status-pill status-offline';
    label.textContent = 'Offline';
  }
}

async function refreshHealthStatus() {
  try {
    const [metrics, health] = await Promise.all([
      apiFetch('/api/monitoring/metrics').then(r => r.ok ? r.json() : null).catch(() => null),
      apiFetch('/api/health').then(r => r.ok ? r.json() : null).catch(() => null),
    ]);
    const status = metrics?.drift_status || health?.status || 'Healthy';
    updateStatusPill(status);
    state.metrics = metrics || health;
  } catch (_) {
    updateStatusPill('Offline');
  }
}

// ── Auth modal ───────────────────────────────────────────────
function openAuthModal(mode = 'login') {
  const isLogin = mode !== 'register';
  ui.authModalTitle.textContent = isLogin ? 'Welcome back' : 'Create your account';
  ui.loginForm.classList.toggle('hidden', !isLogin);
  ui.registerForm.classList.toggle('hidden', isLogin);
  ui.loginTab.classList.toggle('active', isLogin);
  ui.loginTab.setAttribute('aria-selected', String(isLogin));
  ui.registerTab.classList.toggle('active', !isLogin);
  ui.registerTab.setAttribute('aria-selected', String(!isLogin));
  clearAuthFeedback();
  ui.authModal.classList.remove('hidden');
  ui.authModal.setAttribute('aria-hidden', 'false');
  // Focus first input
  const firstInput = (isLogin ? ui.loginForm : ui.registerForm).querySelector('input');
  if (firstInput) setTimeout(() => firstInput.focus(), 80);
}

function closeAuthModal() {
  ui.authModal.classList.add('hidden');
  ui.authModal.setAttribute('aria-hidden', 'true');
}

function showAuthFeedback(msg, type = 'error') {
  ui.authFeedback.className = `form-feedback ${type}`;
  ui.authFeedback.textContent = msg;
  ui.authFeedback.classList.remove('hidden');
}

function clearAuthFeedback() {
  ui.authFeedback.className = 'form-feedback hidden';
  ui.authFeedback.textContent = '';
}

function setSubmitLoading(form, loading) {
  const btn = form.querySelector('button[type="submit"]');
  if (!btn) return;
  btn.disabled = loading;
  btn.querySelector('.btn-text').classList.toggle('hidden', loading);
  btn.querySelector('.btn-spinner').classList.toggle('hidden', !loading);
}

async function submitLogin(e) {
  e.preventDefault();
  clearAuthFeedback();
  const identifier = document.getElementById('login-identifier').value.trim();
  const password   = document.getElementById('login-password').value;
  if (!identifier || !password) { showAuthFeedback('Please fill in all fields.'); return; }
  setSubmitLoading(ui.loginForm, true);
  try {
    const res  = await apiFetch('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Login failed.');
    state.user = data.user;
    state.userAnalytics = null;
    renderAuthState();
    closeAuthModal();
    await loadUserAnalytics();
    await loadRecommendations();
    setActiveView('dashboard');
  } catch (err) {
    showAuthFeedback(err.message || 'Login failed. Check your credentials.');
  } finally {
    setSubmitLoading(ui.loginForm, false);
  }
}

async function submitRegister(e) {
  e.preventDefault();
  clearAuthFeedback();
  const username = document.getElementById('register-username').value.trim();
  const email    = document.getElementById('register-email').value.trim();
  const password = document.getElementById('register-password').value;
  const confirm  = document.getElementById('register-confirm').value;
  if (!username || !email || !password || !confirm) { showAuthFeedback('Please fill in all fields.'); return; }
  if (password !== confirm) { showAuthFeedback('Passwords do not match.'); return; }
  if (password.length < 8)  { showAuthFeedback('Password must be at least 8 characters.'); return; }
  setSubmitLoading(ui.registerForm, true);
  try {
    const res  = await apiFetch('/api/auth/register', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, email, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Registration failed.');

    // Registration should not expose the dashboard until the user has authenticated.
    ui.registerForm.reset();
    showAuthFeedback('Registration successful. Please log in to continue.', 'success');
    setTimeout(() => {
      openAuthModal('login');
    }, 200);
  } catch (err) {
    showAuthFeedback(err.message || 'Registration failed. Try a different username or email.');
  } finally {
    setSubmitLoading(ui.registerForm, false);
  }
}

function bindPasswordToggles() {
  document.querySelectorAll('.input-toggle-pw').forEach(btn => {
    btn.addEventListener('click', () => {
      const input = document.getElementById(btn.dataset.target);
      if (!input) return;
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
      btn.querySelector('i').className = show ? 'fa-solid fa-eye-slash' : 'fa-solid fa-eye';
    });
  });
}

// ── Navigation ───────────────────────────────────────────────
function setActiveView(viewName) {
  state.currentView = viewName;

  ui.navButtons.forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === viewName);
  });
  ui.pages.forEach(p => {
    p.classList.toggle('active', p.dataset.page === viewName);
  });

  // Protected views require auth
  if (PROTECTED_VIEWS.has(viewName) && !state.user) {
    renderAuthWall(viewName);
    openAuthModal('login');
    return;
  }

  renderPage(viewName);
}

function renderAuthWall(viewName) {
  const page = document.querySelector(`[data-page="${viewName}"]`);
  if (!page) return;
  const label = viewName.charAt(0).toUpperCase() + viewName.slice(1);
  page.innerHTML = `
    <div class="page-content">
      <div class="auth-wall">
        <div class="auth-wall-icon"><i class="fa-solid fa-lock"></i></div>
        <h3>Sign in to access ${escapeHtml(label)}</h3>
        <p>Your personalised ${escapeHtml(label.toLowerCase())} is private to your account.
           Log in or create a free account to continue.</p>
        <div class="auth-wall-actions">
          <button class="btn btn-primary" type="button" data-open-auth="login">
            <i class="fa-solid fa-right-to-bracket"></i> Log in
          </button>
          <button class="btn btn-outline" type="button" data-open-auth="register">
            <i class="fa-solid fa-user-plus"></i> Create account
          </button>
        </div>
      </div>
    </div>`;
  page.querySelectorAll('[data-open-auth]').forEach(b =>
    b.addEventListener('click', () => openAuthModal(b.dataset.openAuth)));
}

function renderPage(viewName) {
  switch (viewName) {
    case 'dashboard':       return renderDashboardPage();
    case 'home':            return renderHomePage();
    case 'movies':          return renderMoviesPage();
    case 'genres':          return renderGenresPage();
    case 'search':          return renderSearchPage();
    case 'recommendations': return renderRecommendationsPage();
    case 'watchlist':       return renderWatchlistPage();
    case 'history':         return renderHistoryPage();
    case 'analytics':       return renderAdvancedAnalyticsPage();
    case 'profile':         return renderProfilePage();
    case 'settings':        return renderSettingsPage();
    default:                return renderHomePage();
  }
}

function renderDashboardPage() {
  return renderHomePage();
}

// ── Reusable rendering helpers ───────────────────────────────
function renderLoading(title, msg) {
  return `<div class="page-content">
    <div class="page-header"><div><p class="eyebrow">Loading</p><h3>${escapeHtml(title)}</h3></div></div>
    <div class="state-box loading-state"><i class="fa-solid fa-circle-notch fa-spin"></i><h4>${escapeHtml(msg)}</h4></div>
  </div>`;
}

function renderPageHeader(eyebrow, title, description, action = '') {
  return `<div class="page-header"><div><p class="eyebrow">${escapeHtml(eyebrow)}</p><h3>${escapeHtml(title)}</h3><p class="page-description">${escapeHtml(description)}</p></div>${action ? `<div class="header-actions">${action}</div>` : ''}</div>`;
}

function getGenreCounts(movies) {
  const counts = {};
  movies.forEach(movie => { if (movie.genre) counts[movie.genre] = (counts[movie.genre] || 0) + 1; });
  return Object.entries(counts).map(([genre, count]) => ({ genre, count })).sort((a, b) => b.count - a.count);
}

function sortMovies(movies, sort = 'rating-desc') {
  return movies.slice().sort((a, b) => {
    if (sort === 'title') return String(a.title || '').localeCompare(String(b.title || ''));
    if (sort === 'year') return Number(b.year || 0) - Number(a.year || 0);
    return Number(b.rating || 0) - Number(a.rating || 0);
  });
}

function getPosterSource(movie) {
  const rawSource = String(movie?.poster || movie?.poster_url || movie?.image || movie?.image_url || '').trim();
  if (!rawSource) return '';

  if (/^(https?:\/\/|\/|data:image\/)/i.test(rawSource)) {
    return rawSource;
  }

  const normalizedSlug = rawSource.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  if (!normalizedSlug) return '';

  const posterPath = `/assets/posters/${normalizedSlug}.svg`;
  return posterPath;
}

function renderPosterArt(movie, extraClass = '') {
  const genre = genreClass(movie.genre);
  const source = getPosterSource(movie);
  return `<div class="poster-art ${genre} ${extraClass}" data-poster-container>
    ${source ? `<div class="poster-skeleton" aria-hidden="true"></div><img class="poster-image" src="${escapeHtml(source)}" alt="${escapeHtml(movie.title || 'Movie poster')}" data-poster-image />` : ''}
    <div class="poster-fallback" ${source ? 'hidden' : ''}><span class="poster-fallback-mark"><i class="fa-solid fa-wand-sparkles"></i></span><strong>${escapeHtml(movie.title || 'Untitled')}</strong><small>${escapeHtml(movie.genre || 'General')} · ${escapeHtml(String(movie.year || 'Year unavailable'))}</small></div>
    <span class="genre-badge">${escapeHtml(movie.genre || 'General')}</span>
  </div>`;
}

function bindPosterImages(root = document) {
  root.querySelectorAll('[data-poster-image]').forEach(image => {
    image.addEventListener('load', () => {
      image.closest('[data-poster-container]')?.classList.add('poster-loaded');
    }, { once: true });
    image.addEventListener('error', () => {
      const container = image.closest('[data-poster-container]');
      image.remove();
      container?.querySelector('.poster-skeleton')?.remove();
      container?.querySelector('.poster-fallback')?.removeAttribute('hidden');
      container?.classList.add('poster-failed');
    }, { once: true });
  });
}

function renderError(msg) {
  return `<div class="state-box error-state">
    <i class="fa-solid fa-circle-exclamation"></i>
    <h4>Something went wrong</h4>
    <p>${escapeHtml(msg)}</p>
  </div>`;
}

function renderEmpty(title, msg, actions = '') {
  return `<div class="state-box empty-state">
    <i class="fa-solid fa-film"></i>
    <h4>${escapeHtml(title)}</h4>
    <p>${escapeHtml(msg)}</p>
    ${actions}
  </div>`;
}

// ── Movie cards ──────────────────────────────────────────────
function renderMovieCards(movies, opts = {}) {
  const { showActions = true, context = '' } = opts;
  if (!Array.isArray(movies) || movies.length === 0) {
    return renderEmpty('No titles found', 'No titles match the current filter.');
  }
  return `<div class="movie-grid">
    ${movies.map(movie => {
      const rat  = movie.rating && Number(movie.rating) ? formatRating(Number(movie.rating)) : 'N/A';
      const userRating = movie.user_rating ? formatRating(Number(movie.user_rating)) : null;
      return `<article class="movie-card" data-id="${movie.id}">
        ${renderPosterArt(movie)}
        <div class="movie-card-body">
          <h4 class="movie-card-title">${escapeHtml(movie.title || 'Untitled')}</h4>
          <div class="meta-row">
            <span class="meta-year">${escapeHtml(String(movie.year || 'N/A'))}</span>
            <span class="rating-chip"><i class="fa-solid fa-star"></i> ${rat}</span>
          </div>
          ${userRating ? `<span class="user-rating-badge"><i class="fa-solid fa-star"></i> ${escapeHtml(userRating)}</span>` : ''}
          ${showActions ? `<div class="movie-card-actions">
            <button class="btn btn-secondary btn-sm" type="button" data-open-detail="${movie.id}">Details</button>
            <button class="btn btn-primary btn-sm" type="button" data-rate-movie="${movie.id}">
              <i class="fa-solid fa-star"></i> Rate
            </button>
            <button class="btn btn-ghost btn-sm btn-icon" type="button"
              data-watchlist-movie="${movie.id}" title="Save to Watchlist" aria-label="Save ${escapeHtml(movie.title || 'movie')} to watchlist">
              <i class="fa-solid fa-heart"></i>
            </button>
          </div>` : ''}
        </div>
      </article>`;
    }).join('')}
  </div>`;
}

function openMovieModal(movie) {
  const genre = movie.genre || 'General';
  ui.movieModalContent.innerHTML = `<div class="movie-detail-layout">${renderPosterArt(movie, 'movie-detail-poster')}<div class="movie-detail-copy"><div class="modal-header"><div><p class="eyebrow">Movie details</p><h3 id="movie-modal-title">${escapeHtml(movie.title || 'Untitled')}</h3></div></div><div class="movie-detail-meta"><span><i class="fa-solid fa-calendar"></i> ${escapeHtml(String(movie.year || 'Year unavailable'))}</span><span><i class="fa-solid fa-star"></i> ${escapeHtml(formatRating(movie.rating))}</span></div><p class="movie-detail-description">${escapeHtml(movie.description || 'AURA has this title in the live catalog. Explore it, rate it, or save it to your watchlist.')}</p><div class="movie-detail-actions">${state.user ? `<button class="btn btn-primary" type="button" data-modal-rate><i class="fa-solid fa-star"></i> Rate this movie</button><button class="btn btn-secondary" type="button" data-modal-watchlist><i class="fa-solid fa-heart"></i> Save to watchlist</button>` : '<p class="text-muted">Sign in to rate or save this movie.</p>'}</div></div></div>`;
  ui.movieModal.classList.remove('hidden');
  ui.movieModal.setAttribute('aria-hidden', 'false');
  bindPosterImages(ui.movieModalContent);
  ui.movieModalContent.querySelector('[data-modal-rate]')?.addEventListener('click', () => launchRatingModal(movie));
  ui.movieModalContent.querySelector('[data-modal-watchlist]')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true;
    const res = await apiFetch(`/api/watchlist/${movie.id}`, { method: 'POST' });
    button.innerHTML = res.ok || res.status === 409 ? '<i class="fa-solid fa-heart-circle-check"></i> Saved' : '<i class="fa-solid fa-heart"></i> Save to watchlist';
    button.disabled = false;
  });
}

function closeMovieModal() {
  ui.movieModal.classList.add('hidden');
  ui.movieModal.setAttribute('aria-hidden', 'true');
}

function launchRatingModal(movie) {
  state.pendingRatingMovie = movie;
  state.ratingSelection = Number(movie.user_rating) || 3;
  ui.ratingModalTitle.textContent = movie.title || 'Movie';
  ui.ratingValueDisplay.textContent = String(state.ratingSelection);
  ui.starButtons.forEach(button => button.classList.toggle('selected', Number(button.dataset.star) <= state.ratingSelection));
  ui.ratingFeedback.className = 'form-feedback hidden';
  ui.ratingModal.classList.remove('hidden');
  ui.ratingModal.setAttribute('aria-hidden', 'false');
}

function closeRatingModal() {
  ui.ratingModal.classList.add('hidden');
  ui.ratingModal.setAttribute('aria-hidden', 'true');
  state.pendingRatingMovie = null;
}

async function submitRating() {
  if (!state.user || !state.pendingRatingMovie) return;
  ui.ratingSubmit.disabled = true;
  try {
    const res = await apiFetch('/api/rate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: state.user.id, movie_id: state.pendingRatingMovie.id, rating: state.ratingSelection }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Rating failed.');
    await Promise.all([loadUserAnalytics(), loadHistory(), loadRecommendations()]);
    closeRatingModal();
    setActiveView(state.currentView);
  } catch (error) {
    ui.ratingFeedback.className = 'form-feedback error';
    ui.ratingFeedback.textContent = error.message;
    ui.ratingFeedback.classList.remove('hidden');
  } finally { ui.ratingSubmit.disabled = false; }
}

function attachMovieCardEvents(container, opts = {}) {
  if (!container) return;
  const { watchlistRemove = false } = opts;
  bindPosterImages(container);

  container.querySelectorAll('[data-open-detail]').forEach(btn =>
    btn.addEventListener('click', () => {
      const movie = getMovieById(btn.dataset.openDetail);
      if (movie) openMovieModal(movie);
    }));

  container.querySelectorAll('[data-rate-movie]').forEach(btn =>
    btn.addEventListener('click', () => {
      if (!state.user) { openAuthModal('login'); return; }
      const movie = getMovieById(btn.dataset.rateMovie);
      if (movie) launchRatingModal(movie);
    }));

  container.querySelectorAll('[data-watchlist-movie]').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!state.user) { openAuthModal('login'); return; }
      const movieId = btn.dataset.watchlistMovie;
      btn.disabled = true;
      if (watchlistRemove) {
        const res = await apiFetch(`/api/watchlist/${movieId}`, { method: 'DELETE' });
        if (res.ok || res.status === 204) {
          btn.closest('.movie-card')?.remove();
          const page = document.querySelector('[data-page="watchlist"]');
          if (page && !page.querySelector('.movie-card')) {
            page.querySelector('.movie-grid')?.replaceWith(
              Object.assign(document.createElement('div'),
                { innerHTML: renderEmpty('Watchlist is empty', 'Add movies to keep them close.') })
                .firstElementChild
            );
          }
        } else {
          btn.disabled = false;
        }
      } else {
        const res = await apiFetch(`/api/watchlist/${movieId}`, { method: 'POST' });
        if (res.ok || res.status === 201) {
          btn.innerHTML = '<i class="fa-solid fa-heart-circle-check"></i>';
          btn.title = 'Saved to Watchlist';
        } else if (res.status === 409) {
          btn.innerHTML = '<i class="fa-solid fa-heart-circle-check"></i>';
          btn.title = 'Already in Watchlist';
        } else {
          btn.disabled = false;
        }
      }
    });
  });
}

// ── Data loaders ─────────────────────────────────────────────
async function fetchMovies(force = false) {
  if (state.movies.length && !force) return state.movies;
  const res = await apiFetch('/api/movies');
  if (!res.ok) throw new Error(`Movie catalog returned HTTP ${res.status}`);
  const data = await res.json();
  if (!Array.isArray(data)) throw new Error('Invalid response from /api/movies');
  state.movies = data;
  return state.movies;
}

async function loadRecommendations() {
  try {
    const res = await apiFetch('/api/recommend');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!Array.isArray(data?.recommendations)) throw new Error('Bad response');
    state.recommendations = data.recommendations;
  } catch (_) {
    state.recommendations = [];
  }
}

async function loadUserAnalytics() {
  if (!state.user) { state.userAnalytics = null; return null; }
  try {
    const res = await apiFetch('/api/analytics/me');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.userAnalytics = await res.json();
    return state.userAnalytics;
  } catch (_) {
    state.userAnalytics = null;
    return null;
  }
}

async function loadHistory() {
  const res = await apiFetch('/api/history/ratings');
  if (!res.ok) throw new Error(`History returned HTTP ${res.status}`);
  const data = await res.json();
  return Array.isArray(data?.items) ? data.items : [];
}

async function loadWatchlist() {
  const res = await apiFetch('/api/watchlist');
  if (!res.ok) throw new Error(`Watchlist returned HTTP ${res.status}`);
  const data = await res.json();
  return Array.isArray(data?.items) ? data.items : [];
}

function renderBarList(items, valueKey, labelKey) {
  const max = Math.max(...items.map(item => Number(item[valueKey]) || 0), 1);
  return `<div class="analytics-bars">${items.map(item => `
    <div class="analytics-bar-row">
      <span>${escapeHtml(item[labelKey])}</span>
      <span class="analytics-bar-track"><span style="width:${Math.round((Number(item[valueKey]) || 0) / max * 100)}%"></span></span>
      <strong>${escapeHtml(String(item[valueKey]))}</strong>
    </div>`).join('')}</div>`;
}

function renderMoviesPage() {
  const page = document.querySelector('[data-page="movies"]');
  if (!page) return;
  const movies = sortMovies(state.movies, state.currentSort);
  const genres = getGenreCounts(state.movies);
  page.innerHTML = `<div class="page-content">${renderPageHeader('Discover', 'Discover your next favorite', 'Explore the live AURA catalog across every mood and category.', '<button class="btn btn-primary" type="button" data-view-trigger="recommendations"><i class="fa-solid fa-wand-sparkles"></i> For You</button>')}<section class="discover-hero"><div><p class="eyebrow">AURA discovery</p><h4>Stories worth finding.</h4><p>Browse the current catalog, then narrow it by genre, rating, year, or sort order.</p><button class="btn btn-secondary btn-sm" type="button" data-view-trigger="genres"><i class="fa-solid fa-layer-group"></i> Explore genres</button></div><div class="discover-hero-art"><i class="fa-solid fa-film"></i><span>${state.movies.length} catalog titles</span></div></section><section class="filter-bar discover-filter-bar"><select id="discover-genre" aria-label="Filter discover by genre"><option value="all">All genres</option>${genres.map(item => `<option value="${escapeHtml(item.genre)}">${escapeHtml(item.genre)}</option>`).join('')}</select><select id="discover-rating" aria-label="Filter discover by minimum rating"><option value="0">Any rating</option><option value="4.5">4.5 and above</option><option value="4">4.0 and above</option></select><select id="discover-year" aria-label="Filter discover by year"><option value="all">All years</option>${[...new Set(state.movies.map(movie => movie.year).filter(Boolean))].sort((a, b) => b - a).map(year => `<option value="${year}">${year}</option>`).join('')}</select><select id="discover-sort" aria-label="Sort discover movies"><option value="rating-desc">Top rated</option><option value="year">Recently added</option><option value="title">Title A-Z</option></select></section><section><div class="section-heading"><div><p class="eyebrow">Catalog shelf</p><h4>Explore the catalog</h4></div><span class="result-count" id="discover-result-count">${movies.length} titles</span></div><div id="discover-results">${renderMovieCards(movies)}</div></section></div>`;
  attachMovieCardEvents(page.querySelector('.movie-grid'));
  const updateDiscover = () => {
    const genre = page.querySelector('#discover-genre').value;
    const rating = Number(page.querySelector('#discover-rating').value);
    const year = page.querySelector('#discover-year').value;
    const sort = page.querySelector('#discover-sort').value;
    const filtered = sortMovies(state.movies.filter(movie => (genre === 'all' || movie.genre === genre) && Number(movie.rating || 0) >= rating && (year === 'all' || String(movie.year) === year)), sort);
    page.querySelector('#discover-result-count').textContent = `${filtered.length} title${filtered.length === 1 ? '' : 's'}`;
    page.querySelector('#discover-results').innerHTML = renderMovieCards(filtered);
    attachMovieCardEvents(page.querySelector('#discover-results .movie-grid'));
  };
  page.querySelectorAll('#discover-genre, #discover-rating, #discover-year, #discover-sort').forEach(control => control.addEventListener('change', updateDiscover));
  page.querySelectorAll('[data-view-trigger]').forEach(btn => btn.addEventListener('click', () => setActiveView(btn.dataset.viewTrigger)));
}

function renderSearchPage() {
  const page = document.querySelector('[data-page="search"]');
  if (!page) return;
  const genres = getGenreCounts(state.movies).map(item => item.genre);
  page.innerHTML = `<div class="page-content">${renderPageHeader('Discover', 'Search your next favorite', 'Search the live catalog by title, genre, or mood.')}<div class="filter-bar"><label class="search-field"><i class="fa-solid fa-magnifying-glass"></i><input class="search-input" id="movie-search" type="search" placeholder="Search by title" aria-label="Search movies" /></label><select id="search-genre" aria-label="Filter by genre"><option value="all">All genres</option>${genres.map(genre => `<option value="${escapeHtml(genre)}">${escapeHtml(genre)}</option>`).join('')}</select><select id="search-sort" aria-label="Sort results"><option value="rating-desc">Top rated</option><option value="year">Recently added</option><option value="title">Title A-Z</option></select><button class="btn btn-ghost btn-icon" id="search-clear" type="button" title="Clear search" aria-label="Clear search"><i class="fa-solid fa-xmark"></i></button></div><div class="section-heading"><div><p class="eyebrow">Results</p><h4 id="search-result-label">Browse all titles</h4></div></div><div id="search-results"></div></div>`;
  const input = page.querySelector('#movie-search');
  const genreSelect = page.querySelector('#search-genre');
  const sortSelect = page.querySelector('#search-sort');
  const update = () => {
    const query = input.value.trim().toLowerCase();
    const results = sortMovies(state.movies.filter(movie => String(movie.title || '').toLowerCase().includes(query) && (genreSelect.value === 'all' || movie.genre === genreSelect.value)), sortSelect.value);
    page.querySelector('#search-result-label').textContent = results.length ? `${results.length} title${results.length === 1 ? '' : 's'} found` : 'Search your next favorite';
    page.querySelector('#search-results').innerHTML = renderMovieCards(results);
    attachMovieCardEvents(page.querySelector('#search-results .movie-grid'));
  };
  input.addEventListener('input', update);
  genreSelect.addEventListener('change', update);
  sortSelect.addEventListener('change', update);
  page.querySelector('#search-clear').addEventListener('click', () => { input.value = ''; genreSelect.value = 'all'; update(); input.focus(); });
  update();
}

function renderGenresPage() {
  const page = document.querySelector('[data-page="genres"]');
  if (!page) return;
  const genres = getGenreCounts(state.movies);
  page.innerHTML = `<div class="page-content">${renderPageHeader('Discover', 'Explore by genre', 'Find your next favorite across every mood and category.')}<section class="genre-hero"><div><p class="eyebrow">Your catalog, organized</p><h4>Pick a feeling. Find a story.</h4><p>${state.movies.length} live titles are grouped across ${genres.length} genres.</p></div><i class="fa-solid fa-layer-group"></i></section><section><div class="section-heading"><div><p class="eyebrow">Catalog mix</p><h4>Every genre, one place</h4></div></div><div class="genre-card-grid">${genres.map(item => `<button class="genre-card ${genreClass(item.genre)}" type="button" data-genre="${escapeHtml(item.genre)}"><span class="genre-card-icon"><i class="fa-solid fa-film"></i></span><span><strong>${escapeHtml(item.genre)}</strong><small>${item.count} title${item.count === 1 ? '' : 's'}</small></span><i class="fa-solid fa-arrow-right"></i></button>`).join('')}</div></section><section class="genre-chart-panel"><div class="section-heading"><div><p class="eyebrow">Distribution</p><h4>Catalog by genre</h4></div></div><div class="chart-frame chart-frame-short"><canvas id="catalog-genre-chart" aria-label="Catalog distribution by genre" role="img"></canvas></div></section><section><div class="section-heading"><div><p class="eyebrow">Selected genre</p><h4 id="genre-results-title">Choose a genre to explore</h4></div></div><div id="genre-results">${renderEmpty('Choose a genre', 'Select a genre above to browse its live movie cards.')}</div></section></div>`;
  requestAnimationFrame(() => renderGenreChart('catalog-genre-chart', genres));
  page.querySelectorAll('[data-genre]').forEach(button => button.addEventListener('click', () => {
    const movies = state.movies.filter(movie => movie.genre === button.dataset.genre);
    page.querySelector('#genre-results-title').textContent = `${button.dataset.genre} titles`;
    page.querySelector('#genre-results').innerHTML = renderMovieCards(movies);
    attachMovieCardEvents(page.querySelector('#genre-results .movie-grid'));
  }));
}

async function renderRecommendationsPage() {
  const page = document.querySelector('[data-page="recommendations"]');
  if (!page) return;
  page.innerHTML = renderLoading('Recommended for you', 'Loading your recommendations.');
  await loadRecommendations();
  page.innerHTML = `<div class="page-content">${renderPageHeader('For You', 'Made for you', 'Recommendations shaped by your viewing behavior.', '<div class="header-actions"><button class="btn btn-outline" type="button" data-refresh-recommendations><i class="fa-solid fa-arrows-rotate"></i> Refresh</button><button class="btn btn-secondary" type="button" data-view-trigger="movies"><i class="fa-solid fa-compass"></i> Discover</button></div>')}<section class="recommendation-hero"><div><p class="eyebrow">AURA signal</p><h4>Top matches for your next watch.</h4><p>Powered by the live Funk SVD recommendation service. Your ratings help the signal sharpen over time.</p></div><div class="recommendation-score"><span>Live model</span><strong>${state.recommendations.length || '—'}</strong><small>matches ready</small></div></section><section><div class="section-heading"><div><p class="eyebrow">Top matches</p><h4>Your next watch</h4></div></div>${state.recommendations.length ? renderMovieCards(state.recommendations) : renderEmpty('Keep exploring to help AURA learn your taste', 'Rate a few movies and your personalized shelf will become more precise.', '<button class="btn btn-primary" data-view-trigger="movies">Discover Movies</button>')}</section></div>`;
  attachMovieCardEvents(page.querySelector('.movie-grid'));
  page.querySelectorAll('[data-view-trigger]').forEach(btn => btn.addEventListener('click', () => setActiveView(btn.dataset.viewTrigger)));
  page.querySelector('[data-refresh-recommendations]')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true;
    button.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Refreshing';
    await loadRecommendations();
    renderRecommendationsPage();
  });
}

function watchlistDate(item) {
  const date = item?.added_at ? new Date(item.added_at) : null;
  return date && !Number.isNaN(date.getTime()) ? date : null;
}

function renderWatchlistSections(items) {
  return `<section class="collection-section"><div class="section-heading collection-heading"><div><p class="eyebrow">Your collection</p><h4>Saved for later</h4></div><span class="result-count">${items.length} title${items.length === 1 ? '' : 's'} saved</span></div>${items.length ? renderMovieCards(items, { watchlistRemove: true }) : renderEmpty('No titles match these filters', 'Try another genre, rating, or sort option.')}</section>`;
}

async function renderWatchlistPage() {
  const page = document.querySelector('[data-page="watchlist"]');
  if (!page) return;
  page.innerHTML = renderLoading('My watchlist', 'Loading your personal collection.');
  try {
    const items = await loadWatchlist();
    state.watchlist = items;
    const genres = getGenreCounts(items);
    const rated = items.filter(item => Number.isFinite(Number(item.rating)));
    const sortedByDate = items.slice().sort((a, b) => (watchlistDate(b)?.getTime() || 0) - (watchlistDate(a)?.getTime() || 0));
    const average = rated.length ? rated.reduce((sum, item) => sum + Number(item.rating), 0) / rated.length : null;
    const filters = `<div class="collection-filters" role="group" aria-label="Filter watchlist"><select id="watchlist-genre" aria-label="Filter watchlist by genre"><option value="all">All genres</option>${genres.map(item => `<option value="${escapeHtml(item.genre)}">${escapeHtml(item.genre)}</option>`).join('')}</select>${rated.length ? '<select id="watchlist-rating" aria-label="Filter watchlist by rating"><option value="0">Any rating</option><option value="4">4.0 and above</option><option value="3">3.0 and above</option></select>' : ''}<select id="watchlist-sort" aria-label="Sort watchlist"><option value="recent">Recently added</option><option value="oldest">Oldest added</option><option value="rating">Highest rated</option><option value="title">Title A-Z</option></select></div>`;
    const emptyActions = '<button class="btn btn-primary" type="button" data-view-trigger="movies"><i class="fa-solid fa-film"></i> Explore Movies</button><button class="btn btn-outline" type="button" data-view-trigger="recommendations"><i class="fa-solid fa-wand-sparkles"></i> For You</button>';
    const highestRated = rated.slice().sort((a, b) => Number(b.rating) - Number(a.rating))[0];
    page.innerHTML = `<div class="page-content watchlist-page">${renderPageHeader('Personal collection', 'My Watchlist', 'Your personal collection of movies waiting to be discovered.', `<button class="btn btn-primary" type="button" data-view-trigger="movies"><i class="fa-solid fa-film"></i> Explore Movies</button>`)}${items.length ? `<div class="stats-row collection-kpis">${renderKpi('Total saved', items.length, 'fa-heart', 'coral')}${average != null ? renderKpi('Average rating', formatRating(average), 'fa-star', 'yellow') : ''}${genres[0] ? renderKpi('Favorite genre', genres[0].genre, 'fa-tags', 'blue') : ''}${renderKpi('Genres', genres.length, 'fa-layer-group', 'green')}</div><div class="collection-overview-grid"><section class="section-card collection-chart-panel"><div class="section-heading"><div><p class="eyebrow">Genre distribution</p><h4>Your collection mix</h4><p class="chart-description">A compact view of your saved titles.</p></div></div><div class="chart-frame chart-frame-compact"><canvas id="watchlist-genre-chart" aria-label="Saved movies by genre" role="img"></canvas></div></section><section class="section-card collection-summary-card"><div class="section-heading"><div><p class="eyebrow">Collection summary</p><h4>What is waiting for you</h4></div></div><ul class="insight-list collection-insights"><li><i class="fa-solid fa-clock"></i><span>Recently added<strong>${sortedByDate[0] ? escapeHtml(sortedByDate[0].title) : 'Unavailable'}</strong></span></li><li><i class="fa-solid fa-star"></i><span>Top rated<strong>${highestRated ? `${escapeHtml(highestRated.title)} · ${formatRating(highestRated.rating)}` : 'No ratings yet'}</strong></span></li><li><i class="fa-solid fa-tags"></i><span>Most common genre<strong>${escapeHtml(genres[0]?.genre || 'Unavailable')}</strong></span></li><li><i class="fa-solid fa-layer-group"></i><span>Genres represented<strong>${genres.length}</strong></span></li></ul></section></div><div class="collection-toolbar"><div class="section-heading collection-heading"><div><p class="eyebrow">Your collection</p><h4>Saved for later</h4></div><span class="result-count" id="watchlist-result-count">${items.length} titles saved</span></div>${filters}</div><div id="watchlist-sections">${renderWatchlistSections(items)}</div>` : renderEmpty('Your watchlist is waiting.', 'Save movies you want to watch later and build your personal collection.', emptyActions)}</div>`;
    const update = () => {
      const genre = page.querySelector('#watchlist-genre')?.value || 'all';
      const minimum = Number(page.querySelector('#watchlist-rating')?.value || 0);
      const sort = page.querySelector('#watchlist-sort')?.value || 'recent';
      let filtered = items.filter(item => (genre === 'all' || item.genre === genre) && Number(item.rating || 0) >= minimum);
      filtered = filtered.slice().sort((a, b) => sort === 'title' ? String(a.title || '').localeCompare(String(b.title || '')) : sort === 'rating' ? Number(b.rating || 0) - Number(a.rating || 0) : sort === 'oldest' ? (watchlistDate(a)?.getTime() || 0) - (watchlistDate(b)?.getTime() || 0) : (watchlistDate(b)?.getTime() || 0) - (watchlistDate(a)?.getTime() || 0));
      const sections = page.querySelector('#watchlist-sections');
      const resultCount = page.querySelector('#watchlist-result-count');
      if (resultCount) resultCount.textContent = `${filtered.length} title${filtered.length === 1 ? '' : 's'} saved`;
      if (sections) { sections.innerHTML = renderWatchlistSections(filtered); sections.querySelectorAll('.movie-grid').forEach(grid => attachMovieCardEvents(grid, { watchlistRemove: true })); }
    };
    page.querySelectorAll('#watchlist-genre, #watchlist-rating, #watchlist-sort').forEach(control => control.addEventListener('change', update));
    page.querySelectorAll('.movie-grid').forEach(grid => attachMovieCardEvents(grid, { watchlistRemove: true }));
    page.querySelectorAll('[data-view-trigger]').forEach(btn => btn.addEventListener('click', () => setActiveView(btn.dataset.viewTrigger)));
    if (items.length) requestAnimationFrame(() => renderDoughnutChart('watchlist-genre-chart', genres));
  } catch (_) {
    page.innerHTML = `<div class="page-content">${renderError('Unable to load your watchlist.')}<button class="btn btn-outline" type="button" data-retry-watchlist><i class="fa-solid fa-arrows-rotate"></i> Try Again</button></div>`;
    page.querySelector('[data-retry-watchlist]')?.addEventListener('click', renderWatchlistPage);
  }
}

function historyDate(item) {
  const date = item?.timestamp ? new Date(item.timestamp) : null;
  return date && !Number.isNaN(date.getTime()) ? date : null;
}

function renderHistoryRecent(items) {
  return `<div class="history-recent-list">${items.slice(0, 5).map(item => `<article class="history-recent-item"><div class="activity-poster ${genreClass(item.genre)}"><i class="fa-solid fa-film"></i></div><div class="activity-copy"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.genre || 'General')} · ${escapeHtml(String(item.year || 'Year unavailable'))}${historyDate(item) ? ` · ${formatDate(item.timestamp)}` : ''}</span></div><span class="rating-chip"><i class="fa-solid fa-star"></i> ${formatRating(item.rating)}</span></article>`).join('')}</div>`;
}

function renderHistoryLoading() {
  return `<div class="page-content history-page"><div class="page-header skeleton-block"><div><span class="skeleton-line skeleton-kicker"></span><span class="skeleton-line skeleton-title"></span><span class="skeleton-line skeleton-copy"></span></div></div><div class="history-loading-kpis">${Array.from({ length: 4 }, () => '<div class="skeleton-card"></div>').join('')}</div><div class="history-loading-panels"><div class="skeleton-card"></div><div class="skeleton-card"></div></div><div class="skeleton-card history-loading-grid"></div></div>`;
}

async function renderHistoryPage() {
  const page = document.querySelector('[data-page="history"]');
  if (!page) return;
  page.innerHTML = renderHistoryLoading();
  try {
    const items = await loadHistory();
    state.history = items;
    const genres = getGenreCounts(items);
    const datedItems = items.filter(item => historyDate(item));
    const ratedItems = items.filter(item => Number.isFinite(Number(item.rating)));
    const average = ratedItems.length ? ratedItems.reduce((sum, item) => sum + Number(item.rating), 0) / ratedItems.length : null;
    const sortedRecent = datedItems.slice().sort((a, b) => historyDate(b) - historyDate(a));
    const topRated = ratedItems.slice().sort((a, b) => Number(b.rating) - Number(a.rating)).slice(0, 4).map(item => ({ ...item, id: item.movie_id, user_rating: item.rating }));
    const emptyActions = '<button class="btn btn-primary" type="button" data-view-trigger="movies"><i class="fa-solid fa-film"></i> Explore Movies</button><button class="btn btn-outline" type="button" data-view-trigger="recommendations"><i class="fa-solid fa-wand-sparkles"></i> For You</button>';
    const filters = `<div class="history-filters"><label class="search-field"><i class="fa-solid fa-magnifying-glass"></i><input id="history-search" type="search" placeholder="Search your history..." aria-label="Search your history" /></label><select id="history-genre" aria-label="Filter history by genre"><option value="all">All genres</option>${genres.map(item => `<option value="${escapeHtml(item.genre)}">${escapeHtml(item.genre)}</option>`).join('')}</select>${ratedItems.length ? '<select id="history-rating" aria-label="Filter history by rating"><option value="0">Any rating</option><option value="4">4.0 and above</option><option value="3">3.0 and above</option></select>' : ''}<select id="history-sort" aria-label="Sort history"><option value="recent">Recently viewed</option><option value="oldest">Oldest</option><option value="rating">Highest rated</option><option value="title">Title A-Z</option></select></div>`;
    page.innerHTML = `<div class="page-content history-page">${renderPageHeader('Your viewing history', 'Your Viewing History', 'Keep track of your entertainment journey.', `<button class="btn btn-primary" type="button" data-view-trigger="movies"><i class="fa-solid fa-film"></i> Explore Movies</button>`)}${items.length ? `<div class="stats-row history-kpis">${renderKpi('Total movies', items.length, 'fa-film', 'coral')}${average != null ? renderKpi('Average rating', formatRating(average), 'fa-star', 'yellow') : ''}${genres[0] ? renderKpi('Top genre', genres[0].genre, 'fa-tags', 'blue') : ''}${renderKpi('Genres explored', genres.length, 'fa-layer-group', 'green')}</div><section class="section-card history-recent-panel"><div class="section-heading"><div><p class="eyebrow">Recently viewed</p><h4>Your latest activity</h4><p class="chart-description">${datedItems.length ? 'Ordered by the timestamps recorded in your account.' : 'Your recent rated titles from the available history.'}</p></div><span class="result-count">${items.length} entr${items.length === 1 ? 'y' : 'ies'}</span></div>${renderHistoryRecent(sortedRecent.length ? sortedRecent : items)}</section><div class="history-insights-grid"><section class="section-card"><div class="section-heading"><div><p class="eyebrow">Activity overview</p><h4>Activity over time</h4><p class="chart-description">Ratings grouped by recorded dates.</p></div></div>${datedItems.length ? '<div class="chart-frame chart-frame-compact"><canvas id="history-activity-chart" aria-label="Activity over time" role="img"></canvas></div>' : renderEmpty('No timestamps available', 'Your history is available, but the API does not provide dates for a timeline.')}</section><section class="section-card"><div class="section-heading"><div><p class="eyebrow">Your history insights</p><h4>AURA insight</h4></div></div><ul class="insight-list history-insights"><li><i class="fa-solid fa-tags"></i><span>Most explored genre<strong>${escapeHtml(genres[0]?.genre || 'Unavailable')}</strong></span></li>${sortedRecent[0] ? `<li><i class="fa-solid fa-clock"></i><span>Most recent title<strong>${escapeHtml(sortedRecent[0].title)}</strong></span></li>` : ''}${topRated[0] ? `<li><i class="fa-solid fa-star"></i><span>Highest-rated title<strong>${escapeHtml(topRated[0].title)} · ${formatRating(topRated[0].rating)}</strong></span></li>` : ''}<li><i class="fa-solid fa-layer-group"></i><span>Genres explored<strong>${genres.length}</strong></span></li></ul></section></div><section class="section-card history-taste-panel"><div class="section-heading"><div><p class="eyebrow">Your watching taste</p><h4>Genre breakdown</h4><p class="chart-description">Real history entries grouped by genre.</p></div></div><div class="chart-frame chart-frame-compact"><canvas id="history-genre-chart" aria-label="History genre breakdown" role="img"></canvas></div></section>${topRated.length ? `<section class="section-card history-top-rated"><div class="section-heading"><div><p class="eyebrow">Top-rated from your history</p><h4>Titles you rated highest</h4></div></div>${renderMovieCards(topRated)}</section>` : ''}<div class="history-collection-toolbar"><div class="section-heading"><div><p class="eyebrow">Your history</p><h4>Every title you have rated</h4></div><span class="result-count" id="history-result-count">${items.length} titles found</span></div>${filters}</div><div id="history-results">${renderMovieCards(items.map(item => ({ ...item, id: item.movie_id, user_rating: item.rating })))}</div>` : renderEmpty('Your history is empty', 'Your movie journey will appear here as you explore AURA.', emptyActions)}</div>`;
    const bindHistoryCards = () => page.querySelectorAll('#history-results .movie-grid, .history-top-rated .movie-grid').forEach(grid => attachMovieCardEvents(grid));
    bindHistoryCards();
    page.querySelectorAll('[data-view-trigger]').forEach(btn => btn.addEventListener('click', () => setActiveView(btn.dataset.viewTrigger)));
    page.querySelectorAll('[data-rate-movie]').forEach(button => button.addEventListener('click', () => { const movie = getMovieById(button.dataset.rateMovie); if (movie) launchRatingModal(movie); }));
    const update = () => {
      const query = page.querySelector('#history-search')?.value.trim().toLowerCase() || '';
      const genre = page.querySelector('#history-genre')?.value || 'all';
      const minimum = Number(page.querySelector('#history-rating')?.value || 0);
      const sort = page.querySelector('#history-sort')?.value || 'recent';
      let filtered = items.filter(item => String(item.title || '').toLowerCase().includes(query) && (genre === 'all' || item.genre === genre) && Number(item.rating || 0) >= minimum);
      filtered = filtered.slice().sort((a, b) => sort === 'title' ? String(a.title || '').localeCompare(String(b.title || '')) : sort === 'rating' ? Number(b.rating || 0) - Number(a.rating || 0) : sort === 'oldest' ? (historyDate(a)?.getTime() || 0) - (historyDate(b)?.getTime() || 0) : (historyDate(b)?.getTime() || 0) - (historyDate(a)?.getTime() || 0));
      page.querySelector('#history-result-count').textContent = `${filtered.length} title${filtered.length === 1 ? '' : 's'} found`;
      page.querySelector('#history-results').innerHTML = renderMovieCards(filtered.map(item => ({ ...item, id: item.movie_id, user_rating: item.rating })));
      bindHistoryCards();
    };
    page.querySelectorAll('#history-search, #history-genre, #history-rating, #history-sort').forEach(control => control.addEventListener(control.id === 'history-search' ? 'input' : 'change', update));
    if (datedItems.length) requestAnimationFrame(() => renderHistoryChart('history-activity-chart', datedItems));
    if (genres.length) requestAnimationFrame(() => renderDoughnutChart('history-genre-chart', genres));
  } catch (_) {
    page.innerHTML = `<div class="page-content">${renderError('Unable to load your history.')}<button class="btn btn-outline" type="button" data-retry-history><i class="fa-solid fa-arrows-rotate"></i> Try Again</button></div>`;
    page.querySelector('[data-retry-history]')?.addEventListener('click', renderHistoryPage);
  }
}

async function renderAdvancedAnalyticsPage() {
  const page = document.querySelector('[data-page="analytics"]');
  if (!page) return;
  page.innerHTML = renderLoading('Your viewing intelligence', 'Loading your private analytics.');
  const analytics = state.userAnalytics || await loadUserAnalytics();
  if (!analytics) { page.innerHTML = `<div class="page-content">${renderError('Analytics are unavailable right now.')}</div>`; return; }
  const history = state.history || await loadHistory().catch(() => []);
  const watchlist = state.watchlist || await loadWatchlist().catch(() => []);
  const topGenre = analytics.favorite_genres?.[0]?.genre;
  const snapshot = getAnalyticsSnapshot(analytics, history, watchlist);
  const hasRatings = Number(analytics.total_ratings) > 0;
  page.innerHTML = `<div class="page-content">${renderPageHeader('Insights', 'Your viewing intelligence', 'See how your movie preferences evolve over time.', '<span class="data-badge"><i class="fa-solid fa-lock"></i> Private to you</span>')}<section class="analytics-intro"><div><p class="eyebrow">AURA taste profile</p><h4>${escapeHtml(topGenre ? `${topGenre} is your strongest signal` : 'Your profile is taking shape')}</h4><p>${escapeHtml(topGenre ? `Based on ${analytics.total_ratings} ratings in your account. These insights use rating and watchlist activity only.` : 'Rate movies and build a watchlist to unlock evidence-based patterns.')}</p></div><i class="fa-solid fa-chart-line"></i></section>${hasRatings ? `<div class="stats-row analytics-kpis">${renderKpi('Ratings given', analytics.total_ratings, 'fa-star', 'yellow')}${renderKpi('Average rating', formatRating(analytics.average_rating), 'fa-chart-line', 'green')}${renderKpi('Watchlist size', analytics.watchlist_count, 'fa-heart', 'coral')}${renderKpi('Top genre', topGenre, 'fa-tags', 'blue')}${renderKpi('Active rating days', snapshot.activeDays || '—', 'fa-calendar-days', 'pink')}${renderKpi('Most common rating', snapshot.mostCommonRating ? `${snapshot.mostCommonRating} stars` : '—', 'fa-ranking-star', 'yellow')}${renderKpi('Highest rated genre', snapshot.highestRatedGenre, 'fa-trophy', 'green')}${renderKpi('Catalog titles', state.movies.length || '—', 'fa-film', 'blue')}</div><div class="analytics-layout"><section class="section-card chart-panel"><div class="section-heading"><div><p class="eyebrow">Ratings</p><h4>Rating distribution</h4><p class="chart-description">How often you use each star rating.</p></div></div><div class="chart-frame"><canvas id="analytics-rating-chart" aria-label="Bar chart showing your rating distribution" role="img"></canvas></div></section><section class="section-card chart-panel"><div class="section-heading"><div><p class="eyebrow">Taste mix</p><h4>Genres you rate</h4><p class="chart-description">Share of your rating activity by genre.</p></div></div><div class="chart-frame"><canvas id="analytics-genre-chart" aria-label="Doughnut chart showing genres in your ratings" role="img"></canvas></div></section><section class="section-card chart-panel chart-panel-wide"><div class="section-heading"><div><p class="eyebrow">Activity</p><h4>Rating activity over time</h4><p class="chart-description">Ratings grouped by dates recorded in your account.</p></div></div><div class="chart-frame chart-frame-short"><canvas id="analytics-history-chart" aria-label="Line chart showing rating activity over time" role="img"></canvas></div></section><section class="section-card chart-panel"><div class="section-heading"><div><p class="eyebrow">Saved titles</p><h4>Watchlist composition</h4><p class="chart-description">Genres represented in your saved titles.</p></div></div>${snapshot.watchlistGenres.length ? '<div class="chart-frame"><canvas id="analytics-watchlist-chart" aria-label="Doughnut chart showing watchlist genre composition" role="img"></canvas></div>' : renderEmpty('No saved titles yet', 'Add movies to your watchlist to see its composition.')}</section><section class="section-card insight-panel"><span class="eyebrow">Personalized insights</span><h4>Patterns AURA can verify</h4>${renderInsightList(analytics, snapshot)}</section><section class="taste-card taste-card-large"><span class="taste-label">Your AURA taste profile</span><h4>${escapeHtml(topGenre ? `${topGenre} explorer` : 'Your profile is taking shape')}</h4><p>${escapeHtml(topGenre ? `Your strongest recorded signal is ${topGenre}. This profile is based on ratings and saved titles, without guessing at unobserved viewing behavior.` : 'Keep rating and saving movies to build a richer, evidence-based taste profile.')}</p></section><section class="section-card explanation-card"><span class="eyebrow">Recommendation context</span><h4>Why AURA recommendations change</h4><p>AURA uses your ratings with the existing recommendation model. The current API does not expose movie-level explanation data, so this page does not claim why a specific title was selected.</p></section></div>` : renderEmpty('Your viewing intelligence is getting ready', 'Rate movies and build a watchlist to create your first real analytics profile.', '<button class="btn btn-primary" data-view-trigger="movies"><i class="fa-solid fa-film"></i> Discover Movies</button>')}</div>`;
  if (hasRatings) requestAnimationFrame(() => { renderRatingDistChart('analytics-rating-chart', analytics.rating_distribution || {}); renderDoughnutChart('analytics-genre-chart', analytics.favorite_genres || []); renderHistoryChart('analytics-history-chart', history); if (snapshot.watchlistGenres.length) renderDoughnutChart('analytics-watchlist-chart', snapshot.watchlistGenres); appendRatingTrendPanel(page, history); });
  page.querySelector('[data-view-trigger]')?.addEventListener('click', () => setActiveView('movies'));
}

async function renderAnalyticsPage() {
  const page = document.querySelector('[data-page="analytics"]');
  if (!page) return;
  page.innerHTML = renderLoading('Your viewing insights', 'Loading your private analytics.');
  const analytics = state.userAnalytics || await loadUserAnalytics();
  if (!analytics) { page.innerHTML = `<div class="page-content">${renderError('Analytics are unavailable right now.')}</div>`; return; }
  const enough = Number(analytics.total_ratings) > 0;
  const history = state.history || await loadHistory().catch(() => []);
  const topGenre = analytics.favorite_genres?.[0]?.genre;
  page.innerHTML = `<div class="page-content">${renderPageHeader('Insights', 'Your viewing intelligence', 'Understand what you rate, what you save, and how AURA reads your taste.')}<div class="stats-row"><div class="stat-card stat-card-accent"><i class="fa-solid fa-star stat-icon icon-yellow"></i><div><span class="stat-value">${analytics.total_ratings == null ? '—' : analytics.total_ratings}</span><span class="stat-label">Titles rated</span></div></div><div class="stat-card"><i class="fa-solid fa-heart stat-icon icon-coral"></i><div><span class="stat-value">${analytics.watchlist_count == null ? '—' : analytics.watchlist_count}</span><span class="stat-label">Saved for later</span></div></div><div class="stat-card"><i class="fa-solid fa-chart-line stat-icon icon-green"></i><div><span class="stat-value">${analytics.average_rating == null ? '—' : formatRating(analytics.average_rating)}</span><span class="stat-label">Average rating</span></div></div><div class="stat-card"><i class="fa-solid fa-tags stat-icon icon-blue"></i><div><span class="stat-value stat-value-sm">${escapeHtml(topGenre || '—')}</span><span class="stat-label">Top genre</span></div></div></div>${enough ? `<div class="analytics-layout"><section class="section-card chart-panel"><div class="section-heading"><div><p class="eyebrow">Ratings</p><h4>Rating distribution</h4></div></div><div class="chart-frame"><canvas id="analytics-rating-chart" aria-label="Rating distribution" role="img"></canvas></div></section><section class="section-card chart-panel"><div class="section-heading"><div><p class="eyebrow">Taste profile</p><h4>Genre preference</h4></div></div><div class="chart-frame"><canvas id="analytics-genre-chart" aria-label="Genre preference" role="img"></canvas></div></section><section class="section-card chart-panel chart-panel-wide"><div class="section-heading"><div><p class="eyebrow">Activity</p><h4>Rating activity over time</h4></div></div><div class="chart-frame chart-frame-short"><canvas id="analytics-history-chart" aria-label="Rating activity timeline" role="img"></canvas></div></section><section class="taste-card taste-card-large"><span class="taste-label">Your taste profile</span><h4>${escapeHtml(topGenre ? `${topGenre} explorer` : 'A curious explorer')}</h4><p>${escapeHtml(topGenre ? `You interact with ${topGenre.toLowerCase()} titles most often. Keep rating to sharpen AURA's understanding of your preferences.` : 'Keep watching and rating movies to unlock your taste profile.')}</p></section><section class="section-card explanation-card"><span class="eyebrow">Why AURA recommends</span><h4>Personal signals, kept honest</h4><p>AURA uses your ratings and the existing recommendation model to surface your next set of titles. Model explanations are not exposed by the current API, so this view stays grounded in the signals we can verify.</p></section></div>` : renderEmpty('More activity is needed to generate your insights', 'Rate a few movies to unlock your taste profile and visual analytics.', '<button class="btn btn-primary" data-view-trigger="movies"><i class="fa-solid fa-film"></i> Discover Movies</button>')}</div>`;
  if (enough) requestAnimationFrame(() => { renderRatingDistChart('analytics-rating-chart', analytics.rating_distribution || {}); renderGenreChart('analytics-genre-chart', analytics.favorite_genres || [], true); renderHistoryChart('analytics-history-chart', history); appendRatingTrendPanel(page, history); });
  page.querySelector('[data-view-trigger]')?.addEventListener('click', () => setActiveView('movies'));
}

async function renderProfilePage() {
  const page = document.querySelector('[data-page="profile"]');
  if (!page || !state.user) return;
  page.innerHTML = renderLoading('Your AURA profile', 'Loading your account details.');
  try {
    const [analytics, history, watchlist] = await Promise.all([state.userAnalytics || loadUserAnalytics(), state.history || loadHistory(), state.watchlist || loadWatchlist()]);
    state.userAnalytics = analytics || {};
    state.history = history;
    state.watchlist = watchlist;
    const genres = analytics?.favorite_genres || getGenreCounts(history);
    const ratedMovies = history.map(item => ({ ...item, id: item.movie_id, rating: Number(item.rating), user_rating: Number(item.rating) }));
    const topRated = ratedMovies.slice().sort((a, b) => Number(b.rating) - Number(a.rating)).slice(0, 4);
    const distribution = analytics?.rating_distribution || {};
    const topGenre = genres[0]?.genre;
    const average = analytics?.average_rating != null ? formatRating(analytics.average_rating) : '—';
    page.innerHTML = `<div class="page-content">${renderPageHeader('Account', 'Your AURA profile', 'Your identity, activity, and taste signals in one place.')}<section class="profile-hero"><div class="profile-avatar-large">${escapeHtml(avatarLetter(state.user.username))}</div><div><p class="eyebrow">AURA member</p><h4>${escapeHtml(state.user.username)}</h4><p>${escapeHtml(state.user.email || 'Email unavailable')}</p>${state.user.created_at ? `<span class="profile-member"><i class="fa-solid fa-calendar"></i> Member since ${escapeHtml(formatDate(state.user.created_at))}</span>` : ''}</div><span class="profile-status"><i class="fa-solid fa-circle-check"></i> Account active</span></section><div class="stats-row profile-kpis">${renderKpi('Movies watched', history.length, 'fa-film', 'coral')}${renderKpi('Ratings given', analytics?.total_ratings ?? history.length, 'fa-star', 'yellow')}${renderKpi('Watchlist', analytics?.watchlist_count ?? watchlist.length, 'fa-heart', 'pink')}${renderKpi('Average rating', average, 'fa-chart-line', 'green')}${topGenre ? renderKpi('Favorite genre', topGenre, 'fa-tags', 'blue') : ''}</div><div class="profile-summary-grid"><section class="section-card"><div class="section-heading"><div><p class="eyebrow">Your viewing summary</p><h4>Signals AURA can verify</h4></div></div><div class="summary-list"><div><i class="fa-solid fa-film"></i><span>Movies watched<strong>${history.length || '—'}</strong></span></div><div><i class="fa-solid fa-star"></i><span>Ratings recorded<strong>${history.length || '—'}</strong></span></div><div><i class="fa-solid fa-heart"></i><span>Saved for later<strong>${watchlist.length || '—'}</strong></span></div><div><i class="fa-solid fa-calendar-days"></i><span>Active days<strong>${new Set(history.map(item => item.timestamp ? item.timestamp.slice(0, 10) : '').filter(Boolean)).size || '—'}</strong></span></div></div></section><section class="section-card profile-taste-card"><span class="taste-label">Your AURA taste profile</span><h4>${escapeHtml(topGenre ? `${topGenre} is your strongest signal` : 'Your taste profile is building')}</h4><p>${escapeHtml(topGenre ? `Your activity shows a preference for ${topGenre.toLowerCase()} titles. Keep rating movies to sharpen this profile.` : 'Keep watching and rating movies to build your taste profile.')}</p></section></div><div class="profile-insights-grid"><section class="section-card"><div class="section-heading"><div><p class="eyebrow">Favorite genres</p><h4>Your genre signals</h4></div></div>${genres.length ? renderBarList(genres.slice(0, 6), 'count', 'genre') : renderEmpty('Your favorite genres will appear as you explore AURA.', 'Rate movies to build your taste profile.')}</section><section class="section-card chart-panel"><div class="section-heading"><div><p class="eyebrow">Rating behavior</p><h4>How you rate</h4><p class="chart-description">Your real rating distribution.</p></div></div>${Number(analytics?.total_ratings || history.length) ? `<div class="chart-frame chart-frame-compact"><canvas id="profile-rating-chart" aria-label="Rating behavior distribution" role="img"></canvas></div>` : renderEmpty('Rate movies to build your taste profile.', 'Your rating behavior will appear here.')}</section></div><section class="section-card profile-movies-section"><div class="section-heading"><div><p class="eyebrow">Your top-rated movies</p><h4>Titles you rated highest</h4></div><button class="btn btn-ghost btn-sm" type="button" data-view-trigger="history">View history <i class="fa-solid fa-arrow-right"></i></button></div>${topRated.length ? renderMovieCards(topRated) : renderEmpty('No rated movies yet', 'Rate movies to build your personal highlights.', '<button class="btn btn-primary btn-sm" data-view-trigger="movies">Discover Movies</button>')}</section><div class="profile-bottom-grid"><section class="section-card"><div class="section-heading"><div><p class="eyebrow">Recent activity</p><h4>Your latest signals</h4></div></div>${history.length ? `<div class="activity-list">${history.slice(0, 5).map(item => `<article class="activity-item"><div class="activity-poster ${genreClass(item.genre)}"><i class="fa-solid fa-star"></i></div><div class="activity-copy"><strong>Rated ${escapeHtml(item.title)}</strong><span>${formatDate(item.timestamp)} · ${escapeHtml(item.genre || 'General')}</span></div><span class="rating-chip"><i class="fa-solid fa-star"></i> ${formatRating(item.rating)}</span></article>`).join('')}</div>` : renderEmpty('Your viewing journey starts here.', 'Rate movies to build your taste profile.')}</section><section class="section-card account-info-card"><div class="section-heading"><div><p class="eyebrow">Account information</p><h4>Private by default</h4></div></div><dl><div><dt>Name</dt><dd>${escapeHtml(state.user.username)}</dd></div><div><dt>Email</dt><dd>${escapeHtml(state.user.email || 'Unavailable')}</dd></div>${state.user.id != null ? `<div><dt>Account ID</dt><dd>${escapeHtml(String(state.user.id))}</dd></div>` : ''}<div><dt>Session</dt><dd><i class="fa-solid fa-shield-halved"></i> Authenticated</dd></div></dl><button class="btn btn-outline btn-sm" type="button" id="profile-logout"><i class="fa-solid fa-arrow-right-from-bracket"></i> Log out</button></section></div></div>`;
    attachMovieCardEvents(page.querySelector('.movie-grid'));
    page.querySelectorAll('[data-view-trigger]').forEach(btn => btn.addEventListener('click', () => setActiveView(btn.dataset.viewTrigger)));
    page.querySelector('#profile-logout')?.addEventListener('click', performLogout);
    if (Number(analytics?.total_ratings || history.length)) requestAnimationFrame(() => renderRatingDistChart('profile-rating-chart', distribution));
  } catch (_) {
    page.innerHTML = `<div class="page-content">${renderError('Unable to load your profile.')}<button class="btn btn-outline" type="button" data-retry-profile><i class="fa-solid fa-arrows-rotate"></i> Try Again</button></div>`;
    page.querySelector('[data-retry-profile]')?.addEventListener('click', renderProfilePage);
  }
}

function renderSettingsPage() {
  const page = document.querySelector('[data-page="settings"]');
  if (!page) return;
  page.innerHTML = `<div class="page-content">${renderPageHeader('Account', 'Settings', 'Manage the controls currently supported by your AURA account.')}<div class="settings-grid"><section class="settings-card"><span class="settings-icon"><i class="fa-solid fa-user-shield"></i></span><div><p class="eyebrow">Account</p><h4>Privacy by default</h4><p>Your profile, ratings, watchlist, and analytics stay scoped to your authenticated session.</p></div><span class="status-badge"><i class="fa-solid fa-check"></i> Active</span></section><section class="settings-card"><span class="settings-icon"><i class="fa-solid fa-lock"></i></span><div><p class="eyebrow">Security</p><h4>Session security</h4><p>Your session is managed securely by the backend and protected by an HttpOnly cookie.</p></div><span class="status-badge"><i class="fa-solid fa-shield-halved"></i> Protected</span></section><section class="settings-card settings-card-action"><span class="settings-icon"><i class="fa-solid fa-arrow-right-from-bracket"></i></span><div><p class="eyebrow">Session</p><h4>Sign out of AURA</h4><p>End this session and return to the public home experience.</p></div><button class="btn btn-outline" id="settings-logout" type="button">Log out</button></section></div><section class="unsupported-panel"><i class="fa-solid fa-sliders"></i><div><h4>More preferences are coming later</h4><p>Theme, notifications, and profile editing are not backed by the current API, so AURA does not present them as fake controls.</p></div></section></div>`;
  page.querySelector('#settings-logout')?.addEventListener('click', performLogout);
}

// ── HOME / DASHBOARD ─────────────────────────────────────────
async function renderHomePage() {
  const page = document.querySelector(`[data-page="${state.currentView === 'dashboard' ? 'dashboard' : 'home'}"]`);
  if (!page) return;

  if (state.user) {
    // Authenticated: personalised dashboard
    const analytics = state.userAnalytics || (await loadUserAnalytics());
    const history = state.history || await loadHistory().catch(() => []);
    const recs = state.recommendations.length ? state.recommendations : [];
    const userName = escapeHtml(state.user.username);

    const totalRatings    = analytics?.total_ratings ?? 0;
    const avgRating       = analytics?.average_rating != null ? formatRating(analytics.average_rating) : '—';
    const watchlistCount  = analytics?.watchlist_count ?? 0;
    const topGenre        = analytics?.favorite_genres?.[0]?.genre ?? '—';
    const activeDays      = new Set(history.map(item => {
      const date = item.timestamp ? new Date(item.timestamp) : null;
      return date && !Number.isNaN(date.getTime()) ? date.toISOString().slice(0, 10) : null;
    }).filter(Boolean)).size;
    const favoriteGenres  = analytics?.favorite_genres || [];

    page.innerHTML = `
      <div class="page-content">
        <div class="dash-welcome">
          <div class="dash-welcome-text">
            <p class="eyebrow">Welcome back</p>
            <h3>${getTimeGreeting()}, ${userName}</h3>
            <p class="dash-subtitle">Discover something you'll love today.</p>
          </div>
          <div class="dash-quick-actions">
            <button class="btn btn-ghost" type="button" data-view-trigger="search">
              <i class="fa-solid fa-magnifying-glass"></i> Search
            </button>
            <button class="btn btn-ghost" type="button" data-refresh-dashboard>
              <i class="fa-solid fa-arrows-rotate"></i> Refresh
            </button>
            <button class="btn btn-primary" type="button" data-view-trigger="recommendations">
              <i class="fa-solid fa-wand-sparkles"></i> For You
            </button>
            <button class="btn btn-outline" type="button" data-view-trigger="movies">
              <i class="fa-solid fa-film"></i> Explore
            </button>
            <button class="btn btn-ghost" type="button" data-view-trigger="watchlist">
              <i class="fa-solid fa-heart"></i> Watchlist
            </button>
            <button class="btn btn-ghost" type="button" data-view-trigger="analytics">
              <i class="fa-solid fa-chart-line"></i> Analytics
            </button>
          </div>
        </div>

        <div class="stats-row dash-kpis">
          <div class="stat-card">
            <i class="fa-solid fa-star stat-icon icon-yellow"></i>
            <div>
              <span class="stat-value">${escapeHtml(String(totalRatings))}</span>
              <span class="stat-label">Ratings Given</span>
            </div>
          </div>
          <div class="stat-card">
            <i class="fa-solid fa-chart-line stat-icon icon-green"></i>
            <div>
              <span class="stat-value">${escapeHtml(avgRating)}</span>
              <span class="stat-label">Avg Rating</span>
            </div>
          </div>
          <div class="stat-card">
            <i class="fa-solid fa-heart stat-icon icon-coral"></i>
            <div>
              <span class="stat-value">${escapeHtml(String(watchlistCount))}</span>
              <span class="stat-label">Watchlist</span>
            </div>
          </div>
          <div class="stat-card">
            <i class="fa-solid fa-tags stat-icon icon-blue"></i>
            <div>
              <span class="stat-value stat-value-sm">${escapeHtml(topGenre)}</span>
              <span class="stat-label">Top Genre</span>
            </div>
          </div>
          <div class="stat-card">
            <i class="fa-solid fa-calendar-days stat-icon icon-pink"></i>
            <div><span class="stat-value">${escapeHtml(String(activeDays || '—'))}</span><span class="stat-label">Active Days</span></div>
          </div>
        </div>

        <div class="dash-grid">
          <section class="section-card dashboard-recommendations">
            <div class="section-heading"><div><p class="eyebrow">For You</p><h4>Recommended for you</h4><p class="chart-description">Fresh matches from your live recommendation feed.</p></div><button class="btn btn-ghost btn-sm" type="button" data-view-trigger="recommendations">See all <i class="fa-solid fa-arrow-right"></i></button></div>
            ${recs.length
              ? renderMovieCards(recs.slice(0, 6))
              : renderEmpty('No recommendations yet',
                  'Rate some movies to train your personal recommendations.',
                  `<button class="btn btn-primary" type="button" data-view-trigger="movies">
                    <i class="fa-solid fa-film"></i> Explore Movies
                  </button>`)}
          </section>

          <div class="dash-side">
            <section class="section-card">
              <div class="section-heading"><div><p class="eyebrow">Taste mix</p><h4>Your genre mix</h4><p class="chart-description">Where your ratings are concentrated.</p></div></div>
              ${(analytics?.favorite_genres?.length)
                ? `<div class="chart-frame chart-frame-dashboard"><canvas id="dash-genres-chart" aria-label="Favourite genres chart" role="img"></canvas></div>`
                : `<div class="state-box empty-state-sm">
                     <p>Rate movies to see your genre preferences here.</p>
                     <button class="btn btn-outline btn-sm" type="button" data-view-trigger="movies">Explore</button>
                   </div>`}
            </section>

            <section class="section-card">
              <div class="section-heading"><div><p class="eyebrow">Your signals</p><h4>Rating distribution</h4><p class="chart-description">How often you use each star rating.</p></div></div>
              ${(totalRatings > 0)
                ? `<div class="chart-frame chart-frame-dashboard"><canvas id="dash-dist-chart" aria-label="Rating distribution chart" role="img"></canvas></div>`
                : `<div class="state-box empty-state-sm"><p>No rating data yet.</p></div>`}
            </section>
          </div>
        </div>

        <div class="dashboard-lower-grid">
          <section class="section-card">
            <div class="section-heading"><div><p class="eyebrow">Viewing activity</p><h4>Recent rating rhythm</h4><p class="chart-description">Ratings grouped by the dates recorded in your account.</p></div><span class="result-count">${history.length} entries</span></div>
            ${history.length ? `<div class="chart-frame chart-frame-short"><canvas id="dash-history-chart" aria-label="Your viewing activity" role="img"></canvas></div>` : renderEmpty('Your journey starts here', 'Rate movies to see your viewing activity take shape.', '<button class="btn btn-outline btn-sm" data-view-trigger="movies">Explore Movies</button>')}
          </section>
          <section class="section-card">
            <div class="section-heading"><div><p class="eyebrow">Recently watched</p><h4>Keep your taste current</h4><p class="chart-description">Your latest rated titles, straight from history.</p></div><button class="btn btn-ghost btn-sm" type="button" data-view-trigger="history">View all <i class="fa-solid fa-arrow-right"></i></button></div>
            ${history.length ? `<div class="mini-movie-row">${history.slice(0, 4).map(item => `<article class="mini-movie-item"><div class="activity-poster ${genreClass(item.genre)}"><i class="fa-solid fa-film"></i></div><div><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.genre || 'General')} · ${formatDate(item.timestamp)}</span></div></article>`).join('')}</div>` : renderEmpty('No rated titles yet', 'Your recent activity will appear here.')}
          </section>
        </div>

        <div class="dashboard-detail-grid">
          <section class="section-card">
            <div class="section-heading"><div><p class="eyebrow">Your ranking</p><h4>Favorite genres</h4></div></div>
            ${favoriteGenres.length ? `<div class="genre-ranking">${favoriteGenres.slice(0, 5).map((item, index) => `<div class="genre-rank-row"><span class="genre-rank-number">${String(index + 1).padStart(2, '0')}</span><strong>${escapeHtml(item.genre)}</strong><span class="genre-rank-track"><i style="width:${Math.max(8, Math.round((item.count / favoriteGenres[0].count) * 100))}%"></i></span><span class="genre-rank-count">${item.count}</span></div>`).join('')}</div>` : renderEmpty('Your genre profile is building', 'Rate movies to reveal your favorites.')}
          </section>
          <section class="section-card">
            <div class="section-heading"><div><p class="eyebrow">Recent activity</p><h4>What you have done</h4></div></div>
            ${history.length ? `<div class="activity-list dashboard-activity-list">${history.slice(0, 4).map(item => `<article class="activity-item"><div class="activity-poster ${genreClass(item.genre)}"><i class="fa-solid fa-star"></i></div><div class="activity-copy"><strong>Rated ${escapeHtml(item.title)}</strong><span>${formatDate(item.timestamp)} · ${escapeHtml(item.genre || 'General')}</span></div><span class="rating-chip"><i class="fa-solid fa-star"></i> ${formatRating(item.rating)}</span></article>`).join('')}</div>` : renderEmpty('No recent activity', 'Rate or save titles to start your activity feed.')}
          </section>
          <section class="section-card insight-panel">
            <span class="eyebrow">AURA insight</span><h4>Personalized, evidence-based</h4>
            ${analytics ? renderInsightList(analytics, { activeDays, mostCommonRating: null }) : renderEmpty('Your insight is forming', 'Rate movies to reveal patterns.')}
          </section>
        </div>

        <section class="section-card dashboard-discovery">
          <div class="section-heading"><div><p class="eyebrow">Discovery</p><h4>Explore more</h4><p class="chart-description">Jump into live catalog views powered by the data already in AURA.</p></div></div>
          <div class="discovery-actions"><button class="discovery-link" type="button" data-view-trigger="recommendations"><i class="fa-solid fa-wand-sparkles"></i><span><strong>Popular in your genres</strong><small>Personal matches</small></span><i class="fa-solid fa-arrow-right"></i></button><button class="discovery-link" type="button" data-view-trigger="movies"><i class="fa-solid fa-star"></i><span><strong>Highly rated</strong><small>Browse the catalog</small></span><i class="fa-solid fa-arrow-right"></i></button><button class="discovery-link" type="button" data-view-trigger="genres"><i class="fa-solid fa-layer-group"></i><span><strong>New discoveries</strong><small>Explore by genre</small></span><i class="fa-solid fa-arrow-right"></i></button></div>
        </section>

        <!-- System health (subtle, not prominent) -->
        <section class="section-card section-card-muted">
          <h4><i class="fa-solid fa-server"></i> System Health</h4>
          <div class="health-row">
            <span class="health-item"><span class="health-dot dot-green"></span> Recommendation Engine</span>
            <span class="health-item"><span class="health-dot dot-green"></span> Data Pipeline</span>
            <span class="health-item" id="drift-health-item">
              <span class="health-dot" id="drift-dot"></span> Drift Monitor
            </span>
          </div>
        </section>
      </div>`;

    // Wire nav triggers
    page.querySelectorAll('[data-view-trigger]').forEach(btn =>
      btn.addEventListener('click', () => setActiveView(btn.dataset.viewTrigger)));

    // Attach movie card events
    const grid = page.querySelector('.movie-grid');
    if (grid) attachMovieCardEvents(grid);
    // Render charts after DOM paint
    requestAnimationFrame(() => {
      if (analytics?.favorite_genres?.length) {
        renderGenreBarChart('dash-genres-chart', analytics.favorite_genres);
      }
      if (analytics?.rating_distribution && totalRatings > 0) {
        renderRatingDistChart('dash-dist-chart', analytics.rating_distribution);
      }
      if (history.length) renderHistoryChart('dash-history-chart', history);
      // Update drift dot
      const driftStatus = state.metrics?.drift_status || 'Healthy';
      const dot = document.getElementById('drift-dot');
      const item = document.getElementById('drift-health-item');
      if (dot && item) {
        if (driftStatus === 'Drifted') {
          dot.className = 'health-dot dot-red';
          item.querySelector('span:last-child')?.remove();
          item.append(' Drift Detected');
        } else {
          dot.className = 'health-dot dot-green';
        }
      }
    });
    page.querySelector('[data-refresh-dashboard]')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      button.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Refreshing';
      await loadRecommendations();
      await renderHomePage();
    });

  } else {
    // Guest: premium public home/auth experience
    const previewMovies = state.movies.slice(0, 3);
    page.innerHTML = `
      <div class="landing-shell">
        <header class="landing-nav">
          <div class="landing-brand">
            <span class="landing-brand-mark"><i class="fa-solid fa-wand-sparkles"></i></span>
            <span class="landing-brand-name">AURA</span>
          </div>
          <nav class="landing-nav-links" aria-label="Main navigation">
            <a href="#home">Home</a>
            <a href="#discover">Discover</a>
            <a href="#how-it-works">How It Works</a>
            <a href="#features">Features</a>
          </nav>
          <div class="landing-nav-actions">
            <button class="btn btn-secondary btn-sm" type="button" data-open-auth="login">Sign In</button>
            <button class="btn btn-primary btn-sm" type="button" data-open-auth="register">Get Started</button>
          </div>
        </header>

        <main class="landing-main" id="home">
          <section class="landing-hero">
            <div class="landing-hero-copy">
              <p class="landing-kicker">AURA</p>
              <h1>Personalized streaming built around your taste.</h1>
              <p class="landing-lead">Discover movies you'll love with intelligent recommendations, personalized insights, and a secure private experience.</p>
              <div class="hero-actions">
                <button class="btn btn-primary btn-lg" type="button" data-open-auth="register">
                  <i class="fa-solid fa-user-plus"></i> Get Started
                </button>
                <button class="btn btn-secondary btn-lg" type="button" data-open-auth="login">
                  <i class="fa-solid fa-right-to-bracket"></i> Sign In
                </button>
              </div>
              <div class="trust-row">
                <span><i class="fa-solid fa-shield-halved"></i> Secure account</span>
                <span><i class="fa-solid fa-wand-sparkles"></i> Smart discovery</span>
                <span><i class="fa-solid fa-chart-line"></i> Personal insights</span>
              </div>
            </div>

            <div class="hero-preview-panel" aria-label="AURA product preview">
              <div class="hero-preview-head">
                <span class="dot dot-red"></span>
                <span class="dot dot-yellow"></span>
                <span class="dot dot-green"></span>
              </div>
              <div class="hero-preview-body">
                <div class="preview-card preview-card-main">
                  <div class="preview-badge">For you</div>
                  <h3>Midnight Escape</h3>
                  <p>Psychological thriller · 4.7/5</p>
                </div>
                <div class="preview-grid">
                  <div class="mini-stat">
                    <span>Favorite genres</span>
                    <strong>Drama</strong>
                  </div>
                  <div class="mini-stat">
                    <span>Watchlist</span>
                    <strong>12 saved</strong>
                  </div>
                  <div class="mini-stat">
                    <span>Avg. rating</span>
                    <strong>4.2</strong>
                  </div>
                  <div class="mini-stat">
                    <span>History</span>
                    <strong>28 titles</strong>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section class="content-section" id="features">
            <div class="section-heading">
              <p class="section-kicker">Why AURA?</p>
              <h2>Personalized entertainment, designed around your taste.</h2>
            </div>
            <div class="feature-grid">
              <article class="feature-card">
                <div class="feature-icon"><i class="fa-solid fa-brain"></i></div>
                <h3>AI-Powered Recommendations</h3>
                <p>Discover movies based on your unique viewing preferences.</p>
              </article>
              <article class="feature-card">
                <div class="feature-icon"><i class="fa-solid fa-user-check"></i></div>
                <h3>Personalized Experience</h3>
                <p>Your recommendations evolve with every interaction and rating.</p>
              </article>
              <article class="feature-card">
                <div class="feature-icon"><i class="fa-solid fa-chart-pie"></i></div>
                <h3>Smart Analytics</h3>
                <p>Understand your movie taste through meaningful viewing insights.</p>
              </article>
              <article class="feature-card">
                <div class="feature-icon"><i class="fa-solid fa-heart"></i></div>
                <h3>Watchlist</h3>
                <p>Keep track of the titles you want to revisit or discover next.</p>
              </article>
              <article class="feature-card">
                <div class="feature-icon"><i class="fa-solid fa-clock-rotate-left"></i></div>
                <h3>Viewing History</h3>
                <p>Reference your activity and keep your entertainment journey organized.</p>
              </article>
              <article class="feature-card">
                <div class="feature-icon"><i class="fa-solid fa-compass-drafting"></i></div>
                <h3>Intelligent Discovery</h3>
                <p>Explore movies across genres and moods that match your interests.</p>
              </article>
            </div>
          </section>

          <section class="content-section" id="how-it-works">
            <div class="section-heading center">
              <p class="section-kicker">How AURA works</p>
              <h2>Three simple steps to better recommendations.</h2>
            </div>
            <div class="process-grid">
              <article class="process-item">
                <span class="process-number">01</span>
                <h3>Create your profile</h3>
                <p>Create a secure personal account and personalize your experience.</p>
              </article>
              <article class="process-item">
                <span class="process-number">02</span>
                <h3>Explore & rate</h3>
                <p>Browse movies and interact with titles that match your tastes.</p>
              </article>
              <article class="process-item">
                <span class="process-number">03</span>
                <h3>Get personalized recommendations</h3>
                <p>AURA learns from your preferences and surfaces content you are likely to enjoy.</p>
              </article>
            </div>
          </section>

          <section class="content-section" id="discover">
            <div class="section-heading">
              <p class="section-kicker">Your taste. Your discovery.</p>
              <h2>A personalized viewing experience built around what you enjoy.</h2>
            </div>
            <div class="taste-grid">
              <div class="taste-card">
                <span class="taste-label">Your preferences</span>
                <p>Every rating and interaction helps refine your profile.</p>
              </div>
              <div class="taste-card">
                <span class="taste-label">Your interactions</span>
                <p>Movies you rate, save, and revisit shape future suggestions.</p>
              </div>
              <div class="taste-card">
                <span class="taste-label">Recommendation intelligence</span>
                <p>Personalized suggestions are generated from live user behavior and taste signals.</p>
              </div>
              <div class="taste-card">
                <span class="taste-label">Personalized movies</span>
                <p>Discover titles that align with your mood, genre preference, and viewing habits.</p>
              </div>
            </div>
          </section>

          <section class="content-section analytics-preview">
            <div class="section-heading">
              <p class="section-kicker">Understand your movie taste</p>
              <h2>Analytics preview</h2>
            </div>
            <div class="analytics-preview-panel">
              <div class="analytics-panel-left">
                <div class="mini-chart-card">
                  <span>Favorite Genres</span>
                  <div class="mini-bars">
                    <i style="--bar:72%"></i>
                    <i style="--bar:58%"></i>
                    <i style="--bar:82%"></i>
                    <i style="--bar:66%"></i>
                  </div>
                </div>
                <div class="mini-chart-card">
                  <span>Rating Activity</span>
                  <div class="sparkline"><span></span></div>
                </div>
              </div>
              <div class="analytics-panel-right">
                <div class="insight-stack">
                  <div>
                    <small>Total ratings</small>
                    <strong>24</strong>
                  </div>
                  <div>
                    <small>Average rating</small>
                    <strong>4.3</strong>
                  </div>
                  <div>
                    <small>Favorite genre</small>
                    <strong>Drama</strong>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section class="content-section">
            <div class="section-heading">
              <p class="section-kicker">Recommendations made for you</p>
              <h2>Curated picks for your next watch.</h2>
            </div>
            <div class="recommend-grid">
              ${previewMovies.length ? previewMovies.map(movie => `
                <article class="movie-mini-card">
                  <div class="movie-mini-art ${genreClass(movie.genre)}"></div>
                  <div class="movie-mini-meta">
                    <h3>${escapeHtml(movie.title || 'Movie')}</h3>
                    <p>${escapeHtml(movie.genre || 'General')} · ${escapeHtml(String(movie.year || ''))}</p>
                  </div>
                </article>
              `).join('') : `
                <article class="movie-mini-card placeholder">
                  <div class="movie-mini-art placeholder-art"></div>
                  <div class="movie-mini-meta">
                    <h3>Discover titles</h3>
                    <p>Movie recommendations appear after sign in.</p>
                  </div>
                </article>
              `}
            </div>
          </section>

          <section class="content-section trust-section">
            <div class="security-panel">
              <div>
                <p class="section-kicker">Your experience. Your data.</p>
                <h2>Your personalized recommendations, watchlist, history, and insights are available inside your secure account.</h2>
              </div>
              <button class="btn btn-primary btn-lg" type="button" data-open-auth="register">Create your account</button>
            </div>
          </section>

          <section class="content-section cta-section">
            <div class="cta-panel">
              <div>
                <p class="section-kicker">Ready to discover your next favorite?</p>
                <h2>Create your AURA profile and start building your personalized movie experience.</h2>
              </div>
              <div class="cta-actions">
                <button class="btn btn-primary btn-lg" type="button" data-open-auth="register">Create Your Account</button>
                <button class="btn btn-secondary btn-lg" type="button" data-open-auth="login">Sign In</button>
              </div>
            </div>
          </section>
        </main>

        <footer class="landing-footer">
          <div class="footer-brand">
            <div class="landing-brand">
              <span class="landing-brand-mark"><i class="fa-solid fa-wand-sparkles"></i></span>
              <span class="landing-brand-name">AURA</span>
            </div>
            <p>Personalized OTT Recommendation System</p>
          </div>
          <div class="footer-links">
            <div>
              <h4>Product</h4>
              <a href="#discover">Discover</a>
              <a href="#features">Recommendations</a>
              <a href="#discover">Analytics</a>
            </div>
            <div>
              <h4>Account</h4>
              <button type="button" data-open-auth="login">Login</button>
              <button type="button" data-open-auth="register">Register</button>
              <button type="button">Privacy</button>
            </div>
          </div>
        </footer>
      </div>`;

    page.querySelectorAll('[data-open-auth]').forEach(b =>
      b.addEventListener('click', () => openAuthModal(b.dataset.openAuth)));
  }
}

function bindApplicationEvents() {
  ui.navButtons.forEach(btn => btn.addEventListener('click', () => setActiveView(btn.dataset.view)));
  ui.authOpenBtn?.addEventListener('click', () => openAuthModal('login'));
  ui.authLogoutBtn?.addEventListener('click', performLogout);
  ui.sidebarLogoutBtn?.addEventListener('click', performLogout);
  ui.loginForm?.addEventListener('submit', submitLogin);
  ui.registerForm?.addEventListener('submit', submitRegister);
  ui.loginTab?.addEventListener('click', () => openAuthModal('login'));
  ui.registerTab?.addEventListener('click', () => openAuthModal('register'));
  document.getElementById('switch-to-register')?.addEventListener('click', () => openAuthModal('register'));
  document.getElementById('switch-to-login')?.addEventListener('click', () => openAuthModal('login'));
  ui.authModalClose?.addEventListener('click', closeAuthModal);
  ui.authModal?.addEventListener('click', event => {
    if (event.target === ui.authModal) closeAuthModal();
  });
  ui.movieModalClose?.addEventListener('click', closeMovieModal);
  ui.ratingClose?.addEventListener('click', closeRatingModal);
  ui.ratingCancel?.addEventListener('click', closeRatingModal);
  ui.ratingSubmit?.addEventListener('click', submitRating);
  ui.starButtons.forEach(button => button.addEventListener('click', () => {
    state.ratingSelection = Number(button.dataset.star);
    ui.ratingValueDisplay.textContent = String(state.ratingSelection);
    ui.starButtons.forEach(item => item.classList.toggle('selected', Number(item.dataset.star) <= state.ratingSelection));
  }));
  ui.mobileToggle?.addEventListener('click', () => ui.sidebar?.classList.toggle('open'));
  bindPasswordToggles();
}

async function initializeApplication() {
  resolveUI();
  bindApplicationEvents();
  await checkSession();
  await refreshHealthStatus();
  await fetchMovies().catch(() => null);
  if (state.user) {
    await Promise.all([loadUserAnalytics(), loadRecommendations()]);
  }
  setActiveView(state.user ? 'dashboard' : 'home');
}

document.addEventListener('DOMContentLoaded', initializeApplication);
