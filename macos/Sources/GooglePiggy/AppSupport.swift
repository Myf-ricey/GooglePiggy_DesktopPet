import AppKit
import Darwin
import Foundation

let appDisplayName = "GooglePiggy Desktop Pet"
let appBundleIdentifier = "com.myf-ricey.GooglePiggyDesktopPet"
let stateDirectoryName = "GifPigDesktopPet"
let autostartLabel = "com.myf-ricey.GooglePiggyDesktopPet.autostart"

let validStatuses: Set<String> = [
    "idle", "thinking", "working", "compacting", "interrupted", "success", "error", "permission",
]

func defaultStateDirectory() -> URL {
    if
        let override = ProcessInfo.processInfo.environment[
            "GOOGLEPIGGY_STATE_DIR"
        ],
        !override.isEmpty
    {
        return URL(fileURLWithPath: override, isDirectory: true)
            .standardizedFileURL
    }
    let support = FileManager.default.urls(
        for: .applicationSupportDirectory,
        in: .userDomainMask
    ).first!
    return support.appendingPathComponent(
        Bundle.main.object(forInfoDictionaryKey: "GooglePiggyStateDirectory") as? String ?? stateDirectoryName,
        isDirectory: true
    )
}

func defaultStatusURL() -> URL {
    hookActorID.isEmpty ? defaultStateDirectory().appendingPathComponent("codex-status.json") : actorStatusURL(hookActorID)
}

func heartbeatURL() -> URL {
    defaultStateDirectory().appendingPathComponent("pig-heartbeat.json")
}

func permissionDirectoryURL() -> URL {
    defaultStateDirectory().appendingPathComponent(
        "permission-requests",
        isDirectory: true
    )
}

func utcTimestamp() -> String {
    ISO8601DateFormatter().string(from: Date())
}

func parseTimestamp(_ value: String) -> Date? {
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [
        .withInternetDateTime,
        .withFractionalSeconds,
    ]
    return fractional.date(from: value) ?? ISO8601DateFormatter().date(from: value)
}

func readJSONDictionary(_ url: URL) -> [String: Any]? {
    guard
        let data = try? Data(contentsOf: url),
        let object = try? JSONSerialization.jsonObject(with: data),
        let dictionary = object as? [String: Any]
    else {
        return nil
    }
    return dictionary
}

func writeJSONAtomic(_ value: Any, to url: URL) throws {
    try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(),
        withIntermediateDirectories: true
    )
    let data = try JSONSerialization.data(
        withJSONObject: value,
        options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    )
    var terminated = data
    terminated.append(0x0A)
    try terminated.write(to: url, options: .atomic)
}

func appendJSONLine(_ value: Any, to url: URL) {
    guard
        let data = try? JSONSerialization.data(
            withJSONObject: value,
            options: [.sortedKeys, .withoutEscapingSlashes]
        )
    else {
        return
    }
    do {
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        let handle = try FileHandle(forWritingTo: url)
        try handle.seekToEnd()
        try handle.write(contentsOf: data)
        try handle.write(contentsOf: Data([0x0A]))
        try handle.close()
    } catch {
        // The pet bridge is decorative and must not interrupt Codex.
    }
}

@discardableResult
func writeBridgeState(
    status: String,
    event: String,
    sessionID: String = "",
    turnID: String = "",
    message: String = "",
    permissionRequestID: String = "",
    source: String = "codex-hook",
    statusURL: URL = defaultStatusURL()
) throws -> [String: Any] {
    guard validStatuses.contains(status) else {
        throw NSError(
            domain: appBundleIdentifier,
            code: 1,
            userInfo: [NSLocalizedDescriptionKey: "Unsupported status: \(status)"]
        )
    }
    let updatedAt = utcTimestamp()
    var state: [String: Any] = [
        "status": status,
        "token": "\(DispatchTime.now().uptimeNanoseconds)-\(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased())",
        "updated_at": updatedAt,
        "source": source,
        "event": event,
        "message": message,
        "session_id": sessionID,
        "turn_id": turnID,
    ]
    if !permissionRequestID.isEmpty {
        state["permission_request_id"] = permissionRequestID
    }
    for (key, value) in hookMetadata { state[key] = value }
    state["received_at"] = Date().timeIntervalSince1970
    try writeJSONAtomic(state, to: statusURL)
    let filename = String(format: "%020.6f", Date().timeIntervalSince1970) + "-" + UUID().uuidString + ".json"
    try writeJSONAtomic(state, to: familyEventDirectory().appendingPathComponent(filename))

    var log: [String: Any] = [
        "updated_at": updatedAt,
        "status": status,
        "event": event,
        "session_id": sessionID,
        "turn_id": turnID,
    ]
    if !permissionRequestID.isEmpty {
        log["permission_request_id"] = permissionRequestID
    }
    appendJSONLine(
        log,
        to: statusURL.deletingLastPathComponent()
            .appendingPathComponent("codex-hook-events.jsonl")
    )
    return state
}

