import Foundation
import CoreGraphics

struct PlaybackTiming {
    private var accumulated = 0.0
    mutating func reset() { accumulated = 0 }
    mutating func frames(elapsed: Double, fps: Double, speed: Double) -> Int {
        let duration = 1 / max(1, fps)
        accumulated += min(max(0, elapsed), 0.1) * speed
        let count = min(32, Int((accumulated + 0.000000001) / duration))
        accumulated -= Double(count) * duration
        if count == 32 { accumulated = min(accumulated, duration) }
        return count
    }
}

enum PlaybackLayout {
    static func viewport(screen: CGSize, game: CGSize, mode: Int) -> CGRect {
        guard screen.width > 0, screen.height > 0, game.width > 0, game.height > 0 else { return .zero }
        var scale = mode == 2 ? max(screen.width / game.width, screen.height / game.height) : min(screen.width / game.width, screen.height / game.height)
        if mode == 1 && scale >= 1 { scale = floor(scale) }
        let size = CGSize(width: game.width * scale, height: game.height * scale)
        return CGRect(x: (screen.width - size.width) / 2, y: (screen.height - size.height) / 2, width: size.width, height: size.height)
    }
}
