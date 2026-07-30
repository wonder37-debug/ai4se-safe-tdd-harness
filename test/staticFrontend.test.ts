import http from 'http';
import { startWebServer } from '../src/web/webServer';
import { EventStore } from '../src/loop/eventSink';
import { HttpApprovalGateway } from '../src/approval/httpApprovalGateway';
import { EncryptedFileStore } from '../src/creds/credentialStore';
import { JsonConfigStore } from '../src/creds/configStore';
import * as os from 'os'; import * as fs from 'fs/promises'; import * as path from 'path';

// 始终 resolve 的 GET 采集器：断言失败也不会让 'end' 回调挂起（避免 RED 态句柄残留）
function get(port: number, p: string): Promise<{ status: number; body: string }> {
  return new Promise((resolve) => {
    const req = http.get(`http://localhost:${port}${p}`, (res) => {
      let b = '';
      res.on('data', (c) => (b += c));
      res.on('end', () => resolve({ status: res.statusCode ?? 0, body: b }));
    });
    req.on('error', () => resolve({ status: 0, body: '' }));
  });
}

async function boot() {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'fe-'));
  const srv = await startWebServer({
    port: 0, eventStore: new EventStore(), approval: new HttpApprovalGateway(),
    creds: new EncryptedFileStore(path.join(dir, 'c.enc')),
    config: new JsonConfigStore(path.join(dir, 'config.json')),
    loopFactory: async () => ({ haltReason: 'finish', iterations: 0 }),
  });
  return { srv, port: (srv.server.address() as any).port };
}

test('GET / serves index.html', async () => {
  const { srv, port } = await boot();
  try {
    const { status, body } = await get(port, '/');
    expect(status).toBe(200);
    expect(body).toContain('AI4SE-Safe-TDD-Harness');
  } finally { srv.server.close(); }
});

test('redesign: approval reason input + Deny & 反馈 served via /app.js', async () => {
  const { srv, port } = await boot();
  try {
    const { status, body } = await get(port, '/app.js');
    expect(status).toBe(200);
    // 人工审批卡片内的原因输入框（placeholder 明确为"补充指示或拒绝原因"）
    expect(body).toContain('补充指示或拒绝原因');
    // 拒绝按钮改为「Deny & 反馈」——拒绝时把输入框内容作为 reason 回灌
    expect(body).toContain('Deny');
    expect(body).toContain('反馈');
    // 拒绝时把输入框内容作为 reason 发送给后端（对话重定向）
    expect(body).toContain('reason');
    // 点击反馈：app.js 含 flash() 与 postWithFeedback()，按钮成功/失败可见
    expect(body).toContain('flash');
    expect(body).toContain('postWithFeedback');
    expect(body).toContain('is-flash-ok');
    expect(body).toContain('is-flash-fail');
  } finally { srv.server.close(); }
});

test('事件流增强：app.js 含 thought 气泡渲染 + 等待提示 + Emoji 动作翻译，废除裸 JSON', async () => {
  const { srv, port } = await boot();
  try {
    const { status, body } = await get(port, '/app.js');
    expect(status).toBe(200);
    // thought 事件分支与思考气泡样式类
    expect(body).toContain('thought');
    expect(body).toContain('event--thought');
    // 启动循环后的"等待大模型响应"驻留提示
    expect(body).toContain('等待大模型响应');
    // Action 翻译为带 Emoji 的自然语言短句（对齐 CLI）
    expect(body).toContain('📄');
    expect(body).toContain('写入文件');
    expect(body).toContain('🧪');
    expect(body).toContain('运行测试');
    // Observation 成功/失败带 Emoji
    expect(body).toContain('✅');
    expect(body).toContain('❌');
    // 废除裸露 JSON：默认分支不再 JSON.stringify(payload) 打印
    expect(body).not.toContain('JSON.stringify(ev.payload)');
  } finally { srv.server.close(); }
});

test('事件流增强：index.html 含等待提示横幅容器', async () => {
  const { srv, port } = await boot();
  try {
    const { status, body } = await get(port, '/');
    expect(status).toBe(200);
    expect(body).toContain('id="waitBanner"');
  } finally { srv.server.close(); }
});

test('端点配置：index.html 含 API_KEY 标签与 baseurl/model 输入框', async () => {
  const { srv, port } = await boot();
  try {
    const { status, body } = await get(port, '/');
    expect(status).toBe(200);
    // 标签由 CLAUDE_API_KEY 改为 API_KEY
    expect(body).not.toContain('CLAUDE_API_KEY');
    expect(body).toContain('API_KEY');
    // 新增请求地址 / 模型输入框
    expect(body).toContain('id="baseurl"');
    expect(body).toContain('id="model"');
    // 提示使用 OpenAI 兼容格式
    expect(body).toContain('OpenAI');
  } finally { srv.server.close(); }
});
