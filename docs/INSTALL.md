# Установка QuizUpdater на другой Mac (в том числе Intel)

Документ написан и для человека, и для **Claude Code**, который выполняет установку на этом Mac.
Пометки: 🤖 — делает Claude сам, 👤 — нужен человек (клик в окне, файл с другого Mac).

Если ты Claude Code и пользователь попросил «установи QuizUpdater» — сначала прочитай «Правила», затем иди по шагам 1–8 сверху вниз,
после каждого шага сверяйся с «Ожидаемым результатом» и не переходи дальше, пока он не совпал.

## Правила (обязательно)

1. **Ключ сервисного аккаунта — секрет.** Не читай его содержимое, не печатай в ответах и логах, не
   коммить, не загружай никуда (ни в GitHub, ни в релизы, ни в чаты). Работай только с путём к файлу.
2. **Презентации Keynote не меняй.** Для проверок — только чтение и `--dry-run` (он ничего не меняет).
3. **Не запускай `/usr/bin/python3`, пока не убедился, что Command Line Tools установлены** (шаг 2):
   без них macOS откроет окно установки и команда зависнет.
4. Не используй `sudo`: установка идёт в `/Applications` и домашнюю папку пользователя.
5. На шагах 👤 остановись, объясни человеку, что сделать, и дождись ответа. Не придумывай путь к ключу.
6. В конце выдай человеку итог по чек-листу из шага 8: что проверено, что нет.

## Что нужно и что получится

| | |
|---|---|
| Mac | Intel (`x86_64`) или Apple Silicon (`arm64`) — приложение универсальное |
| macOS | 13 (Ventura) или новее |
| Command Line Tools | нужны: из них берётся системный `/usr/bin/python3` 3.9, на котором работает бэкенд |
| Keynote | установлен |
| Интернет | нужен при установке и при работе (таблица берётся с Google Drive) |
| От человека | JSON-ключ сервисного аккаунта (файл `service-account.json`) с первого Mac |

Что получится: `/Applications/QuizUpdater.app`, ключ в `~/Library/Application Support/QuizUpdater/`,
выбранная таблица результатов в настройках приложения. Устанавливать Python-пакеты вручную не нужно —
они внутри `.app`.

## Шаг 1. Проверить Mac 🤖

```bash
sw_vers -productVersion        # ожидается 13.0 или больше
uname -m                       # x86_64 (Intel) или arm64 (Apple Silicon)
ls -d /Applications/Keynote.app
```

Ожидаемый результат: версия ≥ 13, Keynote найден. Если macOS старше 13 — остановись и сообщи человеку:
приложение не запустится.

## Шаг 2. Command Line Tools 🤖/👤

```bash
xcode-select -p                # ожидается путь, например /Library/Developer/CommandLineTools
```

Если команда вернула ошибку — CLT нет:

```bash
xcode-select --install         # откроет системное окно
```

👤 Человек нажимает «Установить» в появившемся окне и ждёт окончания (несколько минут). После этого снова
`xcode-select -p` — должен вернуть путь. Только теперь можно запускать Python:

```bash
/usr/bin/python3 --version     # ожидается Python 3.9.x (допустимо и новее)
```

## Шаг 3. Получить приложение 🤖

### Вариант А — готовый релиз (быстрее всего)

Проверь, что релиз есть:

```bash
gh release list --repo shancept/quiz-updater 2>/dev/null | head -3
# или без gh:
curl -fsI https://github.com/shancept/quiz-updater/releases/latest/download/QuizUpdater-universal.zip | head -1
```

`HTTP/2 302` (или релиз в списке `gh`) — релиз есть. `HTTP/2 404` или пустой список — релиза ещё нет,
переходи к варианту Б. Если релиз есть — скачай и проверь контрольную сумму:

```bash
mkdir -p ~/Downloads/QuizUpdater-install && cd ~/Downloads/QuizUpdater-install
curl -fL -O https://github.com/shancept/quiz-updater/releases/latest/download/QuizUpdater-universal.zip
curl -fL -O https://github.com/shancept/quiz-updater/releases/latest/download/QuizUpdater-universal.zip.sha256
shasum -a 256 -c QuizUpdater-universal.zip.sha256
```

Ожидаемый результат: `QuizUpdater-universal.zip: OK`. Если не `OK` — не устанавливай, скачай заново; если и
тогда не сошлось, сообщи человеку.

Файлы, скачанные через `curl`, обычно не получают метку карантина macOS — но шаг 4 снимает её на всякий случай.

### Вариант Б — собрать из исходников (если релиза нет)

Нужны только Command Line Tools (полный Xcode не нужен) и интернет (зависимости ставятся с PyPI):

