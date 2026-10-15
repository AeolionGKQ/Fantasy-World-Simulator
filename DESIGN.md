# Design System

## Direction

明亮的冒险绘本：浅蓝纸面背景、暖白卡片、深蓝描边和少量向日葵黄点缀。卡片使用实色偏移阴影，营造手绘插画书的质感；正文区域保持安静、宽松，方便长时间阅读。主色（靛蓝）只用于主要操作、已选状态和焦点，向日葵黄用于品牌标记、当前步骤和当前页签。

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
  --danger / --success / --warning: 文字色，配套 *-soft 底色与 *-line 边框
  --info-soft / --info-line: 提示与任务状态卡
  --card-shadow-color: #d2def0; /* 卡片偏移阴影 */
}
```

状态（成功、警告、错误）同时使用文字、符号和颜色，颜色不是唯一编码。

## Typography

- 字体：`"Noto Sans SC", "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", system-ui, sans-serif`，不依赖网络字体。
- 正文 16px/1.65；剧情正文 16px/2.05，最大宽度 45em；世界资料正文 1rem/1.95，阅读列最大宽度 48em。
- h1 1.75rem、h2 1.375rem、h3 1.125rem，字重 750，页面主标题 800。
- 标题使用 `text-wrap: balance`，正文使用 `text-wrap: pretty`。

## Responsive Layout

只有两档，断点 1024px：

- **电脑端（≥ 1024px）**：存档侧栏 + 顶部工具栏 + 主工作区。角色创建为“步骤导航 + 步骤卡片”两列，剧情页为“阅读列 + 操作列”两列。
  - 1024px → 1200px 之间，侧栏宽度、页面边距、步骤导航宽度、剧情操作列宽度等“桌面密度”数值从紧凑值线性过渡到完整值（见 `tokens.css` 中的 Desktop density），1200px 以上固定为完整值。这不是额外的档位，没有新的断点。
- **移动端（≤ 1023px）**：侧栏变为抽屉，工具栏只显示图标；步骤导航变为横向滚动条；剧情页、设置页和各页签改为单列。
- 每个样式文件把移动端规则集中在文件末尾的一个 `@media (max-width: 1023px)` 块中。

## Components

- 按钮：主按钮为靛蓝实色、深色描边和偏移阴影，按下时阴影收起；次按钮为卡片色加完整边框；危险操作为浅红底红字；文字按钮无边框。所有按钮最小高度 44px（文字按钮 36px）。
- 表单：标签始终可见，输入框最小高度 44px、圆角 12px；错误信息与字段关联。
- 单选组：用原生单选框 + 相邻 `<span>` 呈现为按钮。`segmented-field` 为等宽三列，已选项实色填充；`choice-field` 为可换行芯片；`option-track` 为横向滚动芯片（世界资料浏览）。
- 卡片：页面主要区块（设置分区、步骤卡片、剧情阅读列、各页签）使用 2px 描边、22px 圆角和偏移阴影。
- 世界资料：种族、地点与势力共用 `ResponsiveArtwork`。电脑端及横屏使用 12:5 横图；移动端竖屏使用 4:5 竖图，高度不超过 85vh。图片切换条件在 `types.ts` 的 `PORTRAIT_ART_MEDIA` 与 `styles/components/artwork.css` 中保持一致。缺图时显示带条目名的占位。
- 势力资料只读；地点资料使用单选语义。
- 等阶：一至十阶用中文数字显示，后端保存整数；六阶以下建议属于游戏体验提示。
- 对话：页面内确认优先；删除等不可逆操作才使用原生 `<dialog>`。

## Motion

- 交互状态过渡 160–180ms，缓动 `--ease`（ease-out-quart）。
- 页面进入只做 4px 位移；生成中使用低频脉冲，不使用旋转装饰或粒子。
- `prefers-reduced-motion: reduce` 下关闭动画与过渡。

## Content Rules

- 操作按钮采用“动词 + 对象”，如“保存设置”“生成角色”“接受角色”。
- 明确区分程序规则、世界提示和模型建议。
- 不使用营销文案，不承诺尚未实现的玩法。

## Frontend Structure

```
apps/web/src/
  app/            应用外壳：路由、存档侧栏、工具栏
  components/     通用组件：Icon、Modal、ErrorPanel、LoadingPanel、SegmentedField、ResponsiveArtwork…
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
| `components` | 多个页面共用的控件：按钮、表单、反馈、弹窗、设定图 |
| `layout` | 应用外壳与页面容器 |
| `features` | 各页面/功能的样式，一个功能一个文件 |
| `utilities` | 必须压过其他规则的单一用途类（`.sr-only`、`.warning-text`） |

修改约定：

- 新样式放进对应功能的文件；被两个以上功能使用时再提到 `components`。
- 颜色、阴影色、桌面密度数值使用令牌；新的重复数值先加令牌。
- 不使用 `!important`（减少动效规则除外）；需要覆盖时提高选择器特异性或放到更靠后的层。
- 不新增断点：移动端规则写进文件末尾的 `@media (max-width: 1023px)` 块。
