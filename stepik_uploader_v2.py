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
  ТАБЛИЦА  → table

Иерархия файла:  # Курс  →  ## Модуль  →  ### Урок  →  #### Шаг

Использование:
    python3 stepik_uploader_v2.py курс.md --keys keys.env           # загрузка
    python3 stepik_uploader_v2.py курс.md --keys keys.env --dry-run # предпросмотр

    keys.env содержит две строки:
        STEPIK_CLIENT_ID=ВАШ_ID
        STEPIK_CLIENT_SECRET=ВАШ_SECRET
    Получить ключи: https://stepik.org/oauth2/applications/

Требования:
    pip install requests pyyaml markdown
"""

import os
import sys
import re
import time
import requests
import yaml
import markdown as md_lib
from pathlib import Path

BASE_URL      = "https://stepik.org"
REQUEST_DELAY = 0.4
API_TIMEOUT   = 30
API_RETRIES   = 3


# ════════════════════════════════════════════════════════════════
#  АВТОРИЗАЦИЯ И БАЗОВЫЕ ВЫЗОВЫ
# ════════════════════════════════════════════════════════════════

def load_credentials(keys_file=None):
    """
    Читает CLIENT_ID и CLIENT_SECRET из:
      1. keys_file (--keys путь/к/keys.env)
      2. Переменных окружения STEPIK_CLIENT_ID / STEPIK_CLIENT_SECRET
    """
    client_id     = os.environ.get("STEPIK_CLIENT_ID", "")
    client_secret = os.environ.get("STEPIK_CLIENT_SECRET", "")

    if keys_file:
        kp = Path(keys_file)
        if not kp.exists():
            print(f"❌ Файл ключей не найден: {keys_file}")
            sys.exit(1)
        for line in kp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("STEPIK_CLIENT_ID="):
                client_id = line.split("=", 1)[1].strip()
            elif line.startswith("STEPIK_CLIENT_SECRET="):
                client_secret = line.split("=", 1)[1].strip()

    if not client_id or not client_secret:
        print("❌ Не найдены API-ключи Stepik.")
        print("   Укажите через: --keys keys.env")
        print("   или через переменные окружения STEPIK_CLIENT_ID / STEPIK_CLIENT_SECRET")
        sys.exit(1)

    return client_id, client_secret


def get_token(client_id, client_secret):
    resp = requests.post(
        f"{BASE_URL}/oauth2/token/",
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=API_TIMEOUT,
    )
    resp.raise_for_status()
    print("✅ Авторизация успешна")
    return resp.json()["access_token"]


def api_post(token, endpoint, payload):
    """timeout и exponential backoff retry на 429/5xx."""
    headers = {"Authorization": f"Bearer {token}"}
    for attempt in range(API_RETRIES):
        try:
            resp = requests.post(
                f"{BASE_URL}/api/{endpoint}",
                headers=headers,
                json=payload,
                timeout=API_TIMEOUT,
            )
        except requests.exceptions.Timeout:
            wait = 2 ** attempt
            print(f"⏳ Таймаут [{endpoint}], повтор через {wait}с (попытка {attempt+1}/{API_RETRIES})")
            time.sleep(wait)
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            wait = 2 ** attempt
            print(f"⏳ {resp.status_code} [{endpoint}], повтор через {wait}с (попытка {attempt+1}/{API_RETRIES})")
            time.sleep(wait)
            continue

        if not resp.ok:
            print(f"❌ Ошибка {resp.status_code} [{endpoint}]: {resp.text[:500]}")
            resp.raise_for_status()

        time.sleep(REQUEST_DELAY)
        return resp.json()

    print(f"❌ Все {API_RETRIES} попытки исчерпаны для [{endpoint}]")
    raise RuntimeError(f"API endpoint {endpoint} недоступен после {API_RETRIES} попыток")


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


def create_section(token, course_id, title, position, description=""):
    payload = {"title": title, "course": course_id, "position": position}
    if description:
        payload["description"] = description
    data = api_post(token, "sections", {"section": payload})
    return data["sections"][0]["id"]


def create_lesson(token, title, description=""):
    payload = {"title": title, "language": "ru"}
    if description:
        payload["description"] = description
    data = api_post(token, "lessons", {"lesson": payload})
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
                       options_data, is_multiple=False, preserve_order=True,
                       feedback_correct="", feedback_wrong=""):
    source = {
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
    if feedback_correct:
        source["feedback_correct"] = feedback_correct
    if feedback_wrong:
        source["feedback_wrong"] = feedback_wrong
    block = {"name": "choice", "text": question_html, "source": source}
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
    all_answers = [answer] + (aliases or [])
    escaped = [re.escape(a.strip()) for a in all_answers if a.strip()]
    pattern = "|".join(escaped) if len(escaped) > 1 else (escaped[0] if escaped else answer)
    block = {
        "name": "string",
        "text": question_html,
        "source": {"pattern": pattern, "case_sensitive": case_sensitive, "code": "", "use_re": False, "match_substring": False}
    }
    return _post_step(token, _step_base(lesson_id, position, block))


def create_free_answer_step(token, lesson_id, position, question_html,
                            min_words=None, max_words=None, peer_review=False):
    source = {"is_attachments_enabled": False, "is_html_enabled": True}
#    if min_words is not None:
#        source["min_words"] = int(min_words)
#    if max_words is not None:
#        source["max_words"] = int(max_words)
    if peer_review:
        source["manual_scoring"] = True
    block = {"name": "free-answer", "text": question_html, "source": source}
    return _post_step(token, _step_base(lesson_id, position, block))


def create_sorting_step(token, lesson_id, position, question_html, options_ordered):
    block = {
        "name": "sorting",
        "text": question_html,
        "source": {"options": [{"text": o} for o in options_ordered]}
    }
    return _post_step(token, _step_base(lesson_id, position, block))


def create_matching_step(token, lesson_id, position, question_html, pairs,
                         shuffle_rows=False):
    source = {"pairs": [{"first": p["first"], "second": p["second"]} for p in pairs], "preserve_firsts_order": True, "preserve_seconds_order": False}
    if shuffle_rows:
        source["is_options_feedback"] = False
        source["preserve_order"] = False
    block = {"name": "matching", "text": question_html, "source": source}
    return _post_step(token, _step_base(lesson_id, position, block))


def create_fill_blanks_step(token, lesson_id, position, question_html, components):
    block = {
        "name": "fill-blanks",
        "text": question_html,
        "source": {"components": components, "is_case_sensitive": False}
    }
    return _post_step(token, _step_base(lesson_id, position, block))


def create_table_step(token, lesson_id, position, question_html, rows, cols,
                      correct_cells=None):
    correct_cells = correct_cells or []
    cell_list = []
    for r_i, row in enumerate(rows):
        for c_i, col in enumerate(cols):
            cell_list.append({
                "name": f"{row} / {col}",
                "is_correct": [r_i, c_i] in correct_cells,
            })
    block = {
        "name": "table",
        "text": question_html,
        "source": {
            "columns": [{"name": c} for c in cols],
            "rows": [{"name": r} for r in rows],
            "options": cell_list,
            "is_checkbox": True,
        }
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
    Удаляет строки-комментарии шаблона перед парсингом:
      - обычные YAML-комментарии:  # ...
      - комментарии шаблона SCF:  /# ...
    Возвращает (meta_dict, body_string).
    """
    meta, body = {}, content
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if m:
        yaml_raw = m.group(1)
        yaml_clean = '\n'.join(
            l for l in yaml_raw.split('\n')
            if not re.match(r'^\s*/?(#|/#)', l)  # фильтр: # ... и /# ...
        )
        try:
            meta = yaml.safe_load(yaml_clean) or {}
        except yaml.YAMLError as e:
            print(f"⚠️  Ошибка YAML-фронтматера: {e}")
        body = content[m.end():]
    return meta, body


