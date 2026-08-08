import {
  activatePeriodButton as activatePeriodButtonFor,
  setPeriodInUrl as setPeriodInUrlFor,
} from "./period-controls.js";

function activatePeriodButton(){
  activatePeriodButtonFor(period);
}

function setPeriodInUrl(){
  setPeriodInUrlFor(period);
}

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

let dailyRevenuePlan=10000;
let dashboardLoadSequence=0;

function daysInclusive(fromDate,toDate){
  const start=new Date(fromDate.getFullYear(),fromDate.getMonth(),fromDate.getDate());
  const end=new Date(toDate.getFullYear(),toDate.getMonth(),toDate.getDate());
  return Math.max(1,Math.round((end-start)/86400000)+1);
}

function planForPeriod(periodName,range){
  if(periodName==="today"||periodName==="yesterday"){
    return dailyRevenuePlan;
  }

  if(periodName==="month"||periodName==="prevmonth"){
    const daysInMonth=new Date(
      range.fromDate.getFullYear(),
      range.fromDate.getMonth()+1,
      0
    ).getDate();
    return dailyRevenuePlan*daysInMonth;
  }

  return dailyRevenuePlan*daysInclusive(range.fromDate,range.toDate);
}

function percentOf(value,total){
  if(!total) return 0;
  return value/total*100;
}

function mainScoreReason(factors){
  const negative=(factors||[])
    .filter(item=>item.points<0)
    .sort((a,b)=>a.points-b.points);

  if(negative.length){
    return {
      title:negative[0].title,
      description:negative[0].description,
      points:negative[0].points,
    };
  }

  const positive=(factors||[])
    .filter(item=>item.points>0&&item.title!=="Базовая оценка")
    .sort((a,b)=>b.points-a.points);

  return positive[0]??null;
}

function leaderUnitPrice(item){
  if(!item) return 0;
  const quantity=itemQuantity(item);
  const revenue=itemRevenue(item);
  return quantity>0?revenue/quantity:revenue;
}

function salesNeeded(amount,unitPrice){
  if(amount<=0) return 0;
  if(unitPrice<=0) return null;
  return Math.ceil(amount/unitPrice);
}

function cleanText(value){
  return String(value??"")
    .replace(/\uFFFD+/g,"")
    .replace(/^[\s\u0000-\u001f]+/g,"")
    .replace(/\s{2,}/g," ")
    .trim();
}

function safeDate(value){
  if(!value) return null;
  const result=new Date(value);
  return Number.isNaN(result.getTime())?null:result;
}

function resolveAgentState(lastSignal,reportedOnline){
  const signal=safeDate(lastSignal);
  if(!signal){
    return {code:"offline",title:"Недоступен",detail:"Нет данных о последнем сигнале"};
  }

  const minutes=Math.max(0,(Date.now()-signal.getTime())/60000);

  if(minutes<=5){
    return {
      code:"online",
      title:"Онлайн",
      detail:`Последний сигнал ${Math.max(1,Math.round(minutes))} мин. назад`,
    };
  }
  if(minutes<=20){
    return {code:"delayed",title:"Нет новых данных",detail:`Последний сигнал ${Math.round(minutes)} мин. назад`};
  }
  if(minutes<=60){
    return {code:"warning",title:"Требуется проверка",detail:`Нет связи ${Math.round(minutes)} мин.`};
  }
  return {
    code:"offline",
    title:"Недоступен",
    detail:`Нет связи ${Math.floor(minutes/60)} ч. ${Math.round(minutes%60)} мин.`,
  };
}

function lastSaleFromSnapshot(latest){
  const sale=latest?.payload?.latest_sale??latest?.latest_sale;
  const rows=rowsToObjects(sale);
  const item=rows[0];
  if(!item) return null;
  return {
    name:itemName(item),
    amount:Number(item?.amount??item?.revenue??item?.line_amount??0),
    time:item?.sale_at??item?.sale_time??item?.check_date??null,
  };
}

