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

struct ReadExcelPayload: Decodable {
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
    let teams: [Team]?
    let updated: Int?
    let message: String?
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

    var errorDescription: String? { message }

    /// true для кода AUTOMATION_DENIED — UI показывает кнопку в Настройки.
    var isAutomationDenied: Bool { code == "AUTOMATION_DENIED" }
}

/// Минимальная форма ответа бэкенда, достаточная чтобы понять успех/ошибку
/// до декодирования полного payload.
struct BackendEnvelopeCheck: Decodable {
    let ok: Bool
    let code: String?
    let error: String?
}
