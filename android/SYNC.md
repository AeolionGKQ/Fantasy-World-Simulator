# Android 版：构建、签名与同步说明

这个文件夹是安卓版（`android` 分支）专有的部分。安卓版和电脑版共用同一套后端（`apps/api`）、世界正典（`canon/`）和前端（`apps/web`），只在“怎么把请求送到后端”和“怎么存文件、存密钥”这几处做了适配。

## 工作方式

```text
WebView（apps/web 构建产物，Capacitor 托管在 https://localhost）
  ├─ api.ts → platform/native.ts → Backend 插件 (BackendPlugin.java)
  │                                   └─ Backend.java（有界线程池）→ Chaquopy → android_bridge.py
  │                                                                          └─ 电脑版 server.py 的请求处理器（原样复用，不开端口）
  ├─ <img src="/api/...">  → BackendWebViewClient 拦截 GET → 同上
  └─ 导出存档 / 保存图片 → 系统“另存为”（Storage Access Framework）
```

- 手机上没有 HTTP 服务、没有端口。`android_bridge.py` 用内存流驱动电脑版的 `FantasySimulatorHandler`，所以路由、校验、错误码和电脑版完全一致；只接受 `/api/` 开头的路径。
- 数据在应用私有目录 `files/game-data/`（数据库与生成的图片）。卸载应用会删除这些数据，提醒玩家先导出存档。
- API 密钥用 Android Keystore 中的 AES 密钥加密后保存（`SecretCipher.java`，设置页显示为 `android_keystore`），重启后不用重新填写。
- 有角色、剧情或图片任务在跑时，`JobKeepAliveService` 以前台服务（dataSync）保持进程运行，并显示“正在生成剧情”通知。没有它，切到后台约十秒后系统会冻结进程，进行中的模型请求会断开（实测 `Software caused connection abort`）。任务结束后服务自动停止。
- 返回键：先关闭打开的对话框，再返回上一页；在首页时把应用切到后台而不是关闭，后台任务不受影响。

## 平台专属文件

合并电脑版改动时，这些文件只属于安卓版，不要被电脑版的文件覆盖：

| 位置 | 作用 |
|---|---|
| `android/` 整个目录 | Capacitor 生成的原生工程，以及下面这些自写文件 |
| `android/app/src/main/python/android_bridge.py` | Python 入口：请求转发、Keystore 密钥存储、`busy()` |
| `android/app/src/main/python-package/__init__.py` | 打包时放到 `apps/` 下，让 `apps.api` 可以作为包导入 |
| `android/app/src/main/java/com/fantasysimulator/app/*.java` | Python 启动与调用、插件、图片拦截、密钥加密、前台服务 |
| `android/app/build.gradle` 中 Chaquopy、签名、版本号部分 | 打包 `apps/api` 与 `canon/` |
| `android/build-apk.ps1` | 一键构建 |
| `apps/web/src/platform/native.ts` | 前端的平台层：请求、保存文件、返回键 |
| `apps/web/capacitor.config.json` | Capacitor 配置 |

共用代码中为安卓做的改动只有这几处，合并时注意保留：

- `apps/web/src/api.ts`：两处 `fetch(` 改为 `platformFetch(`。
- `apps/web/src/features/saves/downloadBlob.ts`：改为调用 `saveFile`，返回是否已保存。
- `apps/web/src/app/App.tsx`：导出后只有真正保存了才提示“存档已导出”。
- `apps/web/src/features/scene-image/SceneImageWorkspace.tsx`：安卓上“保存图片”改为取回图片后另存为。
- `apps/web/src/main.tsx`：`installBackButton()`。
- `apps/web/src/types.ts`：密钥保存方式增加 `android_keystore`。
- `apps/web/package.json`：Capacitor 依赖。

## 构建

工具链统一放在 `D:\Android`：

| 工具 | 位置 | 版本 |
|---|---|---|
| JDK | `D:\Android\jdk-21` | Temurin 21（Gradle 8.14 不能在系统自带的 JDK 25 上运行） |
| Android SDK | `D:\Android\Sdk` | platform-tools、Android 16（API 36）、build-tools 35/36.1 |
| 桌面 Python | `D:\Android\python-3.14` | 3.14.9，Chaquopy 编译字节码用，版本必须与应用内 Python（3.14）一致 |
| Node.js | 系统已装 | 24 |

`android/local.properties`（不进 git）写明 SDK 与桌面 Python 的位置：

```properties
sdk.dir=D\:/Android/Sdk
chaquopy.buildPython=D\:/Android/python-3.14/python.exe
```

在 `android` 目录执行：

```powershell
.\build-apk.ps1            # 正式版：dist\FantasySimulator-v<版本>-android.apk 和 .sha256
.\build-apk.ps1 -Debug     # 调试版（可用 chrome://inspect 调试 WebView）
.\build-apk.ps1 -Install   # 构建后安装到 USB 连接的手机
```