func currentExecutableURL() -> URL {
    URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL
}

func runProcess(
    executable: URL,
    arguments: [String],
    wait: Bool = true
) throws -> Int32 {
    let process = Process()
    process.executableURL = executable
    process.arguments = arguments
    process.standardInput = FileHandle.nullDevice
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice
    try process.run()
    if wait {
        process.waitUntilExit()
        return process.terminationStatus
    }
    return 0
}

func launchAgentURL() -> URL {
    FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/LaunchAgents", isDirectory: true)
        .appendingPathComponent("\(autostartLabel).plist")
}

func isAutostartEnabled() -> Bool {
    FileManager.default.fileExists(atPath: launchAgentURL().path)
}

func setAutostart(_ enabled: Bool, executableURL: URL = currentExecutableURL()) throws {
    let plistURL = launchAgentURL()
    let domain = "gui/\(getuid())"
    if enabled {
        try FileManager.default.createDirectory(
            at: plistURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let plist: [String: Any] = [
            "Label": autostartLabel,
            "ProgramArguments": [executableURL.path],
            "RunAtLoad": true,
            "KeepAlive": false,
            "ProcessType": "Interactive",
        ]
        let data = try PropertyListSerialization.data(
            fromPropertyList: plist,
            format: .xml,
            options: 0
        )
        try data.write(to: plistURL, options: .atomic)
        _ = try? runProcess(
            executable: URL(fileURLWithPath: "/bin/launchctl"),
            arguments: ["bootout", domain, plistURL.path]
        )
        _ = try? runProcess(
            executable: URL(fileURLWithPath: "/bin/launchctl"),
            arguments: ["bootstrap", domain, plistURL.path]
        )
    } else {
        _ = try? runProcess(
            executable: URL(fileURLWithPath: "/bin/launchctl"),
            arguments: ["bootout", domain, plistURL.path]
        )
        try? FileManager.default.removeItem(at: plistURL)
    }
}

func hookCommand(executableURL: URL = currentExecutableURL()) -> String {
    let escaped = executableURL.path.replacingOccurrences(
        of: "'",
        with: "'\"'\"'"
    )
    return "'\(escaped)' --hook"
}

func isGooglePiggyHook(_ hook: [String: Any]) -> Bool {
    guard let command = hook["command"] as? String else {
        return false
    }
    return command.contains("--hook")
        && (
            command.contains("GooglePiggy")
                || command.contains("codex-pig-hook.py")
        )
}

func cleanedHookGroups(_ value: Any?) -> [[String: Any]] {
    guard let groups = value as? [Any] else {
        return []
    }
    var kept: [[String: Any]] = []
    for case let group as [String: Any] in groups {
        let hooks = (group["hooks"] as? [Any] ?? []).compactMap {
            $0 as? [String: Any]
        }.filter { !isGooglePiggyHook($0) }
        if hooks.isEmpty {
            continue
        }
        var copy = group
        copy["hooks"] = hooks
        kept.append(copy)
    }
    return kept
}

func codexHooksURL() -> URL {
    if let configured = ProcessInfo.processInfo.environment["CODEX_HOME"], !configured.isEmpty {
        return URL(fileURLWithPath: configured, isDirectory: true)
            .appendingPathComponent("hooks.json")
    }
    return FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".codex", isDirectory: true)
        .appendingPathComponent("hooks.json")
}

