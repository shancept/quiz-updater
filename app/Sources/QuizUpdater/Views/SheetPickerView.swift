import SwiftUI

/// Выбор таблицы результатов: список того, что доступно роботу (свежие сверху), поиск по названию
/// и запасной вариант — вставить ссылку на таблицу.
struct SheetPickerView: View {
    @EnvironmentObject private var viewModel: AppViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var link = ""

    private var filteredSheets: [DriveSheet] {
        let trimmed = query.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return viewModel.availableSheets }
        return viewModel.availableSheets.filter { $0.name.localizedCaseInsensitiveContains(trimmed) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Таблица результатов").font(.headline)

            if viewModel.drive.isConnected {
                TextField("Поиск по названию", text: $query)
                    .textFieldStyle(.roundedBorder)
                sheetList
            } else {
                notConnected
            }

            Divider()
            linkSection

            HStack {
                Spacer()
                Button("Отмена") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
        }
        .padding(16)
        .frame(width: 520, height: 540)
        .task { await viewModel.loadSheets() }
        .onChange(of: viewModel.drive.isConnected) { _ in
            Task { await viewModel.loadSheets() }
        }
    }

    // MARK: - Список

    @ViewBuilder
    private var sheetList: some View {
        if viewModel.isLoadingSheets && viewModel.availableSheets.isEmpty {
            ProgressView("Загружаю список таблиц…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = viewModel.sheetListError, viewModel.availableSheets.isEmpty {
            StatusMessageView(message: error)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        } else if viewModel.availableSheets.isEmpty {
            noSheetsShared
        } else if filteredSheets.isEmpty {
            Text("Ничего не найдено")
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            List(filteredSheets) { sheet in
                Button {
                    dismiss()
                    Task { await viewModel.selectSheet(sheet) }
                } label: {
                    row(for: sheet)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func row(for sheet: DriveSheet) -> some View {
        HStack(spacing: 10) {
            Image(systemName: sheet.isGoogleSheet ? "tablecells" : "doc.richtext")
                .foregroundStyle(.secondary)
                .frame(width: 20)
            VStack(alignment: .leading, spacing: 2) {
                Text(sheet.name).lineLimit(1).truncationMode(.middle)
                if let date = sheet.modifiedDate {
                    Text(date.formatted(date: .abbreviated, time: .shortened))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            if sheet.id == viewModel.selectedSheet?.id {
                Image(systemName: "checkmark").foregroundStyle(.tint)
            }
        }
        .contentShape(Rectangle())
    }

    private var noSheetsShared: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Робот пока не видит ни одной таблицы.")
            Text("В Google Drive откройте папку КВИЗ → «Поделиться» и дайте доступ «Читатель» адресу робота — и положите таблицы игр в эту папку.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if let email = viewModel.drive.clientEmail {
                HStack {
                    Text(email).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    CopyButton(text: email)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private var notConnected: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Google Drive не подключён.")
            Text("Выберите JSON-ключ сервисного аккаунта — это делается один раз на каждом Mac.")
                .font(.caption)
                .foregroundStyle(.secondary)
            ConnectDriveButton()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    // MARK: - Ссылка

    private var linkSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Или вставьте ссылку на таблицу").font(.subheadline)
            HStack {
                TextField("https://docs.google.com/spreadsheets/d/…", text: $link)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit(openLink)
                Button("Открыть", action: openLink)
                    .disabled(link.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isBusy)
                if viewModel.isBusy { ProgressView().controlSize(.small) }
            }
            if let error = viewModel.sheetLinkError {
                StatusMessageView(message: error)
            }
        }
    }

    private func openLink() {
        Task {
            if await viewModel.selectSheet(fromLink: link) {
                dismiss()
            }
        }
    }
}
