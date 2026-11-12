import Foundation

/// JavaScript injected into the RecoverIQ page before it runs (document start).
///  • exposes `window.RIQNative` — the bridge the web app uses (tracking, files, settings),
///  • restores the device id / session kept by the native side if the WebView lost them,
///  • replaces `navigator.geolocation` with native Core Location (no repeated web prompts).
enum Bootstrap {
    static func script() -> String {
        let saved: [String: Any] = [
            "token": NativeStore.token,
            "device": NativeStore.deviceId,
            "user": NativeStore.userJSON,
            "version": AppInfo.version,
            "build": AppInfo.build,
        ]
        let json = (try? JSONSerialization.data(withJSONObject: saved)).flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
        return "(function(){var S=" + json + ";" + body + "})();"
    }

    private static let body = #"""
try {
  if (S.device && !localStorage.getItem('ssd_device')) localStorage.setItem('ssd_device', S.device);
  if (S.token && !localStorage.getItem('ssd_token')) {
    localStorage.setItem('ssd_token', S.token);
    if (S.user && !localStorage.getItem('ssd_user')) localStorage.setItem('ssd_user', S.user);
  }
} catch (e) {}
var post = function (m) { try { window.webkit.messageHandlers.riq.postMessage(m); } catch (e) {} };
var cbs = {}, keep = {}, seq = 0;
window.__riqCb = function (id, data) {
  var f = cbs[id]; if (!f) return;
  if (!keep[id]) delete cbs[id];
  try { f(data); } catch (e) {}
};
function call(cmd, args) {
  return new Promise(function (res) {
    var id = ++seq; cbs[id] = res;
    var m = { cmd: cmd, id: id }; for (var k in (args || {})) m[k] = args[k];
    post(m);
  });
}
window.RIQNative = { platform: 'ios', version: S.version, build: S.build, post: post, call: call };

// ---- navigator.geolocation backed by native Core Location ----
var ERR = { PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 };
function mkErr(r) { var e = { code: (r && r.code) || 2, message: (r && r.message) || 'Location unavailable' };
  for (var k in ERR) e[k] = ERR[k]; return e; }
function mkPos(r) { return { coords: r.coords, timestamp: r.timestamp }; }
var geo = {
  getCurrentPosition: function (ok, fail, o) {
    o = o || {}; var done = false, t = null;
    if (o.timeout && isFinite(o.timeout)) t = setTimeout(function () {
      if (done) return; done = true; fail && fail(mkErr({ code: 3, message: 'Timeout' })); }, Math.max(o.timeout, 1000));
    call('geo', { op: 'get', maxAge: o.maximumAge || 0 }).then(function (r) {
      if (done) return; done = true; if (t) clearTimeout(t);
      if (r && r.ok) { ok && ok(mkPos(r)); } else { fail && fail(mkErr(r)); }
    });
  },
  watchPosition: function (ok, fail) {
    var id = ++seq; keep[id] = 1;
    cbs[id] = function (r) { if (r && r.ok) { ok && ok(mkPos(r)); } else { fail && fail(mkErr(r)); } };
    post({ cmd: 'geo', op: 'watch', id: id });
    return id;
  },
  clearWatch: function (id) { delete cbs[id]; delete keep[id]; post({ cmd: 'geo', op: 'clear', id: id }); }
};
try { Object.defineProperty(navigator, 'geolocation', { value: geo, configurable: true }); } catch (e) {}
"""#
}
