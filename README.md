# OKSP_HW2 — нагрузочное испытание сервиса библиотеки

Домашнее задание № 2 по дисциплине «Оптимизация клиент-серверных приложений».
Вариант 1. Персональный префикс стенда задаётся локально в `.env`.

Репозиторий: https://github.com/Maxus17/OKSP_HW2

Здесь находится сервис библиотеки из ДЗ 1 вместе со средствами ДЗ 2: открытая нагрузка k6, сбор ресурсов приложения и PostgreSQL, профиль py-spy и анализ результатов.

## Запуск

Нужны Ubuntu/WSL2, Docker Engine и Docker Compose.

```bash
git clone https://github.com/Maxus17/OKSP_HW2.git
cd OKSP_HW2
cp .env.example .env
nano .env
```

В `.env` задайте `PERSONAL_PREFIX=your_name` и собственные значения `DB_PASSWORD`, `API_PASSWORD`. Для пароля БД используйте буквы и цифры: он входит в URL подключения. В опубликованном примере значения паролей пустые.

```bash
docker compose -f compose.yaml -f compose.hw2.yaml up -d --build app db
docker compose -f compose.yaml -f compose.hw2.yaml exec app python -m pytest -q
docker compose -f compose.yaml -f compose.hw2.yaml run --rm --no-deps k6 version
```

Интерфейс: http://localhost:20001. Учётная запись API — `librarian`.

## Нагрузочные испытания

Перед каждой ступенью скрипт восстанавливает рабочее наполнение учебной БД. Ручные изменения учебных выдач при этом удаляются.

```bash
python3 load/run_step.py mixed 2
python3 load/run_step.py heavy 2
```

Режимы испытываются отдельными лестницами. Удваивайте частоту последовательно: 2, 4, 8, 16, 32, 64… Остановитесь при первом нарушении порога или появлении пропусков. Между запусками скрипт ждёт простоя. Ступень длится 30 секунд; частота и длительность задаются параметрами.

Критерии: p95 < 500 мс, неожиданные ошибки < 1%. Пропуски `dropped_iterations` учитываются отдельно. Ожидаемые конфликты 409 при выдаче и возврате считаются бизнес-отказами.

## Профиль и анализ

Повторите частоту излома тяжёлой операции с `--profile`. Например, если излом найден на 64 запросах/с:

```bash
python3 load/run_step.py heavy 64 --profile
docker compose -f compose.yaml -f compose.hw2.yaml exec app python load/explain.py
python3 load/analyze.py
```

Профиль снимается 15 секунд на 10 Гц; частоту можно изменить через `--profile-rate`. Ресурсы собираются каждые две секунды. Результаты и профиль сохраняются локально в `results/hw2/`.

Полная методика, веса операций и правила интерпретации: [README_HW2.md](README_HW2.md).
Происхождение исходников: [MEASURED_VERSION.md](MEASURED_VERSION.md).
