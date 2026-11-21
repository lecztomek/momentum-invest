
/* Dane przychodza z plikow JSON w docs/data/ - to jest kontrakt miedzy
   pipeline'em (GitHub Actions zapisuje te pliki) a ta strona (tylko je czyta).
   Modul + top-level await: reszta pliku wykonuje sie dopiero po wczytaniu. */
/* Logowanie i baza sa opcjonalne: dane publiczne ida z plikow JSON w repo,
   wiec brak Firebase nie moze zatrzymac strony. */
let FB=null;
try{ FB=await import("./fb.js") }catch(e){ console.warn("Firebase niedostepny:",e.message) }
let USER=null, ADMIN_BAZA=false;
/* Niezalogowany oglada strategie i nic poza tym: zadnego portfela i zadnego
   zapisu. Portfel to dane konkretnej osoby, wiec bez konta nie ma czego
   pokazac - a udawanie, ze cos sie zapisalo "lokalnie", tylko myli. */
const ZAL=()=>!!USER;
const TYLKO_ZALOGOWANY=["pulpit","transakcje"];

let SIG,PERF,PRC,PORT=null;
try{
  [SIG,PERF,PRC]=await Promise.all(["signals","performance","prices"]
    .map(f=>fetch(`web/data/${f}.json`).then(r=>{if(!r.ok)throw new Error(f+".json: HTTP "+r.status);return r.json()})));
}catch(err){
  document.body.innerHTML='<div class="fatal"><b>Nie udalo sie wczytac danych.</b>'
    +'<p>'+String(err.message||err)+'</p><p>Strona czyta pliki przez fetch, wiec musi byc '
    +'serwowana przez HTTP. Otworz ja przez GitHub Pages albo lokalnie: '
    +'<code>python3 -m http.server</code> w katalogu glownym repo.</p></div>';
  throw err;
}
const SIGNALS=SIG.signals, HIST=SIG.history, ORDER=SIG.universe, ROLE=SIG.roles;
/* Kazda transza ma wlasny dzien rebalansu, wlasny sygnal i wlasna diagnostyke -
   ekran Analizy pokazuje jedna naraz, przelacznik wybiera ktora. */
const TRN=(SIG.tranches||[10,25]).map(String);
let DTAB=TRN[0];
const D=()=>SIG.diagnostics[DTAB];
/* Dane konta sa wlasnoscia uzytkownika i licza sie WYLACZNIE z jego wpisow.
   Nie ma zadnego "przykladowego portfela" - panel, ktory pokazuje wymyslone
   48 680 USD, jest gorszy niz panel, ktory mowi "nie wiem, ile masz".
   BRAK = nie ma ani jednego wpisu stanu konta, wiec kwot nie pokazujemy wcale,
   a sklad docelowy idzie w procentach. */
let CAPITAL,HOLDINGS,MONTHS,VALUE,PAID,VUSD,PUSD,RETC,FXN,BRAK=true,ZLOZONE=false,WPISY=false;
function ustawPortfel(P){
  PORT=P;BRAK=!P;
  if(P){
    CAPITAL=P.capital;HOLDINGS=P.holdings;MONTHS=P.months;VALUE=P.value;PAID=P.paid;
    VUSD=P.value_usd;PUSD=P.paid_usd;RETC=P.returns;FXN=P.fx.rate;
  }else{
    /* 100 + 100 = "sto procent kazdej nogi" - te same wzory licza wtedy udzialy
       zamiast zlotowek, a formatowanie pilnuje, zeby nikt nie wzial ich za kwote. */
    CAPITAL={best17:100,gpm:100,split10:.5};HOLDINGS={};MONTHS=[];VALUE=[];PAID=[];
    VUSD=[];PUSD=[];RETC={usd:[],pln:[]};FXN=WPISY?kursTeraz():KURS;   /* przy starcie wpisow jeszcze nie ma */
  }
  if(ZLOZONE)przeliczTransze();   /* przy pierwszym wywolaniu transz jeszcze nie ma */
}
/* Kurs do przeliczenia na zlote. Jedna liczba dla calej historii - to jest
   uproszczenie i panel tak to podpisuje. */
let KURS=4.06;
try{const k=parseFloat(localStorage.getItem("kurs"));if(k>0)KURS=k}catch(e){}
ustawPortfel(null);
const RET=PERF.monthly;
const INSTR=PRC.instruments, FEED=PRC.feed;
const COMPO=SIG.composition;

/* Wlasne grupowanie: pl-PL nie grupuje liczb czterocyfrowych (minimumGroupingDigits=2),
   wiec "7640" staloby obok "197 640" i kolumna liczb przestawalaby sie zgadzac wzrokowo. */
const zl=n=>String(Math.round(Math.abs(n))).replace(/\B(?=(\d{3})+(?!\d))/g," ");
const pc=n=>(n*100).toFixed(1).replace(".",",")+"%";
const sg=n=>(n>=0?"+":"−")+Math.abs(n).toFixed(1).replace(".",",");
const sg2=n=>(n>=0?"+":"−")+Math.abs(n).toFixed(2).replace(".",",");
const px=n=>n.toFixed(n<20?4:2).replace(".",",");
const CSS=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
/* Wszystkie kwoty w kodzie sa w USD (bo w USD sa wpisy i notowania). Ta funkcja
   jest JEDYNYM miejscem, w ktorym robi sie z nich zlotowki. */
const kw=v=>CURV==="usd"?zl(v)+" USD":zl(v*FXN)+" zł";
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

/* ============ ceny: to, czym liczyl silnik ============
   Nic tu nie generujemy. px to notowanie z sesji (null = tego dnia gielda tego
   waloru byla zamknieta), used to liczba, z ktora silnik naprawde pracowal
   (interpolacja), asof to dzien, z ktorego pochodzi kurs - potrafi byc inny niz
   data kolumny, bo nogi US i UK maja rozne swieta. */
const PRICES=Object.fromEntries(Object.entries(PRC.series).map(([k,s])=>
  [k,{dates:[...s.dates],px:Object.fromEntries(Object.entries(s.px).map(([t,v])=>[t,[...v]])),
      used:s.used,asof:s.asof}]));
/* dni wpisane recznie doklejaja sie do szeregu z feedu */
try{
  const r=JSON.parse(localStorage.getItem("recz")||"{}");
  for(const tab of ["10","25"])for(const d of (r[tab]||[])){
    const P=PRICES[tab];if(P.dates.includes(d.data))continue;
    P.dates.push(d.data);
    for(const[t]of INSTR)P.px[t].push(d.ceny[t]??null);
  }
}catch(e){}
async function wczytajKursyZBazy(){
  if(!FB||!USER)return;
  try{
    const z=await FB.wczytajKursy();
    KURSY=z.map(r=>({id:r.id,d:r.d,k:+r.k})).filter(r=>r.d&&r.k>0);
    zapiszKursyLokalnie();
  }catch(e){console.warn("kursy z bazy:",e.message)}
  poWpisach();
}
async function dodajKurs(d,k){
  const r={id:d,d,k};
  if(!mozeKursy()){alert("Kursy wpisuje admin.");return}
  KURSY=KURSY.filter(x=>x.d!==d).concat(r);
  zapiszKursyLokalnie();
  try{await FB.zapiszKurs(d,{d,k})}catch(e){alert("Nie zapisano kursu w bazie: "+e.message)}
  poWpisach();
}
async function usunKurs(d){
  if(!mozeKursy())return;
  KURSY=KURSY.filter(x=>x.d!==d);
  zapiszKursyLokalnie();
  try{await FB.usunKurs(d)}catch(e){console.warn(e.message)}
  poWpisach();
}
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
/* Sklad docelowy zalezy od kapitalu, a kapital od wpisow usera - wiec liczy sie
   na nowo za kazdym razem, gdy wpisy sie zmienia (ustawPortfel). */
let T10,T25,TOTAL,COMBINED,LEG;
function przeliczTransze(){
  T10=tranche(SIGNALS[0],CAPITAL.split10);T25=tranche(SIGNALS[1],1-CAPITAL.split10);
  TOTAL=CAPITAL.best17+CAPITAL.gpm;
  COMBINED={};
  for(const t of[...ORDER,"GOTOWKA"]){const v=(T10.out[t]||0)+(T25.out[t]||0);if(v>.5)COMBINED[t]=v}
  LEG={best17:{},gpm:{}};
  for(const T of[T10,T25]){
    for(const[t,v]of Object.entries(T.best17))LEG.best17[t]=(LEG.best17[t]||0)+v;
    for(const[t,v]of Object.entries(T.gpm))LEG.gpm[t]=(LEG.gpm[t]||0)+v;
    LEG.best17.GOTOWKA=(LEG.best17.GOTOWKA||0)+T.cashB;LEG.gpm.GOTOWKA=(LEG.gpm.GOTOWKA||0)+T.cashG}
}
przeliczTransze();ZLOZONE=true;

/* Uklady przykladowe - widoczne, dopoki user nie ma wlasnych wpisow. */
const UKLADY_PRZYKLAD={
  rozdzielnie:{label:"2 konta",accounts:[
    {name:"LYNX",alloc:{best17:1,gpm:0},value:99180,pln:4.15,usd:-.91},
    {name:"XTB",alloc:{best17:0,gpm:1},value:98460,pln:2.28,usd:-2.77}]},
  jedno:{label:"1 konto",accounts:[
    {name:"Konto główne",alloc:{best17:1,gpm:1},value:197640,pln:3.21,usd:-1.84}]},
  porowno:{label:"Po równo",accounts:[
    {name:"Broker A",alloc:{best17:.5,gpm:.5},value:99400,pln:3.30,usd:-1.75},
    {name:"Broker B",alloc:{best17:.5,gpm:.5},value:98240,pln:3.12,usd:-1.93}]}};
const SETUPS={...UKLADY_PRZYKLAD};
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
  renderSklad()});

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

/* Miks klas to historia STRATEGII, nie portfela - idzie z performance.json,
   ktore liczy silnik, i ma wlasna os czasu (okresy rebalansu obu transz). */
