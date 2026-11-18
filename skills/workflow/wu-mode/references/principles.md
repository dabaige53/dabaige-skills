# Principles

沿用 `poteto-mode` 入口中的原则名、分组与顺序。以下是 Wu 环境中的用法，不依赖外部 `principle-*` Skills。

## Core

- **Foundational Thinking**：先画清数据、所有者和先后依赖，再写逻辑。
- **Redesign from First Principles**：把新要求视为一开始就存在，比较当前设计与更简单的目标结构。
- **Attack the Premise**：两次修复被同一条件挡住时，先检验它们共用的假设。
- **Subtract Before You Add**：先移除确定无用的分支或重复路径，再决定是否需要新结构。
- **Minimize Reader Load**：简化需要读者同时记住的层次、隐含状态和例外。
- **Outcome-Oriented Execution**：迁移按可交付结果分段，不让仅用于过渡的路径永久并存。
- **Experience First**：产品取舍先比较用户实际体验，再比较实现成本。
- **Exhaust the Design Space**：确有多个可行方向时，用少量可比的原型拉开差异。
- **Build the Lever**：有重复操作或可重复测量的需要时，留下可以再次运行的工具。

## Architecture

- **Model the Domain**：用能表达业务状态的类型或数据结构代替散落的条件判断。
- **Type System Discipline**：让类型或构造过程排除不合法的组合。
- **Make Operations Idempotent**：可能重试的操作重复执行后仍得到同一个预期结果。
- **Migrate Callers Then Delete Legacy APIs**：先迁移所有实际使用方，再删除旧入口。
- **Separate Before Serializing Shared State**：先划分写入责任；确实共享的部分再安排先后。多端仍共用同一份业务状态。

## Verification

- **Prove It Works**：证据来自对应产物或用户入口。没有执行时写明未知。
- **Fix Root Causes**：沿症状找到第一个出错的位置，别在末端遮住问题。
- **Sequence Work into Verifiable Units**：一次交付一个可观察的变化，让下一步依赖明确的结果。
- **Explain the Number**：说明指标测到什么，排除输入、环境和工作量差异。

## Meta

- **Encode Lessons in Structure**：同一错误反复出现时，优先修订产生它的模板、数据结构或规则。
