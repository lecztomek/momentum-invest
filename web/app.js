
/* Dane przychodza z plikow JSON w docs/data/ - to jest kontrakt miedzy
   pipeline'em (GitHub Actions zapisuje te pliki) a ta strona (tylko je czyta).
   Modul + top-level await: reszta pliku wykonuje sie dopiero po wczytaniu. */
let SIG,PERF,PRC,PORT;
try{
  [SIG,PERF,PRC,PORT]=await Promise.all(["signals","performance","prices","portfolio"]
    .map(f=>fetch(`web/data/${f}.json`).then(r=>{if(!r.ok)throw new Error(f+".json: HTTP "+r.status);return r.json()})));
}catch(err){
  document.body.innerHTML='<div class="fatal"><b>Nie udalo sie wczytac danych.</b>'
    +'<p>'+String(err.message||err)+'</p><p>Strona czyta pliki przez fetch, wiec musi byc '
    +'serwowana przez HTTP. Otworz ja przez GitHub Pages albo lokalnie: '
    +'<code>python3 -m http.server</code> w katalogu glownym repo.</p></div>';
  throw err;
}
const SIGNALS=SIG.signals, HIST=SIG.history, RANK=SIG.ranking, CAN_VT=SIG.canary.vt, CAN_XLK=SIG.canary.xlk,
      ORDER=SIG.universe, ROLE=SIG.roles;
const CAPITAL=PORT.capital, HOLDINGS=PORT.holdings, MONTHS=PORT.months, VALUE=PORT.value,
      PAID=PORT.paid, MIX=PORT.mix, KLASY=PORT.classes;
const RET=PERF.monthly;
const INSTR=PRC.instruments, BASE=PRC.base, FEED=PRC.feed;
const COMPO=SIG.composition;

/* Wlasne grupowanie: pl-PL nie grupuje liczb czterocyfrowych (minimumGroupingDigits=2),
   wiec "7640" staloby obok "197 640" i kolumna liczb przestawalaby sie zgadzac wzrokowo. */
const zl=n=>String(Math.round(Math.abs(n))).replace(/\B(?=(\d{3})+(?!\d))/g," ");
const pc=n=>(n*100).toFixed(1).replace(".",",")+"%";
const sg=n=>(n>=0?"+":"−")+Math.abs(n).toFixed(1).replace(".",",");
const sg2=n=>(n>=0?"+":"−")+Math.abs(n).toFixed(2).replace(".",",");
const px=n=>n.toFixed(n<20?4:2).replace(".",",");
const CSS=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const esc=s=>String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const MN=["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paź","lis","gru"];
const mLbl=m=>MN[+m.slice(5)-1]+" "+m.slice(2,4);

/* ============ daty transz: pierwsza sesja N-tego lub pozniej ============ */
function ruleDate(y,m,day){
  const d=new Date(Date.UTC(y,m,day));
  while(d.getUTCDay()===0||d.getUTCDay()===6||
    (d.getUTCMonth()===0&&d.getUTCDate()===1)||(d.getUTCMonth()===11&&(d.getUTCDate()===25||d.getUTCDate()===26)))
    d.setUTCDate(d.getUTCDate()+1);
  return d.toISOString().slice(0,10)}
function lastDates(day,n,endY,endM){
  const out=[];let y=endY,m=endM;
  for(let i=0;i<n;i++){out.unshift(ruleDate(y,m,day));m--;if(m<0){m=11;y--}}
  return out}

/* ============ ceny: deterministyczny szereg wstecz od ceny biezacej ============ */
function mkPrices(day,endY,endM){
  const dates=lastDates(day,13,endY,endM),out={};
  let s=day*7919;const rnd=()=>{s=(s*1103515245+12345)&0x7fffffff;return s/0x7fffffff};
  for(const[t]of INSTR){
    const a=[BASE[t]*(day===10?1:0.982)];
    for(let i=1;i<dates.length;i++)a.unshift(a[0]/(1+(rnd()-.46)*.09));
    out[t]=a.map(v=>+v.toFixed(v<20?4:2))}
  /* w danych demo jeden zastoj, zeby bylo widac po co jest kontrola */
  if(day===10)out.CMOD[12]=out.CMOD[11];
  return{dates,px:out}}
const PRICES={10:mkPrices(10,2026,11),25:mkPrices(25,2026,10)};
let PTAB="10";

/* ============ skladanie transz ============ */
function tranche(sig,share){
  const kB=CAPITAL.best17*share,kG=CAPITAL.gpm*share,out={};let uB=0,uG=0;
  for(const[t,w]of Object.entries(sig.best17.weights)){out[t]=(out[t]||0)+kB*w;uB+=w}
  for(const[t,w]of Object.entries(sig.gpm.weights)){out[t]=(out[t]||0)+kG*w;uG+=w}
  const cB=kB*Math.max(0,1-uB),cG=kG*Math.max(0,1-uG);out.GOTOWKA=cB+cG;
  return{out,kB,kG,cashB:cB,cashG:cG,
    best17:Object.fromEntries(Object.entries(sig.best17.weights).map(([t,w])=>[t,kB*w])),
    gpm:Object.fromEntries(Object.entries(sig.gpm.weights).map(([t,w])=>[t,kG*w]))}}
const T10=tranche(SIGNALS[0],CAPITAL.split10),T25=tranche(SIGNALS[1],1-CAPITAL.split10);
const TOTAL=CAPITAL.best17+CAPITAL.gpm;
const COMBINED={};
for(const t of[...ORDER,"GOTOWKA"]){const v=(T10.out[t]||0)+(T25.out[t]||0);if(v>.5)COMBINED[t]=v}
const LEG={best17:{},gpm:{}};
for(const T of[T10,T25]){
  for(const[t,v]of Object.entries(T.best17))LEG.best17[t]=(LEG.best17[t]||0)+v;
  for(const[t,v]of Object.entries(T.gpm))LEG.gpm[t]=(LEG.gpm[t]||0)+v;
  LEG.best17.GOTOWKA=(LEG.best17.GOTOWKA||0)+T.cashB;LEG.gpm.GOTOWKA=(LEG.gpm.GOTOWKA||0)+T.cashG}

const SETUPS={
  rozdzielnie:{label:"2 konta, noga na konto",accounts:[
    {name:"LYNX",alloc:{best17:1,gpm:0},value:99180,pln:4.15,usd:-.91},
    {name:"XTB",alloc:{best17:0,gpm:1},value:98460,pln:2.28,usd:-2.77}]},
  jedno:{label:"jedno konto",accounts:[
    {name:"Konto główne",alloc:{best17:1,gpm:1},value:197640,pln:3.21,usd:-1.84}]},
  porowno:{label:"2 konta po równo",accounts:[
    {name:"Broker A",alloc:{best17:.5,gpm:.5},value:99400,pln:3.30,usd:-1.75},
    {name:"Broker B",alloc:{best17:.5,gpm:.5},value:98240,pln:3.12,usd:-1.93}]}};
let SETUP="rozdzielnie";
const accComp=a=>{const o={};
  for(const leg of["best17","gpm"]){const f=a.alloc[leg]||0;if(!f)continue;
    for(const[t,v]of Object.entries(LEG[leg]))o[t]=(o[t]||0)+v*f}
  return Object.fromEntries(Object.entries(o).filter(([,v])=>v>.5).sort((x,y)=>y[1]-x[1]))};
