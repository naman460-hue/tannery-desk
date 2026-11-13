// RFQ detail page for all three roles: client compares quotations, factory responds and quotes, admin oversees.
import { api, session, getOptions } from '../api.js';
import { h, mount, raw, wire, openModal, confirmBox, loading, errorBox, empty, pill, timeline, inr, num, fdate, fdatetime, fld, sel, toast, esc } from '../ui.js';
import { factoryModal, messagesPanel, stars } from '../shared.js';

const facts = (r) => h`<dl class="facts"><dt>Leather</dt><dd>${r.color} ${r.leather_type}${r.finish ? ', ' + r.finish : ''}</dd><dt>Application</dt><dd>${r.application}</dd><dt>Thickness</dt><dd>${Number(r.thickness_min)}–${Number(r.thickness_max)} mm</dd>
  <dt>Quantity</dt><dd>${num(r.quantity)} ${r.unit_label}</dd><dt>Target price</dt><dd>${r.target_price ? inr(r.target_price) + ' per unit' : 'Not specified'}</dd><dt>Needed by</dt><dd>${fdate(r.required_date)}</dd>
  <dt>Delivery to</dt><dd>${[r.delivery_city, r.delivery_state].filter(Boolean).join(', ') || r.client_city || '—'}</dd><dt>Certifications</dt><dd>${(r.required_certifications || []).join(', ') || 'None required'}</dd></dl>
  ${r.requirements ? h`<p style="margin-top:12px"><strong>Notes</strong><br>${r.requirements}</p>` : ''}
  ${r.attachments.length ? h`<p>${r.attachments.map((a) => h`<button class="btn sm ghost" data-dl="${a.download_url}" data-name="${a.original_name}">📎 ${a.original_name}</button> `)}</p>` : ''}`;

