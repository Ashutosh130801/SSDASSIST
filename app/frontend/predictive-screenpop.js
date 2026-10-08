/* Event-driven screen-pop. Dialer state is queried only on connect/focus/recovery. */
(function (root) {
  function createWatcher({ request, subscribe, onStatus, onCall, seen, remember,
    schedule = setTimeout, cancel = clearTimeout, isVisible = () => !document.hidden }) {
    let stopped = false, running = false, timer = null, controller = null, failures = 0, socket = null, pending = null;
    async function drain() {
      if (stopped || running) return;
      cancel(timer);
      if (!isVisible() || !pending) return;
      const task = pending; pending = null;
      running = true;
      controller = new AbortController();
      const deadline = schedule(() => controller && controller.abort(), 10000);
      let delay = 0;
      try {
        const path = task === 'reconcile' ? '/api/integration/vicidial/my-live-call' : '/api/integration/vicidial/events/' + encodeURIComponent(task);
        const live = await request(path, { signal: controller.signal });
        if (stopped) return;
        if (live.state === 'expired') return;
        onStatus(live);
        if (live.state === 'error') throw new Error(live.detail || 'Dialer recovery failed');
        if (live.state === 'connected' && live.event_id && live.case_id && !seen.has(live.event_id)) {
          // Only mark delivered after the scoped detail fetch AND UI delivery succeed.
          const c = await request('/api/cases/' + live.case_id, { signal: controller.signal });
          if (stopped) return;
          if (!isVisible()) { pending = pending || 'reconcile'; return; }
          onCall(c, live);
          seen.add(live.event_id);
          while (seen.size > 100) seen.delete(seen.values().next().value);
          remember(Array.from(seen));
        }
        failures = 0;
      } catch (err) {
        if (!stopped) {
          failures += 1;
          delay = Math.min(30000, 2000 * Math.pow(2, Math.min(failures, 4)));
          const retryable = ![400, 401, 403, 404, 409, 422].includes(err.status);
          if (retryable) pending = pending || task;
          onStatus({ state: 'error', detail: 'Screen-pop could not refresh or open the case. ' + (retryable ? 'Retrying automatically. ' : 'Check access/mapping with your administrator. ') + (err.name === 'AbortError' ? 'Request timed out.' : (err.message || 'Check your connection.')) });
        }
      } finally {
        cancel(deadline);
        controller = null;
        running = false;
        if (!stopped && pending && isVisible()) timer = schedule(drain, delay);
      }
    }
    function poll() { pending = 'reconcile'; return drain(); }
    function receive(e) {
      try {
        const message = JSON.parse(e.data);
        if (message.type === 'predictive_screenpop' && /^[a-f0-9]{64}$/.test(message.event_id) && !seen.has(message.event_id)) {
          pending = message.event_id;
          drain();
        }
      } catch (_) {}
    }
    return { poll, receive, start() {
      if (socket || stopped) return;
      socket = subscribe({ onOpen: poll, onMessage: receive,
        onClose: () => { if (!stopped) onStatus({ state: 'error', detail: 'Live connection interrupted. Reconnecting automatically; call details will be checked on reconnect.' }); } });
    }, stop() { stopped = true; pending = null; cancel(timer); if (controller) controller.abort(); if (socket) socket.close(); } };
  }
  root.RecoverIQPredictive = { createWatcher };
  if (typeof module !== 'undefined' && module.exports) module.exports = root.RecoverIQPredictive;
})(typeof window !== 'undefined' ? window : globalThis);
