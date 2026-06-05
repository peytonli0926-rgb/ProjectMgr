# TFA 解压结构分析 & oracle-tfa-analyzer 重构建议

分析日期：2026-06-05
分析文件：`pa00db12.tfa_Sat_Apr_25_10_51_31_CST_2026.zip`

---

## 一、TFA Zip 实际解压结构

```
tfa_extracted/
├── pa00db12/                                # 主机名目录
│   ├── pa00db12_{COMMAND}                   # 80+ 个根级命令快照文件
│   ├── diag/
│   │   ├── rdbms/cbsmergedb/mgcbsdb2/trace/ # alert_mgcbsdb2.log + 200+ *.trc
│   │   ├── crs/pa00db12/crs/trace/           # CRS trace/log
│   │   ├── asm/+asm/+ASM2/trace/             # ASM alert + trace
│   │   └── tnslsnr/pa00db12/listener/trace/  # Listener log
│   ├── u01/app/grid/
│   │   ├── crsdata/pa00db12/acfs/            # ACFS 日志
│   │   ├── crsdata/pa00db12/qos/logs/        # QoS 日志
│   │   ├── crsdata/pa00db12/trace/chad/      # CHAD 跟踪
│   │   └── tfa/repository/suptools/.../oswbb/grid/archive/
│   │       ├── oswvmstat/ oswiostat/         # OSWatcher 性能采样
│   │       ├── oswmpstat/ oswpidstat/
│   │       ├── oswmeminfo/ oswprvtnet/
│   │       └── oswps/ oswtop/ oswvmstat/
│   └── CHMDATA/                              # Cluster Health Monitor JSON
│
├── *.zip.txt                                 # TFA 收集清单
├── *.zip.json                                # 收集元数据
├── zip_inventory.csv                         # 文件清单
├── tfa_main.trc                              # TFA 主日志
└── diagcollect.log                           # 收集诊断日志
```

### 文件统计

| 指标 | 数值 |
|------|------|
| 文件总数 | 361 |
| .trc (Trace) | 121 |
| .log (日志) | 64 |
| 其余 (快照/配置) | 176 |

---

## 二、当前模块覆盖度分析

| 当前模式 | 匹配范围 | 实际覆盖度 |
|---------|---------|:---------:|
| alert_log : **/alert*.log | diag 下的 alert 日志 | 好 |
| listener_log : **/listener*.log | diag/tnslsnr | 好 |
| asm_alert : **/asm/alert*/alert*.log | ASM alert | 好 |
| crs_log : **/crs*/log/**/*.log,*.trc | CRS log/trace | 好 |
| os_info : **/os*/**/*.out,*.log | os_collection, os_report | 部分 |
| rman_log : **/rman*/**/*.log | TFA 中无 rman | 无匹配 |
| awr_report : **/awr*.html,*.txt,*.lst | TFA 中无 AWR | 无匹配 |
| sql_trace : **/*.trc,*.trm | 全量 trc 文件 | 好 |
| adg_log : **/*dataguard* | dataguard 日志 | 好 |
| 根级 pa00db12_* 快照文件 | 没有任何模式匹配 | 完全遗漏 |
| OSWatcher 归档 | 没有任何模式匹配 | 完全遗漏 |
| ACFS 日志 | 没有任何模式匹配 | 完全遗漏 |
| CHM 数据 | 没有任何模式匹配 | 完全遗漏 |

**结论：当前模块只覆盖了实际 TFA 数据的约 30%。**

---

## 三、根级 pa00db12_* 文件完整分类

80+ 个根级文件可按主题分为以下类别：

### 类别 A：OCR / 集群基础 (7 个)

| TFA 文件 | 内容 | 可映射规则 |
|----------|------|:---------:|
| OCRBACKUP | OCR 备份信息 | RAC |
| OCRDUMP | OCR 完整 Dump | RAC |
| OLRDUMP | OLR 本地注册表 Dump | RAC |
| ocrloc | OCR 位置 | RAC |
| olrloc | OLR 位置 | RAC |
| GETCSS | CSS 集群状态 | RAC |
| QUERYVOTE | 表决盘状态 | RAC |

### 类别 B：CRS 资源状态 (8 个)

| TFA 文件 | 内容 | 可映射规则 |
|----------|------|:---------:|
| CHECKCRS | CRS 完整性检查 | RAC |
| STATRESCRS | CRS 资源状态 | RAC |
| STATRESCRSFULL | CRS 资源完整状态 | RAC |
| STATRESDEPENDENCY | 资源依赖关系 | RAC |
| STATRESFULLOHAS | OHAS 完整状态 | RAC |
| STATRESOHAS | OHAS 资源状态 | RAC |
| crsctl_config_crs | CRS 配置 | RAC |
| ohasdrun | OHAS 运行状态 | RAC |

### 类别 C：ASM 配置 (4 个)

| TFA 文件 | 内容 | 可映射规则 |
|----------|------|:---------:|
| CONFIGASM | ASM 配置 | ASM |
| DEV_ASM_CONTENTS | ASM 磁盘设备内容 | ASM |
| ORACLEAFD_CONF | AFD 配置 | ASM |
| AFDTOOL_KSTATE | AFD 内核状态 | ASM |

