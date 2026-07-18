import Darwin
import Foundation

private let permissionTimeout: TimeInterval = 600

private func stringValue(_ object: Any?, names: [String]) -> String {
    guard let dictionary = object as? [String: Any] else {
        return ""
    }
    for name in names {
        if let value = dictionary[name] {
            if let string = value as? String {
                return string
            }
            return String(describing: value)
        }
    }
    return ""
}

private func directOrNamedString(
    _ object: Any?,
    names: [String]
) -> String {
    if let string = object as? String {
        return string
    }
    return stringValue(object, names: names)
}

private func protectedPermissionText(
    _ text: String,
    maximumLength: Int? = 260
) -> String {
    if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        return ""
    }
    var value = text
    let patterns = [
        #"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*["']?[^"'\s,;]+"#,
        #"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"#,
        #"[A-Za-z0-9_-]{72,}"#,
    ]
    let replacements = ["$1=[redacted]", "$1[redacted]", "[redacted-token]"]
    for (pattern, replacement) in zip(patterns, replacements) {
        guard let regex = try? NSRegularExpression(
            pattern: pattern,
            options: []
        ) else {
            continue
        }
        value = regex.stringByReplacingMatches(
            in: value,
            range: NSRange(value.startIndex..., in: value),
            withTemplate: replacement
        )
    }
    if let maximumLength, value.count > maximumLength {
        value = String(value.prefix(maximumLength - 1)) + "…"
    }
    return value
}

private func rawToolName(_ payload: [String: Any]) -> String {
    let name = stringValue(
        payload,
        names: ["tool_name", "toolName", "name"]
    ).trimmingCharacters(in: .whitespacesAndNewlines)
    return name.isEmpty ? "Codex" : name
}

private func localizedToolName(_ rawName: String) -> String {
    let name = rawName.lowercased()
    if name.contains("apply_patch")
        || name == "edit"
        || name == "write"
    {
        return "修改文件"
    }
    if name == "bash"
        || name == "shell"
        || name == "exec"
        || name.contains("exec_command")
        || name.contains("functions.exec")
    {
        return "终端命令"
    }
    if name == "read" || name.contains("read_file") {
        return "读取文件"
    }
    if name.contains("web") || name.contains("browser") {
        return "联网访问"
    }
    return "Codex 操作"
}

private func displayPermissionPath(
    _ rawPath: String,
    baseDirectory: String = ""
) -> String {
    var path = rawPath.trimmingCharacters(
        in: CharacterSet(charactersIn: " \t\"'`")
    )
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    if path == "~" {
        path = home
    } else if path.hasPrefix("~/") {
        path = home + String(path.dropFirst())
    } else if path == "$HOME" {
        path = home
    } else if path.hasPrefix("$HOME/") {
        path = home + String(path.dropFirst("$HOME".count))
    }
    if !path.isEmpty, !path.hasPrefix("/") {
        var base = baseDirectory.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        if base == "~" {
            base = home
        } else if base.hasPrefix("~/") {
            base = home + String(base.dropFirst())
        }
        if base.isEmpty {
            base = FileManager.default.currentDirectoryPath
        }
        path = (base as NSString).appendingPathComponent(path)
    }
    if path.hasPrefix("/") {
        path = (path as NSString).standardizingPath
    }
    return protectedPermissionText(path, maximumLength: nil)
}

private func containsChineseText(_ text: String) -> Bool {
    text.unicodeScalars.contains { scalar in
        let value = scalar.value
        return (0x3400...0x4DBF).contains(value)
            || (0x4E00...0x9FFF).contains(value)
            || (0xF900...0xFAFF).contains(value)
    }
}

private func cleanedChinesePermissionReason(_ text: String) -> String {
    var value = protectedPermissionText(text)
    let lowercased = value.lowercased()
    if lowercased.contains("*** begin patch")
        || lowercased.contains("*** update file:")
        || lowercased.contains("*** add file:")
        || lowercased.contains("*** delete file:")
    {
        return ""
    }

    if let prefix = try? NSRegularExpression(
        pattern:
            #"(?i)^\s*(?:apply_patch|bash|shell|exec(?:_command)?|functions\.exec)\s*:\s*"#
    ) {
        value = prefix.stringByReplacingMatches(
            in: value,
            range: NSRange(value.startIndex..., in: value),
            withTemplate: ""
        )
    }
    return containsChineseText(value) ? value : ""
}

