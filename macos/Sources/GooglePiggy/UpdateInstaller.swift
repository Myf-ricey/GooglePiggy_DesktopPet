import AppKit
import Foundation
import Sparkle

enum InstallationEvent {
    case working(String, Double?, Bool)
    case failed(String)
    case cancelled
}

/// Sparkle owns download verification, staging, replacement and relaunch.
/// The pig's custom bubble is the user driver; no second install prompt is needed.
final class UpdateInstaller: NSObject, SPUUserDriver, SPUUpdaterDelegate {
    var onChange: ((InstallationEvent) -> Void)?
    var canRelaunch: () -> Bool = { true }
    private(set) var busy = false
    private var expectedVersion = ""
    private var updater: SPUUpdater?
    private var cancellation: (() -> Void)?
    private var expectedBytes: UInt64 = 0
    private var receivedBytes: UInt64 = 0
    private var readyReply: ((SPUUserUpdateChoice) -> Void)?
    private var waitingTimer: Timer?
    private var failed = false
    private var backingUp = false

    func install(_ release: PiggyRelease) {
        guard !busy else { return }
        let app = Bundle.main.bundleURL.resolvingSymlinksInPath()
        guard app.pathExtension == "app", !app.path.hasPrefix("/Volumes/"),
              !app.path.contains("/AppTranslocation/"),
              FileManager.default.isWritableFile(atPath: app.deletingLastPathComponent().path) else {
            onChange?(.failed("请先将猪猪安装到本机可写入的位置，再执行更新。")); return
        }
        busy = true; failed = false; expectedVersion = release.version
        expectedBytes = 0; receivedBytes = 0
        onChange?(.working("正在获取已签名的更新…", nil, false))
        if updater == nil {
            let instance = SPUUpdater(hostBundle: .main, applicationBundle: .main, userDriver: self, delegate: self)
            updater = instance
            do { try instance.start() }
            catch { updater = nil; fail("无法启动更新：\(error.localizedDescription)"); return }
            instance.automaticallyChecksForUpdates = false
            instance.automaticallyDownloadsUpdates = false
        }
        guard updater?.canCheckForUpdates == true else { fail("更新器正在忙，请稍后重试。"); return }
        updater?.checkForUpdates()
    }

    func cancel() {
        guard let action = cancellation else { return }
        cancellation = nil
        action()
    }

    private func fail(_ message: String) {
        failed = true; busy = false; cancellation = nil
        waitingTimer?.invalidate(); waitingTimer = nil; readyReply = nil
        onChange?(.failed(message))
    }

