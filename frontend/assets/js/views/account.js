import { api, session, signOut, getOptions } from '../api.js';
import { h, mount, raw, wire, loading, errorBox, empty, fld, toast, fdatetime } from '../ui.js';

export async function profileView(page) {
  const u = session.user;
  mount(page, h`<div class="head"><h1>My account</h1><button class="btn ghost" data-act="logout">Sign out</button></div>
    <div class="two"><form class="card" data-form="profile" novalidate><h2 style="font-size:1.2rem">Your details</h2><p class="mute small">${u.email} · ${u.role.toLowerCase()}${u.is_demo ? ' · demo account' : ''}</p>
      ${fld('Name', 'name', { value: u.name })}${fld('Phone', 'phone', { type: 'tel', value: u.phone })}${fld('Company', 'company_name', { value: u.company_name })}${fld('Address', 'address', { value: u.address })}${fld('City', 'city', { value: u.city })}${fld('State', 'state', { value: u.state })}
      ${u.role === 'CLIENT' ? h`${fld('GST number', 'gst_number', { value: u.client_profile && u.client_profile.gst_number, note: '(optional)' })}${fld('Industry', 'industry', { value: u.client_profile && u.client_profile.industry, note: '(optional)' })}` : ''}
      <div class="form-actions"><button class="btn" type="submit">Save details</button></div></form>
    <form class="card" data-form="password" novalidate><h2 style="font-size:1.2rem">Change password</h2>${fld('Current password', 'old_password', { type: 'password', attrs: 'autocomplete="current-password"' })}${fld('New password', 'new_password', { type: 'password', note: '(8+ characters)', attrs: 'autocomplete="new-password"' })}<div class="form-actions"><button class="btn" type="submit">Change password</button></div></form></div>`);
  wire(page, {
    logout: async () => { await signOut(); window.dispatchEvent(new Event('td:session')); location.hash = '#/'; },
    profile: async (form, d) => { session.user = await api.patch('/auth/me/', d); window.dispatchEvent(new Event('td:session')); toast('Details saved.'); },
    password: async (form, d) => { await api.post('/auth/change-password/', d); form.reset(); toast('Password changed.'); },
  });
}

export async function notificationsView(page) {
  async function load() {
    mount(page, loading('Loading notifications…'));
    try {
      const d = await api.get('/notifications/?page_size=50');
      mount(page, h`<div class="head"><h1>Notifications</h1>${d.results.some((n) => !n.is_read) ? h`<button class="btn ghost sm" data-act="all">Mark all as read</button>` : ''}</div>
        ${d.results.length ? h`<div class="stack">${d.results.map((n) => h`<div class="card" style="${n.is_read ? '' : 'border-color:var(--gold)'}"><strong>${n.title}</strong> ${n.is_read ? '' : h`<span class="tag v">new</span>`}<br>${n.message}<br><span class="small mute">${fdatetime(n.created_at)}</span>${n.link ? h` · <a href="${n.link}" data-act="open" data-id="${n.id}">Open</a>` : ''}</div>`)}</div>` : empty("You're all caught up. New notifications will appear here.")}`);
    } catch (err) { mount(page, errorBox(err)); }
  }
  wire(page, {
    retry: load,
    all: async () => { await api.post('/notifications/read-all/'); window.dispatchEvent(new Event('td:notifications')); load(); },
    open: async (b) => { try { await api.post(`/notifications/${b.dataset.id}/read/`); } catch (e) { /* ignore */ } window.dispatchEvent(new Event('td:notifications')); location.hash = b.getAttribute('href'); },
  });
  load();
}

export async function searchView(page, ctx) {
  const q = ctx.query.q || '';
  mount(page, h`<h1>Search</h1>${loading('Searching…')}`);
  try {
    const r = await api.get('/search/?q=' + encodeURIComponent(q));
    const group = (title, items, link) => (items.length ? h`<section class="sec"><h2>${title}</h2><div class="stack">${items.map((i) => h`<div class="card"><a href="${link(i)}"><strong>${i.name}</strong></a><br><span class="mute small">${i.sub}</span></div>`)}</div></section>` : '');
    const total = r.products.length + r.factories.length + r.rfqs.length + r.orders.length;
    mount(page, h`<h1>Search results</h1><p class="mute">${q.length < 2 ? 'Type at least 2 characters.' : `${total} result${total === 1 ? '' : 's'} for “${q}”`}</p>
      ${group('Leather products', r.products, () => '#/catalog')}${group('Factories', r.factories, () => '#/catalog')}${group('RFQs', r.rfqs, (i) => '#/rfqs/' + i.id)}${group('Orders', r.orders, (i) => '#/orders/' + i.id)}
      ${total === 0 && q.length >= 2 ? empty('Nothing found. Try a different word, or browse the catalog.') : ''}`);
  } catch (err) { mount(page, errorBox(err, false)); }
}