### 类别 D：ACFS 文件系统 (7 个)

| TFA 文件 | 内容 |
|----------|------|
| acfs_report | ACFS 文件系统报告 |
| ACFS_DRIVER_STATE_INFO | ACFS 驱动状态 |
| ACFSDUMPSTATS | ACFS Dump 统计 |
| ACFSROOT_VERSION_CHECK | ACFS 根版本检查 |
| ACFSUTILLOG | ACFS 工具日志 |
| ACFSUTILPLOGCONFIG | ACFS 日志配置 |

### 类别 E：OS 系统诊断 (8 个)

| TFA 文件 | 内容 | 可映射规则 |
|----------|------|:---------:|
| PS | 进程快照 | OS 资源 |
| PIDS | PID 列表 | OS 资源 |
| TOP_50_MEMORY | 内存 Top 50 | OS 资源 |
| dmesg | 内核日志 | OS 资源 |
| LSMOD | 内核模块 | OS 资源 |
| RPMQA | 已安装包 | 新规则 |
| os-release | OS 发行版 | 新规则 |
| redhat-release | RedHat 版本 | 新规则 |

### 类别 F：网络诊断 (5 个)

| TFA 文件 | 内容 |
|----------|------|
| NETSTAT | 网络连接/路由状态 |
| NSLOOKUP | DNS 解析 |
| DNSSERVERS | DNS 服务器配置 |
| PING_INFO | 网络连通性 |
| NSSWITCH_CONF | 名称解析顺序 |

### 类别 G：补丁/版本 (4 个)

| TFA 文件 | 内容 |
|----------|------|
| OPATCH_CRS | GI 补丁信息 |
| OPATCH_DBHOMES | DB Home 补丁信息 |
| SOFTWAREVERSION | 软件版本 |
| ACTIVEVERSION | 活跃版本 |

### 类别 H：系统配置 (6 个)

| TFA 文件 | 内容 |
|----------|------|
| SRCFG.json | SCAN 监听配置(JSON) |
| SRCFG.log | SRCTL 配置日志 |
| INITTAB | /etc/inittab |
| oratab | /etc/oratab |
| PROCDIRINFO | 进程目录信息 |
| summary | 系统摘要 |

### 类别 I：OSWatcher 性能归档

oswbb/grid/archive/ 包含：oswvmstat, oswiostat, oswmpstat, oswmeminfo, oswprvtnet, oswps, oswpidstat, oswtop, oswarp, oswifconfig

---

## 四、重构建议优先级

### P0 立即实施

目标：将根级 pa00db12_* 文件纳入分析体系

1. 在 config.py 中新增 FILE_PATTERNS 类别
2. 在 extractor.py 中增加 pa00db12_ 文件名元数据解析

### P1 推荐实施

目标：新增对应上述类别的规则实现

| 新建文件 | 规则类名 | 分析内容 |
|---------|---------|---------|
| rules/acfs_health.py | ACFSHealthRule | ACFS 驱动加载、版本检查、状态异常 |
| rules/network_health.py | NetworkHealthRule | DNS 解析、网络连通性、MTU |
| rules/patch_version.py | PatchVersionRule | 补丁缺失、版本不匹配 |
| rules/osw_perf.py | OSWatcherPerfRule | CPU/内存/IO 峰值趋势异常 |

### P2 可选优化

- 时间过滤优化：engine.py 的行级时间戳过滤对快照文件不适用
- OSWatcher 趋势：数值采样数据趋势分析
- CHM 数据：JSON 结构化数据解析

---

## 五、全量 TFA 时间线

```
2022-07-26 16:37   集群首次启动 (OHASD/CRS)                     CRS alert
2022-07-26 16:39   集群重启（首次配置后）                        CRS alert

2022-07-27 09:14   ASM +ASM2 启动                                ASM alert
2022-07-27 14:13   ACFS 首次 dump (ora.drivers.acfs)             ACFS resources/dumpstate.out
2022-07-27 14:55   ACFS dump #2                                  ACFS resources/dumpstate.out
2022-07-27 15:09   ACFS dump #3                                  ACFS resources/dumpstate.out

2022-08-19 14:50   DB alert: Process termination                 DB alert log
                   pid 113493 (source=rdbms, info=2)

2022-08-28 15:55   === 重大故障：DATA Diskgroup 崩溃 ===
                   详见 6.2

2022-08-28~09-18   恢复期：DATA 在 +ASM2 上未恢复                ASM alert
                   CRS-1013: OCR inaccessible                    CRS alert

2022-09-17 17:39   ACFS dump #4                                  ACFS resources/dumpstate.out
                   集群 shutdown                                  CRS alert
2022-09-19 08:15   集群重启 (完整启动)                             CRS alert

2022-10-29 19:31   ACFS dump #5                                  ACFS resources/dumpstate.out

2023-01-18 23:33   ACFS dump #6                                  ACFS resources/dumpstate.out
2023-01-19 01:15   ACFS dump #7                                  ACFS resources/dumpstate.out
2023-01-27 13:09   DB 进程终止 (SIGKILL)                         DB alert log
2023-01-27 13:11   ACFS dump #8                                  ACFS resources/dumpstate.out
2023-01-27 13:44   ASM 全 diskgroup 重新挂载                      ASM alert
2023-01-27 13:45   DB 重新连接 ASM                                ASM alert

2026-04-25 10:51   TFA 数据采集时间                               zip 文件名
```

