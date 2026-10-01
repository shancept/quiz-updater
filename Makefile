SYS_PYTHON  ?= /usr/bin/python3
APP         := dist/QuizUpdater.app

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

test-backend:
	PYTHONPATH=backend:backend/vendor $(SYS_PYTHON) -m quiz_backend list-documents
	PYTHONPATH=backend:backend/vendor $(SYS_PYTHON) -m quiz_backend read-excel

build:
	swift build --package-path app -c release --arch arm64 --arch x86_64 --product QuizUpdater

app: build vendor
	rm -rf $(APP)
	mkdir -p "$(APP)/Contents/MacOS" "$(APP)/Contents/Resources/backend"
	cp app/Info.plist "$(APP)/Contents/Info.plist"
	cp "$$(swift build --package-path app -c release --arch arm64 --arch x86_64 --product QuizUpdater --show-bin-path)/QuizUpdater" "$(APP)/Contents/MacOS/QuizUpdater"
	rsync -a --exclude '__pycache__' backend/quiz_backend backend/vendor "$(APP)/Contents/Resources/backend/"
	codesign --force --deep --sign - "$(APP)"
	@echo "Собрано: $(APP)"
	@lipo -archs "$(APP)/Contents/MacOS/QuizUpdater"

run: app
	open "$(APP)"

clean:
	rm -rf app/.build dist
