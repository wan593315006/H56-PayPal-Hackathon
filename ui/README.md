# H56 只读证据台（ui/）

交付包里的**展示层**，不参与评估、不参与支付。它把磁盘上已经存在的 `runs/` 与 `records/` 读出来，排成一张审计视图。

- 只用 Python 标准库（`http.server`、`json`、`hashlib`、`pathlib`、`secrets`、`argparse`、`urllib`）。
- 不 import `app`，不 import `h56_core`，不装 `requests`。
- 除本目录外，不读写交付包的其它任何文件。

## 启动

```bash
python -B ui/server.py --port 8848
```

进程会在 stdout 打印三行：

```
H56 只读证据台已启动
  URL   : http://127.0.0.1:8848/
  TOKEN : <32 位十六进制>
```

把这串 token 粘到页面顶部的 `RUN TOKEN` 输入框里，点「载入」。token 只存在当前标签页的 `sessionStorage`，页面 HTML 与源码里都不含 token。

**必须用 `http://127.0.0.1:8848/` 打开，不能用 `http://localhost:8848/`。** 这是下面第一道闸的直接后果。

## 三道闸

页面每次 `/api/*` 请求都要连过三关，任何一关不过就没有数据：

| 闸 | 规则 | 不过时 |
| --- | --- | --- |
| 一 · Host 精确匹配 | `Host` 头必须**逐字节等于** `127.0.0.1:<port>` | 403 |
| 二 · 一次性 token | 必须带 `X-H56-Run-Token`，值与进程启动时 `secrets.token_hex(16)` 生成的一致 | 401 |
| 三 · 空体 | POST 的 body 必须恰好是 `{}`（允许前后空白） | 400 |

`/api/*` 只接受 GET 与 POST，其它方法（PUT/DELETE/PATCH…）一律 405。

**为什么第一道闸要拒 `localhost`？** 本机服务最典型的攻击面是 DNS rebinding：攻击者把自己的域名解析改到 `127.0.0.1`，再让受害者的浏览器去请求。若服务按"host 里含 localhost 就放行"来判断，这条路就通了。这里要求 Host 与预期的 `127.0.0.1:<port>` 完全相等，`localhost:<port>`、`127.0.0.1.evil.com`、`[::1]`、带尾点或大小写变体全部落在 403。

**第三道闸为什么存在？** 这个服务本该没有任何写操作，那么 POST 就不该有语义。要求 body 恒为 `{}` 是一个"空操作证明"：任何试图携带指令的请求（哪怕未来误加了路由）在数据形状上就先被拒绝，不必依赖下游校验。

## 为什么是只读

代码里没有任何 `open(..., "w")`、`mkdir`、`unlink`、`rename`。所有读操作都走 `pathlib.Path.read_bytes()` / `read_text()`，`runs/` 与 `records/` 只出现在路径拼接的左侧。

可自证：跑页面前后对两个目录做文件级 sha256 快照，`added / lost / changed` 应恒为 `0 / 0 / 0`。

## 为什么没有"点击运行"

评估链（业务策略 → 主机证明 → 四个内核 → 绑定）是一次**带副作用的判定动作**，它决定"这笔钱能不能动"。把它做成按钮等于把治理边界降级成一个 UI 事件：谁点了、点了多少次、点的时候读的是不是同一份证据，都失去可追溯性。

所以这里的选择是：**证据台只呈现已固化的判定**。要看新结果，去命令行跑 `python -B -m app.main evaluate`；要看某个 run 的深度复核，跑：

```bash
python -B -m app.main verify --stamp 20261103T171000Z --business shop
```

页面上出现的每个 run 都是磁盘上已经存在的一次判定，页面不产生第 N+1 次。

## 页面上的 `binding_ok` 是什么

只做**字节级自洽**，不重算语义链：

1. 取 `binding.json`，把 `binding_sha256` 之外的字段按
   `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
   序列化后取 sha256，与文件里自称的 `binding_sha256` 比对。
2. 取 `binding.json` 里的 `evidence_sha256`，与 `evidence.json` 的**文件字节** sha256 比对。

两项都过才显示 `OK`，否则 `REJECTED`。这只回答"这份绑定文件有没有被事后改动过"，不回答"这次判定在业务上对不对"——后者属于 `app.main verify` 的语义链重放，本页不做，页面上也明确写了这条提示。

## 接口

| 路由 | 说明 |
| --- | --- |
| `GET /` | 返回 `index.html` |
| `GET /api/runs` | 每个 run 一条：`stamp`、`business`、`decision`、`stage`、`native_calls`、`boundary`（三布尔）、`has_binding`、`files`、`binding_ok` |
| `GET /api/run?stamp=…&business=…` | 单个 run 的完整只读视图，含 `order`、`policy`、`reference`、`binding` 原文与 `binding_check` |
| `GET /api/records` | 每个 session：`session`、`assessment_id`、`decision`、`artifact_bytes`、`events`、`journal_state` |

路径参数按白名单校验：`stamp` 必须匹配 `^[0-9]{8}T[0-9]{6}Z$`，`business` 必须匹配 `^[A-Za-z0-9_-]{1,32}$`。`..`、`/`、`\` 不可能出现在参数里，因为它们过不了正则。

异常一律收敛成 `{"error": "<code>"}` + 500，响应体里不会有 traceback。

## 已知边界

- 只监听 `127.0.0.1`，不监听 `0.0.0.0`，局域网内其它机器访问不到。
- token 每次重启都变，旧标签页会拿到 401，重新粘贴即可。
- `records/*/events.jsonl` 末行不完整时标记 `journal_state=DAMAGED` 并继续展示其余 session，不抛异常。
- 页面零外链（无 CDN、无远程字体、无图片），断网可用。
