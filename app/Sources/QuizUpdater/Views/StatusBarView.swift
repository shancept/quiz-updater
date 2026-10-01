import SwiftUI

struct StatusBarView: View {
    @EnvironmentObject private var viewModel: AppViewModel

    var body: some View {
        HStack {
            if viewModel.isBusy {
                ProgressView().controlSize(.small)
            }
            if let status = viewModel.statusMessage {
                StatusMessageView(message: status)
            } else {
                Text(" ")
                Spacer()
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }
}