const accTarget=a=>(a.alloc.best17||0)*CAPITAL.best17+(a.alloc.gpm||0)*CAPITAL.gpm;
const accLegs=a=>["best17","gpm"].filter(l=>a.alloc[l]>0)
  .map(l=>(a.alloc[l]===1?"":Math.round(a.alloc[l]*100)+"% ")+(l==="best17"?"BEST17":"GPM")).join(" + ");
const fillSel=()=>document.querySelectorAll(".setupSel").forEach(e=>e.innerHTML=
  Object.entries(SETUPS).map(([k,s])=>`<button type="button" data-setup="${k}" aria-pressed="${k===SETUP}">${s.label}</button>`).join(""));
document.addEventListener("click",e=>{
  const b=e.target.closest("[data-setup]");if(!b)return;
  SETUP=b.dataset.setup;fillSel();renderAccounts();fillAccSelect();renderPulpit();
  const m=document.querySelector("#segS button[aria-pressed='true']");if(m)renderSklad(m.dataset.s)});

/* ============ statystyki ============ */
const SER=[];
for(const y of Object.keys(RET).sort())RET[y].forEach((r,i)=>{if(r!=null)SER.push({y:+y,m:i,r})});
const STAT=(()=>{
  let eq=1,peak=1,mdd=0,uw=0,maxuw=0,wins=0;const curve=[];
  for(const p of SER){eq*=1+p.r/100;peak=Math.max(peak,eq);const d=eq/peak-1;mdd=Math.min(mdd,d);
    uw=d<-1e-9?uw+1:0;maxuw=Math.max(maxuw,uw);if(p.r>0)wins++;curve.push({...p,eq,dd:d*100})}
  const yrs=SER.length/12,cagr=(Math.pow(eq,1/yrs)-1)*100;
  const years={};for(const p of SER)years[p.y]=(years[p.y]||1)*(1+p.r/100);
  const yl=Object.entries(years).map(([y,v])=>[+y,(v-1)*100]);
  return{eq,cagr,mdd:mdd*100,maxuw,win:wins/SER.length*100,curve,yl,
    calmar:cagr/Math.abs(mdd*100),best:Math.max(...yl.map(a=>a[1])),worst:Math.min(...yl.map(a=>a[1]))}})();

/* ============ wykresy ============ */
const charts=[];const chart=(id,draw)=>charts.push({id,draw});
function mount(c){
  const el=document.getElementById(c.id);if(!el)return;
  const sec=el.closest("section");if(sec&&sec.hidden)return;
  const w=Math.max(260,el.clientWidth||300);
  el.innerHTML='<div class="tip"></div>'+c.draw(w);
  const tip=el.querySelector(".tip"),svg=el.querySelector("svg");
  if(svg&&svg.dataset.hover)wire(el,svg,tip,JSON.parse(svg.dataset.hover))}
const renderAll=()=>charts.forEach(mount);
let rt;addEventListener("resize",()=>{clearTimeout(rt);rt=setTimeout(()=>{renderAll();if(!MXN)renderMatrix()},120)});
function wire(box,svg,tip,H){
  const move=e=>{
    const r=svg.getBoundingClientRect(),x=(e.clientX-r.left)/r.width*H.W,y=(e.clientY-r.top)/r.height*H.H;
    let best=null,bd=1e9;
    for(const h of H.hit){
      const d=(h.y0==null)?Math.abs(x-h.cx):((x>=h.x0&&x<=h.x1&&y>=h.y0&&y<=h.y1)?0:1e9);
      if(d<bd){bd=d;best=h}}
    if(!best||bd>H.max){tip.dataset.on="0";return}
    tip.innerHTML=best.html;tip.dataset.on="1";
    const br=box.getBoundingClientRect();
    let p=e.clientX-br.left+14;if(p+tip.offsetWidth>br.width-4)p=e.clientX-br.left-tip.offsetWidth-14;
    tip.style.left=Math.max(4,p)+"px";
    tip.style.top=Math.max(4,Math.min(e.clientY-br.top-10,br.height-tip.offsetHeight-4))+"px";
    const cl=svg.querySelector(".xh");if(cl&&best.cx!=null){cl.setAttribute("x1",best.cx);cl.setAttribute("x2",best.cx);cl.style.opacity="1"}};
  svg.addEventListener("pointermove",move);svg.addEventListener("pointerdown",move);
  svg.addEventListener("pointerleave",()=>{tip.dataset.on="0";const cl=svg.querySelector(".xh");if(cl)cl.style.opacity="0"})}