```bash
git clone https://github.com/shancept/quiz-updater.git ~/quiz-updater && cd ~/quiz-updater
make app                       # 3–5 минут; соберёт dist/QuizUpdater.app
```

Ожидаемый результат: строка `Собрано: dist/QuizUpdater.app` и `x86_64 arm64`. Если сборка под вторую
архитектуру падает, а Mac Intel — собери только под него: `make app ARCHS=x86_64` (на Apple Silicon:
`make app ARCHS=arm64`). Остальной шаг 4 выполняй с `dist/QuizUpdater.app` вместо распакованного архива.

## Шаг 4. Установить в «Программы» и снять карантин 🤖

Если приложение уже установлено и запущено — сначала закрой его (`osascript -e 'tell application "QuizUpdater" to quit'`).
Старую версию удаляй только при обновлении и только вместе с этим шагом (ключ и настройки лежат вне `.app`
и сохранятся).

```bash
cd ~/Downloads/QuizUpdater-install                       # вариант А; для варианта Б — ~/quiz-updater
rm -rf /Applications/QuizUpdater.app                      # только если это обновление
ditto -x -k QuizUpdater-universal.zip /Applications       # вариант Б: ditto dist/QuizUpdater.app /Applications/QuizUpdater.app
xattr -dr com.apple.quarantine /Applications/QuizUpdater.app
codesign --verify --deep --strict /Applications/QuizUpdater.app && echo "подпись валидна"
lipo -archs /Applications/QuizUpdater.app/Contents/MacOS/QuizUpdater
```

Ожидаемый результат: `подпись валидна` и в списке архитектур есть архитектура этого Mac (`x86_64` для Intel).

> Приложение подписано «ad-hoc» (без платного Apple-аккаунта) и не нотаризовано. Если карантин не снять,
> macOS при запуске скажет, что разработчик не проверен или файл «повреждён», — это он. Команда `xattr`
> выше это лечит. Альтернатива для человека: «Системные настройки → Конфиденциальность и безопасность →
> Всё равно открыть».

## Шаг 5. Проверить бэкенд без окна 🤖

```bash
B=/Applications/QuizUpdater.app/Contents/Resources/backend
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$B:$B/vendor"
/usr/bin/python3 -m quiz_backend drive-status
```

Ожидаемый результат (ключа ещё нет): `{"ok": true, "connected": false, "clientEmail": null}`.
Любая другая строка (traceback, «ModuleNotFoundError», пустой вывод) — установка повреждена: повтори шаг 4
или скачай архив заново.

## Шаг 6. Подключить Google Drive (ключ) 👤 → 🤖

👤 **Попроси человека** перенести файл ключа на этот Mac **не через GitHub**: AirDrop, флешка, менеджер
паролей. На первом Mac он лежит в `~/Library/Application Support/QuizUpdater/service-account.json`
(если ключ потерян — его нельзя скачать заново, нужно создать новый в Google Cloud Console → Keys; см.
README, раздел 8). Узнай у человека, **где лежит файл**, и подставь путь.

🤖 Подключи через бэкенд — он сам проверит ключ запросом к Drive и только после успеха скопирует его
в `~/Library/Application Support/QuizUpdater/` с правами `0600`:

```bash
B=/Applications/QuizUpdater.app/Contents/Resources/backend
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$B:$B/vendor"
/usr/bin/python3 -m quiz_backend connect-drive --key "<путь к service-account.json>"
```

Ожидаемый результат: `{"ok": true, "clientEmail": "quiz-updater@…", "sheetCount": N}`, где N ≥ 1.

| Ответ | Что значит и что делать |
|---|---|
| `DRIVE_KEY_INVALID` | это не ключ сервисного аккаунта (например, OAuth-файл) или файл повреждён — нужен другой файл |
| `DRIVE_AUTH_FAILED` | Google не принял ключ (удалён/отозван) или неверны дата и время на Mac — проверь время, иначе нужен новый ключ |
| `NETWORK_ERROR` | нет интернета — проверь связь и повтори |
| `sheetCount: 0` | ключ рабочий, но роботу ничего не расшарено: человеку нужно дать адрес из `clientEmail` доступ «Читатель» к папке `КВИЗ` в Google Drive |

Проверь список таблиц (ничего не меняет):

```bash
/usr/bin/python3 -m quiz_backend list-sheets
```

Ожидаемый результат: `"ok": true` и в `sheets` есть таблицы результатов (имена и даты изменения).

👤 После успеха предложи человеку удалить скопированный файл ключа из `Загрузок`/AirDrop (копия в
`Application Support` уже сохранена) — но только если у него есть ещё одна копия (менеджер паролей).
Удалять без его согласия не нужно.

## Шаг 7. Запустить и выбрать таблицу 👤

```bash
open /Applications/QuizUpdater.app
```

