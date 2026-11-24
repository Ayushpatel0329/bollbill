// Offline test for the cloud sync code in index.html (no browser, no Supabase).
// Run:  node frontend/tests/sync_harness.js
const fs = require('fs'), vm = require('vm'), path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const cloudJs = scripts[scripts.length - 1];
const sleep = ms => new Promise(r => setTimeout(r, ms));
let fails = 0;
const ok = (c, m) => { console.log((c ? 'PASS ' : 'FAIL ') + m); if (!c) fails++; };

/* ---------- a tiny in-memory "Supabase" with the same rules as schema.sql ---------- */
function makeServer() {
  const S = { shop: { name: 'Sharma Store', upi_id: 'sharma@upi', gstin: '', low_stock_limit: 5, next_bill_no: 1 }, items: [], bills: [], down: false, calls: [] };
  const rpc = {
    save_shop: a => { Object.assign(S.shop, { name: a.p_name, upi_id: a.p_upi, gstin: a.p_gstin }); if (a.p_low_stock != null) S.shop.low_stock_limit = a.p_low_stock; return S.shop; },
    replace_items: a => { S.items = a.p_items.filter(i => i.name).map((i, n) => ({ ...i, position: n })); },
    create_bill: a => {
      const ex = S.bills.find(b => b.client_id && b.client_id === a.p_client_id); if (ex) return ex;
      if (!a.p_lines.length) throw { code: 'P0001', message: 'bill has no items' };
      if (a.p_pay === 'Udhaar' && !a.p_customer) throw { code: 'P0001', message: 'customer name is required for udhaar' };
      let no = (a.p_bill_no && !S.bills.some(b => b.bill_no === a.p_bill_no)) ? a.p_bill_no : S.shop.next_bill_no;
      S.shop.next_bill_no = Math.max(S.shop.next_bill_no, no + 1);
      const sub = a.p_lines.reduce((t, l) => t + l.qty * l.price, 0);
      const b = { id: 'id' + (S.bills.length + 1), client_id: a.p_client_id, bill_no: no, billed_at: a.p_billed_at || new Date().toISOString(), sub, disc_type: a.p_disc_type, disc_val: 0, disc: 0, gst_pct: 0, gst: 0, total: sub, pay_method: a.p_pay, customer: a.p_customer, paid: a.p_pay !== 'Udhaar', lines: a.p_lines };
      S.bills.push(b); return b;
    },
    mark_bill_paid: a => { const b = S.bills.find(x => x.bill_no === a.p_bill_no && !x.paid); if (!b) throw { code: 'P0001', message: 'bill not found or already paid' }; b.paid = true; return b; },
    clear_bills: () => { S.bills = []; },
  };
  const client = () => ({
    auth: { getSession: async () => ({ data: { session: { access_token: 'tok', user: { id: 'user-1', email: 'a@b.co' } } } }) },
    rpc: async (fn, args) => { S.calls.push(fn); if (S.down) return { data: null, error: { message: 'Failed to fetch' } }; try { return { data: rpc[fn](args), error: null }; } catch (e) { return { data: null, error: e }; } },
    from: table => {
      const q = { f: [], lim: null, ord: null };
      const run = () => {
        if (S.down) return { data: null, error: { message: 'Failed to fetch' } };
        if (table === 'shops') return { data: S.shop, error: null };
        if (table === 'items') return { data: [...S.items].sort((a, b) => a.position - b.position), error: null };
        let r = [...S.bills].sort((a, b) => b.billed_at.localeCompare(a.billed_at));
        q.f.forEach(([k, v]) => { r = r.filter(b => b[k] === v); });
        return { data: q.lim ? r.slice(0, q.lim) : r, error: null };
      };
      const b = { select: () => b, order: () => b, limit: n => { q.lim = n; return b; }, eq: (k, v) => { q.f.push([k, v]); return b; },
        maybeSingle: async () => run(), then: (res, rej) => Promise.resolve(run()).then(res, rej) };
      return b;
    },
  });
  return { S, client };
}

