// A small searchable, filterable, paginated table used on most dashboards.
import { api } from './api.js';
import { h, mount, raw, loading, empty, errorBox, debounce, $ } from './ui.js';

export function dataTable(el, cfg) {
  const state = { page: 1, q: '', filters: {} };
  const pageSize = cfg.pageSize || 20;
  el.innerHTML = '';
  const bar = document.createElement('div');
  bar.className = 'toolbar';
  const body = document.createElement('div');
  el.append(bar, body);
  mount(bar, h`${cfg.search ? h`<input type="search" placeholder="${cfg.search}" aria-label="Search" data-q>` : ''}${(cfg.filters || []).map((f) => h`<select aria-label="${f.label}" data-filter="${f.key}"><option value="">${f.label}</option>${f.options.map(([v, l]) => h`<option value="${v}">${l}</option>`)}</select>`)}`);
  if (!cfg.search && !(cfg.filters || []).length) bar.remove();

  async function load() {
    mount(body, loading(cfg.loading || 'Loading…'));
    try {
      const params = { ...(cfg.params || {}), ...state.filters, page: state.page, page_size: pageSize };
      if (state.q) params[cfg.searchParam || 'q'] = state.q;
      const data = await api.list(cfg.endpoint, params);
      const rows = data.results;
      if (!rows.length) {
        mount(body, empty(state.q || Object.values(state.filters).some(Boolean) ? 'Nothing matches your search.' : cfg.empty || 'Nothing to show yet.'));
      } else {
        mount(body, h`<div class="tbl"><table class="stack"><thead><tr>${cfg.columns.map(([l]) => h`<th>${l}</th>`)}</tr></thead><tbody>${rows.map((r) => h`<tr class="${cfg.rowClass ? cfg.rowClass(r) : ''}">${cfg.columns.map(([l, fn]) => h`<td data-label="${l}" class="${l === '' ? 'act' : ''}">${fn(r)}</td>`)}</tr>`)}</tbody></table></div>
          ${data.next || state.page > 1 ? h`<div class="pager"><button class="btn sm ghost" data-pg="-1" ${raw(state.page <= 1 ? 'disabled' : '')}>Previous</button><span>Page ${state.page} · ${data.count} in total</span><button class="btn sm ghost" data-pg="1" ${raw(data.next ? '' : 'disabled')}>Next</button></div>` : ''}`);
      }
      if (cfg.onLoaded) cfg.onLoaded(data);
    } catch (err) {
      mount(body, errorBox(err));
      const b = $('[data-act=retry]', body);
      if (b) b.onclick = load;
    }
  }
  const search = debounce(() => { state.page = 1; load(); });
  el.addEventListener('input', (e) => { if (e.target.matches('[data-q]')) { state.q = e.target.value.trim(); search(); } });
  el.addEventListener('change', (e) => { if (e.target.matches('[data-filter]')) { state.filters[e.target.dataset.filter] = e.target.value; state.page = 1; load(); } });
  el.addEventListener('click', (e) => {
    const b = e.target.closest('[data-pg]');
    if (b && !b.disabled) { state.page += Number(b.dataset.pg); load(); }
  });
  load();
  return { reload: load };
}
