import { api, session, getOptions, qs } from '../api.js';
import { h, mount, raw, wire, openModal, loading, empty, errorBox, debounce, num, $ } from '../ui.js';
import { factoryModal, stars } from '../shared.js';
import { startFromProduct } from './wizard.js';

const card = (p) => h`<article class="card"><div class="swatch" style="background-color:${p.color_hex};${p.image ? `background-image:url('${encodeURI(p.image)}')` : ''}" role="img" aria-label="${p.color} leather"></div>
  <h3>${p.name}</h3><p class="small mute" style="margin-bottom:8px">${p.factory.name} · ${p.factory.city}${p.factory.state ? ', ' + p.factory.state : ''}</p>
  <p><span class="tag">${p.leather_type}</span><span class="tag">${p.finish}</span><span class="tag">${p.application}</span><span class="tag">${p.thickness_display}</span>${p.sample_available ? h`<span class="tag v">Sample available</span>` : ''}</p>
  <p class="small">MOQ <strong>${num(p.moq)} ${p.unit_label}</strong> · Lead time <strong>${p.lead_time_days} days</strong></p>
  <p>${p.certifications.map((c) => h`<span class="tag v">${c}</span>`)}</p>
  <div class="form-actions" style="margin-top:6px"><button class="btn sm" data-act="detail" data-id="${p.id}">View details</button><button class="btn sm gold" data-act="quote" data-id="${p.id}">Request quote</button></div></article>`;

export async function catalogView(page) {
  const o = await getOptions();
  const f = { q: '', leather_type: '', application: '', finish: '', color: '', band: '', certification: '', location: '', moq: '', sample: false };
  let pg = 1;
  let items = [];
  const opt = (list) => list.map((v) => h`<option value="${v}">${v}</option>`);
  mount(page, h`<div class="head"><div><h1>Leather catalog</h1><p class="mute" style="margin:0">Browse what verified factories make. Found something close? Request a quote in one click.</p></div></div>
    <form class="card" data-form="none" onsubmit="return false"><div class="fields">
    <label>Search<input type="search" data-input="f" name="q" placeholder="Name, factory, city…"></label>
    <label>Leather type<select data-change="f" name="leather_type"><option value="">Any</option>${opt(o.leather_types)}</select></label>
    <label>Application<select data-change="f" name="application"><option value="">Any</option>${opt(o.applications)}</select></label>
    <label>Finish<select data-change="f" name="finish"><option value="">Any</option>${opt(o.finishes)}</select></label>
    <label>Color<select data-change="f" name="color"><option value="">Any</option>${o.colors.map((c) => h`<option>${c.name}</option>`)}</select></label>
    <label>Thickness<select data-change="f" name="band"><option value="">Any</option>${o.thickness_bands.map((b) => h`<option value="${b.label}">${b.label}</option>`)}</select></label>
    <label>Certification<select data-change="f" name="certification"><option value="">Any</option>${opt(o.certifications)}</select></label>
    <label>Factory location<select data-change="f" name="location"><option value="">Anywhere</option>${opt(o.locations)}</select></label>
    <label>Your quantity <span class="opt-note">(shows items you can order)</span><input type="number" min="0" step="any" data-input="f" name="moq" placeholder="e.g. 1000"></label>
    <label class="check"><input type="checkbox" data-change="f" name="sample"> Sample available</label></div>
    <div class="form-actions"><button type="button" class="btn sm ghost" data-act="clear">Clear filters</button></div></form>
    <div id="results" class="sec" style="margin-top:20px"></div>`);
  const results = $('#results', page);

  async function load() {
    mount(results, loading('Loading leather…'));
    const band = o.thickness_bands.find((b) => b.label === f.band);
    try {
      const data = await api.list('/products/', { q: f.q, leather_type: f.leather_type, application: f.application, finish: f.finish, color: f.color, certification: f.certification, location: f.location, moq: f.moq, sample: f.sample, thickness_min: band && band.min, thickness_max: band && band.max, page: pg, page_size: 12 });
      items = data.results;
      mount(results, items.length ? h`<p class="mute small">${data.count} result${data.count === 1 ? '' : 's'}</p><div class="grid">${items.map(card)}</div>${data.next || pg > 1 ? h`<div class="pager"><button class="btn sm ghost" data-act="pg" data-d="-1" ${raw(pg <= 1 ? 'disabled' : '')}>Previous</button><span>Page ${pg}</span><button class="btn sm ghost" data-act="pg" data-d="1" ${raw(data.next ? '' : 'disabled')}>Next</button></div>` : ''}` : empty('No leather matches these filters. Try clearing a filter, or create a requirement and let factories quote for you.'));
    } catch (err) { mount(results, errorBox(err)); }
  }
  const reload = () => { pg = 1; load(); };
  const typed = debounce(reload);

  const showDetail = async (p) => {
    const m = openModal(p.name, h`<div class="swatch" style="background-color:${p.color_hex};${p.image ? `background-image:url('${encodeURI(p.image)}')` : ''}"></div>
      <p><span class="tag">${p.leather_type}</span><span class="tag">${p.finish}</span><span class="tag">${p.application}</span><span class="tag">${p.color}</span>${p.sample_available ? h`<span class="tag v">Sample available</span>` : ''}</p>
      ${p.description ? h`<p>${p.description}</p>` : ''}
      <dl class="facts"><dt>Thickness</dt><dd>${p.thickness_display}</dd><dt>Minimum order</dt><dd>${num(p.moq)} ${p.unit_label}</dd><dt>Lead time</dt><dd>${p.lead_time_days} days</dd><dt>Certifications</dt><dd>${p.certifications.join(', ') || '—'}</dd>
      <dt>Factory</dt><dd>${p.factory.name}, ${p.factory.city}<br><span class="y">${stars(p.factory.rating)}</span> <button class="btn sm ghost" data-act="factory" data-id="${p.factory.id}">View factory profile</button></dd></dl>
      <div class="form-actions"><button class="btn gold" data-act="quote" data-id="${p.id}">Request quote</button></div>`);
    wire(m, { factory: (b) => factoryModal(b.dataset.id), quote: () => { m.close(); requestQuote(p); } });
  };
  const requestQuote = (p) => {
    startFromProduct(p, o);
    if (!session.user) sessionStorage.setItem('td_next', '#/new-requirement');
    location.hash = session.user ? '#/new-requirement' : '#/login';
  };

  wire(page, {
    f: (el) => { f[el.name] = el.type === 'checkbox' ? el.checked : el.value.trim(); el.tagName === 'INPUT' && el.type !== 'checkbox' ? typed() : reload(); },
    clear: () => { page.querySelectorAll('form select,form input').forEach((e) => { if (e.type === 'checkbox') e.checked = false; else e.value = ''; }); Object.keys(f).forEach((k) => { f[k] = k === 'sample' ? false : ''; }); reload(); },
    detail: (b) => showDetail(items.find((p) => String(p.id) === b.dataset.id)),
    quote: (b) => requestQuote(items.find((p) => String(p.id) === b.dataset.id)),
    pg: (b) => { pg += Number(b.dataset.d); load(); },
    retry: load,
  });
  load();
}
