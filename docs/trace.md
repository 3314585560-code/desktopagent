# 实际运行记录

通过本机 SSE 接口运行内置离线场景。以下为一次实际执行的事件，使用固定演示流程，不调用在线模型。会话标识已省略。

~~~jsonl
{"kind": "mcp", "name": "demo", "text": "已连接 MCP 服务"}
{"kind": "status", "text": "离线演示：按预设顺序执行真实工具"}
{"kind": "call", "name": "read", "text": "{\"path\": \"stats.py\", \"limit\": 12}"}
{"kind": "result", "name": "read", "text": "1: def average(values):\n2:     divisor = len(values)\n3:     return sum(values) / divisor\n4: \n5: \n6: def average_legacy(values):\n7:     divisor = len(values)\n8:     return sum(values) / divisor\n后面还有 0 行"}
{"kind": "call", "name": "edit", "text": "{\"path\": \"stats.py\", \"old\": \"    divisor = len(values)\", \"new\": \"    divisor = len(values) or 1\"}"}
{"kind": "error", "name": "edit", "text": "旧内容匹配到多处，请提供更具体的内容"}
{"kind": "call", "name": "edit", "text": "{\"path\": \"stats.py\", \"old\": \"def average(values):\\n    divisor = len(values)\", \"new\": \"def average(values):\\n    divisor = len(values) or 1\"}"}
{"kind": "diff", "name": "stats.py", "text": "--- a/stats.py\n+++ b/stats.py\n@@ -1,5 +1,5 @@\n def average(values):\n-    divisor = len(values)\n+    divisor = len(values) or 1\n     return sum(values) / divisor\n \n "}
{"kind": "result", "name": "edit", "text": "覆盖成功，原来 8 行，现在 8 行"}
{"kind": "call", "name": "write", "text": "{\"path\": \"notes/run.txt\", \"content\": \"空列表已处理。请运行单元测试。\\n\"}"}
{"kind": "diff", "name": "notes/run.txt", "text": "--- a/notes/run.txt\n+++ b/notes/run.txt\n@@ -0,0 +1 @@\n+空列表已处理。请运行单元测试。"}
{"kind": "result", "name": "write", "text": "新建成功，共 1 行"}
{"kind": "call", "name": "bash", "text": "{\"command\": \"python -m unittest -v\", \"timeout\": 40}"}
{"kind": "result", "name": "bash", "text": "退出码 0\nstdout:\n\nstderr:\ntest_empty (test_stats.StatsTest.test_empty) ... ok\r\ntest_regular (test_stats.StatsTest.test_regular) ... ok\r\n\r\n----------------------------------------------------------------------\r\nRan 2 tests in 0.000s\r\n\r\nOK\r\n"}
{"kind": "call", "name": "mcp__demo__project_checklist", "text": "{\"project\": \"统计函数\"}"}
{"kind": "result", "name": "mcp__demo__project_checklist", "text": "统计函数：检查改动范围，运行测试，记录失败及恢复。"}
{"kind": "answer", "text": "已从重复匹配中恢复，只修改 average，测试通过，MCP 已返回检查清单。"}
{"kind": "done", "text": "已完成"}
~~~

## 2026-11-09 安装包发布前复验

使用 `MiniCursor-Setup-1.0.0-x64.exe` 解包出的程序，在全新测试目录运行。解包后的程序与构建产物的 SHA-256 一致。

- 修复前运行安装版的测试入口，退出码 `1`，空列表测试报 `ZeroDivisionError`。
- 用精确编辑工具修复 `average` 后重新运行，退出码 `0`，两项测试均通过。
- 通过 stdio MCP 连接安装版启动的独立进程，发现 `project_checklist` 并成功调用。返回原文：`Mini Cursor 发布验收：检查改动范围，运行测试，记录失败及恢复。`

本轮验证使用本机测试和 MCP 工具，没有调用在线 DeepSeek。
