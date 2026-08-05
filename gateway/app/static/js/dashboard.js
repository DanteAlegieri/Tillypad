let agent="gastrodom3";

const PERIODS = new Set([
  "today",
  "yesterday",
  "week",
  "month",
  "prevmonth",
]);

const urlParams = new URLSearchParams(window.location.search);
let period = PERIODS.has(urlParams.get("period"))
  ? urlParams.get("period")
  : "today";

const money=v=>new Intl.NumberFormat("ru-RU",{maximumFractionDigits:0}).format(Number(v||0))+" ₽";
const integer=v=>new Intl.NumberFormat("ru-RU",{maximumFractionDigits:0}).format(Number(v||0));
const isoLocal=d=>{
  const y=d.getFullYear();
  const m=String(d.getMonth()+1).padStart(2,"0");
  const day=String(d.getDate()).padStart(2,"0");
  return `${y}-${m}-${day}`;
};
const localTime=v=>v?new Date(v).toLocaleString("ru-RU",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"}):"—";
const api=async u=>{const r=await fetch(u);if(!r.ok)throw new Error(await r.text());return r.json()};

const byId=id=>document.getElementById(id);
const setText=(id,value)=>{
  const node=byId(id);
  if(node) node.textContent=value;
};
const setHtml=(id,value)=>{
  const node=byId(id);
  if(node) node.innerHTML=value;
};
const setClass=(id,value)=>{
  const node=byId(id);
  if(node) node.className=value;
};

function monthName(monthIndex){
  return [
    "Январь","Февраль","Март","Апрель","Май","Июнь",
    "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь",
  ][monthIndex];
}

function formatShort(dateValue){
  return new Intl.DateTimeFormat("ru-RU",{
    day:"2-digit",
    month:"2-digit",
    year:"numeric",
  }).format(dateValue);
}

function ranges(){
  const now=new Date();
  const from=new Date(now);
  const to=new Date(now);
  const pf=new Date(now);
  const pt=new Date(now);

  if(period==="today"){
    pf.setDate(pf.getDate()-1);
    pt.setDate(pt.getDate()-1);
  }

  if(period==="yesterday"){
    from.setDate(from.getDate()-1);
    to.setDate(to.getDate()-1);
    pf.setDate(pf.getDate()-2);
    pt.setDate(pt.getDate()-2);
  }

  if(period==="week"){
    from.setDate(from.getDate()-6);
    pf.setDate(pf.getDate()-13);
    pt.setDate(pt.getDate()-7);
  }

  if(period==="month"){
    from.setDate(1);

    pf.setMonth(pf.getMonth()-1,1);
    pt.setFullYear(pf.getFullYear(),pf.getMonth()+1,0);
  }

  if(period==="prevmonth"){
    from.setMonth(from.getMonth()-1,1);
    to.setDate(0);

    pf.setFullYear(from.getFullYear(),from.getMonth()-1,1);
    pt.setFullYear(from.getFullYear(),from.getMonth(),0);
  }

  return {
    from:isoLocal(from),
    to:isoLocal(to),
    pf:isoLocal(pf),
    pt:isoLocal(pt),
    fromDate:from,
    toDate:to,
  };
}

function periodPresentation(range){
  if(period==="today"){
    return {
      title:"Сегодня",
      subtitle:new Intl.DateTimeFormat("ru-RU",{
        day:"2-digit",month:"long",year:"numeric",
      }).format(range.fromDate),
      revenue:"Выручка сегодня",
      average:"Средний чек сегодня",
      checks:"Чеков сегодня",
      forecast:"Прогноз дня",
      hero:"Сегодня",
    };
  }

  if(period==="yesterday"){
    return {
      title:"Вчера",
      subtitle:new Intl.DateTimeFormat("ru-RU",{
        day:"2-digit",month:"long",year:"numeric",
      }).format(range.fromDate),
      revenue:"Выручка вчера",
      average:"Средний чек вчера",
      checks:"Чеков вчера",
      forecast:"Итог дня",
      hero:"Вчера",
    };
  }

  if(period==="week"){
    return {
      title:"Последние 7 дней",
      subtitle:`${formatShort(range.fromDate)} — ${formatShort(range.toDate)}`,
      revenue:"Выручка за 7 дней",
      average:"Средний чек за 7 дней",
      checks:"Чеков за 7 дней",
      forecast:"Итог периода",
      hero:"За последние 7 дней",
    };
  }

  const monthTitle=`${monthName(range.fromDate.getMonth())} ${range.fromDate.getFullYear()}`;

  if(period==="month"){
    return {
      title:monthTitle,
      subtitle:`${formatShort(range.fromDate)} — ${formatShort(range.toDate)}`,
      revenue:`Выручка за ${monthName(range.fromDate.getMonth()).toLowerCase()}`,
      average:`Средний чек за ${monthName(range.fromDate.getMonth()).toLowerCase()}`,
      checks:`Чеков за ${monthName(range.fromDate.getMonth()).toLowerCase()}`,
      forecast:"Итог текущего месяца",
      hero:`За ${monthName(range.fromDate.getMonth()).toLowerCase()}`,
    };
  }

  return {
    title:monthTitle,
    subtitle:`${formatShort(range.fromDate)} — ${formatShort(range.toDate)}`,
    revenue:`Выручка за ${monthName(range.fromDate.getMonth()).toLowerCase()}`,
    average:`Средний чек за ${monthName(range.fromDate.getMonth()).toLowerCase()}`,
    checks:`Чеков за ${monthName(range.fromDate.getMonth()).toLowerCase()}`,
    forecast:"Итог прошлого месяца",
    hero:`В ${monthName(range.fromDate.getMonth()).toLowerCase()}`,
  };
}

function aggregate(data){
  const rows=data?.rows||data||[];
  return rows.reduce((a,x)=>({
    revenue:a.revenue+Number(x.revenue||0),
    checks:a.checks+Number(x.checks_count||x.orders||0),
  }),{revenue:0,checks:0});
}

function comparison(current,previous){
  if(!previous)return {raw:null,text:"нет базы сравнения",cls:"text-muted"};
  const raw=(current-previous)/previous*100;
  return {
    raw,
    text:`${raw>=0?"▲":"▼"} ${Math.abs(raw).toFixed(1)}% к прошлому периоду`,
    cls:raw>=0?"text-good":"text-bad",
  };
}

function setDelta(id,value){
  const element=byId(id);
  if(!element) return;
  element.textContent=value.text;
  element.className=`delta ${value.cls}`;
}

function topItems(menu){
  if(Array.isArray(menu?.top_items))return menu.top_items;
  if(Array.isArray(menu?.items))return menu.items;
  if(Array.isArray(menu?.rows))return menu.rows;
  return [];
}

function setPeriodInUrl(){
  const url=new URL(window.location.href);
  url.searchParams.set("period",period);
  history.replaceState({period},"",url);
}

function activatePeriodButton(){
  document.querySelectorAll("[data-period]").forEach(button=>{
    button.classList.toggle("is-active",button.dataset.period===period);
  });
}

async function initialize(){
  const agents=await api("/api/web/agents").catch(()=>[]);
  const select=document.getElementById("agent-select");
  select.innerHTML=(agents||[]).map(x=>`<option value="${x.agent_id}">${x.name||x.agent_id}</option>`).join("");

  agent=agents?.[0]?.agent_id||"gastrodom3";
  select.value=agent;
  select.onchange=()=>{
    agent=select.value;
    loadDashboard();
  };

  document.querySelectorAll("[data-period]").forEach(button=>{
    button.onclick=()=>{
      period=button.dataset.period;
      activatePeriodButton();
      setPeriodInUrl();
      loadDashboard();
    };
  });

  activatePeriodButton();
  setPeriodInUrl();
  await loadDashboard();
}

async function loadDashboard(){
  const range=ranges();
  const presentation=periodPresentation(range);

  document.querySelector(".workspace-header h1").textContent=presentation.title;
  setText("date-title",presentation.subtitle);
  setText("chart-caption",presentation.subtitle);
  setText("revenue-label",presentation.revenue);
  setText("average-label",presentation.average);
  setText("checks-label",presentation.checks);
  setText("forecast-label",presentation.forecast);

  const [historyRows,previousRows,status,latest,menu,report,events]=await Promise.all([
    api(`/api/web/${agent}/sales/history?date_from=${range.from}&date_to=${range.to}`).catch(()=>[]),
    api(`/api/web/${agent}/sales/history?date_from=${range.pf}&date_to=${range.pt}`).catch(()=>[]),
    api(`/api/web/${agent}/status`).catch(()=>({})),
    api(`/api/web/${agent}/sales/latest`).catch(()=>({})),
    api(`/api/web/${agent}/menu/history?date_from=${range.from}&date_to=${range.to}`).catch(()=>({})),
    api(`/api/web/${agent}/ai/director?date_from=${range.from}&date_to=${range.to}&previous_from=${range.pf}&previous_to=${range.pt}`).catch(()=>null),
    api(`/api/web/${agent}/events?limit=40`).catch(()=>[]),
  ]);

  const current=aggregate(historyRows);
  const previous=aggregate(previousRows);
  const average=current.checks?current.revenue/current.checks:0;
  const previousAverage=previous.checks?previous.revenue/previous.checks:0;

  const revenueDelta=comparison(current.revenue,previous.revenue);
  const averageDelta=comparison(average,previousAverage);
  const checksDelta=comparison(current.checks,previous.checks);

  document.getElementById("revenue").textContent=money(current.revenue);
  document.getElementById("average").textContent=money(average);
  document.getElementById("checks").textContent=integer(current.checks);
  document.getElementById("forecast").textContent=money(current.revenue);

  setDelta("revenue-delta",revenueDelta);
  setDelta("average-delta",averageDelta);
  setDelta("checks-delta",checksDelta);

  const hasCurrentData=current.checks>0||current.revenue>0;
  const score=report?.health_score?.score??report?.score??0;
  document.getElementById("score").textContent=hasCurrentData&&score?score:"—";

  const scoreNode=document.getElementById("score-status");
  if(!hasCurrentData){
    scoreNode.textContent="Нет данных за период";
    scoreNode.className="text-muted";
  }else{
    scoreNode.textContent=score>=80?"Хорошее состояние":score>=60?"Требует внимания":"Высокий риск";
    scoreNode.className=score>=80?"text-good":score>=60?"text-warn":"text-bad";
  }

  const online=Boolean(status?.online||status?.connected||status?.status==="online");
  document.getElementById("agent-state").innerHTML=
    `<i class="status-dot" style="background:${online?"var(--color-green)":"var(--color-red)"}"></i>${online?"Агент подключён":"Агент не в сети"}`;

  document.getElementById("sync-state").textContent=
    `Синхронизация: ${localTime(latest?.captured_at||latest?.created_at)}`;
  document.getElementById("last-seen").textContent=
    localTime(status?.last_seen_at||status?.last_heartbeat_at);
  document.getElementById("last-sync").textContent=
    localTime(latest?.captured_at||latest?.created_at);

  const leaders=topItems(menu);
  const leader=leaders[0]?.item_name||leaders[0]?.name||"Не определён";

  document.getElementById("leader").textContent=leader;
  document.getElementById("peak-hour").textContent=latest?.peak_hour||"Нет данных";
  document.getElementById("class-c").textContent=
    menu?.abc?.C?.count??menu?.class_c_count??"Нет данных";
  document.getElementById("last-check").textContent=
    latest?.last_check_at?localTime(latest.last_check_at):"Нет данных";
  document.getElementById("data-health").textContent=
    online?"Данные поступают":"Требуется проверка";

  const heroTitle=document.getElementById("hero-title");
  const heroText=document.getElementById("hero-text");

  if(!hasCurrentData){
    heroTitle.textContent=`За выбранный период данных пока нет`;
    heroText.innerHTML=
      `${presentation.subtitle}. Последняя синхронизация: <b>${localTime(latest?.captured_at||latest?.created_at)}</b>. `+
      `Для прошлых месяцев агент должен один раз выполнить загрузку истории.`;
  }else{
    const deltaText=revenueDelta.raw===null
      ?"сравнение пока недоступно"
      : revenueDelta.raw>=0
        ? `выручка выше прошлого периода на ${Math.abs(revenueDelta.raw).toFixed(1)}%`
        : `выручка ниже прошлого периода на ${Math.abs(revenueDelta.raw).toFixed(1)}%`;

    heroTitle.textContent=`${presentation.hero} ресторан сформировал ${money(current.revenue)}`;
    heroText.innerHTML=
      `Чеков — <b>${integer(current.checks)}</b>, средний чек — <b>${money(average)}</b>; ${deltaText}. `+
      `Лидер продаж — <b>${leader}</b>.`;
  }

  renderAttention(events,revenueDelta,averageDelta,online,menu,hasCurrentData);
  renderRecommendations(revenueDelta,averageDelta,menu,hasCurrentData);
  renderLeaders(leaders);
  renderChart(historyRows,latest);
}

function renderAttention(events,revenueDelta,averageDelta,online,menu,hasData){
  const items=[];

  if(!online){
    items.push({title:"Агент не в сети",text:"Свежие показатели могут не поступать."});
  }

  if(!hasData){
    items.push({
      title:"Нет данных за выбранный период",
      text:"Запустите агент 31.1.0 для загрузки истории из Tillypad.",
    });
  }else{
    if(revenueDelta.raw!==null&&revenueDelta.raw<-5){
      items.push({
        title:"Выручка ниже прошлого периода",
        text:`Отставание ${Math.abs(revenueDelta.raw).toFixed(1)}%.`,
      });
    }

    if(averageDelta.raw!==null&&averageDelta.raw<-5){
      items.push({
        title:"Средний чек снизился",
        text:"Нужны допродажи и комбо.",
      });
    }

    const classC=menu?.abc?.C?.count??menu?.class_c_count;
    if(Number(classC)>0){
      items.push({
        title:`${classC} позиций класса C`,
        text:"Низкий вклад в выручку — требуется анализ меню.",
      });
    }
  }

  (events||[])
    .filter(x=>x.event_type!=="snapshot_created")
    .slice(0,2)
    .forEach(x=>items.push({title:x.title,text:x.description}));

  if(!items.length){
    items.push({
      title:"Критических проблем нет",
      text:"Основные показатели находятся в нормальном диапазоне.",
    });
  }

  document.getElementById("attention").innerHTML=
    items.slice(0,5).map(x=>
      `<article class="issue"><b>${x.title}</b><p>${x.text}</p></article>`
    ).join("");
}

function renderRecommendations(revenueDelta,averageDelta,menu,hasData){
  const items=[];

  if(!hasData){
    items.push({
      title:"Загрузить историю",
      text:"Обновите Windows Agent до 31.1.0. Он отправит последние 70 дней продаж в облако.",
    });
  }else{
    if(averageDelta.raw!==null&&averageDelta.raw<-3){
      items.push({
        title:"Усилить допродажи",
        text:"Предлагать напиток или гарнир к каждому третьему заказу.",
      });
    }

    if(revenueDelta.raw!==null&&revenueDelta.raw<-5){
      items.push({
        title:"Восстановить темп продаж",
        text:"Проверить акции и продвижение в слабые часы.",
      });
    }

    const classC=menu?.abc?.C?.count??menu?.class_c_count;
    if(Number(classC)>0){
      items.push({
        title:"Проверить класс C",
        text:`Пересмотреть ${classC} слабых позиций.`,
      });
    }
  }

  if(!items.length){
    items.push({
      title:"Сохранять текущий темп",
      text:"Контролировать средний чек и наличие лидеров меню.",
    });
  }

  document.getElementById("recommendations").innerHTML=
    items.slice(0,4).map(x=>
      `<article class="recommendation"><b>${x.title}</b><p>${x.text}</p></article>`
    ).join("");
}

function renderLeaders(items){
  document.getElementById("leaders").innerHTML=
    items.slice(0,5).map((x,i)=>
      `<div><span>${i+1}. ${x.item_name||x.name||"Без названия"}</span><strong>${money(x.revenue||0)}</strong></div>`
    ).join("")||'<div class="empty">Нет данных</div>';
}

function renderChart(historyRows,latest){
  const rows=historyRows?.rows||historyRows||[];
  let labels=rows.map(x=>x.business_date||x.date||"");
  let values=rows.map(x=>Number(x.revenue||0));

  if(period==="today"&&latest?.hourly?.rows){
    const columns=latest.hourly.columns||[];
    labels=latest.hourly.rows.map(row=>{
      const x=Object.fromEntries(columns.map((column,index)=>[column,row[index]]));
      return String(x.hour??x.sale_hour??"");
    });
    values=latest.hourly.rows.map(row=>{
      const x=Object.fromEntries(columns.map((column,index)=>[column,row[index]]));
      return Number(x.revenue||0);
    });
  }

  const chart=echarts.init(document.getElementById("sales-chart"));
  chart.setOption({
    grid:{left:48,right:14,top:18,bottom:34},
    tooltip:{trigger:"axis"},
    xAxis:{type:"category",boundaryGap:false,data:labels},
    yAxis:{type:"value"},
    series:[{
      type:"line",
      smooth:true,
      symbol:"none",
      lineStyle:{width:3},
      areaStyle:{opacity:.08},
      data:values,
    }],
  },true);
}

window.addEventListener("popstate",()=>{
  const requested=new URLSearchParams(window.location.search).get("period");
  period=PERIODS.has(requested)?requested:"today";
  activatePeriodButton();
  loadDashboard();
});

initialize().catch(error=>{
  console.error("Dashboard initialization failed",error);
  setText("hero-title","Не удалось загрузить рабочий стол");
  setText("hero-text",error.message);
});
