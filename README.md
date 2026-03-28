# Stepik Course Factory (SCF v2)

> **Пишешь курс в Markdown — скрипт сам загружает его на Stepik.**  
> Полная поддержка 10 типов шагов: от теории до сопоставлений и пропусков.

---

## 📦 Состав репозитория

| Файл | Назначение |
|------|-----------|
| `stepik_uploader_v2.py` | Главный скрипт: парсинг MD → загрузка на Stepik API |
| `stepik_course_template_v2.md` | Шаблон курса SCF v2 — заполните и загружайте |
| `keys.env` | Шаблон файла с ключами API (замените на свои!) |
| `README.md` | Эта документация |

> ⚠️ **`keys.env` с реальными ключами — не загружать на GitHub!**  
> Добавьте в `.gitignore`: `echo "keys.env" >> .gitignore`

---

## 🚀 Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone https://github.com/LionetGolovin/stepik-course-factory.git
cd stepik-course-factory
```

### 2. Установить зависимости

```bash
# Стандартный pip
pip install requests pyyaml markdown

# Или через uv (macOS / быстрый старт)
uv run --with requests --with pyyaml --with markdown \
    stepik_uploader_v2.py мой_курс.md --dry-run
```

### 3. Добавить ключи API

Получите ключи на [stepik.org/oauth2/applications](https://stepik.org/oauth2/applications)  
(Тип приложения: **Confidential**, грант: **Client credentials**)

**Способ 1 — файл `keys.env`** (рекомендуется):

```
STEPIK_CLIENT_ID=ваш_client_id
STEPIK_CLIENT_SECRET=ваш_client_secret
```

> ⚠️ Без пробелов вокруг `=` и без кавычек.

**Способ 2 — переменные окружения:**

```bash
export STEPIK_CLIENT_ID=ваш_client_id
export STEPIK_CLIENT_SECRET=ваш_client_secret
```

### 4. Заполнить шаблон курса

Откройте `stepik_course_template_v2.md` и замените все `[заглушки]` на реальный контент.

### 5. Проверить структуру (без загрузки)

```bash
# --dry-run не требует ключей API
python stepik_uploader_v2.py мой_курс.md --dry-run
```

### 6. Загрузить курс на Stepik

```bash
python stepik_uploader_v2.py мой_курс.md --keys keys.env
```

---

## 📐 Структура курса (SCF v2)

Курс описывается в одном `.md`-файле с иерархией:

```
# Название курса          ← H1  (метаданные в YAML frontmatter)
## Модуль 1               ← H2  (раздел / секция)
### Урок 1.1              ← H3  (урок)
#### ТЕКСТ: Заголовок     ← H4  (шаг — тип указывается ключевым словом)
```

### Типы шагов

| Ключевое слово | Тип на Stepik | Описание |
|----------------|---------------|----------|
| `ТЕКСТ:`    | `text`         | Теоретический блок |
| `ВЫБОР:`    | `choice`       | Один правильный ответ |
| `МУЛЬТИ:`   | `choice multi` | Несколько правильных ответов |
| `ЧИСЛО:`    | `number`       | Числовой ответ |
| `СТРОКА:`   | `string`       | Короткий текстовый ответ |
| `ЭССЕ:`     | `free-answer`  | Развёрнутый ответ / эссе |
| `ПОРЯДОК:`  | `sorting`      | Расставить элементы по порядку |
| `ПАРЫ:`     | `matching`     | Сопоставить два столбца |
| `ПРОПУСКИ:` | `fill-blanks`  | Заполнить пропуски в тексте |
| `ТАБЛИЦА:`  | `table`        | Таблица с чекбоксами для отметки ячеек |

### Параметры шагов

Параметры задаются HTML-комментариями сразу после заголовка `####`:

**ВЫБОР / МУЛЬТИ:**
```markdown
#### ВЫБОР: Какое определение точнее?
<!-- shuffle: true -->
<!-- feedback-correct: Верно! -->
<!-- feedback-wrong: Подсказка: вернитесь к теоретическому блоку. -->

- [ ] Неверный вариант A
- [x] Верный вариант B
- [ ] Неверный вариант C
```

**ЧИСЛО:**
```markdown
#### ЧИСЛО: Сколько уровней в модели OSI?
<!-- answer: 7 -->
<!-- precision: 0 -->
```

**СТРОКА:**
```markdown
#### СТРОКА: Введите название протокола
<!-- answer: HTTP -->
<!-- answer-aliases: http | Http -->
<!-- case-sensitive: false -->
```

**ЭССЕ:**
```markdown
#### ЭССЕ: Опишите подход к цифровой трансформации
<!-- min-words: 50 -->
<!-- max-words: 500 -->
<!-- peer-review: true -->
```

**ПАРЫ:**
```markdown
#### ПАРЫ: Сопоставьте понятия
<!-- shuffle-rows: true -->

| Левый столбец | Правый столбец |
|---------------|----------------|
| Понятие А     | Определение 1  |
| Понятие Б     | Определение 2  |
```

**ПРОПУСКИ:**
```markdown
#### ПРОПУСКИ: Вставьте пропущенные слова
<!-- blank: слово1 = системный | комплексный -->
<!-- blank: слово2 = управлению | организации -->

Это {слово1} подход к {слово2}.
```

**Описания секций и уроков:**
```markdown
## Модуль 1 — Введение
<!-- section-description: Краткое описание модуля для студентов. -->

### Урок 1.1 — Основные понятия
<!-- lesson-description: Что узнает студент в этом уроке. -->
```

---

## 🔑 Файл `keys.env`

