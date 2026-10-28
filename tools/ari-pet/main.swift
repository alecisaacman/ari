// Desktop pets: a small character that lives on top of the desktop, apart from its app.
// One program, one character per app bundle: ARI's owl reads ~/ARI/state/pet-status.json
// (written by ARI's poller); Claude's golden retriever reads Claude's local session files.
// Neither calls a model or an API. Drag a pet anywhere: it leans, flaps or paddles, and
// dangles with the drag. Click it to open its app; hover for a status line.
import AppKit
import SwiftUI

enum Mood { case idle, thinking, alert, asleep, outOfCredits, offline }
enum DragPose { case none, left, right, up, down }
enum Character { case owl, retriever }

struct Reading {
    var mood: Mood
    var summary: String
    // A new message worth saying: an id that changes when there is something new, and its text.
    var newsID: String?
    var news: String?
}

func lateNight() -> Bool {
    let hour = Calendar.current.component(.hour, from: Date())
    return hour >= 23 || hour < 6
}

func parseDate(_ raw: String) -> Date? {
    let iso = ISO8601DateFormatter()
    iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return iso.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
}

// MARK: - ARI's status

struct AriStatus: Decodable {
    let updatedAt: String
    let paused: Bool
    let thinking: Bool
    let outOfCredits: Bool
    let budgetUsedUp: Bool
    let spend: String
    let needsYou: Int
    let latest: String?
}

let ariHome = URL(fileURLWithPath: ProcessInfo.processInfo.environment["ARI_HOME"] ?? NSHomeDirectory() + "/ARI")
// The poller writes every 10 seconds while the Mac is awake; older than this means ARI isn't running.
let ariStaleAfter: TimeInterval = 180

func readAri() -> Reading {
    let url = ariHome.appendingPathComponent("state/pet-status.json")
    guard let data = try? Data(contentsOf: url), let status = try? JSONDecoder().decode(AriStatus.self, from: data) else {
        return Reading(mood: .offline, summary: "ARI isn't running. Its status file is missing.")
    }
    let fresh = Date().timeIntervalSince(parseDate(status.updatedAt) ?? .distantPast) < ariStaleAfter
    let news = status.latest
    if !fresh {
        return Reading(mood: .offline, summary: "ARI hasn't checked in for a few minutes. Is the Mac asleep?", newsID: news, news: news)
    }
    if status.outOfCredits || status.budgetUsedUp {
        let summary = status.budgetUsedUp ? "Out of budget: \(status.spend). Say \"ARI budget\" to raise it." : "Out of Anthropic credits. Top up to wake me."
        return Reading(mood: .outOfCredits, summary: summary, newsID: news, news: news)
    }
    if status.thinking { return Reading(mood: .thinking, summary: "Thinking about your message...", newsID: news, news: news) }
    if status.paused { return Reading(mood: .asleep, summary: "Paused. Say \"ARI resume\" when you want me.", newsID: news, news: news) }
    if status.needsYou > 0 {
        let things = status.needsYou == 1 ? "thing needs" : "things need"
        return Reading(mood: .alert, summary: "\(status.needsYou) \(things) you. Click to open the hub.", newsID: news, news: news)
    }
    if lateNight() { return Reading(mood: .asleep, summary: "Resting. Text me if you need anything.", newsID: news, news: news) }
    return Reading(mood: .idle, summary: "All quiet. \(status.spend).", newsID: news, news: news)
}

// MARK: - Claude's status

let claudeProjects = URL(fileURLWithPath: NSHomeDirectory() + "/.claude/projects")
let claudeBundleID = "com.anthropic.claudefordesktop"

// The newest Claude session file, and its most recent reply.
func latestClaudeSession() -> (url: URL, modified: Date)? {
    let manager = FileManager.default
    guard let projects = try? manager.contentsOfDirectory(at: claudeProjects, includingPropertiesForKeys: nil) else { return nil }
    var best: (URL, Date)?
    for project in projects {
        guard let files = try? manager.contentsOfDirectory(at: project, includingPropertiesForKeys: [.contentModificationDateKey]) else { continue }
        for file in files where file.pathExtension == "jsonl" {
            let modified = (try? file.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            if best == nil || modified > best!.1 { best = (file, modified) }
        }
    }
    return best.map { (url: $0.0, modified: $0.1) }
}

struct ClaudeTurn {
    let id: String
    let finished: Bool
    let text: String
    let at: Date
    let limited: Bool
}

func lastClaudeTurn(in url: URL) -> ClaudeTurn? {
    guard let handle = try? FileHandle(forReadingFrom: url) else { return nil }
    defer { try? handle.close() }
    let size = (try? handle.seekToEnd()) ?? 0
    try? handle.seek(toOffset: size > 300_000 ? size - 300_000 : 0)
    guard let data = try? handle.readToEnd(), let tail = String(data: data, encoding: .utf8) else { return nil }
    for line in tail.split(separator: "\n").reversed() {
        guard let object = try? JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any] else { continue }
        let type = object["type"] as? String
        if type == "user", let message = object["message"] as? [String: Any], message["content"] is String {
            return nil  // Alec spoke last; Claude is picking it up
        }
        guard type == "assistant", let message = object["message"] as? [String: Any] else { continue }
        let blocks = message["content"] as? [[String: Any]] ?? []
        let text = blocks.compactMap { $0["type"] as? String == "text" ? $0["text"] as? String : nil }.joined(separator: " ")
        let lowered = text.lowercased()
        let limited = (object["isApiErrorMessage"] as? Bool ?? false)
            && (lowered.contains("limit") || lowered.contains("credit") || lowered.contains("usage"))
        return ClaudeTurn(
            id: object["uuid"] as? String ?? UUID().uuidString,
            finished: (message["stop_reason"] as? String) == "end_turn",
            text: text,
            at: parseDate(object["timestamp"] as? String ?? "") ?? .distantPast,
            limited: limited
        )
    }
    return nil
}

