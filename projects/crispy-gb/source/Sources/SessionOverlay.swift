import SwiftUI
import AppKit

final class SessionOverlayState: ObservableObject {
    @Published var settings = SessionSettings() { didSet { changed?(settings) } }
    @Published var visible = false
    @Published var tab = "Session"
    @Published var preview = false
    @Published var draftFill = 1.0
    @Published var speed = 1.0
    @Published var volume = 0.8
    var changeSpeed: ((Double) -> Void)?
    var changeVolume: ((Double) -> Void)?
    var fullscreen: (() -> Void)?
    var reset: (() -> Void)?
    @Published var slots = ["Empty", "Empty", "Empty"]
    @Published var battery = ""
    @Published var coreLabel = ""
    @Published var coreError: String?
    @Published var hasRecovery = false
    var loadRecovery: (() -> Void)?
    @Published var controller = "● No controller"
    @Published var devices: [String] = []
    @Published var controllerCount = 0
    @Published var capturing: String?
    @Published var keyboardCapture: String?
    var nativeSize = CGSize(width: 160, height: 144)
    var changed: ((SessionSettings) -> Void)?
    var resume: (() -> Void)?
    var quit: (() -> Void)?
    var save: ((Int) -> Void)?
    var load: ((Int) -> Void)?
    var batteryLoad: (() -> Void)?
    var detect: (() -> Void)?
    var assignKey: ((String, NSEvent) -> Void)?
    var resetControls: (() -> Void)?
}
private struct GlassMaterial: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView(); view.material = .hudWindow; view.blendingMode = .withinWindow; view.state = .active
        return view
    }
    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {}
}
private final class CaptureView: NSButton {
    var assigned: ((NSEvent) -> Void)?
    var begin: (() -> Void)?
    override var acceptsFirstResponder: Bool { true }
    private func startCapture() { begin?(); title = "Press input…"; window?.makeFirstResponder(self) }
    override func mouseDown(with event: NSEvent) { startCapture() }
    override func accessibilityPerformPress() -> Bool { startCapture(); return true }
    override func keyDown(with event: NSEvent) { if !event.isARepeat { assigned?(event) } }
}
private struct KeyCapture: NSViewRepresentable {
    var title: String
    var capturing: Bool
    var begin: () -> Void
    var capture: (NSEvent) -> Void
    func makeNSView(context: Context) -> CaptureView { let b = CaptureView(); b.bezelStyle = .rounded; b.font = .systemFont(ofSize: 10); b.lineBreakMode = .byTruncatingTail; b.setContentCompressionResistancePriority(.defaultLow, for: .horizontal); b.setContentHuggingPriority(.defaultLow, for: .horizontal); return b }
    func updateNSView(_ view: CaptureView, context: Context) { view.title = capturing ? "Press input…" : title; view.begin = begin; view.assigned = capture }
}

