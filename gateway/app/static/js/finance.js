const byId=id=>document.getElementById(id);
let agent="gastrodom3";
let period="month";
let currentOperations=[];
let chart=null;

const expenseCategories=[
 "Продукты и закупки","ФОТ","Аренда","Коммунальные","Налоги",
 "Эквайринг","Доставка","Реклама","Ремонт и обслуживание","Прочее"
];
const incomeCategories=["Прочий доход","Возврат поставщика","Компенсация","Прочее"];

const money=value=>new Intl.NumberFormat("ru-RU",{maximumFractionDigits:0}).format(Number(value||0))+" ₽";
const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;

function rangeFor(name){
 const now=new Date(),from=new Date(now),to=new Date(now);
 if(name==="yesterday"){from.setDate(from.getDate()-1);to.setDate(to.getDate()-1)}
 if(name==="week")from.setDate(from.getDate()-6);
 if(name==="month")from.setDate(1);
 if(name==="prevmonth"){from.setMonth(from.getMonth()-1,1);to.setDate(0)}
 return {from:iso(from),to:iso(to)};
}

async function api(url,options){
 const response=await fetch(url,options);
 if(!response.ok){
  let detail=`HTTP ${response.status}`;
  try{const body=await response.json();detail=body.detail||detail}catch{}
  throw new Error(detail);
 }
 return response.status===204?null:response.json();
}

function setText(id,value){const node=byId(id);if(node)node.textContent=value}

function activatePeriod(){
 document.querySelectorAll("#finance-periods [data-period]").forEach(button=>
  button.classList.toggle("is-active",button.dataset.period===period)
 );
}

function periodLabel(){
 return {today:"Сегодня",yesterday:"Вчера",week:"Последние 7 дней",month:"Этот месяц",prevmonth:"Прошлый месяц"}[period]||"Период";
}

function renderSummary(data){
 setText("finance-revenue",money(data.revenue));
 setText("finance-expenses",money(data.expenses));
 setText(
  "finance-expense-breakdown",
  `накладные ${money(data.purchase_expenses||0)} · ручные ${money(data.manual_expenses||0)}`
 );
 setText("finance-income",money(data.manual_income));
 setText("finance-result",money(data.operating_result));
 setText("finance-margin",data.operating_margin===null?"Рентабельность —":`Рентабельность ${data.operating_margin.toFixed(1)}%`);
 const resultNode=byId("finance-result");
 resultNode.className=data.operating_result>=0?"positive":"negative";
 setText("finance-range-label",`${data.date_from} — ${data.date_to}`);

 const resultWord=data.operating_result>=0?"положительный":"отрицательный";
 setText("finance-hero-title",`${periodLabel()}: результат ${money(data.operating_result)}`);
 setText("finance-hero-text",`Выручка ${money(data.revenue)}, расходы ${money(data.expenses)}. Операционный результат ${resultWord}.`);

 currentOperations=data.operations||[];
 renderOperations(currentOperations);
 renderCategories(data.categories||[]);
 renderPayments(data.payments||{},data.revenue||0);
 renderPurchases(data.purchases||{});
 renderInsights(data);
 renderChart(data.daily||[]);
}

function renderOperations(items){
 const body=byId("finance-operations");
 if(!items.length){
  body.innerHTML='<tr><td colspan="6" class="finance-empty">За выбранный период ручных финансовых операций нет</td></tr>';
  return;
 }
 body.innerHTML=items.map(item=>`
  <tr>
   <td>${item.operation_date}</td>
   <td>${item.operation_type==="expense"?"Расход":"Прочий доход"}</td>
   <td>${item.category}</td>
   <td>${item.description||"—"}</td>
   <td class="amount ${item.operation_type}">${item.operation_type==="expense"?"−":"+"}${money(item.amount)}</td>
   <td>
    <button data-edit="${item.id}">Изменить</button>
    <button data-delete="${item.id}">Удалить</button>
   </td>
  </tr>`).join("");

 body.querySelectorAll("[data-edit]").forEach(button=>button.onclick=()=>openEdit(Number(button.dataset.edit)));
 body.querySelectorAll("[data-delete]").forEach(button=>button.onclick=()=>deleteOperation(Number(button.dataset.delete)));
}