const KLASY=PERF.classes, MIX=PERF.mix, MIXM=PERF.mix_months;
chart("c-mix",W=>{
  const od=MIXM.length-odcinek(MIXM.length,1);
  const MIXM_=MIXM.slice(od),MIX_=MIX.slice(od);
  const nr=W<460,H=nr?220:260,L=nr?34:40,R=10,T=12,B=28,n=MIXM_.length,f=FS(W);
  const X=i=>L+(W-L-R)*i/(n-1),Y=p=>T+(H-T-B)*(1-p/100);
  const cum=MIX_.map(r=>{let a=0;return r.map(v=>a+=v)});
  let paths="";
  for(let s=KLASY.length-1;s>=0;s--){
    const d=cum.map((r,i)=>(i?"L":"M")+X(i).toFixed(1)+" "+Y(r[s]).toFixed(1)).join(" ")+` L${X(n-1)} ${Y(0)} L${X(0)} ${Y(0)} Z`;
    paths+=`<path d="${d}" fill="${CSS(KLASY[s][1])}" stroke="${CSS("--surface")}" stroke-width="2" stroke-linejoin="round"/>`}
  let g="";for(let p=0;p<=100;p+=25)g+=`<text x="${L-7}" y="${Y(p)+4}" text-anchor="end" fill="${CSS("--faint")}" font-size="${f}">${p}</text>`;
  const kr=Math.max(1,Math.round(n/(nr?4:6)));
  let xl="";for(let i=0;i<n;i+=kr)xl+=`<text x="${X(i)}" y="${H-8}" text-anchor="middle" fill="${CSS("--faint")}" font-size="${f}">${mLbl(MIXM_[i])}</text>`;
  const hit=MIXM_.map((m,i)=>({cx:X(i),html:`<div class="th">${mLbl(m)}</div>`+KLASY.map((k,s)=>MIX_[i][s]?
    `<div class="tr"><span class="sw" style="background:${CSS(k[1])}"></span>${k[0]}<span class="tv">${MIX_[i][s]}%</span></div>`:"").join("")}));
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Udział klas aktywów w czasie" data-hover='${HV({W,H,max:(W-L-R)/n,hit})}'>
    ${g}${paths}<line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="${CSS("--fg")}" style="opacity:0"/>${xl}</svg>`});

/* Porownanie z rynkiem. Benchmarki to UK-listowane ETF-y klasy Acc - te same,
   ktore user realnie kupuje - wiec licza dywidendy w NAV. Benchmark zaczynajacy
   sie pozniej startuje od wartosci strategii z tamtego dnia, zeby dalo sie
   porownac ksztalt, a nie tylko poziom. */
const CMP=PERF.compare, BENCH=PERF.benchmarks||[];
const CMPK=[{key:"strategy",label:"BEST17 + GPM",col:"--accent"},
  ...BENCH.map((b,i)=>({key:b.key,label:b.label,col:["--s2","--s5","--s3"][i]||"--s6"}))];
chart("c-cmp",W=>{
  /* Przy wybranym zakresie KAZDA seria startuje od x1 - wtedy koniec krzywej
     czyta sie wprost jako "tyle zarobil w tym okresie". Przy calej historii
     zostaje oryginalne polozenie, zeby bylo widac, ze benchmark o krotszej
     historii doklada sie pozniej, a nie od poczatku. */
  const od=CMP.dates.length-odcinek(CMP.dates.length,4.345);
  const daty=CMP.dates.slice(od);
  const SER_=Object.fromEntries(CMPK.map(k=>{
    const a=(CMP[k.key]||[]).slice(od);
    const baza=ZAKRES?(a.find(v=>v!=null)||1):1;
    return [k.key,a.map(v=>v==null?null:v/baza)]}));
  const n=daty.length,nr=W<460,H=nr?210:250,L=nr?34:42,R=10,T=14,B=28,f=FS(W);
  const wsz=CMPK.flatMap(k=>SER_[k.key]||[]).filter(v=>v!=null);
  const lo=Math.min(1,...wsz)*.98,hi=Math.max(...wsz)*1.03;
  const X=i=>L+(W-L-R)*i/(n-1),Y=v=>T+(H-T-B)*(1-(v-lo)/(hi-lo));
  const st=(hi-lo)/4;
  let g="";for(let v=Math.ceil(lo/st)*st;v<=hi;v+=st)
    g+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${CSS("--line")}"/><text x="${L-7}" y="${Y(v)+4}" text-anchor="end" fill="${CSS("--faint")}" font-size="${f}">×${v.toFixed(1).replace(".",",")}</text>`;
  let xl="",ost="";for(let i=0;i<n;i++){const y=ZAKRES&&ZAKRES<=12?daty[i].slice(0,7):daty[i].slice(0,4);
    if(y!==ost){ost=y;if(nr&&+y%2)continue;
      xl+=`<text x="${X(i)}" y="${H-8}" text-anchor="middle" fill="${CSS("--faint")}" font-size="${f}">${ZAKRES&&ZAKRES<=12?mLbl(y):y}</text>`}}
  let paths="";
  for(const k of CMPK){const a=SER_[k.key];if(!a)continue;
    let d="",otw=false;
    a.forEach((v,i)=>{if(v==null){otw=false;return}d+=(otw?"L":"M")+X(i).toFixed(1)+" "+Y(v).toFixed(1)+" ";otw=true});
    paths+=`<path d="${d}" fill="none" stroke="${CSS(k.col)}" stroke-width="${k.key==="strategy"?3:2}" stroke-linejoin="round"/>`}
  const hit=daty.map((d,i)=>({cx:X(i),html:`<div class="th">${d}</div>`
    +CMPK.map(k=>SER_[k.key]?.[i]==null?"":`<div class="tr"><span class="sw" style="background:${CSS(k.col)}"></span>${k.label}<span class="tv">×${SER_[k.key][i].toFixed(2).replace(".",",")}</span></div>`).join("")}));
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Strategia na tle rynku" data-hover='${HV({W,H,max:(W-L-R)/n,hit})}'>
    ${g}<line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="${CSS("--line-strong")}" style="opacity:0"/>${paths}${xl}</svg>`});

/* Obsuniecie liczone z DZIENNEJ krzywej kapitalu (silnik), probkowane tygodniowo -
   z miesiecznych zamkniec dolki wychodza plytsze, niz byly. */
const DD=PERF.drawdown;
/* Zakres wykresow na Wynikach. Jeden wspolny stan - ten sam przelacznik stoi
   pod kazdym wykresem, ktorego dotyczy, zeby bylo widac, co zmienia.
   Kafelki i tabela miesieczna zostaja na calej historii: CAGR czy MaxDD z
   trzech miesiecy to nie jest ta sama wielkosc i nie wolno ich mieszac. */
let ZAKRES=0;   /* w miesiacach; 0 = cala historia */
const ZAKRESY=[[3,"3M"],[6,"6M"],[12,"1R"],[36,"3L"],[0,"MAX"]];
function rysujZakresy(){
  const h=ZAKRESY.map(([m,l])=>
    `<button type="button" data-z="${m}" aria-pressed="${m===ZAKRES}">${l}</button>`).join("");
  document.querySelectorAll(".zakres").forEach(e=>e.innerHTML=h);
}
/* Ile ostatnich punktow zostawic przy danym zakresie (tygodnie albo miesiace). */
const odcinek=(n,naMiesiac)=>ZAKRES?Math.max(2,Math.min(n,Math.round(ZAKRES*naMiesiac))):n;
document.addEventListener("click",e=>{
  const b=e.target.closest(".zakres button");if(!b)return;
  ZAKRES=+b.dataset.z;rysujZakresy();
  for(const id of ["c-dd","c-cmp","c-mix"])mount(charts.find(c=>c.id===id));
});
chart("c-dd",W=>{
  const od=DD.dd.length-odcinek(DD.dd.length,4.345);
  const c=DD.dd.slice(od),daty=DD.dates.slice(od);
  const nr=W<460,H=nr?190:225,L=nr?40:48,R=10,T=12,B=28,n=c.length,f=FS(W);
  const lo=Math.floor(Math.min(...c)/5)*5-2;
  const X=i=>L+(W-L-R)*i/(n-1),Y=v=>T+(H-T-B)*(1-(v-lo)/(0-lo));
  const d=c.map((v,i)=>(i?"L":"M")+X(i).toFixed(1)+" "+Y(v).toFixed(1)).join(" ");
  let g="";for(let v=0;v>=lo;v-=5)g+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${CSS("--line")}"/><text x="${L-7}" y="${Y(v)+4}" text-anchor="end" fill="${CSS("--faint")}" font-size="${f}">${v}%</text>`;
  let xl="",ost="";for(let i=0;i<n;i++){const y=ZAKRES&&ZAKRES<=12?daty[i].slice(0,7):daty[i].slice(0,4);
    if(y!==ost){ost=y;if(nr&&+y%2)continue;
      xl+=`<text x="${X(i)}" y="${H-8}" text-anchor="middle" fill="${CSS("--faint")}" font-size="${f}">${ZAKRES&&ZAKRES<=12?mLbl(y):y}</text>`}}
  const mi=c.reduce((b,v,i)=>v<c[b]?i:b,0);
  const hit=c.map((v,i)=>({cx:X(i),html:`<div class="th">${daty[i]}</div>
    <div class="tr">Obsunięcie<span class="tv" style="color:${CSS("--neg")}">${v.toFixed(1).replace(".",",")}%</span></div>`}));
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Obsunięcie od szczytu" data-hover='${HV({W,H,max:(W-L-R)/n,hit})}'>
    <defs><linearGradient id="dg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${CSS("--neg")}" stop-opacity="0"/><stop offset="1" stop-color="${CSS("--neg")}" stop-opacity=".35"/></linearGradient></defs>
    ${g}${xl}<path d="${d} L${X(n-1)} ${Y(0)} L${X(0)} ${Y(0)} Z" fill="url(#dg)"/>
    <path d="${d}" fill="none" stroke="${CSS("--neg")}" stroke-width="2.5" stroke-linejoin="round"/>
    <line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="${CSS("--line-strong")}" style="opacity:0"/>
    <circle cx="${X(mi)}" cy="${Y(c[mi])}" r="5" fill="${CSS("--neg")}" stroke="${CSS("--surface")}" stroke-width="2.5"/>
    <text x="${X(mi)}" y="${Y(c[mi])+19}" text-anchor="middle" fill="${CSS("--neg")}" font-size="${f+1}" font-weight="700">${ZAKRES?"najgłębiej tu":"MaxDD"} ${c[mi].toFixed(1).replace(".",",")}%</text></svg>`});

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

const BRAK_SKLADU='<div class="empty">Nie wiem, co trzymasz. Przy stanie konta możesz rozpisać kwoty na walory — wtedy panel policzy, co dokupić, a co sprzedać.</div>';
chart("c-drift",W=>{
  const tot=Object.values(HOLDINGS).reduce((a,b)=>a+b,0);
  if(!tot)return BRAK_SKLADU;
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
      <div class="tr">Mam<span class="tv">${kw(r.have)}</span></div><div class="tr">Cel<span class="tv">${kw(r.want)}</span></div>`})});
  out+=`<text x="${C+8}" y="${rows.length*bh+24}" fill="${CSS("--faint")}" font-size="${f}">nadwaga →</text>`
    +`<text x="${C-8}" y="${rows.length*bh+24}" text-anchor="end" fill="${CSS("--faint")}" font-size="${f}">← niedowaga</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Odchylenie od składu docelowego" data-hover='${HV({W,H,max:1e9,hit})}'>${out}</svg>`});

/* Kanarek: skala i prog ida z danych (signals.json), nie z kodu - inaczej zmiana
   progu w strategii zostawilaby na wykresie stara, nieprawdziwa linie. */
