
/* Dane przychodza z plikow JSON w docs/data/ - to jest kontrakt miedzy
   pipeline'em (GitHub Actions zapisuje te pliki) a ta strona (tylko je czyta).
   Modul + top-level await: reszta pliku wykonuje sie dopiero po wczytaniu. */
/* Logowanie i baza sa opcjonalne: dane publiczne ida z plikow JSON w repo,
   wiec brak Firebase nie moze zatrzymac strony. */
let FB=null;
try{ FB=await import("./fb.js") }catch(e){ console.warn("Firebase niedostepny:",e.message) }
let USER=null, ADMIN_BAZA=false;

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
/* Aktywa sa dolarowe: USD jest wartoscia pierwotna, PLN to przeliczenie po kursie z danego miesiaca. */
const FXS=PORT.fx.series, VUSD=PORT.value_usd, PUSD=PORT.paid_usd, RETC=PORT.returns, LEGS=PORT.legs;
const CUR={usd:{v:VUSD,p:PUSD,u:"USD",r:RETC.usd},pln:{v:VALUE,p:PAID,u:"zł",r:RETC.pln}};
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
/* dni wpisane recznie doklejaja sie do szeregu z feedu */
try{
  const r=JSON.parse(localStorage.getItem("recz")||"{}");
  for(const tab of ["10","25"])for(const d of (r[tab]||[])){
    const P=PRICES[tab];if(P.dates.includes(d.data))continue;
    P.dates.push(d.data);
    for(const[t]of INSTR)P.px[t].push(d.ceny[t]??null);
  }
}catch(e){}
async function wczytajCenyZBazy(){
  if(!FB||!USER)return;
  try{
    for(const w of await FB.wczytajCeny()){
      const P=PRICES[String(w.tranche)];if(!P||P.dates.includes(w.date))continue;
      P.dates.push(w.date);
      for(const[t]of INSTR)P.px[t].push(w.px?.[t]??null);
      P.man=P.man||{};P.man[w.date]=true;
      const kol=P.dates.map((d,i)=>[d,i]).sort((a,b)=>a[0].localeCompare(b[0]));
      P.dates=kol.map(x=>x[0]);
      for(const[t]of INSTR)P.px[t]=kol.map(x=>P.px[t][x[1]]);
    }
    for(const k of await FB.wczytajKorekty())OVR[k.id.replace(/^\d+_/, "").replace(/_/,"@")]={v:k.value,r:k.reason,who:k.author,when:k.created_at||""};
  }catch(e){console.warn("ceny z bazy:",e.message)}
  renderCeny();
}
const zapiszReczne=()=>{try{
  const r={};
  for(const tab of ["10","25"]){const P=PRICES[tab];
    r[tab]=P.dates.map((d,i)=>({data:d,ceny:Object.fromEntries(INSTR.map(([t])=>[t,P.px[t][i]])),man:!!P.man?.[d]}))
      .filter(x=>x.man)}
  localStorage.setItem("recz",JSON.stringify(r))}catch(e){}};
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
  rozdzielnie:{label:"2 konta",accounts:[
    {name:"LYNX",alloc:{best17:1,gpm:0},value:99180,pln:4.15,usd:-.91},
    {name:"XTB",alloc:{best17:0,gpm:1},value:98460,pln:2.28,usd:-2.77}]},
  jedno:{label:"1 konto",accounts:[
    {name:"Konto główne",alloc:{best17:1,gpm:1},value:197640,pln:3.21,usd:-1.84}]},
  porowno:{label:"Po równo",accounts:[
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
  const n=MXN||6;   /* pulpit pokazuje biezaca sytuacje; pelna historia jest w Wynikach */
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

/* ---- ostatnie miesiace: slupki w wybranej walucie ---- */
chart("c-month",W=>{
  const R=cur().r,K=6,idx=[...Array(K)].map((_,k)=>MONTHS.length-K+k);
  const nr=W<520,H=nr?150:175,T=20,B=26,L=6,Rp=6,f=FS(W);
  const mx=Math.max(...idx.map(i=>Math.abs(R[i]||0)))*1.35||1;
  const step=(W-L-Rp)/K,bw=Math.min(step*.44,40);
  const X=k=>L+step*(k+.5),Y=v=>T+(H-T-B)*(1-(v+mx)/(2*mx));
  let g=`<line x1="${L}" x2="${W-Rp}" y1="${Y(0)}" y2="${Y(0)}" stroke="${CSS("--line")}"/>`;const hit=[];
  idx.forEach((i,k)=>{const v=R[i];if(v==null)return;
    const top=Math.min(Y(v),Y(0)),h=Math.max(3,Math.abs(Y(v)-Y(0)));
    g+=`<rect x="${X(k)-bw/2}" y="${top}" width="${bw}" height="${h}" rx="5" fill="${v>=0?CSS("--pos"):CSS("--neg")}"/>`
      +`<text x="${X(k)}" y="${v>=0?top-6:top+h+14}" text-anchor="middle" fill="${CSS("--muted")}" font-size="${f}" font-weight="600">${sg(v)}</text>`
      +`<text x="${X(k)}" y="${H-7}" text-anchor="middle" fill="${CSS("--faint")}" font-size="${f}">${mLbl(MONTHS[i])}</text>`;
    hit.push({cx:X(k),html:`<div class="th">${mLbl(MONTHS[i])}</div><div class="tr">Wynik<span class="tv" style="color:${v>=0?CSS("--pos"):CSS("--neg")}">${sg2(v)}%</span></div>`})});
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Wyniki ostatnich szesciu miesiecy" data-hover='${HV({W,H,max:step/1.6,hit})}'>${g}</svg>`});

/* ============ widoki ============ */
const legend=(id,it)=>document.getElementById(id).innerHTML=it.map(([n,c])=>`<span><i style="background:${c}"></i>${n}</span>`).join("");
/* Odcien niesie klase aktywa, jasniejszy krok rozroznia walory w tej samej klasie,
   zeby dwie pozycje trzymane naraz nigdy nie mialy identycznej probki. */
const KOL={IUIT:"--s1",CNDX:"--s1b",CSPX:"--s2",VWRA:"--s2b",EIMI:"--s2c",IUES:"--s2d",
  CMOD:"--s3",XRES:"--s3b",IGLN:"--s4",IBTA:"--s5",CBU0:"--s5b",DTLA:"--s5c",
  IHYA:"--s5d",LQDA:"--s7",GOTOWKA:"--s6",
  /* walory sygnalowe w kolorze swoich odpowiednikow wykonawczych */
  XLK:"--s1",IVV:"--s2",VT:"--s2b",IAU:"--s4",DBC:"--s3"};
const tbl=(h,b,f)=>`<div class="card tw"><table><thead><tr>${h}</tr></thead><tbody>${b}</tbody>${f?`<tfoot>${f}</tfoot>`:""}</table></div>`;
/* ---- pulpit ---- */
let CURV="usd", RNG=6;
const FXN=PORT.fx.rate;
/* Nastepny rebalans liczony z danych, nie wpisany. Silnik trzyma rytm miesieczny,
   wiec kolejny okres to ten sam dzien miesiaca w nastepnym miesiacu. */
const MIES=["stycznia","lutego","marca","kwietnia","maja","czerwca","lipca",
  "sierpnia","września","października","listopada","grudnia"];
function nastepnyRebalans(){
  const ost=SIGNALS[0].date,d=new Date(ost+"T00:00:00Z");
  d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()+1);
  const dzien=Math.min(+ost.slice(8,10),new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0)).getUTCDate());
  d.setUTCDate(dzien);
  const dni=Math.round((d-new Date(new Date().toISOString().slice(0,10)+"T00:00:00Z"))/864e5);
  return {iso:d.toISOString().slice(0,10),dni,
    opis:`${d.getUTCDate()} ${MIES[d.getUTCMonth()]}`,
    kiedy:dni>1?`za ${dni} dni`:dni===1?"jutro":dni===0?"dzisiaj":`${-dni} dni temu`}}
const cur=()=>CURV==="usd"
  ? {v:VUSD,p:PUSD,u:"USD",alt:{v:VALUE,u:"zł"},r:RETC.usd,twr:PORT.twr.usd,k:x=>x}
  : {v:VALUE,p:PAID,u:"zł", alt:{v:VUSD, u:"USD"},r:RETC.pln,twr:PORT.twr.pln,k:x=>x/FXN};

/* duzy wykres kapitalu: sama krzywa i wypelnienie, bez siatki i osi */
chart("c-hero",W=>{
  const C=cur(),n=C.v.length,from=RNG?Math.max(0,n-RNG-1):0,V=C.v.slice(from),P=C.p.slice(from),M=MONTHS.slice(from);
  const m=V.length,nr=W<520,H=nr?170:210,T=14,B=26,L=4,R=4;
  const all=[...V,...P],lo=Math.min(...all),hi=Math.max(...all),pad=(hi-lo)*.14||1;
  const X=i=>L+(W-L-R)*(m>1?i/(m-1):.5),Y=v=>T+(H-T-B)*(1-(v-lo+pad)/(hi-lo+2*pad));
  const pa=a=>a.map((v,i)=>(i?"L":"M")+X(i).toFixed(1)+" "+Y(v).toFixed(1)).join(" ");
  const up=V.at(-1)>=V[0],col=up?CSS("--pos-soft2"):CSS("--neg");
  const hit=M.map((mm,i)=>({cx:X(i),html:`<div class="th">${mLbl(mm)}</div>
    <div class="tr">Wartość<span class="tv">${zl(V[i])} ${C.u}</span></div>
    <div class="tr">Wpłacone<span class="tv">${zl(P[i])} ${C.u}</span></div>`}));
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Wartosc portfela" data-hover='${HV({W,H,max:(W-L-R)/m,hit})}'>
    <defs><linearGradient id="hg" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="${col}" stop-opacity=".30"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    <path d="${pa(V)} L${X(m-1)} ${H-B} L${X(0)} ${H-B} Z" fill="url(#hg)"/>
    <path d="${pa(P)}" fill="none" stroke="${CSS("--line-strong")}" stroke-width="1.8" stroke-dasharray="5 5"/>
    <path d="${pa(V)}" fill="none" stroke="${col}" stroke-width="2.8" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${X(m-1)}" cy="${Y(V.at(-1))}" r="5" fill="${col}" stroke="${CSS("--bg")}" stroke-width="3"/>
    <line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="${CSS("--line-strong")}" style="opacity:0"/>
    <text x="${L}" y="${H-7}" fill="${CSS("--faint")}" font-size="${nr?11:12}">${mLbl(M[0])}</text>
    <text x="${W-R}" y="${H-7}" text-anchor="end" fill="${CSS("--faint")}" font-size="${nr?11:12}">${mLbl(M.at(-1))}</text>
  </svg>`});

function renderPulpit(){
  const C=cur(),V=C.v.at(-1),P=C.p.at(-1),zy=V-P;
  const from=RNG?Math.max(0,C.v.length-RNG-1):0;
  const okres=C.v.at(-1)-C.v[from]-(C.p.at(-1)-C.p[from]);
  const pct=C.v[from]?okres/C.v[from]*100:0;
  document.getElementById("heroVal").innerHTML=`${zl(V)}<span>${C.u}</span>`;
  document.getElementById("heroSub").innerHTML=
    `<span style="color:var(${okres>=0?"--pos":"--neg"})">${okres>=0?"+":"−"}${zl(okres)} ${C.u} · ${sg(pct)}%</span>`
    +` <em>${RNG?"w "+RNG+" mies.":"od początku"}</em>`;
  document.getElementById("heroAlt").textContent=`≈ ${zl(C.alt.v.at(-1))} ${C.alt.u}`;
  document.getElementById("heroStats").innerHTML=[
    ["Wpłacone",zl(P)+" "+C.u,"--muted"],
    ["Wynik",(zy>=0?"+":"−")+zl(zy)+" "+C.u,zy>=0?"--pos":"--neg"],
    ["TWR",sg2(C.twr)+"%",C.twr>=0?"--pos":"--neg"]
  ].map(([l,v,c])=>`<div><span>${l}</span><b style="color:var(${c})">${v}</b></div>`).join("");

  const R=nastepnyRebalans();
  document.getElementById("nextBox").innerHTML=
    `<div class="ico">${R.iso.slice(8,10)}</div><div><b>Najbliższy rebalans</b><span>${R.opis} · ostatni sygnał ${SIGNALS[0].date}</span></div>
     <div class="r"${R.dni<0?' style="color:var(--neg)"':""}>${R.kiedy}</div>`;

  renderAccounts();

  const HT=Object.values(HOLDINGS).reduce((a,b)=>a+b,0);
  document.getElementById("holdList").innerHTML=Object.entries(HOLDINGS).sort((a,b)=>b[1]-a[1]).map(([t,v])=>{
    const nm=t==="GOTOWKA"?"Gotówka":t;
    return `<div class="row"><div class="ic" style="background:${CSS(KOL[t]||"--s6")}">${nm.slice(0,2).toUpperCase()}</div>
      <div class="nm">${nm}<em>${t==="GOTOWKA"?"nieulokowane":(ROLE[t]||"")}</em></div>
      <div class="vl"><b>${zl(CURV==="usd"?v/FXN:v)} ${C.u}</b><span>${pc(v/HT)}</span></div></div>`}).join("");
}
document.getElementById("curTog").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b)return;
  document.querySelectorAll("#curTog button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));
  CURV=b.dataset.cur;renderPulpit();mount(charts.find(c=>c.id==="c-hero"));mount(charts.find(c=>c.id==="c-month"))});
document.getElementById("ranges").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b)return;
  document.querySelectorAll("#ranges button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));
  RNG=+b.dataset.r;renderPulpit();mount(charts.find(c=>c.id==="c-hero"))});

function renderActions(){
  const rows=[...new Set([...Object.keys(T25.out),...Object.keys(HOLDINGS)])].filter(t=>t!=="GOTOWKA")
    .map(t=>({t,want:T25.out[t]||0,d:(T25.out[t]||0)-(HOLDINGS[t]||0)*(1-CAPITAL.split10)}))
    .filter(r=>Math.abs(r.d)>=TOTAL*.02).sort((a,b)=>Math.abs(b.d)-Math.abs(a.d));
  document.getElementById("actions").innerHTML=rows.length?rows.map(r=>
    `<div class="act ${r.d>0?"buy":"sell"}"><i class="w"></i><div><div class="t">${r.d>0?"Kup":"Sprzedaj"} ${r.t}</div>
     <div class="sub">${ROLE[r.t]||""}</div></div><div class="q"><b>${zl(Math.abs(r.d))} zł</b>
     <span class="sub">cel ${zl(r.want)} zł</span></div></div>`).join("")
    :'<div class="act hold"><i class="w"></i><div><div class="t">Bez zmian</div></div></div>'}
function renderHist(){
  const R=nastepnyRebalans();
  document.getElementById("sigVal").innerHTML=`${R.kiedy}<span>do rebalansu</span>`;
  document.getElementById("sigAlt").textContent=`${R.opis} · ostatni sygnał z ${SIGNALS[0].date}`;
  document.getElementById("modeCards").innerHTML=[["BEST17",SIGNALS[0].best17,SIGNALS[0].best17.picks.join(" · ")||"gotówka"],
    ["GPM",SIGNALS[0].gpm,Object.keys(SIGNALS[0].gpm.weights).join(" · ")]].map(([n,L,txt])=>
    `<div class="legc"><div class="t">${n} <em>sygnał z ${SIGNALS[0].date}</em></div>
      <div class="n" style="font-size:1.6rem;color:var(${L.mode==="RISK"?"--pos":"--cash"})">${L.mode}</div>
      <div class="d">${esc(txt)}</div></div>`).join("");
  document.getElementById("histList").innerHTML=HIST.map(h=>
    `<div class="row"><div class="ic" style="background:${CSS(h[1]==="RISK"?"--pos":"--cash")}">${h[1]==="RISK"?"R":"C"}</div>
      <div class="nm">${h[0]}<em>${esc(h[4])}</em></div>
      <div class="vl"><b>${esc(h[2])}</b><span>GPM ${h[3]}</span></div></div>`).join("")}
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
    h+=`<h2 class="psec">${esc(a.name)} <span class="sub" style="font-weight:400">· ${accLegs(a)} · ${zl(cap)} zł</span></h2>`
      +tbl("<th>ETF</th><th>Kwota</th><th>Udział konta</th>",Object.entries(o).map(([t,v])=>
        `<tr><td><span class="sw-in" style="background:${CSS(KOL[t]||"--s6")}"></span>${t==="GOTOWKA"?"Gotówka":t}</td>
         <td class="num">${zl(v)}</td><td class="num">${pc(v/cap)}</td></tr>`).join(""))}
  return h}
const viewDat=()=>[[T10,SIGNALS[0]],[T25,SIGNALS[1]]].map(([T,s])=>
  `<h2 class="psec">Transza ${s.tranche}-tego <span class="sub" style="font-weight:400">· ${s.date}</span></h2>
   <div style="margin-bottom:11px">
     <div class="leg"><b>BEST17</b><span class="pill ${s.best17.mode==="RISK"?"p-risk":"p-cash"}">${s.best17.mode}</span><span class="as">${s.best17.picks.join(" · ")||"gotówka"}</span></div>
     <div class="leg"><b>GPM</b><span class="pill ${s.gpm.mode==="RISK"?"p-risk":"p-cash"}">${s.gpm.mode}</span><span class="as">${Object.keys(s.gpm.weights).join(" · ")}</span></div></div>`
  +tbl("<th>ETF</th><th>Kwota</th><th>Udział</th>",Object.entries(T.out).filter(([,v])=>v>.5).sort((a,b)=>b[1]-a[1]).map(([t,v])=>
    `<tr><td><span class="sw-in" style="background:${CSS(KOL[t]||"--s6")}"></span>${t==="GOTOWKA"?"Gotówka":t}</td>
     <td class="num">${zl(v)}</td><td class="num">${pc(v/(T.kB+T.kG))}</td></tr>`).join(""))).join("");
function renderSklad(m){document.getElementById("skladBody").innerHTML=m==="acc"?viewAcc():m==="dat"?viewDat():viewSum();fillSel()}
function renderAccounts(){
  const s=SETUPS[SETUP];
  document.getElementById("accCards").innerHTML=s.accounts.map(a=>{
    const o=accComp(a),cap=accTarget(a),d=a.value-cap,capo=Object.values(o).reduce((x,y)=>x+y,0);
    return `<div class="legc"><div class="t">${esc(a.name)} <em>${accLegs(a)}</em></div>
      <div class="n">${zl(CURV==="usd"?a.value/FXN:a.value)}<span>${CURV==="usd"?"USD":"zł"}</span></div>
      <div class="d">cel ${zl(CURV==="usd"?cap/FXN:cap)} · <span style="color:var(${Math.abs(d)<cap*.02?"--faint":"--warn"})">${d>=0?"+":"−"}${zl(CURV==="usd"?d/FXN:d)}</span></div>
      <div class="d">TWR <span style="color:var(${a.pln>=0?"--pos":"--neg"})">${sg(a.pln)}% PLN</span> · <span style="color:var(${a.usd>=0?"--pos":"--neg"})">${sg(a.usd)}% USD</span></div>
      <div class="bar">${Object.entries(o).map(([t,v])=>{const pr=v/capo*100;
        return `<span style="flex:${pr};background:${CSS(KOL[t]||"--s6")}" title="${t} ${pc(v/capo)}">${pr>13?(t==="GOTOWKA"?"GOT.":t):""}</span>`}).join("")}</div></div>`}).join("");
  document.getElementById("accNote").textContent=s.accounts.length===1
    ?"Jedno konto: obie nogi w jednej liście, pozycje wspólne w jednym zleceniu."
    :"Różnicę wobec celu wyrównujesz przy wpłacie, nie przelewem między brokerami.";
  const tot=Object.values(HOLDINGS).reduce((x,y)=>x+y,0);
  document.getElementById("driftList").innerHTML=[...new Set([...Object.keys(COMBINED),...Object.keys(HOLDINGS)])]
    .map(t=>{const hh=HOLDINGS[t]||0,w=COMBINED[t]||0;return {t,h:hh,w,d:hh-w,pp:(hh/tot-w/TOTAL)*100}})
    .sort((a,b)=>Math.abs(b.pp)-Math.abs(a.pp)).map(r=>{
      const nm=r.t==="GOTOWKA"?"Gotówka":r.t,c=Math.abs(r.pp)<1?"--faint":r.pp>0?"--warn":"--cash";
      return `<div class="row"><div class="ic" style="background:${CSS(KOL[r.t]||"--s6")}">${nm.slice(0,2).toUpperCase()}</div>
        <div class="nm">${nm}<em>mam ${zl(r.h)} · cel ${zl(r.w)} zł</em></div>
        <div class="vl"><b style="color:var(${c})">${r.d>=0?"+":"−"}${zl(r.d)} zł</b><span>${sg(r.pp)} pp</span></div></div>`}).join("");
  fillSel()}

function renderDiag(){
  const prz=SIG.diagnostics_source==="przykladowe";
  document.getElementById("diagWarn").innerHTML=prz
    ? `<div class="ostrz"><b>Ranking i kanarek na tym ekranie są przykładowe.</b>
       Silnik nie wystawia tej diagnostyki osobno, więc dopóki jej nie liczy, nie są to liczby z Twojej strategii.
       Skład w zakładce Sygnał jest prawdziwy.</div>` : "";
  document.getElementById("progi").innerHTML=[
    ["ok","XLK traci pozycję 1","przy spadku","−2,6%"],
    ["ok","DBC wypada z podium","przy spadku","−5,8%"],
    ["no","IAU wraca do gry","przy mom3 o","+1,9 pp"],
    ["nr","Kanarek przełącza w CASH","przy spadku VT i XLK o","−3,4%"],
  ].map(([s,t,o,w])=>
    `<div class="row"><div class="ic" style="background:${CSS(s==="ok"?"--pos":s==="no"?"--neg":"--s6")}">${s==="ok"?"✓":s==="no"?"!":"~"}</div>
      <div class="nm">${t}<em>${o}</em></div><div class="vl"><b>${w}</b></div></div>`).join("");
  document.getElementById("gpmInfo").innerHTML=[
    ["Ryzykowne w top 3","CNDX · CMOD · IUES"],["Przeszło filtr trendu","3 z 10"],
    ["Mianownik","5"],["Udział ochronny","40% · IBTA"],
  ].map(([t,w])=>`<div class="row" style="grid-template-columns:1fr auto">
      <div class="nm">${t}</div><div class="vl"><b>${w}</b></div></div>`).join("");
}

function renderWyniki(){
  document.getElementById("wynStamp").textContent=
    `${mLbl(SER[0].y+"-"+String(SER[0].m+1).padStart(2,"0"))} – ${mLbl(SER.at(-1).y+"-"+String(SER.at(-1).m+1).padStart(2,"0"))}`;
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
let ADMIN=false,EDIT=null,PIDX=null;  /* PIDX: ktora data jest ogladana; null = ostatnia */
let OVR={};try{OVR=JSON.parse(localStorage.getItem("ovr")||"{}")}catch(e){OVR={}}
const saveOVR=()=>{try{localStorage.setItem("ovr",JSON.stringify(OVR))}catch(e){}};
const okey=(t,d)=>t+"@"+d;
const eff=(t,i)=>{const P=PRICES[PTAB],o=OVR[okey(t,P.dates[i])];return o?o.v:P.px[t][i]};
const pidx=()=>PIDX==null?PRICES[PTAB].dates.length-1:PIDX;
const pdate=()=>PRICES[PTAB].dates[pidx()];
function renderCeny(){
  const P=PRICES[PTAB],last=pidx();
  document.getElementById("feedStamp").textContent=FEED.source+" · "+FEED.fetched;
  const chk=[];
  const brak=INSTR.filter(([t])=>eff(t,last)==null);
  chk.push([brak.length?"warn":"ok","Komplet instrumentów",(INSTR.length-brak.length)+"/"+INSTR.length]);
  chk.push(["ok","Data zgodna z regułą "+PTAB+"-tego",P.dates[last]]);
  const stale=last>0?INSTR.filter(([t])=>eff(t,last)===eff(t,last-1)).map(a=>a[0]):[];
  chk.push([stale.length?"warn":"ok",stale.length?"Cena bez zmian: "+stale.join(", "):"Brak zastoju cen",stale.length?"sprawdź":"OK"]);
  const jump=last>0?INSTR.filter(([t])=>Math.abs(eff(t,last)/eff(t,last-1)-1)>.25).map(a=>a[0]):[];
  chk.push([jump.length?"warn":"ok",jump.length?"Skok powyżej 25%: "+jump.join(", "):"Brak skoków powyżej 25%",jump.length?"sprawdź":"OK"]);
  const nov=Object.keys(OVR).length;
  chk.push([nov?"warn":"ok",nov?"Korekty ręczne w historii":"Brak korekt ręcznych",nov?nov+"":"0"]);
  const zle=chk.filter(c=>c[0]!=="ok").length;
  document.getElementById("feedCount").innerHTML=`${INSTR.length-brak.length} / ${INSTR.length}<span>instrumentów</span>`;
  document.getElementById("feedDate").innerHTML=zle
    ? `<span style="color:var(--warn)">${zle} ${zle===1?"ostrzeżenie":"ostrzeżenia"}</span> · ceny z ${P.dates[last]}`
    : `<span style="color:var(--pos)">bez zastrzeżeń</span> · ceny z ${P.dates[last]}`;
  document.getElementById("dStrip").innerHTML=P.dates.map((d,i)=>{
    const fix=INSTR.some(([t])=>OVR[okey(t,d)]);
    return `<button type="button" data-di="${i}" aria-pressed="${i===last}" class="${fix?"fix":""}">
      <b>${d.slice(8)}.${d.slice(5,7)}</b>${d.slice(0,4)}</button>`}).join("");
  document.getElementById("addHint").textContent=`Następny dzień wg reguły: ${nastepnaData()}`;
  rysujPrawoZapisu();
  document.getElementById("dPrev").disabled=last===0;
  document.getElementById("dNext").disabled=last===P.dates.length-1;
  document.querySelector(`#dStrip [data-di="${last}"]`)?.scrollIntoView({block:"nearest",inline:"center"});
  document.getElementById("checks").innerHTML=chk.map(([s,t,m])=>
    `<div class="row"><div class="ic" style="background:${CSS(s==="ok"?"--pos":"--warn")}">${s==="ok"?"✓":"!"}</div>
      <div class="nm">${esc(t)}</div><div class="vl"><b>${esc(m)}</b></div></div>`).join("");

  document.getElementById("priceList").innerHTML=INSTR.map(([t,mk])=>{
    const d=P.dates[last],o=OVR[okey(t,d)],v=eff(t,last),ch=last>0?(v/eff(t,last-1)-1)*100:null;
    if(EDIT===t)return `<div class="row" style="grid-template-columns:1fr"><form class="form" id="ovrForm" style="grid-template-columns:1fr 2fr;align-items:end">
      <div class="fld"><label for="ovrV">Cena ${t}</label><input type="number" id="ovrV" step="0.0001" value="${v}" required></div>
      <div class="fld"><label for="ovrR">Powód korekty</label><input type="text" id="ovrR" placeholder="np. zły kurs z feedu" required></div>
      <div class="fld"><button class="btn" type="submit">Zapisz</button></div>
      <div class="fld"><button class="btn" type="button" data-cancel style="background:var(--surface2);color:var(--muted)">Anuluj</button></div>
    </form></div>`;
    return `<div class="row"><div class="ic" style="background:${CSS(KOL[t]||"--s6")}">${t.slice(0,2)}</div>
      <div class="nm">${t}<em>${mk==="US"?"sygnał":"wykonanie"} · ${d}${o?` · <span style="color:var(--cash)">skorygowane</span>`:""}</em></div>
      <div class="vl" style="display:flex;align-items:center;gap:12px"><div><b>${px(v)}</b>
        <span style="color:${ch==null?"var(--faint)":ch>=0?"var(--pos)":"var(--neg)"}">${ch==null?"—":sg(ch)+"%"}</span></div>
        ${ADMIN?`<button class="del" data-edit="${t}" style="font-size:.8rem">zmień</button>`:""}
        ${ADMIN&&o?`<button class="del" data-undo="${t}">×</button>`:""}</div></div>`}).join("")}

/* nastepna data wedlug reguly: pierwsza sesja N-tego lub pozniej w kolejnym miesiacu */
function nastepnaData(){
  const P=PRICES[PTAB],ost=P.dates.at(-1),d=new Date(ost+"T00:00:00Z");
  d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()+1);
  return ruleDate(d.getUTCFullYear(),d.getUTCMonth(),+PTAB)}

function rysujFormularz(){
  const P=PRICES[PTAB],ost=P.dates.length-1;
  document.getElementById("addForm").innerHTML=
    `<div class="hd"><label for="adData">Data</label><input type="date" id="adData" value="${nastepnaData()}">
       <span class="note">Podpowiedziana z reguły ${PTAB}-tego. Przy każdym polu poprzednia cena — literówka rzuci się w oczy.</span></div>
     <div class="pgrid">${INSTR.map(([t,mk])=>
       `<label class="pf"><b>${t}<em>${mk==="US"?"sygnał":"wykon."}</em></b>
         <input type="number" step="0.0001" min="0" data-t="${t}" placeholder="${px(eff(t,ost))}"></label>`).join("")}</div>
     <div class="foot"><button class="btn" id="adSave">Zapisz dzień</button>
       <button class="btn" id="adCancel" style="background:var(--surface2);color:var(--muted)">Anuluj</button>
       <span class="note" id="adMsg"></span></div>`}

function rysujPrawoZapisu(){
  const b=document.getElementById("addDay"),h=document.getElementById("addHint");
  if(!b)return;
  const moze=!FB||ADMIN_BAZA;
  b.disabled=!moze;b.style.opacity=moze?"":"0.45";b.style.cursor=moze?"":"default";
  if(FB&&USER&&!ADMIN_BAZA)h.textContent="Podgląd — wpisywanie cen wymaga uprawnień admina.";
  else if(FB&&!USER)h.textContent="Zaloguj się, żeby zapisywać ceny w bazie.";
}
document.getElementById("addDay").addEventListener("click",()=>{
  const f=document.getElementById("addForm");
  if(!f.hidden){f.hidden=true;return}
  rysujFormularz();f.hidden=false;f.scrollIntoView({block:"nearest"})});

document.getElementById("addForm").addEventListener("click",e=>{
  if(e.target.id==="adCancel"){document.getElementById("addForm").hidden=true;return}
  if(e.target.id!=="adSave")return;
  const data=document.getElementById("adData").value;
  const pola=[...document.querySelectorAll("#addForm input[data-t]")];
  const P=PRICES[PTAB],ost=P.dates.length-1;
  let brak=0;const ceny={};
  for(const i of pola){
    const v=parseFloat(i.value);
    i.classList.toggle("zle",!(v>0));
    if(!(v>0)){brak++;continue}
    ceny[i.dataset.t]=v}
  const msg=document.getElementById("adMsg");
  if(brak){msg.innerHTML=`<span style="color:var(--warn)">Brakuje ${brak} z ${pola.length} cen. Sygnał liczony z niekompletnych danych byłby błędny.</span>`;return}
  if(!data){msg.innerHTML='<span style="color:var(--warn)">Podaj datę.</span>';return}
  if(P.dates.includes(data)){msg.innerHTML='<span style="color:var(--warn)">Ten dzień już jest. Popraw go na liście zamiast dopisywać drugi raz.</span>';return}
  /* skok powyzej 25% nie blokuje, ale musi byc powiedziany przed zapisem */
  const dziwne=INSTR.filter(([t])=>Math.abs(ceny[t]/eff(t,ost)-1)>.25).map(a=>a[0]);
  if(dziwne.length&&!msg.dataset.potw){
    msg.dataset.potw="1";
    msg.innerHTML=`<span style="color:var(--warn)">Skok powyżej 25%: ${dziwne.join(", ")}. Kliknij Zapisz ponownie, jeśli tak ma być.</span>`;return}
  delete msg.dataset.potw;
  P.dates.push(data);
  for(const[t]of INSTR)P.px[t].push(ceny[t]);
  P.man=P.man||{};P.man[data]=true;
  if(FB&&ADMIN_BAZA){
    FB.zapiszCeny(`${PTAB}_${data}`,{tranche:+PTAB,date:data,px:ceny,source:"reczne",
      author:USER?.email||USER?.uid||"admin",created_at:new Date().toISOString()})
      .catch(err=>{msg.innerHTML=`<span style="color:var(--warn)">Zapisane lokalnie, ale nie w bazie: ${esc(err.message)}</span>`});
  }
  const kol=P.dates.map((d,i)=>[d,i]).sort((a,b)=>a[0].localeCompare(b[0]));
  P.dates=kol.map(x=>x[0]);
  for(const[t]of INSTR)P.px[t]=kol.map(x=>P.px[t][x[1]]);
  zapiszReczne();
  PIDX=P.dates.indexOf(data);EDIT=null;
  document.getElementById("addForm").hidden=true;renderCeny()});

document.getElementById("segP").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b)return;
  document.querySelectorAll("#segP button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));
  PTAB=b.dataset.p;EDIT=null;PIDX=null;renderCeny()});
