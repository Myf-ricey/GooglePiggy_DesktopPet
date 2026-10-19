import Foundation
let fixture = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
try FileManager.default.createDirectory(at:fixture,withIntermediateDirectories:true)
setenv("GOOGLEPIGGY_STATE_DIR",fixture.appendingPathComponent("pet").path,1)
setenv("CODEX_HOME",fixture.path,1)
defer { try? FileManager.default.removeItem(at:fixture) }
let db=Process();db.executableURL=URL(fileURLWithPath:"/usr/bin/sqlite3")
db.arguments=[fixture.appendingPathComponent("state_5.sqlite").path,"CREATE TABLE threads(id TEXT,name TEXT,title TEXT,source TEXT,rollout_path TEXT); INSERT INTO threads VALUES('registered','','','{}',''); INSERT INTO threads VALUES('metadata-child','','','{\"subagent\":{\"thread_spawn\":{\"parent_thread_id\":\"parent\"}}}','');"]
try db.run();db.waitUntilExit();assert(db.terminationStatus==0)
let marker="You are an expert at upholding safety and compliance standards for Codex ambient suggestions.\n\nI wil"
func event(_ id:String,_ kind:String="UserPromptSubmit") -> [String:Any] {
 ["session_id":id,"event":kind,"status":kind == "Stop" ? "success":"thinking","turn_id":"t1","prompt_preview":kind == "UserPromptSubmit" ? marker:"","cwd":"/","source":"codex-hook"]
}
let store=FamilyStore()
for id in ["internal-a","internal-b"] {
 store.ingest(event(id,"SessionStart"));store.ingest(event(id));assert(store.nodes[id]==nil)
 for kind in ["Stop","PostToolUse","ResumeDetected","TaskCompleteFallback","SessionEnd"] {store.ingest(event(id,kind));assert(store.nodes[id]==nil)}
}
for id in ["registered","metadata-child"] {store.ingest(event(id));assert(store.nodes[id]?.active==true)}
var ordinary=event("unnamed-user");ordinary["prompt_preview"]="检查我的程序";store.ingest(ordinary);assert(store.nodes["unnamed-user"]?.active==true)
for (id,key,value) in [("quoted","prompt_preview","请解释："+marker),("project","cwd","/tmp/project"),("other-source","source","user"),("explicit-child","agent_id","child"),("parented","parent_thread_id","parent"),("near-match","prompt_preview","You are an expert at upholding safety and compliance standards.")] {
 var e=event(id);e[key]=value;store.ingest(e);assert(store.nodes[id == "explicit-child" ? "child":id]?.active==true)
}
let files=familyEventDirectory();try FileManager.default.createDirectory(at:files,withIntermediateDirectories:true)
for (i,kind) in ["SessionStart","UserPromptSubmit","Stop","SessionEnd"].enumerated(){try writeJSONAtomic(event("restart",kind),to:files.appendingPathComponent("\(i).json"))}
let restarted=FamilyStore();restarted.poll();assert(restarted.nodes["restart"]==nil)
// Sanitized recorded envelopes: no local user database or logs required.
let source = URL(fileURLWithPath:#filePath).deletingLastPathComponent().appendingPathComponent("observed-events.json")
let rows = try JSONSerialization.jsonObject(with:Data(contentsOf:source)) as! [[String:Any]]
let ids:Set<String> = ["observed-safety-a", "observed-safety-b"]
var prompts=0
for row in rows {
 let id=row["session_id"] as! String
 restarted.ingest(row)
 if row["event"] as? String == "UserPromptSubmit" {prompts+=1;assert(restarted.nodes[id]==nil)}
}
assert(prompts==2);for id in ids {assert(restarted.nodes[id]==nil)}
print("PASS: two observed envelopes; late events; restart; registered unnamed user; unregistered user; quoted marker; project cwd; other source; explicit child; metadata child; parent marker; near-match")
