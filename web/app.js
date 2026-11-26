
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
let CAPITAL,HOLDINGS,MONTHS,VALUE,PAID,VUSD,PUSD,RETC,FXN,TRACK=[],BRAK=true,ZLOZONE=false,WPISY=false;
/* Ktore nogi lezą na ktorym koncie. DEKLAROWANE przez usera, bo z samych
   pozycji nie da sie tego odczytac: CMOD i CSPX naleza do obu nog naraz, wiec
   odczyt rozdziela je po polowie i wychodzi, ze kazde konto ma trohe obu.
   Brak deklaracji = stare zachowanie, czyli odczyt z pozycji. */
const ROLE_OK=["wszystko","best17","gpm"];
const ROLE_LBL={wszystko:"Wszystko",best17:"BEST17",gpm:"GPM"};
let ROLE_KONT={};
function ustawPortfel(P){
  PORT=P;BRAK=!P;
  if(P){
    CAPITAL=P.capital;HOLDINGS=P.holdings;MONTHS=P.months;VALUE=P.value;PAID=P.paid;
    VUSD=P.value_usd;PUSD=P.paid_usd;RETC=P.returns;FXN=P.fx.rate;TRACK=P.track||[];
  }else{
    /* 100 + 100 = "sto procent kazdej nogi" - te same wzory licza wtedy udzialy
       zamiast zlotowek, a formatowanie pilnuje, zeby nikt nie wzial ich za kwote. */
    CAPITAL={best17:100,gpm:100,split10:.5};HOLDINGS={};MONTHS=[];VALUE=[];PAID=[];
    VUSD=[];PUSD=[];RETC={usd:[],pln:[]};FXN=WPISY?kursTeraz():null;TRACK=[];   /* przy starcie wpisow jeszcze nie ma */
  }
  if(ZLOZONE)przeliczTransze();   /* przy pierwszym wywolaniu transz jeszcze nie ma */
}
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
const kw=v=>CURV==="usd"?zl(v)+" USD":FXN==null?"— zł":zl(v*FXN)+" zł";
const zlk=v=>CURV==="usd"?zl(v):FXN==null?"—":zl(v*FXN);
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
/* Cel konta liczy sie na JEGO WLASNYM stanie, nie na udziale w modelowym
   50/50. Nogi siedza u roznych brokerow, wiec wyrownanie miedzy nimi
   wymagaloby przelewu - a tego sie nie robi co transze. W obrebie konta
   trzymamy proporcje nog, ktore ono niesie. Rozjazd wobec modelu pokazuje
   osobno accIdeal, zeby bylo widac, ze nogi sie rozeszly. */
const legProp=leg=>{const s=Object.values(LEG[leg]||{}).reduce((a,b)=>a+b,0);
  return s?Object.fromEntries(Object.entries(LEG[leg]).map(([t,v])=>[t,v/s])):{}};
const accComp=a=>{const o={},w={};let s=0;
  for(const leg of["best17","gpm"]){const f=a.alloc[leg]||0;if(f>0){w[leg]=f;s+=f}}
  if(!s)return{};
  for(const[leg,f]of Object.entries(w))
    for(const[t,p]of Object.entries(legProp(leg)))o[t]=(o[t]||0)+a.value*(f/s)*p;
  return Object.fromEntries(Object.entries(o).filter(([,v])=>v>.5).sort((x,y)=>y[1]-x[1]))};
const accTarget=a=>a.value;
const accIdeal=a=>(a.alloc.best17||0)*CAPITAL.best17+(a.alloc.gpm||0)*CAPITAL.gpm;
/* Cel OSIAGALNY: suma celow poszczegolnych kont, liczonych na ICH wartosciach.
   COMBINED to cel modelowy 50/50 na calym kapitale - gdy konta rozjechaly sie
   wartoscia, roznicy wobec niego NIE da sie zamknac kupnem ani sprzedaza, bo
   wymagalaby przelewu miedzy brokerami. Pokazywanie jej jako "odchylenie waloru"
   mowilo "IUIT -1,9 pp" o portfelu, ktory jest co do grosza na celu. Sam rozjazd
   kont jest realny i wazny - ale to osobna wielkosc, patrz bilansNog(). */
const celOsiagalny=()=>{
  const k=(SETUPS[SETUP]?.accounts||[]).filter(a=>a.value>0);
  if(!PORT||!k.length)return{cel:COMBINED,suma:TOTAL};
  const o={};let s=0;
  for(const a of k)for(const[t,v]of Object.entries(accComp(a))){o[t]=(o[t]||0)+v;s+=v}
  return s>0?{cel:o,suma:s}:{cel:COMBINED,suma:TOTAL}};
/* O ile nogi rozjechaly sie wartoscia wobec 50/50. To JEST realne odchylenie i
   jedyne, ktorego nie zamknie zadne zlecenie - wyrownuje sie je kierunkiem wplaty. */
const bilansNog=()=>{
  const k=(SETUPS[SETUP]?.accounts||[]).filter(a=>a.value>0);
  if(!PORT||k.length<2)return null;
  const w={best17:0,gpm:0};let s=0;
  for(const a of k){
    const su=(a.alloc.best17||0)+(a.alloc.gpm||0);
    if(!su)continue;
    for(const l of["best17","gpm"])w[l]+=a.value*((a.alloc[l]||0)/su);
    s+=a.value}
  return s>0?["best17","gpm"].map(l=>({nazwa:l==="best17"?"BEST17":"GPM",
    ma:w[l],cel:s/2,d:w[l]-s/2,pp:(w[l]/s-.5)*100})):null};
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

/* Ile zrobila strategia na konkretnej kwocie: JEDEN wklad na starcie i zero
   doplat. Krzywa z wpisow (Pulpit) rosnie takze od samych wplat, wiec nie
   odpowiada na pytanie "ile zrobila strategia" - ta odpowiada.
   Start od dnia, w ktorym wszedl pierwszy kapital, jesli sa wpisy; bez nich od
   poczatku historii na okraglej kwocie, zeby bylo od czego liczyc procent. */
const GROW_KWOTA=100000;
function growBaza(){
  const d0=CMP.dates[0]||null;
  if(!BRAK&&TRACK.length&&TRACK[0].d>d0)return{od:TRACK[0].d,kwota:GROW_KWOTA,wlasny:true};
  return{od:d0,kwota:GROW_KWOTA,wlasny:false}}
