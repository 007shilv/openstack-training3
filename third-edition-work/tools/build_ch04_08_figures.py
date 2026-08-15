"""Generate chapter 4-13 textbook diagrams as editable SVG files.

The SVG source is assembled with the list method required by the diagram skill.
PNG rendering is performed separately by the workspace browser runtime.
"""

from __future__ import annotations

from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "revision" / "figures"
WIDTH = 1600
HEIGHT = 900


def start_svg(title: str) -> list[str]:
    return [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900" width="1600" height="900">',
        '<style>text{font-family:"Times New Roman","SimSun","宋体",serif;font-size:36px;fill:#111827} .title{font-size:46px;font-weight:700} .node-title{font-size:40px;font-weight:700} .sub{font-size:36px;fill:#4b5563} .white{fill:#fff}</style>',
        '<defs><marker id="blue" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="#2563eb"/></marker><marker id="green" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="#16a34a"/></marker><marker id="purple" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="#9333ea"/></marker></defs>',
        '<rect width="1600" height="900" fill="#ffffff"/>',
        f'<text x="800" y="70" text-anchor="middle" class="title">{escape(title)}</text>',
    ]


def box(lines: list[str], x: int, y: int, w: int, h: int, labels: list[str], *, fill: str = "#eff6ff", stroke: str = "#93c5fd", title: bool = False) -> None:
    lines.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="{fill}" stroke="{stroke}" stroke-width="3"/>')
    gap = 46
    first_y = y + h / 2 - (len(labels) - 1) * gap / 2 + 12
    for index, label in enumerate(labels):
        cls = ' class="node-title"' if title and index == 0 else ""
        lines.append(f'<text x="{x + w/2}" y="{first_y + index*gap}" text-anchor="middle"{cls}>{escape(label)}</text>')


def arrow(lines: list[str], x1: int, y1: int, x2: int, y2: int, *, color: str = "blue", dashed: bool = False) -> None:
    dash = ' stroke-dasharray="14 10"' if dashed else ""
    colors = {"blue": "#2563eb", "green": "#16a34a", "purple": "#9333ea"}
    lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colors[color]}" stroke-width="5"{dash} marker-end="url(#{color})"/>')


def save(number: str, lines: list[str]) -> None:
    lines.append("</svg>")
    directory = FIGURES / f"ch{number.split('.')[0]}"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"图{number}.svg").write_text("\n".join(lines), encoding="utf-8")


