import Foundation

enum AppMode: String, CaseIterable {
    case rating = "Таблица рейтинга"
    case names = "Имена призёров"
    case schedule = "Расписание игр"
}

enum PreviewState {
    case idle
    case exporting(done: Int, total: Int)
    case ready([SlidePreview])
    case failed(String)
}

struct PlaceSlidePair: Identifiable, Hashable {
    var id: Int { place }
    let place: Int
    let teamName: String
    var slide: Int
}

struct StatusMessage: Identifiable {
    let id = UUID()
    let text: String
    let isError: Bool
    var isAutomationDenied = false
    /// Адрес робота — рядом с сообщением показывается кнопка «Скопировать».
    var clientEmail: String?
    /// Drive не подключён или ключ непригоден — рядом показывается «Подключить Google Drive…».
    var needsDriveConnection = false
}

/// Состояние подключения к Google Drive на этом Mac.
struct DriveConnection: Equatable {
    var isConnected = false
    /// Адрес робота (сервисного аккаунта), которому ведущий даёт доступ к папке с таблицами.
    var clientEmail: String?
    /// Сколько таблиц видит робот; известно после проверки доступа.
    var sheetCount: Int?
}

@MainActor
final class AppViewModel: ObservableObject {
    @Published var documents: [KeynoteDocument] = []
    @Published var selectedDocument: KeynoteDocument?

    @Published var drive = DriveConnection()
    @Published var selectedSheet: SelectedSheet?
    @Published var teams: [Team] = []

    // Окно выбора таблицы
    @Published var availableSheets: [DriveSheet] = []
    @Published var isLoadingSheets = false
    @Published var sheetListError: StatusMessage?
    @Published var sheetLinkError: StatusMessage?

    @Published var previewState: PreviewState = .idle
    private var progressTask: Task<Void, Never>?

    @Published var mode: AppMode = .rating

    // Режим "Таблица рейтинга"
    @Published var ratingSlide: Int?
    @Published var maxRows: Int

    // Режим "Имена призёров"
    @Published var selectedPlaces: Set<Int> = []
    @Published var startSlide: Int?
    /// Места 1–3 с готовыми слайдами (слайд определяется номером места).
    @Published var pairs: [PlaceSlidePair] = []
    /// Слайд-шаблон «НОМЕР МЕСТО» для остальных мест; по умолчанию — слайд перед слайдом 3-го места.
    @Published var templateSlide: Int?
    private var templateSlideIsManual = false
    @Published var placeholderFoundBySlide: [Int: Bool] = [:]

    // Режим "Расписание игр"
    @Published var scheduleGames: [ScheduleGame] = []
    @Published var selectedGameIDs: Set<String> = []
    @Published var scheduleTargetSlide: Int?
    @Published var scheduleSlots: [SlotFillResult] = []
    @Published var scheduleWarnings: [String] = []

    @Published var statusMessage: StatusMessage?
    @Published var isBusy: Bool = false

    private var settings = SettingsStore()
    private let bridge = PythonBridge.shared

    init() {
        self.selectedSheet = settings.sheet
        self.maxRows = settings.maxRows
        self.ratingSlide = settings.ratingSlide ?? 81
    }

    // MARK: - Документы

    func refreshDocuments() async {
        isBusy = true
        defer { isBusy = false }
        do {
            let payload: ListDocumentsPayload = try await bridge.run(["list-documents"])
            documents = payload.documents
            if !payload.keynoteRunning {
                setStatus("Keynote не запущен", isError: true)
            } else if payload.documents.isEmpty {
                setStatus("Нет открытых документов Keynote", isError: true)
            }
            if let selected = selectedDocument, !documents.contains(selected) {
                selectedDocument = nil
                previewState = .idle
            }
            if selectedDocument == nil {
                selectedDocument = documents.first
            }
        } catch {
            setStatus(error.localizedDescription, isError: true)
        }
    }

    // MARK: - Google Drive