private func singlePatchPermissionSummary(
    verb: String,
    path: String
) -> String {
    switch verb {
    case "创建":
        return "Codex 准备创建文件“\(path)”并写入内容，是否允许？"
    case "删除":
        return "Codex 准备删除文件“\(path)”，是否允许？"
    case "移动":
        return "Codex 准备把文件移动到“\(path)”，是否允许？"
    default:
        return "Codex 准备修改文件“\(path)”，是否允许执行本次修改？"
    }
}

private func patchPermissionSummary(
    _ input: Any?,
    baseDirectory: String = ""
) -> String? {
    let patch = directOrNamedString(
        input,
        names: ["input", "patch", "patch_text", "text", "content"]
    )
    guard !patch.isEmpty else {
        return nil
    }

    let markers = [
        ("*** Update File:", "修改"),
        ("*** Add File:", "创建"),
        ("*** Delete File:", "删除"),
        ("*** Move to:", "移动"),
    ]
    var operations: [(verb: String, path: String)] = []
    for line in patch.components(separatedBy: .newlines) {
        for (marker, verb) in markers where line.hasPrefix(marker) {
            let path = displayPermissionPath(
                String(line.dropFirst(marker.count)),
                baseDirectory: baseDirectory
            )
            if !path.isEmpty {
                operations.append((verb, path))
            }
            break
        }
    }

    guard let first = operations.first else {
        return nil
    }
    if operations.count == 1 {
        return singlePatchPermissionSummary(
            verb: first.verb,
            path: first.path
        )
    }

    var seen = Set<String>()
    let uniqueOperations = operations.filter { operation in
        seen.insert("\(operation.verb)\u{0}\(operation.path)").inserted
    }
    if uniqueOperations.count == 1 {
        return singlePatchPermissionSummary(
            verb: first.verb,
            path: first.path
        )
    }
    let pathComponents = uniqueOperations.map {
        $0.path.split(separator: "/", omittingEmptySubsequences: true)
            .map(String.init)
    }
    var commonComponentCount = pathComponents.first?.count ?? 0
    for components in pathComponents.dropFirst() {
        commonComponentCount = min(commonComponentCount, components.count)
        while commonComponentCount > 0,
            Array(components.prefix(commonComponentCount))
                != Array(pathComponents[0].prefix(commonComponentCount))
        {
            commonComponentCount -= 1
        }
    }
    if commonComponentCount > 0 {
        let commonDirectory = "/"
            + pathComponents[0].prefix(commonComponentCount)
                .joined(separator: "/")
        let relativeOperations = zip(
            uniqueOperations,
            pathComponents
        ).compactMap { operation, components
            -> (verb: String, relativePath: String)? in
            let relativePath = components.dropFirst(commonComponentCount)
                .joined(separator: "/")
            guard !relativePath.isEmpty else {
                return nil
            }
            return (operation.verb, relativePath)
        }
        if relativeOperations.count == uniqueOperations.count {
            let details = relativeOperations.map {
                "\($0.verb)“\($0.relativePath)”"
            }.joined(separator: "；")
            return "Codex 准备在“\(commonDirectory)”中：\(details)，是否允许？"
        }
    }
    let details = uniqueOperations.map {
        "\($0.verb)文件“\($0.path)”"
    }.joined(separator: "；")
    return "Codex 准备\(details)，是否允许？"
}

private func readRecentSessionText(_ url: URL) -> String? {
    guard let handle = try? FileHandle(forReadingFrom: url) else {
        return nil
    }
    defer {
        try? handle.close()
    }
    do {
        let end = try handle.seekToEnd()
        let maximumBytes: UInt64 = 8 * 1024 * 1024
        try handle.seek(toOffset: end > maximumBytes ? end - maximumBytes : 0)
        let data = try handle.readToEnd() ?? Data()
        return String(data: data, encoding: .utf8)
    } catch {
        return nil
    }
}