    func show(_ request: SPUUpdatePermissionRequest, reply: @escaping (SUUpdatePermissionResponse) -> Void) {
        reply(SUUpdatePermissionResponse(automaticUpdateChecks: false, sendSystemProfile: false))
    }
    func showUserInitiatedUpdateCheck(cancellation: @escaping () -> Void) {
        self.cancellation = cancellation
        onChange?(.working("正在获取已签名的更新…", nil, true))
    }
    func showUpdateFound(with appcastItem: SUAppcastItem, state: SPUUserUpdateState, reply: @escaping (SPUUserUpdateChoice) -> Void) {
        guard !appcastItem.isInformationOnlyUpdate, appcastItem.displayVersionString == expectedVersion else {
            fail("更新包尚未准备好，或版本已变化。请稍后重新检查更新。")
            reply(.dismiss); return
        }
        reply(.install)
    }
    func showUpdateReleaseNotes(with downloadData: SPUDownloadData) {}
    func showUpdateReleaseNotesFailedToDownloadWithError(_ error: Error) {}
    func showUpdateNotFoundWithError(_ error: Error, acknowledgement: @escaping () -> Void) {
        fail("暂时没有可安装的更新包，请稍后重新检查更新。")
        acknowledgement()
    }
    func showUpdaterError(_ error: Error, acknowledgement: @escaping () -> Void) {
        fail("更新未完成，当前版本已保留。\n\(error.localizedDescription)")
        acknowledgement()
    }
    func showDownloadInitiated(cancellation: @escaping () -> Void) {
        self.cancellation = cancellation; receivedBytes = 0
        onChange?(.working("正在下载新版本…", nil, true))
    }
    func showDownloadDidReceiveExpectedContentLength(_ expectedContentLength: UInt64) { expectedBytes = expectedContentLength }
    func showDownloadDidReceiveData(ofLength length: UInt64) {
        receivedBytes += length
        let fraction = expectedBytes > 0 ? min(1, Double(receivedBytes)/Double(expectedBytes)) : nil
        let text = fraction.map { "正在下载新版本… \(Int($0*100))%" } ?? "正在下载新版本…"
        onChange?(.working(text, fraction, true))
    }
    func showDownloadDidStartExtractingUpdate() {
        cancellation = nil
        onChange?(.working("正在校验并解压更新包…", nil, false))
    }
    func showExtractionReceivedProgress(_ progress: Double) {
        onChange?(.working("正在校验并解压更新包…", progress, false))
    }
    func showReady(toInstallAndRelaunch reply: @escaping (SPUUserUpdateChoice) -> Void) {
        readyReply = reply
        waitingTimer = Timer(timeInterval: 0.3, repeats: true) { [weak self] _ in self?.tryInstallWhenReady() }
        RunLoop.main.add(waitingTimer!, forMode: .common)
        tryInstallWhenReady()
    }
    private func tryInstallWhenReady() {
        guard let reply = readyReply, !backingUp else { return }
        guard canRelaunch() else {
            onChange?(.working("下载完成，等待权限请求处理完后重启…", 1, false)); return
        }
        backingUp = true
        onChange?(.working("正在备份当前版本…", nil, false))
        let source = Bundle.main.bundleURL
        let backup = source.deletingLastPathComponent().appendingPathComponent("GooglePiggy Backups")
            .appendingPathComponent("update-\(UpdateChecker.currentVersion)-\(UUID().uuidString)")
            .appendingPathComponent("GooglePiggy.app")
        DispatchQueue.global(qos: .utility).async {
            let error: Error?
            do {
                try FileManager.default.createDirectory(at: backup.deletingLastPathComponent(), withIntermediateDirectories: true)
                // ditto preserves framework symlinks, executable permissions and signing metadata.
                let task = Process(); task.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
                task.arguments = [source.path, backup.path]
                task.standardOutput = FileHandle.nullDevice; task.standardError = FileHandle.nullDevice
                try task.run(); task.waitUntilExit()
                guard task.terminationStatus == 0 else { throw CocoaError(.fileWriteUnknown) }
                error = nil
            } catch let issue { error = issue }
            DispatchQueue.main.async {
                self.backingUp = false
                if let error {
                    self.fail("无法备份当前版本，已取消安装。\n\(error.localizedDescription)")
                    reply(.skip); return
                }
                // A permission request could have arrived while copying the backup.
                self.finishAfterBackup(reply)
            }
        }
    }
    private func finishAfterBackup(_ reply: @escaping (SPUUserUpdateChoice) -> Void) {
        waitingTimer?.invalidate(); waitingTimer = nil
        if !canRelaunch() {
            backingUp = true
            onChange?(.working("备份完成，等待权限请求处理完后重启…", 1, false))
            waitingTimer = Timer(timeInterval: 0.3, repeats: true) { [weak self] _ in
                guard let self, self.canRelaunch() else { return }
                self.finishAfterBackup(reply)
            }
            RunLoop.main.add(waitingTimer!, forMode: .common)
            return
        }
        backingUp = false; readyReply = nil
        onChange?(.working("正在安装，猪猪马上回来…", 1, false))
        reply(.install)
    }
    func showInstallingUpdate(withApplicationTerminated applicationTerminated: Bool, retryTerminatingApplication: @escaping () -> Void) {
        onChange?(.working("正在安装，猪猪马上回来…", 1, false))
    }
    func showUpdateInstalledAndRelaunched(_ relaunched: Bool, acknowledgement: @escaping () -> Void) { acknowledgement() }
    func dismissUpdateInstallation() {
        waitingTimer?.invalidate(); waitingTimer = nil; readyReply = nil; cancellation = nil; busy = false
        if !failed { onChange?(.cancelled) }
    }
    func feedURLString(for updater: SPUUpdater) -> String? {
        #if UPDATE_TESTING
        if let fixture = ProcessInfo.processInfo.environment["GOOGLEPIGGY_TEST_FEED"] { return fixture }
        #endif
        guard UpdateChecker.version(expectedVersion) != nil else { return nil }
        return "https://github.com/Myf-ricey/GooglePiggy_DesktopPet/releases/download/v\(expectedVersion)-macos/appcast.xml"
    }
}
