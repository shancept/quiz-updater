import Foundation

/// Хранилище пользовательских настроек в UserDefaults (путь к Excel, число команд, слайд рейтинга).
struct SettingsStore {
    static let defaultExcelPath = ("~/Library/CloudStorage/GoogleDrive-shancept@gmail.com/"
        + "My Drive/КВИЗ/Копия Копия Калькулятор баллов Классика.xlsx" as NSString)
        .expandingTildeInPath

    private static let excelPathKey = "excelPath"
    private static let maxRowsKey = "maxRows"
    private static let ratingSlideKey = "ratingSlide"

    var excelPath: String {
        get { UserDefaults.standard.string(forKey: Self.excelPathKey) ?? Self.defaultExcelPath }
        set { UserDefaults.standard.set(newValue, forKey: Self.excelPathKey) }
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
