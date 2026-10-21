// Appended to the player source by check-crispy-app.sh for private-state access.
extension PlayerWindowController {
    func verifyIndependentFaultExit() {
        start()
        RunLoop.main.run(until: Date().addingTimeInterval(0.35))
        precondition(paused && overlay.coreError != nil, "Unsupported core operation must pause and report an error")
        precondition(String(cString: studio_core_name(core)).hasPrefix("Crispy Core"))
        precondition(prepareToQuit(), "A faulted prototype must not trap the user in a cancelled quit")
        precondition(!FileManager.default.fileExists(atPath: slotURL(-1).path), "Faulted core must preserve the last valid recovery")
        if let window, let sheet = window.attachedSheet { window.endSheet(sheet); sheet.orderOut(nil) }
        window?.close()
        precondition(prepareToQuit(), "Closed prototype must not block termination")
        print("PASS: unsupported independent-core operation pauses safely, preserves valid recovery and allows quit")
    }
}
@main enum CoreFaultCheckMain {
    static func main() throws {
        let app = NSApplication.shared; app.setActivationPolicy(.accessory)
        let root = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("crispy-fault-\(UUID())")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        var rom = Data(repeating: 0, count: 32768)
        rom[0] = 0; rom[1] = 0; rom[2] = 0xff; rom[3] = 0xef; rom[0xb2] = 0x96
        let url = root.appendingPathComponent("unsupported.gba"); try rom.write(to: url)
        let player = try PlayerWindowController(romURL: url, title: "Independent core fault check", saveDirectory: root.appendingPathComponent("Saves"), settings: SessionSettings())
        player.verifyIndependentFaultExit()
    }
}
