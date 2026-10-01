import SwiftUI

/// Подключение Google Drive на этом Mac: ключ сервисного аккаунта и адрес робота,
/// которому ведущий даёт доступ «Читатель» к папке с таблицами.
struct DriveSettingsView: View {
    @EnvironmentObject private var viewModel: AppViewModel
    @Environment(\.dismiss) private var dismiss

    private var connectionLine: String {
        guard let count = viewModel.drive.sheetCount else { return "Подключено" }
        return "Подключено, таблиц доступно: \(count)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Google Drive").font(.headline)

            if viewModel.drive.isConnected {
                Label(connectionLine, systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)

                if let email = viewModel.drive.clientEmail {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Адрес робота").font(.caption).foregroundStyle(.secondary)
                        HStack {
                            Text(email)
                                .textSelection(.enabled)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 8)
                            CopyButton(text: email)
                        }
                        Text("В Google Drive откройте папку КВИЗ → «Поделиться» и дайте этому адресу доступ «Читатель». Таблицы игр должны лежать в этой папке.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            } else {
                Label("Не подключён", systemImage: "xmark.circle")
                    .foregroundStyle(.secondary)
                Text("Выберите JSON-ключ сервисного аккаунта. Делается один раз на каждом Mac.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let error = viewModel.sheetListError {
                StatusMessageView(message: error)
            }

            HStack {
                ConnectDriveButton()
                if viewModel.isBusy { ProgressView().controlSize(.small) }
                Spacer()
                Button("Закрыть") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
        }
        .padding(20)
        .frame(width: 480)
        .task {
            // Живая проверка доступа: обновляет «таблиц доступно: N».
            await viewModel.loadSheets()
        }
    }
}
