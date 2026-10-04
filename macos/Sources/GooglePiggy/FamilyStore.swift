import Foundation

// Hook processes have separate address spaces. These values only scope their
// own state/permission checks; the UI consumes immutable event files.
var hookActorID = ""
var hookMetadata: [String: Any] = [:]
func actorStatusURL(_ id: String) -> URL {
    let key = Data(id.utf8).base64EncodedString().replacingOccurrences(of: "/", with: "_")
    return defaultStateDirectory().appendingPathComponent("actors/\(key).json")
}
func familyEventDirectory() -> URL { defaultStateDirectory().appendingPathComponent("family-events") }

struct ThreadMetadata {
    var title = ""
    var parent = ""
    var path = ""
    var rollout = ""
}
func lookupThreadMetadata(_ id: String) -> ThreadMetadata {
    guard !id.isEmpty else { return ThreadMetadata() }
    let home = ProcessInfo.processInfo.environment["CODEX_HOME"].map { URL(fileURLWithPath: $0) }
        ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".codex")
    let databases = ((try? FileManager.default.contentsOfDirectory(at: home, includingPropertiesForKeys: nil)) ?? [])
        .filter { $0.lastPathComponent.hasPrefix("state_") && $0.pathExtension == "sqlite" }
        .sorted { $0.lastPathComponent > $1.lastPathComponent }
    guard let database = databases.first else { return ThreadMetadata() }
    let process = Process(), pipe = Pipe()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/sqlite3")
    let escaped = id.replacingOccurrences(of: "'", with: "''")
    process.arguments = ["-readonly", "-json", database.path,
        "SELECT COALESCE(NULLIF(name,''),title) AS title,source,rollout_path FROM threads WHERE id='\(escaped)' LIMIT 1;"]
    process.standardOutput = pipe; process.standardError = FileHandle.nullDevice
    guard (try? process.run()) != nil else { return ThreadMetadata() }
    let data = pipe.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit()
    guard let rows = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]], let row = rows.first else { return ThreadMetadata() }
    var result = ThreadMetadata(title: row["title"] as? String ?? "")
    result.rollout = row["rollout_path"] as? String ?? ""
    if let source = row["source"] as? String, let bytes = source.data(using: .utf8),
       let json = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
       let sub = json["subagent"] as? [String: Any], let spawn = sub["thread_spawn"] as? [String: Any] {
        result.parent = spawn["parent_thread_id"] as? String ?? ""
        result.path = spawn["agent_path"] as? String ?? ""
    }
    return result
}

final class FamilyNode {
    let id: String
    var parent: String
    var title: String
    var payload: [String: Any] = [:]
    var turn = ""
    var retiredTurns = Set<String>()
    var active = false
    var status = "idle"
    var changed = Date()
    var created = Date()
    var completion: Date?
    var lastEventAt = Date.distantPast
    var rollout = ""
    var unread = false
    var resultAvailable = false
    init(id: String, parent: String, title: String) { self.id = id; self.parent = parent; self.title = title }
}

