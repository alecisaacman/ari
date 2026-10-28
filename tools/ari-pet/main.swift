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


// MARK: - The golden retriever

struct Retriever: View {
    @ObservedObject var model: PetModel

    var body: some View {
        TimelineView(.animation) { context in
            dog(at: context.date.timeIntervalSinceReferenceDate)
        }
    }

    @ViewBuilder
    func dog(at t: Double) -> some View {
        let mood = model.mood
        let drag = model.drag
        let dull = mood == .offline || mood == .outOfCredits
        let coat = dull ? Color(hex: 0xb9a079) : Color(hex: 0xe0a446)
        let shade = dull ? Color(hex: 0x9c8462) : Color(hex: 0xc4852c)
        let cream = dull ? Color(hex: 0xe6dccb) : Color(hex: 0xf6dfae)
        let dark = Color(hex: 0x2a1d14)

        let breathe = 1 + 0.02 * sin(t * (mood == .asleep ? 1.0 : 1.9))
        let blinking = t.truncatingRemainder(dividingBy: 4.8) > 4.63
        let eyesClosed = mood == .asleep || mood == .offline || (blinking && drag == .none)
        let sad = mood == .outOfCredits
        let tongue = (mood == .thinking || mood == .alert || drag == .left || drag == .right) && !sad
        let wagSpeed: Double = {
            switch mood {
            case .alert: return 16
            case .thinking: return 11
            case .idle: return 5
            default: return 0
            }
        }()
        let wag = wagSpeed == 0 ? -30 : sin(t * wagSpeed) * 26
        let tilt: Double = {
            switch drag {
            case .left: return -14
            case .right: return 14
            default: return mood == .thinking ? 10 + sin(t * 2) * 3 : 0
            }
        }()
        // Ears trail the motion: they fly up when dragged down, droop when sad.
        let ear: Double = {
            switch drag {
            case .left: return 28
            case .right: return -28
            case .up: return sin(t * 22) * 22
            case .down: return 0
            default: return sad ? -6 : (mood == .alert ? 8 : 0)
            }
        }()
        let earsUp = drag == .down
        let paddle = drag == .up ? sin(t * 20) * 3 : 0
        let hop: Double = mood == .alert && sin(t * 3) > 0.75 ? -3 : 0
        let pupil: CGSize = {
            switch drag {
            case .left: return CGSize(width: -1.6, height: 0)
            case .right: return CGSize(width: 1.6, height: 0)
            case .up: return CGSize(width: 0, height: -1.6)
            case .down: return CGSize(width: 0, height: 1.4)
            default: return .zero
            }
        }()

        ZStack {
            Ellipse().fill(Color.black.opacity(0.10)).frame(width: 46, height: 6).offset(y: 40)

            ZStack {
                // Tail, wagging behind the body
                Capsule().fill(coat).frame(width: 8, height: 26)
                    .rotationEffect(.degrees(40 + wag), anchor: .bottom).offset(x: 20, y: 12)
                // Sitting body and chest
                Ellipse().fill(coat).frame(width: 46, height: 40).offset(y: 18)
                Ellipse().fill(cream).frame(width: 22, height: 26).offset(y: 16)
                // Front paws
                HStack(spacing: 6) {
                    Capsule().fill(coat).frame(width: 10, height: 15).offset(y: paddle)
                    Capsule().fill(coat).frame(width: 10, height: 15).offset(y: -paddle)
                }.offset(y: 31)
                HStack(spacing: 8) {
                    Capsule().fill(cream).frame(width: 9, height: 4)
                    Capsule().fill(cream).frame(width: 9, height: 4)
                }.offset(y: 37)

                // Head
                ZStack {
                    // Floppy ears
                    Ellipse().fill(shade).frame(width: 13, height: 24)
                        .rotationEffect(.degrees(earsUp ? 155 : 18 + ear), anchor: .top).offset(x: earsUp ? -11 : -15, y: earsUp ? 2 : 4)
                    Ellipse().fill(shade).frame(width: 13, height: 24)
                        .rotationEffect(.degrees(earsUp ? -155 : -18 + ear), anchor: .top).offset(x: earsUp ? 11 : 15, y: earsUp ? 2 : 4)
                    Ellipse().fill(coat).frame(width: 34, height: 31)
                    // Muzzle
                    Ellipse().fill(cream).frame(width: 18, height: 13).offset(y: 8)
                    Ellipse().fill(dark).frame(width: 7, height: 5).offset(y: 4)
                    MouthShape().stroke(dark, style: StrokeStyle(lineWidth: 1.2, lineCap: .round))
                        .frame(width: 9, height: 4).rotationEffect(.degrees(sad ? 180 : 0)).offset(y: sad ? 11 : 10)
                    if tongue {
                        Capsule().fill(Color(hex: 0xe8737a)).frame(width: 6, height: 7 + max(0, sin(t * 9)) * 1.5)
                            .offset(y: 14.5)
                    }
                    // Eyes, with brows that tip up when sad
                    HStack(spacing: 9) {
                        dogEye(closed: eyesClosed, pupil: pupil, dark: dark)
                        dogEye(closed: eyesClosed, pupil: pupil, dark: dark)
                    }.offset(y: -3)
                    if sad {
                        HStack(spacing: 11) {
                            Capsule().fill(shade).frame(width: 6, height: 1.6).rotationEffect(.degrees(-20))
                            Capsule().fill(shade).frame(width: 6, height: 1.6).rotationEffect(.degrees(20))
                        }.offset(y: -9)
                    }
                }
                .offset(y: -14)
                .rotationEffect(.degrees(tilt * 0.6), anchor: .bottom)
            }
            .scaleEffect(x: 2 - breathe, y: breathe * (drag == .down ? 1.06 : 1), anchor: .bottom)
            .rotationEffect(.degrees(drag == .left || drag == .right ? tilt * 0.5 : 0), anchor: .bottom)
            .offset(y: hop)

            if mood == .alert {
                Circle().fill(Color(hex: 0xe5484d)).frame(width: 9, height: 9)
                    .overlay(Circle().stroke(Color.white, lineWidth: 1.5)).offset(x: 24, y: -32)
            }
            if mood == .asleep || mood == .offline {
                let phase = t.truncatingRemainder(dividingBy: 3) / 3
                Text("z").font(.system(size: 9, weight: .bold, design: .rounded)).foregroundColor(.secondary)
                    .opacity(sin(phase * .pi)).offset(x: 24, y: -32 - phase * 8)
            }
            if mood == .outOfCredits {
                EmptyBowl().offset(x: 30, y: 36)
            }
            if mood == .thinking {
                HStack(spacing: 3) {
                    ForEach(0..<3) { index in
                        Circle().fill(Color.secondary).frame(width: 4, height: 4)
                            .opacity(0.35 + 0.65 * max(0, sin(t * 5 - Double(index) * 0.7)))
                    }
                }.offset(x: 28, y: -34)
            }
        }
        .frame(width: 84, height: 92)
    }

