import Darwin
import Foundation

let appDisplayName = "GooglePiggy Desktop Pet"
let appBundleIdentifier = "com.myf-ricey.GooglePiggyDesktopPet"
let stateDirectoryName = "GifPigDesktopPet"
let autostartLabel = "com.myf-ricey.GooglePiggyDesktopPet.autostart"

let validStatuses: Set<String> = [
    "idle", "thinking", "success", "error", "permission",
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
    return support.appendingPathComponent(stateDirectoryName, isDirectory: true)
}

func defaultStatusURL() -> URL {
    defaultStateDirectory().appendingPathComponent("codex-status.json")
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
    try writeJSONAtomic(state, to: statusURL)

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