chart("c-canary",W=>{
  const CAN=D().canary,CAN_VT=CAN.vt,CAN_XLK=CAN.xlk,CM=CAN.months,TH=CAN.threshold;
  const nr=W<460,H=nr?200:235,L=nr?38:46,R=10,T=12,B=28,n=CM.length,f=FS(W);
  const vs=[...CAN_VT,...CAN_XLK,TH],lo=Math.floor(Math.min(...vs)-1),hi=Math.ceil(Math.max(...vs)+1);
  const st=Math.max(1,Math.round((hi-lo)/5));
  const X=i=>L+(W-L-R)*i/(n-1),Y=v=>T+(H-T-B)*(1-(v-lo)/(hi-lo));
  const p=a=>a.map((v,i)=>(i?"L":"M")+X(i).toFixed(1)+" "+Y(v).toFixed(1)).join(" ");
  const zly=i=>CAN_VT[i]<=TH||CAN_XLK[i]<=TH;   /* max_bad_count = 0: wystarczy jeden */
  let g="";for(let v=Math.ceil(lo/st)*st;v<=hi;v+=st)g+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${CSS("--line")}"/><text x="${L-7}" y="${Y(v)+4}" text-anchor="end" fill="${CSS("--faint")}" font-size="${f}">${v}%</text>`;
  let xl="";for(let i=0;i<n;i+=nr?6:4)xl+=`<text x="${X(i)}" y="${H-8}" text-anchor="middle" fill="${CSS("--faint")}" font-size="${f}">${mLbl(CM[i])}</text>`;
  const hit=CM.map((m,i)=>({cx:X(i),html:`<div class="th">${mLbl(m)}</div>
    <div class="tr"><span class="sw" style="background:${CSS("--s1")}"></span>VT<span class="tv">${sg2(CAN_VT[i])}%</span></div>
    <div class="tr"><span class="sw" style="background:${CSS("--s2")}"></span>XLK<span class="tv">${sg2(CAN_XLK[i])}%</span></div>
    <div class="tr" style="color:${zly(i)?CSS("--cash"):CSS("--pos")}"><span class="sw" style="background:transparent"></span>Tryb<span class="tv">${zly(i)?"CASH":"RISK"}</span></div>`}));
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Kanarek wobec progu ${TH} procent" data-hover='${HV({W,H,max:(W-L-R)/n,hit})}'>
    ${g}<rect x="${L}" y="${Y(TH)}" width="${W-L-R}" height="${Math.max(0,H-B-Y(TH))}" fill="${CSS("--cash")}" opacity=".1"/>
    <line x1="${L}" x2="${W-R}" y1="${Y(TH)}" y2="${Y(TH)}" stroke="${CSS("--neg")}" stroke-width="2" stroke-dasharray="5 4"/>
    <text x="${W-R}" y="${Y(TH)-7}" text-anchor="end" fill="${CSS("--neg")}" font-size="${f}" font-weight="700">próg ${sg2(TH)}%</text>
    <line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="${CSS("--line-strong")}" style="opacity:0"/>
    <path d="${p(CAN_VT)}" fill="none" stroke="${CSS("--s1")}" stroke-width="2.5" stroke-linejoin="round"/>
    <path d="${p(CAN_XLK)}" fill="none" stroke="${CSS("--s2")}" stroke-width="2.5" stroke-linejoin="round"/>
    <circle cx="${X(n-1)}" cy="${Y(CAN_VT[n-1])}" r="5" fill="${CSS("--s1")}" stroke="${CSS("--surface")}" stroke-width="2.5"/>
    <circle cx="${X(n-1)}" cy="${Y(CAN_XLK[n-1])}" r="5" fill="${CSS("--s2")}" stroke="${CSS("--surface")}" stroke-width="2.5"/>${xl}</svg>`});

/* Ranking: etykieta "kupione" bierze sie z FAKTYCZNEJ wagi w sygnale, nie z miejsca
   w tabeli - selektor wybiera sposrod zdatnych, wiec top rankingu i top portfela to
   nie zawsze to samo. */
const STAN={ok:["",""],no:["ODCIĘTE","--line-strong"],nodata:["CZEKA NA KURS","--warn"],canary:["KANAREK","--s6"]};
chart("c-rank",W=>{
  const RANK=D().ranking,G=D().gate_threshold,bh=40,H=RANK.length*bh+34,L=58,R=14,f=FS(W);
  const vs=RANK.map(r=>r.score).concat([G,0]);
  const lo=Math.min(...vs,0),hi=Math.max(...vs)*1.18;
  const SX=v=>L+(W-R-L)*(v-lo)/(hi-lo||1),X0=SX(0);
  let out=`<line x1="${SX(G)}" x2="${SX(G)}" y1="4" y2="${RANK.length*bh+6}" stroke="${CSS("--neg")}" stroke-width="2" stroke-dasharray="5 4"/>`
    +`<text x="${SX(G)+6}" y="${RANK.length*bh+25}" fill="${CSS("--neg")}" font-size="${f}" font-weight="700">bramka ${sg2(G)}%</text>`;
  const hit=[];
  RANK.forEach((r,i)=>{
    const v=r.score,kup=r.weight>0,y=i*bh+9,h=22,[lab,lc]=STAN[r.gate]||["",""];
    const col=kup?CSS("--accent"):CSS(lc||"--s6"),x0=Math.min(X0,SX(v)),w=Math.max(2,Math.abs(SX(v)-X0));
    out+=`<rect x="${x0}" y="${y}" width="${w}" height="${h}" rx="5" fill="${col}"/>`
      +`<text x="${L-10}" y="${y+16}" text-anchor="end" fill="${CSS("--fg")}" font-size="${f+1.5}" font-weight="700">${r.t}</text>`
      +`<text x="${x0+w+8}" y="${y+16}" fill="${CSS("--muted")}" font-size="${f}" font-family="var(--f-mono)" font-weight="600">${sg2(v)}%</text>`
      +(kup?`<text x="${x0+9}" y="${y+16}" fill="#06201D" font-size="${f}" font-weight="700">KUPIONE · ${Math.round(r.weight*100)}%</text>`
           :lab?`<text x="${x0+9}" y="${y+16}" fill="${CSS(r.gate==="no"?"--neg":"--fg")}" font-size="${f}" font-weight="700">${lab}</text>`:"");
    hit.push({x0:0,x1:W,y0:y-5,y1:y+h+5,html:`<div class="th">${r.t}</div>
      <div class="tr">Kupujesz<span class="tv">${r.exec||r.t}</span></div>
      <div class="tr">Wynik<span class="tv">${sg2(v)}%</span></div>
      <div class="tr">Status<span class="tv">${kup?"kupione, "+Math.round(r.weight*100)+"%":{no:"odcięte bramką",nodata:"czeka na kurs",canary:"tylko kanarek"}[r.gate]||"poza podium"}</span></div>`})});
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
  if(BRAK)return "";
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
/* Nastepny rebalans liczony z danych, nie wpisany. Silnik trzyma rytm miesieczny,
   wiec kolejny okres to ten sam dzien miesiaca w nastepnym miesiacu. */
const MIES=["stycznia","lutego","marca","kwietnia","maja","czerwca","lipca",
  "sierpnia","września","października","listopada","grudnia"];
/* Dzien rebalansu bierzemy z numeru transzy, nie z daty sygnalu: realna data wykonania
   bywa pozniejsza (10-ty w niedziele => 11-ty), a regula i tak mowi "10-ty albo pierwsza
   sesja po nim". */
function rebalansDla(s){
  const d=new Date(s.date+"T00:00:00Z");
  d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()+1);
  d.setUTCDate(Math.min(s.tranche,new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0)).getUTCDate()));
  const dni=Math.round((d-new Date(new Date().toISOString().slice(0,10)+"T00:00:00Z"))/864e5);
  return {iso:d.toISOString().slice(0,10),dni,tranche:s.tranche,
    opis:`${d.getUTCDate()} ${MIES[d.getUTCMonth()]}`,
    kiedy:dni>1?`za ${dni} dni`:dni===1?"jutro":dni===0?"dzisiaj":`${-dni} dni temu`}}
/* Najblizszy z obu terminow - ale gdy oba juz minely (sygnal jest stary), pokazujemy
   ten BARDZIEJ przeterminowany, zeby zaleglosc rzucala sie w oczy, a nie chowala. */
function nastepnyRebalans(){
  const r=SIGNALS.map(rebalansDla).sort((a,b)=>a.dni-b.dni);
  return r.some(x=>x.dni>=0)?r.find(x=>x.dni>=0):r[0]}
const cur=()=>CURV==="usd"
  ? {v:VUSD,p:PUSD,u:"USD",alt:{v:VALUE,u:"zł"},r:RETC.usd,twr:PORT?.twr.usd??0,k:x=>x}
  : {v:VALUE,p:PAID,u:"zł", alt:{v:VUSD, u:"USD"},r:RETC.pln,twr:PORT?.twr.pln??0,k:x=>x*FXN};

/* duzy wykres kapitalu: sama krzywa i wypelnienie, bez siatki i osi */
chart("c-hero",W=>{
  if(BRAK)return "";
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
  const R0=nastepnyRebalans();
  document.getElementById("nextBox").innerHTML=
    `<div class="ico">${R0.iso.slice(8,10)}</div><div><b>Najbliższy rebalans</b><span>${R0.opis} · ostatni sygnał ${SIGNALS[0].date}</span></div>
     <div class="r"${R0.dni<0?' style="color:var(--neg)"':""}>${R0.kiedy}</div>`;
  /* Bez wpisow nie pokazujemy ZADNEJ kwoty - zamiast wymyslonego portfela
     jedno zdanie o tym, czego brakuje, i przycisk tam, gdzie to sie wpisuje. */
  document.getElementById("pulpitDane").hidden=BRAK;
  document.getElementById("pulpitPusty").hidden=!BRAK;
  document.getElementById("curTog").hidden=BRAK;
  if(BRAK){
    document.getElementById("pulpitPusty").innerHTML=
      `<div class="pusto"><b>Panel nie wie, ile masz na koncie.</b>
        <p>Sygnał, ceny i wyniki strategii są policzone przez silnik i są prawdziwe.
        Kapitał, wynik i „co dokupić” wymagają jednej rzeczy od Ciebie: wpisania stanu konta.</p>
        <a class="btn" href="#transakcje">Dopisz stan konta</a></div>`;
    return;
  }
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

  renderAccounts();

  const HT=Object.values(HOLDINGS).reduce((a,b)=>a+b,0);
  document.getElementById("holdList").innerHTML=!HT?BRAK_SKLADU:Object.entries(HOLDINGS).sort((a,b)=>b[1]-a[1]).map(([t,v])=>{
    const nm=t==="GOTOWKA"?"Gotówka":t;
    return `<div class="row"><div class="ic" style="background:${CSS(KOL[t]||"--s6")}">${nm.slice(0,2).toUpperCase()}</div>
      <div class="nm">${nm}<em>${t==="GOTOWKA"?"nieulokowane":(ROLE[t]||"")}</em></div>
      <div class="vl"><b>${kw(v)}</b><span>${pc(v/HT)}</span></div></div>`}).join("");
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
  document.getElementById("sygDane").hidden=BRAK;
  if(BRAK)return;
  if(!Object.keys(HOLDINGS).length){
    document.getElementById("actions").innerHTML=BRAK_SKLADU;return}
  const rows=[...new Set([...Object.keys(T25.out),...Object.keys(HOLDINGS)])].filter(t=>t!=="GOTOWKA")
    .map(t=>({t,want:T25.out[t]||0,d:(T25.out[t]||0)-(HOLDINGS[t]||0)*(1-CAPITAL.split10)}))
    .filter(r=>Math.abs(r.d)>=TOTAL*.02).sort((a,b)=>Math.abs(b.d)-Math.abs(a.d));
  document.getElementById("actions").innerHTML=rows.length?rows.map(r=>
    `<div class="act ${r.d>0?"buy":"sell"}"><i class="w"></i><div><div class="t">${r.d>0?"Kup":"Sprzedaj"} ${r.t}</div>
     <div class="sub">${ROLE[r.t]||""}</div></div><div class="q"><b>${kw(Math.abs(r.d))}</b>
     <span class="sub">cel ${kw(r.want)}</span></div></div>`).join("")
    :'<div class="act hold"><i class="w"></i><div><div class="t">Bez zmian</div></div></div>'}
/* Pasek skladu: segment na kazdy walor, podpis w srodku jesli sie miesci.
   To ma byc PIERWSZA rzecz widoczna na ekranie - odpowiedz na "co trzymac",
   a nie slowo RISK powtorzone cztery razy. */
function segmenty(sklad,suma){
  return Object.entries(sklad).filter(([,v])=>v/suma>.001).sort((a,b)=>b[1]-a[1]).map(([t,v])=>{
    const pr=v/suma*100;
    return `<span style="flex:${pr};background:${CSS(KOL[t]||"--s6")}" title="${t} ${pc(v/suma)}">${
      pr>9?(t==="GOTOWKA"?"GOT.":t)+(pr>13?`<em>${Math.round(pr)}%</em>`:""):""}</span>`}).join("");
}
const pasek=(sklad,suma,wys)=>`<div class="skladbar"${wys?` style="height:${wys}px"`:""}>${segmenty(sklad,suma)}</div>`;
function renderHist(){
  const R=nastepnyRebalans();
  document.getElementById("sigStamp").textContent="policzono "+(SIG.generated||"").slice(0,10);
  document.getElementById("sigNext").innerHTML=
    `<div class="ico">${R.iso.slice(8,10)}</div><div><b>Najbliższy rebalans</b><span>${R.opis} · transza ${R.tranche}-tego</span></div>
     <div class="r"${R.dni<0?' style="color:var(--neg)"':""}>${R.kiedy}</div>`;

  /* Sklad docelowy calosci - pasek plus lista z udzialami. */
  document.getElementById("skladBar").innerHTML=segmenty(COMBINED,TOTAL);
  const naj=Math.max(...Object.values(COMBINED));
  document.getElementById("skladLista").innerHTML=Object.entries(COMBINED)
    .sort((a,b)=>b[1]-a[1]).map(([t,v])=>{
      const nm=t==="GOTOWKA"?"Gotówka":t;
      return `<div class="row"><div class="ic" style="background:${CSS(KOL[t]||"--s6")}">${nm.slice(0,2).toUpperCase()}</div>
        <div class="nm">${nm}<em>${t==="GOTOWKA"?"nieulokowane":(ROLE[t]||"")}</em></div>
        <div class="vl" style="display:flex;align-items:center;gap:12px">
          <span class="udz"><i style="width:${v/naj*100}%;background:${CSS(KOL[t]||"--s6")}"></i></span>
          <div><b>${pc(v/TOTAL)}</b>${BRAK?"":`<span>${kw(v)}</span>`}</div></div></div>`}).join("");

  /* Transze maja wlasne dni rebalansu, wiec i wlasne sklady - jedna karta na
     transze, z trybem obu nog jako plakietka, a nie jako naglowek. */
  document.getElementById("modeCards").innerHTML=[[T10,SIGNALS[0]],[T25,SIGNALS[1]]].map(([T,s])=>
    `<div class="legc"><div class="t">Transza ${s.tranche}-tego <em>${s.date}</em></div>
      <div class="pills">
        <span class="pill ${s.best17.mode==="RISK"?"p-risk":"p-cash"}">BEST17 ${s.best17.mode}</span>
        <span class="pill ${s.gpm.mode==="RISK"?"p-risk":"p-cash"}">GPM ${s.gpm.mode}</span></div>
      ${pasek(T.out,T.kB+T.kG,38)}
      <div class="d">${Object.entries(T.out).filter(([,v])=>v/(T.kB+T.kG)>.001).sort((a,b)=>b[1]-a[1])
        .map(([t,v])=>`${t==="GOTOWKA"?"Gotówka":t} ${pc(v/(T.kB+T.kG))}`).join(" · ")}</div></div>`).join("");
  document.getElementById("histList").innerHTML=HIST.map(h=>
    `<div class="row"><div class="ic" style="background:${CSS(h[2]==="RISK"?"--pos":"--cash")}">${h[1]}</div>
      <div class="nm">${h[0]}<em>${esc(h[5])}</em></div>
      <div class="vl"><b>${esc(h[3])}</b><span>GPM ${h[4]}</span></div></div>`).join("")}
/* Bez wpisow pokazujemy UDZIALY, nie kwoty - kolumna "Kwota" liczona z
   wymyslonego kapitalu bylaby zwykla sciema. Udzial jest prawdziwy niezaleznie
   od tego, ile kto ma. */
const kwota=(v)=>BRAK?"":`<td class="num">${zl(v)}</td>`;
const kolKwota=BRAK?"":"<th>Kwota</th>";
function viewAcc(){
  if(!ZAL())return `<div class="pusto"><b>Podział na konta jest Twój, nie strategii.</b>
    <p>Strategia mówi, co trzymać i w jakich proporcjach — to widać wyżej. Na ile kont to
    rozbijesz i która noga wyląduje u którego brokera, to już Twoja sprawa i Twoje dane.</p>
    <button type="button" class="btn" data-login>Zaloguj się, żeby prowadzić portfel</button></div>`;
  if(BRAK)return `<div class="pusto"><b>Nie wiem, na których kontach to trzymasz.</b>
    <p>Dopisz stan każdego konta w zakładce Wpisy — najlepiej z rozbiciem na walory.
    Wtedy panel sam odczyta, która noga leży gdzie, i policzy cel dla każdego konta osobno.</p>
    <a class="btn" href="#transakcje">Dopisz stan konta</a></div>`;
  const s=SETUPS[SETUP];let h=`<div class="seg setupSel"></div>`;
  for(const a of s.accounts){
    const o=accComp(a),cap=accTarget(a);
    h+=`<h2 class="psec">${esc(a.name)} <span class="sub" style="font-weight:400">· ${accLegs(a)} · ${kw(cap)}</span></h2>`
      +tbl(`<th>ETF</th><th>${CURV==="usd"?"USD":"zł"}</th><th>Udział konta</th>`,Object.entries(o).map(([t,v])=>
        `<tr><td><span class="sw-in" style="background:${CSS(KOL[t]||"--s6")}"></span>${t==="GOTOWKA"?"Gotówka":t}</td>
         <td class="num">${zl(CURV==="usd"?v:v*FXN)}</td><td class="num">${pc(v/cap)}</td></tr>`).join(""))}
  return h}
/* Jedyny widok, ktorego nie ma wyzej: podzial miedzy KONTA. Sklad calosci
   i transz pokazuja paski w sekcji "Co trzymac" - powtarzanie go w tabelce
   tylko rozwadnialo ekran. */
function renderSklad(){document.getElementById("skladBody").innerHTML=viewAcc();fillSel()}
function renderAccounts(){
  const s=SETUPS[SETUP];
  document.getElementById("accCards").innerHTML=s.accounts.map(a=>{
    const o=accComp(a),cap=accTarget(a),d=a.value-cap,capo=Object.values(o).reduce((x,y)=>x+y,0);
    return `<div class="legc"><div class="t">${esc(a.name)} <em>${accLegs(a)}</em></div>
      <div class="n">${zl(CURV==="usd"?a.value:a.value*FXN)}<span>${CURV==="usd"?"USD":"zł"}</span></div>
      <div class="d">cel ${kw(cap)} · <span style="color:var(${Math.abs(d)<cap*.02?"--faint":"--warn"})">${d>=0?"+":"−"}${kw(Math.abs(d))}</span></div>
      <div class="d">TWR <span style="color:var(${a.pln>=0?"--pos":"--neg"})">${sg(a.pln)}% PLN</span> · <span style="color:var(${a.usd>=0?"--pos":"--neg"})">${sg(a.usd)}% USD</span></div>
      <div class="bar">${Object.entries(o).map(([t,v])=>{const pr=v/capo*100;
        return `<span style="flex:${pr};background:${CSS(KOL[t]||"--s6")}" title="${t} ${pc(v/capo)}">${pr>13?(t==="GOTOWKA"?"GOT.":t):""}</span>`}).join("")}</div></div>`}).join("");
  document.getElementById("accNote").textContent=s.accounts.length===1
    ?"Jedno konto: obie nogi w jednej liście, pozycje wspólne w jednym zleceniu."
    :"Różnicę wobec celu wyrównujesz przy wpłacie, nie przelewem między brokerami.";
  const tot=Object.values(HOLDINGS).reduce((x,y)=>x+y,0);
  document.getElementById("driftList").innerHTML=!tot?BRAK_SKLADU:[...new Set([...Object.keys(COMBINED),...Object.keys(HOLDINGS)])]
    .map(t=>{const hh=HOLDINGS[t]||0,w=COMBINED[t]||0;return {t,h:hh,w,d:hh-w,pp:(hh/tot-w/TOTAL)*100}})
    .sort((a,b)=>Math.abs(b.pp)-Math.abs(a.pp)).map(r=>{
      const nm=r.t==="GOTOWKA"?"Gotówka":r.t,c=Math.abs(r.pp)<1?"--faint":r.pp>0?"--warn":"--cash";
      return `<div class="row"><div class="ic" style="background:${CSS(KOL[r.t]||"--s6")}">${nm.slice(0,2).toUpperCase()}</div>
        <div class="nm">${nm}<em>mam ${kw(r.h)} · cel ${kw(r.w)}</em></div>
        <div class="vl"><b style="color:var(${c})">${r.d>=0?"+":"−"}${kw(Math.abs(r.d))}</b><span>${sg(r.pp)} pp</span></div></div>`}).join("");
  fillSel()}

function renderDiag(){
  const d=D(),RANK=d.ranking,CAN=d.canary;
  document.querySelectorAll("#segD button").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.d===DTAB)));
  /* Dwie rzeczy moga sprawic, ze to, co widac, nie jest sygnalem na dzis:
     okres, ktoremu brakuje notowania z dnia rebalansu (SIG.awaiting - taki okres w
     ogole nie jest publikowany), oraz bramka 3m bez kursu (d.pending). */
  const niepub=(SIG.awaiting||[]).filter(c=>String(c.tranche)===DTAB),cz=d.pending||[];
  document.getElementById("diagWarn").innerHTML=[
    niepub.length?`<div class="ostrz"><b>To diagnostyka sygnału z ${d.date}, nie z dzisiaj.</b>
      ${niepub.map(c=>`Okres ${c.period}: ${c.reason}.`).join(" ")}
      Dopóki brakuje notowań, nowszy sygnał nie jest liczony — zamiast zgadywać, panel pokazuje ostatni rozstrzygnięty.</div>`:"",
    cz.length?`<div class="ostrz"><b>Bramka 3-miesięczna dla ${cz.join(" i ")} nie ma kursu z dnia rebalansu.</b>
      Silnik traktuje wtedy te walory jako niezdatne — to brak danych, nie ocena momentum.</div>`:"",
  ].join("");
  document.getElementById("progi").innerHTML=d.progi.map(p=>
    `<div class="row"><div class="ic" style="background:${CSS(p.status==="ok"?"--pos":p.status==="no"?"--neg":"--s6")}">${p.status==="ok"?"✓":p.status==="no"?"!":"~"}</div>
      <div class="nm">${p.title}<em>${p.sub}</em></div><div class="vl"><b>${p.value}</b></div></div>`).join("");
  document.getElementById("gpmInfo").innerHTML=d.gpm_info
    .map(([t,w])=>`<div class="row" style="grid-template-columns:1fr auto">
      <div class="nm">${t}</div><div class="vl"><b>${w}</b></div></div>`).join("");

  const TH=CAN.threshold,ost=[["VT",CAN.vt.at(-1)],["XLK",CAN.xlk.at(-1)]],zle=ost.filter(([,v])=>v<=TH);
  document.getElementById("whyCanary").innerHTML=zle.length
    ? `${zle.map(([t,v])=>`<b>${t} ${sg2(v)}%</b>`).join(" i ")} na progu ${sg2(TH)}% lub niżej, więc <b>CASH</b>.
       Wystarczy jeden kanarek pod linią, żeby BEST17 wyszedł do gotówki.`
    : `${ost.map(([t,v])=>`<b>${t} ${sg2(v)}%</b>`).join(" i ")} są nad progiem ${sg2(TH)}%, więc <b>RISK</b>.
       Wystarczy, że <b>jeden</b> z nich spadnie na próg lub niżej, a BEST17 wychodzi do gotówki.`;

  const kup=RANK.filter(r=>r.weight>0),od=RANK.filter(r=>r.gate==="no"),nd=RANK.filter(r=>r.gate==="nodata");
  document.getElementById("whyRank").innerHTML=[
    kup.length?`Kupione: ${kup.map(r=>`<b>${r.exec||r.t} ${Math.round(r.weight*100)}%</b> (sygnał ${r.t})`).join(" i ")}.`
      :nd.length?`Skład nie jest jeszcze rozstrzygnięty — brakuje kursu z dnia rebalansu dla <b>${nd.map(r=>r.t).join(", ")}</b>.`
      :"Nic nie przeszło przez filtry — cała noga stoi w gotówce.",
    od.length?`Bramki 3-miesięcznej (${sg2(d.gate_threshold)}%) nie przeszło: <b>${od.map(r=>r.t).join(", ")}</b>.`:"",
    (kup.length&&nd.length)?`Czeka na kurs z dnia rebalansu: <b>${nd.map(r=>r.t).join(", ")}</b>.`:"",
  ].filter(Boolean).join(" ");
}

function renderWyniki(){
  document.getElementById("wynStamp").textContent=PERF.metrics.from+" – "+PERF.metrics.to;
  /* Podatek jest na tyle duzy, ze bez wyjasnienia liczby wygladaja na blad:
     x3,09 przed i x2,61 po to ta sama historia. */
  const pod=Math.round((PERF.tax_rate||0)*100),B=PERF.metrics_pre_tax;
  document.getElementById("podatekNota").innerHTML=!pod?"":
    `Liczby <b>po podatku ${pod}%</b>, liczonym tak, jak robi to silnik: raz w roku, od wzrostu ponad
     poprzedni szczyt (rok stratny nie daje zwrotu, ale nie kasuje szczytu).
     Przed podatkiem byłoby ${sg2(B.cagr*100)}% rocznie i ×${B.multiple.toFixed(2).replace(".",",")}.`;
  document.getElementById("mgridSub").textContent=PERF.monthly_pre_tax?"· przed podatkiem":"";
  /* Liczby z silnika, nie przeliczone z miesiecznej siatki: MaxDD i Sharpe licza
     sie z DZIENNEJ krzywej kapitalu, wiec obsuniecie w srodku miesiaca nie znika.
     Z samych miesiecy MaxDD wychodzil dwa razy plytszy niz byl naprawde. */
  const M=PERF.metrics;
  document.getElementById("tiles").innerHTML=[
    ["CAGR",sg2(M.cagr*100)+"%",PERF.pre_tax?"rocznie":"rocznie, po podatku","--pos"],
    ["MaxDD",(M.max_drawdown*100).toFixed(1).replace(".",",")+"%","dziennie, najgłębsze","--neg"],
    ["Calmar",M.calmar.toFixed(2).replace(".",","),"zysk do ryzyka","--fg"],
    ["Sharpe",M.sharpe.toFixed(2).replace(".",","),"rf = 0","--fg"],
    /* Lata biora sie z TEJ SAMEJ siatki, ktora user widzi nizej - inaczej kafelek
       i tabela pokazywalyby dla 2025 dwie rozne liczby (okresy transz vs rok
       kalendarzowy z dziennej krzywej). */
    ["Najgorszy rok",sg(STAT.worst)+"%","z "+STAT.yl.length+" lat","--neg"],
    ["Najlepszy rok",sg(STAT.best)+"%","","--pos"],
    ["Dodatnie miesiące",PERF.positive_months.toFixed(0)+"%",PERF.months+" miesięcy","--fg"],
    ["Pod wodą",M.max_time_underwater_months+" mies.","najdłużej","--warn"],
    ["Obrót",M.annual_turnover.toFixed(1).replace(".",",")+"×","rocznie","--muted"],
    ["Mnożnik","×"+M.multiple.toFixed(2).replace(".",","),PERF.pre_tax?"bez wpłat":"bez wpłat, po podatku","--accent"]
  ].map(([l,v,d,c])=>`<div class="tile"><div class="lbl">${l}</div><div class="v" style="color:var(${c})">${v}</div><div class="d">${d}</div></div>`).join("");
  const col=r=>{const a=Math.min(Math.abs(r)/6,1)*.55+.08;return `background:rgba(${r>=0?"12,163,12":"208,59,59"},${a.toFixed(2)})`};
  let h=`<thead><tr><th>Rok</th>${MN.map(m=>`<th>${m}</th>`).join("")}<th>Rok</th></tr></thead><tbody>`;
  for(const y of Object.keys(RET).sort()){
    const yv=STAT.yl.find(a=>a[0]===+y)[1];
    /* spread, nie r.map: tablica rzadka gubi w map puste sloty i przesuwa miesiace o kolumne */
    h+=`<tr><td>${y}</td>`+[...RET[y]].map(v=>v==null?'<td class="na">·</td>':`<td style="${col(v)}">${sg(v)}</td>`).join("")
      +`<td class="yr" style="color:var(${yv>=0?"--pos":"--neg"})">${sg(yv)}</td></tr>`}
  document.getElementById("mgrid").innerHTML=h+"</tbody>";

  /* Porownanie: kazdy wiersz z wlasnym oknem, bo VWRA notowany jest krocej niz
     strategia i udawanie, ze to ten sam okres, byloby nieprawda. */
  const wiersz=(nazwa,sub,m,col)=>
    `<div class="row" style="grid-template-columns:auto 1fr auto auto auto;gap:10px">
      <div class="ic" style="background:${CSS(col)};width:10px;height:34px;border-radius:4px"></div>
      <div class="nm">${nazwa}<em>${sub}</em></div>
      <div class="vl" style="min-width:74px"><b style="color:var(${m.cagr>=0?"--pos":"--neg"})">${sg2(m.cagr*100)}%</b><span>CAGR</span></div>
      <div class="vl" style="min-width:74px"><b style="color:var(--neg)">${(m.max_drawdown*100).toFixed(1).replace(".",",")}%</b><span>MaxDD</span></div>
      <div class="vl" style="min-width:58px"><b>×${m.multiple.toFixed(2).replace(".",",")}</b><span>wzrost</span></div></div>`;
  document.getElementById("cmpList").innerHTML=
    wiersz("BEST17 + GPM","strategia · "+M.from+" – "+M.to,M,"--accent")
    +BENCH.map((b,i)=>wiersz(b.label,b.note+" · "+b.from+" – "+b.to,b.metrics,["--s2","--s5","--s3"][i]||"--s6")).join("");
  const krotsze=BENCH.filter(b=>!b.pelne_okno).map(b=>b.label+" od "+b.from);
  document.getElementById("cmpNote").innerHTML=
    (pod?`<b>Obie strony po podatku ${pod}%, ale płaconym inaczej</b> — i to jest tu najważniejsze.
      Strategia rebalansuje co miesiąc, więc realizuje zyski i płaci co roku. Kup i trzymaj nie
      sprzedaje nic, więc płaci raz, przy sprzedaży — krzywa pokazuje, ile zostaje, gdyby sprzedać
      tego dnia. To odroczenie jest realną przewagą benchmarku i nie wolno jej ukryć. `:"")
    +"Benchmarki to ETF-y klasy <b>Acc</b> — dywidendy wchodzą w NAV, więc nie są zaniżone. "
    +"Noga BEST17 liczy się na surowych cenach z USA, <b>bez dywidend</b> — czyli strategia jest tu "
    +"raczej zaniżona niż podkoloryzowana."
    +(krotsze.length?" Krótsza historia: "+krotsze.join(", ")+" — wykres startuje wtedy od wartości strategii z tamtego dnia.":"")}

/* ---- ceny: cena z feedu jest nietykalna, korekta to osobny wpis ---- */
let EDIT=null,PIDX=null;  /* PIDX: ktora data jest ogladana; null = ostatnia */
const ADMIN=()=>ADMIN_BAZA;   /* prawo wpisywania cen - z bazy, nie z przelacznika w UI */
let OVR={};try{OVR=JSON.parse(localStorage.getItem("ovr")||"{}")}catch(e){OVR={}}
const saveOVR=()=>{try{localStorage.setItem("ovr",JSON.stringify(OVR))}catch(e){}};
const okey=(t,d)=>t+"@"+d;
/* Kolejnosc: korekta reczna > notowanie z sesji > liczba, ktorej uzyl silnik
   (interpolacja, gdy tego dnia gielda tego waloru byla zamknieta). */
const eff=(t,i)=>{const P=PRICES[PTAB],o=OVR[okey(t,P.dates[i])];
  return o?o.v:(P.px[t][i]??P.used?.[t]?.[i]??null)};
const interp=(t,i)=>{const P=PRICES[PTAB];
  return !OVR[okey(t,P.dates[i])]&&P.px[t][i]==null&&P.used?.[t]?.[i]!=null};
const asof=(t,i)=>PRICES[PTAB].asof?.[t]?.[i]||PRICES[PTAB].dates[i];
const pidx=()=>PIDX==null?PRICES[PTAB].dates.length-1:PIDX;
const pdate=()=>PRICES[PTAB].dates[pidx()];
/* Pasek dat przewijamy RECZNIE. scrollIntoView przewija takze cala strone, a
   przy pierwszym rysowaniu (sekcja jeszcze ukryta) nie robi nic - dlatego
   wolamy to jeszcze raz przy wejsciu na ekran. */
function przewinPasek(){
  const pasek=document.getElementById("dStrip");
  const b=pasek.querySelector('[aria-pressed="true"]');
  if(!b||!pasek.clientWidth)return;
  pasek.scrollLeft=Math.max(0,b.offsetLeft-(pasek.clientWidth-b.offsetWidth)/2);
}
function renderCeny(){
  const P=PRICES[PTAB],last=pidx();
  document.getElementById("feedStamp").textContent=FEED.source+" · "+FEED.fetched;
  const chk=[];
  const brak=INSTR.filter(([t])=>eff(t,last)==null);
  chk.push([brak.length?"warn":"ok","Komplet instrumentów",(INSTR.length-brak.length)+"/"+INSTR.length]);
  chk.push(["ok","Data zgodna z regułą "+PTAB+"-tego",P.dates[last]]);
  const itp=INSTR.filter(([t])=>interp(t,last)).map(a=>a[0]);
  if(itp.length)chk.push(["warn","Bez notowania, silnik interpolował: "+itp.join(", "),"święto"]);
  const inne=INSTR.filter(([t])=>asof(t,last)!==P.dates[last]&&!interp(t,last)).map(a=>a[0]);
  if(inne.length)chk.push(["warn","Kurs z innego dnia: "+inne.join(", "),asof(inne[0],last)]);
  /* Wartosc interpolowana potrafi po zaokragleniu trafic w sasiednie notowanie -
     to nie jest zastoj ceny, tylko artefakt, wiec takich par nie zglaszamy. */
  const stale=last>0?INSTR.filter(([t])=>eff(t,last)===eff(t,last-1)
    &&!interp(t,last)&&!interp(t,last-1)).map(a=>a[0]):[];
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
  przewinPasek();
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
      <div class="nm">${t}<em>${mk==="US"?"sygnał":"wykonanie"} · ${asof(t,last)}${
        interp(t,last)?` · <span style="color:var(--warn)">brak sesji, interpolacja</span>`:""}${
        o?` · <span style="color:var(--cash)">skorygowane</span>`:""}</em></div>
      <div class="vl" style="display:flex;align-items:center;gap:12px"><div><b>${px(v)}</b>
        <span style="color:${ch==null?"var(--faint)":ch>=0?"var(--pos)":"var(--neg)"}">${ch==null?"—":sg(ch)+"%"}</span></div>
        ${ADMIN()?`<button class="del" data-edit="${t}" style="font-size:.8rem">zmień</button>`:""}
        ${ADMIN()&&o?`<button class="del" data-undo="${t}">×</button>`:""}</div></div>`}).join("")}

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
  const moze=ADMIN_BAZA;
  b.disabled=!moze;b.style.opacity=moze?"":"0.45";b.style.cursor=moze?"":"default";
  h.textContent=!FB?"Baza niedostępna — ceny tylko do odczytu."
    :!USER?"Zaloguj się, żeby zapisywać ceny w bazie."
    :!ADMIN_BAZA?"Podgląd — wpisywanie cen wymaga uprawnień admina.":"";
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
document.getElementById("segD").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b||!SIG.diagnostics[b.dataset.d])return;
  DTAB=b.dataset.d;renderDiag();renderAll()});

