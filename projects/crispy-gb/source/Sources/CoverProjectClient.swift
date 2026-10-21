import Foundation

final class CoverProjectRedirects: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(request.url.map(CoverProjectClient.isAllowedURL) == true ? request : nil)
    }
}

actor CoverProjectClient {
    private var catalog: [String: [(String, URL)]] = [:]
    private let session = URLSession(configuration: .ephemeral, delegate: CoverProjectRedirects(), delegateQueue: nil)
    nonisolated static func isProviderURL(_ url: URL) -> Bool {
        url.scheme == "https" && ["www.thecoverproject.net", "thecoverproject.net"].contains(url.host?.lowercased() ?? "")
    }
    nonisolated static func isAllowedURL(_ url: URL) -> Bool {
        isProviderURL(url) || (url.scheme == "https" && url.host == "coverproject.sfo2.cdn.digitaloceanspaces.com")
    }
    private func download(_ url: URL) async throws -> Data {
        guard Self.isAllowedURL(url) else { throw URLError(.unsupportedURL) }
        var request = URLRequest(url: url)
        request.timeoutInterval = 15
        request.setValue("CrispyGB/1.0 (local ROM library; cover lookup)", forHTTPHeaderField: "User-Agent")
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse, response.statusCode == 200,
              let finalURL = response.url, Self.isAllowedURL(finalURL), data.count <= 20_000_000 else { throw URLError(.badServerResponse) }
        return data
    }
    func image(at url: URL) async throws -> Data { try await download(url) }
    private func html(at url: URL) async throws -> String {
        let data = try await download(url)
        guard let text = String(data: data, encoding: .utf8) ?? String(data: data, encoding: .isoLatin1) else { throw URLError(.cannotDecodeContentData) }
        return text
    }
    static func captures(_ pattern: String, in text: String) -> [[String]] {
        guard let expression = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive, .dotMatchesLineSeparators]) else { return [] }
        return expression.matches(in: text, range: NSRange(text.startIndex..., in: text)).map { match in
            (1..<match.numberOfRanges).map { index in Range(match.range(at: index), in: text).map { String(text[$0]) } ?? "" }
        }
    }
    static func plainText(_ text: String) -> String {
        var result = text.replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression)
        for (encoded, decoded) in [("&amp;", "&"), ("&#039;", "'"), ("&#39;", "'"), ("&quot;", "\""), ("&nbsp;", " "), ("&lt;", "<"), ("&gt;", ">"), ("&apos;", "'")] {
            result = result.replacingOccurrences(of: encoded, with: decoded)
        }
        return result.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    func search(_ query: String, platform: String) async throws -> [CoverCandidate] {
        guard let category = ["GB": 12, "GBC": 14, "GBA": 13][platform] else { return [] }
        let normalized = LibrarySearch.normalizedTitle(query)
        guard let initial = normalized.first else { return [] }
        let letter = initial.isLetter && initial.isASCII ? String(initial) : "0"
        let key = "\(category)-\(letter)"
        if catalog[key] == nil {
            var entries: [URL: String] = [:]
            var next: URL? = URL(string: "https://www.thecoverproject.net/view.php?cat_id=\(category)&view=\(letter)")
            var visited: Set<URL> = []
            while let page = next, visited.count < 12, !visited.contains(page) {
                visited.insert(page)
                let content = try await html(at: page)
                let links = Self.captures(#"<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>"#, in: content)
                next = nil
                for link in links {
                    guard let url = URL(string: Self.plainText(link[0]), relativeTo: page)?.absoluteURL, Self.isProviderURL(url) else { continue }
                    let items = URLComponents(url: url, resolvingAgainstBaseURL: true)?.queryItems ?? []
                    let title = Self.plainText(link[1]).replacingOccurrences(of: #"\s*\(\d+\)\s*$"#, with: "", options: .regularExpression)
                    if items.contains(where: { $0.name == "game_id" }), !title.isEmpty { entries[url] = title }
                    if ["›", "Next", "»"].contains(title), items.contains(where: { $0.name == "cat_id" && $0.value == String(category) }), !visited.contains(url) { next = url }
                }
            }
            catalog[key] = entries.map { ($0.value, $0.key) }
        }
        let ranked = (catalog[key] ?? []).filter { title, _ in
            let candidate = LibrarySearch.normalizedTitle(title)
            return candidate == normalized || candidate.contains(normalized) || normalized.contains(candidate)
        }.sorted { first, second in
            let firstExact = LibrarySearch.normalizedTitle(first.0) == normalized
            let secondExact = LibrarySearch.normalizedTitle(second.0) == normalized
            return firstExact != secondExact ? firstExact : first.0 < second.0
        }
        var results: [CoverCandidate] = []
        for (title, page) in ranked.prefix(6) {
            let content = try await html(at: page)
            let images = Self.captures(#"<img\b[^>]*src\s*=\s*["']([^"']+)["']"#, in: content)
            let image = images.compactMap { URL(string: Self.plainText($0[0]), relativeTo: page)?.absoluteURL }
                .first { Self.isAllowedURL($0) && ($0.path.contains("_thumb.") || $0.path.contains("/covers/")) }
            let identifier = URLComponents(url: page, resolvingAgainstBaseURL: true)?.queryItems?.first { $0.name == "game_id" }?.value.flatMap(Int.init)
            if let identifier, let image { results.append(CoverCandidate(id: identifier, title: title, imageURL: image, pageURL: page, summary: nil)) }
        }
        return results
    }
}