```
# ЛИЧНЫЙ ФАЙЛ — НЕ ЗАГРУЖАТЬ НА GITHUB!
# Получить: https://stepik.org/oauth2/applications

STEPIK_CLIENT_ID=ваш_client_id
STEPIK_CLIENT_SECRET=ваш_client_secret
```

> ⚠️ Формат строгий: **без пробелов** вокруг `=`, **без кавычек**, имена ключей точно как выше.

**Безопасность:** добавьте в `.gitignore`:
```bash
echo "keys.env" >> .gitignore
```

---

## ⌨️ Параметры командной строки

```
stepik_uploader_v2.py курс.md [--keys FILE] [--dry-run]

  курс.md        Путь к MD-файлу курса в формате SCF v2
  --keys FILE    Путь к файлу ключей API (нужен только для загрузки)
  --dry-run      Предпросмотр структуры без загрузки на Stepik
```

> Вместо `--keys` можно задать переменные окружения `STEPIK_CLIENT_ID` и `STEPIK_CLIENT_SECRET`.

### Примеры

```bash
# Предпросмотр — ключи не нужны
python stepik_uploader_v2.py мой_курс.md --dry-run

# Загрузка с файлом ключей
python stepik_uploader_v2.py мой_курс.md --keys keys.env

# Загрузка через переменные окружения
export STEPIK_CLIENT_ID=...
export STEPIK_CLIENT_SECRET=...
python stepik_uploader_v2.py мой_курс.md

# macOS + uv (все зависимости автоматически)
uv run --with requests --with pyyaml --with markdown \
    stepik_uploader_v2.py мой_курс.md --keys keys.env --dry-run
```

---

## 📋 Пример вывода `--dry-run`

```
📄 Читаю файл: мой_курс.md

══════════════════════════════════════════════════════════════
  ПРЕДПРОСМОТР КУРСА
══════════════════════════════════════════════════════════════
  Название : Основы цифровой трансформации
  Summary  : Для кого курс, чему научит, какой главный результат...
  Язык     : ru
  Модулей  : 3
  Уроков   : 11
  Шагов    : 25

  📦 [1] Модуль 1 — Введение в тему
       📖 [1.1] Урок 1.1 — Что такое [Тема]  [text×3]
       📖 [1.2] Урок 1.2 — История и тренды  [text×2, choice×1]
  📦 [2] Модуль 2 — Практика
       📖 [2.1] Урок 2.1 — Инструмент №1     [text×1, choice×1]
       ...

  Типы шагов итого: {'text': 17, 'choice': 3, 'matching': 2, ...}
══════════════════════════════════════════════════════════════

ℹ️  Режим --dry-run: загрузка не выполняется.
```

---

## ✅ После загрузки

Скрипт выведет прямые ссылки:

```
  Редактор  : https://stepik.org/course/XXXXX/edit
  Просмотр  : https://stepik.org/course/XXXXX/promo
```

**Вручную в редакторе Stepik необходимо:**
- Загрузить обложку курса (1280×720 px, JPG/PNG)
- Добавить промо-видео (YouTube / Vimeo)
- Заполнить полное описание, теги, авторов
- Нажать **Publish** для публикации

---

## 🛠 Требования

| Зависимость | Версия | Назначение |
|-------------|--------|-----------|
| Python      | ≥ 3.8  | Интерпретатор |
| `requests`  | ≥ 2.31 | HTTP-запросы к Stepik API |
| `pyyaml`    | ≥ 6.0  | Парсинг YAML frontmatter |
| `markdown`  | ≥ 3.5  | Конвертация MD → HTML |

Проверить окружение:
```bash
python -c "import requests, yaml, markdown; print('OK')"
```

---

## 🏗 Архитектура скрипта

```
stepik_uploader_v2.py  (944 строки, 33 функции)
│
├── load_credentials(keys_file)  # Загрузка ключей из файла или env-переменных
│
├── API-слой
│   ├── get_token(client_id, client_secret)
│   ├── api_post()               # С timeout и exponential backoff retry
│   ├── create_course/section/lesson/unit()
│   └── _post_step() / _step_base()
│
├── Билдеры payload (по типу шага)
│   ├── create_text_step()
│   ├── create_choice_step()     # + feedback_correct / feedback_wrong
│   ├── create_number_step()
│   ├── create_string_step()
│   ├── create_free_answer_step() # + min_words / max_words / peer_review
│   ├── create_sorting_step()
│   ├── create_matching_step()   # + shuffle_rows
│   ├── create_fill_blanks_step()
│   └── create_table_step()      # Новый тип: таблица с чекбоксами
│
├── Парсер SCF v2
│   ├── parse_md_file()          # Главный парсер иерархии (# → ## → ### → ####)
│   ├── parse_frontmatter()      # YAML метаданные + #-комментарии
│   ├── strip_template_comments()
│   ├── detect_step_type()       # Определение типа по ключевому слову
│   ├── extract_params()         # <!-- key: value --> параметры
│   ├── clean_option_text()      # Удаление шаблонных маркеров
│   ├── parse_choice_options()   # [ ] / [x] варианты
│   ├── parse_sorting_options()  # [N] порядок
│   ├── parse_matching_pairs()   # MD-таблица пар (по позиции строк)
│   └── parse_fill_blanks()      # {пропуски} + <!-- blank -->
│
└── Оркестратор
    ├── upload_step()    # Диспетчер по типу
    ├── upload_course()  # Полный цикл загрузки
    ├── print_preview()  # Вывод dry-run
    └── main()
```

---

## 📄 Лицензия

MIT — используйте свободно, ссылка на репозиторий приветствуется.

---

*Создано для автоматизации загрузки курсов на [Stepik](https://stepik.org) из Markdown-файлов.*  
*Автор: [@LionetGolovin](https://github.com/LionetGolovin)*