document.getElementById("segR").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b)return;
  document.querySelectorAll("#segR button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));
  ADMIN=b.dataset.r==="1";EDIT=null;renderCeny()});
document.getElementById("dStrip").addEventListener("click",e=>{
  const b=e.target.closest("[data-di]");if(!b)return;PIDX=+b.dataset.di;EDIT=null;renderCeny()});
document.getElementById("dPrev").addEventListener("click",()=>{PIDX=Math.max(0,pidx()-1);EDIT=null;renderCeny()});
document.getElementById("dNext").addEventListener("click",()=>{PIDX=Math.min(PRICES[PTAB].dates.length-1,pidx()+1);EDIT=null;renderCeny()});
document.getElementById("priceList").addEventListener("click",e=>{
  const ed=e.target.closest("[data-edit]"),un=e.target.closest("[data-undo]"),ca=e.target.closest("[data-cancel]");
  if(ed){EDIT=ed.dataset.edit;renderCeny();document.getElementById("ovrV")?.focus()}
  else if(un){delete OVR[okey(un.dataset.undo,pdate())];saveOVR();
    if(FB&&ADMIN_BAZA)FB.usunKorekte(`${PTAB}_${pdate()}_${un.dataset.undo}`).catch(()=>{});
    renderCeny()}
  else if(ca){EDIT=null;renderCeny()}});