func readClaude() -> Reading {
    let running = !NSRunningApplication.runningApplications(withBundleIdentifier: claudeBundleID).isEmpty
    guard let session = latestClaudeSession() else {
        return Reading(mood: running ? .idle : .asleep, summary: running ? "Claude is open. Nothing going on yet." : "Claude is closed. Click to open it.")
    }
    let quietFor = Date().timeIntervalSince(session.modified)
    let turn = lastClaudeTurn(in: session.url)
    let news = turn.flatMap { $0.finished && !$0.text.isEmpty ? $0.text : nil }
    let newsID = news == nil ? nil : turn?.id
    if let turn, turn.limited {
        return Reading(mood: .outOfCredits, summary: "Claude hit its usage limit. It'll be back when the limit resets.", newsID: newsID, news: news)
    }
    if quietFor < 25 || (turn != nil && !turn!.finished && quietFor < 120) {
        return Reading(mood: .thinking, summary: "Claude is working...", newsID: newsID, news: news)
    }
    if let turn, turn.finished, Date().timeIntervalSince(turn.at) < 30 * 60 {
        return Reading(mood: .alert, summary: "Claude finished and is waiting for you. Click to open it.", newsID: newsID, news: news)
    }
    if !running || lateNight() {
        return Reading(mood: .asleep, summary: running ? "Resting. Claude is open if you need it." : "Claude is closed. Click to open it.", newsID: newsID, news: news)
    }
    return Reading(mood: .idle, summary: "Claude is open and idle.", newsID: newsID, news: news)
}

// MARK: - Model

final class PetModel: ObservableObject {
    let character: Character
    @Published var mood: Mood = .offline
    @Published var drag: DragPose = .none
    @Published var bubble: String?
    var summary = ""
    private var lastNewsID: String?
    private var firstRead = true
    private var bubbleTimer: Timer?

    init(character: Character) { self.character = character }

    func poll() {
        let reading = character == .owl ? readAri() : readClaude()
        mood = reading.mood
        summary = reading.summary
        // Something new: say it, briefly. Nothing is said for what was already there at launch.
        if let id = reading.newsID, id != lastNewsID {
            if !firstRead, let news = reading.news { say(news, seconds: 8) }
            lastNewsID = id
        }
        firstRead = false
    }

    func say(_ text: String, seconds: TimeInterval = 5) {
        let flat = text.replacingOccurrences(of: "\n", with: " ")
        bubble = flat.count > 140 ? String(flat.prefix(137)) + "..." : flat
        bubbleTimer?.invalidate()
        bubbleTimer = Timer.scheduledTimer(withTimeInterval: seconds, repeats: false) { [weak self] _ in
            self?.bubble = nil
        }
    }
}

// MARK: - The owl

extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xff) / 255, green: Double((hex >> 8) & 0xff) / 255, blue: Double(hex & 0xff) / 255)
    }
}

struct Owl: View {
    @ObservedObject var model: PetModel

    var body: some View {
        TimelineView(.animation) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            owl(at: t)
        }
    }

    @ViewBuilder
    func owl(at t: Double) -> some View {
        let mood = model.mood
        let drag = model.drag
        let dull = mood == .offline || mood == .outOfCredits
        let body = dull ? Color(hex: 0x6f7c88) : Color(hex: 0x3e5c76)
        let wing = dull ? Color(hex: 0x5c6872) : Color(hex: 0x2f4a61)
        let belly = Color(hex: 0xe9dfcf)
        let beak = dull ? Color(hex: 0xb8a07a) : Color(hex: 0xe8a33d)

        let breathe = 1 + 0.018 * sin(t * (mood == .asleep ? 1.0 : 1.7))
        let blinking = (t.truncatingRemainder(dividingBy: 5.5)) > 5.32
        let eyesClosed = mood == .asleep || mood == .offline || (blinking && drag == .none)
        let halfLids = mood == .outOfCredits
        let wide = drag == .up || drag == .down

        let tilt: Double = {
            switch drag {
            case .left: return -14
            case .right: return 14
            default: break
            }
            if mood == .thinking { return sin(t * 3.2) * 6 }
            return 0
        }()
        let hop: Double = mood == .alert ? max(0, sin(t * 2.6)) * -4 * (sin(t * 2.6) > 0.7 ? 1 : 0) : 0
        let flap: Double = {
            switch drag {
            case .up: return sin(t * 28) * 40
            case .left, .right: return 22
            case .down: return 48 + sin(t * 14) * 6
            default: return mood == .alert ? max(0, sin(t * 2.6)) * 18 : 0
            }
        }()
        let pupil: CGSize = {
            switch drag {
            case .left: return CGSize(width: -2.2, height: 0)
            case .right: return CGSize(width: 2.2, height: 0)
            case .up: return CGSize(width: 0, height: -2.2)
            case .down: return CGSize(width: 0, height: 2)
            default: return mood == .thinking ? CGSize(width: 1.8, height: -2.2) : .zero
            }
        }()
        let stretch: Double = drag == .down ? 1.08 : (mood == .outOfCredits ? 0.94 : 1)
        let feetDrop: Double = drag == .down ? 8 + sin(t * 9) * 2 : 0

        ZStack {
            Ellipse().fill(Color.black.opacity(0.10)).frame(width: 34, height: 6).offset(y: 40)

            ZStack {
                // Feet
                HStack(spacing: 6) {
                    Capsule().fill(beak).frame(width: 8, height: 4)
                    Capsule().fill(beak).frame(width: 8, height: 4)
                }.offset(y: 32 + feetDrop)
                // Wings, pivoting at the shoulder
                Ellipse().fill(wing).frame(width: 12, height: 27)
                    .rotationEffect(.degrees(flap), anchor: .top).offset(x: -21, y: 5)
                Ellipse().fill(wing).frame(width: 12, height: 27)
                    .rotationEffect(.degrees(-flap), anchor: .top).offset(x: 21, y: 5)
                // Ear tufts
                Triangle().fill(body).frame(width: 12, height: 13).rotationEffect(.degrees(-18)).offset(x: -15, y: -25)
                Triangle().fill(body).frame(width: 12, height: 13).rotationEffect(.degrees(18)).offset(x: 15, y: -25)
                // Body and belly
                Ellipse().fill(body).frame(width: 44, height: 52)
                Ellipse().fill(belly).frame(width: 27, height: 26).offset(y: 10)
                Chevrons().stroke(Color(hex: 0xc9b99f), style: StrokeStyle(lineWidth: 1.2, lineCap: .round, lineJoin: .round))
                    .frame(width: 10, height: 8).offset(y: 12)
                // Eyes
                HStack(spacing: 2) {
                    eye(closed: eyesClosed, half: halfLids, wide: wide, pupil: pupil, body: body)
                    eye(closed: eyesClosed, half: halfLids, wide: wide, pupil: pupil, body: body)
                }.offset(y: -7)
                Triangle().fill(beak).frame(width: 6, height: 5).rotationEffect(.degrees(180)).offset(y: 2)
            }
            .scaleEffect(x: 1 / sqrt(stretch) * (2 - breathe), y: stretch * breathe, anchor: .bottom)
            .rotationEffect(.degrees(tilt), anchor: .bottom)
            .offset(y: hop)

            if mood == .alert {
                Circle().fill(Color(hex: 0xe5484d)).frame(width: 9, height: 9)
                    .overlay(Circle().stroke(Color.white, lineWidth: 1.5)).offset(x: 22, y: -24)
            }
            if mood == .asleep || mood == .offline {
                let phase = t.truncatingRemainder(dividingBy: 3) / 3
                Text("z").font(.system(size: 9, weight: .bold, design: .rounded)).foregroundColor(.secondary)
                    .opacity(sin(phase * .pi)).offset(x: 24, y: -26 - phase * 8)
            }
            if mood == .outOfCredits {
                EmptyBattery().offset(x: 0, y: -40).opacity(0.6 + 0.4 * sin(t * 2))
            }
            if mood == .thinking {
                HStack(spacing: 3) {
                    ForEach(0..<3) { index in
                        Circle().fill(Color.secondary).frame(width: 4, height: 4)
                            .opacity(0.35 + 0.65 * max(0, sin(t * 5 - Double(index) * 0.7)))
                    }
                }.offset(x: 26, y: -30)
            }
        }
        .frame(width: 84, height: 92)
    }

    func eye(closed: Bool, half: Bool, wide: Bool, pupil: CGSize, body: Color) -> some View {
        ZStack {
            Circle().fill(Color.white).frame(width: 16, height: 16)
            Circle().fill(Color(hex: 0x16202a)).frame(width: wide ? 6 : 7.5, height: wide ? 6 : 7.5).offset(pupil)
            Circle().fill(Color.white).frame(width: 2.2, height: 2.2).offset(x: pupil.width + 1.6, y: pupil.height - 1.6)
            if closed {
                Circle().fill(body).frame(width: 17, height: 17)
                Capsule().fill(Color(hex: 0x1d2c3a)).frame(width: 10, height: 1.6).offset(y: 1)
            } else if half {
                Rectangle().fill(body).frame(width: 17, height: 8).offset(y: -4.5)
            }
        }
        .frame(width: 17, height: 17)
        .clipShape(Circle())
    }
}


