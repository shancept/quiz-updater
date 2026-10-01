import SwiftUI

struct TopBarView: View {
    @EnvironmentObject private var viewModel: AppViewModel
    @State private var isShowingSheetPicker = false
    @State private var isShowingDriveSettings = false

    var body: some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Документ Keynote").font(.caption).foregroundStyle(.secondary)
                HStack {
                    Picker("", selection: $viewModel.selectedDocument) {
                        Text("Не выбран").tag(KeynoteDocument?.none)
                        ForEach(viewModel.documents) { doc in
                            Text("\(doc.name) (\(doc.slideCount) слайдов)").tag(Optional(doc))
                        }
                    }
                    .labelsHidden()
                    .frame(minWidth: 260)

                    Button {
                        Task { await viewModel.refreshDocuments() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .help("Обновить список открытых документов")
                }
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Таблица результатов").font(.caption).foregroundStyle(.secondary)
                HStack {
                    Text(viewModel.selectedSheet?.name ?? "Не выбрана")
                        .foregroundStyle(viewModel.selectedSheet == nil ? .secondary : .primary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .frame(minWidth: 150, maxWidth: 240, alignment: .leading)
                        .help(viewModel.selectedSheet?.name ?? "Таблица не выбрана")

                    Button("Выбрать…") { isShowingSheetPicker = true }

                    Button {
                        isShowingDriveSettings = true
                    } label: {
                        Image(systemName: viewModel.drive.isConnected ? "icloud" : "icloud.slash")
                    }
                    .help("Google Drive: подключение и адрес робота")
                }
            }

            Spacer()

            Button {
                Task { await viewModel.loadPreviews(force: true) }
            } label: {
                Label("Обновить превью", systemImage: "photo.on.rectangle")
            }
            .disabled(viewModel.selectedDocument == nil || viewModel.isBusy)
        }
        .sheet(isPresented: $isShowingSheetPicker) {
            SheetPickerView().environmentObject(viewModel)
        }
        .sheet(isPresented: $isShowingDriveSettings) {
            DriveSettingsView().environmentObject(viewModel)
        }
        .onChange(of: viewModel.selectedDocument) { _ in
            Task { await viewModel.loadPreviews() }
        }
    }
}