document.getElementById("dStrip").addEventListener("click",e=>{
  const b=e.target.closest("[data-di]");if(!b)return;PIDX=+b.dataset.di;EDIT=null;renderCeny()});
document.getElementById("dPrev").addEventListener("click",()=>{PIDX=Math.max(0,pidx()-1);EDIT=null;renderCeny()});
document.getElementById("dNext").addEventListener("click",()=>{PIDX=Math.min(PRICES[PTAB].dates.length-1,pidx()+1);EDIT=null;renderCeny()});
document.getElementById("priceList").addEventListener("click",e=>{
  const ed=e.target.closest("[data-edit]"),un=e.target.closest("[data-undo]"),ca=e.target.closest("[data-cancel]");
  if(ed){EDIT=ed.dataset.edit;renderCeny();document.getElementById("ovrV")?.focus()}
  else if(un){delete OVR[okey(un.dataset.undo,pdate())];saveOVR();
    if(ADMIN_BAZA)FB.usunKorekte(`${PTAB}_${pdate()}_${un.dataset.undo}`).catch(()=>{});
    renderCeny()}
  else if(ca){EDIT=null;renderCeny()}});
document.getElementById("priceList").addEventListener("submit",e=>{
  e.preventDefault();
  const klucz=okey(EDIT,pdate()),wpis={v:parseFloat(document.getElementById("ovrV").value),
    r:document.getElementById("ovrR").value,who:USER?.email||"admin",
    when:new Date().toISOString().slice(0,16).replace("T"," ")};
  OVR[klucz]=wpis;saveOVR();
  if(ADMIN_BAZA)FB.zapiszKorekte(`${PTAB}_${pdate()}_${EDIT}`,
    {value:wpis.v,reason:wpis.r,author:wpis.who,created_at:wpis.when})
    .catch(err=>console.warn("korekta nie trafila do bazy:",err.message));
  EDIT=null;renderCeny()});