// MARK: - The golden retriever, from photos

// Photo poses ship inside Claude Pet.app (Contents/Resources/poses), cut out of their
// backgrounds by tools/ari-pet/cutout.swift. When they're there, the retriever is the
// photo of the pose that fits, with live motion on top; otherwise it's drawn.
let photoPoses: [String: NSImage] = {
    guard let folder = Bundle.main.resourceURL?.appendingPathComponent("poses"),
          let files = try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil) else { return [:] }
    var poses: [String: NSImage] = [:]
    for file in files where file.pathExtension == "png" {
        poses[file.deletingPathExtension().lastPathComponent] = NSImage(contentsOf: file)
    }
    return poses
}()

struct PhotoRetriever: View {
    @ObservedObject var model: PetModel

    // The photo for the moment, and whether to mirror it (the leap faces right).
    func photo() -> (name: String, flipped: Bool) {
        let wanted: (String, Bool) = {
            switch model.drag {
            case .left: return ("leap", true)
            case .right: return ("leap", false)
            case .up: return ("lifted", false)
            case .down: return ("startled", false)
            case .none: break
            }
            switch model.mood {
            case .thinking: return ("panting", false)
            case .alert: return ("alert", false)
            case .asleep, .offline: return ("asleep", false)
            case .outOfCredits: return ("sad", false)
            case .idle: return ("sit", false)
            }
        }()
        return photoPoses[wanted.0] == nil ? ("sit", false) : wanted
    }

    var body: some View {
        TimelineView(.animation) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            let mood = model.mood
            let drag = model.drag
            let current = photo()
            let panting = current.name == "panting"
            let breathe = 1 + (panting ? 0.022 * sin(t * 9) : 0.012 * sin(t * (mood == .asleep ? 1.0 : 1.8)))
            let hop: Double = mood == .alert && drag == .none && sin(t * 3) > 0.8 ? -3 : 0
            let sway: Double = {
                switch drag {
                case .left: return -5 + sin(t * 10) * 1.5
                case .right: return 5 + sin(t * 10) * 1.5
                case .up: return sin(t * 6) * 6
                case .down: return sin(t * 30) * 1.5
                case .none: return 0
                }
            }()
            ZStack {
                if let image = photoPoses[current.name] {
                    Image(nsImage: image)
                        .resizable()
                        .interpolation(.high)
                        .aspectRatio(contentMode: .fit)
                        .scaleEffect(x: (current.flipped ? -1 : 1) * (2 - breathe), y: breathe, anchor: .bottom)
                        .rotationEffect(.degrees(sway), anchor: drag == .up ? .top : .bottom)
                        .offset(y: hop)
                        .saturation(mood == .offline ? 0.25 : (mood == .outOfCredits ? 0.6 : 1))
                        .opacity(mood == .offline ? 0.8 : 1)
                        .shadow(color: .black.opacity(0.18), radius: 3, y: 2)
                        .id(current.name + (current.flipped ? "-flipped" : ""))
                        .transition(.opacity)
                }
                if mood == .alert {
                    Circle().fill(Color(hex: 0xe5484d)).frame(width: 9, height: 9)
                        .overlay(Circle().stroke(Color.white, lineWidth: 1.5)).offset(x: 34, y: -40)
                }
                if mood == .asleep || mood == .offline {
                    let phase = t.truncatingRemainder(dividingBy: 3) / 3
                    Text("z").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundColor(.secondary)
                        .opacity(sin(phase * .pi)).offset(x: 34, y: -30 - phase * 8)
                }
                if mood == .outOfCredits {
                    EmptyBowl().offset(x: 44, y: 40)
                }
                if mood == .thinking {
                    HStack(spacing: 3) {
                        ForEach(0..<3) { index in
                            Circle().fill(Color.secondary).frame(width: 4, height: 4)
                                .opacity(0.35 + 0.65 * max(0, sin(t * 5 - Double(index) * 0.7)))
                        }
                    }.offset(x: 38, y: -42)
                }
            }
            .frame(width: petBox.width, height: petBox.height, alignment: .bottom)
            .animation(.easeInOut(duration: 0.18), value: current.name + (current.flipped ? "1" : "0"))
        }
    }
}

