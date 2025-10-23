
# 🗂 Tracker → Reminders Sync

Автоматическая синхронизация задач из **Yandex Tracker** в **Apple Reminders** на macOS.  
Скрипт каждый день проверяет активный спринт и создает/обновляет напоминания.

---

## 📌 Возможности
- Автоматическое обновление в **09:00 (Europe/Moscow)**  
- Получение задач из **активного спринта** по `board_id`  
- Проставление:
  - **статуса** (`statusType.display`)  
  - **дедлайна** (`due date` и `remind me`)  
  - **completed** если задача закрыта  
- Запись **автора** и **исполнителя** (email) в тело заметки  
- Если у задачи нет `deadline` → используется **дата окончания спринта**  

---

## ⚙️ Установка

### 1. Склонировать проект
```bash
git clone https://gitlab.example.com/your/tracker-reminders.git
cd tracker-reminders
````

### 2. Запустить установщик

```bash
chmod +x install.sh
./install.sh
```

Скрипт проверит наличие:

* `python3`
* `yc` (**Yandex Cloud CLI**) — если не найден, установит автоматически

### 3. Конфигурация

При первом запуске `install.sh` задаст параметры и сохранит их в
`~/.tracker_reminders.env` (или использовать переменную окружения `TRACKER_REMINDERS_ENV`).

Пример:

```ini
# ~/.tracker_reminders.env
CLOUD_ORG_ID=bpft1b2sgogor548lq3k
YT_BOARD_ID=582
YT_QUERY_XTRA=Status: !Closed
YT_ASSIGNEE=me()
REM_LIST_PREFIX=
```

---

## 🔑 Параметры `.env`

| Переменная        | Описание                                                                | Пример                 |
| ----------------- |-------------------------------------------------------------------------| ---------------------- |
| `CLOUD_ORG_ID`    | Идентификатор организации в Яндекс Облаке  (задан по умолчанию)         | `bpft1b2sgogor548lq3k` |
| `YT_BOARD_ID`     | ID Agile-доски (см. в URL `.../board/582`)                              | `582`                  |
| `YT_QUERY_XTRA`   | Дополнительный фильтр в Tracker Query                                   | `Status: !Closed`      |
| `YT_ASSIGNEE`     | Фильтр по исполнителю (`me()`, `unassigned`, список через запятую)      | `me()`                 |
| `REM_LIST_PREFIX` | Префикс для названий списков в Reminders (если ведется несколько досок) | `TeamX-`               |

---

## ⏰ Автоматизация

После установки создаётся **LaunchAgent**:
`~/Library/LaunchAgents/com.tracker.reminders.sync.plist`

* Скрипт запускается **каждый час**
* Внутри есть «охранник»: выполняется **только в 09:00 (Europe/Moscow)**

Проверить расписание:

```bash
launchctl list | grep tracker
```

Посмотреть логи:

```bash
tail -f /tmp/tracker2reminders.out
tail -f /tmp/tracker2reminders.err
```

---

## 🖥 Использование вручную

Запуск вручную:

```bash
python3 ~/bin/tracker_to_reminders.py
```

---

## 📒 Как работают напоминания

* **Название**: `[QUEUE-123] Название задачи`

* **Текст**:

  ```
  Статус: В процессе
  Автор: user@company.ru
  Исполнитель: teammate@company.ru
  Ссылка: https://tracker.yandex.ru/QUEUE-123

  Описание:
  ...
  ```

* **Дата**:

  * Берётся из `deadline` тикета
  * Если `deadline` нет → дата окончания активного спринта

* **Completed**:

  * Если статус тикета = `Closed` → напоминание закрывается

---

## 🔍 Отладка

1. Проверить токен Яндекса:

   ```bash
   yc iam create-token
   ```

2. Проверить, что задачи приходят:

   ```bash
   python3 -m yandex_tracker_client --help
   ```

3. Получить список напоминаний AppleScript:

   ```bash
   osascript -e 'tell application "Reminders" to get name of every reminder'
   ```

---

## ✅ Поддержка

* macOS 12+ (с приложением Reminders)
* Python 3.9+
* Яндекс Tracker + `yc` CLI
