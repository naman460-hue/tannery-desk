import { api } from '../api.js';
import { h, mount, wire, loading, errorBox, empty, pill, inr, num, fdate, fdatetime, fld, sel, openModal, confirmBox, toast } from '../ui.js';
import { dataTable } from '../table.js';

const TABS = [['overview', 'Overview'], ['factories', 'Factories'], ['users', 'Users'], ['rfqs', 'RFQs'], ['orders', 'Orders'], ['payments', 'Payments'], ['products', 'Products'], ['disputes', 'Disputes'], ['reports', 'Reports']];
const stat = (n, label, hot, to) => h`<a class="card stat ${hot && Number(n) ? 'hot' : ''}" href="#/admin/${to}" style="text-decoration:none;color:inherit"><b>${n}</b><span>${label}</span></a>`;
const RFQ_STATUS = [['SUBMITTED', 'Submitted'], ['MATCHING', 'Factory matching'], ['QUOTATION_RECEIVED', 'Quotation received'], ['ORDER_CREATED', 'Order created'], ['CANCELLED', 'Cancelled']];
const VERIF = [['PENDING', 'Pending'], ['VERIFIED', 'Verified'], ['REJECTED', 'Rejected'], ['SUSPENDED', 'Suspended']];

function factoryModal(f, reload) {
  const m = openModal(f.name, h`<p>${pill(f.verification_status)} <span class="mute small">${f.owner_email}</span></p>
    <dl class="facts"><dt>Location</dt><dd>${[f.city, f.state].filter(Boolean).join(', ') || '—'}</dd><dt>Contact</dt><dd>${f.contact_name || '—'} · ${f.contact_phone || '—'}<br>${f.contact_email || ''}</dd><dt>Leather types</dt><dd>${(f.leather_types || []).join(', ') || '—'}</dd><dt>Applications</dt><dd>${(f.applications || []).join(', ') || '—'}</dd>
    <dt>Certifications</dt><dd>${(f.certifications || []).join(', ') || '—'}</dd><dt>Minimum order</dt><dd>${f.min_order_quantity ? num(f.min_order_quantity) : '—'}</dd><dt>Capacity / month</dt><dd>${f.production_capacity ? num(f.production_capacity) : '—'}</dd><dt>Lead time</dt><dd>${f.typical_lead_time_days ? f.typical_lead_time_days + ' days' : '—'}</dd></dl>
    ${f.description ? h`<p style="margin-top:10px">${f.description}</p>` : ''}${f.documents.length ? h`<p>${f.documents.map((d) => h`<button class="btn sm ghost" data-dl="${d.download_url}" data-name="${d.original_name}">${d.title}</button> `)}</p>` : h`<p class="mute small">No documents uploaded.</p>`}
    ${f.verification_note ? h`<p class="small mute">Last note: ${f.verification_note}</p>` : ''}${verifyButtons(f)}`);
  wire(m, verifyHandlers(reload, m));
}
const verifyButtons = (f) => h`<div class="form-actions">${f.verification_status !== 'VERIFIED' ? h`<button class="btn gold" data-act="verify" data-id="${f.id}" data-status="VERIFIED">${f.verification_status === 'PENDING' ? 'Approve' : 'Verify again'}</button>` : ''}${f.verification_status === 'PENDING' ? h`<button class="btn ghost danger" data-act="verify" data-id="${f.id}" data-status="REJECTED">Reject</button>` : ''}${f.verification_status === 'VERIFIED' ? h`<button class="btn ghost danger" data-act="verify" data-id="${f.id}" data-status="SUSPENDED">Suspend</button>` : ''}</div>`;
function verifyHandlers(reload, parentModal) {
  return {
    verify: async (b) => {
      const status = b.dataset.status;
      if (status === 'VERIFIED') { await api.post(`/factories/admin/${b.dataset.id}/verification/`, { status }); toast('Factory approved.'); if (parentModal) parentModal.close(); reload(); return; }
      const m = openModal(status === 'REJECTED' ? 'Reject factory' : 'Suspend factory', h`<form data-form="note" novalidate><label>Reason <span class="opt-note">(the factory will see this)</span><textarea name="note" rows="3" maxlength="300"></textarea></label><div class="form-actions"><button class="btn danger" type="submit">${status === 'REJECTED' ? 'Reject' : 'Suspend'}</button><button class="btn ghost" type="button" data-close>Cancel</button></div></form>`);
      wire(m, { note: async (f, d) => { await api.post(`/factories/admin/${b.dataset.id}/verification/`, { status, note: d.note }); m.close(); if (parentModal) parentModal.close(); toast('Factory updated.'); reload(); } });
    },
  };
}

