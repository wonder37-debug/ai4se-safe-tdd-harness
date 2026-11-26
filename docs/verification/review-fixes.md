# PR #1 Review 修复报告（五轮共 24 条）

> 基准 SHA：6d8b0c6 → 修复后见 git log。第一轮 12 条经逐项核对**确认为真实问题**
> （无误报、无已修复项），每条均先写能复现失败的回归测试（RED）再修复（GREEN）。

## P1（7）

### 1. thread 4661696737 — apply_patch 可改 .git 元数据 → 宿主 git 执行不可信配置
- **修复**：`tools/files.py:_fence` 拒绝任何 `.git` 路径分量（read/patch/search 共用）；
  `tools/git.py` 所有宿主 git 调用前置 `GIT_HARDEN_ARGS`（`-c core.fsmonitor=false`、
  `-c core.hooksPath=<devnull>`、`--no-optional-locks`），diff 类调用加
  `--no-ext-diff --no-textconv`，env `GIT_TERMINAL_PROMPT=0`。
  系统/全局配置保留（宿主管理员控制、非仓库可写攻击面），避免破坏 autocrlf 一致性。
- **测试**：`tests/unit/test_patch_security.py`（.git/config 补丁、hooks 新建、read 拒绝）；
  `tests/unit/test_git_hardening.py`（flags/env 断言 + **行为级**：仓库配置 fsmonitor /
  diff.external 指向写标记文件的命令，调用后标记文件不存在）。

### 2. thread 4661696747 — search_code 跟随 symlink 泄漏宿主文件
- **修复**：`_walk` 对每个条目 `resolve()` 后做工作区包含检查；搜索 worker 内对每个
  候选文件再次 resolve+包含检查后才 stat/read。
- **测试**：`tests/unit/test_search_security.py::test_search_does_not_leak_external_symlink_target`
  （指向外部含 canary key 文件的 symlink，搜索结果不含外部内容；Windows 无 symlink
  权限时 skip，Linux CI 真实执行）。

### 3. thread 4661696753 — 新建 untracked 文件不在补丁导出与验证范围
- **修复**：`tools/git.py:full_candidate_diff` = `git diff HEAD`（tracked）+ 对每个
  untracked 文件 `git diff --no-index /dev/null <file>` 合成新文件 diff；
  **刻意不用 `git add`**（会触发仓库配置的 clean/smudge filter 驱动在宿主执行）。
  workflow 导出、verifier、GitDiffTool 统一使用该完整候选变更；
  `prepare_workspace` 写 `.git/info/exclude` 排除工具产物（.deps/.safefix-memory/
  __pycache__/_eval_verify 等）。
- **测试**：`tests/unit/test_workflow_integrity.py::test_new_file_included_in_patch_and_verification`
  （修复依赖新建 helper.py，导出补丁含新文件且 verified）。

### 4. thread 4662992875 — 改 pytest.ini/addopts 伪造 verified
- **修复**：`verifier._PROTECTED_CONFIG`（pytest.ini/tox.ini/setup.cfg/conftest.py/
  pyproject.toml）纳入 tests_untouched（含 untracked 新增）；独立验证命令追加
  `--override-ini=addopts= -p no:cacheprovider`（覆盖工作区配置）；
  `_tests_actually_passed` 要求输出含 `N passed` 且无 "no tests ran"
  （collect-only 返回 0 也被拒绝）。
- **测试**：`tests/unit/test_workflow_integrity.py::test_pytest_ini_collect_only_forgery_rejected`。

### 5. thread 4662992887 — 超时只杀 docker 客户端，容器继续运行
- **修复**：`build_argv` 加 `--cidfile`；`DockerExecutor._execute` 在超时或
  `asyncio.CancelledError` 时读 cid 并 `docker rm -f`（`_default_remove_container`），
  finally 清理 cidfile 临时目录。