👤 Человек делает в окне приложения:

1. На вопрос macOS «QuizUpdater хочет управлять Keynote» — нажать **«Разрешить»** (без этого не работает
   ничего, что связано с презентацией; если ответил «Не разрешать» — «Системные настройки →
   Конфиденциальность и безопасность → Автоматизация → QuizUpdater → Keynote»).
2. Открыть нужную презентацию в Keynote и выбрать её в списке «Документ Keynote» вверху.
3. Рядом с «Таблица результатов» нажать **«Выбрать…»** и выбрать таблицу игры (после этого выбор запоминается).
4. Облако рядом с «Выбрать…» должно показывать «Подключено, таблиц доступно: N».

## Шаг 8. Итоговая проверка 🤖/👤

Чек-лист для отчёта человеку (отметь, что проверено, а что нет):

- [ ] macOS ≥ 13, Command Line Tools стоят, `/usr/bin/python3` отвечает (шаги 1–2)
- [ ] приложение в `/Applications`, подпись валидна, архитектура совпадает с Mac (шаг 4)
- [ ] `drive-status` отвечает `ok: true` (шаг 5)
- [ ] `connect-drive` вернул `sheetCount ≥ 1`, `list-sheets` показал таблицы (шаг 6)
- [ ] приложение запускается без предупреждения Gatekeeper (шаг 7) — 👤
- [ ] Keynote разрешён в «Автоматизации» (шаг 7) — 👤
- [ ] в приложении выбрана таблица, в режиме «Таблица рейтинга» слева виден список команд — 👤
- [ ] нажали **«Проверить»** (он ничего не меняет) и получили «Проверка ок: …» — 👤

Кнопки «Обновить таблицу в презентации» и «Заменить имена» **меняют** презентацию — их жми только когда
человек сам хочет обновить рейтинг. Для проверки установки достаточно «Проверить».

Если приложение собрано под Intel, а проверка идёт на другом Mac, честно напиши в отчёте, что запуск
самого окна не проверялся.

## Обновление до новой версии

Закрыть приложение → шаги 3 и 4 заново (скачать новый архив и заменить `/Applications/QuizUpdater.app`) →
шаг 5 для проверки. Ключ и выбранная таблица сохраняются: они лежат в
`~/Library/Application Support/QuizUpdater/` и в настройках приложения, а не внутри `.app`. После замены
приложения macOS может снова спросить разрешение управлять Keynote (подпись «ad-hoc» меняется при каждой сборке).

## Если что-то не так

| Симптом | Причина и решение |
|---|---|
| «Приложение повреждено», «не удаётся проверить разработчика» | не снят карантин: `xattr -dr com.apple.quarantine /Applications/QuizUpdater.app` |
| «Не найден Python 3. Установите Command Line Tools» | нет CLT — шаг 2 |
| Окно «Установить команды разработчика» при запуске Python | CLT не стоят; это окно из шага 2 — дождаться установки |
| «Google Drive не подключён» | нет ключа — шаг 6 |
| `AUTOMATION_DENIED` («Нет разрешения на управление Keynote») | «Системные настройки → Конфиденциальность и безопасность → Автоматизация» → включить Keynote для QuizUpdater |
| `FILE_NOT_SHARED` | таблица не расшарена роботу: дать адрес робота доступ «Читатель» (адрес показан в сообщении с кнопкой «Скопировать») |
| В списке таблиц пусто | роботу не расшарена папка `КВИЗ` или в ней нет таблиц |
| «Слайда N нет в документе» | презентацию изменили после выбора слайда — кликнуть по слайду заново |

Полный список кодов ошибок — в README, раздел 5.2.

## Для мейнтейнера: как выпустить релиз

Имена файлов в релизе **постоянные** (без версии), чтобы ссылка `releases/latest/download/…` работала всегда;
версия — в теге и названии релиза.

```bash
make app                                                        # на машине, где собирается релиз
ditto -c -k --keepParent dist/QuizUpdater.app QuizUpdater-universal.zip
shasum -a 256 QuizUpdater-universal.zip > QuizUpdater-universal.zip.sha256
gh release create vX.Y.Z QuizUpdater-universal.zip QuizUpdater-universal.zip.sha256 \
  --title "QuizUpdater X.Y.Z" --notes "см. docs/INSTALL.md" --target main
```

Версию предварительно поднимают в `app/Info.plist` (`CFBundleShortVersionString`). Архив делают именно `ditto`
(а не `zip`): он сохраняет подпись и атрибуты. Перед публикацией проверь, что в `.app` нет секретов
(ключей, адреса робота): `grep -r -a "BEGIN PRIVATE KEY" dist/QuizUpdater.app` может находить только
строки-маркеры в `quiz_backend/drive.py`, но не настоящий ключ.
