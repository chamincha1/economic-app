import {readFileSync} from 'node:fs';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {dirname,resolve} from 'node:path';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const pageTags=['#nav','#content','#notice','#current-page','#page-heading','#page-lead','#ai-tag','#csv-input','#board-search','#board-sector','#refresh-three','#detail-choice','#detail-refresh','#news-form','#quality','#article-urls','#news-output','#analyze-news','#news-status','#pred-output','#run-pred','#predict-code','#clear-csv'];
const items = new Map(pageTags.map(tag=>[tag,{innerHTML:'',textContent:'',value:'',disabled:false,
  focus(){},setSelectionRange(){},addEventListener(){},querySelectorAll(){return[]},get selectionStart(){return 0},set className(v){this._className=v;}}]));
globalThis.document={querySelector:selector=>items.get(selector)||null,querySelectorAll:()=>[]};
globalThis.window={scrollTo(){}};
globalThis.fetch=async url=>{
  if(url==='/api/catalog')return{ok:true,json:async()=>JSON.parse(readFileSync(resolve(root,'assets/catalog.json'),'utf8'))};
  if(url==='/api/health')return{ok:true,json:async()=>({ok:true,ai_configured:false,ai_calls_remaining_local:0})};
  if(url.startsWith('/api/stock'))return{ok:false,status:503,json:async()=>({ok:false,error:'TEST_OFFLINE'})};
  throw Error('unexpected fetch '+url);
};
const {nav}=await import(pathToFileURL(resolve(root,'src/app.js')).href);
await new Promise(resolve=>setTimeout(resolve,200));
const contents={home:'데이터 현황',board:'국내 30개 기업',detail:'종목 상세',anomaly:'가격 급변 탐지',
  news:'기사 URL',ai:'AI 상승 방향',backtest:'시계열 검증',data:'데이터 센터'};
let tests=0;
for(const [section,needle] of Object.entries(contents)){
  nav(section);
  if(!items.get('#content').innerHTML.includes(needle))throw Error(`${section}: ${needle} missing`);
  tests++;
}
if(!items.get('#nav').innerHTML.includes('AI 예측'))throw Error('navigation missing');tests++;
console.log(`UI state/render smoke: ${tests} checks passed`);
