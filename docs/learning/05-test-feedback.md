# 05 · 测试反馈：失败信息怎么变成模型的"下一轮线索"

## 解决什么问题

`run_tests` 失败后，把整坨控制台输出丢回给模型既浪费 token 又没重点。
需要**结构化反馈**：哪类错误、哪些测试、哪个文件哪一行、证据片段、行动提示。

## 数据流

```
run_tests 工具 → Observation(exit_code, stdout, stderr, error)
→ FeedbackClassifier.parse(obs)          (feedback/classifier.py)
    exit 0        → Feedback(kind=PASS)
    error=timeout → kind=TIMEOUT
    否则 → parser.parse(stdout, stderr)  (PytestParser / JestParser)
           解析异常 → kind=UNEXPECTED + 输出尾部 30 行
→ Feedback.model_dump_json() 作为 user 消息回灌
→ AgentLoop 记录失败键，做进展感知重试
```

## 六类错误

`models.py:FeedbackKind`：`pass / assertion / syntax / timeout /
infrastructure / unexpected`。

`PytestParser`（`feedback/pytest_parser.py`）的判定顺序：
1. `INTERNALERROR` → infrastructure（环境/插件问题，不是补丁的错）；
2. `SyntaxError / IndentationError / ImportError / ModuleNotFoundError`
   → syntax（import 坏了和语法坏了一样挡住收集）；
3. `FAILED path::test` 摘要行或 `AssertionError` → assertion，
   用正则 `(\S+\.py):(\d+): AssertionError` 提取 file:line；
4. 其余 → unexpected。

`JestParser` 是旧 TS 实现的等价移植（`●` 失败块 + `at file:line:col`），
作为外部 JS 目标仓库的可选适配器——SafeFix 本体不依赖 Node。

## 进展感知重试（关键升级）

旧实现"同一错误出现 2 次就判 stuck"太激进——同错两次不等于修不好。
现在（`agent/loop.py`）：

- 失败键 = `kind | 排序后的失败测试列表 | file:line`；
- 连续同键 ≥ `Budgets.max_same_failure`（默认 3）才 stuck；
- **`apply_patch` 成功会清零计数**——补丁落地就是进展，值得再试。

## 具体例子

pytest 输出含 `FAILED tests/test_math.py::test_add - assert 3 == 4` 与
`tests/test_math.py:4: AssertionError`：

```json
{"kind":"assertion","failed_tests":["tests/test_math.py::test_add"],
 "location":{"file":"tests/test_math.py","line":4},
 "evidence":"...尾部2000字符...","hint":"adjust implementation so tests/test_math.py:4 passes"}
```

模型下一轮看到的是这条 JSON，而不是 5000 行原始输出。

## 常见失败场景

- 分类总是 unexpected → 输出不是 pytest/Jest 格式（换 parser 或加规则）。
- evidence 为空 → obs.stdout/stderr 都空（执行器问题，看 04）。
- 误判 stuck → 检查失败键是否因测试名排序/位置变化而"看起来不同"。

## 如何修改与测试

支持新 runner（如 unittest）：写 `feedback/unittest_parser.py` 实现
`parse(stdout, stderr) -> Feedback`，先在 `tests/unit/test_feedback.py`
加样例输出测试（红），再实现（绿）。evidence 截断阈值在
`classifier.py:_truncate`（保留尾部，因为摘要在最后）。