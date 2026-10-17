# 本地演示：历史结果浏览器

## 启动

Python 3.12+，无GPU要求。建议Web依赖和推理依赖使用不同虚拟环境。

```bash
python -m pip install -r web-requirements.txt
python -m benchmark_lab
```

按终端打印的地址打开，默认 <http://127.0.0.1:8765>。Windows 的 Hyper-V/WSL 会动态保留端口段（本机 2026-10-17 实测 8752–8851 被保留，8765 绑定报 WinError 10013），此时不带 `--port` 会自动改用空闲本地端口；显式 `--port` 被占用时直接报错，不静默换端口。Windows PowerShell可在仓库根目录执行：

```powershell
.\scripts\start-demo.ps1
# Python不在PATH时：
.\scripts\start-demo.ps1 -Python C:\path\to\python.exe
```

脚本只准备项目内的隔离Web环境，启动本地只读服务。Ctrl+C退出。Windows无法通过localhost访问WSL服务时，直接用Windows脚本启动，不必改推理环境或开放外网端口。默认只监听回环地址；此版本不提供公网托管或账号认证。

## 给导师/评委的演示顺序

1. 首页展示24次历史运行、1536条请求，明确这些是已有真实GPU实验，不是当前实时运行。
2. 选择vLLM，再选择并发32，列表缩小为3次重复。
3. 切换TTFT、TPOT和吞吐图表。每根柱是重复均值的中位数，竖线是最小/最大值，不是置信区间。
4. 选择某一次运行，查看该次64请求的P50/P95/P99和TTFT序列。P99只作描述，不宣称线上尾延迟可靠。
5. 下载原始JSON、原校验记录和配置；导出与当前筛选一致的CSV。

图表不会启动模型或调用GPU；页面不生成根因诊断。研究测量HOLD和工程展示可用分别验收。

## 实现与数据边界

- `benchmark_lab/catalog.py`复用`lab.validate`和`tail_report.summarize`，不复制新的指标公式。
- 启动时核对`reports/001-raw-sha256.json`列出的原始件，再将单次运行摘要导入SQLite。缺件、哈希不符、校验失败或请求计时无效会拒绝导入。
- `.benchmark/catalog.sqlite3`只存可重建索引，不是原始数据权威。启动重建不修改原始件；删掉缓存后重启即可重建。
- 列表是启动时已校验的索引快照，不监控文件编辑。详情和下载重新核对相应原始文件哈希，发现修改返回409，不把修改后的文件当成原始证据。
- 下载只允许当前运行登记的result/metadata/validation，不能通过API指定任意文件路径。没有任务创建、命令执行或推理端点。
- 引擎过滤和单引擎索引已支持，不代表原CLI已完成单引擎配置解耦。单worker、任务状态及在线压测仍是下一阶段。

## 测试

```bash
python -m pip install -r report-requirements.txt -r web-requirements.txt
python -m unittest discover -s tests -v
python -m unittest discover -s web_tests -v
python scripts/check-demo-data.py
```

`.github/workflows/ci.yml`在 Ubuntu 与 Windows 上运行上述命令（另含`test_readiness`）。仓库`.gitattributes`对全部文件关闭换行转换：Git for Windows默认`core.autocrlf=true`，否则全新克隆会把原始JSON转成CRLF，导致哈希核对失败、演示无法启动（2026-10-17用全新克隆复现）。

CPU单元/API测试使用显式fixture；最后一个命令校验仓库已有真实数据，不运行推理。当前FastAPI/Starlette环境使用TestClient时会提示httpx兼容层弃用警告，测试仍可运行；后续升级依赖单独验证，不隐去警告。

可选浏览器端测试：Node 22+和本地Edge/Chrome，先启动演示服务，再执行`node scripts/check-demo-ui.mjs`（服务不在8765时用`DEMO_URL`指定实际地址）。通过`BROWSER_PATH`指定浏览器程序；使用独立无头测试profile，输出桌面/手机截图与测试JSON，缓存位于`.benchmark/`。

Web接口：`GET /api/runs`、`GET /api/runs/{id}`、`GET /api/runs/{id}/artifacts/{kind}`、`GET /api/export.csv`。筛选支持`engine`和`concurrency`。CSV每行对应一次运行，不混合重复试验的分位数。
