import AppKit
import ImageIO
import SwiftUI

struct SlideThumbnailView: View {
    @EnvironmentObject private var viewModel: AppViewModel
    let slide: SlidePreview

    @State private var image: NSImage?

    private static let cache = NSCache<NSString, NSImage>()

    var body: some View {
        ZStack(alignment: .topTrailing) {
            RoundedRectangle(cornerRadius: 6)
                .fill(Color.gray.opacity(0.15))
                .aspectRatio(16.0 / 9.0, contentMode: .fit)
                .overlay {
                    if let image {
                        Image(nsImage: image)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                    } else {
                        ProgressView().controlSize(.small)
                    }
                }
                .overlay(alignment: .bottomLeading) {
                    Text("\(slide.slide)")
                        .font(.caption2)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(.black.opacity(0.6))
                        .foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                        .padding(4)
                }
                .overlay {
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(borderColor, lineWidth: isSelected ? 3 : 2)
                }
                .clipShape(RoundedRectangle(cornerRadius: 6))

            if let badgeText {
                Text(badgeText)
                    .font(.caption2.bold())
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(Color.accentColor)
                    .foregroundStyle(.white)
                    .clipShape(Capsule())
                    .padding(4)
            }
        }
        .task(id: slide.path) {
            await loadThumbnail()
        }
    }

    private var isSelected: Bool {
        switch viewModel.mode {
        case .rating: return viewModel.ratingSlide == slide.slide
        case .names: return viewModel.startSlide == slide.slide
        case .schedule: return viewModel.scheduleTargetSlide == slide.slide
        }
    }

    private var badgeText: String? {
        guard viewModel.mode == .names else { return nil }
        guard let pair = viewModel.pairs.first(where: { $0.slide == slide.slide }) else { return nil }
        return "\(pair.place) место"
    }

    private var borderColor: Color {
        if isSelected { return .accentColor }
        if viewModel.mode == .names, let found = viewModel.placeholderFoundBySlide[slide.slide] {
            return found ? .green : .red
        }
        return .clear
    }

    private func loadThumbnail() async {
        let cacheKey = slide.path as NSString
        if let cached = Self.cache.object(forKey: cacheKey) {
            image = cached
            return
        }
        let path = slide.path
        let loaded = await Task.detached(priority: .userInitiated) { () -> NSImage? in
            let url = URL(fileURLWithPath: path)
            guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
            let options: [CFString: Any] = [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceThumbnailMaxPixelSize: 400,
                kCGImageSourceCreateThumbnailWithTransform: true,
            ]
            guard let cgImage = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else { return nil }
            return NSImage(cgImage: cgImage, size: .zero)
        }.value
        if let loaded {
            Self.cache.setObject(loaded, forKey: cacheKey)
            image = loaded
        }
    }
}
