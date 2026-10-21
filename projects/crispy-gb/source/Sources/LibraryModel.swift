import SwiftUI
import AppKit
import CryptoKit
import UniformTypeIdentifiers

struct Game: Identifiable, Codable, Hashable {
    var id: String
    var title: String
    var platform: String
    var fileExtension: String
    var importedAt: Date = Date()
    var lastPlayed: Date?
    var favorite: Bool = false
    var coverFile: String?
    var sourceURL: String?
    var summary: String?
    var metadataTitle: String?
    var metadataSourceURL: String?
    var hidden: Bool?
    var author: String?
    var genre: String?
    var originalName: String?
    var display: DisplaySettings?
    var controls: ControlSettings?
    var coverIdentity: String?
}
struct CoverCandidate: Identifiable {
    var id: Int
    var title: String
    var imageURL: URL?
    var pageURL: URL
    var summary: String?
}
enum CoverStatus: String, CaseIterable, Codable { case all = "All", covers = "✓ Covers", missing = "✗ No cover", stale = "⚠ Stale" }
private struct LibraryIndex: Codable {
    var games: [Game]; var coverFilter: CoverStatus = .all
    init(games: [Game], coverFilter: CoverStatus) { self.games = games; self.coverFilter = coverFilter }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        games = try c.decode([Game].self, forKey: .games)
        coverFilter = try c.decodeIfPresent(CoverStatus.self, forKey: .coverFilter) ?? .all
    }
}
@MainActor final class LibraryModel: ObservableObject {
    @Published var games: [Game] = []
    @Published var coverFilter: CoverStatus = .all { didSet { persist() } }
    @Published var fetchingMissing = false
    @Published var coverProgress = 0.0
    @Published var coverBanner = ""
    @Published var busy = false
    @Published var status = ""
    @Published var error: String?
    @Published var removals: [RemovedGame] = []
    private let covers = CoverProjectClient()
    private let libretro = LibretroArtwork()
    var artworkProvider: String { UserDefaults.standard.string(forKey: "CrispyGB.Artwork") ?? "Libretro" }
    private var coverRequests: Set<String> = []
    private var attemptedCovers: Set<String> = []
    private var identityCache: [String: (stamp: String, hash: String)] = [:]
    struct RemovedGame: Identifiable {
        let id = UUID()
        let game: Game
        let trashURL: URL
        let index: Int
    }
    let root: URL
    init(root: URL? = nil) {
        self.root = root ?? (ProcessInfo.processInfo.environment["CRISPY_GB_LIBRARY_ROOT"] ?? ProcessInfo.processInfo.environment["CRISP_GB_LIBRARY_ROOT"] ?? ProcessInfo.processInfo.environment["MGBA_STUDIO_LIBRARY_ROOT"]).map { URL(fileURLWithPath: $0, isDirectory: true) } ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent(CoreIdentity.libraryFolder, isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: self.root, withIntermediateDirectories: true)
            let index = self.root.appendingPathComponent("library.json")
            if FileManager.default.fileExists(atPath: index.path) {
                let data = try Data(contentsOf: index)
                if let legacy = try? JSONDecoder().decode([Game].self, from: data) {
                    games = legacy
                    let backup = self.root.appendingPathComponent("library-v1.backup.json")
                    if !FileManager.default.fileExists(atPath: backup.path) { try data.write(to: backup, options: .atomic) }
                }
                else { let saved = try JSONDecoder().decode(LibraryIndex.self, from: data); games = saved.games; coverFilter = saved.coverFilter }
            }
        } catch { self.error = "Could not load library: \(error.localizedDescription)" }
        var migrated = false
        for index in games.indices where games[index].coverIdentity == nil && coverURL(for: games[index]) != nil {
            games[index].coverIdentity = artworkIdentity(games[index]); migrated = true
        }
        if migrated { persist() }
    }
    func romURL(for game: Game) -> URL { root.appendingPathComponent(game.id).appendingPathComponent("game.\(game.fileExtension)") }
    func coverURL(for game: Game) -> URL? {
        guard let source = game.sourceURL.flatMap(URL.init(string:)), CoverProjectClient.isProviderURL(source) || LibretroArtwork.isSourceURL(source) else { return nil }
        guard let file = game.coverFile, file == URL(fileURLWithPath: file).lastPathComponent else { return nil }
        let url = root.appendingPathComponent(game.id).appendingPathComponent(file)
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }
    func artworkIdentity(_ game: Game) -> String {
        let name = game.originalName ?? game.title
        let url = romURL(for: game)
        let attributes = try? FileManager.default.attributesOfItem(atPath: url.path)
        let stamp = name + "|" + url.path + "|" + String((attributes?[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0) + "|" + String(describing: attributes?[.size])
        if let cached = identityCache[game.id], cached.stamp == stamp { return cached.hash }
        var header = Data()
        if let handle = try? FileHandle(forReadingFrom: url) {
            defer { try? handle.close() }
            let offset: UInt64 = game.platform == "GBA" ? 0xA0 : 0x100
            try? handle.seek(toOffset: offset)
            header = (try? handle.read(upToCount: game.platform == "GBA" ? 32 : 80)) ?? Data()
        }
        let hash = SHA256.hash(data: Data((name + "\n" + url.lastPathComponent + "\n").utf8) + header).map { String(format: "%02x", $0) }.joined()
        identityCache[game.id] = (stamp, hash); return hash
    }
    func coverStatus(_ game: Game) -> CoverStatus {
        guard coverURL(for: game) != nil else { return .missing }
        return game.coverIdentity.map { $0 != artworkIdentity(game) } == true ? .stale : .covers
    }
    func matchesCover(_ game: Game, filter: CoverStatus) -> Bool {
        if filter == .all { return true }
        let status = coverStatus(game)
        return filter == .covers ? status == .covers || status == .stale : status == filter
    }
    func removeCover(_ game: Game) {
        guard var current = games.first(where: { $0.id == game.id }) else { return }
        do {
            if let url = coverURL(for: current) { try FileManager.default.removeItem(at: url) }
            current.coverFile = nil; current.coverIdentity = nil; current.sourceURL = nil
            attemptedCovers.insert("\(artworkProvider)-\(game.id)")
            update(current)
        } catch { self.error = error.localizedDescription }
    }
    func updateSession(_ settings: SessionSettings, for id: String) {
        guard var game = games.first(where: { $0.id == id }) else { return }
        game.display = settings.display; game.controls = settings.controls; update(game)
    }
    func fetchMissing(_ titles: [Game]) {
        guard !fetchingMissing else { return }
        fetchingMissing = true; coverProgress = 0; coverBanner = "Fetching missing covers from Libretro…"
        Task {
            var failed = 0
            for (index, game) in titles.enumerated() {
                do {
                    let names = [game.originalName ?? game.title, romHeaderTitle(for: game) ?? ""]
                    var found = false
                    for name in names where !name.isEmpty {
                        let candidates = try await libretro.search(name, platform: game.platform)
                        if let match = candidates.first(where: { LibretroArtwork.isAutomaticMatch(name, title: $0.title) }) {
                            try await applyCandidate(match, to: game); found = true; break
                        }
                    }
                    if !found { failed += 1 }
                } catch { failed += 1 }
                coverProgress = Double(index + 1) / Double(max(1, titles.count))
            }
            fetchingMissing = false
            coverBanner = failed == 0 ? "Covers fetched." : "\(failed) titles still have no cover. No confident match, offline access or provider limits may prevent a download. Retry later."
        }
    }
    func saveDirectory(for game: Game) -> URL {
        let url = root.appendingPathComponent(game.id).appendingPathComponent("Saves", isDirectory: true)
        do { try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true) } catch { self.error = error.localizedDescription }
        return url
    }
    func persist() { do { try JSONEncoder().encode(LibraryIndex(games: games, coverFilter: coverFilter)).write(to: root.appendingPathComponent("library.json"), options: .atomic) } catch { self.error = error.localizedDescription } }
    func update(_ game: Game) { if let i = games.firstIndex(where: {$0.id == game.id}) { games[i] = game; persist() } }
    func recordPlayed(_ game: Game) { var g = games.first(where: {$0.id == game.id}) ?? game; g.lastPlayed = Date(); update(g) }
    func toggleFavorite(_ game: Game) { var g = game; g.favorite.toggle(); update(g) }
    func toggleHidden(_ game: Game) { var current = games.first(where: { $0.id == game.id }) ?? game; current.hidden = !(current.hidden ?? false); update(current) }
    func remove(_ game: Game) {
        guard let index = games.firstIndex(where: { $0.id == game.id }) else { return }
        var trashURL: NSURL?
        do {
            try FileManager.default.trashItem(at: root.appendingPathComponent(game.id), resultingItemURL: &trashURL)
            guard let trashURL else { throw CocoaError(.fileWriteUnknown) }
            let removal = RemovedGame(game: games[index], trashURL: trashURL as URL, index: index)
            games.remove(at: index); persist(); removals.append(removal)
            Task { try? await Task.sleep(for: .seconds(5)); removals.removeAll { $0.id == removal.id } }
        } catch { self.error = "Could not remove game: \(error.localizedDescription)" }
    }
    func undoRemoval(_ removal: RemovedGame) {
        do {
            guard !games.contains(where: { $0.id == removal.game.id }) else { throw CocoaError(.fileWriteFileExists) }
            try FileManager.default.moveItem(at: removal.trashURL, to: root.appendingPathComponent(removal.game.id))
            games.insert(removal.game, at: min(removal.index, games.count)); persist()
            removals.removeAll { $0.id == removal.id }
        } catch { self.error = "Could not restore game: \(error.localizedDescription)" }
    }
    func chooseROMs() {
        let panel = NSOpenPanel(); panel.allowsMultipleSelection = true; panel.canChooseDirectories = true; panel.canChooseFiles = true
        panel.allowedContentTypes = ["gb", "gbc", "gba"].compactMap { UTType(filenameExtension: $0) }
        panel.message = "Import Game Boy, Game Boy Color or Game Boy Advance ROMs and folders."
        if let path = UserDefaults.standard.string(forKey: "CrispyGB.ImportPath") { panel.directoryURL = URL(fileURLWithPath: path) }
        if panel.runModal() == .OK {
            if let first = panel.urls.first { UserDefaults.standard.set(first.deletingLastPathComponent().path, forKey: "CrispyGB.ImportPath") }
            importURLs(panel.urls)
        }
    }
    func importURLs(_ urls: [URL]) {
        guard !busy else { return }; busy = true; status = "Importing ROMs…"
        let destination = root
        let knownIDs = Set(games.map(\.id))
        Task {
          let result = await Task.detached(priority: .userInitiated) {
            var imported: [Game] = []; var seen = knownIDs
            var duplicates = 0; var failures: [String] = []
            for url in urls {
                let scoped = url.startAccessingSecurityScopedResource(); defer { if scoped { url.stopAccessingSecurityScopedResource() } }
                var files: [URL] = []
                let values = try? url.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
                if values?.isSymbolicLink == true { continue }
                if values?.isDirectory == true {
                    if let enumerator = FileManager.default.enumerator(at: url, includingPropertiesForKeys: [.isRegularFileKey,.isSymbolicLinkKey], options: [.skipsHiddenFiles, .skipsPackageDescendants]) {
                        while let file = enumerator.nextObject() as? URL { let v = try? file.resourceValues(forKeys: [.isSymbolicLinkKey,.isRegularFileKey]); if v?.isSymbolicLink == true { enumerator.skipDescendants(); continue }; if v?.isRegularFile == true { files.append(file) } }
                    }
                } else { files = [url] }
                for file in files where ["gb","gbc","gba"].contains(file.pathExtension.lowercased()) {
                    do {
                        let data = try Data(contentsOf: file, options: .mappedIfSafe)
                        guard data.count >= 0x150 else { throw NSError(domain: "Import", code: 1, userInfo: [NSLocalizedDescriptionKey: "File is too small to be a ROM."]) }
                        let hash = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
                        if seen.contains(hash) { duplicates += 1; continue }
                        let ext = file.pathExtension.lowercased(); let dir = destination.appendingPathComponent(hash)
                        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
                        try data.write(to: dir.appendingPathComponent("game.\(ext)"), options: .atomic)
                        imported.append(Game(id: hash, title: file.deletingPathExtension().lastPathComponent, platform: ext.uppercased(), fileExtension: ext, originalName: file.deletingPathExtension().lastPathComponent)); seen.insert(hash)
                    } catch { failures.append("\(file.lastPathComponent): \(error.localizedDescription)") }

                }
            }
            return (imported, duplicates, failures)
          }.value
            games.append(contentsOf: result.0)
            persist(); busy = false; status = "Imported \(result.0.count) game\(result.0.count == 1 ? "" : "s") · \(result.1) already in library"
            if !result.2.isEmpty { error = result.2.joined(separator: "\n") }
            for game in result.0 { await fetchCover(for: game) }
        }
    }
    func fetchCover(for game: Game, retry: Bool = false) async {
        let requestID = "\(artworkProvider)-\(game.id)"
        guard ["GB", "GBC", "GBA"].contains(game.platform), !coverRequests.contains(game.id),
              retry || !attemptedCovers.contains(requestID),
              retry || coverURL(for: game) == nil else { return }
        coverRequests.insert(game.id)
        attemptedCovers.insert(requestID)
        defer { coverRequests.remove(game.id) }
        do {
            let name = game.originalName ?? game.title
            var names = [name]
            if artworkProvider == "Libretro", let header = romHeaderTitle(for: game), header != name { names.append(header) }
            for query in names {
                let candidates = try await searchCovers(query, platform: game.platform)
                guard let candidate = candidates.first else { continue }
                let matches = LibretroArtwork.isSourceURL(candidate.pageURL) ? LibretroArtwork.isAutomaticMatch(query, title: candidate.title) : LibrarySearch.normalizedTitle(candidate.title) == LibrarySearch.normalizedTitle(query)
                if matches { try await applyCandidate(candidate, to: game); return }
            }
        } catch {
            if retry { status = "Cover lookup unavailable; showing a cartridge placeholder." }
        }
    }
    func searchCovers(_ query: String, platform: String) async throws -> [CoverCandidate] {
        if artworkProvider == "Libretro" { return try await libretro.search(query, platform: platform) }
        return try await covers.search(query, platform: platform)
    }
    private func romHeaderTitle(for game: Game) -> String? {
        guard let handle = try? FileHandle(forReadingFrom: romURL(for: game)) else { return nil }
        defer { try? handle.close() }
        let offset: UInt64 = game.platform == "GBA" ? 0xA0 : 0x134
        let count = game.platform == "GBA" ? 12 : game.platform == "GBC" ? 11 : 16
        do {
            try handle.seek(toOffset: offset)
            guard let data = try handle.read(upToCount: count), let title = String(data: data.prefix { $0 != 0 }, encoding: .ascii) else { return nil }
            let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        } catch { return nil }
    }
    func applyCandidate(_ candidate: CoverCandidate, to game: Game) async throws {
        guard let imageURL = candidate.imageURL else { return }
        let identity = artworkIdentity(game)
        let data = LibretroArtwork.isSourceURL(candidate.pageURL) ? try await libretro.image(at: imageURL) : try await covers.image(at: imageURL)
        guard let image = NSImage(data: data), let tiff = image.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff),
              let png = bitmap.representation(using: .png, properties: [:]) else { throw CocoaError(.fileReadCorruptFile) }
        guard var current = games.first(where: { $0.id == game.id }) else { return }
        try png.write(to: root.appendingPathComponent(game.id).appendingPathComponent("cover.png"), options: .atomic)
        current.coverFile = "cover.png"
        current.sourceURL = candidate.pageURL.absoluteString
        current.coverIdentity = identity
        update(current)
    }
}