/* ---- wpisy: stan konta i przeplywy ----------------------------------------
   User nie prowadzi ksiegi transakcji - "co jakis czas wpisuje, ile ma na
   koncie". Z takich migawek plus wplat/wyplat da sie policzyc wszystko, co
   pokazuje Pulpit: kapital, wynik, krzywa wartosci i TWR. Czego NIE da sie
   policzyc bez rozbicia na walory, to co dokupic - i tak to jest napisane.

   Kwoty sa w USD, bo ETF-y sa dolarowe. Zlote to przeliczenie po kursie. */
/* Wpisy zyja WYLACZNIE w bazie, pod kontem uzytkownika. Nie ma wersji
   "lokalnej": dane portfela sa prywatne i maja przezyc zmiane urzadzenia, a
   nie zniknac z wyczyszczona pamiecia przegladarki. */
let TX=[];
WPISY=true;   /* od tego miejsca wolno pytac o kursy z wpisow */
/* Zalogowany trzyma wpisy w bazie - przezywaja zmiane urzadzenia.
   Niezalogowany zostaje przy przegladarce, zeby panel dalo sie klikac. */
async function wczytajTXzBazy(){
  try{
    const z=await FB.wczytaj(USER.uid,"transactions");
    TX=z.map(r=>({id:r.id,d:r.d,a:r.a||"",t:r.t,k:r.k,px:r.px||null}));
  }catch(e){console.warn("nie udalo sie wczytac wpisow:",e.message)}
  poWpisach();
}
async function dodajTX(r){
  if(!ZAL()){alert("Zaloguj się, żeby prowadzić portfel.");return}
  r.id=r.id||(r.d+"_"+Date.now().toString(36));
  TX.push(r);
  try{await FB.zapisz(USER.uid,"transactions",r.id,r)}catch(e){alert("Nie zapisano w bazie: "+e.message)}
  poWpisach();
}
async function usunTX(i){
  const r=TX[i];TX.splice(i,1);
  if(r?.id){try{await FB.usun(USER.uid,"transactions",r.id)}catch(e){console.warn(e.message)}}
  poWpisach();
}
const TYP={stan:"Stan konta",wplata:"Wpłata",wyplata:"Wypłata"};
const TXI={stan:["=","--accent"],wplata:["↓","--pos"],wyplata:["↑","--cash"]};

