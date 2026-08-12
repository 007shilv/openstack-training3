# 13 Swift 计算节点手工部署

`16-compute-swift.sh` 仅作参数/顺序参考，严禁执行。Swift 只能使用 compute `192.168.234.150` 的 `/dev/sdc`；绝不触碰系统盘 `/dev/sda` 或 Cinder PV `/dev/sdb`。

安装仅限本地源的 `openstack-swift`、account/container/object、`rsync` 和 `xfsprogs`。写入前需逐项确认：`/dev/sdc` 是精确 50 GiB 整盘、非根盘祖先、无分区/挂载/签名/PV，且 `/dev/sdb` 唯一属于 `cinder-volumes`。

本机 XFS 的卷标上限为 12 字符；原计划的 20 字符标签在写入前被 XFS 拒绝，因此经授权采用精确标签 `swift-data`。仅在空白分支由人工确认 `YES` 后运行：

```bash
mkfs.xfs -f -L swift-data /dev/sdc
uuid=$(blkid -s UUID -o value /dev/sdc)
vi /etc/fstab # UUID=<运行时UUID> /srv/node/sdc xfs defaults,noatime,nodiratime 0 0
mkdir -p /srv/node/sdc
mount /srv/node/sdc
chown -R swift:swift /srv/node /var/cache/swift
```

已初始化分支只接受 `/dev/sdc` 的 XFS 类型、`swift-data` 精确标签、UUID fstab 条目及 `/srv/node/sdc` 精确挂载；任何第三状态均停止。手工编辑 `/etc/rsyncd.conf` 和 account/container/object 三个服务配置，`devices = /srv/node`、端口依次 6202/6201/6200、地址为 `.150`。复制并核验 controller 的 `swift.conf` 和三份 ring 后执行：

```bash
systemctl enable --now rsyncd
systemctl enable --now openstack-swift-account openstack-swift-container openstack-swift-object
```

最后在 controller 以认证 CLI 创建一个唯一容器和小对象、下载后仅在内存中比对摘要、按创建时的精确名称删除对象和容器并确认无残留。不得创建快照或保留测试对象。

## Focused Swift contract（只用于验收，不是安装入口）

```python
def validate_swift_lightweight_evidence(evidence: dict[str, object]) -> None:
    expected = {
        "controller": {"openstack-swift-proxy"},
        "compute": {"rsyncd", "openstack-swift-account", "openstack-swift-container", "openstack-swift-object"},
    }
    if evidence.get("services") != expected:
        raise ValueError("Swift service evidence mismatch")
    if evidence.get("rings") != {"replicas": 1, "ip": "192.168.234.150", "device": "sdc"}:
        raise ValueError("Swift ring evidence mismatch")
    if evidence.get("disk") != {"device": "/dev/sdc", "filesystem": "xfs", "label": "swift-data", "mounted": True, "cinder_untouched": True}:
        raise ValueError("Swift disk evidence mismatch")
    if evidence.get("lifecycle") != {"api": True, "authenticated_cli": True, "one_object": True, "digest_matches": True, "deleted_exactly": True, "no_residue": True}:
        raise ValueError("Swift lifecycle evidence mismatch")
```
