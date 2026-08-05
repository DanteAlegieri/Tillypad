# Restaurant OS 8.1.1

Исправлена ошибка JavaScript:

`Cannot set properties of null (setting 'textContent')`

Причина: Dashboard JS обновлял динамические подписи KPI, но в `dashboard.html` отсутствовали четыре соответствующих ID.

Добавлены ID и безопасные DOM helpers, поэтому отсутствие отдельного необязательного элемента больше не прерывает загрузку всей панели.