def build_chapter4() -> None:
    lines = start_svg("信创OpenStack技术栈")
    layers = [
        ("访问入口", "Horizon　命令行　应用接口", "#fff7ed", "#fdba74"),
        ("OpenStack云平台", "身份　镜像　计算　网络　存储", "#eff6ff", "#93c5fd"),
        ("虚拟化与资源管理", "KVM　libvirt　Linux网络　LVM", "#faf5ff", "#c4b5fd"),
        ("openEuler操作系统", "内核　驱动　进程　软件包", "#f0fdf4", "#86efac"),
        ("国产软硬件基础", "处理器　服务器　网卡　磁盘", "#fef2f2", "#fca5a5"),
    ]
    for i, (a, b, fill, stroke) in enumerate(layers):
        y = 120 + i * 138
        box(lines, 220, y, 1160, 102, [a, b], fill=fill, stroke=stroke)
        if i < len(layers) - 1:
            arrow(lines, 800, y + 102, 800, y + 132)
    save("4.1", lines)

    lines = start_svg("双节点环境拓扑与组件分布")
    arrow(lines, 300, 235, 350, 235)
    arrow(lines, 860, 235, 950, 235)
    arrow(lines, 605, 680, 605, 720)
    arrow(lines, 1240, 680, 1240, 720, color="green")
    box(lines, 35, 150, 265, 170, ["管理主机", "SSH远程连接"], fill="#fff7ed", stroke="#fdba74")
    box(lines, 350, 100, 510, 580, [
        "controller 控制节点",
        "192.168.234.151　ens33",
        "MariaDB　RabbitMQ",
        "Memcached",
        "Keystone　Glance",
        "Placement",
        "Nova控制服务",
        "Neutron控制服务",
        "Cinder控制服务",
        "Swift Proxy",
        "Horizon　Apache",
    ], fill="#eff6ff", stroke="#93c5fd", title=True)
    box(lines, 950, 100, 590, 580, [
        "compute 计算节点",
        "192.168.234.150　ens33",
        "KVM　libvirt",
        "nova-compute",
        "Neutron代理",
        "Cinder：/dev/sdb",
        "Swift：/dev/sdc",
        "ens34：Provider接口",
        "无IP地址",
    ], fill="#f0fdf4", stroke="#86efac", title=True)
    box(lines, 350, 720, 510, 150, ["管理网络", "192.168.234.0/24", "SSH、API与节点通信"], fill="#eff6ff", stroke="#93c5fd")
    box(lines, 950, 720, 590, 150, ["Provider网络", "外部二层网络", "实例外部网络数据"], fill="#f0fdf4", stroke="#86efac")
    save("4.2", lines)

    lines = start_svg("双网卡与网络平面")
    box(lines, 80, 150, 650, 560, ["controller", "ens33：192.168.234.151/24", "ens34：无IP地址"], fill="#f9fafb", stroke="#9ca3af", title=True)
    box(lines, 870, 150, 650, 560, ["compute", "ens33：192.168.234.150/24", "ens34：无IP地址"], fill="#f9fafb", stroke="#9ca3af", title=True)
    lines.append('<rect x="120" y="520" width="1360" height="90" rx="18" fill="#eff6ff" stroke="#93c5fd" stroke-width="3"/><text x="800" y="578" text-anchor="middle">管理网络：SSH、API、数据库、消息与节点通信</text>')
    lines.append('<rect x="120" y="650" width="1360" height="90" rx="18" fill="#f0fdf4" stroke="#86efac" stroke-width="3"/><text x="800" y="708" text-anchor="middle">Provider网络：Neutron接入外部二层网络，承载实例数据</text>')
    arrow(lines, 270, 350, 270, 520)
    arrow(lines, 1030, 350, 1030, 520)
    arrow(lines, 540, 400, 540, 650, color="green")
    arrow(lines, 1300, 400, 1300, 650, color="green")
    save("4.3", lines)

def two_column(number: str, title: str, left_title: str, left_items: list[str], right_title: str, right_items: list[str], footer: str) -> None:
    lines = start_svg(title)
    box(lines, 80, 210, 660, 360, [left_title, *left_items], fill="#eff6ff", stroke="#93c5fd", title=True)
    box(lines, 860, 210, 660, 360, [right_title, *right_items], fill="#f0fdf4", stroke="#86efac", title=True)
    arrow(lines, 740, 320, 860, 320)
    arrow(lines, 860, 500, 740, 500, color="green")
    lines.append(f'<text x="800" y="815" text-anchor="middle" class="sub">{escape(footer)}</text>')
    save(number, lines)


def flow(number: str, title: str, nodes: list[list[str]], footer: str) -> None:
    lines = start_svg(title)
    count = len(nodes)
    gap = 60
    w = int((1460 - (count - 1) * gap) / count)
    positions = [70 + i * (w + gap) for i in range(count)]
    for i in range(count - 1):
        arrow(lines, positions[i] + w, 395, positions[i + 1], 395)
    for i, labels in enumerate(nodes):
        x = positions[i]
        box(lines, x, 245, w, 300, labels, fill="#eff6ff" if i % 2 == 0 else "#f0fdf4", stroke="#93c5fd" if i % 2 == 0 else "#86efac", title=True)
    lines.append(f'<text x="800" y="720" text-anchor="middle" class="sub">{escape(footer)}</text>')
    save(number, lines)


