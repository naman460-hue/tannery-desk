import { api, getOptions } from '../api.js';
import { h, mount, raw, wire, loading, errorBox, empty, pill, inr, num, fdate, fld, sel, openModal, confirmBox, toast, $ } from '../ui.js';
import { dataTable } from '../table.js';

const stat = (n, label, hot, tab) => h`<a class="card stat ${hot && n ? 'hot' : ''}" href="#/factory/${tab}" style="text-decoration:none;color:inherit"><b>${n}</b><span>${label}</span></a>`;

export async function factoryDashboard(page, ctx) {
  const tab = ctx.params[0] || 'new';
  mount(page, loading('Loading your dashboard…'));
  let s;
  try { s = await api.get('/dashboard/'); } catch (err) { mount(page, errorBox(err)); return; }
  const verified = s.verification_status === 'VERIFIED';
  const tabs = [['new', 'New RFQs'], ['relevant', 'Relevant RFQs'], ['quotes', 'Quotations'], ['orders', 'Orders']];
  mount(page, h`<div class="head"><h1>Factory dashboard</h1>${verified ? h`<a class="btn gold" href="#/factory/new">View New RFQs${s.new_rfqs ? ` (${s.new_rfqs})` : ''}</a>` : h`<a class="btn gold" href="#/factory/profile">Complete your profile</a>`}</div>
    ${s.verification_status === 'PENDING' ? h`<div class="banner warn"><strong>Your factory is waiting for verification.</strong> ${s.profile_complete ? 'The Tannery Desk team is reviewing your profile. You will be notified once it is approved.' : 'Please complete your profile and upload certificates so we can verify you faster.'} <a href="#/factory/profile">Open profile</a></div>` : ''}
    ${['REJECTED', 'SUSPENDED'].includes(s.verification_status) ? h`<div class="banner bad"><strong>Your factory is ${s.verification_status.toLowerCase()}.</strong> ${s.verification_note || ''} <a href="#/factory/profile">Update your profile</a></div>` : ''}
    ${verified && !s.profile_complete ? h`<div class="banner warn">Your profile is incomplete, so you may miss matching RFQs. <a href="#/factory/profile">Complete it now</a></div>` : ''}
    ${s.orders_needing_update ? h`<div class="next"><strong>${s.orders_needing_update} order${s.orders_needing_update > 1 ? 's are' : ' is'} paid and waiting for you to start production.</strong><a class="btn gold" href="#/factory/orders">Open orders</a></div>` : ''}
    <div class="stats">${stat(s.new_rfqs, 'New RFQs', true, 'new')}${stat(s.relevant_rfqs, 'Relevant RFQs', false, 'relevant')}${stat(s.submitted_quotations, 'Submitted quotations', false, 'quotes')}${stat(s.accepted_quotations, 'Accepted quotations', false, 'quotes')}${stat(s.active_orders, 'Active orders', false, 'orders')}${stat(s.production_orders, 'In production', false, 'orders')}${stat(s.completed_orders, 'Completed orders', false, 'orders')}</div>
    <div class="opts" role="tablist">${tabs.map(([k, l]) => h`<a class="opt ${tab === k ? 'on' : ''}" role="tab" href="#/factory/${k}">${l}</a>`)}</div><div id="tbl"></div>`);
  const el = page.querySelector('#tbl');
  const rfqCols = [['RFQ', (r) => h`<a href="#/rfqs/${r.id}"><strong>${r.number}</strong></a>`], ['Leather', (r) => r.title], ['Application', (r) => r.application], ['Quantity', (r) => `${num(r.quantity)} ${r.unit_label}`], ['Needed by', (r) => fdate(r.required_date)], ['Match', (r) => (r.my_match ? r.my_match.score + '/100' : '—')], ['Response', (r) => pill(r.my_match ? r.my_match.response : 'NEW')],
    ['', (r) => h`<div class="cell-actions"><a class="btn sm" href="#/rfqs/${r.id}">View & quote</a>${r.my_match && r.my_match.response === 'NEW' ? h`<button class="btn sm ghost" data-act="interest" data-id="${r.id}">Accept</button><button class="btn sm ghost danger" data-act="decline" data-id="${r.id}">Reject</button>` : ''}</div>`]];
  let ctl;
  if (tab === 'new') ctl = dataTable(el, { endpoint: '/rfqs/', params: { open: 1, response: 'NEW' }, search: 'Search RFQs', empty: 'No new RFQs right now. We will notify you when one matches your factory.', loading: 'Loading new RFQs…', columns: rfqCols });
  else if (tab === 'relevant') ctl = dataTable(el, { endpoint: '/rfqs/', params: { open: 1 }, search: 'Search RFQs', empty: 'No relevant RFQs yet.', loading: 'Loading RFQs…', columns: rfqCols });
  else if (tab === 'quotes') ctl = dataTable(el, { endpoint: '/quotations/', empty: 'You have not submitted any quotations yet.', loading: 'Loading your quotations…', filters: [{ key: 'status', label: 'All statuses', options: [['SUBMITTED', 'Submitted'], ['ACCEPTED', 'Accepted'], ['REJECTED', 'Rejected'], ['CLOSED', 'Closed'], ['WITHDRAWN', 'Withdrawn']] }],
    columns: [['RFQ', (q) => h`<a href="#/rfqs/${q.rfq}"><strong>${q.rfq_number}</strong></a>`], ['Requirement', (q) => q.rfq_title], ['Price', (q) => `${inr(q.price)} / ${q.unit_label}`], ['Total', (q) => inr(q.total_amount)], ['Lead time', (q) => q.lead_time_days + ' days'], ['Valid until', (q) => fdate(q.validity_date)], ['Status', (q) => pill(q.status)], ['', (q) => h`<a class="btn sm ghost" href="#/rfqs/${q.rfq}">${q.status === 'SUBMITTED' ? 'Edit' : 'Open'}</a>`]] });
  else ctl = dataTable(el, { endpoint: '/orders/', search: 'Search orders', empty: 'No orders yet. Orders appear when a client accepts your quotation.', loading: 'Loading orders…',
    filters: [{ key: 'bucket', label: 'All orders', options: [['active', 'Active'], ['production', 'In production'], ['completed', 'Completed']] }],
    columns: [['Order', (o) => h`<a href="#/orders/${o.id}"><strong>${o.number}</strong></a>`], ['Requirement', (o) => o.title], ['Buyer', (o) => o.client_name], ['Total', (o) => inr(o.total_amount)], ['Stage', (o) => pill(o.status, o.status_label)], ['Progress', (o) => o.progress_percent + '%'], ['Delivery', (o) => fdate(o.expected_delivery)], ['', (o) => h`<a class="btn sm ghost" href="#/orders/${o.id}">${o.status === 'PAYMENT_RECEIVED' ? 'Start production' : 'Update'}</a>`]] });
  wire(page, {
    interest: async (b) => { await api.post(`/rfqs/${b.dataset.id}/respond/`, { action: 'accept' }); toast('Marked as interested.'); ctl.reload(); },
    decline: (b) => {
      const m = openModal('Decline this RFQ', h`<form data-form="decline" novalidate><label>Reason <span class="opt-note">(optional)</span><textarea name="reason" rows="3" maxlength="300"></textarea></label><div class="form-actions"><button class="btn danger" type="submit">Decline RFQ</button><button class="btn ghost" type="button" data-close>Cancel</button></div></form>`);
      wire(m, { decline: async (f, d) => { await api.post(`/rfqs/${b.dataset.id}/respond/`, { action: 'decline', reason: d.reason }); m.close(); toast('RFQ declined.'); ctl.reload(); } });
    },
  });
}

