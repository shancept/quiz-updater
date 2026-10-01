SYS_PYTHON  ?= /usr/bin/python3
APP         := dist/QuizUpdater.app
ARCHS       := arm64 x86_64
MIN_MACOS   := 13.0
UNIVERSAL   := app/.build/QuizUpdater-universal

.PHONY: vendor test-backend build app run clean

# Зависимости ставятся ТЕМ ЖЕ интерпретатором, на котором бэкенд работает в бандле
# (системный 3.9), чтобы pip выбрал версии, совместимые с ним. Только pure-Python
# wheels: один набор файлов подходит и arm64, и x86_64.
vendor:
	rm -rf backend/vendor
	$(SYS_PYTHON) -m pip install --target backend/vendor -r backend/requirements.txt \
		--only-binary=:all: --no-compile --disable-pip-version-check
	rm -rf backend/vendor/bin
	@if find backend/vendor \( -name '*.so' -o -name '*.dylib' \) | grep -q .; then \
		echo "ОШИБКА: в backend/vendor есть нативные библиотеки — бандл не будет universal"; exit 1; \
	fi

# Тесты бэкенда системным Python 3.9 — тем же, на котором он работает в бандле (код не должен
# использовать синтаксис новее). Сеть и ключ Google не нужны: настоящий urllib ходит на локальный
# фейк Drive, подпись JWT проверяет openssl. Затем два безопасных прогона подкоманд:
# drive-status (без сети) и list-documents (только читает Keynote).
test-backend:
	$(SYS_PYTHON) --version
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:backend/vendor $(SYS_PYTHON) -m unittest discover -s backend/tests -t backend
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:backend/vendor $(SYS_PYTHON) -m quiz_backend drive-status
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:backend/vendor $(SYS_PYTHON) -m quiz_backend list-documents

# Universal-бинарь собирается по одной архитектуре (--triple) и склеивается lipo, а не одним
# `swift build --arch arm64 --arch x86_64`: тот режим требует xcbuild из полного Xcode,
# а так хватает одних Command Line Tools. Результат тот же: arm64 + x86_64.
build:
	$(foreach arch,$(ARCHS),swift build --package-path app -c release --triple $(arch)-apple-macosx$(MIN_MACOS) --product QuizUpdater &&) true
	lipo -create $(foreach arch,$(ARCHS),app/.build/$(arch)-apple-macosx/release/QuizUpdater) -output $(UNIVERSAL)

app: build vendor
	rm -rf $(APP)
	mkdir -p "$(APP)/Contents/MacOS" "$(APP)/Contents/Resources/backend"
	cp app/Info.plist "$(APP)/Contents/Info.plist"
	cp $(UNIVERSAL) "$(APP)/Contents/MacOS/QuizUpdater"
	rsync -a --exclude '__pycache__' backend/quiz_backend backend/vendor "$(APP)/Contents/Resources/backend/"
	codesign --force --deep --sign - "$(APP)"
	@echo "Собрано: $(APP)"
	@lipo -archs "$(APP)/Contents/MacOS/QuizUpdater"

run: app
	open "$(APP)"

clean:
	rm -rf app/.build dist
