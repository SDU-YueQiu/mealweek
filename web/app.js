/* 本周菜单 — 一人一锅的每周备餐卡 */
(() => {
  'use strict';

  const OFFLINE = window.MW_OFFLINE || null;
  const PACK = !!(OFFLINE && OFFLINE.week);
  const PACK_BASE = (OFFLINE && OFFLINE.serverBase) || '';
  const IS_FILE = location.protocol === 'file:';
  const MOBILE = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  const SECURE = (typeof window.isSecureContext === 'boolean')
    ? window.isSecureContext
    : (location.protocol === 'https:' || /^(localhost|127\.0\.0\.1)$/.test(location.hostname));
  const INSTALLED = () => {
    try { return window.matchMedia('(display-mode: standalone)').matches || !!navigator.standalone; } catch (e) { return false; }
  };
  const SW_READY = () => {
    try { return !!navigator.serviceWorker && !!navigator.serviceWorker.controller; } catch (e) { return false; }
  };

  const $ = (s, el = document) => el.querySelector(s);
  const app = $('#app');
  const tabsEl = $('#tabs');
  const sheetEl = $('#sheet');
  const timerEl = $('#timer');
  const toastEl = $('#toast');

  const TAGS_GOOD = ['好吃', '下饭', '够嫩', '清爽', '分量刚好', '省事'];
  const TAGS_BAD = ['太咸', '太淡', '太油', '太干', '太麻烦', '量太大', '量太少'];
  const STATUS = [['eaten', '照做'], ['skipped', '跳过'], ['swapped', '换了']];
  const RATING = [[1, '不想再做'], [2, '还行'], [3, '还想吃']];

  const state = {
    week: null,
    assets: { dish: {}, food: {} },
    placeholder: { dish: [], food: [] },
    tab: 'today',
    day: 0,
    data: { meals: {}, shopping: {}, days: {}, thaw: {}, weight: null },
    queue: [],
    sheet: null,
    online: false,
    flushing: false,
    lastSync: null,
    customUrls: {},
    prefetch: null,
    pack: PACK,
    collapsed: {},
  };

  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  // 凌晨 4 点前还算「前一天」：十二点后做饭、解冻都还是这一晚的事。
  const DAY_CUTOFF = 4;
  const todayIso = () => {
    const d = new Date();
    if (d.getHours() < DAY_CUTOFF) d.setDate(d.getDate() - 1);
    return iso(d);
  };
  const shiftIso = (s, n) => {
    const d = new Date(s + 'T12:00:00');
    d.setDate(d.getDate() + n);
    return iso(d);
  };
  const uid = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);

  function md(isoStr) {
    const [, m, d] = isoStr.split('-');
    return `${Number(m)} 月 ${Number(d)} 日`;
  }

  function store(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* ignore */ }
  }
  function read(key, fallback) {
    try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch (e) { return fallback; }
  }

  // Never let a dead LAN address hold the first paint hostage.
  function fetchT(input, opts, ms) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), ms || 6000);
    return fetch(input, Object.assign({}, opts, { signal: ctrl.signal }))
      .finally(() => clearTimeout(t));
  }

  // The standalone offline file is on file://, so relative /api calls would
  // hit nothing.  It carries the LAN address it was generated from.
  function api(path) {
    if (PACK && PACK_BASE) return PACK_BASE.replace(/\/+$/, '') + path;
    return path;
  }

  /* ---------------- custom dish photos (IndexedDB) ---------------- */

  function idbOpen() {
    return new Promise((res, rej) => {
      const r = indexedDB.open('mw-media', 1);
      r.onupgradeneeded = () => r.result.createObjectStore('img');
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
      r.onblocked = () => rej(new Error('idb blocked'));
    });
  }

  function idbPut(k, v) {
    return idbOpen().then((db) => new Promise((res, rej) => {
      const t = db.transaction('img', 'readwrite');
      t.objectStore('img').put(v, k);
      t.oncomplete = () => res();
      t.onerror = () => rej(t.error);
    }));
  }

  function idbAll() {
    return idbOpen().then((db) => new Promise((res, rej) => {
      const t = db.transaction('img', 'readonly');
      const s = t.objectStore('img');
      const keys = s.getAllKeys();
      const vals = s.getAll();
      t.oncomplete = () => res([keys.result, vals.result]);
      t.onerror = () => rej(t.error);
    }));
  }

  async function shrink(file) {
    const url = URL.createObjectURL(file);
    const im = new Image();
    await new Promise((res, rej) => { im.onload = res; im.onerror = rej; im.src = url; });
    const W = 1280, H = 720;
    const c = document.createElement('canvas');
    c.width = W; c.height = H;
    const ctx = c.getContext('2d');
    const scale = Math.max(W / im.width, H / im.height);
    const dw = im.width * scale, dh = im.height * scale;
    ctx.drawImage(im, (W - dw) / 2, (H - dh) / 2, dw, dh);
    URL.revokeObjectURL(url);
    return await new Promise((res) => c.toBlob(res, 'image/webp', 0.82));
  }

  async function loadCustomPhotos() {
    try {
      const [keys, vals] = await idbAll();
      keys.forEach((k, i) => {
        const key = String(k);
        if (key.indexOf('dish:') === 0) state.customUrls[key.slice(5)] = URL.createObjectURL(vals[i]);
      });
    } catch (e) { /* no indexeddb */ }
  }

  /* ---------------- data ---------------- */

  function applyWeek(payload) {
    state.week = payload.week;
    state.assets = payload.assets || { dish: {}, food: {} };
    state.placeholder = payload.placeholder || { dish: [], food: [] };
    state.data = read('mw:data:' + payload.week.id, {
      meals: {}, shopping: {}, days: {}, thaw: {}, weight: null,
    });
    state.queue = read('mw:queue', []);
    state.lastSync = read('mw:lastSync', null);
    state.prefetch = read('mw:prefetch', null);
    state.collapsed = read('mw:collapsed:' + payload.week.id, {}) || {};
    for (const k of ['meals', 'shopping', 'days', 'thaw', 'pantry']) {
      if (!state.data[k] || typeof state.data[k] !== 'object') state.data[k] = {};
    }
  }

  async function fetchWeek() {
    if (PACK) { state.online = false; return; }
    try {
      const r = await fetchT('/api/week', { cache: 'no-store' }, 6000);
      if (!r.ok) throw new Error('http ' + r.status);
      const d = await r.json();
      applyWeek(d);
      store('mw:week', d);
      state.online = r.headers.get('X-MW-Cache') !== '1';
    } catch (e) {
      state.online = false;
      const cached = read('mw:week', null);
      if (cached && !state.week) applyWeek(cached);
    }
  }

  function pickDay() {
    const days = state.week.days;
    const t = todayIso();
    const idx = days.findIndex((d) => d.date === t);
    if (idx >= 0) { state.day = idx; return; }
    if (t < days[0].date) { state.day = 0; return; }
    if (t > days[days.length - 1].date) { state.day = days.length - 1; return; }
    state.day = 0;
  }

  /* ---------------- events ---------------- */

  function pushEvent(obj) {
    obj.id = uid();
    obj.at = new Date().toISOString();
    if (state.week) obj.week = state.week.id;
    state.queue.push(obj);
    store('mw:queue', state.queue);
    flush();
  }

  async function flush() {
    if (state.flushing || !state.queue.length || !state.week) return;
    const mine = state.queue.filter((e) => !e.week || e.week === state.week.id);
    if (!mine.length) return;
    state.flushing = true;
    const batch = mine.slice(0, 100);
    let more = false;
    try {
      const r = await fetchT(api('/api/events'), {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ week: state.week.id, events: batch }),
      }, 6000);
      if (!r.ok) throw new Error('http ' + r.status);
      let j = null;
      try { j = await r.json(); } catch (e) { /* empty body */ }
      if (j && j.week && j.week !== state.week.id) throw new Error('week mismatch');
      const ids = new Set(batch.map((e) => e.id));
      state.queue = state.queue.filter((e) => !ids.has(e.id));
      store('mw:queue', state.queue);
      state.online = true;
      state.lastSync = new Date().toISOString();
      store('mw:lastSync', state.lastSync);
      // Taps that arrived while this request was in flight (eg. 全买了) still
      // sit in the queue; send them now instead of waiting for the next tick.
      more = state.queue.some((e) => !e.week || e.week === state.week.id);
    } catch (e) {
      state.online = false;
    } finally {
      state.flushing = false;
      paintSync();
      if (more) flush();
    }
  }

  let prefetching = false;
  async function prefetchAll(onProgress) {
    if (PACK) return { total: 0, fetched: 0, cached: 0, pack: true };
    if (!('caches' in window) || !state.week || prefetching) {
      return { total: 0, fetched: 0, cached: 0 };
    }
    prefetching = true;
    const urls = [];
    for (const kind of ['dish', 'food']) {
      const m = state.assets[kind] || {};
      for (const id in m) urls.push(url(kind, id));
    }
    let fetched = 0;
    let cached = 0;
    try {
      const cache = await caches.open('mw-assets-v1');
      for (let i = 0; i < urls.length; i++) {
        const u = urls[i];
        if (await cache.match(u)) { cached++; continue; }
        try {
          const r = await fetchT(u, { cache: 'force-cache' }, 10000);
          if (r && r.ok) { await cache.put(u, r); cached++; fetched++; }
        } catch (e) { /* offline */ }
        if (onProgress && i % 10 === 0) onProgress(i + 1, urls.length);
      }
    } catch (e) { /* no cache storage */ }
    prefetching = false;
    const info = { week: state.week.id, total: urls.length, cached, at: new Date().toISOString() };
    state.prefetch = info;
    store('mw:prefetch', info);
    return { total: urls.length, fetched, cached };
  }

  async function syncNow() {
    showToast(PACK ? '正在找电脑…' : '同步中…');
    if (!PACK) {
      await fetchWeek();
      if (!state.online) {
        showToast('连不上电脑，继续用本地缓存');
        paintSync();
        return;
      }
    }
    let res = { total: 0, fetched: 0, cached: 0 };
    if (!PACK && state.week) {
      res = await prefetchAll((n, t) => { if (n % 20 === 0) showToast(`图片 ${n}/${t}`); });
    }
    await flush();
    if (PACK || state.online) await loadEvents();
    if (state.online && state.week) {
      state.lastSync = new Date().toISOString();
      store('mw:lastSync', state.lastSync);
      if (PACK) {
        showToast(pendingCount() ? '反馈还存着，回 WiFi 再传' : '反馈已同步');
      } else {
        showToast(res.fetched ? `已同步 · 新下载 ${res.fetched} 张图` : '已同步 · 都是最新的');
      }
      if (!state.sheet && !state.pantryOpen) render();
      showNotice();
    } else {
      showToast(PACK ? '连不上电脑，反馈先存在手机里' : '连不上电脑，继续用本地缓存');
    }
    paintSync();
  }

  function pendingCount() {
    if (!state.week) return state.queue.length;
    return state.queue.filter((e) => !e.week || e.week === state.week.id).length;
  }

  function paintSync() {
    const dot = $('.dot');
    if (dot) dot.classList.toggle('off', !state.online);
    const lab = $('.sync span');
    if (!lab) return;
    if (!state.online) {
      const n = pendingCount();
      lab.textContent = n ? `待传 ${n}` : '离线';
      return;
    }
    if (state.lastSync) {
      const d = new Date(state.lastSync);
      lab.textContent = `已同步 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    } else {
      lab.textContent = '同步';
    }
  }

  function saveData() { store('mw:data:' + state.week.id, state.data); }

  /* ---------------- event hydration (server is the source of truth) ---------------- */

  function emptyData() {
    return { meals: {}, shopping: {}, days: {}, thaw: {}, weight: null, pantry: {} };
  }

  function applyEvent(data, e) {
    if (!e || !e.type) return;
    if (e.type === 'meal' && e.date && e.slot) {
      const rec = data.meals[e.date + '|' + e.slot] || (data.meals[e.date + '|' + e.slot] = {});
      if (e.value === null || e.value === undefined || e.value === '') delete rec[e.field];
      else rec[e.field] = e.value;
    } else if (e.type === 'day' && e.date) {
      const rec = data.days[e.date] || (data.days[e.date] = {});
      if (e.value === null || e.value === undefined) delete rec[e.field];
      else rec[e.field] = e.value;
    } else if (e.type === 'thaw' && (e.eventAt || e.at)) {
      data.thaw[e.eventAt || e.at] = !!e.done;
    } else if (e.type === 'shopping' && e.batch) {
      data.shopping[e.batch + '|' + e.food] = !!e.checked;
    } else if (e.type === 'pantry' && e.foodId) {
      if (e.value === null || e.value === undefined) delete data.pantry[e.foodId];
      else data.pantry[e.foodId] = Number(e.value);
    } else if (e.type === 'week' && e.field === 'weight') {
      data.weight = e.value;
    }
  }

  async function loadEvents() {
    if (!state.week) return;
    const path = '/api/events' + (PACK ? '?week=' + encodeURIComponent(state.week.id) : '');
    try {
      const r = await fetchT(api(path), { cache: 'no-store' }, 6000);
      const fromCache = r.headers.get('X-MW-Cache') === '1';
      if (!r.ok) {
        if (fromCache) state.online = false;
        return;
      }
      if (fromCache) {
        state.online = false;
        let hasLocal = false;
        try { hasLocal = !!localStorage.getItem('mw:data:' + state.week.id); } catch (e) { /* ignore */ }
        // A cached /api/events can be older than feedback already saved on
        // this phone; never let it erase what the user just did.
        if (hasLocal) return;
      } else {
        state.online = true;
      }
      const d = await r.json();
      if (d.week && d.week !== state.week.id) return;
      const data = emptyData();
      const evs = (d.events || []).slice().sort((a, b) => String(a.at).localeCompare(String(b.at)));
      for (const e of evs) applyEvent(data, e);
      for (const e of state.queue
        .filter((x) => !x.week || x.week === state.week.id)
        .sort((a, b) => String(a.at).localeCompare(String(b.at)))) applyEvent(data, e);
      state.data = data;
      saveData();
      store('mw:events:' + state.week.id, evs);
    } catch (e) {
      state.online = false;
      /* offline: keep the local cache */
    }
  }

  // First open of a downloaded pack: rebuild local state from the snapshot
  // baked into the file, so feedback from before the download is visible.
  function seedPackEvents(events) {
    if (!PACK || !state.week || !events || !events.length) return false;
    const key = 'mw:data:' + state.week.id;
    let hasLocal = false;
    try { hasLocal = !!localStorage.getItem(key); } catch (e) { /* ignore */ }
    if (hasLocal) return false;
    const data = emptyData();
    const evs = events.slice().sort((a, b) => String(a.at).localeCompare(String(b.at)));
    for (const e of evs) applyEvent(data, e);
    for (const e of state.queue
      .filter((x) => !x.week || x.week === state.week.id)
      .sort((a, b) => String(a.at).localeCompare(String(b.at)))) applyEvent(data, e);
    if (!evs.length && !state.queue.length) return false;
    state.data = data;
    saveData();
    return true;
  }

  /* ---------------- assets ---------------- */

  function url(kind, id) {
    const h = state.assets && state.assets[kind] ? state.assets[kind][id] : null;
    const p = `/assets/${kind}/${encodeURIComponent(id)}.webp${h ? '?v=' + h : ''}`;
    return (PACK && OFFLINE.images && OFFLINE.images[p]) || p;
  }

  const ART = {
    '炒': ['chao', '炒'], '汤面': ['tangmian', '面'], '汤': ['tang', '汤'],
    '炖': ['dun', '炖'], '烧': ['shao', '烧'], '煎': ['jian', '饼'],
  };

  function dishArt(method) {
    const [cls, ch] = ART[method] || ['default', '菜'];
    return `<div class="dish-art art-${cls}"><span>${ch}</span></div>`;
  }

  function img(kind, id, cls, label, method, noZoom) {
    if (kind === 'dish' && state.customUrls[id]) {
      return `<img class="${cls || ''}"${noZoom ? '' : ' data-zoom'} src="${state.customUrls[id]}" alt="" onerror="this.style.visibility='hidden'">`;
    }
    const has = !!(state.assets && state.assets[kind] && state.assets[kind][id]);
    if (!has || (state.placeholder && state.placeholder[kind] || []).includes(id)) {
      if (kind === 'dish') return dishArt(method);
      return `<span class="ph-ic ${cls || ''}">${esc(String(label || id || '?').slice(0, 1))}</span>`;
    }
    return `<img class="${cls || ''}"${noZoom ? '' : ' data-zoom'} src="${url(kind, id)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`;
  }

  /* ---------------- lightbox ---------------- */

  const lb = document.getElementById('lightbox');
  const lbImg = lb.querySelector('img');

  function openLightbox(src, fromHistory) {
    if (!src) return;
    if (!fromHistory) history.pushState({ mw: 'lightbox', src }, '', '#img');
    lbImg.src = src;
    lb.hidden = false;
    lbClosing = false;
    document.documentElement.classList.add('lb-open');
  }

  let lbClosing = false;

  function hideLightbox() {
    lb.hidden = true;
    lbImg.removeAttribute('src');
    document.documentElement.classList.remove('lb-open');
    lbClosing = false;
  }

  function closeLightbox() {
    if (lbClosing) return;
    if (history.state && history.state.mw === 'lightbox') {
      lbClosing = true;
      history.back();
    } else {
      hideLightbox();
    }
  }

  document.addEventListener('click', (e) => {
    if (e.target.closest('[data-act="close"]')) return;
    let im = e.target.closest('img[data-zoom]');
    if (!im) {
      const hero = e.target.closest('.hero');
      if (hero) im = hero.querySelector('img[data-zoom]');
    }
    if (!im) return;
    e.preventDefault();
    e.stopPropagation();
    openLightbox(im.currentSrc || im.src);
  }, true);

  lb.addEventListener('click', closeLightbox);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeLightbox(); });

  /* ---------------- shell ---------------- */

  function pageHead(title, sub) {
    return `<header class="top">
      <div class="top-row">
        <div class="brand">${esc(state.week.title)} · <b>${esc(title)}</b></div>
        <button class="sync" data-act="sync"><i class="dot"></i><span>同步</span></button>
      </div>
      ${sub ? `<div class="daytitle" style="text-align:left;margin-top:4px"><div class="d1">${sub}</div></div>` : ''}
    </header>`;
  }

  function renderTabs() {
    const items = [
      ['today', '今天', '<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>'],
      ['shop', '买菜', '<path d="M6 8h12l-1 11H7L6 8z"/><path d="M9 8a3 3 0 0 1 6 0"/>'],
      ['fridge', '冰箱', '<rect x="6" y="3" width="12" height="18" rx="2"/><path d="M6 10h12"/>'],
      ['week', '本周', '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>'],
    ];
    tabsEl.innerHTML = items.map(([k, label, path]) => `
      <button class="tab ${state.tab === k ? 'on' : ''}" data-act="tab" data-tab="${k}">
        <svg viewBox="0 0 24 24">${path}</svg><span>${label}</span>
      </button>`).join('');
    tabsEl.hidden = false;
  }

  /* ---------------- today ---------------- */

  function rangeClass(v, range) {
    return v >= range[0] && v <= range[1] ? 'ok' : 'warn';
  }

  function dayPage(d, di) {
    const t = state.week.targets;
    const tr = (d.target && d.target.range) || t.range;
    const tot = d.totals;
    const cells = [
      ['热量', Math.round(tot.kcal), 'kcal', tr.kcal],
      ['碳水', tot.carb, 'g', tr.carb],
      ['蛋白', tot.protein, 'g', tr.protein],
      ['脂肪', tot.fat, 'g', tr.fat],
    ];

    const totals = `<div class="totals">${cells.map(([k, v, u, r]) => `
      <div class="tot ${rangeClass(v, r)}"><div class="k">${k}</div>
        <div class="v">${v}<small>${u === 'kcal' ? '' : '&nbsp;' + u}</small></div></div>`).join('')}</div>`;

    const meals = d.meals.map((m, i) => {
      const rec = state.data.meals[d.date + '|' + m.slot] || {};
      let badge = '';
      if (rec.status === 'eaten') badge = '<div class="meal-done">已做</div>';
      else if (rec.status === 'skipped') badge = '<div class="meal-done skip">跳过</div>';
      else if (rec.status === 'swapped') badge = '<div class="meal-done swap">换了</div>';
      const bm = t.byMeal[m.slot] || {};
      return `<article class="meal" data-act="meal" data-di="${di}" data-mi="${i}">
        <div class="meal-img">${img('dish', m.dishId, '', m.name, m.method, true)}<div class="meal-slot">${esc(m.slot)}</div>${badge}</div>
        <div class="meal-body">
          <h3>${esc(m.name)}</h3>
          <div class="meal-meta">
            <span class="chip">热量 <b>${Math.round(m.macros.kcal)}</b></span>
            <span class="chip">碳水 <b>${m.macros.carb}</b> / ${bm.carb || '-'}</span>
            <span class="chip">蛋白 <b>${m.macros.protein}</b> / ${bm.protein || '-'}</span>
            <span class="chip">脂肪 <b>${m.macros.fat}</b></span>
            ${rec.note ? '<span class="chip note-chip">✎ 备注</span>' : ''}
          </div>
        </div>
      </article>`;
    }).join('');

    const tn = d.date === todayIso() ? tonightBlock() : '';
    return `<section class="page" data-i="${di}" data-date="${d.date}">
      ${totals}<div class="meals">${meals}</div>${tn}${moodBlock(d)}
    </section>`;
  }

  function renderToday() {
    const days = state.week.days;
    app.innerHTML = `${headerToday(days[state.day])}<div class="pager" id="pager">
      ${days.map((d, i) => dayPage(d, i)).join('')}
    </div>`;
    const p = $('#pager');
    if (p) p.scrollLeft = state.day * p.clientWidth;
    initPager();
    paintSync();
  }

  function scrollToDay(n) {
    const p = $('#pager');
    if (!p) return;
    n = Math.max(0, Math.min(state.week.days.length - 1, n));
    p.scrollTo({ left: n * p.clientWidth, behavior: 'smooth' });
  }

  function initPager() {
    const p = $('#pager');
    if (!p || p.dataset.bound) return;
    p.dataset.bound = '1';
    let t = null;
    p.addEventListener('scroll', () => {
      clearTimeout(t);
      t = setTimeout(() => {
        const w = p.clientWidth || 1;
        const i = Math.round(p.scrollLeft / w);
        if (i !== state.day && i >= 0 && i < state.week.days.length) {
          state.day = i;
          const top = $('#top');
          if (top) top.outerHTML = headerToday(state.week.days[i]);
          paintSync();
        }
      }, 70);
    }, { passive: true });
  }

  function headerToday(d) {
    return `<header class="top" id="top">
      <div class="top-row">
        <div class="brand">${esc(state.week.title)} · <b>${esc(d.label)}</b></div>
        <button class="sync" data-act="sync"><i class="dot"></i><span>同步</span></button>
      </div>
      <div class="daynav">
        <button data-act="day" data-dir="-1" ${state.day === 0 ? 'disabled' : ''}>‹</button>
        <div class="daytitle">
          <div class="d1">${md(d.date)}</div>
          <div class="d2">${esc(d.label)} · 第 ${state.day + 1} 天 / 7${d.date === todayIso() ? ' · <b style="color:var(--accent)">今天</b>' : ''}</div>
        </div>
        <button data-act="day" data-dir="1" ${state.day === state.week.days.length - 1 ? 'disabled' : ''}>›</button>
      </div>
    </header>`;
  }

  function tonightBlock() {
    const today = todayIso();
    const prev = shiftIso(today, -1);
    const evs = (state.week.events || []).filter((e) => (e.at || '').slice(0, 10) === today);
    // 昨晚没做完的事今天还留着，别因为过了零点就消失。
    const carried = (state.week.events || [])
      .filter((e) => (e.at || '').slice(0, 10) === prev && !state.data.thaw[e.at]);
    if (!evs.length && !carried.length) return '';
    const row = (e, late) => {
      const done = !!state.data.thaw[e.at];
      const label = { thaw: '解冻', split: '分装', open: '开封', finish: '吃完' }[e.type] || e.type;
      return `<div class="tonight-row ${done ? 'done' : ''}" data-act="thaw" data-at="${esc(e.at)}">
        <span class="ck ${done ? 'on' : ''}">✓</span>
        <div class="tx">${late ? '<i class="late">昨天</i>' : ''}${label} ${esc(e.food)} ${e.qty ? `<b>${e.qty}${esc(e.unit || '')}</b>` : ''}
          <small>${esc(e.note || '')}</small></div>
      </div>`;
    };
    return `<section class="tonight"><h4>今晚要做的</h4>${evs.map((e) => row(e, false)).join('')}${carried.map((e) => row(e, true)).join('')}</section>`;
  }

  function moodBlock(d) {
    const rec = state.data.days[d.date] || {};
    const scale = (field, q, lo, hi) => {
      const cur = rec[field];
      return `<div class="mood">
        <div class="mood-q">${q}</div>
        <div class="scale"><span>${lo}</span>
          <div class="dots">${[1, 2, 3, 4, 5].map((n) =>
            `<button data-act="mood" data-field="${field}" data-v="${n}" class="${cur === n ? 'on' : ''}">${n}</button>`).join('')}</div>
          <span>${hi}</span></div>
      </div>`;
    };
    return `<div class="block" style="margin-top:20px">
      <h3>今天怎么样</h3>
      ${scale('hunger', '今天饿不饿', '不饿', '很饿')}
      ${scale('energy', '今天有精神吗', '没精神', '精神')}
    </div>`;
  }

  /* ---------------- shopping ---------------- */

  function renderShopping() {
    const w = state.week;
    const batches = w.shopping.map((b) => {
      const total = b.items.length;
      const done = b.items.filter((it) => state.data.shopping[b.batch + '|' + it.food]).length;
      const collapsed = batchCollapsed(b.batch, done, total);
      const rows = b.items.map((it) => {
        const key = b.batch + '|' + it.food;
        const ok = !!state.data.shopping[key];
        const qty = it.qty ? `${it.qty}${it.unit === 'g' || it.unit === 'ml' ? ' ' + it.unit : ' ' + it.unit}` : '';
        const exp = it.expireAt ? `${Number(it.expireAt.slice(5, 7))}/${Number(it.expireAt.slice(8, 10))} 前` : (it.shelfLife || '');
        return `<div class="shop ${ok ? 'done' : ''}" data-act="shop" data-key="${esc(key)}">
          <div class="box">✓</div>
          ${img('food', it.foodId, '', it.food)}
          <div class="txt">
            <div class="nm">${esc(it.food)}<em>${esc(qty)}</em></div>
            <div class="sub">${esc(it.note || '')}${it.use ? ' · ' + esc(it.use) : ''}</div>
          </div>
          <div class="exp">${esc(exp)}</div>
        </div>`;
      }).join('');
      const when = b.when ? md(b.when.slice(0, 10)) : '';
      return `<section class="batch ${collapsed ? 'collapsed' : ''}">
        <button class="batch-head" data-act="batch" data-batch="${esc(b.batch)}" aria-expanded="${!collapsed}">
          <h3>${esc(b.batch)}</h3><small>${esc(when)} · ${esc(b.covers || '')}</small>
          <span class="prog" data-prog="${esc(b.batch)}">已买 ${done}/${total}</span>
          <span class="chev" aria-hidden="true">›</span>
        </button>
        ${rows}
      </section>`;
    }).join('');

    app.innerHTML = `${pageHead('买菜')}${batches}`;
    paintSync();
  }

  // A finished batch folds away, the one you are still shopping stays open.
  function batchCollapsed(batch, done, total) {
    const saved = state.collapsed ? state.collapsed[batch] : undefined;
    if (saved === undefined) return total > 0 && done === total;
    return !!saved;
  }

  /* ---------------- cyber fridge ---------------- */

  function pantryList() { return state.week.pantry || []; }

  // A pantry row is the sum of its sources: what you already had before the
  // week, plus each shopping batch.  A batch only counts after its items are
  // ticked on the 买菜 page, so Friday's plan never appears in the fridge on
  // Wednesday.
  function pantryParts(p) {
    if (Array.isArray(p.parts) && p.parts.length) return p.parts;
    return [{ src: 'before', food: p.food, qty: p.base || 0, unit: p.unit,
              at: p.stockedAt || null, expireAt: p.expireAt || null }];
  }

  function partBought(part) {
    if (!part || part.src === 'before') return true;
    return !!state.data.shopping[part.src + '|' + (part.food || '')];
  }

  function sumParts(p, want) {
    let sum = 0;
    for (const q of pantryParts(p)) {
      if (partBought(q) === want && (!q.unit || q.unit === p.unit)) sum += Number(q.qty) || 0;
    }
    return sum;
  }

  function pantryStock(p) { return sumParts(p, true); }
  function pantryWaiting(p) { return sumParts(p, false); }

  function pantryExpireAt(p) {
    const dates = pantryParts(p).filter((q) => partBought(q) && q.expireAt).map((q) => String(q.expireAt));
    if (!dates.length) return p.expireAt || null;
    return dates.sort()[0];
  }

  function pantryUsed() {
    const used = {};
    for (const d of state.week.days) {
      for (const m of d.meals) {
        const rec = state.data.meals[d.date + '|' + m.slot] || {};
        if (rec.status !== 'eaten') continue;
        for (const it of m.items || []) {
          const p = pantryList().find((x) => x.foodId === it.foodId);
          if (!p || !p.tracked) continue;
          let amt = 0;
          if (p.unit === 'g' && (it.unit === 'g' || it.unit === 'ml')) amt = it.qty || 0;
          else if (p.unit === '个' && it.unit === '个') amt = it.qty || 0;
          if (amt) used[p.foodId] = (used[p.foodId] || 0) + amt;
        }
      }
    }
    return used;
  }

  function pantryAuto(p, used) {
    return Math.max(0, pantryStock(p) - (used[p.foodId] || 0));
  }

  function pantryShown(p, used) {
    const m = state.data.pantry ? state.data.pantry[p.foodId] : null;
    return (m === undefined || m === null || m === '') ? pantryAuto(p, used) : Number(m);
  }

  function fmtAmt(v, unit) {
    v = Number(v) || 0;
    if (unit === 'g') {
      if (v >= 1000) return (v / 1000).toFixed(1).replace(/\.0$/, '') + ' kg';
      return Math.round(v) + ' g';
    }
    return Math.round(v) + ' ' + (unit || '');
  }

  function daysUntil(isoDate) {
    if (!isoDate) return null;
    const parts = String(isoDate).slice(0, 10).split('-').map(Number);
    if (parts.length !== 3 || parts.some((n) => !isFinite(n))) return null;
    const target = new Date(parts[0], parts[1] - 1, parts[2]);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return Math.round((target - today) / 86400000);
  }

  function shortDate(isoDate) {
    if (!isoDate) return '';
    const p = String(isoDate).slice(0, 10).split('-').map(Number);
    if (p.length !== 3 || p.some((n) => !isFinite(n))) return esc(isoDate);
    const year = new Date().getFullYear();
    return (p[0] !== year ? p[0] + '/' : '') + p[1] + '/' + p[2];
  }

  function expiryInfo(p) {
    const days = daysUntil(p && p.expireAt);
    if (days == null) return { days: null, cls: 'none', text: '保质期未标', date: '' };
    let cls = 'ok';
    let text = `还剩 ${days} 天`;
    if (days < 0) { cls = 'expired'; text = `已过期 ${-days} 天`; }
    else if (days === 0) { cls = 'expired'; text = '今天吃完'; }
    else if (days <= 7) { cls = 'soon'; }
    return { days, cls, text, date: shortDate(p.expireAt) };
  }

  function expiryLine(p) {
    const e = expiryInfo(p);
    const state = p.state ? esc(p.state) : '—';
    if (e.days == null) return `<div class="st-exp none">${state} · 保质期未标</div>`;
    const tail = e.days <= 30 ? ` · ${e.text}` : '';
    return `<div class="st-exp ${e.cls}">${state} · 最晚 ${e.date}${tail}</div>`;
  }

  function expirySummary(used = {}) {
    const rows = pantryList()
      .filter((p) => p.tracked && pantryExpireAt(p) && pantryShown(p, used) > 0)
      .map((p) => ({ p, e: expiryInfo({ expireAt: pantryExpireAt(p) }) }))
      .sort((a, b) => a.e.days - b.e.days);
    const urgent = rows.filter((x) => x.e.days != null && x.e.days <= 3);
    if (!urgent.length) return '';
    return `<div class="expiry-alert"><b>优先吃</b>${urgent.slice(0, 3).map(({ p, e }) =>
      `<span class="ea ${e.cls}">${esc(p.food)} <em>${esc(e.text)}</em></span>`).join('')}
      ${urgent.length > 3 ? `<span class="ea more">+${urgent.length - 3}</span>` : ''}</div>`;
  }

  // The day each item ran out, by replaying the eaten meals in date order.
  function pantryFinished() {
    const stock = {};
    for (const p of pantryList()) if (p.tracked) stock[p.foodId] = pantryStock(p);
    const acc = {};
    const out = {};
    const days = state.week.days.slice().sort((a, b) => a.date.localeCompare(b.date));
    for (const d of days) {
      for (const m of d.meals) {
        const rec = state.data.meals[d.date + '|' + m.slot] || {};
        if (rec.status !== 'eaten') continue;
        for (const it of m.items || []) {
          const fid = it.foodId;
          if (!stock[fid]) continue;
          const p = pantryList().find((x) => x.foodId === fid);
          if (p && p.unit === '个' && it.unit !== '个') continue;
          if (p && p.unit === 'g' && it.unit !== 'g' && it.unit !== 'ml') continue;
          acc[fid] = (acc[fid] || 0) + (it.qty || 0);
          if (!out[fid] && acc[fid] >= stock[fid] - 0.01) out[fid] = d.date;
        }
      }
    }
    return out;
  }

  function renderFridge() {
    const used = pantryUsed();
    const items = pantryList();
    const cats = ['肉', '蛋', '豆', '蔬菜', '菌菇', '主食', '干货', '坚果', '调味'];
    let html = pageHead('冰箱', '只算买到的，照做自动扣') + expirySummary(used);
    let shown = 0;
    for (const cat of cats) {
      const list = items.filter((p) => p.cat === cat)
        .filter((p) => !p.tracked || pantryShown(p, used) > 0)
        .sort((a, b) => String(pantryExpireAt(a) || '9999').localeCompare(String(pantryExpireAt(b) || '9999')));
      if (!list.length) continue;
      const soon = list.filter((p) => {
        const e = expiryInfo({ expireAt: pantryExpireAt(p) });
        return e.days != null && e.days <= 7 && (!p.tracked || pantryShown(p, used) > 0);
      }).length;
      html += `<div class="sec"><h2>${cat}</h2><span>${list.length} 种${soon ? ` · ${soon} 种 7 天内到期` : ''}</span></div><div class="stock">`;
      for (const p of list) {
        if (!p.tracked) {
          html += `<div class="stock-row flat">${img('food', p.foodId, '', p.food)}
            <div class="st-main"><div class="st-top"><b>${esc(p.food)}</b><span class="st-num">常备</span></div>
            <div class="st-sub">不计入扣减</div>${expiryLine({ expireAt: pantryExpireAt(p), state: p.state })}</div></div>`;
          continue;
        }
        shown++;
        const left = pantryShown(p, used);
        const stock = pantryStock(p);
        const manual = state.data.pantry && state.data.pantry[p.foodId] != null;
        const pct = stock > 0 ? Math.max(0, Math.min(100, left / stock * 100)) : 0;
        html += `<button class="stock-row" data-act="pantry" data-id="${p.foodId}">
          ${img('food', p.foodId, '', p.food)}
          <div class="st-main">
            <div class="st-top"><b>${esc(p.food)}</b><span class="st-num">${fmtAmt(left, p.unit)}</span></div>
            <div class="bar"><i style="width:${pct}%"></i></div>
            <div class="st-sub">买到 ${fmtAmt(stock, p.unit)} · 已用 ${fmtAmt(used[p.foodId] || 0, p.unit)}${manual ? ' · 手动' : ''}</div>
            ${expiryLine({ expireAt: pantryExpireAt(p), state: p.state })}
          </div>
        </button>`;
      }
      html += `</div>`;
    }
    if (!shown) {
      html += `<div class="empty">冰箱是空的。<br>买的菜在「买菜」打勾后才会进来。</div>`;
    }
    const finished = pantryFinished();
    const gone = items.filter((p) => p.tracked && pantryShown(p, used) <= 0)
      .sort((a, b) => String(finished[b.foodId] || '').localeCompare(String(finished[a.foodId] || '')));
    if (gone.length) {
      html += `<details class="gone"><summary>已吃完 ${gone.length} 种</summary>
        <div class="gone-list">${gone.map((p) => `
          <div class="gone-row"><span>${esc(p.food)}</span>
            <small>${finished[p.foodId] ? shortDate(finished[p.foodId]) + ' 用完' : '手动清零'}</small></div>`).join('')}
        </div></details>`;
    }
    app.innerHTML = html;
    paintSync();
  }

  function openPantry(fid, fromHistory) {
    const p = pantryList().find((x) => x.foodId === fid);
    if (!p) return;
    if (!fromHistory) history.pushState({ mw: 'pantry', id: fid }, '', '#p/' + fid);
    state.pantryOpen = fid;
    renderPantrySheet(p);
    sheetEl.hidden = false;
    document.body.style.overflow = 'hidden';
    sheetEl.scrollTop = 0;
  }

  function renderPantrySheet(p) {
    const used = pantryUsed();
    const auto = pantryAuto(p, used);
    const manual = state.data.pantry ? state.data.pantry[p.foodId] : null;
    const e = expiryInfo({ expireAt: pantryExpireAt(p) });
    const parts = pantryParts(p);
    const partRows = parts.map((q) => {
      const bought = partBought(q);
      const label = q.src === 'before' ? '家里原有' : `${esc(q.src)}${bought ? ' · 已买' : ' · 还没买'}`;
      return `<div class="calc-row part${bought ? '' : ' wait'}"><span>${label}</span><b>${fmtAmt(q.qty, q.unit)}</b></div>`;
    }).join('');
    const wait = pantryWaiting(p);
    sheetEl.innerHTML = `<div class="hero" style="aspect-ratio:16/7">${img('food', p.foodId, '', p.food)}
      <button class="close" data-act="close">×</button>
      <div class="ht"><div class="s">赛博冰箱</div><h2>${esc(p.food)}</h2></div></div>
      <div class="sheet-body">
        <div class="calc">
          ${partRows || `<div class="calc-row"><span>初始</span><b>${fmtAmt(p.base, p.unit)}</b></div>`}
          <div class="calc-row"><span>照做已用</span><b>−${fmtAmt(used[p.foodId] || 0, p.unit)}</b></div>
          <div class="calc-row total"><span>自动计算</span><b>${fmtAmt(auto, p.unit)}</b></div>
          <div class="calc-row"><span>存放</span><b>${esc(p.state || '—')}</b></div>
          <div class="calc-row"><span>入库</span><b>${p.stockedAt ? shortDate(p.stockedAt) : '—'}</b></div>
          <div class="calc-row"><span>保质期</span><b>${esc(p.shelfLife || '—')}</b></div>
          <div class="calc-row"><span>最晚吃完</span><b class="exp-${e.cls}">${e.days == null ? '未标' : `${e.date} · ${esc(e.text)}`}</b></div>
        </div>
        <div class="note-hint" style="margin:-8px 0 18px">${wait > 0
          ? `「还没买」的 ${fmtAmt(wait, p.unit)} 不算库存，买了才加进来。`
          : '按采购/入库日与保质期估算；开封后以包装为准。'}</div>
        <div class="block"><h3>手动校正</h3>
          <div class="edit-row">
            <input id="pantry-input" type="number" inputmode="decimal" min="0" step="1"
              value="${manual == null ? '' : manual}" placeholder="${Math.round(auto)}">
            <span class="unit">${esc(p.unit)}</span>
            <button class="fb small" data-act="pantry-save" data-id="${p.foodId}">保存</button>
          </div>
          <div class="note-hint">留空就一直接受自动值。手动值优先显示，自动计算不会丢。</div>
        </div>
        <button class="fb" style="width:100%;padding:13px" data-act="pantry-reset" data-id="${p.foodId}">恢复自动计算</button>
      </div>`;
  }

  /* ---------------- offline status ---------------- */

  function offlineInfo() {
    const info = state.prefetch || read('mw:prefetch', null);
    const cached = read('mw:week', null);
    const week = cached && cached.week ? cached.week : null;
    const total = info && typeof info.total === 'number' ? info.total : 0;
    const got = info && typeof info.cached === 'number' ? info.cached : 0;
    const sameWeek = !!(info && week && info.week === week.id);
    return { info, week, total, cached: got, sameWeek, ready: PACK || (sameWeek && got >= total) };
  }

  function offlineCard() {
    const oi = offlineInfo();
    const swReady = SW_READY();
    const installed = INSTALLED();
    const meta = PACK
      ? `<div class="oc-meta">生成于 ${esc(String(OFFLINE.generatedAt || '').replace('T', ' ').slice(0, 16))}
          · 同步地址 ${esc(PACK_BASE || '未设置')}</div>`
      : `<div class="oc-grid">
          <span class="oc-pill ${SECURE ? 'on' : 'off'}">HTTPS ${SECURE ? '✓' : '✗'}</span>
          <span class="oc-pill ${swReady ? 'on' : 'off'}">离线缓存 ${swReady ? '✓' : '✗'}</span>
          <span class="oc-pill ${installed ? 'on' : 'off'}">桌面 App ${installed ? '✓' : '✗'}</span>
          <span class="oc-pill ${oi.ready ? 'on' : 'off'}">图片 ${oi.cached}/${oi.total}</span>
        </div>`;
    return `<div class="offline-card">
      <div class="oc-head"><b>离线</b><span class="oc-badge ${oi.ready ? 'on' : ''}">${oi.ready ? '已就绪' : '待下载'}</span></div>
      <p>${PACK
        ? '这是下载到手机的离线包：菜单、步骤、图片都在文件里，关掉电脑、离开 WiFi 都能看。新的一周到了，在电脑上重新下载一次离线包。'
        : '离开 WiFi 后，浏览器里的 192.168.x.x 地址打不开；要打开手机桌面上的图标，或下载下面的单文件离线包。'}</p>
      ${meta}
      <div class="oc-actions">
        <button class="fb" data-act="sync">${PACK ? '同步反馈' : '立即同步'}</button>
        ${PACK ? '' : '<a class="fb ghost" href="/offline.html" download>下载离线包</a>'}
        ${PACK ? '' : '<a class="fb ghost" href="/setup">安装到手机</a>'}
      </div>
    </div>`;
  }

  function showNotice() {
    const el = document.getElementById('notice');
    if (!el || PACK || IS_FILE) return;
    if (read('mw:noticeDismissed', false)) { el.hidden = true; return; }
    const oi = offlineInfo();
    const swReady = SW_READY();
    const installed = INSTALLED();
    const reasons = [];
    if (!SECURE) {
      reasons.push(location.protocol === 'https:'
        ? '这个 HTTPS 证书手机还没信任，浏览器不会保存离线缓存。'
        : '现在是用 HTTP 打开的：浏览器不会把离线缓存留在手机里。');
    } else if (!swReady) reasons.push('离线缓存还没接管，刷新一次或重新打开桌面图标。');
    else if (!installed && MOBILE) reasons.push('还没装到手机桌面，离开 WiFi 就会打不开。');
    else if (!oi.ready) reasons.push('这一周的图片还没全部存到手机。');
    if (!reasons.length) { el.hidden = true; return; }
    const links = [];
    if (!SECURE) links.push('<a href="/setup">用 HTTPS 安装</a>');
    else if (!installed) links.push('<a href="/setup">看安装步骤</a>');
    if (!oi.ready) links.push('<a href="/offline.html" download>下载离线包</a>');
    el.innerHTML = `<div class="notice-tx">${reasons.map(esc).join('<br>')}
      <div class="notice-links">${links.join('')}</div></div>
      <button class="notice-x" data-act="dismiss-notice" aria-label="关闭">×</button>`;
    el.hidden = false;
  }

  /* ---------------- week ---------------- */

  function renderWeek() {
    const w = state.week;
    const today = todayIso();
    const rangeOf = (d) => (d.target && d.target.range) || w.targets.range;
    const rows = w.days.map((d, i) => {
      const cur = i === state.day;
      const r = rangeOf(d).kcal;
      const ok = d.totals.kcal >= r[0] && d.totals.kcal <= r[1];
      return `<div class="wrow ${cur ? 'cur' : ''}" data-act="jump" data-di="${i}">
        <div class="dd"><b>${Number(d.date.slice(8, 10))}</b><small>${esc(d.label)}</small></div>
        <div class="mm">${d.meals.map((m) => `<div>${esc(m.name)}</div>`).join('')}</div>
        <div class="kc"><b style="color:${ok ? 'var(--green)' : 'var(--amber)'}">${Math.round(d.totals.kcal)}</b><small>kcal</small></div>
      </div>`;
    }).join('');

    const wt = state.data.weight == null ? '' : state.data.weight;
    const passing = w.days.filter((d) => {
      const r = rangeOf(d).kcal;
      return d.totals.kcal >= r[0] && d.totals.kcal <= r[1];
    }).length;
    app.innerHTML = `${pageHead('本周', w.start.slice(5).replace('-', '/') + ' – ' + w.end.slice(5).replace('-', '/'))}
      <div class="sec"><h2>每日合计</h2><span>${passing}/${w.days.length} 天达标</span></div>
      ${rows}
      <div class="weight"><label for="wt">周日体重</label>
        <input id="wt" type="number" step="0.1" inputmode="decimal" value="${wt}" placeholder="98.9">
        <span class="unit">kg</span>
        <button class="fb small" data-act="weight">记下</button>
      </div>
      ${offlineCard()}`;
    paintSync();
  }

  /* ---------------- meal sheet ---------------- */

  function openMeal(di, mi, fromHistory) {
    if (!fromHistory) history.pushState({ mw: 'meal', di, mi }, '', `#m/${di}/${mi}`);
    state.sheet = { di, mi, big: false, step: 0 };
    renderSheet();
    sheetEl.hidden = false;
    document.body.style.overflow = 'hidden';
    sheetEl.scrollTop = 0;
  }

  function hideSheet() {
    state.sheet = null;
    state.pantryOpen = null;
    sheetEl.hidden = true;
    sheetEl.innerHTML = '';
    document.body.style.overflow = '';
    releaseWake();
    stopTimer();
  }

  function closeSheet() {
    if (history.state && (history.state.mw === 'meal' || history.state.mw === 'pantry')) {
      history.back();
    } else {
      hideSheet();
      history.replaceState(null, '', '#' + state.tab);
    }
  }

  function durations(text) {
    const out = [];
    const re = /(\d+(?:\.\d+)?)\s*(分钟|分|秒)/g;
    let m;
    while ((m = re.exec(text))) {
      const n = parseFloat(m[1]);
      out.push({ sec: Math.round(m[2] === '秒' ? n : n * 60), label: m[0] });
    }
    return out.slice(0, 2);
  }

  function stepText(text) {
    let html = esc(text);
    const ds = durations(text);
    if (ds.length) {
      html += ' ' + ds.map((d, i) => `<button class="tbtn" data-act="timer" data-sec="${d.sec}">⏱ ${d.sec >= 60 ? Math.round(d.sec / 60) + ' 分' : d.sec + ' 秒'}</button>`).join(' ');
    }
    return html;
  }

  function renderSheet() {
    const { di, mi } = state.sheet;
    const d = state.week.days[di];
    const m = d.meals[mi];
    const rec = state.data.meals[d.date + '|' + m.slot] || {};

    const head = `<div class="hero">${img('dish', m.dishId, '', m.name, m.method)}
      <button class="close" data-act="close">×</button>
      <div class="ht"><div class="s">${esc(m.slot)} · ${esc(d.label)}</div><h2>${esc(m.name)}</h2></div>
    </div>`;

    const macro = `<div class="macros">
      ${[['热量', Math.round(m.macros.kcal), 'kcal'], ['碳水', m.macros.carb, 'g'], ['蛋白', m.macros.protein, 'g'], ['脂肪', m.macros.fat, 'g']]
        .map(([k, v, u]) => `<div class="m"><b>${v}</b><small>${k}${u === 'g' ? ' g' : ''}</small></div>`).join('')}
    </div>`;

    const ings = `<div class="block"><h3>食材</h3>${m.items.filter((it) => !it.note || !/清水/.test(it.food))
      .map((it) => `<div class="ing">${img('food', it.foodId, '', it.food)}<div class="n">${esc(it.food)}${it.note ? `<small>${esc(it.note)}</small>` : ''}</div>
        <div class="q">${it.qty == null ? '' : it.qty + ' ' + esc(it.unit || '')}</div></div>`).join('')}</div>`;

    if (state.sheet.big) {
      const steps = m.steps;
      const i = state.sheet.step;
      const ds = durations(steps[i]);
      sheetEl.innerHTML = `${head}
        <div class="sheet-body">
          <div class="bigstep">
            <div class="cnt">第 ${i + 1} 步 / 共 ${steps.length} 步</div>
            <div class="txt">${esc(steps[i])}
              ${ds.map((x) => `<br><button class="tbtn" data-act="timer" data-sec="${x.sec}">⏱ ${x.sec >= 60 ? Math.round(x.sec / 60) + ' 分' : x.sec + ' 秒'}</button>`).join('')}
            </div>
            <div class="bignav">
              <button data-act="step" data-dir="-1" ${i === 0 ? 'disabled' : ''}>上一步</button>
              ${i === steps.length - 1
                ? '<button class="pri" data-act="big">完成</button>'
                : '<button class="pri" data-act="step" data-dir="1">下一步</button>'}
            </div>
            <div style="margin-top:14px"><button class="fb small" data-act="big">退出大字</button></div>
          </div>
        </div>`;
      return;
    }

    const steps = `<div class="block"><h3>做法</h3><ol class="steps">
      ${m.steps.map((s) => `<li>${stepText(s)}</li>`).join('')}</ol></div>`;

    const tip = m.tip ? `<div class="tip">${esc(m.tip)}</div>` : '';

    const fb = `<div class="block"><h3>这顿怎么样</h3>
      <div class="fb-row">${STATUS.map(([v, l]) => `<button class="fb ${rec.status === v ? 'on' : ''}" data-act="status" data-v="${v}">${l}</button>`).join('')}</div>
      <div class="fb-row">${RATING.map(([v, l]) => `<button class="fb ${rec.rating === v ? 'on' : ''}" data-act="rating" data-v="${v}">${l}</button>`).join('')}</div>
      <div class="taggroup"><div class="taglabel">做得好的</div>
        <div class="fb-row">${TAGS_GOOD.map((t) => `<button class="fb small tag good ${(rec.tags || []).includes(t) ? 'on' : ''}" data-act="tag" data-v="${t}">${t}</button>`).join('')}</div>
      </div>
      <div class="taggroup"><div class="taglabel">可以改的</div>
        <div class="fb-row">${TAGS_BAD.map((t) => `<button class="fb small tag ${(rec.tags || []).includes(t) ? 'on' : ''}" data-act="tag" data-v="${t}">${t}</button>`).join('')}</div>
      </div>
      <textarea class="note" data-act="note" rows="3"
        placeholder="写两句：太咸还是太淡、火候、下次想怎么改……">${esc(rec.note || '')}</textarea>
      <div class="note-hint">自动保存 · 下次排菜和诊断会读</div>
    </div>`;

    const photoBtn = `<label class="photo-btn">换成我自己拍的照片
      <input type="file" accept="image/*" capture="environment" data-act="photo" data-id="${m.dishId}" hidden></label>`;

    sheetEl.innerHTML = `${head}<div class="sheet-body">${macro}${ings}${steps}${tip}
      <button class="fb" style="width:100%;padding:13px" data-act="big">大字模式 · 一步一步做</button>${photoBtn}${fb}</div>`;
  }

  /* ---------------- timers ---------------- */

  let timerInt = null;
  let wake = null;

  function startTimer(sec) {
    stopTimer();
    const end = Date.now() + sec * 1000;
    timerEl.hidden = false;
    const paint = () => {
      const left = Math.max(0, Math.round((end - Date.now()) / 1000));
      const mm = String(Math.floor(left / 60)).padStart(2, '0');
      const ss = String(left % 60).padStart(2, '0');
      timerEl.innerHTML = `<b>${mm}:${ss}</b><button data-act="stoptimer">停止</button>`;
      if (left <= 0) { beep(); stopTimer(); showToast('时间到'); }
    };
    paint();
    timerInt = setInterval(paint, 500);
  }

  function stopTimer() {
    if (timerInt) clearInterval(timerInt);
    timerInt = null;
    timerEl.hidden = true;
    timerEl.innerHTML = '';
  }

  function beep() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.connect(g); g.connect(ctx.destination);
      o.frequency.value = 880; g.gain.value = .12;
      o.start(); setTimeout(() => { o.stop(); ctx.close(); }, 420);
    } catch (e) { /* ignore */ }
  }

  async function requestWake() {
    try {
      if ('wakeLock' in navigator) wake = await navigator.wakeLock.request('screen');
    } catch (e) { /* ignore */ }
  }
  function releaseWake() {
    if (wake) { try { wake.release(); } catch (e) { /* ignore */ } wake = null; }
  }

  /* ---------------- toast ---------------- */

  let toastT = null;
  function showToast(msg) {
    toastEl.textContent = msg;
    toastEl.hidden = false;
    clearTimeout(toastT);
    toastT = setTimeout(() => { toastEl.hidden = true; }, 1600);
  }

  /* ---------------- actions ---------------- */

  let noteTimer = null;
  const noteSent = {};
  function saveNote(t, immediate) {
    if (!state.sheet || !state.week) return;
    const { di, mi } = state.sheet;
    const d = state.week.days[di];
    const m = d.meals[mi];
    const key = d.date + '|' + m.slot;
    const rec = state.data.meals[key] || (state.data.meals[key] = {});
    rec.note = t.value;
    saveData();
    clearTimeout(noteTimer);
    const fire = () => {
      if (noteSent[key] === rec.note) return;
      noteSent[key] = rec.note;
      pushEvent({ type: 'meal', date: d.date, slot: m.slot, field: 'note', value: rec.note || '' });
    };
    if (immediate) fire();
    else noteTimer = setTimeout(fire, 1600);
  }

  document.addEventListener('input', (e) => {
    const t = e.target.closest('[data-act="note"]');
    if (t) saveNote(t, false);
  });

  document.addEventListener('focusout', (e) => {
    const t = e.target.closest('[data-act="note"]');
    if (!t) return;
    clearTimeout(noteTimer);
    saveNote(t, true);
  });

  document.addEventListener('change', async (e) => {
    const inp = e.target.closest('[data-act="photo"]');
    if (!inp || !inp.files || !inp.files[0] || !state.sheet) return;
    const id = inp.dataset.id;
    try {
      const blob = await shrink(inp.files[0]);
      if (!blob) throw new Error('no blob');
      await idbPut('dish:' + id, blob);
      if (state.customUrls[id]) URL.revokeObjectURL(state.customUrls[id]);
      state.customUrls[id] = URL.createObjectURL(blob);
      renderSheet();
      showToast('已换上你的照片');
    } catch (err) {
      showToast('这张图用不了，换一张试试');
    }
  });

  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-act]');
    if (!el) return;
    const act = el.dataset.act;

    if (act === 'sync') { syncNow(); return; }

    if (act === 'dismiss-notice') {
      store('mw:noticeDismissed', true);
      const n = document.getElementById('notice');
      if (n) n.hidden = true;
      return;
    }

    if (act === 'tab') {
      state.tab = el.dataset.tab;
      history.replaceState(null, '', '#' + state.tab);
      render();
      window.scrollTo(0, 0);
      return;
    }
    if (act === 'day') {
      scrollToDay(state.day + Number(el.dataset.dir));
      return;
    }
    if (act === 'meal') { openMeal(Number(el.dataset.di), Number(el.dataset.mi)); return; }
    if (act === 'close') { closeSheet(); return; }
    if (act === 'jump') { state.day = Number(el.dataset.di); state.tab = 'today'; render(); window.scrollTo(0, 0); return; }

    if (act === 'big') {
      if (state.sheet) {
        state.sheet.big = !state.sheet.big;
        state.sheet.step = 0;
        renderSheet();
        if (state.sheet.big) { requestWake(); sheetEl.scrollTop = 0; } else releaseWake();
      }
      return;
    }
    if (act === 'step') {
      const d = Number(el.dataset.dir);
      const m = state.week.days[state.sheet.di].meals[state.sheet.mi];
      state.sheet.step = Math.max(0, Math.min(m.steps.length - 1, state.sheet.step + d));
      renderSheet();
      sheetEl.scrollTop = 0;
      return;
    }
    if (act === 'timer') { startTimer(Number(el.dataset.sec)); return; }
    if (act === 'stoptimer') { stopTimer(); return; }

    if (act === 'status' || act === 'rating' || act === 'tag') {
      const { di, mi } = state.sheet;
      const d = state.week.days[di];
      const m = d.meals[mi];
      const key = d.date + '|' + m.slot;
      const rec = state.data.meals[key] || (state.data.meals[key] = {});
      const v = act === 'rating' ? Number(el.dataset.v) : el.dataset.v;

      if (act === 'tag') {
        const set = new Set(rec.tags || []);
        set.has(v) ? set.delete(v) : set.add(v);
        rec.tags = [...set];
      } else {
        if (rec[act === 'status' ? 'status' : 'rating'] === v) delete rec[act === 'status' ? 'status' : 'rating'];
        else rec[act === 'status' ? 'status' : 'rating'] = v;
      }
      saveData();
      pushEvent({ type: 'meal', date: d.date, slot: m.slot, field: act === 'status' ? 'status' : act === 'rating' ? 'rating' : 'tags', value: act === 'tag' ? rec.tags : rec[act === 'status' ? 'status' : 'rating'] ?? null });
      el.classList.toggle('on');
      if (act !== 'tag') {
        el.parentNode.querySelectorAll('.fb').forEach((b) => { if (b !== el) b.classList.remove('on'); });
      }
      if (act === 'status') render();
      return;
    }

    if (act === 'pantry') { openPantry(el.dataset.id); return; }

    if (act === 'pantry-save') {
      const id = el.dataset.id;
      const inp = $('#pantry-input');
      const raw = inp && inp.value.trim();
      state.data.pantry = state.data.pantry || {};
      if (raw === '') delete state.data.pantry[id];
      else state.data.pantry[id] = Math.max(0, Number(raw));
      saveData();
      pushEvent({ type: 'pantry', foodId: id, value: raw === '' ? null : Number(raw) });
      closeSheet();
      render();
      return;
    }

    if (act === 'pantry-reset') {
      const id = el.dataset.id;
      if (state.data.pantry) delete state.data.pantry[id];
      saveData();
      pushEvent({ type: 'pantry', foodId: id, value: null });
      closeSheet();
      render();
      return;
    }

    if (act === 'batch') {
      const batch = el.dataset.batch;
      const sec = el.closest('.batch');
      const next = !(sec && sec.classList.contains('collapsed'));
      state.collapsed[batch] = next;
      store('mw:collapsed:' + state.week.id, state.collapsed);
      if (sec) sec.classList.toggle('collapsed', next);
      el.setAttribute('aria-expanded', String(!next));
      return;
    }

    if (act === 'shop') {
      const key = el.dataset.key;
      const on = !state.data.shopping[key];
      state.data.shopping[key] = on;
      saveData();
      el.classList.toggle('done', on);
      const batch = key.split('|')[0];
      const b = state.week.shopping.find((x) => x.batch === batch);
      const done = b.items.filter((it) => state.data.shopping[b.batch + '|' + it.food]).length;
      const prog = document.querySelector(`[data-prog="${batch}"]`);
      if (prog) prog.textContent = `已买 ${done}/${b.items.length}`;
      pushEvent({ type: 'shopping', batch, food: key.split('|')[1], checked: on });
      return;
    }

    if (act === 'thaw') {
      const at = el.dataset.at;
      const on = !state.data.thaw[at];
      state.data.thaw[at] = on;
      saveData();
      el.classList.toggle('done', on);
      const ck = el.querySelector('.ck');
      if (ck) ck.classList.toggle('on', on);
      pushEvent({ type: 'thaw', eventAt: at, done: on });
      return;
    }

    if (act === 'mood') {
      const page = el.closest('.page');
      const di = page ? Number(page.dataset.i) : state.day;
      const d = state.week.days[di];
      const field = el.dataset.field;
      const v = Number(el.dataset.v);
      const rec = state.data.days[d.date] || (state.data.days[d.date] = {});
      rec[field] = rec[field] === v ? null : v;
      saveData();
      el.parentNode.querySelectorAll('button').forEach((b) => b.classList.remove('on'));
      if (rec[field] === v) el.classList.add('on');
      pushEvent({ type: 'day', date: d.date, field, value: rec[field] });
      return;
    }

    if (act === 'weight') {
      const input = $('#wt');
      const v = input && input.value ? Number(input.value) : null;
      state.data.weight = v;
      saveData();
      pushEvent({ type: 'week', field: 'weight', value: v });
      showToast(v ? '记下了' : '已清空');
      return;
    }
  });

  /* ---------------- render ---------------- */

  function render() {
    if (!state.week) return;
    if (state.tab === 'today') renderToday();
    else if (state.tab === 'shop') renderShopping();
    else if (state.tab === 'fridge') renderFridge();
    else renderWeek();
    renderTabs();
  }

  function showEmpty() {
    app.innerHTML = `<div class="empty">
      ${PACK ? '这个离线包里没有菜单数据。' : '还没有周计划，也没有本地缓存。'}<br>
      ${PACK ? '请重新下载一次离线包。' : '连上电脑打开一次，或者下载单文件离线包。'}<br>
      ${PACK ? '' : '<a class="fb" style="display:inline-block;margin-top:16px;padding:10px 18px;text-decoration:none" href="/offline.html" download>下载离线包</a>'}
    </div>`;
  }

  async function boot() {
    try {
      // 1. Instant paint from the last good copy, or from the pack itself.
      if (PACK) {
        applyWeek(OFFLINE);
        seedPackEvents(OFFLINE.events);
        const snapshot = {
          week: OFFLINE.week,
          assets: OFFLINE.assets,
          placeholder: OFFLINE.placeholder,
          serverBase: OFFLINE.serverBase,
          generatedAt: OFFLINE.generatedAt,
        };
        store('mw:week', snapshot);
        state.online = false;
      } else {
        const cached = read('mw:week', null);
        if (cached && cached.week) applyWeek(cached);
      }
      if (state.week) {
        pickDay();
        render();
        applyHash();
      }

      // 2. Refresh from the PC.  fetchT keeps a dead LAN address to 6s.
      if (!PACK) {
        const before = state.week ? state.week.id : null;
        await fetchWeek();
        if (!state.week) { showEmpty(); showNotice(); return; }
        if (!before || state.week.id !== before) {
          pickDay();
          if (!state.sheet && !state.pantryOpen) {
            render();
            applyHash();
          }
        } else {
          paintSync();
        }
      } else if (!state.week) {
        showEmpty();
        showNotice();
        return;
      }

      // 3. Feedback can arrive a moment later; never block the menu on it.
      const hydrated = loadEvents().then(() => {
        if (!state.sheet && !state.pantryOpen) render();
        paintSync();
      });
      await Promise.race([hydrated, new Promise((r) => setTimeout(r, 2500))]);

      loadCustomPhotos().then(() => {
        if (!state.sheet && !state.pantryOpen) render();
      });
      window.addEventListener('popstate', onPop);
      if (pendingCount()) flush();
      setInterval(() => flush(), 20000);      window.addEventListener('online', () => flush());
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden) { flush(); paintSync(); }
      });
      if (!PACK && navigator.storage && navigator.storage.persist) {
        navigator.storage.persist().catch(() => {});
      }
      showNotice();

      if (!PACK) {
        setTimeout(() => {
          if (!state.online) return;
          prefetchAll().then(() => {
            if (state.online) {
              state.lastSync = new Date().toISOString();
              store('mw:lastSync', state.lastSync);
            }
            paintSync();
            if (state.tab === 'week' && !state.sheet && !state.pantryOpen) render();
            showNotice();
          });
        }, 800);
      }
    } catch (e) {
      const msg = e && e.message ? e.message : String(e);
      app.innerHTML = `<div class="empty">启动失败：${esc(msg)}<br>下拉刷新试试。</div>`;
    }
  }

  function applyHash() {
    const h = (location.hash || '').replace(/^#\/?/, '');
    if (!h) return;
    if (h === 'img') {
      history.replaceState(null, '', '#' + state.tab);
      return;
    }
    const m = h.match(/^m\/(\d+)\/(\d+)$/);
    if (m) {
      state.tab = 'today';
      state.day = Math.max(0, Math.min(state.week.days.length - 1, Number(m[1])));
      render();
      history.replaceState(null, '', '#today');
      openMeal(state.day, Number(m[2]));
      return;
    }
    const pm = h.match(/^p\/([^/]+)$/);
    if (pm) {
      state.tab = 'fridge';
      render();
      history.replaceState(null, '', '#fridge');
      openPantry(pm[1]);
      return;
    }
    if (['today', 'shop', 'fridge', 'week'].indexOf(h) >= 0) {
      state.tab = h;
      if (state.sheet) hideSheet();
      render();
    }
  }

  function onPop(e) {
    const st = e.state;
    if (st && st.mw === 'lightbox') {
      openLightbox(st.src, true);
      return;
    }
    if (!lb.hidden) hideLightbox();
    if (st && st.mw === 'meal') {
      if (state.sheet && state.sheet.di === st.di && state.sheet.mi === st.mi) return;
      state.tab = 'today';
      state.day = st.di;
      render();
      openMeal(st.di, st.mi, true);
      return;
    }
    if (st && st.mw === 'pantry') {
      if (state.pantryOpen === st.id) return;
      state.tab = 'fridge';
      render();
      openPantry(st.id, true);
      return;
    }
    if (state.sheet || state.pantryOpen) hideSheet();
    const h = (location.hash || '').replace(/^#\/?/, '');
    if (['today', 'shop', 'fridge', 'week'].indexOf(h) >= 0 && h !== state.tab) {
      state.tab = h;
      render();
    }
  }

  /* ---------------- pager resize ---------------- */

  window.addEventListener('resize', () => {
    const p = $('#pager');
    if (p) p.scrollLeft = state.day * p.clientWidth;
  });

  boot();
})();
