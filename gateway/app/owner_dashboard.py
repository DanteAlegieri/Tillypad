from __future__ import annotations

from datetime import date, timedelta
from html import escape

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .config import settings
from .storage import GatewayStorage
from .connections import ConnectionManager
from .ai import build_director_report
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
<title>Restaurant OS — цифровые помощники</title>
<style>
:root{
 --bg:#f3efe9;--card:#fff;--text:#211915;--muted:#786c65;--line:#ded4cc;
 --red:#ad3024;--red2:#cf6b3b;--green:#407b5d;--amber:#cf8527;--blue:#347c98;
 --dark:#2d201a;--dark2:#3a2b24;--soft:#f8f5f2;--sidebar:#2f211b
}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);font-family:Segoe UI,Arial,sans-serif}
body{display:grid;grid-template-columns:300px 1fr}
.sidebar{
 min-height:100vh;background:var(--sidebar);color:#fff;padding:24px 18px;position:sticky;top:0;
 height:100vh;overflow:auto
}
.brand{display:flex;align-items:center;gap:13px;padding:4px 8px 22px;border-bottom:1px solid #4d3a31}
.logo{width:48px;height:48px;border-radius:15px;background:var(--red);display:grid;place-items:center;font-size:20px;font-weight:900}
.brand strong{font-size:20px;display:block}.brand small{color:#cbbdb5;display:block;margin-top:2px}
.nav-section{margin-top:22px}
.nav-title{font-size:11px;color:#a9988f;letter-spacing:.16em;font-weight:800;padding:0 10px 8px}
.nav-item{
 width:100%;display:grid;grid-template-columns:40px 1fr;gap:10px;align-items:center;
 border:0;background:transparent;color:#e8ddd7;padding:11px 10px;border-radius:13px;text-align:left;cursor:pointer
}
.nav-item:hover{background:#3c2c25}
.nav-item.active{background:#49342b;color:#fff}
.nav-icon{width:36px;height:36px;border-radius:11px;background:#4a382f;display:grid;place-items:center;font-size:18px}
.nav-item.active .nav-icon{background:var(--red)}
.nav-name{font-weight:800;font-size:15px}
.nav-desc{font-size:11px;color:#bcaea6;margin-top:2px}
.sidebar-footer{margin-top:24px;border-top:1px solid #4d3a31;padding:18px 8px 0}
.sidebar-footer a{color:#fff;text-decoration:none;font-size:14px}
.main{min-width:0}
.topbar{
 background:#fff;border-bottom:1px solid var(--line);padding:14px 24px;display:flex;align-items:center;
 justify-content:space-between;gap:16px;position:sticky;top:0;z-index:15
}
.assistant-title{display:flex;align-items:center;gap:12px}
.assistant-avatar{width:42px;height:42px;border-radius:13px;background:#e8f1f4;color:var(--blue);display:grid;place-items:center;font-weight:900}
.assistant-title strong{font-size:18px;display:block}.assistant-title small{color:var(--muted)}
.top-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
select,input,button{
 border:1px solid var(--line);border-radius:11px;padding:10px 12px;background:#fff;font-weight:700;font-size:14px
}
button{cursor:pointer}
button.primary{background:var(--red);color:#fff;border-color:var(--red)}
.quick.active{background:var(--dark);color:#fff;border-color:var(--dark)}
.content{padding:24px;max-width:1540px;margin:auto}
.hero{display:grid;grid-template-columns:1fr 310px;gap:16px;margin-bottom:16px}
.hero-main{
 background:linear-gradient(135deg,#fff 0%,#fbf7f3 100%);border:1px solid var(--line);
 border-radius:24px;padding:26px;box-shadow:0 10px 30px rgba(45,30,20,.05)
}
.kicker{color:var(--red);font-weight:850;letter-spacing:.12em;font-size:13px}
h1{font-size:42px;margin:7px 0 8px}
.sub{font-size:18px;color:var(--muted);line-height:1.5}
.hero-side{background:#eaf2f5;border-radius:24px;padding:24px;border:1px solid #d6e4e9}
.health-number{font-size:62px;font-weight:900;color:var(--blue);line-height:1}
.health-label{color:var(--muted);margin-top:6px}
.statusbar{display:flex;gap:10px;align-items:center;margin:12px 0 0;color:var(--muted)}
.dot{width:10px;height:10px;border-radius:50%;background:var(--amber)}
.dot.online{background:var(--green)}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px}
.card{background:#fff;border:1px solid var(--line);border-radius:20px;padding:20px;box-shadow:0 8px 28px rgba(45,30,20,.04)}
.metric-card{grid-column:span 3}
.metric-card h2{font-size:14px;color:var(--muted);font-weight:500;margin:0 0 12px}
.metric{font-size:34px;font-weight:800;line-height:1.1}
.note{color:var(--muted);margin-top:8px;font-size:14px}
.delta{margin-top:10px;font-size:14px;font-weight:800}
.delta.up{color:var(--green)}.delta.down{color:var(--red)}.delta.flat{color:var(--muted)}
.span-8{grid-column:span 8}.span-4{grid-column:span 4}.span-6{grid-column:span 6}.full{grid-column:1/-1}
.section-title{font-size:27px;font-weight:800;margin:0 0 16px}
.workspace{display:none}.workspace.active{display:block}
.action-list{display:grid;gap:12px}
.action-card{display:grid;grid-template-columns:auto 1fr auto;gap:14px;align-items:start;border:1px solid var(--line);border-radius:16px;padding:16px}
.action-priority{padding:6px 10px;border-radius:9px;background:#fde8e5;color:var(--red);font-weight:800;font-size:12px}
.action-card strong{font-size:19px;display:block;margin-bottom:5px}
.action-card p{margin:0;color:var(--muted);line-height:1.45}
.action-score{font-size:24px;font-weight:900}
.assistant-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.assistant-card{background:#fff;border:1px solid var(--line);border-radius:20px;padding:20px;cursor:pointer}
.assistant-card:hover{transform:translateY(-2px);box-shadow:0 10px 28px rgba(45,30,20,.08)}
.assistant-card .avatar{width:48px;height:48px;border-radius:14px;display:grid;place-items:center;font-size:22px;margin-bottom:14px;background:#f0e8e2}
.assistant-card h3{margin:0 0 7px;font-size:20px}.assistant-card p{margin:0;color:var(--muted);line-height:1.45}
.chart{height:310px;display:flex;align-items:end;gap:7px;border-bottom:1px solid var(--line);padding:20px 6px 0;overflow-x:auto}
.bar-wrap{flex:1;min-width:24px;height:100%;display:flex;flex-direction:column;justify-content:end;align-items:center;gap:6px}
.bar{width:100%;max-width:48px;background:linear-gradient(to top,var(--red),var(--red2));border-radius:8px 8px 2px 2px;min-height:2px}
.bar.secondary{background:linear-gradient(to top,var(--amber),#efbc6a)}
.bar-label{font-size:11px;color:var(--muted);white-space:nowrap}
.line-chart{position:relative;height:310px;padding:20px 8px 30px}
svg{width:100%;height:100%;overflow:visible}
.axis-label{font-size:11px;fill:var(--muted)}
.line{fill:none;stroke:var(--red);stroke-width:3}.line2{fill:none;stroke:var(--amber);stroke-width:3}
.point{fill:var(--red)}.point2{fill:var(--amber)}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;color:var(--muted);font-size:13px}
.legend span::before{content:"";display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;background:var(--red)}
.legend span.avg::before{background:var(--amber)}
.insights{display:grid;gap:12px}
.insight{padding:15px;border:1px solid var(--line);border-radius:14px;background:var(--soft)}
.insight strong{display:block;font-size:18px;margin-bottom:5px}.insight small{color:var(--muted)}
.history{width:100%;border-collapse:collapse}
.history th,.history td{text-align:left;padding:13px 8px;border-bottom:1px solid var(--line)}
.history th{color:var(--muted);font-size:13px}
.empty{padding:40px;text-align:center;color:var(--muted)}
.badge{display:inline-flex;align-items:center;padding:6px 9px;border-radius:9px;background:#edf5ef;color:var(--green);font-weight:800;font-size:12px}
.health-breakdown{display:grid;gap:10px;margin-top:18px}
.health-factor{border:1px solid var(--line);border-radius:14px;padding:14px;background:#fff}
.health-factor-head{display:flex;justify-content:space-between;gap:12px;align-items:center}
.health-factor-title{font-weight:800}
.health-factor-score{font-weight:900}
.health-factor-note{font-size:13px;color:var(--muted);margin-top:7px}
.health-progress{height:8px;border-radius:999px;background:#eee7e1;overflow:hidden;margin-top:10px}
.health-progress>span{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--red),var(--amber),var(--green))}
.health-change{font-size:15px;font-weight:800;margin-top:10px}
.health-change.up{color:var(--green)}
.health-change.down{color:var(--red)}
.health-change.flat{color:var(--muted)}
.health-mini-chart{height:150px;display:flex;align-items:end;gap:8px;padding-top:16px}
.health-mini-bar{flex:1;min-width:14px;border-radius:8px 8px 2px 2px;background:linear-gradient(to top,var(--blue),#7db5c9);position:relative}
.health-mini-bar span{position:absolute;bottom:-22px;left:50%;transform:translateX(-50%);font-size:10px;color:var(--muted);white-space:nowrap}

@media(max-width:1180px){
 body{grid-template-columns:240px 1fr}.sidebar{padding:18px 12px}
 .metric-card{grid-column:span 6}.span-8,.span-4,.span-6{grid-column:span 12}
 .assistant-grid{grid-template-columns:1fr 1fr}
}
@media(max-width:760px){
 body{display:block}.sidebar{position:relative;width:100%;height:auto;min-height:0}
 .nav-section{display:grid;grid-template-columns:1fr 1fr;gap:6px}
 .nav-title{grid-column:1/-1}.main{width:100%}.topbar{position:relative;padding:12px}
 .top-actions{display:none}.content{padding:14px}.hero{grid-template-columns:1fr}
 h1{font-size:32px}.metric-card{grid-column:span 12}.assistant-grid{grid-template-columns:1fr}
 .chart,.line-chart{height:245px}
}
</style>
</head>
<body>
<aside class="sidebar">
 <div class="brand">
  <div class="logo">ГЗ</div>
  <div><strong>Restaurant OS</strong><small>Цифровая команда ресторана</small></div>
 </div>

 <div class="nav-section">
  <div class="nav-title">УПРАВЛЕНИЕ</div>
  <button class="nav-item active" data-workspace="manager">
   <div class="nav-icon">◎</div><div><div class="nav-name">Цифровой управляющий</div><div class="nav-desc">Главная картина бизнеса</div></div>
  </button>
  <button class="nav-item" data-workspace="operations">
   <div class="nav-icon">⌂</div><div><div class="nav-name">Операционный центр</div><div class="nav-desc">Ресторан прямо сейчас</div></div>
  </button>
  <button class="nav-item" data-workspace="decisions">
   <div class="nav-icon">◆</div><div><div class="nav-name">Центр решений</div><div class="nav-desc">Что нужно сделать</div></div>
  </button>
 </div>

 <div class="nav-section">
  <div class="nav-title">ЦИФРОВЫЕ ПОМОЩНИКИ</div>
  <button class="nav-item" data-workspace="marketer">
   <div class="nav-icon">↗</div><div><div class="nav-name">Цифровой маркетолог</div><div class="nav-desc">Рост среднего чека</div></div>
  </button>
  <button class="nav-item" data-workspace="technologist">
   <div class="nav-icon">◉</div><div><div class="nav-name">Цифровой технолог</div><div class="nav-desc">Меню и стабильность спроса</div></div>
  </button>
  <button class="nav-item" data-workspace="finance">
   <div class="nav-icon">₽</div><div><div class="nav-name">Финансовый директор</div><div class="nav-desc">Выручка и экономика</div></div>
  </button>
  <button class="nav-item" data-workspace="delivery">
   <div class="nav-icon">→</div><div><div class="nav-name">Доставка</div><div class="nav-desc">Каналы и допродажи</div></div>
  </button>
  <button class="nav-item" data-workspace="analyst">
   <div class="nav-icon">◇</div><div><div class="nav-name">Бизнес-аналитик</div><div class="nav-desc">Графики и детализация</div></div>
  </button>
 </div>

 <div class="sidebar-footer"><a href="/logout">Выйти из системы</a></div>
</aside>

<section class="main">
 <div class="topbar">
  <div class="assistant-title">
   <div class="assistant-avatar" id="assistant-avatar">◎</div>
   <div><strong id="assistant-name">Цифровой управляющий</strong><small id="assistant-desc">Главная картина бизнеса</small></div>
  </div>
  <div class="top-actions">
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

 <div class="content">
  <div class="workspace active" id="workspace-manager">
   <div class="hero">
    <div class="hero-main">
     <div class="kicker">ЦИФРОВОЙ УПРАВЛЯЮЩИЙ</div>
     <h1 id="greeting">Добрый день, Андрей</h1>
     <div class="sub" id="manager-summary">Система анализирует фактические данные ресторана и формирует управленческий вывод.</div>
     <div class="statusbar"><span class="dot" id="status-dot"></span><span id="status-text">Загрузка статуса...</span></div>
    </div>
    <div class="hero-side">
     <div class="kicker" style="color:var(--blue)">ИНДЕКС РЕСТОРАНА</div>
     <div class="health-number" id="health-index">—</div>
     <div class="health-label" id="health-label">Ожидание данных</div>
    </div>
   </div>

   <div class="grid">
    <article class="card metric-card"><h2>Выручка за период</h2><div class="metric" id="revenue">—</div><div class="delta flat" id="revenue-delta">—</div></article>
    <article class="card metric-card"><h2>Чеков</h2><div class="metric" id="checks">—</div><div class="delta flat" id="checks-delta">—</div></article>
    <article class="card metric-card"><h2>Средний чек</h2><div class="metric" id="avg">—</div><div class="delta flat" id="avg-delta">—</div></article>
    <article class="card metric-card"><h2>Последняя синхронизация</h2><div class="metric" id="sync-age">—</div><div class="note" id="sync-time">—</div></article>

    <article class="card span-6">
     <div class="kicker">ПОЧЕМУ ТАКАЯ ОЦЕНКА</div>
     <h3 class="section-title">Факторы индекса</h3>
     <div id="health-breakdown" class="health-breakdown"></div>
    </article>

    <article class="card span-6">
     <div class="kicker">ДИНАМИКА ИНДЕКСА</div>
     <h3 class="section-title">История состояния</h3>
     <div id="health-change" class="health-change flat">—</div>
     <div id="health-history-chart" class="health-mini-chart"></div>
    </article>

    <article class="card span-8">
     <div class="kicker">ЖИВОЙ ЦИФРОВОЙ АНАЛИТИК</div>
     <h3 class="section-title">Лента событий и сигналов</h3>
     <div class="action-list" id="event-feed"></div>
    </article>
    <article class="card span-4">
     <div class="kicker">КОМАНДА</div>
     <h3 class="section-title">Цифровые помощники</h3>
     <div class="assistant-grid" style="grid-template-columns:1fr" id="assistant-shortcuts"></div>
    </article>
   </div>
  </div>

  <div class="workspace" id="workspace-operations">
   <div class="hero"><div class="hero-main"><div class="kicker">ОПЕРАЦИОННЫЙ ЦЕНТР</div><h1>Состояние ресторана сейчас</h1><div class="sub">Онлайн-статус агента, свежесть данных, текущая выручка и нагрузка.</div></div><div class="hero-side"><div class="kicker" style="color:var(--blue)">СТАТУС</div><div class="health-number" id="ops-status">—</div><div class="health-label">связь с рестораном</div></div></div>
   <div class="grid">
    <article class="card metric-card"><h2>Выручка сегодня</h2><div class="metric" id="ops-revenue">—</div></article>
    <article class="card metric-card"><h2>Чеков сегодня</h2><div class="metric" id="ops-checks">—</div></article>
    <article class="card metric-card"><h2>Средний чек</h2><div class="metric" id="ops-avg">—</div></article>
    <article class="card metric-card"><h2>Последний сигнал</h2><div class="metric" id="ops-sync">—</div></article>
    <article class="card full"><div class="kicker">НАГРУЗКА</div><h3 class="section-title">Продажи по часам</h3><div class="chart" id="ops-hourly"></div></article>
   </div>
  </div>

  <div class="workspace" id="workspace-decisions">
   <div class="hero"><div class="hero-main"><div class="kicker">ЕДИНЫЙ ДВИЖОК РЕКОМЕНДАЦИЙ</div><h1>Центр решений</h1><div class="sub">Система объединяет выводы цифровых помощников в единый план действий.</div></div><div class="hero-side"><div class="kicker" style="color:var(--blue)">НАЙДЕНО</div><div class="health-number" id="decision-count">—</div><div class="health-label">рекомендаций</div></div></div>
   <div class="card"><div class="kicker">ЧТО НУЖНО СДЕЛАТЬ</div><h3 class="section-title">Единый план рекомендаций</h3><div class="action-list" id="decision-list"></div></div>
  </div>

  <div class="workspace" id="workspace-marketer">
   <div class="hero"><div class="hero-main"><div class="kicker">ЦИФРОВОЙ МАРКЕТОЛОГ</div><h1>Рост среднего чека</h1><div class="sub">Возможности допродажи, лидеры спроса и идеи для акций.</div></div><div class="hero-side"><div class="kicker" style="color:var(--blue)">ПОТЕНЦИАЛ</div><div class="health-number" id="marketing-potential">—</div><div class="health-label">оценка допродаж</div></div></div>
   <div class="grid"><article class="card span-6"><div class="kicker">ЛИДЕРЫ</div><h3 class="section-title">Что продвигать</h3><div class="insights" id="marketing-top"></div></article><article class="card span-6"><div class="kicker">ИДЕИ</div><h3 class="section-title">Что предложить гостю</h3><div class="action-list" id="marketing-actions"></div></article></div>
  </div>

  <div class="workspace" id="workspace-technologist">
   <div class="hero"><div class="hero-main"><div class="kicker">ЦИФРОВОЙ ТЕХНОЛОГ</div><h1>Меню</h1><div class="sub">Популярность, структура спроса и рекомендации по позициям.</div></div><div class="hero-side"><div class="kicker" style="color:var(--blue)">ЗДОРОВЬЕ МЕНЮ</div><div class="health-number" id="menu-health">—</div><div class="health-label">из 100</div></div></div>
   <div class="grid"><article class="card span-6"><div class="kicker">ЛИДЕРЫ</div><h3 class="section-title">ТОП блюд</h3><div class="insights" id="top-menu"></div></article><article class="card span-6"><div class="kicker">ABC-АНАЛИЗ</div><h3 class="section-title">Структура меню</h3><div class="insights" id="abc-summary"></div></article></div>
  </div>

  <div class="workspace" id="workspace-finance">
   <div class="hero"><div class="hero-main"><div class="kicker">ФИНАНСОВЫЙ ДИРЕКТОР</div><h1>Финансовая картина</h1><div class="sub">Выручка, количество чеков, средний чек и сравнение периодов.</div></div><div class="hero-side"><div class="kicker" style="color:var(--blue)">ОБОРОТ</div><div class="health-number" id="finance-revenue">—</div><div class="health-label">за выбранный период</div></div></div>
   <div class="grid"><article class="card metric-card"><h2>Выручка</h2><div class="metric" id="finance-r">—</div></article><article class="card metric-card"><h2>Чеков</h2><div class="metric" id="finance-c">—</div></article><article class="card metric-card"><h2>Средний чек</h2><div class="metric" id="finance-a">—</div></article><article class="card metric-card"><h2>Дней в периоде</h2><div class="metric" id="finance-days">—</div></article></div>
  </div>

  <div class="workspace" id="workspace-delivery">
   <div class="hero"><div class="hero-main"><div class="kicker">ЦИФРОВОЙ ПОМОЩНИК ДОСТАВКИ</div><h1>Доставка</h1><div class="sub">Канал доставки будет анализироваться отдельно от блюд и допродаж.</div></div><div class="hero-side"><div class="kicker" style="color:var(--blue)">СТАТУС</div><div class="health-number">β</div><div class="health-label">модуль в развитии</div></div></div>
   <div class="card"><div class="kicker">ВАЖНО</div><h3 class="section-title">Доставка не считается блюдом</h3><p class="sub">В следующих снимках стоимость доставки будет вынесена в отдельный канал выручки и исключена из рейтинга меню и ABC-анализа.</p></div>
  </div>

  <div class="workspace" id="workspace-analyst">
   <div class="hero"><div class="hero-main"><div class="kicker">БИЗНЕС-АНАЛИТИК</div><h1>Подробная аналитика</h1><div class="sub">Графики, сравнение периодов и история облачных снимков.</div></div><div class="hero-side"><div class="kicker" style="color:var(--blue)">ПЕРИОД</div><div class="health-number" id="analyst-days">—</div><div class="health-label">дней</div></div></div>
   <div class="grid">
    <article class="card span-8"><div class="kicker">ДИНАМИКА</div><h3 class="section-title">Выручка и средний чек</h3><div class="line-chart" id="trend-chart"></div><div class="legend"><span>Выручка</span><span class="avg">Средний чек</span></div></article>
    <article class="card span-4"><div class="kicker">ГЛАВНЫЕ ТОЧКИ</div><h3 class="section-title">Что важно за период</h3><div class="insights" id="insights"></div></article>
    <article class="card span-6"><div class="kicker">НАГРУЗКА</div><h3 class="section-title">Продажи по часам</h3><div class="chart" id="hourly-chart"></div></article>
    <article class="card span-6"><div class="kicker">ДНИ</div><h3 class="section-title">Выручка по дням</h3><div class="chart" id="daily-chart"></div></article>
    <article class="card full"><div class="kicker">ДЕТАЛИ</div><h3 class="section-title">История продаж</h3><div id="history-wrap"></div></article>
   </div>
  </div>
 </div>
</section>

<script>
const money=new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:0});
const number=new Intl.NumberFormat('ru-RU');
let currentPeriod='30';
let currentWorkspace='manager';
let cached={history:[],previous:[],agentInfo:null,latest:null,menu:[]};

const assistantMeta={
 manager:['◎','Цифровой управляющий','Главная картина бизнеса'],
 operations:['⌂','Операционный центр','Ресторан прямо сейчас'],
 decisions:['◆','Центр решений','Единый план действий'],
 marketer:['↗','Цифровой маркетолог','Рост среднего чека'],
 technologist:['◉','Цифровой технолог','Меню и стабильность спроса'],
 finance:['₽','Финансовый директор','Выручка и экономика'],
 delivery:['→','Доставка','Каналы и допродажи'],
 analyst:['◇','Бизнес-аналитик','Графики и детализация']
};

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
function pct(current,previous){if(previous===0)return current===0?0:null;return(current-previous)/previous*100}
function setDelta(id,value){
 const el=document.getElementById(id);
 if(value===null){el.textContent='нет базы сравнения';el.className='delta flat';return}
 const sign=value>0?'+':'';
 el.textContent=`${sign}${value.toFixed(1)}% к прошлому периоду`;
 el.className='delta '+(value>0?'up':value<0?'down':'flat')
}
function setQuick(period){
 currentPeriod=period;document.querySelectorAll('.quick').forEach(b=>b.classList.toggle('active',b.dataset.period===period));
 const today=new Date(),from=new Date(),to=new Date();
 if(period==='today'){from.setTime(today.getTime());to.setTime(today.getTime())}
 else if(period==='yesterday'){from.setDate(today.getDate()-1);to.setDate(today.getDate()-1)}
 else{from.setDate(today.getDate()-Number(period)+1)}
 document.getElementById('date-from').value=isoDate(from);document.getElementById('date-to').value=isoDate(to)
}
function switchWorkspace(name){
 currentWorkspace=name;
 document.querySelectorAll('.workspace').forEach(x=>x.classList.toggle('active',x.id===`workspace-${name}`));
 document.querySelectorAll('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.workspace===name));
 const meta=assistantMeta[name];
 document.getElementById('assistant-avatar').textContent=meta[0];
 document.getElementById('assistant-name').textContent=meta[1];
 document.getElementById('assistant-desc').textContent=meta[2];
 window.scrollTo({top:0,behavior:'smooth'})
}
function renderBars(el,items,labelKey,valueKey,labelFormatter,secondary=false){
 el.innerHTML='';if(!items.length){el.innerHTML='<div class="empty">Данных пока нет</div>';return}
 const max=Math.max(...items.map(x=>Number(x[valueKey]||0)),1);
 for(const item of items){
  const wrap=document.createElement('div');wrap.className='bar-wrap';
  const bar=document.createElement('div');bar.className='bar'+(secondary?' secondary':'');
  bar.style.height=Math.max(2,Number(item[valueKey]||0)/max*92)+'%';bar.title=money.format(Number(item[valueKey]||0));
  const label=document.createElement('div');label.className='bar-label';label.textContent=labelFormatter(item[labelKey]);
  wrap.append(bar,label);el.append(wrap)
 }
}
function renderTrend(el,items){
 if(!items.length){el.innerHTML='<div class="empty">Данных пока нет</div>';return}
 const w=900,h=250,p=28,revMax=Math.max(...items.map(x=>Number(x.revenue||0)),1),avgMax=Math.max(...items.map(x=>Number(x.average_check||0)),1);
 const step=items.length>1?(w-2*p)/(items.length-1):0;
 const rev=items.map((x,i)=>[p+i*step,h-p-Number(x.revenue||0)/revMax*(h-2*p)]);
 const avg=items.map((x,i)=>[p+i*step,h-p-Number(x.average_check||0)/avgMax*(h-2*p)]);
 const path=pts=>pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
 const labels=items.map((x,i)=>(items.length>14&&i%Math.ceil(items.length/7)!==0&&i!==items.length-1)?'':`<text class="axis-label" x="${p+i*step}" y="${h-5}" text-anchor="middle">${x.business_date.slice(5)}</text>`).join('');
 el.innerHTML=`<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><path class="line" d="${path(rev)}"></path><path class="line2" d="${path(avg)}"></path>${rev.map(p=>`<circle class="point" cx="${p[0]}" cy="${p[1]}" r="3"></circle>`).join('')}${avg.map(p=>`<circle class="point2" cx="${p[0]}" cy="${p[1]}" r="3"></circle>`).join('')}${labels}</svg>`
}
function buildInsights(history){
 const c=document.getElementById('insights');if(!history.length){c.innerHTML='<div class="empty">Данных пока нет</div>';return}
 const best=history.reduce((a,b)=>Number(b.revenue||0)>Number(a.revenue||0)?b:a),worst=history.reduce((a,b)=>Number(b.revenue||0)<Number(a.revenue||0)?b:a),peak=history.reduce((a,b)=>Number(b.average_check||0)>Number(a.average_check||0)?b:a);
 c.innerHTML=`<div class="insight"><small>Лучший день</small><strong>${best.business_date}</strong>${money.format(best.revenue||0)}</div><div class="insight"><small>Слабый день</small><strong>${worst.business_date}</strong>${money.format(worst.revenue||0)}</div><div class="insight"><small>Максимальный средний чек</small><strong>${peak.business_date}</strong>${money.format(peak.average_check||0)}</div>`
}
function eventFeed(history,menu,revenueDelta,avgDelta){
 const events=[];
 if(revenueDelta!==null)events.push({title:revenueDelta>=0?'Продажи растут':'Продажи ниже прошлого периода',text:`Изменение выручки: ${revenueDelta>=0?'+':''}${revenueDelta.toFixed(1)}%.`,badge:revenueDelta>=0?'Положительно':'Требует внимания'});
 if(avgDelta!==null)events.push({title:avgDelta>=0?'Средний чек вырос':'Средний чек снизился',text:`Изменение среднего чека: ${avgDelta>=0?'+':''}${avgDelta.toFixed(1)}%.`,badge:'Финансы'});
 if(menu.length)events.push({title:`Лидер меню: ${menu[0].item_name}`,text:`Продано ${number.format(menu[0].quantity||0)} ед. на ${money.format(menu[0].revenue||0)}.`,badge:'Меню'});
 if(history.length)events.push({title:'Облачная синхронизация работает',text:`Последний день в истории: ${history[history.length-1].business_date}.`,badge:'Система'});
 document.getElementById('event-feed').innerHTML=events.map(x=>`<div class="action-card"><span class="badge">${x.badge}</span><div><strong>${x.title}</strong><p>${x.text}</p></div><span>→</span></div>`).join('')
}
function decisions(history,menu,revenueDelta,avgDelta){
 const items=[];
 if(revenueDelta!==null&&revenueDelta<0)items.push(['Срочно','Разобрать снижение продаж','Проверить слабые часы и позиции с падением спроса.',91]);
 if(avgDelta!==null&&avgDelta<0)items.push(['Высокий','Поднять средний чек','Усилить допродажи напитков, картофеля и дополнений.',88]);
 if(menu.length)items.push(['Высокий',`Не допускать стоп-листа: ${menu[0].item_name}`,'Обеспечить наличие ключевых ингредиентов лидера.',92]);
 if(menu.length>5)items.push(['Средний','Проверить позиции класса C','Слабые позиции требуют акции, комбо или пересмотра.',78]);
 if(!items.length)items.push(['Наблюдение','Сохранять текущую динамику','Критических отклонений за выбранный период не найдено.',84]);
 document.getElementById('decision-count').textContent=items.length;
 document.getElementById('decision-list').innerHTML=items.map(x=>`<div class="action-card"><span class="action-priority">${x[0]}</span><div><strong>${x[1]}</strong><p>${x[2]}</p></div><div class="action-score">${x[3]}%</div></div>`).join('')
}
async function loadAgents(){
 const data=await api('/api/web/agents'),select=document.getElementById('restaurant'),previous=select.value;select.innerHTML='';
 for(const a of data){const o=document.createElement('option');o.value=a.agent_id;o.textContent=a.name||a.agent_id;select.append(o)}
 if(previous&&[...select.options].some(o=>o.value===previous))select.value=previous
}
async function loadAll(){
 const agent=getAgent();if(!agent)return;
 const dateFrom=document.getElementById('date-from').value,dateTo=document.getElementById('date-to').value;
 const from=parseDate(dateFrom),to=parseDate(dateTo),days=diffDays(from,to),prevTo=new Date(from);prevTo.setDate(prevTo.getDate()-1);
 const prevFrom=new Date(prevTo);prevFrom.setDate(prevTo.getDate()-days+1);
 const [history,previous,agentInfo,latest,menu,aiReport]=await Promise.all([
  api(`/api/web/${agent}/sales/history?date_from=${dateFrom}&date_to=${dateTo}`),
  api(`/api/web/${agent}/sales/history?date_from=${isoDate(prevFrom)}&date_to=${isoDate(prevTo)}`),
  api(`/api/web/${agent}/status`),
  api(`/api/web/${agent}/sales/latest`).catch(()=>null),
  api(`/api/web/${agent}/menu/history?date_from=${dateFrom}&date_to=${dateTo}`).catch(()=>[]),
  api(`/api/web/${agent}/ai/director?date_from=${dateFrom}&date_to=${dateTo}&previous_from=${isoDate(prevFrom)}&previous_to=${isoDate(prevTo)}`).catch(()=>null)
 ]);
 cached={history,previous,agentInfo,latest,menu};
 const revenue=sum(history,'revenue'),checks=sum(history,'checks_count'),avg=checks?revenue/checks:0,prevRevenue=sum(previous,'revenue'),prevChecks=sum(previous,'checks_count'),prevAvg=prevChecks?prevRevenue/prevChecks:0;
 const revenueDelta=pct(revenue,prevRevenue),checksDelta=pct(checks,prevChecks),avgDelta=pct(avg,prevAvg);

 document.getElementById('revenue').textContent=money.format(revenue);document.getElementById('checks').textContent=number.format(checks);document.getElementById('avg').textContent=money.format(avg);
 setDelta('revenue-delta',revenueDelta);setDelta('checks-delta',checksDelta);setDelta('avg-delta',avgDelta);
 const dot=document.getElementById('status-dot');dot.className='dot '+(agentInfo.online?'online':'');document.getElementById('status-text').textContent=(agentInfo.online?'Агент подключён':'Агент не в сети')+(agentInfo.last_seen_at?` · последний сигнал ${agentInfo.last_seen_at}`:'');
 const health=aiReport?.health?.score ?? 0;
 document.getElementById('health-index').textContent=health;
 const healthStatus=aiReport?.health?.status||'attention';
 document.getElementById('health-label').textContent={
  excellent:'Отличное состояние',
  good:'Состояние хорошее',
  attention:'Требует внимания',
  critical:'Критическое состояние'
 }[healthStatus]||'Требует внимания';
 document.getElementById('manager-summary').textContent=
  aiReport?.briefing||'Недостаточно данных для формирования брифинга.';

 const healthFactors=aiReport?.health?.factors||[];
 document.getElementById('health-breakdown').innerHTML=healthFactors.length
  ? healthFactors.map(f=>`
   <div class="health-factor">
    <div class="health-factor-head">
     <span class="health-factor-title">${f.title}</span>
     <span class="health-factor-score">${Math.round(f.score)}/100 · вес ${f.weight}</span>
    </div>
    <div class="health-factor-note">${f.explanation}</div>
    <div class="health-progress"><span style="width:${Math.max(0,Math.min(100,f.score))}%"></span></div>
   </div>`).join('')
  : '<div class="empty">Факторы ещё не рассчитаны</div>';

 const healthChange=aiReport?.health_change;
 const healthChangeEl=document.getElementById('health-change');
 if(healthChange===null||healthChange===undefined){
  healthChangeEl.textContent='Недостаточно истории для сравнения';
  healthChangeEl.className='health-change flat';
 }else{
  healthChangeEl.textContent=`${healthChange>0?'+':''}${healthChange} пункта к предыдущему дню`;
  healthChangeEl.className='health-change '+(healthChange>0?'up':healthChange<0?'down':'flat');
 }

 const healthHistory=aiReport?.health_history||[];
 const healthChart=document.getElementById('health-history-chart');
 if(!healthHistory.length){
  healthChart.innerHTML='<div class="empty">История ещё не накоплена</div>';
 }else{
  const maxScore=Math.max(...healthHistory.map(x=>Number(x.score||0)),100);
  healthChart.innerHTML=healthHistory.map(x=>`
   <div class="health-mini-bar"
    style="height:${Math.max(8,Number(x.score||0)/maxScore*100)}%"
    title="${x.business_date}: ${x.score}/100">
    <span>${x.business_date.slice(5)}</span>
   </div>`).join('');
 }

 let mins=null,hourly=[];
 if(latest){const sync=new Date(latest.captured_at);mins=Math.max(0,Math.round((Date.now()-sync.getTime())/60000));document.getElementById('sync-age').textContent=mins<1?'сейчас':mins+' мин';document.getElementById('sync-time').textContent=latest.captured_at||'';const cols=latest.hourly?.columns||[],rows=latest.hourly?.rows||[];hourly=rows.map(r=>Object.fromEntries(cols.map((c,i)=>[c,r[i]])))}
 else{document.getElementById('sync-age').textContent='—';document.getElementById('sync-time').textContent='данные ещё не получены'}

 const aiEvents=aiReport?.events||[];
 document.getElementById('event-feed').innerHTML=aiEvents.length
  ? aiEvents.map(x=>`<div class="action-card"><span class="badge">${x.source}</span><div><strong>${x.title}</strong><p>${x.text}</p></div><span>→</span></div>`).join('')
  : '<div class="empty">Значимых событий не найдено</div>';

 const aiRecommendations=aiReport?.recommendations||[];
 document.getElementById('decision-count').textContent=aiRecommendations.length;
 document.getElementById('decision-list').innerHTML=aiRecommendations.length
  ? aiRecommendations.map(x=>`<div class="action-card"><span class="action-priority">${x.priority}</span><div><strong>${x.title}</strong><p>${x.action}</p><details><summary>Почему?</summary><p>${x.reason}</p><p><strong>Ожидаемый эффект:</strong> ${x.expected_effect}</p><p><strong>Основание:</strong> ${(x.evidence||[]).join('; ')}</p></details></div><div class="action-score">${x.confidence}%</div></div>`).join('')
  : '<div class="empty">Рекомендаций нет</div>';

 document.getElementById('assistant-shortcuts').innerHTML=[['technologist','Цифровой технолог','Меню и ABC-анализ'],['marketer','Цифровой маркетолог','Возможности роста'],['finance','Финансовый директор','Финансовая картина']].map(x=>`<div class="assistant-card" onclick="switchWorkspace('${x[0]}')"><div class="avatar">${assistantMeta[x[0]][0]}</div><h3>${x[1]}</h3><p>${x[2]}</p></div>`).join('');

 document.getElementById('ops-status').textContent=agentInfo.online?'ON':'OFF';document.getElementById('ops-revenue').textContent=latest?money.format(latest.revenue||0):'—';document.getElementById('ops-checks').textContent=latest?number.format(latest.checks_count||0):'—';document.getElementById('ops-avg').textContent=latest?money.format(latest.average_check||0):'—';document.getElementById('ops-sync').textContent=mins===null?'—':mins<1?'сейчас':mins+' мин';renderBars(document.getElementById('ops-hourly'),hourly,'sale_hour','revenue',v=>String(v).padStart(2,'0'));

 const top=document.getElementById('top-menu');
 top.innerHTML=menu.length?menu.slice(0,10).map((x,i)=>`<div class="insight" style="display:grid;grid-template-columns:34px 1fr auto;gap:10px;align-items:center"><strong style="margin:0">${i+1}</strong><div><strong style="margin:0">${x.item_name}</strong><small>${number.format(x.quantity||0)} шт. · ${Number(x.revenue_share||0).toFixed(1)}%</small></div><strong style="margin:0">${money.format(x.revenue||0)}</strong></div>`).join(''):'<div class="empty">Данные по меню ещё не получены</div>';
 const classes={A:{count:0,revenue:0},B:{count:0,revenue:0},C:{count:0,revenue:0}};menu.forEach(x=>{const c=classes[x.abc_class]||classes.C;c.count++;c.revenue+=Number(x.revenue||0)});
 document.getElementById('abc-summary').innerHTML=['A','B','C'].map(l=>`<div class="insight"><small>Класс ${l}</small><strong>${classes[l].count} позиций</strong>${money.format(classes[l].revenue)}</div>`).join('');
 document.getElementById('menu-health').textContent=menu.length?Math.max(0,Math.min(100,Math.round(100-classes.C.count*3))):'—';

 document.getElementById('marketing-potential').textContent=money.format(Math.round(checks*avg*.05));
 document.getElementById('marketing-top').innerHTML=menu.slice(0,5).map(x=>`<div class="insight"><small>Лидер спроса</small><strong>${x.item_name}</strong>${number.format(x.quantity||0)} шт.</div>`).join('')||'<div class="empty">Нет данных</div>';
 document.getElementById('marketing-actions').innerHTML=menu.slice(0,3).map(x=>`<div class="action-card"><span class="badge">Идея</span><div><strong>Комбо с ${x.item_name}</strong><p>Добавить напиток или гарнир к лидеру продаж.</p></div><span>→</span></div>`).join('')||'<div class="empty">Нет данных</div>';

 document.getElementById('finance-revenue').textContent=money.format(revenue);document.getElementById('finance-r').textContent=money.format(revenue);document.getElementById('finance-c').textContent=number.format(checks);document.getElementById('finance-a').textContent=money.format(avg);document.getElementById('finance-days').textContent=days;
 document.getElementById('analyst-days').textContent=days;
 renderTrend(document.getElementById('trend-chart'),history);buildInsights(history);renderBars(document.getElementById('hourly-chart'),hourly,'sale_hour','revenue',v=>String(v).padStart(2,'0'));renderBars(document.getElementById('daily-chart'),history,'business_date','revenue',v=>v.slice(5),true);

 const wrap=document.getElementById('history-wrap');
 wrap.innerHTML=history.length?`<table class="history"><thead><tr><th>Дата</th><th>Выручка</th><th>Чеков</th><th>Средний чек</th><th>Обновлено</th></tr></thead><tbody>${history.slice().reverse().map(x=>`<tr><td>${x.business_date}</td><td><strong>${money.format(x.revenue||0)}</strong></td><td>${number.format(x.checks_count||0)}</td><td>${money.format(x.average_check||0)}</td><td>${x.captured_at||''}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">История пока не накоплена</div>'
}
document.querySelectorAll('.nav-item').forEach(x=>x.addEventListener('click',()=>switchWorkspace(x.dataset.workspace)));
document.querySelectorAll('.quick').forEach(x=>x.addEventListener('click',()=>{setQuick(x.dataset.period);loadAll()}));
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

    @router.get(
        "/api/web/{agent_id}/ai/director",
        include_in_schema=False,
    )
    def web_ai_director(
        agent_id: str,
        request: Request,
        date_from: str,
        date_to: str,
        previous_from: str,
        previous_to: str,
    ):
        require_browser_session(request)

        agents = {
            item["agent_id"]: item
            for item in storage.list_agents()
        }
        agent_info = agents.get(agent_id)
        if agent_info is None:
            return JSONResponse(
                {"detail": "Агент не найден"},
                status_code=404,
            )
        agent_info["online"] = connections.is_online(agent_id)

        history = storage.sales_history(
            agent_id,
            date_from,
            date_to,
        )
        previous = storage.sales_history(
            agent_id,
            previous_from,
            previous_to,
        )
        latest = storage.latest_sales_snapshot(agent_id)
        menu = storage.menu_sales_history(
            agent_id,
            date_from,
            date_to,
        )

        sync_age_minutes = None
        if latest and latest.get("captured_at"):
            from datetime import datetime, timezone
            try:
                captured = datetime.fromisoformat(
                    latest["captured_at"]
                )
                if captured.tzinfo is None:
                    captured = captured.replace(
                        tzinfo=timezone.utc
                    )
                sync_age_minutes = max(
                    0,
                    int(
                        (
                            datetime.now(timezone.utc)
                            - captured.astimezone(timezone.utc)
                        ).total_seconds()
                        / 60
                    ),
                )
            except (TypeError, ValueError):
                sync_age_minutes = None

        report = build_director_report(
            owner_name="Андрей",
            history=history,
            previous=previous,
            latest=latest,
            menu_items=menu,
            agent_info=agent_info,
            sync_age_minutes=sync_age_minutes,
        )

        business_date = (
            history[-1]["business_date"]
            if history
            else date_to
        )
        storage.save_health_score(
            agent_id,
            business_date,
            report,
        )

        health_history = storage.health_score_history(
            agent_id,
            date_from,
            date_to,
        )
        report["health_history"] = health_history

        if len(health_history) >= 2:
            report["health_change"] = (
                int(health_history[-1]["score"])
                - int(health_history[-2]["score"])
            )
        else:
            report["health_change"] = None

        return report

    @router.get(
        "/api/web/{agent_id}/ai/health/history",
        include_in_schema=False,
    )
    def web_health_history(
        agent_id: str,
        request: Request,
        date_from: str,
        date_to: str,
    ):
        require_browser_session(request)
        return storage.health_score_history(
            agent_id,
            date_from,
            date_to,
        )

    return router
