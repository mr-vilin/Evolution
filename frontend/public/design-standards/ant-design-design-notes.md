概述
本文档描述 Ant Design v6 的默认浅色主题。该系统遵循语义化版本：主版本发布（v5 → v6）意味着设计语言的全面 overhaul（重构/革新），而次版本和补丁版本会保持本文档稳定。关于同一主版本内逐版本的 token 漂移，请参阅 CHANGELOG.en-US.md。

Ant Design 是 Ant Group 用于交付企业软件的开源设计系统——主要面向中后台控制台、仪表盘和运营工具。该系统创建于 2015 年，旨在为大型产品团队提供共享的、有主张的基础，使他们无需在每个屏幕上重新决定基础问题，就能交付密集、数据丰富的界面。

四条价值观指导该系统中的每一个决策：

自然。 界面遵循既有惯例；不会让回访用户感到意外。优先采用操作系统和上一代企业软件中已经存在的模式，而不是新颖发明。

确定。 用户始终知道自己处于什么状态、输入产生了什么结果、下一步是什么。悬停、聚焦、加载和错误状态明确且一致。

有意义。 视觉强调只保留给操作。不传达信息的装饰会被移除。

成长。 系统从小型表单扩展到密集表格，再扩展到多租户管理控制台，而不会失去一致性。

颜色
调色板由一个 primary 品牌种子、四个语义状态种子（success、warning、error、info）以及用于文本和表面的中性基础色构成。颜色种子会通过 @ant-design/colors 自动扩展为渐变阶梯，覆盖背景浅色、悬停、激活和描边变体——更改种子，整个派生调色板都会随之移动。

选择 #1677FF 作为 primary，是因为蓝色读起来可信、专注，既没有深海军蓝的企业扁平感，也没有高饱和青色的玩味感。它是操作、链接、聚焦环、选中导航和活动标签页的默认品牌色。

可访问性说明：本文件记录 Ant Design 的默认视觉 token。一些品牌色配对，尤其是 #1677FF 上的白色文本，以及浅色选中背景上的 primary 文本，低于 WCAG AA 对小文本的 4.5:1 对比度阈值。对于严格的可访问性目标，请通过 ConfigProvider 加深 colorPrimary，或使用组件级 token 覆盖，而不是发明一次性颜色。

运行时 token 系统中的中性文本和叠加层以 rgba(0, 0, 0, α) 表示，而不是扁平灰色十六进制值。原因是叠加：当文本位于带色卡片或彩色单元格高亮之上时，不透明灰色会破坏色调，而透明黑色会自然混合。四个标准 alpha 步进是 0.88（主要文本，此处导出为 #1F1F1F）、0.65（次要文本，#595959）、0.45（三级/描述文本）和 0.25（占位符/禁用，#BFBFBF）。本文档中列出的十六进制值是在白色表面上等效的合成结果，适用于需要十六进制的静态导出目标；支持 alpha 的下游消费者应优先使用来自 @ant-design/cssinjs 的 rgba() 形式。

预设颜色（blue、purple、cyan、green、magenta、red、orange、yellow、volcano、geekblue、gold、lime；在运行时 token 中，pink 是 magenta 的已弃用别名）保留用于标签、图表和分类可视化——绝不用于主要 UI 可供性。使用功能色（success/warning/error/info）表示状态，并将 primary 保留给每个屏幕上最重要的单个操作。

排版
基础字号是 14 px，不是 16。企业控制台用可读性余量换取信息密度——一个 1440 px 宽的窗口必须舒适地容纳侧边栏、页头、八列数据表和详情面板。在 14 px 下，一行正文文本在这些布局所需的列宽下达到约 75 个字符的眼跳最佳区间。

字体栈按顺序优先使用操作系统 UI 字体：Apple 的 -apple-system，然后是 BlinkMacSystemFont，然后是 Windows 的 Segoe UI，然后是 Android/ChromeOS 的 Roboto，然后是 Helvetica Neue，然后是 Arial，用 Noto Sans 覆盖 Linux。Emoji 回退保持简短。代码字体按相同顺序使用 SFMono-Regular、Consolas、Liberation Mono、Menlo 和 Courier。

产品 UI 中只出现 两种字重：400（正文、控件、菜单项、标签页标签）和 600（fontWeightStrong——标题、表头以及任何标题级排版）。细体（100–300）、粗体（700+）和斜体不用于界面 chrome——它们会与系统追求的平静、确定基调相冲突。斜体仅在长篇文档正文中可接受。选中/激活状态的视觉强调来自颜色和描边（边框、下划线），而不是字重。

布局
所有间距都对齐到 4 px 网格。六步间距刻度（unit、xs、sm、md、lg、xl → 4 / 4 / 8 / 16 / 24 / 32 px）覆盖系统中的每个间隙、槽和 inset。魔法数字——padding: 11px、gap: 13px——不会出现在 token 驱动的代码中；输入字段的 11 px 水平内边距之所以存在，只是因为该设计早于 4 px 网格，而一像素迁移会移动数百万个现有屏幕。

