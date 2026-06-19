# Training Platform

Платформа продуктового обучения для сотрудников розничного магазина.
Контент генерируется из Google Doc через Claude; интерфейс — одностраничник;
бэкенд — Google Apps Script + Google Sheets.

```
training-platform/
├── pipeline/           # Python-скрипты генерации контента
│   ├── fetch_doc.py    # шаг 1: читает Google Doc → topics.json
│   ├── build_modules.py# шаг 2: Claude → content.json
│   ├── prompts/        # системный промпт + шаблон модуля
│   └── output/         # сгенерированные файлы (в .gitignore)
├── web/
│   └── index.html      # SPA: вход по PIN, лекция, карта, тест, тренажёр
└── backend/
    ├── Code.gs         # Apps Script: auth/progress/test/sim
    └── appsscript.json
```

---

## Assumptions (задокументированные допущения)

| # | Допущение | Где используется |
|---|-----------|-----------------|
| 1 | Темы в Google Doc разделяются заголовками **HEADING_1**. Текст до первого H1 игнорируется. | `fetch_doc.py` |
| 2 | Сервисный аккаунт имеет роль **Viewer** на документе. | `fetch_doc.py` |
| 3 | PIN — числовой, 4–6 символов. В таблице Employees хранится в столбце A как строка или число. | `Code.gs / handleAuth` |
| 4 | Таблица Google Sheets создаётся автоматически при первом обращении к `getSheet()`. Лист **Employees** создаётся пустым — заполните его вручную: A=PIN, B=имя, C=роль. | `Code.gs` |
| 5 | **Бренд-цвета и шрифты** заданы как CSS-переменные в `:root` блоке `web/index.html`. Текущие значения — нейтральная индиго-палитра; замените на ваши `--clr-primary`, `--clr-secondary` и `--font-heading`. | `web/index.html` |
| 6 | Sim-тренажёр: первая реплика «покупателя» показывается только в UI и не включается в историю сообщений для API. Это значит, что Claude не «знает» свою первую реплику — при необходимости добавьте её в system prompt в `buildSimSystem()`. | `Code.gs / handleSim` |
| 7 | Прогресс quiz сохраняется как лучший результат (последующие попытки сохраняются, но `progress_get` возвращает максимум). | `Code.gs / handleProgressGet` |
| 8 | `web/index.html` загружает `content.json` через `fetch('content.json')`. При локальном запуске нужен HTTP-сервер (CORS). Для продакшена положите оба файла на один хост или укажите полный URL в `CFG.contentUrl`. | `web/index.html` |

---

## Setup

### 1. Подготовка сервисного аккаунта Google

```bash
# В Google Cloud Console:
# IAM → Service Accounts → Create → скачайте JSON-ключ
# Откройте ваш Google Doc → Share → добавьте email сервисного аккаунта (Viewer)
```

### 2. Pipeline

```bash
cd pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp ../.env.example ../.env
# заполните .env: PRODUCT_DOC_ID, GOOGLE_SERVICE_ACCOUNT_JSON, ANTHROPIC_API_KEY

python3 fetch_doc.py          # → output/topics.json
python3 build_modules.py      # → output/content.json  (Claude, ~1 мин на тему)

# Пересборка одной темы:
python3 build_modules.py --topic "Точное название темы"
```

### 3. Backend (Google Apps Script)

1. Перейдите на [script.google.com](https://script.google.com) → New project.
2. Скопируйте содержимое `backend/Code.gs` и `backend/appsscript.json`.
3. **Project settings → Script properties** → добавьте:
   - `SPREADSHEET_ID` — ID таблицы Google Sheets (создайте пустую таблицу заранее)
   - `ANTHROPIC_API_KEY` — ваш ключ Anthropic
4. **Deploy → New deployment → Web app**:
   - Execute as: **Me**
   - Who has access: **Anyone**
5. Скопируйте URL деплоя.

### 4. Web App

1. Откройте `web/index.html`, замените строку:
   ```js
   appsScriptUrl: 'REPLACE_WITH_YOUR_APPS_SCRIPT_WEB_APP_URL',
   ```
2. Положите `web/index.html` и `pipeline/output/content.json` на один хост
   (Netlify, GitHub Pages, Firebase Hosting — любой статический хостинг).

### 5. Сотрудники

Откройте таблицу Google Sheets, лист **Employees**:

| A (PIN) | B (name) | C (role) |
|---------|----------|----------|
| 1234    | Анна     | consultant |
| 5678    | Максим   | senior |

---

## Локальный запуск (для разработки)

```bash
cd web
python3 -m http.server 8080
# откройте http://localhost:8080
```

При локальном запуске запросы к Apps Script будут работать, но нужно,
чтобы `content.json` лежал в `web/` (скопируйте из `pipeline/output/`).

---

## Дизайн-токены (брендбук)

Замените переменные в `web/index.html → :root`:

```css
--clr-primary       /* основной цвет кнопок, прогресс-баров */
--clr-primary-dark  /* hover-состояние кнопок */
--clr-primary-light /* светлый фон-акцент */
--clr-secondary     /* тёмный цвет заголовков */
--clr-surface       /* фон страницы */
--font-heading      /* шрифт заголовков */
--font-body         /* шрифт текста */
```

---

## Схема content.json

```jsonc
[
  {
    "topic":        "Название темы (H1 из Google Doc)",
    "lecture_html": "<HTML-контент лекции>",
    "mindmap": {
      "nodes": [{"id": "1", "label": "Корень"}, ...],
      "edges": [{"from": "1", "to": "2"}, ...]
    },
    "mindmap_md":   "# Корень\n## Ветка\n...",
    "quiz": [
      {"q": "Вопрос?", "options": ["A","Б","В","Г"], "correct": 0, "explain": "..."}
    ],
    "sim_brief": {
      "persona":    "Описание покупателя",
      "need":       "Что ищет покупатель",
      "objections": ["Возражение 1", "..."],
      "rubric":     ["Критерий оценки 1", "..."]
    }
  }
]
```
