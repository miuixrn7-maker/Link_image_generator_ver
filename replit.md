# Генератор прямых ссылок

Внутренний инструмент для обработки ZIP-архивов с изображениями товаров, ручного распределения фото по слотам и генерации CSV с прямыми публичными URL.

## Run & Operate

- Workflow `Start application` — запускает Python/FastAPI сервер на порту 5000
- URL приложения: `/` (корень)
- Логин по умолчанию: `admin` / `admin123` (задаётся через env ADMIN_LOGIN / ADMIN_PASSWORD)

## Stack

- Python 3.11, FastAPI + Uvicorn (Starlette 1.0)
- Jinja2 (HTML шаблоны), TailwindCSS (CDN)
- Pillow (обработка изображений)
- Сессии через itsdangerous (SessionMiddleware)
- Хранение данных: локальная файловая система (`data/`)

## Where things live

```
artifacts/api-server/
├── main.py                  # точка входа FastAPI
├── app/
│   ├── config.py            # настройки, пути
│   ├── auth.py              # авторизация
│   ├── extractor.py         # распаковка ZIP
│   ├── distributor.py       # авто-распределение изображений
│   ├── preview_gen.py       # генерация превью (Pillow)
│   ├── csv_export.py        # генерация CSV
│   ├── metadata.py          # CRUD метаданных партий (JSON)
│   ├── logger_utils.py      # логирование событий партии
│   ├── cleanup.py           # удаление партий
│   ├── utils.py             # вспомогательные функции
│   └── routes/              # маршруты (по модулям)
├── templates/               # Jinja2 HTML шаблоны
├── static/                  # CSS + JS
│   ├── css/style.css
│   └── js/viewer.js
└── data/                    # рабочие данные (gitignore)
    ├── uploads/             # загруженные ZIP
    ├── batches/             # распакованные изображения
    ├── previews/            # превью изображений
    ├── exports/             # готовые CSV
    ├── logs/                # логи партий
    └── metadata/            # JSON метаданные партий
```

## Architecture decisions

- Starlette 1.0 требует `TemplateResponse(request, name, context)` — request первым аргументом, без него в context
- BASE_URL env var используется для генерации абсолютных URL в CSV; если пуст — используется REPLIT_DEV_DOMAIN
- Данные хранятся в JSON-файлах (не в БД) — простота и переносимость для V1
- Превью генерируются при распаковке и кэшируются в `data/previews/`
- Архив удаляется после успешной распаковки для экономии места

## Product

- Загрузка ZIP-архива с изображениями товаров (структура: папка/артикул/файлы)
- Авто-распределение по слотам (Главная, Увеличенная фото)
- Ручная правка через drag-and-drop в интерфейсе превью
- Генерация CSV с прямыми URL для каждого слота
- История партий, логи, скачивание CSV

## User preferences

- Интерфейс на русском языке, код на английском
- Версия 1: без WB/Ozon экспорта, без мультиюзера, без ресайза изображений

## Gotchas

- `configureWorkflow` иногда даёт "failed" даже если сервер запустился — проверять через `getWorkflowStatus`
- Порт 8080 занят старым Node.js api-server workflow — Python приложение на порту 5000
- В Starlette 1.0 `TemplateResponse(name, context)` → ошибка; нужно `TemplateResponse(request, name, context)`
- При развёртывании установить BASE_URL = публичный домен для корректных URL в CSV

## Pointers

- See the `pnpm-workspace` skill for workspace structure
- Python deps устанавливаются через pip в `.pythonlibs/`