struct SessionOverlay: View {
    @ObservedObject var state: SessionOverlayState
    @State private var offset = CGSize.zero
    @State private var dragStart = CGSize.zero
    @State private var safe = true
    @State private var confirmBattery = false
    private var accent: Color { CrispySettingsView.color(UserDefaults.standard.string(forKey: "CrispyGB.Accent") ?? "Green") }
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                if state.visible {
                    Color.black.opacity(0.4).ignoresSafeArea()
                    if state.preview { demo(size: geometry.size) }
                    else {
                        VStack(spacing: 10) {
                            HStack {
                                Picker("Tab", selection: $state.tab) { ForEach(["Session", "Display", "Controls"], id: \.self) { Text($0).tag($0) } }.pickerStyle(.segmented).labelsHidden()
                                Text(geometry.size.height < 420 ? "Ⅱ" : "▸ Paused").font(.caption).foregroundStyle(.secondary)
                            }.padding(.bottom, 5).contentShape(Rectangle())
                                .gesture(DragGesture().onChanged { offset = CGSize(width: dragStart.width + $0.translation.width, height: dragStart.height + $0.translation.height) }.onEnded { _ in dragStart = offset })
                            Divider()
                            ScrollView {
                                VStack(alignment: .leading, spacing: 12) {
                                    if state.tab == "Session" { session }
                                    else if state.tab == "Display" { display }
                                    else { controls }
                                }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 4)
                            }.id(state.tab)
                            Divider()
                            HStack {
                                Button("Resume") { state.resume?() }.buttonStyle(.borderedProminent).disabled(state.coreError != nil)
                                Spacer()
                                Button("Quit to Library") { state.quit?() }
                            }
                        }.padding(18)
                            .frame(width: min(geometry.size.height < 420 || geometry.size.width < 600 ? 360 : 480, geometry.size.width - 32), height: geometry.size.height < 420 ? 300 : 360)
                            .background(GlassMaterial())
                            .clipShape(RoundedRectangle(cornerRadius: 18))
                            .overlay(RoundedRectangle(cornerRadius: 18).stroke(.black.opacity(0.15), lineWidth: 2).blur(radius: 2).padding(1).clipShape(RoundedRectangle(cornerRadius: 18)))
                            .overlay(RoundedRectangle(cornerRadius: 18).stroke(.white.opacity(0.12), lineWidth: 1))
                            .shadow(color: .black.opacity(0.25), radius: 18, y: 8)
                            .offset(x: min(max(offset.width, -(geometry.size.width-360)/2), (geometry.size.width-360)/2), y: min(max(offset.height, -(geometry.size.height-300)/2), (geometry.size.height-300)/2))
                    }
                }
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
        }.tint(accent)
            .onChange(of: state.visible) { _, shown in if !shown { offset = .zero; dragStart = .zero } }
            .alert("Overwrite current state?", isPresented: $confirmBattery) {
                Button("Load latest", role: .destructive) { state.batteryLoad?() }
                Button("Cancel", role: .cancel) {}
            } message: { Text("Restart the game with the latest 30-second battery checkpoint. Unsaved progress in memory will be replaced.") }
    }
    private var session: some View {
        VStack(alignment: .leading, spacing: 12) {
            if !state.coreLabel.isEmpty { Text(state.coreLabel).font(.caption).foregroundStyle(.secondary) }
            if let issue = state.coreError { Text(issue).font(.caption).foregroundStyle(.orange) }
            ForEach(0..<3, id: \.self) { slot in
                HStack {
                    Text("S\(slot+1)").font(.headline)
                    Text(state.slots[slot]).font(.caption).lineLimit(2)
                    Spacer()
                    Button("Save") { state.save?(slot) }.disabled(state.coreError != nil)
                    Button("Load") { state.load?(slot) }.disabled(state.slots[slot] == "Empty")
                }
            }
            if state.hasRecovery { Button("Load quit recovery") { state.loadRecovery?() } }
            HStack {
                Picker("Speed", selection: Binding(get: { state.speed }, set: { state.changeSpeed?($0) })) {
                    ForEach([1.0,2.0,4.0,8.0], id: \.self) { Text("\(Int($0))×").tag($0) }
                }
                Button("Fullscreen") { state.fullscreen?() }
                Button("Reset") { state.reset?() }
            }
            HStack { Text("Volume").font(.caption); Slider(value: Binding(get: { state.volume }, set: { state.changeVolume?($0) }), in: 0...1) }
            Text("Battery · \(state.battery)").font(.caption)
            Button("Battery Load · Load latest…") { confirmBattery = true }
            HStack {
                Button("Colour →") { state.tab = "Display" }
                Button("Fit / Fill → Preview…") { beginPreview() }
            }
            Text("Esc / ⌘P / controller Menu to resume. Hold Option for original-left A/B.").font(.caption).foregroundStyle(.secondary)
        }
    }
    private func beginPreview() { state.draftFill = state.settings.display.fillPercent; state.preview = true }
    private var display: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Picker("Scale", selection: $state.settings.display.fitMode) {
                    Text("Fit").tag("fit"); Text("Fill").tag("fill"); Text("Integer").tag("integer")
                }.pickerStyle(.segmented)
                Button("Preview…") { beginPreview() }
            }
            Picker("Filter", selection: Binding(get: { state.settings.display.filter }, set: { filter in
                var display = state.settings.display; display.filter = filter
                if filter == "scanline" { display.colour.scanline.on = true }
                state.settings.display = display
            })) {
                Text("None").tag("none"); Text("CRT").tag("crt"); Text("Scanline").tag("scanline"); Text("Smooth").tag("smooth"); Text("LCD").tag("lcd")
            }
            Picker("Aspect", selection: $state.settings.display.aspectLock) {
                Text("Native").tag("native"); Text("4:3").tag("4:3"); Text("16:9").tag("16:9"); Text("Free").tag("free")
            }
            HStack { Text("Colour").font(.headline); Spacer(); Button("Reset all") { state.settings.display.colour = ColourSettings() } }
            ForEach(0..<3, id: \.self) { index in
                slider(["Red", "Green", "Blue"][index], value: Binding(get: { state.settings.display.colour.rgbShift[index] }, set: { state.settings.display.colour.rgbShift[index] = $0 }), range: 0...255, defaultValue: 0, percent: false)
            }
            ColorPicker("Combined tint wheel", selection: Binding(get: {
                let rgb = state.settings.display.colour.rgbShift
                return Color(red: rgb[0]/255, green: rgb[1]/255, blue: rgb[2]/255)
            }, set: { colour in
                if let c = NSColor(colour).usingColorSpace(.deviceRGB) { state.settings.display.colour.rgbShift = [c.redComponent*255, c.greenComponent*255, c.blueComponent*255] }
            }), supportsOpacity: false)
            slider("Gamma", value: $state.settings.display.colour.gamma)
            slider("Brightness", value: $state.settings.display.colour.brightness)
            slider("Contrast", value: $state.settings.display.colour.contrast)
            slider("Saturation", value: $state.settings.display.colour.saturation)
            Toggle("Scanlines", isOn: $state.settings.display.colour.scanline.on)
            slider("Intensity", value: $state.settings.display.colour.scanline.intensity, range: 0...1, defaultValue: 0.15)
            HStack {
                ForEach(["#333333", "#382710", "#1a1a2e", "off"], id: \.self) { hex in
                    Button(hex == "off" ? "Off" : hex == "#333333" ? "Grey" : hex == "#382710" ? "Amber" : "Blue") {
                        state.settings.display.colour.scanline.on = hex != "off"
                        if hex != "off" { state.settings.display.colour.scanline.colour = hex }
                    }
                }
                ColorPicker("Custom", selection: Binding(get: { Color(nsColor: Self.colour(state.settings.display.colour.scanline.colour)) }, set: { color in
                    if let c = NSColor(color).usingColorSpace(.deviceRGB) {
                        state.settings.display.colour.scanline.colour = String(format: "#%02x%02x%02x", Int(c.redComponent*255), Int(c.greenComponent*255), Int(c.blueComponent*255)); state.settings.display.colour.scanline.on = true
                    }
                }), supportsOpacity: false)
            }.font(.system(size: 10)).fixedSize(horizontal: false, vertical: true)
            HStack {
                Button("Crispy") { state.settings.display.colour = .crispy }
                ForEach(0..<3, id: \.self) { slot in
                    Menu("P\(slot+1)") {
                        Button("Store current") { state.settings.display.presets[slot] = state.settings.display.colour }
                        Button("Recall") { if let saved = state.settings.display.presets[slot] { state.settings.display.colour = saved } }.disabled(state.settings.display.presets[slot] == nil)
                    }
                }
            }
        }
    }
    private func slider(_ name: String, value: Binding<Double>, range: ClosedRange<Double> = 0...2, defaultValue: Double = 1, percent: Bool = true) -> some View {
        HStack {
            Text(name).frame(width: 75, alignment: .leading)
            Slider(value: value, in: range).accessibilityLabel(name)
            Text("\(Int(value.wrappedValue * (percent ? 100 : 1)))\(percent ? "%" : "")").monospacedDigit().frame(width: 45)
            Button("↺") { value.wrappedValue = defaultValue }.help("Reset \(name)")
        }.font(.caption)
    }
    private var controls: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack { Text(state.controller).font(.caption).help("Event-to-poll delay; excludes controller hardware and transmission latency.").foregroundStyle(state.controllerCount > 0 ? .green : .secondary); Spacer(); Button("Detect") { state.detect?() } }
            if state.controllerCount > 1 {
                Picker("Controller slot", selection: $state.settings.controls.controllerSlot) {
                    ForEach(0..<state.controllerCount, id: \.self) { Text("Controller \($0+1)").tag($0) }
                }
            }
            ForEach(state.devices, id: \.self) { Text($0).font(.caption).foregroundStyle(.secondary) }
            Text("Gamepad · click a button, then press a controller input").font(.caption)
            VStack(spacing: 8) {
                HStack { pad("L"); Spacer(); pad("R") }
                HStack {
                    VStack { pad("Up"); HStack { pad("Left"); pad("Down"); pad("Right") } }
                    Spacer(); pad("B"); pad("A")
                }
                HStack { Spacer(); pad("Select"); pad("Start"); Spacer() }
            }.padding(8).frame(height: 120).background(.primary.opacity(0.06), in: RoundedRectangle(cornerRadius: 24))
            if let action = state.capturing { Text("Press any controller button for \(action)…").font(.caption); Button("Cancel capture") { state.capturing = nil } }
            Text("Keyboard · click then press a key").font(.caption)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 5)) {
                ForEach(["Up", "Down", "Left", "Right", "A", "B", "Select", "Start", "L", "R"], id: \.self) { action in
                    KeyCapture(title: "\(action): \(keyLabel(action))", capturing: state.keyboardCapture == action, begin: { state.keyboardCapture = action }) { event in state.assignKey?(action, event); state.keyboardCapture = nil }.frame(height: 28)
                }
            }
            Button("Reset to default") { state.resetControls?() }.buttonStyle(.link)
        }
    }
    private func pad(_ action: String) -> some View { Button(action) { state.capturing = action }.buttonStyle(.bordered).controlSize(.small) }
    private func demo(size: CGSize) -> some View {
        let game = state.nativeSize
        let presentation = state.settings.display.presentationSize(native: game, screen: size)
        let viewport = FillGeometry.viewport(screen: size, game: presentation, percent: state.draftFill)
        let crop = state.settings.display.previewCrop(native: game, screen: size, percent: state.draftFill)
        let safeRect = state.settings.display.previewSafeZone(native: game, percent: state.draftFill)
        return ZStack(alignment: .bottom) {
            Color.black
            Canvas { context, _ in
                context.clip(to: Path(CGRect(origin: .zero, size: size)))
                let scale = viewport.width / game.width
                let scaleY = viewport.height / game.height
                // Native-resolution checkerboard and labelled edge markers are a demo, never ROM pixels.
                for y in stride(from: 0, to: Int(game.height), by: 8) {
                    for x in stride(from: 0, to: Int(game.width), by: 8) {
                        let r = CGRect(x: viewport.minX + Double(x)*scale, y: viewport.minY + Double(y)*scaleY, width: 8*scale, height: 8*scaleY)
                        context.fill(Path(r), with: .color((x/8+y/8)%2 == 0 ? .gray.opacity(0.45) : .gray.opacity(0.25)))
                    }
                }
                context.stroke(Path(viewport.insetBy(dx: scale, dy: scaleY)), with: .color(.orange), lineWidth: 2*scale)
                for (label, point) in [("LEFT", CGPoint(x: viewport.minX+12*scale,y:viewport.midY)), ("RIGHT", CGPoint(x:viewport.maxX-16*scale,y:viewport.midY)), ("TOP", CGPoint(x:viewport.midX,y:viewport.minY+8*scaleY)), ("BOTTOM", CGPoint(x:viewport.midX,y:viewport.maxY-8*scaleY))] {
                    context.draw(Text(label).font(.system(size: 5*scale, weight: .bold)).foregroundColor(.white), at: point)
                }
                if safe {
                    let rect = CGRect(x: viewport.minX + safeRect.minX*scale, y: viewport.minY + safeRect.minY*scaleY, width: safeRect.width*scale, height: safeRect.height*scaleY)
                    context.fill(Path(rect), with: .color(.green.opacity(0.18)))
                    context.stroke(Path(rect), with: .color(.green), lineWidth: 2)
                }
            }
            VStack(spacing: 8) {
                Text("Fill preview · \(Int(game.width)) × \(Int(game.height)) native pixels").font(.headline)
                HStack { Text("0% Fit"); Slider(value: $state.draftFill, in: 0...1); Text("\(Int(state.draftFill*100))% Fill") }
                Text(String(format: "cropping %.1f px L / %.1f px R · %.1f px T / %.1f px B", crop.width, crop.width, crop.height, crop.height)).font(.caption).monospacedDigit()
                Toggle("Safe zone · 16:9 / 16:10 / 21:9", isOn: $safe)
                HStack {
                    Button("Cancel") { state.preview = false }.keyboardShortcut(.cancelAction)
                    Spacer()
                    Button("Confirm") { var display = state.settings.display; display.fillPercent = state.draftFill; display.fitMode = "fill"; state.settings.display = display; state.preview = false; state.resume?() }.buttonStyle(.borderedProminent)
                }
            }.padding(16).frame(maxWidth: 480).background(GlassMaterial()).clipShape(RoundedRectangle(cornerRadius: 18)).padding(20)
        }.clipped()
    }
    private func keyLabel(_ action: String) -> String {
        guard let input = state.settings.controls.overrides[action] else { return Self.defaultLabels[action] ?? "—" }
        if input.hasPrefix("ctrl.") { return "pad" }
        let token = String(input.dropFirst(3))
        let names = ["6":"Z", "7":"X", "0":"A", "1":"S", "2":"D", "3":"F", "4":"H", "5":"G", "8":"C", "9":"V", "11":"B", "12":"Q", "13":"W", "14":"E", "15":"R", "16":"Y", "17":"T", "31":"O", "32":"U", "34":"I", "35":"P", "37":"L", "38":"J", "40":"K", "45":"N", "46":"M", "36":"↵", "51":"⌫", "53":"Esc", "49":"Space", "123":"←", "124":"→", "125":"↓", "126":"↑"]
        return names[token] ?? token
    }
    private static let defaultLabels = ["A":"X", "B":"Z", "Select":"⌫", "Start":"↵", "Up":"↑", "Down":"↓", "Left":"←", "Right":"→", "L":"A", "R":"S"]
    static func colour(_ hex: String) -> NSColor {
        let n = UInt32(hex.replacingOccurrences(of: "#", with: ""), radix: 16) ?? 0x1a1a2e
        return NSColor(red: Double((n >> 16)&255)/255, green: Double((n >> 8)&255)/255, blue: Double(n&255)/255, alpha: 1)
    }
}
