import Foundation

let fixture = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
try FileManager.default.createDirectory(at: fixture, withIntermediateDirectories: true)
setenv("GOOGLEPIGGY_STATE_DIR", fixture.appendingPathComponent("pet").path, 1)
setenv("CODEX_HOME", fixture.path, 1)
defer { try? FileManager.default.removeItem(at: fixture) }
let db = Process()
db.executableURL = URL(fileURLWithPath:"/usr/bin/sqlite3")
db.arguments = [fixture.appendingPathComponent("state_5.sqlite").path,
    "CREATE TABLE threads(id TEXT,name TEXT,title TEXT,source TEXT,rollout_path TEXT); INSERT INTO threads VALUES('registered','','User thread','{}','');"]
try db.run(); db.waitUntilExit(); assert(db.terminationStatus == 0)

let marker = "This is an app-generated request for a suggested next user message."
func event(_ id: String, _ event: String, prompt: String = "", agent: String = "", parent: String = "") -> [String:Any] {
    ["session_id":id, "event":event, "status":event == "Stop" ? "success" : "thinking",
     "turn_id":"turn-1", "prompt_preview":prompt, "agent_id":agent, "parent_thread_id":parent]
}
let store = FamilyStore()
store.ingest(event("normal", "UserPromptSubmit", prompt:"正常任务"))
store.reconcileSelection()
store.ingest(event("suggestion", "SessionStart"))
store.ingest(event("suggestion", "UserPromptSubmit", prompt:marker))
store.ingest(event("suggestion", "Stop"))
store.reconcileSelection()
assert(store.nodes["suggestion"] == nil, "Suggested-reply session leaked into task family")
assert(store.selectedID == "normal" && store.nodes["normal"]!.active)
assert(store.roots.map { $0.id } == ["normal"])
print("PASS: suggested reply removed; normal task remains selected and active")

// Explicit marker in a real registered task must not hide that task.
store.ingest(event("registered", "SessionStart"))
store.ingest(event("registered", "UserPromptSubmit", prompt:marker))
assert(store.nodes["registered"]?.active == true)
store.ingest(event("normal", "UserPromptSubmit", prompt:marker, agent:"child"))
assert(store.nodes["child"]?.parent == "normal")
store.ingest(event("parented", "UserPromptSubmit", prompt:marker, parent:"normal"))
assert(store.nodes["parented"] != nil)
store.ingest(event("unregistered-user", "UserPromptSubmit", prompt:"帮我检查项目"))
assert(store.nodes["unregistered-user"]?.active == true)
store.ingest(event("quoted-marker", "UserPromptSubmit", prompt:"请解释：" + marker))
assert(store.nodes["quoted-marker"] != nil)
for name in ["PreToolUse", "PostToolUse", "ResumeDetected", "TaskCompleteFallback", "SessionEnd"] {
    store.ingest(event("suggestion", name))
    assert(store.nodes["suggestion"] == nil)
}
// A selected SessionStart shell is removed even without another running task.
let shell = FamilyStore()
shell.selectedID = ""
shell.ingest(event("shell", "SessionStart"))
assert(shell.selectedID == "shell")
shell.ingest(event("shell", "UserPromptSubmit", prompt:marker))
shell.reconcileSelection()
assert(shell.selectedID.isEmpty && shell.roots.isEmpty)
// Restart replay reads the same immutable events and still suppresses completion.
let directory = familyEventDirectory()
try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
for (i,name) in ["SessionStart","UserPromptSubmit","Stop"].enumerated() {
    try writeJSONAtomic(event("replayed",name,prompt:name == "UserPromptSubmit" ? marker : ""),
        to:directory.appendingPathComponent("00\(i).json"))
}
let restarted = FamilyStore(); restarted.poll()
assert(restarted.nodes["replayed"] == nil && restarted.roots.isEmpty)
print("PASS: registered tasks, real children, unknown ordinary tasks preserved; late events, shell selection and restart replay filtered")
