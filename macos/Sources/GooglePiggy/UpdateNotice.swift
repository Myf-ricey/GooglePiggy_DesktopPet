import AppKit
import Foundation

struct PiggyRelease {
    let version: String
    let notes: String
    let url: URL
}

enum UpdateResult {
    case available(PiggyRelease)
    case current
    case failed
}

final class UpdateChecker {
    private(set) var checking = false
    private var manualRequested = false
    private let session: URLSession
    init(session: URLSession = .shared) { self.session = session }
    static let currentVersion = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.5.2"
    static func version(_ value: String) -> [Int]? {
        let parts = value.split(separator: ".", omittingEmptySubsequences: false)
        guard (2...4).contains(parts.count), parts.allSatisfy({ !$0.isEmpty && $0.allSatisfy({ $0.isASCII && $0.isNumber }) }) else { return nil }
        let numbers = parts.compactMap { Int($0) }
        return numbers.count == parts.count ? numbers : nil
    }
    static func newer(_ candidate: String, than current: String) -> Bool {
        guard var a = version(candidate), var b = version(current) else { return false }
        let count = max(a.count, b.count)
        a += Array(repeating: 0, count: count-a.count); b += Array(repeating: 0, count: count-b.count)
        return b.lexicographicallyPrecedes(a)
    }
    static func parse(_ rows: [[String: Any]]) -> [PiggyRelease] {
        rows.compactMap { row in
            guard row["draft"] as? Bool == false, row["prerelease"] as? Bool == false,
                  let tag = row["tag_name"] as? String, tag.hasPrefix("v"), tag.hasSuffix("-macos"),
                  let link = row["html_url"] as? String, let url = URL(string: link),
                  url.scheme == "https", url.host == "github.com",
                  url.path.hasPrefix("/Myf-ricey/GooglePiggy_DesktopPet/releases/tag/"),
                  let assets = row["assets"] as? [[String: Any]],
                  assets.contains(where: { ($0["name"] as? String ?? "").lowercased().contains("macos") && ($0["size"] as? Int ?? 0) > 0 }) else { return nil }
            let number = String(tag.dropFirst().dropLast(6))
            guard version(number) != nil else { return nil }
            let raw = row["body"] as? String ?? ""
            let bullets = raw.components(separatedBy: .newlines).map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { $0.hasPrefix("- ") || $0.hasPrefix("* ") }.prefix(3)
                .map { "• " + String($0.dropFirst(2)).replacingOccurrences(of: "**", with: "").replacingOccurrences(of: "`", with: "") }
            let notes = bullets.isEmpty ? "新版已发布，点击更新即可下载并安装。" : bullets.joined(separator: "\n")
            return PiggyRelease(version: number, notes: String(notes.prefix(180)), url: url)
        }
    }
    // One request chain per app launch/manual check; never run from --hook processes.
    func check(manual: Bool, completion: @escaping (UpdateResult, Bool) -> Void) {
        manualRequested = manualRequested || manual
        guard !checking else { return }
        checking = true
        fetch(page: 1, collected: []) { result in
            DispatchQueue.main.async {
                self.checking = false
                let show = self.manualRequested; self.manualRequested = false
                completion(result, show)
            }
        }
    }
    private func fetch(page: Int, collected: [PiggyRelease], completion: @escaping (UpdateResult) -> Void) {
        let url = URL(string: "https://api.github.com/repos/Myf-ricey/GooglePiggy_DesktopPet/releases?per_page=100&page=\(page)")!
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 15)
        request.setValue("GooglePiggy-macOS", forHTTPHeaderField: "User-Agent")
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        session.dataTask(with: request) { data, response, error in
            guard error == nil, (response as? HTTPURLResponse)?.statusCode == 200,
                  let data, data.count < 8_000_000,
                  let rows = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
                completion(.failed); return
            }
            let all = collected + Self.parse(rows)
            if rows.count == 100 {
                guard page < 5 else { completion(.failed); return }
                self.fetch(page: page+1, collected: all, completion: completion); return
            }
            guard let latest = all.max(by: { Self.newer($1.version, than: $0.version) }) else { completion(.failed); return }
            completion(Self.newer(latest.version, than: Self.currentVersion) ? .available(latest) : .current)
        }.resume()
    }
}