function peakHourFromSnapshot(latest){
  const rows=rowsToObjects(latest?.hourly);
  if(!rows.length) return null;
  const peak=rows.reduce((best,row)=>
    Number(row?.revenue??0)>Number(best?.revenue??0)?row:best
  ,rows[0]);
  const hour=Number(peak?.sale_hour??peak?.hour);
  if(!Number.isFinite(hour)) return null;
  return `${String(hour).padStart(2,"0")}:00–${String((hour+1)%24).padStart(2,"0")}:00`;
}

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
const query=selector=>document.querySelector(selector);
const setQueryText=(selector,value)=>{
  const node=query(selector);
  if(node) node.textContent=value;
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

function ranges(periodName=period){
  const now=new Date();
  const from=new Date(now);
  const to=new Date(now);
  const pf=new Date(now);
  const pt=new Date(now);

  if(periodName==="today"){
    pf.setDate(pf.getDate()-1);
    pt.setDate(pt.getDate()-1);
  }

  if(periodName==="yesterday"){
    from.setDate(from.getDate()-1);
    to.setDate(to.getDate()-1);
    pf.setDate(pf.getDate()-2);
    pt.setDate(pt.getDate()-2);
  }

  if(periodName==="week"){
    from.setDate(from.getDate()-6);
    pf.setDate(pf.getDate()-13);
    pt.setDate(pt.getDate()-7);
  }

  if(periodName==="month"){
    // MTD сравниваем только с сопоставимым отрезком прошлого месяца:
    // 1..сегодня против 1..того же числа прошлого месяца.
    from.setDate(1);

    pf.setFullYear(from.getFullYear(),from.getMonth()-1,1);
    const previousMonthLastDay=new Date(
      pf.getFullYear(),
      pf.getMonth()+1,
      0
    ).getDate();
    const comparableDay=Math.min(to.getDate(),previousMonthLastDay);
    pt.setFullYear(pf.getFullYear(),pf.getMonth(),comparableDay);
  }

  if(periodName==="prevmonth"){
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

function periodPresentation(range,periodName=period){
  if(periodName==="today"){
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

  if(periodName==="yesterday"){
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

  if(periodName==="week"){
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

  if(periodName==="month"){
    return {
      title:monthTitle,
      subtitle:`${formatShort(range.fromDate)} — ${formatShort(range.toDate)}`,
      revenue:`Выручка за ${monthName(range.fromDate.getMonth()).toLowerCase()}`,
      average:`Средний чек за ${monthName(range.fromDate.getMonth()).toLowerCase()}`,
      checks:`Чеков за ${monthName(range.fromDate.getMonth()).toLowerCase()}`,
      forecast:"Прогноз месяца",
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

function rowsToObjects(dataset){
  if(!dataset) return [];
  if(Array.isArray(dataset)){
    if(!dataset.length) return [];
    if(typeof dataset[0]==="object"&&!Array.isArray(dataset[0])) return dataset;
  }

  const rows=dataset?.rows;
  const columns=dataset?.columns;
  if(Array.isArray(rows)&&Array.isArray(columns)){
    return rows.map(row=>Object.fromEntries(
      columns.map((column,index)=>[column,row[index]])
    ));
  }

  return [];
}

function topItems(menu){
  const candidates=[
    menu?.top_items,
    menu?.items,
    menu?.rows,
    menu?.top,
    menu?.leaders,
    menu?.menu?.top_items,
    menu?.data?.top_items,
    menu?.snapshot?.top_items,
  ];

  for(const candidate of candidates){
    const rows=rowsToObjects(candidate);
    if(rows.length) return rows;
  }

  if(Array.isArray(menu)){
    const rows=rowsToObjects(menu);
    if(rows.length) return rows;
  }

  return [];
}

function itemName(item){
  return cleanText(
    item?.item_name
    ??item?.name
    ??item?.menu_item_name
    ??item?.product_name
    ??item?.title
    ??"Без названия"
  );
}

function itemRevenue(item){
  return Number(
    item?.revenue
    ??item?.sum
    ??item?.amount
    ??item?.sales_sum
    ??item?.total
    ??0
  );
}

function itemQuantity(item){
  return Number(
    item?.quantity
    ??item?.qty
    ??item?.count
    ??item?.sales_count
    ??item?.volume
    ??0
  );
}

function calculateRestaurantScore({
  hasData,
  online,
  revenueDelta,
  averageDelta,
  checksDelta,
  classC,
}){
  if(!hasData) return {score:null,factors:[]};

  let score=65;
  const factors=[
    {
      title:"Базовая оценка",
      description:"Стартовая оценка при наличии продаж",
      points:65,
    },
  ];

  const apply=(title,description,points)=>{
    score+=points;
    factors.push({title,description,points});
  };

  apply(
    "Связь с рестораном",
    online?"Агент передаёт свежие данные":"Агент не в сети",
    online?15:-15
  );

  if(revenueDelta.raw!==null){
    let points=0;
    if(revenueDelta.raw>=10) points=12;
    else if(revenueDelta.raw>=0) points=7;
    else if(revenueDelta.raw>=-10) points=-5;
    else if(revenueDelta.raw>=-25) points=-12;
    else points=-22;

    apply(
      "Динамика выручки",
      `${revenueDelta.raw>=0?"Рост":"Снижение"} ${Math.abs(revenueDelta.raw).toFixed(1)}%`,
      points
    );
  }

  if(averageDelta.raw!==null){
    let points=0;
    if(averageDelta.raw>=5) points=8;
    else if(averageDelta.raw>=0) points=4;
    else if(averageDelta.raw>=-10) points=-5;
    else points=-12;

    apply(
      "Средний чек",
      `${averageDelta.raw>=0?"Рост":"Снижение"} ${Math.abs(averageDelta.raw).toFixed(1)}%`,
      points
    );
  }

  if(checksDelta.raw!==null){
    let points=0;
    if(checksDelta.raw>=5) points=6;
    else if(checksDelta.raw< -15) points=-8;

    apply(
      "Количество чеков",
      `${checksDelta.raw>=0?"Рост":"Снижение"} ${Math.abs(checksDelta.raw).toFixed(1)}%`,
      points
    );
  }

  const weakItems=Number(classC);
  if(Number.isFinite(weakItems)){
    let points=0;
    if(weakItems===0) points=4;
    else if(weakItems<=5) points=1;
    else if(weakItems>=15) points=-6;

    apply(
      "Структура меню",
      weakItems===0?"Нет слабых позиций":`${weakItems} позиций класса C`,
      points
    );
  }

  return {
    score:Math.max(0,Math.min(100,Math.round(score))),
    factors,
  };
}

function calculateForecast(currentRevenue,periodName){
  if(periodName==="today"){
    const now=new Date();
    const hour=now.getHours()+now.getMinutes()/60;
    const serviceStart=10;
    const serviceEnd=22;
    const elapsed=Math.max(.5,Math.min(serviceEnd-serviceStart,hour-serviceStart));
    const fullDay=serviceEnd-serviceStart;

    if(hour<=serviceStart) return currentRevenue;
    return Math.round(currentRevenue*(fullDay/elapsed));
  }

  if(periodName==="month"){
    const now=new Date();
    const elapsedDays=Math.max(1,now.getDate());
    const totalDays=new Date(now.getFullYear(),now.getMonth()+1,0).getDate();
    return Math.round(currentRevenue/elapsedDays*totalDays);
  }

  return currentRevenue;
}

function isForecastPeriod(periodName){
  return periodName==="today"||periodName==="month";
}

function isCompletedPeriod(periodName){
  return periodName==="yesterday"||periodName==="prevmonth";
}

function buildDecisions({
  online,
  hasData,
  revenueDelta,
  averageDelta,
  checksDelta,
  classC,
  leader,
  leaderItem,
  currentRevenue,
  forecastRevenue,
  revenuePlan,
  periodName,
}){
  const decisions=[];
  const usesForecast=isForecastPeriod(periodName);
  const comparisonRevenue=usesForecast?forecastRevenue:currentRevenue;
  const forecastGap=Math.max(0,revenuePlan-comparisonRevenue);
  const leaderPrice=leaderUnitPrice(leaderItem);
  const requiredLeaderSales=salesNeeded(forecastGap,leaderPrice);

  if(hasData&&forecastGap>0&&requiredLeaderSales!==null){
    const completed=isCompletedPeriod(periodName);
    const rolling=periodName==="week";
    decisions.push({
      severity:completed||rolling?"warning":"critical",
      title:completed
        ?"План периода не выполнен"
        :rolling
          ?"Разрыв до плана за 7 дней"
          :"Закрыть разрыв до плана",
      text:completed
        ?`Факт ниже плана на ${money(forecastGap)}. Для ориентира это примерно ${integer(requiredLeaderSales)} продаж позиции «${leader}».`
        :rolling
          ?`За выбранные 7 дней выручка ниже плана на ${money(forecastGap)}. Это примерно ${integer(requiredLeaderSales)} продаж позиции «${leader}».`
          :`При текущем темпе прогноз ниже плана на ${money(forecastGap)}. Для компенсации нужно примерно ${integer(requiredLeaderSales)} продаж позиции «${leader}».`,
      meta:completed?"Итог":rolling?"Период":"Срочно",
      effect:`До плана ${money(forecastGap)}`,
    });
  }

  if(!online){
    decisions.push({
      severity:"critical",
      title:"Восстановить связь с агентом",
      text:"Без свежих данных прогноз и рекомендации могут быть неточными.",
      meta:"Срочно",
      effect:"Надёжность данных",
    });
  }

  if(hasData&&checksDelta.raw!==null&&checksDelta.raw<-15){
    decisions.push({
      severity:"critical",
      title:"Увеличить поток чеков",
      text:"Количество заказов снизилось сильнее среднего чека. Основная проблема — поток гостей.",
      meta:"Срочно",
      effect:`Чеки ${checksDelta.raw.toFixed(1)}%`,
    });
  }

  if(hasData&&averageDelta.raw!==null&&averageDelta.raw<-5){
    decisions.push({
      severity:"warning",
      title:"Усилить допродажи",
      text:"Добавляйте напиток или гарнир к основным позициям.",
      meta:"Требует внимания",
      effect:`Средний чек ${averageDelta.raw.toFixed(1)}%`,
    });
  }

  if(hasData&&revenueDelta.raw!==null&&revenueDelta.raw<-10){
    decisions.push({
      severity:"warning",
      title:"Поддержать продажи в слабые часы",
      text:`Используйте лидера продаж «${leader}» в акции или комбо.`,
      meta:"Требует внимания",
      effect:`Выручка ${revenueDelta.raw.toFixed(1)}%`,
    });
  }

  const weakItems=Number(classC);
  if(Number.isFinite(weakItems)&&weakItems>10){
    decisions.push({
      severity:"warning",
      title:"Проверить слабые позиции меню",
      text:`В классе C находится ${weakItems} позиций. Их стоит убрать, изменить или объединить в комбо.`,
      meta:"Планово",
      effect:"Оптимизация меню",
    });
  }

  if(!decisions.length){
    decisions.push({
      severity:"ok",
      title:"Сохранять текущий темп",
      text:"Критических отклонений нет. Контролируйте наличие лидеров продаж.",
      meta:"Всё хорошо",
      effect:"Стабильная работа",
    });
  }

  return decisions.slice(0,3);
}

function renderDecisions(decisions){
  setHtml("decision-center",
    decisions.map(item=>`
      <article class="decision-card ${item.severity}">
        <strong>${item.title}</strong>
        <p>${item.text}</p>
        <div class="decision-card__meta">
          <span>${item.meta}</span>
          <span>${item.effect}</span>
        </div>
      </article>
    `).join("")
  );
}

function renderScoreBreakdown(factors){
  const reason=mainScoreReason(factors);
  const maxAbsolute=Math.max(
    1,
    ...factors.map(item=>Math.abs(Number(item.points)||0))
  );

  setHtml("score-breakdown",
    factors.map(item=>{
      const isMain=Boolean(
        reason
        &&item.title===reason.title
        &&item.points===reason.points
      );
      const width=Math.max(
        8,
        Math.round(Math.abs(item.points)/maxAbsolute*100)
      );

      return `
        <article class="ros-factor-card ${isMain?"is-main":""}">
          <div class="ros-factor-card__top">
            <div>
              <strong>${item.title}</strong>
              <p>${item.description}</p>
            </div>
            <span class="ros-factor-card__points ${
              item.points>=0?"positive":"negative"
            }">
              ${item.points>=0?"+":""}${item.points}
            </span>
          </div>
          <div class="ros-factor-card__bar">
            <span style="width:${width}%"></span>
          </div>
        </article>
      `;
    }).join("")
  );
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

  const scoreDrawer=byId("score-drawer");
  const scoreOpen=byId("score-details-button");
  const scoreClose=byId("score-drawer-close");

  const openScoreDrawer=()=>{
    if(!scoreDrawer) return;
    scoreDrawer.hidden=false;
    requestAnimationFrame(()=>{
      scoreDrawer.classList.add("is-open");
      document.body.classList.add("drawer-open");
    });
  };

  const closeScoreDrawer=()=>{
    if(!scoreDrawer||scoreDrawer.hidden) return;
    scoreDrawer.classList.remove("is-open");
    document.body.classList.remove("drawer-open");
    window.setTimeout(()=>{
      if(!scoreDrawer.classList.contains("is-open")){
        scoreDrawer.hidden=true;
      }
    },220);
  };

  if(scoreOpen) scoreOpen.onclick=openScoreDrawer;
  if(scoreClose) scoreClose.onclick=closeScoreDrawer;

  if(scoreDrawer){
    scoreDrawer.onclick=event=>{
      if(event.target===scoreDrawer) closeScoreDrawer();
    };
  }

  document.addEventListener("keydown",event=>{
    if(event.key==="Escape") closeScoreDrawer();
  });

  activatePeriodButton();
  setPeriodInUrl();
  await loadDashboard();
}

async function loadDashboard(){
  const loadId=++dashboardLoadSequence;
  const requestedPeriod=period;
  setText("hero-title","Обновляю данные…");
  const range=ranges(requestedPeriod);
  const presentation=periodPresentation(range,requestedPeriod);

  setQueryText(".workspace-header h1",presentation.title);
  setText("date-title",presentation.subtitle);
  setText(
    "chart-caption",
    requestedPeriod==="today"
      ?`${presentation.subtitle} · по часам`
      :requestedPeriod==="yesterday"
        ?`${presentation.subtitle} · по часам`
        :presentation.subtitle
  );
  setText("revenue-label",presentation.revenue);
  setText("average-label",presentation.average);
  setText("checks-label",presentation.checks);
  setText("forecast-label",presentation.forecast);

  const [historyRows,previousRows,status,latest,menu,report,events,restaurantSettings]=await Promise.all([
    api(`/api/web/${agent}/sales/history?date_from=${range.from}&date_to=${range.to}`).catch(()=>[]),
    api(`/api/web/${agent}/sales/history?date_from=${range.pf}&date_to=${range.pt}`).catch(()=>[]),
    api(`/api/web/${agent}/status`).catch(()=>({})),
    api(`/api/web/${agent}/sales/latest`).catch(()=>({})),
    api(`/api/web/${agent}/menu/history?date_from=${range.from}&date_to=${range.to}`).catch(()=>({})),
    api(`/api/web/${agent}/ai/director?date_from=${range.from}&date_to=${range.to}&previous_from=${range.pf}&previous_to=${range.pt}`).catch(()=>null),
    api(`/api/web/${agent}/events?limit=40`).catch(()=>[]),
    api(`/api/web/${agent}/settings`).catch(()=>({daily_revenue_plan:10000})),
  ]);

  // Если пользователь уже переключил период, этот ответ устарел.
  // Он не имеет права перерисовывать новый экран.
  if(loadId!==dashboardLoadSequence||requestedPeriod!==period){
    return;
  }

  dailyRevenuePlan=Number(
    restaurantSettings?.daily_revenue_plan??10000
  );

  const current=aggregate(historyRows);
  const previous=aggregate(previousRows);
  const average=current.checks?current.revenue/current.checks:0;
  const previousAverage=previous.checks?previous.revenue/previous.checks:0;

  const revenueDelta=comparison(current.revenue,previous.revenue);
  const averageDelta=comparison(average,previousAverage);
  const checksDelta=comparison(current.checks,previous.checks);

  setText("revenue",money(current.revenue));
  setText("average",money(average));
  setText("checks",integer(current.checks));
  const forecastRevenue=calculateForecast(current.revenue,requestedPeriod);
  const revenuePlan=planForPeriod(requestedPeriod,range);
  const planPercent=percentOf(current.revenue,revenuePlan);
  const forecastPercent=percentOf(forecastRevenue,revenuePlan);
  const planGap=Math.max(0,revenuePlan-current.revenue);
  const forecastGap=Math.max(0,revenuePlan-forecastRevenue);

  setText("forecast",money(forecastRevenue));
  setText("plan-fact",money(current.revenue));
  setText("plan-target",money(revenuePlan));
  setText("plan-percent",`${Math.min(999,planPercent).toFixed(1)}%`);
  setText(
    "plan-status",
    planPercent>=100?"План выполнен":planPercent>=70?"Близко к плану":"Требуется рост"
  );
  setText(
    "plan-period-label",
    requestedPeriod==="today"
      ?"План на сегодня"
      :requestedPeriod==="yesterday"
        ?"План на вчера"
        :"План за выбранный период"
  );
  setText(
    "plan-gap",
    planGap>0?`До плана: ${money(planGap)}`:`План превышен на ${money(current.revenue-revenuePlan)}`
  );
  setText(
    "plan-forecast-status",
    isForecastPeriod(requestedPeriod)
      ?(
        forecastGap>0
          ?`Прогноз ниже плана на ${money(forecastGap)}`
          :`Прогноз выполняет план на ${forecastPercent.toFixed(1)}%`
      )
      :(
        planGap>0
          ?`Факт ниже плана на ${money(planGap)}`
          :`Факт выше плана на ${money(current.revenue-revenuePlan)}`
      )
  );

  const planFill=byId("plan-progress-fill");
  if(planFill){
    planFill.style.width=`${Math.min(100,planPercent)}%`;
    planFill.className=planPercent>=100?"good":planPercent>=70?"warning":"";
  }

  setDelta("revenue-delta",revenueDelta);
  setDelta("average-delta",averageDelta);
  setDelta("checks-delta",checksDelta);

  const hasCurrentData=current.checks>0||current.revenue>0;
  const lastSignalValue=status?.last_seen_at||status?.last_heartbeat_at||latest?.captured_at||latest?.created_at;
  const reportedOnline=Boolean(status?.online||status?.connected||status?.status==="online");
  const agentStatus=resolveAgentState(lastSignalValue,reportedOnline);
  const online=agentStatus.code==="online";
  const classC=menu?.abc?.C?.count??menu?.class_c_count??null;
  const scoreResult=calculateRestaurantScore({
    hasData:hasCurrentData,
    online,
    revenueDelta,
    averageDelta,
    checksDelta,
    classC,
  });
  const backendScore=report?.health_score?.score??report?.score;
  const score=Number.isFinite(Number(backendScore))
    ?Math.round(Number(backendScore))
    :scoreResult.score;

  renderScoreBreakdown(scoreResult.factors);

  const primaryScoreReason=mainScoreReason(scoreResult.factors);
  setText(
    "score-main-reason",
    primaryScoreReason
      ?`${primaryScoreReason.points<0?"▼":"▲"} ${primaryScoreReason.title}: ${primaryScoreReason.description}`
      :"Критических факторов нет"
  );

  setText("score-drawer-value",score??"—");
  setText(
    "score-drawer-status",
    score===null||score===undefined
      ?"Нет данных"
      :score>=80
        ?"Стабильно"
        :score>=60
          ?"Требует внимания"
          :"Высокий риск"
  );
  setText(
    "score-drawer-reason",
    primaryScoreReason
      ?`${primaryScoreReason.points<0?"▼":"▲"} ${primaryScoreReason.title}: ${primaryScoreReason.description}`
      :"Критических факторов нет"
  );

  setText("score",score===null?"—":score);

  const scoreNode=byId("score-status");
  const scoreBox=document.querySelector(".score");
  if(scoreBox) scoreBox.classList.remove("good-score","warn-score","bad-score");

  if(scoreNode&&score===null){
    scoreNode.textContent="Нет данных за период";
    scoreNode.className="muted";
  }else if(scoreNode){
    scoreNode.textContent=score>=80?"Состояние хорошее":score>=60?"Требует внимания":"Высокий риск";
    scoreNode.className=score>=80?"good":score>=60?"warn":"bad";
    if(scoreBox){
      scoreBox.classList.add(score>=80?"good-score":score>=60?"warn-score":"bad-score");
    }
  }

  setHtml(
    "agent-state",
    `<span class="agent-state ${agentStatus.code}">
      <i class="agent-state__dot" style="background:currentColor"></i>
      ${agentStatus.title}
    </span>`
  );

  setText(
    "sync-state",
    `Синхронизация: ${localTime(latest?.captured_at||latest?.created_at)}`
  );
  setText(
    "last-seen",
    localTime(status?.last_seen_at||status?.last_heartbeat_at)
  );
  setText(
    "last-sync",
    localTime(latest?.captured_at||latest?.created_at)
  );

  // Аналитические лидеры зависят от выбранного периода.
  const leaders=topItems(menu);
  const leader=leaders.length?itemName(leaders[0]):"Не определён";

  // «Ресторан сейчас» всегда строится из последнего live snapshot и
  // не должен меняться при переключении Сегодня/Месяц/Прошлый месяц.
  const liveLeaders=topItems(latest?.menu);
  const liveLeader=liveLeaders.length?itemName(liveLeaders[0]):"Не определён";
  const lastSale=lastSaleFromSnapshot(latest);
  if(lastSale){
    setText("last-sale-name",lastSale.name);
    setText("last-sale-time",lastSale.time?localTime(lastSale.time):"—");
    setText("last-sale-amount",money(lastSale.amount));
  }else{
    setText("last-sale-name","Нет данных от агента");
    setText("last-sale-time","—");
    setText("last-sale-amount","—");
  }
  const decisions=buildDecisions({
    online,
    hasData:hasCurrentData,
    revenueDelta,
    averageDelta,
    checksDelta,
    classC,
    leader,
    leaderItem:leaders[0]??null,
    currentRevenue:current.revenue,
    forecastRevenue,
    revenuePlan,
    periodName:requestedPeriod,
  });
  renderDecisions(decisions);

  setText("leader",liveLeader);
  setText("peak-hour",peakHourFromSnapshot(latest)||"Нет данных");
  setText(
    "class-c",
    menu?.abc?.C?.count??menu?.class_c_count??"Нет данных"
  );
  setText(
    "last-check",
    latest?.last_check_at?localTime(latest.last_check_at):"Нет данных"
  );
  setText(
    "data-health",
    agentStatus.code==="online"?"Данные поступают":agentStatus.detail
  );

  const heroTitle=byId("hero-title");
  const heroText=byId("hero-text");

  if(!hasCurrentData){
    if(heroTitle) heroTitle.textContent=`За выбранный период данных пока нет`;
    if(heroText) heroText.innerHTML=
      `${presentation.subtitle}. Последняя синхронизация: <b>${localTime(latest?.captured_at||latest?.created_at)}</b>. `+
      `Для прошлых месяцев агент должен один раз выполнить загрузку истории.`;
  }else{
    const deltaText=revenueDelta.raw===null
      ?"сравнение пока недоступно"
      : revenueDelta.raw>=0
        ? `выручка выше прошлого периода на ${Math.abs(revenueDelta.raw).toFixed(1)}%`
        : `выручка ниже прошлого периода на ${Math.abs(revenueDelta.raw).toFixed(1)}%`;

    const flowProblem=checksDelta.raw!==null&&checksDelta.raw<averageDelta.raw;
    if(heroTitle) heroTitle.textContent=`${presentation.hero} выручка составила ${money(current.revenue)}`;
    if(heroText) heroText.innerHTML=
      `Оформлено <b>${integer(current.checks)}</b> чеков, средний чек — <b>${money(average)}</b>; ${deltaText}. `+
      `${flowProblem?"Основная проблема — снижение количества заказов.":"Основная динамика связана со средним чеком."} `+
      `Лидер продаж — <b>${leader}</b>.`;
  }

  renderAttention(events,revenueDelta,averageDelta,online,menu,hasCurrentData);
  renderRecommendations(revenueDelta,averageDelta,menu,hasCurrentData);
  renderLeaders(leaders);
  renderChart(historyRows,latest,requestedPeriod);
}

function renderAttention(events,revenueDelta,averageDelta,online,menu,hasData){
  const items=[];

  if(!online){
    items.push({
      severity:"critical",
      title:"Агент не в сети",
      text:"Свежие показатели могут не поступать.",
      tag:"Связь",
    });
  }

  if(!hasData){
    items.push({
      severity:"warning",
      title:"Нет данных за выбранный период",
      text:"Проверьте загрузку истории Windows Agent.",
      tag:"Данные",
    });
  }else{
    if(revenueDelta.raw!==null&&revenueDelta.raw<-5){
      items.push({
        severity:"critical",
        title:"Выручка ниже прошлого периода",
        text:`Отставание ${Math.abs(revenueDelta.raw).toFixed(1)}%.`,
        tag:"Продажи",
      });
    }

    if(averageDelta.raw!==null&&averageDelta.raw<-5){
      items.push({
        severity:"warning",
        title:"Средний чек снизился",
        text:`Снижение ${Math.abs(averageDelta.raw).toFixed(1)}%. Проверьте допродажи напитков, гарниров и комбо.`,
        tag:"Маркетинг",
      });
    }

    const classC=menu?.abc?.C?.count??menu?.class_c_count;
    if(Number(classC)>0){
      items.push({
        severity:"warning",
        title:`${classC} позиций класса C`,
        text:"Слабые позиции требуют пересмотра или объединения в комбо.",
        tag:"Меню",
      });
    }
  }

  if(!items.length){
    items.push({
      severity:"ok",
      title:"Критических проблем нет",
      text:"Основные показатели находятся в нормальном диапазоне.",
      tag:"Всё хорошо",
    });
  }

  setHtml("attention",
    items.slice(0,5).map(x=>
      `<article class="issue ${x.severity}">
        <div class="rail"></div>
        <div class="issue__body">
          <b>${x.title}</b>
          <p>${x.text}</p>
        </div>
        <span class="issue__tag">${x.tag}</span>
      </article>`
    ).join(""));
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
        text:"Количество чеков снижается сильнее среднего чека. Запустите акцию на лидера продаж в слабые часы и вынесите комбо в закреплённое меню.",
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

  setHtml("recommendations",
    items.slice(0,4).map(x=>
      `<article class="recommendation"><b>${x.title}</b><p>${x.text}</p></article>`
    ).join(""));
}

function renderLeaders(items){
  const sorted=[...items]
    .sort((a,b)=>itemRevenue(b)-itemRevenue(a))
    .slice(0,5);

  const totalRevenue=sorted.reduce(
    (sum,item)=>sum+itemRevenue(item),
    0
  );

  setHtml("leaders",
    sorted.length
      ?sorted.map((item,index)=>{
        const quantity=itemQuantity(item);
        const revenue=itemRevenue(item);
        const unitPrice=leaderUnitPrice(item);
        const share=percentOf(revenue,totalRevenue);

        return `<div class="leader-row">
          <span class="leader-row__share" style="width:${Math.min(100,share)}%"></span>
          <div class="leader-row__content">
            <span class="leader-row__rank">${index+1}</span>
            <span class="leader-row__name">${itemName(item)}</span>
            <span class="leader-row__meta">
              <b>${money(revenue)}</b>
              <span class="leader-row__details">
                ${quantity?`<span>${integer(quantity)} продаж</span>`:""}
                ${unitPrice?`<span>${money(unitPrice)} / шт.</span>`:""}
                <span>${share.toFixed(1)}%</span>
              </span>
            </span>
          </div>
        </div>`;
      }).join("")
      :'<div class="empty">Нет данных о составе продаж за период</div>'
  );
}

function hourlyRowsFromSnapshot(snapshot){
  const hourly=snapshot?.hourly;
  if(!hourly) return [];

  if(Array.isArray(hourly)){
    return rowsToObjects(hourly);
  }

  if(Array.isArray(hourly?.rows)&&Array.isArray(hourly?.columns)){
    return hourly.rows.map(row=>
      Object.fromEntries(
        hourly.columns.map((column,index)=>[column,row[index]])
      )
    );
  }

  return [];
}

function renderChart(historyRows,latest,periodName=period){
  let labels=[];
  let values=[];
  let cumulative=0;

  const history=rowsToObjects(historyRows);
  let hourly=[];

  if(periodName==="today"){
    hourly=hourlyRowsFromSnapshot(latest);
  }else if(periodName==="yesterday"&&history.length){
    hourly=hourlyRowsFromSnapshot(history[0]);
  }

  if((periodName==="today"||periodName==="yesterday")&&hourly.length){
    hourly
      .sort((a,b)=>Number(a.hour??a.sale_hour??0)-Number(b.hour??b.sale_hour??0))
      .forEach(item=>{
        cumulative+=Number(
          item.revenue??item.sum??item.amount??item.sales??0
        );
        const hour=Number(item.hour??item.sale_hour??0);
        labels.push(Number.isFinite(hour)?`${String(hour).padStart(2,"0")}:00`:String(item.hour??item.sale_hour??""));
        values.push(cumulative);
      });
  }else{
    history
      .sort((a,b)=>String(a.business_date||a.date||"").localeCompare(String(b.business_date||b.date||"")))
      .forEach(item=>{
        cumulative+=Number(item.revenue||item.sum||item.amount||0);
        labels.push(item.business_date||item.date||item.day||"");
        values.push(cumulative);
      });
  }

  const chartNode=byId("sales-chart");
  if(!chartNode) return;

  if(!labels.length||!values.some(value=>value>0)){
    chartNode.innerHTML='<div class="chart-empty">Недостаточно данных для графика выбранного периода</div>';
    return;
  }

  if(typeof echarts==="undefined"){
    chartNode.innerHTML='<div class="chart-empty">Библиотека графиков не загрузилась</div>';
    return;
  }

  chartNode.innerHTML="";
  const existing=echarts.getInstanceByDom(chartNode);
  if(existing) existing.dispose();

  const chart=echarts.init(chartNode);
  chart.setOption({
    grid:{left:56,right:18,top:18,bottom:34},
    tooltip:{trigger:"axis",valueFormatter:value=>money(value)},
    xAxis:{type:"category",boundaryGap:false,data:labels},
    yAxis:{type:"value",axisLabel:{formatter:value=>integer(value)}},
    series:[{
      name:"Накопительная выручка",
      type:"line",
      smooth:true,
      symbol:"circle",
      symbolSize:6,
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
  setText("hero-text",error?.message||String(error));
});
