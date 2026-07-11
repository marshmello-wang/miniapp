/*!
 * oneagent.js — app-skill v0.3 widget 侧 Bridge SDK
 *
 * 在小程序 iframe 内运行,通过 postMessage 与客户端运行时(Host)通信。
 * Host 负责把上行帧转发到 WebSocket 引擎,并把下行 app.event 回传给本 iframe。
 *
 * API:
 *   oneagent.data                      // 最近一次 ui_update 的 structuredContent
 *   oneagent.onUiUpdate(cb)            // 订阅 ui_update 事件 (cb(event))
 *   oneagent.onTrajectory(cb)         // 订阅 thinking/text/tool_call/tool_result (cb(event))
 *   oneagent.directAction(name, args, {onData,onDone,onTrajectory})  // 不经过 AI
 *   oneagent.agentAction(intent, focus, {onData,onDone,onTrajectory}) // 经过 AI
 *   oneagent.setEnv(fn)               // 提供当前界面状态,agentAction 时随包上报
 *   oneagent.transcribe(blob)         // 语音转文字,返回 Promise<string>
 *   oneagent.cancel(requestId)
 */
(function () {
  var handlers = { uiUpdate: [], trajectory: [] };
  var pending = {};
  var lastData = {};
  var envProvider = null;

  // 客户端运行时通过 ?device=desktop|mobile 注入当前预览设备
  var DEVICE = "desktop";
  try {
    DEVICE = new URLSearchParams(window.location.search).get("device") || "desktop";
  } catch (e) {}
  // 便于 CSS 按设备适配:<html data-device="mobile">
  try {
    document.documentElement.setAttribute("data-device", DEVICE);
  } catch (e) {}

  function post(frame) {
    parent.postMessage({ source: "oneagent", frame: frame }, "*");
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
    if (!msg || msg.source !== "oneagent-host" || !msg.frame) return;
    var frame = msg.frame;

    if (frame.data_type === "app.resource") {
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

  var oneagent = {
    device: DEVICE,
    get data() { return lastData; },
    onUiUpdate: function (cb) { handlers.uiUpdate.push(cb); },
    onTrajectory: function (cb) { handlers.trajectory.push(cb); },
    directAction: function (name, args, cbs) {
      var requestId = uuid();
      pending[requestId] = cbs || {};
      post({ data_type: "app.call", name: name, args: args || {}, requestId: requestId });
      return requestId;
    },
    agentAction: function (intent, focus, cbs) {
      var requestId = uuid();
      pending[requestId] = cbs || {};
      var env = collectEnv() || {};
      if (env.device == null) env.device = DEVICE; // 把当前设备并入 env 上报给 agent
      post({
        data_type: "app.agent",
        intent: intent,
        focus: focus || {},
        env: env,
        requestId: requestId,
      });
      return requestId;
    },
    setEnv: function (fn) { envProvider = fn; },
    cancel: function (requestId) { post({ data_type: "cancel", requestId: requestId }); },
    // 语音转文字:上传录音 blob 到后端 ASR,返回识别文本(Promise<string>)。
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

  window.oneagent = oneagent;
  post({ data_type: "app.init" });
})();