const HV=o=>JSON.stringify(o).replace(/'/g,"&apos;");
const FS=w=>w<460?11:12.5;

chart("c-equity",W=>{
  const nr=W<460,H=nr?210:250,L=nr?48:58,R=10,T=12,B=28,n=MONTHS.length,lo=95000,hi=205000,f=FS(W);
  const X=i=>L+(W-L-R)*i/(n-1),Y=v=>T+(H-T-B)*(1-(v-lo)/(hi-lo));
  const p=a=>a.map((v,i)=>(i?"L":"M")+X(i).toFixed(1)+" "+Y(v).toFixed(1)).join(" ");
  let g="";for(let v=100000;v<=200000;v+=25000)g+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${CSS("--line")}"/><text x="${L-8}" y="${Y(v)+4}" text-anchor="end" fill="${CSS("--faint")}" font-size="${f}">${v/1000}k</text>`;
  let xl="";for(let i=0;i<n;i+=nr?6:4)xl+=`<text x="${X(i)}" y="${H-8}" text-anchor="middle" fill="${CSS("--faint")}" font-size="${f}">${mLbl(MONTHS[i])}</text>`;
  const hit=MONTHS.map((m,i)=>({cx:X(i),html:`<div class="th">${mLbl(m)}</div>
    <div class="tr"><span class="sw" style="background:${CSS("--accent")}"></span>Wartość<span class="tv">${zl(VALUE[i])}</span></div>
    <div class="tr"><span class="sw" style="background:${CSS("--muted")}"></span>Wpłacone<span class="tv">${zl(PAID[i])}</span></div>
    <div class="tr" style="color:${VALUE[i]>=PAID[i]?CSS("--pos"):CSS("--neg")}"><span class="sw" style="background:transparent"></span>Wynik<span class="tv">${sg((VALUE[i]/PAID[i]-1)*100)}%</span></div>`}));
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Wartość portfela i wpłacony kapitał" data-hover='${HV({W,H,max:(W-L-R)/n,hit})}'>
    <defs><linearGradient id="eg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${CSS("--accent")}" stop-opacity=".3"/><stop offset="1" stop-color="${CSS("--accent")}" stop-opacity="0"/></linearGradient></defs>
    ${g}${xl}<line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="${CSS("--line-strong")}" style="opacity:0"/>
    <path d="${p(VALUE)} L${X(n-1)} ${Y(lo)} L${X(0)} ${Y(lo)} Z" fill="url(#eg)"/>
    <path d="${p(PAID)}" fill="none" stroke="${CSS("--muted")}" stroke-width="2.5" stroke-dasharray="6 5"/>
    <path d="${p(VALUE)}" fill="none" stroke="${CSS("--accent")}" stroke-width="2.5" stroke-linejoin="round"/>
    <circle cx="${X(n-1)}" cy="${Y(VALUE[n-1])}" r="5" fill="${CSS("--accent")}" stroke="${CSS("--surface")}" stroke-width="2.5"/></svg>`});

chart("c-mix",W=>{
  const nr=W<460,H=nr?220:260,L=nr?34:40,R=10,T=12,B=28,n=MONTHS.length,f=FS(W);
  const X=i=>L+(W-L-R)*i/(n-1),Y=p=>T+(H-T-B)*(1-p/100);
  const cum=MIX.map(r=>{let a=0;return r.map(v=>a+=v)});
  let paths="";
  for(let s=KLASY.length-1;s>=0;s--){
    const d=cum.map((r,i)=>(i?"L":"M")+X(i).toFixed(1)+" "+Y(r[s]).toFixed(1)).join(" ")+` L${X(n-1)} ${Y(0)} L${X(0)} ${Y(0)} Z`;
    paths+=`<path d="${d}" fill="${CSS(KLASY[s][1])}" stroke="${CSS("--surface")}" stroke-width="2" stroke-linejoin="round"/>`}
  let g="";for(let p=0;p<=100;p+=25)g+=`<text x="${L-7}" y="${Y(p)+4}" text-anchor="end" fill="${CSS("--faint")}" font-size="${f}">${p}</text>`;
  let xl="";for(let i=0;i<n;i+=nr?6:4)xl+=`<text x="${X(i)}" y="${H-8}" text-anchor="middle" fill="${CSS("--faint")}" font-size="${f}">${mLbl(MONTHS[i])}</text>`;
  const hit=MONTHS.map((m,i)=>({cx:X(i),html:`<div class="th">${mLbl(m)}</div>`+KLASY.map((k,s)=>MIX[i][s]?
    `<div class="tr"><span class="sw" style="background:${CSS(k[1])}"></span>${k[0]}<span class="tv">${MIX[i][s]}%</span></div>`:"").join("")}));
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Udział klas aktywów w czasie" data-hover='${HV({W,H,max:(W-L-R)/n,hit})}'>
    ${g}${paths}<line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="${CSS("--fg")}" style="opacity:0"/>${xl}</svg>`});

chart("c-dd",W=>{
  const nr=W<460,H=nr?190:225,L=nr?40:48,R=10,T=12,B=28,c=STAT.curve,n=c.length,f=FS(W);
  const lo=Math.floor(STAT.mdd/5)*5-2;
  const X=i=>L+(W-L-R)*i/(n-1),Y=v=>T+(H-T-B)*(1-(v-lo)/(0-lo));
  const d=c.map((p,i)=>(i?"L":"M")+X(i).toFixed(1)+" "+Y(p.dd).toFixed(1)).join(" ");
  let g="";for(let v=0;v>=lo;v-=5)g+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${CSS("--line")}"/><text x="${L-7}" y="${Y(v)+4}" text-anchor="end" fill="${CSS("--faint")}" font-size="${f}">${v}%</text>`;
  let xl="";for(let i=0;i<n;i+=nr?24:12)xl+=`<text x="${X(i)}" y="${H-8}" text-anchor="middle" fill="${CSS("--faint")}" font-size="${f}">${c[i].y}</text>`;
  const mi=c.reduce((b,p,i)=>p.dd<c[b].dd?i:b,0);
  const hit=c.map((p,i)=>({cx:X(i),html:`<div class="th">${MN[p.m]} ${p.y}</div>
    <div class="tr">Obsunięcie<span class="tv" style="color:${CSS("--neg")}">${p.dd.toFixed(1).replace(".",",")}%</span></div>
    <div class="tr">Miesiąc<span class="tv" style="color:${p.r>=0?CSS("--pos"):CSS("--neg")}">${sg(p.r)}%</span></div>`}));
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Obsunięcie od szczytu" data-hover='${HV({W,H,max:(W-L-R)/n,hit})}'>
    <defs><linearGradient id="dg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${CSS("--neg")}" stop-opacity="0"/><stop offset="1" stop-color="${CSS("--neg")}" stop-opacity=".35"/></linearGradient></defs>
    ${g}${xl}<path d="${d} L${X(n-1)} ${Y(0)} L${X(0)} ${Y(0)} Z" fill="url(#dg)"/>
    <path d="${d}" fill="none" stroke="${CSS("--neg")}" stroke-width="2.5" stroke-linejoin="round"/>
    <line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="${CSS("--line-strong")}" style="opacity:0"/>
    <circle cx="${X(mi)}" cy="${Y(c[mi].dd)}" r="5" fill="${CSS("--neg")}" stroke="${CSS("--surface")}" stroke-width="2.5"/>
    <text x="${X(mi)}" y="${Y(c[mi].dd)+19}" text-anchor="middle" fill="${CSS("--neg")}" font-size="${f+1}" font-weight="700">MaxDD ${STAT.mdd.toFixed(1).replace(".",",")}%</text></svg>`});

chart("c-yr",W=>{
  const yl=STAT.yl,n=yl.length,H=W<460?195:215,T=16,B=30,L=36,R=10,f=FS(W);
  const mx=Math.max(...yl.map(a=>Math.abs(a[1])))*1.25;
  const bw=(W-L-R)/n*.6,X=i=>L+(W-L-R)*(i+.5)/n,Y=v=>T+(H-T-B)*(1-(v+mx)/(2*mx));
  let g=`<line x1="${L}" x2="${W-R}" y1="${Y(0)}" y2="${Y(0)}" stroke="${CSS("--line-strong")}"/>`;const hit=[];
  yl.forEach(([y,v],i)=>{
    const top=Math.min(Y(v),Y(0)),h=Math.max(2,Math.abs(Y(v)-Y(0)));
    g+=`<rect x="${X(i)-bw/2}" y="${top}" width="${bw}" height="${h}" rx="4" fill="${v>=0?CSS("--pos"):CSS("--neg")}"/>`
      +`<text x="${X(i)}" y="${v>=0?top-5:top+h+13}" text-anchor="middle" fill="${CSS("--muted")}" font-size="${f}" font-family="var(--f-mono)" font-weight="600">${sg(v)}</text>`
      +`<text x="${X(i)}" y="${H-8}" text-anchor="middle" fill="${CSS("--faint")}" font-size="${f}">${String(y).slice(2)}</text>`;
    hit.push({cx:X(i),html:`<div class="th">${y}</div><div class="tr">Wynik roku<span class="tv" style="color:${v>=0?CSS("--pos"):CSS("--neg")}">${sg2(v)}%</span></div>`})});
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Wynik rok po roku" data-hover='${HV({W,H,max:(W-L-R)/n/1.5,hit})}'>${g}</svg>`});

chart("c-drift",W=>{
  const tot=Object.values(HOLDINGS).reduce((a,b)=>a+b,0);
  const rows=[...new Set([...Object.keys(COMBINED),...Object.keys(HOLDINGS)])]
    .sort((a,b)=>(a==="GOTOWKA")-(b==="GOTOWKA")||ORDER.indexOf(a)-ORDER.indexOf(b))
    .map(t=>({t,pp:((HOLDINGS[t]||0)/tot-(COMBINED[t]||0)/TOTAL)*100,have:HOLDINGS[t]||0,want:COMBINED[t]||0}));
  const bh=34,H=rows.length*bh+30,L=78,R=12,C=(L+W-R)/2,f=FS(W);
  const mx=Math.max(3,...rows.map(r=>Math.abs(r.pp)))*1.18,SX=p=>C+(W-R-C)*p/mx;
  let out=`<line x1="${C}" x2="${C}" y1="6" y2="${rows.length*bh+6}" stroke="${CSS("--line-strong")}"/>`;const hit=[];
  rows.forEach((r,i)=>{
    const y=i*bh+9,h=18,w=Math.abs(SX(r.pp)-C);
    const col=Math.abs(r.pp)<1?CSS("--line-strong"):(r.pp>0?CSS("--warn"):CSS("--cash"));
    out+=`<rect x="${r.pp>=0?C+1:SX(r.pp)}" y="${y}" width="${Math.max(1,w-1)}" height="${h}" rx="5" fill="${col}"/>`
      +`<text x="${L-10}" y="${y+14}" text-anchor="end" fill="${CSS("--fg")}" font-size="${f+1.5}" font-weight="700">${r.t==="GOTOWKA"?"Gotówka":r.t}</text>`
      +`<text x="${r.pp>=0?C+w+8:C-w-8}" y="${y+14}" text-anchor="${r.pp>=0?"start":"end"}" fill="${CSS("--muted")}" font-size="${f}" font-family="var(--f-mono)" font-weight="600">${sg(r.pp)} pp</text>`;
    hit.push({x0:0,x1:W,y0:y-5,y1:y+h+5,html:`<div class="th">${r.t}</div>
      <div class="tr">Mam<span class="tv">${zl(r.have)} zł</span></div><div class="tr">Cel<span class="tv">${zl(r.want)} zł</span></div>`})});
  out+=`<text x="${C+8}" y="${rows.length*bh+24}" fill="${CSS("--faint")}" font-size="${f}">nadwaga →</text>`
    +`<text x="${C-8}" y="${rows.length*bh+24}" text-anchor="end" fill="${CSS("--faint")}" font-size="${f}">← niedowaga</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Odchylenie od składu docelowego" data-hover='${HV({W,H,max:1e9,hit})}'>${out}</svg>`});

chart("c-canary",W=>{
  const nr=W<460,H=nr?200:235,L=nr?38:46,R=10,T=12,B=28,n=MONTHS.length,lo=-6,hi=5,f=FS(W);
  const X=i=>L+(W-L-R)*i/(n-1),Y=v=>T+(H-T-B)*(1-(v-lo)/(hi-lo));
  const p=a=>a.map((v,i)=>(i?"L":"M")+X(i).toFixed(1)+" "+Y(v).toFixed(1)).join(" ");
  let g="";for(let v=-6;v<=4;v+=2)g+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${CSS("--line")}"/><text x="${L-7}" y="${Y(v)+4}" text-anchor="end" fill="${CSS("--faint")}" font-size="${f}">${v}%</text>`;
  let xl="";for(let i=0;i<n;i+=nr?6:4)xl+=`<text x="${X(i)}" y="${H-8}" text-anchor="middle" fill="${CSS("--faint")}" font-size="${f}">${mLbl(MONTHS[i])}</text>`;
  const hit=MONTHS.map((m,i)=>({cx:X(i),html:`<div class="th">${mLbl(m)}</div>
    <div class="tr"><span class="sw" style="background:${CSS("--s1")}"></span>VT<span class="tv">${sg(CAN_VT[i])}%</span></div>
    <div class="tr"><span class="sw" style="background:${CSS("--s2")}"></span>XLK<span class="tv">${sg(CAN_XLK[i])}%</span></div>
    <div class="tr" style="color:${(CAN_VT[i]<-2&&CAN_XLK[i]<-2)?CSS("--cash"):CSS("--pos")}"><span class="sw" style="background:transparent"></span>Tryb<span class="tv">${(CAN_VT[i]<-2&&CAN_XLK[i]<-2)?"CASH":"RISK"}</span></div>`}));
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Kanarek wobec progu minus 2 procent" data-hover='${HV({W,H,max:(W-L-R)/n,hit})}'>
    ${g}<rect x="${L}" y="${Y(-2)}" width="${W-L-R}" height="${H-B-Y(-2)}" fill="${CSS("--cash")}" opacity=".1"/>
    <line x1="${L}" x2="${W-R}" y1="${Y(-2)}" y2="${Y(-2)}" stroke="${CSS("--neg")}" stroke-width="2" stroke-dasharray="5 4"/>
    <text x="${W-R}" y="${Y(-2)-7}" text-anchor="end" fill="${CSS("--neg")}" font-size="${f}" font-weight="700">próg −2%</text>
    <line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="${CSS("--line-strong")}" style="opacity:0"/>
    <path d="${p(CAN_VT)}" fill="none" stroke="${CSS("--s1")}" stroke-width="2.5" stroke-linejoin="round"/>
    <path d="${p(CAN_XLK)}" fill="none" stroke="${CSS("--s2")}" stroke-width="2.5" stroke-linejoin="round"/>
    <circle cx="${X(n-1)}" cy="${Y(CAN_VT[n-1])}" r="5" fill="${CSS("--s1")}" stroke="${CSS("--surface")}" stroke-width="2.5"/>
    <circle cx="${X(n-1)}" cy="${Y(CAN_XLK[n-1])}" r="5" fill="${CSS("--s2")}" stroke="${CSS("--surface")}" stroke-width="2.5"/>${xl}</svg>`});

chart("c-rank",W=>{
  const bh=40,H=RANK.length*bh+34,L=58,R=14,mx=5.4,SX=v=>L+(W-R-L)*v/mx,f=FS(W);
  let out=`<line x1="${SX(1)}" x2="${SX(1)}" y1="4" y2="${RANK.length*bh+6}" stroke="${CSS("--neg")}" stroke-width="2" stroke-dasharray="5 4"/>`
    +`<text x="${SX(1)+6}" y="${RANK.length*bh+25}" fill="${CSS("--neg")}" font-size="${f}" font-weight="700">bramka +1%</text>`;
  const hit=[];
  RANK.forEach(([t,v,gate],i)=>{
    const y=i*bh+9,h=22,top=i<2,col=top?CSS("--accent"):(gate==="no"?CSS("--line-strong"):CSS("--s6"));
    out+=`<rect x="${L}" y="${y}" width="${Math.max(2,SX(v)-L)}" height="${h}" rx="5" fill="${col}"/>`
      +`<text x="${L-10}" y="${y+16}" text-anchor="end" fill="${CSS("--fg")}" font-size="${f+1.5}" font-weight="700">${t}</text>`
      +`<text x="${SX(v)+8}" y="${y+16}" fill="${CSS("--muted")}" font-size="${f}" font-family="var(--f-mono)" font-weight="600">+${v.toFixed(2).replace(".",",")}%</text>`
      +(top?`<text x="${L+9}" y="${y+16}" fill="#06201D" font-size="${f}" font-weight="700">TOP ${i+1} · ${i?20:80}%</text>`:"")
      +(gate==="no"?`<text x="${L+9}" y="${y+16}" fill="${CSS("--neg")}" font-size="${f}" font-weight="700">ODCIĘTE</text>`:"");
    hit.push({x0:0,x1:W,y0:y-5,y1:y+h+5,html:`<div class="th">${t}</div>
      <div class="tr">Wynik<span class="tv">+${v.toFixed(2).replace(".",",")}%</span></div>
      <div class="tr">Pozycja<span class="tv">${top?"top "+(i+1):gate==="no"?"odcięte":"poza podium"}</span></div>`})});
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Ranking BEST17 z progiem bramki" data-hover='${HV({W,H,max:1e9,hit})}'>${out}</svg>`});

/* ---- macierz skladu: wiersz = walor, kolumna = data rebalansu ---- */
const hexRGB=h=>{const n=parseInt(h.replace("#",""),16);return [n>>16&255,n>>8&255,n&255].join(",")};
/* Zaokraglanie metoda najwiekszych reszt: same round() daje 27+27+27+20 = 101,
   a kolumna, ktora nie sumuje sie do 100, wyglada na blad danych. */
function round100(o){
  const e=Object.entries(o).filter(([,w])=>w>.0005);
  if(!e.length)return {};
  const f=e.map(([t,w])=>[t,w*100,Math.floor(w*100)]);
  let left=100-f.reduce((a,x)=>a+x[2],0);
  f.sort((a,b)=>(b[1]-b[2])-(a[1]-a[2]));
  for(let k=0;k<f.length&&left>0;k++,left--)f[k][2]++;
  return Object.fromEntries(f.map(([t,,v])=>[t,v]))}
function legCol(c,leg){
  const o={...c[leg]},s=Object.values(o).reduce((a,b)=>a+b,0);
  if(s<.999)o.GOTOWKA=1-s;
  return round100(o)}
let MXN=null;  /* ile ostatnich dat pokazac; null = dobierz do szerokosci */
function renderMatrix(){
  const wide=innerWidth>=560, n=MXN||(wide?12:6);
  const COLS=COMPO.slice(-n);
  document.querySelectorAll("#segMx button").forEach(b=>b.setAttribute("aria-pressed",String(+b.dataset.mx===n)));
  const head=`<thead><tr><th class="st">Walor</th>`
    +COLS.map(c=>`<th>${c.date.slice(8)}.${c.date.slice(5,7)}</th>`).join("")+`</tr></thead>`;
  let body="";
  for(const[leg,name]of [["best17","BEST17"],["gpm","GPM"]]){
    const cols=COLS.map(c=>legCol(c,leg));
    const rows=[...ORDER,"GOTOWKA"].filter(t=>cols.some(c=>c[t]));
    body+=`<tr class="grp"><td class="st">${name}</td><td colspan="${COLS.length}"></td></tr>`;
    for(const t of rows)
      body+=`<tr><td class="st"><span class="sw-in" style="background:${CSS(KOL[t]||"--s6")}"></span>${t==="GOTOWKA"?"Gotówka":t}</td>`
        +cols.map(c=>{const v=c[t]||0;
          return v?`<td style="background:rgba(${hexRGB(CSS(KOL[t]||"--s6"))},${(.16+.006*v).toFixed(2)})">${v}</td>`
                  :'<td class="z">·</td>'}).join("")+`</tr>`}
  document.getElementById("mxComp").innerHTML=head+"<tbody>"+body+"</tbody>";
  const w=document.getElementById("mxWrap");
  w.classList.toggle("more",document.getElementById("mxComp").scrollWidth>w.clientWidth+2)}
document.getElementById("segMx").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b)return;MXN=+b.dataset.mx;renderMatrix()});

