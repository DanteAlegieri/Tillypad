// Compatibility entry point for Restaurant OS 9.1.0.
import("/static/js/dashboard/init.js?v=9.1.0").catch(error=>{
  console.error("Dashboard module load failed",error);
  const title=document.getElementById("hero-title");
  const text=document.getElementById("hero-text");
  if(title) title.textContent="Не удалось загрузить модули рабочего стола";
  if(text) text.textContent=error?.message||String(error);
});
