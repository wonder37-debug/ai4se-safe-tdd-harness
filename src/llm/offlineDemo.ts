// 离线降级用的自修正 TDD 演示脚本：评审在不配置 Key 的情况下，
// 浏览器内即可完整观看「写 buggy 实现 → 跑测试失败(断言) → 修正 → 跑测试通过 → 结束」的纠错闭环。
// 与 demo/mechanism-demo.test.ts 第②幕同源，但此处由 loop 自行写入 add.js，无需测试预置。

// ponytail: \\n 在模板字面量里产出字面 backslash-n，shell 双引号透传给 node，
// node 的 JS 串解析为真换行——JestParser 的关键字正则对换行不敏感，故断言可被识别。
const CHECKER = `node -e "const a=require('./add.js');if(a(2,3)!==5){console.error('FAIL ./add.test.js\\n  expect(received).toBe(expected)\\n  at add.test.js:4:17');process.exit(1)}else process.exit(0)"`;

const act = (tool: string, args: Record<string, unknown>) =>
  '```action\n' + JSON.stringify({ tool, args }) + '\n```';

/** 供 ScriptedMock 逐轮吐出的动作序列：buggy → 测试失败 → 修正 → 测试通过 → finish。 */
export function offlineDemoActions(): string[] {
  return [
    act('write_file', { path: 'add.js', content: 'module.exports=(a,b)=>a-b;\n' }),
    act('run_tests', { command: CHECKER }),
    act('write_file', { path: 'add.js', content: 'module.exports=(a,b)=>a+b;\n' }),
    act('run_tests', { command: CHECKER }),
    act('finish', {}),
  ];
}