/* ---- ostatnie 12 miesiecy ---- */
chart("c-month",W=>{
  const d=SER.slice(-12),n=d.length,nr=W<460,H=nr?180:205,T=18,B=30,L=10,R=10,f=FS(W);
  const mx=Math.max(...d.map(p=>Math.abs(p.r)))*1.35;
  const bw=(W-L-R)/n*.62,X=i=>L+(W-L-R)*(i+.5)/n,Y=v=>T+(H-T-B)*(1-(v+mx)/(2*mx));
  let g=`<line x1="${L}" x2="${W-R}" y1="${Y(0)}" y2="${Y(0)}" stroke="${CSS("--line-strong")}"/>`;const hit=[];
  d.forEach((p,i)=>{
    const top=Math.min(Y(p.r),Y(0)),h=Math.max(3,Math.abs(Y(p.r)-Y(0)));
    g+=`<rect x="${X(i)-bw/2}" y="${top}" width="${bw}" height="${h}" rx="4" fill="${p.r>=0?CSS("--pos"):CSS("--neg")}"/>`
      +`<text x="${X(i)}" y="${p.r>=0?top-5:top+h+13}" text-anchor="middle" fill="${CSS("--muted")}" font-size="${f}" font-family="var(--f-mono)" font-weight="600">${sg(p.r)}</text>`
      +`<text x="${X(i)}" y="${H-9}" text-anchor="middle" fill="${CSS("--faint")}" font-size="${f}">${MN[p.m]}</text>`;
    hit.push({cx:X(i),html:`<div class="th">${MN[p.m]} ${p.y}</div>
      <div class="tr">Wynik<span class="tv" style="color:${p.r>=0?CSS("--pos"):CSS("--neg")}">${sg2(p.r)}%</span></div>`})});
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Wyniki ostatnich dwunastu miesięcy" data-hover='${HV({W,H,max:(W-L-R)/n/1.6,hit})}'>${g}</svg>`});

/* ten sam wykres kapitalu na pulpicie */
chart("c-equity2",charts.find(c=>c.id==="c-equity").draw);

/* ============ widoki ============ */
const legend=(id,it)=>document.getElementById(id).innerHTML=it.map(([n,c])=>`<span><i style="background:${c}"></i>${n}</span>`).join("");
/* Odcien niesie klase aktywa, jasniejszy krok rozroznia walory w tej samej klasie,
   zeby dwie pozycje trzymane naraz nigdy nie mialy identycznej probki. */
const KOL={IUIT:"--s1",CNDX:"--s1b",CSPX:"--s2",VWRA:"--s2b",EIMI:"--s2c",IUES:"--s2d",
  CMOD:"--s3",XRES:"--s3b",IGLN:"--s4",IBTA:"--s5",CBU0:"--s5b",DTLA:"--s5c",
  IHYA:"--s5d",LQDA:"--s7",GOTOWKA:"--s6"};
const tbl=(h,b,f)=>`<div class="card tw"><table><thead><tr>${h}</tr></thead><tbody>${b}</tbody>${f?`<tfoot>${f}</tfoot>`:""}</table></div>`;
/* ---- pulpit ---- */
const WART=VALUE.at(-1),WPL=PAID.at(-1);
function renderPulpit(){
  const zysk=WART-WPL, U=PORT.usd, zyskU=U.value-U.paid, T=PORT.twr;
  const sgn=(v,u)=>(v>=0?"+":"−")+zl(v)+" "+u;
  document.getElementById("kpi").innerHTML=[
    ["Wartość",zl(WART)+" zł",zl(U.value)+" USD","--fg","--muted","kurs "+String(PORT.fx.rate).replace(".",",")],
    ["Wynik",sgn(zysk,"zł"),sgn(zyskU,"USD"),zysk>=0?"--pos":"--neg",zyskU>=0?"--pos":"--neg","wobec wpłat"],
    ["TWR",sg2(T.pln)+"% PLN",sg2(T.usd)+"% USD",T.pln>=0?"--pos":"--neg",T.usd>=0?"--pos":"--neg","same decyzje"],
    ["Rebalans","za 15 dni","25 grudnia","--warn","--muted","transza 25-tego"]
  ].map(([l,v,v2,c,c2,d])=>`<div class="tile"><div class="lbl">${l}</div>
    <div class="v" style="color:var(${c})">${v}</div>
    <div class="v2" style="color:var(${c2})">${v2}</div><div class="d">${d}</div></div>`).join("");

  document.getElementById("accStrips").innerHTML=SETUPS[SETUP].accounts.map(a=>{
    const o=accComp(a),cap=accTarget(a),d=a.value-cap;
    return `<div class="strip">
      <div class="h"><b>${esc(a.name)}</b><span class="sub">${accLegs(a)}</span><span class="v">${zl(a.value)} zł</span></div>
      <div class="bar">${Object.entries(o).map(([t,v])=>{const w=v/cap*100;
        return `<span style="flex:${w};background:${CSS(KOL[t]||"--s6")}" title="${t} ${pc(v/cap)}">${w>11?(t==="GOTOWKA"?"GOT.":t):""}</span>`}).join("")}</div>
      <div class="f"><span>skład docelowy · cel ${zl(cap)} zł</span><span class="d" style="color:${Math.abs(d)<cap*.02?"var(--faint)":"var(--warn)"}">${d>=0?"+":"−"}${zl(Math.abs(d))} zł</span></div>
    </div>`}).join("")}

function renderHero(){
  const e=Object.entries(COMBINED).sort((a,b)=>b[1]-a[1]);
  document.getElementById("allocBar").innerHTML=e.map(([t,v])=>{
    const w=v/TOTAL*100;
    return `<span style="flex:${w};background:${CSS(KOL[t]||"--s6")}" title="${t} ${pc(v/TOTAL)}">${w>9?(t==="GOTOWKA"?"GOT.":t):""}</span>`}).join("");
  document.getElementById("top3").innerHTML=e.slice(0,4).map(([t,v])=>
    `<div><div class="t"><span class="sw-in" style="background:${CSS(KOL[t]||"--s6")};margin:0"></span>${t==="GOTOWKA"?"Gotówka":t}</div>
     <div class="v">${pc(v/TOTAL)}</div><div class="s">${zl(v)} zł</div></div>`).join("")}
function renderActions(){
  const rows=[...new Set([...Object.keys(T25.out),...Object.keys(HOLDINGS)])].filter(t=>t!=="GOTOWKA")
    .map(t=>({t,want:T25.out[t]||0,d:(T25.out[t]||0)-(HOLDINGS[t]||0)*(1-CAPITAL.split10)}))
    .filter(r=>Math.abs(r.d)>=TOTAL*.02).sort((a,b)=>Math.abs(b.d)-Math.abs(a.d));
  document.getElementById("actions").innerHTML=rows.length?rows.map(r=>
    `<div class="act ${r.d>0?"buy":"sell"}"><i class="w"></i><div><div class="t">${r.d>0?"Kup":"Sprzedaj"} ${r.t}</div>
     <div class="sub">${ROLE[r.t]||""}</div></div><div class="q"><b>${zl(Math.abs(r.d))} zł</b>
     <span class="sub">cel ${zl(r.want)} zł</span></div></div>`).join("")
    :'<div class="act hold"><i class="w"></i><div><div class="t">Bez zmian</div></div></div>'}
const renderHist=()=>document.getElementById("hist").innerHTML=HIST.map(h=>
  `<tr><td>${h[0]}</td><td><span class="pill ${h[1]==="RISK"?"p-risk":"p-cash"}">${h[1]}</span><span class="tick">${esc(h[2])}</span></td>
   <td><span class="pill ${h[3]==="RISK"?"p-risk":"p-cash"}">${h[3]}</span></td><td class="sub">${esc(h[4])}</td></tr>`).join("");
const viewSum=()=>tbl("<th>ETF</th><th>Kwota</th><th>Udział</th><th>z 10-tego</th><th>z 25-tego</th>",
  Object.entries(COMBINED).sort((a,b)=>b[1]-a[1]).map(([t,v])=>
    `<tr><td><span class="sw-in" style="background:${CSS(KOL[t]||"--s6")}"></span>${t==="GOTOWKA"?"Gotówka":t}</td>
     <td class="num">${zl(v)}</td><td class="num">${pc(v/TOTAL)}</td>
     <td class="num sub">${zl(T10.out[t]||0)}</td><td class="num sub">${zl(T25.out[t]||0)}</td></tr>`).join(""),
  `<tr><td>Razem</td><td class="num">${zl(TOTAL)}</td><td class="num">100,0%</td><td class="num">${zl(TOTAL/2)}</td><td class="num">${zl(TOTAL/2)}</td></tr>`);
function viewAcc(){
  const s=SETUPS[SETUP];let h=`<div class="seg setupSel"></div>`;
  for(const a of s.accounts){
    const o=accComp(a),cap=accTarget(a);
    h+=`<h2 class="sec">${esc(a.name)} <span class="sub" style="font-weight:400">· ${accLegs(a)} · ${zl(cap)} zł</span></h2>`
      +tbl("<th>ETF</th><th>Kwota</th><th>Udział konta</th>",Object.entries(o).map(([t,v])=>
        `<tr><td><span class="sw-in" style="background:${CSS(KOL[t]||"--s6")}"></span>${t==="GOTOWKA"?"Gotówka":t}</td>
         <td class="num">${zl(v)}</td><td class="num">${pc(v/cap)}</td></tr>`).join(""))}
  return h}
const viewDat=()=>[[T10,SIGNALS[0]],[T25,SIGNALS[1]]].map(([T,s])=>
  `<h2 class="sec">Transza ${s.tranche}-tego <span class="sub" style="font-weight:400">· ${s.date}</span></h2>
   <div style="margin-bottom:11px">
     <div class="leg"><b>BEST17</b><span class="pill ${s.best17.mode==="RISK"?"p-risk":"p-cash"}">${s.best17.mode}</span><span class="as">${s.best17.picks.join(" · ")||"gotówka"}</span></div>
     <div class="leg"><b>GPM</b><span class="pill ${s.gpm.mode==="RISK"?"p-risk":"p-cash"}">${s.gpm.mode}</span><span class="as">${Object.keys(s.gpm.weights).join(" · ")}</span></div></div>`
  +tbl("<th>ETF</th><th>Kwota</th><th>Udział</th>",Object.entries(T.out).filter(([,v])=>v>.5).sort((a,b)=>b[1]-a[1]).map(([t,v])=>
    `<tr><td><span class="sw-in" style="background:${CSS(KOL[t]||"--s6")}"></span>${t==="GOTOWKA"?"Gotówka":t}</td>
     <td class="num">${zl(v)}</td><td class="num">${pc(v/(T.kB+T.kG))}</td></tr>`).join(""))).join("");
function renderSklad(m){document.getElementById("skladBody").innerHTML=m==="acc"?viewAcc():m==="dat"?viewDat():viewSum();fillSel()}
function renderAccounts(){
  const s=SETUPS[SETUP];
  document.getElementById("accRows").innerHTML=s.accounts.map(a=>{
    const cel=accTarget(a),d=a.value-cel;
    return `<tr><td>${esc(a.name)}<span class="tick">${accLegs(a)}</span></td><td class="num">${zl(a.value)}</td>
      <td class="num sub">${zl(cel)}<span class="tick" style="color:${Math.abs(d)<cel*.02?"var(--faint)":"var(--warn)"}">${d>=0?"+":"−"}${zl(Math.abs(d))}</span></td>
      <td class="num" style="color:${a.pln>=0?"var(--pos)":"var(--neg)"}">${sg(a.pln)}%</td>
      <td class="num" style="color:${a.usd>=0?"var(--pos)":"var(--neg)"}">${sg(a.usd)}%</td></tr>`}).join("");
  document.getElementById("accNote").textContent=s.accounts.length===1
    ?"Jedno konto: obie nogi w jednej liście, pozycje wspólne w jednym zleceniu."
    :"Różnicę wobec celu wyrównujesz przy wpłacie, nie przelewem między brokerami.";
  fillSel()}

function renderWyniki(){
  document.getElementById("tiles").innerHTML=[
    ["CAGR",sg2(STAT.cagr)+"%","rocznie","--pos"],
    ["MaxDD",STAT.mdd.toFixed(1).replace(".",",")+"%","najgłębsze","--neg"],
    ["Calmar",STAT.calmar.toFixed(2).replace(".",","),"zysk do ryzyka","--fg"],
    ["Najgorszy rok",sg(STAT.worst)+"%","z "+STAT.yl.length+" lat","--neg"],
    ["Najlepszy rok",sg(STAT.best)+"%","","--pos"],
    ["Dodatnie miesiące",STAT.win.toFixed(0)+"%",SER.length+" miesięcy","--fg"],
    ["Pod wodą",STAT.maxuw+" mies.","najdłużej","--warn"],
    ["Mnożnik","×"+STAT.eq.toFixed(2).replace(".",","),"bez wpłat","--accent"]
  ].map(([l,v,d,c])=>`<div class="tile"><div class="lbl">${l}</div><div class="v" style="color:var(${c})">${v}</div><div class="d">${d}</div></div>`).join("");
  const col=r=>{const a=Math.min(Math.abs(r)/6,1)*.55+.08;return `background:rgba(${r>=0?"12,163,12":"208,59,59"},${a.toFixed(2)})`};
  let h=`<thead><tr><th>Rok</th>${MN.map(m=>`<th>${m}</th>`).join("")}<th>Rok</th></tr></thead><tbody>`;
  for(const y of Object.keys(RET).sort()){
    const yv=STAT.yl.find(a=>a[0]===+y)[1];
    /* spread, nie r.map: tablica rzadka gubi w map puste sloty i przesuwa miesiace o kolumne */
    h+=`<tr><td>${y}</td>`+[...RET[y]].map(v=>v==null?'<td class="na">·</td>':`<td style="${col(v)}">${sg(v)}</td>`).join("")
      +`<td class="yr" style="color:var(${yv>=0?"--pos":"--neg"})">${sg(yv)}</td></tr>`}
  document.getElementById("mgrid").innerHTML=h+"</tbody>"}

/* ---- ceny: cena z feedu jest nietykalna, korekta to osobny wpis ---- */
let ADMIN=false,EDIT=null;
let OVR={};try{OVR=JSON.parse(localStorage.getItem("ovr")||"{}")}catch(e){OVR={}}
const saveOVR=()=>{try{localStorage.setItem("ovr",JSON.stringify(OVR))}catch(e){}};
const okey=(t,d)=>t+"@"+d;
const eff=(t,i)=>{const P=PRICES[PTAB],o=OVR[okey(t,P.dates[i])];return o?o.v:P.px[t][i]};
function renderCeny(){
  const P=PRICES[PTAB],last=P.dates.length-1;
  document.getElementById("feedStamp").textContent=FEED.source+" · "+FEED.fetched;
  document.getElementById("thAct").hidden=!ADMIN;
  const chk=[];
  const brak=INSTR.filter(([t])=>eff(t,last)==null);
  chk.push([brak.length?"warn":"ok","Komplet instrumentów",(INSTR.length-brak.length)+"/"+INSTR.length]);
  chk.push(["ok","Data zgodna z regułą "+PTAB+"-tego",P.dates[last]]);
  const stale=INSTR.filter(([t])=>eff(t,last)===eff(t,last-1)).map(a=>a[0]);
  chk.push([stale.length?"warn":"ok",stale.length?"Cena bez zmian: "+stale.join(", "):"Brak zastoju cen",stale.length?"sprawdź":"OK"]);
  const jump=INSTR.filter(([t])=>Math.abs(eff(t,last)/eff(t,last-1)-1)>.25).map(a=>a[0]);
  chk.push([jump.length?"warn":"ok",jump.length?"Skok powyżej 25%: "+jump.join(", "):"Brak skoków powyżej 25%",jump.length?"sprawdź":"OK"]);
  const nov=Object.keys(OVR).length;
  chk.push([nov?"warn":"ok",nov?"Korekty ręczne w historii":"Brak korekt ręcznych",nov?nov+"":"0"]);
  document.getElementById("checks").innerHTML=chk.map(([s,t,m])=>
    `<div class="chk"><span class="ic ${s}">${s==="ok"?"✓":"!"}</span>${esc(t)}<span class="m">${esc(m)}</span></div>`).join("");

  document.getElementById("priceRows").innerHTML=INSTR.map(([t,mk])=>{
    const d=P.dates[last],o=OVR[okey(t,d)],raw=P.px[t][last],v=eff(t,last),ch=(v/eff(t,last-1)-1)*100;
    if(EDIT===t)return `<tr><td>${t}</td><td colspan="${ADMIN?5:4}" style="text-align:left;padding:10px 0">
      <form class="form" id="ovrForm" style="grid-template-columns:1fr 2fr auto auto;align-items:end">
        <div class="fld"><label for="ovrV">Cena</label><input type="number" id="ovrV" step="0.0001" value="${v}" required></div>
        <div class="fld"><label for="ovrR">Powód korekty</label><input type="text" id="ovrR" placeholder="np. zły kurs z feedu" required></div>
        <button class="btn" type="submit">Zapisz</button>
        <button class="btn" type="button" data-cancel style="background:var(--surface2);color:var(--muted)">Anuluj</button>
      </form></td></tr>`;
    return `<tr><td>${t}<span class="tick">${mk==="US"?"sygnał":"wykonanie"}</span></td>
      <td class="num">${px(v)}${o?`<span class="tick" style="text-decoration:line-through">${px(raw)}</span>`:""}</td>
      <td class="num sub">${d}</td>
      <td class="num" style="color:${ch>=0?"var(--pos)":"var(--neg)"}">${sg(ch)}%</td>
      <td>${o?`<span class="pill p-cash" title="${esc(o.r)} · ${esc(o.who)} · ${esc(o.when)}">skorygowane</span>`
        :v===eff(t,last-1)?'<span class="pill p-warn">zastój</span>':'<span class="pill p-neu">ok</span>'}</td>
      ${ADMIN?`<td style="width:1%"><button class="del" data-edit="${t}" aria-label="Koryguj ${t}" style="font-size:.85rem">zmień</button>
        ${o?`<button class="del" data-undo="${t}" aria-label="Cofnij korektę ${t}">×</button>`:""}</td>`:""}</tr>`}).join("");

  let h=`<thead><tr><th>Data</th>${INSTR.map(([t])=>`<th>${t}</th>`).join("")}</tr></thead><tbody>`;
  for(let i=P.dates.length-1;i>=0;i--)
    h+=`<tr><td>${P.dates[i]}</td>`+INSTR.map(([t])=>{
      const o=OVR[okey(t,P.dates[i])];
      return `<td${o?' style="background:rgba(127,168,206,.22)" title="skorygowane"':""}>${px(eff(t,i))}</td>`}).join("")+"</tr>";
  document.getElementById("priceHist").innerHTML=h+"</tbody>"}
document.getElementById("segP").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b)return;
  document.querySelectorAll("#segP button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));
  PTAB=b.dataset.p;EDIT=null;renderCeny()});