// MARK: - The golden retriever

// Drawn on a 100 x 110 canvas, sitting and facing out, with shading and fur strokes.
struct DogPose {
    let mood: Mood
    let drag: DragPose
    let t: Double

    var dull: Bool { mood == .offline || mood == .outOfCredits }
    var sad: Bool { mood == .outOfCredits }
    var breathe: Double { 1 + 0.018 * sin(t * (mood == .asleep ? 1.0 : 1.9)) }
    var eyesClosed: Bool {
        mood == .asleep || mood == .offline || (t.truncatingRemainder(dividingBy: 4.8) > 4.64 && drag == .none)
    }
    var tongue: Bool { (mood == .thinking || mood == .alert || drag == .left || drag == .right) && !sad }
    var pant: Double { tongue ? max(0, sin(t * 9)) * 1.6 : 0 }
    var wag: Double {
        switch mood {
        case .alert: return sin(t * 16) * 24
        case .thinking: return sin(t * 11) * 20
        case .idle: return sin(t * 5) * 12
        default: return -38
        }
    }
    var lean: Double {
        switch drag {
        case .left: return -9
        case .right: return 9
        default: return 0
        }
    }
    var headTilt: Double {
        switch drag {
        case .left: return -8
        case .right: return 8
        default: return mood == .thinking ? 11 + sin(t * 2) * 3 : (sad ? -4 : 0)
        }
    }
    // Ears trail the motion, flap when lifted, fly up when dragged down, droop when sad.
    var ear: Double {
        switch drag {
        case .left: return 24
        case .right: return -24
        case .up: return sin(t * 22) * 18
        default: return sad ? -5 : (mood == .alert ? 6 : 0)
        }
    }
    var earsUp: Bool { drag == .down }
    var paddle: Double { drag == .up ? sin(t * 20) * 4 : 0 }
    var hop: Double { mood == .alert && sin(t * 3) > 0.78 ? -3 : (drag == .down ? 2 : 0) }
    var look: CGSize {
        switch drag {
        case .left: return CGSize(width: -1.1, height: 0)
        case .right: return CGSize(width: 1.1, height: 0)
        case .up: return CGSize(width: 0, height: -1.0)
        case .down: return CGSize(width: 0, height: 0.8)
        default: return mood == .thinking ? CGSize(width: 0.9, height: -0.9) : .zero
        }
    }
}

struct Retriever: View {
    @ObservedObject var model: PetModel

    var body: some View {
        TimelineView(.animation) { context in
            let pose = DogPose(mood: model.mood, drag: model.drag, t: context.date.timeIntervalSinceReferenceDate)
            ZStack {
                Canvas { canvas, size in drawRetriever(canvas, size: size, pose: pose) }
                    .saturation(pose.dull ? 0.3 : 1)
                    .opacity(pose.mood == .offline ? 0.75 : 1)
                if pose.mood == .alert {
                    Circle().fill(Color(hex: 0xe5484d)).frame(width: 9, height: 9)
                        .overlay(Circle().stroke(Color.white, lineWidth: 1.5)).offset(x: 24, y: -36)
                }
                if pose.mood == .asleep || pose.mood == .offline {
                    let phase = pose.t.truncatingRemainder(dividingBy: 3) / 3
                    Text("z").font(.system(size: 9, weight: .bold, design: .rounded)).foregroundColor(.secondary)
                        .opacity(sin(phase * .pi)).offset(x: 24, y: -36 - phase * 8)
                }
                if pose.mood == .outOfCredits {
                    EmptyBowl().offset(x: 32, y: 38)
                }
                if pose.mood == .thinking {
                    HStack(spacing: 3) {
                        ForEach(0..<3) { index in
                            Circle().fill(Color.secondary).frame(width: 4, height: 4)
                                .opacity(0.35 + 0.65 * max(0, sin(pose.t * 5 - Double(index) * 0.7)))
                        }
                    }.offset(x: 30, y: -38)
                }
            }
            .frame(width: 84, height: 92)
        }
    }
}

private func ellipse(_ cx: CGFloat, _ cy: CGFloat, _ rx: CGFloat, _ ry: CGFloat) -> Path {
    Path(ellipseIn: CGRect(x: cx - rx, y: cy - ry, width: rx * 2, height: ry * 2))
}

private func pivot(_ context: inout GraphicsContext, _ degrees: Double, _ x: CGFloat, _ y: CGFloat) {
    context.translateBy(x: x, y: y)
    context.rotate(by: .degrees(degrees))
    context.translateBy(x: -x, y: -y)
}

private func mirrored(_ path: Path) -> Path {
    path.applying(CGAffineTransform(a: -1, b: 0, c: 0, d: 1, tx: 100, ty: 0))
}

private func shade(_ top: UInt32, _ bottom: UInt32, _ y0: CGFloat, _ y1: CGFloat) -> GraphicsContext.Shading {
    .linearGradient(Gradient(colors: [Color(hex: top), Color(hex: bottom)]), startPoint: CGPoint(x: 50, y: y0), endPoint: CGPoint(x: 50, y: y1))
}

