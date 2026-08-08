# Restaurant OS 10.4.5 — Gateway payment persistence fix

Agent remains 31.4.1.

Gateway:
- нормализует и сохраняет `payments_json` при каждом snapshot;
- сохраняет `payments_json` и в новой схеме таблицы;
- Finance автоматически запускает legacy recovery;
- добавлен `/api/web/{agent_id}/finance/payments/diagnostics`;
- диагностика показывает по каждому дню:
  - revenue,
  - checks_count,
  - payments_rows,
  - payload_payments_rows,
  - payments_total,
  - received_at;
- Finance показывает статус сохранения оплат на Gateway.
