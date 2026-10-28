// ARI Pet: a small owl that lives on top of the desktop, apart from the hub.
// It reads ~/ARI/state/pet-status.json (written by ARI's poller), so it never calls
// a model or the API. Drag it anywhere: it leans, flaps, and dangles with the drag.
// Click it to open the hub; hover for a one-line status; right-click for more.
import AppKit
import SwiftUI

// MARK: - Status

struct PetStatus: Decodable {
    let updatedAt: String
    let paused: Bool
    let pausedReason: String?
    let thinking: Bool
    let outOfCredits: Bool
    let budgetUsedUp: Bool
    let spend: String
    let needsYou: Int
    let latest: String?
}

enum Mood { case idle, thinking, alert, asleep, outOfCredits, offline }
enum DragPose { case none, left, right, up, down }

let ariHome = URL(fileURLWithPath: ProcessInfo.processInfo.environment["ARI_HOME"] ?? NSHomeDirectory() + "/ARI")
let statusURL = ariHome.appendingPathComponent("state/pet-status.json")
let hubApp = URL(fileURLWithPath: NSHomeDirectory() + "/Applications/ARI Hub.app")
// The poller writes every 10 seconds while the Mac is awake; older than this means ARI isn't running.
let staleAfter: TimeInterval = 180

final class PetModel: ObservableObject {
    @Published var mood: Mood = .offline
    @Published var drag: DragPose = .none
    @Published var bubble: String?
    var status: PetStatus?
    private var lastLatest: String?
    private var firstRead = true
    private var bubbleTimer: Timer?

    func poll() {
        let decoder = JSONDecoder()
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let data = try? Data(contentsOf: statusURL), let status = try? decoder.decode(PetStatus.self, from: data) else {
            self.status = nil
            mood = .offline
            return
        }
        self.status = status
        let updated = iso.date(from: status.updatedAt) ?? ISO8601DateFormatter().date(from: status.updatedAt) ?? .distantPast
        let hour = Calendar.current.component(.hour, from: Date())
        if Date().timeIntervalSince(updated) > staleAfter {
            mood = .offline
        } else if status.outOfCredits || status.budgetUsedUp {
            mood = .outOfCredits
        } else if status.thinking {
            mood = .thinking
        } else if status.paused || hour >= 23 || hour < 6 {
            mood = .asleep
        } else if status.needsYou > 0 {
            mood = .alert
        } else {
            mood = .idle
        }
        // Something new from ARI: say it, briefly.
        if let latest = status.latest, latest != lastLatest {
            if !firstRead { say(latest, seconds: 8) }
            lastLatest = latest
        }
        firstRead = false
    }

    var summary: String {
        guard let status else { return "ARI isn't running. Its status file is missing." }
        switch mood {
        case .offline: return "ARI hasn't checked in for a few minutes. Is the Mac asleep?"
        case .outOfCredits:
            return status.budgetUsedUp ? "Out of budget: \(status.spend). Say \"ARI budget\" to raise it." : "Out of Anthropic credits. Top up to wake me."
        case .thinking: return "Thinking about your message..."
        case .asleep: return status.paused ? "Paused. Say \"ARI resume\" when you want me." : "Resting. Text me if you need anything."
        case .alert: return "\(status.needsYou) \(status.needsYou == 1 ? "thing needs" : "things need") you. Click to open the hub."
        case .idle: return "All quiet. \(status.spend)."
        }
    }

    func say(_ text: String, seconds: TimeInterval = 5) {
        let trimmed = text.count > 140 ? String(text.prefix(137)) + "..." : text
        bubble = trimmed
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
            Owl(model: model)
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
            NSWorkspace.shared.openApplication(at: hubApp, configuration: NSWorkspace.OpenConfiguration())
            model.say("Opening the hub.", seconds: 2)
        } else if let origin = window?.frame.origin {
            UserDefaults.standard.set([origin.x, origin.y], forKey: "origin")
        }
    }

    override func rightMouseDown(with event: NSEvent) {
        let menu = NSMenu()
        menu.addItem(withTitle: "Open ARI Hub", action: #selector(openHub), keyEquivalent: "").target = self
        menu.addItem(withTitle: "What's going on?", action: #selector(tell), keyEquivalent: "").target = self
        menu.addItem(.separator())
        menu.addItem(withTitle: "Hide for an hour", action: #selector(hideForAnHour), keyEquivalent: "").target = self
        menu.addItem(withTitle: "Quit ARI Pet", action: #selector(quit), keyEquivalent: "").target = self
        NSMenu.popUpContextMenu(menu, with: event, for: self)
    }

    @objc func openHub() { NSWorkspace.shared.openApplication(at: hubApp, configuration: NSWorkspace.OpenConfiguration()) }
    @objc func tell() { model.say(model.summary, seconds: 6) }
    @objc func hideForAnHour() {
        window?.orderOut(nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + 3600) { [weak self] in self?.window?.orderFrontRegardless() }
    }
    @objc func quit() { NSApp.terminate(nil) }
}

// MARK: - App

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
        for (name, mood, drag, bubble) in poses {
            let model = PetModel()
            model.mood = mood
            model.drag = drag
            model.bubble = bubble
            let renderer = ImageRenderer(content: PetView(model: model).background(Color(white: 0.93)))
            renderer.scale = 2
            if let image = renderer.nsImage, let tiff = image.tiffRepresentation,
               let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) {
                try? png.write(to: directory.appendingPathComponent("\(name).png"))
            }
        }
    }
    exit(0)
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

let model = PetModel()
let size = NSSize(width: 250, height: 210)
let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
var origin = NSPoint(x: screen.maxX - size.width - 24, y: screen.minY + 24)
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
