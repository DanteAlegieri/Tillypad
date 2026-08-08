# Restaurant OS 10.4.6

## Forced historical payment replay

Agent 31.4.2
- каждый исторический snapshot за 70 дней помечается `_replay_payments=true`;
- в лог добавляется `Replay оплат: дата=..., строк=N`;
- данные по оплатам заново читаются из TillyPad SQL.

Gateway 10.4.6
- если получен `_replay_payments=true`, последний snapshot этого business_date обновляется;
- `payments_json`, `payload_json`, revenue, menu и hourly перезаписываются фактическими данными;
- если дня ещё нет, snapshot создаётся обычным способом;
- диагностика Finance смотрит последний snapshot дня.
