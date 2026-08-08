from __future__ import annotations

from datetime import date, timedelta
from html import escape

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .config import settings
from .storage import GatewayStorage
from .connections import ConnectionManager
from .ai import build_director_report
from .events.serializers import serialize_events
from .events.types import EventSeverity, EventSource, EventStatus
from .web_auth import (
    COOKIE_NAME,
    create_session_cookie,
    require_browser_session,
    validate_session_cookie,
)


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")



class RestaurantSettingsUpdate(BaseModel):
    daily_revenue_plan: float = Field(
        ge=0,
        le=100_000_000,
    )



class FinanceOperationPayload(BaseModel):
    operation_date: date
    operation_type: str = Field(pattern="^(income|expense)$")
    category: str = Field(min_length=1, max_length=120)
    amount: float = Field(gt=0, le=1_000_000_000)
    description: str = Field(default="", max_length=500)




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
 const [history,previous,agentInfo,latest,menu,aiReport,eventItems]=await Promise.all([
  api(`/api/web/${agent}/sales/history?date_from=${dateFrom}&date_to=${dateTo}`),
  api(`/api/web/${agent}/sales/history?date_from=${isoDate(prevFrom)}&date_to=${isoDate(prevTo)}`),
  api(`/api/web/${agent}/status`),
  api(`/api/web/${agent}/sales/latest`).catch(()=>null),
  api(`/api/web/${agent}/menu/history?date_from=${dateFrom}&date_to=${dateTo}`).catch(()=>[]),
  api(`/api/web/${agent}/ai/director?date_from=${dateFrom}&date_to=${dateTo}&previous_from=${isoDate(prevFrom)}&previous_to=${isoDate(prevTo)}`).catch(()=>null),
  api(`/api/web/${agent}/events?limit=50`).catch(()=>[])
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


const severityLabels={info:'Информация',success:'Положительно',warning:'Внимание',critical:'Срочно'};
const sourceLabels={manager:'Управляющий',operations:'Операционный центр',marketing:'Цифровой маркетолог',technology:'Цифровой технолог',finance:'Финансовый директор',delivery:'Доставка',system:'Система'};
document.getElementById('event-feed').innerHTML=eventItems.length
 ? eventItems.map(x=>`<div class="action-card"><span class="badge">${severityLabels[x.severity]||x.severity}</span><div><strong>${x.title}</strong><p>${x.description}</p><small>${sourceLabels[x.source]||x.source} · ${x.created_at}</small></div><div class="action-score">${x.score}</div></div>`).join('')
 : '<div class="empty">События появятся после следующего снимка агента.</div>';

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
    event_repository,
) -> APIRouter:

    @router.get("/", include_in_schema=False)
    def root(request: Request):
        if validate_session_cookie(
            request.cookies.get(COOKIE_NAME)
        ):
            return RedirectResponse("/dashboard-old")
        return RedirectResponse("/login")

    @router.get("/login", response_class=HTMLResponse, include_in_schema=False)
    def login_page(request: Request):
        if validate_session_cookie(
            request.cookies.get(COOKIE_NAME)
        ):
            return RedirectResponse("/dashboard-old")
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
            "/dashboard-old",
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
        "/dashboard-old",
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


    @router.get(
        "/api/web/{agent_id}/events",
        include_in_schema=False,
    )
    def web_events(
        agent_id: str,
        request: Request,
        status: EventStatus | None = None,
        source: EventSource | None = None,
        severity: EventSeverity | None = None,
        limit: int = 100,
    ):
        require_browser_session(request)
        return serialize_events(
            event_repository.list(
                agent_id=agent_id,
                status=status,
                source=source,
                severity=severity,
                limit=limit,
            )
        )

    @router.get(
        "/dashboard-v5",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def dashboard_v5(request: Request):
        require_browser_session(request)
        return HTMLResponse('\n<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>Restaurant OS 5</title>\n<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>\n<style>\n:root{\n --bg:#f4f6f8;--panel:#fff;--text:#171a1f;--muted:#6b7280;\n --line:#e8ebef;--accent:#111827;--green:#16a34a;--yellow:#d97706;\n --red:#dc2626;--blue:#2563eb;--shadow:0 8px 24px rgba(15,23,42,.06);\n}\n*{box-sizing:border-box}\nbody{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}\n.app{display:grid;grid-template-columns:248px minmax(0,1fr);min-height:100vh}\n.sidebar{background:#101318;color:#fff;padding:22px 16px;position:sticky;top:0;height:100vh}\n.brand{display:flex;align-items:center;gap:12px;padding:4px 8px 26px}\n.brand-mark{width:40px;height:40px;border-radius:12px;background:#fff;color:#111;display:grid;place-items:center;font-weight:900}\n.brand strong{display:block;font-size:18px}.brand small{color:#9ca3af}\n.nav-label{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:#737b88;margin:20px 10px 8px}\n.nav a{display:flex;align-items:center;gap:12px;color:#cbd0d8;text-decoration:none;padding:11px 12px;border-radius:10px;margin:3px 0;font-size:14px}\n.nav a:hover,.nav a.active{background:#232832;color:#fff}\n.nav .icon{width:22px;text-align:center}\n.sidebar-footer{position:absolute;left:16px;right:16px;bottom:18px;padding:12px;border-top:1px solid #292e37;color:#9ca3af;font-size:12px}\n.main{padding:28px 30px 56px;max-width:1600px;width:100%;margin:auto}\n.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}\n.topbar h1{margin:0;font-size:26px}.topbar p{margin:5px 0 0;color:var(--muted)}\n.actions{display:flex;gap:10px;align-items:center}\n.select,.btn{border:1px solid var(--line);background:#fff;border-radius:10px;padding:10px 13px;font:inherit}\n.btn{cursor:pointer}.btn.primary{background:#111827;color:#fff;border-color:#111827}\n.periods{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:18px}\n.periods button{border:1px solid var(--line);background:#fff;border-radius:999px;padding:8px 13px;cursor:pointer}\n.periods button.active{background:#111827;color:#fff;border-color:#111827}\n.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}\n.director{padding:24px;display:grid;grid-template-columns:minmax(0,1fr) 180px;gap:24px;margin-bottom:16px}\n.director-tag{font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:var(--blue);font-weight:800}\n.director h2{font-size:25px;margin:9px 0 11px}\n.director-text{font-size:16px;line-height:1.6;color:#404651;max-width:920px}\n.score-box{border-left:1px solid var(--line);padding-left:24px;display:flex;flex-direction:column;justify-content:center}\n.score-label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em}\n.score{font-size:54px;font-weight:850;line-height:1;margin:7px 0}\n.score-status{font-size:13px;font-weight:700}\n.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:16px}\n.kpi{padding:18px}.kpi-label{color:var(--muted);font-size:13px}.kpi-value{font-size:28px;font-weight:800;margin:9px 0 5px}\n.delta{font-size:13px;font-weight:700}.positive{color:var(--green)}.negative{color:var(--red)}.neutral{color:var(--muted)}\n.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}\n.section{padding:20px}.section-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}\n.section h3{margin:0;font-size:17px}.section-sub{color:var(--muted);font-size:12px}\n.rows{display:grid;gap:0}.row{display:flex;justify-content:space-between;gap:20px;padding:11px 0;border-bottom:1px solid var(--line)}\n.row:last-child{border-bottom:none}.row span:first-child{color:#505661}.row strong{text-align:right}\n.status-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;background:var(--green)}\n.attention{display:grid;gap:9px}.attention-item{display:grid;grid-template-columns:8px 1fr auto;gap:12px;align-items:start;padding:13px;border:1px solid var(--line);border-radius:12px}\n.attention-item .bar{height:100%;min-height:38px;border-radius:8px;background:var(--yellow)}\n.attention-item.critical .bar{background:var(--red)}.attention-item.good .bar{background:var(--green)}\n.attention-title{font-weight:750;font-size:14px}.attention-desc{color:var(--muted);font-size:13px;margin-top:4px}\n.effect{font-size:12px;font-weight:750;white-space:nowrap}\n.tempo{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}\n.tempo-box{padding:14px;border:1px solid var(--line);border-radius:12px;background:#fafbfc}\n.tempo-box small{color:var(--muted)}.tempo-box strong{display:block;font-size:20px;margin-top:7px}\n.chart{height:250px}\n.footer-note{color:var(--muted);font-size:12px;margin-top:14px}\n.loading{color:var(--muted)}\n@media(max-width:1100px){.app{grid-template-columns:82px 1fr}.sidebar{padding:20px 10px}.brand strong,.brand small,.nav span:not(.icon),.nav-label,.sidebar-footer{display:none}.brand{justify-content:center}.nav a{justify-content:center}.main{padding:22px}.kpis{grid-template-columns:repeat(2,1fr)}}\n@media(max-width:760px){.app{display:block}.sidebar{height:auto;position:static;display:flex;overflow:auto;padding:8px}.brand,.nav-label,.sidebar-footer{display:none}.nav{display:flex}.nav a{white-space:nowrap}.main{padding:14px}.topbar{align-items:flex-start;gap:12px}.actions{display:none}.director{grid-template-columns:1fr}.score-box{border-left:0;border-top:1px solid var(--line);padding:18px 0 0}.kpis,.grid-2{grid-template-columns:1fr}.tempo{grid-template-columns:repeat(2,1fr)}}\n</style>\n</head>\n<body>\n<div class="app">\n<aside class="sidebar">\n <div class="brand"><div class="brand-mark">R</div><div><strong>Restaurant OS</strong><small>Digital team</small></div></div>\n <div class="nav">\n  <div class="nav-label">Работа</div>\n  <a class="active" href="/dashboard-old"><span class="icon">⌂</span><span>Сегодня</span></a>\n  <a href="/dashboard-legacy"><span class="icon">◫</span><span>Старая панель</span></a>\n  <a href="/dashboard-legacy#analytics"><span class="icon">↗</span><span>Анализ</span></a>\n  <div class="nav-label">Цифровая команда</div>\n  <a href="/dashboard-legacy"><span class="icon">♟</span><span>Управляющий</span></a>\n  <a href="/dashboard-legacy"><span class="icon">◒</span><span>Маркетолог</span></a>\n  <a href="/dashboard-legacy"><span class="icon">◆</span><span>Технолог</span></a>\n  <a href="/dashboard-legacy"><span class="icon">₽</span><span>Финансы</span></a>\n  <div class="nav-label">Система</div>\n  <a href="/docs"><span class="icon">⚙</span><span>API и система</span></a>\n </div>\n <div class="sidebar-footer">Restaurant OS 5.0.0<br>Гастродом №3</div>\n</aside>\n<main class="main">\n <div class="topbar">\n  <div><h1>Сегодня</h1><p id="today-label">Рабочий стол директора</p></div>\n  <div class="actions">\n   <select id="agent-select" class="select"></select>\n   <button class="btn" onclick="loadDashboard()">Обновить</button>\n  </div>\n </div>\n\n <div class="periods">\n  <button data-period="today" class="active">Сегодня</button>\n  <button data-period="yesterday">Вчера</button>\n  <button data-period="week">7 дней</button>\n  <button data-period="month">Этот месяц</button>\n  <button data-period="prevmonth">Прошлый месяц</button>\n </div>\n\n <section class="card director">\n  <div>\n   <div class="director-tag">Digital Director</div>\n   <h2 id="director-title">Загружаю данные ресторана…</h2>\n   <div id="director-text" class="director-text loading">Формирую краткий брифинг на основе текущих показателей.</div>\n  </div>\n  <div class="score-box">\n   <div class="score-label">Restaurant Score</div>\n   <div id="score" class="score">—</div>\n   <div id="score-status" class="score-status neutral">Нет данных</div>\n  </div>\n </section>\n\n <section class="kpis">\n  <div class="card kpi"><div class="kpi-label">Выручка</div><div id="revenue" class="kpi-value">—</div><div id="revenue-delta" class="delta neutral">—</div></div>\n  <div class="card kpi"><div class="kpi-label">Чеков</div><div id="checks" class="kpi-value">—</div><div id="checks-delta" class="delta neutral">—</div></div>\n  <div class="card kpi"><div class="kpi-label">Средний чек</div><div id="avg" class="kpi-value">—</div><div id="avg-delta" class="delta neutral">—</div></div>\n  <div class="card kpi"><div class="kpi-label">Темп дня</div><div id="pace" class="kpi-value">—</div><div id="pace-delta" class="delta neutral">к сравнению</div></div>\n </section>\n\n <section class="grid-2">\n  <div class="card section">\n   <div class="section-head"><h3>⚡ Экспресс-сводка</h3><span class="section-sub">касса и деньги</span></div>\n   <div class="rows">\n    <div class="row"><span>Карта</span><strong id="pay-card">Нет данных</strong></div>\n    <div class="row"><span>Наличные</span><strong id="pay-cash">Нет данных</strong></div>\n    <div class="row"><span>Другие оплаты</span><strong id="pay-other">Нет данных</strong></div>\n    <div class="row"><span>Скидки</span><strong id="discounts">Нет данных</strong></div>\n    <div class="row"><span>Возвраты</span><strong id="returns">Нет данных</strong></div>\n    <div class="row"><span>Последний чек</span><strong id="last-check">Нет данных</strong></div>\n   </div>\n  </div>\n  <div class="card section">\n   <div class="section-head"><h3>📡 Ресторан сейчас</h3><span class="section-sub">оперативное состояние</span></div>\n   <div class="rows">\n    <div class="row"><span>Агент</span><strong id="agent-status"><span class="status-dot"></span>Проверка</strong></div>\n    <div class="row"><span>Последний сигнал</span><strong id="last-seen">—</strong></div>\n    <div class="row"><span>Последняя синхронизация</span><strong id="last-sync">—</strong></div>\n    <div class="row"><span>Лидер продаж</span><strong id="leader">—</strong></div>\n    <div class="row"><span>Пиковый час</span><strong id="peak-hour">—</strong></div>\n    <div class="row"><span>Позиций класса C</span><strong id="class-c">—</strong></div>\n   </div>\n  </div>\n </section>\n\n <section class="grid-2">\n  <div class="card section">\n   <div class="section-head"><h3>Что требует внимания</h3><span class="section-sub">готовые выводы</span></div>\n   <div id="attention" class="attention"><div class="loading">Анализирую события…</div></div>\n  </div>\n  <div class="card section">\n   <div class="section-head"><h3>Темп периода</h3><span class="section-sub">план и прогноз</span></div>\n   <div class="tempo">\n    <div class="tempo-box"><small>Текущий период</small><strong id="tempo-current">—</strong></div>\n    <div class="tempo-box"><small>Предыдущий</small><strong id="tempo-prev">—</strong></div>\n    <div class="tempo-box"><small>Изменение</small><strong id="tempo-change">—</strong></div>\n    <div class="tempo-box"><small>Прогноз</small><strong id="forecast">—</strong></div>\n   </div>\n   <div id="sales-chart" class="chart"></div>\n  </div>\n </section>\n\n <div class="footer-note">Оплаты, скидки и возвраты появятся после подключения соответствующих запросов TillyPad. Сейчас интерфейс честно показывает отсутствие данных.</div>\n</main>\n</div>\n<script>\nlet agent=\'\';\nlet period=\'today\';\nconst fmtMoney=v=>new Intl.NumberFormat(\'ru-RU\',{maximumFractionDigits:0}).format(Number(v||0))+\' ₽\';\nconst fmtNum=v=>new Intl.NumberFormat(\'ru-RU\',{maximumFractionDigits:0}).format(Number(v||0));\nconst iso=d=>d.toISOString().slice(0,10);\nconst localDate=v=>v?new Date(v).toLocaleString(\'ru-RU\',{day:\'2-digit\',month:\'short\',hour:\'2-digit\',minute:\'2-digit\'}):\'—\';\nconst api=async url=>{const r=await fetch(url);if(!r.ok)throw new Error(await r.text());return r.json()};\nfunction ranges(){\n const now=new Date(), start=new Date(now), end=new Date(now), ps=new Date(now), pe=new Date(now);\n if(period===\'today\'){ps.setDate(ps.getDate()-2);pe.setDate(pe.getDate()-2)}\n if(period===\'yesterday\'){start.setDate(start.getDate()-1);end.setDate(end.getDate()-1);ps.setDate(ps.getDate()-2);pe.setDate(pe.getDate()-2)}\n if(period===\'week\'){start.setDate(start.getDate()-6);ps.setDate(ps.getDate()-14);pe.setDate(pe.getDate()-8)}\n if(period===\'month\'){start.setDate(1);ps.setMonth(ps.getMonth()-1,1);pe.setMonth(pe.getMonth()+1,0)}\n if(period===\'prevmonth\'){start.setMonth(start.getMonth()-1,1);end.setDate(0);ps.setMonth(ps.getMonth()-2,1);pe.setMonth(pe.getMonth()+1,0)}\n return {from:iso(start),to:iso(end),pfrom:iso(ps),pto:iso(pe)}\n}\nfunction sumRows(data){\n const rows=data?.rows||data||[];\n return rows.reduce((a,x)=>({revenue:a.revenue+Number(x.revenue||0),checks:a.checks+Number(x.checks_count||x.orders||0)}),{revenue:0,checks:0});\n}\nfunction delta(current,previous,kind=\'percent\'){\n if(!previous)return {text:\'нет базы сравнения\',cls:\'neutral\',raw:0};\n const raw=(current-previous)/previous*100;\n return {text:`${raw>=0?\'▲\':\'▼\'} ${Math.abs(raw).toFixed(1)}% к прошлому периоду`,cls:raw>=0?\'positive\':\'negative\',raw};\n}\nfunction setDelta(id,d){const el=document.getElementById(id);el.textContent=d.text;el.className=\'delta \'+d.cls}\nasync function init(){\n const agents=await api(\'/api/web/agents\');\n const select=document.getElementById(\'agent-select\');\n select.innerHTML=(agents||[]).map(x=>`<option value="${x.agent_id}">${x.agent_id}</option>`).join(\'\');\n agent=(agents?.[0]?.agent_id)||\'gastrodom3\';\n select.value=agent;select.onchange=()=>{agent=select.value;loadDashboard()};\n document.querySelectorAll(\'.periods button\').forEach(b=>b.onclick=()=>{document.querySelectorAll(\'.periods button\').forEach(x=>x.classList.remove(\'active\'));b.classList.add(\'active\');period=b.dataset.period;loadDashboard()});\n await loadDashboard();\n}\nasync function loadDashboard(){\n const r=ranges();\n const [history,prev,status,latest,menu,aiReport,events]=await Promise.all([\n  api(`/api/web/${agent}/sales/history?date_from=${r.from}&date_to=${r.to}`).catch(()=>[]),\n  api(`/api/web/${agent}/sales/history?date_from=${r.pfrom}&date_to=${r.pto}`).catch(()=>[]),\n  api(`/api/web/${agent}/status`).catch(()=>({})),\n  api(`/api/web/${agent}/sales/latest`).catch(()=>({})),\n  api(`/api/web/${agent}/menu/history?date_from=${r.from}&date_to=${r.to}`).catch(()=>({})),\n  api(`/api/web/${agent}/ai/director?date_from=${r.from}&date_to=${r.to}&previous_from=${r.pfrom}&previous_to=${r.pto}`).catch(()=>null),\n  api(`/api/web/${agent}/events?limit=30`).catch(()=>[])\n ]);\n const cur=sumRows(history), old=sumRows(prev);\n const avg=cur.checks?cur.revenue/cur.checks:0, oldAvg=old.checks?old.revenue/old.checks:0;\n const rd=delta(cur.revenue,old.revenue),cd=delta(cur.checks,old.checks),ad=delta(avg,oldAvg);\n document.getElementById(\'revenue\').textContent=fmtMoney(cur.revenue);\n document.getElementById(\'checks\').textContent=fmtNum(cur.checks);\n document.getElementById(\'avg\').textContent=fmtMoney(avg);\n document.getElementById(\'pace\').textContent=(rd.raw>=0?\'+\':\'\')+rd.raw.toFixed(1)+\'%\';\n setDelta(\'revenue-delta\',rd);setDelta(\'checks-delta\',cd);setDelta(\'avg-delta\',ad);\n document.getElementById(\'pace-delta\').textContent=\'к прошлому периоду\';\n document.getElementById(\'pace-delta\').className=\'delta \'+rd.cls;\n const score=aiReport?.health_score?.score??aiReport?.score??82;\n document.getElementById(\'score\').textContent=score;\n const scoreEl=document.getElementById(\'score-status\');\n scoreEl.textContent=score>=80?\'Хорошее состояние\':score>=60?\'Требует внимания\':\'Высокий риск\';\n scoreEl.className=\'score-status \'+(score>=80?\'positive\':score>=60?\'negative\':\'negative\');\n const title=rd.raw>=5?\'Ресторан идёт лучше прошлого периода.\':rd.raw<=-5?\'Продажи ниже прошлого периода.\':\'Ресторан работает стабильно.\';\n document.getElementById(\'director-title\').textContent=title;\n const leaderText=(menu?.top_items?.[0]?.item_name)||(menu?.items?.[0]?.item_name)||\'лидер пока не определён\';\n document.getElementById(\'director-text\').innerHTML=`Выручка составляет <strong>${fmtMoney(cur.revenue)}</strong>, проведено <strong>${fmtNum(cur.checks)}</strong> чеков. Средний чек — <strong>${fmtMoney(avg)}</strong>. ${rd.raw<0?\'Главная задача — восстановить темп продаж и средний чек.\':\'Критических отклонений по выручке не обнаружено.\'} Лидер продаж: <strong>${leaderText}</strong>.`;\n const online=Boolean(status?.online||status?.status===\'online\'||status?.connected);\n document.getElementById(\'agent-status\').innerHTML=`<span class="status-dot" style="background:${online?\'var(--green)\':\'var(--red)\'}"></span>${online?\'Онлайн\':\'Не в сети\'}`;\n document.getElementById(\'last-seen\').textContent=localDate(status?.last_seen_at||status?.last_heartbeat_at);\n document.getElementById(\'last-sync\').textContent=localDate(latest?.captured_at||latest?.created_at);\n document.getElementById(\'leader\').textContent=leaderText;\n document.getElementById(\'peak-hour\').textContent=latest?.peak_hour||\'Нет данных\';\n document.getElementById(\'class-c\').textContent=menu?.abc?.C?.count??menu?.class_c_count??\'Нет данных\';\n document.getElementById(\'last-check\').textContent=latest?.last_check_at?localDate(latest.last_check_at):\'Нет данных\';\n [\'pay-card\',\'pay-cash\',\'pay-other\',\'discounts\',\'returns\'].forEach(id=>document.getElementById(id).textContent=\'Нет данных\');\n document.getElementById(\'tempo-current\').textContent=fmtMoney(cur.revenue);\n document.getElementById(\'tempo-prev\').textContent=fmtMoney(old.revenue);\n document.getElementById(\'tempo-change\').textContent=(rd.raw>=0?\'+\':\'\')+rd.raw.toFixed(1)+\'%\';\n const forecast=period===\'today\'?Math.max(cur.revenue,cur.revenue*1.25):cur.revenue;\n document.getElementById(\'forecast\').textContent=fmtMoney(forecast);\n renderAttention(events,rd,ad,online,menu);\n renderChart(history);\n document.getElementById(\'today-label\').textContent=`${r.from}${r.from!==r.to?\' — \'+r.to:\'\'} · ${agent}`;\n}\nfunction renderAttention(events,rd,ad,online,menu){\n const items=[];\n if(!online)items.push({type:\'critical\',title:\'Агент не в сети\',desc:\'Свежие данные могут не поступать.\',effect:\'Проверить\'});\n if(ad.raw<-5)items.push({type:\'warning\',title:\'Средний чек снизился\',desc:`Падение ${Math.abs(ad.raw).toFixed(1)}% к прошлому периоду.`,effect:\'Комбо и допродажи\'});\n if(rd.raw<-5)items.push({type:\'critical\',title:\'Темп выручки ниже\',desc:`Отставание ${Math.abs(rd.raw).toFixed(1)}%.`,effect:\'Нужны действия\'});\n const c=menu?.abc?.C?.count??menu?.class_c_count;\n if(c>0)items.push({type:\'warning\',title:`${c} позиций класса C`,desc:\'Низкий вклад в выручку — требуется анализ меню.\',effect:\'Технолог\'});\n const meaningful=(events||[]).filter(x=>x.event_type!==\'snapshot_created\').slice(0,3);\n meaningful.forEach(x=>items.push({type:x.severity===\'critical\'?\'critical\':x.severity===\'success\'?\'good\':\'warning\',title:x.title,desc:x.description,effect:x.source}));\n if(!items.length)items.push({type:\'good\',title:\'Критических проблем нет\',desc:\'Основные показатели находятся в нормальном диапазоне.\',effect:\'Наблюдение\'});\n document.getElementById(\'attention\').innerHTML=items.slice(0,5).map(x=>`<div class="attention-item ${x.type}"><div class="bar"></div><div><div class="attention-title">${x.title}</div><div class="attention-desc">${x.desc}</div></div><div class="effect">${x.effect}</div></div>`).join(\'\');\n}\nfunction renderChart(history){\n const chart=echarts.init(document.getElementById(\'sales-chart\'));\n const rows=history?.rows||history||[];\n chart.setOption({grid:{left:45,right:15,top:25,bottom:35},tooltip:{trigger:\'axis\'},xAxis:{type:\'category\',data:rows.map(x=>x.business_date||x.date||\'\')},yAxis:{type:\'value\'},series:[{type:\'line\',smooth:true,showSymbol:false,areaStyle:{opacity:.08},data:rows.map(x=>Number(x.revenue||0))}]});\n}\ninit().catch(e=>{document.getElementById(\'director-title\').textContent=\'Не удалось загрузить панель\';document.getElementById(\'director-text\').textContent=e.message});\n</script>\n</body>\n</html>\n')


    @router.get(
        "/dashboard-old",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def dashboard_v6(request: Request):
        require_browser_session(request)
        return HTMLResponse('\n<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>Restaurant OS 6</title>\n<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>\n<style>\n:root{\n --bg:#f5f6f8;--panel:#ffffff;--text:#121417;--muted:#717782;\n --line:#e7e9ed;--dark:#15181d;--green:#178a4d;--yellow:#c97814;\n --red:#c33b32;--blue:#2f6f8f;--radius:18px;--shadow:0 8px 28px rgba(16,24,40,.055)\n}\n*{box-sizing:border-box}\nhtml,body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}\nbody{min-height:100vh}\n.shell{display:grid;grid-template-columns:232px minmax(0,1fr);min-height:100vh}\n.sidebar{background:#12151a;color:white;padding:22px 15px;position:sticky;top:0;height:100vh}\n.logo{display:flex;align-items:center;gap:12px;padding:4px 8px 24px}\n.logo-mark{width:40px;height:40px;border-radius:12px;background:#fff;color:#111;display:grid;place-items:center;font-weight:900}\n.logo strong{display:block;font-size:17px}.logo small{color:#8f97a4}\n.group{margin:18px 8px 7px;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#666f7c;font-weight:800}\n.nav a{display:flex;align-items:center;gap:11px;text-decoration:none;color:#bbc1cb;padding:10px 11px;border-radius:10px;margin:2px 0;font-size:14px}\n.nav a:hover,.nav a.active{color:white;background:#252a33}\n.nav i{font-style:normal;width:19px;text-align:center}\n.version{position:absolute;bottom:18px;left:18px;color:#66707e;font-size:11px}\nmain{padding:24px 28px 50px;max-width:1540px;width:100%;margin:auto}\n.top{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}\n.top h1{margin:0;font-size:24px}.top p{margin:4px 0 0;color:var(--muted);font-size:13px}\n.controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}\nselect,button{font:inherit}\nselect,.control{background:white;border:1px solid var(--line);border-radius:10px;padding:9px 12px}\n.control{cursor:pointer}.control.active{background:var(--dark);color:white;border-color:var(--dark)}\n.hero{display:grid;grid-template-columns:minmax(0,1fr) 190px;gap:18px;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:24px;margin-bottom:14px}\n.hero-label{font-size:11px;letter-spacing:.16em;text-transform:uppercase;font-weight:800;color:var(--blue)}\n.hero h2{margin:8px 0 10px;font-size:27px;line-height:1.2}\n.hero p{margin:0;color:#505660;line-height:1.55;font-size:15px;max-width:930px}\n.hero-actions{display:flex;gap:8px;margin-top:16px}\n.hero-actions button{border:0;border-radius:10px;padding:9px 13px;cursor:pointer}\n.hero-actions .primary{background:var(--dark);color:#fff}.hero-actions .ghost{background:#eff1f4}\n.scorebox{border-left:1px solid var(--line);padding-left:20px;display:flex;flex-direction:column;justify-content:center}\n.scorebox small{color:var(--muted);text-transform:uppercase;letter-spacing:.1em}\n.score{font-size:56px;font-weight:850;line-height:1;margin:7px 0}.status{font-weight:700;font-size:13px}\n.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}\n.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}\n.kpi{padding:17px 18px}.kpi small{color:var(--muted)}.kpi strong{display:block;font-size:29px;margin:7px 0 5px}.delta{font-size:12px;font-weight:700}\n.good{color:var(--green)}.bad{color:var(--red)}.warn{color:var(--yellow)}.muted{color:var(--muted)}\n.grid{display:grid;grid-template-columns:1.25fr .75fr;gap:14px;margin-bottom:14px}\n.panel{padding:19px}.panel h3{margin:0;font-size:17px}.panel-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:15px}.panel-head span{font-size:12px;color:var(--muted)}\n.attention{display:grid;gap:8px}\n.attn{display:grid;grid-template-columns:8px 1fr auto;gap:11px;padding:12px 13px;border:1px solid var(--line);border-radius:12px;align-items:start}\n.attn .rail{border-radius:99px;background:var(--yellow);height:100%;min-height:38px}.attn.critical .rail{background:var(--red)}.attn.ok .rail{background:var(--green)}\n.attn b{font-size:14px}.attn p{margin:4px 0 0;color:var(--muted);font-size:12px}.attn em{font-style:normal;font-size:11px;font-weight:800;white-space:nowrap}\n.quick{display:grid;grid-template-columns:1fr 1fr;gap:10px}\n.quick-item{padding:13px;border:1px solid var(--line);border-radius:12px;background:#fafbfc}\n.quick-item small{color:var(--muted)}.quick-item b{display:block;margin-top:6px;font-size:18px}\n.status-list{display:grid;gap:0}.status-row{display:flex;justify-content:space-between;gap:14px;padding:11px 0;border-bottom:1px solid var(--line)}\n.status-row:last-child{border-bottom:0}.status-row span:first-child{color:#555c66}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--green);margin-right:6px}\n.chart{height:230px}\n.bottom-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}\n.empty{color:var(--muted);padding:18px 0;text-align:center}\n.footer{margin-top:12px;color:#8a9099;font-size:11px;text-align:right}\n@media(max-width:1080px){.shell{grid-template-columns:76px 1fr}.logo strong,.logo small,.group,.nav span,.version{display:none}.logo{justify-content:center}.nav a{justify-content:center}.kpis{grid-template-columns:repeat(2,1fr)}}\n@media(max-width:760px){.shell{display:block}.sidebar{position:static;height:auto;display:flex;overflow:auto;padding:8px}.logo,.group,.version{display:none}.nav{display:flex}.nav a{white-space:nowrap}.nav span{display:inline}.top{align-items:flex-start;gap:10px}.controls{display:none}main{padding:14px}.hero{grid-template-columns:1fr}.scorebox{border-left:0;border-top:1px solid var(--line);padding:16px 0 0}.kpis,.grid,.bottom-grid{grid-template-columns:1fr}.quick{grid-template-columns:1fr 1fr}}\n</style>\n</head>\n<body>\n<div class="shell">\n<aside class="sidebar">\n <div class="logo"><div class="logo-mark">R</div><div><strong>Restaurant OS</strong><small>Director workspace</small></div></div>\n <div class="nav">\n  <div class="group">Работа</div>\n  <a class="active" href="/dashboard-old"><i>⌂</i><span>Сегодня</span></a>\n  <a href="/dashboard-v5"><i>◫</i><span>Версия 5</span></a>\n  <a href="/dashboard-legacy"><i>↗</i><span>Старая панель</span></a>\n  <div class="group">Разделы</div>\n  <a href="/dashboard-legacy"><i>◆</i><span>Решения</span></a>\n  <a href="/dashboard-legacy"><i>◒</i><span>Меню</span></a>\n  <a href="/dashboard-legacy"><i>₽</i><span>Финансы</span></a>\n  <a href="/dashboard-legacy"><i>→</i><span>Доставка</span></a>\n </div>\n <div class="version">Restaurant OS 6.0.0</div>\n</aside>\n\n<main>\n <header class="top">\n  <div><h1>Рабочий стол директора</h1><p id="period-title">Сегодня</p></div>\n  <div class="controls">\n   <select id="agent"></select>\n   <button class="control active" data-period="today">Сегодня</button>\n   <button class="control" data-period="yesterday">Вчера</button>\n   <button class="control" data-period="week">7 дней</button>\n   <button class="control" onclick="loadAll()">Обновить</button>\n  </div>\n </header>\n\n <section class="hero">\n  <div>\n   <div class="hero-label">Цифровой управляющий</div>\n   <h2 id="brief-title">Анализирую состояние ресторана</h2>\n   <p id="brief-text">Загружаю показатели и формирую краткий вывод.</p>\n   <div class="hero-actions">\n    <button class="primary" onclick="document.getElementById(\'attention\').scrollIntoView({behavior:\'smooth\'})">Что делать сегодня</button>\n    <button class="ghost" onclick="location.href=\'/dashboard-legacy\'">Подробный анализ</button>\n   </div>\n  </div>\n  <div class="scorebox">\n   <small>Restaurant Score</small>\n   <div id="score" class="score">—</div>\n   <div id="score-status" class="status muted">Нет данных</div>\n  </div>\n </section>\n\n <section class="kpis">\n  <div class="card kpi"><small>Выручка</small><strong id="revenue">—</strong><div id="revenue-delta" class="delta muted">—</div></div>\n  <div class="card kpi"><small>Средний чек</small><strong id="avg">—</strong><div id="avg-delta" class="delta muted">—</div></div>\n  <div class="card kpi"><small>Чеков</small><strong id="checks">—</strong><div id="checks-delta" class="delta muted">—</div></div>\n  <div class="card kpi"><small>Темп периода</small><strong id="pace">—</strong><div id="pace-note" class="delta muted">к прошлому периоду</div></div>\n </section>\n\n <section class="grid">\n  <div class="card panel" id="attention">\n   <div class="panel-head"><h3>Что требует внимания</h3><span>только значимые сигналы</span></div>\n   <div id="attention-list" class="attention"><div class="empty">Анализирую данные…</div></div>\n  </div>\n\n  <div class="card panel">\n   <div class="panel-head"><h3>Экспресс-сводка</h3><span>деньги и касса</span></div>\n   <div class="quick">\n    <div class="quick-item"><small>Карта</small><b id="pay-card">Нет данных</b></div>\n    <div class="quick-item"><small>Наличные</small><b id="pay-cash">Нет данных</b></div>\n    <div class="quick-item"><small>Скидки</small><b id="discounts">Нет данных</b></div>\n    <div class="quick-item"><small>Возвраты</small><b id="returns">Нет данных</b></div>\n    <div class="quick-item"><small>Последний чек</small><b id="last-check">Нет данных</b></div>\n    <div class="quick-item"><small>Лидер продаж</small><b id="leader">—</b></div>\n   </div>\n  </div>\n </section>\n\n <section class="grid">\n  <div class="card panel">\n   <div class="panel-head"><h3>Продажи</h3><span>динамика выбранного периода</span></div>\n   <div id="sales-chart" class="chart"></div>\n  </div>\n\n  <div class="card panel">\n   <div class="panel-head"><h3>Ресторан сейчас</h3><span>оперативный статус</span></div>\n   <div class="status-list">\n    <div class="status-row"><span>Агент</span><b id="agent-status"><span class="dot"></span>Проверка</b></div>\n    <div class="status-row"><span>Последний сигнал</span><b id="last-seen">—</b></div>\n    <div class="status-row"><span>Последняя синхронизация</span><b id="last-sync">—</b></div>\n    <div class="status-row"><span>Пиковый час</span><b id="peak">—</b></div>\n    <div class="status-row"><span>Позиций класса C</span><b id="class-c">—</b></div>\n    <div class="status-row"><span>Прогноз периода</span><b id="forecast">—</b></div>\n   </div>\n  </div>\n </section>\n\n <section class="bottom-grid">\n  <div class="card panel">\n   <div class="panel-head"><h3>Лидеры продаж</h3><span>ключевые позиции</span></div>\n   <div id="leaders-list" class="status-list"><div class="empty">Нет данных</div></div>\n  </div>\n  <div class="card panel">\n   <div class="panel-head"><h3>Последние умные события</h3><span>без технических снимков</span></div>\n   <div id="events-list" class="attention"><div class="empty">Нет значимых событий</div></div>\n  </div>\n </section>\n\n <div class="footer">Оплаты, скидки и возвраты появятся после подключения соответствующих запросов TillyPad.</div>\n</main>\n</div>\n\n<script>\nlet agent=\'gastrodom3\',period=\'today\';\nconst money=v=>new Intl.NumberFormat(\'ru-RU\',{maximumFractionDigits:0}).format(Number(v||0))+\' ₽\';\nconst num=v=>new Intl.NumberFormat(\'ru-RU\',{maximumFractionDigits:0}).format(Number(v||0));\nconst iso=d=>d.toISOString().slice(0,10);\nconst dt=v=>v?new Date(v).toLocaleString(\'ru-RU\',{day:\'2-digit\',month:\'short\',hour:\'2-digit\',minute:\'2-digit\'}):\'—\';\nconst api=async u=>{const r=await fetch(u);if(!r.ok)throw new Error(await r.text());return r.json()};\nfunction periodRange(){\n const n=new Date(),s=new Date(n),e=new Date(n),ps=new Date(n),pe=new Date(n);\n if(period===\'today\'){ps.setDate(ps.getDate()-1);pe.setDate(pe.getDate()-1)}\n if(period===\'yesterday\'){s.setDate(s.getDate()-1);e.setDate(e.getDate()-1);ps.setDate(ps.getDate()-2);pe.setDate(pe.getDate()-2)}\n if(period===\'week\'){s.setDate(s.getDate()-6);ps.setDate(ps.getDate()-13);pe.setDate(pe.getDate()-7)}\n return {from:iso(s),to:iso(e),pfrom:iso(ps),pto:iso(pe)}\n}\nfunction aggregate(data){\n const rows=data?.rows||data||[];\n return rows.reduce((a,x)=>({revenue:a.revenue+Number(x.revenue||0),checks:a.checks+Number(x.checks_count||x.orders||0)}),{revenue:0,checks:0});\n}\nfunction change(cur,prev){\n if(!prev)return {raw:0,text:\'нет базы сравнения\',cls:\'muted\'};\n const raw=(cur-prev)/prev*100;\n return {raw,text:`${raw>=0?\'▲\':\'▼\'} ${Math.abs(raw).toFixed(1)}%`,cls:raw>=0?\'good\':\'bad\'};\n}\nfunction setDelta(id,d){const el=document.getElementById(id);el.textContent=d.text;el.className=\'delta \'+d.cls}\nasync function init(){\n const agents=await api(\'/api/web/agents\').catch(()=>[]);\n const sel=document.getElementById(\'agent\');\n sel.innerHTML=(agents||[]).map(x=>`<option value="${x.agent_id}">${x.name||x.agent_id}</option>`).join(\'\');\n agent=agents?.[0]?.agent_id||\'gastrodom3\';sel.value=agent;sel.onchange=()=>{agent=sel.value;loadAll()};\n document.querySelectorAll(\'[data-period]\').forEach(b=>b.onclick=()=>{document.querySelectorAll(\'[data-period]\').forEach(x=>x.classList.remove(\'active\'));b.classList.add(\'active\');period=b.dataset.period;loadAll()});\n loadAll();\n}\nasync function loadAll(){\n const r=periodRange();\n document.getElementById(\'period-title\').textContent=`${r.from}${r.from!==r.to?\' — \'+r.to:\'\'}`;\n const [history,prev,status,latest,menu,report,events]=await Promise.all([\n  api(`/api/web/${agent}/sales/history?date_from=${r.from}&date_to=${r.to}`).catch(()=>[]),\n  api(`/api/web/${agent}/sales/history?date_from=${r.pfrom}&date_to=${r.pto}`).catch(()=>[]),\n  api(`/api/web/${agent}/status`).catch(()=>({})),\n  api(`/api/web/${agent}/sales/latest`).catch(()=>({})),\n  api(`/api/web/${agent}/menu/history?date_from=${r.from}&date_to=${r.to}`).catch(()=>({})),\n  api(`/api/web/${agent}/ai/director?date_from=${r.from}&date_to=${r.to}&previous_from=${r.pfrom}&previous_to=${r.pto}`).catch(()=>null),\n  api(`/api/web/${agent}/events?limit=40`).catch(()=>[])\n ]);\n const cur=aggregate(history),old=aggregate(prev),avg=cur.checks?cur.revenue/cur.checks:0,oldAvg=old.checks?old.revenue/old.checks:0;\n const rd=change(cur.revenue,old.revenue),ad=change(avg,oldAvg),cd=change(cur.checks,old.checks);\n document.getElementById(\'revenue\').textContent=money(cur.revenue);\n document.getElementById(\'avg\').textContent=money(avg);\n document.getElementById(\'checks\').textContent=num(cur.checks);\n document.getElementById(\'pace\').textContent=(rd.raw>=0?\'+\':\'\')+rd.raw.toFixed(1)+\'%\';\n setDelta(\'revenue-delta\',rd);setDelta(\'avg-delta\',ad);setDelta(\'checks-delta\',cd);\n document.getElementById(\'pace-note\').className=\'delta \'+rd.cls;\n const score=report?.health_score?.score??report?.score??0;\n document.getElementById(\'score\').textContent=score||\'—\';\n const scoreStatus=score>=80?\'Хорошее состояние\':score>=60?\'Требует внимания\':score?\'Высокий риск\':\'Нет данных\';\n const se=document.getElementById(\'score-status\');se.textContent=scoreStatus;se.className=\'status \'+(score>=80?\'good\':score>=60?\'warn\':score?\'bad\':\'muted\');\n const top=getTop(menu);\n const leader=top[0]?.item_name||top[0]?.name||\'Не определён\';\n document.getElementById(\'leader\').textContent=leader;\n const online=Boolean(status?.online||status?.connected||status?.status===\'online\');\n document.getElementById(\'agent-status\').innerHTML=`<span class="dot" style="background:${online?\'var(--green)\':\'var(--red)\'}"></span>${online?\'Онлайн\':\'Не в сети\'}`;\n document.getElementById(\'last-seen\').textContent=dt(status?.last_seen_at||status?.last_heartbeat_at);\n document.getElementById(\'last-sync\').textContent=dt(latest?.captured_at||latest?.created_at);\n document.getElementById(\'peak\').textContent=latest?.peak_hour||\'Нет данных\';\n document.getElementById(\'class-c\').textContent=menu?.abc?.C?.count??menu?.class_c_count??\'Нет данных\';\n document.getElementById(\'last-check\').textContent=latest?.last_check_at?dt(latest.last_check_at):\'Нет данных\';\n [\'pay-card\',\'pay-cash\',\'discounts\',\'returns\'].forEach(id=>document.getElementById(id).textContent=\'Нет данных\');\n const forecast=period===\'today\'?cur.revenue*1.25:cur.revenue;\n document.getElementById(\'forecast\').textContent=money(forecast);\n const title=rd.raw>=5?\'Ресторан идёт лучше прошлого периода\':rd.raw<=-5?\'Темп продаж ниже прошлого периода\':\'Ресторан работает стабильно\';\n document.getElementById(\'brief-title\').textContent=title;\n document.getElementById(\'brief-text\').innerHTML=`Выручка — <b>${money(cur.revenue)}</b>, чеков — <b>${num(cur.checks)}</b>, средний чек — <b>${money(avg)}</b>. ${ad.raw<0?\'Средний чек требует внимания.\':\'Критических отклонений по среднему чеку нет.\'} Лидер продаж — <b>${leader}</b>.`;\n renderAttention(events,rd,ad,online,menu);\n renderEvents(events);\n renderLeaders(top);\n renderChart(history);\n}\nfunction getTop(menu){\n if(Array.isArray(menu?.top_items))return menu.top_items;\n if(Array.isArray(menu?.items))return menu.items;\n if(Array.isArray(menu?.rows))return menu.rows;\n return [];\n}\nfunction renderAttention(events,rd,ad,online,menu){\n const list=[];\n if(!online)list.push({c:\'critical\',t:\'Агент не в сети\',d:\'Свежие данные могут не поступать.\',e:\'Проверить\'});\n if(rd.raw<-5)list.push({c:\'critical\',t:\'Выручка отстаёт\',d:`Снижение ${Math.abs(rd.raw).toFixed(1)}% к прошлому периоду.`,e:\'Действие\'});\n if(ad.raw<-5)list.push({c:\'\',t:\'Средний чек снизился\',d:`Падение ${Math.abs(ad.raw).toFixed(1)}%.`,e:\'Комбо\'});\n const c=menu?.abc?.C?.count??menu?.class_c_count;\n if(Number(c)>0)list.push({c:\'\',t:`${c} позиций класса C`,d:\'Низкий вклад в выручку — нужен пересмотр.\',e:\'Меню\'});\n const smart=(events||[]).filter(x=>x.event_type!==\'snapshot_created\').slice(0,2);\n smart.forEach(x=>list.push({c:x.severity===\'critical\'?\'critical\':x.severity===\'success\'?\'ok\':\'\',t:x.title,d:x.description,e:x.source}));\n if(!list.length)list.push({c:\'ok\',t:\'Критических проблем нет\',d:\'Основные показатели находятся в нормальном диапазоне.\',e:\'Норма\'});\n document.getElementById(\'attention-list\').innerHTML=list.slice(0,5).map(x=>`<div class="attn ${x.c}"><div class="rail"></div><div><b>${x.t}</b><p>${x.d}</p></div><em>${x.e}</em></div>`).join(\'\');\n}\nfunction renderEvents(events){\n const smart=(events||[]).filter(x=>x.event_type!==\'snapshot_created\').slice(0,4);\n document.getElementById(\'events-list\').innerHTML=smart.length?smart.map(x=>`<div class="attn ${x.severity===\'critical\'?\'critical\':x.severity===\'success\'?\'ok\':\'\'}"><div class="rail"></div><div><b>${x.title}</b><p>${x.description}</p></div><em>${x.score||\'\'}</em></div>`).join(\'\'):\'<div class="empty">Значимых событий пока нет</div>\';\n}\nfunction renderLeaders(items){\n document.getElementById(\'leaders-list\').innerHTML=items.slice(0,5).map((x,i)=>`<div class="status-row"><span>${i+1}. ${x.item_name||x.name||\'Без названия\'}</span><b>${money(x.revenue||0)}</b></div>`).join(\'\')||\'<div class="empty">Нет данных</div>\';\n}\nfunction renderChart(history){\n const rows=history?.rows||history||[];\n const chart=echarts.init(document.getElementById(\'sales-chart\'));\n chart.setOption({grid:{left:45,right:12,top:18,bottom:32},tooltip:{trigger:\'axis\'},xAxis:{type:\'category\',boundaryGap:false,data:rows.map(x=>x.business_date||x.date||\'\')},yAxis:{type:\'value\'},series:[{type:\'line\',smooth:true,symbol:\'none\',lineStyle:{width:3},areaStyle:{opacity:.07},data:rows.map(x=>Number(x.revenue||0))}]});\n}\ninit().catch(e=>{document.getElementById(\'brief-title\').textContent=\'Не удалось загрузить данные\';document.getElementById(\'brief-text\').textContent=e.message});\n</script>\n</body>\n</html>\n')

    @router.get(
        "/finance",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def finance_page(request: Request):
        require_browser_session(request)
        return templates.TemplateResponse(
            request=request,
            name="finance.html",
            context={
                "app_version": "10.4.7",
                "product_name": "Restaurant OS",
            },
        )

    @router.get(
        "/api/web/{agent_id}/finance/summary",
        include_in_schema=False,
    )
    def web_finance_summary(
        agent_id: str,
        request: Request,
        date_from: str,
        date_to: str,
    ):
        require_browser_session(request)

        # Lightweight compatibility recovery for snapshots created while
        # Gateway had not yet migrated to payments_json.
        storage.recover_payments_from_payloads(agent_id)

        return storage.finance_summary(
            agent_id,
            date_from,
            date_to,
        )

    @router.get(
        "/api/web/{agent_id}/finance/payments/diagnostics",
        include_in_schema=False,
    )
    def web_finance_payment_diagnostics(
        agent_id: str,
        request: Request,
        date_from: str,
        date_to: str,
    ):
        require_browser_session(request)
        return storage.payment_persistence_diagnostics(
            agent_id,
            date_from,
            date_to,
        )

    @router.post(
        "/api/web/{agent_id}/finance/payments/recover",
        include_in_schema=False,
    )
    def recover_web_finance_payments(
        agent_id: str,
        request: Request,
    ):
        require_browser_session(request)
        return storage.recover_payments_from_payloads(
            agent_id
        )

    @router.post(
        "/api/web/{agent_id}/finance/operations",
        include_in_schema=False,
    )
    def create_web_finance_operation(
        agent_id: str,
        payload: FinanceOperationPayload,
        request: Request,
    ):
        require_browser_session(request)
        try:
            return storage.create_finance_operation(
                agent_id,
                operation_date=payload.operation_date.isoformat(),
                operation_type=payload.operation_type,
                category=payload.category,
                amount=payload.amount,
                description=payload.description,
            )
        except ValueError as exc:
            return JSONResponse(
                {"detail": str(exc)},
                status_code=400,
            )

    @router.put(
        "/api/web/{agent_id}/finance/operations/{operation_id}",
        include_in_schema=False,
    )
    def update_web_finance_operation(
        agent_id: str,
        operation_id: int,
        payload: FinanceOperationPayload,
        request: Request,
    ):
        require_browser_session(request)
        try:
            return storage.update_finance_operation(
                agent_id,
                operation_id,
                operation_date=payload.operation_date.isoformat(),
                operation_type=payload.operation_type,
                category=payload.category,
                amount=payload.amount,
                description=payload.description,
            )
        except KeyError:
            return JSONResponse(
                {"detail": "Операция не найдена"},
                status_code=404,
            )
        except ValueError as exc:
            return JSONResponse(
                {"detail": str(exc)},
                status_code=400,
            )

    @router.delete(
        "/api/web/{agent_id}/finance/operations/{operation_id}",
        include_in_schema=False,
    )
    def delete_web_finance_operation(
        agent_id: str,
        operation_id: int,
        request: Request,
    ):
        require_browser_session(request)
        deleted = storage.delete_finance_operation(
            agent_id,
            operation_id,
        )
        if not deleted:
            return JSONResponse(
                {"detail": "Операция не найдена"},
                status_code=404,
            )
        return {"ok": True}

    @router.get(
        "/settings",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def restaurant_settings_page(request: Request):
        require_browser_session(request)
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "app_version": "10.4.7",
                "product_name": "Restaurant OS",
            },
        )

    @router.get(
        "/api/web/{agent_id}/settings",
        include_in_schema=False,
    )
    def web_restaurant_settings(
        agent_id: str,
        request: Request,
    ):
        require_browser_session(request)
        return storage.get_restaurant_settings(agent_id)

    @router.put(
        "/api/web/{agent_id}/settings",
        include_in_schema=False,
    )
    def update_web_restaurant_settings(
        agent_id: str,
        payload: RestaurantSettingsUpdate,
        request: Request,
    ):
        require_browser_session(request)
        return storage.update_restaurant_settings(
            agent_id,
            daily_revenue_plan=payload.daily_revenue_plan,
        )

    @router.get(
        "/dashboard",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def dashboard_v8(request: Request):
        require_browser_session(request)
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "app_version": "10.4.7",
                "product_name": "Restaurant OS",
            },
        )
        require_browser_session(request)
        return HTMLResponse('\n<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>Restaurant OS 7</title>\n<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>\n<style>\n:root{\n --bg:#f4f5f7;--card:#fff;--text:#17191d;--muted:#737983;\n --line:#e7e9ed;--dark:#171a1f;--green:#198754;--amber:#c47a19;\n --red:#c73e36;--blue:#2f7897;--radius:18px;--shadow:0 8px 26px rgba(16,24,40,.05)\n}\n*{box-sizing:border-box}\nhtml,body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}\n.layout{display:grid;grid-template-columns:225px minmax(0,1fr);min-height:100vh}\n.sidebar{background:#14171c;color:#fff;padding:21px 14px;position:sticky;top:0;height:100vh}\n.brand{display:flex;align-items:center;gap:11px;padding:4px 8px 24px}\n.brand-badge{width:40px;height:40px;border-radius:12px;background:#fff;color:#111;display:grid;place-items:center;font-weight:900}\n.brand strong{display:block;font-size:17px}.brand small{color:#8c94a0}\n.nav-title{margin:19px 9px 7px;color:#68717f;font-size:10px;font-weight:800;letter-spacing:.15em;text-transform:uppercase}\n.nav a{display:flex;gap:11px;align-items:center;padding:10px 11px;border-radius:10px;text-decoration:none;color:#bec4cd;font-size:14px;margin:2px 0}\n.nav a:hover,.nav a.active{background:#252a32;color:#fff}.nav i{width:20px;text-align:center;font-style:normal}\n.version{position:absolute;bottom:18px;left:20px;color:#69727e;font-size:11px}\nmain{max-width:1540px;width:100%;margin:auto;padding:22px 27px 48px}\n.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}\n.topbar h1{margin:0;font-size:23px}.topbar p{margin:4px 0 0;color:var(--muted);font-size:13px}\n.filters{display:flex;gap:7px;align-items:center;flex-wrap:wrap}\nselect,.pill{border:1px solid var(--line);background:#fff;border-radius:10px;padding:9px 12px;font:inherit}\n.pill{cursor:pointer}.pill.active{background:var(--dark);border-color:var(--dark);color:#fff}\n.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}\n.hero{padding:23px;display:grid;grid-template-columns:minmax(0,1fr) 205px;gap:20px;margin-bottom:13px}\n.eyebrow{font-size:11px;text-transform:uppercase;letter-spacing:.15em;font-weight:850;color:var(--blue)}\n.hero h2{font-size:28px;margin:8px 0 9px;line-height:1.15}\n.hero p{margin:0;color:#505661;line-height:1.55;font-size:15px;max-width:920px}\n.hero-meta{display:flex;gap:14px;align-items:center;margin-top:14px;color:var(--muted);font-size:12px}\n.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--green);margin-right:6px}\n.score{border-left:1px solid var(--line);padding-left:21px;display:flex;flex-direction:column;justify-content:center}\n.score small{color:var(--muted);text-transform:uppercase;letter-spacing:.09em}\n.score b{font-size:55px;line-height:1;margin:7px 0}.score span{font-size:13px;font-weight:750}\n.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:13px}\n.kpi{padding:17px}.kpi small{color:var(--muted)}.kpi b{display:block;font-size:29px;margin:7px 0 5px}.delta{font-size:12px;font-weight:750}\n.good{color:var(--green)}.bad{color:var(--red)}.warn{color:var(--amber)}.muted{color:var(--muted)}\n.grid-main{display:grid;grid-template-columns:1.12fr .88fr;gap:13px;margin-bottom:13px}\n.panel{padding:18px}.panel-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}\n.panel-head h3{margin:0;font-size:17px}.panel-head span{font-size:12px;color:var(--muted)}\n.attention{display:grid;gap:8px}\n.issue{display:grid;grid-template-columns:7px 1fr auto;gap:11px;align-items:start;padding:12px;border:1px solid var(--line);border-radius:12px}\n.issue .rail{height:100%;min-height:38px;border-radius:99px;background:var(--amber)}\n.issue.critical .rail{background:var(--red)}.issue.ok .rail{background:var(--green)}\n.issue b{font-size:14px}.issue p{margin:4px 0 0;color:var(--muted);font-size:12px}.issue em{font-style:normal;font-size:11px;font-weight:800;white-space:nowrap}\n.express{display:grid;grid-template-columns:repeat(2,1fr);gap:9px}\n.express-item{padding:12px;border:1px solid var(--line);border-radius:12px;background:#fafbfc}\n.express-item small{color:var(--muted)}.express-item b{display:block;margin-top:6px;font-size:18px}\n.chart{height:265px}\n.now-list,.leaders{display:grid}.now-row,.leader-row{display:flex;justify-content:space-between;gap:14px;padding:11px 0;border-bottom:1px solid var(--line)}\n.now-row:last-child,.leader-row:last-child{border-bottom:0}.now-row span:first-child,.leader-row span:first-child{color:#555c66}\n.recommendations{display:grid;gap:8px}.rec{padding:13px;border:1px solid var(--line);border-radius:12px}\n.rec b{display:block;font-size:14px}.rec p{margin:5px 0 0;color:var(--muted);font-size:12px;line-height:1.4}\n.empty{color:var(--muted);text-align:center;padding:20px 0}\n.note{margin-top:10px;color:#8b9199;font-size:11px;text-align:right}\n@media(max-width:1050px){.layout{grid-template-columns:74px 1fr}.brand strong,.brand small,.nav-title,.nav span,.version{display:none}.brand{justify-content:center}.nav a{justify-content:center}.kpis{grid-template-columns:repeat(2,1fr)}}\n@media(max-width:740px){.layout{display:block}.sidebar{position:static;height:auto;padding:8px;overflow:auto}.brand,.nav-title,.version{display:none}.nav{display:flex}.nav a{white-space:nowrap}.nav span{display:inline}main{padding:13px}.filters{display:none}.hero{grid-template-columns:1fr}.score{border-left:0;border-top:1px solid var(--line);padding:15px 0 0}.kpis,.grid-main{grid-template-columns:1fr}}\n</style>\n</head>\n<body>\n<div class="layout">\n<aside class="sidebar">\n <div class="brand"><div class="brand-badge">R</div><div><strong>Restaurant OS</strong><small>Director workspace</small></div></div>\n <nav class="nav">\n  <div class="nav-title">Рабочий стол</div>\n  <a class="active" href="/dashboard"><i>⌂</i><span>Сегодня</span></a>\n  <a href="/dashboard-old"><i>◫</i><span>Старая панель</span></a>\n  <div class="nav-title">Управление</div>\n  <a href="/dashboard-old"><i>◆</i><span>Центр решений</span></a>\n  <a href="/dashboard-old"><i>◒</i><span>Меню</span></a>\n  <a href="/dashboard-old"><i>₽</i><span>Финансы</span></a>\n  <a href="/dashboard-old"><i>→</i><span>Доставка</span></a>\n </nav>\n <div class="version">Restaurant OS 7.0.0</div>\n</aside>\n\n<main>\n <header class="topbar">\n  <div><h1>Сегодня</h1><p id="date-title">Рабочий стол директора</p></div>\n  <div class="filters">\n   <select id="agent-select"></select>\n   <button class="pill active" data-period="today">Сегодня</button>\n   <button class="pill" data-period="yesterday">Вчера</button>\n   <button class="pill" data-period="week">7 дней</button>\n   <button class="pill" data-period="month">Этот месяц</button>\n   <button class="pill" data-period="prevmonth">Прошлый месяц</button>\n  </div>\n </header>\n\n <section class="card hero">\n  <div>\n   <div class="eyebrow">Цифровой управляющий</div>\n   <h2 id="hero-title">Загружаю состояние ресторана</h2>\n   <p id="hero-text">Собираю показатели и формирую краткий управленческий вывод.</p>\n   <div class="hero-meta">\n    <span id="agent-state"><span class="dot"></span>Проверяю соединение</span>\n    <span id="sync-state">Синхронизация: —</span>\n   </div>\n  </div>\n  <div class="score">\n   <small>Индекс ресторана</small>\n   <b id="score">—</b>\n   <span id="score-status" class="muted">Нет данных</span>\n  </div>\n </section>\n\n <section class="kpis">\n  <div class="card kpi"><small>Выручка сегодня</small><b id="revenue">—</b><div id="revenue-delta" class="delta muted">—</div></div>\n  <div class="card kpi"><small>Средний чек</small><b id="average">—</b><div id="average-delta" class="delta muted">—</div></div>\n  <div class="card kpi"><small>Чеков</small><b id="checks">—</b><div id="checks-delta" class="delta muted">—</div></div>\n  <div class="card kpi"><small>Прогноз периода</small><b id="forecast">—</b><div class="delta muted">по текущему темпу</div></div>\n </section>\n\n <section class="grid-main">\n  <div class="card panel">\n   <div class="panel-head"><h3>Требует внимания</h3><span>не более пяти пунктов</span></div>\n   <div id="attention" class="attention"><div class="empty">Анализирую показатели…</div></div>\n  </div>\n  <div class="card panel">\n   <div class="panel-head"><h3>Экспресс-сводка</h3><span>касса и деньги</span></div>\n   <div class="express">\n    <div class="express-item"><small>Карта</small><b>Нет данных</b></div>\n    <div class="express-item"><small>Наличные</small><b>Нет данных</b></div>\n    <div class="express-item"><small>QR / прочее</small><b>Нет данных</b></div>\n    <div class="express-item"><small>Скидки</small><b>Нет данных</b></div>\n    <div class="express-item"><small>Возвраты</small><b>Нет данных</b></div>\n    <div class="express-item"><small>Последний чек</small><b id="last-check">Нет данных</b></div>\n   </div>\n  </div>\n </section>\n\n <section class="grid-main">\n  <div class="card panel">\n   <div class="panel-head"><h3>Продажи по времени</h3><span id="chart-caption">сегодня</span></div>\n   <div id="sales-chart" class="chart"></div>\n  </div>\n  <div class="card panel">\n   <div class="panel-head"><h3>Ресторан сейчас</h3><span>оперативный статус</span></div>\n   <div class="now-list">\n    <div class="now-row"><span>Последний сигнал</span><b id="last-seen">—</b></div>\n    <div class="now-row"><span>Последняя синхронизация</span><b id="last-sync">—</b></div>\n    <div class="now-row"><span>Пиковый час</span><b id="peak-hour">—</b></div>\n    <div class="now-row"><span>Лидер продаж</span><b id="leader">—</b></div>\n    <div class="now-row"><span>Позиций класса C</span><b id="class-c">—</b></div>\n    <div class="now-row"><span>Состояние данных</span><b id="data-health">—</b></div>\n   </div>\n  </div>\n </section>\n\n <section class="grid-main">\n  <div class="card panel">\n   <div class="panel-head"><h3>ТОП продаж</h3><span>пять позиций</span></div>\n   <div id="leaders" class="leaders"><div class="empty">Нет данных</div></div>\n  </div>\n  <div class="card panel">\n   <div class="panel-head"><h3>ИИ рекомендует</h3><span>без технических событий</span></div>\n   <div id="recommendations" class="recommendations"><div class="empty">Нет рекомендаций</div></div>\n  </div>\n </section>\n\n <div class="note">Оплаты, скидки и возвраты появятся после подключения соответствующих запросов TillyPad.</div>\n</main>\n</div>\n\n<script>\nlet agent=\'gastrodom3\';\nlet period=\'today\';\n\nconst money=v=>new Intl.NumberFormat(\'ru-RU\',{maximumFractionDigits:0}).format(Number(v||0))+\' ₽\';\nconst integer=v=>new Intl.NumberFormat(\'ru-RU\',{maximumFractionDigits:0}).format(Number(v||0));\nconst iso=d=>d.toISOString().slice(0,10);\nconst localTime=v=>v?new Date(v).toLocaleString(\'ru-RU\',{day:\'2-digit\',month:\'short\',hour:\'2-digit\',minute:\'2-digit\'}):\'—\';\nconst api=async u=>{const r=await fetch(u);if(!r.ok)throw new Error(await r.text());return r.json()};\n\nfunction ranges(){\n const now=new Date(),from=new Date(now),to=new Date(now),pf=new Date(now),pt=new Date(now);\n if(period===\'today\'){pf.setDate(pf.getDate()-1);pt.setDate(pt.getDate()-1)}\n if(period===\'yesterday\'){from.setDate(from.getDate()-1);to.setDate(to.getDate()-1);pf.setDate(pf.getDate()-2);pt.setDate(pt.getDate()-2)}\n if(period===\'week\'){from.setDate(from.getDate()-6);pf.setDate(pf.getDate()-13);pt.setDate(pt.getDate()-7)}\n if(period===\'month\'){from.setDate(1);pf.setMonth(pf.getMonth()-1,1);pt.setMonth(pt.getMonth()+1,0)}\n if(period===\'prevmonth\'){from.setMonth(from.getMonth()-1,1);to.setDate(0);pf.setMonth(pf.getMonth()-2,1);pt.setMonth(pt.getMonth()+1,0)}\n return {from:iso(from),to:iso(to),pf:iso(pf),pt:iso(pt)}\n}\n\nfunction aggregate(data){\n const rows=data?.rows||data||[];\n return rows.reduce((a,x)=>({\n  revenue:a.revenue+Number(x.revenue||0),\n  checks:a.checks+Number(x.checks_count||x.orders||0)\n }),{revenue:0,checks:0});\n}\n\nfunction comparison(current,previous){\n if(!previous)return {raw:0,text:\'нет базы сравнения\',cls:\'muted\'};\n const raw=(current-previous)/previous*100;\n return {raw,text:`${raw>=0?\'▲\':\'▼\'} ${Math.abs(raw).toFixed(1)}% к прошлому периоду`,cls:raw>=0?\'good\':\'bad\'};\n}\n\nfunction setDelta(id,value){\n const el=document.getElementById(id);\n el.textContent=value.text;\n el.className=\'delta \'+value.cls;\n}\n\nasync function initialize(){\n const agents=await api(\'/api/web/agents\').catch(()=>[]);\n const select=document.getElementById(\'agent-select\');\n select.innerHTML=(agents||[]).map(x=>`<option value="${x.agent_id}">${x.name||x.agent_id}</option>`).join(\'\');\n agent=agents?.[0]?.agent_id||\'gastrodom3\';\n select.value=agent;\n select.onchange=()=>{agent=select.value;loadDashboard()};\n\n document.querySelectorAll(\'[data-period]\').forEach(button=>{\n  button.onclick=()=>{\n   document.querySelectorAll(\'[data-period]\').forEach(x=>x.classList.remove(\'active\'));\n   button.classList.add(\'active\');\n   period=button.dataset.period;\n   loadDashboard();\n  };\n });\n\n period=\'today\';\n await loadDashboard();\n}\n\nasync function loadDashboard(){\n const r=ranges();\n document.getElementById(\'date-title\').textContent=`${r.from}${r.from!==r.to?\' — \'+r.to:\'\'}`;\n document.getElementById(\'chart-caption\').textContent=period===\'today\'?\'сегодня\':`${r.from} — ${r.to}`;\n\n const [history,previous,status,latest,menu,report,events]=await Promise.all([\n  api(`/api/web/${agent}/sales/history?date_from=${r.from}&date_to=${r.to}`).catch(()=>[]),\n  api(`/api/web/${agent}/sales/history?date_from=${r.pf}&date_to=${r.pt}`).catch(()=>[]),\n  api(`/api/web/${agent}/status`).catch(()=>({})),\n  api(`/api/web/${agent}/sales/latest`).catch(()=>({})),\n  api(`/api/web/${agent}/menu/history?date_from=${r.from}&date_to=${r.to}`).catch(()=>({})),\n  api(`/api/web/${agent}/ai/director?date_from=${r.from}&date_to=${r.to}&previous_from=${r.pf}&previous_to=${r.pt}`).catch(()=>null),\n  api(`/api/web/${agent}/events?limit=40`).catch(()=>[])\n ]);\n\n const cur=aggregate(history),old=aggregate(previous);\n const avg=cur.checks?cur.revenue/cur.checks:0;\n const oldAvg=old.checks?old.revenue/old.checks:0;\n const revenueDelta=comparison(cur.revenue,old.revenue);\n const avgDelta=comparison(avg,oldAvg);\n const checksDelta=comparison(cur.checks,old.checks);\n\n document.getElementById(\'revenue\').textContent=money(cur.revenue);\n document.getElementById(\'average\').textContent=money(avg);\n document.getElementById(\'checks\').textContent=integer(cur.checks);\n setDelta(\'revenue-delta\',revenueDelta);\n setDelta(\'average-delta\',avgDelta);\n setDelta(\'checks-delta\',checksDelta);\n\n const forecast=period===\'today\'?cur.revenue*1.25:cur.revenue;\n document.getElementById(\'forecast\').textContent=money(forecast);\n\n const score=report?.health_score?.score??report?.score??0;\n document.getElementById(\'score\').textContent=score||\'—\';\n const scoreStatus=score>=80?\'Хорошее состояние\':score>=60?\'Требует внимания\':score?\'Высокий риск\':\'Нет данных\';\n const scoreNode=document.getElementById(\'score-status\');\n scoreNode.textContent=scoreStatus;\n scoreNode.className=score>=80?\'good\':score>=60?\'warn\':score?\'bad\':\'muted\';\n\n const online=Boolean(status?.online||status?.connected||status?.status===\'online\');\n document.getElementById(\'agent-state\').innerHTML=`<span class="dot" style="background:${online?\'var(--green)\':\'var(--red)\'}"></span>${online?\'Агент подключён\':\'Агент не в сети\'}`;\n document.getElementById(\'sync-state\').textContent=`Синхронизация: ${localTime(latest?.captured_at||latest?.created_at)}`;\n document.getElementById(\'last-seen\').textContent=localTime(status?.last_seen_at||status?.last_heartbeat_at);\n document.getElementById(\'last-sync\').textContent=localTime(latest?.captured_at||latest?.created_at);\n\n const top=getTop(menu);\n const leader=top[0]?.item_name||top[0]?.name||\'Не определён\';\n document.getElementById(\'leader\').textContent=leader;\n document.getElementById(\'peak-hour\').textContent=latest?.peak_hour||\'Нет данных\';\n document.getElementById(\'class-c\').textContent=menu?.abc?.C?.count??menu?.class_c_count??\'Нет данных\';\n document.getElementById(\'last-check\').textContent=latest?.last_check_at?localTime(latest.last_check_at):\'Нет данных\';\n document.getElementById(\'data-health\').textContent=online?\'Данные поступают\':\'Требуется проверка\';\n\n const title=revenueDelta.raw>=5?\'Сегодня ресторан идёт лучше прошлого периода\':revenueDelta.raw<=-5?\'Сегодня темп продаж ниже прошлого периода\':\'Ресторан работает стабильно\';\n document.getElementById(\'hero-title\').textContent=title;\n document.getElementById(\'hero-text\').innerHTML=`Выручка — <b>${money(cur.revenue)}</b>, чеков — <b>${integer(cur.checks)}</b>, средний чек — <b>${money(avg)}</b>. ${avgDelta.raw<0?\'Средний чек требует внимания.\':\'Критических отклонений по среднему чеку нет.\'} Лидер продаж — <b>${leader}</b>.`;\n\n renderAttention(events,revenueDelta,avgDelta,online,menu);\n renderRecommendations(events,revenueDelta,avgDelta,menu);\n renderLeaders(top);\n renderChart(history,latest);\n}\n\nfunction getTop(menu){\n if(Array.isArray(menu?.top_items))return menu.top_items;\n if(Array.isArray(menu?.items))return menu.items;\n if(Array.isArray(menu?.rows))return menu.rows;\n return [];\n}\n\nfunction renderAttention(events,revenueDelta,avgDelta,online,menu){\n const list=[];\n if(!online)list.push({type:\'critical\',title:\'Агент не в сети\',text:\'Свежие показатели могут не поступать.\',tag:\'Проверить\'});\n if(revenueDelta.raw<-5)list.push({type:\'critical\',title:\'Выручка ниже прошлого периода\',text:`Отставание ${Math.abs(revenueDelta.raw).toFixed(1)}%.`,tag:\'Продажи\'});\n if(avgDelta.raw<-5)list.push({type:\'\',title:\'Средний чек снизился\',text:`Падение ${Math.abs(avgDelta.raw).toFixed(1)}%. Нужны допродажи и комбо.`,tag:\'Допродажи\'});\n const c=menu?.abc?.C?.count??menu?.class_c_count;\n if(Number(c)>0)list.push({type:\'\',title:`${c} позиций класса C`,text:\'Низкий вклад в выручку — требуется анализ меню.\',tag:\'Меню\'});\n const smart=(events||[]).filter(x=>x.event_type!==\'snapshot_created\').slice(0,2);\n smart.forEach(x=>list.push({\n  type:x.severity===\'critical\'?\'critical\':x.severity===\'success\'?\'ok\':\'\',\n  title:x.title,\n  text:x.description,\n  tag:x.source||\'Событие\'\n }));\n if(!list.length)list.push({type:\'ok\',title:\'Критических проблем нет\',text:\'Основные показатели находятся в нормальном диапазоне.\',tag:\'Норма\'});\n document.getElementById(\'attention\').innerHTML=list.slice(0,5).map(x=>`<div class="issue ${x.type}"><div class="rail"></div><div><b>${x.title}</b><p>${x.text}</p></div><em>${x.tag}</em></div>`).join(\'\');\n}\n\nfunction renderRecommendations(events,revenueDelta,avgDelta,menu){\n const rec=[];\n if(avgDelta.raw<-3)rec.push({title:\'Усилить допродажи\',text:\'Предлагать напиток или гарнир к каждому третьему заказу.\'});\n if(revenueDelta.raw<-5)rec.push({title:\'Восстановить темп продаж\',text:\'Проверить акции и продвижение в слабые часы.\'});\n const c=menu?.abc?.C?.count??menu?.class_c_count;\n if(Number(c)>0)rec.push({title:\'Проверить класс C\',text:`Пересмотреть ${c} слабых позиций: убрать, объединить в комбо или изменить цену.`});\n const smart=(events||[]).filter(x=>x.event_type!==\'snapshot_created\'&&x.severity!==\'info\').slice(0,2);\n smart.forEach(x=>rec.push({title:x.title,text:x.description}));\n if(!rec.length)rec.push({title:\'Сохранять текущий темп\',text:\'Критических отклонений нет. Контролировать средний чек и наличие лидеров меню.\'});\n document.getElementById(\'recommendations\').innerHTML=rec.slice(0,4).map(x=>`<div class="rec"><b>${x.title}</b><p>${x.text}</p></div>`).join(\'\');\n}\n\nfunction renderLeaders(items){\n document.getElementById(\'leaders\').innerHTML=items.slice(0,5).map((x,i)=>`<div class="leader-row"><span>${i+1}. ${x.item_name||x.name||\'Без названия\'}</span><b>${money(x.revenue||0)}</b></div>`).join(\'\')||\'<div class="empty">Нет данных</div>\';\n}\n\nfunction renderChart(history,latest){\n const rows=history?.rows||history||[];\n let labels=rows.map(x=>x.business_date||x.date||\'\');\n let values=rows.map(x=>Number(x.revenue||0));\n\n if(period===\'today\' && latest?.hourly?.rows){\n  const columns=latest.hourly.columns||[];\n  labels=latest.hourly.rows.map(row=>{\n   const obj=Object.fromEntries(columns.map((c,i)=>[c,row[i]]));\n   return String(obj.hour??obj.sale_hour??\'\');\n  });\n  values=latest.hourly.rows.map(row=>{\n   const obj=Object.fromEntries(columns.map((c,i)=>[c,row[i]]));\n   return Number(obj.revenue||0);\n  });\n }\n\n const chart=echarts.init(document.getElementById(\'sales-chart\'));\n chart.setOption({\n  grid:{left:48,right:14,top:18,bottom:34},\n  tooltip:{trigger:\'axis\'},\n  xAxis:{type:\'category\',boundaryGap:false,data:labels},\n  yAxis:{type:\'value\'},\n  series:[{\n   type:\'line\',smooth:true,symbol:\'none\',lineStyle:{width:3},\n   areaStyle:{opacity:.08},data:values\n  }]\n });\n}\n\ninitialize().catch(error=>{\n document.getElementById(\'hero-title\').textContent=\'Не удалось загрузить рабочий стол\';\n document.getElementById(\'hero-text\').textContent=error.message;\n});\n</script>\n</body>\n</html>\n')


    return router