    func dogEye(closed: Bool, pupil: CGSize, dark: Color) -> some View {
        ZStack {
            if closed {
                Capsule().fill(dark).frame(width: 6, height: 1.6)
            } else {
                Circle().fill(dark).frame(width: 6.5, height: 6.5).offset(pupil)
                Circle().fill(Color.white).frame(width: 2, height: 2).offset(x: pupil.width + 1.2, y: pupil.height - 1.2)
            }
        }
        .frame(width: 8, height: 8)
    }
}

struct MouthShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX, y: rect.minY))
        path.addQuadCurve(to: CGPoint(x: rect.midX, y: rect.minY), control: CGPoint(x: rect.width * 0.25, y: rect.maxY))
        path.addQuadCurve(to: CGPoint(x: rect.maxX, y: rect.minY), control: CGPoint(x: rect.width * 0.75, y: rect.maxY))
        return path
    }
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
            if model.character == .owl { Owl(model: model) } else { Retriever(model: model) }
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
        let owlBox = NSRect(x: bounds.midX - 42, y: 0, width: 84, height: 92)
        return owlBox.contains(local) ? self : nil
    }

    override func updateTrackingAreas() {
        trackingAreas.forEach(removeTrackingArea)
        let owlBox = NSRect(x: bounds.midX - 42, y: 0, width: 84, height: 92)
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
