// Talks to the Django REST API. The short-lived access token is kept in memory only (never localStorage);
// the refresh token lives in an HttpOnly cookie that JavaScript cannot read.
let accessToken = null;
let refreshing = null;
export const session = { user: null };

export class ApiError extends Error {
  constructor(status, data) {
    super((data && data.detail) || 'Something went wrong. Please try again.');
    this.status = status;
    this.errors = (data && data.errors) || {};
  }
}

async function refresh() {
  if (!refreshing) {
    refreshing = fetch('/api/auth/refresh/', { method: 'POST', credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(async (r) => {
        if (!r.ok || r.status === 204) return false;
        const d = await r.json();
        accessToken = d.access;
        session.user = d.user;
        return true;
      })
      .catch(() => false)
      .finally(() => { refreshing = null; });
  }
  return refreshing;
}

export async function request(method, path, body, opts = {}) {
  const headers = { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' };
  let payload;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
  if (accessToken) headers.Authorization = 'Bearer ' + accessToken;
  let res;
  try {
    res = await fetch('/api' + path, { method, headers, body: payload, credentials: 'same-origin' });
  } catch (e) {
    throw new ApiError(0, { detail: 'Cannot reach the server. Please check your connection and try again.' });
  }
  if (res.status === 401 && opts.retry !== false && !path.startsWith('/auth/')) {
    if (await refresh()) return request(method, path, body, { ...opts, retry: false });
    accessToken = null;
    session.user = null;
    window.dispatchEvent(new Event('td:signedout'));
  }
  if (opts.raw) return res;
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b === undefined ? {} : b),
  patch: (p, b) => request('PATCH', p, b),
  del: (p) => request('DELETE', p, undefined, { raw: true }),
  async list(path, params = {}) {
    return request('GET', path + qs(params));
  },
  async download(url, name) {
    const res = await request('GET', url.replace(/^\/api/, ''), undefined, { raw: true });
    if (!res.ok) throw new ApiError(res.status, { detail: 'We could not download that file.' });
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name || 'download';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  },
};

export function qs(params) {
  const p = Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined && v !== false);
  return p.length ? '?' + p.map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v === true ? '1' : v)).join('&') : '';
}

export async function restoreSession() {
  await refresh();
  return session.user;
}

export async function signIn(path, body) {
  const d = await request('POST', path, body);
  accessToken = d.access;
  session.user = d.user;
  return d.user;
}

export async function signOut() {
  try { await request('POST', '/auth/logout/', {}); } catch (e) { /* ignore */ }
  accessToken = null;
  session.user = null;
}

let optionsCache = null;
export async function getOptions() {
  if (!optionsCache) optionsCache = await api.get('/meta/options/');
  return optionsCache;
}