chart("c-grow",W=>{
  const glowa=document.getElementById("growHead"),nota=document.getElementById("growNote");
  const S=CMP.strategy||[],B0=growBaza();
  if(!B0.od||S.length<2){if(glowa)glowa.innerHTML="";if(nota)nota.textContent="";return ""}
  let i0=CMP.dates.findIndex(d=>d>=B0.od);if(i0<0)i0=0;
  while(i0<S.length&&S[i0]==null)i0++;
  const daty=CMP.dates.slice(i0),ser=S.slice(i0),baza=ser.find(v=>v!=null);
  if(!baza||ser.filter(v=>v!=null).length<2){
    if(glowa)glowa.innerHTML="";if(nota)nota.textContent="";return ""}
  const kw=ser.map(v=>v==null?null:B0.kwota*v/baza);
  const konc=kw.filter(v=>v!=null).at(-1),zm=konc/B0.kwota-1;
  const nr=W<520,H=nr?200:240,T=16,B=28,L=nr?52:62,R=8;
  const osLbl=v=>nr&&Math.abs(v)>=10000?zl(v/1000)+" tys.":zl(v);
  const ts=x=>Date.parse(x),t0=ts(daty[0]),t1=Math.max(ts(daty.at(-1)),t0+1);
  const X=i=>L+(W-L-R)*(ts(daty[i])-t0)/(t1-t0);
  const wsz=kw.filter(v=>v!=null);
  const lo=Math.min(...wsz),hi=Math.max(...wsz),pad=(hi-lo)*.12||Math.max(1,hi*.06);
  const Y=v=>T+(H-T-B)*(1-(v-lo+pad)/(hi-lo+2*pad));
  const col=zm>=0?CSS("--pos-soft2"):CSS("--neg");
  const okragly=r=>{const p=Math.pow(10,Math.floor(Math.log10(r)))||1,m=r/p;
    return (m<1.5?1:m<3?2:m<7?5:10)*p};
  const st=okragly((hi-lo+2*pad)/4);
  let g="";for(let v=Math.ceil((lo-pad)/st)*st;v<=hi+pad;v+=st)
    g+=`<line x1="${L}" x2="${W-R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="${CSS("--line")}"/>`
      +`<text x="${L-7}" y="${(Y(v)+4).toFixed(1)}" text-anchor="end" fill="${CSS("--faint")}" font-size="${FS(W)}">${osLbl(v)}</text>`;
  let d="",otw=false;
  kw.forEach((v,i)=>{if(v==null){otw=false;return}d+=(otw?"L":"M")+X(i).toFixed(1)+" "+Y(v).toFixed(1)+" ";otw=true});
  const ost=kw.length-1;
  const hit=daty.map((dd,i)=>({cx:X(i),html:kw[i]==null?`<div class="th">${dd}</div>`
    :`<div class="th">${dd}</div><div class="tr">Wartość<span class="tv">${zl(kw[i])} USD</span></div>
      <div class="tr">Zmiana<span class="tv">${sg((kw[i]/B0.kwota-1)*100)}%</span></div>`}));
  if(glowa)glowa.innerHTML=`<div class="gh1">${zl(B0.kwota)} USD <i>→</i> ${zl(konc)} USD</div>
    <div class="gh2 ${zm>=0?"pos":"neg"}">${sg(zm*100)}%</div>
    <div class="gh3">${dLbl(daty[0])} ${daty[0].slice(0,4)} — ${dLbl(daty.at(-1))} ${daty.at(-1).slice(0,4)}</div>`;
  if(nota)nota.textContent=(B0.wlasny
    ?`Liczone od dnia, w którym wszedł Twój pierwszy kapitał, na przyjętych ${zl(B0.kwota)} USD — to kwota umowna, nie Twoja. `
    :`Nie masz wpisów, więc liczone od początku historii strategii, na przyjętych ${zl(B0.kwota)} USD. `)
    +`To jeden wkład na starcie i zero dopłat — czysty wynik strategii, po podatku 19% i kosztach. `
    +`Kończy się na ${dLbl(daty.at(-1))}, bo to ostatni ZAMKNIĘTY okres transzy; `
    +`trwający okres nie jest tu liczony, więc bieżącego miesiąca tu nie ma. `
    +`Twój rachunek wygląda inaczej, bo dopłacałeś w trakcie; to pokazuje wykres na Pulpicie.`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Ile zrobila strategia na kwocie" data-hover='${HV({W,H,max:(W-L-R)/Math.max(daty.length,2),hit})}'>
    <defs><linearGradient id="gg" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="${col}" stop-opacity=".28"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    ${g}<path d="${d} L${X(ost).toFixed(1)} ${H-B} L${X(0).toFixed(1)} ${H-B} Z" fill="url(#gg)"/>
    <line x1="${L}" x2="${W-R}" y1="${Y(B0.kwota).toFixed(1)}" y2="${Y(B0.kwota).toFixed(1)}" stroke="${CSS("--line-strong")}" stroke-width="1.6" stroke-dasharray="5 5"/>
    <path d="${d}" fill="none" stroke="${col}" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${X(ost).toFixed(1)}" cy="${Y(kw[ost]).toFixed(1)}" r="5" fill="${col}" stroke="${CSS("--bg")}" stroke-width="2.2"/>
    <line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="${CSS("--line-strong")}" style="opacity:0"/>
    <text x="${L}" y="${H-7}" fill="${CSS("--faint")}" font-size="${nr?11:12}">${daty[0].slice(0,7)}</text>
    <text x="${W-R}" y="${H-7}" text-anchor="end" fill="${CSS("--faint")}" font-size="${nr?11:12}">${daty.at(-1).slice(0,7)}</text>
  </svg>`});

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
  const {cel:CEL,suma:SUMA}=celOsiagalny();
  const rows=[...new Set([...Object.keys(CEL),...Object.keys(HOLDINGS)])]
    .sort((a,b)=>(a==="GOTOWKA")-(b==="GOTOWKA")||ORDER.indexOf(a)-ORDER.indexOf(b))
    .map(t=>({t,pp:((HOLDINGS[t]||0)/tot-(CEL[t]||0)/SUMA)*100,have:HOLDINGS[t]||0,want:CEL[t]||0}));
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
/* "Do zrobienia" dotyczy OSTATNIEGO policzonego sygnalu, nie najblizszego terminu.
   Sygnalu na przyszla transze jeszcze nie ma - powstaje dopiero z kursu z jej dnia -
   wiec ruch "na zapas" celowalby w target, ktory i tak zostanie przeliczony. Dopoki
   nowy sygnal nie powstanie, jedyny ruch, ktory ma sens, to ten z ostatniej transzy:
   albo zostal zrobiony i odchylenia sa zerowe, albo nie zostal i wlasnie o tym trzeba
   przypomniec. Dzien po transzy panel ma pokazywac zaleglosc, nie nastepny termin. */
function ostatniSygnal(){
  const i=SIGNALS.length>1&&SIGNALS[1].date>SIGNALS[0].date?1:0;
  return {i,s:SIGNALS[i]}}
const cur=()=>CURV==="usd"
  ? {v:VUSD,p:PUSD,u:"USD",alt:{v:VALUE,u:"zł"},r:RETC.usd,twr:PORT?.twr.usd??0,k:x=>x}
  : {v:VALUE,p:PAID,u:"zł", alt:{v:VUSD, u:"USD"},r:RETC.pln,twr:PORT?.twr.pln??0,k:x=>x*FXN};

/* Punkty widoczne na Pulpicie: KAZDY wpisany dzien, przyciety do wybranego
   zakresu. Nie miesiace - miesiac bez wpisu nic nie mowi, a dwa wpisy w jednym
   miesiacu to dwie rozne informacje. */
function trackWidok(){
  const pln=CURV!=="usd";
  const pkt=TRACK.map(p=>({d:p.d,v:pln?p.wartPln:p.wart,p:pln?p.wplPln:p.wpl,ruch:p.ruch||0}))
    .filter(x=>x.v!=null&&x.p!=null);
  if(!RNG||pkt.length<3)return pkt;
  const o=new Date(pkt.at(-1).d);
  const gr=Date.UTC(o.getUTCFullYear(),o.getUTCMonth()-RNG,o.getUTCDate());
  const w=pkt.filter(x=>Date.parse(x.d)>=gr);
  return w.length>=2?w:pkt.slice(-2);
}
const dLbl=d=>(+d.slice(8,10))+" "+MN[+d.slice(5,7)-1];

chart("c-hero",W=>{
  if(BRAK)return "";
  const pkt=trackWidok();
  if(pkt.length<2)return "";
  const nr=W<520,H=nr?180:220,T=16,B=28,L=6,R=6;
  const ts=x=>Date.parse(x.d),t0=ts(pkt[0]);
  const t1=Math.max(ts(pkt.at(-1)),t0+1);
  const X=x=>L+(W-L-R)*(ts(x)-t0)/(t1-t0);
  const all=pkt.flatMap(x=>[x.v,x.p]);
  const lo=Math.min(...all),hi=Math.max(...all),pad=(hi-lo)*.16||Math.max(1,Math.abs(hi)*.06);
  const Y=v=>T+(H-T-B)*(1-(v-lo+pad)/(hi-lo+2*pad));
  const pa=k=>pkt.map((x,i)=>(i?"L":"M")+X(x).toFixed(1)+" "+Y(x[k]).toFixed(1)).join(" ");
  const up=pkt.at(-1).v>=pkt[0].v,col=up?CSS("--pos-soft2"):CSS("--neg");
  const jed=CURV==="usd"?"USD":"zł";
  const hit=pkt.map(x=>({cx:X(x),html:`<div class="th">${x.d}</div>
    <div class="tr">Wartość<span class="tv">${zl(x.v)} ${jed}</span></div>
    <div class="tr">Wpłacone<span class="tv">${zl(x.p)} ${jed}</span></div>`
    +(x.ruch?`<div class="tr">${x.ruch>0?"Wpłata":"Wypłata"}<span class="tv">${zl(Math.abs(x.ruch))} USD</span></div>`:"")}));
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Wartosc portfela w czasie" data-hover='${HV({W,H,max:(W-L-R)/Math.max(pkt.length,2),hit})}'>
    <defs><linearGradient id="hg" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="${col}" stop-opacity=".30"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    <path d="${pa("v")} L${X(pkt.at(-1)).toFixed(1)} ${H-B} L${X(pkt[0]).toFixed(1)} ${H-B} Z" fill="url(#hg)"/>
    ${pkt.filter(x=>x.ruch).map(x=>`<line x1="${X(x).toFixed(1)}" x2="${X(x).toFixed(1)}" y1="${T}" y2="${H-B}" stroke="${CSS(x.ruch>0?"--cash":"--warn")}" stroke-width="1.2" stroke-dasharray="3 3" opacity=".8"/>`).join("")}
    <path d="${pa("p")}" fill="none" stroke="${CSS("--line-strong")}" stroke-width="1.8" stroke-dasharray="5 5"/>
    <path d="${pa("v")}" fill="none" stroke="${col}" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>
    ${pkt.map((x,i)=>`<circle cx="${X(x).toFixed(1)}" cy="${Y(x.v).toFixed(1)}" r="${i===pkt.length-1?5:3.2}" fill="${col}" stroke="${CSS("--bg")}" stroke-width="2.2"/>`).join("")}
    <line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="${CSS("--line-strong")}" style="opacity:0"/>
    <text x="${L}" y="${H-7}" fill="${CSS("--faint")}" font-size="${nr?11:12}">${dLbl(pkt[0].d)}</text>
    <text x="${W-R}" y="${H-7}" text-anchor="end" fill="${CSS("--faint")}" font-size="${nr?11:12}">${dLbl(pkt.at(-1).d)}</text>
  </svg>`});

/* Ile konto jest nad albo pod wplaconym - w kazdym dniu, ktory wpisales.
   Krzywa kapitalu rosnie takze od samych wplat, wiec sama nie odpowiada na
   pytanie "jestem na plusie czy na minusie". Ta odpowiada. */
