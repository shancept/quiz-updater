import SwiftUI
import UniformTypeIdentifiers

struct TopBarView: View {
    @EnvironmentObject private var viewModel: AppViewModel
    @State private var isShowingExcelPicker = false

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
                Text("Excel-файл").font(.caption).foregroundStyle(.secondary)
                HStack {
                    Text((viewModel.excelPath as NSString).lastPathComponent)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .frame(minWidth: 200, maxWidth: 260, alignment: .leading)
                        .help(viewModel.excelPath)

                    Button("Выбрать…") { isShowingExcelPicker = true }
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
        .fileImporter(
            isPresented: $isShowingExcelPicker,
            allowedContentTypes: [
                UTType(filenameExtension: "xlsx") ?? .data
            ]
        ) { result in
            if case .success(let url) = result {
                viewModel.excelPath = url.path
                Task { await viewModel.loadExcel() }
            }
        }
        .onChange(of: viewModel.selectedDocument) { _ in
            Task { await viewModel.loadPreviews() }
        }
    }
}
