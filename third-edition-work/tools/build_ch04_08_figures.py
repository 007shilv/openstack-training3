"""Generate chapter 4-8 textbook diagrams as editable SVG files.

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
        '<style>text{font-family:"SimSun","宋体",serif;font-size:36px;fill:#111827} .title{font-size:46px;font-weight:700} .sub{font-size:36px;fill:#4b5563} .white{fill:#fff}</style>',
        '<defs><marker id="blue" markerWidth="12" markerHeight="8" refX="11" refY="4" orient="auto"><path d="M0,0 L12,4 L0,8 Z" fill="#2563eb"/></marker><marker id="green" markerWidth="12" markerHeight="8" refX="11" refY="4" orient="auto"><path d="M0,0 L12,4 L0,8 Z" fill="#16a34a"/></marker><marker id="purple" markerWidth="12" markerHeight="8" refX="11" refY="4" orient="auto"><path d="M0,0 L12,4 L0,8 Z" fill="#9333ea"/></marker></defs>',
        '<rect width="1600" height="900" fill="#ffffff"/>',
        f'<text x="800" y="70" text-anchor="middle" class="title">{escape(title)}</text>',
    ]


def box(lines: list[str], x: int, y: int, w: int, h: int, labels: list[str], *, fill: str = "#eff6ff", stroke: str = "#93c5fd", title: bool = False) -> None:
    lines.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="{fill}" stroke="{stroke}" stroke-width="3"/>')
    gap = 46
    first_y = y + h / 2 - (len(labels) - 1) * gap / 2 + 12
    for index, label in enumerate(labels):
        cls = ' class="title"' if title and index == 0 else ""
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

    lines = start_svg("双节点实验环境拓扑")
    box(lines, 70, 150, 350, 190, ["管理主机", "SSH终端", "Xshell / PowerShell"], fill="#fff7ed", stroke="#fdba74")
    box(lines, 540, 125, 440, 260, ["controller", "192.168.234.151", "控制服务与基础服务"], fill="#eff6ff", stroke="#93c5fd", title=True)
    box(lines, 1100, 125, 440, 260, ["compute", "192.168.234.150", "实例与资源代理"], fill="#f0fdf4", stroke="#86efac", title=True)
    box(lines, 540, 525, 440, 190, ["管理网络", "192.168.234.0/24", "ens33"], fill="#eff6ff", stroke="#93c5fd")
    box(lines, 1100, 525, 440, 190, ["Provider网络", "外部二层网络", "ens34（无IP）"], fill="#f0fdf4", stroke="#86efac")
    arrow(lines, 420, 230, 540, 230)
    arrow(lines, 980, 250, 1100, 250)
    arrow(lines, 760, 385, 760, 525)
    arrow(lines, 1320, 385, 1320, 525, color="green")
    lines.append('<text x="70" y="805" class="sub">蓝色：管理与控制通信　　绿色：实例外部网络数据</text>')
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

    lines = start_svg("控制节点与计算节点组件分布")
    box(lines, 70, 120, 690, 650, ["controller 控制节点", "MariaDB　RabbitMQ　Memcached", "Keystone　Glance　Placement", "Nova控制服务　Neutron控制服务", "Cinder API/Scheduler　Swift Proxy", "Horizon　Apache"], fill="#eff6ff", stroke="#93c5fd", title=True)
    box(lines, 840, 120, 690, 650, ["compute 计算节点", "KVM　libvirt　nova-compute", "Neutron Linux Bridge代理", "Cinder Volume（/dev/sdb）", "Swift存储服务（/dev/sdc）", "实例与虚拟网络"], fill="#f0fdf4", stroke="#86efac", title=True)
    arrow(lines, 760, 300, 840, 300)
    arrow(lines, 840, 430, 760, 430, color="purple")
    lines.append('<text x="800" y="835" text-anchor="middle" class="sub">控制节点保存状态并作出决策；计算节点报告资源并执行任务</text>')
    save("4.4", lines)


def two_column(number: str, title: str, left_title: str, left_items: list[str], right_title: str, right_items: list[str], footer: str) -> None:
    lines = start_svg(title)
    box(lines, 80, 150, 660, 560, [left_title, *left_items], fill="#eff6ff", stroke="#93c5fd", title=True)
    box(lines, 860, 150, 660, 560, [right_title, *right_items], fill="#f0fdf4", stroke="#86efac", title=True)
    arrow(lines, 740, 330, 860, 330)
    arrow(lines, 860, 500, 740, 500, color="green")
    lines.append(f'<text x="800" y="815" text-anchor="middle" class="sub">{escape(footer)}</text>')
    save(number, lines)


def flow(number: str, title: str, nodes: list[list[str]], footer: str) -> None:
    lines = start_svg(title)
    count = len(nodes)
    gap = 35
    w = int((1460 - (count - 1) * gap) / count)
    for i, labels in enumerate(nodes):
        x = 70 + i * (w + gap)
        box(lines, x, 245, w, 300, labels, fill="#eff6ff" if i % 2 == 0 else "#f0fdf4", stroke="#93c5fd" if i % 2 == 0 else "#86efac", title=True)
        if i < count - 1:
            arrow(lines, x + w, 395, x + w + gap, 395)
    lines.append(f'<text x="800" y="720" text-anchor="middle" class="sub">{escape(footer)}</text>')
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
    flow("6.2", "Keystone认证与服务发现", [["OpenStackClient", "提交凭据"], ["Keystone", "认证并签发令牌", "返回服务目录"], ["业务服务端点", "Glance / Nova / Neutron"], ["策略处理", "依据角色与作用域", "执行业务请求"]], "Keystone建立统一身份，业务服务仍负责自己的资源操作")

    lines = start_svg("Glance主要组成")
    box(lines, 60, 250, 310, 230, ["客户端", "Horizon", "OpenStackClient", "Nova"], fill="#fff7ed", stroke="#fdba74", title=True)
    box(lines, 500, 200, 430, 330, ["glance-api", "身份与策略", "镜像元数据", "镜像数据传输"], fill="#eff6ff", stroke="#93c5fd", title=True)
    box(lines, 1070, 130, 450, 230, ["MariaDB", "镜像元数据", "状态与属性"], fill="#faf5ff", stroke="#c4b5fd", title=True)
    box(lines, 1070, 500, 450, 230, ["存储后端", "文件系统", "RBD / Swift等"], fill="#f0fdf4", stroke="#86efac", title=True)
    arrow(lines, 370, 365, 500, 365)
    arrow(lines, 930, 300, 1070, 245, color="purple")
    arrow(lines, 930, 430, 1070, 610, color="green")
    save("7.1", lines)
    flow("7.2", "Glance部署与调用顺序", [["数据库与身份", "建库、用户、服务、端点"], ["配置与同步", "glance-api.conf", "glance-manage db_sync"], ["服务启动", "openstack-glance-api"], ["镜像请求", "元数据写数据库", "数据写后端"]], "依赖先建立，配置随后写入，数据库同步后再启动服务")

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
    flow("8.2", "Nova与Placement调度协作", [["nova-compute", "登记资源提供者", "清单与特征"], ["Nova Scheduler", "提交实例资源请求"], ["Placement", "返回分配候选"], ["Nova", "选择目标并建立分配", "交给计算节点创建实例"]], "Placement提供资源事实和候选，Nova完成最终调度与实例生命周期")


def main() -> None:
    build_chapter4()
    build_chapters5_8()


if __name__ == "__main__":
    main()
