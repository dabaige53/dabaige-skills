# Audience

本文件是项目内人员、角色与文档受众的唯一映射。AI 回复前以此确定读者和确认人；新增或调整时只改本文件。

## 角色

角色值是受控词表，回复和文档只使用这里登记的值。

| 角色 | 任务语境 | 经验水平 | 关注点与写法 |
| --- | --- | --- | --- |
| product-manager | evaluating | general | 目标、影响、风险与决策点；少讲实现细节 |
| developer | programming | expert | 改动范围、接口、命令与验证方式 |
| reviewer | reviewing | expert | 变更依据、风险点与验收标准 |

## 人员

| 人员 | 角色 | 备注 |
| --- | --- | --- |
| @示例姓名 | product-manager | 负责需求确认 |

## 文档受众

确认人是该类文档或回复需要获得确认的人；可填多人。

| 文档类型或路径 | 受众角色 | 确认人 |
| --- | --- | --- |
| 需求与方案 `docs/specs/` | product-manager, developer | @示例姓名 |
| 实现说明 `README.md` | developer | @示例姓名 |
| 进度汇报 | product-manager | @示例姓名 |
