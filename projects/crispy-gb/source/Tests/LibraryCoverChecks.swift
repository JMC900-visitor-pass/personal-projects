import Foundation
import AppKit

@main struct LibraryCoverChecks {
    @MainActor static func main() throws {
        let root = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("crispy-covers-\(UUID())")
        let fm = FileManager.default
        try fm.createDirectory(at: root,withIntermediateDirectories:true)
        defer { try? fm.removeItem(at:root) }
        let model = LibraryModel(root:root)
        var game = Game(id:"fixture",title:"Fixture",platform:"GB",fileExtension:"gb",originalName:"Fixture")
        model.games = [game]
        let folder = root.appendingPathComponent(game.id)
        try fm.createDirectory(at:folder,withIntermediateDirectories:true)
        let rom = folder.appendingPathComponent("game.gb")
        try Data(repeating:0,count:1024).write(to:rom)
        precondition(model.coverStatus(game) == .missing)
        game.coverFile = "cover.png"; game.sourceURL = "https://github.com/libretro-thumbnails/Nintendo_-_Game_Boy/blob/master/Named_Boxarts/Fixture.png"
        precondition(model.coverStatus(game) == .missing) // path metadata alone is not cached artwork
        try Data([1,2,3]).write(to:folder.appendingPathComponent("cover.png"))
        game.coverIdentity = model.artworkIdentity(game)
        precondition(model.coverStatus(game) == .covers)
        var changed = game; changed.originalName = "Renamed"
        precondition(model.coverStatus(changed) == .stale)
        precondition(model.matchesCover(changed,filter:.covers))
        var data = try Data(contentsOf:rom); data[0x134] = 65; try data.write(to:rom)
        precondition(model.coverStatus(game) == .stale)
        game.coverIdentity = model.artworkIdentity(game); model.games = [game]
        var session = SessionSettings(); session.display.colour = .crispy
        session.controls.overrides = ["A":"kb.z"]
        model.updateSession(session,for:game.id); model.coverFilter = .missing
        let restored = LibraryModel(root:root)
        precondition(restored.error == nil && restored.coverFilter == .missing)
        precondition(restored.games[0].display?.colour == .crispy && restored.games[0].controls?.overrides["A"] == "kb.z")
        model.removeCover(game)
        precondition(model.coverStatus(model.games[0]) == .missing && model.error == nil)
        // Old array indexes still load with all newly added properties absent.
        var old = try JSONSerialization.jsonObject(with:JSONEncoder().encode(game)) as! [String:Any]
        for key in ["display","controls","coverIdentity"] { old.removeValue(forKey:key) }
        try JSONSerialization.data(withJSONObject:[old]).write(to:root.appendingPathComponent("library.json"))
        let legacy = LibraryModel(root:root)
        precondition(legacy.error == nil && legacy.games.count == 1 && legacy.games[0].display == nil && legacy.coverFilter == .all)
        print("PASS: cached-file existence, stale filename/header, covers includes stale, per-ROM display/controls persistence, filter persistence, cover removal, legacy array migration")
    }
}