def strip_template_comments(body):
    """
    Удаляет декоративные строки-комментарии шаблона из тела документа:
    # ═══..., # ───..., /# ═══..., /# УРОК 2.1..., /# Синтаксис...
    """
    result = []
    for line in body.split('\n'):
        if re.match(r'^/?#\s*(═+|─+|УРОК\s+\d|Синтаксис)', line):
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
            params.setdefault('_blanks', []).append(val)
        else:
            params[key] = val
    return params


def clean_option_text(text):
    """Убирает шаблонные маркеры из текста варианта ответа."""
    text = re.sub(r'\s*—\s*\*\*правильный\s*ответ.*?\*\*.*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*—\s*\*\*правильн.*?\*\*.*$',           '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*[—–-]\s*(относится|неправильный|правильный|распространённое).*$',
                  '', text, flags=re.IGNORECASE)
    text = re.sub(r':\s*(относится|неправильный|правильный|это признак|это следствие|это последствие).*$',
                  '', text, flags=re.IGNORECASE)
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
    'таблица':  'table',
}


def detect_step_type(heading):
    m = re.match(r'^([\w]+):\s*(.*)', heading.strip(), re.IGNORECASE | re.UNICODE)
    if m:
        keyword   = m.group(1).lower()
        clean_ttl = m.group(2).strip()
        return STEP_TYPE_MAP.get(keyword, 'text'), clean_ttl
    return 'text', heading.strip()


