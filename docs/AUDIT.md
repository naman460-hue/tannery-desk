# Audit of the original prototype

**What existed:** one 147-line `index.html` plus a README. A leather/brown design (CSS variables), a home page with a 10-step requirement wizard, a product catalog of six hard-coded products with filter chips, a client "RFQ + factory quotation" screen and an admin "mediator" screen, all driven by JavaScript arrays in browser memory. Nothing was saved; refreshing reset everything.

**Gaps found**
- No backend, database, API, authentication, roles or authorization.
- Business data (products, factories, quotations, option lists) hard-coded in JavaScript.
- No RFQ numbers, order lifecycle, production tracking, payments, notifications, messaging, file uploads, reviews, disputes, search or reports.
- Catalog filters and the "Request sample" / "Ask mediator" buttons only showed a toast; the wizard summary could not be edited; no validation.
- User-supplied text was inserted with `innerHTML` unescaped (XSS risk).
- Not usable on phones (fixed-width tables).

**Kept:** the brown/cream/gold identity and tokens, the wizard idea (now 12 steps plus summary), the catalog cards, the timeline idea.

**Changed on purpose:** the prototype routed every quotation through the admin as a mediator. The request describes factories quoting clients directly with a side-by-side comparison, so that is what is built. The mediator role remains: admin verifies factories, can assign factories to an RFQ, sees everything, resolves disputes, and can join any conversation through the API. A platform margin on quotations is **not** implemented; say so if you want it.
