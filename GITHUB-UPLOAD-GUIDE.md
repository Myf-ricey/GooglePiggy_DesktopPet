# GitHub 覆盖上传指南

这里的交付分为“仓库源码覆盖包”和“GitHub Release 二进制附件”，两者用途不同。

## 1. 覆盖现有 Windows 仓库

使用：

```text
GooglePiggy-GitHub-source-v0.2.3.zip
```

操作方式：

1. 先保留现有 GitHub 仓库或本地仓库备份。
2. 把源码覆盖包解压到现有 Windows 项目的仓库根目录。
3. 对同名文件选择替换。包中保留了 Windows 源码、安装器和工作流，并新增 Mac
   源码、构建脚本、说明文档和工作流。
4. 查看 Git diff，确认没有个人文件、测试文件、虚拟环境或构建产物。
5. 阅读 `README.md`、`README-MAC.md`、`RELEASE-CHECKLIST.md` 和
   `RELEASE-NOTES-v0.2.3.md`。
6. 你确认后再提交、推送或创建 `v0.2.3` 标签。

不要把 `GooglePiggy-GitHub-source-v0.2.3.zip` 当成程序下载附件让普通用户安装；
GitHub 会从提交后的仓库自动生成 Source code ZIP。

## 2. GitHub Release 附件

本地已经验证、可直接作为 macOS 下载项上传：

```text
GooglePiggy-macos-universal.zip
GooglePiggy-macos-universal.dmg
```

Windows x64、macOS arm64 和 macOS x64 包可由仓库里的两个 GitHub Actions
工作流生成。创建 `v0.2.3` 标签前，先按 `RELEASE-CHECKLIST.md` 完成清洁系统测试。

## 3. 一次性交付总包

`GooglePiggy-GitHub-upload-v0.2.3.zip` 只用于交付和备份，里面包含：

- 仓库源码覆盖包；
- Universal 2 Mac ZIP 与 DMG；
- 上传指南与 Release Notes；
- 所有交付文件的 SHA-256。

不要把这个总包本身作为最终用户下载项上传到 GitHub Release。