def decision_loop(
    number: str,
    title: str,
    start: list[str],
    first_question: list[str],
    yes_process: list[str],
    no_process: list[str],
    second_question: list[str],
    success: list[str],
    retry: list[str],
    footer: str,
) -> None:
    """Draw a component-specific decision flow with an external feedback loop.

    All connectors are drawn before the modules.  The feedback path stays in the
    bottom corridor, so arrows never cross module text or cover a decision box.
    """

    lines = start_svg(title)
    # Main path and the two branches.  Paths terminate at module edges.
    lines.extend(
        [
            '<path d="M280 390 H300" stroke="#2563eb" stroke-width="5" fill="none" marker-end="url(#blue)"/>',
            '<path d="M430 270 V230 H650" stroke="#16a34a" stroke-width="5" fill="none" marker-end="url(#green)"/>',
            '<path d="M430 510 V600 H650" stroke="#9333ea" stroke-width="5" fill="none" marker-end="url(#purple)"/>',
            '<path d="M950 250 L1110 270" stroke="#16a34a" stroke-width="5" fill="none" marker-end="url(#green)"/>',
            '<path d="M950 600 L1110 510" stroke="#9333ea" stroke-width="5" fill="none" marker-end="url(#purple)"/>',
            '<path d="M1110 270 V230 H1270" stroke="#16a34a" stroke-width="5" fill="none" marker-end="url(#green)"/>',
            '<path d="M1110 510 V600 H1270" stroke="#9333ea" stroke-width="5" fill="none" marker-end="url(#purple)"/>',
            '<path class="feedback-loop" d="M1420 680 V790 H430 V510" stroke="#2563eb" stroke-width="5" stroke-dasharray="14 10" fill="none" marker-end="url(#blue)"/>',
        ]
    )
    lines.extend(
        [
            '<text x="520" y="205" text-anchor="middle" fill="#15803d">是</text>',
            '<text x="520" y="650" text-anchor="middle" fill="#7e22ce">否</text>',
            '<text x="1200" y="205" text-anchor="middle" fill="#15803d">是</text>',
            '<text x="1200" y="650" text-anchor="middle" fill="#7e22ce">否</text>',
        ]
    )

    box(lines, 30, 320, 250, 140, start, fill="#eff6ff", stroke="#93c5fd", title=True)
    lines.append('<polygon class="decision" points="430,270 560,390 430,510 300,390" fill="#fff7ed" stroke="#fdba74" stroke-width="3"/>')
    for index, label in enumerate(first_question):
        lines.append(f'<text x="430" y="{378 + index * 44}" text-anchor="middle">{escape(label)}</text>')
    box(lines, 650, 170, 300, 160, yes_process, fill="#f0fdf4", stroke="#86efac", title=True)
    box(lines, 650, 520, 300, 160, no_process, fill="#faf5ff", stroke="#c4b5fd", title=True)
    lines.append('<polygon class="decision" points="1110,270 1240,390 1110,510 980,390" fill="#fff7ed" stroke="#fdba74" stroke-width="3"/>')
    for index, label in enumerate(second_question):
        lines.append(f'<text x="1110" y="{378 + index * 44}" text-anchor="middle">{escape(label)}</text>')
    box(lines, 1270, 170, 300, 160, success, fill="#f0fdf4", stroke="#86efac", title=True)
    box(lines, 1270, 520, 300, 160, retry, fill="#fef2f2", stroke="#fca5a5", title=True)
    lines.append(f'<text x="800" y="865" text-anchor="middle" class="sub">{escape(footer)}</text>')
    save(number, lines)


