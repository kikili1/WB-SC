#!/usr/bin/env node
import { pathToFileURL } from 'node:url';

const STORAGE_KEY = 'agent-ui-keyboard-shortcuts';

export function mergeOverride(current, id, binding, platform) {
  if (!['mac', 'win'].includes(platform)) throw new Error('无效平台');
  if (['toggle-window', 'send-message'].includes(id)) {
    throw new Error('该动作需要内部 IPC/事件桥，请使用设置界面');
  }
  if (!current || typeof current !== 'object' || Array.isArray(current) ||
      (current.overrides != null && (typeof current.overrides !== 'object' || Array.isArray(current.overrides)))) {
    throw new Error('现有快捷键配置无效，已中止');
  }
  const previous = current.overrides?.[id];
  if (previous != null && (typeof previous !== 'object' || Array.isArray(previous))) {
    throw new Error('现有动作覆盖值无效，已中止');
  }
  return { ...current, version: current.version || 1,
    overrides: { ...current.overrides, [id]: { ...previous, [platform]: binding } } };
}

function parseArgs(argv) {
  const out = { reload: false };
  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--reload') out.reload = true;
    else if (arg.startsWith('--')) out[arg.slice(2)] = argv[++i];
  }
  return out;
}

async function connect(port) {
  const response = await fetch(`http://127.0.0.1:${port}/json/list`, { signal: AbortSignal.timeout(5000) });
  if (!response.ok) throw new Error('无法读取 CDP 页面列表');
  const targets = (await response.json()).filter(t => t.type === 'page' && t.webSocketDebuggerUrl &&
    !/devtools/i.test(t.url) && /workbuddy/i.test(`${t.url} ${t.title}`));
  if (targets.length !== 1) throw new Error('无法唯一确认 WorkBuddy 页面，请使用设置界面');
  const ws = new WebSocket(targets[0].webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => { ws.close(); reject(new Error('CDP 连接超时')); }, 5000);
    ws.addEventListener('open', () => { clearTimeout(timer); resolve(); }, { once: true });
    ws.addEventListener('error', () => { clearTimeout(timer); reject(new Error('CDP 连接失败')); }, { once: true });
  });
  return ws;
}

let msgId = 0;
function call(ws, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++msgId;
    const cleanup = () => { clearTimeout(timer); ws.removeEventListener('message', onMessage); };
    const timer = setTimeout(() => { cleanup(); reject(new Error('CDP 超时')); }, 8000);
    const onMessage = event => {
      let message;
      try { message = JSON.parse(event.data.toString()); } catch { return; }
      if (message.id !== id) return;
      cleanup();
      if (message.error || message.result?.exceptionDetails) {
        reject(new Error(JSON.stringify(message.error || message.result.exceptionDetails)));
      } else resolve(message.result);
    };
    ws.addEventListener('message', onMessage);
    try { ws.send(JSON.stringify({ id, method, params })); }
    catch (error) { cleanup(); reject(error); }
  });
}

const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

export async function main(argv = process.argv) {
  const args = parseArgs(argv);
  const platform = args.platform || (process.platform === 'darwin' ? 'mac' : 'win');
  if (!args.id || !args.binding) throw new Error('缺少 --id 或 --binding');
  mergeOverride({}, args.id, args.binding, platform);
  if (typeof fetch !== 'function' || typeof WebSocket !== 'function') {
    throw new Error('需要支持内置 fetch/WebSocket 的 Node.js（建议 22+），或使用设置界面');
  }
  const port = Number(args.port || 9222);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('无效 CDP 端口');
  let ws = await connect(port);
  try {
    const expression = `(() => {
      const key = ${JSON.stringify(STORAGE_KEY)};
      const current = JSON.parse(localStorage.getItem(key) || '{"version":1,"overrides":{}}');
      const next = (${mergeOverride.toString()})(current, ${JSON.stringify(args.id)},
        ${JSON.stringify(args.binding)}, ${JSON.stringify(platform)});
      localStorage.setItem(key, JSON.stringify(next));
      return next;
    })()`;
    const written = await call(ws, 'Runtime.evaluate', { expression, returnByValue: true });
    const expected = written.result.value;
    if (args.reload) {
      await call(ws, 'Page.reload', { ignoreCache: false });
      ws.close();
      await pause(1500);
      ws = await connect(port);
    }
    for (let attempt = 0; attempt < 3; attempt++) {
      await pause(500);
      const checked = await call(ws, 'Runtime.evaluate', {
        expression: `JSON.parse(localStorage.getItem(${JSON.stringify(STORAGE_KEY)}))`, returnByValue: true,
      });
      if (JSON.stringify(checked.result.value) !== JSON.stringify(expected)) {
        throw new Error('重载/回读值与写入值不一致，可能被云端覆盖；请使用设置界面');
      }
    }
    console.log(args.reload ? '已写入并在重载后回读验证；后续云同步仍可能覆盖。' :
      '已写入并回读；尚未重载，不能确认实际生效。');
  } finally {
    ws.close();
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => { console.error('注入失败：', error.message); process.exitCode = 1; });
}