private func sessionWorkingDirectory(sessionID: String) -> String {
    guard
        let sessionURL = newestSessionFile(sessionID: sessionID),
        let handle = try? FileHandle(forReadingFrom: sessionURL)
    else {
        return ""
    }
    defer {
        try? handle.close()
    }
    do {
        try handle.seek(toOffset: 0)
        let data = try handle.read(upToCount: 256 * 1024) ?? Data()
        guard let text = String(data: data, encoding: .utf8) else {
            return ""
        }
        for line in text.split(separator: "\n").prefix(200) {
            guard
                let lineData = line.data(using: .utf8),
                let record = try? JSONSerialization.jsonObject(with: lineData)
                    as? [String: Any],
                record["type"] as? String == "session_meta",
                let payload = record["payload"] as? [String: Any],
                let cwd = payload["cwd"] as? String,
                !cwd.isEmpty
            else {
                continue
            }
            return cwd
        }
    } catch {
        return ""
    }
    return ""
}

private func sessionToolInput(
    sessionID: String,
    turnID: String,
    rawTool: String
) -> String {
    guard !sessionID.isEmpty, !turnID.isEmpty else {
        return ""
    }
    var sessionURL = newestSessionFile(sessionID: sessionID)
    for attempt in 0..<8 {
        var fallbackInput = ""
        if sessionURL == nil {
            sessionURL = newestSessionFile(sessionID: sessionID)
        }
        if let sessionURL, let text = readRecentSessionText(sessionURL) {
            for line in text.split(separator: "\n").reversed().prefix(2000) {
                guard
                    let data = line.data(using: .utf8),
                    let record = try? JSONSerialization.jsonObject(with: data)
                        as? [String: Any],
                    record["type"] as? String == "response_item",
                    let payload = record["payload"] as? [String: Any],
                    payload["type"] as? String == "custom_tool_call",
                    let recordedTool = payload["name"] as? String,
                    let input = payload["input"] as? String,
                    !input.isEmpty,
                    sessionToolNamesMatch(
                        recorded: recordedTool,
                        requested: rawTool,
                        input: input
                    ),
                    let metadata =
                        payload["internal_chat_message_metadata_passthrough"]
                            as? [String: Any],
                    metadata["turn_id"] as? String == turnID
                else {
                    continue
                }
                if sessionInputIsExplicitPermissionCall(
                    recordedTool: recordedTool,
                    input: input
                ) {
                    return input
                }
                if fallbackInput.isEmpty {
                    fallbackInput = input
                }
            }
            if !fallbackInput.isEmpty {
                return fallbackInput
            }
        }
        if attempt < 7 {
            Thread.sleep(forTimeInterval: 0.05)
        }
    }
    return ""
}

private func sessionInputIsExplicitPermissionCall(
    recordedTool: String,
    input: String
) -> Bool {
    if recordedTool.lowercased().contains("apply_patch") {
        return true
    }
    let normalized = input.lowercased()
    return normalized.contains("require_escalated")
        || normalized.contains("\"justification\"")
        || normalized.contains("justification:")
}

private func sessionToolNamesMatch(
    recorded: String,
    requested: String,
    input: String
) -> Bool {
    let recordedName = recorded.lowercased()
    let requestedName = requested.lowercased()
    if requestedName.contains("apply_patch") {
        return recordedName.contains("apply_patch")
            || (
                (
                    recordedName == "exec"
                        || recordedName.contains("exec_command")
                        || recordedName.contains("functions.exec")
                )
                && input.contains("*** Begin Patch")
            )
    }
    if requestedName == "bash"
        || requestedName == "shell"
        || requestedName == "exec"
        || requestedName.contains("exec_command")
        || requestedName.contains("functions.exec")
    {
        return recordedName == "bash"
            || recordedName == "shell"
            || recordedName == "exec"
            || recordedName.contains("exec_command")
            || recordedName.contains("functions.exec")
    }
    return recordedName == requestedName
}

