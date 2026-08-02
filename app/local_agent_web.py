from __future__ import annotations

import html
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from app.agent_state import get_runtime_state
from app.agent_config import reload_config


LOGGER = logging.getLogger("restaurantos.local_web")


PAGE = r"""
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Restaurant OS Agent</title>
<style>
:root {
  --bg:#f3efe9;
  --card:#fff;
  --text:#211915;
  --muted:#796d66;
  --line:#ded4cc;
  --red:#ad3024;
  --green:#407b5d;
  --amber:#cf8527;
  --blue:#347c98;
}
*{box-sizing:border-box}
body{
  margin:0;
  background:var(--bg);
  color:var(--text);
  font-family:Segoe UI,Arial,sans-serif;
}
main{max-width:1180px;margin:0 auto;padding:28px}
header{
  display:flex;justify-content:space-between;gap:20px;
  align-items:flex-start;margin-bottom:22px
}
h1{font-size:40px;margin:0 0 6px}
.subtitle{color:var(--muted);font-size:18px}
.badge{
  border:1px solid var(--line);border-radius:18px;background:#fff;
  padding:12px 18px;font-weight:700
}
.grid{
  display:grid;grid-template-columns:repeat(4,1fr);gap:14px
}
.card{
  background:var(--card);border:1px solid var(--line);
  border-radius:18px;padding:20px;box-shadow:0 8px 24px rgba(45,30,20,.04)
}
.card h2{font-size:14px;color:var(--muted);margin:0 0 12px;font-weight:500}
.value{font-size:27px;font-weight:750;overflow-wrap:anywhere}
.ok{color:var(--green)}
.bad{color:var(--red)}
.warn{color:var(--amber)}
.info{color:var(--blue)}
.wide{grid-column:span 2}
.full{grid-column:1/-1}
table{width:100%;border-collapse:collapse}
td{padding:11px 4px;border-bottom:1px solid var(--line);vertical-align:top}
td:first-child{width:230px;color:var(--muted)}
pre{
  background:#201b18;color:#eee;padding:18px;border-radius:14px;
  min-height:260px;max-height:520px;overflow:auto;white-space:pre-wrap
}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
button{
  border:0;border-radius:10px;padding:10px 15px;
  font-weight:700;cursor:pointer;background:var(--red);color:#fff
}
button.secondary{background:#6e625b}
@media(max-width:900px){
  .grid{grid-template-columns:1fr 1fr}
  .wide{grid-column:span 2}
}
@media(max-width:560px){
  main{padding:14px}
  header{display:block}
  h1{font-size:30px}
  .grid{grid-template-columns:1fr}
  .wide,.full{grid-column:span 1}
}
</style>
</head>
<body>
<main>
<header>
  <div>
    <div style="color:#ad3024;font-weight:800;letter-spacing:.12em">ЛОКАЛЬНАЯ ДИАГНОСТИКА</div>
    <h1>Restaurant OS Agent</h1>
    <div class="subtitle">Служба, SQL Server, Gateway и текущая активность агента.</div>
  </div>
  <div class="badge" id="version">Загрузка...</div>
</header>

<section class="grid">
  <article class="card"><h2>Служба</h2><div class="value" id="service">—</div></article>
  <article class="card"><h2>Gateway</h2><div class="value" id="gateway">—</div></article>
  <article class="card"><h2>SQL Server</h2><div class="value" id="sql">—</div></article>
  <article class="card"><h2>Кэш запросов</h2><div class="value" id="cache">—</div></article>

  <article class="card wide">
    <h2>Подключение</h2>
    <table>
      <tr><td>Agent ID</td><td id="agent-id">—</td></tr>
      <tr><td>Gateway URL</td><td id="gateway-url">—</td></tr>
      <tr><td>Файл настроек</td><td id="config-path">—</td></tr>
      <tr><td>Последнее подключение</td><td id="connected-at">—</td></tr>
      <tr><td>Последний heartbeat</td><td id="heartbeat-at">—</td></tr>
      <tr><td>Последний запрос</td><td id="query-at">—</td></tr>
      <tr><td>Последняя синхронизация</td><td id="cloud-sync-at">—</td></tr>
      <tr><td>Попытка переподключения</td><td id="reconnect">—</td></tr>
    </table>
  </article>

  <article class="card wide">
    <h2>Последняя ошибка</h2>
    <div class="value" id="error" style="font-size:18px">Нет</div>
    <div class="actions">
      <button onclick="reloadAll()">Обновить</button>
      <button class="secondary" onclick="reloadConfig()">Перечитать настройки</button>
      <button class="secondary" onclick="clearCache()">Очистить кэш</button>
    </div>
  </article>

  <article class="card full">
    <h2>Последние записи журнала</h2>
    <pre id="logs">Загрузка...</pre>
  </article>
</section>
</main>
<script>
function cls(el, state) {
  el.className = 'value ' + (
    ['connected','running','ok'].includes(state) ? 'ok' :
    ['error','disconnected','stopped'].includes(state) ? 'bad' :
    ['starting','connecting','unknown'].includes(state) ? 'warn' : 'info'
  );
}
function value(v){ return v === null || v === undefined || v === '' ? '—' : v; }
async function loadStatus(){
  const r = await fetch('/api/status', {cache:'no-store'});
  const s = await r.json();
  document.getElementById('version').textContent = 'Версия ' + value(s.version);
  const service = document.getElementById('service');
  service.textContent = value(s.service_status); cls(service,s.service_status);
  const gateway = document.getElementById('gateway');
  gateway.textContent = value(s.gateway_status); cls(gateway,s.gateway_status);
  const sql = document.getElementById('sql');
  sql.textContent = value(s.sql_status); cls(sql,s.sql_status);
  document.getElementById('cache').textContent = value(s.cache_entries);
  document.getElementById('agent-id').textContent = value(s.agent_id);
  document.getElementById('gateway-url').textContent = value(s.gateway_url);
  document.getElementById('config-path').textContent = value(s.config_path);
  document.getElementById('connected-at').textContent = value(s.last_connected_at);
  document.getElementById('heartbeat-at').textContent = value(s.last_heartbeat_at);
  document.getElementById('query-at').textContent = value(s.last_query_at);
  document.getElementById('cloud-sync-at').textContent = value(s.last_cloud_sync_at);
  document.getElementById('reconnect').textContent = value(s.reconnect_attempt);
  const error = document.getElementById('error');
  error.textContent = value(s.last_error || 'Нет');
  error.className = 'value ' + (s.last_error ? 'bad' : 'ok');
}
async function loadLogs(){
  const r = await fetch('/api/logs?lines=150', {cache:'no-store'});
  const data = await r.json();
  document.getElementById('logs').textContent = data.text || 'Журнал пока пуст.';
}
async function reloadConfig(){
  await fetch('/api/config/reload', {method:'POST'});
  await new Promise(resolve => setTimeout(resolve, 1500));
  await reloadAll();
}
async function clearCache(){
  await fetch('/api/cache/clear', {method:'POST'});
  await reloadAll();
}
async function reloadAll(){
  await Promise.all([loadStatus(),loadLogs()]);
}
reloadAll();
setInterval(loadStatus, 3000);
setInterval(loadLogs, 10000);
</script>
</body>
</html>
"""


