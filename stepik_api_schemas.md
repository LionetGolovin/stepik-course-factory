# Stepik API — Реальные схемы step-sources

> Официальная документация (https://github.com/StepicOrg/Stepik-API)[Stepik-API] не содержит схем payload для типов шагов.
> Все поля ниже выявлены методом реверс-инжиниринга в марте 2026.
> Верифицированы успешной загрузкой курса ID 280295 (3 модуля, 11 уроков, 25 шагов).

---

## Общая структура запроса

POST /api/step-sources
```json
{
  "stepSource": {
    "lesson": 12345,
    "position": 1,
    "block": {
      "name": "<тип>",
      "text": "<HTML>",
      "source": { ... }
    }
  }
}
```

## ТЕКСТ (text) — source не нужен

## ВЫБОР / МУЛЬТИ (choice)
```json
"source": {
  "options": [{"text": "...", "is_correct": true, "feedback": ""}],
  "is_always_correct": false, "is_html_enabled": true,
  "sample_size": 3, "is_multiple_choice": false,
  "preserve_order": true, "is_options_feedback": false
}
```

## ЧИСЛО (number)
```json
"source": {"options": [{"answer": "42", "max_error": "0"}]}
```

## СТРОКА (string) — все 5 полей обязательны
```json
"source": {
  "pattern": "ответ1|ответ2",
  "case_sensitive": false,
  "code": "",
  "use_re": false,
  "match_substring": false
}
```

## ЭССЕ (free-answer) — min_words/max_words API не принимает
```json
"source": {
  "is_attachments_enabled": false,
  "is_html_enabled": true,
  "manual_scoring": false
}
```

## ПОРЯДОК (sorting) — options: список dict, не строк
```json
"source": {"options": [{"text": "Первый"}, {"text": "Второй"}]}
```

## ПАРЫ (matching) — preserve_*_order обязательны
```json
"source": {
  "pairs": [{"first": "A", "second": "1"}],
  "preserve_firsts_order": true,
  "preserve_seconds_order": false
}
```

## ПРОПУСКИ (fill-blanks) — самый сложный тип
```json
"source": {
  "is_case_sensitive": false,
  "components": [
    {"type": "text",  "text": "Вставьте: ", "options": []},
    {"type": "input", "text": "",
     "options": [
       {"text": "правильный", "is_correct": true},
       {"text": "вариант2",   "is_correct": false}
     ]}
  ]
}
```

## ТАБЛИЦА (table)
```json
"source": {
  "columns": [{"name": "Столбец 1"}],
  "rows": [{"name": "Строка 1"}],
  "options": [{"name": "Строка 1 / Столбец 1", "is_correct": true}],
  "is_checkbox": true
}
```

## Ограничения
- title курса: макс 64 символа
- summary курса: макс 255 символов
- Обложка, видео, теги — только через веб-редактор
- Rate limit: рекомендуется REQUEST_DELAY >= 0.4s