private func firstRegexCapture(
    pattern: String,
    text: String
) -> String? {
    guard
        let regex = try? NSRegularExpression(
            pattern: pattern,
            options: []
        ),
        let match = regex.firstMatch(
            in: text,
            range: NSRange(text.startIndex..., in: text)
        )
    else {
        return nil
    }
    for index in 1..<match.numberOfRanges {
        let range = match.range(at: index)
        guard
            range.location != NSNotFound,
            let swiftRange = Range(range, in: text)
        else {
            continue
        }
        return String(text[swiftRange])
    }
    return nil
}

private func decodedStringField(
    _ input: Any?,
    names: [String]
) -> String {
    let named = stringValue(input, names: names)
        .trimmingCharacters(in: .whitespacesAndNewlines)
    if !named.isEmpty {
        return named
    }
    guard let raw = input as? String else {
        return ""
    }
    let fieldAlternation = names.map {
        NSRegularExpression.escapedPattern(for: $0)
    }.joined(separator: "|")
    guard let encoded = firstRegexCapture(
        pattern:
            #"(?:^|[,{]\s*)(?:"?(?:"# + fieldAlternation + #")"?)\s*:\s*"((?:\\.|[^"\\])*)""#,
        text: raw
    ) else {
        return ""
    }
    let wrapped = "\"\(encoded)\""
    guard
        let data = wrapped.data(using: .utf8),
        let decoded = try? JSONSerialization.jsonObject(
            with: data,
            options: [.fragmentsAllowed]
        ) as? String
    else {
        return ""
    }
    return decoded
}

private func workingDirectoryFromToolInput(_ input: Any?) -> String {
    decodedStringField(
        input,
        names: ["workdir", "cwd", "working_directory"]
    )
}

private func justificationFromToolInput(_ input: Any?) -> String {
    decodedStringField(
        input,
        names: ["justification", "description", "reason"]
    )
}

private func commandFromToolInput(_ input: Any?) -> String {
    let decoded = decodedStringField(input, names: ["command", "cmd"])
    if !decoded.isEmpty {
        return decoded
    }
    guard
        let raw = input as? String,
        !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
        return ""
    }
    if !raw.contains("tools.exec_command")
        && !raw.contains("*** Begin Patch")
    {
        return raw
    }
    return ""
}

private func commandPermissionSummary(
    _ rawCommand: String,
    baseDirectory: String = ""
) -> String? {
    let command = protectedPermissionText(rawCommand)
    guard !command.isEmpty else {
        return nil
    }

    if let application = firstRegexCapture(
        pattern:
            #"(?i)\bopen\s+-a\s+(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))"#,
        text: command
    ) {
        return "Codex 准备打开应用“\(application)”，是否允许？"
    }
    if let application = firstRegexCapture(
        pattern:
            #"(?is)tell\s+application\s+["']([^"']+)["'].*\bactivate\b"#,
        text: command
    ) {
        return "Codex 准备打开应用“\(application)”，是否允许？"
    }
    if let brightness = firstRegexCapture(
        pattern:
            #"(?i)\bbrightness(?:\s+of\s+display\s+\d+\s+to)?\s+([01](?:\.\d+)?)"#,
        text: command
    ), let value = Double(brightness) {
        let percent = Int((min(1, max(0, value)) * 100).rounded())
        return "Codex 准备将屏幕亮度调节为 \(percent)%，是否允许？"
    }
    if let path = firstRegexCapture(
        pattern:
            #"(?i)(?:^|[;&|]\s*)(?:sudo\s+)?rm(?:\s+-[A-Za-z]+)*\s+(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))"#,
        text: command
    ) {
        return "Codex 准备删除“\(displayPermissionPath(path, baseDirectory: baseDirectory))”，是否允许？"
    }
    if let path = firstRegexCapture(
        pattern:
            #"(?i)(?:^|[;&|]\s*)mkdir(?:\s+-[A-Za-z]+)*\s+(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))"#,
        text: command
    ) {
        return "Codex 准备创建文件夹“\(displayPermissionPath(path, baseDirectory: baseDirectory))”，是否允许？"
    }
    if let path = firstRegexCapture(
        pattern:
            #"(?i)(?:^|[;&|]\s*)touch\s+(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))"#,
        text: command
    ) {
        return "Codex 准备创建文件“\(displayPermissionPath(path, baseDirectory: baseDirectory))”，是否允许？"
    }
    if let path = firstRegexCapture(
        pattern:
            #"(?:>|>>)\s*(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))"#,
        text: command
    ) {
        return "Codex 准备创建或覆盖文件“\(displayPermissionPath(path, baseDirectory: baseDirectory))”，是否允许？"
    }
    if let target = firstRegexCapture(
        pattern:
            #"(?i)\bopen\s+(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))"#,
        text: command
    ), !target.hasPrefix("-") {
        return "Codex 准备打开“\(displayPermissionPath(target, baseDirectory: baseDirectory))”，是否允许？"
    }
    if command.lowercased().contains("defaults write") {
        return "Codex 准备修改系统设置，具体命令为“\(command)”，是否允许？"
    }
    return "Codex 准备执行终端命令“\(command)”，是否允许？"
}