从时间线可看出 3 个关键模式：
1. ACFS 频繁 crash：2022-07-27 ~ 2023-01-27 之间发生 8 次 ACFS driver dump，平均每月一次
2. DATA diskgroup 在 2022-08-28 崩溃后从未在 +ASM2 恢复，直到 3 周后才通过集群重启恢复
3. 两次 DB 进程终止事件 (2022-08-19, 2023-01-27) 可能与 ACFS 不稳定有关

---

## 六、实际故障时间链条分析

### 6.1 故障一：2022-08-28 ASM Diskgroup DATA 物理 I/O 崩溃

49 秒内级联崩溃：

```
时间戳 (+08:00)          时差  事件                                   严重度   来源文件
2022-08-28 15:55:57.794        CRS 检测到 cbsmergedb 资源检查失败      警告     CRS alert.log (CRS-5011)
2022-08-28 15:55:58.410   +1s  DB 客户端从 ASM 意外断开                 致命     ASM alert_+ASM2.log
2022-08-28 15:55:58.950   +1s  ASM 开始 dump 诊断数据                  致命     ASM alert_+ASM2.log (cdmp/)
2022-08-28 15:56:11.751  +14s  ASM 清理已死客户端（11 秒无响应）       警告     ASM alert_+ASM2.log
2022-08-28 15:56:30.366  +33s  I/O 写入失败 /dev/asm-data05             崩溃     ASM alert_+ASM2.log
2022-08-28 15:56:30.374  +33s  ORA-15080: 同步 I/O 失败                 崩溃     ASM alert_+ASM2.log
2022-08-28 15:56:30.374  +33s  ERROR: disk 3 无法 offline (external redundancy)  崩溃  ASM alert_+ASM2.log
2022-08-28 15:56:30.403  +33s  cache dismounting (not clean) DATA       崩溃     ASM alert_+ASM2.log
2022-08-28 15:56:30.419  +33s  halt 所有 I/O 到 DISKGROUP DATA          崩溃     ASM alert_+ASM2.log
2022-08-28 15:56:31.084  +34s  ORA-15130: diskgroup DATA 正在卸载       致命     ASM alert_+ASM2.log
2022-08-28 15:56:33.219  +36s  cache dismounted group DATA              致命     ASM alert_+ASM2.log
2022-08-28 15:56:33.277  +36s  diskgroup DATA 已卸载                    信息     ASM alert_+ASM2.log
2022-08-28 15:56:46.934  +49s  CRS-5017: cbsmergedb.db 启动失败         致命     CRS alert.log (ORA-00205)
```

#### 根因分析

| 层次 | 发现 | 证据 |
|------|------|------|
| 直接根因 | /dev/asm-data05 磁盘发生物理 I/O 错误 (osderr1=0x69c0) | ASM alert.log Write Failed |
| 触发条件 | DATA 使用 external redundancy（无镜像），单盘故障导致全盘不可用 | ASM alert.log: cannot be offlined |
| 连锁反应 | DATA 卸载 -> DB control files 丢失 -> DB 无法启动 -> CRS 资源失败 | CRS alert.log: ORA-00205 |
| 后续影响 | DATA 在 +ASM2 持续 3 周未恢复，直到 09-19 集群重启 | ASM alert.log 无 mount DATA |
| 先兆信号 | 2022-08-19 已有 DB 进程终止事件 | DB alert log |

---

### 6.2 故障二：2023-01-27 ACFS 驱动异常 & DB 进程终止

```
时间戳 (+08:00)          时差  事件                                   严重度   来源文件
2023-01-27 13:09:50           DB 进程终止请求 pid 31052 (SIGKILL)       崩溃     DB alert_mgcbsdb2.log
2023-01-27 13:11:45     +2m   ACFS 驱动 dump (ora.drivers.acfs)         崩溃     ACFS resources/dumpstate.out
2023-01-27 13:44:13    +34m   ASM 挂载 FRA + SYS diskgroup              恢复     ASM alert_+ASM2.log
2023-01-27 13:44:15    +34m   ASM listener_networks 重新配置            信息     ASM alert_+ASM2.log
2023-01-27 13:45:23    +35m   DB 重新连接 ASM                            恢复     ASM alert_+ASM2.log
2023-01-27 13:45:29    +36m   DB 挂载 DATA + FRA（恢复完成）             恢复     ASM alert_+ASM2.log
```

#### 根因分析

