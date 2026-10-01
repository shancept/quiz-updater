import SwiftUI

struct SlideGridView: View {
    @EnvironmentObject private var viewModel: AppViewModel

    private let columns = [GridItem(.adaptive(minimum: 140), spacing: 10)]

    var body: some View {
        Group {
            switch viewModel.previewState {
            case .idle:
                placeholder("Выберите документ и нажмите «Обновить превью»", systemImage: "photo.stack")

            case .exporting(let done, let total):
                VStack(spacing: 12) {
                    ProgressView(value: total > 0 ? Double(done) / Double(total) : 0)
                        .frame(width: 240)
                    Text("Экспорт слайдов: \(done) из \(total)…")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            case .ready(let slides):
                ScrollView {
                    LazyVGrid(columns: columns, spacing: 10) {
                        ForEach(slides) { slide in
                            SlideThumbnailView(slide: slide)
                                .onTapGesture { handleTap(on: slide) }
                        }
                    }
                    .padding(10)
                }

            case .failed(let message):
                placeholder(message, systemImage: "exclamationmark.triangle", isError: true)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func handleTap(on slide: SlidePreview) {
        switch viewModel.mode {
        case .rating:
            viewModel.selectRatingSlide(slide.slide)
        case .names:
            viewModel.selectStartSlide(slide.slide)
        case .schedule:
            viewModel.selectScheduleSlide(slide.slide)
        }
    }

    private func placeholder(_ text: String, systemImage: String, isError: Bool = false) -> some View {
        VStack(spacing: 8) {
            Image(systemName: systemImage)
                .font(.system(size: 32))
                .foregroundStyle(isError ? .red : .secondary)
            Text(text)
                .multilineTextAlignment(.center)
                .foregroundStyle(isError ? .red : .secondary)
                .padding(.horizontal, 24)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
