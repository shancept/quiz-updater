// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "QuizUpdater",
    platforms: [
        .macOS(.v13)
    ],
    targets: [
        .executableTarget(
            name: "QuizUpdater",
            path: "Sources/QuizUpdater"
        )
    ]
)
