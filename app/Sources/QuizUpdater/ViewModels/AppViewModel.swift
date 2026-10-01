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
    let isAutomationDenied: Bool
}

@MainActor
final class AppViewModel: ObservableObject {
    @Published var documents: [KeynoteDocument] = []
    @Published var selectedDocument: KeynoteDocument?

    @Published var excelPath: String
    @Published var teams: [Team] = []

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
        self.excelPath = settings.excelPath
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

    // MARK: - Excel

    func loadExcel() async {
        isBusy = true
        defer { isBusy = false }
        settings.excelPath = excelPath
        do {
            let payload: ReadExcelPayload = try await bridge.run(["read-excel", "--path", excelPath])
            teams = payload.teams
            setStatus("Загружено команд: \(teams.count)", isError: false)
        } catch {
            setStatus(error.localizedDescription, isError: true)
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
        isBusy = true
        defer { isBusy = false }
        settings.maxRows = maxRows

        var args = [
            "update-rating", "--doc", doc.name, "--slide", String(slide),
            "--excel", excelPath, "--max-rows", String(maxRows),
        ]
        if dryRun { args.append("--dry-run") }

        do {
            let payload: UpdateRatingPayload = try await bridge.run(args)
            if dryRun {
                setStatus("Проверка ок: слайд \(payload.slide), команд к обновлению: \(payload.teams?.count ?? 0)", isError: false)
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
        isBusy = true
        defer { isBusy = false }

        var args = [
            "replace-names", "--doc", doc.name, "--excel", excelPath, "--pairs", pairsArgument(),
        ]
        if dryRun { args.append("--dry-run") }

        do {
            let payload: ReplaceNamesPayload = try await bridge.run(args)
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

    private func reportBackendError(_ error: Error) {
        if let backendError = error as? BackendError {
            setStatus(backendError.message, isError: true, isAutomationDenied: backendError.isAutomationDenied)
        } else {
            setStatus(error.localizedDescription, isError: true)
        }
    }

    private func setStatus(_ text: String, isError: Bool, isAutomationDenied: Bool = false) {
        statusMessage = StatusMessage(text: text, isError: isError, isAutomationDenied: isAutomationDenied)
    }
}
