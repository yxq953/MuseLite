# Skill 创建接口

调用 `skill_create`：

```json
{
  "content": "---\nname: meeting-summary\ndescription: 将用户提供的会议记录整理为决策和行动项。当用户需要总结会议时使用。\n---\n\n整理讨论主题、已确认决策和行动项。负责人或期限未知时标注待确认，不编造内容。输出格式参照 references/output.md。\n",
  "files": [
    {
      "path": "references/output.md",
      "content": "# 输出结构\n主题、决策、行动项（事项、负责人、期限）。\n",
      "encoding": "utf-8"
    }
  ]
}
```

`content` 是完整 `SKILL.md`。`files` 可省略，每项包含 Skill 内相对路径与文件内容；文本使用 `utf-8`（默认），真实二进制模板可以使用 `base64`。不要编造二进制素材。路径不能绝对定位、越界或重复，不能再提交一个 `SKILL.md`。支持最多 200 个文件，单文件不超过 5 MB、总计不超过 20 MB；文本读取与编辑不超过 1 MB。

成功后新技能立即启用。调用 `skill_load` 的 `name` 参数加载说明，再按需通过 `skill_read` 的 `name` 和 `path` 读取参考文件。资源路径和脚本运行路径由 `skill_load` 返回的 `base_path` 解析。

脚本需要 Python、其他软件包或网络时，在 Skill 中说明真实依赖；Android 沙箱默认只有最小 Alpine，不默认提供 Python。依赖不可用时报告情况，不假装脚本已执行。
