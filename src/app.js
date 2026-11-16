import {parsePriceCsv, analyzeSeries, formatPrice, formatPct} from './analytics.js';

// Keep the original MARKET PULSE dashboard's sidebar, cards, typography and colors.
// Only update visible views; expensive price/ML/AI calls are strictly user-driven.
const PAGES = [
  ['home','홈 대시보드','◈'],['board','국내 시세 보드','▤'],['detail','종목 상세','⌕'],
  ['anomaly','급변 탐지','⚡'],['news','뉴스·공시','▣'],['ai','AI 예측','✦'],
  ['backtest','백테스트','◷'],['data','데이터 센터','⚙']
];
const WATCH_KEY='market-pulse-watchlist-v21';
const DEFAULT_WATCH=['005930','000660','005380','000270','035420','035720'];
const MAX_WATCH=12;
const state={page:'home',catalog:[],custom:new Map(),watchlist:[...DEFAULT_WATCH],online:new Map(),uploads:new Map(),analyzed:new Map(),errors:new Map(),inflight:new Set(),
 selectedCode:'005930',keyword:'',sector:'전체',lastNews:null,predictions:new Map(),aiConfigured:false,aiDailyRemaining:0,quality:'deep'};
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const metric=(label,value,description='')=>`<div class="card"><div class="stat-label">${esc(label)}</div><div class="stat-value">${esc(value)}</div><div class="stat-footer">${esc(description)}</div></div>`;
const section=(title,sub='',more='')=>`<div class="section-head"><div><h2>${esc(title)}</h2><p>${esc(sub)}</p></div>${more}</div>`;
const empty=(msg,icon='◫')=>`<div class="empty"><div class="empty-icon">${icon}</div>${esc(msg)}</div>`;
const btn=(label,id,primary=false)=>`<button class="btn ${primary?'primary':''}" id="${id}" type="button">${esc(label)}</button>`;
function status(message,kind='blue') {const el=$('#notice');if(!el)return;el.className=`notice ${kind==='green'?'green':''}`;el.textContent=message;}
function itemByCode(code){return state.catalog.find(x=>x.code===code)||state.custom.get(code);}
function currentCatalog(){return [...state.catalog,...[...state.custom.values()].filter(x=>!state.catalog.some(y=>y.code===x.code))];}
function registered(){return [...state.online.values()].filter(x=>state.watchlist.includes(x.code)).concat([...state.uploads.values()]);}
function saveWatchlist(){
  try{globalThis.localStorage?.setItem(WATCH_KEY,JSON.stringify(state.watchlist.map(code=>({code,name:itemByCode(code)?.name||`종목 ${code}`,sector:itemByCode(code)?.sector||'직접 추가'}))));}catch{/* restricted browser storage */}
}
function restoreWatchlist(){
  try{
    const raw=globalThis.localStorage?.getItem(WATCH_KEY);if(!raw)return;
    const parsed=JSON.parse(raw);if(!Array.isArray(parsed))return;
    const codes=[];
    for(const r of parsed.slice(0,MAX_WATCH)){
      if(!r||typeof r.code!=='string'||!/^\d{6}$/.test(r.code)||r.code==='000000'||codes.includes(r.code))continue;
      codes.push(r.code);
      if(!state.catalog.some(x=>x.code===r.code)){
        const name=typeof r.name==='string'&&r.name.length<=60?r.name:`종목 ${r.code}`;
        const sector=typeof r.sector==='string'&&r.sector.length<=30?r.sector:'직접 추가';
        state.custom.set(r.code,{code:r.code,name,sector});
      }
    }
    if(codes.length)state.watchlist=codes;
  }catch{/* corrupt/unavailable storage: use six default codes */}
}
function addWatch(code,detail=null){
  if(!/^\d{6}$/.test(code)||code==='000000'){status('6자리 국내 종목코드를 입력하세요.');return false;}
  if(state.watchlist.includes(code)){status('이미 관심종목에 추가되어 있어요.');return false;}
  if(state.watchlist.length>=MAX_WATCH){status(`관심종목은 최대 ${MAX_WATCH}개까지 등록할 수 있어요.`);return false;}
  if(!itemByCode(code))state.custom.set(code,detail||{code,name:`종목 ${code}`,sector:'직접 추가'});
  state.watchlist.push(code);saveWatchlist();render();
  status(`${itemByCode(code)?.name||code} 추가 완료 · 실제 시세를 자동 조회합니다.`,'green');
  void fetchStock(code);return true;
}
function removeWatch(code){
  state.watchlist=state.watchlist.filter(x=>x!==code);
  state.online.delete(code);state.errors.delete(code);state.predictions.delete(code);state.analyzed.clear();
  if(state.selectedCode===code)state.selectedCode=state.watchlist[0]||'';
  saveWatchlist();render();status(`${itemByCode(code)?.name||code} 관심목록에서 제거했어요.`,'green');
}
function renderWatchPanel(){
  const count=$('#watch-count'),list=$('#watch-items');if(!count||!list)return;
  count.textContent=`${state.watchlist.length}개`;
  list.innerHTML=state.watchlist.map(code=>{
    const item=itemByCode(code)||{name:`종목 ${code}`},p=byCode(code);
    const value=p?`${formatPrice(p.last)}원`:(state.inflight.has(code)?'조회 중…':(state.errors.has(code)?'조회 실패':'자동 조회 예정'));
    return `<div class="watch-item"><div style="min-width:0"><span class="watch-name">${esc(item.name)}</span><span class="watch-code">${esc(code)}</span></div><span class="watch-value">${esc(value)}</span><button type="button" data-remove-watch="${esc(code)}" aria-label="${esc(item.name)} 삭제" title="관심종목 삭제">×</button></div>`;
  }).join('')||'<p class="watch-hint">관심종목을 추가해 주세요.</p>';
  list.querySelectorAll('[data-remove-watch]').forEach(el=>el.addEventListener('click',()=>removeWatch(el.dataset.removeWatch)));
}
function renderWatchSuggestions(query,remote=null){
  const el=$('#watch-suggestions');if(!el)return;
  const q=query.trim().toLowerCase();
  const matches=remote||(!q?[]:currentCatalog().filter(x=>(x.name.toLowerCase().includes(q)||x.code.includes(q))&&!state.watchlist.includes(x.code)).slice(0,6));
  el.innerHTML=matches.map(x=>`<button type="button" data-suggest="${esc(x.code)}">＋ ${esc(x.name)} <small>(${esc(x.code)})</small></button>`).join('');
  el.querySelectorAll('[data-suggest]').forEach(b=>b.addEventListener('click',()=>{
    const code=b.dataset.suggest;const item=matches.find(x=>x.code===code);
    if(item&&!itemByCode(code))state.custom.set(code,item);
    if(addWatch(code,item)){$('#watch-search').value='';el.innerHTML='';}
  }));
}
function bindWatchControls(){
  const form=$('#watch-form'),input=$('#watch-search');if(!form||!input)return;
  input.addEventListener('input',()=>renderWatchSuggestions(input.value));
  form.addEventListener('submit',e=>{
    e.preventDefault();const query=input.value.trim();
    if(/^\d{6}$/.test(query)){
      if(addWatch(query)){input.value='';renderWatchSuggestions('');}return;
    }
    const matches=currentCatalog().filter(x=>x.name.toLowerCase().includes(query.toLowerCase())&&query.length>=2&&!state.watchlist.includes(x.code));
    if(matches.length===1){if(addWatch(matches[0].code,matches[0])){input.value='';renderWatchSuggestions('');}}
    else if(matches.length>1){renderWatchSuggestions(query);status('검색 결과 중 원하는 종목을 선택해 주세요.');}
    else{status('30개 기본 목록에서 찾지 못했어요. 6자리 코드를 입력하거나 KRX 전체 검색을 누르세요.');}
  });
  $('#watch-refresh')?.addEventListener('click',()=>{const codes=state.watchlist.slice(0,10);status(`관심종목 ${codes.length}개를 새로 확인합니다.`);void loadWatchPrices(codes,true);});
  $('#watch-krx-search')?.addEventListener('click',async()=>{
    const q=input.value.trim();if(q.length<2){status('전체 KRX 검색어를 2글자 이상 입력해 주세요.');return;}
    const button=$('#watch-krx-search');button.disabled=true;status('KRX 전체 상장종목 이름을 검색합니다...');
    try{const data=await requestJson(`/api/search?q=${encodeURIComponent(q)}`);renderWatchSuggestions(q,data.results.filter(x=>!state.watchlist.includes(x.code)));if(!data.results.length)status('검색 결과가 없습니다.');else status('아래 검색 결과에서 종목을 선택해 주세요.','green');}
    catch(err){status(`KRX 검색 실패: ${err.message}`);}finally{button.disabled=false;}
  });
}

