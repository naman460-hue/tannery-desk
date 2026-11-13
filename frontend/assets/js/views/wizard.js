// The requirement wizard (kept from the prototype, now backed by the API).
import { api, session, getOptions } from '../api.js';
import { h, mount, raw, wire, toast, esc, fld, sel, loading } from '../ui.js';

const KEY = 'td_wizard';
let files = [];
let returnToSummary = false;

const newToken = () => (window.crypto && crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));
const load = () => { try { return JSON.parse(sessionStorage.getItem(KEY)) || null; } catch (e) { return null; } };
const save = (s) => sessionStorage.setItem(KEY, JSON.stringify(s));
const fresh = () => ({ step: 0, data: {}, token: newToken() });
const fail = (msg, field) => Object.assign(new Error(msg), { errors: field ? { [field]: [msg] } : {} });
const tomorrow = () => new Date(Date.now() + 86400000).toISOString().slice(0, 10);

// "choice" steps show buttons, "form" steps show inputs. Lists come from /api/meta/options/.
const STEPS = [
  { id: 'need', title: 'What do you need?', hint: 'Choose the closest option.', kind: 'choice', list: (o) => o.needs.map((n) => [n, n]), msg: 'Please select what you need.' },
  { id: 'leather_type', title: 'Which leather type?', hint: 'The animal the leather comes from.', kind: 'choice', list: (o) => o.leather_types.map((n) => [n, n]), msg: 'Please select leather type.' },
  { id: 'application', title: 'What will you use it for?', hint: 'This helps us find factories with experience in your product.', kind: 'choice', list: (o) => o.applications.map((n) => [n, n]), msg: 'Please select an application.' },
  { id: 'color', title: 'Which color?', hint: 'Pick the closest color. You can describe special shades in the notes.', kind: 'choice', list: (o) => o.colors.map((c) => [c.name, c.name, c.hex]), msg: 'Please select a color.' },
  { id: 'thickness', title: 'How thick should it be?', hint: 'Not sure? Choose the middle option and mention it in the notes.', kind: 'choice', list: (o) => o.thickness_bands.map((b) => [b.label, b.label]), msg: 'Please select a thickness.' },
  { id: 'finish', title: 'Which finish?', hint: 'The surface look and feel. You can skip this if you are not sure.', kind: 'choice', optional: true, list: (o) => o.finishes.map((n) => [n, n]) },
  { id: 'quantity', title: 'How much do you need?', hint: 'Enter the total quantity for this order.', kind: 'form' },
  { id: 'price', title: 'Do you have a target price?', hint: 'Optional. It helps factories quote closer to your budget.', kind: 'form' },
  { id: 'date', title: 'When do you need it?', hint: 'The date you need the leather delivered.', kind: 'form' },
  { id: 'location', title: 'Where should it be delivered?', hint: 'We use this to find nearby factories.', kind: 'form' },
  { id: 'certs', title: 'Any certifications required?', hint: 'Optional. Only factories holding all of them will be a full match.', kind: 'form' },
  { id: 'notes', title: 'Notes and files', hint: 'Optional. Add reference images, specifications or anything else the factory should know.', kind: 'form' },
];
const SUMMARY = STEPS.length;

function labelFor(d, id, o) {
  switch (id) {
    case 'quantity': return d.quantity ? `${d.quantity} ${(o.units.find((u) => u.value === d.unit) || {}).label || ''}` : '—';
    case 'price': return d.target_price ? `₹${d.target_price} per unit` : 'Not specified';
    case 'date': return d.required_date || '—';
    case 'location': return [d.delivery_city, d.delivery_state].filter(Boolean).join(', ') || 'Not specified';
    case 'certs': return (d.certs || []).join(', ') || 'None';
    case 'notes': return [d.notes ? 'Notes added' : '', files.length ? `${files.length} file${files.length > 1 ? 's' : ''}` : ''].filter(Boolean).join(', ') || 'None';
    case 'finish': return d.finish || 'Not sure';
    default: return d[id] || '—';
  }
}

export function startFromProduct(p, o) {
  const band = o.thickness_bands.find((b) => Number(b.min) <= Number(p.thickness_max) && Number(b.max) >= Number(p.thickness_min));
  const s = fresh();
  s.data = { need: 'Finished Leather', leather_type: p.leather_type, application: p.application, color: p.color, finish: p.finish,
    thickness: band ? band.label : '', thickness_min: p.thickness_min, thickness_max: p.thickness_max, quantity: String(Number(p.moq)), unit: p.unit,
    product: p.id, productName: p.name };
  if (band) { s.data.thickness_min = band.min; s.data.thickness_max = band.max; }
  s.step = STEPS.findIndex((x) => x.id === 'quantity');
  save(s);
  files = [];
}

