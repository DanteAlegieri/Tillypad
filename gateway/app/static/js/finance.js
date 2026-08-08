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

async function loadFinance(){
 const range=rangeFor(period);
 setText("finance-hero-title","Загружаю финансы…");
 const data=await api(`/api/web/${agent}/finance/summary?date_from=${range.from}&date_to=${range.to}`);
 renderSummary(data);
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