func drawRetriever(_ base: GraphicsContext, size: CGSize, pose: DogPose) {
    var c = base
    let scale = min(size.width / 100, size.height / 110)
    c.translateBy(x: (size.width - 100 * scale) / 2, y: size.height - 110 * scale + pose.hop)
    c.scaleBy(x: scale, y: scale)

    let gold = UInt32(0xd8963f), goldLight = UInt32(0xebb663), goldDeep = UInt32(0xa9682a)
    let cream = UInt32(0xf3d79f), creamDeep = UInt32(0xe2bb78)
    let furLine = Color(hex: 0x9a6326).opacity(0.45)
    let ink = Color(hex: 0x1a120c)

    c.fill(ellipse(50, 106, 27, 3.6), with: .color(.black.opacity(0.10)))
    pivot(&c, pose.lean, 50, 104)
    c.translateBy(x: 50, y: 104)
    c.scaleBy(x: 2 - pose.breathe, y: pose.breathe)
    c.translateBy(x: -50, y: -104)

    // Tail: a feathered plume behind the body, wagging from its base.
    var tail = c
    pivot(&tail, pose.wag, 70, 93)
    var plume = Path()
    plume.move(to: CGPoint(x: 67, y: 96))
    plume.addCurve(to: CGPoint(x: 93, y: 62), control1: CGPoint(x: 84, y: 94), control2: CGPoint(x: 95, y: 78))
    plume.addCurve(to: CGPoint(x: 83, y: 64), control1: CGPoint(x: 90, y: 60), control2: CGPoint(x: 85, y: 61))
    plume.addQuadCurve(to: CGPoint(x: 80, y: 72), control: CGPoint(x: 84, y: 69))
    plume.addQuadCurve(to: CGPoint(x: 76, y: 78), control: CGPoint(x: 79, y: 77))
    plume.addQuadCurve(to: CGPoint(x: 71, y: 85), control: CGPoint(x: 75, y: 84))
    plume.addCurve(to: CGPoint(x: 66, y: 90), control1: CGPoint(x: 70, y: 88), control2: CGPoint(x: 68, y: 89))
    plume.closeSubpath()
    tail.fill(plume, with: shade(goldLight, goldDeep, 60, 96))
    var plumeFur = Path()
    plumeFur.move(to: CGPoint(x: 80, y: 84)); plumeFur.addQuadCurve(to: CGPoint(x: 88, y: 70), control: CGPoint(x: 86, y: 79))
    tail.stroke(plumeFur, with: .color(furLine), lineWidth: 0.8)

    // Haunches, then the body.
    c.fill(ellipse(26, 93, 12, 11), with: shade(gold, goldDeep, 82, 104))
    c.fill(ellipse(74, 93, 12, 11), with: shade(gold, goldDeep, 82, 104))
    var body = Path()
    body.move(to: CGPoint(x: 36, y: 50))
    body.addCurve(to: CGPoint(x: 22, y: 96), control1: CGPoint(x: 26, y: 58), control2: CGPoint(x: 20, y: 80))
    body.addCurve(to: CGPoint(x: 50, y: 104), control1: CGPoint(x: 24, y: 104), control2: CGPoint(x: 40, y: 104))
    body.addCurve(to: CGPoint(x: 78, y: 96), control1: CGPoint(x: 60, y: 104), control2: CGPoint(x: 76, y: 104))
    body.addCurve(to: CGPoint(x: 64, y: 50), control1: CGPoint(x: 80, y: 80), control2: CGPoint(x: 74, y: 58))
    body.closeSubpath()
    c.fill(body, with: shade(goldLight, gold, 50, 104))

    // The cream chest ruff, scalloped at its point.
    var ruff = Path()
    ruff.move(to: CGPoint(x: 37, y: 52))
    ruff.addCurve(to: CGPoint(x: 63, y: 52), control1: CGPoint(x: 44, y: 47), control2: CGPoint(x: 56, y: 47))
    ruff.addCurve(to: CGPoint(x: 59, y: 74), control1: CGPoint(x: 65, y: 60), control2: CGPoint(x: 63, y: 68))
    ruff.addQuadCurve(to: CGPoint(x: 55, y: 80), control: CGPoint(x: 58, y: 79))
    ruff.addQuadCurve(to: CGPoint(x: 50, y: 87), control: CGPoint(x: 53, y: 86))
    ruff.addQuadCurve(to: CGPoint(x: 45, y: 80), control: CGPoint(x: 47, y: 86))
    ruff.addQuadCurve(to: CGPoint(x: 41, y: 74), control: CGPoint(x: 42, y: 79))
    ruff.addCurve(to: CGPoint(x: 37, y: 52), control1: CGPoint(x: 37, y: 68), control2: CGPoint(x: 35, y: 60))
    ruff.closeSubpath()
    c.fill(ruff, with: shade(cream, creamDeep, 50, 87))
    for (x, y, dx) in [(44.0, 62.0, -2.0), (56.0, 62.0, 2.0), (47.0, 72.0, -1.5), (53.0, 72.0, 1.5), (50.0, 67.0, 0.0)] {
        var strand = Path()
        strand.move(to: CGPoint(x: x, y: y)); strand.addQuadCurve(to: CGPoint(x: x + dx, y: y + 6), control: CGPoint(x: x + dx * 1.5, y: y + 3))
        c.stroke(strand, with: .color(Color(hex: 0xc99a55).opacity(0.5)), lineWidth: 0.7)
    }

    // Front legs and paws; they paddle when lifted.
    for (x, offset) in [(42.0, pose.paddle), (58.0, -pose.paddle)] {
        let leg = Path(roundedRect: CGRect(x: x - 4.5, y: 74 + offset, width: 9, height: 26), cornerRadius: 4.5)
        c.fill(leg, with: shade(gold, goldDeep, 74, 100))
        c.fill(ellipse(x, 100.5 + offset, 6.2, 3.4), with: .color(Color(hex: goldLight)))
        for toe in [-2.2, 0.0, 2.2] {
            var line = Path()
            line.move(to: CGPoint(x: x + toe, y: 99 + offset)); line.addLine(to: CGPoint(x: x + toe, y: 102 + offset))
            c.stroke(line, with: .color(furLine), lineWidth: 0.6)
        }
    }

    // The head, tilting at the neck.
    var head = c
    pivot(&head, pose.headTilt, 50, 50)

    // Ears hang from the top of the skull, feathered at the tips.
    var ear = Path()
    ear.move(to: CGPoint(x: 37, y: 23))
    ear.addCurve(to: CGPoint(x: 27, y: 45), control1: CGPoint(x: 29, y: 25), control2: CGPoint(x: 24, y: 37))
    ear.addQuadCurve(to: CGPoint(x: 31, y: 48.5), control: CGPoint(x: 27, y: 49))
    ear.addQuadCurve(to: CGPoint(x: 35, y: 46), control: CGPoint(x: 33.5, y: 48.5))
    ear.addCurve(to: CGPoint(x: 41, y: 29), control1: CGPoint(x: 38, y: 40), control2: CGPoint(x: 41, y: 34))
    ear.closeSubpath()
    for (path, attachX, sign) in [(ear, CGFloat(37), 1.0), (mirrored(ear), CGFloat(63), -1.0)] {
        var earContext = head
        pivot(&earContext, pose.earsUp ? 165 * sign : pose.ear * sign, attachX, 24)
        earContext.fill(path, with: shade(gold, goldDeep, 22, 58))
        var strand = Path()
        let x = attachX - 6 * sign
        strand.move(to: CGPoint(x: x, y: 32)); strand.addQuadCurve(to: CGPoint(x: x - 1.5 * sign, y: 44), control: CGPoint(x: x - 2.5 * sign, y: 38))
        earContext.stroke(strand, with: .color(furLine), lineWidth: 0.7)
    }

    // Skull and cheeks.
    var skull = Path()
    skull.move(to: CGPoint(x: 50, y: 15))
    skull.addCurve(to: CGPoint(x: 67, y: 30), control1: CGPoint(x: 61, y: 15), control2: CGPoint(x: 67, y: 22))
    skull.addCurve(to: CGPoint(x: 60, y: 47), control1: CGPoint(x: 67, y: 38), control2: CGPoint(x: 64, y: 45))
    skull.addCurve(to: CGPoint(x: 40, y: 47), control1: CGPoint(x: 55, y: 50), control2: CGPoint(x: 45, y: 50))
    skull.addCurve(to: CGPoint(x: 33, y: 30), control1: CGPoint(x: 36, y: 45), control2: CGPoint(x: 33, y: 38))
    skull.addCurve(to: CGPoint(x: 50, y: 15), control1: CGPoint(x: 33, y: 22), control2: CGPoint(x: 39, y: 15))
    skull.closeSubpath()
    head.fill(skull, with: .radialGradient(Gradient(colors: [Color(hex: goldLight), Color(hex: gold), Color(hex: goldDeep)]),
                                           center: CGPoint(x: 50, y: 27), startRadius: 2, endRadius: 22))

    // The muzzle, lighter, tapering to the nose.
    var muzzle = Path()
    muzzle.move(to: CGPoint(x: 42, y: 35))
    muzzle.addCurve(to: CGPoint(x: 58, y: 35), control1: CGPoint(x: 46, y: 32), control2: CGPoint(x: 54, y: 32))
    muzzle.addCurve(to: CGPoint(x: 57, y: 48), control1: CGPoint(x: 61, y: 39), control2: CGPoint(x: 60, y: 46))
    muzzle.addCurve(to: CGPoint(x: 43, y: 48), control1: CGPoint(x: 54, y: 51), control2: CGPoint(x: 46, y: 51))
    muzzle.addCurve(to: CGPoint(x: 42, y: 35), control1: CGPoint(x: 40, y: 46), control2: CGPoint(x: 39, y: 39))
    muzzle.closeSubpath()
    head.fill(muzzle, with: shade(cream, creamDeep, 32, 50))

    // Brows: soft ridges, angled up in the middle when sad.
    let browLift: CGFloat = pose.sad ? 1.6 : 0
    for (x0, x1, lift0, lift1) in [(38.5, 46.5, 0.0, browLift), (53.5, 61.5, browLift, 0.0)] {
        var brow = Path()
        brow.move(to: CGPoint(x: x0, y: 26.5 - lift0)); brow.addQuadCurve(to: CGPoint(x: x1, y: 26.5 - lift1), control: CGPoint(x: (x0 + x1) / 2, y: 24.6 - (lift0 + lift1) / 2))
        head.stroke(brow, with: .color(Color(hex: goldDeep).opacity(0.75)), lineWidth: 1.1)
    }

    // Almond eyes, dark brown, with a catchlight; closed eyes are a soft curve.
    for x in [42.5, 57.5] {
        if pose.eyesClosed {
            var lid = Path()
            lid.move(to: CGPoint(x: x - 3.2, y: 30.6)); lid.addQuadCurve(to: CGPoint(x: x + 3.2, y: 30.6), control: CGPoint(x: x, y: 32.6))
            head.stroke(lid, with: .color(ink), style: StrokeStyle(lineWidth: 1.1, lineCap: .round))
        } else {
            let cx = x + pose.look.width, cy = 30.6 + pose.look.height
            head.fill(ellipse(x, 30.6, 3.6, 2.8), with: .color(Color(hex: 0x6b4423)))
            head.fill(ellipse(cx, cy, 2.5, 2.4), with: .color(Color(hex: 0x24160d)))
            head.fill(ellipse(cx + 0.9, cy - 0.9, 0.75, 0.75), with: .color(.white.opacity(0.95)))
            if pose.sad {
                head.fill(Path(CGRect(x: x - 4, y: 27.2, width: 8, height: 2.6)), with: .color(Color(hex: gold)))
            }
        }
    }

    // Nose: glossy black, with nostrils.
    var nose = Path()
    nose.move(to: CGPoint(x: 45.6, y: 38.6))
    nose.addCurve(to: CGPoint(x: 54.4, y: 38.6), control1: CGPoint(x: 47, y: 37), control2: CGPoint(x: 53, y: 37))
    nose.addCurve(to: CGPoint(x: 50, y: 43.4), control1: CGPoint(x: 55.6, y: 40.6), control2: CGPoint(x: 52.4, y: 43.4))
    nose.addCurve(to: CGPoint(x: 45.6, y: 38.6), control1: CGPoint(x: 47.6, y: 43.4), control2: CGPoint(x: 44.4, y: 40.6))
    nose.closeSubpath()
    head.fill(nose, with: .color(ink))
    head.fill(ellipse(48.6, 38.9, 1.5, 0.7), with: .color(.white.opacity(0.35)))
    head.fill(ellipse(48.0, 40.6, 0.8, 0.55), with: .color(.black))
    head.fill(ellipse(52.0, 40.6, 0.8, 0.55), with: .color(.black))

    // Mouth: a soft smile, a frown when sad, and a panting tongue when happy.
    var mouth = Path()
    mouth.move(to: CGPoint(x: 50, y: 43.4)); mouth.addLine(to: CGPoint(x: 50, y: 45.4))
    let corner: CGFloat = pose.sad ? 48.8 : 46.4
    mouth.move(to: CGPoint(x: 45, y: corner)); mouth.addQuadCurve(to: CGPoint(x: 50, y: 45.4), control: CGPoint(x: 47.6, y: pose.sad ? 45.2 : 47.6))
    mouth.addQuadCurve(to: CGPoint(x: 55, y: corner), control: CGPoint(x: 52.4, y: pose.sad ? 45.2 : 47.6))
    if pose.tongue {
        var tongue = Path()
        tongue.move(to: CGPoint(x: 47.4, y: 46.4))
        tongue.addLine(to: CGPoint(x: 52.6, y: 46.4))
        tongue.addCurve(to: CGPoint(x: 50, y: 52.6 + pose.pant), control1: CGPoint(x: 53.2, y: 50 + pose.pant), control2: CGPoint(x: 52, y: 52.6 + pose.pant))
        tongue.addCurve(to: CGPoint(x: 47.4, y: 46.4), control1: CGPoint(x: 48, y: 52.6 + pose.pant), control2: CGPoint(x: 46.8, y: 50 + pose.pant))
        head.fill(tongue, with: shade(0xec8b8f, 0xd9666d, 46, 53))
        var crease = Path()
        crease.move(to: CGPoint(x: 50, y: 47.4)); crease.addLine(to: CGPoint(x: 50, y: 50.4 + pose.pant))
        head.stroke(crease, with: .color(Color(hex: 0xc4555c)), lineWidth: 0.5)
    }
    head.stroke(mouth, with: .color(ink), style: StrokeStyle(lineWidth: 0.9, lineCap: .round))
}