chart("c-zysk",W=>{
  if(BRAK)return "";
  const pkt=trackWidok().map(x=>({d:x.d,z:x.v-x.p,v:x.v,p:x.p}));
  const nota=document.getElementById("zyskNote");
  if(pkt.length<2){if(nota)nota.textContent="";return ""}
  const nr=W<520,H=nr?160:190,T=16,B=26,L=6,R=6;
  const ts=x=>Date.parse(x.d),t0=ts(pkt[0]),t1=Math.max(ts(pkt.at(-1)),t0+1);
  const X=x=>L+(W-L-R)*(ts(x)-t0)/(t1-t0);
  const zs=pkt.map(x=>x.z);
  const lo=Math.min(0,...zs),hi=Math.max(0,...zs),pad=(hi-lo)*.18||1;
  const Y=v=>T+(H-T-B)*(1-(v-lo+pad)/(hi-lo+2*pad));
  const d0=pa=>pa.map((x,i)=>(i?"L":"M")+X(x).toFixed(1)+" "+Y(x.z).toFixed(1)).join(" ");
  const ost=pkt.at(-1).z,col=CSS(ost>=0?"--pos":"--neg");
  const jed=CURV==="usd"?"USD":"zł";
  const hit=pkt.map(x=>({cx:X(x),html:`<div class="th">${x.d}</div>
    <div class="tr">${x.z>=0?"Nad wpłaconym":"Pod wpłaconym"}<span class="tv" style="color:${CSS(x.z>=0?"--pos":"--neg")}">${zl(x.z)} ${jed}</span></div>
    <div class="tr">Wartość<span class="tv">${zl(x.v)} ${jed}</span></div>
    <div class="tr">Wpłacone<span class="tv">${zl(x.p)} ${jed}</span></div>`
    +(x.p?`<div class="tr">Wobec wpłaconego<span class="tv">${sg2(x.z/x.p*100)}%</span></div>`:"")}));
  if(nota)nota.textContent=ost>=0
    ? `Linia nad zerem znaczy, że konto jest warte więcej, niż w nie włożyłeś. Teraz: ${zl(ost)} ${jed} nad.`
    : `Linia pod zerem znaczy, że konto jest warte mniej, niż w nie włożyłeś. Teraz: ${zl(-ost)} ${jed} pod.`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Ile konto jest nad albo pod wplaconym" data-hover='${HV({W,H,max:(W-L-R)/Math.max(pkt.length,2),hit})}'>
    <defs><linearGradient id="zg" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="${col}" stop-opacity=".28"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    <path d="${d0(pkt)} L${X(pkt.at(-1)).toFixed(1)} ${Y(0).toFixed(1)} L${X(pkt[0]).toFixed(1)} ${Y(0).toFixed(1)} Z" fill="url(#zg)"/>
    <line x1="${L}" x2="${W-R}" y1="${Y(0).toFixed(1)}" y2="${Y(0).toFixed(1)}" stroke="${CSS("--line-strong")}"/>
    <text x="${W-R}" y="${Y(0)-5}" text-anchor="end" fill="${CSS("--faint")}" font-size="${nr?10:11}">wpłacone</text>
    <path d="${d0(pkt)}" fill="none" stroke="${col}" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>
    ${pkt.map((x,i)=>`<circle cx="${X(x).toFixed(1)}" cy="${Y(x.z).toFixed(1)}" r="${i===pkt.length-1?5:3.2}" fill="${CSS(x.z>=0?"--pos":"--neg")}" stroke="${CSS("--bg")}" stroke-width="2.2"/>`).join("")}
    <line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="${CSS("--line-strong")}" style="opacity:0"/>
    <text x="${L}" y="${H-7}" fill="${CSS("--faint")}" font-size="${nr?11:12}">${dLbl(pkt[0].d)}</text>
    <text x="${W-R}" y="${H-7}" text-anchor="end" fill="${CSS("--faint")}" font-size="${nr?11:12}">${dLbl(pkt.at(-1).d)}</text>
  </svg>`});

/* Twoj wynik obok wyniku strategii. Obie linie licza sie metoda TWR - wplaty
   i wyplaty nie ruszaja wyniku, wiec da sie je zestawic. Punktem wspolnym jest
   dzien Twojego pierwszego wpisu: tam obie startuja ze 100. */
function serieVs(){
  const pole=CURV==="usd"?"idx":"idxPln";
  const okno=trackWidok();
  if(okno.length<2)return null;
  const pkt=TRACK.filter(p=>p.d>=okno[0].d&&p[pole]!=null);
  if(pkt.length<2||!pkt[0][pole])return null;
  const od=pkt[0].d,doD=pkt.at(-1).d;
  const C=PERF.compare||{},dat=C.dates||[];
  const rebase=k=>{
    if(!C[k])return null;
    const pary=dat.map((d,i)=>[d,C[k][i]]).filter(([,v])=>v!=null&&v>0);
    const baza=pary.filter(([d])=>d<=od).at(-1);
    if(!baza)return null;
    const s=pary.filter(([d])=>d>=baza[0]&&d<=doD).map(([d,v])=>({d,i:v/baza[1]}));
    return s.length>=2?s:null;
  };
  return {moje:pkt.map(p=>({d:p.d,i:p[pole]/pkt[0][pole]})),
          strategia:rebase("strategy"),rynek:rebase("cspx"),od,doD};
}

chart("c-vs",W=>{
  if(BRAK)return "";
  const S=serieVs();
  if(!S){document.getElementById("l-vs").innerHTML="";return ""}
  const linie=[["Ty",S.moje,CSS("--accent"),2.8],
               ["Strategia",S.strategia,CSS("--s1"),2],
               ["S&P 500",S.rynek,CSS("--faint"),1.6]].filter(x=>x[1]);
  const wsz=linie.flatMap(x=>x[1]);
  const nr=W<520,H=nr?170:200,T=16,B=26,L=6,R=6;
  const t0=Math.min(...wsz.map(p=>Date.parse(p.d)));
  const t1=Math.max(t0+1,...wsz.map(p=>Date.parse(p.d)));
  const lo=Math.min(...wsz.map(p=>p.i)),hi=Math.max(...wsz.map(p=>p.i));
  const pad=(hi-lo)*.18||.02;
  const X=d=>L+(W-L-R)*(Date.parse(d)-t0)/(t1-t0);
  const Y=v=>T+(H-T-B)*(1-(v-lo+pad)/(hi-lo+2*pad));
  const pa=s=>s.map((p,i)=>(i?"L":"M")+X(p.d).toFixed(1)+" "+Y(p.i).toFixed(1)).join(" ");
  const naDzien=(s,d)=>s.filter(p=>p.d<=d).at(-1);
  const hit=S.moje.map(p=>({cx:X(p.d),html:`<div class="th">${p.d}</div>`
    +linie.map(([n,s])=>{const q=naDzien(s,p.d);return q
      ?`<div class="tr">${n}<span class="tv" style="color:${q.i>=1?CSS("--pos"):CSS("--neg")}">${sg2((q.i-1)*100)}%</span></div>`:""}).join("")}));
  legend("l-vs",linie.map(([n,,c])=>[n,c]));
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Twoj wynik obok strategii" data-hover='${HV({W,H,max:(W-L-R)/Math.max(S.moje.length,2),hit})}'>
    <line x1="${L}" x2="${W-R}" y1="${Y(1).toFixed(1)}" y2="${Y(1).toFixed(1)}" stroke="${CSS("--line")}" stroke-dasharray="4 4"/>
    ${linie.map(([,s,c,gr])=>`<path d="${pa(s)}" fill="none" stroke="${c}" stroke-width="${gr}" stroke-linejoin="round" stroke-linecap="round"/>`).join("")}
    ${linie.map(([,s,c])=>`<circle cx="${X(s.at(-1).d).toFixed(1)}" cy="${Y(s.at(-1).i).toFixed(1)}" r="4" fill="${c}" stroke="${CSS("--bg")}" stroke-width="2"/>`).join("")}
    <line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="${CSS("--line-strong")}" style="opacity:0"/>
    <text x="${L}" y="${H-7}" fill="${CSS("--faint")}" font-size="${nr?11:12}">${dLbl(S.od)}</text>
    <text x="${W-R}" y="${H-7}" text-anchor="end" fill="${CSS("--faint")}" font-size="${nr?11:12}">${dLbl(S.doD)}</text>
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
  const brakPln=FXN==null||!TRACK.some(p=>p.wartPln!=null&&p.wplPln!=null);
  const plnBtn=document.querySelector('#curTog button[data-cur="pln"]');
  plnBtn.disabled=brakPln;
  plnBtn.title=brakPln?"Brak kursu USD/PLN — kursy wpisuje admin":"";
  if(brakPln&&CURV!=="usd"){CURV="usd";
    document.querySelectorAll("#curTog button").forEach(x=>x.setAttribute("aria-pressed",String(x.dataset.cur==="usd")))}
  const pln=CURV!=="usd",jed=pln?"zł":"USD";
  /* Kwoty bierzemy z TYCH SAMYCH punktow, ktore widac na wykresie - inaczej
     liczba w naglowku mowilaby o czym innym niz krzywa pod nia. */
  const okno=trackWidok(),a0=okno[0],ostW=okno.at(-1);
  const V=ostW?ostW.v:0,P=ostW?ostW.p:0,zy=V-P;
  const okres=okno.length<2?0:V-a0.v-(P-a0.p);
  /* Procent to TWR okna, nie zysk/wartosc poczatkowa. Przy wplatach w srodku
     ten drugi zawyza wynik: 30 tys. urosle do 89 tys. po dolozeniu 41 tys.
     wygladaloby na +60%, a zarobione jest kilkanascie. */
  const polIdx=pln?"idxPln":"idx";
  const i1=okno.length>1?TRACK.find(p=>p.d===a0.d)?.[polIdx]:null;
  const i2=okno.length>1?TRACK.find(p=>p.d===ostW.d)?.[polIdx]:null;
  const pct=i1&&i2?(i2/i1-1)*100:0;
  const twr=pln?(PORT?.twr.pln??0):(PORT?.twr.usd??0);
  document.getElementById("heroVal").innerHTML=`${zl(V)}<span>${jed}</span>`;
  const pelneOkno=okno.length>=2&&a0.d===(TRACK.find(p=>(pln?p.wartPln:p.wart)!=null)||{}).d;
  /* Najwieksza liczba na ekranie mowi o CALEJ historii, nie o wycinku. Wynik
     wybranego zakresu stoi nizej, przy przyciskach zakresu - inaczej naglowek
     potrafi chwalic sie zyskiem z ostatnich tygodni, kiedy od poczatku jest
     strata. */
  document.getElementById("heroSub").innerHTML=okno.length>=2
    ? `<span style="color:var(${zy>=0?"--pos":"--neg"})">${zy>=0?"+":"−"}${zl(zy)} ${jed} · ${sg2(twr)}%</span>`
      +` <em>od początku</em>`
    : pln&&TRACK.length>1
      ? `<em>Wcześniejsze wpisy nie mają kursu — w złotych mam tylko ten jeden punkt.</em>`
      : `<em>Jeden wpis — wynik policzę od drugiego.</em>`;
  const rn=document.getElementById("rngNote");
  rn.hidden=okno.length<2;
  /* Gdy od poczatku jest strata, "+8 616" czyta sie jak zysk, a to jest
     odrobiona czesc straty. Nazywamy rzecz po imieniu. */
  const zmiana=!okres?"bez zmian"
    :zy<0?(okres>0?`strata zmalała o ${zl(okres)} ${jed}`:`strata urosła o ${zl(-okres)} ${jed}`)
    :(okres>0?`+${zl(okres)} ${jed}`:`−${zl(-okres)} ${jed}`);
  if(okno.length>=2)rn.innerHTML=pelneOkno
    ? `Wykres pokazuje całą historię: ${dLbl(a0.d)} – ${dLbl(ostW.d)}.`
    : `Od ${dLbl(a0.d)}, czyli tyle, ile widać na wykresie: `
      +`<b style="color:var(${okres>=0?"--pos":"--neg"})">${zmiana} · ${sg(pct)}%</b>`
      +`. Całość liczy kwota wyżej.`;
  const tOst=ostW?TRACK.find(p=>p.d===ostW.d):null;
  const alt=tOst?(pln?tOst.wart:tOst.wartPln):null;
  document.getElementById("heroAlt").textContent=alt==null?"":`≈ ${zl(alt)} ${pln?"USD":"zł"}`;
  document.getElementById("heroStats").innerHTML=[
    ["Wpłacone łącznie",zl(P)+" "+jed,"--muted"],
    ["Wynik od początku",(zy>=0?"+":"−")+zl(zy)+" "+jed,zy>=0?"--pos":"--neg"],
    ["TWR od początku",sg2(twr)+"%",twr>=0?"--pos":"--neg"]
  ].map(([l,v,c])=>`<div><span>${l}</span><b style="color:var(${c})">${v}</b></div>`).join("");

  const hn=document.getElementById("heroNote"),uw=[];
  for(const b of (PORT?.bezStanu||[]))
    uw.push(`Konto ${b} ma wpłaty, ale ani jednego wpisanego stanu — jego pieniądze nie wchodzą do żadnej z liczb powyżej.`);
  for(const s of (PORT?.spoznione||[]))
    uw.push(`Na koncie ${s.konto} są wpłaty sprzed pierwszego wpisanego stanu (${s.od}). `
      +`Liczą się dopiero od tej daty — wcześniej nie wiadomo, ile konto było warte. `
      +`Dopisz stan z wcześniejszej daty, jeśli go znasz.`);
  hn.hidden=!uw.length;
  hn.textContent=uw.join(" ");

  const S=serieVs(),nota=document.getElementById("vsNote");
  if(!S)nota.textContent=TRACK.length<2
    ? "Porównanie pojawi się przy drugim wpisie stanu konta — jeden punkt nie tworzy wyniku."
    : "Twoje daty nie nakładają się z policzoną historią strategii.";
  else{
    const kon=S.strategia&&S.strategia.at(-1).d<S.doD?S.strategia.at(-1).d:null;
    nota.textContent="Obie linie to TWR: wpłaty i wypłaty nie ruszają wyniku, więc da się je zestawić. "
      +"Start = 0% w dniu Twojego pierwszego wpisu w tym zakresie."
      +(kon?` Linia strategii urywa się ${kon} — dalej nie ma jeszcze policzonego okresu.`:"");
  }

  renderAccounts();

  const HT=Object.values(HOLDINGS).reduce((a,b)=>a+b,0);
  document.getElementById("holdList").innerHTML=!HT?BRAK_SKLADU:Object.entries(HOLDINGS).sort((a,b)=>b[1]-a[1]).map(([t,v])=>{
    const nm=t==="GOTOWKA"?"Gotówka":t;
    return `<div class="row"><div class="ic" style="background:${CSS(KOL[t]||"--s6")}">${nm.slice(0,2).toUpperCase()}</div>
      <div class="nm">${nm}<em>${t==="GOTOWKA"?"nieulokowane":(ROLE[t]||"")}</em></div>
      <div class="vl"><b>${kw(v)}</b><span>${pc(v/HT)}</span></div></div>`}).join("");
}
document.getElementById("curTog").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b||b.disabled)return;
  document.querySelectorAll("#curTog button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));
  CURV=b.dataset.cur;renderPulpit();
  for(const id of ["c-hero","c-month","c-vs","c-zysk"])mount(charts.find(c=>c.id===id))});
document.getElementById("ranges").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b)return;
  document.querySelectorAll("#ranges button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));
  RNG=+b.dataset.r;renderPulpit();
  for(const id of ["c-hero","c-vs","c-zysk"])mount(charts.find(c=>c.id===id))});

function renderActions(){
  document.getElementById("sygDane").hidden=BRAK;
  if(BRAK)return;
  if(!Object.keys(HOLDINGS).length){
    document.getElementById("actions").innerHTML=BRAK_SKLADU;return}
  const R=nastepnyRebalans(),{s:SYG}=ostatniSygnal();
  const nota=`<div class="actnote">Odległość od celu <b>obu transz łącznie</b>, liczona na wartości
    każdego konta — te same liczby co w „Na których kontach”. Po dniu transzy ta odległość JEST jej
    ruchem, bo cel łączony zmienia się dokładnie o to, co zmieniła ta transza.
    Ostatni policzony sygnał: transza ${SYG.tranche}-tego z ${SYG.date}. Druga połowa rusza
    ${R.opis}${R.dni>=0?` (${R.kiedy})`:""} – sygnału na tamten dzień jeszcze nie ma, bo liczy się
    go z kursu zamknięcia z dnia transzy.</div>`;
  const karta=r=>
    `<div class="act ${r.d>0?"buy":"sell"}"><i class="w"></i><div><div class="t">${r.d>0?"Kup":"Sprzedaj"} ${r.t}</div>
     <div class="sub">${ROLE[r.t]||""}</div></div><div class="q"><b>${kw(Math.abs(r.d))}</b>
     <span class="sub">cel ${kw(r.want)}</span></div></div>`;
  const bez='<div class="act hold"><i class="w"></i><div><div class="t">Bez zmian</div></div></div>';
  const lista=(cel,mam,prog)=>[...new Set([...Object.keys(cel),...Object.keys(mam)])]
    .filter(t=>t!=="GOTOWKA")
    .map(t=>({t,want:cel[t]||0,d:(cel[t]||0)-(mam[t]||0)}))
    .filter(r=>Math.abs(r.d)>=prog).sort((a,b)=>Math.abs(b.d)-Math.abs(a.d));
  /* Zlecenia sklada sie U BROKERA, nie w portfelu lacznym - a walor potrafi lezec na
     dwoch kontach naraz (CMOD jest i w BEST17, i w GPM), wiec lista laczna mowilaby
     "sprzedaj CMOD 14 169" i nie dalo by sie tego wykonac.
     Porownujemy z celem LACZONYM obu transz, nie z celem jednej transzy wobec
     proporcjonalnie przypisanego stanu. Tamto zalozenie - ze kazda transza trzyma ten
     sam miks - jest falszywe dokladnie wtedy, gdy transze roznia sie skladem, czyli w
     jedynym ciekawym przypadku: po ruchu CMOD->CSPX portfel stal na celu, a box
     kazal sprzedac CMOD za 4 235 i dokupic CSPX za 4 080. Prog i cel sa teraz takie
     same jak w viewAcc, wiec oba widoki nie moga sie rozjechac. */
  const konta=(SETUPS[SETUP]?.accounts||[]).filter(a=>a.value>0);
  const perK=PORT?.perKonto||{};
  const rozbij=konta.length>1&&konta.every(a=>perK[a.name]);
  document.getElementById("actions").innerHTML=nota+(rozbij
    ? konta.map(a=>{
        const rows=lista(accComp(a),perK[a.name],Math.max(a.value*.01,1));
        return `<div class="actkonto">${esc(a.name)}<span>${accLegs(a)}</span></div>`
          +(rows.length?rows.map(karta).join(""):bez)}).join("")
    : (()=>{const{cel,suma}=celOsiagalny();
        const rows=lista(cel,HOLDINGS,Math.max(suma*.01,1));
        return rows.length?rows.map(karta).join(""):bez})())}
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
  document.getElementById("histList").innerHTML=tabelaHist()}
const pp1=n=>n.toFixed(1).replace(".",",")+"%";
const chip=(t,pp,klasa)=>`<span class="chip ${klasa}">
  <i style="background:${CSS(KOL[t]||"--s6")}"></i>${esc(t)}<b>${pp1(pp)}</b></span>`;
const normHist=h=>Array.isArray(h)
  ?{date:h[0],tranche:h[1],best17:h[2],picks:h[3],gpm:h[4],note:h[5],cash:0}
  :h;
/* Ktore nogi niesie konto i w jakiej proporcji - ta sama normalizacja co w
   accComp, zeby ruch nogi przeliczyc na punkty procentowe KONTA. Konto niosace
   cala noge dostaje jej procenty bez zmiany. */
function kontaNog(){
  return ((PORT&&PORT.accounts)||[]).map(a=>{
    const w={};let s=0;
    for(const l of["best17","gpm"]){const f=(a.alloc&&a.alloc[l])||0;if(f>0){w[l]=f;s+=f}}
    if(!s)return null;
    for(const l in w)w[l]/=s;
    return{name:a.name,w}}).filter(Boolean)}
const ruchKonta=(h,k,kier)=>{
  const m={};
  for(const[l,f]of Object.entries(k.w))
    for(const r of (h.legs&&h.legs[l]&&h.legs[l][kier])||[])m[r.t]=(m[r.t]||0)+r.pp*f;
  return Object.entries(m).filter(([,v])=>v>.05).sort((a,b)=>b[1]-a[1])};
function tabelaHist(){
  const K=kontaNog();
  const wiersze=HIST.map(normHist).map(h=>{
    const rozbij=K.length>1&&h.legs;
    const perKonto=(kier,klasa)=>{
      return K.map(k=>{const r=ruchKonta(h,k,kier);return r.length
        ?`<div class="kgr"><span class="kontoL">${esc(k.name)}</span><span class="kchips">${
            r.map(([t,pp])=>chip(t,pp,klasa)).join("")}</span></div>`:""}).join("")};
    const znane=Array.isArray(h.sold)&&Array.isArray(h.bought);
    const nic=znane&&!h.sold.length&&!h.bought.length;
    const sp=rozbij?perKonto("sold","out")
      :(h.sold?.length?h.sold.map(r=>chip(r.t,r.pp,"out")).join(""):"");
    const kp=rozbij?perKonto("bought","in")
      :(h.bought?.length?h.bought.map(r=>chip(r.t,r.pp,"in")).join(""):"");
    const got=h.cash??0,poprz=h.cash_prev;
    const strzalka=poprz==null||Math.abs(got-poprz)<.05?""
      :`<em class="${got>poprz?"up":"dn"}">${got>poprz?"▲":"▼"}${pp1(Math.abs(got-poprz))}</em>`;
    return `<tr>
      <td class="kiedy"><b>${esc(h.date)}</b><span class="tr${h.tranche}">transza ${h.tranche}</span></td>
      ${nic?'<td class="bezzmian" colspan="2">bez zmian · nic nie kupujesz ani nie sprzedajesz</td>'
        :!znane?`<td class="bezzmian" colspan="2">${esc(h.note||"")}</td>`
            :`<td class="ruch" data-l="Sprzedane">${sp||'<span class="nic">—</span>'}</td>
              <td class="ruch" data-l="Kupione">${kp||'<span class="nic">—</span>'}</td>`}
      <td class="num got">${got>.05?`<b>${pp1(got)}</b>`:'<span class="nic">0%</span>'}${strzalka}</td></tr>`}).join("");
  return tbl(`<th>Kiedy</th><th>Sprzedane</th><th>Kupione</th><th class="num">Gotówka</th>`,wiersze)}
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
    const o=accComp(a),cap=accTarget(a),ideal=accIdeal(a),roz=a.value-ideal;
    const mam=(PORT?.perKonto||{})[a.name]||{};
    const jed=CURV==="usd"?"USD":"zł";
    h+=`<h2 class="psec">${esc(a.name)} <span class="sub" style="font-weight:400">· ${accLegs(a)}</span></h2>`
      +`<p class="accsum">masz <b>${kw(a.value)}</b>`
      +(Math.abs(roz)<Math.max(ideal*.02,1)?" · zgodnie z modelem 50/50"
        :` · wg modelu 50/50 ${kw(ideal)}, czyli <em class="${roz>0?"nad":"pod"}">${
            roz>0?"nadwyżka":"niedobór"} ${kw(Math.abs(roz))}</em>`)
      +`</p>`
      +tbl(`<th>ETF</th><th>masz ${jed}</th><th>cel ${jed}</th><th>różnica</th><th class="udzkol">Udział</th>`,
        [...new Set([...Object.keys(o),...Object.keys(mam)])]
          .sort((x,y)=>(o[y]||0)-(o[x]||0)||(mam[y]||0)-(mam[x]||0)).map(t=>{
          const ma=mam[t]||0,ce=o[t]||0,d=ce-ma;
          const kol=Math.abs(d)<Math.max(cap*.01,1)?"--faint":d>0?"--pos":"--neg";
          return `<tr><td><span class="sw-in" style="background:${CSS(KOL[t]||"--s6")}"></span>${t==="GOTOWKA"?"Gotówka":t}</td>
           <td class="num">${zlk(ma)}</td><td class="num">${zlk(ce)}</td>
           <td class="num" style="color:var(${kol})">${Math.abs(d)<Math.max(cap*.01,1)?"—":(d>0?"+":"−")+zlk(Math.abs(d))}</td>
           <td class="num udzkol">${cap?pc(ce/cap):"—"}</td></tr>`}).join(""))}
  return h}
/* Jedyny widok, ktorego nie ma wyzej: podzial miedzy KONTA. Sklad calosci
   i transz pokazuja paski w sekcji "Co trzymac" - powtarzanie go w tabelce
   tylko rozwadnialo ekran. */
function renderSklad(){document.getElementById("skladBody").innerHTML=viewAcc();fillSel()}
/* Instrukcja dnia transzy. Krokow jest wiecej dla admina, bo tylko on dokłada
   ceny i odswieza dane - zwykly user dostaje sygnal juz policzony. */
const KROKI_USER=[
  ["Sprawdź, która transza","Na ekranie <b>Sygnał</b>, na górze, stoi najbliższy rebalans i ile dni zostało. "
   +"Ale <b>Do zrobienia</b> dotyczy <b>ostatniej policzonej</b> transzy, czyli tej, którą masz wykonać — "
   +"sygnału na następną jeszcze nie ma. Ruszasz tylko tę jedną; druga czeka na swoją datę."],
  ["Ustaw role kont (raz na zawsze)","<b>Wpisy → Konta</b>: przy każdym koncie wybierz, co na nim leży — "
   +"Wszystko, BEST17 albo GPM. Bez tego panel zgaduje z pozycji i myli się, bo CMOD i CSPX należą do obu nóg naraz."],
  ["Wpisz, co masz teraz","<b>Wpisy → Importuj stan konta</b> albo ręcznie: stan każdego konta "
   +"<b>z rozbiciem na walory</b>. Bez rozbicia panel zna tylko wartość i nie policzy zleceń."],
  ["Odczytaj zlecenia","<b>Sygnał → Do zrobienia</b> — kup/sprzedaj z kwotami. "
   +"Dokładniej, per konto: <b>Sygnał → Na których kontach</b>, kolumna <b>różnica</b>. "
   +"Plus to dokupienie, minus to sprzedaż."],
  ["Złóż zlecenia u brokera","Giełda w Londynie handluje 9:00–17:30 naszego czasu. "
   +"Jeśli nie zdążysz w dniu transzy, reguła brzmi „tego dnia <b>lub później</b>” — następna sesja też jest w porządku."],
  ["Wpisz stan po transakcjach","Jeszcze raz stan każdego konta, już po ruchu. Nadpisze ten sprzed — "
   +"i dobrze, bo na krzywej kapitału ma zostać stan faktyczny."],
  ["Sprawdź, czy się zgadza","<b>Sygnał → Ostatnie sygnały</b>: przy kilku kontach ruchy są rozbite na konta. "
   +"Powinny odpowiadać temu, co zrobiłeś."],
];
const KROKI_ADMIN=[
  ["Poczekaj na zamknięcie","Sygnał liczy się z <b>ceny zamknięcia dnia transzy</b>. Noga GPM domyka się "
   +"o 17:30 (Londyn), noga BEST17 o 22:00 (USA), bo jej wskaźniki liczą się na tickerach amerykańskich."],
  ["Odśwież dane — droga główna","Paczki dzienne ze stooq (sekcja z bazą danych): <code>d_us_txt</code> i <code>d_uk_txt</code>. "
   +"Rozpakuj obie, potem <b>z korzenia repo</b>:"
   +"<span class='cmd'>python3 tools/odswiez_dane.py ~/pobrane/d_us_txt --cel data/us\n"
   +"python3 tools/odswiez_dane.py ~/pobrane/d_uk_txt --cel data/uk</span>"
   +"Tak uruchomione to <b>tylko podgląd</b> — skrypt wypisze, co by podmienił, i nic nie zapisze. "
   +"Gdy lista się zgadza, powtórz oba z <code>--zapisz</code> na końcu. Podmienia wyłącznie pliki, które już są "
   +"w <code>data/</code>, i tylko wtedy, gdy paczka ma nowsze notowania. "
   +"<b>Ścieżkę ze spacją w nazwie bierz w cudzysłów</b> — inaczej powłoka rozbije ją na dwa argumenty "
   +"i dostaniesz <code>unrecognized arguments</code>. Można też wskazać <code>--cel data</code> (cały katalog) "
   +"i przelecieć obie nogi jednym uruchomieniem, jeśli paczki są rozpakowane obok siebie."],
  ["Wypchnij zmiany","<span class='cmd'>git add data\ngit commit -m \"Dane: RRRR-MM-DD\"\ngit push</span>"
   +"Workflow <b>Sygnał</b> ma trigger na <code>data/**</code> i odpali się sam — przeliczy sygnał, ceny wykonania "
   +"i historię, po czym wrzuci je na stronę. Można go też odpalić ręcznie: <b>Actions → Sygnał → Run workflow</b>. "
   +"Niezależnie od tego chodzi raz na dobę, o 7:23 UTC."],
  ["Szybka droga — dociągnięcie z Yahoo","Gdy nie chcesz ściągać paczki: <code>python3 tools/fetch_prices.py</code> "
   +"dokleja brakujące dni z Yahoo (bez <code>--zapisz</code> tylko sprawdza). Każdy ticker przechodzi trzy sita — "
   +"zgodność dziennych zwrotów, stały kurs przeliczenia i komplet sesji — więc część symboli może zostać odrzucona. "
   +"Dlatego po tym i tak zajrzyj w <b>Ceny → Kontrola danych</b>."],
  ["Albo ceny ręcznie — droga awaryjna","<b>Ceny → + Dopisz dzień</b>. Panel poprosi o <b>17 instrumentów</b>: "
   +"pięć z BEST17 i dwanaście z GPM. Dzień niekompletny jest w całości pomijany, "
   +"bo sygnał z połowy cen byłby błędny. Prawdziwe zamknięcie z paczki później i tak wygra nad wpisem ręcznym. "
   +"Ta droga nie daje notowań dziennych, więc krzywa kapitału i obsunięcie na Wynikach są z niej uboższe."],
  ["Sprawdź dane","<b>Ceny → Kontrola danych</b> plus lista dni do wpisania. Panel sam mówi, czego brakuje: "
   +"dwa dni na miesiąc, po jednym na transzę."],
  ["Dopisz kurs USD/PLN","<b>Wpisy → Kursy USD/PLN</b>, jeśli chcesz widzieć wartości w złotych. "
   +"Bez kursu z danego dnia panel nie przelicza — woli pokazać kreskę niż zmyśloną złotówkę."],
];
function renderPomoc(){
  const box=document.getElementById("pomocBody");if(!box)return;
  const st=document.getElementById("pomocStamp");
  const admin=!!ADMIN_BAZA;
  if(st)st.textContent=admin?"widok administratora":ZAL()?"widok użytkownika":"nie jesteś zalogowany";
  const lista=(kroki,od)=>`<ol class="kroki">`+kroki.map(([t,o],i)=>
    `<li><span class="kn">${od+i}</span><b>${t}</b><p>${o}</p></li>`).join("")+`</ol>`;
  let h="";
  if(!ZAL())h+=`<div class="card pusto"><b>Większość tych kroków wymaga zalogowania.</b>
    <p>Bez niego widzisz samą strategię — sygnał, wyniki i ceny. Portfel, stany kont i lista zleceń
    to dane prywatne i leżą w bazie, nie w tej stronie.</p>
    <button type="button" class="btn" data-login>Zaloguj się</button></div>`;
  if(admin){
    h+=`<h2 class="psec">Najpierw dane <span class="sub" style="font-weight:400">· tylko administrator</span></h2>`
      +lista(KROKI_ADMIN,1)
      +`<h2 class="psec">Potem portfel</h2>`+lista(KROKI_USER,KROKI_ADMIN.length+1);
  }else{
    h+=`<h2 class="psec">Krok po kroku</h2>`+lista(KROKI_USER,1)
      +`<p class="note">Cen i danych nie musisz dotykać — sygnał dostajesz policzony.</p>`;
  }
  box.innerHTML=h;
}
function renderAccounts(){
  const s=SETUPS[SETUP];
  document.getElementById("accCards").innerHTML=s.accounts.map(a=>{
    const o=accComp(a),cap=accTarget(a),d=a.value-cap,capo=Object.values(o).reduce((x,y)=>x+y,0);
    return `<div class="legc"><div class="t">${esc(a.name)} <em>${accLegs(a)}</em></div>
      <div class="n">${zlk(a.value)}<span>${CURV==="usd"?"USD":"zł"}</span></div>
      <div class="d">cel ${kw(cap)} · <span style="color:var(${Math.abs(d)<cap*.02?"--faint":"--warn"})">${d>=0?"+":"−"}${kw(Math.abs(d))}</span></div>
      <div class="d">TWR <span style="color:var(${a.usd>=0?"--pos":"--neg"})">${sg(a.usd)}% USD</span>${a.pln==null?"":` · <span style="color:var(${a.pln>=0?"--pos":"--neg"})">${sg(a.pln)}% PLN</span>`}</div>
      <div class="bar">${Object.entries(o).map(([t,v])=>{const pr=v/capo*100;
        return `<span style="flex:${pr};background:${CSS(KOL[t]||"--s6")}" title="${t} ${pc(v/capo)}">${pr>13?(t==="GOTOWKA"?"GOT.":t):""}</span>`}).join("")}</div></div>`}).join("");
  document.getElementById("accNote").textContent=s.accounts.length===1
    ?"Jedno konto: obie nogi w jednej liście, pozycje wspólne w jednym zleceniu."
    :"Różnicę wobec celu wyrównujesz przy wpłacie, nie przelewem między brokerami.";
  const tot=Object.values(HOLDINGS).reduce((x,y)=>x+y,0);
  const bil=bilansNog();
  document.getElementById("legBal").innerHTML=!bil?"":
    `<div class="legbal"><div class="t">Rozjazd nóg wobec 50/50</div>`
    +bil.map(r=>{const c=Math.abs(r.pp)<1?"--faint":r.pp>0?"--warn":"--cash";
      return `<div class="row"><div class="ic" style="background:${CSS(r.nazwa==="BEST17"?"--s1":"--s4")}">${r.nazwa.slice(0,2)}</div>
        <div class="nm">${r.nazwa}<em>masz ${kw(r.ma)} · połowa kapitału ${kw(r.cel)}</em></div>
        <div class="vl"><b style="color:var(${c})">${r.d>=0?"+":"−"}${kw(Math.abs(r.d))}</b><span>${sg(r.pp)} pp</span></div></div>`}).join("")
    +`<p class="note">Tego nie zamkniesz zleceniem — nogi leżą u różnych brokerów. Wyrównujesz kierunkiem
      następnej wpłaty, nie przelewem między nimi.</p></div>`;
  const {cel:CEL,suma:SUMA}=celOsiagalny();
  document.getElementById("driftList").innerHTML=!tot?BRAK_SKLADU:[...new Set([...Object.keys(CEL),...Object.keys(HOLDINGS)])]
    .map(t=>{const hh=HOLDINGS[t]||0,w=CEL[t]||0;return {t,h:hh,w,d:hh-w,pp:(hh/tot-w/SUMA)*100}})
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
  document.getElementById("addHint").textContent=PRC.missing?.length
    ? `Najbliższy brakujący: ${nastepnaData()}` : `Następny dzień wg reguły: ${nastepnaData()}`;
  rysujPrawoZapisu();rysujBraki();
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

/* Lista dni, ktorych silnikowi brakuje. Liczy ja pipeline (build_prices), bo
   tylko on wie, co naprawde jest w data/ - panel tylko pokazuje. */
function rysujBraki(){
  const b=PRC.missing||[],box=document.getElementById("brakiBox");
  if(!b.length){box.innerHTML="";box.hidden=true;return}
  box.hidden=false;
  const ile=b.length*INSTR.length;
  box.innerHTML=`<div class="braki"><b>Do wpisania: ${b.length} ${b.length===1?"dzień":b.length<5?"dni":"dni"} ·
      ${ile} ${ile<5?"ceny":"cen"}</b>
    <p>Silnik potrzebuje trzech dni z miesiąca: obu dni rebalansu i <b>ostatniej sesji</b> —
      na niej liczą się ranking i kanarek. Bez niej co czwarty okres wychodzi z innym składem.
      Jeśli któregoś dnia giełda była zamknięta, wpisz pierwszą sesję po nim.</p>
    <div class="dni">${b.map(x=>
      `<button type="button" data-brak="${x.date}"><b>${x.date.slice(8)}.${x.date.slice(5,7)}</b>${x.why}</button>`).join("")}</div></div>`;
}
/* nastepna data wedlug reguly: pierwsza sesja N-tego lub pozniej w kolejnym miesiacu */
function nastepnaData(){
  /* Najpierw to, czego naprawde brakuje - dopiero gdy nic nie brakuje, kolejny
     dzien z reguly. */
  if(PRC.missing?.length)return PRC.missing[0].date;
  const P=PRICES[PTAB],ost=P.dates.at(-1),d=new Date(ost+"T00:00:00Z");
  d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()+1);
  return ruleDate(d.getUTCFullYear(),d.getUTCMonth(),+PTAB)}

function rysujFormularz(){
  const P=PRICES[PTAB],ost=P.dates.length-1;
  document.getElementById("addForm").innerHTML=
    `<div class="hd"><label for="adData">Data</label><input type="date" id="adData" value="${nastepnaData()}">
       <span class="note">${PRC.missing?.length?"Pierwszy brakujący dzień":"Z reguły "+PTAB+"-tego"}. Przy każdym polu poprzednia cena — literówka rzuci się w oczy.</span></div>
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
document.getElementById("brakiBox").addEventListener("click",e=>{
  const b=e.target.closest("[data-brak]");if(!b)return;
  const f=document.getElementById("addForm");
  rysujFormularz();f.hidden=false;
  document.getElementById("adData").value=b.dataset.brak;
  f.scrollIntoView({block:"nearest"})});
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
    TX=z.map(r=>({id:r.id,d:r.d,a:r.a||"",t:r.t,k:r.k,px:r.px||null,ts:r.ts||0}));
  }catch(e){console.warn("nie udalo sie wczytac wpisow:",e.message)}
  try{
    ROLE_KONT={};
    for(const r of await FB.wczytaj(USER.uid,"role_kont"))
      if(r.konto&&ROLE_OK.includes(r.rola))ROLE_KONT[r.konto]=r.rola;
  }catch(e){console.warn("nie udalo sie wczytac rol kont:",e.message)}
  poWpisach();
}
async function ustawRoleKonta(konto,rola){
  if(!ZAL()){alert("Zaloguj się, żeby ustawić układ kont.");return}
  if(rola==="auto")delete ROLE_KONT[konto];else ROLE_KONT[konto]=rola;
  const id=konto.replace(/[^\w-]+/g,"_");
  if(FB)try{
    if(rola==="auto")await FB.usun(USER.uid,"role_kont",id);
    else await FB.zapisz(USER.uid,"role_kont",id,{konto,rola});
  }catch(e){alert("Nie zapisano układu kont: "+e.message)}
  poWpisach();
}
/* Kolejny wpis NIE kasuje poprzedniego - rowniez tego samego dnia. User: "glupio ze
   ginie stan konta, jak wtedy policzysz ile zarobilem". Zapisujemy `ts` (moment
   zapisu), zeby "ktory jest aktualny" bylo rozstrzygniete przez to, co wpisano
   pozniej, a nie przez kolejnosc zwrocona przez baze - sortowanie po samej dacie
   przy dwoch wpisach z jednego dnia remisuje. Wczesniejszy wpis zostaje w historii
   i jest w liscie oznaczony jako wczesniejszy z tego dnia. */