document.getElementById("priceList").addEventListener("submit",e=>{
  e.preventDefault();
  const klucz=okey(EDIT,pdate()),wpis={v:parseFloat(document.getElementById("ovrV").value),
    r:document.getElementById("ovrR").value,who:USER?.email||"admin",
    when:new Date().toISOString().slice(0,16).replace("T"," ")};
  OVR[klucz]=wpis;saveOVR();
  if(FB&&ADMIN_BAZA)FB.zapiszKorekte(`${PTAB}_${pdate()}_${EDIT}`,
    {value:wpis.v,reason:wpis.r,author:wpis.who,created_at:wpis.when})
    .catch(err=>console.warn("korekta nie trafila do bazy:",err.message));
  EDIT=null;renderCeny()});

/* ---- transakcje ---- */
let TX=[];
try{TX=JSON.parse(localStorage.getItem("tx")||"[]")}catch(e){TX=[]}
if(!TX.length)TX=[{d:"2026-11-20",a:"LYNX",t:"wplata",k:10000},{d:"2026-11-20",a:"LYNX",t:"kupno",w:"IUIT",k:10000},
  {d:"2026-09-15",a:"XTB",t:"wplata",k:15000},{d:"2026-09-16",a:"XTB",t:"kupno",w:"IBTA",k:15000}];