struct EmptyBowl: View {
    var body: some View {
        ZStack {
            BowlShape().fill(Color(hex: 0xe5484d)).frame(width: 18, height: 8)
            Capsule().fill(Color(hex: 0xb83236)).frame(width: 18, height: 3).offset(y: -4)
        }
    }
}

struct BowlShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX - 3, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX + 3, y: rect.maxY))
        path.closeSubpath()
        return path
    }
}

struct Triangle: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
        path.closeSubpath()
        return path
    }
}

struct Chevrons: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        for row in 0..<2 {
            let y = rect.minY + CGFloat(row) * rect.height / 2
            path.move(to: CGPoint(x: rect.minX, y: y))
            path.addLine(to: CGPoint(x: rect.minX + rect.width * 0.25, y: y + 2))
            path.addLine(to: CGPoint(x: rect.midX, y: y))
            path.addLine(to: CGPoint(x: rect.minX + rect.width * 0.75, y: y + 2))
            path.addLine(to: CGPoint(x: rect.maxX, y: y))
        }
        return path
    }
}

struct EmptyBattery: View {
    var body: some View {
        HStack(spacing: 1) {
            RoundedRectangle(cornerRadius: 2).stroke(Color(hex: 0xe5484d), lineWidth: 1.4).frame(width: 16, height: 8)
                .overlay(Rectangle().fill(Color(hex: 0xe5484d)).frame(width: 2.5, height: 4), alignment: .leading)
            Rectangle().fill(Color(hex: 0xe5484d)).frame(width: 1.6, height: 3.5)
        }
    }
}

