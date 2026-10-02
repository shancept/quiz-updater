import Foundation

/// Таблица результатов, выбранная ведущим: ID файла на Google Drive и название для отображения.
struct SelectedSheet: Hashable {
    let id: String
    let name: String
}

/// Хранилище пользовательских настроек в UserDefaults (выбранная таблица, число команд, слайд рейтинга).
struct SettingsStore {
    private static let sheetIDKey = "sheetID"
    private static let sheetNameKey = "sheetName"
    private static let maxRowsKey = "maxRows"
    private static let ratingSlideKey = "ratingSlide"
    /// Ключ локального режима, который удалён: старое значение чистим, чтобы не висело в настройках.
    private static let legacyExcelPathKey = "excelPath"

    init() {
        UserDefaults.standard.removeObject(forKey: Self.legacyExcelPathKey)
    }

    /// Выбор действует, пока ведущий не выберет другую таблицу.
    var sheet: SelectedSheet? {
        get {
            guard let id = UserDefaults.standard.string(forKey: Self.sheetIDKey), !id.isEmpty else { return nil }
            let name = UserDefaults.standard.string(forKey: Self.sheetNameKey) ?? id
            return SelectedSheet(id: id, name: name)
        }
        set {
            if let newValue {
                UserDefaults.standard.set(newValue.id, forKey: Self.sheetIDKey)
                UserDefaults.standard.set(newValue.name, forKey: Self.sheetNameKey)
            } else {
                UserDefaults.standard.removeObject(forKey: Self.sheetIDKey)
                UserDefaults.standard.removeObject(forKey: Self.sheetNameKey)
            }
        }
    }

    var maxRows: Int {
        get {
            let value = UserDefaults.standard.integer(forKey: Self.maxRowsKey)
            return value == 0 ? 10 : value
        }
        set { UserDefaults.standard.set(newValue, forKey: Self.maxRowsKey) }
    }

    var ratingSlide: Int? {
        get {
            let value = UserDefaults.standard.integer(forKey: Self.ratingSlideKey)
            return value == 0 ? nil : value
        }
        set {
            if let newValue {
                UserDefaults.standard.set(newValue, forKey: Self.ratingSlideKey)
            } else {
                UserDefaults.standard.removeObject(forKey: Self.ratingSlideKey)
            }
        }
    }
}
