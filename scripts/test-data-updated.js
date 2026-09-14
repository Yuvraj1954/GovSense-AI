#!/usr/bin/env node
/*
 * Regression test for the header "Data updated …" timestamp.
 *
 * Runs the REAL public/js/data-updated.js in a sandboxed DOM and asserts that
 * the header NEVER renders NaN / undefined / null / Invalid Date, for valid,
 * missing, invalid, stale-cache and API-error cases.
 *
 * Usage:  node scripts/test-data-updated.js
 * Exit code 0 = all pass.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC_PATH = path.join(__dirname, '..', 'public', 'js', 'data-updated.js');
const src = fs.readFileSync(SRC_PATH, 'utf8');
const APP_VERSION = '2026-09-14.1';

function makeEl(classes) {
  return {
    _h: '',
    classList: { contains: (c) => classes.includes(c) },
    parentElement: null,
    textContent: '',
    set innerHTML(v) { this._h = v; },
    get innerHTML() { return this._h; },
    setAttribute() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
}

function run({ fetchImpl, cacheValue, versionMarker }) {
  const store = new Map();
  if (cacheValue !== undefined) store.set('dataUpdatedCache', cacheValue);
  if (versionMarker !== undefined) store.set('govsenseAppVersion', versionMarker);
  const localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
  const headerParent = makeEl(['inline-flex', 'items-center', 'bg-slate-100']);
  const dot = makeEl(['w-1.5', 'h-1.5', 'rounded-full', 'bg-emerald-500']);
  dot.parentElement = headerParent;
  let domReady = null;
  const document = {
    addEventListener: (ev, fn) => { if (ev === 'DOMContentLoaded') domReady = fn; },
    querySelectorAll: (sel) => (sel === 'header span' ? [dot] : []),
    getElementById: () => null,
  };
  const ctx = {
    window: { APP_VERSION }, document, localStorage, console, Date, JSON, isNaN, Promise,
    fetch: fetchImpl,
  };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  domReady();
  return new Promise((res) => setTimeout(() => res(headerParent._h), 60));
}

const ok = (payload) => () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) });
const err = () => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
const V = APP_VERSION;

const scenarios = [
  ['valid API', ok({ completed_at: '2026-09-13T21:10:55.525341Z' }), undefined, V, 'Data updated'],
  ['API 500, no cache', err, undefined, V, 'Data update unavailable'],
  ['bug repro: index-shape cache, missing field', err, JSON.stringify({ data: { status: 'complete' }, ts: Date.now() }), V, 'Data update unavailable'],
  ['index-shape cache valid', err, JSON.stringify({ data: { completed_at: '2026-09-13T21:10:55Z' }, ts: Date.now() }), V, 'Data updated'],
  ['legacy-shape cache valid', err, JSON.stringify({ completed_at: '2026-09-13T21:10:55Z', timestamp: Date.now() }), V, 'Data updated'],
  ['API ok, field missing', ok({ status: 'complete' }), undefined, V, 'Data update unavailable'],
  ['API ok, invalid date', ok({ completed_at: 'garbage' }), undefined, V, 'Data update unavailable'],
  ['post-deploy reset, API ok', ok({ completed_at: '2026-09-13T21:10:55Z' }), JSON.stringify({ data: { completed_at: '2026-09-13T21:10:55Z' }, ts: Date.now() }), undefined, 'Data updated'],
  ['post-deploy reset, API 500', err, JSON.stringify({ data: { completed_at: '2026-09-13T21:10:55Z' }, ts: Date.now() }), undefined, 'Data update unavailable'],
  ['stale cache (>24h)', err, JSON.stringify({ completed_at: '2020-01-01T00:00:00Z', timestamp: Date.now() - 25 * 3600 * 1000 }), V, 'Data update unavailable'],
];

(async () => {
  let failures = 0;
  for (const [name, f, cache, ver, expectPrefix] of scenarios) {
    const html = await run({ fetchImpl: f, cacheValue: cache, versionMarker: ver });
    const bad = /NaN|undefined|null|Invalid Date/.test(html);
    const m = html.match(/<span>([^<]*)<\/span>/);
    const label = m ? m[1] : html;
    const okPrefix = label.indexOf(expectPrefix) === 0;
    if (bad || !okPrefix) failures++;
    console.log(
      `${bad || !okPrefix ? 'FAIL' : 'PASS'}  ${name.padEnd(46)} => ${JSON.stringify(label)}`
    );
  }
  console.log(`\n${failures === 0 ? 'ALL PASS' : failures + ' FAILURE(S)'}`);
  process.exit(failures === 0 ? 0 : 1);
})();