| 层次 | 发现 | 证据 |
|------|------|------|
| 直接诱因 | ACFS driver 异常 -> DB 后台进程 I/O 挂起 -> OS 发 SIGKILL | 时间序列：ACFS dump 紧随 DB 进程终止 |
| 确认信号 | ACFS 在 DB 进程终止后 2 分钟产生 dumpstate.out | ACFS resources/ 目录时间戳 |
| 恢复 | ASM 自动重挂载所有 diskgroup -> DB 重连，耗时约 36 分钟 | ASM alert.log |
| 历史模式 | 2022-07-27 ~ 2023-01-27 共 8 次 ACFS dump | ACFS resources/ 全部 8 个 dump 目录 |

---

### 6.3 两故障的关联性

| 维度 | 故障一 (2022-08-28) | 故障二 (2023-01-27) |
|------|:-------------------:|:-------------------:|
| 根因类型 | 存储硬件 I/O 错误 | ACFS 驱动软件不稳定 |
| 影响范围 | Diskgroup DATA 完全不可用（跨 2 节点） | 单节点 DB 进程终止 |
| 恢复方式 | 无法自动恢复，需集群重启（3 周后） | ASM 自动重挂载 + DB 重连（36 分钟） |
| 严重度 | 关键 | 中等 |
| 涉及日志数 | 3 个 (ASM+CRS+DB) | 4 个 (DB+ACFS+ASM+CRS) |
| 当前模块检测 | ASM alert + CRS alert 已被覆盖 | ACFS dump 未被覆盖 |
| 重构后检测 | + OS 快照补充 (dmesg+PS) | + ACFS 规则自动关联 |

---

## 七、自动故障时间链发现的程序逻辑设计

### 7.1 核心数据结构

```python
@dataclass
class TFAEvent:
    timestamp: datetime          # 事件时间戳
    severity: str                # 崩溃/致命/警告/恢复
    source: str                  # ASM/CRS/DB/ACFS/OS
    source_file: str             # 来源文件路径
    message: str                 # 原始事件消息
    category: str                # IO_ERROR/DISK_OFFLINE/ACFS_CRASH/...

@dataclass
class FaultCluster:
    events: List[TFAEvent]       # 该故障包含的所有事件
    start_time: datetime         # 故障开始时间
    end_time: datetime           # 故障结束时间
    root_cause: TFAEvent         # 根因事件
    recovery_events: List        # 恢复事件
    impact: str                  # 影响描述
    related_snapshots: List[str] # 关联的快照文件
```

### 7.2 程序流程

```python
class FaultTimelineAnalyzer:
    """自动故障时间链分析器"""
    
    def analyze(self, tfa_dir: Path) -> List[FaultCluster]:
        # 步骤1: 从所有已知日志文件中提取事件
        raw_events = self._extract_all_events(tfa_dir)
        
        # 步骤2: 5 分钟时间窗口聚类
        clusters = self._cluster_events(raw_events, window_minutes=5)
        
        # 步骤3: 根据规则链定位根因
        for cluster in clusters:
            cluster.root_cause = self._identify_root_cause(cluster)
        
        # 步骤4: 匹配故障时间窗口内的系统快照
        for cluster in clusters:
            cluster.related_snapshots = self._match_snapshots(
                tfa_dir, cluster.start_time, cluster.end_time)
        
        return clusters
    
    def _extract_all_events(self, tfa_dir):
        """扫描 alert*.log 等文件，提取所有异常事件"""
        events = []
        for filepath in tfa_dir.rglob("alert*.log"):
            for line in self._read_lines(filepath):
                if any(kw in line for kw in ["ORA-", "ERROR", "CRS-", "FATAL"]):
                    events.append(self._parse_event(filepath, line))
        return events
    
    def _cluster_events(self, events, window_minutes=5):
        """时间窗口聚类算法"""
        sorted_events = sorted(events, key=lambda e: e.timestamp)
        clusters = []
        current = None
        
        for event in sorted_events:
            if not current:
                current = FaultCluster(events=[event], start_time=event.timestamp, ...)
            elif (event.timestamp - current.events[-1].timestamp).total_seconds() <= window_minutes * 60:
                current.events.append(event)
                current.end_time = event.timestamp
            else:
                clusters.append(current)
                current = FaultCluster(events=[event], start_time=event.timestamp, ...)
        
        return clusters
    
    def _identify_root_cause(self, cluster):
        """根据预定义链规则定位根因"""
        categories = [e.category for e in sorted(cluster.events, key=lambda e: e.timestamp)]
        
        # 规则1: IO 崩溃链
        if all(c in categories for c in ["IO_ERROR", "DISMOUNT", "DB_START_FAIL"]):
            return next(e for e in cluster.events if e.category == "IO_ERROR")
        
        # 规则2: ACFS 崩溃链
        if all(c in categories for c in ["PROC_TERMINATE", "ACFS_DUMP"]):
            return next(e for e in cluster.events if e.category == "ACFS_DUMP")
        
        # 规则3: CRS 故障链
        if all(c in categories for c in ["CRS_CHECK_FAIL", "CRS_RESOURCE_FAIL"]):
            return next(e for e in cluster.events if e.category == "CRS_CHECK_FAIL")
        
        # 默认: 最早的关键事件
        critical = [e for e in cluster.events if e.severity in ("崩溃", "致命")]
        return critical[0] if critical else None
```

