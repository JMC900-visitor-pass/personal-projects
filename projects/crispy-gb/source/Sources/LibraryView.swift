import SwiftUI
import AppKit

struct LibraryView: View {
    @ObservedObject var model: LibraryModel
    var onPlay: (Game) -> Void
    var onExport: (Game) -> Void
    var onRemove: (Game) -> Void
    @State private var category = "All Games"
    @State private var search = ""
    @State private var selected: String?
    @State private var coverGame: Game?
    @State private var settings = false
    @FocusState private var searchFocused: Bool
    @AppStorage("CrispyGB.Theme") private var theme = "Dark"
    @AppStorage("CrispyGB.Accent") private var accent = "Green"
    @AppStorage("CrispyGB.Artwork") private var artwork = "Libretro"
    private let categories = ["All Games", "GB", "GBC", "GBA", "Favorites", "Hidden"]
    private var accentColor: Color { CrispySettingsView.color(accent) }
    var baseFiltered: [Game] {
        model.games.filter { game in
            ["GB", "GBC", "GBA"].contains(game.platform) &&
            (category == "Hidden" ? game.hidden == true : game.hidden != true) &&
            (category == "All Games" || category == "Hidden" || category == game.platform || (category == "Favorites" && game.favorite)) &&
            LibrarySearch.matches(search, game: game)
        }.sorted { $0.title.localizedStandardCompare($1.title) == .orderedAscending }
    }
    var filtered: [Game] { baseFiltered.filter { model.matchesCover($0, filter: model.coverFilter) } }
    var body: some View {
        let statuses = baseFiltered.map { model.coverStatus($0) }
        let counts = Dictionary(uniqueKeysWithValues: CoverStatus.allCases.map { filter in
            (filter, statuses.filter { filter == .all || (filter == .covers ? $0 == .covers || $0 == .stale : $0 == filter) }.count)
        })
        NavigationSplitView {
            VStack(alignment: .leading, spacing: 18) {
                Text(CoreIdentity.experimental ? "Crispy Core" : "Crispy GB").font(.system(size: 28, weight: .heavy, design: .rounded)).padding(18)
                List(categories, id: \.self, selection: $category) { item in
                    Label(item, systemImage: item == "Hidden" ? "eye.slash" : item == "Favorites" ? "star" : "square.grid.2x2")
                        .padding(.vertical, 4)
                        .overlay(alignment: .bottom) { if category == item { Rectangle().fill(accentColor).frame(height: 2) } }
                        .tag(item)
                }.listStyle(.sidebar).frame(height: 260)
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 6) {
                    ForEach(CoverStatus.allCases, id: \.self) { filter in
                        Button("\(filter.rawValue) (\(counts[filter] ?? 0))") { model.coverFilter = filter }
                            .font(.system(size: 10)).lineLimit(1).minimumScaleFactor(0.8).buttonStyle(.bordered).tint(model.coverFilter == filter ? accentColor : .secondary)
                    }
                }.padding(.horizontal, 12)
                Spacer()
                Button("Settings…", systemImage: "gearshape") { settings = true }.padding(18)
            }.navigationSplitViewColumnWidth(min: 180, ideal: 205, max: 240)
        } detail: {
            VStack(spacing: 0) {
                if CoreIdentity.experimental {
                    HStack {
                        Text("Independent core preview · GB / GBC / GBA bring-up · compatibility and audio incomplete").font(.caption)
                        Spacer()
                        Button("Original demos") { if let url = Bundle.main.resourceURL?.appendingPathComponent("CoreDemos") { NSWorkspace.shared.activateFileViewerSelecting([url]) } }
                    }.padding(10).background(Color.orange.opacity(0.12))
                }
                HStack(spacing: 12) {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField("Search games, authors or genres", text: $search).textFieldStyle(.plain).focused($searchFocused).accessibilityLabel("Search library")
                    if !search.isEmpty { Button { search = "" } label: { Image(systemName: "xmark.circle.fill") }.buttonStyle(.plain).accessibilityLabel("Clear search") }
                    Text("⌃K").font(.caption).foregroundStyle(.secondary)
                    Button("Add ROMs", systemImage: "plus") { model.chooseROMs() }.buttonStyle(.borderedProminent).disabled(model.busy)
                }.padding(18)
                Divider()
                HStack(spacing: 0) {
                    VStack(alignment: .leading, spacing: 16) {
                        HStack { Text(category).font(.title.bold()); Text("\(filtered.count) games").foregroundStyle(.secondary); Spacer() }
                        if model.coverFilter == .missing {
                            Button("Fetch missing (\(filtered.count))") { model.fetchMissing(filtered) }.disabled(model.fetchingMissing || filtered.isEmpty)
                        }
                        if model.fetchingMissing { ProgressView(value: model.coverProgress) }
                        if !model.coverBanner.isEmpty { Text(model.coverBanner).font(.caption).foregroundStyle(.secondary) }
                        if filtered.isEmpty {
                            ContentUnavailableView(model.coverFilter == .missing ? "No missing covers" : model.coverFilter == .stale ? "No stale covers" : search.isEmpty ? "No games here yet" : "No matching games", systemImage: "externaldrive",
                                description: Text(model.coverFilter == .missing ? "Every matching title has cached artwork." : model.coverFilter == .stale ? "No matching cached artwork has changed ROM metadata." : search.isEmpty ? "Add or drop .gb, .gbc and .gba files to start your library." : "Try another name, author or genre."))
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                        } else {
                            ScrollViewReader { proxy in
                            ScrollView {
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 155, maximum: 210), spacing: 18)], spacing: 22) {
                                    ForEach(filtered) { game in card(game).id(game.id) }
                                }.padding(3)
                            }.onChange(of: model.coverFilter) { _, _ in
                                if let first = filtered.first { selected = first.id; proxy.scrollTo(first.id, anchor: .top) }
                            }
                            }
                        }
                        ForEach(model.removals) { removal in
                            HStack {
                                Text("Crispy GB – removed \(removal.game.title)").lineLimit(1)
                                Spacer()
                                Button("Undo") { model.undoRemoval(removal) }
                            }.padding(10).background(accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
                        }
                        Text(model.status.isEmpty ? "ROMs stay local · Drop .gb, .gbc or .gba files to add" : model.status).font(.caption).foregroundStyle(.secondary)
                    }.padding(22).frame(maxWidth: .infinity, maxHeight: .infinity)
                    if let game = filtered.first(where: { $0.id == selected }) {
                        Divider()
                        details(game).frame(width: 230).padding(20)
                    }
                }
            }.background(Color(nsColor: .windowBackgroundColor))
                .onDrop(of: ["public.file-url"], isTargeted: nil) { providers in
                    Task {
                        var urls: [URL] = []
                        for provider in providers {
                            let url: URL? = await withCheckedContinuation { continuation in
                                _ = provider.loadObject(ofClass: URL.self) { url, _ in continuation.resume(returning: url) }
                            }
                            if let url { urls.append(url) }
                        }
                        model.importURLs(urls)
                    }
                    return true
                }
        }
        .tint(accentColor)
        .preferredColorScheme(theme == "Light" ? .light : .dark)
        .onChange(of: theme) { _, value in NSApp.appearance = NSAppearance(named: value == "Light" ? .aqua : .darkAqua) }
        .onReceive(NotificationCenter.default.publisher(for: Notification.Name("CrispyGB.FocusSearch"))) { _ in settings = false; coverGame = nil; searchFocused = true }
        .onReceive(NotificationCenter.default.publisher(for: Notification.Name("CrispyGB.Settings"))) { _ in settings = true }
        .sheet(isPresented: $settings) { CrispySettingsView(model: model) }
        .sheet(item: $coverGame) { game in CoverSearchView(model: model, game: game) }
        .alert("Crispy GB", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
            Button("OK") { model.error = nil }
        } message: { Text(model.error ?? "") }
    }
    func card(_ game: Game) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            Button { selected = game.id } label: {
                CoverArt(model: model, game: game).frame(height: 175).clipShape(RoundedRectangle(cornerRadius: 10))
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(selected == game.id ? accentColor : .secondary.opacity(0.2), lineWidth: selected == game.id ? 3 : 1))
            }.buttonStyle(.plain).simultaneousGesture(TapGesture(count: 2).onEnded { onPlay(game) })
            Text(game.title).font(.headline).lineLimit(2).frame(height: 36, alignment: .topLeading)
            HStack {
                Text(game.platform).font(.caption.bold()).foregroundStyle(accentColor)
                Spacer()
                Button { model.toggleHidden(game) } label: { Image(systemName: game.hidden == true ? "eye" : "eye.slash") }
                    .help(game.hidden == true ? "Unhide game" : "Hide game").accessibilityLabel(game.hidden == true ? "Unhide \(game.title)" : "Hide \(game.title)")
                Button { onRemove(game) } label: { Image(systemName: "trash") }
                    .help("Remove game · Undo available for 5 seconds").accessibilityLabel("Remove \(game.title)")
            }.buttonStyle(.borderless)
        }.contextMenu {
            Button("Play") { onPlay(game) }
            Button(game.favorite ? "Remove Favorite" : "Favorite") { model.toggleFavorite(game) }
            Button("Find Cover…") { coverGame = game }
            Button("Remove cached cover") { model.removeCover(game) }.disabled(model.coverURL(for: game) == nil)
            Button("Export Standalone App…") { onExport(game) }
        }.task(id: "\(game.id)-\(artwork)") { if model.coverFilter != .missing { await model.fetchCover(for: game) } }
    }
    func details(_ game: Game) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                CoverArt(model: model, game: game).frame(height: 210)
                TextField("Title", text: textBinding(game, keyPath: \.title)).font(.title2.bold()).textFieldStyle(.plain)
                Text(game.platform == "GBA" ? "Game Boy Advance" : game.platform == "GBC" ? "Game Boy Color" : "Game Boy").foregroundStyle(.secondary)
                Button("Play Game", systemImage: "play.fill") { onPlay(game) }.buttonStyle(.borderedProminent)
                Button(game.favorite ? "Remove Favorite" : "Add Favorite", systemImage: "star") { model.toggleFavorite(game) }
                Button(game.hidden == true ? "Unhide Game" : "Hide Game", systemImage: "eye") { model.toggleHidden(game) }
                Button("Remove Game", systemImage: "trash") { onRemove(game) }
                Divider()
                TextField("Author (optional)", text: optionalBinding(game, keyPath: \.author))
                TextField("Genre (optional)", text: optionalBinding(game, keyPath: \.genre))
                Button("Find Cover…", systemImage: "photo") { coverGame = game }
                Button("Export Standalone App…", systemImage: "square.and.arrow.up") { onExport(game) }
                Button("Show Save Folder", systemImage: "folder") { NSWorkspace.shared.open(model.saveDirectory(for: game)) }
                if let source = game.sourceURL, let url = URL(string: source), CoverProjectClient.isProviderURL(url) || LibretroArtwork.isSourceURL(url) {
                    Link(LibretroArtwork.isSourceURL(url) ? "Cover · Libretro" : "Cover · The Cover Project", destination: url).font(.caption)
                }
            }.buttonStyle(.borderless)
        }
    }
    func textBinding(_ game: Game, keyPath: WritableKeyPath<Game, String>) -> Binding<String> {
        Binding(get: { model.games.first { $0.id == game.id }?[keyPath: keyPath] ?? game[keyPath: keyPath] }, set: { value in
            if var current = model.games.first(where: { $0.id == game.id }) { current[keyPath: keyPath] = value; model.update(current) }
        })
    }
    func optionalBinding(_ game: Game, keyPath: WritableKeyPath<Game, String?>) -> Binding<String> {
        Binding(get: { model.games.first { $0.id == game.id }?[keyPath: keyPath] ?? "" }, set: { value in
            if var current = model.games.first(where: { $0.id == game.id }) { current[keyPath: keyPath] = value; model.update(current) }
        })
    }
}

