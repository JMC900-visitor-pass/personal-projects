import Foundation
// Separate app/bundle and data namespace during independent-engine development.
enum CoreIdentity {
    static var experimental: Bool { Bundle.main.object(forInfoDictionaryKey: "CrispyCoreBackend") as? String == "crispy" }
    static var applicationName: String { experimental ? "Crispy Core Preview" : "Crispy GB" }
    static var libraryFolder: String { experimental ? "Crispy Core Preview/Library" : "mGBA Studio/Library" }
    static func saveDirectory(_ base: URL) -> URL { experimental ? base.appendingPathComponent("CrispyCore-v1", isDirectory: true) : base }
}
