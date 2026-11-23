# 06 · Git 与补丁：最小修改 + 独立验证

## 解决什么问题

整文件覆写不可审查、易破坏无关代码。SafeFix 要求**最小 unified diff**，
并且"修好了"必须由独立证据判定，而不是模型说 `finish`。

## 工作区生命周期（repair/workflow.py）

```
prepare_workspace(repo)     # git clone --local --no-hardlinks → 临时副本
  → 记录 base_commit（git rev-parse HEAD）
  → [可信准备] → [复现失败] → AgentLoop 修复
  → git diff 提取补丁 → verify_patch 独立验证
  → outcome.json / patch.diff / events.jsonl
cleanup_workspace(ws)       # shutil.rmtree（Windows 只读文件 chmod 重试）
```

原仓库从头到尾零写入（`tests/unit/test_workflow.py` 有断言）。

## apply_patch：纯 Python diff 应用器

`tools/patch.py`。输入标准 unified diff：

```diff
--- a/shop/paginate.py
+++ b/shop/paginate.py
@@ -5,3 +5,3 @@
     """Return the page-th slice..."""
-    start = page * size
+    start = (page - 1) * size
     return items[start : start + size]
```

实现要点：
- `_parse` 解析 `---/+++/@@` 与 ` /-/+` 行；`/dev/null` 表示新建/删除；
- `_find` 先按 hunk 声明行号定位，失配则**全文件搜索**精确上下文（容忍行号漂移）；
- 上下文不匹配 → `PatchError`，文件保持原样（绝不"尽力而为"地破坏代码）；
- **两阶段**：先渲染所有文件的新内容，全部成功后才写盘（多文件补丁无半 applying）；
- 路径过 `_fence` 工作区围栏，`../evil` 直接拒绝。

## 独立验证器（repair/verifier.py）

`verify_patch` 在 agent 终止后执行 5 项检查：

| 检查 | 拒绝什么 |
|---|---|
| patch_nonempty | 空补丁谎报修复 |
| tests_untouched | 修改/删除/重命名已有测试（git diff --name-status） |
| repro_passes | 复现命令仍失败 |
| regression_passes | 全量测试仍失败 |
| eval_passes | 独立 eval 测试失败（生成期 agent 看不到它们） |

`status=verified` 还要求**初始确实可复现**（防止"修一个不存在的 bug"）。
eval 测试临时拷入 `_eval_verify/` 运行后立即删除。

## 具体例子（实测轨迹）

paginate fixture：base 测试红 → 补丁改一行 → 可见测试绿 → eval 5 项绿 →
`outcome.json` 记录 base_commit、patch、checks 全过 → 工作区清理。
沙箱版同一流程在 Docker 内跑通（`tests/integration/test_sandboxed_repair.py`）。

## 常见失败场景

- `hunk context mismatch` → 模型给的 diff 上下文与真实文件不符（让它先 read_file）。
- `tests_untouched failed` → 模型动了测试（作弊被拒，反馈会说明）。
- `file already exists` → 新建补丁目标已存在。
- Windows 清理失败 → git 对象只读；`_on_rm_error` 已 chmod 重试。

## 如何修改与测试

给验证器加新检查（如"禁止修改 CI 配置"）：先在 `tests/unit/test_verifier.py`
构造对应 repo 状态写失败测试，再在 `verify_patch` 加 `CheckResult`。
补丁应用器的边界用例都在 `tests/unit/test_patch.py`（8 个）。