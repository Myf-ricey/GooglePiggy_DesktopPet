import AppKit
import Darwin
import Foundation

signal(SIGPIPE, SIG_IGN)

let arguments = Array(CommandLine.arguments.dropFirst())

if arguments.first == "--hook" {
    runCodexHook()
    exit(EXIT_SUCCESS)
}

if arguments.first == "--watch-completion" {
    guard arguments.count >= 3 else {
        exit(EXIT_FAILURE)
    }
    runCompletionWatcher(sessionID: arguments[1], turnID: arguments[2])
    exit(EXIT_SUCCESS)
}

if arguments.first == "--install-hooks" {
    do {
        try updateCodexHooks(install: true)
        print("codex_hooks=installed")
        exit(EXIT_SUCCESS)
    } catch {
        fputs("Failed to install Codex hooks: \(error)\n", stderr)
        exit(EXIT_FAILURE)
    }
}

if arguments.first == "--uninstall-hooks" {
    do {
        try updateCodexHooks(install: false)
        print("codex_hooks=removed")
        exit(EXIT_SUCCESS)
    } catch {
        fputs("Failed to remove Codex hooks: \(error)\n", stderr)
        exit(EXIT_FAILURE)
    }
}

if arguments.first == "--enable-autostart"
    || arguments.first == "--disable-autostart"
{
    do {
        try setAutostart(arguments.first == "--enable-autostart")
        print(
            arguments.first == "--enable-autostart"
                ? "autostart=enabled"
                : "autostart=disabled"
        )
        exit(EXIT_SUCCESS)
    } catch {
        fputs("Failed to update autostart: \(error)\n", stderr)
        exit(EXIT_FAILURE)
    }
}

if arguments.first == "--bridge-event" {
    guard arguments.count >= 2, validStatuses.contains(arguments[1]) else {
        fputs(
            "Usage: GooglePiggy --bridge-event STATUS [MESSAGE] [--permission-request-id ID]\n",
            stderr
        )
        exit(EXIT_FAILURE)
    }
    var message = ""
    var permissionRequestID = ""
    var index = 2
    while index < arguments.count {
        if arguments[index] == "--permission-request-id", index + 1 < arguments.count {
            permissionRequestID = arguments[index + 1]
            index += 2
        } else if message.isEmpty {
            message = arguments[index]
            index += 1
        } else {
            fputs("Unexpected bridge argument: \(arguments[index])\n", stderr)
            exit(EXIT_FAILURE)
        }
    }
    do {
        try writeBridgeState(
            status: arguments[1],
            event: "manual",
            message: message,
            permissionRequestID: permissionRequestID,
            source: "pig-pet-cli"
        )
        exit(EXIT_SUCCESS)
    } catch {
        fputs("Failed to write bridge status: \(error)\n", stderr)
        exit(EXIT_FAILURE)
    }
}

if arguments.first == "--preview-permission" {
    let seconds = arguments.count >= 2
        ? max(1, min(600, Double(arguments[1]) ?? 10))
        : 10
    let requestID = "preview-\(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased())"
    let requestURL = permissionDirectoryURL()
        .appendingPathComponent("\(requestID).request.json")
    let responseURL = permissionDirectoryURL()
        .appendingPathComponent("\(requestID).response.json")
    let now = Date()
    do {
        try writeJSONAtomic(
            [
                "request_id": requestID,
                "created_at": ISO8601DateFormatter().string(from: now),
                "expires_at": ISO8601DateFormatter().string(
                    from: now.addingTimeInterval(seconds)
                ),
                "session_id": "manual-preview",
                "turn_id": "manual-preview",
                "tool_name": "修改文件",
                "summary":
                    "Codex 准备修改文件“~/Documents/杂七杂八的东东/测试一下.txt”，是否允许执行本次修改？",
            ],
            to: requestURL
        )
        try writeBridgeState(
            status: "permission",
            event: "PermissionRequest",
            sessionID: "manual-preview",
            turnID: "manual-preview",
            permissionRequestID: requestID,
            source: "pig-pet-cli"
        )
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline {
            if let response = readJSONDictionary(responseURL) {
                print(
                    "permission_preview_decision=\(response["decision"] as? String ?? "unknown")"
                )
                break
            }
            Thread.sleep(forTimeInterval: 0.1)
        }
        try? FileManager.default.removeItem(at: requestURL)
        try? FileManager.default.removeItem(at: responseURL)
        if
            let state = readJSONDictionary(defaultStatusURL()),
            state["permission_request_id"] as? String == requestID
        {
            try writeBridgeState(
                status: "idle",
                event: "PermissionPreviewComplete",
                sessionID: "manual-preview",
                turnID: "manual-preview",
                source: "pig-pet-cli"
            )
        }
        exit(EXIT_SUCCESS)
    } catch {
        fputs("Failed to preview permission UI: \(error)\n", stderr)
        exit(EXIT_FAILURE)
    }
}

if arguments.first == "--show-state-path" {
    print(defaultStateDirectory().path)
    exit(EXIT_SUCCESS)
}

if arguments.first == "--self-test" {
    do {
        try runManifestSelfTest()
        exit(EXIT_SUCCESS)
    } catch {
        fputs("Self-test failed: \(error)\n", stderr)
        exit(EXIT_FAILURE)
    }
}

let application = NSApplication.shared
application.setActivationPolicy(.accessory)
let controller = PetController()
application.delegate = controller
application.run()