/* ---- portfel policzony z wpisow ---- */
const mies=d=>d.slice(0,7);
/* Kursy USD/PLN z konkretnych dni. To dane WSPOLNE - kurs z 10 marca jest taki
   sam dla kazdego - wiec wpisuje je admin, a reszta tylko czyta. Trzymamy kopie
   w przegladarce, zeby po wylogowaniu panel nie tracil nagle zlotowek.
   Jeden kurs na cala historie zanizalby albo zawyzal stare wplaty, a "wplacone
   w zlotych" ma byc tym, co naprawde wyszlo z konta. */
let KURSY=[];
try{KURSY=JSON.parse(localStorage.getItem("fx")||"[]")}catch(e){KURSY=[]}
const zapiszKursyLokalnie=()=>{try{localStorage.setItem("fx",JSON.stringify(KURSY))}catch(e){}};
const kursy=()=>KURSY.filter(r=>r.k>0).sort((a,b)=>a.d.localeCompare(b.d));
function kursNa(data){
  const k=kursy();
  if(!k.length)return KURS;
  let w=k[0].k;                       /* przed pierwszym wpisem - najstarszy znany */
  for(const r of k){if(r.d<=data)w=r.k;else break}
  return w;
}
const kursTeraz=()=>{const k=kursy();return k.length?k.at(-1).k:KURS};
/* Ktora noga odpowiada za dany walor - z ROLE w signals.json. Walor wspolny dla
   obu nog (np. CSPX: BEST17 + GPM) liczy sie po polowie. */
const nogaWaloru=t=>{const r=ROLE[t]||"";const b=r.includes("BEST17"),g=r.includes("GPM");
  return b&&g?{best17:.5,gpm:.5}:b?{best17:1,gpm:0}:{best17:0,gpm:1}};

/* Lancuch zwrotow miedzy obserwowanymi miesiacami. Ta sama funkcja liczy TWR w
   dolarach i w zlotych - roznia sie tylko tym, jakie tablice dostanie. W zlotych
   wychodzi inaczej, bo dochodzi na to ruch kursu, i tak ma byc: kto liczy w
   zlotowkach, ten zarabia lub traci takze na kursie. */