    /// Подключён ли Drive на этом Mac (читает ключ с диска, без сети).
    func refreshDriveStatus() async {
        do {
            let payload: DriveStatusPayload = try await bridge.run(["drive-status"])
            drive.isConnected = payload.connected
            drive.clientEmail = payload.clientEmail
            if !payload.connected {
                setStatus(
                    "Google Drive не подключён. Нажмите «Подключить Google Drive…» и выберите JSON-ключ.",
                    isError: true, needsDriveConnection: true
                )
            }
        } catch {
            reportBackendError(error)
        }
    }

    /// Копирует ключ в ~/Library/Application Support/QuizUpdater и сразу проверяет доступ.
    func connectDrive(keyURL: URL) async {
        isBusy = true
        defer { isBusy = false }
        do {
            let payload: ConnectDrivePayload = try await bridge.run(
                ["connect-drive", "--key", keyURL.path], timeout: 90
            )
            drive = DriveConnection(isConnected: true, clientEmail: payload.clientEmail, sheetCount: payload.sheetCount)
            sheetListError = nil
            sheetLinkError = nil
            availableSheets = []
            setStatus("Подключено, таблиц доступно: \(payload.sheetCount)", isError: false)
        } catch {
            reportBackendError(error)
        }
    }

    func loadSheets() async {
        guard drive.isConnected else { return }
        isLoadingSheets = true
        sheetListError = nil
        defer { isLoadingSheets = false }
        do {
            let payload: ListSheetsPayload = try await bridge.run(["list-sheets"], timeout: 90)
            availableSheets = payload.sheets
            drive.clientEmail = payload.clientEmail
            drive.sheetCount = payload.sheets.count
        } catch {
            sheetListError = statusMessage(for: error)
        }
    }

    func selectSheet(_ sheet: DriveSheet) async {
        selectedSheet = SelectedSheet(id: sheet.id, name: sheet.name)
        settings.sheet = selectedSheet
        sheetLinkError = nil
        await loadTeams()
    }

    /// Выбор по ссылке из браузера. Возвращает true, если таблица найдена и доступна роботу.
    func selectSheet(fromLink link: String) async -> Bool {
        isBusy = true
        defer { isBusy = false }
        sheetLinkError = nil
        do {
            let payload: ResolveLinkPayload = try await bridge.run(["resolve-link", "--link", link], timeout: 90)
            await selectSheet(payload.sheet)
            return true
        } catch {
            sheetLinkError = statusMessage(for: error)
            return false
        }
    }

    // MARK: - Команды из таблицы

