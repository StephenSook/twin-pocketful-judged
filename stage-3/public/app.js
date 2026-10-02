'use strict';
// Pocketful browser client. Renders every screen from the API; user-supplied
// text is only ever set through textContent, never parsed as markup.
(() => {
  const TOKEN_KEY = 'pocketful.token';
  const INTRO_KEY = 'pocketful.intro';
  const REQUEST_TIMEOUT_MS = 15000;
  const PROTECTED = new Set(['/', '/requests', '/split', '/authorizations']);
  const NAV = [
    ['/', 'Home'],
    ['/requests', 'Requests'],
    ['/split', 'Split'],
    ['/authorizations', 'Holds'],
  ];
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const SVG_NS = 'http://www.w3.org/2000/svg';

  // ---- DOM ---------------------------------------------------------------

  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    if (props) {
      for (const [k, val] of Object.entries(props)) {
        if (val === undefined || val === null || val === false) continue;
        if (k === 'class') el.className = val;
        else if (k === 'testid') el.setAttribute('data-testid', val);
        else if (k === 'text') el.textContent = val;
        else if (k === 'on') for (const [ev, fn] of Object.entries(val)) el.addEventListener(ev, fn);
        else if (k === 'value') el.value = val;
        else el.setAttribute(k, val === true ? '' : String(val));
      }
    }
    append(el, kids);
    return el;
  }

  function append(el, kids) {
    for (const kid of kids.flat(Infinity)) {
      if (kid === undefined || kid === null || kid === false) continue;
      el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }

  // replaceChildren that skips null/false children (never renders "null").
  function fill(el, ...kids) {
    el.replaceChildren();
    return append(el, kids);
  }

  function icon(name) {
    const paths = {
      lock: 'M7 11V8a5 5 0 0 1 10 0v3M5 11h14v10H5z',
      globe: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18',
      out: 'M7 17L17 7M9 7h8v8',
      in: 'M17 7L7 17M15 17H7V9',
      swap: 'M4 8h13l-3-3M20 16H7l3 3',
      check: 'M5 12l5 5L20 7',
      alert: 'M12 8v5M12 17h.01M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
      clock: 'M12 7v5l3 2M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18',
      dots: 'M5 12h.01M12 12h.01M19 12h.01',
      refresh: 'M20 11a8 8 0 0 0-14.3-4.9L4 8M4 4v4h4M4 13a8 8 0 0 0 14.3 4.9L20 16M20 20v-4h-4',
      arrow: 'M5 12h14M13 6l6 6-6 6',
      x: 'M6 6l12 12M18 6L6 18',
    };
    const s = document.createElementNS(SVG_NS, 'svg');
    s.setAttribute('viewBox', '0 0 24 24');
    s.setAttribute('class', `icon icon-${name}`);
    s.setAttribute('aria-hidden', 'true');
    s.setAttribute('focusable', 'false');
    const p = document.createElementNS(SVG_NS, 'path');
    p.setAttribute('d', paths[name]);
    s.append(p);
    return s;
  }

  function art(name, cls) {
    return h('img', { class: `art ${cls || ''}`, src: `/static/art/${name}.webp`, alt: '', loading: 'lazy', decoding: 'async' });
  }

  function blobs(cls) {
    const s = document.createElementNS(SVG_NS, 'svg');
    s.setAttribute('class', `blobs ${cls || ''}`);
    s.setAttribute('viewBox', '0 0 400 300');
    s.setAttribute('aria-hidden', 'true');
    s.setAttribute('focusable', 'false');
    s.setAttribute('preserveAspectRatio', 'xMidYMid slice');
    const shapes = [
      ['blob blob-a', 'M318 40c42 22 66 78 44 120s-82 54-128 36-86-46-74-92 116-86 158-64z'],
      ['blob blob-b', 'M76 196c34-16 86-2 100 34s-14 70-56 72-74-20-80-50 2-40 36-56z'],
    ];
    for (const [c, d] of shapes) {
      const p = document.createElementNS(SVG_NS, 'path');
      p.setAttribute('class', c);
      p.setAttribute('d', d);
      s.append(p);
    }
    return s;
  }

  function button(label, props = {}) {
    const { variant = 'primary', chip = true, ...rest } = props;
    const labelSpan = h('span', { class: 'btn-label' }, label);
    const el = h('button', { type: 'button', class: `btn btn-${variant}`, ...rest },
      h('span', { class: 'btn-face' }, labelSpan),
      chip ? h('span', { class: 'btn-chip', 'aria-hidden': 'true' }, icon('arrow')) : null);
    el._label = labelSpan;
    return el;
  }

  function setBusy(btn, busy, busyLabel) {
    if (busy) {
      btn._idle = btn._idle || btn._label.textContent;
      btn._label.textContent = busyLabel;
      btn.disabled = true;
      btn.classList.add('is-pending');
      btn.setAttribute('aria-busy', 'true');
    } else {
      if (btn._idle) btn._label.textContent = btn._idle;
      btn.disabled = false;
      btn.classList.remove('is-pending');
      btn.removeAttribute('aria-busy');
    }
  }

  function field(id, label, input, hint) {
    input.id = id;
    const hintEl = hint ? h('span', { class: 'field-hint', id: `${id}-hint` }, hint) : null;
    if (hintEl) input.setAttribute('aria-describedby', hintEl.id);
    return h('div', { class: 'field' }, h('label', { for: id, class: 'field-label' }, label), input, hintEl);
  }

  function textInput(testid, props = {}) {
    return h('input', { type: 'text', testid, class: 'input', autocomplete: 'off', spellcheck: 'false', ...props });
  }

  function handleInput(testid, placeholder) {
    const input = textInput(testid, { autocapitalize: 'none', placeholder: placeholder || 'their handle' });
    return { input, wrap: h('div', { class: 'input-prefix' }, h('span', { class: 'prefix', 'aria-hidden': 'true' }, '@'), input) };
  }

  function chip(kind, label, iconName) {
    return h('span', { class: `chip chip-${kind}` }, iconName ? icon(iconName) : null, h('span', null, label));
  }

  function stretchHeading(tag, text, cls) {
    const el = h(tag, { class: `display ${cls || ''}`, 'aria-label': text });
    const words = text.split(' ');
    words.forEach((w, i) => {
      const span = h('span', { class: 'word', 'aria-hidden': 'true' }, w);
      span.style.setProperty('--i', String(i));
      el.append(span);
      if (i < words.length - 1) el.append(document.createTextNode(' '));
    });
    return el;
  }

  function scribble(text, cls) {
    const el = h('p', { class: `scribble ${cls || ''}`, 'aria-hidden': 'true' });
    Array.from(text).forEach((ch, i) => {
      const span = h('span', { class: 'letter' }, ch);
      span.style.setProperty('--i', String(i));
      el.append(span);
    });
    return el;
  }

  // ---- token and API -----------------------------------------------------

  function getToken() {
    try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
  }
  function setToken(t) {
    try { localStorage.setItem(TOKEN_KEY, t); } catch { /* private mode */ }
  }
  function clearToken() {
    try { localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ }
  }

  // Resolves { kind: 'ok', status, data } | { kind: 'refused', status, code,
  // message } | { kind: 'unknown' }. A lost connection, a timeout, a server
  // error or an unreadable reply is 'unknown': the outcome is not known.
  async function api(method, path, { body, key } = {}) {
    const headers = { Accept: 'application/json' };
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (key) headers['Idempotency-Key'] = key;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
    try {
      const res = await fetch(path, {
        method, headers, body: body === undefined ? undefined : JSON.stringify(body),
        signal: ctrl.signal, cache: 'no-store', credentials: 'omit', redirect: 'error',
      });
      let data = null;
      try { data = await res.json(); } catch { data = null; }
      if (res.status >= 500) return { kind: 'unknown' };
      if (res.ok) return data === null ? { kind: 'unknown' } : { kind: 'ok', status: res.status, data };
      const err = data && data.error ? data.error : {};
      const out = { kind: 'refused', status: res.status, code: err.code || 'error', message: err.message || '' };
      if (res.status === 401 && !path.startsWith('/auth/')) signedOut();
      return out;
    } catch {
      return { kind: 'unknown' };
    } finally {
      clearTimeout(timer);
    }
  }

  function signedOut() {
    clearToken();
    if (PROTECTED.has(location.pathname)) location.replace('/login');
  }

  function newKey() {
    const b = new Uint8Array(16);
    crypto.getRandomValues(b);
    return Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  }

  function canonical(value) {
    if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
    if (value && typeof value === 'object') {
      return `{${Object.keys(value).sort().map((k) => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
    }
    return JSON.stringify(value);
  }

  // One idempotency identity per form: the same path and body reuse the same
  // key (a retry or an unchanged resubmission is a replay, never a second
  // write); any change to the body starts a new key.
  function retryIdentity() {
    let sig = null;
    let key = null;
    return (path, body) => {
      const s = `${path} ${canonical(body)}`;
      if (s !== sig) { sig = s; key = newKey(); }
      return key;
    };
  }

  // ---- money and time ----------------------------------------------------

  const money = { code: '', units: 2 };

  function formatAmount(minor) {
    const units = money.units;
    let digits = String(Math.abs(Math.trunc(minor)));
    if (units > 0) {
      digits = digits.padStart(units + 1, '0');
      digits = `${digits.slice(0, -units)}.${digits.slice(-units)}`;
    }
    return `${minor < 0 ? '-' : ''}${digits} ${money.code}`;
  }

  function formatPlain(minor) {
    return formatAmount(minor).split(' ')[0];
  }

  // Decimal text as a person types it -> integer minor units, or null when it
  // is not a plain non-negative decimal or has more than minor_units places.
  function parseAmount(text) {
    const t = String(text).trim();
    const m = /^([0-9]*)(?:\.([0-9]*))?$/.exec(t);
    if (!m || (m[1] === '' && !m[2])) return null;
    const frac = m[2] || '';
    if (frac.length > money.units) return null;
    const whole = BigInt(m[1] || '0') * 10n ** BigInt(money.units);
    const part = money.units ? BigInt((frac + '0'.repeat(money.units)).slice(0, money.units)) : 0n;
    const total = whole + part;
    if (total > BigInt(Number.MAX_SAFE_INTEGER)) return null;
    return Number(total);
  }

  function amountPlaceholder() {
    return money.units ? `0.${'0'.repeat(money.units)}` : '0';
  }

  // stage-1 §9: equal shares, larger ones first in the given order.
  function splitShares(amount, n) {
    const base = Math.floor(amount / n);
    const extra = amount - base * n;
    return Array.from({ length: n }, (_, i) => (i < extra ? base + 1 : base));
  }

  const fullFmt = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  const dayFmt = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  const dayYearFmt = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });

  function relativeTime(iso) {
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return iso;
    const diff = Date.now() - t;
    const abs = Math.abs(diff);
    const future = diff < 0;
    const wrap = (s) => (future ? `in ${s}` : `${s} ago`);
    if (abs < 45000) return future ? 'in a moment' : 'just now';
    if (abs < 3600000) return wrap(`${Math.max(1, Math.round(abs / 60000))} min`);
    if (abs < 86400000) return wrap(`${Math.round(abs / 3600000)} h`);
    const d = new Date(t);
    return (d.getFullYear() === new Date().getFullYear() ? dayFmt : dayYearFmt).format(d);
  }

  function timeEl(iso, extraClass) {
    const t = Date.parse(iso);
    const full = Number.isNaN(t) ? iso : fullFmt.format(new Date(t));
    return h('time', { class: `when ${extraClass || ''}`, datetime: iso, title: full, tabindex: '0', 'data-full': full, 'aria-label': full },
      relativeTime(iso));
  }

  function initials(handle) {
    return String(handle || '?').replace(/[^a-z0-9]/gi, '').slice(0, 2).toUpperCase() || '?';
  }

  // ---- messages ----------------------------------------------------------

  function messageFor(r, context) {
    const by = {
      insufficient_funds: context === 'authorize'
        ? 'You don’t have enough available money to hold that much. Money already on hold can’t be used.'
        : 'You don’t have enough available money for this. Nothing was sent.',
      not_found: context === 'request-action' ? 'That request no longer exists.'
        : context === 'hold-action' ? 'That hold no longer exists.'
          : 'We couldn’t find anyone with that handle. Check the spelling and try again.',
      self_payment: 'That’s your own handle. Choose someone else.',
      self_request: 'You can’t ask yourself for money. Choose someone else.',
      request_not_pending: 'This request is no longer pending. It was already paid, declined or cancelled.',
      authorization_not_open: 'This hold is already closed.',
      authorization_expired: 'This hold has expired, so it can’t be collected any more.',
      capture_exceeds_authorization: 'That’s more than the amount still on hold.',
      forbidden: 'You’re not allowed to do that.',
      email_taken: 'An account with that email already exists. Try logging in.',
      handle_taken: 'The handle made from that email is already taken. Try a different email.',
      unauthenticated: 'That email and password don’t match an account.',
      idempotency_key_reuse: 'This was already submitted with different details. Change a field and try again.',
      malformed_request: 'Something in the form couldn’t be read. Check the details and try again.',
    };
    if (by[r.code]) return by[r.code];
    if (r.code === 'validation_failed') return `Please check the details: ${r.message || 'something isn’t valid.'}`;
    return r.message ? `That didn’t go through: ${r.message}` : 'That didn’t go through.';
  }

  // ---- status messages ---------------------------------------------------

  // A region holding at most one message: refused (testid -error), outcome
  // unknown (testid -uncertain) or success. Absent elements mean "none".
  function statusRegion(prefix, uncertainTestid) {
    const region = h('div', { class: 'status-region', 'aria-live': 'polite' });
    const api = {
      el: region,
      clear() { fill(region); },
      error(text) {
        fill(region, h('p', { class: 'msg msg-refused', role: 'alert', testid: `${prefix}-error` },
          icon('alert'), h('span', null, text)));
      },
      uncertain(text) {
        fill(region, h('div', { class: 'msg msg-uncertain', role: 'status', testid: uncertainTestid },
          h('span', { class: 'chip chip-uncertain' }, icon('dots'), h('span', null, 'not confirmed yet')),
          h('span', { class: 'msg-text' }, text)));
      },
      success(text) {
        fill(region, h('p', { class: 'msg msg-success sticker-in', role: 'status' }, icon('check'), h('span', null, text)));
      },
    };
    return api;
  }

  // ---- motion helpers ----------------------------------------------------

  function burst(from) {
    if (reduceMotion) return;
    const r = from.getBoundingClientRect();
    const layer = h('div', { class: 'burst', 'aria-hidden': 'true' });
    layer.style.setProperty('left', `${r.left + r.width / 2}px`);
    layer.style.setProperty('top', `${r.top + r.height / 2}px`);
    const shapes = ['dot', 'star', 'ring', 'pill'];
    for (let i = 0; i < 20; i++) {
      const a = (Math.PI * 2 * i) / 20 + Math.random() * 0.3;
      const d = 50 + Math.random() * 70;
      const p = h('span', { class: `burst-bit burst-${shapes[i % 4]}` });
      p.style.setProperty('--dx', `${Math.cos(a) * d}px`);
      p.style.setProperty('--dy', `${Math.sin(a) * d}px`);
      p.style.setProperty('--rot', `${Math.round(Math.random() * 360)}deg`);
      layer.append(p);
    }
    document.body.append(layer);
    setTimeout(() => layer.remove(), 800);
  }

  function intro() {
    if (reduceMotion) return;
    try {
      if (sessionStorage.getItem(INTRO_KEY)) return;
      sessionStorage.setItem(INTRO_KEY, '1');
    } catch { return; }
    const s = document.createElementNS(SVG_NS, 'svg');
    s.setAttribute('viewBox', '0 0 400 200');
    s.setAttribute('preserveAspectRatio', 'none');
    s.setAttribute('class', 'intro-stroke');
    const p = document.createElementNS(SVG_NS, 'path');
    p.setAttribute('d', 'M-40 120 C 60 40, 140 170, 220 100 S 360 40, 440 90');
    s.append(p);
    const layer = h('div', { class: 'intro', 'aria-hidden': 'true' }, s,
      h('img', { class: 'intro-mark', src: '/static/mark.svg', alt: '' }));
    document.body.append(layer);
    setTimeout(() => layer.remove(), 700);
  }

  function ambient() {
    const root = document.documentElement;
    const sync = () => root.classList.toggle('is-hidden', document.hidden);
    document.addEventListener('visibilitychange', sync);
    sync();
    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver((entries) => {
        for (const e of entries) e.target.classList.toggle('is-offscreen', !e.isIntersecting);
      });
      for (const b of document.querySelectorAll('.blobs')) io.observe(b);
    }
  }

  // ---- shared state: the caller ------------------------------------------

  let me = null;
  let meSeq = 0;
  let resolveMe;
  const meReady = new Promise((r) => { resolveMe = r; });
  const walletViews = [];
  const currencyViews = [];

  // Latest refresh wins: only the newest call may render.
  async function refreshMe() {
    const seq = ++meSeq;
    const r = await api('GET', '/me');
    if (seq !== meSeq) return null;
    if (r.kind !== 'ok') {
      for (const v of walletViews) v.failed(r);
      return null;
    }
    const first = me === null;
    me = r.data;
    money.code = me.currency;
    money.units = me.minor_units;
    if (first) {
      renderWho();
      for (const fn of currencyViews) fn();
      resolveMe(me);
    }
    for (const v of walletViews) v.render(me);
    return me;
  }

  // The caller's profile, loading it if no refresh has succeeded yet.
  async function ensureMe() {
    if (me) return me;
    await refreshMe();
    return me;
  }

  function renderNav(path) {
    const nav = document.getElementById('nav');
    const signedIn = Boolean(getToken());
    const items = signedIn ? NAV : [['/login', 'Log in'], ['/signup', 'Sign up']];
    fill(nav, h('ul', { class: 'nav-list' }, items.map(([href, label]) =>
      h('li', null, h('a', { href, class: 'nav-link', 'aria-current': href === path ? 'page' : undefined }, label)))));
  }

  function renderWho() {
    const who = document.getElementById('who');
    if (!me) { fill(who); return; }
    const logout = h('button', { type: 'button', class: 'btn btn-ghost btn-small', testid: 'logout-button' },
      h('span', { class: 'btn-face' }, h('span', { class: 'btn-label' }, 'Log out')));
    logout.addEventListener('click', () => { clearToken(); location.assign('/login'); });
    fill(who, 
      h('span', { class: 'avatar avatar-me', 'aria-hidden': 'true' }, initials(me.handle)),
      h('span', { class: 'who-text' },
        h('span', { class: 'who-name', testid: 'current-user' }, me.display_name),
        h('span', { class: 'who-handle' }, h('span', { 'aria-hidden': 'true' }, '@'), h('span', { testid: 'current-handle' }, me.handle))),
      logout);
  }

  // ---- wallet panel ------------------------------------------------------

  function walletPanel({ compact = false } = {}) {
    const box = h('div', { class: `wallet ${compact ? 'wallet-compact' : ''}`, 'aria-busy': 'true' },
      h('div', { class: 'skeleton skeleton-amount' }), h('div', { class: 'skeleton skeleton-line' }));
    let last = null;
    walletViews.push({
      render(raw) {
        // A pre-upgrade /me has only balance: no holds, everything available.
        const m = { ...raw, available: typeof raw.available === 'number' ? raw.available : raw.balance, held: typeof raw.held === 'number' ? raw.held : 0 };
        const changed = last !== null && last !== m.available;
        last = m.available;
        box.removeAttribute('aria-busy');
        const avail = h('span', { class: `amount-hero tabular ${changed ? 'tint' : ''}`, testid: 'wallet-available', 'data-amount': String(m.available) }, formatAmount(m.available));
        const rows = [];
        if (m.held !== 0) {
          rows.push(h('div', { class: 'wallet-row' },
            h('span', { class: 'wallet-key' }, icon('lock'), 'On hold'),
            h('span', { class: 'chip-held tabular', testid: 'wallet-held', 'data-amount': String(m.held) }, formatAmount(m.held))));
        }
        rows.push(h('div', { class: 'wallet-row' },
          h('span', { class: 'wallet-key' }, 'Total'),
          h('span', { class: 'wallet-total tabular', testid: 'wallet-balance', 'data-amount': String(m.balance) }, formatAmount(m.balance))));
        fill(box, 
          h('p', { class: 'wallet-label' }, h('span', { class: 'dot dot-available', 'aria-hidden': 'true' }), 'Available to spend'),
          h('p', { class: 'wallet-hero' }, avail),
          h('div', { class: 'wallet-secondary' }, rows));
      },
      failed(r) {
        if (r.kind === 'refused' && r.status === 401) return;
        if (box.getAttribute('aria-busy')) {
          fill(box, h('p', { class: 'msg msg-uncertain' }, icon('dots'),
            h('span', null, 'We couldn’t load your balance. Check your connection and refresh.')));
        }
      },
    });
    return box;
  }

  // ---- money forms (pay, request, authorise) -----------------------------

  function moneyForm(cfg) {
    const { prefix, path, handleField, handleLabel, submitLabel, busyLabel, withVisibility, uncertainTestid, context } = cfg;
    const handle = handleInput(`${prefix}-handle`);
    const amount = textInput(`${prefix}-amount`, { inputmode: 'decimal', placeholder: amountPlaceholder() });
    const note = textInput(`${prefix}-note`, { placeholder: 'what it’s for' });
    const amountLabel = h('span', null, 'Amount');
    const curTag = h('span', { class: 'cur-tag' });
    currencyViews.push(() => { curTag.textContent = money.code; amount.placeholder = amountPlaceholder(); });
    let visibility = null;
    if (withVisibility) {
      visibility = h('select', { testid: `${prefix}-visibility`, class: 'input select' },
        h('option', { value: 'public' }, 'Public – anyone on Pocketful can see it'),
        h('option', { value: 'private' }, 'Private – only the two of you'));
    }
    const status = statusRegion(prefix, uncertainTestid);
    const submit = button(submitLabel, { type: 'submit', testid: `${prefix}-submit` });
    const keyFor = retryIdentity();
    let busy = false;

    const form = h('form', { class: 'form', novalidate: true },
      h('div', { class: 'field' }, h('label', { for: `${prefix}-handle-input`, class: 'field-label' }, handleLabel), handle.wrap),
      h('div', { class: 'field' }, h('label', { for: `${prefix}-amount-input`, class: 'field-label' }, amountLabel, ' ', curTag),
        amount, h('span', { class: 'field-hint' }, 'Use a dot for decimals, for example 15.50')),
      field(`${prefix}-note-input`, h('span', null, 'Note ', h('span', { class: 'optional' }, '(optional)')), note),
      visibility ? field(`${prefix}-visibility-input`, 'Who can see it', visibility) : null,
      status.el,
      h('div', { class: 'form-actions' }, submit));
    handle.input.id = `${prefix}-handle-input`;
    amount.id = `${prefix}-amount-input`;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (busy) return;
      if (!(await ensureMe())) { status.error('We couldn\u2019t load your account, so nothing was sent. Check your connection and try again.'); return; }
      const to = handle.input.value.trim().replace(/^@/, '');
      if (!to) { status.error('Enter the handle of the person, without spaces.'); return; }
      const minor = parseAmount(amount.value);
      if (minor === null) {
        status.error(money.units
          ? `Enter an amount like 15.00, with at most ${money.units} decimal place${money.units > 1 ? 's' : ''}.`
          : 'Enter a whole amount like 1200, without decimals.');
        return;
      }
      if (minor < 1) { status.error('Enter an amount greater than zero.'); return; }
      const body = { [handleField]: to, amount: minor, note: note.value };
      if (visibility) body.visibility = visibility.value;
      const key = keyFor(path, body);
      busy = true;
      setBusy(submit, true, busyLabel);
      const r = await api('POST', path, { body, key });
      busy = false;
      setBusy(submit, false);
      if (r.kind === 'ok') {
        status.success(cfg.successText(r.data));
        if (cfg.celebrate) burst(submit);
        cfg.after('ok', r.data);
      } else if (r.kind === 'refused') {
        status.error(messageFor(r, context));
        cfg.after('refused', r);
      } else {
        status.uncertain(cfg.uncertainText);
      }
    });
    return form;
  }

  // ---- pages -------------------------------------------------------------

  function pageHead(title, sub, artName) {
    return h('div', { class: 'page-head' },
      h('div', { class: 'page-head-text' }, stretchHeading('h1', title, 'page-title'), sub ? h('p', { class: 'lede' }, sub) : null),
      artName ? art(artName, 'sticker art-head') : null);
  }

  function homePage(main) {
    const refresh = button('Refresh', { variant: 'secondary', testid: 'wallet-refresh', chip: false });
    refresh.prepend(icon('refresh'));
    const feedBox = h('div', { class: 'feed', 'aria-busy': 'true' }, skeletonRows(3));
    let feedSeq = 0;
    let feedLimit = 50;
    let seen = null;

    async function refreshFeed() {
      const seq = ++feedSeq;
      const r = await api('GET', `/activity?limit=${feedLimit}`);
      if (seq !== feedSeq) return;
      await ensureMe();
      if (seq !== feedSeq || !me) return;
      if (r.kind !== 'ok') {
        if (r.kind === 'refused' && r.status === 401) return;
        feedBox.removeAttribute('aria-busy');
        if (!feedBox.querySelector('[data-testid="activity-list"]')) {
          fill(feedBox, h('p', { class: 'msg msg-uncertain' }, icon('dots'),
            h('span', null, 'We couldn’t load your activity. Check your connection and press Refresh.')));
        }
        return;
      }
      renderFeed(r.data);
    }

    function renderFeed(data) {
      feedBox.removeAttribute('aria-busy');
      const items = data.payments;
      if (items.length === 0) {
        seen = new Set();
        fill(feedBox, emptyState('empty-activity', 'wallet', 'Nothing here yet',
          'Payments you send or receive, and public payments, will show up here.', 'quiet so far…',
          h('a', { class: 'btn btn-secondary', href: '#pay-handle-input' }, h('span', { class: 'btn-face' }, h('span', { class: 'btn-label' }, 'Send your first payment')))));
        return;
      }
      const prev = seen;
      seen = new Set(items.map((p) => p.payment_id));
      const list = h('ul', { class: 'list feed-list', testid: 'activity-list' },
        items.map((p) => feedItem(p, prev !== null && !prev.has(p.payment_id))));
      const more = data.has_more && feedLimit < 200
        ? button('Show older payments', { variant: 'secondary', chip: false, on: { click: () => { feedLimit = Math.min(200, feedLimit + 50); refreshFeed(); } } })
        : null;
      fill(feedBox, list, more);
    }

    function feedItem(p, isNew) {
      const out = p.from_user_id === me.user_id;
      const inn = p.to_user_id === me.user_id;
      const dir = out ? 'out' : inn ? 'in' : 'other';
      const dirLabel = out ? 'Sent' : inn ? 'Received' : 'Between others';
      const priv = p.visibility === 'private';
      return h('li', { class: `feed-item dir-${dir} ${isNew && !reduceMotion ? 'plop' : ''}`, testid: `activity-item-${p.payment_id}`, 'data-visibility': p.visibility },
        h('span', { class: 'avatar', 'aria-hidden': 'true' }, initials(out ? p.to_handle : p.from_handle)),
        h('div', { class: 'feed-main' },
          h('p', { class: 'feed-parties', testid: `activity-parties-${p.payment_id}` },
            h('span', { class: 'handle' }, `@${p.from_handle}`), h('span', { class: 'verb' }, ' paid '), h('span', { class: 'handle' }, `@${p.to_handle}`)),
          h('p', { class: 'feed-note', testid: `activity-note-${p.payment_id}` }, p.note),
          h('p', { class: 'feed-meta' },
            h('span', { class: `privacy privacy-${p.visibility}` }, icon(priv ? 'lock' : 'globe'), priv ? 'Private' : 'Public'),
            p.request_id ? h('span', { class: 'meta-tag' }, 'Request') : null,
            p.authorization_id ? h('span', { class: 'meta-tag' }, 'Hold collected') : null,
            p.settlement_id ? h('span', { class: 'meta-tag' }, 'Settlement') : null,
            timeEl(p.created_at))),
        h('div', { class: 'feed-side' },
          h('span', { class: `dir-tag dir-tag-${dir}` }, icon(out ? 'out' : inn ? 'in' : 'swap'), dirLabel),
          h('span', { class: `feed-amount tabular amount-${dir}`, testid: `activity-amount-${p.payment_id}` }, formatAmount(p.amount))));
    }

    refresh.addEventListener('click', () => { refreshMe(); refreshFeed(); });

    const pay = moneyForm({
      prefix: 'pay', path: '/payments', handleField: 'to_handle', handleLabel: 'Send to', submitLabel: 'Send money', busyLabel: 'Sending…',
      withVisibility: true, uncertainTestid: 'pay-uncertain', context: 'pay', celebrate: true,
      uncertainText: 'We lost the connection, so we don’t know whether this payment went through. Press Send money again without changing anything: if it already went through, it won’t be sent twice.',
      successText: (p) => `Sent ${formatAmount(p.amount)} to @${p.to_handle}.`,
      after: () => { refreshMe(); refreshFeed(); },
    });
    const req = moneyForm({
      prefix: 'request', path: '/requests', handleField: 'payer_handle', handleLabel: 'Ask', submitLabel: 'Request money', busyLabel: 'Requesting…',
      withVisibility: false, uncertainTestid: 'request-uncertain', context: 'request',
      uncertainText: 'We lost the connection, so we don’t know whether the request was created. Press Request money again without changing anything: it won’t be created twice.',
      successText: (q) => `Asked @${q.payer_handle} for ${formatAmount(q.amount)}. You’ll see it under Requests.`,
      after: () => {},
    });

    fill(main, 
      h('section', { class: 'panel panel-sun hero', 'aria-labelledby': 'wallet-title' },
        blobs('blobs-sun'),
        art('coins', 'sticker art-hero'),
        h('div', { class: 'hero-body' },
          h('h1', { id: 'wallet-title', class: 'display hero-kicker' }, 'Your pocket'),
          walletPanel(),
          h('div', { class: 'hero-actions' }, refresh))),
      h('div', { class: 'grid-2' },
        h('section', { class: 'card form-card', 'aria-labelledby': 'pay-title' },
          h('div', { class: 'card-head' }, h('h2', { id: 'pay-title', class: 'section-title' }, 'Send money'), art('paper-plane', 'sticker art-card')),
          pay),
        h('section', { class: 'card form-card', 'aria-labelledby': 'request-title' },
          h('div', { class: 'card-head' }, h('h2', { id: 'request-title', class: 'section-title' }, 'Request money')),
          h('p', { class: 'card-lede' }, 'They can pay it whenever they’re ready, even if they’re short today.'),
          req)),
      h('section', { class: 'panel panel-butter', 'aria-labelledby': 'feed-title' },
        h('div', { class: 'panel-head' }, h('h2', { id: 'feed-title', class: 'section-title' }, 'Activity')),
        feedBox));
    refreshMe();
    refreshFeed();
  }

  function skeletonRows(n) {
    return h('div', { class: 'skeleton-list', 'aria-hidden': 'true' },
      Array.from({ length: n }, () => h('div', { class: 'skeleton skeleton-row' })));
  }

  function emptyState(testid, artName, title, text, note, action) {
    return h('div', { class: 'empty', testid },
      art(artName, 'sticker art-empty'),
      h('div', { class: 'empty-body' },
        h('p', { class: 'empty-title display' }, title),
        h('p', { class: 'empty-text' }, text),
        note ? scribble(note) : null,
        action || null));
  }

  function requestsPage(main) {
    const status = statusRegion('request', 'request-uncertain');
    const lists = h('div', { class: 'requests-body', 'aria-busy': 'true' }, skeletonRows(3));
    const keys = new Map();
    let seq = 0;

    async function refreshRequests() {
      const my = ++seq;
      const [a, b] = await Promise.all([
        api('GET', '/requests?direction=incoming&limit=200'),
        api('GET', '/requests?direction=outgoing&limit=200'),
      ]);
      if (my !== seq) return;
      await ensureMe();
      if (my !== seq || !me) return;
      if (a.kind !== 'ok' || b.kind !== 'ok') {
        if ([a, b].some((r) => r.kind === 'refused' && r.status === 401)) return;
        if (lists.getAttribute('aria-busy')) {
          lists.removeAttribute('aria-busy');
          fill(lists, h('p', { class: 'msg msg-uncertain' }, icon('dots'), h('span', null, 'We couldn’t load your requests. Check your connection and reload.')));
        }
        return;
      }
      render(a.data, b.data);
    }

    function statusChip(s) {
      const map = { pending: ['pending', 'Pending', 'clock'], paid: ['success', 'Paid', 'check'], declined: ['muted', 'Declined', 'x'], cancelled: ['muted', 'Cancelled', 'x'] };
      const [kind, label, ic] = map[s] || ['muted', s, null];
      return chip(kind, label, ic);
    }

    async function act(btn, kind, q, visSelect) {
      if (btn.disabled) return;
      const id = encodeURIComponent(q.request_id);
      let path = `/requests/${id}/${kind}`;
      let opts = {};
      if (kind === 'pay') {
        const body = { visibility: visSelect.value };
        if (!keys.has(q.request_id)) keys.set(q.request_id, retryIdentity());
        opts = { body, key: keys.get(q.request_id)(path, body) };
      }
      setBusy(btn, true, kind === 'pay' ? 'Paying…' : kind === 'decline' ? 'Declining…' : 'Cancelling…');
      const r = await api('POST', path, opts);
      setBusy(btn, false);
      if (r.kind === 'ok') {
        const verb = kind === 'pay' ? `Paid ${formatAmount(q.amount)} to @${q.requester_handle}.`
          : kind === 'decline' ? `Declined the request from @${q.requester_handle}.` : `Cancelled your request to @${q.payer_handle}.`;
        status.success(verb);
        if (kind === 'pay') burst(btn);
        refreshRequests();
        refreshMe();
      } else if (r.kind === 'refused') {
        status.error(messageFor(r, 'request-action'));
        refreshRequests();
        refreshMe();
      } else {
        status.uncertain(kind === 'pay'
          ? 'We lost the connection, so we don’t know whether this request was paid. Press Pay again: it won’t be paid twice.'
          : 'We lost the connection, so we don’t know whether that went through. Try again or reload the list.');
      }
    }

    function row(q, incoming) {
      const who = incoming ? q.requester_handle : q.payer_handle;
      const pending = q.status === 'pending';
      const actions = [];
      if (pending && incoming) {
        const vis = h('select', { class: 'input select select-small', id: `vis-${q.request_id}` },
          h('option', { value: 'public' }, 'Public'), h('option', { value: 'private' }, 'Private'));
        const pay = button('Pay', { testid: `request-pay-${q.request_id}` });
        pay.addEventListener('click', () => act(pay, 'pay', q, vis));
        const decline = button('Decline', { variant: 'secondary', chip: false, testid: `request-decline-${q.request_id}` });
        decline.addEventListener('click', () => act(decline, 'decline', q));
        actions.push(h('div', { class: 'inline-field' }, h('label', { for: vis.id, class: 'field-label-small' }, 'Show payment as'), vis), pay, decline);
      } else if (pending) {
        const cancel = button('Cancel request', { variant: 'secondary', chip: false, testid: `request-cancel-${q.request_id}` });
        cancel.addEventListener('click', () => act(cancel, 'cancel', q));
        actions.push(cancel);
      }
      return h('li', { class: `row request-row status-${q.status}`, testid: `request-item-${q.request_id}`, 'data-status': q.status },
        h('span', { class: 'avatar', 'aria-hidden': 'true' }, initials(who)),
        h('div', { class: 'row-main' },
          h('p', { class: 'row-title' }, incoming ? h('span', null, h('span', { class: 'handle' }, `@${who}`), ' asks you') : h('span', null, 'You asked ', h('span', { class: 'handle' }, `@${who}`))),
          h('p', { class: 'row-note' }, q.note || 'No note'),
          h('p', { class: 'row-meta' }, statusChip(q.status), timeEl(q.created_at))),
        h('div', { class: 'row-side' },
          h('span', { class: 'row-amount tabular', testid: `request-amount-${q.request_id}` }, formatAmount(q.amount)),
          actions.length ? h('div', { class: 'row-actions' }, actions) : null));
    }

    function group(title, testid, items, incoming, emptyText) {
      return h('section', { class: 'group', 'aria-labelledby': `${testid}-title` },
        h('h2', { class: 'section-title', id: `${testid}-title` }, title, ' ', h('span', { class: 'count' }, `(${items.length})`)),
        h('ul', { class: 'list', testid }, items.map((q) => row(q, incoming))),
        items.length === 0 ? h('p', { class: 'group-empty' }, emptyText) : null);
    }

    function render(inc, out) {
      lists.removeAttribute('aria-busy');
      const both = inc.requests.length === 0 && out.requests.length === 0;
      fill(lists, 
        both ? emptyState('empty-requests', 'wallet', 'No requests yet', 'When you ask someone for money, or someone asks you, it shows up here.', 'all square!',
          h('a', { class: 'btn btn-secondary', href: '/' }, h('span', { class: 'btn-face' }, h('span', { class: 'btn-label' }, 'Request money')))) : null,
        h('div', { class: 'grid-2 groups' },
          group('Incoming', 'incoming-list', inc.requests, true, 'Nobody is asking you for money.'),
          group('Outgoing', 'outgoing-list', out.requests, false, 'You haven’t asked anyone for money.')));
    }

    fill(main, 
      h('section', { class: 'panel panel-pink' }, blobs('blobs-pink'),
        pageHead('Requests', 'Money you’ve asked for, and money people have asked you for.', 'paper-plane'),
        walletPanel({ compact: true })),
      h('section', { class: 'panel panel-plain' }, status.el, lists));
    refreshMe();
    refreshRequests();
  }

  function splitPage(main) {
    const amount = textInput('split-amount', { inputmode: 'decimal', placeholder: amountPlaceholder() });
    const handles = textInput('split-handles', { autocapitalize: 'none', placeholder: 'your handle, their handle, …' });
    const note = textInput('split-note', { placeholder: 'what it was for' });
    const curTag = h('span', { class: 'cur-tag' });
    currencyViews.push(() => { curTag.textContent = money.code; amount.placeholder = amountPlaceholder(); refreshPreview(); });
    const previewBox = h('div', { class: 'preview-box', 'aria-live': 'polite' });
    const status = statusRegion('split', 'split-uncertain');
    const submit = button('Split the bill', { type: 'submit', testid: 'split-submit' });
    const result = h('div', { class: 'split-result' });
    const keyFor = retryIdentity();
    let busy = false;

    function parsedHandles() {
      return handles.value.split(',').map((s) => s.trim().replace(/^@/, '')).filter((s) => s !== '');
    }

    function refreshPreview() {
      const list = parsedHandles();
      const minor = me ? parseAmount(amount.value) : null;
      if (minor === null || minor < 1 || list.length === 0) {
        fill(previewBox, h('p', { class: 'preview-hint' }, 'Enter an amount and the people sharing it to see each share.'));
        return;
      }
      if (new Set(list).size !== list.length) {
        fill(previewBox, h('p', { class: 'preview-hint preview-warn' }, icon('alert'), 'Each person can only appear once.'));
        return;
      }
      const shares = splitShares(minor, list.length);
      fill(previewBox, h('div', { class: 'preview', testid: 'split-preview' },
        h('ul', { class: 'share-list' }, list.map((hd, i) => h('li', { class: `share ${me && hd === me.handle ? 'share-me' : ''}` },
          h('span', { class: 'avatar avatar-small', 'aria-hidden': 'true' }, initials(hd)),
          h('span', { class: 'share-who' }, `@${hd}`, me && hd === me.handle ? h('span', { class: 'you-tag' }, ' (you)') : null),
          h('span', { class: 'share-amount tabular', testid: `split-share-${hd}` }, formatAmount(shares[i]))))),
        h('p', { class: 'share-total' }, h('span', null, 'Total'), h('span', { class: 'tabular' }, formatAmount(shares.reduce((x, y) => x + y, 0))), chip('success', 'matches', 'check'))));
    }

    amount.addEventListener('input', refreshPreview);
    handles.addEventListener('input', refreshPreview);

    const form = h('form', { class: 'form', novalidate: true },
      h('div', { class: 'field' }, h('label', { for: 'split-amount-input', class: 'field-label' }, 'Total you paid ', curTag), amount,
        h('span', { class: 'field-hint' }, 'Use a dot for decimals, for example 30.00')),
      h('div', { class: 'field' }, h('label', { for: 'split-handles-input', class: 'field-label' }, 'Who shared it'), handles,
        h('span', { class: 'field-hint' }, 'Handles separated by commas, in order. Include yourself to take a share; the first people listed take any leftover cent.')),
      field('split-note-input', h('span', null, 'Note ', h('span', { class: 'optional' }, '(optional)')), note),
      status.el,
      h('div', { class: 'form-actions' }, submit));
    amount.id = 'split-amount-input';
    handles.id = 'split-handles-input';

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (busy) return;
      if (!(await ensureMe())) { status.error('We couldn\u2019t load your account, so nothing was sent. Check your connection and try again.'); return; }
      const minor = parseAmount(amount.value);
      if (minor === null) {
        status.error(money.units ? `Enter an amount like 30.00, with at most ${money.units} decimal place${money.units > 1 ? 's' : ''}.` : 'Enter a whole amount like 3000, without decimals.');
        return;
      }
      if (minor < 1) { status.error('Enter an amount greater than zero.'); return; }
      const list = parsedHandles();
      if (list.length === 0) { status.error('Add at least one handle.'); return; }
      if (new Set(list).size !== list.length) { status.error('Each person can only appear once.'); return; }
      const body = { amount: minor, participant_handles: list, note: note.value };
      const key = keyFor('/splits', body);
      busy = true;
      setBusy(submit, true, 'Splitting…');
      const r = await api('POST', '/splits', { body, key });
      busy = false;
      setBusy(submit, false);
      if (r.kind === 'ok') {
        const n = r.data.requests.length;
        status.success(n ? `Split done. We asked ${n} ${n === 1 ? 'person' : 'people'} for their share.` : 'Split done. There was nobody else to ask.');
        burst(submit);
        fill(result, h('div', { class: 'card result-card sticker-in' },
          h('h2', { class: 'section-title' }, 'Requests sent'),
          n ? h('ul', { class: 'share-list' }, r.data.requests.map((q) => h('li', { class: 'share' },
            h('span', { class: 'avatar avatar-small', 'aria-hidden': 'true' }, initials(q.payer_handle)),
            h('span', { class: 'share-who' }, `@${q.payer_handle}`),
            h('span', { class: 'share-amount tabular' }, formatAmount(q.amount)))))
            : h('p', null, 'Only you were in this split, so no requests were needed.'),
          h('a', { class: 'link', href: '/requests' }, 'See them under Requests')));
      } else if (r.kind === 'refused') {
        status.error(messageFor(r, 'split'));
      } else {
        status.uncertain('We lost the connection, so we don’t know whether the split was created. Press Split the bill again without changing anything: it won’t be created twice.');
      }
    });

    fill(main, 
      h('section', { class: 'panel panel-aqua' }, blobs('blobs-aqua'),
        pageHead('Split a bill', 'You paid for everyone. Pocketful works out the shares and asks the others for theirs.', 'split-receipt')),
      h('div', { class: 'grid-2' },
        h('section', { class: 'card form-card', 'aria-labelledby': 'split-form-title' },
          h('h2', { id: 'split-form-title', class: 'section-title' }, 'The bill'), form),
        h('section', { class: 'card preview-card', 'aria-labelledby': 'split-preview-title' },
          h('h2', { id: 'split-preview-title', class: 'section-title' }, 'Each share'), previewBox, result)));
    refreshPreview();
    refreshMe();
  }

  function holdsPage(main) {
    const status = statusRegion('authorization', 'authorization-uncertain');
    const listBox = h('div', { class: 'holds-body', 'aria-busy': 'true' }, skeletonRows(2));
    const keys = new Map();
    let seq = 0;

    async function refreshHolds() {
      const my = ++seq;
      const r = await api('GET', '/authorizations?limit=200');
      if (my !== seq) return;
      await ensureMe();
      if (my !== seq || !me) return;
      if (r.kind !== 'ok') {
        if (r.kind === 'refused' && r.status === 401) return;
        if (listBox.getAttribute('aria-busy')) {
          listBox.removeAttribute('aria-busy');
          fill(listBox, h('p', { class: 'msg msg-uncertain' }, icon('dots'), h('span', null, 'We couldn’t load your holds. Check your connection and reload.')));
        }
        return;
      }
      render(r.data.authorizations);
    }

    function statusChip(s) {
      const map = { open: ['held', 'On hold', 'lock'], captured: ['success', 'Collected', 'check'], voided: ['muted', 'Released', 'x'], expired: ['muted', 'Expired', 'clock'] };
      const [kind, label, ic] = map[s] || ['muted', s, null];
      return chip(kind, label, ic);
    }

    async function capture(btn, a, input, keepOpen) {
      if (btn.disabled) return;
      const minor = parseAmount(input.value);
      if (minor === null) {
        status.error(money.units ? `Enter an amount like 15.00, with at most ${money.units} decimal place${money.units > 1 ? 's' : ''}.` : 'Enter a whole amount without decimals.');
        return;
      }
      if (minor < 1) { status.error('Enter an amount greater than zero.'); return; }
      const body = { amount: minor };
      if (keepOpen.checked) body.final = false;
      const path = `/authorizations/${encodeURIComponent(a.authorization_id)}/capture`;
      if (!keys.has(a.authorization_id)) keys.set(a.authorization_id, retryIdentity());
      setBusy(btn, true, 'Collecting…');
      const r = await api('POST', path, { body, key: keys.get(a.authorization_id)(path, body) });
      setBusy(btn, false);
      if (r.kind === 'ok') {
        status.success(`Collected ${formatAmount(r.data.amount)} from @${a.from_handle}.`);
        burst(btn);
        refreshHolds();
        refreshMe();
      } else if (r.kind === 'refused') {
        status.error(messageFor(r, 'hold-action'));
        refreshHolds();
        refreshMe();
      } else {
        status.uncertain('We lost the connection, so we don’t know whether the money was collected. Press Collect again without changing the amount: it won’t be collected twice.');
      }
    }

    async function voidHold(btn, a) {
      if (btn.disabled) return;
      setBusy(btn, true, 'Releasing…');
      const r = await api('POST', `/authorizations/${encodeURIComponent(a.authorization_id)}/void`);
      setBusy(btn, false);
      if (r.kind === 'ok') {
        status.success(`Released the hold for @${a.to_handle}. The money is available to you again.`);
        refreshHolds();
        refreshMe();
      } else if (r.kind === 'refused') {
        status.error(messageFor(r, 'hold-action'));
        refreshHolds();
        refreshMe();
      } else {
        status.uncertain('We lost the connection, so we don’t know whether the hold was released. Try again or reload the list.');
      }
    }

    function card(a) {
      const outgoing = a.from_user_id === me.user_id;
      const open = a.status === 'open';
      const id = a.authorization_id;
      const remaining = typeof a.remaining_amount === 'number' ? a.remaining_amount : (open ? a.amount - (a.captured_amount || 0) : 0);
      const facts = [
        h('div', { class: 'fact' }, h('dt', null, 'Reserved'), h('dd', null, h('span', { class: 'tabular', testid: `authorization-amount-${id}` }, formatAmount(a.amount)))),
      ];
      if (open) facts.push(h('div', { class: 'fact' }, h('dt', null, 'Still held'), h('dd', null, h('span', { class: 'tabular chip-held' }, formatAmount(remaining)))));
      if (a.status === 'captured') {
        facts.push(h('div', { class: 'fact' }, h('dt', null, 'Collected'), h('dd', null, h('span', { class: 'tabular', testid: `authorization-captured-${id}` }, formatAmount(a.captured_amount)))));
      } else if (a.captured_amount > 0) {
        facts.push(h('div', { class: 'fact' }, h('dt', null, 'Collected so far'), h('dd', null, h('span', { class: 'tabular' }, formatAmount(a.captured_amount)))));
      }
      facts.push(h('div', { class: 'fact fact-wide' }, h('dt', null, open ? 'Expires' : 'Expiry'),
        h('dd', null, h('span', { class: 'mono', testid: `authorization-expires-${id}` }, a.expires_at), ' ', h('span', { class: 'when-rel' }, `(${relativeTime(a.expires_at)})`))));
      const actions = [];
      if (open && !outgoing) {
        const input = textInput(`authorization-capture-amount-${id}`, { inputmode: 'decimal', id: `cap-${id}`, value: formatPlain(remaining) });
        const keep = h('input', { type: 'checkbox', id: `keep-${id}`, class: 'check' });
        const btn = button('Collect', { testid: `authorization-capture-${id}` });
        btn.addEventListener('click', () => capture(btn, a, input, keep));
        actions.push(h('div', { class: 'capture' },
          h('div', { class: 'field' }, h('label', { for: input.id, class: 'field-label' }, 'Amount to collect'), input),
          h('label', { class: 'check-label', for: keep.id }, keep, h('span', null, 'Keep the rest on hold for later')),
          btn));
      }
      if (open && outgoing) {
        const btn = button('Release hold', { variant: 'secondary', chip: false, testid: `authorization-void-${id}` });
        btn.addEventListener('click', () => voidHold(btn, a));
        actions.push(btn);
      }
      return h('li', { class: `hold-card status-${a.status}`, testid: `authorization-item-${id}`, 'data-status': a.status },
        h('div', { class: 'hold-head' },
          h('span', { class: 'avatar', 'aria-hidden': 'true' }, initials(outgoing ? a.to_handle : a.from_handle)),
          h('p', { class: 'row-title' }, outgoing
            ? h('span', null, 'You’re holding money for ', h('span', { class: 'handle' }, `@${a.to_handle}`))
            : h('span', null, h('span', { class: 'handle' }, `@${a.from_handle}`), ' is holding money for you')),
          statusChip(a.status)),
        a.note ? h('p', { class: 'row-note' }, a.note) : null,
        h('dl', { class: 'facts' }, facts),
        h('p', { class: 'row-meta' }, h('span', { class: `privacy privacy-${a.visibility}` }, icon(a.visibility === 'private' ? 'lock' : 'globe'), a.visibility === 'private' ? 'Private' : 'Public'), timeEl(a.created_at)),
        actions.length ? h('div', { class: 'row-actions' }, actions) : null);
    }

    function render(items) {
      listBox.removeAttribute('aria-busy');
      fill(listBox, 
        items.length === 0 ? emptyState('empty-authorizations', 'wallet', 'No holds right now', 'Hold money for someone and they can collect it later, all at once or bit by bit.', 'nothing locked up', null) : null,
        h('ul', { class: 'hold-list', testid: 'authorization-list' }, items.map(card)));
    }

    const authorize = moneyForm({
      prefix: 'authorize', path: '/authorizations', handleField: 'to_handle', handleLabel: 'Hold for', submitLabel: 'Hold money', busyLabel: 'Holding…',
      withVisibility: true, uncertainTestid: 'authorize-uncertain', context: 'authorize',
      uncertainText: 'We lost the connection, so we don’t know whether the hold was placed. Press Hold money again without changing anything: it won’t be placed twice.',
      successText: (a) => `Holding ${formatAmount(a.amount)} for @${a.to_handle}. They can collect it until it expires.`,
      after: () => { refreshHolds(); refreshMe(); },
    });

    fill(main, 
      h('section', { class: 'panel panel-sun' }, blobs('blobs-sun'),
        pageHead('Holds', 'Reserve money for someone now. They collect it later, and anything left over comes back to you.', 'hold-padlock'),
        walletPanel({ compact: true })),
      h('div', { class: 'grid-holds' },
        h('section', { class: 'card form-card', 'aria-labelledby': 'authorize-title' },
          h('h2', { id: 'authorize-title', class: 'section-title' }, 'Hold money'), authorize),
        h('section', { class: 'panel panel-plain holds-panel', 'aria-labelledby': 'holds-title' },
          h('h2', { id: 'holds-title', class: 'section-title' }, 'Your holds'), status.el, listBox)));
    refreshMe();
    refreshHolds();
  }

  function authPage(main, mode) {
    const isSignup = mode === 'signup';
    const p = isSignup ? 'signup' : 'login';
    const email = h('input', { type: 'email', testid: `${p}-email`, class: 'input', id: `${p}-email-input`, autocomplete: 'email', autocapitalize: 'none', spellcheck: 'false', placeholder: 'you@example.com' });
    const password = h('input', { type: 'password', testid: `${p}-password`, class: 'input', id: `${p}-password-input`, autocomplete: isSignup ? 'new-password' : 'current-password' });
    const name = isSignup ? h('input', { type: 'text', testid: 'signup-display-name', class: 'input', id: 'signup-name-input', autocomplete: 'name', placeholder: 'how friends know you' }) : null;
    const errBox = h('div', { class: 'status-region', 'aria-live': 'polite' });
    const submit = button(isSignup ? 'Create account' : 'Log in', { type: 'submit', testid: `${p}-submit` });
    let busy = false;
    const showError = (text) => fill(errBox, h('p', { class: 'msg msg-refused', role: 'alert', testid: 'auth-error' }, icon('alert'), h('span', null, text)));

    const form = h('form', { class: 'form', novalidate: true },
      h('div', { class: 'field' }, h('label', { for: email.id, class: 'field-label' }, 'Email'), email),
      h('div', { class: 'field' }, h('label', { for: password.id, class: 'field-label' }, 'Password'), password,
        isSignup ? h('span', { class: 'field-hint' }, 'At least 8 characters.') : null),
      isSignup ? h('div', { class: 'field' }, h('label', { for: name.id, class: 'field-label' }, 'Your name'), name,
        h('span', { class: 'field-hint' }, 'Your handle is made from the part of your email before the @.')) : null,
      errBox,
      h('div', { class: 'form-actions' }, submit),
      h('p', { class: 'switch' }, isSignup ? 'Already have an account? ' : 'New to Pocketful? ',
        h('a', { class: 'link', href: isSignup ? '/login' : '/signup' }, isSignup ? 'Log in' : 'Create an account')));

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (busy) return;
      const body = { email: email.value.trim(), password: password.value };
      if (isSignup) body.display_name = name.value;
      busy = true;
      setBusy(submit, true, isSignup ? 'Creating…' : 'Logging in…');
      const r = await api('POST', isSignup ? '/auth/signup' : '/auth/login', { body });
      busy = false;
      setBusy(submit, false);
      if (r.kind === 'ok') {
        fill(errBox);
        setToken(r.data.token);
        location.assign('/');
      } else if (r.kind === 'refused') {
        if (r.code === 'validation_failed') {
          showError(isSignup ? 'Check your details: use a valid email, a password of at least 8 characters, and your name.' : 'Enter your email and password.');
        } else {
          showError(messageFor(r, 'auth'));
        }
      } else {
        showError(isSignup
          ? 'We couldn’t reach Pocketful, so we don’t know whether your account was created. Try logging in, or try again.'
          : 'We couldn’t reach Pocketful. Check your connection and try again.');
      }
    });

    const benefits = ['Pay by handle', 'Split to the cent', 'Hold, then collect', 'Private when you want'];
    const steps = [['1', 'Sign up', 'Your handle comes from your email.'], ['2', 'Send or ask', 'Pay friends or request what they owe.'], ['3', 'Split & hold', 'Share bills and reserve money for later.']];
    fill(main, h('div', { class: `auth auth-${p}` },
      h('section', { class: 'card auth-card', 'aria-labelledby': 'auth-title' },
        h('h1', { id: 'auth-title', class: 'section-title auth-title' }, isSignup ? 'Create your account' : 'Welcome back'),
        form),
      h('section', { class: 'panel panel-indigo auth-hero', 'aria-label': 'About Pocketful' },
        blobs('blobs-indigo'),
        stretchHeading('p', isSignup ? 'Money between friends, made easy' : 'Good to see you again', 'auth-display'),
        h('ul', { class: 'stickers' }, benefits.map((b, i) => h('li', { class: `sticker-pill sticker-in tilt-${i}` }, b))),
        art('phone-coin', 'sticker art-auth'),
        scribble('takes a minute!', 'scribble-auth'),
        h('ol', { class: 'steps' }, steps.map(([n, t, d], i) => h('li', { class: `step-card sticker-in tilt-${i + 4}` },
          h('span', { class: 'step-num', 'aria-hidden': 'true' }, n), h('span', { class: 'step-title' }, t), h('span', { class: 'step-text' }, d)))))));
    if (getToken()) refreshMe();
  }

  // ---- boot --------------------------------------------------------------

  function boot() {
    const path = location.pathname.replace(/\/+$/, '') || '/';
    const main = document.getElementById('main');
    if (PROTECTED.has(path) && !getToken()) {
      location.replace('/login');
      return;
    }
    document.body.dataset.page = path === '/' ? 'home' : path.slice(1);
    renderNav(path);
    const titles = { '/': 'Home', '/requests': 'Requests', '/split': 'Split a bill', '/authorizations': 'Holds', '/login': 'Log in', '/signup': 'Sign up' };
    document.title = `${titles[path] || 'Pocketful'} · Pocketful`;
    if (path === '/requests') requestsPage(main);
    else if (path === '/split') splitPage(main);
    else if (path === '/authorizations') holdsPage(main);
    else if (path === '/login') authPage(main, 'login');
    else if (path === '/signup') authPage(main, 'signup');
    else homePage(main);
    intro();
    ambient();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
