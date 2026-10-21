import Cocoa
import MetalKit
import AVFoundation
import GameController
import SwiftUI
import IOKit.hid
import EmulatorBridge

private final class AudioCore {
    let lock = NSLock()
    let scratch = UnsafeMutablePointer<Float>.allocate(capacity: 16384)
    var core: OpaquePointer?
    var lastLeft: Float = 0
    var lastRight: Float = 0
    deinit { scratch.deallocate() }
    init(_ core: OpaquePointer) { self.core = core }
    func silenceAndDetach() { lock.lock(); core = nil; lock.unlock() }
}

private final class GameView: MTKView {
    var keyChanged: ((UInt16, Bool) -> Void)?
    var releaseKeys: (() -> Void)?
    var specialKey: ((NSEvent, Bool) -> Bool)?
    override var acceptsFirstResponder: Bool { true }
    override func keyDown(with event: NSEvent) { if specialKey?(event, true) == true { return }; if !event.isARepeat { keyChanged?(event.keyCode, true) } }
    override func keyUp(with event: NSEvent) { if specialKey?(event, false) == true { return }; keyChanged?(event.keyCode, false) }
    override func resignFirstResponder() -> Bool { releaseKeys?(); return super.resignFirstResponder() }
    override func mouseDown(with event: NSEvent) { window?.makeFirstResponder(self) }
}

private final class KeyBindingButton: NSButton {
    var capture: ((NSEvent) -> Void)?
    override var acceptsFirstResponder: Bool { true }
    override func mouseDown(with event: NSEvent) { title = "Press a key…"; window?.makeFirstResponder(self) }
    override func keyDown(with event: NSEvent) {
        guard !event.modifierFlags.contains(.command), !event.isARepeat else { return }
        capture?(event)
    }
}

final class PlayerWindowController: NSWindowController, NSWindowDelegate, MTKViewDelegate {
    private let overlay = SessionOverlayState()
    private var overlayHost: NSHostingView<SessionOverlay>?
    private var eventMonitor: Any?
    private var settingsWriter: ((SessionSettings) -> Void)?
    private var lastBattery = Date()
    private var lastControllerSample = Date.distantPast
    private var menuWasDown = false
    private var lastInputTimestamp = 0.0
    private var sampledInputDelay: Double?
    private var fadingOut = false
    private var compare = false
    private var compareTexture: MTLTexture?
    private let saveDirectory: URL
    private var core: OpaquePointer?
    private let audioCore: AudioCore
    private let engine = AVAudioEngine()
    private var audioNode: AVAudioSourceNode?
    private let gameView: GameView
    private let queue: MTLCommandQueue
    private let pipeline: MTLRenderPipelineState
    private var texture: MTLTexture?
    private var timer: Timer?
    private var lastTick = 0.0
    private var clock = PlaybackTiming()
    private var playbackSpeed = 1.0
    private var fastForwardHeld = false
    private var controlsShown = false
    private let controlsPanel = NSVisualEffectView()
    private let controlsToggle = NSButton(title: "Pause / Tools", target: nil, action: nil)
    private var speedPicker: NSPopUpButton?
    private var metricsStart = 0.0
    private var paused = false
    private var closed = false
    private var keyboardKeys: UInt32 = 0
    private var displayMode = 0
    private var shaderMode: UInt32 = 0
    private let stateURL: URL
    private let pauseButton = NSButton(title: "Pause", target: nil, action: nil)
    private var observers: [NSObjectProtocol] = []
    private var keyMap: [UInt16: UInt32] = [7: 0, 6: 1, 51: 2, 36: 3, 124: 4, 123: 5, 126: 6, 125: 7, 1: 8, 0: 9]
    private var frameNumber = 0
    private var baseTitle = ""
    private var audioFailure: String?
    private let preferences = UserDefaults.standard
    private var keyNames: [String: String] = ["6":"Z", "7":"X", "51":"Delete", "36":"Return", "124":"→", "123":"←", "126":"↑", "125":"↓", "1":"S", "0":"A"]
    private static let actions = ["A", "B", "Select", "Start", "Right", "Left", "Up", "Down", "R", "L"]

