# 一键更新发布指南

## 首次启用

0.5.0 的“更新”仅打开下载页，无法远程变成安装器。用户手动安装带 Sparkle 的 0.5.1 后，才可一键安装后续版本。

检查仍由 GitHub Release API 按 macOS 标签执行。点击更新后，Sparkle 从选中版本的 Release 附件读取 `appcast.xml`，要求更新清单及下载包的 Ed25519 签名有效，并核对版本与用户选中的版本相同。

框架固定为 Sparkle 2.10.0；`tools/prepare_sparkle.sh` 校验官方归档 SHA-256 后下载到忽略的 cache 目录。应用内附 Sparkle 许可证。

## 私钥

私钥保存于发布者本机钥匙串，账户 `GooglePiggyDesktopPet`。应用仅内置公钥。切勿将私钥放入仓库、安装包或 Release；换机前应通过 Sparkle generate_keys 的导出工具备份到受保护的位置。签名工具首次访问钥匙串时需在本机授权。

## 每次发布

1. 更新 macos/Info.plist 的用户版本及递增构建号、build-macos.sh 默认版本、UpdateNotice.swift 命令行测试版本回退值、发布说明。
2. 运行 `./build-macos.sh`，验证双架构、签名、ZIP/DMG；本机 ZIP 使用 Keka 的 `-snl` 保留 Sparkle 符号链接。
3. 运行 `./tools/package_macos_update.sh`，输出到 `dist/macos-update-版本/`。清单和归档均由本机钥匙串私钥签名；已有更新包时脚本拒绝覆盖。
4. 先创建草稿 Release，标签为 `v版本-macos`，上传普通安装包，以及上述目录中的 `appcast.xml` 和 `GooglePiggy-macos-update-版本.zip`。生成并上传校验文件。
5. 确认两份更新附件都已上传，再发布。不要修改已签名的 XML 或归档；若必须修改，重新生成签名并在草稿阶段完成全部上传。

当前 CI 只构建普通安装包，不持有签名私钥。签名更新包由发布机本地生成。CI 仅向已有 Release 上传附件，不会将草稿公开。先推送源码、创建草稿并上传本机签名附件，再推送标签触发 CI；待双架构 CI 成功后手动发布。签名归档在验收后保持不变，可直接将验收候选构建提升为正式发行。

## 安装行为

保留安装路径、自启动配置、Codex hooks 和应用支持目录。不运行 install.command，不重新授权 hooks。
备份位于当前应用同级 `GooglePiggy Backups/update-旧版本-UUID/GooglePiggy.app`。
不能创建备份则取消安装；已有权限请求或拖动时延后重启。Sparkle 负责验签、暂存、替换与重启。

## 测试

`python3 tools/test_update_install.py` 使用独立应用包与本地 HTTP 测试服务验证完整升级、重启、备份、设置保留、取消、备份失败、版本不匹配和损坏包拒绝。
测试编译专用 `UPDATE_TESTING` 开关用于 localhost feed；正式构建不接受环境变量覆盖更新地址。