/* ---------- a fake browser page with the app's globals ---------- */
function makePage(server, ls = {}) {
  const els = {};
  const El = id => ({ id, value: '', textContent: '', hidden: false, disabled: false, dataset: {}, style: { setProperty() {} }, className: '', handlers: {},
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    addEventListener(t, f) { this.handlers[t] = f; }, setAttribute() {}, focus() {}, remove() {}, append() {}, appendChild() {},
    querySelector() { return El('x'); }, querySelectorAll() { return []; } });
  const document = { getElementById: id => els[id] || (els[id] = El(id)), body: El('body'), documentElement: El('html'), createElement: () => El('n'),
    addEventListener() {}, querySelector: () => null };
  const local = { ...ls };
  const localStorage = { getItem: k => (k in local ? local[k] : null), setItem: (k, v) => { local[k] = String(v); }, removeItem: k => { delete local[k]; } };
  const ctx = { document, localStorage, console: { ...console, warn() {} }, setTimeout, clearTimeout, setInterval: () => 0, crypto: globalThis.crypto, Event: class {},
    TextEncoder, Promise, JSON, Math, Number, Array, Set, Date, String, Object, Error,
    TEAM: [], SAMPLE: [{ name: 'Aata', unit: 'kg', price: 50, stock: 10 }, { name: 'Tel', unit: 'litre', price: 190, stock: null }],
    items: [], hist: [], shop: { name: 'My Shop', upi: '' }, billNo: 1, bill: [], rendered: 0,
    render() { ctx.rendered++; }, renderHist() {}, renderPrices() {}, renderPay() {}, saveShop() {}, snap() {}, addLine() {},
    supabase: { createClient: () => server.client() },
    BB_CONFIG: { SUPABASE_URL: 'https://x.supabase.co', SUPABASE_ANON_KEY: 'k' } };
  ctx.window = ctx; ctx.addEventListener = () => {}; ctx.dispatchEvent = () => {}; ctx.scrollTo = () => {}; ctx.location = { reload() {} };
  ctx.store = { get: (k, d) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } }, set: (k, v) => localStorage.setItem(k, JSON.stringify(v)) };
  // like the app does at page load: read what this browser already has
  ctx.items = ctx.store.get('vb_items', ctx.SAMPLE.map(i => ({ ...i })));
  ctx.hist = ctx.store.get('vb_hist', []); ctx.billNo = ctx.store.get('vb_no', 1); ctx.shop = ctx.store.get('vb_shop', { name: 'My Shop', upi: '' });
  vm.createContext(ctx); vm.runInContext(cloudJs, ctx);
  return { ctx, els, local, click: async id => { await els[id].handlers.click(); await sleep(30); } };
}
const newBill = (ctx, no, pay = 'Cash', cust = '') => ({ no, time: new Date(Date.now() + no).toISOString(), total: 100, sub: 100, discType: 'pct', discVal: 0, disc: 0, gstPct: 0, gst: 0, pay, cust, paid: pay !== 'Udhaar', lines: [{ name: 'Aata', unit: 'kg', qty: 2, price: 50 }] });

