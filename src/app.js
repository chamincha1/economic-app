import {parsePriceCsv, analyzeSeries, keywordAnalysis, formatPrice, formatPct} from './analytics.js';
const PAGES=[
 ['home','홈 대시보드','◈'],['board','국내 시세 보드','▤'],['detail','종목 상세','⌕'],
 ['anomaly','급변 탐지','⚡'],['news','뉴스·공시','▣'],['ai','AI 예측','✦'],
 ['backtest','백테스트','◷'],['data','데이터 센터','⚙']
];
const state={page:'home',catalog:[],uploads:new Map(),selected:'',keyword:'',sector:'전체',lastNews:null};
const $=sel=>document.querySelector(sel);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const eNum=n=>n==null||!Number.isFinite(n)?'—':formatPrice(n);
const metric=(label,value,description='')=>`<div class="card"><div class="stat-label">${esc(label)}</div><div class="stat-value">${esc(value)}</div><div class="stat-footer">${esc(description)}</div></div>`;
const section=(title,sub='',more='')=>`<div class="section-head"><div><h2>${esc(title)}</h2><p>${esc(sub)}</p></div>${more}</div>`;
const empty=(msg,icon='◫')=>`<div class="empty"><div class="empty-icon">${icon}</div>${esc(msg)}</div>`;
const status=(message,kind='blue')=>{const el=$('#notice');el.className=`notice ${kind==='green'?'green':''}`;el.textContent=message;};
const loaded=()=>[...state.uploads.values()].map(x=>analyzeSeries(x));
const byCode=code=>loaded().find(x=>x.code===code);
const actionBtn=(label,id,primary=false)=>`<button class="btn ${primary?'primary':''}" id="${id}" type="button">${esc(label)}</button>`;
const uploadBox=()=>`<div class="upload-box"><strong>📁 실제 주가 CSV 가져오기</strong><p>Date(날짜), Close(종가) 열이 있는 CSV를 가져와 분석합니다.<br>프로그램은 가상 가격을 생성하지 않습니다.</p><label class="btn primary" for="csv-input">CSV 파일 선택 (여러 개 가능)</label><input id="csv-input" type="file" accept=".csv,text/csv" multiple /></div>`;
function bindUpload() {
  const input=$('#csv-input'); if(!input) return;
  input.addEventListener('change',async event=>{
    const files=[...event.target.files];let count=0,fail=[];
    for(const f of files) {
      if(f.size>8*1024*1024) {fail.push(`${f.name}: 8MB 초과`);continue;}
      try {
        const parsed=parsePriceCsv(await f.text(),f.name,state.catalog);
        state.uploads.set(parsed.filename,parsed);state.selected=parsed.filename;count++;
      }catch(err){fail.push(`${f.name}: ${err.message}`);}
    }
    if(count) status(`실제 CSV ${count}개를 불러왔습니다. 앱에 표시되는 가격은 사용자 CSV에서 계산한 결과입니다.`,'green');
    if(fail.length) alert('불러오지 못한 파일:\n'+fail.join('\n'));
    render();
  });
}
function choosePage(page){state.page=page;render();window.scrollTo({top:0,behavior:'smooth'});}
function renderNav(){
  const nav=$('#nav');nav.innerHTML=PAGES.map(([id,name,icon])=>`<button type="button" data-page="${id}" ${state.page===id?'aria-current="page"':''}><span class="nav-icon">${icon}</span>${name}</button>`).join('');
  nav.querySelectorAll('button[data-page]').forEach(b=>b.addEventListener('click',()=>choosePage(b.dataset.page)));
}
function chartSvg(series) {
  const prices=series.prices;
  if(prices.length<2)return '';
  const data=prices.length>300?prices.filter((_,i)=>i%Math.ceil(prices.length/300)===0||i===prices.length-1):prices;
  const width=920,height=295,pad=44;
  const lo=Math.min(...data.map(x=>x.close)),hi=Math.max(...data.map(x=>x.close));
  const span=Math.max(hi-lo,hi*.00001);
  const X=i=>pad+i*(width-pad*2)/(data.length-1);
  const Y=p=>height-pad-((p-lo)/span)*(height-pad*2);
  const path=data.map((v,i)=>`${i?'L':'M'}${X(i).toFixed(2)},${Y(v.close).toFixed(2)}`).join(' ');
  const final=data.at(-1).close,first=data[0].close;
  const color=final>=first?'#13a36f':'#e34c56';
  return `<svg class="chart" role="img" aria-label="${esc(series.name)}의 업로드된 주가 추이" viewBox="0 0 ${width} ${height}">
  <line x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}" stroke="#d9e4ef"/>
  <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${height-pad}" stroke="#d9e4ef"/>
  <path d="${path}" stroke="${color}" fill="none" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>
  <text x="${pad+5}" y="${pad-12}" fill="#7c8b9e" font-size="14">${esc(formatPrice(hi))}</text>
  <text x="${pad+5}" y="${height-pad-9}" fill="#7c8b9e" font-size="14">${esc(formatPrice(lo))}</text>
  <text x="${pad}" y="${height-9}" fill="#7c8b9e" font-size="14">${esc(data[0].date)}</text>
  <text x="${width-pad}" y="${height-9}" text-anchor="end" fill="#7c8b9e" font-size="14">${esc(data.at(-1).date)}</text></svg>`;
}
function stockCard(item) {
 const row=byCode(item.code);
 return `<div class="stock-mini" data-stock="${esc(item.code)}"><div class="stock-title">${esc(item.name)}</div><div class="stock-symbol">${esc(item.code)} · ${esc(item.sector)}</div>
 <div class="stock-price">${row?formatPrice(row.last)+'원':'—'}</div>
 <div class="change ${row?(row.changePct>=0?'up':'down'):'muted'}">${row?formatPct(row.changePct):'CSV 미등록'}</div>
 <div class="card-caption">${row?`${esc(row.lastDate)} · 사용자 CSV 종가`:'실시간 시세를 조회하지 않습니다'}</div></div>`;
}
function bindStockCards(){document.querySelectorAll('[data-stock]').forEach(el=>el.addEventListener('click',()=>{
 const item=state.catalog.find(x=>x.code===el.dataset.stock);
 const match=loaded().find(x=>x.code===item.code);
 if(match){state.selected=match.filename;choosePage('detail');}
 else{status(`${item.name}의 데이터가 없습니다. ${item.code}.csv 파일을 업로드하면 상세 분석을 볼 수 있습니다.`);}
}));}
function renderHome(){
 const list=loaded(),valid=list.length;
 const av=valid?list.reduce((s,x)=>s+x.changePct,0)/valid:null;
 const totalAnomalies=list.reduce((s,x)=>s+x.anomalies.length,0);
 const lastDate=valid?list.map(x=>x.lastDate).sort().at(-1):null;
 $('#content').innerHTML=`
 ${section('데이터 현황','직접 업로드한 CSV 자료에 기반한 결과입니다.')}
 <div class="grid grid-4">
 ${metric('불러온 종목',`${valid}개`,'직접 가져온 CSV 기준')}
 ${metric('평균 일별 변동',av===null?'—':formatPct(av),'마지막 두 거래일 비교')}
 ${metric('가격 급변 탐지',valid?`${totalAnomalies}건`:'—','직전 20거래일 대비 |Z| ≥ 2.5')}
 ${metric('최근 데이터 날짜',lastDate||'—','업로드된 데이터의 마지막 거래일')}</div>
 ${section('관심 기업','기본 표시 종목 6개 · 가격은 CSV를 업로드한 기업에 한해 표시')}
 <div class="stock-grid">${state.catalog.slice(0,6).map(stockCard).join('')}</div>
 ${section('데이터 가져오기','종목코드가 파일명에 포함되면 자동으로 기업을 인식합니다. 예: 005930.csv')}
 ${uploadBox()}
 <div class="note blue"><strong>실시간 시세에 관하여</strong><br>이 웹 미리보기는 외부 주가 API를 임의로 호출하지 않습니다. 원본 FinanceDataReader·KIS 기반 실시간/과거 데이터 기능은 함께 보존한 Python Streamlit 앱에서 이용할 수 있습니다.</div>`;
 bindUpload();bindStockCards();
}
function renderBoard(){
 const sectors=['전체',...new Set(state.catalog.map(x=>x.sector))];
 const matched=state.catalog.filter(x=>(state.sector==='전체'||x.sector===state.sector)&&(`${x.name} ${x.code}`.toLowerCase().includes(state.keyword.toLowerCase())));
 $('#content').innerHTML=`
 ${section('국내 30개 기업','원본 stock_catalog.py에 들어 있는 실제 종목 카탈로그 · 시세는 업로드된 자료만 표시')}
 <div class="control-bar"><input class="field" id="board-search" placeholder="기업명 또는 6자리 종목코드" value="${esc(state.keyword)}" aria-label="기업 검색"/>
 <select class="field" id="board-sector" aria-label="업종 선택">${sectors.map(s=>`<option ${s===state.sector?'selected':''}>${esc(s)}</option>`).join('')}</select></div>
 <div class="table-wrap"><table class="table"><thead><tr><th>종목명</th><th>종목코드</th><th>업종</th><th>최근 종가</th><th>전일 대비</th><th>기준 거래일</th></tr></thead><tbody>
 ${matched.map(x=>{const p=byCode(x.code);return `<tr data-stock="${esc(x.code)}" tabindex="0"><td class="name">${esc(x.name)}</td><td>${esc(x.code)}</td><td>${esc(x.sector)}</td><td>${p?formatPrice(p.last)+'원':'—'}</td><td class="${p?(p.changePct>=0?'up':'down'):'muted'}">${p?formatPct(p.changePct):'CSV 미등록'}</td><td>${p?esc(p.lastDate):'—'}</td></tr>`;}).join('')}
 </tbody></table></div><p class="section-text">표시된 종목은 30개 카탈로그이며 30개 기업의 실시간 시세를 갖고 있다는 뜻이 아닙니다.</p>`;
 $('#board-search').addEventListener('input',e=>{state.keyword=e.target.value;renderBoard(); const el=$('#board-search');el.focus();el.setSelectionRange(el.value.length,el.value.length);});
 $('#board-sector').addEventListener('change',e=>{state.sector=e.target.value;renderBoard();});
 bindStockCards();
 document.querySelectorAll('tr[data-stock]').forEach(el=>el.addEventListener('keydown',e=>{if(e.key==='Enter')el.click();}));
}
function renderDetail(){
 const all=loaded(); const chosen=all.find(x=>x.filename===state.selected)||all[0];
 if(!chosen){$('#content').innerHTML=section('종목 상세 분석','실제 주가 CSV를 업로드한 뒤 이용할 수 있습니다.')+uploadBox();bindUpload();return;}
 const select=`<select class="field" id="detail-choice" aria-label="분석 종목 선택">${all.map(x=>`<option value="${esc(x.filename)}" ${x.filename===chosen.filename?'selected':''}>${esc(x.name)} (${esc(x.code||'CSV')})</option>`).join('')}</select>`;
 $('#content').innerHTML=`${section('종목 상세',`${chosen.name} · ${chosen.lastDate} 거래일 종가 · ${chosen.filename}`,select)}
 <div class="grid grid-4">${metric('마지막 종가',formatPrice(chosen.last)+'원','실시간 체결가 아님')}${metric('전일 대비',formatPct(chosen.changePct),`${formatPrice(chosen.change)}원`)}${metric('20일 이동평균',chosen.sma20===null?'—':formatPrice(chosen.sma20)+'원','최근 20개 거래일 평균')}${metric('20일 변동성',chosen.volatility===null?'—':`${chosen.volatility.toFixed(2)}%p`,'일일 수익률 표준편차')}</div>
 ${section('주가 흐름','실제 업로드된 날짜별 종가를 연결한 선 그래프')}
 <div class="card">${chartSvg(chosen)}<div class="legend"><span style="color:#0caa77">상승 흐름</span><span style="color:#e34c56">하락 흐름</span></div></div>
 ${section('추가 통계','52주 범위는 확보된 최근 최대 252거래일 기준')}
 <div class="grid grid-3">${metric('최근 52주 최고',formatPrice(chosen.high52)+'원')}${metric('최근 52주 최저',formatPrice(chosen.low52)+'원')}${metric('기간 전체 등락률',formatPct(chosen.periodChangePct),`${chosen.prices.length}개 가격 기록`)}</div>`;
 $('#detail-choice').addEventListener('change',e=>{state.selected=e.target.value;renderDetail();});
}
function renderAnomaly(){
 const rows=loaded().flatMap(x=>x.anomalies.map(e=>({...e,name:x.name}))).sort((a,b)=>b.date.localeCompare(a.date)).slice(0,200);
 $('#content').innerHTML=`${section('가격 급변 탐지', '과거 20일 수익률 대비 통계적 급변 탐지 · 미래 예측이나 위험 등급이 아닙니다.')}
 ${rows.length?`<div class="table-wrap"><table class="table"><thead><tr><th>종목</th><th>날짜</th><th>일일 수익률</th><th>Z 점수</th></tr></thead><tbody>${rows.map(x=>`<tr><td class="name">${esc(x.name)}</td><td>${esc(x.date)}</td><td class="${x.changePct>=0?'up':'down'}">${formatPct(x.changePct)}</td><td>${x.z.toFixed(2)}</td></tr>`).join('')}</tbody></table></div>`:empty(state.uploads.size?'선택한 CSV 기간에 기준에 맞는 급변 이벤트가 없습니다.':'먼저 CSV를 업로드하면 실제 데이터에서 급변 이벤트를 계산합니다.')}
 <div class="note">평균과 표준편차는 해당 날짜 이전의 거래일만 사용합니다. 값이 없는 경우는 표시하지 않습니다.</div>`;
}
function renderNews(){
 $('#content').innerHTML=`${section('기사 링크 · 뉴스 분석','URL 저장과 기사 텍스트 키워드 분석. 가짜 뉴스·가짜 LLM 결과를 생성하지 않습니다.')}
 <div class="note blue">Google AI Studio 웹 미리보기에는 원본 Python 뉴스 수집기와 AI 서버가 실행되지 않습니다. 링크를 직접 열어 공개 기사 텍스트를 복사해 넣으면 <strong>규칙 기반 키워드</strong>로 분석합니다. Groq/Grok AI를 실제 호출했다고 표시하지 않습니다.</div>
 <div class="card"><form id="news-form"><label class="field-label" for="article-url">기사 URL (선택)</label><input id="article-url" type="url" class="field" placeholder="https://example.com/news" value="${esc(state.lastNews?.url||'')}" />
 <label class="field-label" for="article-text" style="margin-top:16px">기사 제목과 공개 본문·요약 (30자 이상)</label>
 <textarea id="article-text" class="field" rows="7" placeholder="뉴스 사이트에서 읽은 기사 제목과 내용을 붙여 넣어 주세요.">${esc(state.lastNews?.text||'')}</textarea>
 <div class="form-row" style="margin-top:13px"><button type="submit" class="btn primary">키워드 요인 분석</button><span class="muted" style="font-size:11px">분석은 브라우저 안에서 실행 · 외부 AI API 요청 없음</span></div></form>
 <div id="news-output"></div></div>`;
 $('#news-form').addEventListener('submit',e=>{
   e.preventDefault();const txt=$('#article-text').value;const url=$('#article-url').value.trim();
   let safeUrl='';
   if(url){try{const u=new URL(url); if(!['http:','https:'].includes(u.protocol))throw Error(); safeUrl=u.href;}catch{alert('http 또는 https로 시작하는 올바른 기사 주소를 입력하세요.');return;}}
   try {
     const result=keywordAnalysis(txt);state.lastNews={url:safeUrl,text:txt};
     const link=safeUrl?`<a href="${esc(safeUrl)}" target="_blank" rel="noopener noreferrer">원문 링크 열기</a>`:'';
     $('#news-output').innerHTML=`<div class="analysis-result"><strong>${esc(result.label)}</strong><p>${esc(result.method)}</p>
      <div><b>긍정 키워드</b><div>${result.pos.length?result.pos.map(t=>`<span class="mark">${esc(t)}</span>`).join(''):'해당 표현 없음'}</div></div>
      <div style="margin-top:10px"><b>부정 키워드</b><div>${result.neg.length?result.neg.map(t=>`<span class="mark bad">${esc(t)}</span>`).join(''):'해당 표현 없음'}</div></div>
      <p>${link}</p></div>`;
   } catch(err){$('#news-output').innerHTML=`<div class="note">${esc(err.message)}</div>`;}
 });
}
function renderAI(){
 $('#content').innerHTML=`${section('AI 예측 · 모델 연결 상태','기존 Python AI 예측 기능을 보존했습니다.')}
 <div class="card"><h3>Python 분석 엔진이 필요합니다</h3><p class="section-text">원본 MARKET PULSE의 scikit-learn 예측 모델과 뉴스 LLM 분석기는 Python 기반입니다. 이번 웹 미리보기는 JavaScript로 실행되므로 원본 Python 엔진을 가짜로 시뮬레이션하지 않습니다.</p>
 <div class="note blue"><strong>원본 분석 기능 실행</strong><br>Python 개발 환경에서 <code>python -m pip install -r requirements.txt</code> 다음 <code>python -m streamlit run app.py</code>를 실행하세요. API 키는 프로젝트 비공개 Secrets에만 보관하세요.</div></div>`;
}
function renderBacktest(){
 $('#content').innerHTML=`${section('시계열 백테스트','백테스트 결과는 학습·검증 구분이 있는 실제 모델에서만 계산합니다.')}
 <div class="card"><h3>원본 백테스트 엔진 보존</h3><p class="section-text">기존 <code>backtesting.py</code>, <code>prediction_model.py</code> 파일을 수정하거나 제거하지 않았습니다. 임의의 수익률·정확도를 표시하지 않으며, 이 JavaScript 웹 버전에서는 실행하지 않습니다.</p></div>`;
}
function renderData(){
 const items=[...state.uploads.values()];
 $('#content').innerHTML=`${section('데이터 센터','로컬 브라우저에서 처리하는 실제 CSV · 업로드 데이터는 외부 서버에 전송되지 않습니다.')}
 ${uploadBox()}
 ${section('불러온 파일',`${items.length}개 CSV 기록`)}
 ${items.length?`<div class="table-wrap"><table class="table"><thead><tr><th>파일</th><th>종목</th><th>첫 거래일</th><th>마지막 거래일</th><th>행 수</th></tr></thead><tbody>${items.map(x=>`<tr><td>${esc(x.filename)}</td><td>${esc(x.name)}</td><td>${esc(x.prices[0].date)}</td><td>${esc(x.prices.at(-1).date)}</td><td>${x.prices.length}</td></tr>`).join('')}</tbody></table></div>`:empty('아직 불러온 CSV가 없습니다.')}
 <div style="margin-top:16px">${actionBtn('불러온 CSV 초기화','clear-csv')}</div>
 ${section('30개 기업 카탈로그','시세 데이터 자체가 아닌 기업명·코드·업종 목록입니다.')}
 <div class="card"><div class="section-text">CSV 파일명을 <code>005930.csv</code>처럼 종목코드로 저장하면 해당 기업에 매칭됩니다. 이름이나 종목코드가 맞지 않는 파일은 사용자 제공 파일명으로 표시됩니다.</div></div>`;
 bindUpload();
 $('#clear-csv').addEventListener('click',()=>{if(confirm('브라우저에서 불러온 CSV 데이터를 초기화할까요?')){state.uploads.clear();state.selected='';status('브라우저의 CSV 분석 자료가 초기화됐습니다.');render();}});
}
function render(){
 renderNav();
 const label=PAGES.find(x=>x[0]===state.page)?.[1]||'홈 대시보드';
 $('#current-page').textContent=label;
 $('#page-heading').textContent=state.page==='home'?'시장의 흐름을 데이터로 읽다':label;
 $('#page-lead').textContent=state.page==='home'?'실제 업로드 데이터 기반 · 30개 종목 카탈로그 · 빠르고 안전한 웹 미리보기':'실제 데이터만 표시하고 분석 출처를 구분하는 MARKET PULSE';
 ({home:renderHome,board:renderBoard,detail:renderDetail,anomaly:renderAnomaly,news:renderNews,ai:renderAI,backtest:renderBacktest,data:renderData}[state.page]||renderHome)();
}
async function start(){
 try {
   const response=await fetch('/assets/catalog.json');
   if(!response.ok) throw new Error(`HTTP ${response.status}`);
   state.catalog=await response.json();
   if(!Array.isArray(state.catalog)||state.catalog.length!==30) throw new Error('종목 목록이 올바르지 않습니다.');
   render();
 } catch(err){
   $('#content').textContent=`종목 목록을 읽지 못했습니다: ${err.message}`;
   status('파일 구성이 손상되었습니다. 전체 복구 ZIP에서 다시 추출하세요.');
 }
}
start();
