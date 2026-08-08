# Agent 31.6.3 — StoreEngine Food Cost Probe

Gateway остаётся 10.5.2.

Диагностика Food Cost теперь:
- читает структуру tp_StoreEngine;
- выгружает до 500 последних складских движений;
- присоединяет tp_ProductItems и tp_Stores, если связи доступны;
- сохраняет sten_Date / sten_Volume / sten_Price / sten_Sum и служебные поля;
- строит краткую сводку по датам;
- группирует значения полей, похожих на тип/источник операции;
- сохраняет FK-связи StoreEngine;
- строго read-only.

Файл экспорта:
tillypad_food_cost_schema.json
