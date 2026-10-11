# Mama's Loft Training Platform

Платформа обучения сотрудников по материалам раздела
«Полезные материалы» на `mamasloft.ru`.

## Источник контента

`pipeline/fetch_doc.py` читает проверенный production-коммит сайта из
`~/.agents/state/mamasloft-production.json` и извлекает шесть материалов:

- купание новорождённого;
- уход и стирка детских вещей;
- выбор подарка новорождённому;
- первый прикорм;
- одежда малыша осенью и зимой;
- чеклист первого гардероба.

Файлы сайта читаются через `git show <productionCommit>:<path>`, поэтому
текущая ветка основной папки сайта не используется как источник истины.
Для нестандартного окружения пути и коммит можно передать через
`MAMASLOFT_SITE_REPO`, `MAMASLOFT_PRODUCTION_STATE` и
`MAMASLOFT_PRODUCTION_COMMIT`.

## Сборка

```bash
cd /Users/ilyadom/training-platform
python3 pipeline/fetch_doc.py
python3 pipeline/build_modules.py
```

Первый шаг полностью пересобирает `pipeline/output/topics.json`. Второй шаг
полностью заменяет старые модули и синхронно пишет результат в:

- `pipeline/output/content.json`;
- `docs/content.json`;
- `web/content.json`.

В каждом модуле 10 проверенных вопросов. Тесты и сценарии консультаций
хранятся в `pipeline/site_quizzes.py`; сборка детерминирована и не требует
API-ключа внешней модели.

## Локальная проверка

```bash
cd docs
python3 -m http.server 8080
```

Откройте `http://localhost:8080`. Платформа использует рабочий Apps Script
для авторизации и прогресса, поэтому до публикации нового набора тем нужно
синхронно заменить строки на листе «Статус обучения»: для каждой темы создать
три строки — «Лекция», «Карта знаний», «Тест». Старую матрицу прогресса перед
заменой следует сохранить в архивной копии.

## Структура

```text
pipeline/
  fetch_doc.py          # production-статьи сайта → topics.json
  build_modules.py      # topics + проверенные тесты → content.json
  site_quizzes.py       # 10 вопросов и сценарий по каждой теме
  output/
docs/                   # production bundle для Vercel
web/                    # локальная копия интерфейса
apps-script/Code.gs     # Google Sheets backend
```

## Схема модуля

```jsonc
{
  "topic": "Название темы",
  "slug": "site-guide-slug",
  "source_url": "https://mamasloft.ru/guides/...",
  "source_commit": "production git sha",
  "lecture_html": "<h2>...</h2>",
  "mindmap": {"nodes": [], "edges": []},
  "mindmap_md": "# ...",
  "quiz": [
    {"q": "Вопрос?", "options": ["..."], "correct": 0, "explain": "..."}
  ],
  "sim_brief": {
    "persona": "...",
    "need": "...",
    "objections": ["..."],
    "rubric": ["..."]
  }
}
```

Публикация выполняется отдельно: `git push` сохраняет историю, а Vercel
разворачивается вручную, потому что проект не подключён к GitHub auto-deploy.