struct CoverArt: View {
    @ObservedObject var model: LibraryModel
    let game: Game
    var body: some View {
        ZStack {
            Color(nsColor: .controlBackgroundColor)
            if let url = model.coverURL(for: game), let image = NSImage(contentsOf: url) {
                Image(nsImage: image).resizable().scaledToFit().padding(6)
            } else {
                VStack(spacing: 12) { Image(systemName: "externaldrive.fill").font(.system(size: 48)); Text(game.platform).font(.caption.bold()) }
                    .foregroundStyle(.secondary).accessibilityLabel("Game cartridge placeholder")
            }
        }.frame(maxWidth: .infinity)
    }
}

struct CrispySettingsView: View {
    @ObservedObject var model: LibraryModel
    @Environment(\.dismiss) var dismiss
    @AppStorage("CrispyGB.Theme") private var theme = "Dark"
    @AppStorage("CrispyGB.Accent") private var accent = "Green"
    @AppStorage("CrispyGB.ImportPath") private var importPath = ""
    @AppStorage("CrispyGB.Artwork") private var artwork = "Libretro"
    static func color(_ name: String) -> Color {
        switch name { case "Red": return .red; case "Blue": return .blue; case "Yellow": return .yellow; case "Purple": return .purple; default: return .green }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            HStack { Text("Crispy GB Settings").font(.title2.bold()); Spacer(); Button("Done") { dismiss() } }
            Picker("Appearance", selection: $theme) { Text("Dark").tag("Dark"); Text("Light").tag("Light") }.pickerStyle(.segmented)
            Text("Accent colour").font(.headline)
            HStack(spacing: 16) {
                ForEach(["Red", "Blue", "Green", "Yellow", "Purple"], id: \.self) { name in
                    Button { accent = name } label: {
                        Circle().fill(Self.color(name)).frame(width: 30, height: 30)
                            .overlay { if accent == name { Image(systemName: "checkmark").foregroundStyle(name == "Yellow" ? .black : .white) } }
                    }.buttonStyle(.plain).accessibilityLabel("\(name) accent").help(name)
                }
            }
            HStack {
                Text("Import folder").font(.headline); Spacer()
                Button("Choose…") {
                    let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false
                    if panel.runModal() == .OK, let url = panel.url { importPath = url.path }
                }
            }
            Text(importPath.isEmpty ? "Last used folder" : importPath).font(.caption).textSelection(.enabled)
            Text("Library: \(model.root.path)").font(.caption).textSelection(.enabled)
            Picker("Artwork source", selection: $artwork) { Text("Libretro").tag("Libretro"); Text("The Cover Project").tag("The Cover Project") }
            Text("ROM files remain local. Downloaded artwork is cached on your Mac.").font(.caption).foregroundStyle(.secondary)
        }.padding(26).frame(width: 460).tint(Self.color(accent)).preferredColorScheme(theme == "Light" ? .light : .dark)
    }
}

