from __future__ import annotations

from datetime import date, timedelta
from html import escape

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .config import settings
from .storage import GatewayStorage
from .connections import ConnectionManager
from .web_auth import (
    COOKIE_NAME,
    create_session_cookie,
    require_browser_session,
    validate_session_cookie,
)


router = APIRouter()


LOGIN_HTML = r"""
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Restaurant OS — вход</title>
<style>
:root{--bg:#f3efe9;--card:#fff;--text:#211915;--muted:#766a63;--red:#ad3024;--line:#ded4cc}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);font-family:Segoe UI,Arial,sans-serif;color:var(--text);
display:grid;place-items:center;min-height:100vh;padding:20px}
.card{width:min(460px,100%);background:#fff;border:1px solid var(--line);border-radius:24px;
padding:34px;box-shadow:0 20px 60px rgba(45,30,20,.09)}
.kicker{color:var(--red);font-weight:800;letter-spacing:.12em;font-size:13px}
h1{font-size:38px;margin:8px 0 8px}
p{color:var(--muted);font-size:17px;line-height:1.5}
label{display:block;margin:24px 0 8px;font-weight:700}
input{width:100%;padding:14px 16px;border:1px solid var(--line);border-radius:12px;font-size:17px}
button{width:100%;margin-top:16px;border:0;border-radius:12px;padding:14px;background:var(--red);
color:#fff;font-weight:800;font-size:16px;cursor:pointer}
.error{margin-top:16px;color:var(--red);font-weight:700}
</style>
</head>
<body>
<div class="card">
<div class="kicker">RESTAURANT OS CLOUD</div>
<h1>Вход владельца</h1>
<p>Введите административный токен Gateway.</p>
<form method="post" action="/login">
<label for="token">Токен</label>
<input id="token" name="token" type="password" autocomplete="current-password" required autofocus>
<button type="submit">Войти</button>
</form>
__LOGIN_ERROR__
</div>
</body>
</html>
"""


