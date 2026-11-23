# 04 · 沙箱：为什么 worktree 不是安全边界

## 解决什么问题

模型生成的命令可能是 `rm -rf /`、fork bomb、或偷偷外传数据。
**绝不能让它在你的宿主机上 unrestricted 运行。**

## 三层隔离，各管各的

| 层 | 机制 | 保护什么 | 不保护什么 |
|---|---|---|---|
| 工作区副本 | `runtime/workspace.py:prepare_workspace`（git clone --local --no-hardlinks） | 原仓库内容与历史 | 宿主其余部分 |
| Docker 沙箱 | `runtime/docker_executor.py` | 宿主文件系统/网络/资源 | 内核级逃逸 |
| 护栏+审批 | `security/policy.py` + approval | 明显危险动作（启发式） | 创造性绕过 |

**worktree/copy 只保护历史，不是沙箱**——这是面试高频点。

## Docker 命令长什么样

`DockerExecutor.build_argv()` 生成（每个 flag 都有测试断言）：

```
docker run --rm --network none --user 1000:1000
  --cap-drop ALL --security-opt no-new-privileges
  --memory 512m --cpus 1.0 --pids-limit 256
  --mount type=bind,src=<工作区>,dst=/work -w /work
  python:3.12-slim sh -c "<命令>"
```

逐项理解：
- `--network none`：不可信执行断网（依赖安装在**可信准备阶段**
  `run_trusted_prep` 用 `--network bridge`，命令来自人写的配置）；
- `--user 1000:1000` + `--cap-drop ALL` + `no-new-privileges`：非 root、
  无 Linux capabilities、禁止提权；
- `--memory/--cpus/--pids-limit`：资源限额，fork bomb 会被 pids 限额掐死；
- 只挂载工作区，**不挂 docker.sock**（挂了等于给容器宿主控制权）；
- 不透传宿主环境变量（API key 进不了容器）；
- `--rm`：退出即清理。

## Docker 不可用怎么办

`run()` 先 `docker info` 探活；不可达 → 抛 `SandboxUnavailableError`，
CLI 打印明确错误。**绝不静默回退宿主执行**。此时只允许确定性 mock 测试
（`DemoExecutor` 零进程模拟 / 测试内可信执行器）。

## 实测证据

`tests/integration/test_docker_sandbox.py`（真实容器，7 项全过）：
uid=1000、断网连接失败、挂载可写、宿主 env 不泄漏、超时 kill、不可用显式报错。

## 常见失败场景

- `Docker daemon is not reachable` → 启动 Docker Desktop（WSL2 后端）。
- 容器内 `No module named pytest` → 基础镜像没装；用可信准备
  `pip install --target .deps pytest` + `PYTHONPATH=.deps`，或构建
  `safefix-sandbox` 镜像（根目录 Dockerfile）。
- 挂载目录权限问题（Linux）→ 容器 uid 1000 需对工作区可写。

## 如何修改与测试

改限额：`SandboxLimits(memory="1g", ...)`；离线契约测试
`tests/unit/test_docker_executor.py` 用 FakeSpawn 断言 argv，不需要真 Docker。
新增 flag 时先在该测试加断言（红），再改 `build_argv`（绿）。