document.getElementById("segR").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b)return;
  document.querySelectorAll("#segR button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));
  ADMIN=b.dataset.r==="1";EDIT=null;renderCeny()});
document.getElementById("priceRows").addEventListener("click",e=>{
  const ed=e.target.closest("[data-edit]"),un=e.target.closest("[data-undo]"),ca=e.target.closest("[data-cancel]");
  if(ed){EDIT=ed.dataset.edit;renderCeny();document.getElementById("ovrV")?.focus()}
  else if(un){delete OVR[okey(un.dataset.undo,PRICES[PTAB].dates.at(-1))];saveOVR();renderCeny()}
  else if(ca){EDIT=null;renderCeny()}});
document.getElementById("priceRows").addEventListener("submit",e=>{
  e.preventDefault();
  OVR[okey(EDIT,PRICES[PTAB].dates.at(-1))]={v:parseFloat(document.getElementById("ovrV").value),
    r:document.getElementById("ovrR").value,who:"admin",when:new Date().toISOString().slice(0,16).replace("T"," ")};
  saveOVR();EDIT=null;renderCeny()});

/* ---- transakcje ---- */
let TX=[];
try{TX=JSON.parse(localStorage.getItem("tx")||"[]")}catch(e){TX=[]}
if(!TX.length)TX=[{d:"2026-11-20",a:"LYNX",t:"wplata",k:10000},{d:"2026-11-20",a:"LYNX",t:"kupno",w:"IUIT",k:10000},
  {d:"2026-09-15",a:"XTB",t:"wplata",k:15000},{d:"2026-09-16",a:"XTB",t:"kupno",w:"IBTA",k:15000}];