DASHBOARD_HTML = r"""
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Restaurant OS BI</title>
<style>
:root{
 --bg:#f3efe9;--card:#fff;--text:#211915;--muted:#786c65;--line:#ded4cc;
 --red:#ad3024;--red2:#cf6b3b;--green:#407b5d;--amber:#cf8527;--blue:#347c98;
 --dark:#2d201a;--soft:#f8f5f2
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:Segoe UI,Arial,sans-serif}
header{
 background:var(--dark);color:white;padding:16px 24px;display:flex;align-items:center;
 justify-content:space-between;gap:18px;position:sticky;top:0;z-index:20
}
.brand{display:flex;align-items:center;gap:13px}
.logo{width:44px;height:44px;border-radius:14px;background:var(--red);display:grid;place-items:center;
 font-size:19px;font-weight:900}
.brand strong{font-size:20px;display:block}.brand small{color:#cbbdb5}
header a{color:#fff;text-decoration:none;border:1px solid #6b5b52;padding:9px 13px;border-radius:10px}
main{max-width:1540px;margin:auto;padding:24px}
.top{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-bottom:18px}
.kicker{color:var(--red);font-weight:850;letter-spacing:.12em;font-size:13px}
h1{font-size:44px;margin:4px 0 4px}.sub{font-size:18px;color:var(--muted)}
.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
select,input,button{
 border:1px solid var(--line);border-radius:11px;padding:10px 12px;background:#fff;
 font-weight:700;font-size:14px
}
button{cursor:pointer}
button.primary{background:var(--red);color:#fff;border-color:var(--red)}
.quick{background:#fff;color:var(--text)}
.quick.active{background:var(--dark);color:#fff;border-color:var(--dark)}
.statusbar{display:flex;gap:10px;align-items:center;margin-bottom:16px;color:var(--muted)}
.dot{width:10px;height:10px;border-radius:50%;background:var(--amber)}
.dot.online{background:var(--green)}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px}
.card{
 background:var(--card);border:1px solid var(--line);border-radius:20px;padding:20px;
 box-shadow:0 8px 28px rgba(45,30,20,.04)
}
.metric-card{grid-column:span 3}
.metric-card h2{font-size:14px;color:var(--muted);font-weight:500;margin:0 0 12px}
.metric{font-size:34px;font-weight:800;line-height:1.1}
.note{color:var(--muted);margin-top:8px;font-size:14px}
.delta{margin-top:10px;font-size:14px;font-weight:800}
.delta.up{color:var(--green)}.delta.down{color:var(--red)}.delta.flat{color:var(--muted)}
.span-8{grid-column:span 8}.span-4{grid-column:span 4}.span-6{grid-column:span 6}.full{grid-column:1/-1}
.section-title{font-size:27px;font-weight:800;margin:0 0 16px}
.chart{
 height:310px;display:flex;align-items:end;gap:7px;border-bottom:1px solid var(--line);
 padding:20px 6px 0;overflow-x:auto
}
.bar-wrap{flex:1;min-width:24px;height:100%;display:flex;flex-direction:column;justify-content:end;
 align-items:center;gap:6px}
.bar{width:100%;max-width:48px;background:linear-gradient(to top,var(--red),var(--red2));
 border-radius:8px 8px 2px 2px;min-height:2px;transition:.25s}
.bar.secondary{background:linear-gradient(to top,var(--amber),#efbc6a)}
.bar-label{font-size:11px;color:var(--muted);white-space:nowrap}
.line-chart{position:relative;height:310px;padding:20px 8px 30px}
svg{width:100%;height:100%;overflow:visible}
.axis-label{font-size:11px;fill:var(--muted)}
.line{fill:none;stroke:var(--red);stroke-width:3}
.line2{fill:none;stroke:var(--amber);stroke-width:3}
.point{fill:var(--red)}.point2{fill:var(--amber)}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;color:var(--muted);font-size:13px}
.legend span::before{content:"";display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;background:var(--red)}
.legend span.avg::before{background:var(--amber)}
.insights{display:grid;gap:12px}
.insight{
 padding:15px;border:1px solid var(--line);border-radius:14px;background:var(--soft)
}
.insight strong{display:block;font-size:18px;margin-bottom:5px}
.insight small{color:var(--muted)}
.history{width:100%;border-collapse:collapse}
.history th,.history td{text-align:left;padding:13px 8px;border-bottom:1px solid var(--line)}
.history th{color:var(--muted);font-size:13px}
.empty{padding:40px;text-align:center;color:var(--muted)}
.footer-note{margin-top:16px;color:var(--muted);font-size:13px}
@media(max-width:1100px){
 .metric-card{grid-column:span 6}.span-8,.span-4,.span-6{grid-column:span 12}
}
@media(max-width:680px){
 header{padding:13px}.brand small{display:none}main{padding:14px}.top{display:block}
 h1{font-size:33px}.controls{margin-top:15px;justify-content:flex-start}.metric-card{grid-column:span 12}
 .chart,.line-chart{height:245px}.metric{font-size:30px}.card{padding:16px}
}
</style>
</head>
<body>
<header>
 <div class="brand"><div class="logo">ГЗ</div><div><strong>Restaurant OS BI</strong>
 <small>Облачная управленческая аналитика</small></div></div>
 <a href="/logout">Выйти</a>
</header>

<main>
 <div class="top">
  <div>
   <div class="kicker">ЦИФРОВОЙ УПРАВЛЯЮЩИЙ</div>
   <h1>Бизнес-аналитика</h1>
   <div class="sub">Выручка, чеки, средний чек и динамика продаж.</div>
  </div>
  <div class="controls">
   <select id="restaurant"></select>
   <button class="quick" data-period="today">Сегодня</button>
   <button class="quick" data-period="yesterday">Вчера</button>
   <button class="quick" data-period="7">7 дней</button>
   <button class="quick active" data-period="30">30 дней</button>
   <input type="date" id="date-from">
   <input type="date" id="date-to">
   <button class="primary" onclick="loadAll()">Показать</button>
  </div>
 </div>

 <div class="statusbar">
  <span class="dot" id="status-dot"></span>
  <span id="status-text">Загрузка статуса...</span>
 </div>

 <section class="grid">
  <article class="card metric-card">
   <h2>Выручка за период</h2><div class="metric" id="revenue">—</div>
   <div class="delta flat" id="revenue-delta">—</div>
  </article>
  <article class="card metric-card">
   <h2>Чеков</h2><div class="metric" id="checks">—</div>
   <div class="delta flat" id="checks-delta">—</div>
  </article>
  <article class="card metric-card">
   <h2>Средний чек</h2><div class="metric" id="avg">—</div>
   <div class="delta flat" id="avg-delta">—</div>
  </article>
  <article class="card metric-card">
   <h2>Последняя синхронизация</h2><div class="metric" id="sync-age">—</div>
   <div class="note" id="sync-time">—</div>
  </article>

  <article class="card span-8">
   <div class="kicker">ДИНАМИКА</div>
   <h3 class="section-title">Выручка и средний чек</h3>
   <div class="line-chart" id="trend-chart"></div>
   <div class="legend"><span>Выручка</span><span class="avg">Средний чек</span></div>
  </article>

  <article class="card span-4">
   <div class="kicker">ГЛАВНЫЕ ТОЧКИ</div>
   <h3 class="section-title">Что важно за период</h3>
   <div class="insights" id="insights"></div>
  </article>

  <article class="card span-6">
   <div class="kicker">НАГРУЗКА</div>
   <h3 class="section-title">Продажи по часам</h3>
   <div class="chart" id="hourly-chart"></div>
  </article>

  <article class="card span-6">
   <div class="kicker">ДНИ</div>
   <h3 class="section-title">Выручка по дням</h3>
   <div class="chart" id="daily-chart"></div>
  </article>

  <article class="card span-6">
   <div class="kicker">ЛИДЕРЫ</div>
   <h3 class="section-title">ТОП блюд</h3>
   <div class="insights" id="top-menu"></div>
  </article>

  <article class="card span-6">
   <div class="kicker">ABC-АНАЛИЗ</div>
   <h3 class="section-title">Структура меню</h3>
   <div class="insights" id="abc-summary"></div>
  </article>

  <article class="card full">
   <div class="kicker">ДЕТАЛИ</div>
   <h3 class="section-title">История продаж</h3>
   <div id="history-wrap"></div>
   <div class="footer-note">Данные берутся из облачных снимков агента Restaurant OS.</div>
  </article>
 </section>
</main>

<script>
const money = new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:0});
const number = new Intl.NumberFormat('ru-RU');
let currentPeriod = '30';

async function api(url){
 const r=await fetch(url,{cache:'no-store'});
 if(r.status===401){location.href='/login';throw new Error('auth')}
 if(!r.ok){const t=await r.text();throw new Error(t)}
 return r.json()
}
function getAgent(){return document.getElementById('restaurant').value}
function isoDate(d){return d.toISOString().slice(0,10)}
function parseDate(s){return new Date(s+'T00:00:00')}
function diffDays(a,b){return Math.round((b-a)/86400000)+1}
function sum(items,key){return items.reduce((acc,x)=>acc+Number(x[key]||0),0)}
function pct(current,previous){
 if(previous===0)return current===0?0:null;
 return (current-previous)/previous*100;
}
function setDelta(id,value){
 const el=document.getElementById(id);
 if(value===null){el.textContent='нет базы сравнения';el.className='delta flat';return}
 const sign=value>0?'+':'';
 el.textContent=`${sign}${value.toFixed(1)}% к прошлому периоду`;
 el.className='delta '+(value>0?'up':value<0?'down':'flat');
}
function setQuick(period){
 currentPeriod=period;
 document.querySelectorAll('.quick').forEach(b=>b.classList.toggle('active',b.dataset.period===period));
 const today=new Date(),from=new Date(),to=new Date();
 if(period==='today'){
  document.getElementById('date-from').value=isoDate(today);
  document.getElementById('date-to').value=isoDate(today);
 }else if(period==='yesterday'){
  from.setDate(today.getDate()-1);to.setDate(today.getDate()-1);
  document.getElementById('date-from').value=isoDate(from);
  document.getElementById('date-to').value=isoDate(to);
 }else{
  from.setDate(today.getDate()-Number(period)+1);
  document.getElementById('date-from').value=isoDate(from);
  document.getElementById('date-to').value=isoDate(today);
 }
}
function renderBars(el,items,labelKey,valueKey,labelFormatter,secondary=false){
 el.innerHTML='';
 if(!items.length){el.innerHTML='<div class="empty">Данных пока нет</div>';return}
 const max=Math.max(...items.map(x=>Number(x[valueKey]||0)),1);
 for(const item of items){
  const wrap=document.createElement('div');wrap.className='bar-wrap';
  const bar=document.createElement('div');bar.className='bar'+(secondary?' secondary':'');
  bar.style.height=Math.max(2,Number(item[valueKey]||0)/max*92)+'%';
  bar.title=money.format(Number(item[valueKey]||0));
  const label=document.createElement('div');label.className='bar-label';
  label.textContent=labelFormatter(item[labelKey]);
  wrap.append(bar,label);el.append(wrap);
 }
}
function renderTrend(el,items){
 if(!items.length){el.innerHTML='<div class="empty">Данных пока нет</div>';return}
 const w=900,h=250,p=28;
 const revMax=Math.max(...items.map(x=>Number(x.revenue||0)),1);
 const avgMax=Math.max(...items.map(x=>Number(x.average_check||0)),1);
 const step=items.length>1?(w-2*p)/(items.length-1):0;
 const pointsRev=items.map((x,i)=>[p+i*step,h-p-Number(x.revenue||0)/revMax*(h-2*p)]);
 const pointsAvg=items.map((x,i)=>[p+i*step,h-p-Number(x.average_check||0)/avgMax*(h-2*p)]);
 const path=pts=>pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
 const labels=items.map((x,i)=>{
  if(items.length>14 && i%Math.ceil(items.length/7)!==0 && i!==items.length-1)return '';
  return `<text class="axis-label" x="${p+i*step}" y="${h-5}" text-anchor="middle">${x.business_date.slice(5)}</text>`;
 }).join('');
 el.innerHTML=`<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
  <path class="line" d="${path(pointsRev)}"></path>
  <path class="line2" d="${path(pointsAvg)}"></path>
  ${pointsRev.map(p=>`<circle class="point" cx="${p[0]}" cy="${p[1]}" r="3"></circle>`).join('')}
  ${pointsAvg.map(p=>`<circle class="point2" cx="${p[0]}" cy="${p[1]}" r="3"></circle>`).join('')}
  ${labels}
 </svg>`;
}
function buildInsights(history){
 const container=document.getElementById('insights');
 if(!history.length){container.innerHTML='<div class="empty">Данных пока нет</div>';return}
 const best=history.reduce((a,b)=>Number(b.revenue||0)>Number(a.revenue||0)?b:a);
 const worst=history.reduce((a,b)=>Number(b.revenue||0)<Number(a.revenue||0)?b:a);
 const total=sum(history,'revenue'),checks=sum(history,'checks_count');
 const peakAvg=history.reduce((a,b)=>Number(b.average_check||0)>Number(a.average_check||0)?b:a);
 container.innerHTML=`
  <div class="insight"><small>Лучший день</small><strong>${best.business_date}</strong>${money.format(best.revenue||0)}</div>
  <div class="insight"><small>Слабый день</small><strong>${worst.business_date}</strong>${money.format(worst.revenue||0)}</div>
  <div class="insight"><small>Максимальный средний чек</small><strong>${peakAvg.business_date}</strong>${money.format(peakAvg.average_check||0)}</div>
  <div class="insight"><small>Итого за период</small><strong>${number.format(checks)} чеков</strong>${money.format(total)}</div>`;
}
async function loadAgents(){
 const data=await api('/api/web/agents');
 const select=document.getElementById('restaurant');
 const previous=select.value;select.innerHTML='';
 for(const a of data){
  const o=document.createElement('option');o.value=a.agent_id;o.textContent=a.name||a.agent_id;select.append(o)
 }
 if(previous && [...select.options].some(o=>o.value===previous))select.value=previous;
}
async function loadAll(){
 const agent=getAgent();if(!agent)return;
 const dateFrom=document.getElementById('date-from').value;
 const dateTo=document.getElementById('date-to').value;
 const from=parseDate(dateFrom),to=parseDate(dateTo),days=diffDays(from,to);
 const prevTo=new Date(from);prevTo.setDate(prevTo.getDate()-1);
 const prevFrom=new Date(prevTo);prevFrom.setDate(prevTo.getDate()-days+1);

 const [history,previous,agentInfo,latest,menu]=await Promise.all([
  api(`/api/web/${agent}/sales/history?date_from=${dateFrom}&date_to=${dateTo}`),
  api(`/api/web/${agent}/sales/history?date_from=${isoDate(prevFrom)}&date_to=${isoDate(prevTo)}`),
  api(`/api/web/${agent}/status`),
  api(`/api/web/${agent}/sales/latest`).catch(()=>null),
  api(`/api/web/${agent}/menu/history?date_from=${dateFrom}&date_to=${dateTo}`).catch(()=>[])
 ]);

 const dot=document.getElementById('status-dot');
 dot.className='dot '+(agentInfo.online?'online':'');
 document.getElementById('status-text').textContent=
   (agentInfo.online?'Агент подключён':'Агент не в сети')+
   (agentInfo.last_seen_at?` · последний сигнал ${agentInfo.last_seen_at}`:'');

 const revenue=sum(history,'revenue');
 const checks=sum(history,'checks_count');
 const avg=checks?revenue/checks:0;
 const prevRevenue=sum(previous,'revenue');
 const prevChecks=sum(previous,'checks_count');
 const prevAvg=prevChecks?prevRevenue/prevChecks:0;

 document.getElementById('revenue').textContent=money.format(revenue);
 document.getElementById('checks').textContent=number.format(checks);
 document.getElementById('avg').textContent=money.format(avg);
 setDelta('revenue-delta',pct(revenue,prevRevenue));
 setDelta('checks-delta',pct(checks,prevChecks));
 setDelta('avg-delta',pct(avg,prevAvg));

 if(latest){
  const sync=new Date(latest.captured_at);
  const mins=Math.max(0,Math.round((Date.now()-sync.getTime())/60000));
  document.getElementById('sync-age').textContent=mins<1?'сейчас':mins+' мин';
  document.getElementById('sync-time').textContent=latest.captured_at||'';
  const cols=latest.hourly?.columns||[],rows=latest.hourly?.rows||[];
  const hourly=rows.map(r=>Object.fromEntries(cols.map((c,i)=>[c,r[i]])));
  renderBars(document.getElementById('hourly-chart'),hourly,'sale_hour','revenue',v=>String(v).padStart(2,'0'));
 }else{
  document.getElementById('sync-age').textContent='—';
  document.getElementById('sync-time').textContent='данные ещё не получены';
  document.getElementById('hourly-chart').innerHTML='<div class="empty">Первый снимок ещё не получен</div>';
 }

 renderBars(document.getElementById('daily-chart'),history,'business_date','revenue',v=>v.slice(5),true);
 renderTrend(document.getElementById('trend-chart'),history);
 buildInsights(history);

 const top=document.getElementById('top-menu');
 if(!menu.length){
  top.innerHTML='<div class="empty">Данные по меню ещё не получены</div>';
 }else{
  top.innerHTML=menu.slice(0,10).map((x,i)=>`
   <div class="insight" style="display:grid;grid-template-columns:36px 1fr auto;gap:10px;align-items:center">
    <strong style="margin:0">${i+1}</strong>
    <div><strong style="margin:0">${x.item_name}</strong>
    <small>${number.format(x.quantity||0)} шт. · ${Number(x.revenue_share||0).toFixed(1)}%</small></div>
    <strong style="margin:0">${money.format(x.revenue||0)}</strong>
   </div>`).join('');
 }

 const classes={A:{count:0,revenue:0},B:{count:0,revenue:0},C:{count:0,revenue:0}};
 menu.forEach(x=>{
  const cls=classes[x.abc_class]||classes.C;
  cls.count++;cls.revenue+=Number(x.revenue||0);
 });
 document.getElementById('abc-summary').innerHTML=['A','B','C'].map(letter=>`
  <div class="insight"><small>Класс ${letter}</small>
  <strong>${classes[letter].count} позиций</strong>
  ${money.format(classes[letter].revenue)}</div>`).join('');

 const wrap=document.getElementById('history-wrap');
 if(!history.length){wrap.innerHTML='<div class="empty">История пока не накоплена</div>';return}
 wrap.innerHTML=`<table class="history"><thead><tr><th>Дата</th><th>Выручка</th>
  <th>Чеков</th><th>Средний чек</th><th>Обновлено</th></tr></thead><tbody>${
  history.slice().reverse().map(x=>`<tr><td>${x.business_date}</td>
  <td><strong>${money.format(x.revenue||0)}</strong></td>
  <td>${number.format(x.checks_count||0)}</td>
  <td>${money.format(x.average_check||0)}</td>
  <td>${x.captured_at||''}</td></tr>`).join('')
 }</tbody></table>`;
}

document.querySelectorAll('.quick').forEach(btn=>btn.addEventListener('click',()=>{
 setQuick(btn.dataset.period);loadAll();
}));
document.getElementById('restaurant').addEventListener('change',loadAll);
setQuick('30');
(async()=>{await loadAgents();await loadAll();setInterval(loadAll,60000)})().catch(console.error);
</script>
</body>
</html>
"""


