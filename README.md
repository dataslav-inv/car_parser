# Парсер оголошень авто: AUTO.RIA, RST, OLX

Єдина база актуальних оголошень з фільтрами та історією ціни. Телефони та імена продавців не зберігаються. Перевірки «ви не бот» не обходяться: якщо платформа їх показала, збережіть вивід у браузері та передайте файл через `--html`.

## Запуск

```bash
cd car_parser
python3 -m parser search --brand Mitsubishi --model Lancer --year-from 2004 --year-to 2012 --price-to 5000 --pages 3
python3 -m parser show --brand Skoda --price-to 11000
python3 -m parser stats --brand Skoda --model Octavia
python3 -m parser export --out data/listings.csv
```

База за замовчуванням: `data/listings.sqlite`.

Налаштування можна перевизначати через `.env` (скопіюйте `.env.example` у `.env`):

```bash
cp .env.example .env
```

Доступні змінні:

- `CAR_PARSER_DB_PATH` — шлях до SQLite-бази
- `CAR_PARSER_SOURCES` — список джерел, наприклад `autoria,rst,olx`
- `CAR_PARSER_PAGES` — кількість сторінок для пошуку
- `CAR_PARSER_DELAY` — пауза між запитами до сайтів

Точний фільтр сайту надійніший за вгаданий URL. Зберіть вивід на AUTO.RIA та передайте посилання:

```bash
python3 -m parser search --url "https://auto.ria.com/uk/car/skoda/octavia/?page=0&size=20" --sources autoria
```

RST та OLX зараз часто блокують прямий запит перевіркою. Тоді:

```bash
python3 -m parser search --html rst.html --html-source rst --brand Skoda --model Octavia
python3 -m parser search --html olx.html --html-source olx --brand Skoda
```

Повторний `search` не стирає ціну: зміна записується в `price_events`. `stats` рахує медіану, 25-й та 75-й перцентиль і зріз за місяцями. Сезонність з’явиться після щоденних запусків; готового архіву за попередні роки у платформ немає.
