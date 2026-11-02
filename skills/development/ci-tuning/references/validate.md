# validate：验证优化效果

依次核对四件事：任务覆盖、质量门禁、实际执行、前后耗时。全部有证据才算完成；缺哪一项就在报告里写明哪一项未验证。

## 1. 准备

- 改动前的数据：`.ci-tuning/<日期>-before/` 下的 `audit.json`、`runs.json`；有分片或测试选择改动时，还要有基线 JUnit 报告。
- 改动后的静态清单：`workflow_audit.py <项目根> --json .ci-tuning/<日期>-after/audit.json`。
- 缺少改动前数据时：用 `git worktree add <临时目录> <基线提交>` 取出旧版本，再对它运行 `workflow_audit.py`；运行数据用 `run_stats.py runs --until <日期>` 取改动合入前的时间段。

## 2. 任务覆盖

```sh
python3 <skill>/scripts/compare.py coverage before/audit.json after/audit.json \
  --required-from <owner>/<repo>:<默认分支>
```

- 以“分类:工具”为单位，比较每个检查在哪些事件（`pull_request`、`push`、`merge_group`、`schedule`）上运行。某个分类在某个事件上整体消失，直接判定失败。
- 已验证等价的工具替换（如 `lint:eslint` 换成 `lint:oxlint`），用 `--accept 'lint:eslint'` 标记，并在报告中附上等价证据。
- 每个必需检查在改动后都必须仍会产生。读不到分支保护时用 `--required <检查名>` 逐个传入，并说明来源。
- 检查名称的增减逐条说明；动态 Matrix 的名称只能近似比对，结论里注明。

## 3. 质量门禁

`compare.py coverage` 同时报告：

- 严格参数被移除：`--max-warnings=0`、`--strict`、`-D warnings`、`--frozen-lockfile`、`--locked`、`--check`、覆盖率阈值参数等。
- 新增的削弱写法：`continue-on-error`、`|| true`、`|| :`、`--passWithNoTests`、`set +e`。
- 必需检查所在的 workflow 新增了 `paths` 过滤。

另外用 `git diff` 检查 workflow 以外的门禁配置：覆盖率阈值（Jest/Vitest 配置、`.coveragerc`、`pyproject.toml` 的 `fail_under`）、lint 规则集、`tsconfig` 的严格选项、测试的 `include`/`exclude` 范围。任何放宽都需要用户明确同意。

## 4. 实际执行

1. **静态检查**：有 `actionlint` 时运行；没有时询问用户后再下载，或使用 `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:1.7.12`。
2. **真实运行**：征得用户同意后推送分支或更新 PR。所有 Job 成功；被跳过的 Job 都是预期的跳过。
3. **测试数量**：下载各分片的 JUnit 报告（`gh run download <run-id>`），与基线对比：

   ```sh
   python3 <skill>/scripts/compare.py tests --before base-junit/ --after after-junit/
   ```

   不允许出现遗漏、新增跳过或新失败；分片之间不应有重复。
4. **跳过逻辑**：启用了按改动运行时，提交一个映射会漏掉的改动或修改一个全局文件，确认触发全量运行或失败（`parallel.md` 第 8 节）。
5. **稳定性**：对同一提交重跑新流程至少 3 次（`gh run rerun <id>` 或 `workflow_dispatch`，先征得同意）。新增的失败要查根因，不用重试掩盖。
6. **缓存**：改了缓存时，第二次运行（lockfile 未变）应在日志中出现精确命中：`run_stats.py runs --logs 20` 查看 `cache` 统计。`run_stats.py caches` 确认默认分支上存在对应 key 族。

## 5. 前后耗时

1. 采集改动后的运行：最好有 10 次以上同类 PR 运行。PR 太少时，对有代表性的提交手动触发多次，并在报告中说明样本来源。
2. 只比较同类数据：相同事件（`pull_request`）、只取首次尝试、排除被取消的运行。`run_stats.py` 默认如此。
3. 运行对比：

   ```sh
   python3 <skill>/scripts/compare.py timing before/runs.json after/runs.json
   ```

4. 报告内容：提交级 wall-clock P50/P95（前→后，倍数）、各 workflow 的 P50/P95、关键链变化、主要 Job 的排队、setup、执行耗时、首跑失败率、flaky 运行（首跑失败、重跑通过）与重跑率、缓存命中、样本量与时间范围。任一侧样本少于 5 时，只能说明趋势。

## 6. 判定

同时满足以下条件才判定成功：

- 覆盖无丢失（工具替换已标记并有等价证据）。
- 门禁不弱于改动前。
- 真实运行全部通过，测试集合完整，跳过逻辑自检通过（如适用）。
- 提交级 P50 下降，P95 没有超出波动范围的回退，flaky 运行没有增加。PR 运行也会因代码本身有错而失败，所以首跑失败率上升只作提示；上升时对同一提交重跑至少 3 次，排除新增的 flaky。

任一项失败：说明原因，提出修正，或回退对应改动。

## 7. 记录

更新 CI.md 的“性能基线”（日期、样本量、P50/P95、关键路径）。原始数据留在 `.ci-tuning/`，不提交。