private func permissionSummary(
    _ payload: [String: Any],
    rawTool: String,
    sessionID: String,
    turnID: String
) -> String? {
    let input = payload["tool_input"] ?? payload["input"]
    let payloadDirectory = stringValue(
        payload,
        names: ["workdir", "cwd", "working_directory"]
    )
    let sessionDirectory = sessionWorkingDirectory(sessionID: sessionID)
    let inputDirectory = workingDirectoryFromToolInput(input)
    let baseDirectory = !inputDirectory.isEmpty
        ? inputDirectory
        : (!payloadDirectory.isEmpty ? payloadDirectory : sessionDirectory)
    var candidate = stringValue(
        input,
        names: ["justification", "description", "reason"]
    )
    if candidate.isEmpty {
        candidate = stringValue(
            payload,
            names: ["justification", "description", "reason"]
        )
    }
    if candidate.isEmpty {
        candidate = justificationFromToolInput(input)
    }
    let chineseReason = cleanedChinesePermissionReason(candidate)
    let normalizedTool = rawTool.lowercased()
    if normalizedTool.contains("apply_patch") {
        if let summary = patchPermissionSummary(
            input,
            baseDirectory: baseDirectory
        ) {
            return summary
        }
        let recoveredInput = sessionToolInput(
            sessionID: sessionID,
            turnID: turnID,
            rawTool: rawTool
        )
        let recoveredDirectory = workingDirectoryFromToolInput(recoveredInput)
        let recoveredReason = cleanedChinesePermissionReason(
            justificationFromToolInput(recoveredInput)
        )
        if !recoveredReason.isEmpty {
            return recoveredReason
        }
        if let summary = patchPermissionSummary(
            recoveredInput,
            baseDirectory: recoveredDirectory.isEmpty
                ? baseDirectory
                : recoveredDirectory
        ) {
            return summary
        }
        if let summary = patchPermissionSummary(
            commandFromToolInput(recoveredInput),
            baseDirectory: recoveredDirectory.isEmpty
                ? baseDirectory
                : recoveredDirectory
        ) {
            return summary
        }
        if !chineseReason.isEmpty {
            return chineseReason
        }
        return nil
    }

    let command = commandFromToolInput(input)
    if let summary = commandPermissionSummary(
        command,
        baseDirectory: baseDirectory
    ) {
        return summary
    }

    let path = displayPermissionPath(
        stringValue(input, names: ["path", "file_path"]),
        baseDirectory: baseDirectory
    )
    if !path.isEmpty {
        let action = localizedToolName(rawTool)
        return "是否允许\(action)“\(path)”？"
    }

    candidate = protectedPermissionText(
        stringValue(input, names: ["query"])
    )
    if !candidate.isEmpty {
        return "是否允许执行此操作：\(candidate)？"
    }

    let recoveredInput = sessionToolInput(
        sessionID: sessionID,
        turnID: turnID,
        rawTool: rawTool
    )
    let recoveredDirectory = workingDirectoryFromToolInput(recoveredInput)
    let recoveredReason = cleanedChinesePermissionReason(
        justificationFromToolInput(recoveredInput)
    )
    if !recoveredReason.isEmpty {
        return recoveredReason
    }
    let recoveredCommand = commandFromToolInput(recoveredInput)
    if let summary = patchPermissionSummary(
        recoveredCommand,
        baseDirectory: recoveredDirectory.isEmpty
            ? baseDirectory
            : recoveredDirectory
    ) {
        return summary
    }
    if let summary = commandPermissionSummary(
        recoveredCommand,
        baseDirectory: recoveredDirectory.isEmpty
            ? baseDirectory
            : recoveredDirectory
    ) {
        return summary
    }
    if !chineseReason.isEmpty {
        return chineseReason
    }
    return nil
}