- **测试**：`tests/unit/test_runtime_limits.py`（超时/取消触发 force-remove、成功不触发、
  cidfile 清理）；`tests/integration/test_docker_sandbox.py::test_timeout_kills`
  增加 `docker ps --filter ancestor=...` 断言无残留运行容器（真实 Docker）。

### 6. thread 4662795527 — communicate() 先全量缓冲再截断 → 宿主内存耗尽
- **修复**：新增 `runtime/output.py:bounded_communicate`：64KB  chunks 流式排空
  stdout/stderr，仅保留尾部 cap 字节（测试摘要在尾部），超限继续排空；
  docker/git/local 执行器全部改用。
- **测试**：`tests/unit/test_runtime_limits.py::test_bounded_reader_caps_retained_memory`
  （8MB 输出 → 保留 ≤100KB+marker，尾部完整）。

### 7. thread 4663423540 — 灾难性回溯正则阻塞宿主事件循环
- **修复**：`search_code` 改为 **可杀死的 spawn 子进程**执行匹配
  （`_search_worker` + `Pipe`），父进程 `poll(timeout)` 到期 terminate→kill；
  整体经 `asyncio.to_thread` 不占事件循环；`SearchCodeArgs.timeout`（默认 10s，≤60s）。
- **测试**：`tests/unit/test_search_security.py::test_search_catastrophic_regex_is_terminated`
  （`(a+)+$` × 40a!，1s 超时内返回；修复前该输入使进程挂死数分钟——RED 阶段实测）。

## P2（5）

### 8. thread 4661696758 — Single-shot 基线不公平（无源码上下文）
- **修复**：`RepairTask.preseed_context` + `workflow._build_source_context`
  （工作区源码 + 复现输出，20k 字符上限）注入唯一一次生成的初始消息；
  runner 对 Variant.A 启用。A 现在与 B/C 拥有同等信息，仅少迭代机会。
- **测试**：`test_workflow_integrity.py::test_single_shot_preseed_context_enables_patch`；
  修正后真实评测 A 2/5（见 evaluation.md v2）。

### 9. thread 4662795533 — 复用 report_dir 时旧 events 混入
- **修复**：`JsonlSink(append=False)` 初始化时截断一次再追加；AgentLoop 在 fan-out
  前分配 seq/ts（JsonlSink 不再各自编号）。
- **测试**：`test_workflow_integrity.py::test_events_jsonl_fresh_per_run`
  （同目录两次运行，events 仅含第二次、seq 连续）。

### 10. thread 4663355641 — 多 hunk 行号偏移致错误匹配
- **修复**：`patch._render` 累计前序 hunk 的 delta，hint=old_start-1+delta；
  `_find` 增加单调下界（前一 hunk 结束位置），禁止回搜到更早的重复上下文。
- **测试**：`tests/unit/test_patch_offsets.py`（difflib 生成"头部新增 5 行 + 修改第二个
  重复块"补丁，断言修改落在正确块；修复前落到第一个块）。

### 11. thread 4663355656 — root 宿主下非 root 容器工作区不可写
- **修复**：`prepare_workspace._ensure_container_writable`：euid==0 时将 clone
  整树 chown 到 1000:1000（容器保持非 root）；其他环境 no-op。
- **测试**：`test_workflow_integrity.py::test_workspace_exclude_and_root_chown`
  （mock root + chown 记录断言；真实 root 路径由 Linux CI 覆盖）。

### 12. thread 4663423547 — 墙钟预算不约束在途调用
- **修复**：`AgentLoop` 对 `llm.complete` 与 `registry.dispatch` 施加
  `asyncio.wait_for(剩余墙钟)`；响应返回后、处理前**重检 deadline**
  （迟到的 finish 不再记为正常完成）。
- **测试**：`tests/unit/test_loop_deadline.py`（0.15s 迟到 finish / 0.2s 工具
  vs 0.02s 预算 → BUDGET_EXCEEDED，耗时 <0.1s）。

## 第二轮 review（2 条新 P1，针对第一轮修复）