async function dodajTX(r){
  if(!ZAL()){alert("Zaloguj się, żeby prowadzić portfel.");return}
  r.ts=Date.now();
  r.id=r.id||(r.d+"_"+r.ts.toString(36));
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
/* Sama data nie wystarcza: przy dwoch wpisach z tego samego dnia komparator remisuje
   i "ostatni" zalezy od kolejnosci zwroconej przez baze. Decyduje `ts` - moment
   zapisu - wiec aktualny jest ten, ktory wpisano pozniej. Rekordy sprzed wprowadzenia
   `ts` nie maja go wcale; wtedy rozstrzyga id, zeby wynik byl chocby powtarzalny. */
const poDacie=(a,b)=>a.d.localeCompare(b.d)||(a.ts||0)-(b.ts||0)
  ||String(a.id||"").localeCompare(String(b.id||""));
/* Wczesniejszy wpis z tego samego dnia na to samo konto. NIE jest bledny ani
   zastapiony - to osobna, prawdziwa migawka (np. stan przed transakcjami i po).
   Krzywa ma rozdzielczosc dzienna i bierze ostatnia wartosc z dnia, tak jak kazde
   zamkniecie; na wyliczony wynik nie ma to wplywu, bo ogniwa TWR sie skracaja:
   (V_B/V_A)*(V_C/V_B) = V_C/V_A. Lista ma to oznaczyc, zeby bylo wiadomo, ktory
   wpis widac na wykresie - a nie po to, zeby sugerowac blad. */
const wczesniejszy=(r,lista)=>r.t==="stan"&&lista.some(x=>
  x!==r&&x.t==="stan"&&x.d===r.d&&x.a===r.a&&poDacie(r,x)<0);
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
  let w=null;
  for(const r of kursy()){if(r.d<=data)w=r.k;else break}
  return w;
}
const kursTeraz=()=>kursy().at(-1)?.k??null;
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
    if(!obs.has(OSTATNIA_OS[i])||!wart[i]||wpl[i]==null)return;
    if(poprz>=0&&wart[poprz]&&wpl[poprz]!=null)
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
  const przeplyw=r=>r.t==="wplata"?r.k:r.t==="wyplata"?-r.k:0;
  /* Konto wchodzi do sumy dopiero z pierwszym wpisanym stanem. Jego wplaty
     musza wejsc W TYM SAMYM MOMENCIE - inaczej wczesniejsze punkty maja
     wplaty konta, ktorego wartosci jeszcze nie licza, i wygladaja na strate,
     ktorej nie bylo. */
  const odKiedy={};
  for(const k of konta){
    const p=stany.filter(r=>r.a===k).map(r=>r.d).sort()[0];
    if(p)odKiedy[k]=p;
  }
  const liczone=(r,d)=>odKiedy[r.a]!=null&&odKiedy[r.a]<=d;
  const seria=kt=>{
    const moje=r=>!kt||r.a===kt;
    const wart=os.map(m=>{let sum=0;
      for(const k of (kt?[kt]:konta)){
        const ost=stany.filter(r=>r.a===k&&mies(r.d)<=m).sort(poDacie).at(-1);
        if(ost)sum+=ost.k}
      return Math.round(sum)});
    const wpl=os.map(m=>Math.round(TX.filter(r=>moje(r)&&mies(r.d)<=m&&liczone(r,m+"-31"))
      .reduce((s,r)=>s+przeplyw(r),0)));
    /* Zwrot liczymy TYLKO miedzy miesiacami, w ktorych naprawde jest wpis stanu.
       Miesiac bez wpisu nie jest "miesiacem na zero" - po prostu nie wiadomo, ile
       konto wtedy bylo warte, a wykres pokazujacy tam 0,0% klamalby.
       Przeplyw odejmujemy, inaczej wplata wygladalaby jak zysk. */
    const obs=new Set(stany.filter(moje).map(r=>mies(r.d)));
    const {zwr,twr}=lancuch(wart,wpl,obs);
    return {wart,wpl,zwr,twr};
  };
  const P=seria(null);

  /* Druga, gestsza os: punkt na KAZDY dzien, w ktorym wpisales stan. Os
     miesieczna gubi drugi wpis w tym samym miesiacu i rysuje plaska linie
     tam, gdzie nic nie wpisales - a to wlasnie te punkty sa jedynym, co
     o koncie naprawde wiadomo. */
  const trackDla=kt=>{
    const moje=r=>!kt||r.a===kt;
    const daty=[...new Set(stany.filter(moje).map(r=>r.d))].sort();
    const pkt=daty.map(d=>{
      let w=0;
      for(const k of (kt?[kt]:konta)){
        const o=stany.filter(r=>r.a===k&&r.d<=d).sort(poDacie).at(-1);
        if(o)w+=o.k}
      const ruchy=TX.filter(r=>moje(r)&&r.d<=d&&przeplyw(r)&&liczone(r,d));
      const kurs=kursNa(d),brak=ruchy.some(r=>kursNa(r.d)==null);
      return {d,wart:Math.round(w),wpl:Math.round(ruchy.reduce((s,r)=>s+przeplyw(r),0)),
              wartPln:kurs==null?null:Math.round(w*kurs),
              wplPln:brak?null:Math.round(ruchy.reduce((s,r)=>s+przeplyw(r)*kursNa(r.d),0))};
    });
    let i=1,ip=1,maPln=false;
    pkt.forEach((p,n)=>{
      const q=n?pkt[n-1]:null;
      if(q&&q.wart>0)i*=(p.wart-(p.wpl-q.wpl))/q.wart;
      p.idx=i;
      if(p.wartPln==null||p.wplPln==null)p.idxPln=null;
      else{
        if(q&&q.wartPln!=null&&q.wplPln!=null&&q.wartPln>0)
          ip*=(p.wartPln-(p.wplPln-q.wplPln))/q.wartPln;
        p.idxPln=ip;maPln=true}
    });
    /* Wplaty POMIEDZY punktami - zeby bylo widac, ze skok wartosci to przelew,
       a nie zysk. */
    for(let n=1;n<pkt.length;n++)
      pkt[n].ruch=pkt[n].wpl-pkt[n-1].wpl;
    return {pkt,twr:+((i-1)*100).toFixed(2),twrPln:maPln?+((ip-1)*100).toFixed(2):null};
  };
  const CALY=trackDla(null),track=CALY.pkt;
  const idx=1+CALY.twr/100,idxPln=1+(CALY.twrPln??0)/100;

  /* Co trzymam: z ostatniego rozbicia kazdego konta, jesli user je podal. */
  const trzymam={},perKonto={};
  for(const k of konta){
    const ost=stany.filter(r=>r.a===k&&r.px).sort(poDacie).at(-1);
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
  /* Deklaracja bije odczyt: jesli user powiedzial, ktore konto niesie ktora
     noge, dzielimy noge miedzy konta, ktore ja deklaruja, wedle ich wartosci. */
  if(konta.some(k=>ROLE_KONT[k])){
    for(const k of konta){
      const r=ROLE_KONT[k]||"wszystko",w=Math.max(0,konce[k].wart.at(-1)||0);
      for(const l of ["best17","gpm"])udzial[l][k]=(r==="wszystko"||r===l)?w:0;
    }
  }
  const accounts=konta.map(k=>{
    const sum=l=>konta.reduce((a,x)=>a+udzial[l][x],0);
    const tk=trackDla(k);
    const a={name:k,value:Math.round(konce[k].wart.at(-1)),
             pln:tk.twrPln,usd:tk.twr,
             alloc:{best17:sum("best17")?udzial.best17[k]/sum("best17"):0,
                    gpm:sum("gpm")?udzial.gpm[k]/sum("gpm"):0}};
    if(!sum("best17")&&!sum("gpm")){
      const cal=konta.reduce((x,y)=>x+konce[y].wart.at(-1),0)||1;
      a.alloc={best17:konce[k].wart.at(-1)/cal,gpm:konce[k].wart.at(-1)/cal}}
    return a});

  /* Wszystko zostaje w DOLARACH - w nich sa wpisy i w nich notowane sa ETF-y.
     Zlote to wylacznie warstwa wyswietlania (funkcja kw()), po kursie z daty. */
  const kapital=P.wart.at(-1);
  const wartPln=P.wart.map((v,i)=>{const k=kursNa(os[i]+"-28");return k==null?null:Math.round(v*k)});
  const wplPln=os.map(m=>{
    const ruchy=TX.filter(r=>mies(r.d)<=m&&przeplyw(r)&&liczone(r,m+"-31"));
    if(ruchy.some(r=>kursNa(r.d)==null))return null;
    return Math.round(ruchy.reduce((a,r)=>a+przeplyw(r)*kursNa(r.d),0))});
  const pln=lancuch(wartPln,wplPln,new Set(stany.map(r=>mies(r.d))));
  return {
    owner:"wpisy", capital:{best17:kapital/2,gpm:kapital/2,split10:.5},
    holdings:trzymam, perKonto, accounts,
    months:os,
    /* Wartosc w zlotych: kurs z konca danego miesiaca. Wplacone w zlotych:
       KAZDY przeplyw po swoim wlasnym kursie - tyle naprawde kosztowal. */
    value:wartPln, paid:wplPln,
    value_usd:P.wart, paid_usd:P.wpl,
    returns:{usd:P.zwr,pln:pln.zwr},
    legs:{best17:{value_usd:P.wart.at(-1)/2,paid_usd:P.wpl.at(-1)/2},
          gpm:{value_usd:P.wart.at(-1)/2,paid_usd:P.wpl.at(-1)/2}},
    fx:{pair:"USD/PLN",rate:kurs,series:os.map(m=>kursNa(m+"-28"))},
    /* TWR z osi wpisow, nie z miesiecznej - liczy KAZDY wpis, takze drugi
       w tym samym miesiacu. */
    twr:{usd:CALY.twr,pln:CALY.twrPln??pln.twr},
    track,
    /* Konta, ktorych pieniadze nie sa (albo nie byly) widziane przez panel -
       user ma o tym wiedziec, bo to jego wplaty. */
    spoznione:konta.filter(k=>odKiedy[k]&&TX.some(r=>r.a===k&&przeplyw(r)&&r.d<odKiedy[k]))
      .map(k=>({konto:k,od:odKiedy[k]})),
    bezStanu:konta.filter(k=>!odKiedy[k]&&TX.some(r=>r.a===k&&przeplyw(r))),
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
  rysujPasek();rysujRozbicie();renderTX();renderPulpit();renderActions();renderHist();renderAccounts();renderPomoc();renderAll();
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
  document.getElementById("txAcc").closest(".fld").hidden=typ==="kurs";
  /* Kurs to dane wspolne - wpisuje je admin. Reszta widzi liste, ale bez pol.
     `hidden` na <option> nie dziala wszedzie, wiec do tego jeszcze `disabled`. */
  document.getElementById("txKursWrap").hidden=typ==="kurs"||!mozeKursy();
  document.getElementById("txPlnWrap").hidden=typ==="kurs"||!mozeKursy();
  document.getElementById("txPlnLbl").textContent=pok?"Wartość konta w zł":"Kwota w zł";
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
    const stary=wczesniejszy(r,TX);
    return `<div class="row${stary?" zast":""}"><div class="ic" style="background:${CSS(c)}">${sym}</div>
      <div class="nm">${TYP[r.t]||r.t}<em>${r.d} · ${esc(r.a)}${r.px?" · rozbite na walory":""}${
        stary?" · <b>wcześniejszy tego dnia</b> — na wykresie widać ostatni":""}</em></div>
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
        ? "Brak kursów. Dopisz choć jeden — bez niego panel nie przelicza na złote i pokazuje same dolary."
        : "Brak kursów. Wpisuje je admin — do tego czasu panel nie przelicza na złote i pokazuje same dolary."}</div>`;
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
    :'<div><span>Brak wpisów</span><b>—</b></div>';
  rysujRoleKont(ks)}
function rysujRoleKont(ks){
  const box=document.getElementById("roleKont"),nota=document.getElementById("roleNota");
  if(!box)return;
  if(!ks.length){box.innerHTML="";nota.textContent="";return}
  box.innerHTML=ks.map(k=>{
    const r=ROLE_KONT[k]||"auto";
    return `<div class="row rolaRow"><div class="ic" style="background:${CSS("--s6")}">${esc(k).slice(0,2).toUpperCase()}</div>
      <div class="nm">${esc(k)}<em>${r==="auto"?"odczytane z pozycji":"zadeklarowane"}</em></div>
      <div class="vl"><select data-rola="${esc(k)}" aria-label="Co leży na koncie ${esc(k)}">
        <option value="auto"${r==="auto"?" selected":""}>Odczytaj z pozycji</option>
        ${ROLE_OK.map(x=>`<option value="${x}"${r===x?" selected":""}>${ROLE_LBL[x]}</option>`).join("")}
      </select></div></div>`}).join("");
  nota.textContent="Powiedz, co leży na którym koncie. Panel sam tego nie wie: CMOD i CSPX "
    +"należą do obu nóg naraz, więc odczytując ze stanu rozdziela je po połowie i każde konto "
    +"wychodzi mu wymieszane. Przy jednym koncie wybierz Wszystko.";}
document.getElementById("roleKont")?.addEventListener("change",e=>{
  const s=e.target.closest("select[data-rola]");if(!s)return;
  ustawRoleKonta(s.dataset.rola,s.value)});

document.getElementById("txType").addEventListener("change",rysujRozbicie);

/* Kurs i zlotowki to ta sama informacja podana z dwoch stron: przy wplacie
   czesciej wiesz, ile zaplaciles, niz po jakim kursie. Do bazy i tak idzie
   sam kurs - zlotowki nie sa nigdzie zapisywane. */
let KURS_Z="kurs";
function przeliczKwoty(zrodlo){
  if(document.getElementById("txKursWrap").hidden)return;
  const u=document.getElementById("txAmt"),k=document.getElementById("txKurs"),p=document.getElementById("txPln");
  const usd=parseFloat(u.value)||0,kurs=parseFloat(k.value)||0,pln=parseFloat(p.value)||0;
  if(zrodlo!=="amt")KURS_Z=zrodlo;
  if(zrodlo==="pln"||(zrodlo==="amt"&&KURS_Z==="pln")){
    if(usd>0&&pln>0)k.value=+(pln/usd).toFixed(4);
    return}
  if(usd>0&&kurs>0)p.value=+(usd*kurs).toFixed(2);
}
for(const[id,zr]of[["txAmt","amt"],["txKurs","kurs"],["txPln","pln"]])
  document.getElementById(id).addEventListener("input",()=>przeliczKwoty(zr));
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
  }
  /* Kurs podany przy wpisie zapisuje sie jako OSOBNY wpis z ta sama data -
     dzieki temu dziala tak samo, jak gdyby go wpisac recznie. */
  let kr=parseFloat(document.getElementById("txKurs").value)||0;
  const wZl=parseFloat(document.getElementById("txPln").value)||0;
  if(!(kr>0)&&wZl>0&&rec.k>0)kr=+(wZl/rec.k).toFixed(4);
  if(kr>0&&mozeKursy())dodajKurs(rec.d,kr);
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

