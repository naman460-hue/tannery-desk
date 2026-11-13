// Small UI helpers: safe HTML templates, toasts, modals, forms, status pills, timelines.
export class Raw { constructor(s) { this.s = s; } }
export const raw = (s) => new Raw(String(s));
const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ESC[c]);
const part = (v) => (v instanceof Raw ? v.s : Array.isArray(v) ? v.map(part).join('') : v === null || v === undefined || v === false ? '' : esc(v));
// h`...${value}...` escapes every value unless it is already safe HTML (another h`` result).
export const h = (strings, ...vals) => new Raw(strings.reduce((a, s, i) => a + s + (i < vals.length ? part(vals[i]) : ''), ''));
export const mount = (el, r) => { el.innerHTML = r instanceof Raw ? r.s : esc(r); };
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// ---- formatting --------------------------------------------------------------------------------
export const inr = (v) => '₹' + Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
export const num = (v) => Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 });
export const fdate = (d) => (d ? new Date(d.length === 10 ? d + 'T00:00:00' : d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—');
export const fdatetime = (d) => (d ? new Date(d).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—');
const OK = ['VERIFIED', 'COMPLETED', 'PAID', 'ACCEPTED', 'DELIVERED', 'RESOLVED', 'QUOTED'];
const BAD = ['REJECTED', 'SUSPENDED', 'CANCELLED', 'FAILED', 'DECLINED', 'WITHDRAWN', 'CLOSED'];
export function pill(status, label) {
  const cls = OK.includes(status) ? 'ok' : BAD.includes(status) ? 'bad' : ['PENDING', 'CREATED', 'OPEN', 'NEW', 'ORDER_CREATED', 'ADVANCE_PAID'].includes(status) ? 'warn' : '';
  return h`<span class="pill ${cls}">${label || String(status).replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase())}</span>`;
}
export const timeline = (labels, current) => h`<div class="tl" role="list">${labels.map((l, i) => h`<div role="listitem" class="${i < current ? 'done' : i === current ? 'now' : ''}">${l}</div>`)}</div>`;
export const loading = (text = 'Loading…') => h`<div class="state" role="status"><span class="spin"></span>${text}</div>`;
export const empty = (text) => h`<div class="state">${text}</div>`;
export const errorBox = (err, retry = true) => h`<div class="state err" role="alert"><p>${err.message || 'Something went wrong. Please try again.'}</p>${retry ? h`<button class="btn sm" data-act="retry">Try again</button>` : ''}</div>`;

// ---- toast ------------------------------------------------------------------------------------
let toastTimer;
export function toast(message, kind = '') {
  const t = document.getElementById('toast');
  t.textContent = message;
  t.className = 'toast ' + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hide'), kind === 'error' ? 5000 : 3000);
}

// ---- event wiring ---------------------------------------------------------------------------------
// handlers: { actionName: (element, event) => ..., formName: async (form, data) => ... }
export function wire(root, handlers) {
  root.addEventListener('click', (e) => {
    const el = e.target.closest('[data-act]');
    if (!el || !root.contains(el) || el.disabled) return;
    const fn = handlers[el.dataset.act];
    if (fn) { e.preventDefault(); busy(el, () => fn(el, e)); }
  });
  root.addEventListener('submit', (e) => {
    const form = e.target.closest('form[data-form]');
    if (!form) return;
    e.preventDefault();
    const fn = handlers[form.dataset.form];
    if (fn) runForm(form, fn);
  });
  root.addEventListener('change', (e) => {
    const el = e.target.closest('[data-change]');
    if (el && handlers[el.dataset.change]) handlers[el.dataset.change](el, e);
  });
  root.addEventListener('input', (e) => {
    const el = e.target.closest('[data-input]');
    if (el && handlers[el.dataset.input]) handlers[el.dataset.input](el, e);
  });
}

async function busy(el, fn) {
  if (el.dataset.busy) return;
  el.dataset.busy = '1';
  try {
    const r = fn();
    if (r && r.then) await r;
  } catch (err) {
    toast(err.message || 'Something went wrong. Please try again.', 'error');
  } finally {
    delete el.dataset.busy;
  }
}

export function formValues(form) {
  const out = {};
  new FormData(form).forEach((v, k) => {
    if (v instanceof File) return;
    if (k in out) out[k] = [].concat(out[k], v); else out[k] = v;
  });
  return out;
}

export function clearErrors(form) {
  $$('.field-error,.form-error', form).forEach((e) => e.remove());
  $$('.bad', form).forEach((e) => e.classList.remove('bad'));
}

export function showErrors(form, err) {
  clearErrors(form);
  const fields = (err && err.errors) || {};
  let placed = false;
  Object.entries(fields).forEach(([name, msgs]) => {
    const input = form.querySelector(`[name="${name}"]`);
    const text = [].concat(msgs).filter((m) => typeof m === 'string').join(' ');
    if (input && text) {
      input.classList.add('bad');
      const p = document.createElement('div');
      p.className = 'field-error';
      p.textContent = text;
      (input.closest('label') || input).insertAdjacentElement('afterend', p);
      placed = true;
    }
  });
  const box = document.createElement('div');
  box.className = 'form-error';
  box.setAttribute('role', 'alert');
  box.textContent = (err && err.message) || 'Something went wrong. Please try again.';
  const actions = form.querySelector('.form-actions');
  if (actions) actions.insertAdjacentElement('beforebegin', box); else form.appendChild(box);
  if (!placed) box.scrollIntoView({ block: 'nearest' });
}

// Runs a form handler with the submit button disabled (stops double submits) and shows friendly errors.
export async function runForm(form, fn) {
  if (form.dataset.busy) return;
  form.dataset.busy = '1';
  const buttons = $$('button[type=submit],button:not([type])', form);
  buttons.forEach((b) => { b.disabled = true; });
  clearErrors(form);
  try {
    await fn(form, formValues(form));
  } catch (err) {
    showErrors(form, err);
  } finally {
    delete form.dataset.busy;
    buttons.forEach((b) => { b.disabled = false; });
  }
}

// ---- modal -------------------------------------------------------------------------------------------
export function openModal(title, body, { onClose } = {}) {
  const root = document.getElementById('modal-root');
  const el = document.createElement('div');
  el.className = 'overlay';
  el.innerHTML = `<div class="modal" role="dialog" aria-modal="true" aria-label="${esc(title)}"><header><h2>${esc(title)}</h2><button class="x" aria-label="Close" data-close>×</button></header><div class="body"></div></div>`;
  mount($('.body', el), body);
  const previous = document.activeElement;
  const close = () => {
    document.removeEventListener('keydown', onKey);
    el.remove();
    if (previous && previous.focus) previous.focus();
    if (onClose) onClose();
  };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  el.addEventListener('click', (e) => { if (e.target === el || e.target.closest('[data-close]')) close(); });
  document.addEventListener('keydown', onKey);
  root.appendChild(el);
  const first = el.querySelector('input,select,textarea,button:not(.x)') || el.querySelector('.x');
  if (first) first.focus();
  el.close = close;
  el.body = $('.body', el);
  return el;
}

export function confirmBox(title, message, okLabel = 'Yes, continue', danger = false) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => { if (!done) { done = true; resolve(v); } };
    const m = openModal(title, h`<p>${message}</p><div class="form-actions"><button class="btn ${danger ? 'danger' : ''}" data-ok>${okLabel}</button><button class="btn ghost" data-close>Cancel</button></div>`, { onClose: () => finish(false) });
    m.querySelector('[data-ok]').onclick = () => { finish(true); m.close(); };
  });
}