### 13. thread 4664964008 — root chown 跟随 symlink 改宿主文件所有者
- **修复**：`_ensure_container_writable` 跳过 symlink 条目，且
  `os.chown(..., follow_symlinks=False)`；所有权变更严格限于 clone 内对象。
- **测试**：`test_workflow_integrity.py::test_root_chown_does_not_follow_symlinks`
  （mock root + 外部目标 symlink，断言 follow_symlinks=False 且外部目标未被 chown；
  Windows symlink 权限 skip，Linux CI 执行）。

### 14. thread 4664964020 — 测试文件类型变更（T）绕过防篡改
- **修复**：verifier 状态过滤扩展为 M/D/R/T/C（file→symlink 指向通过测试的 helper
  产生 T，必须拒绝）。
- **测试**：`test_workflow_integrity.py::test_type_change_of_test_file_rejected`
  （测试文件替换为 symlink 后 tests_untouched 失败；Linux CI 执行）。

## 第三轮 review（4 P1 + 1 P2，针对可写挂载与交付完整性）

### 15. thread 4665182698 — 容器写 .git/config 的 clean filter 被宿主 git 执行
### 16. thread 4665182713 — 容器提交移动 HEAD，防篡改/导出失去原始基准
- **统一修复**：`prepare_workspace._snapshot_git_dir` 在准备期冻结一份**净化 .git 快照**
  （最小安全 config：无 filter 驱动、fsmonitor off、hooksPath 中和；移除 hooks 与
  info/attributes），HEAD/index 冻结于 base commit。所有宿主 git 读取
  （status/diff/ls-files/验证）经 `--git-dir <快照> --work-tree <工作区>`，
  容器对可写挂载中 .git 的任何修改（filter/HEAD/refs）均不影响宿主读取。
  `Workspace.git_dir` 贯穿 ToolContext/LoopDeps/verifier/full_candidate_diff；
  cleanup 同时清理快照。
- **测试**：`tests/unit/test_round3_security.py::test_container_written_filter_driver_not_executed_by_host_git`
  （模拟容器写入 filter.evil.clean + .gitattributes，宿主 diff 不执行标记命令）；
  `::test_diff_base_frozen_against_container_commits`（容器提交弱化测试后，
  导出仍含测试变更且 tests_untouched 失败）。

### 17. thread 4665182720 — rename 记录只查目标路径
- **修复**：verifier 对 R/C 状态检查**两端**路径（parts[1:]），任一端为受保护
  测试路径即判篡改。
- **测试**：`test_round3_security.py::test_rename_of_test_file_detected_on_both_ends`
  （git mv tests/test_bad.py → helper.py 并提交，tests_untouched 失败）。

### 18. thread 4665182703 — memory symlink 将宿主文件注入 system prompt
- **修复**：双重防御：(1) workflow 将 MemoryStore 移至 **report_dir/memory**
  （harness 控制，目标仓库不可控）；(2) `MemoryStore.read` 拒绝目录本身为 symlink、
  跳过 symlink 条目、逐文件 resolve+包含检查。
- **测试**：`test_round3_security.py::test_memory_symlink_does_not_leak_into_prompt`
  （外部 canary .md symlink 不进 prompt；Windows 权限 skip，Linux CI 执行）。

### 19. thread 4665182729 — 截断的 git 输出被当作完整补丁交付
- **修复**：`full_candidate_diff` 检测截断标记 → 显式失败（rc=-1）；
  workflow 导出失败时 raise RuntimeError，绝不交付不完整补丁。
- **测试**：`test_round3_security.py::test_truncated_diff_refused_as_patch`
  （>1MB 变更 → 拒绝）。

## 第四轮 review（2 P1）+ CI 测试环境修复

