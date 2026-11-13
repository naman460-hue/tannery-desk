import { api } from '../api.js';
import { h, mount, loading, errorBox, empty, pill, inr, num, fdate, wire } from '../ui.js';
import { dataTable } from '../table.js';

const statCard = (n, label, hot) => h`<div class="card stat ${hot && n ? 'hot' : ''}"><b>${n}</b><span>${label}</span></div>`;

export async function clientDashboard(page) {
  mount(page, loading('Loading your dashboard…'));
  async function load() {
    try {
      const [s, rfqs, orders] = await Promise.all([api.get('/dashboard/'), api.get('/rfqs/?status=QUOTATION_RECEIVED&page_size=20'), api.get('/orders/?bucket=active&page_size=50')]);
      const pay = orders.results.filter((o) => o.next_payment);
      const confirm = orders.results.filter((o) => o.status === 'DELIVERED');
      const first = rfqs.results[0];
      mount(page, h`<div class="head"><h1>My dashboard</h1><a class="btn gold" href="#/new-requirement">Create New Requirement</a></div>
        <div class="stats">${statCard(s.quotes_to_review, 'RFQs with quotations to review', true)}${statCard(s.payments_due, 'Payments due', true)}${statCard(s.active_rfqs, 'Open requirements')}${statCard(s.active_orders, 'Active orders')}${statCard(s.completed_orders, 'Completed orders')}</div>
        ${rfqs.results.map((r) => h`<div class="next"><strong>${r.number}: ${r.quotation_count} quotation${r.quotation_count === 1 ? '' : 's'} ready to compare.</strong><a class="btn gold" href="#/rfqs/${r.id}">Compare quotations</a></div>`)}
        ${pay.map((o) => h`<div class="next"><strong>${o.number}: ${o.next_payment.purpose === 'ADVANCE' ? 'advance payment' : 'remaining payment'} of ${inr(o.next_payment.amount)} is due.</strong><a class="btn gold" href="#/orders/${o.id}">${o.next_payment.label}</a></div>`)}
        ${confirm.map((o) => h`<div class="next"><strong>${o.number} was delivered. Please confirm it.</strong><a class="btn gold" href="#/orders/${o.id}">Review order</a></div>`)}
        ${!first && !pay.length && !confirm.length && !s.active_rfqs && !s.active_orders ? h`<div class="next"><strong>Ready to source leather? Start with a short requirement form.</strong><a class="btn gold" href="#/new-requirement">Create New Requirement</a></div>` : ''}
        <section class="sec"><h2>My requirements</h2><div id="rfqs"></div></section><section class="sec"><h2>My orders</h2><div id="orders"></div></section>`);
      dataTable(page.querySelector('#rfqs'), { endpoint: '/rfqs/', search: 'Search RFQ number or leather', loading: 'Loading your requirements…', empty: "You haven't created a requirement yet.",
        filters: [{ key: 'status', label: 'All statuses', options: [['SUBMITTED', 'Submitted'], ['MATCHING', 'Factory matching'], ['QUOTATION_RECEIVED', 'Quotation received'], ['ORDER_CREATED', 'Order created'], ['CANCELLED', 'Cancelled']] }],
        columns: [['RFQ', (r) => h`<a href="#/rfqs/${r.id}"><strong>${r.number}</strong></a>`], ['Requirement', (r) => r.title], ['Quantity', (r) => `${num(r.quantity)} ${r.unit_label}`], ['Quotations', (r) => r.quotation_count], ['Status', (r) => pill(r.status, r.status_label)], ['Created', (r) => fdate(r.created_at)], ['', (r) => h`<a class="btn sm ghost" href="#/rfqs/${r.id}">Open</a>`]] });
      dataTable(page.querySelector('#orders'), { endpoint: '/orders/', search: 'Search order or factory', loading: 'Loading your orders…', empty: 'You have no orders yet. Orders appear after you accept a quotation.',
        columns: [['Order', (o) => h`<a href="#/orders/${o.id}"><strong>${o.number}</strong></a>`], ['Requirement', (o) => o.title], ['Factory', (o) => o.factory_name], ['Total', (o) => inr(o.total_amount)], ['Stage', (o) => pill(o.status, o.status_label)], ['Payment', (o) => pill(o.payment_status, o.payment_status_label)], ['', (o) => h`<a class="btn sm ghost" href="#/orders/${o.id}">Track</a>`]] });
    } catch (err) { mount(page, errorBox(err)); }
  }
  wire(page, { retry: load });
  load();
}
