import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var viewModel: AppViewModel

    var body: some View {
        VStack(spacing: 0) {
            TopBarView()
                .padding(12)
            Divider()

            HSplitView {
                SlideGridView()
                    .frame(minWidth: 420, maxWidth: .infinity, maxHeight: .infinity)

                modePanel
                    .frame(minWidth: 340, idealWidth: 360, maxWidth: 420, maxHeight: .infinity)
            }

            Divider()
            StatusBarView()
        }
        .task {
            await viewModel.refreshDocuments()
            await viewModel.refreshDriveStatus()
            await viewModel.loadTeams()
        }
    }

    @ViewBuilder
    private var modePanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Picker("Режим", selection: $viewModel.mode) {
                ForEach(AppMode.allCases, id: \.self) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()

            Divider()

            switch viewModel.mode {
            case .rating:
                RatingModeView()
            case .names:
                NamesModeView()
            case .schedule:
                ScheduleModeView()
            }

            Spacer()
        }
        .padding(12)
    }
}