const saveTX=()=>{try{localStorage.setItem("tx",JSON.stringify(TX))}catch(e){}};
/* Zalogowany trzyma transakcje w bazie - przezywaja zmiane urzadzenia.
   Niezalogowany zostaje przy przegladarce, zeby prototyp dalo sie klikac. */
async function wczytajTXzBazy(){
  try{
    const z=await FB.wczytaj(USER.uid,"transactions");
    TX=z.map(r=>({id:r.id,d:r.d,a:r.a,t:r.t,w:r.w,k:r.k}));
  }catch(e){console.warn("nie udalo sie wczytac transakcji:",e.message)}
  renderTX();
}
async function dodajTX(r){
  r.id=r.id||(r.d+"_"+Date.now().toString(36));
  TX.push(r);
  if(USER){try{await FB.zapisz(USER.uid,"transactions",r.id,r)}catch(e){alert("Nie zapisano w bazie: "+e.message)}}
  else saveTX();
  renderTX();
}
async function usunTX(i){
  const r=TX[i];TX.splice(i,1);
  if(USER&&r?.id){try{await FB.usun(USER.uid,"transactions",r.id)}catch(e){console.warn(e.message)}}
  else saveTX();
  renderTX();
}
const TYP={wplata:"Wpłata",wyplata:"Wypłata",kupno:"Kupno",sprzedaz:"Sprzedaż"};
function fillAccSelect(){
  const s=document.getElementById("txAcc"),cur=s.value;
  s.innerHTML=SETUPS[SETUP].accounts.map(a=>`<option>${esc(a.name)}</option>`).join("");
  if([...s.options].some(o=>o.value===cur))s.value=cur}