def build_chapters5_8() -> None:
    two_column("5.1", "控制面元数据与资源数据", "MariaDB元数据", ["用户、项目与角色", "镜像、实例与网络记录", "卷状态与对象关系"], "资源数据后端", ["镜像文件", "实例磁盘与块数据", "对象存储数据"], "元数据描述对象与关系，后端保存实际资源数据")
    flow("5.2", "OpenStack基础服务协作", [["客户端", "OpenStack命令"], ["API与后台进程", "身份、计算、网络"], ["RabbitMQ", "任务与消息"], ["数据与缓存", "MariaDB", "Memcached"]], "数据库、消息队列、缓存和客户端各自承担不同职责")

    lines = start_svg("Keystone核心对象关系")
    box(lines, 60, 150, 330, 180, ["域", "Default"], fill="#fff7ed", stroke="#fdba74", title=True)
    box(lines, 460, 130, 430, 230, ["身份对象", "用户　组", "项目　角色"], fill="#eff6ff", stroke="#93c5fd", title=True)
    box(lines, 970, 130, 560, 230, ["服务目录", "服务　区域", "公有/内部/管理端点"], fill="#f0fdf4", stroke="#86efac", title=True)
    box(lines, 460, 520, 430, 180, ["角色授权", "身份 + 作用域 + 角色"], fill="#faf5ff", stroke="#c4b5fd", title=True)
    box(lines, 970, 520, 560, 180, ["令牌", "身份 + 作用域 + 角色 + 目录"], fill="#fef2f2", stroke="#fca5a5", title=True)
    arrow(lines, 390, 240, 460, 240)
    arrow(lines, 675, 360, 675, 520, color="purple")
    arrow(lines, 890, 610, 970, 610, color="green")
    arrow(lines, 1250, 360, 1250, 520, color="green")
    save("6.1", lines)
    flow("6.2", "Keystone认证与服务发现", [["OpenStack", "Client", "提交凭据"], ["Keystone", "认证并签发令牌", "返回服务目录"], ["业务服务端点", "Glance　Nova", "Neutron"], ["策略处理", "依据角色与作用域", "执行业务请求"]], "Keystone建立统一身份，业务服务仍负责自己的资源操作")

    lines = start_svg("Glance主要组成")
    box(lines, 60, 250, 310, 230, ["客户端", "Horizon", "命令行客户端", "Nova"], fill="#fff7ed", stroke="#fdba74", title=True)
    box(lines, 500, 200, 430, 330, ["glance-api", "身份与策略", "镜像元数据", "镜像数据传输"], fill="#eff6ff", stroke="#93c5fd", title=True)
    box(lines, 1070, 130, 450, 230, ["MariaDB", "镜像元数据", "状态与属性"], fill="#faf5ff", stroke="#c4b5fd", title=True)
    box(lines, 1070, 500, 450, 230, ["存储后端", "文件系统", "RBD / Swift等"], fill="#f0fdf4", stroke="#86efac", title=True)
    arrow(lines, 370, 365, 500, 365)
    arrow(lines, 930, 300, 1070, 245, color="purple")
    arrow(lines, 930, 430, 1070, 610, color="green")
    save("7.1", lines)
    flow("7.2", "Glance部署与调用顺序", [["数据库与身份", "建库、授权", "服务、端点"], ["配置与同步", "编辑配置", "同步数据库"], ["启动服务", "启用glance-api"], ["镜像请求", "元数据入库", "镜像写入后端"]], "依赖先建立，配置随后写入，数据库同步后再启动服务")

    lines = start_svg("Placement资源模型")
    box(lines, 70, 150, 420, 240, ["资源提供者", "计算节点　设备", "共享存储池"], fill="#eff6ff", stroke="#93c5fd", title=True)
    box(lines, 600, 120, 400, 240, ["资源清单", "资源类别 + 数量", "总量 / 保留 / 超分"], fill="#f0fdf4", stroke="#86efac", title=True)
    box(lines, 1110, 150, 420, 210, ["资源特征", "架构 / 指令集 / 能力"], fill="#fff7ed", stroke="#fdba74", title=True)
    box(lines, 310, 540, 430, 190, ["消费者", "实例或其他占用对象"], fill="#faf5ff", stroke="#c4b5fd", title=True)
    box(lines, 870, 520, 440, 230, ["资源分配", "消费者 + 提供者", "资源类别 + 数量"], fill="#fef2f2", stroke="#fca5a5", title=True)
    arrow(lines, 490, 255, 600, 255)
    arrow(lines, 1000, 255, 1110, 255)
    arrow(lines, 525, 540, 870, 630, color="purple")
    arrow(lines, 1280, 360, 1100, 520, color="green")
    save("8.1", lines)
    flow("8.2", "Nova与Placement调度协作", [["nova-compute", "登记资源提供者", "清单与特征"], ["Nova调度器", "提交资源请求"], ["Placement", "返回分配候选"], ["Nova", "选择目标", "建立资源分配", "创建实例"]], "Placement提供资源事实和候选，Nova完成最终调度与实例生命周期")