struct PetView: View {
    @ObservedObject var model: PetModel

    var body: some View {
        VStack(spacing: 4) {
            Spacer(minLength: 0)
            if let bubble = model.bubble {
                Text(bubble)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.primary)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 10).padding(.vertical, 7)
                    .background(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(.regularMaterial)
                            .shadow(color: .black.opacity(0.12), radius: 6, y: 2)
                    )
                    .frame(maxWidth: 230)
                    .transition(.opacity.combined(with: .scale(scale: 0.9, anchor: .bottom)))
            }
            if model.character == .owl {
                Owl(model: model)
            } else if photoPoses["sit"] != nil {
                PhotoRetriever(model: model)
            } else {
                Retriever(model: model)
            }
        }
        .frame(width: 250, height: 210, alignment: .bottom)
        .animation(.spring(response: 0.3, dampingFraction: 0.8), value: model.bubble)
    }
}

// MARK: - Window and mouse

final class PetPanel: NSPanel {
    override var canBecomeKey: Bool { false }
}

final class DragLayer: NSView {
    let model: PetModel
    private var startMouse = NSPoint.zero
    private var startOrigin = NSPoint.zero
    private var lastMouse = NSPoint.zero
    private var moved: CGFloat = 0

    init(model: PetModel) {
        self.model = model
        super.init(frame: .zero)
    }

    required init?(coder: NSCoder) { fatalError() }

    // Only the owl itself catches the mouse; the rest of the window is see-through to clicks.
    override func hitTest(_ point: NSPoint) -> NSView? {
        let local = convert(point, from: superview)
        let owlBox = NSRect(x: bounds.midX - petBox.width / 2, y: 0, width: petBox.width, height: petBox.height)
        return owlBox.contains(local) ? self : nil
    }

    override func updateTrackingAreas() {
        trackingAreas.forEach(removeTrackingArea)
        let owlBox = NSRect(x: bounds.midX - petBox.width / 2, y: 0, width: petBox.width, height: petBox.height)
        addTrackingArea(NSTrackingArea(rect: owlBox, options: [.mouseEnteredAndExited, .activeAlways], owner: self))
    }

    override func mouseEntered(with event: NSEvent) {
        if model.bubble == nil { model.say(model.summary, seconds: 4) }
    }