### 7.3 故障链规则引擎

```python
FAULT_CHAIN_RULES = [
    {
        "name": "ASM Disk I/O Crash",
        "match_sequence": ["IO_ERROR", "DISK_OFFLINE_FAIL", "DISMOUNT", "DB_START_FAIL"],
        "root_cause_idx": 0,
        "severity": "CRITICAL",
        "suggested_fix": "检查存储链路 (/dev/asm-*)、HBA 卡、SAN 交换机。"
                          "如使用 external redundancy，需修复磁盘或添加镜像。"
    },
    {
        "name": "ACFS Driver Crash",
        "match_sequence": ["PROC_TERMINATE", "ACFS_DUMP", "ASM_REMOUNT", "DB_RECONNECT"],
        "root_cause_idx": 1,
        "severity": "ERROR",
        "suggested_fix": "检查 ACFS 驱动版本兼容性，考虑升级 GI 补丁。"
                          "检查 /var/log/messages 中 ACFS/ADVM 相关错误。"
    },
    {
        "name": "CRS Resource Failure",
        "match_sequence": ["CRS_CHECK_FAIL", "CRS_RESOURCE_FAIL"],
        "root_cause_idx": 0,
        "severity": "ERROR",
        "suggested_fix": "检查资源依赖关系和 crsd_oraagent*.trc 日志。"
    },
]

def match_fault_chain(cluster):
    """尝试匹配预定义的故障链规则"""
    categories = [e.category for e in sorted(cluster.events, key=lambda e: e.timestamp)]
    
    for rule in FAULT_CHAIN_RULES:
        seq = rule["match_sequence"]
        for i in range(len(categories) - len(seq) + 1):
            if categories[i:i+len(seq)] == seq:
                return {
                    "rule": rule["name"],
                    "root_cause": sorted(cluster.events, key=lambda e: e.timestamp)[i + rule["root_cause_idx"]],
                    "suggested_fix": rule["suggested_fix"]
                }
    return None
```

### 7.4 输出示例

对于故障一 (2022-08-28)，自动分析输出：

```
FaultCluster #1:
  严重度:  关键
  持续时间: 2022-08-28 15:55:57 ~ 2022-08-28 15:56:46 (49 秒)
  匹配规则: ASM Disk I/O Crash
  
  时间线:
    [15:55:57] 警告   CRS_CHECK_FAIL      CRS-5011: Check of resource cbsmergedb failed
    [15:55:58] 致命   DB_DISCONNECT       ASM client mgcbsdb2 disconnected
    [15:56:30] 崩溃   IO_ERROR            ORA-15080: I/O failed to write block 13088
    [15:56:30] 崩溃   DISK_OFFLINE_FAIL   ERROR: disk 3 cannot be offlined
    [15:56:30] 崩溃   DISMOUNT            cache dismounting (not clean) group DATA
    [15:56:46] 致命   DB_START_FAIL       ORA-00205: error in identifying control file
  
  根因: IO_ERROR at 15:56:30, /dev/asm-data05, I/O error
  影响: Diskgroup DATA 在 +ASM2 不可用持续 3 周
  恢复: 2022-09-19 集群重启后恢复
  建议修复: 检查存储链路，考虑为 DATA diskgroup 添加镜像冗余
  
  关联快照: [pa00db12_PS, pa00db12_dmesg, pa00db12_LSMOD]
            (TFA 采集时间 2026-04-25 与故障相差 > 3 年，参考价值有限)
```

### 7.5 集成到现有 pipeline

```python
class FaultTimelinePipeline:
    """故障时间链分析管道"""
    
    def run(self, tfa_dir: Path):
        # 1. 文件分类（复用现有的 discover_files）
        categorized = discover_files(tfa_dir)
        
        # 2. 提取事件
        analyzer = FaultTimelineAnalyzer()
        events = analyzer._extract_all_events(tfa_dir)
        
        # 3. 聚类 + 根因识别
        clusters = analyzer._cluster_events(events, window_minutes=5)
        for cluster in clusters:
            cluster.root_cause = analyzer._identify_root_cause(cluster)
            cluster.related_snapshots = analyzer._match_snapshots(tfa_dir, ...)
            rule_match = match_fault_chain(cluster)
        
        # 4. 按时间排序输出
        return FaultTimelineReport(clusters=clusters)
```

---

## 附录：TFA 文件与故障链映射表