    /// Скачивает таблицу заново (без кэша) и обновляет список команд.
    func loadTeams() async {
        guard let sheet = selectedSheet else {
            if drive.isConnected { setStatus("Выберите таблицу результатов", isError: false) }
            return
        }
        guard drive.isConnected else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let payload: ReadSheetPayload = try await bridge.run(["read-sheet", "--file-id", sheet.id], timeout: 90)
            teams = payload.teams
            setStatus("Загружено команд: \(teams.count) (\(payload.sheetName))", isError: false)
        } catch {
            reportBackendError(error)
        }
    }

    // MARK: - Превью слайдов

    func loadPreviews(force: Bool = false) async {
        guard let doc = selectedDocument else { return }

        if !force, let cached = PreviewCache.shared.cachedPreviews(docName: doc.name, expectedSlideCount: doc.slideCount) {
            previewState = .ready(cached)
            return
        }

        let exportDir = PreviewCache.shared.newExportDirectory(for: doc.name)
        previewState = .exporting(done: 0, total: doc.slideCount)

        progressTask?.cancel()
        progressTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 500_000_000)
                guard !Task.isCancelled else { return }
                let count = PreviewCache.shared.countExportedFiles(in: exportDir)
                await MainActor.run {
                    self?.previewState = .exporting(done: count, total: doc.slideCount)
                }
            }
        }

        do {
            let payload: ExportPreviewsPayload = try await bridge.run(
                ["export-previews", "--doc", doc.name, "--out", exportDir.path],
                timeout: 300
            )
            progressTask?.cancel()
            try PreviewCache.shared.commit(exportDirectory: exportDir, docName: doc.name, slideCount: payload.count)
            if let cached = PreviewCache.shared.cachedPreviews(docName: doc.name, expectedSlideCount: doc.slideCount) {
                previewState = .ready(cached)
            } else {
                previewState = .ready(payload.slides)
            }
        } catch {
            progressTask?.cancel()
            previewState = .failed(error.localizedDescription)
        }
    }

    // MARK: - Режим "Таблица рейтинга"

    func selectRatingSlide(_ slide: Int) {
        ratingSlide = slide
        settings.ratingSlide = slide
    }

    func runRating(dryRun: Bool) async {
        guard let doc = selectedDocument, let slide = ratingSlide else { return }
        guard let sheet = requireSheet() else { return }
        isBusy = true
        defer { isBusy = false }
        settings.maxRows = maxRows

        var args = [
            "update-rating", "--doc", doc.name, "--slide", String(slide),
            "--file-id", sheet.id, "--max-rows", String(maxRows),
        ]
        if dryRun { args.append("--dry-run") }

        do {
            let payload: UpdateRatingPayload = try await bridge.run(args, timeout: 90)
            if dryRun {
                let rounds = payload.rounds.map { ", раундов: \($0)" } ?? ""
                var text = "Проверка ок: слайд \(payload.slide)\(rounds), команд: \(payload.teams?.count ?? 0)"
                if let rows = ratingRowsText(payload) { text += "; \(rows)" }
                setStatus(withWarnings(text, payload.warnings), isError: false)
            } else {
                setStatus(withWarnings(payload.message ?? "Обновлено", payload.warnings), isError: false)
            }
        } catch {
            reportBackendError(error)
        }
    }

    /// «строк в таблице Keynote: 10 → 8 (будет удалено 2)»; nil, если бэкенд не прислал число строк.
    private func ratingRowsText(_ payload: UpdateRatingPayload) -> String? {
        guard let current = payload.keynoteRows, let target = payload.targetRows else { return nil }
        if current == target { return "строк в таблице: \(current)" }
        let change = (payload.rowsAdded ?? 0) > 0
            ? "будет добавлено \(payload.rowsAdded ?? 0)"
            : "будет удалено \(payload.rowsRemoved ?? 0)"
        return "строк в таблице Keynote: \(current) → \(target) (\(change))"
    }

    private func withWarnings(_ text: String, _ warnings: [String]?) -> String {
        guard let warnings, !warnings.isEmpty else { return text }
        return ([text] + warnings.map { "⚠️ \($0)" }).joined(separator: "\n")
    }

    // MARK: - Режим "Имена призёров"

    func togglePlace(_ place: Int) {
        if selectedPlaces.contains(place) {
            selectedPlaces.remove(place)
        } else {
            selectedPlaces.insert(place)
        }
        recomputePairs()
    }

    func selectStartSlide(_ slide: Int) {
        startSlide = slide
        recomputePairs()
    }

    /// Места, у которых есть готовые слайды (1, 2, 3).
    private static let fixedPlaces = 1...3

    /// Дополнительные места (4+), по которым слайды создаются из шаблона; от большего к меньшему — так их показывают.
    var extraTeams: [Team] {
        teams
            .filter { selectedPlaces.contains($0.place) && !Self.fixedPlaces.contains($0.place) }
            .sorted { $0.place > $1.place }
    }

    var canRunNames: Bool {
        guard startSlide != nil else { return false }
        if pairs.isEmpty && extraTeams.isEmpty { return false }
        return extraTeams.isEmpty || templateSlide != nil
    }

    func recomputePairs() {
        guard let start = startSlide else {
            pairs = []
            templateSlide = nil
            return
        }
        // Слайды мест 1–3 идут подряд: 1-е = стартовый, 2-е = перед ним, 3-е = ещё раньше (обратный отсчёт).
        let selected = teams
            .filter { selectedPlaces.contains($0.place) && Self.fixedPlaces.contains($0.place) }
            .sorted { $0.place < $1.place }
        pairs = selected.map { PlaceSlidePair(place: $0.place, teamName: $0.name, slide: start - ($0.place - 1)) }
        if !templateSlideIsManual {
            templateSlide = start - Self.fixedPlaces.count
        }
    }

    func updatePairSlide(place: Int, slide: Int) {
        guard let index = pairs.firstIndex(where: { $0.place == place }) else { return }
        pairs[index].slide = slide
    }

    func updateTemplateSlide(_ slide: Int) {
        templateSlide = slide
        templateSlideIsManual = true
    }

    private func pairsArgument() -> String {
        pairs.map { "\($0.place):\($0.slide)" }.joined(separator: ",")
    }

    func runNames(dryRun: Bool) async {
        guard let doc = selectedDocument, canRunNames else { return }
        guard let sheet = requireSheet() else { return }
        isBusy = true
        defer { isBusy = false }

        var args = ["replace-names", "--doc", doc.name, "--file-id", sheet.id]
        if !pairs.isEmpty { args += ["--pairs", pairsArgument()] }
        let extras = extraTeams
        if !extras.isEmpty { args += ["--extra-places", extras.map { String($0.place) }.joined(separator: ",")] }
        // Шаблон передаём всегда, когда он известен: если дополнительных мест нет, бэкенд скроет его из показа.
        if let templateSlide { args += ["--template-slide", String(templateSlide)] }
        if dryRun { args.append("--dry-run") }

        do {
            let payload: ReplaceNamesPayload = try await bridge.run(args, timeout: 120)
            var found = Dictionary(
                uniqueKeysWithValues: payload.assignments.map { ($0.slide, $0.placeholderFound ?? true) }
            )
            if dryRun, let template = payload.template, template.action != "none" {
                found[template.slide] = template.found
            }
            placeholderFoundBySlide = found
            if dryRun {
                let result = namesDryRunText(payload)
                setStatus(result.text, isError: result.isError)
            } else {
                setStatus(payload.message ?? "Обновлено", isError: false)
                if (payload.created ?? 0) > 0 {
                    await refreshAfterSlidesCreated(docName: doc.name)
                }
            }
        } catch {
            reportBackendError(error)
        }
    }

    /// «Проверить»: что будет сделано со слайдами мест, дополнительными местами и шаблоном.
    private func namesDryRunText(_ payload: ReplaceNamesPayload) -> (text: String, isError: Bool) {
        let missing = payload.assignments.filter { $0.placeholderFound == false }
        if !missing.isEmpty {
            let slides = missing.map { String($0.slide) }.joined(separator: ", ")
            return ("Плейсхолдер «ЗАМЕНИТЬ» не найден на слайдах: \(slides)", true)
        }
        var parts: [String] = []
        if !payload.assignments.isEmpty {
            parts.append("«ЗАМЕНИТЬ» найден на всех \(payload.assignments.count) слайдах мест с готовыми слайдами")
        }
        if let extras = payload.extras, !extras.isEmpty {
            let words = extras.map(\.ordinal).joined(separator: ", ")
            let created = payload.slidesToCreate ?? 0
            let template = payload.template.map { ", шаблон (слайд \($0.slide)) станет «\(extras.last?.ordinal ?? "")»" } ?? ""
            parts.append("дополнительные места: \(words); новых слайдов: \(created)\(template)")
        }
        if let template = payload.template, template.action == "hide" {
            parts.append("дополнительных мест нет — шаблон (слайд \(template.slide)) будет скрыт из показа")
        }
        let warnings = payload.warnings.map { "⚠️ \($0)" }
        return (((["Проверка ок: " + parts.joined(separator: ". ")]) + warnings).joined(separator: "\n"), false)
    }

    /// После создания слайдов номера в документе сдвинулись: обновляем документ (и превью заново) и сбрасываем выбор слайдов.
    private func refreshAfterSlidesCreated(docName: String) async {
        startSlide = nil
        templateSlide = nil
        templateSlideIsManual = false
        pairs = []
        placeholderFoundBySlide = [:]
        do {
            let payload: ListDocumentsPayload = try await bridge.run(["list-documents"])
            documents = payload.documents
            // Смена selectedDocument (число слайдов другое) запускает перезагрузку превью в TopBarView.
            selectedDocument = documents.first { $0.name == docName } ?? selectedDocument
        } catch {
            // Статус уже показан; превью обновятся по кнопке «Обновить превью».
        }
    }

    // MARK: - Режим "Расписание игр"

    func fetchSchedule() async {
        isBusy = true
        defer { isBusy = false }
        do {
            let payload: FetchSchedulePayload = try await bridge.run(["fetch-schedule"], timeout: 20)
            scheduleGames = payload.games
            selectedGameIDs = Set(payload.games.map(\.id))
            setStatus("Загружено игр: \(scheduleGames.count)", isError: false)
        } catch {
            reportBackendError(error)
        }
    }

    func toggleGame(_ id: String) {
        if selectedGameIDs.contains(id) {
            selectedGameIDs.remove(id)
        } else {
            selectedGameIDs.insert(id)
        }
    }

    func selectScheduleSlide(_ slide: Int) {
        scheduleTargetSlide = slide
    }

    func runFillSlots(dryRun: Bool) async {
        guard let doc = selectedDocument, let slide = scheduleTargetSlide else { return }
        isBusy = true
        defer { isBusy = false }

        let selectedGames = scheduleGames
            .filter { selectedGameIDs.contains($0.id) }
            .map { ScheduleSlotGame(cardText: $0.cardText, dateText: $0.dateText, cardFontSize: $0.cardFontSize) }

        guard let gamesJSON = try? JSONEncoder().encode(selectedGames),
              let gamesArg = String(data: gamesJSON, encoding: .utf8) else {
            setStatus("Не удалось подготовить данные игр", isError: true)
            return
        }

        var args = ["fill-schedule-slots", "--doc", doc.name, "--slide", String(slide), "--games", gamesArg]
        if dryRun { args.append("--dry-run") }

        do {
            let payload: FillSlotsPayload = try await bridge.run(args)
            scheduleWarnings = payload.warnings
            if dryRun {
                scheduleSlots = payload.slots ?? []
                let filled = scheduleSlots.filter(\.filled).count
                setStatus("Проверка ок: будет заполнено \(filled) из \(scheduleSlots.count) слотов", isError: false)
            } else {
                setStatus(payload.message ?? "Готово", isError: false)
            }
        } catch {
            reportBackendError(error)
        }
    }

    // MARK: - Статус

    /// Таблица для действий с рейтингом/именами; если не выбрана — подсказка в статус-баре.
    private func requireSheet() -> SelectedSheet? {
        if let sheet = selectedSheet { return sheet }
        setStatus("Выберите таблицу результатов (кнопка «Выбрать…» вверху)", isError: true)
        return nil
    }

    private func statusMessage(for error: Error) -> StatusMessage {
        if let backendError = error as? BackendError {
            return StatusMessage(
                text: backendError.message,
                isError: true,
                isAutomationDenied: backendError.isAutomationDenied,
                clientEmail: backendError.clientEmail,
                needsDriveConnection: backendError.needsDriveConnection
            )
        }
        return StatusMessage(text: error.localizedDescription, isError: true)
    }

    private func reportBackendError(_ error: Error) {
        statusMessage = self.statusMessage(for: error)
    }

    private func setStatus(
        _ text: String, isError: Bool, isAutomationDenied: Bool = false, needsDriveConnection: Bool = false
    ) {
        statusMessage = StatusMessage(
            text: text, isError: isError, isAutomationDenied: isAutomationDenied,
            needsDriveConnection: needsDriveConnection
        )
    }
}