const TXI={wplata:["↓","--pos"],wyplata:["↑","--cash"],kupno:["+","--s1"],sprzedaz:["−","--s2"]};
function renderTX(){
  TX.sort((a,b)=>b.d.localeCompare(a.d));
  document.getElementById("txCount").textContent=TX.length+" "+(TX.length===1?"rekord":TX.length<5?"rekordy":"rekordów");
  document.getElementById("txList").innerHTML=TX.length?TX.map((r,i)=>{
    const[sym,c]=TXI[r.t];
    return `<div class="row"><div class="ic" style="background:${CSS(c)}">${sym}</div>
      <div class="nm">${TYP[r.t]}${r.w?" "+esc(r.w):""}<em>${r.d} · ${esc(r.a)}</em></div>
      <div class="vl" style="display:flex;align-items:center;gap:10px"><b>${zl(r.k)} zł</b>
        <button class="del" data-del="${i}" aria-label="Usuń rekord z ${r.d}">×</button></div></div>`}).join("")
    :'<div class="empty">Brak rekordów. Dopisz pierwszy powyżej.</div>';
  const acc={};
  for(const r of TX){acc[r.a]=acc[r.a]||{in:0,out:0};
    if(r.t==="wplata")acc[r.a].in+=r.k;if(r.t==="wyplata")acc[r.a].out+=r.k}
  const ks=Object.keys(acc);
  document.getElementById("depStats").innerHTML=ks.length
    ? ks.map(k=>`<div><span>${esc(k)}</span><b>${zl(acc[k].in-acc[k].out)} zł</b></div>`).join("")
      +`<div><span>Razem</span><b style="color:var(--accent)">${zl(ks.reduce((s,k)=>s+acc[k].in-acc[k].out,0))} zł</b></div>`
    :'<div><span>Brak wpłat</span><b>—</b></div>'}
