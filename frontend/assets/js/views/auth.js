import { api, signIn, getOptions } from '../api.js';
import { h, mount, raw, wire, fld, toast } from '../ui.js';

export const roleHome = (u) => (u.role === 'ADMIN' ? '#/admin' : u.role === 'FACTORY' ? '#/factory' : '#/client');

function afterLogin(user) {
  window.dispatchEvent(new Event('td:session'));
  const next = sessionStorage.getItem('td_next');
  sessionStorage.removeItem('td_next');
  location.hash = next || roleHome(user);
}

export function loginView(page, { admin = false } = {}) {
  const note = sessionStorage.getItem('td_next') ? h`<div class="banner">Please sign in or create an account to continue. Your answers are saved.</div>` : '';
  mount(page, h`<div class="card narrow" style="max-width:460px;margin:20px auto"><h1>${admin ? 'Admin sign in' : 'Sign in'}</h1>${note}
    <form data-form="login" class="narrow" novalidate>${fld('Email', 'email', { type: 'email', required: true, attrs: 'autocomplete="username"' })}
    ${fld('Password', 'password', { type: 'password', required: true, attrs: 'autocomplete="current-password"' })}
    <div class="form-actions"><button class="btn" type="submit">Sign in</button><a href="#/forgot">Forgot password?</a></div></form>
    ${admin ? '' : h`<p class="mute" style="margin-top:18px">New here? <a href="#/register">Create an account</a></p>`}</div>`);
  wire(page, {
    login: async (form, d) => {
      if (!d.email.trim()) throw Object.assign(new Error('Please enter your email.'), { errors: { email: ['Please enter your email.'] } });
      if (!d.password) throw Object.assign(new Error('Please enter your password.'), { errors: { password: ['Please enter your password.'] } });
      afterLogin(await signIn('/auth/login/', { email: d.email.trim(), password: d.password, ...(admin ? { portal: 'ADMIN' } : {}) }));
    },
  });
}

export function registerView(page) {
  let role = 'CLIENT';
  const draw = () => mount(page, h`<div class="card" style="max-width:640px;margin:20px auto"><h1>Create your account</h1>
    <div class="opts" role="radiogroup" aria-label="Account type"><button class="opt ${role === 'CLIENT' ? 'on' : ''}" data-act="role" data-role="CLIENT">I am a buyer (client)</button><button class="opt ${role === 'FACTORY' ? 'on' : ''}" data-act="role" data-role="FACTORY">I am a leather factory</button></div>
    <form data-form="register" novalidate><div class="fields">${fld('Your name', 'name', { required: true })}${fld(role === 'FACTORY' ? 'Factory name' : 'Company name (optional)', 'company_name', { required: role === 'FACTORY' })}
    ${fld('Email', 'email', { type: 'email', required: true })}${fld('Phone', 'phone', { type: 'tel', required: true, attrs: 'placeholder="+91 98765 43210"' })}
    ${fld('City', 'city')}${fld('State', 'state')}
    ${fld('Password', 'password', { type: 'password', required: true, note: '(8+ characters)', attrs: 'autocomplete="new-password"' })}${fld('Confirm password', 'confirm_password', { type: 'password', required: true, attrs: 'autocomplete="new-password"' })}</div>
    ${role === 'FACTORY' ? h`<p class="mute small">After you register, the Tannery Desk team verifies your factory before you can receive RFQs.</p>` : ''}
    <div class="form-actions"><button class="btn" type="submit">Create account</button><a href="#/login">I already have an account</a></div></form></div>`);
  draw();
  wire(page, {
    role: (el) => { role = el.dataset.role; draw(); },
    register: async (form, d) => {
      const user = await signIn('/auth/register/', { ...d, role });
      toast('Account created. Welcome to Tannery Desk.');
      afterLogin(user);
      if (user.role === 'FACTORY') location.hash = '#/factory/profile';
    },
  });
}

export function forgotView(page) {
  mount(page, h`<div class="card" style="max-width:460px;margin:20px auto"><h1>Forgot password</h1><p class="mute">Enter your email and we will send you a link to choose a new password.</p>
    <form data-form="forgot" novalidate>${fld('Email', 'email', { type: 'email', required: true })}<div class="form-actions"><button class="btn" type="submit">Send reset link</button><a href="#/login">Back to sign in</a></div></form></div>`);
  wire(page, { forgot: async (form, d) => { const r = await api.post('/auth/password-reset/', { email: d.email }); form.innerHTML = `<p>${r.detail.replace(/[<>&]/g, '')}</p>`; } });
}

export function resetView(page, ctx) {
  const { uid, token } = ctx.query;
  mount(page, h`<div class="card" style="max-width:460px;margin:20px auto"><h1>Choose a new password</h1>
    <form data-form="reset" novalidate>${fld('New password', 'new_password', { type: 'password', required: true, attrs: 'autocomplete="new-password"' })}${fld('Confirm new password', 'confirm', { type: 'password', required: true })}
    <div class="form-actions"><button class="btn" type="submit">Save new password</button></div></form></div>`);
  wire(page, {
    reset: async (form, d) => {
      if (d.new_password !== d.confirm) throw Object.assign(new Error('The two passwords do not match.'), { errors: { confirm: ['The two passwords do not match.'] } });
      await api.post('/auth/password-reset/confirm/', { uid, token, new_password: d.new_password });
      toast('Password changed. Please sign in.');
      location.hash = '#/login';
    },
  });
}
