import AppKit
import OpenDirectory

enum Outcome: Int32 {
    case approved = 0
    case denied = 2
    case timedOut = 3
    case failed = 4
}

struct Request {
    let reason: String
    let scopeLabel: String
    let timeoutSeconds: Double
    let iconPath: String
    let printsPassword: Bool
}

func parseRequest() -> Request {
    var values: [String: String] = [:]
    var printsPassword = false
    var arguments = CommandLine.arguments.dropFirst().makeIterator()
    while let argument = arguments.next() {
        if argument == "--print-password" {
            printsPassword = true
        } else if let value = arguments.next() {
            values[argument] = value
        }
    }
    return Request(
        reason: values["--reason"] ?? "",
        scopeLabel: values["--scope-label"] ?? "",
        timeoutSeconds: Double(values["--timeout"] ?? "") ?? 120,
        iconPath: values["--icon"] ?? "",
        printsPassword: printsPassword
    )
}

func passwordIsValid(_ password: String) -> Bool {
    guard
        let node = try? ODNode(session: ODSession.default(), type: ODNodeType(kODNodeTypeLocalNodes)),
        let record = try? node.record(withRecordType: kODRecordTypeUsers, name: NSUserName(), attributes: nil)
    else {
        return false
    }
    return (try? record.verifyPassword(password)) != nil
}

func makeAlert(for request: Request, notice: String?) -> (NSAlert, NSSecureTextField) {
    let alert = NSAlert()
    alert.messageText = "A2Assistant bittet um Freigabe"
    let details = "\(request.reason)\n\nBereich: \(request.scopeLabel)\nGilt 10 Minuten und läuft dann automatisch ab."
    alert.informativeText = notice.map { "\($0)\n\n\(details)" } ?? details
    alert.addButton(withTitle: "Freigeben")
    alert.addButton(withTitle: "Ablehnen")
    if let icon = NSImage(contentsOfFile: request.iconPath) {
        alert.icon = icon
    }
    let field = NSSecureTextField(frame: NSRect(x: 0, y: 0, width: 300, height: 24))
    field.placeholderString = "Passwort von \(NSFullUserName())"
    alert.accessoryView = field
    alert.window.initialFirstResponder = field
    alert.window.level = .floating
    return (alert, field)
}

let request = parseRequest()
NSApplication.shared.setActivationPolicy(.accessory)
let timeout = Timer(timeInterval: request.timeoutSeconds, repeats: false) { _ in NSApp.abortModal() }
RunLoop.main.add(timeout, forMode: .modalPanel)
NSApp.activate(ignoringOtherApps: true)

var notice: String?
for _ in 0..<3 {
    let (alert, field) = makeAlert(for: request, notice: notice)
    let response = alert.runModal()
    if response == .abort {
        exit(Outcome.timedOut.rawValue)
    }
    guard response == .alertFirstButtonReturn else {
        exit(Outcome.denied.rawValue)
    }
    let password = field.stringValue
    if passwordIsValid(password) {
        if request.printsPassword {
            FileHandle.standardOutput.write(Data(password.utf8))
        }
        exit(Outcome.approved.rawValue)
    }
    notice = "Das Passwort war falsch."
}
exit(Outcome.failed.rawValue)