document.getElementById("txType").addEventListener("change",e=>{
  document.getElementById("txTickWrap").hidden=!(e.target.value==="kupno"||e.target.value==="sprzedaz")});
document.getElementById("txForm").addEventListener("submit",e=>{
  e.preventDefault();
  const t=document.getElementById("txType").value,trade=t==="kupno"||t==="sprzedaz";
  dodajTX({d:document.getElementById("txDate").value,a:document.getElementById("txAcc").value,t,
    w:trade?document.getElementById("txTick").value:null,
    k:parseFloat(document.getElementById("txAmt").value)||0});
  e.target.reset();
  document.getElementById("txDate").value=new Date().toISOString().slice(0,10);
  document.getElementById("txTickWrap").hidden=true});
document.getElementById("txList").addEventListener("click",e=>{
  const b=e.target.closest("[data-del]");if(!b)return;
  usunTX(+b.dataset.del)});

/* ============ nawigacja ============ */
const VIEWS=["pulpit","sygnal","wyniki","transakcje","ceny","dlaczego"];
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
fillAccSelect();renderTX();renderPulpit();renderMatrix();renderActions();renderHist();renderSklad("sum");renderAccounts();renderWyniki();renderDiag();renderCeny();

legend("l-mix",KLASY.map(k=>[k[0],CSS(k[1])]));
legend("l-canary",[["VT",CSS("--s1")],["XLK",CSS("--s2")]]);
show(location.hash.slice(1)||"pulpit");

