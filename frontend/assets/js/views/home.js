import { getOptions, session } from '../api.js';
import { h, mount, timeline } from '../ui.js';
import { renderWizard } from './wizard.js';

export async function homeView(page) {
  let stages = [];
  try { stages = (await getOptions()).order_stages.map((s) => s.label); } catch (e) { /* the page still works without it */ }
  mount(page, h`<section class="hero"><div><p class="small" style="color:var(--gold);letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px">Digital sourcing network for the leather industry</p>
      <h1>Source leather without visiting a single factory</h1>
      <p>Tell us what you need. Verified factories send you quotations. You compare, choose, pay and track your order, all in one place.</p>
      <div class="row"><a class="btn gold" href="#/new-requirement">Create a requirement</a><a class="btn ghost" href="#/catalog">Browse leather</a></div></div>
      <div class="card"><h3>How your order moves</h3>${timeline(stages.length ? stages : ['Requirement', 'Quotation', 'Order', 'Production', 'Delivery'], -1)}<p class="mute small" style="margin:0">You can see the current stage and the latest factory update at any time.</p></div></section>
    <section class="sec"><h2>Three simple steps</h2><div class="grid">
      <div class="card"><h3>1. Tell us what you need</h3><p class="mute">Answer a few easy questions about leather type, color, thickness and quantity.</p></div>
      <div class="card"><h3>2. Compare quotations</h3><p class="mute">Matching factories send price, lead time and certifications side by side.</p></div>
      <div class="card"><h3>3. Order and track</h3><p class="mute">Approve one quotation, pay securely and follow production until delivery.</p></div></div></section>
    <section class="sec" id="start"><h2>Create your requirement</h2><p class="mute">It takes about two minutes. You can edit everything before you submit.</p><div id="wizard"></div></section>
    <section class="sec"><h2>Are you a leather factory?</h2><p>Join as a supplier to receive matching requirements and send quotations to buyers.</p>${session.user ? '' : h`<a class="btn" href="#/register">Register your factory</a>`}</section>`);
  renderWizard(page.querySelector('#wizard'));
}

export async function newRequirementView(page) {
  mount(page, h`<div class="head"><h1>New requirement</h1><a href="#/client" class="small">Back to dashboard</a></div><div id="wizard"></div>`);
  renderWizard(page.querySelector('#wizard'));
}
