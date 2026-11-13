// Router, navigation and session handling.
import { api, session, restoreSession, signOut } from './api.js';
import { h, mount, toast, errorBox, loading, $ } from './ui.js';
import { homeView, newRequirementView } from './views/home.js';
import { catalogView } from './views/catalog.js';
import { loginView, registerView, forgotView, resetView, roleHome } from './views/auth.js';
import { clientDashboard } from './views/client.js';
import { rfqView } from './views/rfq.js';
import { orderView } from './views/order.js';
import { factoryDashboard, factoryProfileView, factoryProductsView } from './views/factory.js';
import { adminDashboard } from './views/admin.js';
import { profileView, notificationsView, searchView } from './views/account.js';

const ANY = ['CLIENT', 'FACTORY', 'ADMIN'];
const routes = [
  [/^\/?$/, homeView],
  [/^\/catalog$/, catalogView],
  [/^\/login$/, loginView],
  [/^\/admin-login$/, (p, c) => loginView(p, { admin: true })],
  [/^\/register$/, registerView],
  [/^\/forgot$/, forgotView],
  [/^\/reset-password$/, resetView],
  [/^\/new-requirement$/, newRequirementView],
  [/^\/search$/, searchView],
  [/^\/client$/, clientDashboard, ['CLIENT']],
  [/^\/rfqs\/(\d+)$/, rfqView, ANY],
  [/^\/orders\/(\d+)$/, orderView, ANY],
  [/^\/orders$/, (p) => { location.replace(roleHome(session.user)); }, ANY],
  [/^\/factory\/profile$/, factoryProfileView, ['FACTORY']],
  [/^\/factory\/products$/, factoryProductsView, ['FACTORY']],
  [/^\/factory(?:\/(new|relevant|quotes|orders))?$/, factoryDashboard, ['FACTORY']],
  [/^\/admin(?:\/(overview|factories|users|rfqs|orders|payments|products|disputes|reports))?$/, adminDashboard, ['ADMIN']],
  [/^\/profile$/, profileView, ANY],
  [/^\/notifications$/, notificationsView, ANY],
];

const app = document.getElementById('app');
const nav = document.getElementById('nav');
let unread = 0;

function parseHash() {
  const raw = location.hash.replace(/^#/, '') || '/';
  const [path, query = ''] = raw.split('?');
  return { path: path || '/', query: Object.fromEntries(new URLSearchParams(query)) };
}

function renderNav() {
  const { path } = parseHash();
  const u = session.user;
  const link = (to, label, cls = '') => h`<a href="#${to}" class="${cls} ${path === to || (to !== '/' && path.startsWith(to + '/')) ? 'on' : ''}">${label}</a>`;
  const bell = h`<a href="#/notifications" class="bell" aria-label="Notifications">🔔${unread ? h`<b>${unread}</b>` : ''}</a>`;
  const search = h`<form class="ns" role="search" data-search><input type="search" name="q" placeholder="Search…" aria-label="Search products, factories, RFQs and orders"></form>`;
  let links;
  if (!u) links = h`${link('/', 'Home')}${link('/catalog', 'Catalog')}${link('/login', 'Sign in')}${link('/register', 'Register', 'cta')}`;
  else if (u.role === 'CLIENT') links = h`${link('/client', 'Dashboard')}${link('/catalog', 'Catalog')}${link('/new-requirement', 'New requirement', 'cta')}${bell}${link('/profile', u.name.split(' ')[0])}`;
  else if (u.role === 'FACTORY') links = h`${link('/factory', 'Dashboard')}${link('/factory/products', 'My products')}${link('/factory/profile', 'Factory profile')}${bell}${link('/profile', u.name.split(' ')[0])}`;
  else links = h`${link('/admin', 'Admin')}${link('/catalog', 'Catalog')}${bell}${link('/profile', u.name.split(' ')[0])}`;
  mount(nav, h`<a class="logo" href="#/">Tannery Desk</a><button class="nl burger" aria-label="Menu" aria-expanded="false" data-burger>☰</button><div class="links">${search}${links}</div>`);
}

async function refreshUnread() {
  if (!session.user) { unread = 0; return; }
  try { unread = (await api.get('/notifications/unread-count/')).count; } catch (e) { return; }
  renderNav();
}

async function route() {
  nav.classList.remove('open');
  const { path, query } = parseHash();
  const hit = routes.find(([re]) => re.test(path));
  const page = document.createElement('div');
  app.replaceChildren(page);
  if (!hit) { mount(page, h`<div class="state"><h2>Page not found</h2><p><a href="#/">Go to the home page</a></p></div>`); renderNav(); return; }
  const [re, view, roles] = hit;
  if (roles) {
    if (!session.user) {
      sessionStorage.setItem('td_next', '#' + path + (location.hash.includes('?') ? '?' + location.hash.split('?')[1] : ''));
      location.hash = path.startsWith('/admin') ? '#/admin-login' : '#/login';
      return;
    }
    if (!roles.includes(session.user.role)) { toast('That page is not available for your account.', 'error'); location.hash = roleHome(session.user); return; }
  }
  renderNav();
  window.scrollTo(0, 0);
  const ctx = { params: re.exec(path).slice(1), query, path };
  try { await view(page, ctx); } catch (err) { mount(page, errorBox(err, false)); }
  app.focus({ preventScroll: true });
  refreshUnread();
}

// ---- global listeners -----------------------------------------------------------------------------------
document.addEventListener('click', async (e) => {
  const dl = e.target.closest('[data-dl]');
  if (dl) {
    e.preventDefault();
    try { await api.download(dl.dataset.dl, dl.dataset.name); } catch (err) { toast(err.message, 'error'); }
    return;
  }
  if (e.target.closest('[data-burger]')) {
    const open = nav.classList.toggle('open');
    nav.querySelector('[data-burger]').setAttribute('aria-expanded', String(open));
    return;
  }
  if (e.target.closest('nav a')) nav.classList.remove('open');
});
document.addEventListener('submit', (e) => {
  const f = e.target.closest('form[data-search]');
  if (!f) return;
  e.preventDefault();
  const q = new FormData(f).get('q').trim();
  if (q) location.hash = '#/search?q=' + encodeURIComponent(q);
});
window.addEventListener('hashchange', route);
window.addEventListener('td:session', () => { unread = 0; renderNav(); refreshUnread(); });
window.addEventListener('td:notifications', refreshUnread);
window.addEventListener('td:signedout', () => {
  toast('Your session has expired. Please sign in again.', 'error');
  renderNav();
  const { path } = parseHash();
  if (routes.find(([re, , roles]) => roles && re.test(path))) { sessionStorage.setItem('td_next', location.hash); location.hash = '#/login'; }
});
setInterval(refreshUnread, 60000);

(async () => {
  mount(app, loading('Loading Tannery Desk…'));
  await restoreSession();
  renderNav();
  route();
})();
