import AppKit
import CryptoKit
import Foundation

struct EmbeddedGame: Codable {
    let title: String
    let filename: String
    let sha256: String
    let coverFilename: String?

    static func current() -> (EmbeddedGame, URL)? {
        guard let resources = Bundle.main.resourceURL else { return nil }
        let folder = resources.appendingPathComponent("EmbeddedGame", isDirectory: true)
        guard let data = try? Data(contentsOf: folder.appendingPathComponent("game.json")),
              let game = try? JSONDecoder().decode(EmbeddedGame.self, from: data),
              game.filename == URL(fileURLWithPath: game.filename).lastPathComponent else { return nil }
        let rom = folder.appendingPathComponent(game.filename)
        guard FileManager.default.fileExists(atPath: rom.path) else { return nil }
        return (game, rom)
    }

    var saveDirectory: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("mGBA Studio/Standalone/\(sha256)", isDirectory: true)
    }
}

enum StandaloneExporter {
    struct ExportError: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    static func export(title: String, romURL: URL, coverURL: URL?, to destination: URL) throws {
        let manager = FileManager.default
        let app = Bundle.main.bundleURL
        guard app.pathExtension == "app", manager.fileExists(atPath: app.appendingPathComponent("Contents/MacOS/CrispyGB").path) else {
            throw ExportError(message: "Export is available from the built Crispy GB app.")
        }
        guard !manager.fileExists(atPath: destination.path) else {
            throw ExportError(message: "An app already exists at this location. Choose a different name.")
        }
        let romData = try Data(contentsOf: romURL, options: .mappedIfSafe)
        let digest = SHA256.hash(data: romData).map { String(format: "%02x", $0) }.joined()
        let staging = destination.deletingLastPathComponent().appendingPathComponent(".mgba-export-\(UUID().uuidString).app")
        defer { try? manager.removeItem(at: staging) }
        try manager.copyItem(at: app, to: staging)
        let contents = staging.appendingPathComponent("Contents")
        let resources = contents.appendingPathComponent("Resources")
        let embedded = resources.appendingPathComponent("EmbeddedGame", isDirectory: true)
        if manager.fileExists(atPath: embedded.path) { try manager.removeItem(at: embedded) }
        try manager.createDirectory(at: embedded, withIntermediateDirectories: true)
        let filename = "game.\(romURL.pathExtension.lowercased())"
        try romData.write(to: embedded.appendingPathComponent(filename), options: .atomic)
        var embeddedCover: String?
        if let coverURL, manager.fileExists(atPath: coverURL.path) {
            let filename = "cover.\(coverURL.pathExtension.isEmpty ? "png" : coverURL.pathExtension)"
            try manager.copyItem(at: coverURL, to: embedded.appendingPathComponent(filename))
            embeddedCover = filename
        }
        let manifest = EmbeddedGame(title: title, filename: filename, sha256: digest, coverFilename: embeddedCover)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(manifest).write(to: embedded.appendingPathComponent("game.json"), options: .atomic)
        let plistURL = contents.appendingPathComponent("Info.plist")
        var plist = try PropertyListSerialization.propertyList(from: Data(contentsOf: plistURL), format: nil) as? [String: Any] ?? [:]
        plist["CFBundleName"] = title
        plist["CFBundleDisplayName"] = title
        plist["CFBundleIdentifier"] = "local.crispygb.\(CoreIdentity.experimental ? "corepreview.game" : "game").\(digest.prefix(24))"
        plist.removeValue(forKey: "CFBundleDocumentTypes")
        try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0).write(to: plistURL, options: .atomic)
        // Resource edits invalidate the parent signature. Re-sign the complete local app.
        let signer = Process()
        signer.executableURL = URL(fileURLWithPath: "/usr/bin/codesign")
        signer.arguments = ["--force", "--deep", "--sign", "-", staging.path]
        let errors = Pipe()
        signer.standardError = errors
        try signer.run()
        signer.waitUntilExit()
        let diagnostics = String(data: errors.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        guard signer.terminationStatus == 0 else {
            throw ExportError(message: "Could not sign the exported app. \(diagnostics)")
        }
        try manager.moveItem(at: staging, to: destination)
    }
}
