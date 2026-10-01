import AppKit
import SwiftUI

struct StatusBarView: View {
    @EnvironmentObject private var viewModel: AppViewModel

    var body: some View {
        HStack {
            if viewModel.isBusy {
                ProgressView().controlSize(.small)
            }
            if let status = viewModel.statusMessage {
                Text(status.text)
                    .foregroundStyle(status.isError ? .red : .primary)
                    .lineLimit(1)
                    .truncationMode(.tail)
            } else {
                Text(" ")
            }
            Spacer()
            if viewModel.statusMessage?.isAutomationDenied == true {
                Button("Открыть настройки") {
                    if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation") {
                        NSWorkspace.shared.open(url)
                    }
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }
}
