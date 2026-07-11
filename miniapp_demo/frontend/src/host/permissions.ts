// 框架级权限申请:麦克风权限按顶层 origin 记录,框架统一申请一次即可覆盖所有小程序,
// 无需每个 app(iframe)各自弹窗。iframe 侧仍需 allow="microphone" 才被策略放行。

let micRequested = false;

export async function ensureMicPermission(): Promise<boolean> {
  try {
    // 已授权/已拒绝则直接返回,不再打扰用户。
    const perms = (navigator as any).permissions;
    if (perms && perms.query) {
      try {
        const status = await perms.query({ name: "microphone" as PermissionName });
        if (status.state === "granted") return true;
        if (status.state === "denied") return false;
      } catch {
        // 某些浏览器不支持查询 microphone,忽略,走 getUserMedia 兜底。
      }
    }
    if (micRequested) return true;
    micRequested = true;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return false;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    // 只为拿授权,拿到后立即释放设备。
    stream.getTracks().forEach((t) => t.stop());
    return true;
  } catch {
    return false;
  }
}