def parse_choice_options(body):
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
    Заголовок таблицы определяется по позиции (1-я строка),
    а не по словарному матчингу ключевых слов.
    """
    lines = body.strip().split('\n')
    pairs, q_lines = [], []
    in_table     = False
    header_found = False
    sep_found    = False

    for line in lines:
        if re.match(r'^\s*\|', line):
            in_table = True
            cells = [c.strip() for c in line.strip('|').split('|')]
            if len(cells) < 2:
                continue
            left, right = cells[0].strip(), cells[1].strip()

            if not header_found:
                header_found = True
                continue

            if not sep_found:
                sep_found = True
                continue

            if left and right:
                pairs.append({"first": left, "second": right})
        elif not in_table and not re.match(r'^<!--', line) and not re.match(r'^#\s', line):
            q_lines.append(line)

    q_md   = '\n'.join(q_lines).strip()
    q_html = md_to_html(q_md) if q_md else "<p>Сопоставьте элементы:</p>"
    return q_html, pairs


def parse_fill_blanks(body):
    params = extract_params(body)

    blanks = {}
    for raw in params.get('_blanks', []):
        m = re.match(r'(.+?)\s*=\s*(.+)', raw)
        if m:
            key     = m.group(1).strip()
            answers = [a.strip() for a in m.group(2).split('|') if a.strip()]
            blanks[key] = answers

    text_lines = [
        l for l in body.split('\n')
        if not re.match(r'^\s*<!--', l) and not re.match(r'^#\s', l)
    ]
    fill_text = '\n'.join(text_lines).strip()

    components = []
    parts = re.split(r'\{(\w+)\}', fill_text)
    for i, part in enumerate(parts):
        if i % 2 == 0:
            if part.strip():
                components.append({"type": "text", "text": part, "options": []})
        else:
            key     = part
            answers = blanks.get(key, [key])
            components.append({"type": "input", "text": "", "options": [{"text": answers[0], "is_correct": True}] + [{"text": a, "is_correct": False} for a in answers[1:]]})

    return "", components


# ════════════════════════════════════════════════════════════════
#  ГЛАВНЫЙ ПАРСЕР SCF v2 (# → ## → ### → ####)
# ════════════════════════════════════════════════════════════════

def parse_md_file(filepath):
    content = Path(filepath).read_text(encoding='utf-8')
    meta, body = parse_frontmatter(content)
    body = strip_template_comments(body)

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

        sec_desc_m = re.match(r'\s*<!--\s*section-description\s*:\s*(.*?)\s*-->', mod_body, re.DOTALL)
        sec_desc   = sec_desc_m.group(1).strip() if sec_desc_m else ""

        les_re      = re.compile(r'^###\s+(.+)$', re.MULTILINE)
        les_matches = list(les_re.finditer(mod_body))

        lessons = []
        for li, lm in enumerate(les_matches):
            les_title = lm.group(1).strip()
            l_start   = lm.end()
            l_end     = les_matches[li + 1].start() if li + 1 < len(les_matches) else len(mod_body)
            les_body  = mod_body[l_start:l_end].strip()

            les_desc_m = re.match(r'\s*<!--\s*lesson-description\s*:\s*(.*?)\s*-->', les_body, re.DOTALL)
            les_desc   = les_desc_m.group(1).strip() if les_desc_m else ""

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

            lessons.append({"title": les_title, "description": les_desc, "steps": steps})

        modules.append({"title": mod_title, "description": sec_desc, "lessons": lessons})

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
    step_id = None

    if stype == "text":
        html    = md_to_html(body)
        step_id = create_text_step(token, lesson_id, position, title, html)
        print(f"      ✏️   [{position}] ТЕКСТ    : {title[:55]}")

    elif stype in ("choice", "multi"):
        q_html, options = parse_choice_options(body)
        if not options:
            print(f"      ⚠️   [{position}] {stype.upper():6s}: нет вариантов ответа в '{title[:45]}' — пропущен")
            return None
        is_multiple = (stype == "multi")
        preserve    = params.get("shuffle", "false").lower() != "true"
        fb_ok       = params.get("feedback-correct", "")
        fb_err      = params.get("feedback-wrong", "")
        step_id     = create_choice_step(
            token, lesson_id, position, q_html,
            options, is_multiple, preserve, fb_ok, fb_err
        )
        kind  = "МУЛЬТИ" if is_multiple else "ВЫБОР"
        n_ok  = sum(1 for o in options if o["is_correct"])
        print(f"      ✅   [{position}] {kind:6s}   : {title[:45]} "
              f"({len(options)} вар., {n_ok} верных)")

    elif stype == "number":
        q_html  = md_to_html(re.sub(r'<!--.*?-->', '', body, flags=re.DOTALL).strip())
        answer  = params.get("answer", "0")
        max_err = params.get("precision", "0")
        step_id = create_number_step(token, lesson_id, position, q_html, answer, max_err)
        print(f"      🔢   [{position}] ЧИСЛО    : {title[:50]} (ответ: {answer})")

    elif stype == "string":
        q_html    = md_to_html(re.sub(r'<!--.*?-->', '', body, flags=re.DOTALL).strip())
        answer    = params.get("answer", "")
        al_raw    = params.get("answer-aliases", "")
        aliases   = [a.strip() for a in al_raw.split("|") if a.strip()] if al_raw else []
        case_sens = params.get("case-sensitive", "false").lower() == "true"
        step_id   = create_string_step(token, lesson_id, position, q_html,
                                       answer, aliases, case_sens)
        print(f"      🔤   [{position}] СТРОКА   : {title[:50]} (ответ: {answer})")

    elif stype == "free-answer":
        q_html  = md_to_html(re.sub(r'<!--.*?-->', '', body, flags=re.DOTALL).strip())
        min_w   = params.get("min-words")
        max_w   = params.get("max-words")
        peer    = params.get("peer-review", "false").lower() == "true"
        step_id = create_free_answer_step(
            token, lesson_id, position, q_html, min_w, max_w, peer
        )
        print(f"      📝   [{position}] ЭССЕ     : {title[:55]}")

    elif stype == "sorting":
        q_html, ordered = parse_sorting_options(body)
        step_id         = create_sorting_step(token, lesson_id, position, q_html, ordered)
        print(f"      🔀   [{position}] ПОРЯДОК  : {title[:48]} ({len(ordered)} эл.)")

    elif stype == "matching":
        q_html, pairs = parse_matching_pairs(body)
        shuffle_r = params.get("shuffle-rows", "false").lower() == "true"
        step_id   = create_matching_step(token, lesson_id, position, q_html, pairs, shuffle_r)
        print(f"      🔗   [{position}] ПАРЫ     : {title[:50]} ({len(pairs)} пар)")

    elif stype == "fill-blanks":
        intro_html, components = parse_fill_blanks(body)
        n_blanks = sum(1 for c in components if c["type"] == "input")
        step_id  = create_fill_blanks_step(token, lesson_id, position, intro_html, components)
        print(f"      🔲   [{position}] ПРОПУСКИ : {title[:46]} ({n_blanks} пропусков)")

    elif stype == "table":
        q_html, pairs = parse_matching_pairs(body)
        rows = list(dict.fromkeys(p["first"]  for p in pairs))
        cols = list(dict.fromkeys(p["second"] for p in pairs))
        correct_raw = params.get("correct", "")
        correct_cells = []
        for cell in correct_raw.split(";"):
            cell = cell.strip()
            parts = cell.split(",")
            if len(parts) == 2:
                try:
                    correct_cells.append([int(parts[0]), int(parts[1])])
                except ValueError:
                    pass
        step_id = create_table_step(token, lesson_id, position, q_html,
                                    rows, cols, correct_cells)
        print(f"      🗂️   [{position}] ТАБЛИЦА  : {title[:48]} ({len(rows)}×{len(cols)})")

    else:
        html    = md_to_html(body)
        step_id = create_text_step(token, lesson_id, position, title, html)
        print(f"      ⚠️   [{position}] НЕИЗВ.   : '{stype}' → загружен как ТЕКСТ: {title[:40]}")

    return step_id


# ════════════════════════════════════════════════════════════════
#  ЗАГРУЗКА КУРСА
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
        sec_id = create_section(
            token, course_id, module["title"], mi + 1,
            description=module.get("description", "")
        )
        stats["modules"] += 1
        print(f"\n  📦 Модуль {mi + 1}: {module['title']}")
        time.sleep(0.5)

        for li, lesson in enumerate(module["lessons"]):
            les_id = create_lesson(
                token, lesson["title"],
                description=lesson.get("description", "")
            )
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
    s = course_data['summary']
    print(f"  Summary  : {s[:72]}{('...' if len(s) > 72 else '')}")
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
    args = sys.argv[1:]
    if not args:
        print("Использование:")
        print("  python3 stepik_uploader_v2.py курс.md --keys keys.env")
        print("  python3 stepik_uploader_v2.py курс.md --keys keys.env --dry-run")
        print()
        print("  keys.env содержит:")
        print("    STEPIK_CLIENT_ID=ВАШ_ID")
        print("    STEPIK_CLIENT_SECRET=ВАШ_SECRET")
        print()
        print("  Также можно задать переменные окружения:")
        print("    export STEPIK_CLIENT_ID=...")
        print("    export STEPIK_CLIENT_SECRET=...")
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
            print("❌ После --keys укажите путь к файлу (например: --keys keys.env).")
            sys.exit(1)

    if not dry_run and keys_file is None and \
            not os.environ.get("STEPIK_CLIENT_ID"):
        print("❌ Для загрузки нужны API-ключи.")
        print("   Передайте через: --keys keys.env")
        print("   или через переменные окружения STEPIK_CLIENT_ID / STEPIK_CLIENT_SECRET")
        print("   Для предпросмотра без загрузки используйте: --dry-run")
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
    client_id, client_secret = load_credentials(keys_file)
    token = get_token(client_id, client_secret)

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