const saveTX=()=>{try{localStorage.setItem("tx",JSON.stringify(TX))}catch(e){}};
const TYP={wplata:"Wpłata",wyplata:"Wypłata",kupno:"Kupno",sprzedaz:"Sprzedaż"};
function fillAccSelect(){
  const s=document.getElementById("txAcc"),cur=s.value;
  s.innerHTML=SETUPS[SETUP].accounts.map(a=>`<option>${esc(a.name)}</option>`).join("");
  if([...s.options].some(o=>o.value===cur))s.value=cur}
function renderTX(){
  TX.sort((a,b)=>b.d.localeCompare(a.d));
  document.getElementById("txCount").textContent=TX.length+" "+(TX.length===1?"rekord":TX.length<5?"rekordy":"rekordów");
  document.getElementById("txRows").innerHTML=TX.length?TX.map((r,i)=>
    `<tr><td class="num" style="font-weight:400">${r.d}</td><td>${esc(r.a)}</td>
      <td style="text-align:right"><span class="pill ${r.t==="wplata"?"p-risk":r.t==="wyplata"?"p-cash":"p-neu"}">${TYP[r.t]}</span>${r.w?` <b>${esc(r.w)}</b>`:""}</td>
      <td class="num">${zl(r.k)} zł</td>
      <td style="width:1%"><button class="del" data-del="${i}" aria-label="Usuń rekord z ${r.d}">×</button></td></tr>`).join("")
    :'<tr><td colspan="5"><div class="empty">Brak rekordów</div></td></tr>';
  const acc={};
  for(const r of TX){acc[r.a]=acc[r.a]||{in:0,out:0};
    if(r.t==="wplata")acc[r.a].in+=r.k;if(r.t==="wyplata")acc[r.a].out+=r.k}
  const ks=Object.keys(acc);
  document.getElementById("depRows").innerHTML=ks.length?ks.map(k=>
    `<tr><td>${esc(k)}</td><td class="num">${zl(acc[k].in)}</td><td class="num sub">${acc[k].out?zl(acc[k].out):"—"}</td>
     <td class="num" style="font-weight:700">${zl(acc[k].in-acc[k].out)} zł</td></tr>`).join("")
    :'<tr><td colspan="4"><div class="empty">Brak wpłat</div></td></tr>'}