class AgentWebHandler(BaseHTTPRequestHandler):
    server_version = "RestaurantOSLocal/1.0"

    def log_message(self, format: str, *args) -> None:
        LOGGER.debug(format, *args)

    def _json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/":
            raw = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
            return

        if parsed.path == "/health":
            state = get_runtime_state().snapshot()
            self._json({
                "ok": True,
                "service": "restaurant-os-agent",
                "version": state.get("version"),
                "gateway_status": state.get("gateway_status"),
                "sql_status": state.get("sql_status"),
            })
            return

        if parsed.path == "/api/status":
            state = get_runtime_state().snapshot()
            config = reload_config()
            state["agent_id"] = config.agent_id
            state["gateway_url"] = config.gateway_url
            state["config_path"] = str(config.source_path)
            self._json(state)
            return

        if parsed.path == "/api/logs":
            self._json({"text": self._read_logs(150)})
            return

        self._json({"error": "not_found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/config/reload":
            config = reload_config()
            state = get_runtime_state()
            state.update(
                agent_id=config.agent_id,
                gateway_url=config.gateway_url,
                last_error=None,
            )
            marker = Path(
                os.environ.get(
                    "RESTAURANTOS_DATA_DIR",
                    os.getcwd(),
                )
            ) / "reload_config.request"
            marker.write_text("1", encoding="utf-8")
            self._json({
                "ok": True,
                "agent_id": config.agent_id,
                "gateway_url": config.gateway_url,
            })
            return

        if parsed.path == "/api/cache/clear":
            marker = Path(
                os.environ.get(
                    "RESTAURANTOS_DATA_DIR",
                    os.getcwd(),
                )
            ) / "clear_cache.request"
            marker.write_text("1", encoding="utf-8")
            self._json({"ok": True})
            return
        self._json({"error": "not_found"}, 404)

    @staticmethod
    def _read_logs(lines: int) -> str:
        data_dir = Path(
            os.environ.get(
                "RESTAURANTOS_DATA_DIR",
                os.getcwd(),
            )
        )
        log_path = data_dir / "logs" / "agent.log"
        if not log_path.exists():
            return ""
        try:
            content = log_path.read_text(
                encoding="utf-8",
                errors="replace",
            ).splitlines()
            return "\n".join(content[-lines:])
        except Exception as exc:
            return f"Не удалось прочитать журнал: {exc}"


class LocalAgentWebServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8090,
    ) -> None:
        self.host = host
        self.port = port
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.httpd = ThreadingHTTPServer(
            (self.host, self.port),
            AgentWebHandler,
        )
        self.thread = threading.Thread(
            target=self.httpd.serve_forever,
            name="RestaurantOSLocalWeb",
            daemon=True,
        )
        self.thread.start()
        LOGGER.info(
            "Локальный веб-интерфейс запущен: http://%s:%s",
            self.host,
            self.port,
        )

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=5)
