# Развёртывание на Ubuntu VPS

## Структура проекта

```
репозиторий/
├── artifacts/api-server/   ← здесь находится main.py
│   ├── main.py
│   ├── requirements.txt
│   ├── app/
│   ├── templates/
│   ├── static/
│   └── data/               ← создаётся автоматически при запуске
├── deploy/
│   ├── linkgen.service.example
│   └── nginx-linkgen.conf.example
└── .env.example
```

**WorkingDirectory:** `/var/www/linkgen/artifacts/api-server`  
**Команда запуска:** `uvicorn main:app --host 127.0.0.1 --port 5000`

---

## 1. Подготовка сервера

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx -y
```

---

## 2. Клонирование репозитория

```bash
sudo mkdir -p /var/www/linkgen
sudo chown $USER:$USER /var/www/linkgen
cd /var/www/linkgen
git clone https://github.com/miuixrn7-maker/Link_image_generator_ver.git .
```

---

## 3. Виртуальное окружение и зависимости

```bash
cd /var/www/linkgen
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r artifacts/api-server/requirements.txt
```

---

## 4. Переменные окружения

```bash
cp .env.example .env
nano .env
```

Заполните `.env`:

```
ADMIN_LOGIN=admin
ADMIN_PASSWORD=надёжный_пароль
SESSION_SECRET=длинная_случайная_строка_минимум_32_символа
BASE_URL=https://your-domain.ru
```

> **Важно:** `BASE_URL` — финальный домен с https. Без него ссылки в CSV будут некорректными.

Сгенерировать случайный SESSION_SECRET:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 5. Создание папок и настройка прав

Папки создаются автоматически при первом запуске, но можно создать заранее:

```bash
mkdir -p /var/www/linkgen/artifacts/api-server/data/{uploads,batches,previews,exports,logs,metadata}
sudo chown -R www-data:www-data /var/www/linkgen/artifacts/api-server/data
sudo chmod -R 755 /var/www/linkgen/artifacts/api-server/data
```

---

## 6. Тестовый запуск

```bash
cd /var/www/linkgen
source venv/bin/activate
cd artifacts/api-server
uvicorn main:app --host 0.0.0.0 --port 5000
```

Откройте в браузере `http://ваш-IP:5000` — должна появиться страница входа.  
Остановите: `Ctrl+C`.

---

## 7. Настройка systemd

```bash
sudo cp /var/www/linkgen/deploy/linkgen.service.example /etc/systemd/system/linkgen.service
sudo nano /etc/systemd/system/linkgen.service
```

Проверьте пути в файле (они уже настроены под `/var/www/linkgen`).

```bash
sudo systemctl daemon-reload
sudo systemctl enable linkgen
sudo systemctl start linkgen
sudo systemctl status linkgen
```

Просмотр логов:
```bash
sudo journalctl -u linkgen -f
```

---

## 8. Настройка Nginx

```bash
sudo cp /var/www/linkgen/deploy/nginx-linkgen.conf.example /etc/nginx/sites-available/linkgen
sudo nano /etc/nginx/sites-available/linkgen
```

Замените `your-domain.ru` на ваш реальный домен.

```bash
sudo ln -s /etc/nginx/sites-available/linkgen /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 9. HTTPS через Certbot

```bash
sudo certbot --nginx -d your-domain.ru -d www.your-domain.ru
```

Certbot автоматически обновит nginx-конфиг и добавит SSL.  
Автообновление сертификата настроено автоматически.

---

## 10. Обновление проекта с GitHub

```bash
cd /var/www/linkgen
git pull origin main
source venv/bin/activate
pip install -r artifacts/api-server/requirements.txt
sudo systemctl restart linkgen
```

---

## 11. Чеклист после развёртывания

- [ ] Страница входа открывается по домену
- [ ] Вход с логином и паролем из `.env` работает
- [ ] Загрузка ZIP-архива проходит без ошибок
- [ ] Распаковка и превью изображений работают
- [ ] Страница Preview открывается и показывает артикулы
- [ ] Генерация CSV выполняется успешно
- [ ] Ссылки из CSV открывают изображения напрямую в браузере
- [ ] Удаление партии работает
- [ ] Логи пишутся во вкладке «Логи»

---

## Безопасность

- Файл `.env` **никогда не коммитить** в Git (уже добавлен в `.gitignore`)
- Папка `data/` не коммитится (уже в `.gitignore`)
- Для продакшена используйте уникальный `SESSION_SECRET` и надёжный пароль
