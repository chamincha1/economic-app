// Real uploaded CSV data only. This module never synthesizes market prices.
export function parseCsv(text) {
  const source = String(text ?? '').replace(/^\uFEFF/, '');
  const header = source.split(/\r?\n/, 1)[0] ?? '';
  const candidates = [',', ';', '\t'];
  const delimiter = candidates.map(d => [d, header.split(d).length]).sort((a,b)=>b[1]-a[1])[0][0];
  const rows = [];
  let row = [], current = '', quoted = false;
  for (let i=0; i<source.length; i++) {
    const ch = source[i];
    if (ch === '"') {
      if (quoted && source[i+1] === '"') { current += '"'; i++; }
      else quoted = !quoted;
    } else if (ch===delimiter && !quoted) {
      row.push(current.trim()); current='';
    } else if ((ch==='\n' || ch==='\r') && !quoted) {
      if (ch==='\r' && source[i+1]==='\n') i++;
      row.push(current.trim()); current='';
      if (row.some(x=>x!=='')) rows.push(row);
      row=[];
    } else {
      current += ch;
    }
  }
  if (quoted) throw new Error('CSV의 따옴표가 닫히지 않았습니다.');
  row.push(current.trim());
  if (row.some(x=>x!=='')) rows.push(row);
  return rows;
}

function dateKey(value) {
  const str = String(value ?? '').trim();
  const m = str.match(/^(\d{4})[-./]?(\d{1,2})[-./]?(\d{1,2})(?:[ T].*)?$/);
  if (!m) return null;
  const y=Number(m[1]), month=Number(m[2]), day=Number(m[3]);
  const d=new Date(Date.UTC(y,month-1,day));
  if (d.getUTCFullYear()!==y || d.getUTCMonth()!==month-1 || d.getUTCDate()!==day) return null;
  return `${y}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
}
function numberVal(value) {
  if (value === undefined || value === null || String(value).trim() === '') return null;
  const n=Number(String(value).replace(/,/g,'').replace(/\s/g,'').replace(/원|주/g,''));
  return Number.isFinite(n)?n:null;
}
export function parsePriceCsv(text, filename, catalog=[]) {
  const rows=parseCsv(text);
  if (rows.length<3) throw new Error('헤더와 최소 2개 거래일 데이터가 필요합니다.');
  const headers=rows[0].map(x=>x.toLowerCase().replace(/[\s_()]/g,''));
  const pick=(names)=>headers.findIndex(x=>names.includes(x));
  const iDate=pick(['date','날짜','일자','거래일','datetime']);
  const iClose=pick(['close','adjclose','종가','수정종가','종가원']);
  const iVolume=pick(['volume','거래량','거래량주']);
  const iOpen=pick(['open','시가']);
  const iHigh=pick(['high','고가']);
  const iLow=pick(['low','저가']);
  if (iDate<0 || iClose<0) throw new Error('CSV에 Date/날짜와 Close/종가 열이 필요합니다.');
  const byDay=new Map();
  for (const row of rows.slice(1,50002)) {
    const date=dateKey(row[iDate]);
    const close=numberVal(row[iClose]);
    if (!date || close===null || close<=0) continue;
    const volume=iVolume>=0?numberVal(row[iVolume]):null;
    byDay.set(date,{date, close, volume:volume!==null&&volume>=0?volume:null,
      open:iOpen>=0?numberVal(row[iOpen]):null,
      high:iHigh>=0?numberVal(row[iHigh]):null,
      low:iLow>=0?numberVal(row[iLow]):null});
  }
  const prices=[...byDay.values()].sort((a,b)=>a.date.localeCompare(b.date));
  if (prices.length<2) throw new Error('유효한 거래일이 2개 이상 필요합니다. 날짜와 종가를 확인하세요.');
  const baseName=String(filename).replace(/\.csv$/i,'');
  const match=catalog.find(x=>baseName.includes(x.code)) || catalog.find(x=>baseName.toLowerCase().includes(x.name.toLowerCase()));
  return {code:match?.code||'', name:match?.name||baseName, sector:match?.sector||'사용자 업로드',
    filename, prices:prices.slice(-10000), source:'사용자가 업로드한 CSV'};
}
function avg(nums) { return nums.reduce((s,v)=>s+v,0)/nums.length; }
function stdev(nums) {
  if (nums.length<2) return null;
  const mean=avg(nums);
  return Math.sqrt(nums.reduce((s,v)=>s+(v-mean)**2,0)/(nums.length-1));
}
export function analyzeSeries(series, window=20, zLimit=2.5) {
  const p=series.prices;
  const last=p.at(-1), prev=p.at(-2);
  const returns=p.slice(1).map((v,i)=>({date:v.date, changePct:(v.close/p[i].close-1)*100}));
  const tailReturns=returns.slice(-window).map(v=>v.changePct);
  const vol=tailReturns.length>=2?stdev(tailReturns):null;
  const recent=p.slice(-Math.min(252,p.length));
  const volNums=p.slice(-20).map(v=>v.volume).filter(v=>v!==null);
  const anomalies=[];
  for(let i=window; i<returns.length; i++) {
    const history=returns.slice(i-window,i).map(v=>v.changePct);
    const standard=stdev(history);
    if (standard===null || standard===0) continue;
    const z=(returns[i].changePct-avg(history))/standard;
    if (Math.abs(z)>=zLimit) anomalies.push({date:returns[i].date, z, changePct:returns[i].changePct});
  }
  return {...series, last:last.close, lastDate:last.date,
    changePct:(last.close/prev.close-1)*100,
    change:last.close-prev.close,
    volume:last.volume,
    sma20:p.length>=20?avg(p.slice(-20).map(v=>v.close)):null,
    volatility:vol,
    high52:Math.max(...recent.map(v=>v.close)),
    low52:Math.min(...recent.map(v=>v.close)),
    avgVolume:volNums.length?avg(volNums):null,
    anomalies,
    periodChangePct:(last.close/p[0].close-1)*100};
}
export function keywordAnalysis(text) {
  // Explicitly rule-based, not a generative model or price forecast.
  const content=String(text??'').trim();
  if (content.length<30) throw new Error('분석할 기사 제목·본문을 30자 이상 붙여 넣어 주세요.');
  const positive=['호실적','성장','수주','흑자','상승','증가','확대','개선','투자','기술 개발','신제품','최대 실적'];
  const negative=['적자','하락','감소','부진','소송','리콜','규제','손실','불확실','지연','급락','악화','중단'];
  const hits=(terms)=>terms.filter(term=>content.includes(term));
  const pos=hits(positive), neg=hits(negative);
  const label=pos.length>neg.length?'긍정 표현 우세':neg.length>pos.length?'부정 표현 우세':'혼재 또는 중립';
  return {label,pos,neg,method:'공개된 키워드 목록과의 일치 여부만 확인한 규칙 기반 분석입니다. AI·주가 예측 결과가 아닙니다.'};
}
export const formatPrice = n => n==null||!Number.isFinite(n)?'—':n.toLocaleString('ko-KR',{maximumFractionDigits:2});
export const formatPct = n => n==null||!Number.isFinite(n)?'—':`${n>=0?'+':''}${n.toFixed(2)}%`;
