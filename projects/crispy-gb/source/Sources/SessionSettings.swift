import Foundation
import CoreGraphics

struct ScanlineSettings: Codable, Hashable {
    var on = false
    var intensity = 0.15
    var colour = "#1a1a2e"
}
struct ColourSettings: Codable, Hashable {
    var rgbShift: [Double] = [0, 0, 0]
    var gamma = 1.0
    var brightness = 1.0
    var contrast = 1.0
    var saturation = 1.0
    var scanline = ScanlineSettings()
    static var crispy: Self {
        var c = Self(); c.gamma = 1.1; c.saturation = 1.1; c.scanline.on = true; return c
    }
}
struct DisplaySettings: Codable, Hashable {
    var fitMode = "fit"
    var fillPercent = 1.0
    var colour = ColourSettings()
    var presets: [ColourSettings?] = [nil, nil, nil]
    var filter = "none"
    var aspectLock = "native"
}
struct ControlSettings: Codable, Hashable {
    var overrides: [String: String] = [:]
    var controllerSlot = 0
}
struct SessionSettings: Codable, Hashable {
    var display = DisplaySettings()
    var controls = ControlSettings()
}
struct SlotMetadata: Codable {
    var date: Date
    var frame: Int
}

// Interpolation is in scale space; crop values are measured in source pixels.
enum FillGeometry {
    static func viewport(screen: CGSize, game: CGSize, percent: Double) -> CGRect {
        guard screen.width > 0, screen.height > 0, game.width > 0, game.height > 0 else { return .zero }
        let fit = min(screen.width / game.width, screen.height / game.height)
        let fill = max(screen.width / game.width, screen.height / game.height)
        let scale = fit + (fill - fit) * min(1, max(0, percent))
        let size = CGSize(width: game.width * scale, height: game.height * scale)
        return CGRect(x: (screen.width - size.width) / 2, y: (screen.height - size.height) / 2, width: size.width, height: size.height)
    }
    static func crop(screen: CGSize, game: CGSize, percent: Double) -> CGSize {
        let rect = viewport(screen: screen, game: game, percent: percent)
        guard rect.width > 0 else { return .zero }
        let scale = rect.width / game.width
        return CGSize(width: abs(max(0, -rect.minX / scale)), height: abs(max(0, -rect.minY / scale)))
    }
    static func safeZone(game: CGSize, percent: Double) -> CGRect {
        let crops = [16.0/9, 16.0/10, 21.0/9].map { crop(screen: CGSize(width: $0 * 1000, height: 1000), game: game, percent: percent) }
        let x = crops.map(\.width).max() ?? 0, y = crops.map(\.height).max() ?? 0
        return CGRect(x: x, y: y, width: max(0, game.width - 2*x), height: max(0, game.height - 2*y))
    }
}

// Missing fields keep their defaults so older and partially specified JSON survives.
extension ScanlineSettings {
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        on = try c.decodeIfPresent(Bool.self, forKey: .on) ?? false
        intensity = min(1, max(0, try c.decodeIfPresent(Double.self, forKey: .intensity) ?? 0.15))
        colour = try c.decodeIfPresent(String.self, forKey: .colour) ?? "#1a1a2e"
    }
}
extension ColourSettings {
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let rgb = try c.decodeIfPresent([Double].self, forKey: .rgbShift) ?? [0,0,0]
        rgbShift = (0..<3).map { min(255, max(0, rgb.indices.contains($0) ? rgb[$0] : 0)) }
        gamma = min(2,max(0,try c.decodeIfPresent(Double.self,forKey:.gamma) ?? 1))
        brightness = min(2,max(0,try c.decodeIfPresent(Double.self,forKey:.brightness) ?? 1))
        contrast = min(2,max(0,try c.decodeIfPresent(Double.self,forKey:.contrast) ?? 1))
        saturation = min(2,max(0,try c.decodeIfPresent(Double.self,forKey:.saturation) ?? 1))
        scanline = try c.decodeIfPresent(ScanlineSettings.self,forKey:.scanline) ?? ScanlineSettings()
    }
}
extension DisplaySettings {
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        fitMode = try c.decodeIfPresent(String.self,forKey:.fitMode) ?? "fit"
        fillPercent = min(1,max(0,try c.decodeIfPresent(Double.self,forKey:.fillPercent) ?? 1))
        colour = try c.decodeIfPresent(ColourSettings.self,forKey:.colour) ?? ColourSettings()
        let saved = try c.decodeIfPresent([ColourSettings?].self,forKey:.presets) ?? []
        presets = (0..<3).map { saved.indices.contains($0) ? saved[$0] : nil }
        filter = try c.decodeIfPresent(String.self,forKey:.filter) ?? "none"
        aspectLock = try c.decodeIfPresent(String.self,forKey:.aspectLock) ?? "native"
    }
}
extension ControlSettings {
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        overrides = try c.decodeIfPresent([String:String].self,forKey:.overrides) ?? [:]
        controllerSlot = max(0,try c.decodeIfPresent(Int.self,forKey:.controllerSlot) ?? 0)
    }
}

extension DisplaySettings {
    func presentationSize(native: CGSize, screen: CGSize) -> CGSize {
        switch aspectLock {
        case "4:3": return CGSize(width: native.height * 4/3, height: native.height)
        case "16:9": return CGSize(width: native.height * 16/9, height: native.height)
        case "free": return screen
        default: return native
        }
    }
    func previewCrop(native: CGSize, screen: CGSize, percent: Double) -> CGSize {
        let game = presentationSize(native: native, screen: screen)
        let rect = FillGeometry.viewport(screen: screen, game: game, percent: percent)
        guard rect.width > 0, rect.height > 0 else { return .zero }
        return CGSize(width: abs(max(0, -rect.minX * native.width / rect.width)), height: abs(max(0, -rect.minY * native.height / rect.height)))
    }
    func previewSafeZone(native: CGSize, percent: Double) -> CGRect {
        let crops = [16.0/9,16.0/10,21.0/9].map { previewCrop(native:native,screen:CGSize(width:$0*1000,height:1000),percent:percent) }
        let x = crops.map(\.width).max() ?? 0, y = crops.map(\.height).max() ?? 0
        return CGRect(x:x,y:y,width:max(0,native.width-2*x),height:max(0,native.height-2*y))
    }
}