const D_ISO=/^\d{4}-\d{2}-\d{2}$/;
const D_PL=/^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})$/;
function naDate(s){
  const t=String(s??"").trim();
  if(D_ISO.test(t))return t;
  const m=t.match(D_PL);
  return m?`${m[3]}-${m[2].padStart(2,"0")}-${m[1].padStart(2,"0")}`:null;
}
/* "$42 150,96" -> 42150.96. Przecinek dziesietny wygrywa z kropka tysiecy;
   gdy przecinka nie ma, kropka jest dziesietna. */
function naLiczbe(s){
  let t=String(s??"").replace(/[^\d.,-]/g,"");
  if(!t||!/\d/.test(t))return null;
  if(t.includes(","))t=t.replace(/\./g,"").replace(",",".");
  const v=parseFloat(t);
  return Number.isFinite(v)?v:null;
}
const komorki=w=>w.includes("\t")?w.split("\t"):w.split(/\s{2,}/);
const odm=(n,a,b,c)=>{const d=n%10,s=n%100;return n+" "+(n===1?a:d>=2&&d<=4&&(s<10||s>=20)?b:c)};

const IMP_STALE=[["pomin","— pomiń —"],["data","Data"],["razem","Razem (kontrola)"],["kurs","Kurs USD/PLN"]];
let IMP_MAP=[];
try{IMP_MAP=JSON.parse(localStorage.getItem("impmap")||"[]")}catch(e){IMP_MAP=[]}
const zapiszMape=()=>{try{localStorage.setItem("impmap",JSON.stringify(IMP_MAP))}catch(e){}};

