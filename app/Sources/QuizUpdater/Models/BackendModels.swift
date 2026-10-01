import Foundation

struct KeynoteDocument: Decodable, Identifiable, Hashable {
    var id: String { name }
    let name: String
    let slideCount: Int
}

struct ListDocumentsPayload: Decodable {
    let keynoteRunning: Bool
    let documents: [KeynoteDocument]
}

struct Team: Decodable, Identifiable, Hashable {
    var id: Int { place }
    let place: Int
    let name: String
    let total: Double?
    let rounds: [Double?]
}

/// Таблица результатов на Google Drive (Google Sheets или загруженный .xlsx).
struct DriveSheet: Decodable, Identifiable, Hashable {
    let id: String
    let name: String
    let mimeType: String
    let modifiedTime: String?

    var isGoogleSheet: Bool { mimeType == "application/vnd.google-apps.spreadsheet" }

    /// modifiedTime приходит как ISO 8601 с долями секунды ("2026-09-30T18:00:00.000Z").
    var modifiedDate: Date? {
        guard let modifiedTime else { return nil }
        let withFraction = ISO8601DateFormatter()
        withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = withFraction.date(from: modifiedTime) { return date }
        return ISO8601DateFormatter().date(from: modifiedTime)
    }
}

struct DriveStatusPayload: Decodable {
    let connected: Bool
    let clientEmail: String?
}

struct ConnectDrivePayload: Decodable {
    let clientEmail: String
    let sheetCount: Int
}

struct ListSheetsPayload: Decodable {
    let clientEmail: String
    let sheets: [DriveSheet]
}

struct ResolveLinkPayload: Decodable {
    let sheet: DriveSheet
}

struct ReadSheetPayload: Decodable {
    let sheetName: String
    let teams: [Team]
}

struct SlidePreview: Decodable, Identifiable, Hashable {
    var id: Int { slide }
    let slide: Int
    let path: String
}

struct ExportPreviewsPayload: Decodable {
    let doc: String
    let slides: [SlidePreview]
    let count: Int
}

struct UpdateRatingPayload: Decodable {
    let dryRun: Bool
    let doc: String
    let slide: Int
    /// Сколько раундов записывается: решает таблица Keynote на слайде (колонки минус место/команда/итого).
    let rounds: Int?
    let teams: [Team]?
    let updated: Int?
    let message: String?
    /// Строк в таблице Keynote сейчас и сколько станет: таблица подгоняется под число команд.
    let keynoteRows: Int?
    let targetRows: Int?
    let rowsAdded: Int?
    let rowsRemoved: Int?
    /// Например, «новые строки станут ниже шрифта — текст может не поместиться».
    let warnings: [String]?
}

struct NameAssignment: Decodable, Identifiable, Hashable {
    var id: Int { place }
    let place: Int
    let slide: Int
    let team: String
    let placeholderFound: Bool?
}

struct ReplaceNamesPayload: Decodable {
    let dryRun: Bool
    let doc: String
    let assignments: [NameAssignment]
    let updated: Int?
    let message: String?
    let warnings: [String]
}

struct ScheduleGame: Decodable, Identifiable, Hashable {
    let id: String
    let gameNumber: String
    let rawTitle: String
    let date: String
    let cardText: String
    let dateText: String
    let cardFontSize: Double
}

struct FetchSchedulePayload: Decodable {
    let games: [ScheduleGame]
}

/// Данные для одного слота из --games (то, что реально уходит в бэкенд для fill-schedule-slots).
struct ScheduleSlotGame: Encodable {
    let cardText: String
    let dateText: String
    let cardFontSize: Double
}

struct SlotFillResult: Decodable, Identifiable, Hashable {
    var id: Int { slotIndex }
    let slotIndex: Int
    let filled: Bool
    let cardText: String?
    let dateText: String?
}

struct FillSlotsPayload: Decodable {
    let dryRun: Bool
    let doc: String
    let slide: Int
    let slots: [SlotFillResult]?
    let filledCount: Int?
    let clearedCount: Int?
    let message: String?
    let warnings: [String]
}

/// Ошибка бэкенда: код и человекочитаемое (по-русски) сообщение из quiz_backend.
struct BackendError: Error, LocalizedError, Identifiable {
    let id = UUID()
    let code: String
    let message: String
    /// Адрес робота (сервисного аккаунта) — бэкенд присылает его с FILE_NOT_SHARED, чтобы показать «Скопировать».
    let clientEmail: String?

    init(code: String, message: String, clientEmail: String? = nil) {
        self.code = code
        self.message = message
        self.clientEmail = clientEmail
    }

    var errorDescription: String? { message }

    /// true для кода AUTOMATION_DENIED — UI показывает кнопку в Настройки.
    var isAutomationDenied: Bool { code == "AUTOMATION_DENIED" }

    /// Drive не подключён или ключ непригоден — UI показывает кнопку «Подключить Google Drive…».
    var needsDriveConnection: Bool {
        ["DRIVE_NOT_CONNECTED", "DRIVE_KEY_INVALID", "DRIVE_AUTH_FAILED"].contains(code)
    }
}

/// Минимальная форма ответа бэкенда, достаточная чтобы понять успех/ошибку
/// до декодирования полного payload.
struct BackendEnvelopeCheck: Decodable {
    let ok: Bool
    let code: String?
    let error: String?
    let clientEmail: String?
}
