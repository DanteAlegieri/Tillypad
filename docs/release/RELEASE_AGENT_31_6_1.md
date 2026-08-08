# Agent 31.6.1 — Targeted Food Cost Diagnostics

Gateway остаётся 10.5.2.

Диагностика Food Cost теперь работает только с пятью таблицами:
- tp_SaleDocuments
- tp_SaleDocumentItems
- tp_StoreEngine
- tp_WriteOffDocuments
- tp_WriteOffDocumentItems

Для каждой таблицы сохраняются:
- наличие таблицы;
- все колонки и типы;
- количество строк;
- до 30 последних/характерных строк;
- наиболее интересные поля Price/Sum/Volume/Date/Store/Product/Done/Deleted/State;
- внешние ключи, где одна из сторон — целевая таблица.

Диагностика строго read-only.
Файл экспорта остаётся `tillypad_food_cost_schema.json`.