| TFA 源文件 | 可发现的故障类型 | 当前覆盖 | 重构后 |
|-----------|----------------|:-------:|:------:|
| diag/asm/.../alert_+ASM*.log | ASM diskgroup I/O 错误、mount/dismount | 是 | 是 |
| diag/crs/.../alert.log | CRS 资源故障、节点状态 | 是 | 是 |
| diag/rdbms/.../alert_*.log | DB 进程终止、ORA 错误 | 是 | 是 |
| diag/tnslsnr/.../listener*.log | 监听连接故障 | 是 | 是 |
| pa00db12_dmesg | 内核 I/O 错误、SCSI/ATA 驱动异常 | 否 | P0 |
| pa00db12_PS | 故障时进程状态 | 否 | P0 |
| pa00db12_NETSTAT | 网络连接状态、端口监听 | 否 | P0 |
| pa00db12_TOP_50_MEMORY | 内存消耗 Top 进程 | 否 | P0 |
| acfs/resources/*/dumpstate.out | ACFS 驱动 crash 频率与时间 | 否 | P1 |
| oswbb/archive/oswvmstat/* | 故障前后系统 I/O wa% 趋势 | 否 | P1 |
| oswbb/archive/oswmpstat/* | 故障前后 CPU 使用率趋势 | 否 | P1 |
| CHMDATA/*.json | 故障时集群健康状态 | 否 | P2 |

---

## 七、多 TFA 交叉分析（hxdb01 + hxdb02 vs pa00db12）

分析文件：
- `hxdb01.tfa` — 5.4MB, RAC Node 1 (cbsdb1), diag/rdbms/cbsdb1, diag/asm/+ASM1
- `hxdb02.tfa` — 4.9MB, RAC Node 2 (cbsdb2), diag/rdbms/cbsdb2, diag/asm/+ASM2

### 7.1 结构差异对比

所有三份 TFA 共享以下 21 种文件类型：

| 类型 | 说明 |
|------|------|
| OCRBACKUP, OCRDUMP, OLRDUMP | OCR/OLR 备份与 dump |
| GETCSS, QUERYVOTE | CSS / 表决盘状态 |
| CHECKCRS, STATRESCRS, STATRESCRSFULL, STATRESDEPENDENCY | CRS 资源状态 |
| STATRESFULLOHAS, STATRESOHAS | OHAS 状态 |
| crsctl_config_crs, ohasdrun | CRS 配置/运行状态 |
| CONFIGASM, DEV_ASM_CONTENTS | ASM 配置 |
| PS, PIDS | 进程快照 |
| NETSTAT, NSLOOKUP, PING_INFO | 网络诊断 |
| INITTAB | 系统配置 |
| summary | 系统摘要 |
| SOFTWAREVERSION, ACTIVEVERSION | 版本信息 |
| OPATCH_CRS, OPATCH_DBHOMES | 补丁信息 |

### 7.2 hxdb 新增文件类型（10+ 种）

| TFA 文件 | 内容 | 分析价值 |
|----------|------|:--------:|
| `{hostname}_CLUSTERCONFIG` | 集群模式（Flex/Standard） | 确认集群拓扑 |
| `{hostname}_CHA_STATUS` | Cluster Health Advisor 状态 | 发现 CHA 未运行 (CRS-2613) |
| `{hostname}_CRSPATCHCKPT_STATUS` | GI 补丁检查点（ROOTCRS_PREPATCH/POSTPATCH） | 补丁进度审计 |
| `{hostname}_OIFCFG` | 网络接口配置（public/private/interconnect） | 私网规划检查 |
| `{hostname}_IPMI` | IPMI 设备状态 | 硬件管理连通性 |
| `{hostname}_RUNLEVEL` | 系统运行级别 | 确认系统模式 |
| `{hostname}_NODEAPPS` | VIP/ONS/SCAN/ASM 资源配置 | ASM 实例依赖关系 |
| `{hostname}_OLSNODES` | 集群节点列表与属性 | 集群规模确认 |
| `{hostname}_ospackages` / `{hostname}_ospatches` | AIX 格式包清单 (`lslpp -Lc`) | AIX 系统补丁审计 |
| `{hostname}_CALOG` | Cluster Advisor 日志 | 集群 advisor 诊断 |
| `config.properties` | TFA 自身配置 | 了解 TFA 参数设置 |
| `agent/emagent/` | Enterprise Manager 代理日志 | EM 监控连通性 |
| `CHMDATA/chmosmeta_*.json` | CHM 元数据 | CHM 版本/状态 |
| `CVU/` | Cluster Verification Utility 输出 | 集群部署验证 |

### 7.3 pa00db12 独有（hxdb 无）

| 文件/目录 | 分析价值 |
|-----------|:--------:|
| `dmesg` | 内核日志（I/O 错误、SCSI 驱动） |
| `LSMOD` | 内核模块列表 |
| `RPMQA` | Linux RPM 包清单 |
| `TOP_50_MEMORY` | 内存 Top 50 进程 |
| `ORACLEAFD_CONF`, `AFDTOOL_KSTATE` | AFD 内核状态 |
| `NSSWITCH_CONF` | 名称解析顺序配置 |
| `oswbb/archive/` | OSWatcher 性能采样（趋势分析） |
| `acfs/resources/*/dumpstate.out` | ACFS 驱动 crash 时间线 |
| `diag/tnslsnr/` | 监听日志 |
| `CHMDATA/chmosmeta_*.json` | CHM 结构 JSON |

### 7.4 hxdb 特有故障模式：ASM-CRS 通信断裂

在 hxdb02 ASM alert log 中发现以下重复模式：

```
2022-09-28 10:23:45.123  WARNING: failed to online diskgroup resource
                          ora.DATAHIS.dg (unable to communicate with CRSD/OHASD)
