import CryptoKit
import Foundation

/// Кэш превью слайдов в ~/Library/Caches/QuizUpdater/<hash(docName)>/current/,
/// с meta.json для проверки актуальности (по числу слайдов документа).
final class PreviewCache {
    static let shared = PreviewCache()

    struct Meta: Codable {
        let docName: String
        let slideCount: Int
        let exportedAt: Date
    }

    private let root: URL

    private init() {
        let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first!
        root = caches.appendingPathComponent("QuizUpdater", isDirectory: true)
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    private func hash(_ docName: String) -> String {
        let digest = SHA256.hash(data: Data(docName.utf8))
        return digest.compactMap { String(format: "%02x", $0) }.joined().prefix(16).description
    }

    private func docDirectory(for docName: String) -> URL {
        root.appendingPathComponent(hash(docName), isDirectory: true)
    }

    private func slideNumber(from url: URL) -> Int {
        let name = url.deletingPathExtension().lastPathComponent // "export-169....001"
        let numberPart = name.split(separator: ".").last.map(String.init) ?? "0"
        return Int(numberPart) ?? 0
    }

    /// Возвращает кэшированные превью, если они валидны (совпадает число слайдов документа).
    func cachedPreviews(docName: String, expectedSlideCount: Int) -> [SlidePreview]? {
        let dir = docDirectory(for: docName)
        let metaURL = dir.appendingPathComponent("meta.json")
        let currentURL = dir.appendingPathComponent("current", isDirectory: true)

        guard let metaData = try? Data(contentsOf: metaURL),
              let meta = try? JSONDecoder().decode(Meta.self, from: metaData),
              meta.slideCount == expectedSlideCount else {
            return nil
        }
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: currentURL, includingPropertiesForKeys: nil
        ) else {
            return nil
        }
        let jpegs = files.filter { $0.pathExtension.lowercased() == "jpeg" }
        guard jpegs.count == expectedSlideCount else { return nil }

        let sorted = jpegs.sorted { slideNumber(from: $0) < slideNumber(from: $1) }
        return sorted.enumerated().map { index, url in SlidePreview(slide: index + 1, path: url.path) }
    }

    /// Новая временная папка под экспорт — родитель уже существует, саму папку создаст Keynote.
    func newExportDirectory(for docName: String) -> URL {
        let dir = docDirectory(for: docName)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let stamp = Int(Date().timeIntervalSince1970 * 1000)
        return dir.appendingPathComponent("export-\(stamp)", isDirectory: true)
    }

    /// Считает количество уже экспортированных файлов в директории — для прогресс-бара.
    func countExportedFiles(in directory: URL) -> Int {
        (try? FileManager.default.contentsOfDirectory(atPath: directory.path))?.count ?? 0
    }

    /// Атомарно делает только что экспортированную папку текущей и обновляет meta.json.
    func commit(exportDirectory: URL, docName: String, slideCount: Int) throws {
        let dir = docDirectory(for: docName)
        let currentURL = dir.appendingPathComponent("current", isDirectory: true)
        let staleURL = dir.appendingPathComponent("stale-\(Int(Date().timeIntervalSince1970 * 1000))", isDirectory: true)

        if FileManager.default.fileExists(atPath: currentURL.path) {
            try FileManager.default.moveItem(at: currentURL, to: staleURL)
        }
        try FileManager.default.moveItem(at: exportDirectory, to: currentURL)
        if FileManager.default.fileExists(atPath: staleURL.path) {
            try? FileManager.default.removeItem(at: staleURL)
        }

        let meta = Meta(docName: docName, slideCount: slideCount, exportedAt: Date())
        let metaData = try JSONEncoder().encode(meta)
        try metaData.write(to: dir.appendingPathComponent("meta.json"))
    }
}
