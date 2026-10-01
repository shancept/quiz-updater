import SwiftUI

struct NamesModeView: View {
    @EnvironmentObject private var viewModel: AppViewModel

    var body: some View {
        // Прокрутка: в минимальном окне (высота 600) панель с дополнительными местами иначе не помещается.
        ScrollView(.vertical) {
            content
                .padding(.trailing, 4)
        }
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Отметьте места. Кликните по слайду 1-го места слева: места 1–3 возьмут готовые слайды, остальные создадутся из слайда-шаблона «НОМЕР МЕСТО»")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            List(viewModel.teams) { team in
                Toggle(isOn: Binding(
                    get: { viewModel.selectedPlaces.contains(team.place) },
                    set: { _ in viewModel.togglePlace(team.place) }
                )) {
                    Text("\(team.place). \(team.name)")
                }
            }
            .frame(height: 170)

            if let start = viewModel.startSlide {
                Text("Слайд 1-го места: \(start)").font(.callout)
            } else {
                Text("Слайд 1-го места не выбран").font(.callout).foregroundStyle(.secondary)
            }

            if !viewModel.pairs.isEmpty {
                Text("Места с готовыми слайдами").font(.headline)
                VStack(alignment: .leading, spacing: 4) {
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
            }

            if !viewModel.extraTeams.isEmpty {
                Text("Дополнительные места").font(.headline)
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(viewModel.extraTeams) { team in
                        HStack {
                            Text("\(team.place) место").frame(width: 70, alignment: .leading)
                            Text(team.name).lineLimit(1)
                            Spacer()
                            Text("новый слайд").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }

            if viewModel.startSlide != nil, let template = viewModel.templateSlide {
                VStack(alignment: .leading, spacing: 2) {
                    Stepper(
                        value: Binding(get: { template }, set: { viewModel.updateTemplateSlide($0) }),
                        in: 1...9999
                    ) {
                        Text("Слайд-шаблон «НОМЕР»: \(template)")
                    }
                    Text(viewModel.extraTeams.isEmpty
                         ? "Дополнительных мест нет — шаблон будет скрыт из показа"
                         : "Новые слайды встанут перед слайдом 3-го места, от большего места к меньшему; сам шаблон станет самым младшим из дополнительных мест")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            HStack {
                Button("Проверить") {
                    Task { await viewModel.runNames(dryRun: true) }
                }
                .disabled(!viewModel.canRunNames || viewModel.isBusy)

                Button("Заменить имена") {
                    Task { await viewModel.runNames(dryRun: false) }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(!viewModel.canRunNames || viewModel.isBusy)
            }
        }
    }
}
