import SwiftUI

struct NamesModeView: View {
    @EnvironmentObject private var viewModel: AppViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Отметьте места, затем кликните по слайду 1-го места слева")
                .font(.caption)
                .foregroundStyle(.secondary)

            List(viewModel.teams) { team in
                Toggle(isOn: Binding(
                    get: { viewModel.selectedPlaces.contains(team.place) },
                    set: { _ in viewModel.togglePlace(team.place) }
                )) {
                    Text("\(team.place). \(team.name)")
                }
            }
            .frame(minHeight: 160)

            if let start = viewModel.startSlide {
                Text("Стартовый слайд: \(start)").font(.callout)
            } else {
                Text("Стартовый слайд не выбран").font(.callout).foregroundStyle(.secondary)
            }

            if !viewModel.pairs.isEmpty {
                Text("Назначения").font(.headline)
                List {
                    ForEach(viewModel.pairs) { pair in
                        HStack {
                            Text("\(pair.place) место").frame(width: 70, alignment: .leading)
                            Text(pair.teamName).lineLimit(1)
                            Spacer()
                            Stepper(
                                value: Binding(
                                    get: { pair.slide },
                                    set: { viewModel.updatePairSlide(place: pair.place, slide: $0) }
                                ),
                                in: 1...9999
                            ) {
                                Text("Слайд \(pair.slide)")
                            }
                        }
                    }
                }
                .frame(minHeight: 140)
            }

            HStack {
                Button("Проверить") {
                    Task { await viewModel.runNames(dryRun: true) }
                }
                .disabled(viewModel.pairs.isEmpty || viewModel.isBusy)

                Button("Заменить имена") {
                    Task { await viewModel.runNames(dryRun: false) }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(viewModel.pairs.isEmpty || viewModel.isBusy)
            }
        }
    }
}