document.getElementById("txType").addEventListener("change",e=>{
  document.getElementById("txTickWrap").hidden=!(e.target.value==="kupno"||e.target.value==="sprzedaz")});
document.getElementById("txForm").addEventListener("submit",e=>{
  e.preventDefault();
  const t=document.getElementById("txType").value,trade=t==="kupno"||t==="sprzedaz";
  TX.push({d:document.getElementById("txDate").value,a:document.getElementById("txAcc").value,t,
    w:trade?document.getElementById("txTick").value:undefined,
    k:parseFloat(document.getElementById("txAmt").value)||0});
  saveTX();renderTX();e.target.reset();
  document.getElementById("txDate").value=new Date().toISOString().slice(0,10);
  document.getElementById("txTickWrap").hidden=true});
document.getElementById("txRows").addEventListener("click",e=>{
  const b=e.target.closest("[data-del]");if(!b)return;
  TX.splice(+b.dataset.del,1);saveTX();renderTX()});

/* ============ nawigacja ============ */
const VIEWS=["pulpit","sygnal","portfel","wyniki","transakcje","ceny","dlaczego"];
function show(v){
  if(!VIEWS.includes(v))v="pulpit";
  VIEWS.forEach(x=>document.getElementById("v-"+x).hidden=(x!==v));
  document.querySelectorAll("#nav a").forEach(a=>a.getAttribute("href")==="#"+v?a.setAttribute("aria-current","page"):a.removeAttribute("aria-current"));
  renderAll();scrollTo(0,0)}
addEventListener("hashchange",()=>show(location.hash.slice(1)));
document.getElementById("segS").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b)return;
  document.querySelectorAll("#segS button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));
  renderSklad(b.dataset.s)});

document.getElementById("txTick").innerHTML=ORDER.map(t=>`<option>${t}</option>`).join("");
document.getElementById("txDate").value=new Date().toISOString().slice(0,10);
fillAccSelect();renderTX();renderPulpit();renderMatrix();renderHero();renderActions();renderHist();renderSklad("sum");renderAccounts();renderWyniki();renderCeny();
const EQL=[["Wartość portfela",CSS("--accent")],["Wpłacony kapitał",CSS("--muted")]];
legend("l-equity",EQL);legend("l-equity2",EQL);
legend("l-mix",KLASY.map(k=>[k[0],CSS(k[1])]));
legend("l-canary",[["VT",CSS("--s1")],["XLK",CSS("--s2")]]);
show(location.hash.slice(1)||"pulpit");