final class FamilyStore {
    var nodes: [String: FamilyNode] = [:]
    private var pendingAutoSelection: String?
    var selectedID = ""
    init() { selectedID = readJSONDictionary(defaultStateDirectory().appendingPathComponent("selected-family.json"))?["id"] as? String ?? "" }
    func select(_ id: String) {
        pendingAutoSelection = nil
        selectedID = id
        try? writeJSONAtomic(["id": id], to: defaultStateDirectory().appendingPathComponent("selected-family.json"))
    }
    private var seen = Set<String>()
    private var initialized = false
    private var rolloutModifications: [String:Date] = [:]
    private var metadataAttempts: [String:Date] = [:]
    private var observationAt = Date.distantPast
    private var dismissedResults = Set<String>()
    private var titleRefresh = Date.distantPast
    var roots: [FamilyNode] {
        nodes.values.filter { $0.parent.isEmpty && ($0.active || $0.unread || !children($0.id).isEmpty) }
            .sorted { $0.created < $1.created }
    }
    func children(_ root: String) -> [FamilyNode] {
        nodes.values.filter { $0.parent == root && ($0.active || ($0.completion.map { Date().timeIntervalSince($0) < 2.84 } ?? false)) }
            .sorted { $0.created < $1.created }
    }
    var selected: FamilyNode? { nodes[selectedID] }
    func ingest(_ value: [String: Any], now: Date = Date()) {
        let session = value["session_id"] as? String ?? ""
        guard !session.isEmpty else { return }
        let event = value["event"] as? String ?? ""
        let explicitAgent = value["agent_id"] as? String ?? ""
        let actor = explicitAgent.isEmpty ? session : explicitAgent
        let meta = nodes[actor] == nil ? lookupThreadMetadata(actor) : ThreadMetadata()
        let parent = explicitAgent.isEmpty ? meta.parent : session
        if nodes[actor] == nil {
            let fallback = value["thread_title"] as? String ?? value["prompt_preview"] as? String ?? ""
            nodes[actor] = FamilyNode(id: actor, parent: parent, title: meta.title.isEmpty ? (fallback.isEmpty ? "线程 \(actor.prefix(8))" : fallback) : meta.title)
            nodes[actor]?.created = now
            nodes[actor]?.rollout = meta.rollout
        }
        guard let node = nodes[actor] else { return }
        if !parent.isEmpty, nodes[parent] == nil {
            let m = lookupThreadMetadata(parent)
            nodes[parent] = FamilyNode(id: parent, parent: "", title: m.title.isEmpty ? "线程 \(parent.prefix(8))" : m.title)
        }
        let turn = explicitAgent.isEmpty ? (value["turn_id"] as? String ?? "") : ""
        let begins = ["UserPromptSubmit", "SubagentStart", "PreCompact", "ResumeDetected"].contains(event)
        if node.retiredTurns.contains(turn), !turn.isEmpty { return }
        if begins, !turn.isEmpty, turn != node.turn {
            if !node.turn.isEmpty { node.retiredTurns.insert(node.turn) }
            node.turn = turn; node.completion = nil
        } else if !turn.isEmpty, !node.turn.isEmpty, turn != node.turn { return }
        if node.turn.isEmpty { node.turn = turn }
        if event == "SessionStart", node.active { return }
        if node.status == "interrupted", ["PostToolUse", "Stop", "PostCompact", "TaskCompleteFallback"].contains(event) { return }
        if node.completion != nil, !begins, ["PreToolUse", "PostToolUse", "SubagentStop", "Stop", "TaskCompleteFallback"].contains(event) { return }
        if node.status == "compacting", ["PreToolUse", "PostToolUse"].contains(event) { return }
        if event == "PostCompact", node.status != "compacting" { return }
        let newStatus = value["status"] as? String ?? "idle"
        if newStatus != node.status || begins { node.changed = now }
        node.lastEventAt = now
        node.status = newStatus
        node.payload = value
        node.active = ["thinking", "working", "compacting", "permission", "interrupted"].contains(node.status)
        if ["Stop", "SubagentStop", "TaskCompleteFallback", "SessionEnd"].contains(event) {
            node.active = false; node.completion = now
        }
        if ["Stop", "TaskCompleteFallback"].contains(event), node.parent.isEmpty {
            node.resultAvailable = true; node.unread = true; dismissedResults.remove(node.id)
        }
        if begins { node.active = true; node.completion = nil; node.unread = false; node.resultAvailable = false; dismissedResults.remove(node.id) }
        if begins && ["UserPromptSubmit", "ResumeDetected", "PreCompact"].contains(event) && node.parent.isEmpty {
            pendingAutoSelection = actor
        }
        if selectedID.isEmpty { selectedID = node.parent.isEmpty ? actor : node.parent }
    }
    func reconcileSelection(now: Date = Date()) {
        let available = roots
        func working(_ node: FamilyNode) -> Bool {
            guard node.status != "interrupted" else { return false }
            return node.active || children(node.id).contains { $0.active && $0.status != "interrupted" }
        }
        let running = available.filter(working)
        let newest = { (nodes: [FamilyNode]) in nodes.max { $0.lastEventAt < $1.lastEventAt } }
        var target = selectedID
        if let wanted = pendingAutoSelection, running.contains(where: { $0.id == wanted }) { target = wanted }
        else if !running.contains(where: { $0.id == selectedID }) {
            if let active = newest(running) { target = active.id }
            else if !available.contains(where: { $0.id == selectedID && $0.active }) {
                if let paused = newest(available.filter { $0.active }) { target = paused.id }
                else if let node = selected, let done = node.completion, now.timeIntervalSince(done) < 2.84 { target = node.id }
                else { target = "" }
            }
        }
        pendingAutoSelection = nil
        if target != selectedID { select(target) }
    }
    func markResultOpened(_ id: String) {
        dismissedResults.insert(id); nodes[id]?.unread = false
    }
    func childIsPaused(_ node: FamilyNode) -> Bool {
        node.status == "interrupted" || nodes[node.parent]?.status == "interrupted"
    }
    func reconcileObservations() {
        let now = Date()
        guard now.timeIntervalSince(observationAt) >= 1 else { return }
        observationAt = now
        for node in Array(nodes.values) {
            guard node.active || node.parent.isEmpty else { continue }
            if node.rollout.isEmpty {
                guard now.timeIntervalSince(metadataAttempts[node.id] ?? .distantPast) > 15 else { continue }
                metadataAttempts[node.id] = now; node.rollout = lookupThreadMetadata(node.id).rollout
            }
            guard !node.rollout.isEmpty,
                let attributes = try? FileManager.default.attributesOfItem(atPath:node.rollout),
                let modified = attributes[.modificationDate] as? Date,
                rolloutModifications[node.id] != modified else { continue }
            rolloutModifications[node.id] = modified
            guard let observed = latestLifecycle(at:node.rollout), observed.date > node.lastEventAt else { continue }
            // PostCompact finishes its own visual cycle; don't replay its earlier task start.
            let event = observed.kind == "task_started" ? "ResumeDetected" : (observed.kind == "turn_aborted" ? "Interrupt" : "TaskCompleteFallback")
            if event == "ResumeDetected", observed.turn == node.turn, node.status != "interrupted" { continue }
            if observed.turn != node.turn && event != "ResumeDetected" {
                ingest(["session_id":node.id,"event":"ResumeDetected","status":"working","turn_id":observed.turn,"token":"observed-start-"+observed.turn],now:observed.date.addingTimeInterval(-0.001))
            }
            ingest(["session_id":node.id,"event":event,"status":event == "ResumeDetected" ? "working" : (event == "Interrupt" ? "interrupted" : "success"),
                    "turn_id":observed.turn,"token":"observed-"+observed.kind+observed.turn,"received_at":observed.date.timeIntervalSince1970],now:observed.date)
        }
        if let value = readJSONDictionary(codexDataHome().appendingPathComponent(".codex-global-state.json")), let unread = codexUnreadIDs(from:value) {
            for node in nodes.values where node.parent.isEmpty && node.resultAvailable {
                if unread.contains(node.id) { node.unread = !dismissedResults.contains(node.id) }
                else if now.timeIntervalSince(node.completion ?? .distantPast) > 3 { node.unread = false }
            }
        }
    }
    func poll() {
        if Date().timeIntervalSince(titleRefresh) > 15 {
            titleRefresh = Date()
            for node in roots {
                let meta = lookupThreadMetadata(node.id)
                if !meta.title.isEmpty { node.title = meta.title }
            }
        }
        let files = ((try? FileManager.default.contentsOfDirectory(at: familyEventDirectory(), includingPropertiesForKeys: nil)) ?? [])
            .filter { $0.pathExtension == "json" && !seen.contains($0.lastPathComponent) }.sorted { $0.lastPathComponent < $1.lastPathComponent }
        for file in files {
            seen.insert(file.lastPathComponent)
            guard let p = readJSONDictionary(file) else { continue }
            let when = (p["received_at"] as? Double).map(Date.init(timeIntervalSince1970:)) ?? Date()
            // Never replay old celebration on application restart.
            ingest(p, now: when)
        }
        reconcileObservations()
        reconcileSelection()
        if !initialized {
            initialized = true

        }
    }
}