func updateCodexHooks(install: Bool, executableURL: URL = currentExecutableURL()) throws {
    let hooksURL = codexHooksURL()
    try FileManager.default.createDirectory(
        at: hooksURL.deletingLastPathComponent(),
        withIntermediateDirectories: true
    )
    var config = readJSONDictionary(hooksURL) ?? ["hooks": [String: Any]()]
    if FileManager.default.fileExists(atPath: hooksURL.path) {
        let suffix = install ? ".bak-pig-pet" : ".bak-pig-pet-uninstall"
        let backupURL = URL(fileURLWithPath: hooksURL.path + suffix)
        try? FileManager.default.removeItem(at: backupURL)
        try FileManager.default.copyItem(at: hooksURL, to: backupURL)
    }

    var hooks = config["hooks"] as? [String: Any] ?? [:]
    for (event, value) in hooks {
        hooks[event] = cleanedHookGroups(value)
    }

    if install {
        let timeouts: [(String, Int)] = [
            ("SessionStart", 10),
            ("UserPromptSubmit", 10),
            ("PreToolUse", 10),
            ("PostToolUse", 10),
            ("Stop", 10),
            ("Interrupt", 3),
            ("PreCompact", 10),
            ("PostCompact", 10),
            ("SubagentStart", 10),
            ("SubagentStop", 10),
            ("SessionEnd", 10),
            ("PermissionRequest", 600),
        ]
        let command = hookCommand(executableURL: executableURL)
        for (event, timeout) in timeouts {
            let group: [String: Any] = [
                "hooks": [[
                    "type": "command",
                    "command": command,
                    "timeout": timeout,
                ]],
            ]
            let existing = hooks[event] as? [[String: Any]] ?? []
            hooks[event] = [group] + existing
        }
    }
    config["hooks"] = hooks
    try writeJSONAtomic(config, to: hooksURL)
}

final class InstanceLock {
    private var descriptor: Int32 = -1

    init?() {
        let directory = defaultStateDirectory()
        try? FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true
        )
        let path = directory.appendingPathComponent("pig-pet.lock").path
        descriptor = open(path, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
        guard descriptor >= 0, flock(descriptor, LOCK_EX | LOCK_NB) == 0 else {
            if descriptor >= 0 {
                close(descriptor)
            }
            return nil
        }
    }

    deinit {
        if descriptor >= 0 {
            flock(descriptor, LOCK_UN)
            close(descriptor)
        }
    }
}