private func petHeartbeatIsFresh() -> Bool {
    guard
        let heartbeat = readJSONDictionary(heartbeatURL()),
        let updatedAt = heartbeat["updated_at"] as? String,
        let date = parseTimestamp(updatedAt)
    else {
        return false
    }
    let age = Date().timeIntervalSince(date)
    guard age >= 0, age <= 180 else {
        return false
    }
    if let pid = heartbeat["pid"] as? NSNumber {
        errno = 0
        if kill(pid.int32Value, 0) != 0, errno != EPERM {
            return false
        }
    }
    return true
}

private func permissionOutput(decision: String, message: String = "") -> String {
    var decisionBody: [String: Any] = ["behavior": decision]
    if decision == "deny", !message.isEmpty {
        decisionBody["message"] = message
    }
    let value: [String: Any] = [
        "hookSpecificOutput": [
            "hookEventName": "PermissionRequest",
            "decision": decisionBody,
        ],
    ]
    guard
        let data = try? JSONSerialization.data(withJSONObject: value),
        let text = String(data: data, encoding: .utf8)
    else {
        return "{}"
    }
    return text
}

private func completePermissionWithoutDecision(
    requestURL: URL,
    responseURL: URL,
    sessionID: String,
    turnID: String,
    reason: String
) -> String {
    try? FileManager.default.removeItem(at: requestURL)
    try? FileManager.default.removeItem(at: responseURL)
    _ = try? writeBridgeState(
        status: "idle",
        event: "PermissionNoDecision",
        sessionID: sessionID,
        turnID: turnID,
        message: reason
    )
    return "{}"
}

