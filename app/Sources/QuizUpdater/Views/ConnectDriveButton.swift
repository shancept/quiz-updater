import SwiftUI
import UniformTypeIdentifiers

/// «Подключить Google Drive…»: выбор JSON-ключа сервисного аккаунта → копирование в
/// ~/Library/Application Support/QuizUpdater и проверка доступа (делает бэкенд).
struct ConnectDriveButton: View {
    @EnvironmentObject private var viewModel: AppViewModel
    @State private var isImporting = false

    var body: some View {
        Button("Подключить Google Drive…") { isImporting = true }
            .disabled(viewModel.isBusy)
            .fileImporter(isPresented: $isImporting, allowedContentTypes: [.json]) { result in
                if case .success(let url) = result {
                    Task { await viewModel.connectDrive(keyURL: url) }
                }
            }
    }
}