// Appearance values are independent of task state and survive application updates.
final class PetAppearance {
    static let shared = PetAppearance()
    private let defaults: UserDefaults
    init(defaults: UserDefaults = .standard) { self.defaults = defaults }
    func number(_ key: String, fallback: Double = 1) -> CGFloat {
        let value = defaults.object(forKey: "appearance." + key) as? Double ?? fallback
        let lower = key == "dialogGap" ? -80.0 : key == "taskGap" ? 0.0 : 0.1
        let upper = key.hasSuffix("Gap") ? 200.0 : 2.0
        return CGFloat(value.isFinite ? min(upper, max(lower, value)) : fallback)
    }
    func set(_ key: String, _ value: Double) { defaults.set(value, forKey: "appearance." + key) }
    func color(_ key: String, fallback: NSColor) -> NSColor {
        guard let rgb = defaults.array(forKey: "appearance." + key) as? [Double], rgb.count == 3 else { return fallback }
        return NSColor(srgbRed: rgb[0], green: rgb[1], blue: rgb[2], alpha: 1)
    }
    func setColor(_ key: String, _ color: NSColor) {
        guard let rgb = color.usingColorSpace(.sRGB) else { return }
        defaults.set([rgb.redComponent, rgb.greenComponent, rgb.blueComponent], forKey: "appearance." + key)
    }
    var petScale: CGFloat { number("petScale") }
    var dialogScale: CGFloat { number("dialogScale") }
    var taskScale: CGFloat { number("taskScale") }
    // nil preserves each original renderer's cream-to-pink gradient.
    var customDialogColor: NSColor? {
        guard let rgb = defaults.array(forKey: "appearance.dialogColor") as? [Double], rgb.count == 3 else { return nil }
        return color("dialogColor", fallback: .white)
    }
    var dialogColor: NSColor { customDialogColor ?? NSColor(calibratedRed: 0.985, green: 0.90, blue: 0.92, alpha: 1) }
    func customColor(_ key: String) -> NSColor? {
        guard let rgb = defaults.array(forKey: "appearance." + key) as? [Double], rgb.count == 3 else { return nil }
        return color(key, fallback: .black)
    }
    var dialogTextColor: NSColor? { customColor("dialogTextColor") }
    var buttonTextColor: NSColor? { customColor("buttonTextColor") }
    var taskTextColor: NSColor? { customColor("taskTextColor") }
    var resolvedTaskTextColor: NSColor {
        if let taskTextColor { return taskTextColor }
        let rgb = taskColor.usingColorSpace(.sRGB)
        let light = rgb.map { ($0.redComponent + $0.greenComponent + $0.blueComponent) / 3 } ?? 1
        return light < 0.45 ? .white : .black
    }
    var dialogGap: CGFloat { number("dialogGap", fallback: 0) }
    var taskGap: CGFloat { number("taskGap", fallback: 8) }
    var taskColor: NSColor { color("taskColor", fallback: .windowBackgroundColor) }
    func reset() {
        for key in ["petScale", "dialogScale", "taskScale", "dialogOpacity", "buttonOpacity", "taskOpacity", "dialogColor", "taskColor", "dialogTextColor", "buttonTextColor", "taskTextColor", "dialogGap", "taskGap"] {
            defaults.removeObject(forKey: "appearance." + key)
        }
    }
}

