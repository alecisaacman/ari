// ari-eventkit: ARI's bridge to Apple Reminders and Calendar, through EventKit.
// Every command prints one JSON object; failures print {"error": "..."} and exit 1.
import EventKit
import Foundation

let store = EKEventStore()
let iso = ISO8601DateFormatter()

func emit(_ value: Any) -> Never {
    let data = try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write("\n".data(using: .utf8)!)
    exit(0)
}

func fail(_ message: String) -> Never {
    let data = try! JSONSerialization.data(withJSONObject: ["error": message])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write("\n".data(using: .utf8)!)
    exit(1)
}

func access(_ type: EKEntityType) {
    let done = DispatchSemaphore(value: 0)
    var granted = false
    let finish: (Bool, Error?) -> Void = { ok, _ in granted = ok; done.signal() }
    if type == .reminder { store.requestFullAccessToReminders(completion: finish) }
    else { store.requestFullAccessToEvents(completion: finish) }
    done.wait()
    if !granted { fail("ARI doesn't have access to \(type == .reminder ? "Reminders" : "Calendar").") }
}

func date(_ raw: String?) -> Date? {
    guard let raw, !raw.isEmpty else { return nil }
    return iso.date(from: raw)
}

func reminderList(_ name: String) -> EKCalendar {
    guard let list = store.calendars(for: .reminder).first(where: { $0.title == name }) else {
        fail("There's no Reminders list named \(name).")
    }
    return list
}

func describe(_ r: EKReminder) -> [String: Any] {
    var out: [String: Any] = ["id": r.calendarItemIdentifier, "title": r.title ?? "", "list": r.calendar.title, "completed": r.isCompleted]
    if let due = r.dueDateComponents?.date { out["due"] = iso.string(from: due) }
    if let notes = r.notes, !notes.isEmpty { out["notes"] = notes }
    return out
}

func describe(_ e: EKEvent) -> [String: Any] {
    var out: [String: Any] = ["id": e.eventIdentifier ?? "", "title": e.title ?? "", "calendar": e.calendar.title,
                              "start": iso.string(from: e.startDate), "end": iso.string(from: e.endDate), "all_day": e.isAllDay]
    if let location = e.location, !location.isEmpty { out["location"] = location }
    return out
}

// Arguments come as one JSON object on stdin, so titles and notes never need shell quoting.
let command = CommandLine.arguments.dropFirst().first ?? ""
let input = (try? JSONSerialization.jsonObject(with: FileHandle.standardInput.readDataToEndOfFile())) as? [String: Any] ?? [:]

switch command {
case "reminders":
    access(.reminder)
    let list = reminderList(input["list"] as? String ?? "")
    let done = DispatchSemaphore(value: 0)
    var found: [EKReminder] = []
    store.fetchReminders(matching: store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: nil, calendars: [list])) {
        found = $0 ?? []; done.signal()
    }
    done.wait()
    emit(["reminders": found.map(describe)])

case "add-reminder":
    access(.reminder)
    let reminder = EKReminder(eventStore: store)
    reminder.calendar = reminderList(input["list"] as? String ?? "")
    reminder.title = input["title"] as? String ?? ""
    reminder.notes = input["notes"] as? String
    if let due = date(input["due"] as? String) {
        reminder.dueDateComponents = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute, .timeZone], from: due)
        reminder.addAlarm(EKAlarm(absoluteDate: due))
    }
    do { try store.save(reminder, commit: true) } catch { fail("Reminders refused it: \(error.localizedDescription)") }
    emit(["reminder": describe(reminder)])

case "complete-reminder", "remove-reminder":
    access(.reminder)
    guard let item = store.calendarItem(withIdentifier: input["id"] as? String ?? "") as? EKReminder else {
        fail("That reminder isn't in Reminders anymore.")
    }
    do {
        if command == "complete-reminder" { item.isCompleted = true; try store.save(item, commit: true) }
        else { try store.remove(item, commit: true) }
    } catch { fail("Reminders refused it: \(error.localizedDescription)") }
    emit(["reminder": describe(item)])

case "events":
    access(.event)
    guard let start = date(input["start"] as? String), let end = date(input["end"] as? String) else { fail("Give a start and an end.") }
    let events = store.events(matching: store.predicateForEvents(withStart: start, end: end, calendars: nil))
    emit(["events": events.sorted { $0.startDate < $1.startDate }.map(describe)])

case "add-event":
    access(.event)
    let name = input["calendar"] as? String ?? ""
    guard let calendar = store.calendars(for: .event).first(where: { $0.title == name && $0.allowsContentModifications }) else {
        fail("There's no calendar named \(name) that ARI can add to.")
    }
    guard let start = date(input["start"] as? String), let end = date(input["end"] as? String), end > start else {
        fail("Give a start and an end after it.")
    }
    let event = EKEvent(eventStore: store)
    event.calendar = calendar
    event.title = input["title"] as? String ?? ""
    event.startDate = start
    event.endDate = end
    event.notes = input["notes"] as? String
    event.location = input["location"] as? String
    do { try store.save(event, span: .thisEvent, commit: true) } catch { fail("Calendar refused it: \(error.localizedDescription)") }
    emit(["event": describe(event)])

default:
    fail("Unknown command \(command).")
}