func codexDataHome() -> URL {
    ProcessInfo.processInfo.environment["CODEX_HOME"].map { URL(fileURLWithPath:$0) }
        ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".codex")
}
struct ObservedLifecycle {
    let turn: String
    let kind: String
    let date: Date
}
func latestLifecycle(at path: String) -> ObservedLifecycle? {
    guard !path.isEmpty, let handle = FileHandle(forReadingAtPath:path) else { return nil }
    defer { try? handle.close() }
    guard let size = try? handle.seekToEnd() else { return nil }
    var span: UInt64 = 262144
    while true {
        let offset = size > span ? size-span : 0
        try? handle.seek(toOffset:offset)
        guard let data = try? handle.readToEnd() else { return nil }
        let text = String(decoding:data,as:UTF8.self)
        for line in text.split(separator:"\n").reversed() {
            guard let bytes = String(line).data(using:.utf8),
                let row = try? JSONSerialization.jsonObject(with:bytes) as? [String:Any],
                row["type"] as? String == "event_msg",
                let payload = row["payload"] as? [String:Any],
                let kind = payload["type"] as? String,
                ["task_started","task_complete","turn_aborted"].contains(kind),
                let turn = payload["turn_id"] as? String,
                let stamp = row["timestamp"] as? String, let date = parseTimestamp(stamp) else { continue }
            return ObservedLifecycle(turn:turn,kind:kind,date:date)
        }
        if offset == 0 || span >= 16777216 { return nil }; span *= 2
    }
}
// Fail closed for an ambiguous account/host schema. Never write Codex state.
func codexUnreadIDs(from value: [String:Any]) -> Set<String>? {
    guard let state = value["electron-thread-read-state-v1"] as? [String:Any],
        state["version"] as? Int == 1,
        let identities = state["unreadByIdentity"] as? [String:[String:[String]]],
        identities.count == 1, let hosts = identities.values.first else { return nil }
    let locals = hosts.filter { $0.key.hasPrefix("local:") }
    guard locals.count == 1, let ids = locals.values.first else { return nil }
    return Set(ids)
}
