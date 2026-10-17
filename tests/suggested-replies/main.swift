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

// Actual 100-character preview from the 2026-10-16 17:17 background run.
let ambient = "# Overview\n\nGenerate 0 to 3 hyperpersonalized suggestions for what this user can do with Codex in th"
for name in ["SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "SessionEnd", "TaskCompleteFallback"] {
    store.ingest(event("ambient", name, prompt: name == "UserPromptSubmit" ? ambient : ""))
}
assert(store.nodes["ambient"] == nil)
store.ingest(event("registered", "UserPromptSubmit", prompt:ambient))
assert(store.nodes["registered"]?.active == true)
store.ingest(event("quoted-ambient", "UserPromptSubmit", prompt:"解释这段提示词：" + ambient))
assert(store.nodes["quoted-ambient"]?.active == true)
for (i,name) in ["SessionStart","UserPromptSubmit","PostToolUse","Stop","SessionEnd"].enumerated() {
    try writeJSONAtomic(event("ambient-replay",name,prompt:name == "UserPromptSubmit" ? ambient : ""),
        to:directory.appendingPathComponent("10\(i).json"))
}
let ambientRestart = FamilyStore(); ambientRestart.poll()
assert(ambientRestart.nodes["ambient-replay"] == nil && ambientRestart.roots.isEmpty)
print("PASS: ambient suggestions, late completion and restart replay filtered; user tasks preserved")

let titlePreview = "User's request:\n\"\"\"\n把大学物理课本里面所有单开的 SVG 都在教材末尾开一个文件夹，专门存放图片，以后也是，记得写入规则，并且引用 SVG 之类的格式不要乱了\n\"\"\"\n\nGener"
for (i,name) in ["SessionStart","UserPromptSubmit"].enumerated() {
    try writeJSONAtomic(event("title-stuck",name,prompt:name == "UserPromptSubmit" ? titlePreview : ""),
        to:directory.appendingPathComponent("20\(i).json"))
}
let titleRestart = FamilyStore(); titleRestart.poll()
assert(titleRestart.nodes["title-stuck"] == nil && titleRestart.roots.isEmpty)
var tagged = event("long-title", "UserPromptSubmit", prompt:"User's request:\n\"\"\"\n" + String(repeating:"长",count:80))
tagged["internal_request_kind"] = "conversation_title"
store.ingest(tagged)
assert(store.nodes["long-title"] == nil)
store.ingest(event("registered","UserPromptSubmit",prompt:titlePreview))
assert(store.nodes["registered"]?.active == true)
store.ingest(event("envelope-only","UserPromptSubmit",prompt:"User's request:\n\"\"\"\nPlease do work"))
assert(store.nodes["envelope-only"]?.active == true)
print("PASS: Claudian title request without Stop removed on replay; long tagged titles filtered; actual requests preserved")

let memoryMarker = "## Memory Writing Agent: Phase 2 (Consolidation)\nYou are a Memory Writing Agent."
func memoryEvent(_ id: String, _ name: String, cwd: String = "C:\\Users\\fixture\\.codex\\memories", prompt: String = memoryMarker) -> [String:Any] {
    var value = event(id, name, prompt:name == "UserPromptSubmit" ? prompt : "")
    value["cwd"] = cwd
    return value
}
// Issue #3: no Stop, repeated working events, then restart from immutable logs.
for (i,name) in ["SessionStart","UserPromptSubmit","PreToolUse","PostToolUse","PreToolUse","PostToolUse"].enumerated() {
    try writeJSONAtomic(memoryEvent("memory-stuck",name),to:directory.appendingPathComponent("30\(i).json"))
}
let memoryRestart = FamilyStore(); memoryRestart.poll()
assert(memoryRestart.nodes["memory-stuck"] == nil && memoryRestart.roots.isEmpty)
for name in ["Stop", "ResumeDetected", "TaskCompleteFallback", "SessionEnd"] {
    memoryRestart.ingest(memoryEvent("memory-stuck",name))
    assert(memoryRestart.nodes["memory-stuck"] == nil)
}
store.ingest(memoryEvent("memory-custom","UserPromptSubmit",cwd:fixture.appendingPathComponent("memories").path))
assert(store.nodes["memory-custom"] == nil)
store.ingest(memoryEvent("memory-user","UserPromptSubmit",prompt:"请整理我的记忆"))
assert(store.nodes["memory-user"]?.active == true)
store.ingest(memoryEvent("memory-quoted","UserPromptSubmit",cwd:"/tmp/project"))
assert(store.nodes["memory-quoted"]?.active == true)
store.ingest(memoryEvent("registered","UserPromptSubmit"))
assert(store.nodes["registered"] == nil, "Internal consolidation can have a metadata row")
var childMemory = memoryEvent("memory-parent","UserPromptSubmit")
childMemory["agent_id"] = "memory-child"
store.ingest(childMemory)
assert(store.nodes["memory-child"] != nil)
print("PASS: memory consolidation without Stop, restart and late events filtered; custom home, registered internal sessions, normal requests and children covered")
