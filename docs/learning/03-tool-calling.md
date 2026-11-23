# 03 · 工具调用：LLM 的"手"是怎么接上的

## 解决什么问题

LLM 只会输出文本。要让它读文件、打补丁、跑测试，需要：
一套**工具协议** + **参数校验** + **分发执行** + **结果回灌**。

## 双通道协议

1. **原生 tool calling**：请求体带 `tools`（JSON Schema，由
   `ToolRegistry.schemas()` 从 Pydantic 模型生成）；响应里的
   `message.tool_calls` 被解析为 `ToolCall`（`llm/openai_compatible.py:_parse_tool_calls`）。
2. **围栏兜底**：不是所有 OpenAI 兼容端点都支持原生工具。模型也可以输出：

   ````
   ```action
   {"tool": "read_file", "args": {"path": "shop/paginate.py"}}
   ```
   ````

   `agent/protocol.py:parse_actions()` 用正则
   `r"```action\s*(.*?)(?:```|$)"`（DOTALL）提取——**容忍未闭合围栏**
   （模型常漏写结尾反引号），畸形 JSON 跳过不抛错，未知工具名拒绝。

循环里（`agent/loop.py`）：`resp.tool_calls` 非空走通道 1，否则走通道 2。

## 严格校验，绝不执行畸形调用

`tools/registry.py:dispatch()`：

```python
args = tool.args_model.model_validate(action.args, strict=True)
```

`strict=True` 禁止隐式转换（比如把数字 5 当字符串 "5"）。校验失败 →
`Observation(ok=False, error="invalid arguments ...")` 回灌给模型，
**工具函数根本不会被调用**。未知工具同理。

## 八个工具一览

| 工具 | 文件 | 要点 |
|---|---|---|
| read_file | tools/files.py | 工作区围栏 + 20k 字符截断 |
| list_files | tools/files.py | 跳过 .git/缓存，500 条上限 |
| search_code | tools/files.py | 正则逐行搜索，file:line 输出 |
| apply_patch | tools/patch.py | 纯 Python unified-diff（见 06） |
| run_tests | tools/tests.py | 委托执行后端（沙箱），不自己 spawn |
| git_status / git_diff | tools/git.py | 固定 argv，无模型可控 shell 串 |
| finish | （循环内处理） | 仅声明完成，验证器说了算 |

## 具体例子

模型输出 `{"tool": "search_code", "args": {"pattern": "def paginate"}}`：

```
dispatch → SearchCodeArgs 校验通过
→ _fence(workspace, ".") 解析路径并检查包含关系
→ 遍历文本文件逐行 re.search
→ Observation(ok=True, content="shop/paginate.py:4: def paginate(...)")
→ 循环把 JSON 回灌为 user 消息 "Observation: {...}"
```

## 常见失败场景

- `path escapes workspace` → 路径越界或 symlink 指向外部（`_fence` 用
  `Path.resolve()` 后 `is_relative_to` 检查）。
- `invalid arguments` → 模型给了错类型/缺字段；看 error 里的 Pydantic 详情。
- `unknown tool` → 模型幻觉了不存在的工具名。
- 搜索无结果 → 返回 "no matches"（不是错误）。

## 如何修改与测试

加一个新工具（例如 `file_info`）：
1. 在 `tests/unit/test_files_tools.py` 写失败测试；
2. 定义 `FileInfoArgs(BaseModel)` + `FileInfoTool`（name/args_model/description/execute）；
3. 在 `agent/protocol.py:TOOL_NAMES` 与 workflow 的 registry 列表注册；
4. `uv run pytest tests/unit/test_files_tools.py` 转绿后跑全量。