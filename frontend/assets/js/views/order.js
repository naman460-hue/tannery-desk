// Order page for all roles: timeline, payments, production updates, dispatch, documents, delivery, review.
import { api, session, getOptions } from '../api.js';
import { h, mount, raw, wire, openModal, confirmBox, loading, errorBox, empty, pill, timeline, inr, num, fdate, fdatetime, fld, sel, toast } from '../ui.js';
import { messagesPanel, startPayment, receiptModal, paymentsTable } from '../shared.js';

export async function orderView(page, ctx) {
  const id = ctx.params[0];
  const role = session.user.role;
  const o = await getOptions();
  let order, rating = 0;

  async function load() {
    mount(page, loading('Loading order…'));
    try { order = await api.get(`/orders/${id}/`); draw(); } catch (err) { mount(page, errorBox(err)); }
  }

  const stageOptions = () => {
    const allowed = order.status === 'DISPATCHED' || order.status === 'IN_TRANSIT' ? ['IN_TRANSIT', 'DELIVERED'] : ['PRODUCTION_STARTED', 'QUALITY_CHECK', 'PACKAGING'];
    const labels = Object.fromEntries(o.order_stages.map((s) => [s.value, s.label]));
    const cur = o.order_stages.findIndex((s) => s.value === order.status);
    return allowed.filter((s) => o.order_stages.findIndex((x) => x.value === s) >= cur).map((s) => [s, labels[s]]);
  };

  function draw() {
    const labels = [...o.rfq_stages.slice(0, 3).map((s) => s.label), 'Client Approval', ...o.order_stages.map((s) => s.label)];
    const cur = 4 + o.order_stages.findIndex((s) => s.value === order.status);
    const d = order;
    const due = d.next_payment;
    const paid = d.payment_status !== 'PENDING';
    mount(page, h`<p class="small"><a href="${role === 'ADMIN' ? '#/admin/orders' : role === 'FACTORY' ? '#/factory' : '#/client'}">← Back to dashboard</a></p>
      <div class="head"><div><h1>${d.number}</h1><p class="mute" style="margin:0">${d.title} · <a href="#/rfqs/${d.rfq_id}">${d.rfq_number}</a></p></div><div>${pill(d.status, d.status_label)} ${pill(d.payment_status, d.payment_status_label)}</div></div>
      ${d.status === 'CANCELLED' ? '' : timeline(labels, cur)}
      ${role === 'CLIENT' ? clientNext() : role === 'FACTORY' ? factoryNext() : ''}
      <div class="stats"><div class="card stat"><b>${d.status_label}</b><span>Current stage</span></div><div class="card stat"><b>${d.progress_percent}%</b><span>Production progress</span><div class="progress" style="margin-top:6px"><i style="width:${d.progress_percent}%"></i></div></div>
        <div class="card stat"><b>${fdate(d.expected_completion)}</b><span>Expected completion</span></div><div class="card stat"><b>${fdate(d.expected_delivery)}</b><span>Expected delivery</span></div></div>
      <div class="card"><strong>Latest update:</strong> ${d.latest_update ? h`${d.latest_update.stage}${d.latest_update.message ? ' — ' + d.latest_update.message : ''} <span class="mute small">(${fdatetime(d.latest_update.created_at)})</span>` : 'No updates yet.'}</div>
      <div class="two sec" style="margin-top:20px"><div class="card"><h2 style="font-size:1.2rem">Order summary</h2><dl class="facts"><dt>Product</dt><dd>${d.title}</dd><dt>Quantity</dt><dd>${num(d.quantity)} ${d.unit_label} at ${inr(d.price)}</dd><dt>Total</dt><dd><strong>${inr(d.total_amount)}</strong></dd>
          <dt>Advance (${o.advance_percent}%)</dt><dd>${inr(d.advance_amount)}</dd><dt>Remaining</dt><dd>${inr(d.remaining_amount)}</dd><dt>Factory</dt><dd>${d.factory_name}</dd><dt>Buyer</dt><dd>${d.client_name}</dd>
          ${d.courier_name ? h`<dt>Courier</dt><dd>${d.courier_name}</dd><dt>Tracking number</dt><dd>${d.tracking_number}</dd>` : ''}</dl>${d.quotation_notes ? h`<p class="small mute" style="margin-top:10px">Quotation notes: ${d.quotation_notes}</p>` : ''}
          ${parties()}</div>
        <div class="stack"><div class="card"><h2 style="font-size:1.2rem">Payments</h2>${role === 'CLIENT' && due ? h`<p>${due.purpose === 'ADVANCE' ? 'Pay the advance to start production.' : 'Production is nearly done. Please pay the remaining amount.'}</p><button class="btn gold" data-act="pay" data-purpose="${due.purpose}">${due.label} · ${inr(due.amount)}</button>` : ''}
          ${paymentsTable(d.payments)}${role === 'CLIENT' && o.payments_sandbox && due ? h`<p class="small mute">Test mode: payments are simulated and no money moves.</p>` : ''}</div>
          ${role === 'FACTORY' ? factoryPanel(paid) : ''}</div></div>
      <section class="sec"><h2>Progress updates</h2>${d.updates.length ? h`<ul class="updates">${d.updates.map((u) => h`<li><strong>${u.stage_label}</strong> · ${u.percentage}%${u.message ? h`<br>${u.message}` : ''}<br><span class="small mute">${u.updated_by_name} · ${fdatetime(u.created_at)}</span></li>`)}</ul>` : empty('No production updates yet.')}</section>
      <section class="sec"><h2>Documents</h2>${d.documents.length ? h`<div class="tbl"><table class="stack"><thead><tr><th>Title</th><th>Type</th><th>Added</th><th></th></tr></thead><tbody>${d.documents.map((x) => h`<tr><td data-label="Title">${x.title}</td><td data-label="Type">${x.kind.replace(/_/g, ' ').toLowerCase()}</td><td data-label="Added">${fdate(x.created_at)}</td><td class="act"><button class="btn sm ghost" data-dl="${x.download_url}" data-name="${x.original_name}">Download</button></td></tr>`)}</tbody></table></div>` : empty('No documents yet.')}
        ${role !== 'CLIENT' ? docForm() : ''}</section>
      ${role === 'CLIENT' && d.status === 'COMPLETED' ? reviewBlock() : d.review ? h`<section class="sec"><h2>Review</h2><p class="y">${'★'.repeat(d.review.rating)}${'☆'.repeat(5 - d.review.rating)}</p><p>${d.review.review}</p></section>` : ''}
      ${role !== 'ADMIN' ? h`<div class="form-actions no-print"><button class="btn ghost sm" data-act="dispute">Report a problem with this order</button></div>` : ''}
      <section class="sec" id="chat"></section>`);
    messagesPanel(page.querySelector('#chat'), { order: id });
  }

  function clientNext() {
    const d = order;
    if (d.next_payment && d.next_payment.purpose === 'ADVANCE') return h`<div class="next"><strong>Next step: pay the advance of ${inr(d.next_payment.amount)} so the factory can start production.</strong><button class="btn gold" data-act="pay" data-purpose="ADVANCE">Pay advance</button></div>`;
    if (d.next_payment) return h`<div class="next"><strong>Next step: pay the remaining ${inr(d.next_payment.amount)}.</strong><button class="btn gold" data-act="pay" data-purpose="REMAINING">Pay remaining amount</button></div>`;
    if (d.status === 'DELIVERED') return h`<div class="next"><strong>Your order has arrived. Please check the goods and confirm.</strong><button class="btn gold" data-act="confirm">Confirm delivery</button></div>`;
    if (d.status === 'DELIVERED' || d.status === 'COMPLETED') return '';
    return '';
  }

  function factoryNext() {
    const d = order;
    if (d.status === 'ORDER_CREATED') return h`<div class="banner warn">Waiting for the client to pay the advance. You can start production once it is paid.</div>`;
    if (d.status === 'PAYMENT_RECEIVED') return h`<div class="next"><strong>The advance is paid. Start production and post an update.</strong></div>`;
    return '';
  }

  function parties() {
    const p = order.parties || {};
    return h`${p.client ? h`<h3 style="margin-top:14px">Buyer contact</h3><p class="small">${p.client.company_name || p.client.name}<br>${p.client.name} · ${p.client.phone}<br>${[p.client.address, p.client.city, p.client.state].filter(Boolean).join(', ')}</p>` : ''}
      ${p.factory ? h`<h3 style="margin-top:14px">Factory contact</h3><p class="small">${p.factory.name}<br>${p.factory.contact_name} · ${p.factory.phone}<br>${p.factory.email}</p>` : ''}`;
  }

  function factoryPanel(paid) {
    const d = order;
    if (['COMPLETED', 'CANCELLED', 'DELIVERED'].includes(d.status)) return '';
    if (!paid) return h`<div class="card"><h2 style="font-size:1.2rem">Production</h2><p class="mute">Production updates unlock when the client has paid the advance.</p></div>`;
    const dispatched = ['DISPATCHED', 'IN_TRANSIT'].includes(d.status);
    const stages = stageOptions();
    return h`<div class="card"><h2 style="font-size:1.2rem">${dispatched ? 'Delivery update' : 'Update production'}</h2>
      <form data-form="production" novalidate>${sel('Stage', 'stage', stages, stages[0] && stages[0][0], { blank: false })}${dispatched ? '' : fld('Progress (%)', 'percentage', { type: 'number', value: d.progress_percent, attrs: 'min="0" max="100"' })}
      <label>Message to the client <span class="opt-note">(optional)</span><textarea name="message" rows="2" maxlength="500"></textarea></label><div class="form-actions"><button class="btn" type="submit">Post update</button></div></form></div>
      ${d.status === 'PACKAGING' ? h`<div class="card"><h2 style="font-size:1.2rem">Dispatch</h2>${d.ready_for_dispatch ? h`<form data-form="dispatch" novalidate><div class="fields">${fld('Courier', 'courier_name')}${fld('Tracking number', 'tracking_number')}${fld('Expected delivery', 'expected_delivery', { type: 'date', value: d.expected_delivery || '', note: '(optional)' })}</div><div class="form-actions"><button class="btn gold" type="submit">Mark as dispatched</button></div></form>` : h`<p class="mute">Packed and ready? Tell the client and unlock dispatch.</p><button class="btn" data-act="ready">Mark ready for dispatch</button>`}</div>` : ''}
      <div class="card"><h2 style="font-size:1.2rem">Expected delivery</h2><form data-form="eta" novalidate><div class="fields">${fld('New date', 'expected_delivery', { type: 'date', value: d.expected_delivery || '' })}${fld('Reason', 'message', { note: '(optional)' })}</div><div class="form-actions"><button class="btn ghost" type="submit">Update date</button></div></form></div>`;
  }

  function docForm() {
    return h`<form class="card" data-form="doc" novalidate style="margin-top:12px"><h3>Upload a document</h3><div class="fields">${sel('Type', 'kind', o.order_document_kinds.map((k) => [k, k.replace(/_/g, ' ').toLowerCase()]), 'OTHER', { blank: false })}${fld('Title', 'title')}</div>
      <label>File <span class="opt-note">(max ${o.max_upload_mb} MB: PDF, image, Word, Excel)</span><input type="file" name="file"></label><div class="form-actions"><button class="btn" type="submit">Upload</button></div></form>`;
  }

  function reviewBlock() {
    if (order.review) return h`<section class="sec"><h2>Your review</h2><p class="y">${'★'.repeat(order.review.rating)}${'☆'.repeat(5 - order.review.rating)}</p><p>${order.review.review}</p></section>`;
    return h`<section class="sec"><h2>Rate ${order.factory_name}</h2><form class="card" data-form="review" novalidate><div class="stars" role="radiogroup" aria-label="Rating">${[1, 2, 3, 4, 5].map((n) => h`<button type="button" class="${n <= rating ? 'on' : ''}" data-act="star" data-n="${n}" aria-label="${n} star${n > 1 ? 's' : ''}">★</button>`)}</div>
      <label>Your review <span class="opt-note">(optional)</span><textarea name="review" rows="3" maxlength="1500"></textarea></label><div class="form-actions"><button class="btn" type="submit">Submit review</button></div></form></section>`;
  }

  wire(page, {
    retry: load,
    pay: (b) => startPayment(order.id, b.dataset.purpose, load),
    receipt: (b) => receiptModal(order.payments.find((p) => String(p.id) === b.dataset.id)),
    confirm: async () => { if (await confirmBox('Confirm delivery?', 'Only confirm once you have received and checked the goods.', 'Yes, confirm')) { await api.post(`/orders/${id}/confirm-delivery/`); toast('Order completed. Thank you!'); load(); } },
    ready: async () => { await api.post(`/orders/${id}/ready-for-dispatch/`); toast('Marked as ready for dispatch.'); load(); },
    star: (b) => { rating = Number(b.dataset.n); page.querySelectorAll('.stars button').forEach((s) => s.classList.toggle('on', Number(s.dataset.n) <= rating)); },
    review: async (form, d) => { if (!rating) throw Object.assign(new Error('Please select a rating from 1 to 5 stars.')); await api.post('/reviews/create/', { order: Number(id), rating, review: d.review }); toast('Thank you for your review.'); load(); },
    production: async (form, d) => { await api.post(`/orders/${id}/production/`, { stage: d.stage, percentage: Number(d.percentage ?? order.progress_percent), message: d.message || '' }); toast('Update posted. The client has been notified.'); load(); },
    dispatch: async (form, d) => {
      if (!d.courier_name || !d.tracking_number) throw Object.assign(new Error('Please enter the courier and tracking number.'));
      await api.post(`/orders/${id}/dispatch/`, { courier_name: d.courier_name, tracking_number: d.tracking_number, ...(d.expected_delivery ? { expected_delivery: d.expected_delivery } : {}) });
      toast('Order dispatched.'); load();
    },
    eta: async (form, d) => { if (!d.expected_delivery) throw Object.assign(new Error('Please choose a date.')); await api.post(`/orders/${id}/expected-delivery/`, d); toast('Expected delivery updated.'); load(); },
    doc: async (form) => {
      const fd = new FormData(form);
      if (!fd.get('title')) throw Object.assign(new Error('Please enter a title.'), { errors: { title: ['Please enter a title.'] } });
      if (!fd.get('file') || !fd.get('file').size) throw Object.assign(new Error('Please choose a file.'));
      await api.post(`/orders/${id}/documents/`, fd); toast('Document uploaded.'); load();
    },
    dispute: () => {
      const m = openModal('Report a problem', h`<form data-form="dispute" novalidate>${fld('Subject', 'subject', { required: true })}<label>What went wrong?<textarea name="description" rows="4" maxlength="2000"></textarea></label><div class="form-actions"><button class="btn" type="submit">Send to Tannery Desk</button><button type="button" class="btn ghost" data-close>Cancel</button></div></form>`);
      wire(m, { dispute: async (f, d) => { await api.post('/disputes/', { order: Number(id), subject: d.subject, description: d.description }); m.close(); toast('Thank you. The Tannery Desk team will look into it.'); } });
    },
  });
  load();
}
