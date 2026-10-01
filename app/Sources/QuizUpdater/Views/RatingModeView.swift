import SwiftUI

struct RatingModeView: View {
    @EnvironmentObject private var viewModel: AppViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Слайд с таблицей:")
                if let slide = viewModel.ratingSlide {
                    Text("\(slide)").bold()
                } else {
                    Text("не выбран").foregroundStyle(.secondary)
                }
            }

            Stepper("Команд не больше: \(viewModel.maxRows)", value: $viewModel.maxRows, in: 1...50)

            Text("Строк в таблице Keynote станет столько, сколько команд (не больше этого числа)")
                .font(.caption)
                .foregroundStyle(.secondary)

            Text("Кликните по слайду с таблицей рейтинга слева")
                .font(.caption)
                .foregroundStyle(.secondary)

            List(viewModel.teams.prefix(viewModel.maxRows)) { team in
                HStack {
                    Text("\(team.place)").frame(width: 24, alignment: .trailing).bold()
                    Text(team.name).lineLimit(1)
                    Spacer()
                    Text(formatValue(team.total)).foregroundStyle(.secondary)
                }
            }
            .frame(minHeight: 200)

            HStack {
                Button("Проверить") {
                    Task { await viewModel.runRating(dryRun: true) }
                }
                .disabled(viewModel.ratingSlide == nil || viewModel.isBusy)

                Button("Обновить таблицу") {
                    Task { await viewModel.runRating(dryRun: false) }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(viewModel.ratingSlide == nil || viewModel.isBusy)
            }
        }
    }

    private func formatValue(_ value: Double?) -> String {
        guard let value else { return "-" }
        if value == value.rounded() {
            return String(Int(value))
        }
        return String(value)
    }
}