def build_chapters9_13() -> None:
    lines = start_svg("Nova双节点组件分布")
    box(lines, 60, 130, 670, 480, ["controller控制节点", "nova-api", "nova-scheduler", "nova-conductor", "nova-novncproxy"], fill="#eff6ff", stroke="#93c5fd", title=True)
    box(lines, 870, 130, 670, 480, ["compute计算节点", "nova-compute", "libvirt", "QEMU / KVM", "实例虚拟机"], fill="#f0fdf4", stroke="#86efac", title=True)
    arrow(lines, 730, 320, 870, 320)
    arrow(lines, 870, 470, 730, 470, color="green")
    box(lines, 170, 680, 1260, 130, ["公共依赖", "Keystone　Glance　Placement　RabbitMQ　MariaDB"], fill="#fff7ed", stroke="#fdba74", title=True)
    arrow(lines, 400, 610, 400, 680, color="purple")
    arrow(lines, 1200, 610, 1200, 680, color="purple")
    save("9.1", lines)
    flow("9.2", "实例创建的主要调用过程", [["用户请求", "镜像、规格、网络"], ["Nova控制服务", "认证与调度"], ["Placement", "资源候选"], ["nova-compute", "调用libvirt", "创建虚拟机"]], "控制面完成认证和调度，计算节点执行虚拟化操作")

    lines = start_svg("Neutron双节点网络拓扑")
    box(lines, 60, 120, 680, 500, ["controller控制节点", "neutron-server", "DHCP代理", "L3代理", "元数据代理", "Linux Bridge代理"], fill="#eff6ff", stroke="#93c5fd", title=True)
    box(lines, 860, 120, 680, 500, ["compute计算节点", "Linux Bridge代理", "实例端口与网桥", "ens33：管理和隧道", "ens34：Provider网络"], fill="#f0fdf4", stroke="#86efac", title=True)
    arrow(lines, 740, 300, 860, 300)
    arrow(lines, 860, 460, 740, 460, color="green", dashed=True)
    box(lines, 100, 690, 600, 120, ["管理与VXLAN网络", "192.168.234.0/24"], fill="#eff6ff", stroke="#93c5fd", title=True)
    box(lines, 900, 690, 600, 120, ["Provider外部网络", "ens34二层接入"], fill="#f0fdf4", stroke="#86efac", title=True)
    arrow(lines, 350, 620, 350, 690)
    arrow(lines, 1250, 620, 1250, 690, color="green")
    save("10.1", lines)
    flow("10.2", "实例访问外部网络的路径", [["实例接口", "安全组"], ["计算节点网桥", "Linux Bridge"], ["虚拟路由器", "路由与地址转换"], ["Provider网络", "外部二层网络"]], "租户网络经虚拟路由器连接Provider网络，flat网络可直接接入外部网络")

    two_column("11.1", "Cinder控制面与数据面", "controller控制面", ["cinder-api", "cinder-scheduler", "数据库与消息"], "compute存储面", ["cinder-volume", "LVM卷组", "LIO目标服务"], "控制请求决定卷对象和后端，实例数据直接访问存储面")
    flow("11.2", "Cinder卷连接过程", [["Nova", "请求卷连接"], ["Cinder", "返回连接信息"], ["计算节点", "建立iSCSI会话"], ["实例", "读写块设备"]], "API负责连接参数，LIO和LVM提供实际块数据")

    lines = start_svg("Swift双节点组件分布")
    box(lines, 80, 150, 640, 430, ["controller控制节点", "代理服务：8080", "Keystone认证", "三类Ring文件"], fill="#eff6ff", stroke="#93c5fd", title=True)
    box(lines, 880, 150, 640, 430, ["compute存储节点", "账户服务：6202", "容器服务：6201", "对象服务：6200", "/dev/sdc：XFS"], fill="#f0fdf4", stroke="#86efac", title=True)
    arrow(lines, 720, 300, 880, 300)
    arrow(lines, 880, 470, 720, 470, color="green")
    box(lines, 300, 670, 1000, 130, ["Ring映射", "区域　节点　端口　设备　分区"], fill="#fff7ed", stroke="#fdba74", title=True)
    arrow(lines, 520, 580, 650, 670, color="purple")
    arrow(lines, 1080, 580, 950, 670, color="purple")
    save("12.1", lines)
    flow("12.2", "Swift对象请求过程", [["客户端", "上传或读取对象"], ["Keystone", "签发访问令牌"], ["代理服务", "依据Ring路由"], ["存储服务", "读写XFS数据"]], "认证决定访问权限，Ring决定后端位置，存储服务保存对象")

    flow("13.1", "Horizon访问OpenStack服务", [["浏览器", "登录与页面操作"], ["Horizon", "Web管理界面"], ["Keystone", "认证与服务目录"], ["业务API", "计算　网络", "镜像　存储"]], "Horizon把页面操作转换为OpenStack API请求")
    flow("13.2", "云平台基础资源创建顺序", [["项目与用户", "角色授权"], ["公共资源", "规格与镜像"], ["网络资源", "子网与路由器"], ["实例", "安全组与密钥对"]], "资源按依赖关系建立，实例同时引用身份、计算、镜像和网络对象")


