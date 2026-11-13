// Pieces used on several pages: factory profile popup, messages, payment flow, receipts.
import { api, session, getOptions } from './api.js';
import { h, mount, raw, openModal, toast, wire, inr, fdate, fdatetime, loading, errorBox, empty, pill, sel, $ } from './ui.js';

export const stars = (r) => { const n = Math.round(Number(r) || 0); return '★'.repeat(n) + '☆'.repeat(5 - n); };

export async function factoryModal(id) {
  const m = openModal('Factory profile', loading('Loading factory…'));
  try {
    const [f, reviews] = await Promise.all([api.get(`/factories/${id}/`), api.get(`/reviews/?factory=${id}`)]);
    mount(m.body, h`<p><strong>${f.name}</strong><br><span class="mute">${[f.city, f.state, f.country].filter(Boolean).join(', ')}</span></p>
      <p class="y">${stars(f.rating)} <span class="mute small">${Number(f.rating) ? `${f.rating} from ${f.review_count} review${f.review_count === 1 ? '' : 's'}` : 'No reviews yet'}</span></p>
      ${f.description ? h`<p>${f.description}</p>` : ''}
      <dl class="facts"><dt>Leather types</dt><dd>${(f.leather_types || []).join(', ') || '—'}</dd><dt>Applications</dt><dd>${(f.applications || []).join(', ') || '—'}</dd>
      <dt>Colors</dt><dd>${(f.colors || []).join(', ') || '—'}</dd><dt>Thickness</dt><dd>${f.min_thickness && f.max_thickness ? `${Number(f.min_thickness)}–${Number(f.max_thickness)} mm` : '—'}</dd>
      <dt>Minimum order</dt><dd>${f.min_order_quantity ? Number(f.min_order_quantity).toLocaleString('en-IN') : '—'}</dd><dt>Monthly capacity</dt><dd>${f.production_capacity ? Number(f.production_capacity).toLocaleString('en-IN') : '—'}</dd>
      <dt>Typical lead time</dt><dd>${f.typical_lead_time_days ? f.typical_lead_time_days + ' days' : '—'}</dd></dl>
      <h3 style="margin-top:16px">Certifications</h3>
      <p>${(f.certifications || []).map((c) => h`<span class="tag v">${c}</span>`)}${(f.certifications || []).length ? '' : 'None listed.'}</p>
      ${f.documents.length ? (session.user ? h`<p>${f.documents.map((d) => h`<button class="btn sm ghost" data-dl="${d.download_url}" data-name="${d.original_name}">${d.title}</button> `)}</p>` : h`<p class="mute small">Sign in to download certificate files.</p>`) : ''}
      <h3 style="margin-top:16px">Reviews</h3>
      ${reviews.results.length ? reviews.results.map((r) => h`<p><span class="y">${stars(r.rating)}</span> <span class="mute small">${r.client_name} · ${fdate(r.created_at)}</span><br>${r.review || ''}</p>`) : h`<p class="mute">No reviews yet.</p>`}`);
  } catch (err) { mount(m.body, errorBox(err, false)); }
}

// ---- messages between client and factory (admin can read and join) ----------------------------------
// target: {rfq} or {order}; factories: [{id (user id), name}] to choose from (client/admin on an RFQ)
export async function messagesPanel(el, target, factories = null) {
  let factoryUser = factories && factories.length ? factories[0].id : '';
  const needsFactory = factories !== null && !target.order;
  if (needsFactory && !factories.length) {
    mount(el, h`<div class="card"><h3>Messages</h3><p class="mute">You can message a factory once it sends a quotation.</p></div>`);
    return;
  }
  const query = () => (target.order ? `order=${target.order}` : `rfq=${target.rfq}${needsFactory ? '&factory=' + factoryUser : ''}`);
  async function load() {
    const box = $('[data-chat]', el);
    try {
      const msgs = await api.get('/messages/?' + query());
      mount(box, msgs.length ? h`${msgs.map((m) => h`<div class="msg ${m.mine ? 'mine' : ''}"><small>${m.sender_name} · ${fdatetime(m.created_at)}</small>${m.body}${m.attachment_url ? h`<br><button class="btn sm ghost" data-dl="${m.attachment_url}" data-name="${m.attachment_name}">📎 ${m.attachment_name}</button>` : ''}</div>`)}` : h`<div class="state">No messages yet. Say hello.</div>`);
      box.scrollTop = box.scrollHeight;
    } catch (err) { mount(box, errorBox(err, false)); }
  }
  mount(el, h`<div class="card"><div class="head"><h3 style="margin:0">Messages</h3><button class="btn sm ghost" data-act="msg-refresh">Refresh</button></div>
    ${needsFactory && factories.length > 1 ? h`<label>Conversation with<select data-change="msg-factory">${factories.map((f) => h`<option value="${f.id}">${f.name}</option>`)}</select></label>` : needsFactory ? h`<p class="mute small">Conversation with ${factories[0].name}</p>` : ''}
    <div class="chat" data-chat aria-live="polite">${loading('Loading messages…')}</div>
    <form data-form="msg-send"><label>Your message<textarea name="body" rows="2" maxlength="2000"></textarea></label>
    <label>Attach a file <span class="opt-note">(optional)</span><input type="file" name="attachment"></label>
    <div class="form-actions"><button class="btn" type="submit">Send message</button></div></form></div>`);
  wire(el, {
    'msg-refresh': load,
    'msg-factory': (s) => { factoryUser = s.value; load(); },
    'msg-send': async (form) => {
      const fd = new FormData(form);
      if (target.order) fd.append('order', target.order); else { fd.append('rfq', target.rfq); if (needsFactory) fd.append('factory', factoryUser); }
      if (!fd.get('attachment') || !fd.get('attachment').size) fd.delete('attachment');
      await api.post('/messages/', fd);
      form.reset();
      await load();
    },
  });
  load();
}