const impKonta=()=>[...new Set([
  ...TX.filter(r=>r.a).map(r=>r.a),
  ...IMP_MAP.filter(x=>x.startsWith("konto:")).map(x=>x.slice(6)),
  "LYNX","XTB"])];

const impSzerokosc=tekst=>{
  const l=String(tekst??"").split(/\r?\n/).map(w=>w.trim()).filter(Boolean);
  return l.length?Math.max(...l.map(w=>komorki(w).length)):0;
};

function impDomyslna(szer){
  const m=new Array(szer).fill("pomin");
  if(szer>0)m[0]="data";
  if(szer>=5){m[1]="konto:LYNX";m[2]="konto:XTB";m[3]="razem";m[4]="kurs"}
  else if(szer===4){m[1]="konto:LYNX";m[2]="konto:XTB";m[3]="kurs"}
  else if(szer===3){m[1]="konto:LYNX";m[2]="kurs"}
  else if(szer===2)m[1]="konto:LYNX";
  return m;
}

function impBledy(mapa){
  const b=[],ile=r=>mapa.filter(x=>x===r).length;
  if(!ile("data"))b.push("wskaż kolumnę z datą");
  if(ile("data")>1)b.push("data może być tylko w jednej kolumnie");
  if(ile("razem")>1)b.push("„Razem” może być tylko w jednej kolumnie");
  if(ile("kurs")>1)b.push("kurs może być tylko w jednej kolumnie");
  const k=mapa.filter(x=>x.startsWith("konto:"));
  if(!k.length)b.push("wskaż przynajmniej jedną kolumnę z kontem");
  const dub=[...new Set(k.filter((x,i)=>k.indexOf(x)!==i))];
  if(dub.length)b.push(`to samo konto w dwóch kolumnach: ${dub.map(x=>x.slice(6)).join(", ")}`);
  return b;
}

