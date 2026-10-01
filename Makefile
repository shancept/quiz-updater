PYTHON      ?= python3
SYS_PYTHON  ?= /usr/bin/python3
APP         := dist/QuizUpdater.app
EXCEL       ?= ~/Library/CloudStorage/GoogleDrive-shancept@gmail.com/My Drive/КВИЗ/Копия Копия Калькулятор баллов Классика.xlsx

.PHONY: vendor test-backend build app run clean

vendor:
	rm -rf backend/vendor
	$(PYTHON) -m pip install --target backend/vendor -r backend/requirements.txt --no-compile

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