export async function adminDashboard(page, ctx) {
  const tab = ctx.params[0] || 'overview';
  mount(page, h`<div class="head"><h1>Admin dashboard</h1></div><div class="opts" role="tablist">${TABS.map(([k, l]) => h`<a class="opt ${tab === k ? 'on' : ''}" role="tab" href="#/admin/${k}">${l}</a>`)}</div><div id="tab"></div>`);
  const el = page.querySelector('#tab');
  let ctl = null;
  let rows = [];
  const keep = (d) => { rows = d.results; };
  const handlers = { retry: () => location.reload() };

  if (tab === 'overview') {
    mount(el, loading('Loading overview…'));
    try {
      const s = await api.get('/dashboard/');
      mount(el, h`${s.pending_factories ? h`<div class="next"><strong>${s.pending_factories} factor${s.pending_factories === 1 ? 'y is' : 'ies are'} waiting for verification.</strong><a class="btn gold" href="#/admin/factories?status=PENDING">Review Pending Factories</a></div>` : ''}
        ${s.rfqs_without_factory ? h`<div class="next"><strong>${s.rfqs_without_factory} RFQ${s.rfqs_without_factory === 1 ? ' has' : 's have'} no matching factory. Please assign one.</strong><a class="btn" href="#/admin/rfqs">Open RFQs</a></div>` : ''}
        <div class="stats">${stat(s.total_clients, 'Total clients', false, 'users')}${stat(s.total_factories, 'Total factories', false, 'factories')}${stat(s.active_rfqs, 'Active RFQs', false, 'rfqs')}${stat(s.active_orders, 'Active orders', false, 'orders')}${stat(s.completed_orders, 'Completed orders', false, 'orders')}${stat(s.pending_factories, 'Pending verification', true, 'factories')}${stat(inr(s.payments_total), `Payments received (${s.payments_count})`, false, 'payments')}${stat(s.open_disputes, 'Open disputes', true, 'disputes')}</div>
        <h2>Recent activity</h2>${s.recent_activities.length ? h`<div class="card"><ul class="updates">${s.recent_activities.map((a) => h`<li>${a.action}<br><span class="small mute">${a.actor} · ${fdatetime(a.created_at)}</span></li>`)}</ul></div>` : empty('No activity yet.')}`);
    } catch (err) { mount(el, errorBox(err)); }
  } else if (tab === 'factories') {
    const init = (ctx.query.status || '');
    ctl = dataTable(el, { endpoint: '/factories/admin/', search: 'Search factories', loading: 'Loading factories…', empty: 'No factories yet.', onLoaded: keep,
      filters: [{ key: 'status', label: 'All statuses', options: VERIF }],
      columns: [['Factory', (f) => h`<strong>${f.name}</strong>`], ['Location', (f) => [f.city, f.state].filter(Boolean).join(', ') || '—'], ['Owner', (f) => f.owner_email], ['Profile', (f) => pill(f.is_profile_complete ? 'VERIFIED' : 'PENDING', f.is_profile_complete ? 'Complete' : 'Incomplete')], ['Rating', (f) => (Number(f.rating) ? f.rating : '—')], ['Status', (f) => pill(f.verification_status)],
        ['', (f) => h`<div class="cell-actions"><button class="btn sm ghost" data-act="view" data-id="${f.id}">View</button>${f.verification_status === 'PENDING' ? h`<button class="btn sm gold" data-act="verify" data-id="${f.id}" data-status="VERIFIED">Approve</button><button class="btn sm ghost danger" data-act="verify" data-id="${f.id}" data-status="REJECTED">Reject</button>` : f.verification_status === 'VERIFIED' ? h`<button class="btn sm ghost danger" data-act="verify" data-id="${f.id}" data-status="SUSPENDED">Suspend</button>` : h`<button class="btn sm ghost" data-act="verify" data-id="${f.id}" data-status="VERIFIED">Verify</button>`}</div>`]] });
    if (init) { const s = el.querySelector('[data-filter=status]'); if (s) { s.value = init; s.dispatchEvent(new Event('change', { bubbles: true })); } }
    Object.assign(handlers, verifyHandlers(() => ctl.reload()), { view: (b) => factoryModal(rows.find((f) => String(f.id) === b.dataset.id), () => ctl.reload()) });
  } else if (tab === 'users') {
    ctl = dataTable(el, { endpoint: '/auth/admin/users/', search: 'Search name, email or company', loading: 'Loading users…', empty: 'No users.', onLoaded: keep,
      filters: [{ key: 'role', label: 'All roles', options: [['CLIENT', 'Clients'], ['FACTORY', 'Factories'], ['ADMIN', 'Admins']] }, { key: 'active', label: 'Active and suspended', options: [['true', 'Active'], ['false', 'Suspended']] }],
      columns: [['Name', (u) => h`<strong>${u.name}</strong>${u.is_demo ? h` <span class="demo">demo</span>` : ''}`], ['Company', (u) => u.company_name || '—'], ['Email', (u) => u.email], ['Role', (u) => u.role.toLowerCase()], ['Joined', (u) => fdate(u.created_at)], ['Status', (u) => pill(u.is_active ? 'VERIFIED' : 'SUSPENDED', u.is_active ? 'Active' : 'Suspended')],
        ['', (u) => (u.role === 'ADMIN' ? '' : h`<button class="btn sm ghost ${u.is_active ? 'danger' : ''}" data-act="active" data-id="${u.id}" data-to="${u.is_active ? 'false' : 'true'}">${u.is_active ? 'Suspend' : 'Reactivate'}</button>`)]] });
    handlers.active = async (b) => {
      const on = b.dataset.to === 'true';
      if (!on && !(await confirmBox('Suspend this user?', 'They will be signed out and unable to sign in until reactivated.', 'Suspend', true))) return;
      await api.post(`/auth/admin/users/${b.dataset.id}/set-active/`, { is_active: on }); toast(on ? 'User reactivated.' : 'User suspended.'); ctl.reload();
    };
  } else if (tab === 'rfqs') {
    ctl = dataTable(el, { endpoint: '/rfqs/', search: 'Search RFQs', loading: 'Loading RFQs…', empty: 'No RFQs yet.', filters: [{ key: 'status', label: 'All statuses', options: RFQ_STATUS }], rowClass: (r) => ((r.matches || []).length ? '' : 'best'),
      columns: [['RFQ', (r) => h`<a href="#/rfqs/${r.id}"><strong>${r.number}</strong></a>`], ['Client', (r) => r.client.company_name || r.client.name], ['Requirement', (r) => r.title], ['Quantity', (r) => `${num(r.quantity)} ${r.unit_label}`], ['Factories', (r) => (r.matches || []).length || h`<span class="r">None</span>`], ['Quotes', (r) => r.quotation_count], ['Status', (r) => pill(r.status, r.status_label)], ['', (r) => h`<a class="btn sm ghost" href="#/rfqs/${r.id}">${(r.matches || []).length ? 'Open' : 'Assign'}</a>`]] });
  } else if (tab === 'orders') {
    ctl = dataTable(el, { endpoint: '/orders/', search: 'Search orders', loading: 'Loading orders…', empty: 'No orders yet.', filters: [{ key: 'bucket', label: 'All orders', options: [['active', 'Active'], ['production', 'In production'], ['completed', 'Completed']] }],
      columns: [['Order', (o) => h`<a href="#/orders/${o.id}"><strong>${o.number}</strong></a>`], ['Client', (o) => o.client_name], ['Factory', (o) => o.factory_name], ['Total', (o) => inr(o.total_amount)], ['Stage', (o) => pill(o.status, o.status_label)], ['Payment', (o) => pill(o.payment_status, o.payment_status_label)], ['', (o) => h`<a class="btn sm ghost" href="#/orders/${o.id}">Open</a>`]] });
  } else if (tab === 'payments') {
    ctl = dataTable(el, { endpoint: '/payments/', loading: 'Loading payments…', empty: 'No payments yet.', filters: [{ key: 'status', label: 'All statuses', options: [['PAID', 'Paid'], ['CREATED', 'Waiting'], ['FAILED', 'Failed']] }],
      columns: [['Receipt', (p) => p.receipt_number], ['Order', (p) => h`<a href="#/orders/${p.order}">${p.order_number}</a>`], ['Payer', (p) => p.payer_name], ['Type', (p) => p.purpose_label], ['Amount', (p) => inr(p.amount)], ['Status', (p) => pill(p.status, p.status_label)], ['Mode', (p) => (p.mode === 'SANDBOX' ? h`<span class="demo">sandbox</span>` : 'Razorpay')], ['Date', (p) => fdatetime(p.paid_at || p.created_at)]] });
  } else if (tab === 'products') {
    ctl = dataTable(el, { endpoint: '/products/admin/', search: 'Search products', loading: 'Loading products…', empty: 'No products yet.', onLoaded: keep,
      columns: [['Product', (p) => h`<strong>${p.name}</strong>`], ['Factory', (p) => p.factory.name], ['Type', (p) => `${p.leather_type} · ${p.finish}`], ['Application', (p) => p.application], ['MOQ', (p) => `${num(p.moq)} ${p.unit_label}`], ['Shown', (p) => pill(p.is_active ? 'VERIFIED' : 'PENDING', p.is_active ? 'Yes' : 'Hidden')], ['', (p) => h`<button class="btn sm ghost" data-act="show" data-id="${p.id}" data-to="${p.is_active ? 'false' : 'true'}">${p.is_active ? 'Hide' : 'Show'}</button>`]] });
    handlers.show = async (b) => { await api.patch(`/products/admin/${b.dataset.id}/`, { is_active: b.dataset.to === 'true' }); toast('Product updated.'); ctl.reload(); };
  } else if (tab === 'disputes') {
    ctl = dataTable(el, { endpoint: '/disputes/', loading: 'Loading disputes…', empty: 'No disputes. Great.', onLoaded: keep, filters: [{ key: 'status', label: 'All statuses', options: [['OPEN', 'Open'], ['UNDER_REVIEW', 'Under review'], ['RESOLVED', 'Resolved'], ['CLOSED', 'Closed']] }],
      columns: [['Order', (d) => h`<a href="#/orders/${d.order}">${d.order_number}</a>`], ['Raised by', (d) => `${d.raised_by_name} (${d.raised_by_role.toLowerCase()})`], ['Subject', (d) => d.subject], ['Date', (d) => fdate(d.created_at)], ['Status', (d) => pill(d.status, d.status_label)], ['', (d) => h`<button class="btn sm ghost" data-act="dispute" data-id="${d.id}">Review</button>`]] });
    handlers.dispute = (b) => {
      const d = rows.find((x) => String(x.id) === b.dataset.id);
      const m = openModal(`Dispute on ${d.order_number}`, h`<p><strong>${d.subject}</strong><br>${d.description}</p><p class="small mute">Raised by ${d.raised_by_name} on ${fdate(d.created_at)}</p>
        <form data-form="dstatus" novalidate>${sel('Status', 'status', [['OPEN', 'Open'], ['UNDER_REVIEW', 'Under review'], ['RESOLVED', 'Resolved'], ['CLOSED', 'Closed']], d.status, { blank: false })}<label>Resolution note<textarea name="resolution" rows="3" maxlength="2000">${d.resolution}</textarea></label><div class="form-actions"><button class="btn" type="submit">Save</button></div></form>`);
      wire(m, { dstatus: async (f, v) => { await api.patch(`/disputes/${d.id}/`, v); m.close(); toast('Dispute updated.'); ctl.reload(); } });
    };
  } else if (tab === 'reports') {
    mount(el, loading('Loading reports…'));
    try {
      const r = await api.get('/admin/reports/');
      const list = (obj) => (Object.keys(obj).length ? h`<table><tbody>${Object.entries(obj).map(([k, v]) => h`<tr><td>${k.replace(/_/g, ' ').toLowerCase()}</td><td class="right"><strong>${typeof v === 'object' ? `${v.count} · ${inr(v.total)}` : v}</strong></td></tr>`)}</tbody></table>` : h`<p class="mute">No data yet.</p>`);
      mount(el, h`<div class="grid"><div class="card"><h3>RFQs by status</h3>${list(r.rfq_by_status)}</div><div class="card"><h3>Orders by status</h3>${list(r.order_by_status)}</div><div class="card"><h3>Payments by status</h3>${list(r.payments_by_status)}</div><div class="card"><h3>Last 30 days</h3>${list(r.last_30_days)}</div></div>
        <h2 class="sec">Top factories (completed orders)</h2>${r.top_factories.length ? h`<div class="tbl"><table class="stack"><thead><tr><th>Factory</th><th>Orders</th><th>Value</th></tr></thead><tbody>${r.top_factories.map((t) => h`<tr><td data-label="Factory">${t.name}</td><td data-label="Orders">${t.orders}</td><td data-label="Value">${inr(t.value)}</td></tr>`)}</tbody></table></div>` : empty('No completed orders yet.')}`);
    } catch (err) { mount(el, errorBox(err)); }
  }
  wire(page, handlers);
}
