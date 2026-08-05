export function activatePeriodButton(period){
  document.querySelectorAll("[data-period]").forEach(button=>{
    button.classList.toggle(
      "is-active",
      button.dataset.period===period
    );
  });
}

export function setPeriodInUrl(period){
  const url=new URL(window.location.href);
  url.searchParams.set("period",period);
  window.history.replaceState({period},"",url);
}