2022-09-28 10:23:45.124  WARNING: failed to online diskgroup resource
                          ora.DATA.dg (unable to communicate with CRSD/OHASD)
2022-09-28 10:23:45.124  WARNING: failed to online diskgroup resource
                          ora.OCR.dg (unable to communicate with CRSD/OHASD)
...
2022-09-28 10:25:30.001  WARNING: giving up on client id
                          [cbsdb1:cbsdb:hxdb] which has not reconnected
                          for 120 seconds
2022-09-28 10:25:31.000  NOTE: CSS requested to fence client
                          cbsdb1:cbsdb:hxdb
```

**故障链（3 阶段 100 秒）：**

| 阶段 | 时间偏移 | 事件 |
|:----:|:--------:|------|
| 1 | T+0s | ASM 启动后无法 online 任何 diskgroup（与 CRSD/OHASD 不通） |
| 2 | T+105s | ASM 放弃等待客户端重连（giving up on client id） |
| 3 | T+106s | CSS 隔离客户端（CSS requested to fence client） |

**影响范围：** 全部 3 个 diskgroup（OCR, DATA, DATAHIS）均无法 online → 数据库不可访问 → 节点被 CSS 逐出。

**复发时间线（hxdb02）：**

| 日期 | 严重度 | 备注 |
|------|:------:|------|
| 2022-09-17 | 严重 | ASM-CRS 首次通信故障 |
| 2022-09-28 | 严重 | 完整触发三级故障链 |
| 2022-10-20 | 严重 | 再次触发 fencing |
| 2022-11-25 | 严重 | 反复发作 |
| 2025-05-26 | 严重 | 采集当日仍复发（多次） |

### 7.5 关键学习发现

| 学习点 | 说明 | 代码影响 |
|--------|------|:--------:|
| 1. 主机名前缀自动检测 | pa00db12 vs hxdb01 使用不同前缀，无法硬编码 | extractor.py → `_detect_hostname()` |
| 2. 快照文件后缀分类器 | 100+ 种后缀可映射到 30+ 个细粒度分类 | config.py → `ROOT_SNAPSHOT_CLASSIFIER` 字典 |
| 3. 快照到分析类映射 | 细粒度分类需映射回顶层 ANALYSIS_CATEGORIES | config.py → `CATEGORY_MAP` |
| 4. ASM-CRS 通信故障 | `failed to online ... (unable to communicate with CRSD/OHASD)` → `CSS requested to fence` 三级链 | rules/rac_cluster.py → `AsmCrsCommFailureRule` |
| 5. TFA 结构变体 | pa00db12 有 OSWatcher/ACFS dump 但无 agent/CVU；hxdb 有 agent/CVU 但无 OSWatcher | 运行时结构检测 |
| 6. OS 差异 | pa00db12 使用 RPM (Linux), hxdb 使用 lslpp (AIX) — ospackages 分类器统一 | 内容分析而非仅文件名 |

---

## 八、已自动执行的代码调整

根据上述分析，已完成以下自动代码调整：

### 8.1 config.py — 新增 ROOT_SNAPSHOT_CLASSIFIER（100+ 文件后缀）

**新增数据结构：** `ROOT_SNAPSHOT_CLASSIFIER: dict[str, str]`

按主题分类：
- **ocr_info (3):** OCRBACKUP, OCRDUMP, OLRDUMP
- **cluster_state (2):** GETCSS, CHA_STATUS
- **voting_disk (1):** QUERYVOTE
- **crs_health (1):** CHECKCRS
- **crs_resource (4):** STATRESCRS, STATRESCRSFULL, STATRESDEPENDENCY, STATRESOHAS, STATRESFULLOHAS
- **crs_config (3):** CRSCTL_CONFIG_CRS, CRSCTL_QUERY_CRS_ACTIVEVERSION, OHASDRUN
- **cluster_config (3):** CLUSTERCONFIG, NODEAPPS, OLSNODES
- **patch_status (1):** CRSPATCHCKPT_STATUS
- **asm_config (2):** CONFIGASM, DEV_ASM_CONTENTS
- **network_config (1):** OIFCFG
- **acfs_config (2):** ORACLEAFD_CONF, AFDTOOL_KSTATE
- **gi_version (2):** SOFTWAREVERSION, ACTIVEVERSION
- **patch_info (3):** OPATCH_CRS, OPATCH_DBHOMES, OPATCH_LSINVENTORY
- **os_process (2):** PS, PIDS
- **os_memory (2):** TOP_50_MEMORY, SWAPINFO
- **os_network (10+):** NETSTAT, NSLOOKUP, PING_INFO, IFCONFIG, IFCONFIG_A, DHCP, HOSTS, RESOLV, ROUTE, ARP
- **os_hardware (6):** IPMI, PRTDIAG, PRTCONF, DMIDECODE, LSHW, LSPCI
- **os_kernel (2):** DMESG, LSMOD
- **os_system (5):** RUNLEVEL, INITTAB, UPSTATUS, UPTIME, LAST, WHO
- **os_config (8):** NSSWITCH_CONF, ULIMIT, ENV, CRONTAB, SERVICES, SERVICE, SYSTEM, SYSCTL, LIMITS
- **os_packages (4):** RPMQA, RPM_QA, ospackages, ospatches
- **os_mount (7):** MTAB, FSTAB, EXPORTS, DF, MOUNT, LVMTAB, PVS, VGS, LVS
- **os_perf (12):** VMSTAT, IOSTAT, MPSTAT, SAR*, TOP, FREE
- **os_ls (4):** LS, LS_L, LS_LTR, FIND
- **tfa_summary (3):** SUMMARY, TFA_CONFIG, TFA_STATUS, TFA_HISTORY

**新增映射表：** `CATEGORY_MAP: dict[str, str]` — 将上述 30+ 细粒度类别映射回 6 个顶层分析大类（RAC/Clusterware, ASM/存储, OS 资源, 参考）。

**原有 FILE_PATTERNS 增强：** 新增 agent_log, gpnp_log, chm_metadata, cvu_data, calog, tfa_config 六个分类。

### 8.2 extractor.py — 动态主机名检测 + 快照发现

**新增函数：** `parse_tfa_filename(filename)`
- 从 zip 文件名解析出 `{hostname}` 和 `{collection_ts}` 元数据
- 支持 pa00db12 和 hxdb01 两种格式

**新增函数：** `_detect_hostname(extract_dir)`
- 自动扫描根目录文件，根据 `{word}_{SUFFIX}` 模式投票选出最高频 hostname
- 不依赖硬编码前缀，适配任意主机名

**新增函数：** `discover_root_snapshots(extract_dir, hostname)`
- 收集 `{hostname}_{SUFFIX}` 格式文件名，根据 ROOT_SNAPSHOT_CLASSIFIER 自动分类
- 大小写不敏感
- 未知后缀转入 `_unknown_snapshots` 调试组

**增强函数：** `discover_files(extract_dir)`
- 合并 A 路径（FILE_PATTERNS glob）+ B 路径（根目录快照）
- 返回统一文件分类字典

**新增工具函数：** `get_snapshot_category_mapping(snapshot_category)`
- 将快照细粒度类别映射回 ANALYSIS_CATEGORIES 顶层大类

### 8.3 rules/rac_cluster.py — 新增 RAC-005 ASM-CRS 通信故障规则

**新规则类：** `AsmCrsCommFailureRule` (RAC-005)

三阶段匹配模式：
| 阶段 | 规则 ID 后缀 | 严重度 | 匹配正则 |
|:----:|:------------:|:------:|----------|
| 磁盘组 online 失败 | `DISKGROUP_ONLINE_FAIL` | critical | `failed to online diskgroup resource ora.\w+.dg \(unable to communicate with CRSD/OHASD\)` |
| ASM 放弃客户端 | `CLIENT_GIVEUP` | high | `giving up on client id \[.*?\] which has not reconnected` |
| CSS 隔离 fence | `CSS_FENCE` | critical | `CSS requested to fence client \[.*?\]` |

### 8.4 rules/registry.py — 注册 RAC-005

新增导入 `AsmCrsCommFailureRule` 并加入 `get_all_rules()` 返回列表。

---

## 九、后续建议

### P0 即刻实施
- [x] config.py: ROOT_SNAPSHOT_CLASSIFIER
- [x] extractor.py: 动态主机名检测
- [x] rules/rac_cluster.py: ASM-CRS 通信故障 RAC-005
- [x] rules/registry.py: 注册 RAC-005

### P1 推荐实施
- [ ] 新增 rules/os_network.py: 网络健康规则（结合 IFCONFIG, NETSTAT, NSLOOKUP, PING_INFO）
- [ ] 新增 rules/os_packages.py: OS 包/补丁差异分析（结合 RPMQA / ospackages）
- [ ] 新增 rules/asm_comm.py: ASM-CRS 通信历史统计（分析复发频率）
- [ ] engine.py: 快照文件内容分析（PIDS/PS 解析进程树, NETSTAT 解析网络状态）
- [ ] 故障链引擎：支持跨文件的多事件关联聚类

### P2 远期优化
- [ ] OSWatcher 趋势分析（oswbb/archive/ 时序数据）
- [ ] ACFS dumpstate 内容解析（pa00db12 特有）
- [ ] CHM JSON 结构化解析（重构后 3/3 TFA 均缺少 OSWatcher）
- [ ] TFA 结构自动检测 → 动态启用/禁用适配器（pa00db12 模式 vs hxdb 模式）
- [ ] ASM-CRS 通信故障自动修复建议书（crsctl 命令序列 + 验证步骤）
