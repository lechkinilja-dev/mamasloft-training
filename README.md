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

В каждом модуле 10–15 проверенных вопросов. Тесты и сценарии консультаций
по статьям хранятся в `pipeline/site_quizzes.py`, а два тренинга IVA Design —
в `pipeline/iva_modules.py`. Сборка детерминирована и не требует API-ключа
внешней модели.

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
docs/                   # production bundle для academy.analytics-mamasloft.ru
web/                    # локальная копия интерфейса
apps-script/Code.gs     # Google Sheets backend
server/                 # редактируемый контент и история прохождений
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

Production размещён как статический сайт на сервере Mama's Loft:

- курсы: `https://academy.analytics-mamasloft.ru/`;
- админка: `https://academy.analytics-mamasloft.ru/admin.html`;
- статический каталог: `/var/www/dashboards/academy/`;
- nginx-блок: `deploy/academy.nginx.conf`.

`git push` сохраняет историю, но не публикует платформу: production bundle из
`docs/` переносится на сервер отдельным согласованным деплоем.

Админка редактирует темы через same-origin API `/academy-api/rpc`. Текущая
версия хранится на сервере в `content.json`, а перед каждым изменением API
создаёт снимок в каталоге `revisions/`. Удаление темы мягкое: тема скрывается и
остаётся доступной для восстановления вместе с историей результатов.

Скрипт ниже оставлен только для архива старой Google Sheets-схемы. Новая
версия пишет прогресс в серверное версионированное хранилище и не требует
синхронизации матрицы тем:

```bash
/Users/ilyadom/mamas-loft-finance/.venv/bin/python scripts/sync_training_topics.py
```

После явного согласования публикации ключ `--apply` создаёт архивные копии
листов «Статус обучения» и «Свод », заменяет активную матрицу тем и обнуляет
сводный прогресс для нового цикла обучения.
