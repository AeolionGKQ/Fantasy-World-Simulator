# Design System

## Direction

明亮的冒险绘本：浅蓝纸面背景、暖白卡片、深蓝描边和少量向日葵黄点缀。卡片使用实色偏移阴影，营造手绘插画书的质感；正文区域保持安静、宽松，方便长时间阅读。主色（靛蓝）只用于主要操作、已选状态和焦点；向日葵黄只用于品牌标记与“当前位置”（当前步骤、当前页签），不用于装饰。

## Color Palette

所有颜色以设计令牌定义在 `apps/web/src/styles/tokens.css`，组件和页面只通过 `var(--token)` 引用。主要令牌：

```css
:root {
  --bg: #edf4ff;            /* 页面背景 */
  --surface: #fffdf7;       /* 卡片、输入区 */
  --surface-raised: #e1ebff;/* 悬停与已选底色 */
  --selected: #e8efff;      /* 已选芯片 */
  --line: #c4d0e5;
  --line-strong: #7385a3;
  --outline: #344675;       /* 卡片描边 */
  --ink: #1f2850;           /* 标题与正文 */
  --body: #354467;          /* 长篇正文 */
  --muted: #53617c;         /* 辅助文字 */
  --primary: #3548bd;
  --accent: #80591e;        /* 阶位、世界资料标签 */
  --sunflower: #f7ce59;     /* 品牌、当前步骤与页签 */
  --surface-sunken: #eef3fd;/* L2 内部分组 */
  --surface-tint: #e4edff;  /* 设定图占位、候选面板标题 */
  --danger / --success / --warning: 文字色，配套 *-soft 底色与 *-line 边框
  --info-soft / --info-line: 提示与任务状态卡
  --card-shadow-color: #d2def0; /* 卡片偏移阴影 */
  --shadow-float / --shadow-dialog / --shadow-drawer: 只用于浮起的元素
}
```

`features/`、`components/`、`layout/` 与 `base.css` 中不写十六进制颜色，新颜色先加令牌。状态（成功、警告、错误）同时使用文字、符号和颜色，颜色不是唯一编码。

### 表面层级

| 级别 | 用途 | 样式 |
| --- | --- | --- |
| L0 页面 | 页面背景 | `--bg`，无边框 |
| L1 主表面 | 每个页面区域最多一个：剧情阅读列、建议行动列、当前步骤卡片、页签面板、设置分区、首页档案列表、弹窗 | 2px `--outline` 描边 + 偏移阴影 |
| L2 内部分组 | 状态条、长期属性、本段变化、输入摘要、首页档案卡、等阶提示 | `--surface-sunken`，不加描边 |
| L3 可交互项 | 选项按钮、芯片 | 默认 1px `--line`，悬停或选中时加深 |

提示框（错误、警告、信息）保留描边，以便状态不只靠颜色区分。

## Typography

- 界面字体：`"Noto Sans SC", "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", system-ui, sans-serif`。
- 阅读字体 `--font-reading`：Noto Serif SC（`@fontsource/noto-serif-sc`，400 与 700 两个字重，打包在本地，不依赖网络）。只用于剧情章节标题与正文、世界资料的条目标题与正文；按字符范围分片，只在用到的页面下载。
- 字号只用令牌：`--text-xs` 13px、`--text-sm` 14px、`--text-base` 16px、`--text-md` 18px（h3）、`--text-read` 18px（阅读正文）、`--text-lg` 22px（h2）、`--text-xl` 28px（h1）、`--text-display` clamp(32px, 2.8vw, 44px)（角色名、章节标题、首页标题）。中文最小 13px。
- 界面正文 16px/1.65；剧情正文 18px/1.85，每行约 36 个汉字（`max-width: 36em`）。
- 字重 750，页面主标题 800；宋体标题 700。
- 标题使用 `text-wrap: balance`，正文使用 `text-wrap: pretty`。

## Responsive Layout

只有两档，断点 1024px：

- **电脑端（≥ 1024px）**：存档侧栏 + 顶部工具栏 + 主工作区。角色创建为“步骤导航 + 步骤卡片”两列，剧情页为“阅读列 + 操作列”两列。
  - 1024px → 1200px 之间，侧栏宽度、页面边距、步骤导航宽度、剧情操作列宽度等“桌面密度”数值从紧凑值线性过渡到完整值（见 `tokens.css` 中的 Desktop density），1200px 以上固定为完整值。这不是额外的档位，没有新的断点。
- **移动端（≤ 1023px）**：侧栏变为抽屉，工具栏只显示图标；步骤导航变为横向滚动条；剧情页、设置页和各页签改为单列。
- 每个样式文件把移动端规则集中在文件末尾的一个 `@media (max-width: 1023px)` 块中。

## Components

