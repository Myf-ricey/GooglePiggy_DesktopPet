import AppKit
let app=NSApplication.shared
app.setActivationPolicy(.accessory)
let directory=Bundle.main.bundleURL.deletingLastPathComponent()
let marker=directory.appendingPathComponent("events.txt")
func log(_ text:String) {
    let line=Data((text+"\n").utf8)
    if !FileManager.default.fileExists(atPath:marker.path) { FileManager.default.createFile(atPath:marker.path,contents:nil) }
    if let file=try? FileHandle(forWritingTo:marker) { _ = try? file.seekToEnd();try? file.write(contentsOf:line);try? file.close() }
}
if UpdateChecker.currentVersion == "0.5.2" {
    log("RELAUNCHED_0.5.2")
    exit(0)
}
let installer=UpdateInstaller()
let scenario=ProcessInfo.processInfo.environment["GOOGLEPIGGY_TEST_CASE"] ?? "valid"
let deadline=Date().addingTimeInterval(4)
installer.canRelaunch={Date() > deadline}
installer.onChange={event in
    switch event {
    case .working(let message,_,_):
        log(message)
        if scenario == "cancel", message == "正在下载新版本…" { DispatchQueue.main.async { installer.cancel() } }
    // Immediate exit catches staged updates that were not cancelled before reporting failure.
    case .failed(let message): log("FAILED: "+message);app.terminate(nil)
    case .cancelled: log("CANCELLED");if scenario == "cancel" { app.terminate(nil) }
    }
}
DispatchQueue.main.async {
    installer.install(PiggyRelease(version:scenario == "version-mismatch" ? "0.5.3" : "0.5.2",notes:"Test",url:URL(string:"https://example.invalid")!))
}
let timeout=Timer.scheduledTimer(withTimeInterval:40,repeats:false) { _ in log("TIMEOUT");app.terminate(nil) }
app.run()
