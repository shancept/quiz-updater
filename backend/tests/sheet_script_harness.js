// Запускает чистые функции скрипта таблицы (sheets/SortResults.gs) в JavaScriptCore через osascript -l JavaScript:
// на stdin {"fn": "имя", "args": [...]}, в stdout — JSON результата. Так тесты не зависят от Node.
ObjC.import('Foundation');

function readFile(path) {
  return $.NSString.stringWithContentsOfFileEncodingError($(path), $.NSUTF8StringEncoding, null).js;
}

function run(argv) {
  var scriptPath = argv[0];
  (0, eval)(readFile(scriptPath)); // функции скрипта попадают в глобальную область
  var data = $.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile;
  var request = JSON.parse($.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding).js);
  var fn = this[request.fn] || (0, eval)(request.fn);
  if (typeof fn !== 'function') throw new Error('нет функции ' + request.fn);
  return JSON.stringify({ result: fn.apply(null, request.args) });
}