脚本依次执行：前端构建 → `npx cap sync android` → Gradle → `apksigner verify` → 复制到 `dist\` 并计算 SHA-256。脚本会把 TEMP 设为 `D:\Android\tmp`：在这台电脑上用默认 TEMP 时 Gradle 守护进程报 `Unable to establish loopback connection`。

安卓版的前端构建输出到 `apps/web/dist-android`（不进 git）。`apps/web/dist` 是电脑版的构建产物，由 main 维护，安卓分支不提交它的改动，这样合并 main 时不会在构建产物上冲突。

`android/app/src/main/assets/public`、`capacitor.config.json`、`capacitor.plugins.json` 等由 `cap sync` 生成，不要手改。

## 版本号与签名

- `versionName` 自动读取 `apps/web/package.json` 的 `version`，与电脑版保持一致。
- `versionCode` 在 `android/app/build.gradle` 中手动维护，**每次给玩家新 APK 都要加 1**，否则无法覆盖安装。
- 正式版签名密钥：`D:\Android\signing\fantasy-simulator-release.jks`，密码在 `android/keystore.properties`（不进 git，`D:\Android\signing\` 下有一份副本）。
- 证书 SHA-256 指纹：`62:42:A5:D4:1D:B5:8A:D3:5A:FA:01:EC:D1:2A:1A:99:85:62:77:5B:32:E8:33:89:65:22:8B:36:8F:AF:F9:98`
- **请把 `.jks` 和 `keystore.properties` 备份到别处。** 丢失后无法再发布可以覆盖安装的更新，玩家只能卸载重装（会丢失手机上的存档）。
- 调试版和正式版签名不同，两者不能互相覆盖安装。

## 从电脑版同步改动

`origin` 指向本地的电脑版仓库 `D:\Fantasy Simulator\Fantasy-World-Simulator`。

```powershell
git fetch origin
git merge origin/main
```

不要把电脑版的文件整份复制过来；有冲突逐处解决，保留上面列出的安卓改动。合并后逐项检查这次带进来的改动：

1. **新增或修改的接口**：是否用到查询参数、二进制响应、下载头或其他只有真实 HTTP 才有的行为？`android_bridge.py` 会原样传递方法、路径、查询串、头和请求体，一般无需改动；返回图片等二进制内容时，确认 `Content-Type` 正确（插件按类型决定用文本还是 base64 传回）。
2. **浏览器下载或文件选择**：新的“下载”入口要走 `downloadBlob`/`saveFile`，不能用 `<a download>` 或直接链接。
3. **新的 Python 依赖**：只能是纯 Python 包，或有 Android arm64 预编译轮子的包；需要的话写进 `build.gradle` 的 `chaquopy { pip { ... } }`。
4. **密钥与文件路径**：新的密钥要走 `SecretStore`/`NamedSecretStore`，并在 `android_bridge._use_keystore_secrets` 中换成 Keystore 版本；不要假设当前目录或写入 `apps/api` 下的路径。
5. **新的后台任务**：必须放进 `AppContext._workers`（经 `schedule*` 启动），前台服务才能感知到它并保持应用运行。
6. **启动器改动**（`启动游戏.*`、`launch_port.py`）：安卓不需要，忽略。
7. **只能靠鼠标悬停才能完成的操作**：手机上没有悬停，需要有点按的方式。
8. **正典或提示词改动**：自动随 `canon/`、`apps/api` 打包，无需额外处理。

然后：

```powershell
cd apps\api; ..\..\runtime\python\python.exe -m unittest discover -s tests   # 后端测试
cd ..\web; npm run test; npx tsc -b                                         # 前端测试与类型检查
cd ..\..\android; .\build-apk.ps1 -Install                                  # 构建并装到手机
```

在真机上至少走一遍：新建存档 → 生成角色 → 开场 → 提交一回合时切到后台再回来 → 导出、导入存档 → 生图并保存图片。最后把 `versionCode` 加 1。

## 已知限制

- 只打包 arm64-v8a（目前绝大多数安卓手机），不支持 32 位设备和 x86 模拟器；需要时在 `build.gradle` 的 `abiFilters` 加上，APK 会变大。
- 最低支持 Android 7.0（API 24）。实测设备：努比亚 NX809J，Android 16。
- 剧情生成中如果应用被强行结束（从多任务里划掉并强制停止），这一回合会标记为“已中断”，重新打开后需要再次提交行动；这与电脑版服务重启时的行为一致。
- 通知权限只在首次启动时询问一次。拒绝后后台生成照常进行，只是看不到“正在生成剧情”通知；可以在系统设置中随时打开。