function parsujImport(tekst,mapa){
  const linie=String(tekst??"").split(/\r?\n/).map(w=>w.trim()).filter(Boolean);
  const problemy=[],wiersze=[],iData=mapa.indexOf("data");
  if(iData<0)return {wiersze,problemy};
  for(const linia of linie){
    const r=komorki(linia);
    const d=naDate(r[iData]);
    if(!d){problemy.push(`pomijam wiersz bez daty: ${linia.slice(0,50)}`);continue}
    const kwoty={},w={d,kwoty,kurs:null,razem:null};
    mapa.forEach((rola,i)=>{
      if(rola==="pomin"||rola==="data")return;
      const v=naLiczbe(r[i]);
      if(v==null)return;
      if(rola==="kurs")w.kurs=v;
      else if(rola==="razem")w.razem=v;
      else kwoty[rola.slice(6)]=v;
    });
    if(!Object.keys(kwoty).length){problemy.push(`${d}: żadnej kwoty, pomijam`);continue}
    wiersze.push(w);
  }
  return {wiersze,problemy};
}

const stanTeraz=(d,a)=>{const r=TX.find(x=>x.t==="stan"&&x.d===d&&x.a===a);return r?r.k:null};

async function ustawStan(d,a,k){
  const i=TX.findIndex(x=>x.t==="stan"&&x.d===d&&x.a===a);
  if(i>=0){
    if(Math.abs(TX[i].k-k)<0.005)return false;
    TX[i].k=k;TX[i].ts=Date.now();
    if(FB&&USER)await FB.zapisz(USER.uid,"transactions",TX[i].id,TX[i]);
    return true;
  }
  const r={id:`stan_${d}_${a.replace(/[^\w]+/g,"-")}`,d,a,t:"stan",k,px:null,ts:Date.now()};
  TX.push(r);
  if(FB&&USER)await FB.zapisz(USER.uid,"transactions",r.id,r);
  return true;
}
async function ustawKurs(d,k){
  const ist=KURSY.find(x=>x.d===d);
  if(ist&&Math.abs(ist.k-k)<1e-9)return false;
  KURSY=KURSY.filter(x=>x.d!==d).concat({id:d,d,k});
  zapiszKursyLokalnie();
  if(FB)await FB.zapiszKurs(d,{d,k});
  return true;
}

