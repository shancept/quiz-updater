import AppKit
import SwiftUI

/// Кнопка «Скопировать»: кладёт текст в буфер обмена и на секунду-другую подтверждает это.
struct CopyButton: View {
    let text: String
    var title = "Скопировать"
    @State private var copied = false

    var body: some View {
        Button(copied ? "Скопировано" : title) {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(text, forType: .string)
            copied = true
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { copied = false }
        }
    }
}