export async function rfqView(page, ctx) {
  const id = ctx.params[0];
  const role = session.user.role;
  const o = await getOptions();
  let rfq, quotes = [], mine = null;

  async function load() {
    mount(page, loading('Loading requirement…'));
    try {
      rfq = await api.get(`/rfqs/${id}/`);
      quotes = []; mine = null;
      if (role === 'FACTORY') { const q = await api.get(`/quotations/?rfq=${id}`); mine = q.results[0] || null; }
      else quotes = (await api.get(`/quotations/?rfq=${id}&page_size=50`)).results;
      draw();
    } catch (err) { mount(page, errorBox(err)); }
  }

  function draw() {
    const stageIdx = o.rfq_stages.findIndex((s) => s.value === rfq.status);
    const live = ['SUBMITTED', 'MATCHING', 'QUOTATION_RECEIVED'].includes(rfq.status);
    mount(page, h`<p class="small"><a href="${role === 'ADMIN' ? '#/admin/rfqs' : role === 'FACTORY' ? '#/factory' : '#/client'}">← Back to dashboard</a></p>
      <div class="head"><div><h1>${rfq.number}</h1><p class="mute" style="margin:0">${rfq.title}</p></div><div>${pill(rfq.status, rfq.status_label)}</div></div>
      ${rfq.status === 'CANCELLED' ? '' : timeline(o.rfq_stages.map((s) => s.label), stageIdx)}
      ${role === 'CLIENT' ? clientNext() : ''}
      <div class="two"><div class="card"><div class="head"><h2 style="font-size:1.2rem">Requirement</h2>${role === 'CLIENT' && ['SUBMITTED', 'MATCHING'].includes(rfq.status) && !quotes.length ? h`<button class="btn sm ghost" data-act="edit">Edit</button>` : ''}</div>${facts(rfq)}
        ${role !== 'FACTORY' && live ? h`<div class="form-actions"><button class="btn sm ghost danger" data-act="cancel">Cancel requirement</button></div>` : ''}</div>
        <div class="stack">${role === 'FACTORY' ? factorySide() : role === 'ADMIN' ? adminSide() : h`<div class="card"><h2 style="font-size:1.2rem">Status</h2><p>${rfq.status === 'ORDER_CREATED' ? 'An order was created from this requirement.' : rfq.status === 'QUOTATION_RECEIVED' ? 'Factories have sent quotations. Compare them below.' : rfq.status === 'CANCELLED' ? 'This requirement was cancelled.' : 'We are matching your requirement with suitable factories. You will be notified when a quotation arrives.'}</p></div>`}</div></div>
      ${role !== 'FACTORY' ? h`<section class="sec"><h2>Quotations</h2>${quotesTable()}</section>` : ''}
      <section class="sec" id="chat"></section>`);
    const chat = page.querySelector('#chat');
    if (role === 'FACTORY') messagesPanel(chat, { rfq: id });
    else if (role === 'CLIENT') messagesPanel(chat, { rfq: id }, quotes.filter((q) => q.status !== 'WITHDRAWN').map((q) => ({ id: q.factory.user_id, name: q.factory.name })).filter((f, i, a) => a.findIndex((x) => x.id === f.id) === i));
    else messagesPanel(chat, { rfq: id }, (rfq.matches || []).filter((m) => m.response === 'QUOTED').map((m) => ({ id: m.factory_user_id, name: m.factory_name })));
  }

  function clientNext() {
    const n = quotes.filter((q) => q.status === 'SUBMITTED').length;
    return n && rfq.status === 'QUOTATION_RECEIVED' ? h`<div class="next"><strong>You have ${n} quotation${n > 1 ? 's' : ''} to review.</strong><a class="btn gold" href="#/rfqs/${id}" data-act="goto-quotes">Compare quotations</a></div>` : '';
  }

  function quotesTable() {
    const rows = quotes.filter((q) => q.status !== 'WITHDRAWN');
    if (!rows.length) return empty(role === 'CLIENT' ? 'No quotations yet. We will notify you as soon as a factory responds.' : 'No quotations yet.');
    const open = rows.filter((q) => q.status === 'SUBMITTED');
    const cheapest = open.length ? Math.min(...open.map((q) => Number(q.price))) : null;
    const fastest = open.length ? Math.min(...open.map((q) => q.lead_time_days)) : null;
    return h`<div class="tbl"><table class="stack"><thead><tr><th>Factory</th><th>Price</th><th>MOQ</th><th>Lead time</th><th>Certification</th><th>Rating</th><th></th></tr></thead><tbody>${rows.map((q) => h`<tr class="${q.recommended ? 'best' : ''}">
      <td data-label="Factory"><button class="btn sm ghost" data-act="factory" data-id="${q.factory.id}">${q.factory.name}</button><br><span class="small mute">${q.factory.city}</span>${q.recommended ? h`<br><span class="tag v">★ Recommended</span>` : ''}</td>
      <td data-label="Price"><strong>${inr(q.price)}</strong> <span class="small mute">/ ${q.unit_label}</span><br><span class="small mute">Total ${inr(q.total_amount)}</span>${q.status === 'SUBMITTED' && Number(q.price) === cheapest && open.length > 1 ? h`<br><span class="tag">Lowest price</span>` : ''}</td>
      <td data-label="MOQ">${q.moq ? num(q.moq) : '—'}</td>
      <td data-label="Lead time">${q.lead_time_days} days${q.status === 'SUBMITTED' && q.lead_time_days === fastest && open.length > 1 ? h`<br><span class="tag">Fastest</span>` : ''}</td>
      <td data-label="Certification">${q.factory.certifications.map((c) => h`<span class="tag">${c}</span>`)}${q.factory.certifications.length ? '' : '—'}</td>
      <td data-label="Rating"><span class="y">${stars(q.factory.rating)}</span><br><span class="small mute">${q.factory.review_count} review${q.factory.review_count === 1 ? '' : 's'}</span></td>
      <td class="act"><div class="cell-actions"><button class="btn sm ghost" data-act="qdetail" data-id="${q.id}">Details</button>${role === 'CLIENT' && q.status === 'SUBMITTED' ? h`<button class="btn sm gold" data-act="accept" data-id="${q.id}">Accept</button><button class="btn sm ghost danger" data-act="reject" data-id="${q.id}">Reject</button>` : q.status !== 'SUBMITTED' ? pill(q.status) : ''}</div></td></tr>`)}</tbody></table></div>`;
  }

  function factorySide() {
    const m = rfq.my_match || {};
    const canQuote = ['SUBMITTED', 'MATCHING', 'QUOTATION_RECEIVED'].includes(rfq.status) && m.response !== 'DECLINED';
    const q = mine && mine.status !== 'WITHDRAWN' ? mine : null;
    return h`<div class="card"><h2 style="font-size:1.2rem">Why this matches you</h2><p class="mute small">Match score ${m.score ?? '—'} / 100</p>${(m.reasons || []).map((r) => h`<span class="tag v">${r}</span>`)}
        <p style="margin-top:12px">Your response: ${pill(m.response || 'NEW')}</p>
        ${canQuote && !q && m.response === 'NEW' ? h`<div class="form-actions"><button class="btn" data-act="interested">I am interested</button><button class="btn ghost danger" data-act="decline">Decline</button></div>` : ''}
        ${m.response === 'DECLINED' && ['SUBMITTED', 'MATCHING', 'QUOTATION_RECEIVED'].includes(rfq.status) ? h`<div class="form-actions"><button class="btn ghost" data-act="interested">Changed my mind: accept</button></div>` : ''}</div>
      ${canQuote ? h`<div class="card"><h2 style="font-size:1.2rem">${q ? 'Your quotation' : 'Send a quotation'}</h2>${q ? h`<p>${pill(q.status)} ${q.status === 'ACCEPTED' ? 'The client accepted this quotation.' : ''}</p>` : ''}${q && q.status !== 'SUBMITTED' ? '' : quoteForm(q)}</div>` : mine && mine.status !== 'WITHDRAWN' ? h`<div class="card"><h2 style="font-size:1.2rem">Your quotation</h2><p>${pill(mine.status)} ${inr(mine.price)} per ${mine.unit_label}</p>${mine.status === 'ACCEPTED' ? h`<p><a class="btn" href="#/orders">View orders</a></p>` : ''}</div>` : ''}`;
  }

  function quoteForm(q) {
    const d = q || {};
    const plus14 = new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10);
    return h`<form data-form="quote" novalidate><div class="fields">${fld(`Price per ${rfq.unit_label} (₹)`, 'price', { type: 'number', value: d.price || '', attrs: 'min="0" step="any"' })}${fld(`Quantity (${rfq.unit_label})`, 'quantity', { type: 'number', value: d.quantity || rfq.quantity, attrs: 'min="1" step="any"' })}
      ${fld('Your minimum order', 'moq', { type: 'number', value: d.moq || '', note: '(optional)', attrs: 'min="0" step="any"' })}${fld('Production time (days)', 'production_days', { type: 'number', value: d.production_days || '', attrs: 'min="1" max="365"' })}
      ${fld('Shipping time (days)', 'shipping_days', { type: 'number', value: d.shipping_days ?? 5, attrs: 'min="0" max="365"' })}${fld('Quotation valid until', 'validity_date', { type: 'date', value: d.validity_date || plus14 })}</div>
      <label>Notes <span class="opt-note">(optional)</span><textarea name="notes" rows="3" maxlength="1500">${d.notes || ''}</textarea></label>
      <label>Attach a document <span class="opt-note">(optional)</span><input type="file" name="attachment"></label>
      <div class="form-actions"><button class="btn" type="submit">${q ? 'Update quotation' : 'Send quotation'}</button>${q ? h`<button type="button" class="btn ghost danger" data-act="withdraw">Withdraw</button>` : ''}</div></form>`;
  }

  async function adminOptions() {
    const list = await api.get('/factories/?page_size=100');
    const have = new Set((rfq.matches || []).map((m) => m.factory_id));
    return list.results.filter((f) => !have.has(f.id));
  }

  function adminSide() {
    return h`<div class="card"><h2 style="font-size:1.2rem">Client</h2><p>${rfq.client.company_name || rfq.client.name}<br><span class="mute small">${rfq.client.name} · ${rfq.client.email} · ${rfq.client.phone}</span></p></div>
      <div class="card"><h2 style="font-size:1.2rem">Factories that have this RFQ</h2>${(rfq.matches || []).length ? h`<div class="tbl"><table class="stack"><thead><tr><th>Factory</th><th>Match</th><th>Response</th></tr></thead><tbody>${rfq.matches.map((m) => h`<tr><td data-label="Factory">${m.factory_name}${m.assigned_by_admin ? h` <span class="tag">assigned</span>` : ''}</td><td data-label="Match">${m.score}</td><td data-label="Response">${pill(m.response)}</td></tr>`)}</tbody></table></div>` : h`<p class="banner warn">No factory matched automatically. Please assign one.</p>`}
        ${['SUBMITTED', 'MATCHING', 'QUOTATION_RECEIVED'].includes(rfq.status) ? h`<div class="form-actions"><button class="btn sm" data-act="assign">Assign a factory</button></div>` : ''}</div>`;
  }

  async function qDetail(q) {
    const m = openModal('Quotation details', h`<p><strong>${q.factory.name}</strong> ${pill(q.status)}</p>
      <dl class="facts"><dt>Price</dt><dd>${inr(q.price)} per ${q.unit_label}</dd><dt>Quantity</dt><dd>${num(q.quantity)} ${q.unit_label}</dd><dt>Total</dt><dd><strong>${inr(q.total_amount)}</strong></dd><dt>Minimum order</dt><dd>${q.moq ? num(q.moq) : '—'}</dd>
      <dt>Production time</dt><dd>${q.production_days} days</dd><dt>Shipping time</dt><dd>${q.shipping_days} days</dd><dt>Valid until</dt><dd>${fdate(q.validity_date)}</dd><dt>Advance to pay</dt><dd>${inr(Number(q.total_amount) * o.advance_percent / 100)} (${o.advance_percent}%)</dd></dl>
      ${q.notes ? h`<p style="margin-top:12px"><strong>Factory notes</strong><br>${q.notes}</p>` : ''}
      ${(q.match_reasons || []).length ? h`<p class="small"><strong>Why this factory fits (${q.match_score}/100):</strong> ${q.match_reasons.join(' · ')}</p>` : ''}
      ${q.attachment_url ? h`<p><button class="btn sm ghost" data-dl="${q.attachment_url}" data-name="${q.attachment_name || 'quotation'}">📎 ${q.attachment_name || 'Attachment'}</button></p>` : ''}
      ${role === 'CLIENT' && q.status === 'SUBMITTED' ? h`<div class="form-actions"><button class="btn gold" data-act="accept" data-id="${q.id}">Accept this quotation</button></div>` : ''}`);
    wire(m, { accept: (b) => { m.close(); acceptQuote(b.dataset.id); } });
  }

  async function acceptQuote(qid) {
    const q = quotes.find((x) => String(x.id) === String(qid));
    const adv = Number(q.total_amount) * o.advance_percent / 100;
    if (!(await confirmBox('Accept this quotation?', `You are choosing ${q.factory.name} for ${inr(q.total_amount)}. Other quotations for this requirement will be closed. An order is created and you will pay a ${o.advance_percent}% advance (${inr(adv)}) to start production.`, 'Accept and create order'))) return;
    const r = await api.post(`/quotations/${qid}/accept/`);
    toast('Quotation accepted. Your order has been created.');
    location.hash = '#/orders/' + r.order_id;
  }

  wire(page, {
    retry: load,
    'goto-quotes': () => page.querySelector('table') && page.querySelector('table').scrollIntoView({ behavior: 'smooth' }),
    factory: (b) => factoryModal(b.dataset.id),
    qdetail: (b) => qDetail(quotes.find((q) => String(q.id) === b.dataset.id)),
    accept: (b) => acceptQuote(b.dataset.id),
    reject: async (b) => { if (await confirmBox('Reject this quotation?', 'The factory will be told. You can still accept another quotation.', 'Reject', true)) { await api.post(`/quotations/${b.dataset.id}/reject/`); toast('Quotation rejected.'); load(); } },
    cancel: async () => { if (await confirmBox('Cancel this requirement?', 'Factories will be told and open quotations will be closed.', 'Cancel requirement', true)) { await api.post(`/rfqs/${id}/cancel/`); toast('Requirement cancelled.'); load(); } },
    interested: async () => { await api.post(`/rfqs/${id}/respond/`, { action: 'accept' }); toast('Marked as interested.'); load(); },
    decline: () => {
      const m = openModal('Decline this RFQ', h`<form data-form="decline" novalidate><label>Reason <span class="opt-note">(optional)</span><textarea name="reason" rows="3" maxlength="300"></textarea></label><div class="form-actions"><button class="btn danger" type="submit">Decline RFQ</button><button type="button" class="btn ghost" data-close>Cancel</button></div></form>`);
      wire(m, { decline: async (f, d) => { await api.post(`/rfqs/${id}/respond/`, { action: 'decline', reason: d.reason }); m.close(); toast('RFQ declined.'); load(); } });
    },
    quote: async (form) => {
      const fd = new FormData(form);
      [...fd.keys()].forEach((k) => { const v = fd.get(k); if (v === '' || (v instanceof File && !v.size)) fd.delete(k); });
      if (!fd.get('price')) throw Object.assign(new Error('Please enter your price.'), { errors: { price: ['Please enter your price.'] } });
      if (mine && mine.status === 'SUBMITTED') await api.patch(`/quotations/${mine.id}/`, fd);
      else { fd.append('rfq', id); await api.post('/quotations/', fd); }
      toast('Your quotation has been saved.');
      load();
    },
    withdraw: async () => { if (await confirmBox('Withdraw your quotation?', 'The client will no longer see it. You can send a new one later.', 'Withdraw', true)) { await api.post(`/quotations/${mine.id}/withdraw/`); toast('Quotation withdrawn.'); load(); } },
    edit: () => {
      const m = openModal('Edit requirement', h`<form data-form="edit" novalidate><div class="fields">${fld('Quantity', 'quantity', { type: 'number', value: rfq.quantity, attrs: 'min="1" step="any"' })}${sel('Unit', 'unit', o.units.map((u) => [u.value, u.label]), rfq.unit, { blank: false })}
        ${fld('Target price (₹, optional)', 'target_price', { type: 'number', value: rfq.target_price || '', attrs: 'min="0" step="any"' })}${fld('Needed by', 'required_date', { type: 'date', value: rfq.required_date })}${fld('Delivery city', 'delivery_city', { value: rfq.delivery_city })}${fld('Delivery state', 'delivery_state', { value: rfq.delivery_state })}</div>
        <label>Notes<textarea name="requirements" rows="3" maxlength="2000">${rfq.requirements}</textarea></label><div class="form-actions"><button class="btn" type="submit">Save changes</button><button type="button" class="btn ghost" data-close>Cancel</button></div></form>`);
      wire(m, { edit: async (f, d) => { await api.patch(`/rfqs/${id}/`, { ...d, target_price: d.target_price || null }); m.close(); toast('Requirement updated.'); load(); } });
    },
    assign: async () => {
      const list = await adminOptions();
      if (!list.length) { toast('There is no other verified factory to assign.', 'error'); return; }
      const m = openModal('Assign a factory', h`<form data-form="assign" novalidate>${sel('Verified factory', 'factory_id', list.map((f) => [f.id, `${f.name} (${f.city})`]), '', { blank: 'Choose a factory…' })}<div class="form-actions"><button class="btn" type="submit">Send RFQ to this factory</button></div></form>`);
      wire(m, { assign: async (f, d) => { await api.post(`/rfqs/${id}/assign/`, { factory_id: d.factory_id }); m.close(); toast('RFQ assigned.'); load(); } });
    },
  });
  load();
}