/* ============ konto ============ */
function rysujKonto(){
  const e=document.getElementById("konto");
  if(!FB){e.innerHTML='<span class="sub">baza niedostępna</span>';return}
  e.innerHTML=USER
    ? `<div class="kto"><b>${esc(USER.displayName||USER.email||"zalogowany")}</b>
        <span>${ADMIN_BAZA?"admin":"podgląd"}</span></div>
       <button type="button" class="cicho" id="btnWyloguj">Wyloguj</button>`
    : `<button type="button" id="btnZaloguj">Zaloguj przez Google</button>`;
}
function rysujUid(){
  const stare=document.getElementById("uidBox");if(stare)stare.remove();
  if(!USER||ADMIN_BAZA)return;
  const box=document.createElement("div");box.className="uid";box.id="uidBox";
  box.innerHTML=`Nie masz jeszcze praw zapisu. Wklej swój identyfikator do kolekcji
    <b>admins</b> w konsoli Firebase — dokument o tym id, zawartość dowolna.<code>${esc(USER.uid)}</code>`;
  document.querySelector("#v-pulpit .hero").after(box);
}
document.addEventListener("click",async e=>{
  if(e.target.id==="btnZaloguj"){
    try{await FB.zalogujGoogle()}catch(err){alert("Logowanie nie powiodło się: "+err.message)}}
  else if(e.target.id==="btnWyloguj"){await FB.wyloguj()}});

if(FB)FB.naZmianeKonta(async u=>{
  USER=u;
  ADMIN_BAZA=u?await FB.czyAdmin(u.uid):false;
  rysujKonto();rysujUid();rysujPrawoZapisu();
  if(u){await wczytajTXzBazy();await wczytajCenyZBazy()} else renderTX();
});
rysujKonto();
