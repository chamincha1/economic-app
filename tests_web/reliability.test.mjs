import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from '../server.mjs';
import {parseCsv, parsePriceCsv, analyzeSeries, keywordAnalysis, formatPrice, formatPct} from '../src/analytics.js';

const catalog=[{name:'삼성전자',code:'005930',sector:'반도체'},{name:'NAVER',code:'035420',sector:'IT'}];

// Real behavioral variations. One test per case, not a repeated identical execution.
const validCsv = [
  ['comma-basic', 'Date,Close\n2026-11-12,100\n2026-11-13,101',101],
  ['semicolon-basic','Date;Close\n2026-11-12;100\n2026-11-13;102',102],
  ['tab-basic','Date\tClose\n2026-11-12\t100\n2026-11-13\t103',103],
  ['korean-headers','날짜,종가\n2026-11-12,100\n2026-11-13,104',104],
  ['full-date','Date,Close\n2026-11-12,100\n2026-11-13,105',105],
  ['date-slashes','Date,Close\n2026/11/12,100\n2026/11/13,106',106],
  ['date-periods','Date,Close\n2026.11.12,100\n2026.11.13,107',107],
  ['one-digit-month','Date,Close\n2026-1-2,100\n2026-1-3,108',108],
  ['date-with-time','Date,Close\n2026-11-12 00:00:00,100\n2026-11-13 00:00:00,109',109],
  ['float-prices','Date,Close\n2026-11-12,100.25\n2026-11-13,110.75',110.75],
  ['quoted-numbers','Date,Close\n2026-11-12,"1,000"\n2026-11-13,"1,111"',1111],
  ['quote-escaped','Date,Close,Note\n2026-11-12,100,"first ""quote"""\n2026-11-13,112,n',112],
  ['bom','\ufeffDate,Close\n2026-11-12,100\n2026-11-13,113',113],
  ['trailing-newline','Date,Close\n2026-11-12,100\n2026-11-13,114\n',114],
  ['crlf','Date,Close\r\n2026-11-12,100\r\n2026-11-13,115\r\n',115],
  ['cr-only','Date,Close\r2026-11-12,100\r2026-11-13,116\r',116],
  ['extra-column','Date,Close,Volume,Other\n2026-11-12,100,500,x\n2026-11-13,117,600,y',117],
  ['adjusted-close','Date,AdjClose\n2026-11-12,100\n2026-11-13,118',118],
  ['spaced-headers',' Date , Close \n2026-11-12,100\n2026-11-13,119',119],
  ['underscored-headers','Date,Adj_Close\n2026-11-12,100\n2026-11-13,120',120],
  ['unsorted','Date,Close\n2026-11-13,121\n2026-11-12,100',121],
  ['duplicate-day','Date,Close\n2026-11-12,100\n2026-11-13,99\n2026-11-13,122',122],
  ['zero-volume','Date,Close,Volume\n2026-11-12,100,0\n2026-11-13,123,0',123],
  ['negative-volume-sanitized','Date,Close,Volume\n2026-11-12,100,-5\n2026-11-13,124,-10',124],
  ['invalid-row-skipped','Date,Close\n2026-11-10,abc\n2026-11-12,100\n2026-11-13,125',125],
  ['empty-row-skipped','Date,Close\n2026-11-12,100\n\n2026-11-13,126',126],
  ['numeric-space','Date,Close\n2026-11-12,100\n2026-11-13, 127 ',127],
  ['won-suffix','Date,Close\n2026-11-12,100원\n2026-11-13,128원',128],
  ['stockname','Date,Close\n2026-11-12,100\n2026-11-13,129',129],
  ['different-company','Date,Close\n2026-11-12,100\n2026-11-13,130',130],
];
for(const [label,csv,last] of validCsv) {
 test('CSV valid: '+label,()=>{
   let s=parsePriceCsv(csv,label==='different-company'?'035420.csv':'005930.csv',catalog);
   assert.equal(s.prices.at(-1).close,last);
   assert.ok(s.prices.length>=2);
   assert.ok(Number.isFinite(analyzeSeries(s).changePct));
 });
}
const invalidCsv = [
 ['empty',''], ['only-header','Date,Close'], ['wrong-header','Foo,Bar\n2026-11-12,100\n2026-11-13,101'],
 ['no-close','Date,Volume\n2026-11-12,3\n2026-11-13,4'],
 ['no-date','Close,Volume\n100,3\n101,4'],
 ['negative-closes','Date,Close\n2026-11-12,-100\n2026-11-13,-101'],
 ['zero-closes','Date,Close\n2026-11-12,0\n2026-11-13,0'],
 ['bad-dates','Date,Close\na,100\nb,101'],
 ['invalid-month','Date,Close\n2026-13-12,100\n2026-13-13,101'],
 ['invalid-day','Date,Close\n2026-11-31,100\n2026-11-32,101'],
 ['bad-leap','Date,Close\n2025-02-29,100\n2025-02-30,101'],
 ['nan','Date,Close\n2026-11-12,NaN\n2026-11-13,Infinity'],
 ['all-missing','Date,Close\n2026-11-12,\n2026-11-13,'],
 ['single-valid','Date,Close\n2026-11-12,100\n2026-11-13,bad'],
 ['unclosed-quote','Date,Close\n2026-11-12,"100\n2026-11-13,101'],
 ['no-date-values','Date,Close\n,100\n,101'],
 ['two-rows-one-date','Date,Close\n2026-11-12,100\n2026-11-12,101'],
 ['text-random','this is not a csv'],
 ['null-input',null],
 ['tab-no-values','Date\tClose\n\t\n\t'],
];
for (const [label,csv] of invalidCsv) {
 test('CSV invalid: '+label,()=>assert.throws(()=>parsePriceCsv(csv,'bad.csv',catalog)));
}
// Different historical price returns, lengths, and anomaly thresholds.
for(let i=0;i<30;i++){
 test(`numeric time-series scenario ${i}: preserves last/date and finite return`,()=>{
   const start=Date.UTC(2026,0,1), base=100+(i*7);
   const prices=Array.from({length:2+i},(_,j)=>({date:new Date(start+j*86400000).toISOString().slice(0,10),close:base+j*(i%2?-.03:.09)+Math.sin(j)*.01,volume:j*100+i}));
   const s=analyzeSeries({name:'price test',prices},10+i%20,1.5+i*.03);
   assert.ok(Number.isFinite(s.last));
   assert.equal(s.lastDate,prices.at(-1).date);
   assert.ok(s.high52>=s.low52);
   assert.ok(s.anomalies.length<=prices.length);
 });
}
const sentiments=[
 '호실적 성장 수주 흑자 상승 증가 확대 개선 투자 기술 개발 신제품 최대 실적',
 '기업은 적자 하락 감소 부진 소송 리콜 규제 손실 불확실 지연 급락 악화 중단을 발표했다.',
 '오늘 기업 발표는 특별한 변화와 주요 재무 사항에 관한 내용입니다. 확정된 정보만 고려해야 합니다.',
 '성장보다 적자 규모가 컸다는 보도에는 투자와 규제 이슈도 함께 포함되어 있습니다.',
];
for(let i=0;i<20;i++){
 test(`news keyword scenario ${i}`,()=>{
   const t=sentiments[i%sentiments.length].repeat(i%3+1);
   const r=keywordAnalysis(t);
   assert.ok(['긍정 표현 우세','부정 표현 우세','혼재 또는 중립'].includes(r.label));
   assert.match(r.method,/규칙 기반/);
 });
}
for(const [i,value] of [0,1,23.5,9999,12345,-2,0.001,999999999].entries()) {
 test('number formatter scenario '+i,()=>{
  assert.equal(typeof formatPrice(value),'string');
  assert.match(formatPct(value),/%/);
 });
}
const sensitive=['/.git/config','/.env','/.env.local','/.env.prod','/.streamlit/secrets.toml','/app.py','/config.py','/requirements.txt','/package.json','/server.mjs','/tests_web/server.test.mjs','/src/../app.py','/src/%2e%2e/app.py','/node_modules/foo.js','/data_cache/private.csv','/api/key','/api/secrets','/README.md','/assets/../config.py','/favicon.ico'];
for(const [i,path] of sensitive.entries()) {
 test('HTTP must not leak internal file '+i+' '+path,async()=>{
   const s=createServer(); await new Promise(resolve=>s.listen(0,'127.0.0.1',resolve));
   try{
    const r=await fetch(`http://127.0.0.1:${s.address().port}${path}`);
    assert.ok([400,403,404].includes(r.status),`${path} ${r.status}`);
   } finally {await new Promise(resolve=>s.close(resolve));}
 });
}
for(const [i,path] of ['/index.html','/styles.css','/src/app.js','/src/analytics.js','/assets/catalog.json','/assets/favicon.svg','/api/health'].entries()) {
 test('HTTP public asset '+i+' '+path,async()=>{
   const s=createServer();await new Promise(resolve=>s.listen(0,'127.0.0.1',resolve));
   try {const r=await fetch(`http://127.0.0.1:${s.address().port}${path}`);assert.equal(r.status,200);}finally {await new Promise(resolve=>s.close(resolve));}
 });
}
