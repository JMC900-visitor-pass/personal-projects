import Foundation

enum LibrarySearch {
    static func normalizedTitle(_ value: String) -> String {
        let cleaned = value.replacingOccurrences(of: #"\([^)]*\)|\[[^]]*\]"#, with: "", options: .regularExpression)
            .folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "en_US_POSIX"))
        return cleaned.components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { !$0.isEmpty && $0 != "the" }.joined(separator: " ")
    }
    static func matches(_ query: String, game: Game) -> Bool {
        let terms = normalizedTitle(query).split(separator: " ").map(String.init)
        let fields = [game.title, game.originalName ?? "", game.author ?? "", game.genre ?? ""]
        let words = fields.flatMap { normalizedTitle($0).split(separator: " ").map(String.init) }
        return terms.allSatisfy { term in
            words.contains { word in
                word.contains(term) || (term.count >= 4 && distance(term, word) <= (term.count >= 8 ? 2 : 1))
            }
        }
    }
    static func distance(_ first: String, _ second: String) -> Int {
        let firstLetters = Array(first), secondLetters = Array(second)
        var previous = Array(0...secondLetters.count)
        for (firstIndex, firstLetter) in firstLetters.enumerated() {
            var current = [firstIndex + 1]
            for (secondIndex, secondLetter) in secondLetters.enumerated() {
                current.append(min(current[secondIndex] + 1, previous[secondIndex + 1] + 1,
                                   previous[secondIndex] + (firstLetter == secondLetter ? 0 : 1)))
            }
            previous = current
        }
        return previous.last ?? firstLetters.count
    }
}