export async function factoryProfileView(page) {
  const o = await getOptions();
  let f;
  async function load() {
    mount(page, loading('Loading your profile…'));
    try { f = await api.get('/factories/me/'); draw(); } catch (err) { mount(page, errorBox(err)); }
  }
  const checks = (name, list, chosen) => h`<div class="checks">${list.map((v) => h`<label class="check"><input type="checkbox" name="${name}" value="${v}" ${raw((chosen || []).includes(v) ? 'checked' : '')}>${v}</label>`)}</div>`;
  function draw() {
    mount(page, h`<div class="head"><h1>Factory profile</h1><div>${pill(f.verification_status)}</div></div>
      ${f.verification_status === 'PENDING' ? h`<div class="banner warn">Your profile is waiting for verification by the Tannery Desk team.</div>` : ''}
      ${['REJECTED', 'SUSPENDED'].includes(f.verification_status) ? h`<div class="banner bad">${f.verification_note || 'Please update your profile and contact support.'}</div>` : ''}
      ${f.verification_status === 'VERIFIED' ? h`<div class="banner ok">Your factory is verified. Keep your profile up to date to receive the best matching RFQs.</div>` : ''}
      <form class="card" data-form="profile" novalidate><h2 style="font-size:1.2rem">About your factory</h2><div class="fields">${fld('Factory name', 'name', { value: f.name })}${fld('Contact person', 'contact_name', { value: f.contact_name })}${fld('Contact phone', 'contact_phone', { type: 'tel', value: f.contact_phone })}${fld('Contact email', 'contact_email', { type: 'email', value: f.contact_email })}
        ${fld('Address', 'address', { value: f.address })}${fld('City', 'city', { value: f.city })}${fld('State', 'state', { value: f.state })}</div>
        <label>Short description<textarea name="description" rows="3">${f.description}</textarea></label>
        <h2 style="font-size:1.2rem;margin-top:20px">What you make</h2><label>Leather types</label>${checks('leather_types', o.leather_types, f.leather_types)}<label>Applications</label>${checks('applications', o.applications, f.applications)}<label>Colors</label>${checks('colors', o.colors.map((c) => c.name), f.colors)}<label>Certifications you hold</label>${checks('certifications', o.certifications, f.certifications)}
        <div class="fields" style="margin-top:12px">${fld('Thinnest you make (mm)', 'min_thickness', { type: 'number', value: f.min_thickness || '', attrs: 'step="0.1" min="0.1"' })}${fld('Thickest you make (mm)', 'max_thickness', { type: 'number', value: f.max_thickness || '', attrs: 'step="0.1" min="0.1"' })}${fld('Minimum order quantity', 'min_order_quantity', { type: 'number', value: f.min_order_quantity || '', attrs: 'min="1" step="any"' })}${fld('Monthly capacity', 'production_capacity', { type: 'number', value: f.production_capacity || '', attrs: 'min="1" step="any"' })}${fld('Typical lead time (days)', 'typical_lead_time_days', { type: 'number', value: f.typical_lead_time_days || '', attrs: 'min="1"' })}</div>
        <div class="form-actions"><button class="btn" type="submit">Save profile</button><a class="btn ghost" href="#/factory/products">Manage my products</a></div></form>
      <section class="sec"><h2>Certificates and documents</h2>${f.documents.length ? h`<div class="tbl"><table class="stack"><thead><tr><th>Title</th><th>Type</th><th>Added</th><th></th></tr></thead><tbody>${f.documents.map((d) => h`<tr><td data-label="Title">${d.title}</td><td data-label="Type">${d.kind.toLowerCase()}</td><td data-label="Added">${fdate(d.uploaded_at)}</td><td class="act"><div class="cell-actions"><button class="btn sm ghost" data-dl="${d.download_url}" data-name="${d.original_name}">Download</button><button class="btn sm ghost danger" data-act="deldoc" data-id="${d.id}">Remove</button></div></td></tr>`)}</tbody></table></div>` : empty('No documents uploaded yet.')}
        <form class="card" data-form="doc" novalidate style="margin-top:12px"><h3>Upload a document</h3><div class="fields">${sel('Type', 'kind', o.document_kinds.map((k) => [k, k.toLowerCase()]), 'CERTIFICATE', { blank: false })}${fld('Title', 'title', { attrs: 'placeholder="e.g. LWG Gold certificate"' })}</div>
        <label>File <span class="opt-note">(max ${o.max_upload_mb} MB: PDF, image, Word, Excel)</span><input type="file" name="file"></label><div class="form-actions"><button class="btn" type="submit">Upload</button></div></form></section>`);
  }
  wire(page, {
    retry: load,
    profile: async (form) => {
      const g = (n) => Array.from(form.querySelectorAll(`[name="${n}"]:checked`)).map((e) => e.value);
      const v = Object.fromEntries(new FormData(form));
      const num2 = (x) => (x === '' ? null : x);
      await api.patch('/factories/me/', { name: v.name, contact_name: v.contact_name, contact_phone: v.contact_phone, contact_email: v.contact_email, address: v.address, city: v.city, state: v.state, description: v.description,
        leather_types: g('leather_types'), applications: g('applications'), colors: g('colors'), certifications: g('certifications'),
        min_thickness: num2(v.min_thickness), max_thickness: num2(v.max_thickness), min_order_quantity: num2(v.min_order_quantity), production_capacity: num2(v.production_capacity), typical_lead_time_days: num2(v.typical_lead_time_days) });
      toast('Profile saved.');
      load();
    },
    doc: async (form) => {
      const fd = new FormData(form);
      if (!fd.get('title')) throw Object.assign(new Error('Please enter a title.'), { errors: { title: ['Please enter a title.'] } });
      if (!fd.get('file') || !fd.get('file').size) throw Object.assign(new Error('Please choose a file.'));
      await api.post('/factories/me/documents/', fd);
      toast('Document uploaded.');
      load();
    },
    deldoc: async (b) => { if (await confirmBox('Remove this document?', 'It will be deleted.', 'Remove', true)) { await api.del(`/factories/me/documents/${b.dataset.id}/`); toast('Document removed.'); load(); } },
  });
  load();
}