function lancuch(wart,wpl,obs){
  const zwr=wart.map(()=>null);
  let poprz=-1;
  wart.forEach((_,i)=>{
    if(!obs.has(OSTATNIA_OS[i])||!wart[i])return;
    if(poprz>=0&&wart[poprz])
      zwr[i]=+(((wart[i]-(wpl[i]-wpl[poprz]))/wart[poprz]-1)*100).toFixed(2);
    poprz=i});
  const twr=(zwr.filter(x=>x!=null).reduce((a,r)=>a*(1+r/100),1)-1)*100;
  return {zwr,twr:+twr.toFixed(2)};
}
let OSTATNIA_OS=[];
function liczPortfel(){
  const stany=TX.filter(r=>r.t==="stan"&&r.k>0);
  if(!stany.length)return null;
  const konta=[...new Set(TX.map(r=>r.a))].filter(Boolean);

  /* Os czasu zaczyna sie przy PIERWSZYM STANIE KONTA, nie przy pierwszej wplacie:
     przed nim nie wiadomo, ile konto bylo warte, a zero na wykresie wygladaloby
     jak strata calego kapitalu. Wplaty sprzed tej daty i tak licza sie do
     "wplacone" - sumujemy je od poczatku historii. */
  const od=mies(stany.map(r=>r.d).sort()[0]);
  const msc=[od,...TX.map(r=>mies(r.d))].filter(m=>m>=od).sort();
  const os=[];{const [y0,m0]=msc[0].split("-").map(Number),[y1,m1]=msc.at(-1).split("-").map(Number);
    for(let y=y0,m=m0;y<y1||(y===y1&&m<=m1);m++){if(m>12){m=1;y++}
      os.push(y+"-"+String(m).padStart(2,"0"))}}
  OSTATNIA_OS=os;

  /* Jedna funkcja na calosc i na pojedyncze konto - inaczej suma kont i portfel
     liczylyby sie innym kodem i predzej czy pozniej by sie rozjechaly. */
  const seria=kt=>{
    const moje=r=>!kt||r.a===kt;
    const wart=os.map(m=>{let sum=0;
      for(const k of (kt?[kt]:konta)){
        const ost=stany.filter(r=>r.a===k&&mies(r.d)<=m).sort((a,b)=>a.d.localeCompare(b.d)).at(-1);
        if(ost)sum+=ost.k}
      return Math.round(sum)});
    const wpl=os.map(m=>Math.round(TX.filter(r=>moje(r)&&mies(r.d)<=m)
      .reduce((s,r)=>s+(r.t==="wplata"?r.k:r.t==="wyplata"?-r.k:0),0)));
    /* Zwrot liczymy TYLKO miedzy miesiacami, w ktorych naprawde jest wpis stanu.
       Miesiac bez wpisu nie jest "miesiacem na zero" - po prostu nie wiadomo, ile
       konto wtedy bylo warte, a wykres pokazujacy tam 0,0% klamalby.
       Przeplyw odejmujemy, inaczej wplata wygladalaby jak zysk. */
    const obs=new Set(stany.filter(moje).map(r=>mies(r.d)));
    const {zwr,twr}=lancuch(wart,wpl,obs);
    return {wart,wpl,zwr,twr};
  };
  const P=seria(null);

  /* Co trzymam: z ostatniego rozbicia kazdego konta, jesli user je podal. */
  const trzymam={},perKonto={};
  for(const k of konta){
    const ost=stany.filter(r=>r.a===k&&r.px).sort((a,b)=>a.d.localeCompare(b.d)).at(-1);
    if(!ost)continue;
    let suma=0;perKonto[k]={};
    for(const[t,v]of Object.entries(ost.px))if(v>0){
      trzymam[t]=(trzymam[t]||0)+v;perKonto[k][t]=v;suma+=v}
    const reszta=ost.k-suma;
    if(reszta>0.5){trzymam.GOTOWKA=(trzymam.GOTOWKA||0)+reszta;perKonto[k].GOTOWKA=reszta}
  }

  /* Podzial nog miedzy konta - NIE deklarowany, tylko odczytany z tego, co na
     ktorym koncie naprawde lezy. Bez rozbicia dzielimy proporcjonalnie do
     wartosci konta, bo nic lepszego nie wiemy. */
  const udzial={best17:{},gpm:{}};
  for(const k of konta){
    udzial.best17[k]=0;udzial.gpm[k]=0;
    for(const[t,v]of Object.entries(perKonto[k]||{})){
      if(t==="GOTOWKA")continue;
      const n=nogaWaloru(t);udzial.best17[k]+=v*n.best17;udzial.gpm[k]+=v*n.gpm}}
  const kurs=kursTeraz();   /* kurs "na teraz" - do kwot bez wlasnej daty */
  const konce=Object.fromEntries(konta.map(k=>[k,seria(k)]));
  const accounts=konta.map(k=>{
    const sum=l=>konta.reduce((a,x)=>a+udzial[l][x],0);
    const a={name:k,value:Math.round(konce[k].wart.at(-1)),
             pln:konce[k].twr,usd:konce[k].twr,
             alloc:{best17:sum("best17")?udzial.best17[k]/sum("best17"):0,
                    gpm:sum("gpm")?udzial.gpm[k]/sum("gpm"):0}};
    if(!sum("best17")&&!sum("gpm")){
      const cal=konta.reduce((x,y)=>x+konce[y].wart.at(-1),0)||1;
      a.alloc={best17:konce[k].wart.at(-1)/cal,gpm:konce[k].wart.at(-1)/cal}}
    return a});

  /* Wszystko zostaje w DOLARACH - w nich sa wpisy i w nich notowane sa ETF-y.
     Zlote to wylacznie warstwa wyswietlania (funkcja kw()), po kursie z daty. */
  const kapital=P.wart.at(-1);
  const wartPln=P.wart.map((v,i)=>Math.round(v*kursNa(os[i]+"-28")));
  const wplPln=os.map(m=>Math.round(TX.filter(r=>mies(r.d)<=m)
    .reduce((a,r)=>a+(r.t==="wplata"?r.k*kursNa(r.d):r.t==="wyplata"?-r.k*kursNa(r.d):0),0)));
  const pln=lancuch(wartPln,wplPln,new Set(stany.map(r=>mies(r.d))));
  return {
    owner:"wpisy", capital:{best17:kapital/2,gpm:kapital/2,split10:.5},
    holdings:trzymam, accounts,
    months:os,
    /* Wartosc w zlotych: kurs z konca danego miesiaca. Wplacone w zlotych:
       KAZDY przeplyw po swoim wlasnym kursie - tyle naprawde kosztowal. */
    value:wartPln, paid:wplPln,
    value_usd:P.wart, paid_usd:P.wpl,
    returns:{usd:P.zwr,pln:pln.zwr},
    legs:{best17:{value_usd:P.wart.at(-1)/2,paid_usd:P.wpl.at(-1)/2},
          gpm:{value_usd:P.wart.at(-1)/2,paid_usd:P.wpl.at(-1)/2}},
    fx:{pair:"USD/PLN",rate:kurs,series:os.map(m=>kursNa(m+"-28"))},
    twr:{usd:P.twr,pln:pln.twr},
  };
}
function rysujPasek(){
  /* Pasek ma mowic prawde o TYM, co jest na ekranie - a nie wisiec na zawsze.
     Nie ma juz "danych przykladowych": albo sa Twoje liczby, albo panel nie
     pokazuje zadnych. */
  document.getElementById("demoBar").hidden=!BRAK;
  if(!BRAK)return;
  document.getElementById("demoTxt").innerHTML=ZAL()
    ? "Sygnał, ceny i wyniki są policzone przez silnik. <b>O Twoim koncie panel nic nie wie</b> — "
      +"dopisz stan konta w zakładce Wpisy, a policzy kapitał, wynik i co dokupić."
    : "Oglądasz samą strategię: sygnał, wyniki i ceny, z których są policzone. "
      +"<b>Portfel wymaga zalogowania</b> — dane konta są prywatne i leżą w bazie, nie w tej stronie.";
}
function poWpisach(){
  const P=liczPortfel();
  /* Wlasne konta zastepuja przykladowe uklady - trzymanie obok siebie prawdziwego
     konta i wymyslonego "Brokera A" tylko myli. */
  for(const k of Object.keys(SETUPS))delete SETUPS[k];
  if(P&&P.accounts.length){SETUPS.moje={label:"Moje konta",accounts:P.accounts};SETUP="moje"}
  else{Object.assign(SETUPS,UKLADY_PRZYKLAD);SETUP="rozdzielnie"}
  ustawPortfel(P);
  rysujPasek();rysujRozbicie();renderTX();renderPulpit();renderActions();renderHist();renderAccounts();renderAll();
  renderSklad();
}

function fillAccSelect(){
  const s=document.getElementById("txAcc"),cur=s.value;
  const wlasne=[...new Set(TX.map(r=>r.a))].filter(Boolean);
  const lista=wlasne.length?wlasne:SETUPS[SETUP].accounts.map(a=>a.name);
  s.innerHTML=lista.map(a=>`<option>${esc(a)}</option>`).join("")+`<option value="__nowe">+ nowe konto…</option>`;
  if(lista.includes(cur))s.value=cur}
/* Kurs to dane wspolne - wpisuje je wylacznie admin. */
const mozeKursy=()=>ADMIN_BAZA;
function rysujRozbicie(){
  const typ=document.getElementById("txType").value,pok=typ==="stan";
  document.getElementById("txSplit").hidden=!pok;
  /* Kurs podaje sie przy stanie konta (bo wtedy i tak patrzysz na rachunek)
     albo osobnym wpisem dla dowolnej daty. */
  document.getElementById("txKursWrap").hidden=!pok;
  document.getElementById("txAcc").closest(".fld").hidden=typ==="kurs";
  /* Kurs to dane wspolne - wpisuje je admin. Reszta widzi liste, ale bez pol.
     `hidden` na <option> nie dziala wszedzie, wiec do tego jeszcze `disabled`. */
  document.getElementById("txKursWrap").hidden=!pok||!mozeKursy();
  const opt=document.querySelector('#txType option[value="kurs"]');
  opt.hidden=opt.disabled=!mozeKursy();
  if(opt.disabled&&typ==="kurs"){document.getElementById("txType").value="stan";rysujRozbicie()}
  document.getElementById("txAmtLbl").textContent=
    typ==="kurs"?"Ile złotych za dolara":pok?"Wartość konta w USD":"Kwota w USD";
  if(!pok)return;
  /* Walory WYKONAWCZE - to te linie realnie lezą na rachunku, nie tickery
     sygnalowe z USA (sygnal liczy sie na XLK, kupujesz IUIT). */
  document.getElementById("txPx").innerHTML=ORDER.map(t=>
    `<label class="pf"><b>${t}<em>${(ROLE[t]||"").split(" ")[0]||""}</em></b>
      <input type="number" step="0.01" min="0" data-pt="${t}" placeholder="0"></label>`).join("");
  sumujRozbicie()}
function sumujRozbicie(){
  const pola=[...document.querySelectorAll("#txPx input")];
  const suma=pola.reduce((s,i)=>s+(parseFloat(i.value)||0),0);
  const cel=parseFloat(document.getElementById("txAmt").value)||0;
  const el=document.getElementById("txSplitSum");
  if(!suma){el.textContent="Zostaw puste, jeśli nie chcesz rozbijać. Reszta do wartości konta policzy się jako gotówka.";el.style.color="";return}
  const r=cel-suma;
  el.textContent=`Rozpisane ${zl(suma)} USD z ${zl(cel)} USD · ${r>=0?"gotówka "+zl(r)+" USD":"o "+zl(-r)+" USD za dużo"}`;
  el.style.color=r<-0.5?"var(--neg)":"var(--faint)"}

