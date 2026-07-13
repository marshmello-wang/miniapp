/*!
 * miniapp.js — app-skill v0.3 widget 侧 Bridge SDK
 *
 * 在小程序 iframe 内运行,通过 postMessage 与客户端运行时(Host)通信。
 * Host 负责把上行帧 POST 到引擎,并把本次 Action 的 SSE 响应回传给本 iframe。
 *
 * API:
 *   miniapp.data                      // 最近一次 ui_update 的 structuredContent
 *   miniapp.onUiUpdate(cb)            // 订阅 ui_update 事件 (cb(event))
 *   miniapp.onTrajectory(cb)         // 订阅 thinking/text/tool_call/tool_result (cb(event))
 *   miniapp.directAction(name, args, {onData,onDone,onTrajectory})  // 不经过 AI
 *   miniapp.agentAction(intent, focus, {onData,onDone,onTrajectory}) // 经过 AI
 *   miniapp.setEnv(fn)               // 提供当前界面状态,agentAction 时随包上报
 *   miniapp.getHistory()              // 获取当前 session 的对话历史,返回 Promise<[{role,content}]>
 *   miniapp.transcribe(blob)         // 语音转文字,返回 Promise<string>
 *   miniapp.cancel(requestId)
 */
(function () {
  var handlers = { uiUpdate: [], trajectory: [], init: [] };
  var pending = {};
  var lastData = {};
  var envProvider = null;
  var appId = null;

  var _params;
  try { _params = new URLSearchParams(window.location.search); } catch (e) { _params = null; }

  // 客户端运行时通过 ?device=desktop|mobile 注入当前预览设备
  var DEVICE = (_params && _params.get("device")) || "desktop";
  // 便于 CSS 按设备适配:<html data-device="mobile">
  try {
    document.documentElement.setAttribute("data-device", DEVICE);
  } catch (e) {}

  // 共享 session: overlay 通过 ?sessionId=xxx 传入 chat session
  var SESSION_ID = (_params && _params.get("sessionId")) || null;

  function post(frame) {
    parent.postMessage({ source: "miniapp", frame: frame }, "*");
  }

  function uuid() {
    return "req_" + Math.random().toString(36).slice(2, 10);
  }

  function collectEnv() {
    try {
      return envProvider ? envProvider() : {};
    } catch (e) {
      return {};
    }
  }

  window.addEventListener("message", function (e) {
    var msg = e.data;
    if (!msg || msg.source !== "miniapp-host" || !msg.frame) return;
    var frame = msg.frame;

    if (frame.data_type === "app.resource") {
      try { appId = frame.data.app.id; } catch (e) {}
      var onInit = frame.data && frame.data.app && frame.data.app.on_init;
      if (onInit && onInit.user_message) {
        setTimeout(function () {
          var msg = onInit.user_message;
          if (handlers.init.length > 0) {
            handlers.init.forEach(function (cb) { cb(msg); });
          } else {
            miniapp.agentAction(msg, {});
          }
        }, 0);
      }
      return;
    }
    if (frame.data_type !== "app.event") return;

    var d = frame.data;
    var type = d.type;
    var reqId = d.requestId;
    var p = pending[reqId];

    if (type === "ui_update") {
      lastData = (d.payload && d.payload.structuredContent) || {};
      handlers.uiUpdate.forEach(function (cb) { cb(d); });
      if (p && p.onData) p.onData(d);
    } else if (type === "done") {
      if (p && p.onDone) p.onDone(d);
      delete pending[reqId];
    } else {
      handlers.trajectory.forEach(function (cb) { cb(d); });
      if (p && p.onTrajectory) p.onTrajectory(d);
    }
  });

  var miniapp = {
    device: DEVICE,
    get data() { return lastData; },
    onUiUpdate: function (cb) { handlers.uiUpdate.push(cb); },
    onTrajectory: function (cb) { handlers.trajectory.push(cb); },
    onInit: function (cb) { handlers.init.push(cb); },
    directAction: function (name, args, cbs) {
      var requestId = uuid();
      pending[requestId] = cbs || {};
      var f = { data_type: "app.call", name: name, args: args || {}, requestId: requestId };
      if (SESSION_ID) f.sessionId = SESSION_ID;
      post(f);
      return requestId;
    },
    agentAction: function (intent, focus, cbs) {
      var requestId = uuid();
      pending[requestId] = cbs || {};
      var env = collectEnv() || {};
      if (env.device == null) env.device = DEVICE; // 把当前设备并入 env 上报给 agent
      var af = {
        data_type: "app.agent",
        intent: intent,
        focus: focus || {},
        env: env,
        requestId: requestId,
      };
      if (SESSION_ID) af.sessionId = SESSION_ID;
      post(af);
      return requestId;
    },
    setEnv: function (fn) { envProvider = fn; },
    cancel: function (requestId) { post({ data_type: "cancel", requestId: requestId }); },
    getHistory: function () {
      if (!appId) return Promise.resolve([]);
      var url = "/api/apps/" + encodeURIComponent(appId) + "/history";
      if (SESSION_ID) url += "?sessionId=" + encodeURIComponent(SESSION_ID);
      return fetch(url)
        .then(function (r) { return r.ok ? r.json() : []; })
        .catch(function () { return []; });
    },
    transcribe: function (blob, filename) {
      var form = new FormData();
      form.append("audio", blob, filename || "audio.webm");
      return fetch("/api/asr", { method: "POST", body: form }).then(function (r) {
        if (!r.ok) {
          return r.json().catch(function () { return {}; }).then(function (j) {
            throw new Error((j && j.detail) || ("ASR " + r.status));
          });
        }
        return r.json();
      }).then(function (j) { return (j && j.text) || ""; });
    },
  };

  window.miniapp = miniapp;
  var initFrame = { data_type: "app.init", requestId: uuid() };
  if (SESSION_ID) initFrame.sessionId = SESSION_ID;
  post(initFrame);
})();