let IMPORT=null,IMP_SZER=-1;
function rysujMape(){
  const konta=impKonta();
  const opcje=r=>[...IMP_STALE,...konta.map(a=>[`konto:${a}`,a]),["nowe","+ inne konto…"]]
    .map(([v,t])=>`<option value="${esc(v)}"${v===r?" selected":""}>${esc(t)}</option>`).join("");
  document.getElementById("impMapa").innerHTML=IMP_MAP.map((r,i)=>
    `<label><span>kolumna ${i+1}</span><select data-kol="${i}">${opcje(r)}</select></label>`).join("");
}
function rysujImport(){
  const tekst=document.getElementById("impTekst").value;
  const szer=impSzerokosc(tekst)||IMP_MAP.length||5;
  if(szer!==IMP_MAP.length)IMP_MAP=impDomyslna(szer);
  if(szer!==IMP_SZER){IMP_SZER=szer;rysujMape()}
  const pod=document.getElementById("impPodglad"),btn=document.getElementById("impZapisz");
  const zle=impBledy(IMP_MAP);
  if(zle.length){
    IMPORT=null;
    pod.innerHTML=`<p class="note" style="color:var(--neg)">${zle.map(esc).join("<br>")}</p>`;
    btn.disabled=true;return}
  const p=parsujImport(tekst,IMP_MAP);
  IMPORT=p;
  const konta=IMP_MAP.filter(x=>x.startsWith("konto:")).map(x=>x.slice(6));
  let h=p.problemy.length?`<p class="note" style="color:var(--warn)">${p.problemy.map(esc).join("<br>")}</p>`:"";
  if(!p.wiersze.length){
    pod.innerHTML=h||'<p class="note">Wklej wiersze powyżej, a pokażę, co z nich wyjdzie.</p>';
    btn.disabled=true;return}
  let nowe=0,zmiany=0,bezZmian=0,kursow=0,rozjazd=0;
  const wiersze=p.wiersze.map(w=>{
    const suma=Object.values(w.kwoty).reduce((a,b)=>a+b,0);
    const zgoda=w.razem==null||Math.abs(suma-w.razem)<0.5;
    if(!zgoda)rozjazd++;
    const kom=konta.map(a=>{
      const v=w.kwoty[a];
      if(v==null)return '<td class="num">—</td>';
      const b=stanTeraz(w.d,a);
      let st;
      if(b==null){st="nowy";nowe++}
      else if(Math.abs(b-v)<0.005){st="bez zmian";bezZmian++}
      else {st=`było ${zl(b)}`;zmiany++}
      return `<td class="num">${zl(v)}<em>${esc(st)}</em></td>`}).join("");
    let kk;
    if(!(w.kurs>0))kk='<td class="num">—</td>';
    else if(!mozeKursy())kk='<td class="num">'+w.kurs.toFixed(4).replace(".",",")+'<em>tylko admin</em></td>';
    else{
      const ist=KURSY.find(x=>x.d===w.d);
      const nowy=!ist||Math.abs(ist.k-w.kurs)>1e-9;
      if(nowy)kursow++;
      kk=`<td class="num">${w.kurs.toFixed(4).replace(".",",")}<em>${nowy?(ist?"zmiana":"nowy"):"bez zmian"}</em></td>`}
    return `<tr${zgoda?"":' style="background:color-mix(in srgb,var(--warn) 12%,transparent)"'}>
      <td>${w.d}</td>${kom}${kk}
      <td class="num">${zgoda?"":`<span style="color:var(--warn)">Razem ${zl(w.razem)} ≠ ${zl(suma)}</span>`}</td></tr>`}).join("");
  h+=`<div class="card tw imp"><table>
    <thead><tr><th>Data</th>${konta.map(a=>`<th class="num">${esc(a)}</th>`).join("")}
      <th class="num">USD/PLN</th><th class="num">Kontrola</th></tr></thead>
    <tbody>${wiersze}</tbody></table></div>`;
  const co=[nowe?odm(nowe,"nowy stan","nowe stany","nowych stanów"):"",
            zmiany?`${zmiany} do poprawienia`:"",
            bezZmian?`${bezZmian} bez zmian`:"",
            kursow?odm(kursow,"kurs","kursy","kursów"):""].filter(Boolean);
  h+=`<p class="note">${co.join(" · ")||"nic do zapisania"}`
    +(rozjazd?` <span style="color:var(--warn)">· ${odm(rozjazd,"wiersz nie zgadza się","wiersze nie zgadzają się","wierszy nie zgadza się")} z kolumną „Razem” — zapiszę je mimo to, ale sprawdź.</span>`:"")
    +(!mozeKursy()&&p.wiersze.some(w=>w.kurs>0)?' <span style="color:var(--warn)">· kursy pominę, wpisuje je admin.</span>':"")+"</p>";
  pod.innerHTML=h;
  btn.disabled=!(nowe+zmiany+kursow);
  btn.textContent=`Zapisz ${odm(nowe+zmiany,"stan","stany","stanów")}`
    +(kursow?` i ${odm(kursow,"kurs","kursy","kursów")}`:"");
}

async function wykonajImport(){
  const p=IMPORT;if(!p?.wiersze.length)return;
  if(!ZAL()){alert("Zaloguj się, żeby zapisać wpisy.");return}
  const btn=document.getElementById("impZapisz");
  btn.disabled=true;btn.textContent="Zapisuję…";
  let stany=0,kursy=0;const bledy=[];
  for(const w of p.wiersze){
    for(const[a,k]of Object.entries(w.kwoty)){
      try{if(await ustawStan(w.d,a,k))stany++}
      catch(e){bledy.push(`${w.d} ${a}: ${e.message}`)}}
    if(w.kurs>0&&mozeKursy()){
      try{if(await ustawKurs(w.d,w.kurs))kursy++}
      catch(e){bledy.push(`${w.d} kurs: ${e.message}`)}}
  }
  poWpisach();
  const pod=document.getElementById("impPodglad");
  pod.innerHTML=`<p class="note" style="color:var(${bledy.length?"--warn":"--pos"})">
    Zapisane: ${odm(stany,"stan","stany","stanów")}, ${odm(kursy,"kurs","kursy","kursów")}.${bledy.length?"<br>Nie zapisano "+bledy.length+":<br>"+bledy.map(esc).join("<br>"):""}</p>`;
  document.getElementById("impTekst").value="";
  btn.textContent="Zapisz";btn.disabled=true;
}

document.getElementById("btnImport").addEventListener("click",()=>{
  const box=document.getElementById("importBox");
  if(!box.hidden){box.hidden=true;return}
  box.innerHTML=`<div class="card">
    <div class="lbl" style="margin-bottom:10px">Import stanu kont</div>
    <p class="note" style="margin:0 0 10px">Wklej same wiersze z arkusza, bez nagłówków — potem niżej
      powiedz, co jest w której kolumnie. Czego nie potrzebuję, zostaw na „pomiń”.
      Dzień, który już jest, zostanie poprawiony, nie zdublowany.</p>
    <textarea id="impTekst" rows="7" spellcheck="false" placeholder="2026-07-29&#9;$42 150,96&#9;$43 300,00&#9;$85 450,96&#9;3,79588"></textarea>
    <div class="lbl" style="margin:14px 0 8px">Co jest w której kolumnie</div>
    <div class="impmap" id="impMapa"></div>
    <div id="impPodglad" style="margin-top:14px"></div>
    <div class="akcje" style="margin-top:12px">
      <button type="button" class="btn" id="impZapisz" disabled>Zapisz</button>
      <button type="button" class="btn cicho" id="impAnuluj">Zamknij</button></div>
  </div>`;
  box.hidden=false;
  document.getElementById("impTekst").addEventListener("input",rysujImport);
  document.getElementById("impZapisz").addEventListener("click",wykonajImport);
  document.getElementById("impAnuluj").addEventListener("click",()=>{box.hidden=true});
  document.getElementById("impMapa").addEventListener("change",e=>{
    const s=e.target.closest("select");if(!s)return;
    const i=+s.dataset.kol;
    if(s.value==="nowe"){
      const n=(prompt("Nazwa konta")||"").trim();
      if(!n){s.value=IMP_MAP[i];return}
      IMP_MAP[i]="konto:"+n;
      zapiszMape();rysujMape();rysujImport();return}
    IMP_MAP[i]=s.value;
    zapiszMape();rysujImport();
  });
  IMP_SZER=-1;
  rysujImport();
});


/* ============ nawigacja ============ */
const VIEWS=["pulpit","sygnal","wyniki","transakcje","ceny","dlaczego","pomoc"];
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
rysujPasek();fillAccSelect();rysujRozbicie();renderTX();renderPulpit();renderMatrix();renderActions();renderHist();renderSklad();renderAccounts();renderWyniki();renderDiag();renderCeny();renderPomoc();

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