### 20. thread 4665404091 — .gitignore 隐藏受保护文件
- **修复**：`untracked_files` 改用 `git ls-files --others`（**不带** --exclude-standard），
  以 harness 固定规则（_UNTRACKED_SKIP_DIRS：.deps/__pycache__/.safefix-memory/
  _eval_verify/.pytest_cache 等）过滤工具产物，不再信任工作区 .gitignore/info/exclude。
  被隐藏的 conftest.py 仍进入补丁导出与 tests_untouched 检查。
- **测试**：`tests/unit/test_round4_security.py::test_gitignore_cannot_hide_protected_conftest`。

### 21. thread 4665404099 — read_file 读 FIFO 挂死宿主事件循环
- **修复**：ReadFileTool 读取前 `stat.S_ISREG` 拒绝非普通文件（FIFO/socket/设备）；
  读取改为 `f.read(_READ_CAP+1)` 有界读取，不再整文件读入后才截断。
- **测试**：`test_round4_security.py::test_read_file_refuses_fifo`
  （mkfifo 仅 POSIX；Windows skip，Linux CI 执行）。

### CI 测试环境修复（非产品缺陷）
- 第三轮两个测试在 clone 内 commit，clone 无 git identity；Windows 全局配置掩盖了
  该问题，Linux CI 报 exit 128。修复：测试在 clone 内显式配置 user.email/name。

## 第五轮 review（1 P1 + 2 P2，git 路径编码与二进制补丁）

### 22. thread 4665584602 — 非 ASCII 路径被 git 转义后绕过防篡改
- **修复**：name-status 改用 `-z`（NUL 分隔原始路径），按状态 token 解析
  （R/C 双路径），不再 splitlines/split("\t")。
- **测试**：`tests/unit/test_round5_security.py::test_non_ascii_test_config_path_still_protected`
  （中文/conftest.py 修改 → tests_untouched 失败）。

### 23. thread 4665584617 — 转义路径导致新增文件静默遗漏
- **修复**：`untracked_files` 用 `ls-files --others -z`，按 NUL 分割、不 strip，
  原始路径直接用于 --no-index diff。
- **测试**：`test_round5_security.py::test_non_ascii_new_file_exported`
  （把导出补丁应用到原始仓库，校验 `新模块.py` 的文件名与内容，兼容 Git 对路径的引号转义）。

### 24. thread 4665584631 — 二进制变更导出不可应用
- **修复**：tracked 与 --no-index diff 统一加 `--binary`；另发现并修复伴生缺陷：
  patch.diff 以 write_text 落盘时 Windows 文本模式将 \n 转 \r\n 损坏二进制补丁 →
  改为 write_bytes 原始字节。
- **测试**：`test_round5_security.py::test_binary_change_exported_as_applicable_patch`
  （含 NUL 字节文件变更 → 导出含 GIT binary patch 且 `git apply --check` 在 base 状态通过）。

## 验证汇总（修复后实测）

- Windows 单元：**247 passed, 6 skipped**（symlink/mkfifo 权限），覆盖率 88%。
- Windows 全量（Docker 可用、真实 LLM 门控关闭）：**255 passed, 8 skipped**。
- Docker 集成：**8 passed**（含容器无泄漏、沙箱内完整修复）。
- 真实 LLM 验收（`SAFEFIX_REAL_LLM=1`）：**2 passed**（paginate + held-out querystring，
  均强制 verified；第三/四/五轮修复后重跑仍 2 passed）。
- 修正后真实 A/B/C：**A 2/5 · B 5/5 · C 5/5**（92,959 tokens；B 均 8.8 调用、C 均 7.4）。
- ruff 全绿；`uv build` wheel+sdist；净室安装 demo verified / mock eval 5/5。

## 剩余风险

- A 的 3 个失败为真实单发行为缺陷（唯一调用用于 run_tests 或输出 ```python 代码块
  而非 apply_patch），属基线能力测量，非工程缺陷。
- 真实样本仍小（5+1 任务），观察性结论。
- root-host chown 与 symlink 围栏的真实 Linux 行为依赖 CI ubuntu 验证。