    init(romURL: URL, title: String, saveDirectory: URL, settings: SessionSettings? = nil, persist: ((SessionSettings) -> Void)? = nil) throws {
        let saveDirectory = CoreIdentity.saveDirectory(saveDirectory)
        self.saveDirectory = saveDirectory; self.settingsWriter = persist
        guard let device = MTLCreateSystemDefaultDevice(), let queue = device.makeCommandQueue() else { throw NSError(domain: "Crispy GB", code: 1, userInfo: [NSLocalizedDescriptionKey: "Metal graphics is unavailable on this Mac."]) }
        let library = try device.makeLibrary(source: Self.scanlineSource + Self.shaderSource, options: nil)
        let descriptor = MTLRenderPipelineDescriptor()
        descriptor.vertexFunction = library.makeFunction(name: "screenVertex")
        descriptor.fragmentFunction = library.makeFunction(name: "screenFragment")
        descriptor.colorAttachments[0].pixelFormat = .bgra8Unorm
        self.pipeline = try device.makeRenderPipelineState(descriptor: descriptor)
        self.queue = queue
        try FileManager.default.createDirectory(at: saveDirectory, withIntermediateDirectories: true)
        guard let created = studio_create(romURL.path, saveDirectory.path) else { throw NSError(domain: "Crispy GB", code: 2, userInfo: [NSLocalizedDescriptionKey: String(cString: studio_last_error())]) }
        core = created
        audioCore = AudioCore(created)
        stateURL = saveDirectory.appendingPathComponent("quick.state")
        gameView = GameView(frame: .zero, device: device)
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 960, height: 690), styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
        window.title = title
        window.minSize = NSSize(width: 640, height: 360)
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.collectionBehavior.insert(.fullScreenPrimary)
        super.init(window: window)
        baseTitle = title + (CoreIdentity.experimental ? " [Crispy Core · prototype]" : "")
        displayMode = min(2, max(0, preferences.integer(forKey: "Studio.Player.display")))
        let savedSpeed = preferences.double(forKey: "CrispyGB.Player.speed")
        if [1.0, 2.0, 4.0, 8.0].contains(savedSpeed) { playbackSpeed = savedSpeed }
        let arguments = CommandLine.arguments
        if let index = arguments.firstIndex(of: "--speed"), arguments.indices.contains(index + 1), let speed = Double(arguments[index + 1]), [1.0, 2.0, 4.0, 8.0].contains(speed) { playbackSpeed = speed }
        shaderMode = UInt32(min(3, max(0, preferences.integer(forKey: "Studio.Player.shader"))))
        if let volume = preferences.object(forKey: "Studio.Player.volume") as? NSNumber { volumeValue = min(1, max(0, volume.floatValue)) }
        if let saved = preferences.dictionary(forKey: "Studio.Player.keys") as? [String: Int], saved.count == 10 {
            var restored: [UInt16: UInt32] = [:]
            for (key, bit) in saved { if let code = UInt16(key), (0..<10).contains(bit) { restored[code] = UInt32(bit) } }
            if restored.count == 10 && Set(restored.values).count == 10 { keyMap = restored }
        }
        if let names = preferences.dictionary(forKey: "Studio.Player.keyNames") as? [String: String] { keyNames.merge(names) { _, new in new } }
        if let settings { overlay.settings = settings }
        else if let data = try? Data(contentsOf: saveDirectory.appendingPathComponent("session.json")), let saved = try? JSONDecoder().decode(SessionSettings.self, from: data) { overlay.settings = saved }
        else { overlay.settings.display.fitMode = ["fit", "integer", "fill"][displayMode]; overlay.settings.display.filter = ["none","smooth","lcd","crt"][Int(shaderMode)] }
        applySession(overlay.settings)
        overlay.nativeSize = CGSize(width: Int(studio_width(created)), height: Int(studio_height(created)))
        updateTitle()
        window.delegate = self
        window.isReleasedWhenClosed = false
        let content = NSView()
        window.contentView = content
        gameView.translatesAutoresizingMaskIntoConstraints = false
        gameView.colorPixelFormat = .bgra8Unorm
        gameView.clearColor = MTLClearColorMake(0.025, 0.03, 0.04, 1)
        gameView.isPaused = true
        gameView.autoResizeDrawable = true
        gameView.enableSetNeedsDisplay = false
        gameView.framebufferOnly = true
        gameView.delegate = self
        gameView.keyChanged = { [weak self] key, down in
            guard let self, let bit = self.keyMap[key] else { return }
            if down { self.keyboardKeys |= 1 << bit } else { self.keyboardKeys &= ~(1 << bit) }
        }
        gameView.releaseKeys = { [weak self] in self?.releaseInput() }
        gameView.specialKey = { [weak self] event, down in
            guard let self else { return false }
            if event.keyCode == 49 && self.keyMap[49] == nil { self.fastForwardHeld = down; self.updateAudioSpeed(); self.updateTitle(); return true }
            if event.modifierFlags.contains([.command, .shift]) && event.charactersIgnoringModifiers?.lowercased() == "h" {
                if down && !event.isARepeat { self.toggleControls() }; return true
            }
            if event.keyCode == 53 { if down && !event.isARepeat { self.togglePause() }; return true }
            return false
        }
        pauseButton.target = self; pauseButton.action = #selector(togglePause)
        let reset = button("Reset", #selector(resetGame))
        let save = button("Save", #selector(saveState))
        let load = button("Load", #selector(loadState))
        let display = NSPopUpButton(); display.addItems(withTitles: ["Fit · whole image", "Integer scale", "Fill · crop edges"])
        display.selectItem(at: displayMode); display.target = self; display.action = #selector(changeDisplay(_:))
        let shader = NSPopUpButton(); shader.addItems(withTitles: ["Crisp", "Smooth", "LCD", "CRT"])
        shader.selectItem(at: Int(shaderMode)); shader.target = self; shader.action = #selector(changeShader(_:))
        let volume = NSSlider(value: Double(volumeValue), minValue: 0, maxValue: 1, target: self, action: #selector(changeVolume(_:)))
        volume.toolTip = "Volume (drag left to mute)"; volume.widthAnchor.constraint(equalToConstant: 65).isActive = true
        let speed = NSPopUpButton(); speed.addItems(withTitles: ["1× Normal", "2× Fast", "4× Fast", "8× Fast"])
        speed.selectItem(at: [1.0, 2.0, 4.0, 8.0].firstIndex(of: playbackSpeed) ?? 0)
        speed.target = self; speed.action = #selector(changeSpeed(_:)); speedPicker = speed
        let actions = NSStackView(views: [pauseButton, reset, save, load, speed, button("Hide", #selector(toggleControls))])
        let appearance = NSStackView(views: [display, shader, volume, button("⛶", #selector(fullscreen)), button("Key Bindings", #selector(help))])
        let controls = NSStackView(views: [actions, appearance]); controls.orientation = .vertical; controls.spacing = 8
        controls.translatesAutoresizingMaskIntoConstraints = false
        controlsPanel.material = .hudWindow; controlsPanel.blendingMode = .withinWindow
        controlsPanel.wantsLayer = true; controlsPanel.layer?.cornerRadius = 12
        controlsPanel.translatesAutoresizingMaskIntoConstraints = false; controlsPanel.isHidden = true
        controlsToggle.target = self; controlsToggle.action = #selector(toggleControls); controlsToggle.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(gameView); content.addSubview(controlsPanel); content.addSubview(controlsToggle); controlsPanel.addSubview(controls)
        NSLayoutConstraint.activate([
            gameView.topAnchor.constraint(equalTo: content.topAnchor), gameView.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            gameView.leadingAnchor.constraint(equalTo: content.leadingAnchor), gameView.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            controlsToggle.topAnchor.constraint(equalTo: content.topAnchor, constant: 8), controlsToggle.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -12),
            controlsPanel.topAnchor.constraint(equalTo: controlsToggle.bottomAnchor, constant: 8), controlsPanel.centerXAnchor.constraint(equalTo: content.centerXAnchor),
            controls.topAnchor.constraint(equalTo: controlsPanel.topAnchor, constant: 12), controls.bottomAnchor.constraint(equalTo: controlsPanel.bottomAnchor, constant: -12),
            controls.leadingAnchor.constraint(equalTo: controlsPanel.leadingAnchor, constant: 12), controls.trailingAnchor.constraint(equalTo: controlsPanel.trailingAnchor, constant: -12)
        ])
        let menu = NSMenu()
        for (title, selector) in [("Show / Hide Controls", #selector(toggleControls)), ("Fullscreen", #selector(fullscreen)), ("Pause / Resume", #selector(togglePause)), ("Save State", #selector(saveState)), ("Load State", #selector(loadState)), ("Key Bindings…", #selector(help))] {
            let item = NSMenuItem(title: title, action: selector, keyEquivalent: ""); item.target = self; menu.addItem(item)
        }
        gameView.menu = menu
        observers.append(NotificationCenter.default.addObserver(forName: NSWindow.didResignKeyNotification, object: window, queue: .main) { [weak self] _ in self?.releaseInput() })
        observers.append(NotificationCenter.default.addObserver(forName: NSApplication.didResignActiveNotification, object: nil, queue: .main) { [weak self] _ in self?.releaseInput() })
        setupOverlay(content)
        setupAudio()
        updateAudioSpeed()
        window.center()
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is unavailable") }
    private func button(_ title: String, _ selector: Selector) -> NSButton { NSButton(title: title, target: self, action: selector) }
    func start() {
        guard !closed else { return }
        showWindow(nil)
        window?.makeKeyAndOrderFront(nil)
        window?.makeFirstResponder(gameView)
        NSApp.activate(ignoringOtherApps: true)
        if let failure = audioFailure { audioFailure = nil; alert("Audio unavailable", "The game can continue without sound. " + failure) }
        if timer == nil {
            lastTick = ProcessInfo.processInfo.systemUptime
            metricsStart = lastTick
            let timer = Timer(timeInterval: 1.0 / 120.0, repeats: true) { [weak self] _ in self?.tick() }
            self.timer = timer
            RunLoop.main.add(timer, forMode: .common)
        }
    }
    private func setupAudio() {
        let format = AVAudioFormat(standardFormatWithSampleRate: 48000, channels: 2)!
        let audio = audioCore
        let node = AVAudioSourceNode(format: format) { _, _, count, buffers in
            let list = UnsafeMutableAudioBufferListPointer(buffers)
            audio.lock.lock()
            defer { audio.lock.unlock() }
            for buffer in list { if let data = buffer.mData { memset(data, 0, Int(buffer.mDataByteSize)) } }
            guard let core = audio.core, list.count >= 2,
                  let left = list[0].mData?.assumingMemoryBound(to: Float.self),
                  let right = list[1].mData?.assumingMemoryBound(to: Float.self) else { return noErr }
            var offset = 0
            while offset < Int(count) {
                let requested = min(8192, Int(count) - offset)
                let read = studio_read_audio(core, audio.scratch, requested)
                for index in 0..<requested {
                    if index < read { audio.lastLeft = audio.scratch[index * 2]; audio.lastRight = audio.scratch[index * 2 + 1] }
                    else { audio.lastLeft *= 0.97; audio.lastRight *= 0.97 }
                    left[offset + index] = audio.lastLeft; right[offset + index] = audio.lastRight
                }
                offset += requested
            }
            return noErr
        }
        audioNode = node
        engine.attach(node); engine.connect(node, to: engine.mainMixerNode, format: format)
        engine.mainMixerNode.outputVolume = volumeValue
        do { try engine.start() } catch { audioFailure = error.localizedDescription; updateTitle() }
    }
    private func controllerKeys() -> UInt32 {
        var bits: UInt32 = 0
        func add(_ pressed: Bool, _ bit: UInt32) { if pressed { bits |= 1 << bit } }
        for (index, controller) in GCController.controllers().enumerated() where index == overlay.settings.controls.controllerSlot {
            if let pad = controller.extendedGamepad {
                add(pad.buttonA.isPressed, 0); add(pad.buttonB.isPressed, 1)
                add(pad.buttonOptions?.isPressed ?? pad.buttonX.isPressed, 2)
                add(false, 3)
                add(pad.dpad.right.isPressed || pad.leftThumbstick.xAxis.value > 0.4, 4)
                add(pad.dpad.left.isPressed || pad.leftThumbstick.xAxis.value < -0.4, 5)
                add(pad.dpad.up.isPressed || pad.leftThumbstick.yAxis.value > 0.4, 6)
                add(pad.dpad.down.isPressed || pad.leftThumbstick.yAxis.value < -0.4, 7)
                add(pad.rightShoulder.isPressed, 8); add(pad.leftShoulder.isPressed, 9)
            } else if let pad = controller.microGamepad {
                add(pad.buttonA.isPressed, 0); add(pad.buttonX.isPressed, 1); add(false, 3)
                add(pad.dpad.right.isPressed, 4); add(pad.dpad.left.isPressed, 5); add(pad.dpad.up.isPressed, 6); add(pad.dpad.down.isPressed, 7)
            }
        }
        if let controller = GCController.controllers().enumerated().first(where: { $0.offset == overlay.settings.controls.controllerSlot })?.element {
            let inputs = controllerInputs(controller)
            for (action, input) in overlay.settings.controls.overrides where input.hasPrefix("ctrl.") {
                guard let index = Self.actions.firstIndex(of: action) else { continue }
                bits &= ~(1 << UInt32(index))
                if inputs[input] == true { bits |= 1 << UInt32(index) }
            }
        }
        return bits
    }
    private func tick() {
        guard let core, !closed else { return }
        let now = ProcessInfo.processInfo.systemUptime
        let elapsed = min(now - lastTick, 0.1); lastTick = now
        pollOverlayInput()
        if !paused && Date().timeIntervalSince(lastBattery) >= 30 { checkpointBattery() }
        guard !paused else { return }
        let frames = clock.frames(elapsed: elapsed, fps: studio_fps(core), speed: effectiveSpeed)
        let acceptsInput = NSApp.isActive && window?.isKeyWindow == true && window?.attachedSheet == nil && window?.firstResponder === gameView
        studio_set_keys(core, acceptsInput ? keyboardKeys | controllerKeys() : 0)
        for _ in 0..<frames {
            studio_run_frame(core)
            let issue = String(cString: studio_runtime_error(core))
            if !issue.isEmpty {
                if CommandLine.arguments.contains("--smoke-seconds") { fputs("CORE_ERROR: \(issue)\n", stderr); exit(1) }
                overlay.coreError = issue; setOverlay(true)
                alert("Experimental core stopped", issue + "\n\nThis console implementation is still being developed. Your mGBA player remains available in Crispy GB.")
                break
            }
            frameNumber += 1
        }
        if effectiveSpeed != 1 { studio_clear_audio(core) }
        gameView.draw()
    }
    private func setupOverlay(_ content: NSView) {
        let host = NSHostingView(rootView: SessionOverlay(state: overlay)); overlayHost = host
        host.translatesAutoresizingMaskIntoConstraints = false; host.isHidden = true; content.addSubview(host)
        NSLayoutConstraint.activate([host.leadingAnchor.constraint(equalTo: content.leadingAnchor), host.trailingAnchor.constraint(equalTo: content.trailingAnchor), host.topAnchor.constraint(equalTo: content.topAnchor), host.bottomAnchor.constraint(equalTo: content.bottomAnchor)])
        overlay.coreLabel = CoreIdentity.experimental ? "Crispy Core prototype · GB/GBC/GBA bring-up · audio unavailable" : ""
        overlay.speed = playbackSpeed; overlay.volume = Double(volumeValue)
        overlay.changeSpeed = { [weak self] speed in
            guard let self else { return }; self.playbackSpeed = speed; self.overlay.speed = speed
            self.preferences.set(speed, forKey: "CrispyGB.Player.speed"); self.clock.reset(); self.updateAudioSpeed(); self.updateTitle()
        }
        overlay.changeVolume = { [weak self] volume in
            guard let self else { return }; self.volumeValue = Float(volume); self.overlay.volume = volume
            self.preferences.set(volume, forKey: "Studio.Player.volume"); self.engine.mainMixerNode.outputVolume = self.effectiveSpeed == 1 ? Float(volume) : 0
        }
        overlay.fullscreen = { [weak self] in self?.fullscreen() }
        overlay.reset = { [weak self] in self?.resetGame(); self?.gameView.draw() }
        overlay.changed = { [weak self] settings in self?.applySession(settings); self?.writeSession(settings) }
        overlay.resume = { [weak self] in self?.setOverlay(false) }
        overlay.quit = { [weak self] in self?.window?.close(); NotificationCenter.default.post(name: Notification.Name("CrispyGB.ShowLibrary"), object: nil) }
        overlay.save = { [weak self] slot in if self?.commitSlot(slot) == true { self?.setOverlay(false) } }
        overlay.load = { [weak self] slot in self?.restoreSlot(slot) }
        overlay.loadRecovery = { [weak self] in self?.restoreSlot(-1) }
        overlay.batteryLoad = { [weak self] in self?.restoreBattery() }
        overlay.detect = { [weak self] in self?.detectControllers() }
        overlay.assignKey = { [weak self] action, event in self?.assignKey(action, event) }
        overlay.resetControls = { [weak self] in
            guard let self else { return }; self.keyMap = Self.defaultKeyMap
            self.overlay.settings.controls = ControlSettings()
        }
        eventMonitor = NSEvent.addLocalMonitorForEvents(matching: [.keyDown, .flagsChanged]) { [weak self] event in
            guard let self, event.window === self.window else { return event }
            if event.type == .flagsChanged { self.setCompare(event.modifierFlags.contains(.option)); return event }
            if let action = self.overlay.keyboardCapture ?? self.overlay.capturing, event.type == .keyDown {
                self.assignKey(action, event); self.overlay.keyboardCapture = nil; self.overlay.capturing = nil; return nil
            }
            if event.keyCode == 53 || (event.modifierFlags.contains(.command) && event.charactersIgnoringModifiers?.lowercased() == "p") {
                if !event.isARepeat { self.togglePause() }; return nil
            }
            return event
        }
        detectControllers(); checkpointBattery(); refreshSlots()
    }
    private static let defaultKeyMap: [UInt16:UInt32] = [7:0,6:1,51:2,36:3,124:4,123:5,126:6,125:7,1:8,0:9]
    private func applySession(_ settings: SessionSettings) {
        displayMode = ["fit":0,"integer":1,"fill":2][settings.display.fitMode] ?? 0
        shaderMode = ["none":0,"smooth":1,"lcd":2,"crt":3,"scanline":0][settings.display.filter] ?? 0
        var mapping = Self.defaultKeyMap
        let actions = settings.controls.overrides.filter { $0.value.hasPrefix("kb.") }
        let replaced = Set(actions.keys.compactMap { Self.actions.firstIndex(of: $0) }.map(UInt32.init))
        mapping = mapping.filter { !replaced.contains($0.value) }
        for (action, input) in actions.sorted(by: { $0.key < $1.key }) {
            let aliases: [String:UInt16] = ["z":6,"x":7,"a":0,"s":1,"enter":36,"esc":53,"space":49,"up":126,"down":125,"left":123,"right":124]
            let token = String(input.dropFirst(3))
            guard let bit = Self.actions.firstIndex(of: action), let code = UInt16(token) ?? aliases[token.lowercased()] else { continue }
            mapping[code] = UInt32(bit)
        }
        keyMap = mapping
        updateTitle(); gameView.draw()
    }
    private func writeSession(_ settings: SessionSettings) {
        do {
            try JSONEncoder().encode(settings).write(to: saveDirectory.appendingPathComponent("session.json"), options: .atomic)
            settingsWriter?(settings)
        } catch { alert("Could not save display settings", error.localizedDescription) }
    }
    private func assignKey(_ action: String, _ event: NSEvent) {
        guard let bit = Self.actions.firstIndex(of: action), !event.modifierFlags.contains(.command) else { return }
        var controls = overlay.settings.controls
        if let existing = keyMap[event.keyCode], let previous = keyMap.first(where: { $0.value == UInt32(bit) })?.key {
            controls.overrides[Self.actions[Int(existing)]] = "kb.\(previous)"
        }
        controls.overrides[action] = "kb.\(event.keyCode)"; overlay.settings.controls = controls
    }
    private func slotURL(_ slot: Int) -> URL { saveDirectory.appendingPathComponent(slot < 0 ? "quit-recovery.\(CoreIdentity.experimental ? "cstate" : "mbs")" : "slot-\(slot+1).\(CoreIdentity.experimental ? "cstate" : "mbs")") }
    private func refreshSlots() {
        overlay.hasRecovery = FileManager.default.fileExists(atPath: slotURL(-1).path)
        for slot in 0..<3 {
            let url = slotURL(slot)
            if !FileManager.default.fileExists(atPath: url.path) { overlay.slots[slot] = "Empty"; continue }
            if let data = try? Data(contentsOf: url.appendingPathExtension("json")), let meta = try? JSONDecoder().decode(SlotMetadata.self, from: data) {
                overlay.slots[slot] = meta.date.formatted(date: .abbreviated, time: .shortened) + " · frame \(meta.frame)"
            } else { overlay.slots[slot] = "Saved · metadata unavailable" }
        }
    }
    @discardableResult private func commitSlot(_ slot: Int) -> Bool {
        guard let core else { return false }; writeSession(overlay.settings)
        guard studio_save_state(core, slotURL(slot).path) else { alert("Could not save state", String(cString: studio_last_error())); return false }
        do { try JSONEncoder().encode(SlotMetadata(date: Date(), frame: frameNumber)).write(to: slotURL(slot).appendingPathExtension("json"), options: .atomic) }
        catch { alert("Saved state; metadata unavailable", error.localizedDescription) }
        refreshSlots(); return true
    }
    private func restoreSlot(_ slot: Int) {
        guard let core else { return }
        guard studio_load_state(core, slotURL(slot).path) else { alert("Could not load state", String(cString: studio_last_error())); return }
        if let data = try? Data(contentsOf: slotURL(slot).appendingPathExtension("json")), let meta = try? JSONDecoder().decode(SlotMetadata.self, from: data) { frameNumber = meta.frame }
        overlay.coreError = nil; gameView.draw(); setOverlay(false)
    }
    private func checkpointBattery() {
        guard let core else { return }; studio_flush_save(core)
        let battery = saveDirectory.appendingPathComponent("battery.sav")
        do {
            if FileManager.default.fileExists(atPath: battery.path) { try Data(contentsOf: battery).write(to: saveDirectory.appendingPathComponent("battery-checkpoint.sav"), options: .atomic) }
            lastBattery = Date()
        } catch { overlay.battery = "Checkpoint failed: " + error.localizedDescription }
    }
    private func restoreBattery() {
        guard let core else { return }
        guard studio_restore_battery(core, saveDirectory.appendingPathComponent("battery-checkpoint.sav").path) else { alert("Could not load battery", String(cString: studio_last_error())); return }
        frameNumber = 0; overlay.coreError = nil; gameView.draw(); setOverlay(false)
    }
    private func controllerInputs(_ controller: GCController) -> [String:Bool] {
        guard let p = controller.extendedGamepad else {
            if let p = controller.microGamepad { return ["ctrl.a":p.buttonA.isPressed,"ctrl.x":p.buttonX.isPressed,"ctrl.start":p.buttonMenu.isPressed,"ctrl.up":p.dpad.up.isPressed,"ctrl.down":p.dpad.down.isPressed,"ctrl.left":p.dpad.left.isPressed,"ctrl.right":p.dpad.right.isPressed] }
            return [:]
        }
        return ["ctrl.a":p.buttonA.isPressed,"ctrl.b":p.buttonB.isPressed,"ctrl.x":p.buttonX.isPressed,"ctrl.y":p.buttonY.isPressed,"ctrl.select":p.buttonOptions?.isPressed ?? false,"ctrl.start":p.buttonMenu.isPressed,"ctrl.l":p.leftShoulder.isPressed,"ctrl.r":p.rightShoulder.isPressed,"ctrl.up":p.dpad.up.isPressed,"ctrl.down":p.dpad.down.isPressed,"ctrl.left":p.dpad.left.isPressed,"ctrl.right":p.dpad.right.isPressed,"ctrl.lt":p.leftTrigger.isPressed,"ctrl.rt":p.rightTrigger.isPressed]
    }
    private func pollOverlayInput() {
        let controllers = GCController.controllers()
        if let controller = controllers.enumerated().first(where: { $0.offset == overlay.settings.controls.controllerSlot })?.element {
            let timestamp = controller.input.lastEventTimestamp
            if timestamp > 0 && timestamp != lastInputTimestamp {
                sampledInputDelay = max(0, controller.input.lastEventLatency) * 1000
                lastInputTimestamp = timestamp
            }
        }
        if controllers.count != overlay.controllerCount { detectControllers() }
        let menuDown = controllers.contains { $0.extendedGamepad?.buttonMenu.isPressed == true || $0.microGamepad?.buttonMenu.isPressed == true }
        let focused = NSApp.isActive && window?.isKeyWindow == true
        if let action = overlay.capturing, focused {
            for (index, controller) in controllers.enumerated() {
                if let input = controllerInputs(controller).sorted(by: { $0.key < $1.key }).first(where: { $0.value })?.key {
                    var controls = overlay.settings.controls; controls.controllerSlot = index; controls.overrides[action] = input
                    overlay.settings.controls = controls; overlay.capturing = nil; break
                }
            }
        } else if focused && menuDown && !menuWasDown { togglePause() }
        menuWasDown = menuDown
        if Date().timeIntervalSince(lastControllerSample) >= 1 {
            lastControllerSample = Date()
            if let controller = controllers.first {
                _ = controller
                overlay.controller = "● Connected · event delay " + (sampledInputDelay.map { String(format: "%.1f ms", $0) } ?? "—")
            } else { overlay.controller = "○ No controller"; sampledInputDelay = nil; lastInputTimestamp = 0 }
            overlay.battery = "auto every 30 s · last \(lastBattery.formatted(date: .omitted, time: .standard)) · next in \(max(0,30-Int(Date().timeIntervalSince(lastBattery)))) s"
        }
    }
    private func detectControllers() {
        let manager = IOHIDManagerCreate(kCFAllocatorDefault, IOOptionBits(kIOHIDOptionsTypeNone))
        let matches = [4,5,8].map { [kIOHIDDeviceUsagePageKey: 1, kIOHIDDeviceUsageKey: $0] }
        IOHIDManagerSetDeviceMatchingMultiple(manager, matches as CFArray); IOHIDManagerOpen(manager, IOOptionBits(kIOHIDOptionsTypeNone))
        let devices = IOHIDManagerCopyDevices(manager) as? Set<IOHIDDevice> ?? []
        var names: [String] = []
        for device in devices {
            let usage = IOHIDDeviceGetProperty(device, kIOHIDPrimaryUsageKey as CFString) as? Int ?? 0
            let page = IOHIDDeviceGetProperty(device, kIOHIDPrimaryUsagePageKey as CFString) as? Int ?? 0
            if page == 1 && [4,5,8].contains(usage) {
                let name = IOHIDDeviceGetProperty(device, kIOHIDProductKey as CFString) as? String ?? "HID controller"
                names.append(name + " · " + (GCController.controllers().contains(where: { $0.vendorName == name }) ? "mapped" : "unassigned"))
            }
        }
        IOHIDManagerClose(manager, IOOptionBits(kIOHIDOptionsTypeNone))
        names += GCController.controllers().map { ($0.vendorName ?? "Controller") + ($0.extendedGamepad != nil ? " · mapped" : " · partial") }
        overlay.devices = Array(Set(names)).sorted(); overlay.controllerCount = GCController.controllers().count
        if overlay.controllerCount > 0 && overlay.settings.controls.controllerSlot >= overlay.controllerCount { overlay.settings.controls.controllerSlot = 0 }
    }
    private func setCompare(_ held: Bool) {
        guard held != compare else { return }; compare = held
        if held, let core, let pixels = studio_pixels(core), let device = gameView.device {
            let w = Int(studio_width(core)), h = Int(studio_height(core))
            let descriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .rgba8Unorm, width: w, height: h, mipmapped: false); descriptor.storageMode = .shared
            compareTexture = device.makeTexture(descriptor: descriptor)
            compareTexture?.replace(region: MTLRegionMake2D(0,0,w,h), mipmapLevel: 0, withBytes: pixels, bytesPerRow: w*4)
        } else { compareTexture = nil }
        gameView.draw()
    }
    private var effectiveSpeed: Double { fastForwardHeld ? max(4, playbackSpeed) : playbackSpeed }
    private func updateAudioSpeed() {
        if paused { return } // drain the finite queued audio tail naturally while halted
        if let core { studio_clear_audio(core) }
        engine.mainMixerNode.outputVolume = effectiveSpeed != 1 ? 0 : volumeValue
    }
    private func releaseInput() { keyboardKeys = 0; fastForwardHeld = false; updateAudioSpeed(); updateTitle() }
    @objc private func toggleControls() { togglePause() }
    @objc private func changeSpeed(_ sender: NSPopUpButton) { playbackSpeed = [1.0, 2.0, 4.0, 8.0][sender.indexOfSelectedItem]; preferences.set(playbackSpeed, forKey: "CrispyGB.Player.speed"); clock.reset(); updateAudioSpeed(); updateTitle(); window?.makeFirstResponder(gameView) }
    @objc private func togglePause() {
        if overlay.preview { overlay.preview = false; return }
        setOverlay(!paused)
    }
    private func setOverlay(_ shown: Bool) {
        guard !closed, !fadingOut, shown != paused else { return }
        if !shown && overlay.coreError != nil { return }
        // Input and runFrame share the main run loop: halt only between frames.
        if shown {
            if CommandLine.arguments.contains("--player-metrics") { print("PLAYER_HALT frame=\(frameNumber)") }
            paused = true; keyboardKeys = 0; fastForwardHeld = false
            if let core { studio_set_keys(core, 0) }
            refreshSlots(); overlay.tab = "Session"; overlayHost?.isHidden = false
            overlayHost?.alphaValue = 0; overlay.visible = true
            NSAnimationContext.runAnimationGroup { context in context.duration = 0.25; context.timingFunction = CAMediaTimingFunction(name: .easeOut); overlayHost?.animator().alphaValue = 1 }
        } else {
            fadingOut = true; overlay.preview = false
            NSAnimationContext.runAnimationGroup({ context in context.duration = 0.25; overlayHost?.animator().alphaValue = 0 }, completionHandler: { [weak self] in
                guard let self, !self.closed else { return }
                self.overlay.visible = false; self.overlayHost?.isHidden = true; self.paused = false; self.fadingOut = false
                if CommandLine.arguments.contains("--player-metrics") { print("PLAYER_RESUME frame=\(self.frameNumber)") }
                self.clock.reset(); self.lastTick = ProcessInfo.processInfo.systemUptime
                self.updateAudioSpeed(); self.window?.makeFirstResponder(self.gameView)
            })
        }
        pauseButton.title = shown ? "Resume" : "Pause"
    }
    private var volumeValue: Float = 0.8
    @objc private func changeVolume(_ slider: NSSlider) { volumeValue = slider.floatValue; preferences.set(volumeValue, forKey: "Studio.Player.volume"); updateAudioSpeed() }
    @objc private func resetGame() { if let core { studio_reset(core); studio_clear_audio(core); overlay.coreError = nil }; window?.makeFirstResponder(gameView) }
    @objc private func saveState() { _ = commitSlot(0); window?.makeFirstResponder(gameView) }
    @objc private func loadState() { if FileManager.default.fileExists(atPath: slotURL(0).path) { restoreSlot(0); return }; if let core { if !studio_load_state(core, stateURL.path) { alert("Could not load state", FileManager.default.fileExists(atPath: stateURL.path) ? String(cString: studio_last_error()) : "Save a state first using Save.") }; studio_clear_audio(core) }; window?.makeFirstResponder(gameView) }
    @objc private func changeDisplay(_ sender: NSPopUpButton) { displayMode = sender.indexOfSelectedItem; overlay.settings.display.fitMode = ["fit", "integer", "fill"][displayMode]; updateTitle(); gameView.draw(); window?.makeFirstResponder(gameView) }
    @objc private func changeShader(_ sender: NSPopUpButton) { shaderMode = UInt32(sender.indexOfSelectedItem); overlay.settings.display.filter = ["none","smooth","lcd","crt"][Int(shaderMode)]; gameView.draw(); window?.makeFirstResponder(gameView) }
    @objc private func fullscreen() { window?.toggleFullScreen(nil) }
    func windowWillEnterFullScreen(_ notification: Notification) { controlsShown = false; controlsPanel.isHidden = true; controlsToggle.isHidden = true; controlsToggle.title = "Controls ▾" }
    func windowDidExitFullScreen(_ notification: Notification) { controlsToggle.isHidden = false }
    func window(_ window: NSWindow, willUseFullScreenPresentationOptions proposedOptions: NSApplication.PresentationOptions) -> NSApplication.PresentationOptions {
        var options = proposedOptions; options.remove([.hideMenuBar, .hideDock]); options.formUnion([.autoHideMenuBar, .autoHideDock]); return options
    }
    private func updateTitle() {
        window?.title = baseTitle + " — " + ["Aspect fit", "Integer scale", "Fill (cropped)"][displayMode] + " — \(Int(effectiveSpeed))×" + (audioFailure != nil ? " — Audio unavailable" : "")
    }
    @objc private func help() { if !paused { setOverlay(true) }; overlay.tab = "Controls" }
    private func persistKeys() {
        for (key, bit) in keyMap { overlay.settings.controls.overrides[Self.actions[Int(bit)]] = "kb.\(key)" }
        preferences.set(Dictionary(uniqueKeysWithValues: keyMap.map { (String($0.key), Int($0.value)) }), forKey: "Studio.Player.keys")
        preferences.set(keyNames, forKey: "Studio.Player.keyNames")
    }
    private func alert(_ title: String, _ text: String) { let alert = NSAlert(); alert.messageText = title; alert.informativeText = text; if let window { alert.beginSheetModal(for: window) } }
    func prepareToQuit() -> Bool { closed || overlay.coreError != nil || !paused || commitSlot(-1) }
    func windowWillClose(_ notification: Notification) { shutdown() }
    private func shutdown() {
        guard !closed else { return }
        if paused && overlay.coreError == nil { _ = commitSlot(-1) }
        checkpointBattery(); closed = true
        if let eventMonitor { NSEvent.removeMonitor(eventMonitor); self.eventMonitor = nil }
        timer?.invalidate(); timer = nil
        if CommandLine.arguments.contains("--player-metrics"), metricsStart > 0 { print("PLAYER_METRICS frames=\(frameNumber) seconds=\(ProcessInfo.processInfo.systemUptime - metricsStart) speed=\(effectiveSpeed)") }
        engine.stop(); audioCore.silenceAndDetach()
        if let core { studio_flush_save(core); studio_destroy(core) }; core = nil
        for observer in observers { NotificationCenter.default.removeObserver(observer) }; observers.removeAll()
    }
    deinit { shutdown() }
    func mtkView(_ view: MTKView, drawableSizeWillChange size: CGSize) { view.draw() }
    func draw(in view: MTKView) {
        guard let core, let pixels = studio_pixels(core), let device = view.device, let drawable = view.currentDrawable, let pass = view.currentRenderPassDescriptor, let command = queue.makeCommandBuffer() else { return }
        let width = Int(studio_width(core)), height = Int(studio_height(core))
        guard width > 0, height > 0 else { return }
        if texture?.width != width || texture?.height != height {
            let descriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .rgba8Unorm, width: width, height: height, mipmapped: false)
            descriptor.usage = .shaderRead; descriptor.storageMode = .shared
            texture = device.makeTexture(descriptor: descriptor)
        }
        texture?.replace(region: MTLRegionMake2D(0, 0, width, height), mipmapLevel: 0, withBytes: pixels, bytesPerRow: width * 4)
        guard let encoder = command.makeRenderCommandEncoder(descriptor: pass) else { return }
        let game = overlay.settings.display.presentationSize(native: CGSize(width: width,height: height), screen: view.drawableSize)
        let viewport = displayMode == 2 ? FillGeometry.viewport(screen: view.drawableSize, game: game, percent: overlay.settings.display.fillPercent) : PlaybackLayout.viewport(screen: view.drawableSize, game: game, mode: displayMode)
        guard !viewport.isEmpty else { encoder.endEncoding(); return }
        encoder.setViewport(MTLViewport(originX: viewport.minX, originY: viewport.minY, width: viewport.width, height: viewport.height, znear: 0, zfar: 1))
        encoder.setRenderPipelineState(pipeline); encoder.setFragmentTexture(texture, index: 0)
        var mode = shaderMode; encoder.setFragmentBytes(&mode, length: 4, index: 0)
        let c = overlay.settings.display.colour
        let tint = SessionOverlay.colour(c.scanline.colour).usingColorSpace(.deviceRGB)!
        var correction: [Float] = [Float(c.rgbShift[0]/255), Float(c.rgbShift[1]/255), Float(c.rgbShift[2]/255), Float(max(0.01,c.gamma)), Float(c.brightness), Float(c.contrast), Float(c.saturation), Float(c.scanline.on ? c.scanline.intensity : 0), Float(tint.redComponent), Float(tint.greenComponent), Float(tint.blueComponent), compare ? 1 : 0, Float(view.drawableSize.width/2)]
        encoder.setFragmentBytes(&correction, length: correction.count * 4, index: 1)
        encoder.setFragmentTexture(compareTexture ?? texture, index: 1)
        encoder.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
        encoder.endEncoding(); command.present(drawable); command.commit()
        // The shared texture cannot be overwritten by the next CPU frame until Metal finishes reading it.
        command.waitUntilCompleted()
    }
    private static var scanlineSource: String {
        if let url = Bundle.main.url(forResource: "scanline", withExtension: "metal", subdirectory: "overlay"), let source = try? String(contentsOf: url, encoding: .utf8) { return source + "\n" }
        return "#include <metal_stdlib>\nusing namespace metal;\nfloat3 crispyScanline(float3 c,float y,float i,float3 t) { return uint(y)%2 == 1 ? mix(c,t,i) : c; }\n"
    }
    private static let shaderSource = """
    #include <metal_stdlib>
    using namespace metal;
    struct V { float4 position [[position]]; float2 uv; };
    vertex V screenVertex(uint id [[vertex_id]]) {
        float2 p = float2((id << 1) & 2, id & 2);
        V out; out.position = float4(p * float2(2,-2) + float2(-1,1),0,1); out.uv = p; return out;
    }
    fragment float4 screenFragment(V in [[stage_in]], texture2d<float> tex [[texture(0)]], constant uint &mode [[buffer(0)]], constant float *cfx [[buffer(1)]], texture2d<float> original [[texture(1)]]) {
        constexpr sampler nearestSampler(filter::nearest, address::clamp_to_edge);
        constexpr sampler linearSampler(filter::linear, address::clamp_to_edge);
        if(cfx[11] > 0 && in.position.x < cfx[12]) return float4(original.sample(nearestSampler, in.uv).rgb,1);
        float2 uv = in.uv;
        if (mode == 3) { float2 p = uv * 2 - 1; uv = (p * (1 + 0.045 * dot(p,p)) + 1) / 2; if(any(uv < 0) || any(uv > 1)) return float4(0,0,0,1); }
        float3 c = mode == 1 || mode == 3 ? tex.sample(linearSampler, uv).rgb : tex.sample(nearestSampler,uv).rgb;
        float2 size = float2(tex.get_width(), tex.get_height());
        if(mode == 2) { float2 cell = fract(uv * size); c *= (cell.x < .12 || cell.y < .12) ? .73 : 1.04; }
        if(mode == 3) { float2 p = in.uv * 2 - 1; c *= 1 - .17 * dot(p,p); }
        c = clamp(c + float3(cfx[0],cfx[1],cfx[2]), 0.0, 1.0);
        c = pow(c, float3(1.0/cfx[3])); c = ((c - .5) * cfx[5] + .5) * cfx[4];
        c = mix(float3(dot(c, float3(.2126,.7152,.0722))), c, cfx[6]);
        c = crispyScanline(c,uv.y*size.y,cfx[7],float3(cfx[8],cfx[9],cfx[10]));
        return float4(clamp(c,0.0,1.0),1);
    }
    """
}