private func handlePermissionRequest(
    _ payload: [String: Any],
    sessionID: String,
    turnID: String
) -> String {
    guard petHeartbeatIsFresh() else {
        appendJSONLine(
            [
                "updated_at": utcTimestamp(),
                "status": "permission",
                "event": "PermissionRequest",
                "session_id": sessionID,
                "turn_id": turnID,
                "ignored": true,
                "reason": "no-fresh-pig-heartbeat",
            ],
            to: defaultStateDirectory()
                .appendingPathComponent("codex-hook-events.jsonl")
        )
        return "{}"
    }

    let requestID = UUID().uuidString.replacingOccurrences(
        of: "-",
        with: ""
    ).lowercased()
    let requestURL = permissionDirectoryURL()
        .appendingPathComponent("\(requestID).request.json")
    let responseURL = permissionDirectoryURL()
        .appendingPathComponent("\(requestID).response.json")
    let createdAt = Date()
    let toolName = rawToolName(payload)
    guard
        let summary = permissionSummary(
            payload,
            rawTool: toolName,
            sessionID: sessionID,
            turnID: turnID
        )
    else {
        appendJSONLine(
            [
                "updated_at": utcTimestamp(),
                "status": "permission",
                "event": "PermissionRequest",
                "session_id": sessionID,
                "turn_id": turnID,
                "ignored": true,
                "reason": "permission-details-unavailable",
            ],
            to: defaultStateDirectory()
                .appendingPathComponent("codex-hook-events.jsonl")
        )
        return "{}"
    }
    let request: [String: Any] = [
        "request_id": requestID,
        "created_at": ISO8601DateFormatter().string(from: createdAt),
        "expires_at": ISO8601DateFormatter().string(
            from: createdAt.addingTimeInterval(permissionTimeout)
        ),
        "session_id": sessionID,
        "turn_id": turnID,
        "tool_name": localizedToolName(toolName),
        "summary": summary,
    ]
    do {
        try writeJSONAtomic(request, to: requestURL)
        try writeBridgeState(
            status: "permission",
            event: "PermissionRequest",
            sessionID: sessionID,
            turnID: turnID,
            permissionRequestID: requestID
        )
    } catch {
        return "{}"
    }

    let deadline = Date().addingTimeInterval(permissionTimeout)
    while Date() < deadline {
        if let response = readJSONDictionary(responseURL) {
            let decision = response["decision"] as? String ?? ""
            if decision == "allow" || decision == "deny" {
                let message = decision == "deny"
                    ? (response["message"] as? String ?? "")
                    : ""
                try? FileManager.default.removeItem(at: requestURL)
                try? FileManager.default.removeItem(at: responseURL)
                _ = try? writeBridgeState(
                    status: decision == "allow" ? "thinking" : "idle",
                    event: "PermissionDecision",
                    sessionID: sessionID,
                    turnID: turnID,
                    message: message
                )
                return permissionOutput(decision: decision, message: message)
            }
            return completePermissionWithoutDecision(
                requestURL: requestURL,
                responseURL: responseURL,
                sessionID: sessionID,
                turnID: turnID,
                reason: "invalid permission response"
            )
        }

        if let state = readJSONDictionary(defaultStatusURL()) {
            let status = state["status"] as? String ?? ""
            let stateRequestID = state["permission_request_id"] as? String ?? ""
            if status != "permission" || stateRequestID != requestID {
                return completePermissionWithoutDecision(
                    requestURL: requestURL,
                    responseURL: responseURL,
                    sessionID: sessionID,
                    turnID: turnID,
                    reason: "permission handled elsewhere"
                )
            }
        }
        Thread.sleep(forTimeInterval: 0.15)
    }
    return completePermissionWithoutDecision(
        requestURL: requestURL,
        responseURL: responseURL,
        sessionID: sessionID,
        turnID: turnID,
        reason: "permission timeout"
    )
}

private func spawnCompletionWatcher(sessionID: String, turnID: String) {
    guard !sessionID.isEmpty, !turnID.isEmpty else {
        return
    }
    let process = Process()
    process.executableURL = currentExecutableURL()
    process.arguments = ["--watch-completion", sessionID, turnID]
    process.standardInput = FileHandle.nullDevice
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice
    try? process.run()
}

func runCodexHook() {
    defer {
        fflush(stdout)
    }
    do {
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let object = input.isEmpty
            ? [String: Any]()
            : try JSONSerialization.jsonObject(with: input)
        let payload = object as? [String: Any] ?? [:]
        let event = payload["hook_event_name"] as? String ?? ""
        let sessionID = payload["session_id"] as? String ?? ""
        let turnID = payload["turn_id"] as? String ?? ""

        if event == "PermissionRequest" {
            print(
                handlePermissionRequest(
                    payload,
                    sessionID: sessionID,
                    turnID: turnID
                )
            )
            return
        }

        let mapping: [String: String] = [
            "SessionStart": "idle",
            "UserPromptSubmit": "thinking",
            "PreToolUse": "thinking",
            "PostToolUse": "thinking",
            "Stop": "success",
        ]
        guard let status = mapping[event] else {
            print("{}")
            return
        }

        if event == "PostToolUse",
            let existing = readJSONDictionary(defaultStatusURL()),
            existing["status"] as? String == "success",
            let timestamp = existing["updated_at"] as? String,
            let date = parseTimestamp(timestamp)
        {
            let age = Date().timeIntervalSince(date)
            if age >= 0, age <= 3 {
                appendJSONLine(
                    [
                        "updated_at": utcTimestamp(),
                        "status": status,
                        "event": event,
                        "session_id": sessionID,
                        "turn_id": turnID,
                        "ignored": true,
                        "reason": "recent-success",
                    ],
                    to: defaultStateDirectory()
                        .appendingPathComponent("codex-hook-events.jsonl")
                )
                print("{}")
                return
            }
        }

        try writeBridgeState(
            status: status,
            event: event,
            sessionID: sessionID,
            turnID: turnID
        )
        if event == "UserPromptSubmit" {
            spawnCompletionWatcher(sessionID: sessionID, turnID: turnID)
        }
    } catch {
        // Hooks must never interrupt Codex if the decorative bridge fails.
    }
    print("{}")
}