function renderTX(){
  TX.sort((a,b)=>b.d.localeCompare(a.d));
  /* polska odmiana: 1 wpis, 2-4 wpisy, 0 i 5+ wpisow (plus wyjatek 12-14) */
  const n=TX.length,d=n%10,st=n%100;
  document.getElementById("txCount").textContent=
    n+" "+(n===1?"wpis":(d>=2&&d<=4&&!(st>=12&&st<=14))?"wpisy":"wpisów");
  const lista=TX.map((r,i)=>[r,i]);
  document.getElementById("txList").innerHTML=lista.length?lista.map(([r,i])=>{
    const[sym,c]=TXI[r.t]||["?","--s6"];
    return `<div class="row"><div class="ic" style="background:${CSS(c)}">${sym}</div>
      <div class="nm">${TYP[r.t]||r.t}<em>${r.d} · ${esc(r.a)}${r.px?" · rozbite na walory":""}</em></div>
      <div class="vl" style="display:flex;align-items:center;gap:10px"><b>${zl(r.k)} USD</b>
        <button class="del" data-del="${i}" aria-label="Usuń wpis z ${r.d}">×</button></div></div>`}).join("")
    :'<div class="empty">Brak wpisów. Dopisz pierwszy stan konta powyżej — od tego momentu Pulpit liczy z Twoich liczb, nie z przykładu.</div>';
  const kur=kursy(),moge=mozeKursy();
  document.getElementById("kursList").innerHTML=kur.length
    ? kur.slice().reverse().map(r=>
        `<div class="row"><div class="ic" style="background:${CSS("--s5")}">zł</div>
          <div class="nm">${r.d}<em>${r.k.toFixed(4).replace(".",",")} zł za dolara</em></div>
          <div class="vl" style="display:flex;align-items:center;gap:10px"><b>${r.k.toFixed(2).replace(".",",")}</b>
            ${moge?`<button class="del" data-fx="${r.d}" aria-label="Usuń kurs z ${r.d}">×</button>`:""}</div></div>`).join("")
    : `<div class="empty">${moge
        ? `Brak kursów. Dopisz choć jeden — bez niego panel pokazuje tylko dolary (przyjmuje ${KURS.toFixed(2).replace(".",",")} jako kurs zastępczy).`
        : "Brak kursów. Wpisuje je admin — do tego czasu złotówki liczą się kursem zastępczym "+KURS.toFixed(2).replace(".",",")+"."}</div>`;
  const nota=document.getElementById("kursNote");
  nota.textContent=moge?"":"Kursy są wspólne dla wszystkich — wpisuje je admin.";
  nota.hidden=moge;
  const acc={};
  for(const r of TX){acc[r.a]=acc[r.a]||{in:0,stan:null,d:""};
    if(r.t==="wplata")acc[r.a].in+=r.k;
    if(r.t==="wyplata")acc[r.a].in-=r.k;
    if(r.t==="stan"&&r.d>=acc[r.a].d){acc[r.a].stan=r.k;acc[r.a].d=r.d}}
  const ks=Object.keys(acc);
  document.getElementById("depStats").innerHTML=ks.length
    ? ks.map(k=>`<div><span>${esc(k)}${acc[k].d?" · "+acc[k].d:""}</span><b>${acc[k].stan!=null?zl(acc[k].stan)+" USD":"—"}</b></div>`).join("")
      +`<div><span>Wpłacone razem</span><b style="color:var(--accent)">${zl(ks.reduce((s,k)=>s+acc[k].in,0))} USD</b></div>`
    :'<div><span>Brak wpisów</span><b>—</b></div>'}

document.getElementById("txType").addEventListener("change",rysujRozbicie);
document.getElementById("txAmt").addEventListener("input",sumujRozbicie);
document.getElementById("txPx").addEventListener("input",sumujRozbicie);
document.getElementById("txAcc").addEventListener("change",e=>{
  if(e.target.value!=="__nowe")return;
  const n=prompt("Nazwa konta (np. LYNX, XTB):");
  if(n&&n.trim()){const o=document.createElement("option");o.textContent=n.trim();
    e.target.insertBefore(o,e.target.lastElementChild);e.target.value=n.trim()}
  else e.target.selectedIndex=0});
document.getElementById("txForm").addEventListener("submit",e=>{
  e.preventDefault();
  const t=document.getElementById("txType").value;
  const konto=document.getElementById("txAcc").value;
  if(konto==="__nowe"){alert("Najpierw nazwij konto.");return}
  const rec={d:document.getElementById("txDate").value,a:konto,t,
    k:parseFloat(document.getElementById("txAmt").value)||0};
  if(t==="kurs"){
    if(!(rec.k>0)){alert("Kurs musi być większy od zera.");return}
    dodajKurs(rec.d,rec.k);
    e.target.reset();document.getElementById("txDate").value=new Date().toISOString().slice(0,10);
    fillAccSelect();rysujRozbicie();return}
  if(t==="stan"){
    const px={};for(const i of document.querySelectorAll("#txPx input")){
      const v=parseFloat(i.value)||0;if(v>0)px[i.dataset.pt]=v}
    const suma=Object.values(px).reduce((a,b)=>a+b,0);
    if(suma-rec.k>0.5){alert("Rozbicie na walory jest większe niż wartość konta.");return}
    if(Object.keys(px).length)rec.px=px;
    /* Kurs podany przy stanie konta zapisuje sie jako OSOBNY wpis z ta sama data -
       dzieki temu dziala tak samo, jak gdyby go wpisac recznie. */
    const kr=parseFloat(document.getElementById("txKurs").value);
    if(kr>0&&mozeKursy())dodajKurs(rec.d,kr);
  }
  dodajTX(rec);
  e.target.reset();
  document.getElementById("txDate").value=new Date().toISOString().slice(0,10);
  fillAccSelect();rysujRozbicie()});
document.getElementById("txList").addEventListener("click",e=>{
  const b=e.target.closest("[data-del]");if(!b)return;
  usunTX(+b.dataset.del)});
document.getElementById("kursList").addEventListener("click",e=>{
  const b=e.target.closest("[data-fx]");if(!b)return;
  usunKurs(b.dataset.fx)});


/* ============ nawigacja ============ */
const VIEWS=["pulpit","sygnal","wyniki","transakcje","ceny","dlaczego"];
function rysujNawigacje(){
  for(const v of TYLKO_ZALOGOWANY)
    document.querySelector(`#nav a[href="#${v}"]`).hidden=!ZAL();
  const teraz=location.hash.slice(1);
  if(!ZAL()&&TYLKO_ZALOGOWANY.includes(teraz))location.hash="#sygnal";
}
function show(v){
  if(!VIEWS.includes(v))v=ZAL()?"pulpit":"sygnal";
  if(!ZAL()&&TYLKO_ZALOGOWANY.includes(v))v="sygnal";
  VIEWS.forEach(x=>document.getElementById("v-"+x).hidden=(x!==v));
  if(v==="ceny")requestAnimationFrame(przewinPasek);   /* ukryty pasek ma szerokosc 0 */
  document.querySelectorAll("#nav a").forEach(a=>a.getAttribute("href")==="#"+v?a.setAttribute("aria-current","page"):a.removeAttribute("aria-current"));
  renderAll();scrollTo(0,0)}
addEventListener("hashchange",()=>show(location.hash.slice(1)));


document.getElementById("txDate").value=new Date().toISOString().slice(0,10);
rysujPasek();fillAccSelect();rysujRozbicie();renderTX();renderPulpit();renderMatrix();renderActions();renderHist();renderSklad();renderAccounts();renderWyniki();renderDiag();renderCeny();

legend("l-mix",KLASY.map(k=>[k[0],CSS(k[1])]));
legend("l-cmp",CMPK.map(k=>[k.label,CSS(k.col)]));
rysujZakresy();
legend("l-canary",[["VT",CSS("--s1")],["XLK",CSS("--s2")]]);
/* Przy wejsciu bez adresu nie wiemy jeszcze, czy ktos jest zalogowany - Firebase
   odpowiada chwile pozniej. Dlatego zapamietujemy, ze user NIE wybral ekranu
   sam, i po zalogowaniu przestawiamy go na Pulpit (jego ekran). Jesli wszedl
   prosto na #wyniki, zostaje tam, gdzie chcial. */
const WEJSCIE_BEZ_WYBORU=!location.hash;
rysujNawigacje();show(location.hash.slice(1)||(ZAL()?"pulpit":"sygnal"));

/* ============ konto ============ */
function rysujKonto(){
  const e=document.getElementById("konto");
  if(!FB){e.innerHTML='<span class="sub">baza niedostępna</span>';return}
  e.innerHTML=USER
    ? `<div class="kto"><b>${esc(USER.displayName||USER.email||"zalogowany")}</b>
        <span>${ADMIN_BAZA?"admin":"podgląd"}</span></div>
       <button type="button" class="cicho" id="btnWyloguj">Wyloguj</button>`
    : `<button type="button" data-login>Zaloguj przez Google</button>`;
}
function rysujUid(){
  const stare=document.getElementById("uidBox");if(stare)stare.remove();
  if(!USER||ADMIN_BAZA)return;
  const box=document.createElement("div");box.className="uid";box.id="uidBox";
  /* Krok jest reczny z zalozenia - zaden klient nie moze dopisac sam siebie do
     adminow (patrz firestore.rules). Skoro reczny, to niech bedzie na dwa
     klikniecia, a nie na przepisywanie 28 znakow z ekranu. */
  const konsola=`https://console.firebase.google.com/project/${esc(FB?.projectId||"")}/firestore/data/~2Fadmins`;
  box.innerHTML=`<div class="hd">Jesteś zalogowany w trybie <b>podglądu</b>.</div>
    Wpisywanie cen i korekt wymaga praw admina. Nadaje się je tylko z konsoli — dopisz
    dokument o poniższym id do kolekcji <b>admins</b> (zawartość dowolna, może być pusta),
    potem odśwież stronę.
    <code id="uidKod">${esc(USER.uid)}</code>
    <div class="akcje"><button type="button" class="btn" id="btnKopiujUid">Kopiuj identyfikator</button>
      <a class="btn cicho" href="${konsola}" target="_blank" rel="noopener">Otwórz kolekcję admins</a></div>`;
  document.querySelector(".topbar").after(box);
}
/* Komunikat ma mowic, CO zrobic. "auth/unauthorized-domain" to najczestszy
   przypadek przy wlasnej domenie i bez tej podpowiedzi nie da sie zgadnac. */
function bladLogowania(err){
  const kod=err?.code||"";
  if(kod==="auth/unauthorized-domain")
    return `Firebase nie dopuszcza domeny ${location.hostname}.\n\n`
      +"Konsola Firebase → Authentication → Settings → Authorized domains → dodaj "
      +location.hostname+".";
  if(kod==="auth/popup-blocked"||kod==="auth/cancelled-popup-request")
    return "Przeglądarka zablokowała okienko logowania. Spróbuj jeszcze raz — przełączę się na przekierowanie.";
  if(kod==="auth/network-request-failed")
    return "Brak połączenia z Firebase. Sprawdź sieć i spróbuj ponownie.";
  return "Logowanie nie powiodło się: "+(err?.message||err);
}
document.addEventListener("click",async e=>{
  if(e.target.id==="btnKopiujUid"){
    const b=e.target;
    try{await navigator.clipboard.writeText(USER.uid);b.textContent="Skopiowane"}
    catch{document.getElementById("uidKod")?.focus();b.textContent="Zaznacz i skopiuj ręcznie"}
    setTimeout(()=>{b.textContent="Kopiuj identyfikator"},2500);return}
  const loguj=e.target.closest("[data-login]");
  if(loguj){
    e.preventDefault();
    const b=loguj;b.disabled=true;b.textContent="Logowanie…";
    try{await FB.zalogujGoogle()}
    catch(err){alert(bladLogowania(err))}
    finally{if(document.body.contains(b)){b.disabled=false;b.textContent="Zaloguj przez Google"}}
    return}
  if(e.target.id==="btnWyloguj"){await FB.wyloguj()}});
/* Powrot z przekierowania: jesli sie nie udalo, user musi wiedziec dlaczego. */
if(FB?.wynikPrzekierowania)FB.wynikPrzekierowania().then(w=>{if(w&&w.code)alert(bladLogowania(w))});

if(FB)FB.naZmianeKonta(async u=>{
  USER=u;
  ADMIN_BAZA=u?await FB.czyAdmin(u.uid):false;
  rysujKonto();rysujUid();rysujPrawoZapisu();rysujNawigacje();
  if(u&&WEJSCIE_BEZ_WYBORU&&!location.hash)show("pulpit");
  if(u){await wczytajTXzBazy();await wczytajKursyZBazy();await wczytajCenyZBazy()}
  else{TX=[];KURSY=[];poWpisach()}   /* wylogowanie zabiera ze soba cudze dane z ekranu */
});
rysujKonto();