struct CoverSearchView: View {
    @ObservedObject var model: LibraryModel
    let game: Game
    @Environment(\.dismiss) var dismiss
    @State private var query = ""
    @State private var results: [CoverCandidate] = []
    @State private var busy = false
    @State private var message = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack { Text("Find a Cover").font(.title2.bold()); Spacer(); Button("Done") { dismiss() } }
            Text("Search \(model.artworkProvider) for \(game.platform) artwork. Unmatched games keep their cartridge placeholder.").foregroundStyle(.secondary)
            HStack { TextField("Game title", text: $query).onSubmit { search() }; Button("Find Cover") { search() }.disabled(busy || query.isEmpty) }
            Text(busy ? "Looking up artwork…" : message).font(.caption).foregroundStyle(.secondary)
            List(results) { result in
                HStack {
                    VStack(alignment: .leading) { Text(result.title); Link("Artwork source", destination: result.pageURL).font(.caption) }
                    Spacer(); Button("Use Cover") { apply(result) }.disabled(busy)
                }
            }
        }.padding(24).frame(width: 560, height: 400).onAppear { query = game.title; search() }
    }
    func search() {
        guard !busy else { return }
        busy = true; message = ""
        Task {
            do { results = try await model.searchCovers(query, platform: game.platform); if results.isEmpty { message = "No cover found. Try a shorter title." } }
            catch { results = []; message = "Artwork lookup is unavailable. Your placeholder will remain." }
            busy = false
        }
    }
    func apply(_ candidate: CoverCandidate) {
        busy = true
        Task {
            do { try await model.applyCandidate(candidate, to: game); dismiss() }
            catch { message = "Could not fetch this cover. Please try again later." }
            busy = false
        }
    }
}
