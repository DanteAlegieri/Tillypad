const select=document.getElementById("settings-agent-select");
const form=document.getElementById("settings-form");
const input=document.getElementById("daily-revenue-plan");
const preview=document.getElementById("plan-preview");
const statusNode=document.getElementById("settings-status");
const saveButton=document.getElementById("save-settings");

let currentAgent="gastrodom3";

const money=value=>new Intl.NumberFormat(
  "ru-RU",
  {maximumFractionDigits:0}
).format(Number(value||0))+" ₽";

function setStatus(text,state=""){
  statusNode.textContent=text;
  statusNode.className=`settings-status ${state}`.trim();
}

function updatePreview(){
  preview.textContent=money(input.value);
}

async function api(url,options={}){
  const response=await fetch(url,{
    headers:{
      "Content-Type":"application/json",
      ...(options.headers||{}),
    },
    ...options,
  });
  if(!response.ok){
    throw new Error(await response.text());
  }
  return response.json();
}

async function loadSettings(){
  setStatus("Загрузка…");
  const data=await api(`/api/web/${currentAgent}/settings`);
  input.value=Number(data.daily_revenue_plan||0);
  updatePreview();
  setStatus("Настройки загружены");
}

async function initialize(){
  const agents=await api("/api/web/agents");
  select.innerHTML=agents.map(item=>
    `<option value="${item.agent_id}">${item.name||item.agent_id}</option>`
  ).join("");

  currentAgent=agents?.[0]?.agent_id||"gastrodom3";
  select.value=currentAgent;
  select.onchange=async()=>{
    currentAgent=select.value;
    await loadSettings();
  };

  input.addEventListener("input",updatePreview);

  form.addEventListener("submit",async event=>{
    event.preventDefault();

    const value=Number(input.value);
    if(!Number.isFinite(value)||value<0){
      setStatus("Проверьте значение плана","error");
      return;
    }

    saveButton.disabled=true;
    setStatus("Сохраняю…");

    try{
      const saved=await api(
        `/api/web/${currentAgent}/settings`,
        {
          method:"PUT",
          body:JSON.stringify({
            daily_revenue_plan:value,
          }),
        }
      );
      input.value=Number(saved.daily_revenue_plan||0);
      updatePreview();
      setStatus("Сохранено","saved");
    }catch(error){
      console.error(error);
      setStatus("Ошибка сохранения","error");
    }finally{
      saveButton.disabled=false;
    }
  });

  await loadSettings();
}

initialize().catch(error=>{
  console.error(error);
  setStatus("Не удалось загрузить настройки","error");
});