function renderCategories(items){
 const node=byId("expense-categories");
 if(!items.length){
  node.innerHTML='<div class="finance-empty">Расходов за период пока нет</div>';
  return;
 }
 const total=items.reduce((s,x)=>s+Number(x.amount||0),0);
 node.innerHTML=items.map(item=>{
  const share=total?item.amount/total*100:0;
  return `<div class="expense-row"><div><strong>${item.category}</strong><br><small>${share.toFixed(1)}% расходов</small></div><strong>${money(item.amount)}</strong></div>`;
 }).join("");
}

function renderPayments(payments,revenue){
 const node=byId("payment-types");
 const items=payments.items||[];
 const order=["cash","card","qr","transfer","staff_meal","owners","bonus","other"];
 const icons={
  cash:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18v12H3V6Zm2 2v8h14V8H5Zm7 1.5A3.5 3.5 0 1 1 12 16a3.5 3.5 0 0 1 0-7Zm0 2a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3ZM6 9h2v2H6V9Zm10 4h2v2h-2v-2Z"/></svg>`,
  card:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h18a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Zm0 2v2h18V7H3Zm0 5v5h18v-5H3Zm13 2h4v2h-4v-2Z"/></svg>`,
  qr:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3h7v7H3V3Zm2 2v3h3V5H5Zm9-2h7v7h-7V3Zm2 2v3h3V5h-3ZM3 14h7v7H3v-7Zm2 2v3h3v-3H5Zm9-2h3v3h-3v-3Zm4 0h3v2h-1v2h-2v-4Zm-4 4h2v3h-2v-3Zm3 1h2v2h-2v-2Zm3-1h1v3h-1v-3Z"/></svg>`,
  transfer:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 3 3.7 10.2c-.8.34-.75 1.5.08 1.76l6.4 2.05L12.22 20c.27.8 1.35.91 1.78.18L21.8 4.4A1 1 0 0 0 21 3Zm-8.2 13.7-1.15-3.37 5.94-5.94-7.1 4.43-3.54-1.13 11.58-4.83-5.73 10.84Z"/></svg>`,
  bonus:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 7h-2.2A3 3 0 0 0 12 5.8 3 3 0 0 0 6.2 7H4a2 2 0 0 0-2 2v3h9V9h2v3h9V9a2 2 0 0 0-2-2ZM9 7a1 1 0 1 1 1-1v1H9Zm5 0V6a1 1 0 1 1 1 1h-1ZM2 14h9v7H4a2 2 0 0 1-2-2v-5Zm11 0h9v5a2 2 0 0 1-2 2h-7v-7Z"/></svg>`,
  staff_meal:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 2h2v7a3 3 0 0 1-2 2.82V22H5V11.82A3 3 0 0 1 3 9V2h2v5h2V2Zm10 0h2v20h-2v-8h-3a2 2 0 0 1-2-2V7a5 5 0 0 1 5-5Zm0 2.18A3 3 0 0 0 14 7v5h3V4.18Z"/></svg>`,
  owners:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0-2a3 3 0 1 1 0-6 3 3 0 0 1 0 6Zm0 4c-5 0-9 2.5-9 6v2h18v-2c0-3.5-4-6-9-6Zm-6.7 6c.55-2.05 3.35-4 6.7-4s6.15 1.95 6.7 4H5.3Z"/></svg>`,
  other:`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6Zm7 0a3 3 0 1 1 0 6 3 3 0 0 1 0-6Zm7 0a3 3 0 1 1 0 6 3 3 0 0 1 0-6Z"/></svg>`
 };
 const byKey=Object.fromEntries(items.map(item=>[item.key,item]));

 const visible=order
  .map(key=>byKey[key])
  .filter(Boolean);

 if(!visible.length){
  node.innerHTML='<div class="finance-empty">Данные по типам оплат ещё не получены. Данные оплат пока не сохранены на Gateway. Проверьте диагностику сохранения.</div>';
 }else{
  node.innerHTML=visible.map(item=>`
   <article class="payment-card">
    <div class="payment-card-icon payment-card-icon--${item.key}">${icons[item.key]||icons.other}</div>
    <div class="payment-card-body">
     <span>${item.name}</span>
     <strong>${money(item.amount)}</strong>
     <small>${Number(item.share||0).toFixed(1)}% оплат · ${Number(item.checks_count||0)} чек.</small>
    </div>
   </article>`).join("");
 }

 const total=Number(payments.total||0);
 const diff=Number(payments.difference_to_revenue||0);
 setText("payment-total",money(total));
 setText("payment-revenue",money(revenue));
 setText("payment-difference",(diff>0?"+":"")+money(diff));

 const reconcile=byId("payment-reconcile");
 const days=Number(payments.days_with_payment_data||0);
 const periodDays=Number(payments.days_in_period||0);

 if(!days){
  reconcile.textContent="Нет данных оплат";
  reconcile.className="payment-reconcile warning";
 }else if(Math.abs(diff)<=1){
  reconcile.textContent="✓ Оплаты сходятся с выручкой";
  reconcile.className="payment-reconcile ok";
 }else{
  reconcile.textContent=`Расхождение ${diff>0?"+":""}${money(diff)}`;
  reconcile.className="payment-reconcile warning";
 }

 if(days&&periodDays&&days<periodDays){
  reconcile.textContent+=` · данные ${days}/${periodDays} дн.`;
 }
}


