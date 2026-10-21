import AppKit
import SwiftUI
import CryptoKit

@MainActor final class StudioAppDelegate: NSObject, NSApplicationDelegate {
    private let model = LibraryModel()
    private var libraryWindow: NSWindow?
    private var players: [String: PlayerWindowController] = [:]
    private let embedded = EmbeddedGame.current()
    private var exportInProgress = false
    private var searchMonitor: Any?
    private var libraryObserver: NSObjectProtocol?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.appearance = NSAppearance(named: UserDefaults.standard.string(forKey: "CrispyGB.Theme") == "Light" ? .aqua : .darkAqua)
        installMenu()
        libraryObserver = NotificationCenter.default.addObserver(forName: Notification.Name("CrispyGB.ShowLibrary"), object: nil, queue: .main) { [weak self] _ in Task { @MainActor in self?.showLibrary() } }
        searchMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            let controlSearch = event.modifierFlags.intersection(.deviceIndependentFlagsMask).contains(.control) && event.charactersIgnoringModifiers?.lowercased() == "k"
            let slashSearch = event.characters == "/" && !(NSApp.keyWindow?.firstResponder is NSTextView)
            guard controlSearch || slashSearch else { return event }
            self?.showLibrary()
            NotificationCenter.default.post(name: Notification.Name("CrispyGB.FocusSearch"), object: nil)
            return nil
        }
        let arguments = CommandLine.arguments
        if let exportIndex = arguments.firstIndex(of: "--export"), arguments.indices.contains(exportIndex + 1),
           let outputIndex = arguments.firstIndex(of: "--output"), arguments.indices.contains(outputIndex + 1) {
            let rom = URL(fileURLWithPath: arguments[exportIndex + 1])
            do {
                try StandaloneExporter.export(title: rom.deletingPathExtension().lastPathComponent, romURL: rom, coverURL: nil, to: URL(fileURLWithPath: arguments[outputIndex + 1]))
                print("EXPORT_OK"); exit(0)
            } catch { fputs("EXPORT_ERROR: \(error.localizedDescription)\n", stderr); exit(1) }
        }
        if let (game, url) = embedded {
            openPlayer(romURL: url, title: game.title, saveDirectory: game.saveDirectory)
        } else if let playIndex = arguments.firstIndex(of: "--play"), arguments.indices.contains(playIndex + 1) {
            openDirect(URL(fileURLWithPath: arguments[playIndex + 1]))
        } else {
            showLibrary()
        }
        if let index = arguments.firstIndex(of: "--smoke-seconds"), arguments.indices.contains(index + 1), let seconds = Double(arguments[index + 1]) {
            DispatchQueue.main.asyncAfter(deadline: .now() + max(1, seconds)) { NSApp.terminate(nil) }
        }
        NSApp.activate(ignoringOtherApps: true)
    }

    func application(_ sender: NSApplication, openFiles filenames: [String]) {
        showLibrary()
        model.importURLs(filenames.map { URL(fileURLWithPath: $0) })
        sender.reply(toOpenOrPrint: .success)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { embedded != nil }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if exportInProgress {
            let alert = NSAlert(); alert.messageText = "An app is being exported"; alert.informativeText = "Let the export finish before quitting."; alert.runModal()
            return .terminateCancel
        }
        for player in players.values { if !player.prepareToQuit() { return .terminateCancel } }
        for player in players.values { player.window?.close() }
        return .terminateNow
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { showLibrary() }
        return true
    }

    @objc func showLibrary() {
        if libraryWindow == nil {
            let view = LibraryView(model: model, onPlay: { [weak self] game in self?.play(game) }, onExport: { [weak self] game in self?.export(game) }, onRemove: { [weak self] game in self?.remove(game) })
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1220, height: 780), styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
            window.title = CoreIdentity.applicationName
            window.titlebarAppearsTransparent = true
            window.minSize = NSSize(width: 880, height: 600)
            window.isReleasedWhenClosed = false
            window.contentView = NSHostingView(rootView: view)
            window.center()
            libraryWindow = window
        }
        libraryWindow?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func play(_ game: Game) {
        if openPlayer(romURL: model.romURL(for: game), title: game.title, saveDirectory: model.saveDirectory(for: game)) { model.recordPlayed(game) }
    }
    private func remove(_ game: Game) {
        let key = model.romURL(for: game).standardizedFileURL.path
        players[key]?.window?.close()
        players.removeValue(forKey: key)
        model.remove(game)
    }
    private func openDirect(_ rom: URL) {
        do {
            let hash = SHA256.hash(data: try Data(contentsOf: rom, options: .mappedIfSafe)).map { String(format: "%02x", $0) }.joined()
            let saves = model.root.deletingLastPathComponent().appendingPathComponent("Direct/\(hash)", isDirectory: true)
            openPlayer(romURL: rom, title: rom.deletingPathExtension().lastPathComponent, saveDirectory: saves)
        } catch { showError(error) }
    }
    @discardableResult private func openPlayer(romURL: URL, title: String, saveDirectory: URL) -> Bool {
        let key = romURL.standardizedFileURL.path
        if let current = players[key], current.window?.isVisible == true { current.showWindow(nil); current.window?.makeKeyAndOrderFront(nil); return true }
        do {
            let game = model.games.first(where: { model.romURL(for: $0).standardizedFileURL == romURL.standardizedFileURL })
            let settings = game.map { SessionSettings(display: $0.display ?? DisplaySettings(), controls: $0.controls ?? ControlSettings()) }
            let player = try PlayerWindowController(romURL: romURL, title: title, saveDirectory: saveDirectory, settings: settings, persist: { [weak self] settings in
                if let id = game?.id { self?.model.updateSession(settings, for: id) }
            })
            players[key] = player
            player.start()
            return true
        } catch { showError(error); return false }
    }

    private func export(_ game: Game) {
        guard !exportInProgress else { return }
        let panel = NSSavePanel()
        let safeTitle = game.title.replacingOccurrences(of: "/", with: "-").replacingOccurrences(of: ":", with: "-")
        panel.title = "Export Standalone Game"
        panel.message = "Creates a self-contained app for Apple silicon Macs. Saved games are stored separately in Application Support."
        panel.nameFieldStringValue = "\(safeTitle.isEmpty ? "My Game" : safeTitle).app"
        panel.canCreateDirectories = true
        guard panel.runModal() == .OK, let chosen = panel.url else { return }
        let destination = chosen.pathExtension == "app" ? chosen : chosen.appendingPathExtension("app")
        let romURL = model.romURL(for: game), coverURL = model.coverURL(for: game), title = game.title
        exportInProgress = true
        model.status = "Exporting \(title)…"
        Task {
            do {
                try await Task.detached(priority: .userInitiated) { try StandaloneExporter.export(title: title, romURL: romURL, coverURL: coverURL, to: destination) }.value
                model.status = "Exported \(destination.lastPathComponent)"
                NSWorkspace.shared.activateFileViewerSelecting([destination])
            } catch { showError(error) }
            exportInProgress = false
        }
    }

    private func showError(_ error: Error) {
        if CommandLine.arguments.contains("--smoke-seconds") { fputs("STUDIO_ERROR: \(error.localizedDescription)\n", stderr); exit(1) }
        let alert = NSAlert(error: error)
        alert.runModal()
    }
    @objc private func importROMs() { showLibrary(); model.chooseROMs() }
    @objc private func showSettings() { showLibrary(); NotificationCenter.default.post(name: Notification.Name("CrispyGB.Settings"), object: nil) }
    @objc private func showAbout() {
        if CoreIdentity.experimental {
            NSApp.orderFrontStandardAboutPanel(options: [.applicationName: CoreIdentity.applicationName, .applicationVersion: "0.1 · independent C++ core prototype", .credits: NSAttributedString(string: "Independent GB/GBC/GBA core bring-up.\nNative macOS frontend, Metal display and controls.\n\nCompatibility, sound and hardware accuracy are incomplete.\nSee the included core development notes and original demo ROMs.")])
            return
        }
        NSApp.orderFrontStandardAboutPanel(options: [.applicationName: "Crispy GB", .applicationVersion: "1.0 · mGBA 0.10.5", .credits: NSAttributedString(string: "A native library and player powered by mGBA.\nGame Boy · Game Boy Color · Game Boy Advance\n\nmGBA © Jeffrey Pfau and contributors.\nLicensed under MPL 2.0. Source and notices are included in the app.")])
    }
    @objc private func showCoreDemos() {
        if let url = Bundle.main.resourceURL?.appendingPathComponent("CoreDemos") { NSWorkspace.shared.activateFileViewerSelecting([url]) }
    }
    @objc private func showSource() {
        if let resources = Bundle.main.resourceURL { NSWorkspace.shared.activateFileViewerSelecting([resources.appendingPathComponent("Source")]) }
    }
    @objc private func showLibraryFolder() { NSWorkspace.shared.open(model.root) }
    private func installMenu() {
        let main = NSMenu()
        func submenu(_ title: String) -> NSMenu { let item = NSMenuItem(); let menu = NSMenu(title: title); item.submenu = menu; main.addItem(item); return menu }
        func item(_ menu: NSMenu, _ title: String, _ action: Selector, _ key: String = "") { let i = NSMenuItem(title: title, action: action, keyEquivalent: key); i.target = self; menu.addItem(i) }
        let appMenu = submenu("Crispy GB")
        item(appMenu, "About Crispy GB", #selector(showAbout))
        item(appMenu, "Settings…", #selector(showSettings), ",")
        appMenu.addItem(.separator())
        let quit = NSMenuItem(title: "Quit Crispy GB", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"); appMenu.addItem(quit)
        let file = submenu("File")
        item(file, "Import ROMs…", #selector(importROMs), "o")
        item(file, "Show Library", #selector(showLibrary), "l")
        item(file, "Show Library Folder", #selector(showLibraryFolder))
        let edit = submenu("Edit")
        for (title, selector, key) in [("Cut", #selector(NSText.cut(_:)), "x"), ("Copy", #selector(NSText.copy(_:)), "c"), ("Paste", #selector(NSText.paste(_:)), "v"), ("Select All", #selector(NSText.selectAll(_:)), "a")] { edit.addItem(NSMenuItem(title: title, action: selector, keyEquivalent: key)) }
        let window = submenu("Window")
        window.addItem(NSMenuItem(title: "Minimize", action: #selector(NSWindow.miniaturize(_:)), keyEquivalent: "m"))
        NSApp.windowsMenu = window
        let help = submenu("Help")
        item(help, "Source and Licenses", #selector(showSource))
        if CoreIdentity.experimental { item(help, "Original Core Demo ROMs", #selector(showCoreDemos)) }
        NSApp.mainMenu = main
    }
}

@main enum StudioMain {
    @MainActor static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        let delegate = StudioAppDelegate()
        app.delegate = delegate
        withExtendedLifetime(delegate) { app.run() }
    }
}