private func newestSessionFile(sessionID: String) -> URL? {
    guard !sessionID.isEmpty else {
        return nil
    }
    let codexHome: URL
    if let configured = ProcessInfo.processInfo.environment["CODEX_HOME"], !configured.isEmpty {
        codexHome = URL(fileURLWithPath: configured, isDirectory: true)
    } else {
        codexHome = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".codex", isDirectory: true)
    }
    let sessions = codexHome.appendingPathComponent("sessions", isDirectory: true)
    guard
        let enumerator = FileManager.default.enumerator(
            at: sessions,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: [.skipsHiddenFiles]
        )
    else {
        return nil
    }
    var newest: (URL, Date)?
    for case let url as URL in enumerator {
        guard
            url.pathExtension == "jsonl",
            url.lastPathComponent.contains(sessionID)
        else {
            continue
        }
        let date = (
            try? url.resourceValues(
                forKeys: [.contentModificationDateKey]
            ).contentModificationDate
        ) ?? .distantPast
        if newest == nil || date > newest!.1 {
            newest = (url, date)
        }
    }
    return newest?.0
}

private func sessionHasTaskComplete(_ url: URL, turnID: String) -> Bool {
    guard let handle = try? FileHandle(forReadingFrom: url) else {
        return false
    }
    defer {
        try? handle.close()
    }
    do {
        let end = try handle.seekToEnd()
        let maximumBytes: UInt64 = 2 * 1024 * 1024
        if end > maximumBytes {
            try handle.seek(toOffset: end - maximumBytes)
        } else {
            try handle.seek(toOffset: 0)
        }
        let data = try handle.readToEnd() ?? Data()
        guard let text = String(data: data, encoding: .utf8) else {
            return false
        }
        for line in text.split(separator: "\n").suffix(1000) {
            guard
                let lineData = line.data(using: .utf8),
                let record = try? JSONSerialization.jsonObject(with: lineData)
                    as? [String: Any],
                record["type"] as? String == "event_msg",
                let payload = record["payload"] as? [String: Any],
                payload["type"] as? String == "task_complete",
                payload["turn_id"] as? String == turnID
            else {
                continue
            }
            return true
        }
    } catch {
        return false
    }
    return false
}

func runCompletionWatcher(sessionID: String, turnID: String) {
    guard !sessionID.isEmpty, !turnID.isEmpty else {
        return
    }
    let deadline = Date().addingTimeInterval(600)
    var sessionURL: URL?
    while Date() < deadline {
        if let state = readJSONDictionary(defaultStatusURL()) {
            guard
                state["status"] as? String == "thinking",
                state["session_id"] as? String == sessionID,
                state["turn_id"] as? String == turnID
            else {
                return
            }
        }
        if sessionURL == nil
            || !FileManager.default.fileExists(atPath: sessionURL!.path)
        {
            sessionURL = newestSessionFile(sessionID: sessionID)
        }
        if let sessionURL, sessionHasTaskComplete(sessionURL, turnID: turnID) {
            if let state = readJSONDictionary(defaultStatusURL()) {
                guard
                    state["status"] as? String == "thinking",
                    state["session_id"] as? String == sessionID,
                    state["turn_id"] as? String == turnID
                else {
                    return
                }
            }
            _ = try? writeBridgeState(
                status: "success",
                event: "TaskCompleteFallback",
                sessionID: sessionID,
                turnID: turnID,
                source: "codex-task-complete-watch"
            )
            return
        }
        Thread.sleep(forTimeInterval: 0.75)
    }
    appendJSONLine(
        [
            "updated_at": utcTimestamp(),
            "status": "thinking",
            "event": "TaskCompleteFallbackTimeout",
            "session_id": sessionID,
            "turn_id": turnID,
        ],
        to: defaultStateDirectory().appendingPathComponent(
            "codex-hook-events.jsonl"
        )
    )
}