export async function renderWizard(el) {
  mount(el, loading('Loading the requirement form…'));
  let o;
  try { o = await getOptions(); } catch (err) { mount(el, h`<div class="state err">We could not load the form. Please refresh the page.</div>`); return; }
  let S = load() || fresh();
  let done = null;

  const draw = () => {
    if (done) {
      mount(el, h`<div class="card" style="text-align:center"><h2>Your RFQ has been submitted successfully.</h2><p class="mute">Your RFQ number</p><p style="font:700 2rem Newsreader,serif;margin:0 0 12px">${done.number}</p>
        <p>${done.status === 'MATCHING' ? 'We have sent it to suitable factories. You will be notified when quotations arrive.' : 'We are looking for suitable factories and will notify you.'}</p>
        <div class="form-actions" style="justify-content:center"><a class="btn gold" href="#/rfqs/${done.id}">View my RFQ</a><button class="btn ghost" data-act="again">Create another requirement</button></div></div>`);
      return;
    }
    const d = S.data;
    const pct = Math.round((Math.min(S.step, SUMMARY) / SUMMARY) * 100);
    if (S.step >= SUMMARY) {
      mount(el, h`<div class="card"><div class="bar" aria-hidden="true"><i style="width:100%"></i></div><h2>Check your requirement</h2><p class="mute">Make sure everything is correct. Use "Change" to edit any answer.</p>
        <dl class="summary">${STEPS.map((s, i) => h`<dt>${s.title.replace('?', '')}</dt><dd>${labelFor(d, s.id, o)} <button class="btn sm ghost" data-act="edit" data-step="${i}">Change</button></dd>`)}</dl>
        ${d.productName ? h`<p class="mute small">Based on catalog product: ${d.productName}</p>` : ''}
        <div class="form-actions"><button class="btn gold" data-act="submit">Submit requirement</button><button class="btn ghost" data-act="back">Back</button></div></div>`);
      return;
    }
    const s = STEPS[S.step];
    const body = s.kind === 'choice'
      ? h`<div class="opts" role="radiogroup" aria-label="${s.title}">${s.list(o).map(([v, l, hex]) => h`<button class="opt ${d[s.id] === v ? 'on' : ''}" role="radio" aria-checked="${d[s.id] === v}" data-act="pick" data-val="${v}">${hex ? h`<span class="dot" style="background:${hex}"></span>` : ''}${l}</button>`)}
        ${s.optional ? h`<button class="opt" data-act="pick" data-val="">Not sure / skip</button>` : ''}</div>`
      : formBody(s.id, d, o);
    mount(el, h`<div class="card"><div class="bar" aria-hidden="true"><i style="width:${pct}%"></i></div><p class="mute small" style="margin:0">Step ${S.step + 1} of ${SUMMARY}</p>
      <h2 style="margin-top:4px">${s.title}</h2><p class="mute">${s.hint}</p>${d.productName && S.step === 6 ? h`<p class="banner ok small">Prefilled from <strong>${d.productName}</strong>. You can go back and change anything.</p>` : ''}${body}
      <div class="form-actions">${S.step > 0 ? h`<button class="btn ghost" data-act="back" type="button">Back</button>` : ''}${s.kind === 'choice' ? (d[s.id] !== undefined && (d[s.id] || s.optional) ? h`<button class="btn" data-act="next">Next</button>` : '') : ''}</div></div>`);
  };

  const go = (n) => { S.step = n; save(S); draw(); const t = el.querySelector('h2'); if (t) t.scrollIntoView({ block: 'nearest' }); };
  const advance = () => { if (returnToSummary) { returnToSummary = false; go(SUMMARY); } else go(S.step + 1); };

  function formBody(id, d, o2) {
    const wrap = (inner) => h`<form data-form="step" novalidate>${inner}<div class="form-actions"><button class="btn" type="submit">${returnToSummary ? 'Save' : 'Next'}</button>${S.step > 0 ? h`<button class="btn ghost" type="button" data-act="back">Back</button>` : ''}</div></form>`;
    switch (id) {
      case 'quantity': return wrap(h`<div class="fields">${fld('Quantity', 'quantity', { type: 'number', value: d.quantity || '', attrs: 'min="1" step="any" inputmode="decimal"' })}${sel('Unit', 'unit', o2.units.map((u) => [u.value, u.label]), d.unit || 'SQ_FT', { blank: false })}</div>`);
      case 'price': return wrap(fld('Target price per unit in ₹ (optional)', 'target_price', { type: 'number', value: d.target_price || '', attrs: 'min="0" step="any" inputmode="decimal"' }));
      case 'date': return wrap(fld('Required delivery date', 'required_date', { type: 'date', value: d.required_date || '', attrs: `min="${tomorrow()}"` }));
      case 'location': return wrap(h`<div class="fields">${fld('City', 'delivery_city', { value: d.delivery_city ?? (session.user && session.user.city) ?? '' })}${fld('State', 'delivery_state', { value: d.delivery_state ?? (session.user && session.user.state) ?? '' })}</div>`);
      case 'certs': return wrap(h`<div class="checks">${o2.certifications.map((c) => h`<label class="check"><input type="checkbox" name="certs" value="${c}" ${raw((d.certs || []).includes(c) ? 'checked' : '')}>${c}</label>`)}</div>`);
      default: return wrap(h`<label>Notes for the factory<textarea name="notes" rows="4" maxlength="2000" placeholder="For example: distressed look, even dye, soft hand feel.">${d.notes || ''}</textarea></label>
        <label>Reference files <span class="opt-note">(optional, up to 5 files, ${o2.max_upload_mb} MB each: images, PDF, Word, Excel)</span><input type="file" name="files" multiple accept=".jpg,.jpeg,.png,.webp,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.dxf"></label>
        ${files.length ? h`<p class="small mute">Selected: ${files.map((f) => f.name).join(', ')}</p>` : ''}`);
    }
  }

  const stepSubmit = async (form, v) => {
    const id = STEPS[S.step].id;
    const d = S.data;
    if (id === 'quantity') {
      const q = Number(v.quantity);
      if (!v.quantity) throw fail('Please enter quantity.', 'quantity');
      if (!(q > 0)) throw fail('Quantity must be more than zero.', 'quantity');
      d.quantity = v.quantity; d.unit = v.unit;
    } else if (id === 'price') {
      if (v.target_price && !(Number(v.target_price) > 0)) throw fail('Please enter a price above zero, or leave it empty.', 'target_price');
      d.target_price = v.target_price || '';
    } else if (id === 'date') {
      if (!v.required_date) throw fail('Please choose a delivery date.', 'required_date');
      if (v.required_date < tomorrow()) throw fail('Please choose a date in the future.', 'required_date');
      d.required_date = v.required_date;
    } else if (id === 'location') {
      d.delivery_city = (v.delivery_city || '').trim(); d.delivery_state = (v.delivery_state || '').trim();
    } else if (id === 'certs') {
      d.certs = [].concat(v.certs || []);
    } else {
      d.notes = v.notes || '';
      const picked = Array.from(form.querySelector('input[type=file]').files);
      if (picked.length) {
        if (picked.length > 5) throw fail('You can attach up to 5 files.', 'files');
        const big = picked.find((f) => f.size > o.max_upload_mb * 1024 * 1024);
        if (big) throw fail(`"${big.name}" is too large. The maximum size is ${o.max_upload_mb} MB.`, 'files');
        files = picked;
      }
    }
    advance();
  };

  async function submit() {
    const user = session.user;
    if (!user) {
      save(S);
      sessionStorage.setItem('td_next', '#/new-requirement');
      toast('Please sign in or register to submit. Your answers are saved.');
      location.hash = '#/login';
      return;
    }
    if (user.role !== 'CLIENT') { toast('Only client accounts can submit requirements.', 'error'); return; }
    const d = S.data;
    const payload = {
      client_token: S.token, product: d.product || null, need: d.need, leather_type: d.leather_type, application: d.application,
      finish: d.finish || '', color: d.color, thickness_min: d.thickness_min, thickness_max: d.thickness_max, quantity: d.quantity,
      unit: d.unit || 'SQ_FT', requirements: d.notes || '', target_price: d.target_price || null, required_date: d.required_date,
      delivery_city: d.delivery_city || '', delivery_state: d.delivery_state || '', required_certifications: d.certs || [],
    };
    let rfq;
    try { rfq = await api.post('/rfqs/', payload); } catch (err) {
      toast(err.status === 400 ? err.message : 'Unable to submit RFQ. Please try again.', 'error');
      return;
    }
    const failed = [];
    for (let i = 0; i < files.length; i++) {
      toast(`Uploading file ${i + 1} of ${files.length}…`);
      try { const fd = new FormData(); fd.append('file', files[i]); await api.post(`/rfqs/${rfq.id}/attachments/`, fd); } catch (err) { failed.push(`${files[i].name} (${err.message})`); }
    }
    if (failed.length) toast('Your RFQ was submitted, but some files were not uploaded: ' + failed.join('; '), 'error');
    sessionStorage.removeItem(KEY);
    files = [];
    done = rfq;
    draw();
  }

  wire(el, {
    pick: (b) => { S.data[STEPS[S.step].id] = b.dataset.val; if (STEPS[S.step].id === 'thickness') { const band = o.thickness_bands.find((x) => x.label === b.dataset.val); S.data.thickness_min = band.min; S.data.thickness_max = band.max; } save(S); if (returnToSummary) { returnToSummary = false; go(SUMMARY); } else go(S.step + 1); },
    next: () => { if (returnToSummary) { returnToSummary = false; go(SUMMARY); } else go(S.step + 1); },
    back: () => { returnToSummary = false; go(Math.max(0, S.step - 1)); },
    edit: (b) => { returnToSummary = true; go(Number(b.dataset.step)); },
    step: stepSubmit,
    submit,
    again: () => { S = fresh(); files = []; done = null; save(S); draw(); },
  });
  draw();
}
