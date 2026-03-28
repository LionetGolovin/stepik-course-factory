#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stepik_uploader_v2.py — Загрузчик курсов SCF v2 на Stepik
==========================================================
Поддерживаемые типы шагов:
  ТЕКСТ    → text          (подтверждено API)
  ВЫБОР    → choice        (подтверждено API)
  МУЛЬТИ   → choice multi  (подтверждено API)
  ЧИСЛО    → number
  СТРОКА   → string
  ЭССЕ     → free-answer
  ПОРЯДОК  → sorting
  ПАРЫ     → matching
  ПРОПУСКИ → fill-blanks

Иерархия файла:  # Курс  →  ## Модуль  →  ### Урок  →  #### Шаг

Использование:
    python3 stepik_uploader_v2.py курс.md           # интерактивная загрузка
    python3 stepik_uploader_v2.py курс.md --dry-run # только предпросмотр

Требования:
    pip install requests pyyaml markdown
"""

import sys
import re
import time
import requests
import yaml
import markdown as md_lib
from pathlib import Path

# ─── ВАШИ КЛЮЧИ: получить на https://stepik.org/oauth2/applications/ ──────────
CLIENT_ID     = "ВАШ_CLIENT_ID"
CLIENT_SECRET = "ВАШ_CLIENT_SECRET"
# ──────────────────────────────────────────────────────────────────────────────

BASE_URL      = "https://stepik.org"
REQUEST_DELAY = 0.4   # секунды между запросами (не менее 0.3 во избежание rate-limit)


# ════════════════════════════════════════════════════════════════
#  АВТОРИЗАЦИЯ И БАЗОВЫЕ ВЫЗОВЫ
# ════════════════════════════════════════════════════════════════

def get_token():
    resp = requests.post(
        f"{BASE_URL}/oauth2/token/",
        data={"grant_type": "client_credentials"},
        auth=(CLIENT_ID, CLIENT_SECRET)
    )
    resp.raise_for_status()
    print("✅ Авторизация успешна")
    return resp.json()["access_token"]


def api_post(token, endpoint, payload):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(f"{BASE_URL}/api/{endpoint}", headers=headers, json=payload)
    if not resp.ok:
        print(f"❌ Ошибка {resp.status_code} [{endpoint}]: {resp.text[:500]}")
        resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return resp.json()


# ════════════════════════════════════════════════════════════════
#  СОЗДАНИЕ СТРУКТУРНЫХ ОБЪЕКТОВ КУРСА
# ════════════════════════════════════════════════════════════════

def create_course(token, title, summary, language="ru"):
    data = api_post(token, "courses", {
        "course": {"title": title, "summary": summary[:255], "language": language}
    })
    cid = data["courses"][0]["id"]
    print(f"📚 Курс создан: ID {cid} — {title}")
    return cid


def create_section(token, course_id, title, position):
    data = api_post(token, "sections", {
        "section": {"title": title, "course": course_id, "position": position}
    })
    return data["sections"][0]["id"]


def create_lesson(token, title):
    data = api_post(token, "lessons", {
        "lesson": {"title": title, "language": "ru"}
    })
    return data["lessons"][0]["id"]


def create_unit(token, section_id, lesson_id, position):
    data = api_post(token, "units", {
        "unit": {"section": section_id, "lesson": lesson_id, "position": position}
    })
    return data["units"][0]["id"]


def _post_step(token, payload):
    data = api_post(token, "step-sources", payload)
    return data["step-sources"][0]["id"]


def _step_base(lesson_id, position, block):
    return {"stepSource": {"lesson": lesson_id, "position": position, "block": block}}


# ════════════════════════════════════════════════════════════════
#  БИЛДЕРЫ API-PAYLOAD ПО ТИПАМ ШАГОВ
# ════════════════════════════════════════════════════════════════

def create_text_step(token, lesson_id, position, title, html):
    header = f"<h2>{title}</h2>\n" if title else ""
    block  = {"name": "text", "text": f"{header}{html}"}
    return _post_step(token, _step_base(lesson_id, position, block))


def create_choice_step(token, lesson_id, position, question_html,
                       options_data, is_multiple=False, preserve_order=True):
    """
    options_data: [{"text": str, "is_correct": bool, "feedback": str}, ...]
    """
    block = {
        "name": "choice",
        "text": question_html,
        "source": {
            "options": [
                {"is_correct": o["is_correct"], "text": o["text"],
                 "feedback": o.get("feedback", "")}
                for o in options_data
            ],
            "is_always_correct":  False,
            "is_html_enabled":    True,
            "sample_size":        len(options_data),
            "is_multiple_choice": is_multiple,
            "preserve_order":     preserve_order,
            "is_options_feedback": False,
        }
    }
    return _post_step(token, _step_base(lesson_id, position, block))


def create_number_step(token, lesson_id, position, question_html, answer, max_error="0"):
    block = {
        "name": "number",
        "text": question_html,
        "source": {"options": [{"answer": str(answer), "max_error": str(max_error)}]}
    }
    return _post_step(token, _step_base(lesson_id, position, block))


def create_string_step(token, lesson_id, position, question_html,
                       answer, aliases=None, case_sensitive=False):
    """
    Несколько допустимых ответов объединяются regex-паттерном через |.
    """
    all_answers = [answer] + (aliases or [])
    escaped = [re.escape(a.strip()) for a in all_answers if a.strip()]
    pattern = "|".join(escaped) if len(escaped) > 1 else (escaped[0] if escaped else answer)
    block = {
        "name": "string",
        "text": question_html,
        "source": {"pattern": pattern, "case_sensitive": case_sensitive}
    }
    return _post_step(token, _step_base(lesson_id, position, block))


def create_free_answer_step(token, lesson_id, position, question_html):
    block = {
        "name": "free-answer",
        "text": question_html,
        "source": {"is_attachments_enabled": False, "is_html_enabled": True}
    }
    return _post_step(token, _step_base(lesson_id, position, block))


def create_sorting_step(token, lesson_id, position, question_html, options_ordered):
    """options_ordered — список строк в правильном порядке."""
    block = {
        "name": "sorting",
        "text": question_html,
        "source": {"options": options_ordered}
    }
    return _post_step(token, _step_base(lesson_id, position, block))


def create_matching_step(token, lesson_id, position, question_html, pairs):
    """pairs: [{"first": str, "second": str}, ...]"""
    block = {
        "name": "matching",
        "text": question_html,
        "source": {"pairs": [{"first": p["first"], "second": p["second"]} for p in pairs]}
    }
    return _post_step(token, _step_base(lesson_id, position, block))


def create_fill_blanks_step(token, lesson_id, position, question_html, components):
    """
    components: [
      {"type": "text",  "text": "..."},
      {"type": "input", "options": ["answer1", "answer2"]},
      ...
    ]
    """
    block = {
        "name": "fill-blanks",
        "text": question_html,
        "source": {"components": components}
    }
    return _post_step(token, _step_base(lesson_id, position, block))


# ════════════════════════════════════════════════════════════════
#  УТИЛИТЫ ПАРСИНГА
# ════════════════════════════════════════════════════════════════

def md_to_html(text):
    """Markdown → HTML. Перед конвертацией удаляет HTML-комментарии."""
    cleaned = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL).strip()
    return md_lib.markdown(cleaned, extensions=["tables", "fenced_code", "nl2br"])


def parse_frontmatter(content):
    """
    Извлекает YAML frontmatter (между ---).
    Строки YAML-комментариев (#) внутри блока удаляются перед парсингом.
    Возвращает (meta_dict, body_string).
    """
    meta, body = {}, content
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if m:
        yaml_raw = m.group(1)
        yaml_clean = '\n'.join(l for l in yaml_raw.split('\n')
                               if not re.match(r'^\s*#', l))
        try:
            meta = yaml.safe_load(yaml_clean) or {}
        except yaml.YAMLError as e:
            print(f"⚠️  Ошибка YAML-фронтматера: {e}")
        body = content[m.end():]
    return meta, body


def strip_template_comments(body):
    """
    Удаляет декоративные строки-комментарии шаблона:
    # ═══..., # ───..., # УРОК 2.1..., # Синтаксис...
    """
    result = []
    for line in body.split('\n'):
        if re.match(r'^#\s*(═+|─+|УРОК\s+\d|Синтаксис)', line):
            continue
        result.append(line)
    return '\n'.join(result)


def extract_params(text):
    """Извлекает параметры <!-- key: value --> из тела шага."""
    params = {}
    for m in re.finditer(r'<!--\s*([\w-]+)\s*:\s*(.*?)\s*-->', text, re.DOTALL):
        key = m.group(1).lower()
        val = m.group(2).strip()
        if key == 'blank':
            # blank встречается несколько раз — собираем в список
            params.setdefault('_blanks', []).append(val)
        else:
            params[key] = val
    return params


def clean_option_text(text):
    """Убирает подсказки-маркеры из текста варианта ответа."""
    text = re.sub(r'\s*—\s*\*\*правильный\s*ответ.*?\*\*.*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*—\s*\*\*правильн.*?\*\*.*$',           '', text, flags=re.IGNORECASE)
    text = re.sub(r':\s*(относится|неправильный|правильный).*$','', text, flags=re.IGNORECASE)
    return text.strip()


# ════════════════════════════════════════════════════════════════
#  ОПРЕДЕЛЕНИЕ ТИПА И ПАРСИНГ ТЕЛА ШАГОВ
# ════════════════════════════════════════════════════════════════

STEP_TYPE_MAP = {
    'текст':    'text',
    'выбор':    'choice',
    'мульти':   'multi',
    'число':    'number',
    'строка':   'string',
    'эссе':     'free-answer',
    'порядок':  'sorting',
    'пары':     'matching',
    'пропуски': 'fill-blanks',
}


def detect_step_type(heading):
    """
    Определяет тип и заголовок шага из строки вида 'КЛЮЧЕВОЕ_СЛОВО: Заголовок'.
    Возвращает (step_type, clean_title).
    """
    m = re.match(r'^([\w]+):\s*(.*)', heading.strip(), re.IGNORECASE | re.UNICODE)
    if m:
        keyword   = m.group(1).lower()
        clean_ttl = m.group(2).strip()
        return STEP_TYPE_MAP.get(keyword, 'text'), clean_ttl
    return 'text', heading.strip()


def parse_choice_options(body):
    """
    Извлекает варианты ответа из строк вида:
      - [ ] неправильный вариант
      - [x] правильный вариант
    Возвращает (question_html, options_list).
    """
    lines = body.strip().split('\n')
    options, q_lines, in_opts = [], [], False

    for line in lines:
        m = re.match(r'^\s*-\s*\[([ xXхХ])\]\s*(.*)', line)
        if m:
            in_opts    = True
            is_correct = m.group(1).strip().lower() in ('x', 'х')
            text       = clean_option_text(m.group(2).strip())
            options.append({"text": text, "is_correct": is_correct, "feedback": ""})
        elif not in_opts and not re.match(r'^<!--', line):
            q_lines.append(line)

    q_md   = '\n'.join(q_lines).strip()
    q_html = md_to_html(q_md) if q_md else "<p>Выберите правильный ответ:</p>"
    return q_html, options


def parse_sorting_options(body):
    """
    Разбирает строки вида: - [N] Текст элемента
    Сортирует по N и возвращает (question_html, ordered_list).
    """
    lines = body.strip().split('\n')
    items, q_lines, in_items = [], [], False

    for line in lines:
        m = re.match(r'^\s*-\s*\[(\d+)\]\s*(.*)', line)
        if m:
            in_items = True
            items.append((int(m.group(1)), m.group(2).strip()))
        elif not in_items and not re.match(r'^<!--', line) and not re.match(r'^#\s', line):
            q_lines.append(line)

    items.sort(key=lambda x: x[0])
    ordered = [t for _, t in items]

    q_md   = '\n'.join(q_lines).strip()
    q_html = md_to_html(q_md) if q_md else "<p>Расставьте в правильном порядке:</p>"
    return q_html, ordered


def parse_matching_pairs(body):
    """
    Разбирает MD-таблицу (2 столбца) на список пар {"first": ..., "second": ...}.
    Пропускает заголовок и разделитель таблицы.
    Возвращает (question_html, pairs).
    """
    lines = body.strip().split('\n')
    pairs, q_lines, in_table = [], [], False

    HEADER_PATTERNS = re.compile(
        r'(левый столбец|правый столбец|роль|понятие|проблема|элемент)', re.IGNORECASE
    )

    for line in lines:
        if re.match(r'^\s*\|', line):
            in_table = True
            cells = [c.strip() for c in line.strip('|').split('|')]
            if len(cells) < 2:
                continue
            left, right = cells[0].strip(), cells[1].strip()
            # Пропускаем заголовок таблицы и строку-разделитель ---
            if re.match(r'^[-:\s]+$', left) or HEADER_PATTERNS.search(left):
                continue
            if left and right:
                pairs.append({"first": left, "second": right})
        elif not in_table and not re.match(r'^<!--', line) and not re.match(r'^#\s', line):
            q_lines.append(line)

    q_md   = '\n'.join(q_lines).strip()
    q_html = md_to_html(q_md) if q_md else "<p>Сопоставьте элементы:</p>"
    return q_html, pairs


def parse_fill_blanks(body):
    """
    Разбирает текст с {пропусками} и <!-- blank: слово = вар1 | вар2 -->.
    Возвращает (intro_html, components).

    components — список:
      {"type": "text",  "text": "..."}
      {"type": "input", "options": ["ответ1", "ответ2"]}
    """
    params = extract_params(body)

    # Словарь допустимых ответов для каждого пропуска
    blanks = {}
    for raw in params.get('_blanks', []):
        m = re.match(r'(.+?)\s*=\s*(.+)', raw)
        if m:
            key     = m.group(1).strip()
            answers = [a.strip() for a in m.group(2).split('|') if a.strip()]
            blanks[key] = answers

    # Извлекаем «чистый» текст (без HTML-комментариев и строк-комментариев)
    text_lines = [
        l for l in body.split('\n')
        if not re.match(r'^\s*<!--', l) and not re.match(r'^#\s', l)
    ]
    fill_text = '\n'.join(text_lines).strip()

    # Разбиваем на сегменты: текст / {пропуск} / текст ...
    components = []
    parts = re.split(r'\{(\w+)\}', fill_text)
    for i, part in enumerate(parts):
        if i % 2 == 0:          # чётные — текстовые сегменты
            if part.strip():
                components.append({"type": "text", "text": part})
        else:                    # нечётные — пропуски
            key     = part
            answers = blanks.get(key, [key])
            components.append({"type": "input", "options": answers})

    return "", components   # intro_html пустой — текст уже в components


# ════════════════════════════════════════════════════════════════
#  ГЛАВНЫЙ ПАРСЕР SCF v2 (# → ## → ### → ####)
# ════════════════════════════════════════════════════════════════

def parse_md_file(filepath):
    """
    Возвращает структуру:
    {
      title, summary, language,
      modules: [
        { title,
          lessons: [
            { title,
              steps: [ {type, title, body, params} ] }
          ]
        }
      ]
    }
    """
    content = Path(filepath).read_text(encoding='utf-8')
    meta, body = parse_frontmatter(content)
    body = strip_template_comments(body)

    # ── Метаданные ────────────────────────────────────────────────────────────
    course_title = str(meta.get('title', '')).strip()
    if not course_title:
        h1 = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
        course_title = h1.group(1).strip() if h1 else Path(filepath).stem

    raw_summary = str(meta.get('summary', '')).strip()
    if not raw_summary:
        after_h1 = re.split(r'^#\s+.+$', body, maxsplit=1, flags=re.MULTILINE)
        if len(after_h1) > 1:
            paras = [p.strip() for p in after_h1[1].split('\n\n')
                     if p.strip() and not p.strip().startswith('#')]
            if paras:
                raw_summary = paras[0]
    course_summary  = raw_summary[:255] if raw_summary else course_title
    course_language = str(meta.get('language', 'ru')).strip()

    # ── Модули (##) ───────────────────────────────────────────────────────────
    mod_re      = re.compile(r'^##\s+(.+)$', re.MULTILINE)
    mod_matches = list(mod_re.finditer(body))

    if not mod_matches:
        print("⚠️  Модули (## заголовки) не найдены. Проверьте структуру файла.")
        sys.exit(1)

    modules = []
    for mi, mm in enumerate(mod_matches):
        mod_title = mm.group(1).strip()
        m_start   = mm.end()
        m_end     = mod_matches[mi + 1].start() if mi + 1 < len(mod_matches) else len(body)
        mod_body  = body[m_start:m_end].strip()

        # ── Уроки (###) ───────────────────────────────────────────────────────
        les_re      = re.compile(r'^###\s+(.+)$', re.MULTILINE)
        les_matches = list(les_re.finditer(mod_body))

        lessons = []
        for li, lm in enumerate(les_matches):
            les_title = lm.group(1).strip()
            l_start   = lm.end()
            l_end     = les_matches[li + 1].start() if li + 1 < len(les_matches) else len(mod_body)
            les_body  = mod_body[l_start:l_end].strip()

            # ── Шаги (####) ───────────────────────────────────────────────────
            step_re      = re.compile(r'^####\s+(.+)$', re.MULTILINE)
            step_matches = list(step_re.finditer(les_body))

            steps = []
            if not step_matches:
                if les_body:
                    steps.append({"type": "text", "title": les_title,
                                  "body": les_body, "params": {}})
            else:
                for si, sm in enumerate(step_matches):
                    step_heading = sm.group(1).strip()
                    s_start      = sm.end()
                    s_end        = (step_matches[si + 1].start()
                                   if si + 1 < len(step_matches) else len(les_body))
                    step_body    = les_body[s_start:s_end].strip()
                    step_type, step_title = detect_step_type(step_heading)
                    steps.append({
                        "type":   step_type,
                        "title":  step_title,
                        "body":   step_body,
                        "params": extract_params(step_body),
                    })

            lessons.append({"title": les_title, "steps": steps})

        modules.append({"title": mod_title, "lessons": lessons})

    return {"title": course_title, "summary": course_summary,
            "language": course_language, "modules": modules}


# ════════════════════════════════════════════════════════════════
#  ДИСПЕТЧЕР: ВЫБОР ФУНКЦИИ ЗАГРУЗКИ ПО ТИПУ ШАГА
# ════════════════════════════════════════════════════════════════

def upload_step(token, lesson_id, position, step):
    stype  = step["type"]
    title  = step["title"]
    body   = step["body"]
    params = step["params"]

    # ── ТЕКСТ ─────────────────────────────────────────────────────────────────
    if stype == "text":
        html     = md_to_html(body)
        step_id  = create_text_step(token, lesson_id, position, title, html)
        print(f"      ✏️   [{position}] ТЕКСТ    : {title[:55]}")

    # ── ВЫБОР / МУЛЬТИ ────────────────────────────────────────────────────────
    elif stype in ("choice", "multi"):
        q_html, options = parse_choice_options(body)
        is_multiple     = (stype == "multi")
        preserve        = params.get("shuffle", "false").lower() != "true"
        step_id         = create_choice_step(token, lesson_id, position, q_html,
                                             options, is_multiple, preserve)
        kind    = "МУЛЬТИ" if is_multiple else "ВЫБОР"
        n_ok    = sum(1 for o in options if o["is_correct"])
        print(f"      ✅   [{position}] {kind:6s}   : {title[:45]} "
              f"({len(options)} вар., {n_ok} верных)")

    # ── ЧИСЛО ─────────────────────────────────────────────────────────────────
    elif stype == "number":
        q_html    = md_to_html(re.sub(r'<!--.*?-->', '', body, flags=re.DOTALL).strip())
        answer    = params.get("answer", "0")
        max_err   = params.get("precision", "0")
        step_id   = create_number_step(token, lesson_id, position, q_html, answer, max_err)
        print(f"      🔢   [{position}] ЧИСЛО    : {title[:50]} (ответ: {answer})")

    # ── СТРОКА ────────────────────────────────────────────────────────────────
    elif stype == "string":
        q_html    = md_to_html(re.sub(r'<!--.*?-->', '', body, flags=re.DOTALL).strip())
        answer    = params.get("answer", "")
        al_raw    = params.get("answer-aliases", "")
        aliases   = [a.strip() for a in al_raw.split("|") if a.strip()] if al_raw else []
        case_sens = params.get("case-sensitive", "false").lower() == "true"
        step_id   = create_string_step(token, lesson_id, position, q_html,
                                       answer, aliases, case_sens)
        print(f"      🔤   [{position}] СТРОКА   : {title[:50]} (ответ: {answer})")

    # ── ЭССЕ ──────────────────────────────────────────────────────────────────
    elif stype == "free-answer":
        q_html  = md_to_html(re.sub(r'<!--.*?-->', '', body, flags=re.DOTALL).strip())
        step_id = create_free_answer_step(token, lesson_id, position, q_html)
        print(f"      📝   [{position}] ЭССЕ     : {title[:55]}")

    # ── ПОРЯДОК ───────────────────────────────────────────────────────────────
    elif stype == "sorting":
        q_html, ordered = parse_sorting_options(body)
        step_id         = create_sorting_step(token, lesson_id, position, q_html, ordered)
        print(f"      🔀   [{position}] ПОРЯДОК  : {title[:48]} ({len(ordered)} эл.)")

    # ── ПАРЫ ──────────────────────────────────────────────────────────────────
    elif stype == "matching":
        q_html, pairs = parse_matching_pairs(body)
        step_id       = create_matching_step(token, lesson_id, position, q_html, pairs)
        print(f"      🔗   [{position}] ПАРЫ     : {title[:50]} ({len(pairs)} пар)")

    # ── ПРОПУСКИ ──────────────────────────────────────────────────────────────
    elif stype == "fill-blanks":
        intro_html, components = parse_fill_blanks(body)
        n_blanks = sum(1 for c in components if c["type"] == "input")
        step_id  = create_fill_blanks_step(token, lesson_id, position,
                                           intro_html, components)
        print(f"      ___  [{position}] ПРОПУСКИ : {title[:47]} ({n_blanks} пропусков)")

    # ── НЕИЗВЕСТНЫЙ ТИП → fallback text ──────────────────────────────────────
    else:
        html    = md_to_html(body)
        step_id = create_text_step(token, lesson_id, position, title, html)
        print(f"      ❓   [{position}] UNKNOWN({stype}) → загружен как ТЕКСТ: {title[:40]}")

    return step_id


# ════════════════════════════════════════════════════════════════
#  ПОЛНЫЙ ЦИКЛ ЗАГРУЗКИ КУРСА
# ════════════════════════════════════════════════════════════════

def upload_course(token, course_data):
    course_id = create_course(
        token,
        course_data["title"],
        course_data["summary"],
        course_data.get("language", "ru")
    )
    time.sleep(1)

    stats = {"modules": 0, "lessons": 0, "steps": 0, "by_type": {}}

    for mi, module in enumerate(course_data["modules"]):
        sec_id = create_section(token, course_id, module["title"], mi + 1)
        stats["modules"] += 1
        print(f"\n  📦 Модуль {mi + 1}: {module['title']}")
        time.sleep(0.5)

        for li, lesson in enumerate(module["lessons"]):
            les_id = create_lesson(token, lesson["title"])
            create_unit(token, sec_id, les_id, li + 1)
            stats["lessons"] += 1
            print(f"    📖 Урок {mi+1}.{li+1}: {lesson['title'][:60]} "
                  f"({len(lesson['steps'])} шагов)")
            time.sleep(0.5)

            for si, step in enumerate(lesson["steps"]):
                upload_step(token, les_id, si + 1, step)
                stats["steps"] += 1
                t = step["type"]
                stats["by_type"][t] = stats["by_type"].get(t, 0) + 1

    return course_id, stats


# ════════════════════════════════════════════════════════════════
#  ПРЕДПРОСМОТР СТРУКТУРЫ (--dry-run)
# ════════════════════════════════════════════════════════════════

def print_preview(course_data):
    SEP = "═" * 62
    print(f"\n{SEP}")
    print(f"  ПРЕДПРОСМОТР КУРСА")
    print(SEP)
    print(f"  Название : {course_data['title']}")
    print(f"  Summary  : {course_data['summary'][:72]}...")
    print(f"  Язык     : {course_data.get('language', 'ru')}")
    total_l = sum(len(m['lessons']) for m in course_data['modules'])
    total_s = sum(len(l['steps']) for m in course_data['modules']
                  for l in m['lessons'])
    print(f"  Модулей  : {len(course_data['modules'])}")
    print(f"  Уроков   : {total_l}")
    print(f"  Шагов    : {total_s}")
    print()

    all_types = {}
    for mi, module in enumerate(course_data['modules']):
        print(f"  📦 [{mi+1}] {module['title']}")
        for li, lesson in enumerate(module['lessons']):
            types = [s['type'] for s in lesson['steps']]
            tmap  = {t: types.count(t) for t in sorted(set(types))}
            tstr  = ', '.join(f"{t}×{n}" for t, n in tmap.items())
            print(f"       📖 [{mi+1}.{li+1}] {lesson['title'][:52]}  [{tstr}]")
            for t, n in tmap.items():
                all_types[t] = all_types.get(t, 0) + n

    print(f"\n  Типы шагов итого: {all_types}")
    print(f"{SEP}\n")


# ════════════════════════════════════════════════════════════════
#  ТОЧКА ВХОДА
# ════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python3 stepik_uploader_v2.py курс.md             # загрузить")
        print("  python3 stepik_uploader_v2.py курс.md --dry-run   # только превью")
        sys.exit(1)

    args = sys.argv[1:]

    if not args:
        print("Использование:")
        print("  stepik_uploader_v2.py курс.md --keys keys.env")
        print("  stepik_uploader_v2.py курс.md --keys keys.env --dry-run")
        sys.exit(0)

    filepath = next((a for a in args if not a.startswith("--")), None)
    if not filepath:
        print("❌ Не указан файл курса.")
        sys.exit(1)

    dry_run = "--dry-run" in args

    keys_file = None
    if "--keys" in args:
        idx = args.index("--keys")
        if idx + 1 < len(args) and not args[idx + 1].startswith("--"):
            keys_file = args[idx + 1]
        else:
            print("❌ После --keys укажите путь к файлу.")
            sys.exit(1)

    if not dry_run and keys_file is None:
        print("❌ Для загрузки нужен файл ключей: --keys keys.env")
        print("   Для предпросмотра используйте: --dry-run")
        sys.exit(1)

    if not Path(filepath).exists():
        print(f"❌ Файл не найден: {filepath}")
        sys.exit(1)

    print(f"📄 Читаю файл: {filepath}\n")
    course_data = parse_md_file(filepath)
    print_preview(course_data)

    if dry_run:
        print("ℹ️  Режим --dry-run: загрузка не выполняется.")
        sys.exit(0)

    confirm = input("🚀 Загрузить курс на Stepik? [y/N]: ").strip().lower()
    if confirm != 'y':
        print("Отменено.")
        sys.exit(0)

    print("\n🔑 Получаю токен...")
    token = get_token()

    course_id, stats = upload_course(token, course_data)

    SEP = "═" * 62
    print(f"\n{SEP}")
    print(f"  КУРС УСПЕШНО ЗАГРУЖЕН")
    print(SEP)
    print(f"  ID курса  : {course_id}")
    print(f"  Модулей   : {stats['modules']}")
    print(f"  Уроков    : {stats['lessons']}")
    print(f"  Шагов     : {stats['steps']}")
    print(f"  По типам  : {stats['by_type']}")
    print(f"\n  Редактор  : https://stepik.org/course/{course_id}/edit")
    print(f"  Просмотр  : https://stepik.org/course/{course_id}/promo")
    print(SEP)
    print()
    print("  ⚠️  Вручную в редакторе Stepik необходимо:")
    print("      • Загрузить обложку (1280×720 px, JPG/PNG)")
    print("      • Добавить промо-видео (YouTube/Vimeo)")
    print("      • Заполнить полное описание, теги, авторов")
    print("      • Нажать «Publish» для публикации курса")
    print()


if __name__ == "__main__":
    main()