function renderPurchases(purchases){
 setText("purchases-total",money(purchases.total||0));
 setText("purchases-documents",String(purchases.documents_count||0));
 setText("purchases-vat",money(purchases.vat_total||0));

 const top=(purchases.suppliers||[])[0];
 setText(
  "purchases-top-supplier",
  top?`${top.supplier} · ${money(top.amount)}`:"—"
 );

 const node=byId("purchases-list");
 const documents=purchases.documents||[];
 if(!documents.length){
  node.innerHTML='<div class="finance-empty">За выбранный период проведённых приходных накладных нет</div>';
  return;
 }

 node.innerHTML=documents.slice(0,12).map(item=>`
  <div class="purchase-row">
   <div>
    <strong>${item.document_name||"Приходная накладная"}</strong>
    <small>${item.document_date||"—"} · ${item.supplier_name||"Поставщик не указан"} · ${Number(item.items_count||0)} поз.</small>
   </div>
   <strong>${money(item.amount||0)}</strong>
  </div>`).join("");
}


function renderInsights(data){
 const items=[];
 if(data.expenses===0)items.push(["Добавьте расходы","Сейчас операционный результат равен почти всей выручке, потому что расходы ещё не внесены."]);
 else{
  const expenseShare=data.revenue?data.expenses/data.revenue*100:null;
  if(expenseShare!==null)items.push(["Доля учтённых расходов",`${expenseShare.toFixed(1)}% от выручки за выбранный период.`]);
  if(data.operating_result<0)items.push(["Отрицательный результат","Учтённые расходы и прочие операции превышают выручку. Проверьте крупнейшие категории."]);
  else items.push(["Положительный результат",`После учтённых расходов остаётся ${money(data.operating_result)}.`]);
 }
 items.push(["Себестоимость не учтена","Операционный результат пока не является чистой прибылью: фактический Food Cost ещё не подключён."]);
 byId("finance-insights").innerHTML=items.map(([title,text])=>`<div class="finance-insight"><strong>${title}</strong><p>${text}</p></div>`).join("");
}

function renderChart(rows){
 const node=byId("finance-chart");
 if(typeof echarts==="undefined"){node.innerHTML='<div class="finance-empty">График недоступен</div>';return}
 if(chart)chart.dispose();
 chart=echarts.init(node);
 const labels=rows.map(x=>x.date);
 chart.setOption({
  tooltip:{trigger:"axis"},
  legend:{data:["Выручка","Расходы","Прочие доходы"]},
  grid:{left:58,right:22,top:45,bottom:35},
  xAxis:{type:"category",data:labels},
  yAxis:{type:"value"},
  series:[
   {name:"Выручка",type:"line",smooth:true,data:rows.map(x=>x.revenue)},
   {name:"Расходы",type:"bar",data:rows.map(x=>x.expenses)},
   {name:"Прочие доходы",type:"bar",data:rows.map(x=>x.income)}
  ]
 },true);
}

async function recoverPayments(){
 const button=byId("recover-payments-button");
 button.disabled=true;
 const previous=button.textContent;
 button.textContent="Восстанавливаю…";

 try{
  const result=await api(
   `/api/web/${agent}/finance/payments/recover`,
   {method:"POST"}
  );
  button.textContent=`Восстановлено: ${Number(result.recovered||0)}`;
  await loadFinance();
 }catch(error){
  button.textContent="Ошибка восстановления";
  alert(error.message);
 }finally{
  setTimeout(()=>{
   button.disabled=false;
   button.textContent=previous;
  },2500);
 }
}


