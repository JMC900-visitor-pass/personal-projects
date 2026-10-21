import Foundation

private actor ArtworkRateLimiter {
    static let shared = ArtworkRateLimiter()
    private var next = Date.distantPast
    func wait() async throws {
        while next > Date() { try await Task.sleep(for: .seconds(next.timeIntervalSinceNow)) }
        next = Date().addingTimeInterval(0.2)
    }
}
actor LibretroArtwork {
    private struct Tree: Decodable {
        let tree: [Entry]
        let truncated: Bool
        struct Entry: Decodable { let path: String; let type: String; let sha: String }
    }
    private var catalogs: [String: [String]] = [:]
    private var requests: [String: Task<[String], Error>] = [:]
    private static let repositories = ["GB": "Nintendo_-_Game_Boy", "GBC": "Nintendo_-_Game_Boy_Color", "GBA": "Nintendo_-_Game_Boy_Advance"]
    nonisolated static func isSourceURL(_ url: URL) -> Bool {
        guard url.scheme == "https", url.host == "github.com" else { return false }
        let components = url.pathComponents
        return components.count > 3 && components[1] == "libretro-thumbnails" && repositories.values.contains(components[2])
    }
    private static func isDownloadURL(_ url: URL) -> Bool {
        guard url.scheme == "https" else { return false }
        let components = url.pathComponents
        if url.host == "raw.githubusercontent.com" {
            return components.count > 4 && components[1] == "libretro-thumbnails" && repositories.values.contains(components[2]) && components[4] == "Named_Boxarts"
        }
        return url.host == "api.github.com" && components.count > 4 && components[1] == "repos" && components[2] == "libretro-thumbnails" && repositories.values.contains(components[3])
    }
    private static func download(_ url: URL) async throws -> Data {
        guard isDownloadURL(url) else { throw URLError(.unsupportedURL) }
        try await ArtworkRateLimiter.shared.wait()
        var request = URLRequest(url: url); request.timeoutInterval = 30
        request.setValue("CrispyGB/1.0", forHTTPHeaderField: "User-Agent")
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let response = response as? HTTPURLResponse, response.statusCode == 200,
              let finalURL = response.url, isDownloadURL(finalURL), data.count < 20_000_000 else { throw URLError(.badServerResponse) }
        return data
    }
    private func catalog(_ repository: String) async throws -> [String] {
        if let cached = catalogs[repository] { return cached }
        if let pending = requests[repository] { return try await pending.value }
        let cacheDirectory = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("Crispy GB/ArtworkCatalog", isDirectory: true)
        let cacheURL = cacheDirectory.appendingPathComponent("\(repository).json")
        if let attributes = try? FileManager.default.attributesOfItem(atPath: cacheURL.path),
           let modified = attributes[.modificationDate] as? Date, Date().timeIntervalSince(modified) < 86400,
           let data = try? Data(contentsOf: cacheURL), let cached = try? JSONDecoder().decode([String].self, from: data) {
            catalogs[repository] = cached; return cached
        }
        let pending = Task {
            let root = URL(string: "https://api.github.com/repos/libretro-thumbnails/\(repository)/git/trees/master")!
            let tree = try JSONDecoder().decode(Tree.self, from: await Self.download(root))
            guard let boxarts = tree.tree.first(where: { $0.path == "Named_Boxarts" && $0.type == "tree" }) else { throw URLError(.cannotParseResponse) }
            let url = root.deletingLastPathComponent().appendingPathComponent(boxarts.sha)
            let result = try JSONDecoder().decode(Tree.self, from: await Self.download(url))
            guard !result.truncated else { throw URLError(.cannotParseResponse) }
            return result.tree.filter { $0.type == "blob" && $0.path.lowercased().hasSuffix(".png") }.map { "Named_Boxarts/" + $0.path }.sorted()
        }
        requests[repository] = pending
        defer { requests[repository] = nil }
        let result = try await pending.value; catalogs[repository] = result
        try? FileManager.default.createDirectory(at: cacheDirectory, withIntermediateDirectories: true)
        if let data = try? JSONEncoder().encode(result) { try? data.write(to: cacheURL, options: .atomic) }
        return result
    }
    nonisolated static func normalized(_ title: String) -> String {
        LibrarySearch.normalizedTitle(title).split(separator: " ").filter { $0 != "version" }.joined(separator: " ")
    }
    nonisolated static func isAutomaticMatch(_ query: String, title: String) -> Bool { normalized(query) == normalized(title) }
    func search(_ query: String, platform: String) async throws -> [CoverCandidate] {
        guard let repository = Self.repositories[platform] else { return [] }
        let queryName = Self.normalized(query)
        guard !queryName.isEmpty else { return [] }
        let paths = try await catalog(repository)
        let matches = paths.filter { path in
            let title = URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent
            let name = Self.normalized(title)
            return name == queryName || name.contains(queryName)
        }.sorted { first, second in
            let firstName = URL(fileURLWithPath: first).deletingPathExtension().lastPathComponent
            let secondName = URL(fileURLWithPath: second).deletingPathExtension().lastPathComponent
            let firstExact = Self.isAutomaticMatch(query, title: firstName), secondExact = Self.isAutomaticMatch(query, title: secondName)
            if firstExact != secondExact { return firstExact }
            let firstUSA = first.contains("USA"), secondUSA = second.contains("USA")
            return firstUSA != secondUSA ? firstUSA : first < second
        }
        return matches.prefix(20).enumerated().map { index, path in
            let title = URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent
            let source = URL(string: "https://github.com/libretro-thumbnails/\(repository)/blob/master")!.appendingPathComponent(path)
            let image = URL(string: "https://raw.githubusercontent.com/libretro-thumbnails/\(repository)/master")!.appendingPathComponent(path)
            return CoverCandidate(id: index, title: title, imageURL: image, pageURL: source, summary: nil)
        }
    }
    func image(at url: URL) async throws -> Data { try await Self.download(url) }
}
