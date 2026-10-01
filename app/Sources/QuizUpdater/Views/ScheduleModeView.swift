import SwiftUI

struct ScheduleModeView: View {
    @EnvironmentObject private var viewModel: AppViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button("Загрузить расписание") {
                Task { await viewModel.fetchSchedule() }
            }
            .disabled(viewModel.isBusy)

            if let slide = viewModel.scheduleTargetSlide {
                Text("Целевой слайд: \(slide)").font(.callout)
            } else {
                Text("Кликните по слайду с 6 карточками слева").font(.callout).foregroundStyle(.secondary)
            }

            if !viewModel.scheduleGames.isEmpty {
                Text("Игры (\(viewModel.selectedGameIDs.count) из \(viewModel.scheduleGames.count))")
                    .font(.headline)
                List(viewModel.scheduleGames) { game in
                    Toggle(isOn: Binding(
                        get: { viewModel.selectedGameIDs.contains(game.id) },
                        set: { _ in viewModel.toggleGame(game.id) }
                    )) {
                        VStack(alignment: .leading) {
                            Text(game.rawTitle).lineLimit(1)
                            Text("\(game.date) · \(game.dateText)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .frame(minHeight: 200)
            }

            if !viewModel.scheduleSlots.isEmpty {
                Text("Превью слотов").font(.headline)
                List(viewModel.scheduleSlots) { slot in
                    HStack {
                        Text("Слот \(slot.slotIndex)").frame(width: 60, alignment: .leading)
                        if slot.filled {
                            Text(slot.cardText?.replacingOccurrences(of: "\n", with: " / ") ?? "")
                                .lineLimit(1)
                            Spacer()
                            Text(slot.dateText ?? "")
                        } else {
                            Text("пусто").foregroundStyle(.secondary)
                        }
                    }
                }
                .frame(minHeight: 140)
            }

            if !viewModel.scheduleWarnings.isEmpty {
                ForEach(viewModel.scheduleWarnings, id: \.self) { warning in
                    Text(warning).font(.caption).foregroundStyle(.orange)
                }
            }

            HStack {
                Button("Проверить") {
                    Task { await viewModel.runFillSlots(dryRun: true) }
                }
                .disabled(viewModel.scheduleTargetSlide == nil || viewModel.selectedGameIDs.isEmpty || viewModel.isBusy)

                Button("Заполнить карточки") {
                    Task { await viewModel.runFillSlots(dryRun: false) }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(viewModel.scheduleTargetSlide == nil || viewModel.selectedGameIDs.isEmpty || viewModel.isBusy)
            }
        }
    }
}