def setup_dashboard_routes(
    storage: GatewayStorage,
    connections: ConnectionManager,
) -> APIRouter:

    @router.get("/", include_in_schema=False)
    def root(request: Request):
        if validate_session_cookie(
            request.cookies.get(COOKIE_NAME)
        ):
            return RedirectResponse("/dashboard")
        return RedirectResponse("/login")

    @router.get("/login", response_class=HTMLResponse, include_in_schema=False)
    def login_page(request: Request):
        if validate_session_cookie(
            request.cookies.get(COOKIE_NAME)
        ):
            return RedirectResponse("/dashboard")
        return HTMLResponse(
            LOGIN_HTML.replace("__LOGIN_ERROR__", "")
        )

    @router.post("/login", response_class=HTMLResponse, include_in_schema=False)
    def login(token: str = Form(...)):
        if token != settings.admin_token:
            return HTMLResponse(
                LOGIN_HTML.replace(
                    "__LOGIN_ERROR__",
                    '<div class="error">Неверный токен</div>',
                ),
                status_code=401,
            )

        response = RedirectResponse(
            "/dashboard",
            status_code=303,
        )
        response.set_cookie(
            COOKIE_NAME,
            create_session_cookie(),
            max_age=60 * 60 * 24 * 7,
            httponly=True,
            samesite="lax",
        )
        return response

    @router.get("/logout", include_in_schema=False)
    def logout():
        response = RedirectResponse("/login")
        response.delete_cookie(COOKIE_NAME)
        return response

    @router.get(
        "/dashboard",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def dashboard(request: Request):
        if not validate_session_cookie(
            request.cookies.get(COOKIE_NAME)
        ):
            return RedirectResponse("/login")
        return DASHBOARD_HTML

    @router.get("/api/web/agents", include_in_schema=False)
    def web_agents(request: Request):
        require_browser_session(request)
        result = storage.list_agents()
        for item in result:
            item["online"] = connections.is_online(
                item["agent_id"]
            )
        return result

    @router.get(
        "/api/web/{agent_id}/status",
        include_in_schema=False,
    )
    def web_agent_status(agent_id: str, request: Request):
        require_browser_session(request)
        agents = {
            item["agent_id"]: item
            for item in storage.list_agents()
        }
        item = agents.get(agent_id)
        if item is None:
            return JSONResponse(
                {"detail": "Агент не найден"},
                status_code=404,
            )
        item["online"] = connections.is_online(agent_id)
        return item

    @router.get(
        "/api/web/{agent_id}/sales/latest",
        include_in_schema=False,
    )
    def web_latest_sales(agent_id: str, request: Request):
        require_browser_session(request)
        result = storage.latest_sales_snapshot(agent_id)
        if result is None:
            return JSONResponse(
                {"detail": "Данные ещё не получены"},
                status_code=404,
            )
        return result

    @router.get(
        "/api/web/{agent_id}/sales/history",
        include_in_schema=False,
    )
    def web_sales_history(
        agent_id: str,
        request: Request,
        date_from: str,
        date_to: str,
    ):
        require_browser_session(request)
        return storage.sales_history(
            agent_id,
            date_from,
            date_to,
        )

    @router.get(
        "/api/web/{agent_id}/menu/history",
        include_in_schema=False,
    )
    def web_menu_history(
        agent_id: str,
        request: Request,
        date_from: str,
        date_to: str,
    ):
        require_browser_session(request)
        return storage.menu_sales_history(
            agent_id,
            date_from,
            date_to,
        )

    return router