def build_theory_decision_figures() -> None:
    decision_loop(
        "7.3",
        "镜像导入、状态分支与缓存循环",
        ["镜像请求", "元数据与数据"],
        ["采用可互操作", "导入流程？"],
        ["暂存与导入", "任务处理"],
        ["直接上传", "写入后端"],
        ["处理成功且", "数据完整？"],
        ["镜像 active", "进入可用缓存"],
        ["FAILED", "清理或重试"],
        "导入任务和缓存任务都根据状态继续、重试或清理",
    )
    decision_loop(
        "8.3",
        "分配候选与并发重试",
        ["资源请求", "数量与能力"],
        ["候选集合", "非空？"],
        ["按权重选择", "候选组合"],
        ["调整请求", "或等待资源"],
        ["generation", "仍一致？"],
        ["写入分配", "返回结果"],
        ["HTTP 409", "重新读取"],
        "并发变化会使旧候选失效，调用方重新读取后再限定次数重试",
    )
    decision_loop(
        "9.3",
        "Nova调度与实例构建重试",
        ["实例请求", "镜像与规格"],
        ["主机候选", "非空？"],
        ["尝试首选", "计算节点"],
        ["记录失败", "实例 ERROR"],
        ["资源声明和", "构建成功？"],
        ["实例 ACTIVE", "清空任务状态"],
        ["选择备用", "主机重试"],
        "调度器保存备用主机，单次构建失败后按重试上限继续选择",
    )
    decision_loop(
        "10.3",
        "端口绑定与代理同步",
        ["端口创建", "或状态变更"],
        ["机制驱动", "完成绑定？"],
        ["代理配置", "网桥与安全组"],
        ["标记端口", "绑定失败"],
        ["设备状态", "已确认？"],
        ["端口 ACTIVE", "进入转发"],
        ["保持 DOWN", "重新同步"],
        "控制面保存期望状态，代理循环检查主机实际状态并回报结果",
    )
    decision_loop(
        "11.3",
        "卷调度、连接与状态变化",
        ["卷请求", "创建或连接"],
        ["后端满足", "过滤条件？"],
        ["调度到目标", "存储后端"],
        ["报告无可用", "后端"],
        ["后端操作和", "连接成功？"],
        ["available", "或 in-use"],
        ["清理连接", "恢复或重试"],
        "卷状态由控制面、后端驱动和计算主机共同推进并最终收敛",
    )
    decision_loop(
        "12.3",
        "对象写入与后台修复循环",
        ["对象请求", "写入或读取"],
        ["主节点达到", "法定数量？"],
        ["访问主节点", "保存副本"],
        ["访问 handoff", "临时节点"],
        ["副本与元数据", "一致？"],
        ["请求成功", "返回客户端"],
        ["复制与审计", "后台修复"],
        "前台请求优先保证可用性，后台进程持续把数据恢复到Ring规定位置",
    )
    decision_loop(
        "13.3",
        "Horizon请求与权限判断",
        ["页面请求", "资源与操作"],
        ["令牌与会话", "有效？"],
        ["读取目录", "执行策略判断"],
        ["返回登录页", "重新认证"],
        ["前端与服务端", "策略允许？"],
        ["调用API", "刷新资源状态"],
        ["隐藏操作或", "返回403"],
        "页面权限只是第一层判断，后端服务仍按令牌与资源关系独立授权",
    )


def main() -> None:
    build_chapter4()
    build_chapters5_8()
    build_chapters9_13()
    build_theory_decision_figures()


if __name__ == "__main__":
    main()