// ---- payments ---------------------------------------------------------------------------------------------
function loadRazorpay() {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) return resolve();
    const s = document.createElement('script');
    s.src = 'https://checkout.razorpay.com/v1/checkout.js';
    s.onload = resolve;
    s.onerror = () => reject(new Error('We could not load the payment window. Please check your connection and try again.'));
    document.head.appendChild(s);
  });
}

export async function startPayment(orderId, purpose, done) {
  const p = await api.post('/payments/create/', { order_id: orderId, purpose });
  if (p.sandbox) return sandboxDialog(p, done);
  await loadRazorpay();
  const rzp = new window.Razorpay({
    key: p.key_id, amount: p.amount_paise, currency: p.currency, name: 'Tannery Desk', description: p.description,
    order_id: p.razorpay_order_id, prefill: { name: p.client_name, email: p.client_email }, theme: { color: '#2B1B12' },
    handler: async (resp) => {
      try {
        await api.post('/payments/verify/', resp); // the server checks the signature; we never trust the browser alone
        toast('Payment successful.');
      } catch (err) { toast(err.message || 'Payment failed. Please try again.', 'error'); }
      done();
    },
  });
  rzp.on('payment.failed', async (r) => {
    try { await api.post('/payments/failed/', { razorpay_order_id: p.razorpay_order_id, reason: (r.error && r.error.description) || '' }); } catch (e) { /* ignore */ }
    toast('Payment failed. Please try again.', 'error');
    done();
  });
  rzp.open();
}

function sandboxDialog(p, done) {
  const m = openModal('Test payment', h`<p><span class="demo">SANDBOX · no real money</span></p>
    <p>You are paying <strong>${inr(p.amount)}</strong> for <strong>${p.description}</strong>.</p>
    <p class="mute small">Razorpay keys are not configured on this server, so this is a safe test checkout. The server still verifies the payment before marking it as paid.</p>
    <div class="form-actions"><button class="btn gold" data-act="ok">Simulate successful payment</button><button class="btn ghost danger" data-act="fail">Simulate failed payment</button></div>`);
  const send = async (outcome) => {
    try {
      const r = await api.post(`/payments/${p.payment_id}/sandbox/`, { outcome });
      toast(r.status === 'PAID' ? 'Payment successful.' : 'Payment failed. Please try again.', r.status === 'PAID' ? '' : 'error');
    } catch (err) { toast(err.message, 'error'); }
    m.close();
    done();
  };
  wire(m, { ok: () => send('success'), fail: () => send('fail') });
}

export function receiptModal(p) {
  const m = openModal('Payment receipt', h`<dl class="facts"><dt>Receipt</dt><dd>${p.receipt_number}</dd><dt>Order</dt><dd>${p.order_number}</dd>
    <dt>Type</dt><dd>${p.purpose_label}</dd><dt>Amount</dt><dd>${inr(p.amount)} ${p.currency}</dd><dt>Status</dt><dd>${p.status_label}</dd>
    <dt>Paid on</dt><dd>${fdatetime(p.paid_at)}</dd><dt>Reference</dt><dd>${p.razorpay_payment_id || '—'}</dd><dt>Gateway order</dt><dd>${p.razorpay_order_id}</dd>
    <dt>Mode</dt><dd>${p.mode_label}</dd></dl><div class="form-actions no-print"><button class="btn" data-act="print">Print receipt</button></div>`);
  wire(m, { print: () => window.print() });
}

export const paymentsTable = (payments) => payments.length
  ? h`<div class="tbl"><table class="stack"><thead><tr><th>Date</th><th>Type</th><th>Amount</th><th>Status</th><th></th></tr></thead><tbody>${payments.map((p) => h`<tr><td data-label="Date">${fdatetime(p.paid_at || p.created_at)}</td><td data-label="Type">${p.purpose_label}</td><td data-label="Amount">${inr(p.amount)}</td><td data-label="Status">${pill(p.status, p.status_label)}</td><td class="act">${p.status === 'PAID' ? h`<button class="btn sm ghost" data-act="receipt" data-id="${p.id}">Receipt</button>` : ''}</td></tr>`)}</tbody></table></div>`
  : empty('No payments yet.');