async function loadPaymentDiagnostics(range){
 try{
  const data=await api(
   `/api/web/${agent}/finance/payments/diagnostics?date_from=${range.from}&date_to=${range.to}`
  );
  const node=byId("payment-diagnostics-status");
  const saved=Number(data.days_with_payments||0);
  const payload=Number(data.days_with_payload_payments||0);
  const total=Number(data.days_count||0);

  if(saved>0){
   node.textContent=`Gateway: оплаты сохранены ${saved}/${total} дн.`;
   node.className="payment-diagnostics-status ok";
  }else if(payload>0){
   node.textContent=`Gateway: оплаты есть в payload ${payload}/${total} дн.`;
   node.className="payment-diagnostics-status warning";
  }else{
   node.textContent=`Gateway: оплат нет в ${total} снимках`;
   node.className="payment-diagnostics-status warning";
  }
 }catch(error){
  const node=byId("payment-diagnostics-status");
  node.textContent="Диагностика Gateway недоступна";
  node.className="payment-diagnostics-status warning";
 }
}


async function loadFinance(){
 const range=rangeFor(period);
 setText("finance-hero-title","Загружаю финансы…");
 const data=await api(`/api/web/${agent}/finance/summary?date_from=${range.from}&date_to=${range.to}`);
 renderSummary(data);
 await loadPaymentDiagnostics(range);
}

function fillCategories(type,value=""){
 const select=byId("operation-category");
 const values=type==="expense"?expenseCategories:incomeCategories;
 select.innerHTML=values.map(x=>`<option value="${x}">${x}</option>`).join("");
 if(value&&!values.includes(value))select.insertAdjacentHTML("beforeend",`<option value="${value}">${value}</option>`);
 if(value)select.value=value;
}

function openModal(item=null){
 const modal=byId("finance-modal");
 modal.hidden=false;
 byId("finance-modal-title").textContent=item?"Изменить операцию":"Добавить операцию";
 byId("operation-id").value=item?.id||"";
 byId("operation-date").value=item?.operation_date||iso(new Date());
 byId("operation-type").value=item?.operation_type||"expense";
 fillCategories(byId("operation-type").value,item?.category||"");
 byId("operation-amount").value=item?.amount||"";
 byId("operation-description").value=item?.description||"";
}
function closeModal(){byId("finance-modal").hidden=true}
function openEdit(id){const item=currentOperations.find(x=>Number(x.id)===id);if(item)openModal(item)}

async function deleteOperation(id){
 if(!confirm("Удалить финансовую операцию?"))return;
 await api(`/api/web/${agent}/finance/operations/${id}`,{method:"DELETE"});
 await loadFinance();
}

async function saveOperation(event){
 event.preventDefault();
 const id=byId("operation-id").value;
 const payload={
  operation_date:byId("operation-date").value,
  operation_type:byId("operation-type").value,
  category:byId("operation-category").value,
  amount:Number(byId("operation-amount").value),
  description:byId("operation-description").value.trim()
 };
 await api(`/api/web/${agent}/finance/operations${id?"/"+id:""}`,{
  method:id?"PUT":"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify(payload)
 });
 closeModal();
 await loadFinance();
}

async function initialize(){
 const agents=(await api("/api/web/agents").catch(()=>[])).filter(x=>String(x.agent_id||"").trim());
 const select=byId("finance-agent-select");
 const preferred=agents.find(x=>x.agent_id==="gastrodom3")||agents[0]||{agent_id:"gastrodom3",name:"Gastrodom 3"};
 select.innerHTML=(agents.length?agents:[preferred]).map(x=>`<option value="${x.agent_id}">${x.name||x.agent_id}</option>`).join("");
 agent=preferred.agent_id;
 select.value=agent;
 select.onchange=()=>{agent=select.value;loadFinance()};

 document.querySelectorAll("#finance-periods [data-period]").forEach(button=>button.onclick=()=>{
  period=button.dataset.period;activatePeriod();loadFinance();
 });
 byId("add-operation-button").onclick=()=>openModal();
 byId("add-operation-button-secondary").onclick=()=>openModal();
 byId("recover-payments-button").onclick=recoverPayments;
 byId("finance-modal-close").onclick=closeModal;
 byId("finance-cancel").onclick=closeModal;
 byId("operation-type").onchange=()=>fillCategories(byId("operation-type").value);
 byId("finance-form").onsubmit=saveOperation;
 activatePeriod();
 await loadFinance();
}

initialize().catch(error=>{
 setText("finance-hero-title","Не удалось загрузить финансы");
 setText("finance-hero-text",error.message);
});