export async function factoryProductsView(page) {
  const o = await getOptions();
  let ctl;
  mount(page, h`<div class="head"><h1>My products</h1><button class="btn gold" data-act="add">Add a product</button></div><p class="mute">Products appear in the public catalog once your factory is verified.</p><div id="tbl"></div>`);
  const form = (p = {}) => h`<form data-form="product" novalidate><div class="fields">${fld('Product name', 'name', { value: p.name })}${sel('Leather type', 'leather_type', o.leather_types, p.leather_type)}${sel('Finish', 'finish', o.finishes, p.finish)}${sel('Application', 'application', o.applications, p.application)}${sel('Color', 'color', o.colors.map((c) => c.name), p.color)}
    ${fld('Thickness from (mm)', 'thickness_min', { type: 'number', value: p.thickness_min || '', attrs: 'step="0.1" min="0.1"' })}${fld('Thickness to (mm)', 'thickness_max', { type: 'number', value: p.thickness_max || '', attrs: 'step="0.1" min="0.1"' })}${fld('Minimum order quantity', 'moq', { type: 'number', value: p.moq || '', attrs: 'min="1" step="any"' })}
    ${sel('Unit', 'unit', o.units.map((u) => [u.value, u.label]), p.unit || 'SQ_FT', { blank: false })}${fld('Lead time (days)', 'lead_time_days', { type: 'number', value: p.lead_time_days || '', attrs: 'min="1" max="365"' })}</div>
    <label>Certifications</label><div class="checks">${o.certifications.map((c) => h`<label class="check"><input type="checkbox" name="certifications" value="${c}" ${raw((p.certifications || []).includes(c) ? 'checked' : '')}>${c}</label>`)}</div>
    <label>Description<textarea name="description" rows="3">${p.description || ''}</textarea></label><label class="check"><input type="checkbox" name="sample_available" ${raw(p.sample_available ? 'checked' : '')}> Sample available</label>
    <label>Photo <span class="opt-note">(optional, JPG/PNG/WebP)</span><input type="file" name="image" accept=".jpg,.jpeg,.png,.webp"></label><div class="form-actions"><button class="btn" type="submit">Save product</button><button class="btn ghost" type="button" data-close>Cancel</button></div></form>`;
  const open = (p) => {
    const m = openModal(p ? 'Edit product' : 'Add a product', form(p));
    wire(m, { product: async (f) => {
      const fd = new FormData();
      new FormData(f).forEach((v, k) => { if (k === 'certifications' || k === 'sample_available') return; if (v instanceof File && !v.size) return; fd.append(k, v); });
      f.querySelectorAll('[name=certifications]:checked').forEach((c) => fd.append('certifications', c.value));
      fd.append('sample_available', f.querySelector('[name=sample_available]').checked ? 'true' : 'false');
      if (p) await api.patch(`/products/mine/${p.id}/`, fd); else await api.post('/products/mine/', fd);
      m.close(); toast('Product saved.'); ctl.reload();
    } });
  };
  let rows = [];
  ctl = dataTable(page.querySelector('#tbl'), { endpoint: '/products/mine/', search: 'Search products', empty: 'You have not added any products yet.', loading: 'Loading your products…', onLoaded: (d) => { rows = d.results; },
    columns: [['Product', (p) => h`<strong>${p.name}</strong>`], ['Type', (p) => `${p.leather_type} · ${p.finish}`], ['Application', (p) => p.application], ['Thickness', (p) => p.thickness_display], ['MOQ', (p) => `${num(p.moq)} ${p.unit_label}`], ['Lead time', (p) => p.lead_time_days + ' days'], ['Shown in catalog', (p) => pill(p.is_active ? 'VERIFIED' : 'PENDING', p.is_active ? 'Yes' : 'Hidden')],
      ['', (p) => h`<div class="cell-actions"><button class="btn sm ghost" data-act="edit" data-id="${p.id}">Edit</button><button class="btn sm ghost" data-act="toggle" data-id="${p.id}">${p.is_active ? 'Hide' : 'Show'}</button><button class="btn sm ghost danger" data-act="del" data-id="${p.id}">Delete</button></div>`]] });
  wire(page, {
    add: () => open(null),
    edit: (b) => open(rows.find((p) => String(p.id) === b.dataset.id)),
    toggle: async (b) => { const p = rows.find((x) => String(x.id) === b.dataset.id); const fd = new FormData(); fd.append('is_active', p.is_active ? 'false' : 'true'); await api.patch(`/products/mine/${p.id}/`, fd); ctl.reload(); },
    del: async (b) => { if (await confirmBox('Delete this product?', 'It will be removed from the catalog.', 'Delete', true)) { await api.del(`/products/mine/${b.dataset.id}/`); toast('Product deleted.'); ctl.reload(); } },
  });
}
