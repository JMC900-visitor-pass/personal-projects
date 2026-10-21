// The check runner appends this file to PlayerWindowController.swift in build/ so
// the extension can inspect private state without adding production test APIs.
extension PlayerWindowController {
    func verifyOverlay() throws {
        func pump(_ seconds: Double) { RunLoop.main.run(until: Date().addingTimeInterval(seconds)) }
        precondition(overlay.settings.display.aspectLock == "native")
        start(); pump(0.2)
        precondition(frameNumber > 0)
        setOverlay(true); let halted = frameNumber; pump(0.35)
        precondition(frameNumber == halted && paused && overlay.visible)
        precondition(overlay.settings.display.aspectLock == "native", "Opening the overlay must not change aspect")
        let core = self.core!
        let count = Int(studio_width(core)*studio_height(core))
        let pixels = Array(UnsafeBufferPointer(start:studio_pixels(core),count:count))
        let before = saveDirectory.appendingPathComponent("before-gamma.mbs")
        precondition(studio_save_state(core,before.path))
        overlay.settings.display.colour.gamma = 1.7
        gameView.draw(); pump(0.05)
        precondition(Array(UnsafeBufferPointer(start:studio_pixels(core),count:count)) == pixels, "Post-render correction mutated core pixels")
        precondition(studio_load_state(core,before.path))
        precondition(overlay.settings.display.colour.gamma == 1.7, "Loading an older state must preserve the current look")
        let settingsURL = saveDirectory.appendingPathComponent("session.json")
        let disk = try Data(contentsOf:settingsURL)
        let settings = overlay.settings
        overlay.draftFill = 0.25; overlay.preview = true; togglePause()
        precondition(!overlay.preview && overlay.settings == settings)
        let afterCancel = try Data(contentsOf:settingsURL)
        precondition(afterCancel == disk, "Cancelling preview wrote settings")
        precondition(commitSlot(2)); precondition(frameNumber == halted)
        let meta = try JSONDecoder().decode(SlotMetadata.self,from:Data(contentsOf:slotURL(2).appendingPathExtension("json")))
        precondition(meta.frame == halted)
        setCompare(true); precondition(compareTexture != nil); setCompare(false)
        checkpointBattery()
        let checkpoint = saveDirectory.appendingPathComponent("battery-checkpoint.sav")
        let checkpointData = try Data(contentsOf:checkpoint)
        precondition(!checkpointData.isEmpty, "Use a ROM with battery RAM for this check")
        precondition(studio_restore_battery(core,checkpoint.path))
        // Inspect fade completion before the next timer advances the core.
        setOverlay(false); pump(0.4)
        precondition(!paused && !overlay.visible && frameNumber > halted)
        setOverlay(true); pump(0.3)
        precondition(prepareToQuit()); precondition(FileManager.default.fileExists(atPath:slotURL(-1).path) && overlay.hasRecovery)
        window?.close()
        precondition(prepareToQuit(), "Closed players must not prevent app termination")
        print("PASS: native aspect retained, frame-boundary halt, frozen core pixels under gamma changes, pre-gamma state loads, transactional preview cancel, slot metadata, A/B texture, battery restore, resume and quit recovery")
    }
}
@main enum PlayerVerificationMain {
    static func main() throws {
        let app = NSApplication.shared; app.setActivationPolicy(.accessory)
        let root = URL(fileURLWithPath:NSTemporaryDirectory()).appendingPathComponent("crispy-player-\(UUID())")
        try FileManager.default.createDirectory(at:root,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:root) }
        let player = try PlayerWindowController(romURL:URL(fileURLWithPath:CommandLine.arguments[1]), title:"Overlay verification", saveDirectory:root,settings:SessionSettings())
        try player.verifyOverlay()
    }
}
