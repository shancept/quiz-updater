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
    @Published var pairs: [PlaceSlidePair] = []
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
                setStatus(
                    "Проверка ок: слайд \(payload.slide)\(rounds), команд к обновлению: \(payload.teams?.count ?? 0)",
                    isError: false
                )
            } else {
                setStatus(payload.message ?? "Обновлено", isError: false)
            }
        } catch {
            reportBackendError(error)
        }
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

    func recomputePairs() {
        guard let start = startSlide else {
            pairs = []
            return
        }
        let selected = teams.filter { selectedPlaces.contains($0.place) }.sorted { $0.place < $1.place }
        pairs = selected.enumerated().map { index, team in
            PlaceSlidePair(place: team.place, teamName: team.name, slide: start - index)
        }
    }

    func updatePairSlide(place: Int, slide: Int) {
        guard let index = pairs.firstIndex(where: { $0.place == place }) else { return }
        pairs[index].slide = slide
    }

    private func pairsArgument() -> String {
        pairs.map { "\($0.place):\($0.slide)" }.joined(separator: ",")
    }

    func runNames(dryRun: Bool) async {
        guard let doc = selectedDocument, !pairs.isEmpty else { return }
        guard let sheet = requireSheet() else { return }
        isBusy = true
        defer { isBusy = false }

        var args = [
            "replace-names", "--doc", doc.name, "--file-id", sheet.id, "--pairs", pairsArgument(),
        ]
        if dryRun { args.append("--dry-run") }

        do {
            let payload: ReplaceNamesPayload = try await bridge.run(args, timeout: 90)
            placeholderFoundBySlide = Dictionary(
                uniqueKeysWithValues: payload.assignments.map { ($0.slide, $0.placeholderFound ?? true) }
            )
            if dryRun {
                let missing = payload.assignments.filter { $0.placeholderFound == false }
                if missing.isEmpty {
                    setStatus("Проверка ок: плейсхолдер найден на всех \(payload.assignments.count) слайдах", isError: false)
                } else {
                    let slides = missing.map { String($0.slide) }.joined(separator: ", ")
                    setStatus("Плейсхолдер «ЗАМЕНИТЬ» не найден на слайдах: \(slides)", isError: true)
                }
            } else {
                setStatus(payload.message ?? "Обновлено", isError: false)
            }
        } catch {
            reportBackendError(error)
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
