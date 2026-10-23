# 本线程改动文件

| 文件 | 行为变化 |
|---|---|
| macos/Sources/GooglePiggy/AppSupport.swift | 外观持久设置、原默认色、原地 reset、大小/alpha/文字色/间距滑条和预览勾选 |
| macos/Sources/GooglePiggy/AppearancePreview.swift | 真实坐标的独立示例预览；不改真实任务状态 |
| macos/Sources/GooglePiggy/FamilySelector.swift | 任务框字体/行高缩放、背景独立 alpha、共享间距定位 |
| macos/Sources/GooglePiggy/PetController.swift | 菜单入口、独立变换及逆命中、任意任务打开、灯泡独立宠物层、尾巴比例 |
| macos/Sources/GooglePiggy/UpdateNotice.swift | 背景/按钮/文字分层与选色，灯泡绘制和边界拆出 |
| macos/Sources/GooglePiggy/EdgeHiding.swift | 大小尾巴及相对间距随宠物缩放 |
| tests/appearance/main.swift | 设置保存/reset、勾选保留、几何命中、位置跟随与 alpha 像素测试 |
| tests/animation-scale/main.swift | 灯泡比例/锚点与四边大小尾巴尺寸测试 |
| tests/appearance-demo/main.swift | 可复现录屏 harness，使用原生控制器与样例数据 |
| tools/test_macos_release.py | 同步文字颜色参数的源码断言，保留最新远端其他检查 |
| macos/Info.plist / build-macos.sh | 交接候选 0.5.6 / 构建 11；不是正式 Release |
| README-MAC.md / VERSIONING.md | 功能、测试与候选版本范围 |
| releases/appearance-0.5.6/* | Windows 落点、保护审计、素材清单、验证和录屏证据 |

Windows 运行代码和源素材本次未修改。包内素材为交接随附，不代表生成了新动画。
