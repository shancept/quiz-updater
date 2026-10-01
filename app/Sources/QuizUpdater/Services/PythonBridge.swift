import Foundation

/// Инфраструктурные ошибки моста Swift↔Python (в отличие от BackendError,
/// который приходит из самого quiz_backend в виде {"ok":false,"code",...}).
enum BridgeError: Error, LocalizedError {
    case pythonNotFound
    case backendNotFound
    case launchFailed(String)
    case invalidOutput(String)
    case timeout

    var errorDescription: String? {
        switch self {
        case .pythonNotFound:
            return "Не найден Python 3. Установите Command Line Tools: xcode-select --install"
        case .backendNotFound:
            return "Не найдена папка backend с quiz_backend. Задайте переменную окружения QUIZ_BACKEND_DIR для запуска в режиме разработки."
        case .launchFailed(let reason):
            return "Не удалось запустить бэкенд: \(reason)"
        case .invalidOutput(let raw):
            return "Бэкенд вернул некорректный ответ: \(raw.isEmpty ? "(пусто)" : raw)"
        case .timeout:
            return "Превышено время ожидания ответа от бэкенда"
        }
    }
}

/// Запускает python3 -m quiz_backend <подкоманда> ... как подпроцесс и декодирует JSON-ответ.
final class PythonBridge {
    static let shared = PythonBridge()

    private let pythonPath: String?
    private let backendDir: URL?
    private let initError: BridgeError?

    private init() {
        do {
            let dir = try Self.resolveBackendDirectory()
            let py = try Self.resolvePythonPath()
            self.backendDir = dir
            self.pythonPath = py
            self.initError = nil
        } catch let error as BridgeError {
            self.backendDir = nil
            self.pythonPath = nil
            self.initError = error
        } catch {
            self.backendDir = nil
            self.pythonPath = nil
            self.initError = .launchFailed(error.localizedDescription)
        }
    }

    // MARK: - Поиск python3 и папки бэкенда

    static func resolveBackendDirectory() throws -> URL {
        if let resourceURL = Bundle.main.resourceURL {
            let candidate = resourceURL.appendingPathComponent("backend")
            if FileManager.default.fileExists(atPath: candidate.appendingPathComponent("quiz_backend").path) {
                return candidate
            }
        }
        if let envDir = ProcessInfo.processInfo.environment["QUIZ_BACKEND_DIR"] {
            let url = URL(fileURLWithPath: envDir)
            if FileManager.default.fileExists(atPath: url.appendingPathComponent("quiz_backend").path) {
                return url
            }
        }
        throw BridgeError.backendNotFound
    }

    static func resolvePythonPath() throws -> String {
        let candidates = [
            "/Library/Developer/CommandLineTools/usr/bin/python3",
            "/Applications/Xcode.app/Contents/Developer/usr/bin/python3",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
        ]
        for path in candidates where FileManager.default.isExecutableFile(atPath: path) {
            return path
        }
        // /usr/bin/python3 без CLT — стаб, показывающий диалог установки. Пробуем последним.
        if commandLineToolsInstalled(), FileManager.default.isExecutableFile(atPath: "/usr/bin/python3") {
            return "/usr/bin/python3"
        }
        throw BridgeError.pythonNotFound
    }

    private static func commandLineToolsInstalled() -> Bool {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/xcode-select")
        process.arguments = ["-p"]
        process.standardOutput = Pipe()
        process.standardError = Pipe()
        do {
            try process.run()
            process.waitUntilExit()
            return process.terminationStatus == 0
        } catch {
            return false
        }
    }

    private func buildEnvironment(backendDir: URL) -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        let vendorDir = backendDir.appendingPathComponent("vendor").path
        var pythonPathValue = backendDir.path + ":" + vendorDir
        if let existing = env["PYTHONPATH"], !existing.isEmpty {
            pythonPathValue += ":" + existing
        }
        env["PYTHONPATH"] = pythonPathValue
        // Без этого Python создаёт __pycache__ в Contents/Resources и ломает подпись .app.
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env
    }

    // MARK: - Публичный API

    func run<T: Decodable>(_ arguments: [String], timeout: TimeInterval = 60) async throws -> T {
        guard let pythonPath, let backendDir else {
            throw initError ?? BridgeError.pythonNotFound
        }
        let data = try await runRaw(pythonPath: pythonPath, backendDir: backendDir, arguments: arguments, timeout: timeout)
        return try decode(data)
    }

    private func decode<T: Decodable>(_ data: Data) throws -> T {
        let decoder = JSONDecoder()
        let check: BackendEnvelopeCheck
        do {
            check = try decoder.decode(BackendEnvelopeCheck.self, from: data)
        } catch {
            let raw = String(data: data, encoding: .utf8) ?? "<binary>"
            throw BridgeError.invalidOutput(raw)
        }
        if !check.ok {
            throw BackendError(code: check.code ?? "UNKNOWN_ERROR", message: check.error ?? "Неизвестная ошибка бэкенда")
        }
        return try decoder.decode(T.self, from: data)
    }

    // MARK: - Запуск подпроцесса

    private func runRaw(pythonPath: String, backendDir: URL, arguments: [String], timeout: TimeInterval) async throws -> Data {
        try await withCheckedThrowingContinuation { continuation in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: pythonPath)
            process.arguments = ["-m", "quiz_backend"] + arguments
            process.environment = buildEnvironment(backendDir: backendDir)

            let stdoutPipe = Pipe()
            let stderrPipe = Pipe()
            process.standardOutput = stdoutPipe
            process.standardError = stderrPipe

            do {
                try process.run()
            } catch {
                continuation.resume(throwing: BridgeError.launchFailed(error.localizedDescription))
                return
            }

            // Читаем stdout/stderr на фоновых очередях ПАРАЛЛЕЛЬНО с ожиданием завершения
            // процесса — иначе вывод больше буфера пайпа (например, JSON с ~200 путями
            // превью) приведёт к дедлоку.
            let group = DispatchGroup()
            let stdoutBox = DataBox()
            let stderrBox = DataBox()

            group.enter()
            DispatchQueue.global(qos: .utility).async {
                stdoutBox.data = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
                group.leave()
            }
            group.enter()
            DispatchQueue.global(qos: .utility).async {
                stderrBox.data = stderrPipe.fileHandleForReading.readDataToEndOfFile()
                group.leave()
            }

            let timedOut = TimeoutFlag()
            let timeoutItem = DispatchWorkItem {
                timedOut.mark()
                if process.isRunning { process.terminate() }
            }
            DispatchQueue.global().asyncAfter(deadline: .now() + timeout, execute: timeoutItem)

            group.notify(queue: .global(qos: .utility)) {
                process.waitUntilExit()
                timeoutItem.cancel()

                if timedOut.isMarked {
                    continuation.resume(throwing: BridgeError.timeout)
                    return
                }
                if process.terminationStatus != 0 && stdoutBox.data.isEmpty {
                    let stderrText = String(data: stderrBox.data, encoding: .utf8) ?? ""
                    continuation.resume(throwing: BridgeError.invalidOutput(stderrText))
                    return
                }
                continuation.resume(returning: stdoutBox.data)
            }
        }
    }
}

private final class DataBox: @unchecked Sendable {
    var data = Data()
}

private final class TimeoutFlag {
    private var value = false
    private let lock = NSLock()

    func mark() {
        lock.lock(); defer { lock.unlock() }
        value = true
    }

    var isMarked: Bool {
        lock.lock(); defer { lock.unlock() }
        return value
    }
}