(async () => {
  const srv = makeServer();

  // A. first login on a browser that already has local (demo) data
  const A = makePage(srv);
  A.ctx.hist = [{ ...newBill(A.ctx, 1), cid: undefined }]; A.ctx.billNo = 2;
  await A.click('gStart');
  ok(srv.S.items.length === 2, 'A: local price list uploaded on first login');
  ok(srv.S.bills.length === 1 && srv.S.bills[0].client_id, 'A: old local bill uploaded with a client id');
  ok(A.ctx.billNo === 2 && srv.S.shop.next_bill_no === 2, 'A: bill counters agree (2)');
  ok(A.local.vb_owner === '"user-1"' || A.local.vb_owner === 'user-1', 'A: browser remembers the owner');

  // B. a new bill made in the app reaches the server
  const nb = newBill(A.ctx, 2); A.ctx.hist.unshift(nb); A.ctx.billNo = 3; A.ctx.store.set('vb_hist', A.ctx.hist); await sleep(450);
  ok(srv.S.bills.length === 2 && nb.cid, 'B: new bill saved to the cloud');

  // C. udhaar bill, then marked paid
  const ub = newBill(A.ctx, 3, 'Udhaar', 'Rahul'); A.ctx.hist.unshift(ub); A.ctx.billNo = 4; A.ctx.store.set('vb_hist', A.ctx.hist); await sleep(450);
  ok(srv.S.bills.find(b => b.bill_no === 3).paid === false, 'C: udhaar saved as unpaid');
  ub.paid = true; A.ctx.store.set('vb_hist', A.ctx.hist); await sleep(450);
  ok(srv.S.bills.find(b => b.bill_no === 3).paid === true, 'C: "mark paid" reaches the cloud');

  // D. price / shop edits
  A.ctx.items[0].price = 55; A.ctx.store.set('vb_items', A.ctx.items); A.ctx.shop.name = 'Sharma Kirana'; A.ctx.store.set('vb_shop', A.ctx.shop); await sleep(1100);
  ok(srv.S.items[0].price === 55 && srv.S.shop.name === 'Sharma Kirana', 'D: price and shop name edits saved');

  // E. second device sees everything
  const B = makePage(srv);
  await B.click('gStart');
  ok(B.ctx.hist.length === 3 && B.ctx.items.length === 2 && B.ctx.items[0].price === 55, 'E: second device loads bills and prices from the cloud');
  ok(B.ctx.billNo === 4 && B.ctx.shop.name === 'Sharma Kirana', 'E: next bill number and shop name correct');
  ok(B.ctx.hist.find(h => h.no === 3).paid === true, 'E: paid status carried over');

  // F. bill-number collision: the server (e.g. the AI) used #4 while device B did not know
  srv.S.bills.push({ id: 'idX', client_id: 'cx', bill_no: 4, billed_at: new Date().toISOString(), sub: 10, total: 10, lines: [{ name: 'Tel', unit: 'litre', qty: 1, price: 10 }], pay_method: 'Cash', customer: '', paid: true }); srv.S.shop.next_bill_no = 5;
  const cb = newBill(B.ctx, 4); B.ctx.hist.unshift(cb); B.ctx.billNo = 5; B.ctx.store.set('vb_hist', B.ctx.hist); await sleep(450);
  ok(srv.S.bills.filter(b => b.bill_no === 4).length === 1 && cb.no === 5, 'F: clashing bill number is renumbered to 5, nothing overwritten');

  // G. broken bills do not block the queue
  const bad = newBill(B.ctx, 6, 'Udhaar', ''); const good = newBill(B.ctx, 7);
  B.ctx.hist.unshift(bad); B.ctx.hist.unshift(good); B.ctx.store.set('vb_hist', B.ctx.hist); await sleep(450);
  ok(srv.S.bills.some(b => b.client_id === good.cid), 'G: a bill the database rejects does not stop later bills');

  // H. server down: app still opens, edits are remembered and uploaded later
  const H = makePage(srv, { ...A.local }); srv.S.down = true;
  await H.click('gStart');
  ok(H.ctx.items.length === 2, 'H: app opens with local data when the cloud is unreachable');
  H.ctx.items[1].price = 200; H.ctx.store.set('vb_items', H.ctx.items); await sleep(1100);
  ok(JSON.parse(H.local.vb_sync_state).dirty.items === true, 'H: offline edit is flagged for later upload');
  srv.S.down = false;
  const H2 = makePage(srv, { ...H.local }); await H2.click('gStart'); await sleep(50);
  ok(srv.S.items[1].price === 200, 'H: flagged edit is uploaded on the next start (not overwritten by old cloud data)');

  // I. a different account on the same browser never receives the previous account's data
  const I = makePage(makeServer(), { ...A.local, vb_owner: '"someone-else"' });
  await I.click('gStart');
  ok(I.ctx.hist.length === 0 && I.ctx.items.length === 0, 'I: other account starts clean (no leaked bills)');

  // J. "Delete all saved bills" is mirrored
  A.ctx.hist.length = 0; A.ctx.store.set('vb_hist', A.ctx.hist); await sleep(450);
  ok(srv.S.bills.length === 0, 'J: clearing history clears the cloud copy');

  console.log(fails ? `\n${fails} FAILED` : '\nall passed'); process.exit(fails ? 1 : 0);
})();
