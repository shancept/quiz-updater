/**
 * Сортировка таблицы результатов квиза кнопкой или из меню «Квиз» (лист «Лист1»).
 *
 * Порядок строк:
 *   1. «Итого» (колонка C) — по убыванию: главный ключ;
 *   2. при равном итоге — раунды по убыванию, начиная с последнего сыгранного и назад до первого;
 *   3. если и они равны — название команды по алфавиту (А→Я, без учёта регистра).
 *
 * Раунд считается сыгранным, пока подряд идут колонки, в которых хотя бы у одной команды есть значение.
 * Первая пустая колонка отсекает себя и все следующие за ней раунды (даже если в них что-то записано):
 * название команды и итог сортируются всегда, раунды — только сыгранные подряд.
 *
 * Колонка A («Место») не трогается: это счётчик строк (=A1+1), он должен остаться 1, 2, 3…
 * Данные идут со 2-й строки до первой пустой, раунды — с колонки D, пока заполнены заголовки.
 *
 * @OnlyCurrentDoc
 */

var SHEET_NAME = 'Лист1';
var HEADER_ROW = 1;
var NAME_COLUMN = 2; // B — название команды; сразу за ней C — итого, затем раунды с колонки D
var FIRST_ROUND_COLUMN = 4;

// --- чистая логика (проверяется тестами на JavaScript) ---------------------------------------------

function isFilled(value) {
  return value !== '' && value !== null && value !== undefined;
}

/** Сколько ячеек подряд сверху заполнено; 0 — значение, а не пустота. */
function leadingFilled(values) {
  var count = 0;
  while (count < values.length && isFilled(values[count])) count++;
  return count;
}

/**
 * План сортировки для строк вида [название, итого, раунд 1, раунд 2, …].
 * Возвращает {rounds: сколько раундов учитывается, keys: [{offset, ascending}, …]}, главный ключ — первый;
 * offset — номер колонки в строке (0 — название, 1 — итого, 2 — раунд 1 и т. д.).
 */
function planSort(rows) {
  var roundColumns = rows.length ? rows[0].length - 2 : 0;
  var played = 0;
  while (played < roundColumns && rows.some(function (row) { return isFilled(row[2 + played]); })) {
    played++;
  }
  var keys = [{ offset: 1, ascending: false }];
  for (var round = played - 1; round >= 0; round--) {
    keys.push({ offset: 2 + round, ascending: false });
  }
  keys.push({ offset: 0, ascending: true });
  return { rounds: played, keys: keys };
}

// --- работа с таблицей ----------------------------------------------------------------------------

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Квиз')
    .addItem('Отсортировать результаты', 'sortResults')
    .addToUi();
}

/** Точка входа: её вызывает пункт меню и кнопка (рисунок с назначенным скриптом sortResults). */
function sortResults() {
  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = spreadsheet.getSheetByName(SHEET_NAME);
  if (!sheet) {
    SpreadsheetApp.getUi().alert('Не найден лист «' + SHEET_NAME + '». Сортировка работает только с ним.');
    return;
  }
  var lastRow = sheet.getLastRow();
  if (lastRow <= HEADER_ROW) {
    spreadsheet.toast('На листе нет данных для сортировки', 'Квиз', 5);
    return;
  }

  var names = sheet.getRange(HEADER_ROW + 1, NAME_COLUMN, lastRow - HEADER_ROW, 1).getValues()
    .map(function (row) { return row[0]; });
  var teamCount = leadingFilled(names);
  if (teamCount < 2) {
    spreadsheet.toast('Команд меньше двух — сортировать нечего', 'Квиз', 5);
    return;
  }

  var headerWidth = Math.max(1, sheet.getLastColumn() - FIRST_ROUND_COLUMN + 1);
  var headers = sheet.getRange(HEADER_ROW, FIRST_ROUND_COLUMN, 1, headerWidth).getValues()[0];
  var roundColumns = leadingFilled(headers);

  // Диапазон: название, итого и колонки раундов; колонка A (место) в него не входит.
  var range = sheet.getRange(HEADER_ROW + 1, NAME_COLUMN, teamCount, 2 + roundColumns);
  var plan = planSort(range.getValues());
  range.sort(plan.keys.map(function (key) {
    return { column: NAME_COLUMN + key.offset, ascending: key.ascending };
  }));
  SpreadsheetApp.flush();

  spreadsheet.toast(
    'Команд: ' + teamCount + ', учтено раундов: ' + plan.rounds + ' (итого и название — всегда).',
    'Таблица отсортирована', 8);
}