// Drawn in the same flipped 640-point canvas as the existing permission bubble.
final class UpdateNotice {
    let result: UpdateResult
    let current: String
    let started = ProcessInfo.processInfo.systemUptime
    var pressed: String?
    var progressMessage: String?
    var progress: Double?
    var canCancel = false
    var installationError: String?
    init(_ result: UpdateResult, current: String = UpdateChecker.currentVersion) { self.result = result; self.current = current }
    var release: PiggyRelease? { if case .available(let release) = result { return release }; return nil }
    var rect: NSRect { NSRect(x: 238, y: release == nil ? 190 : 112, width: 344, height: release == nil ? 146 : 224) }
    var bounds: NSRect { rect.union(NSRect(x: 360, y: 332, width: 100, height: 100)) }
    var buttons: [String: NSRect] {
        if progressMessage != nil {
            return canCancel ? ["cancel": NSRect(x: rect.minX+20, y: rect.maxY-52, width: 304, height: 34)] : [:]
        }
        if release == nil { return ["dismiss": NSRect(x: rect.minX+20, y: rect.maxY-52, width: 304, height: 34)] }
        return ["dismiss": NSRect(x: rect.minX+20, y: rect.maxY-52, width: 142, height: 34),
                "update": NSRect(x: rect.minX+182, y: rect.maxY-52, width: 142, height: 34)]
    }
    func draw(time: TimeInterval? = nil) {
        let elapsed = time ?? ProcessInfo.processInfo.systemUptime-started
        let ink = NSColor(calibratedRed: 0.29, green: 0.23, blue: 0.25, alpha: 1)
        let rose = NSColor(calibratedRed: 0.64, green: 0.38, blue: 0.44, alpha: 1)
        let green = NSColor(calibratedRed: 0.27, green: 0.57, blue: 0.38, alpha: 1)
        func text(_ string: String, _ box: NSRect, _ size: CGFloat, _ weight: NSFont.Weight = .regular, _ color: NSColor? = nil) {
            let paragraph = NSMutableParagraphStyle(); paragraph.lineSpacing = 4; paragraph.lineBreakMode = .byTruncatingTail
            NSAttributedString(string: string, attributes: [.font: NSFont.systemFont(ofSize: size, weight: weight), .foregroundColor: color ?? ink, .paragraphStyle: paragraph]).draw(with: box, options: [.usesLineFragmentOrigin, .truncatesLastVisibleLine])
        }
        let path = NSBezierPath(roundedRect: rect, xRadius: 20, yRadius: 20)
        let tail = NSBezierPath(); tail.move(to: NSPoint(x: 400,y:rect.maxY-1)); tail.line(to:NSPoint(x:410,y:rect.maxY+10)); tail.line(to:NSPoint(x:420,y:rect.maxY-1)); tail.close()
        NSGraphicsContext.saveGraphicsState()
        let shadow = NSShadow(); shadow.shadowColor = NSColor.black.withAlphaComponent(0.14); shadow.shadowBlurRadius = 16; shadow.shadowOffset = NSSize(width:0,height:-4); shadow.set()
        NSColor(calibratedRed:0.99,green:0.95,blue:0.94,alpha:1).setFill(); path.fill()
        NSGraphicsContext.restoreGraphicsState()
        NSGradient(starting:NSColor(calibratedRed:1,green:0.98,blue:0.95,alpha:1),ending:NSColor(calibratedRed:0.985,green:0.90,blue:0.92,alpha:1))!.draw(in:path,angle:70)
        let border = NSColor(calibratedRed:0.88,green:0.59,blue:0.67,alpha:0.92)
        border.setStroke(); path.lineWidth=2; path.stroke()
        NSColor(calibratedRed:0.985,green:0.91,blue:0.92,alpha:1).setFill(); tail.fill()
        let sides = NSBezierPath(); sides.move(to:NSPoint(x:400,y:rect.maxY)); sides.line(to:NSPoint(x:410,y:rect.maxY+10)); sides.line(to:NSPoint(x:420,y:rect.maxY)); sides.lineWidth=2; sides.stroke()
        text("猪猪桌宠 · 软件更新", NSRect(x:rect.minX+20,y:rect.minY+16,width:304,height:18),11,.medium,rose)
        if let release {
            text(installationError != nil ? "更新未完成" : progressMessage != nil ? "正在更新到 \(release.version)" : "检测到有新版本 \(release.version)",NSRect(x:rect.minX+20,y:rect.minY+43,width:304,height:24),17,.semibold)
            text(installationError ?? progressMessage ?? release.notes,NSRect(x:rect.minX+20,y:rect.minY+78,width:304,height:64),13)
            if progressMessage != nil {
                let bar=NSRect(x:rect.minX+20,y:rect.minY+135,width:304,height:6)
                NSColor(calibratedWhite:0.85,alpha:1).setFill()
                NSBezierPath(roundedRect:bar,xRadius:3,yRadius:3).fill()
                green.setFill()
                let width=progress.map { CGFloat(min(1,max(0,$0)))*bar.width } ?? 60
                let offset=progress == nil ? CGFloat((sin(elapsed*2)+1)/2)*(bar.width-width) : 0
                NSBezierPath(roundedRect:NSRect(x:bar.minX+offset,y:bar.minY,width:width,height:bar.height),xRadius:3,yRadius:3).fill()
            }
            text(progressMessage != nil ? "完成后会自动重启，设置和任务数据会保留。" : "是否选择更新版本：\(current)→\(release.version)",NSRect(x:rect.minX+20,y:rect.minY+146,width:304,height:20),12,.medium)
        } else {
            let title: String
            if case .current = result { title = "当前已是最新版本啦！" } else { title = "暂时无法检查更新，请稍后重试" }
            text(title,NSRect(x:rect.minX+20,y:rect.minY+47,width:304,height:25),release == nil && title.count > 16 ? 15 : 17,.semibold)
        }
        for (action,box) in buttons {
            let primary = action == "update" || release == nil
            let adjusted = box.offsetBy(dx:0,dy:pressed == action ? 1 : 0)
            (primary ? green : NSColor(calibratedWhite:0.89,alpha:1)).setFill()
            NSBezierPath(roundedRect:adjusted,xRadius:10,yRadius:10).fill()
            let label = action == "cancel" ? "取消下载" : action == "update" ? (installationError == nil ? "更新" : "重试") : release == nil ? "收到！" : "稍后再说"
            let attributes: [NSAttributedString.Key:Any] = [.font:NSFont.systemFont(ofSize:13,weight:.semibold),.foregroundColor:primary ? NSColor.white : ink]
            let size = (label as NSString).size(withAttributes:attributes)
            (label as NSString).draw(at:NSPoint(x:adjusted.midX-size.width/2,y:adjusted.midY-size.height/2),withAttributes:attributes)
        }
        if release != nil { drawBulb(elapsed) }
    }
    private func drawBulb(_ elapsed: TimeInterval) {
        let reduced = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        let pulse = reduced ? 0.5 : (sin(elapsed * .pi * 1.25)+1)/2
        let lift = reduced ? 0 : sin(elapsed * .pi * 1.25)*2
        NSGraphicsContext.saveGraphicsState()
        let transform = NSAffineTransform(); transform.translateX(by:410,yBy:390+lift)
        // The pet canvas is flipped: negative angles turn visually counterclockwise.
        transform.rotate(byDegrees: -30)
        transform.concat()
        for i in stride(from: 28, through: 18, by: -2) {
            NSColor(calibratedRed:1,green:0.77,blue:0.20,alpha:CGFloat(0.015+0.017*pulse)).setFill()
            NSBezierPath(ovalIn:NSRect(x:-CGFloat(i),y:-CGFloat(i)-5,width:CGFloat(i*2),height:CGFloat(i*2))).fill()
        }
        let outline = NSColor(calibratedRed:0.64,green:0.43,blue:0.19,alpha:1)
        let bulb=NSBezierPath(); bulb.move(to:NSPoint(x:-8,y:10)); bulb.curve(to:NSPoint(x:-15,y:-7),controlPoint1:NSPoint(x:-8,y:4),controlPoint2:NSPoint(x:-15,y:3)); bulb.curve(to:NSPoint(x:15,y:-7),controlPoint1:NSPoint(x:-15,y:-27),controlPoint2:NSPoint(x:15,y:-27)); bulb.curve(to:NSPoint(x:8,y:10),controlPoint1:NSPoint(x:15,y:3),controlPoint2:NSPoint(x:8,y:4)); bulb.close()
        let glow=NSShadow();glow.shadowColor=NSColor.systemYellow.withAlphaComponent(0.6+0.3*pulse);glow.shadowBlurRadius=8+8*pulse;glow.set()
        NSColor(calibratedRed:1,green:0.86+0.07*pulse,blue:0.36,alpha:1).setFill();bulb.fill()
        NSShadow().set();outline.setStroke();bulb.lineWidth=2.5;bulb.stroke()
        let filament=NSBezierPath();filament.move(to:NSPoint(x:-4,y:8));filament.line(to:NSPoint(x:-5,y:-3));filament.line(to:NSPoint(x:0,y:0));filament.line(to:NSPoint(x:5,y:-3));filament.line(to:NSPoint(x:4,y:8));filament.lineWidth=1.8;filament.stroke()
        NSColor(calibratedRed:0.86,green:0.80,blue:0.66,alpha:1).setFill()
        let base=NSBezierPath(roundedRect:NSRect(x:-8,y:10,width:16,height:10),xRadius:3,yRadius:3);base.fill();base.lineWidth=2;base.stroke()
        let line=NSBezierPath();line.move(to:NSPoint(x:-6,y:15));line.line(to:NSPoint(x:6,y:15));line.lineWidth=1.5;line.stroke()
        NSColor.white.withAlphaComponent(0.8).setStroke();let shine=NSBezierPath();shine.move(to:NSPoint(x:-9,y:-8));shine.curve(to:NSPoint(x:-4,y:-15),controlPoint1:NSPoint(x:-9,y:-12),controlPoint2:NSPoint(x:-7,y:-15));shine.lineWidth=3;shine.lineCapStyle = .round;shine.stroke()
        outline.withAlphaComponent(0.45+0.4*pulse).setStroke()
        for angle in [-150.0,-110,-70,-30,15,165] {
            let a=angle * .pi/180;let ray=NSBezierPath();ray.move(to:NSPoint(x:cos(a)*25,y:sin(a)*25-5));ray.line(to:NSPoint(x:cos(a)*(29+3*pulse),y:sin(a)*(29+3*pulse)-5));ray.lineWidth=2;ray.lineCapStyle = .round;ray.stroke()
        }
        NSGraphicsContext.restoreGraphicsState()
    }
}