- 按钮：主按钮为靛蓝实色、深色描边和偏移阴影，按下时阴影收起；次按钮为卡片色加完整边框；危险操作为浅红底红字；文字按钮无边框。所有按钮最小高度 44px（文字按钮 36px）。
- 表单：标签始终可见，输入框最小高度 44px、圆角 `--radius-md`；错误信息与字段关联。
- 圆角只用令牌：`--radius-sm` 8px、`--radius-md` 12px、`--radius-lg` 16px、`--radius-xl` 22px、`--radius-full`；1–3px 的细条保留自身小圆角。
- 单选组：用原生单选框 + 相邻 `<span>` 呈现为按钮。`segmented-field` 为等宽三列，已选项实色填充；`choice-field` 为可换行芯片；`option-track` 为横向滚动芯片（世界资料浏览）。
- 卡片：按“表面层级”使用；L1 为 2px 描边、`--radius-xl` 圆角和偏移阴影。
- 世界资料：种族、地点与势力共用 `ResponsiveArtwork`。电脑端及横屏使用 12:5 横图；移动端竖屏使用 4:5 竖图，高度不超过 85vh。图片切换条件在 `types.ts` 的 `PORTRAIT_ART_MEDIA` 与 `styles/components/artwork.css` 中保持一致。缺图时收为 96px（手机 80px）的横幅，显示条目名与“设定图待补充”。
- 势力资料只读；地点资料使用单选语义。
- 等阶：一至十阶用中文数字显示，后端保存整数；六阶以下建议属于游戏体验提示。
- 对话：页面内确认优先；删除等不可逆操作才使用原生 `<dialog>`（`components/Modal.tsx`）。弹窗内需要初始焦点的输入框加 `data-autofocus`，取消按钮加 `data-modal-close`。
- 当前位置高亮（存档侧栏、游戏页签、剧情输入模式、角色创建步骤导航）由一个滑动元素承担（`useSlidingIndicator` + `.slide-indicator`）。
- 设置入口在工具栏（电脑端与手机端都显示）；剧情 AI 未配置或连接失败时，设置按钮右上角显示红点。
- 存档侧栏底部显示模型服务状态（`ServiceStatusPanel`）：剧情 AI 与图片 AI 各一行，状态为“未配置 / 已配置，未测试 / 已连接 · 模型名 / 连接失败”，用文字、符号和颜色共同表示；整块链接到设置页。后端不可达时只显示“游戏服务未连接”。状态读取已记录的结果，不会调用模型服务。

## Motion

- 只动 `transform` 与 `opacity`；离场比入场快。时长与缓动只用令牌：`--dur-press` 100ms、`--dur-state` 180ms、`--dur-exit` 140ms、`--dur-enter` 240ms、`--dur-move` 320ms；`--ease-out`（即 `--ease`）、`--ease-in`、`--ease-move`；`--rise` 8px、`--slide` 24px、`--stagger` 50ms。
- 页面切换：React Router 的 `viewTransition`（`<Link viewTransition>`、`useAppNavigate`）。只有主内容区淡出并上移淡入，侧栏与工具栏保持不动；工具栏标题交叉淡化。加载态不参与命名，内容加载完成后由 `.page-enter` 入场；骨架屏延迟 150ms 出现。
- 页面内切换：`runViewTransition(kind, update, direction)`（`app/viewTransition.ts`）。在 `<html data-vt>` 上标记类型，`styles/components/motion.css` 按类型命名元素：角色创建步骤与游戏页签按方向滑动，翻阅剧情历史小幅滑动，剧情输入模式与世界资料条目交叉淡化。
- 浮层：弹窗缩放淡入，离场后焦点回到打开它的按钮；Toast 与游戏提示条有入场和离场；手机抽屉的遮罩淡入淡出。
- 内容：新剧情段落依次出现；资源条首次显示时增长；候选面板与生成图片入场；生成中使用低频脉冲，不使用旋转装饰或粒子。
- `prefers-reduced-motion: reduce` 下不启动页面过渡，关闭所有动画与过渡，内容直接显示在最终位置。

## Content Rules

- 操作按钮采用“动词 + 对象”，如“保存设置”“生成角色”“接受角色”。
- 明确区分程序规则、世界提示和模型建议。
- 不使用营销文案，不承诺尚未实现的玩法。

## Frontend Structure

```
apps/web/src/
  app/            应用外壳：路由、存档侧栏（含服务状态）、工具栏、页面过渡（viewTransition.ts）、滚动辅助
  components/     通用组件：Icon、Modal、ErrorPanel、LoadingPanel、SegmentedField、ResponsiveArtwork、FadeImage…；钩子 useAutoFocus、usePresence、useSlidingIndicator
  features/
    home/         首页、404
    saves/        新建、重命名、删除、导入存档弹窗
    settings/     设置页（状态在 useSettingsPage，三个分区组件只负责渲染；纯函数在 settingsLogic）
    character/    角色创建向导（状态在 useCharacterWizard，步骤元数据与校验在 wizardSteps）、各步骤、候选面板、审阅页
    game/         游戏工作区（状态在 useGameWorkspace）、各页签面板、helpers
    scene-image/  生成此刻图片
  styles/         样式（见下）
  api.ts  types.ts  playerCopy.ts
```

### 样式

`styles/index.css` 按顺序声明并导入级联层：

| 层 | 内容 |
| --- | --- |
| `tokens` | 设计令牌（只有自定义属性） |
| `base` | 元素默认样式、图标、关键帧、减少动效 |
| `components` | 多个页面共用的控件：按钮、表单、反馈、弹窗、设定图、动效（`motion.css`） |
| `layout` | 应用外壳与页面容器 |
| `features` | 各页面/功能的样式，一个功能一个文件 |
| `utilities` | 必须压过其他规则的单一用途类（`.sr-only`、`.warning-text`） |

修改约定：

- 新样式放进对应功能的文件；被两个以上功能使用时再提到 `components`。
- 颜色、字号、圆角、阴影、动效时长、桌面密度数值都使用令牌；新的重复数值先加令牌。
- 新动画使用已有关键帧（`base.css`）与动效令牌，并确认减弱动效下内容立即可见。
- 不使用 `!important`（减少动效规则除外）；需要覆盖时提高选择器特异性或放到更靠后的层。
- 不新增断点：移动端规则写进文件末尾的 `@media (max-width: 1023px)` 块。