    override func mouseDown(with event: NSEvent) {
        startMouse = NSEvent.mouseLocation
        lastMouse = startMouse
        startOrigin = window?.frame.origin ?? .zero
        moved = 0
    }

    override func mouseDragged(with event: NSEvent) {
        let mouse = NSEvent.mouseLocation
        let dx = mouse.x - lastMouse.x
        let dy = mouse.y - lastMouse.y
        lastMouse = mouse
        moved = max(moved, hypot(mouse.x - startMouse.x, mouse.y - startMouse.y))
        window?.setFrameOrigin(NSPoint(x: startOrigin.x + mouse.x - startMouse.x, y: startOrigin.y + mouse.y - startMouse.y))
        guard moved > 3 else { return }
        if abs(dx) > abs(dy), abs(dx) > 0.8 {
            model.drag = dx < 0 ? .left : .right
        } else if abs(dy) > 0.8 {
            model.drag = dy > 0 ? .up : .down
        }
    }

    override func mouseUp(with event: NSEvent) {
        model.drag = .none
        if moved <= 3 {
            openApp()
        } else if let origin = window?.frame.origin {
            UserDefaults.standard.set([origin.x, origin.y], forKey: "origin")
        }
    }

    override func rightMouseDown(with event: NSEvent) {
        let menu = NSMenu()
        menu.addItem(withTitle: "Open \(appName)", action: #selector(openApp), keyEquivalent: "").target = self
        menu.addItem(withTitle: "What's going on?", action: #selector(tell), keyEquivalent: "").target = self
        menu.addItem(.separator())
        menu.addItem(withTitle: "Hide for an hour", action: #selector(hideForAnHour), keyEquivalent: "").target = self
        menu.addItem(withTitle: "Quit \(petName)", action: #selector(quit), keyEquivalent: "").target = self
        NSMenu.popUpContextMenu(menu, with: event, for: self)
    }

    @objc func openApp() {
        NSWorkspace.shared.openApplication(at: appURL, configuration: NSWorkspace.OpenConfiguration())
        model.say("Opening \(appName).", seconds: 2)
    }
    @objc func tell() { model.say(model.summary, seconds: 6) }
    @objc func hideForAnHour() {
        window?.orderOut(nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + 3600) { [weak self] in self?.window?.orderFrontRegardless() }
    }
    @objc func quit() { NSApp.terminate(nil) }
}

// MARK: - App

// Which pet this is comes from its app bundle, or `--character claude` when run bare.
let character: Character = (Bundle.main.bundleIdentifier ?? "").contains("claude") || CommandLine.arguments.contains("claude")
    ? .retriever : .owl
let appURL = character == .owl
    ? URL(fileURLWithPath: NSHomeDirectory() + "/Applications/ARI Hub.app")
    : URL(fileURLWithPath: "/Applications/Claude.app")
let appName = character == .owl ? "ARI Hub" : "Claude"
let petBox = character == .retriever && photoPoses["sit"] != nil ? CGSize(width: 118, height: 104) : CGSize(width: 84, height: 92)
let petName = character == .owl ? "ARI Pet" : "Claude Pet"

// `ARI Pet --snapshot DIR` draws every mood and drag pose to PNGs, for checking the art.
if CommandLine.arguments.count == 3, CommandLine.arguments[1] == "--snapshot" {
    let directory = URL(fileURLWithPath: CommandLine.arguments[2])
    let poses: [(String, Mood, DragPose, String?)] = [
        ("idle", .idle, .none, nil), ("thinking", .thinking, .none, nil), ("alert", .alert, .none, nil),
        ("asleep", .asleep, .none, nil), ("out-of-credits", .outOfCredits, .none, nil), ("offline", .offline, .none, nil),
        ("drag-left", .idle, .left, nil), ("drag-right", .idle, .right, nil), ("drag-up", .idle, .up, nil),
        ("drag-down", .idle, .down, nil), ("bubble", .idle, .none, "Set. You'll get \"Say thank you to Claude.\" on your GET DONE list at 1:07 PM."),
    ]
    MainActor.assumeIsolated {
        for who in [Character.owl, .retriever] {
        for (name, mood, drag, bubble) in poses {
            let model = PetModel(character: who)
            model.mood = mood
            model.drag = drag
            model.bubble = bubble
            let renderer = ImageRenderer(content: PetView(model: model).background(Color(white: 0.93)))
            renderer.scale = 2
            if let image = renderer.nsImage, let tiff = image.tiffRepresentation,
               let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) {
                try? png.write(to: directory.appendingPathComponent("\(who == .owl ? "owl" : "dog")-\(name).png"))
            }
        }
        }
    }
    exit(0)
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

let model = PetModel(character: character)
let size = NSSize(width: 250, height: 210)
let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
var origin = NSPoint(x: screen.maxX - size.width - 24 - (character == .retriever ? 130 : 0), y: screen.minY + 24)
if let saved = UserDefaults.standard.array(forKey: "origin") as? [CGFloat], saved.count == 2,
   NSScreen.screens.contains(where: { $0.frame.contains(NSPoint(x: saved[0] + size.width / 2, y: saved[1] + 40)) }) {
    origin = NSPoint(x: saved[0], y: saved[1])
}

let panel = PetPanel(
    contentRect: NSRect(origin: origin, size: size),
    styleMask: [.borderless, .nonactivatingPanel],
    backing: .buffered,
    defer: false
)
panel.isOpaque = false
panel.backgroundColor = .clear
panel.hasShadow = false
panel.level = .floating
panel.hidesOnDeactivate = false
panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]

let container = NSView(frame: NSRect(origin: .zero, size: size))
let hosting = NSHostingView(rootView: PetView(model: model))
hosting.frame = container.bounds
hosting.autoresizingMask = [.width, .height]
let dragLayer = DragLayer(model: model)
dragLayer.frame = container.bounds
dragLayer.autoresizingMask = [.width, .height]
container.addSubview(hosting)
container.addSubview(dragLayer)
panel.contentView = container
panel.orderFrontRegardless()

model.poll()
Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { _ in model.poll() }

app.run()
