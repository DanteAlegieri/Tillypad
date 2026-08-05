# Restaurant OS Design System

## Layers

- `tokens.css` — цвета, интервалы, радиусы, тени.
- `base.css` — базовые правила.
- `layout.css` — layout primitives.
- `components.css` — переиспользуемые компоненты.
- `utilities.css` — короткие вспомогательные классы.

## Components Foundation-02

- `.ros-card`
- `.ros-kpi-card`
- `.ros-kpi-card__label`
- `.ros-kpi-card__value`
- `.ros-kpi-card__meta`
- `.ros-panel`
- `.ros-panel__head`
- `.ros-progress-card`
- `.ros-button`
- `.ros-badge`
- `.ros-empty`

## Shared Jinja components

- `components/sidebar.html`
- `components/header.html`

Существующие JS ID сохраняются, чтобы UI-рефакторинг не менял бизнес-логику.