表面使用 三层模型：

bg-layout（#F5F5F5）——页面背景。它包围并包含其他一切。

bg-container（#FFFFFF）——卡片、面板、表格和表单的表面。大多数内容位于此处。

bg-elevated（#FFFFFF，与 bg-container 相同的十六进制值）——模态框、下拉菜单、弹出层的表面。它与 bg-container 的区别不是颜色，而是阴影。

永远不要在产品代码中硬编码 #FFF 或 #FAFAFA。读取 token。三层模型正是让深色模式算法能够翻转表面阶梯而不破坏布局的原因。

高度与深度
Ant Design 是 扁平优先。边框和色调对比承载层级。阴影只出现在真正悬浮于其上下文之上的表面。

阴影 token 由 colorShadow 生成，因此相同的名称可以跨浅色和深色主题适配。核心层级是：

Tertiary（boxShadowTertiary）——轻型抬升表面阴影：0 1px 2px 0 rgba(0,0,0,0.05), 0 1px 6px -1px rgba(0,0,0,0.03), 0 2px 4px 0 rgba(0,0,0,0.03)。

Popup（boxShadow 和 boxShadowSecondary）——标准浮动层阴影：0 6px 16px 0 rgba(0,0,0,0.08), 0 3px 6px -4px rgba(0,0,0,0.12), 0 9px 28px 8px rgba(0,0,0,0.05)。

Card（boxShadowCard）——卡片专用抬升阴影，扩散更紧，用于卡片需要与容器区分时。

方向性抽屉和溢出阴影（boxShadowDrawer*、boxShadowTabsOverflow*）——用于边缘附着表面和滚动可供性的专用 token。

Popover 箭头（boxShadowPopoverArrow）——仅用于 tooltip 和 popover 箭头上的小三角指针。

动效使用三个时长和一个小型 cubic-bezier 缓动库，全部作为 token 暴露：

motionDurationFast——0.1 s，用于状态变化（悬停、聚焦、按下）。

motionDurationMid——0.2 s，用于组件内部过渡（折叠、淡入淡出）。

motionDurationSlow——0.3 s，用于表面级变化（模态框进入、抽屉滑入）。

缓动是预定义的：motionEaseInOut、motionEaseOut、motionEaseIn、motionEaseOutBack、motionEaseOutCirc 等。不要随意选择 transition-timing-function。如果设计需求不匹配现有缓动，使用 motionEaseInOut 并继续。

形状
默认圆角半径是 6 px。它足够圆润，读起来现代且友好，但又足够小，使 32 像素高的按钮仍呈现干净、近乎矩形的轮廓，适合密集表单。

按组件类别：

控件（按钮、输入框、选择器、下拉触发器）——6 px（rounded.DEFAULT）。

表面（卡片、模态框、抽屉、通知）——8 px（rounded.lg）。

标签和小 chip——4 px（rounded.md）。

Tooltip 和 popover——4 px（rounded.md）。

全胶囊形（rounded.full，9999 px）保留给圆形头像、徽标和圆点——不用于按钮或标签。方形（0 px）保留给表格和分段控件的内边缘。相邻元素混用圆角是一种坏味道：一个 8 px 圆角的卡片不应包含一个 16 px 圆角的按钮。

组件
组件原型捕捉系统最常见的表面和状态。下面每个条目都映射到 YAML front-matter 中的 token 引用。

Button（primary）——每个屏幕的单个主导操作。实心 primary 填充，白色文本，32 px 高，6 px 圆角。悬停将填充变亮为 #4096FF；激活变暗为 #0958D9。不要在一个决策中堆叠两个 primary 按钮。

Button（default）——次要操作。白色表面上的透明背景，深色文本，1 px 描边边框。悬停将文本颜色变为 #4096FF；边框着色以匹配。

Input field——32 px 高，与按钮匹配。细微的 1 px 描边边框；聚焦状态将边框加粗为 primary 并添加内发光。占位符文本使用 on-surface-disabled。

Select——视觉上与 Input 相同。触发器在交互前读起来像输入框。

Card——主力容器。白色表面，8 px 圆角，可选 boxShadowCard 高度。内部内边距四边均为 24 px；嵌套控件保持 16 px 间隙。

Modal——与 Card 相同的表面和圆角，但使用次级阴影层级，并在 rgba(0, 0, 0, 0.45) 遮罩上居中。主体内边距为上下 20 px × 左右 24 px。

Menu（选中项）——#E6F4FF 背景，primary 文本。这是导航中“你在这里”的单一视觉线索。