// Reusable form field helpers
export const fld = (label, name, { type = 'text', value = '', required = false, attrs = '', note = '' } = {}) =>
  h`<label>${label}${note ? h` <span class="opt-note">${note}</span>` : ''}<input type="${type}" name="${name}" value="${value ?? ''}" ${raw(required ? 'required' : '')} ${raw(attrs)}></label>`;
export const sel = (label, name, options, value = '', { blank = '', required = false } = {}) =>
  h`<label>${label}<select name="${name}" ${raw(required ? 'required' : '')}>${blank !== false ? h`<option value="">${blank || 'Select…'}</option>` : ''}${options.map((o) => { const [v, l] = Array.isArray(o) ? o : [o, o]; return h`<option value="${v}" ${raw(String(v) === String(value) ? 'selected' : '')}>${l}</option>`; })}</select></label>`;

export function pager(data, page) {
  if (!data || (!data.next && page <= 1)) return '';
  return h`<div class="pager"><button class="btn sm ghost" data-act="page" data-page="${page - 1}" ${raw(page <= 1 ? 'disabled' : '')}>Previous</button><span>Page ${page} · ${data.count} in total</span><button class="btn sm ghost" data-act="page" data-page="${page + 1}" ${raw(data.next ? '' : 'disabled')}>Next</button></div>`;
}
export const debounce = (fn, ms = 350) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