final class AppearancePanel: NSObject, NSWindowDelegate {
    private var window: NSWindow?
    var onChange: (() -> Void)?
    var onPreview: ((Bool, Bool, NSRect) -> Void)?
    private var dialogPreview: NSButton?
    private var taskPreview: NSButton?
    private let appearance: PetAppearance
    private var sliders: [String: NSSlider] = [:]
    private var colorWells: [String: NSColorWell] = [:]
    init(appearance: PetAppearance = .shared) {
        self.appearance = appearance
        super.init()
    }
    private var values: [String: NSTextField] = [:]
    func show() {
        if let window { window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true); return }
        let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 440, height: 624),
                            styleMask: [.titled, .closable], backing: .buffered, defer: false)
        panel.title = "外观"; panel.isReleasedWhenClosed = false; panel.level = .floating
        window = panel
        panel.delegate = self
        let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 14
        stack.frame = NSRect(x: 24, y: 24, width: 392, height: 576)
        panel.contentView?.addSubview(stack)
        let hint = NSTextField(labelWithString: "实时保存；透明度仅影响背景，文字保持清晰。")
        hint.font = .systemFont(ofSize: 12); hint.textColor = .secondaryLabelColor; stack.addArrangedSubview(hint)
        for (label, key, lower, upper, fallback) in [
            ("桌宠大小", "petScale", 0.5, 2.0, 1.0),
            ("对话框大小", "dialogScale", 0.5, 2.0, 1.0),
            ("对话框不透明度", "dialogOpacity", 0.1, 1.0, 1.0),
            ("按钮不透明度", "buttonOpacity", 0.1, 1.0, 1.0),
            ("任务栏大小", "taskScale", 0.5, 2.0, 1.0),
            ("任务栏不透明度", "taskOpacity", 0.1, 1.0, 0.9),
            ("对话框间距偏移", "dialogGap", -80.0, 200.0, 0.0),
            ("任务栏间距", "taskGap", 0.0, 200.0, 8.0)
        ] {
            let title = NSTextField(labelWithString: label); title.widthAnchor.constraint(equalToConstant: 112).isActive = true
            let slider = NSSlider(value: Double(appearance.number(key, fallback: fallback)), minValue: lower, maxValue: upper, target: self, action: #selector(slide(_:)))
            slider.identifier = NSUserInterfaceItemIdentifier(key); slider.isContinuous = true
            sliders[key] = slider
            slider.widthAnchor.constraint(equalToConstant: 200).isActive = true
            let value = NSTextField(labelWithString: formatted(key, slider.doubleValue))
            value.widthAnchor.constraint(equalToConstant: 48).isActive = true; values[key] = value
            stack.addArrangedSubview(NSStackView(views: [title, slider, value]))
        }
        var colors = NSStackView(); colors.spacing = 12
        for (title, key, color) in [("对话框颜色", "dialogColor", appearance.dialogColor), ("任务栏颜色", "taskColor", appearance.taskColor),
            ("对话框文字", "dialogTextColor", appearance.dialogTextColor ?? NSColor(calibratedRed: 0.29, green: 0.23, blue: 0.25, alpha: 1)),
            ("按钮文字", "buttonTextColor", appearance.buttonTextColor ?? .white),
            ("任务栏文字颜色", "taskTextColor", appearance.resolvedTaskTextColor)] {
            if key == "dialogTextColor" || key == "taskTextColor" {
                stack.addArrangedSubview(colors); colors = NSStackView(); colors.spacing = 12
            }
            colors.addArrangedSubview(NSTextField(labelWithString: title))
            let well = NSColorWell(frame: NSRect(x: 0, y: 0, width: 44, height: 26))
            well.color = color; well.identifier = NSUserInterfaceItemIdentifier(key)
            colorWells[key] = well
            if key == "dialogColor" { well.toolTip = "默认为原版奶油色至浅粉色渐变；选色后使用自定义颜色。" }
            well.target = self; well.action = #selector(changeColor(_:)); colors.addArrangedSubview(well)
        }
        stack.addArrangedSubview(colors)
        let dialog = NSButton(checkboxWithTitle: "预览对话框", target: self, action: #selector(togglePreview(_:)))
        let tasks = NSButton(checkboxWithTitle: "预览任务栏", target: self, action: #selector(togglePreview(_:)))
        dialogPreview = dialog; taskPreview = tasks
        let previews = NSStackView(views: [dialog, tasks]); previews.spacing = 24
        stack.addArrangedSubview(previews)
        stack.addArrangedSubview(NSButton(title: "恢复默认", target: self, action: #selector(reset)))
        panel.center(); panel.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
    }
    @objc private func togglePreview(_ sender: NSButton) { updatePreview() }
    private func updatePreview() {
        onPreview?(dialogPreview?.state == .on, taskPreview?.state == .on, window?.frame ?? .zero)
    }
    func windowDidMove(_ notification: Notification) { updatePreview() }
    func windowWillClose(_ notification: Notification) {
        dialogPreview?.state = .off; taskPreview?.state = .off; updatePreview()
    }
    private func formatted(_ key: String, _ value: Double) -> String {
        key.hasSuffix("Gap") ? "\(Int(value)) pt" : "\(Int(value * 100))%"
    }
    @objc private func slide(_ sender: NSSlider) {
        guard let key = sender.identifier?.rawValue else { return }
        appearance.set(key, sender.doubleValue); values[key]?.stringValue = formatted(key, sender.doubleValue); onChange?()
    }
    @objc private func changeColor(_ sender: NSColorWell) {
        guard let key = sender.identifier?.rawValue else { return }
        appearance.setColor(key, sender.color); onChange?()
    }
    @objc private func reset() {
        appearance.reset()
        for (key, slider) in sliders {
            slider.doubleValue = Double(appearance.number(key, fallback: key == "dialogGap" ? 0 : key == "taskGap" ? 8 : key == "taskOpacity" ? 0.9 : 1))
            values[key]?.stringValue = formatted(key, slider.doubleValue)
        }
        colorWells["dialogColor"]?.color = appearance.dialogColor
        colorWells["taskColor"]?.color = appearance.taskColor
        colorWells["dialogTextColor"]?.color = NSColor(calibratedRed: 0.29, green: 0.23, blue: 0.25, alpha: 1)
        colorWells["buttonTextColor"]?.color = .white
        colorWells["taskTextColor"]?.color = appearance.resolvedTaskTextColor
        onChange?()

    }
}