Tabs（活动标签页）——primary 文本和 2 px primary 下划线。非活动标签页为 on-surface-variant。标签页在任何状态下都没有背景填充。

Table（表头行）——surface-container 背景，title-md 排版（14 px / 600）。正文行仅在悬停时交替，默认不交替——系统信任用户无需斑马纹就能阅读密集数据。

Tag——小型分类标签。4 px 圆角，12 px 字体，来自预设调色板的低饱和 pastel 填充。永远不要用标签表示关键状态——使用 Alert 或 Badge。

Alert——语义反馈表面。成功、警告、错误和信息警报使用浅色语义背景和正常文本颜色；状态通过图标和色调传达，而不是通过低对比度的彩色正文文本。

Badge 状态点——紧凑状态指示器。关键状态可以使用 error 填充，但在可访问性关键流程中，圆点不能替代文本。

Tooltip——高对比度反色表面：rgba(0,0,0,0.85) 背景，白色文本。始终由框架定位，永不手动固定。

Dropdown menu（条目悬停）——悬停时 surface-container 填充，文本颜色不变。悬停可供性已经足够。

应该做与不要做
应该 将四条设计价值观作为决胜依据。当两种方法冲突时，能为用户产生更确定、更易读状态的那一种胜出。

不要 在同一表面上堆叠两个 primary 色按钮。选择一个。将其余降级为 default。

应该 从 colors.surface、colors.surface-container 和 colors.surface-layout 读取表面。它们反映三层模型。

不要 硬编码 #FFFFFF 或 #FAFAFA。十六进制值是偶然的；角色才是重要的。

应该 对于找不到更具体 token 的任何组件级过渡，使用 motionDurationMid（0.2 s）。

不要 发明自定义 cubic-bezier 曲线。使用命名缓动。

应该 将预设调色板（blue 到 lime）保留给标签、图表和分类可视化。

不要 为一次性 UI 表面在预设调色板之外铸造强调色。如果某个屏幕似乎需要一种，设计可能需要的是不同布局。

应该 通过间距刻度将每个间隙、inset 和槽对齐到 4 px 网格。

不要 在产品代码中使用魔法数字。如果刻度缺少你需要的步进，需要重新审视设计，而不是做一像素覆盖。

定制
上述 YAML front-matter 中的每个值都是 defaultAlgorithm——浅色主题——产生的 默认值。Ant Design 主题化比 Design Token 替换更广泛：它包括算法派生、组件作用域覆盖、动态切换、嵌套主题作用域、CSS 变量输出、静态 token 消费和零运行时 CSS 提取。完整运行时 API 和示例请参阅 Customize Theme。

主要主题配置入口是 ConfigProvider 的 theme prop：

种子 token 覆盖。 将 theme.token 传给 ConfigProvider 以替换任何种子。主要和语义颜色种子（colorPrimary、colorSuccess、colorWarning、colorError、colorInfo）会扩展为派生渐变，而 colorBgBase 和 colorTextBase 驱动中性表面和文本。间距、圆角和字号种子以相同方式工作。

算法切换。 设置 theme.algorithm 以切换派生逻辑。defaultAlgorithm、darkAlgorithm 和 compactAlgorithm 可以单独使用，也可以作为数组组合——不要手动反转颜色；算法会考虑非线性调色板、表面、阴影和尺寸关系。

组件级覆盖。 theme.components.Button（或任何组件的 token 命名空间）可以覆盖单个组件的 Component Token 和消费的 Alias Token，而不影响其他组件。在组件配置中，algorithm 可以让该组件进入 token 派生，当覆盖仍应遵循种子 token 关系时。

运行时作用域。 主题可以通过更改 ConfigProvider.theme 动态切换，嵌套的 ConfigProvider 实例创建局部主题，从父级继承未更改的 token。诸如 message.xxx、Modal.xxx 和 notification.xxx 等静态 API 不会自动接收周围上下文；当需要主题化静态反馈时，使用基于 hook 的 API、App 或显式上下文持有者。

Token 消费和输出。 在 React 内使用 theme.useToken()，在 React 外使用 theme.getDesignToken() 来消费已解析的 token。当需要 CSS 变量时使用 theme.cssVar，当必须禁用运行时样式生成时使用 theme.zeroRuntime 配合预构建或提取的 CSS。

对于自定义主题生成，首先保持 Ant Design 的交互结构、密度、状态反馈和组件语义。然后更改最小必要的种子集：通常是 colorPrimary、状态颜色、borderRadius、fontFamily、fontSize 和中性表面基础色。品牌页面可以看起来不同，但表单、表格、导航、覆盖层、聚焦状态和验证反馈仍应感觉像 Ant Design。避免生成绕过 token、算法、theme.components、CSS 变量或提取静态样式的自定义 CSS 规则；如果主题无法通过这些官方层表达，请将其视为设计系统扩展，而不是一次性页面样式。