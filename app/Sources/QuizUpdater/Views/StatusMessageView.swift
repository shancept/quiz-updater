import AppKit
import SwiftUI

/// Сообщение для ведущего с кнопками действий, которые нужны именно для этой ошибки:
/// «Скопировать» адрес робота, «Подключить Google Drive…», «Открыть настройки» (Automation).
struct StatusMessageView: View {
    let message: StatusMessage

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(message.text)
                .foregroundStyle(message.isError ? .red : .primary)
                // Без lineLimit: в сообщении может быть адрес робота, его нельзя обрезать.
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)
            Spacer(minLength: 8)
            if let email = message.clientEmail {
                CopyButton(text: email)
            }
            if message.needsDriveConnection {
                ConnectDriveButton()
            }
            if message.isAutomationDenied {
                Button("Открыть настройки") {
                    if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation") {
                        NSWorkspace.shared.open(url)
                    }
                }
            }
        }
    }
}