function loaded(){return registered().map(x=>cachedAnalyze(x));}
function cachedAnalyze(x){
  if(!state.analyzed.has(x)){state.analyzed.set(x,analyzeSeries(x));}
  return state.analyzed.get(x);
}
function byCode(code){
  const entries=[...state.uploads.values(),...state.online.values()];const row=entries.find(x=>x.code===code);
  return row?cachedAnalyze(row):null;
}
function matchedNames(){return currentCatalog().filter(x=>(state.sector==='전체'||x.sector===state.sector)&&(`${x.name} ${x.code}`.toLowerCase().includes(state.keyword.toLowerCase())));}
async function requestJson(path,options={}){
  const ctrl=new AbortController();const timer=setTimeout(()=>ctrl.abort(),path.includes('/api/news/analyze')?230000:90000);
  try{
    const r=await fetch(path,{...options,signal:ctrl.signal});
    const data=await r.json().catch(()=>({error:'서버가 올바른 JSON을 반환하지 않았습니다.'}));
    if(!r.ok||data.ok===false)throw new Error(data.error||`HTTP ${r.status}`);
    return data;
  }finally{clearTimeout(timer);}
}
function registerOnline(data){
  const item=itemByCode(data.code);
  if(!item)throw new Error('종목 정보가 확인되지 않습니다.');
  const previousSeries=state.online.get(data.code);
  const series={code:data.code,name:item.name,sector:item.sector,filename:`${data.code}.csv`,prices:data.prices,
    source:data.meta?.source||'출처 미확인',meta:data.meta,origin:'online'};
  state.online.set(data.code,series);
  // Invalidate only the previous series; other already-analyzed symbols remain cached.
  if(previousSeries)state.analyzed.delete(previousSeries);
}
async function fetchStock(code,force=false){
  if(state.inflight.has(code))return;
  state.inflight.add(code);
  renderWatchPanel();if(['home','board'].includes(state.page))render();
  try{
    // Local-only instant preview of previously fetched REAL OHLCV. Still refresh online afterwards.
    if(!force&&!state.online.has(code)){
      try{
        const old=await requestJson(`/api/stock/cached?code=${encodeURIComponent(code)}&days=460`);
        registerOnline(old);
        renderWatchPanel();if(['home','board','detail'].includes(state.page))render();
        status(`${itemByCode(code)?.name||code} · 저장된 실제 과거 종가를 먼저 표시합니다. 최신 자료를 조회 중입니다.`);
      }catch{/* on first run no local data exists; continue live fetch */}
    }
    const response=await requestJson(`/api/stock?code=${encodeURIComponent(code)}&days=460${force?'&refresh=1':''}`);
    registerOnline(response);
    state.errors.delete(code);
    status(`${itemByCode(code)?.name||code} 조회 완료 · ${response.meta.last_trade_date} 마지막 거래일 · ${response.meta.status==='cached'?'이전 캐시 사용':response.meta.source}`,'green');
  }catch(e){
    state.errors.set(code,e.message);
    status(`${itemByCode(code)?.name||code} 조회 실패: ${e.message}`);
  }finally{
    state.inflight.delete(code);
    renderWatchPanel();
    if(['home','board','detail','anomaly','data','ai'].includes(state.page))render();
  }
}
async function loadWatchPrices(codes=state.watchlist.slice(0,8),force=false){
  // Three bounded workers give fast first paint without issuing 30 concurrent vendor calls.
  const unique=[...new Set(codes)].filter(code=>/^\d{6}$/.test(code)&&!state.inflight.has(code)&&(force||!state.online.has(code)));
  let next=0;
  const workers=Array.from({length:Math.min(3,unique.length)},async()=>{
    while(next<unique.length){const code=unique[next++];await fetchStock(code,force);}
  });
  await Promise.all(workers);
}
function loadDefault(){void loadWatchPrices(state.watchlist.slice(0,8));}
function nav(page){state.page=page;render();window.scrollTo({top:0,behavior:'smooth'});}
function renderNav(){
  const el=$('#nav');el.innerHTML=PAGES.map(([id,name,icon])=>`<button type="button" data-page="${id}" ${state.page===id?'aria-current="page"':''}><span class="nav-icon">${icon}</span>${name}</button>`).join('');
  el.querySelectorAll('[data-page]').forEach(b=>b.addEventListener('click',()=>nav(b.dataset.page)));
}
function chartSvg(series){
  const prices=series.prices;if(prices.length<2)return '';
  const stride=Math.max(1,Math.ceil(prices.length/300));const data=prices.filter((_,i)=>i%stride===0||i===prices.length-1);
  const width=920,height=295,pad=44;const lo=Math.min(...data.map(x=>x.close)),hi=Math.max(...data.map(x=>x.close));
  const span=Math.max(hi-lo,hi*.00001);const X=i=>pad+i*(width-2*pad)/(data.length-1);const Y=p=>height-pad-((p-lo)/span)*(height-2*pad);
  const path=data.map((v,i)=>`${i?'L':'M'}${X(i).toFixed(2)},${Y(v.close).toFixed(2)}`).join(' ');
  return `<svg class="chart" role="img" aria-label="${esc(series.name)}의 실제 주가 추이" viewBox="0 0 ${width} ${height}">
  <line x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}" stroke="#d9e4ef"/>
  <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${height-pad}" stroke="#d9e4ef"/>
  <path d="${path}" stroke="${data.at(-1).close>=data[0].close?'#13a36f':'#e34c56'}" fill="none" stroke-width="3" stroke-linecap="round" />
  <text x="${pad+5}" y="${pad-12}" fill="#7c8b9e" font-size="14">${esc(formatPrice(hi))}</text>
  <text x="${pad+5}" y="${height-pad-9}" fill="#7c8b9e" font-size="14">${esc(formatPrice(lo))}</text>
  <text x="${pad}" y="${height-9}" fill="#7c8b9e" font-size="14">${esc(data[0].date)}</text>
  <text x="${width-pad}" y="${height-9}" text-anchor="end" fill="#7c8b9e" font-size="14">${esc(data.at(-1).date)}</text></svg>`;
}
const sourceLabel=s=>s?.meta?.status==='cached'?'기존 저장 데이터(최신 아님)':s?.origin==='online'?`일봉 · ${s?.meta?.source||'출처 미확인'}`:'사용자 CSV 종가';
function stockCard(item){
  const x=byCode(item.code);const isLoading=state.inflight.has(item.code);
  return `<div class="stock-mini" data-stock="${esc(item.code)}" tabindex="0"><div class="stock-title">${esc(item.name)}</div><div class="stock-symbol">${esc(item.code)} · ${esc(item.sector)}</div>
    <div class="stock-price">${x?formatPrice(x.last)+'원':isLoading?'조회 중…':'—'}</div>
    <div class="change ${x?(x.changePct>=0?'up':'down'):'muted'}">${x?formatPct(x.changePct):state.errors.get(item.code)?'조회 실패':'데이터 미조회'}</div>
    <div class="card-caption">${x?`${esc(x.lastDate)} · ${esc(sourceLabel(x))}`:state.errors.has(item.code)?'온라인 조회 실패 · 다시 시도':'관심종목 추가 시 자동 조회'}</div></div>`;
}
function bindStockCards(){
  document.querySelectorAll('[data-stock]').forEach(el=>{
    const act=async()=>{const code=el.dataset.stock;state.selectedCode=code;
      if(!byCode(code)){status(`${itemByCode(code)?.name||code}의 실제 일봉을 확인합니다.`);await fetchStock(code);}
      if(byCode(code))nav('detail');};
    el.addEventListener('click',act);el.addEventListener('keydown',e=>{if(e.key==='Enter')act();});
  });
}
function uploadBox(){return `<div class="upload-box"><strong>📁 실제 주가 CSV 가져오기</strong><p>Date(날짜), Close(종가) 열이 포함된 CSV 파일도 바로 분석합니다.<br>가상 가격은 생성하지 않습니다.</p><label class="btn primary" for="csv-input">CSV 파일 선택 (여러 개 가능)</label><input id="csv-input" type="file" accept=".csv,text/csv" multiple /></div>`;}
function bindUpload(){
  const input=$('#csv-input');if(!input)return;
  input.addEventListener('change',async e=>{
    const files=[...e.target.files];let count=0;let errors=[];
    for(const file of files){
      if(file.size>8*1024*1024){errors.push(`${file.name}: 8MB 초과`);continue;}
      try{const parsed=parsePriceCsv(await file.text(),file.name,state.catalog);parsed.origin='csv';state.uploads.set(file.name,parsed);
        state.selectedCode=parsed.code||state.selectedCode;count++;}
      catch(err){errors.push(`${file.name}: ${err.message}`);}
    }
    state.analyzed.clear();if(count)status(`실제 CSV ${count}개를 추가했습니다.`,'green');
    if(errors.length)status(errors.join(' / '));render();
  });
}
function renderHome(){
  const list=loaded(),count=list.length;const avg=count?list.reduce((s,x)=>s+x.changePct,0)/count:null;
  const last=count?list.map(x=>x.lastDate).sort().at(-1):null;
  $('#content').innerHTML=`${section('데이터 현황','CSV 파일 없이 관심종목의 실제 일봉을 자동 조회합니다. 직접 업로드는 선택 기능입니다.')}
    <div class="grid grid-4">${metric('가격 확인 종목',`${count}개`,'관심종목 자동 시세 수집')}${metric('평균 일별 등락',avg==null?'—':formatPct(avg),'각 종목의 마지막 거래일')}${metric('가격 급변 탐지',count?`${list.reduce((s,x)=>s+x.anomalies.length,0)}건`:'—','직전 20거래일 |Z| ≥ 2.5')}${metric('마지막 거래일',last||'—','공급처 제공 일봉')}</div>
    ${section('내 관심종목',`${state.watchlist.length}개 등록 · 처음 8개는 접속 시 자동 조회 · 추가·삭제는 왼쪽 메뉴`)}
    <div class="stock-grid">${state.watchlist.map(code=>stockCard(itemByCode(code)||{code,name:`종목 ${code}`,sector:'직접 추가'})).join('')}</div>
    <div class="note green"><strong>CSV 없이 자동으로 주가를 조회합니다.</strong><br>추가 종목은 왼쪽 사이드바의 검색창에서 등록할 수 있어요. 가격이 늦거나 누락되면 <b>관심종목 가격 새로고침</b>을 선택하세요.</div>
    <div class="note blue"><strong>데이터 기준</strong><br>표시된 가격은 제공처가 반환한 <b>일별 종가</b>이며 실시간 체결가가 아닙니다. 최신 거래일·원출처를 함께 확인해 주세요.</div>`;
  bindStockCards();
}
function renderBoard(){
 const sectors=['전체',...new Set(currentCatalog().map(x=>x.sector))];const matched=matchedNames();
 $('#content').innerHTML=`${section('국내 30개 기업 · 관심종목 추가','30개 기본 목록에서 기업을 검색하고 관심종목에 등록할 수 있습니다. 전체 KRX 검색은 왼쪽 사이드바에 있습니다.')}
   <div class="control-bar"><input class="field" id="board-search" placeholder="기업명 또는 6자리 종목코드" value="${esc(state.keyword)}" aria-label="기업 검색" />
   <select class="field" id="board-sector">${sectors.map(s=>`<option ${s===state.sector?'selected':''}>${esc(s)}</option>`).join('')}</select>
   ${btn('관심종목 가격 갱신','refresh-three')}</div>
   <div class="table-wrap"><table class="table"><thead><tr><th>종목명</th><th>종목코드</th><th>업종</th><th>최근 종가</th><th>등락률</th><th>기준일</th><th>관심종목</th></tr></thead><tbody id="stock-rows">
   ${matched.map(x=>{const p=byCode(x.code);const added=state.watchlist.includes(x.code);return `<tr data-stock="${esc(x.code)}" tabindex="0"><td class="name">${esc(x.name)}</td><td>${esc(x.code)}</td><td>${esc(x.sector)}</td><td>${p?formatPrice(p.last)+'원':state.inflight.has(x.code)?'조회 중…':'행 클릭 시 조회'}</td><td class="${p?(p.changePct>=0?'up':'down'):'muted'}">${p?formatPct(p.changePct):'—'}</td><td>${p?esc(p.lastDate):'—'}</td><td><button class="table-watch" type="button" data-add-board="${esc(x.code)}" ${added?'disabled':''}>${added?'✓ 등록됨':'+ 추가'}</button></td></tr>`;}).join('')}
   </tbody></table></div><div class="note blue">기본 6개 종목은 처음 접속 시 자동 조회됩니다. 나머지는 관심종목에 추가하거나 종목 행을 눌러 조회할 수 있어요.</div>`;
 $('#board-search').addEventListener('input',e=>{state.keyword=e.target.value;const pos=e.target.selectionStart;renderBoard();const x=$('#board-search');x.focus();x.setSelectionRange(pos,pos);});
 $('#board-sector').addEventListener('change',e=>{state.sector=e.target.value;renderBoard();});
 $('#refresh-three').addEventListener('click',()=>{void loadWatchPrices(state.watchlist.slice(0,10),true);});
 bindStockCards();
 $('#content').querySelectorAll('[data-add-board]').forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();addWatch(b.dataset.addBoard);}));
}
function renderDetail(){
 const list=loaded();const selected=list.find(x=>x.code===state.selectedCode)||list[0];
 if(!selected){$('#content').innerHTML=section('종목 상세','카드를 눌러 먼저 종목 시세를 조회해 주세요.')+empty('현재 조회한 주가 데이터가 없습니다.');return;}
 const options=list.map(x=>`<option value="${esc(x.code||x.filename)}" ${(x.code||x.filename)===(selected.code||selected.filename)?'selected':''}>${esc(x.name)} (${esc(x.code||'CSV')})</option>`).join('');
 $('#content').innerHTML=`${section('종목 상세',`${selected.name} · ${selected.lastDate} 거래일 · ${sourceLabel(selected)}`,`<select class="field" id="detail-choice">${options}</select>`)}
 <div class="grid grid-4">${metric('마지막 종가',formatPrice(selected.last)+'원','장중 체결가 아님')}${metric('전일 대비',formatPct(selected.changePct),formatPrice(selected.change)+'원')}${metric('20일 이동평균',selected.sma20==null?'—':formatPrice(selected.sma20)+'원','실제 최근 거래일')}${metric('20일 변동성',selected.volatility==null?'—':selected.volatility.toFixed(2)+'%p','수익률 표준편차')}</div>
 ${section('가격 흐름','실제로 수집한 날짜별 종가만 연결한 차트')}<div class="card">${chartSvg(selected)}</div>
 ${section('추가 통계','최근 최대 252개 거래일 가격 기준')}<div class="grid grid-3">${metric('52주 최고',formatPrice(selected.high52)+'원')}${metric('52주 최저',formatPrice(selected.low52)+'원')}${metric('기간 전체 변동',formatPct(selected.periodChangePct),`${selected.prices.length}개 가격 기록`)}</div>
 <div style="margin-top:14px">${btn('해당 종목 새로 조회','detail-refresh')}</div>`;
 $('#detail-choice').addEventListener('change',e=>{state.selectedCode=e.target.value;renderDetail();});
 $('#detail-refresh').addEventListener('click',()=>fetchStock(selected.code,true));
}
function renderAnomaly(){
 const rows=loaded().flatMap(x=>x.anomalies.map(a=>({...a,name:x.name}))).sort((a,b)=>b.date.localeCompare(a.date)).slice(0,200);
 $('#content').innerHTML=`${section('가격 급변 탐지','이전 20거래일 수익률 대비 통계적 이상 움직임 · 미래 예측이 아닙니다.')}
 ${rows.length?`<div class="table-wrap"><table class="table"><thead><tr><th>종목</th><th>날짜</th><th>등락률</th><th>Z 점수</th></tr></thead><tbody>${rows.map(x=>`<tr><td class="name">${esc(x.name)}</td><td>${esc(x.date)}</td><td class="${x.changePct>=0?'up':'down'}">${formatPct(x.changePct)}</td><td>${x.z.toFixed(2)}</td></tr>`).join('')}</tbody></table></div>`:empty('조회한 데이터에서 급변 이벤트가 발견되지 않았습니다.')}`;
}
const bullets=(items,key='point')=>(items?.length?`<ul class="analysis-list">${items.map(x=>`<li>${esc(x[key]||x)}${x.sources?.length?` <span class="muted">[${x.sources.join(', ')}]</span>`:''}</li>`).join('')}</ul>`:'<p class="muted">기사에서 확인되지 않음</p>');
function renderNews(){
 $('#content').innerHTML=`${section('기사 URL · GroqCloud 심층 분석','공개 기사 1~4개를 비교 분석합니다. 본문 확인 실패 시 결과를 생성하지 않습니다.')}
 <div class="note blue">별도의 NAVER 뉴스 API나 CSV가 필요 없습니다. <strong>GroqCloud 호출은 아래 분석 버튼을 누를 때에만 발생</strong>하며, 심층 분석은 2회의 모델 요청을 사용합니다.</div>
 <div class="card"><form id="news-form"><label class="field-label" for="article-urls">기사 링크 (한 줄에 하나씩 · 최대 4개)</label>
 <textarea id="article-urls" class="field" rows="4" placeholder="https://n.news.naver.com/mnews/article/...\nhttps://www.example.com/news/...">${esc(state.lastNews?.input||'')}</textarea>
 <label class="field-label" for="quality" style="margin-top:14px">AI 분석 품질</label>
 <select id="quality" class="field"><option value="deep" ${state.quality==='deep'?'selected':''}>심층 분석 · 높은 품질 · 2회 모델 호출 (기본)</option><option value="standard" ${state.quality==='standard'?'selected':''}>일반 분석 · 더 빠름 · 1회 모델 호출</option></select>
 <div class="form-row" style="margin-top:14px"><button class="btn primary" id="analyze-news" type="submit" ${state.aiConfigured?'':'disabled'}>공개 기사 불러와 GroqCloud 분석</button><span class="section-text" id="news-status">${state.aiConfigured?'서버에 키가 설정되어 있음':'GROQ_API_KEY 미설정 · .env 확인'}</span></div></form>
 <div id="news-output"></div></div>`;
 $('#quality').addEventListener('change',e=>{state.quality=e.target.value;});
 $('#news-form').addEventListener('submit',async e=>{
  e.preventDefault();const input=$('#article-urls').value.trim();const urls=input.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
  if(urls.length<1||urls.length>4){$('#news-status').textContent='공개 기사 링크 1~4개를 입력하세요.';return;}
  for(const url of urls){try{const u=new URL(url);if(!['http:','https:'].includes(u.protocol))throw Error();}catch{$('#news-status').textContent='올바른 http(s) URL만 입력할 수 있습니다.';return;}}
  state.lastNews={input};const button=$('#analyze-news'),out=$('#news-output');button.disabled=true;
  $('#news-status').textContent='공개 기사 가져오기 → 근거 분석 진행 중…';out.innerHTML='';
  try{
   const result=await requestJson('/api/news/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({urls,quality:state.quality})});
   const r=result.analysis;state.aiDailyRemaining=Math.max(0,state.aiDailyRemaining-(r.request_count||1));$('#ai-tag').textContent=`GroqCloud 설정됨 · 오늘 ${state.aiDailyRemaining}회 남음`;
   out.innerHTML=`<div class="analysis-result"><strong>분석 관점: ${esc(r.stance)}</strong><p>${esc(r.summary)}</p>
   <div class="grid grid-2"><div><h3>긍정적인 요인</h3>${bullets(r.positive_factors)}</div><div><h3>부정적인 요인</h3>${bullets(r.negative_factors)}</div></div>
   <h3>기사에 등장한 수치·사실</h3>${bullets(r.key_numbers,'fact')}
   <h3>주가에 영향을 줄 수 있는 경로 (정성적 해석)</h3><p>${esc(r.possible_impact)}</p>
   <h3>불확실성과 확인할 점</h3>${bullets(r.uncertainties)}
   <div class="note">${esc(r.limitations||'원문 외 사실 검증은 수행하지 않았습니다.')}</div>
   <h3>근거 기사</h3>${(r.sources||[]).map(s=>`<div class="news-item"><strong>[${esc(s.id)}] ${esc(s.title)}</strong><p>${esc(s.publisher)} · ${esc(s.published_at||'일시 미확인')} · ${esc(s.basis)}${s.truncated?' · 본문 일부 발췌':''}</p><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">원문 열기</a></div>`).join('')}
   <p class="muted">AI 모델: ${esc(r.model)} · 서버 호출 ${r.request_count}회 · 기사 외부 진위 검증 아님</p></div>`;
   $('#news-status').textContent='분석 완료 · AI 응답은 실제 기사 내용과 함께 확인하세요.';status('GroqCloud 기사 근거 분석을 완료했습니다.','green');
  }catch(err){out.innerHTML=`<div class="note">${esc(err.message)}</div>`;$('#news-status').textContent='분석 실패 · 이유를 확인하세요.';}
  finally{button.disabled=!state.aiConfigured;}
 });
}
function resultsTable(rows,columns){return `<div class="table-wrap"><table class="table"><thead><tr>${columns.map(([k,l])=>`<th>${esc(l)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${columns.map(([k])=>`<td>${esc(typeof r[k]==='number'?(k==='상승 추정 확률'||['정확도','정밀도','재현율'].includes(k)?(r[k]*100).toFixed(1)+'%':r[k].toFixed(3)):r[k]??'—')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
function renderAI(){
 const options=currentCatalog().filter(x=>state.online.has(x.code));const picked=options.find(x=>x.code===state.selectedCode)||options[0];
 $('#content').innerHTML=`${section('AI 상승 방향 확률 추정','기존 Python 시계열 머신러닝을 버튼 클릭 시에만 실행 · GroqCloud는 뉴스에만 사용')}
 <div class="note blue">상승 추정 확률은 학습·검증·시험 구간을 나눈 로지스틱 분류 모델의 미보정 결과입니다. 검증된 미래 수익이나 투자 추천이 아닙니다.</div>
 <div class="card"><label for="predict-code" class="field-label">대상 기업</label><select class="field" id="predict-code">${options.map(x=>`<option value="${esc(x.code)}" ${x.code===picked?.code?'selected':''}>${esc(x.name)}</option>`).join('')}</select>
 <div style="margin-top:14px">${btn('실제 과거 데이터로 학습·시험·예측','run-pred',true)}</div><p class="section-text">최소 100개 이상 과거 학습 행이 필요하며 결과를 생성하는 데 다소 시간이 걸릴 수 있습니다.</p><div id="pred-output"></div></div>`;
 if(!options.length){$('#pred-output').innerHTML='<div class="note">먼저 홈 대시보드에서 종목을 클릭해 실제 주가 데이터를 불러와 주세요.</div>';$('#run-pred').disabled=true;}
 $('#run-pred').addEventListener('click',async()=>{
  const code=$('#predict-code').value;if(!code)return;
  const out=$('#pred-output'),b=$('#run-pred');b.disabled=true;out.innerHTML='<div class="note blue">과거 데이터 기반 시간순 학습·시험을 계산하고 있습니다…</div>';
  try{
   let pred=state.predictions.get(code);
   if(!pred){pred=await requestJson('/api/predict',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});state.predictions.set(code,pred);}
   out.innerHTML=`<h3>다음 거래일 상승 여부 추정</h3><p class="section-text">기준 거래일 ${esc(pred.last_trade_date||'미확인')}</p>
   ${resultsTable(pred.forecasts,[['모델','모델'],['기준 거래일','기준일'],['상승 추정 확률','상승 추정 확률'],['평가 Brier','시험 Brier']])}
   <h3>시험 구간 예측 성능</h3>${resultsTable(pred.summary,[['모델','모델'],['표본수','시험 표본'],['정확도','정확도'],['Brier','Brier'],['기준 Brier','기준 Brier']])}
   <div class="note">${esc(pred.method)}. Brier가 기준 모델보다 높을 경우 실제 예측 개선을 확인하지 못했습니다.</div>`;
  }catch(err){out.innerHTML=`<div class="note">${esc(err.message)}</div>`;}
  finally{b.disabled=false;}
 });
}
function renderBacktest(){
 const available=[...state.predictions.values()];
 $('#content').innerHTML=`${section('시계열 검증 결과','AI 예측에서 실제 모델을 실행한 종목의 시험 구간 지표')}
 ${available.length?available.map(p=>`<div class="card" style="margin-top:14px"><h3>${esc(p.name)}</h3>${resultsTable(p.summary,[['모델','모델'],['표본수','표본수'],['정확도','정확도'],['Brier','시험 Brier'],['기준 Brier','기준 Brier']])}</div>`).join(''):empty('AI 예측 메뉴에서 종목을 선택하고 모델을 실행하면 시험 구간 지표가 표시됩니다.')}`;
}
function renderData(){
 const all=registered();$('#content').innerHTML=`${section('데이터 센터','읽어온 실제 일별 시세 및 개인 CSV 출처를 확인합니다.')}${uploadBox()}
 ${section('불러온 자료',`${all.length}개 종목`)}
 ${all.length?`<div class="table-wrap"><table class="table"><thead><tr><th>종목</th><th>종류</th><th>시작일</th><th>마지막 거래일</th><th>행 수</th></tr></thead><tbody>${all.map(x=>`<tr><td>${esc(x.name)}</td><td>${esc(sourceLabel(x))}</td><td>${esc(x.prices[0].date)}</td><td>${esc(x.prices.at(-1).date)}</td><td>${x.prices.length}</td></tr>`).join('')}</tbody></table></div>`:empty('아직 불러온 데이터가 없습니다.')}
 <div style="margin-top:16px">${btn('업로드 CSV 기록만 지우기','clear-csv')}</div>
 <div class="note blue">서버의 가격 조회는 15분 캐시를 이용합니다. 날짜가 바뀌면 새 조회가 이루어지며, 시세 제공처가 장중 최신 일봉을 제공하지 않을 수 있습니다.</div>`;
 bindUpload();$('#clear-csv').addEventListener('click',()=>{if(confirm('업로드한 CSV를 초기화할까요?')){state.uploads.clear();state.analyzed.clear();render();}});
}
function render(){
 renderNav();renderWatchPanel();const label=PAGES.find(x=>x[0]===state.page)?.[1]||'홈 대시보드';
 $('#current-page').textContent=label;
 $('#page-heading').textContent=state.page==='home'?'시장의 흐름을 데이터로 읽다':label;
 $('#page-lead').textContent=state.page==='home'?'실제 종목 일봉 + 기사 근거 AI 분석 · 빠른 개인용 대시보드':'시장 데이터와 출처, 검증 범위를 구분하는 MARKET PULSE';
 ({home:renderHome,board:renderBoard,detail:renderDetail,anomaly:renderAnomaly,news:renderNews,ai:renderAI,backtest:renderBacktest,data:renderData}[state.page]||renderHome)();
}
async function start(){
 try{
   const [catalog,health]=await Promise.all([requestJson('/api/catalog'),requestJson('/api/health')]);
   if(!Array.isArray(catalog)||catalog.length!==30)throw Error('카탈로그 파일이 올바르지 않습니다.');
   state.catalog=catalog;state.aiConfigured=health.ai_configured;state.aiDailyRemaining=health.ai_calls_remaining_local??0;
   $('#ai-tag').textContent=health.ai_configured?`GroqCloud 설정됨 · 오늘 ${state.aiDailyRemaining}회 남음`:'AI 키 미설정';
   status(health.ai_configured?'개인 로컬 서버 연결 성공 · GroqCloud 키 설정됨 · 가격은 일봉 기준':'로컬 서버 연결 성공 · 기사 AI 분석은 GROQ_API_KEY를 설정하면 사용할 수 있습니다.','green');
   restoreWatchlist();bindWatchControls();render();loadDefault();
 }catch(err){status(`서버 상태 조회 실패: ${err.message}`);$('#content').textContent='서버에 연결하지 못했습니다. python app_server.py 실행 여부를 확인하세요.';}
}
start();

// Named exports are used by the offline UI smoke test; browser behavior is unchanged.
export {nav, render};
