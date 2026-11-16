import test from 'node:test';
import assert from 'node:assert/strict';
import {parseCsv,parsePriceCsv,analyzeSeries,keywordAnalysis} from '../src/analytics.js';
const catalog=[{name:'삼성전자',code:'005930',sector:'반도체·전자'}];
test('CSV parses Korean and double quotes',()=>{
 assert.deepEqual(parseCsv('날짜,종가,메모\n2026-11-12,"100,000","a,b"'),[['날짜','종가','메모'],['2026-11-12','100,000','a,b']]);
});
test('uploaded prices are sorted and tied to real catalog symbol',()=>{
 const x=parsePriceCsv('Date,Close,Volume\n2026-11-13,"102,000",200\n2026-11-12,"100,000",150\n','005930.csv',catalog);
 assert.equal(x.name,'삼성전자');assert.equal(x.prices[0].date,'2026-11-12');
 assert.ok(Math.abs(analyzeSeries(x).changePct-2)<1e-9);
});
test('invalid prices and CSVs fail clearly',()=>{
 assert.throws(()=>parsePriceCsv('abc,x\n1,2','bad.csv',catalog),/최소 2개|Date/);
 assert.throws(()=>parsePriceCsv('Date,Close\n2026-11-12,0\n2026-11-13,-1\n','005930.csv',catalog),/유효한/);
});
test('no fabricated anomaly data',()=>{
 const x=parsePriceCsv('Date,Close\n2026-11-12,100\n2026-11-13,101','005930.csv',catalog);
 assert.deepEqual(analyzeSeries(x).anomalies,[]);
});
test('article text keyword analysis is rule-based',()=>{
 const x=keywordAnalysis('기업이 새로운 공장 투자와 기술 개발로 성장 기대감을 높였고 매출 증가를 발표했다.');
 assert.equal(x.label,'긍정 표현 우세');
 assert.throws(()=>keywordAnalysis('short'),/30자/);
});
