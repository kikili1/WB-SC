#!/usr/bin/env node
/**
 * 通过 Chrome DevTools Protocol 写入 WorkBuddy 桌面端的快捷键覆盖值。
 *
 * 前提：应用以 --remote-debugging-port=<port> 启动。
 * 用法：node cdp_inject.mjs --port 9222 --id toggle-voice-recording --binding Alt+Shift+P [--reload]
 */

const STORAGE_KEY = "agent-ui-keyboard-shortcuts";

function parseArgs(argv) {
  const out = { reload: false };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--reload") out.reload = true;
    else if (a.startsWith("--")) out[a.slice(2)] = argv[++i];
  }
  return out;
}

const args = parseArgs(process.argv);
const port = Number(args.port || 9222);
const id = args.id;
const binding = args.binding;

if (!id || !binding) {
  console.error("缺少 --id 或 --binding");
  process.exit(2);
}

async function getPageTarget() {
  const res = await fetch(`http://127.0.0.1:${port}/json/list`);
  const targets = await res.json();
  const pages = targets.filter((t) => t.type === "page" && t.webSocketDebuggerUrl);
  const app = pages.find((t) => !/devtools/i.test(t.url));
  return app || pages[0] || null;
}

function evaluate(ws, expression, msgId) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("CDP 超时")), 8000);
    const onMessage = (ev) => {
      let msg;
      try {
        msg = JSON.parse(typeof ev.data === "string" ? ev.data : ev.data.toString());
      } catch {
        return;
      }
      if (msg.id === msgId) {
        clearTimeout(timer);
        ws.removeEventListener("message", onMessage);
        if (msg.error) reject(new Error(JSON.stringify(msg.error)));
        else resolve(msg.result);
      }
    };
    ws.addEventListener("message", onMessage);
    ws.send(JSON.stringify({
      id: msgId,
      method: "Runtime.evaluate",
      params: { expression, returnByValue: true, awaitPromise: true },
    }));
  });
}

const injectExpr = `(() => {
  const KEY = ${JSON.stringify(STORAGE_KEY)};
  let cur = { version: 1, overrides: {} };
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) cur = JSON.parse(raw) || cur;
  } catch (e) {}
  cur.version = cur.version || 1;
  cur.overrides = cur.overrides || {};
  const previous = cur.overrides[${JSON.stringify(id)}] || null;
  cur.overrides[${JSON.stringify(id)}] = { mac: ${JSON.stringify(binding)}, win: ${JSON.stringify(binding)} };
  localStorage.setItem(KEY, JSON.stringify(cur));
  return JSON.stringify({ ok: true, previous, now: cur.overrides[${JSON.stringify(id)}] });
})()`;

(async () => {
  const target = await getPageTarget();
  if (!target) {
    console.error("未找到可注入的页面 target。");
    process.exit(3);
  }
  console.log("target:", target.url);

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", () => reject(new Error("WebSocket 连接失败")), { once: true });
  });

  const result = await evaluate(ws, injectExpr, 1);
  const value = result?.result?.value ?? "(无返回值)";
  console.log("inject:", value);

  if (args.reload) {
    try {
      ws.send(JSON.stringify({ id: 2, method: "Page.reload", params: { ignoreCache: false } }));
      console.log("已请求页面重载，等待新值生效。");
      await new Promise((r) => setTimeout(r, 800));
    } catch (e) {
      console.log("重载请求失败，请手动重载窗口：", e.message);
    }
  } else {
    console.log("未重载页面；请手动重载窗口（Ctrl+R）后生效。");
  }
  ws.close();
  process.exit(0);
})().catch((e) => {
  console.error("注入失败：", e.message);
  process.exit(4);
});
