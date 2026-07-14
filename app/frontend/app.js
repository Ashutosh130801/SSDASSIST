/* SSD Recovery - compiled from app.jsx, do not edit directly */
const {
  useState,
  useEffect,
  useRef,
  useCallback
} = React;

/* ============================== helpers ============================== */
const store = {
  get t() {
    try {
      return localStorage.getItem('ssd_token');
    } catch {
      return null;
    }
  },
  set t(v) {
    try {
      v ? localStorage.setItem('ssd_token', v) : localStorage.removeItem('ssd_token');
    } catch {}
  },
  get u() {
    try {
      return JSON.parse(localStorage.getItem('ssd_user') || 'null');
    } catch {
      return null;
    }
  },
  set u(v) {
    try {
      v ? localStorage.setItem('ssd_user', JSON.stringify(v)) : localStorage.removeItem('ssd_user');
    } catch {}
  }
};
async function api(path, {
  method,
  body,
  form,
  auth = true
} = {}) {
  const headers = {};
  if (auth && store.t) headers['Authorization'] = 'Bearer ' + store.t;
  // A request carrying a body must be POST — a GET+body throws in Firefox.
  const httpMethod = method || (body || form ? 'POST' : 'GET');
  const opts = {
    method: httpMethod,
    headers
  };
  if (form) {
    opts.body = form;
  } else if (body) {
    headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (res.status === 401) {
    store.t = null;
    store.u = null;
    location.reload();
    throw new Error('unauthorized');
  }
  const ct = res.headers.get('content-type') || '';
  if (!res.ok) {
    let msg = res.statusText;
    if (ct.includes('json')) {
      try {
        msg = (await res.json()).detail || msg;
      } catch {}
    }
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  if (ct.includes('json')) return res.json();
  return res;
}
const INR = n => '₹' + Number(n || 0).toLocaleString('en-IN', {
  maximumFractionDigits: 0
});
const INR2 = n => '₹' + Number(n || 0).toLocaleString('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
});
const cx = (...a) => a.filter(Boolean).join(' ');
const initials = name => (name || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
let _toast;
function Toaster() {
  const [msg, setMsg] = useState(null);
  _toast = (text, kind = 'ok') => {
    setMsg({
      text,
      kind
    });
    setTimeout(() => setMsg(null), 2600);
  };
  if (!msg) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: cx('toast', msg.kind)
  }, msg.text);
}
const toast = (t, k) => _toast && _toast(t, k);

/* Google Maps loader (singleton) */
let _mapsPromise = null;
function loadMaps(key) {
  if (window.google && window.google.maps) return Promise.resolve(window.google);
  if (_mapsPromise) return _mapsPromise;
  _mapsPromise = new Promise((resolve, reject) => {
    if (!key) {
      reject(new Error('no-key'));
      return;
    }
    const s = document.createElement('script');
    s.src = `https://maps.googleapis.com/maps/api/js?key=${key}&loading=async`;
    s.async = true;
    s.onload = () => resolve(window.google);
    s.onerror = reject;
    document.head.appendChild(s);
  });
  return _mapsPromise;
}
function getGPS(opts = {}) {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error('Geolocation unavailable'));
    navigator.geolocation.getCurrentPosition(p => resolve(p.coords), reject, {
      enableHighAccuracy: true,
      timeout: 12000,
      maximumAge: 0,
      ...opts
    });
  });
}

/* Chart.js wrapper */
function Chart({
  type,
  data,
  options,
  height = 240
}) {
  const ref = useRef(null);
  const chart = useRef(null);
  useEffect(() => {
    if (!ref.current || !window.Chart) return;
    try {
      chart.current = new window.Chart(ref.current, {
        type,
        data,
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              labels: {
                color: '#C9C0AB',
                font: {
                  family: 'Hanken Grotesk'
                }
              }
            }
          },
          scales: type === 'doughnut' || type === 'pie' ? {} : {
            x: {
              ticks: {
                color: '#8C846F'
              },
              grid: {
                color: 'rgba(255,255,255,.05)'
              }
            },
            y: {
              ticks: {
                color: '#8C846F'
              },
              grid: {
                color: 'rgba(255,255,255,.05)'
              }
            }
          },
          ...options
        }
      });
    } catch (e) {
      console.error('Chart render failed:', e);
    }
    return () => {
      try {
        chart.current && chart.current.destroy();
      } catch (e) {}
    };
  }, [JSON.stringify(data), type]);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      height
    }
  }, /*#__PURE__*/React.createElement("canvas", {
    ref: ref
  }));
}
const GOLD = '#E9C877',
  GOLD2 = '#B8893A';
const PALETTE = ['#E9C877', '#6BB6F0', '#5FD08A', '#F0776B', '#C79A45', '#9b8cf0', '#F0C05A'];

/* ============================== Login ============================== */
function Login({
  onLogin,
  config
}) {
  const [email, setEmail] = useState('');
  const [pw, setPw] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async e => {
    e && e.preventDefault();
    setErr('');
    setBusy(true);
    try {
      const r = await api('/api/auth/login-json', {
        auth: false,
        body: {
          email,
          password: pw
        }
      });
      store.t = r.access_token;
      store.u = r.user;
      onLogin(r.user);
    } catch (ex) {
      setErr(ex.message || 'Login failed');
    } finally {
      setBusy(false);
    }
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "login"
  }, /*#__PURE__*/React.createElement("div", {
    className: "login-art glass",
    style: {
      borderRadius: 0,
      border: 'none'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "orb a"
  }), /*#__PURE__*/React.createElement("div", {
    className: "orb b"
  }), /*#__PURE__*/React.createElement("div", {
    className: "brand",
    style: {
      padding: 0
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: "assets/logo.png",
    alt: ""
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "n brandfont"
  }, "SSD Enterprises"), /*#__PURE__*/React.createElement("div", {
    className: "s"
  }, "Collections & Recovery"))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, "Command Centre"), /*#__PURE__*/React.createElement("div", {
    className: "big"
  }, "Every case tracked.", /*#__PURE__*/React.createElement("br", null), "Every rupee recovered."), /*#__PURE__*/React.createElement("p", {
    style: {
      color: 'var(--ink-soft)',
      maxWidth: 420,
      marginTop: 18,
      lineHeight: 1.6
    }
  }, "One system for admins, field officers and telecallers across ICICI, RBL and Axis — live maps, automatic allocation and clean, reliable numbers.")), /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 12
    }
  }, "© SSD Enterprises")), /*#__PURE__*/React.createElement("div", {
    className: "login-form"
  }, /*#__PURE__*/React.createElement("form", {
    className: "login-card glass",
    onSubmit: submit
  }, /*#__PURE__*/React.createElement("div", {
    className: "brand",
    style: {
      padding: '0 0 14px'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: "assets/logo.png",
    alt: "",
    style: {
      width: 38,
      height: 38
    }
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "n brandfont",
    style: {
      fontSize: 16
    }
  }, "SSD Recovery"), /*#__PURE__*/React.createElement("div", {
    className: "s"
  }, "Sign in"))), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Email"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    type: "email",
    value: email,
    autoComplete: "username",
    onChange: e => setEmail(e.target.value),
    placeholder: "you@ssdrecovery.in",
    required: true
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Password"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    type: "password",
    value: pw,
    autoComplete: "current-password",
    onChange: e => setPw(e.target.value),
    placeholder: "••••••••",
    required: true
  })), err && /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--bad)',
      fontSize: 13,
      marginBottom: 10
    }
  }, err), /*#__PURE__*/React.createElement("button", {
    className: "btn gold block",
    disabled: busy
  }, busy ? 'Signing in…' : 'Sign in'), config && config.google_client_id ? /*#__PURE__*/React.createElement("div", {
    id: "gbtn",
    style: {
      marginTop: 14,
      display: 'flex',
      justifyContent: 'center'
    }
  }) : null, /*#__PURE__*/React.createElement("div", {
    className: "divider"
  }), /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 12,
      lineHeight: 1.7
    }
  }, "Demo logins — admin@ssdrecovery.in / admin123 · ravi@ssdrecovery.in / fos123 · krishna@ssdrecovery.in / tc123"))));
}

/* ============================== shared bits ============================== */
function StatusBadge({
  s
}) {
  const map = {
    paid: 'paid',
    unpaid: 'unpaid',
    new: 'new',
    allocated: 'allocated',
    ptp: 'ptp',
    in_progress: 'partial'
  };
  return /*#__PURE__*/React.createElement("span", {
    className: cx('badge', map[s] || 'new')
  }, (s || '—').replace('_', ' '));
}
function PaidBadge({
  s
}) {
  const k = (s || 'UNPAID').toLowerCase();
  return /*#__PURE__*/React.createElement("span", {
    className: cx('badge', k.includes('unpaid') ? 'unpaid' : k.includes('partial') ? 'partial' : 'paid')
  }, s || 'UNPAID');
}
function Loader() {
  return /*#__PURE__*/React.createElement("div", {
    className: "spin"
  });
}

/* ============================== Dashboard ============================== */
function Dashboard({
  user
}) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    api('/api/analytics/dashboard').then(setD).catch(e => setErr(e.message));
  }, []);
  if (err) return /*#__PURE__*/React.createElement("div", {
    className: "glass card",
    style: {
      color: 'var(--bad)'
    }
  }, err);
  if (!d) return /*#__PURE__*/React.createElement(Loader, null);
  const k = d.kpis;
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "kpis"
  }, /*#__PURE__*/React.createElement("div", {
    className: "glass kpi"
  }, /*#__PURE__*/React.createElement("div", {
    className: "l"
  }, "Total Cases"), /*#__PURE__*/React.createElement("div", {
    className: "v"
  }, k.total_cases), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, k.paid, " paid · ", k.unpaid, " unpaid")), /*#__PURE__*/React.createElement("div", {
    className: "glass kpi"
  }, /*#__PURE__*/React.createElement("div", {
    className: "l"
  }, "Target"), /*#__PURE__*/React.createElement("div", {
    className: "v"
  }, INR(k.target)), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, "committed / funding")), /*#__PURE__*/React.createElement("div", {
    className: "glass kpi"
  }, /*#__PURE__*/React.createElement("div", {
    className: "l"
  }, "Recovered"), /*#__PURE__*/React.createElement("div", {
    className: "v",
    style: {
      color: 'var(--good)'
    }
  }, INR(k.received)), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, k.recovery_rate, "% recovery rate")), /*#__PURE__*/React.createElement("div", {
    className: "glass kpi"
  }, /*#__PURE__*/React.createElement("div", {
    className: "l"
  }, "Pending"), /*#__PURE__*/React.createElement("div", {
    className: "v",
    style: {
      color: 'var(--warn)'
    }
  }, INR(k.pending)), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, k.partial, " partial"))), /*#__PURE__*/React.createElement("div", {
    className: "grid2",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "glass card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-h"
  }, /*#__PURE__*/React.createElement("h3", null, "Collections — last 14 days")), d.trend.length ? /*#__PURE__*/React.createElement(Chart, {
    type: "line",
    height: 260,
    data: {
      labels: d.trend.map(t => t.date.slice(5)),
      datasets: [{
        label: 'Collected',
        data: d.trend.map(t => t.collected),
        borderColor: GOLD,
        backgroundColor: 'rgba(233,200,119,.15)',
        fill: true,
        tension: .35,
        pointRadius: 2
      }]
    }
  }) : /*#__PURE__*/React.createElement("p", {
    className: "muted"
  }, "No visit collections logged yet.")), /*#__PURE__*/React.createElement("div", {
    className: "glass card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-h"
  }, /*#__PURE__*/React.createElement("h3", null, "Paid vs Unpaid")), /*#__PURE__*/React.createElement(Chart, {
    type: "doughnut",
    height: 260,
    data: {
      labels: ['Paid', 'Unpaid', 'Partial'],
      datasets: [{
        data: [k.paid, k.unpaid, k.partial],
        backgroundColor: ['#5FD08A', '#F0776B', '#F0C05A'],
        borderWidth: 0
      }]
    }
  }))), /*#__PURE__*/React.createElement("div", {
    className: "grid2",
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "glass card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-h"
  }, /*#__PURE__*/React.createElement("h3", null, "By Bank")), d.by_bank.length ? /*#__PURE__*/React.createElement(Chart, {
    type: "bar",
    height: 250,
    data: {
      labels: d.by_bank.map(b => b.bank),
      datasets: [{
        label: 'Received',
        data: d.by_bank.map(b => b.received),
        backgroundColor: GOLD
      }, {
        label: 'Pending',
        data: d.by_bank.map(b => b.pending),
        backgroundColor: 'rgba(240,119,107,.7)'
      }]
    }
  }) : /*#__PURE__*/React.createElement("p", {
    className: "muted"
  }, "No data.")), /*#__PURE__*/React.createElement("div", {
    className: "glass card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-h"
  }, /*#__PURE__*/React.createElement("h3", null, "Dispositions")), d.by_disposition.length ? /*#__PURE__*/React.createElement(Chart, {
    type: "bar",
    height: 250,
    options: {
      indexAxis: 'y'
    },
    data: {
      labels: d.by_disposition.map(x => x.disposition),
      datasets: [{
        label: 'Cases',
        data: d.by_disposition.map(x => x.count),
        backgroundColor: PALETTE
      }]
    }
  }) : /*#__PURE__*/React.createElement("p", {
    className: "muted"
  }, "No dispositions yet."))), user.role === 'admin' && d.fo_leaderboard.length > 0 && /*#__PURE__*/React.createElement("div", {
    className: "glass card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-h"
  }, /*#__PURE__*/React.createElement("h3", null, "Field Officer Leaderboard")), /*#__PURE__*/React.createElement("div", {
    className: "tablewrap"
  }, /*#__PURE__*/React.createElement("table", null, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Officer"), /*#__PURE__*/React.createElement("th", null, "Visits"), /*#__PURE__*/React.createElement("th", null, "Collected"))), /*#__PURE__*/React.createElement("tbody", null, d.fo_leaderboard.map((f, i) => /*#__PURE__*/React.createElement("tr", {
    key: i
  }, /*#__PURE__*/React.createElement("td", null, f.name), /*#__PURE__*/React.createElement("td", {
    className: "mono"
  }, f.visits), /*#__PURE__*/React.createElement("td", {
    className: "mono",
    style: {
      color: 'var(--good)'
    }
  }, INR(f.collected)))))))));
}

/* ============================== Cases (admin) ============================== */
function UploadModal({
  onClose,
  onDone
}) {
  const [file, setFile] = useState(null);
  const [bank, setBank] = useState('');
  const [branch, setBranch] = useState('');
  const [prev, setPrev] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const doPreview = async () => {
    if (!file) return;
    setErr('');
    setBusy(true);
    try {
      const f = new FormData();
      f.append('file', file);
      if (bank) f.append('default_bank', bank);
      setPrev(await api('/api/import/preview', {
        method: 'POST',
        form: f
      }));
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  const doCommit = async () => {
    if (!file) return;
    setErr('');
    setBusy(true);
    try {
      const f = new FormData();
      f.append('file', file);
      if (bank) f.append('default_bank', bank);
      if (branch) f.append('branch', branch);
      f.append('auto_allocate', 'true');
      const r = await api('/api/import/commit', {
        method: 'POST',
        form: f
      });
      toast(`Imported ${r.imported}, updated ${r.updated}. ${r.assigned_fos_total}/${r.total_cases} cases assigned to field officers.`);
      onDone();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "modal-bg",
    onClick: onClose
  }, /*#__PURE__*/React.createElement("div", {
    className: "modal glass",
    onClick: e => e.stopPropagation()
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-h"
  }, /*#__PURE__*/React.createElement("h3", null, "Upload cases from Excel"), /*#__PURE__*/React.createElement("button", {
    className: "btn ghost sm",
    onClick: onClose
  }, "✕")), /*#__PURE__*/React.createElement("p", {
    className: "muted",
    style: {
      fontSize: 13
    }
  }, "Reads your loading-file / live-sheet formats and creates or updates cases, then auto-allocates by pincode & nearest FO."), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Excel file (.xlsx)"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    type: "file",
    accept: ".xlsx,.xls",
    onChange: e => {
      setFile(e.target.files[0]);
      setPrev(null);
    }
  })), /*#__PURE__*/React.createElement("div", {
    className: "grid2",
    style: {
      gridTemplateColumns: '1fr 1fr'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Default bank (if not in sheet)"), /*#__PURE__*/React.createElement("select", {
    className: "input",
    value: bank,
    onChange: e => setBank(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: ""
  }, "— auto —"), /*#__PURE__*/React.createElement("option", null, "ICICI"), /*#__PURE__*/React.createElement("option", null, "RBL"), /*#__PURE__*/React.createElement("option", null, "AXIS"))), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Branch (optional)"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: branch,
    onChange: e => setBranch(e.target.value),
    placeholder: "Visakhapatnam"
  }))), err && /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--bad)',
      fontSize: 13,
      marginBottom: 8
    }
  }, err), /*#__PURE__*/React.createElement("div", {
    className: "toolbar"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn",
    onClick: doPreview,
    disabled: !file || busy
  }, "Preview"), /*#__PURE__*/React.createElement("button", {
    className: "btn gold",
    onClick: doCommit,
    disabled: !file || busy
  }, busy ? 'Working…' : 'Import & Allocate')), prev && /*#__PURE__*/React.createElement("div", {
    className: "glass card",
    style: {
      marginTop: 6
    }
  }, /*#__PURE__*/React.createElement("b", null, prev.total_rows), " rows found in sheet ", /*#__PURE__*/React.createElement("b", null, prev.sheet), ". Preview:", /*#__PURE__*/React.createElement("div", {
    className: "tablewrap",
    style: {
      marginTop: 8
    }
  }, /*#__PURE__*/React.createElement("table", null, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Name"), /*#__PURE__*/React.createElement("th", null, "Bank"), /*#__PURE__*/React.createElement("th", null, "Account"), /*#__PURE__*/React.createElement("th", null, "Target"), /*#__PURE__*/React.createElement("th", null, "Pincode"))), /*#__PURE__*/React.createElement("tbody", null, prev.sample.map((s, i) => /*#__PURE__*/React.createElement("tr", {
    key: i
  }, /*#__PURE__*/React.createElement("td", null, s.customer_name), /*#__PURE__*/React.createElement("td", null, s.bank), /*#__PURE__*/React.createElement("td", {
    className: "mono"
  }, s.account_no), /*#__PURE__*/React.createElement("td", {
    className: "mono"
  }, s.funding_amount), /*#__PURE__*/React.createElement("td", null, s.pincode || '—')))))))));
}
function CasesView({
  user
}) {
  const [cases, setCases] = useState(null);
  const [bank, setBank] = useState('');
  const [paid, setPaid] = useState('');
  const [q, setQ] = useState('');
  const [upload, setUpload] = useState(false);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    const p = new URLSearchParams();
    if (bank) p.set('bank', bank);
    if (paid) p.set('paid_status', paid);
    if (q) p.set('search', q);
    api('/api/cases?' + p).then(setCases);
  }, [bank, paid, q]);
  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);
  const allocate = async () => {
    setBusy(true);
    try {
      const r = await api('/api/cases/allocate', {
        method: 'POST',
        body: {
          only_unallocated: true
        }
      });
      toast(`Allocated ${r.fos_allocated} to FOs, ${r.caller_allocated} to callers.`);
      load();
    } catch (e) {
      toast(e.message, 'err');
    } finally {
      setBusy(false);
    }
  };
  const exportXlsx = () => {
    window.open('/api/import/export', '_blank');
  };
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "toolbar"
  }, /*#__PURE__*/React.createElement("input", {
    className: "input",
    style: {
      maxWidth: 260
    },
    placeholder: "Search name / account / phone / pincode",
    value: q,
    onChange: e => setQ(e.target.value)
  }), /*#__PURE__*/React.createElement("select", {
    className: "input",
    style: {
      maxWidth: 130
    },
    value: bank,
    onChange: e => setBank(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: ""
  }, "All banks"), /*#__PURE__*/React.createElement("option", null, "ICICI"), /*#__PURE__*/React.createElement("option", null, "RBL"), /*#__PURE__*/React.createElement("option", null, "AXIS"), /*#__PURE__*/React.createElement("option", null, "BRBL")), ['', 'PAID', 'UNPAID', 'PARTIAL'].map(s => /*#__PURE__*/React.createElement("div", {
    key: s,
    className: cx('chip', paid === s && 'on'),
    onClick: () => setPaid(s)
  }, s || 'All')), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), user.role === 'admin' && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    className: "btn",
    onClick: () => setUpload(true)
  }, "⬆ Upload"), /*#__PURE__*/React.createElement("button", {
    className: "btn",
    onClick: allocate,
    disabled: busy
  }, "⚡ Auto-allocate"), /*#__PURE__*/React.createElement("button", {
    className: "btn gold",
    onClick: exportXlsx
  }, "⬇ Export Excel"))), !cases ? /*#__PURE__*/React.createElement(Loader, null) : /*#__PURE__*/React.createElement("div", {
    className: "glass card",
    style: {
      padding: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "tablewrap"
  }, /*#__PURE__*/React.createElement("table", null, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Customer"), /*#__PURE__*/React.createElement("th", null, "Bank"), /*#__PURE__*/React.createElement("th", null, "Account"), /*#__PURE__*/React.createElement("th", null, "Target"), /*#__PURE__*/React.createElement("th", null, "Received"), /*#__PURE__*/React.createElement("th", null, "Pending"), /*#__PURE__*/React.createElement("th", null, "Status"), /*#__PURE__*/React.createElement("th", null, "Paid"), /*#__PURE__*/React.createElement("th", null, "Pincode"), /*#__PURE__*/React.createElement("th", null, "Dispo"))), /*#__PURE__*/React.createElement("tbody", null, cases.map(c => /*#__PURE__*/React.createElement("tr", {
    key: c.id
  }, /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("b", null, c.customer_name || '—'), /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 12
    }
  }, c.phone)), /*#__PURE__*/React.createElement("td", null, c.bank), /*#__PURE__*/React.createElement("td", {
    className: "mono"
  }, c.account_no), /*#__PURE__*/React.createElement("td", {
    className: "mono"
  }, INR(c.funding_amount)), /*#__PURE__*/React.createElement("td", {
    className: "mono",
    style: {
      color: 'var(--good)'
    }
  }, INR(c.received_amount)), /*#__PURE__*/React.createElement("td", {
    className: "mono",
    style: {
      color: 'var(--warn)'
    }
  }, INR(c.pending_amount)), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement(StatusBadge, {
    s: c.status
  })), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement(PaidBadge, {
    s: c.paid_status
  })), /*#__PURE__*/React.createElement("td", null, c.pincode || '—'), /*#__PURE__*/React.createElement("td", {
    className: "muted"
  }, c.disposition || '—')))))), cases.length === 0 && /*#__PURE__*/React.createElement("p", {
    className: "muted",
    style: {
      padding: 16
    }
  }, "No cases. Upload an Excel to get started.")), upload && /*#__PURE__*/React.createElement(UploadModal, {
    onClose: () => setUpload(false),
    onDone: () => {
      setUpload(false);
      load();
    }
  }));
}

/* ============================== Live Map (admin) ============================== */
function LiveMap({
  config
}) {
  const mapEl = useRef(null);
  const map = useRef(null);
  const markers = useRef({});
  const routeLine = useRef(null);
  const routeMarks = useRef([]);
  const routeActive = useRef(false);
  const [status, setStatus] = useState('loading');
  const [officers, setOfficers] = useState([]);
  const [histOfficer, setHistOfficer] = useState(null);
  const [dates, setDates] = useState(null);
  const [selDate, setSelDate] = useState('');
  const [routeInfo, setRouteInfo] = useState(null);
  const refresh = useCallback(async () => {
    try {
      const list = await api('/api/tracking/live?minutes=1440');
      setOfficers(list);
      if (map.current && window.google) {
        const g = window.google;
        const bounds = new g.maps.LatLngBounds();
        list.forEach(o => {
          const pos = {
            lat: o.latitude,
            lng: o.longitude
          };
          if (markers.current[o.officer_id]) markers.current[o.officer_id].setPosition(pos);else markers.current[o.officer_id] = new g.maps.Marker({
            position: pos,
            map: map.current,
            title: o.name,
            label: {
              text: initials(o.name),
              color: '#221a06',
              fontWeight: '700'
            },
            icon: {
              path: g.maps.SymbolPath.CIRCLE,
              scale: 16,
              fillColor: '#E9C877',
              fillOpacity: 1,
              strokeColor: '#B8893A',
              strokeWeight: 2
            }
          });
          bounds.extend(pos);
        });
        if (list.length && !routeActive.current) map.current.fitBounds(bounds, 80);
      }
    } catch (e) {/* ignore transient */}
  }, []);
  useEffect(() => {
    let timer;
    loadMaps(config && config.google_maps_api_key).then(g => {
      map.current = new g.maps.Map(mapEl.current, {
        center: {
          lat: 17.72,
          lng: 83.30
        },
        zoom: 11,
        disableDefaultUI: false,
        styles: DARK_MAP_STYLE
      });
      setStatus('ready');
      refresh();
      const secs = config.location_ping_seconds || 60;
      timer = setInterval(refresh, Math.max(20, secs) * 1000);
    }).catch(() => setStatus('nokey'));
    return () => timer && clearInterval(timer);
  }, []);
  const navigateTo = o => window.open(`https://www.google.com/maps/dir/?api=1&destination=${o.latitude},${o.longitude}`, '_blank');
  const clearRoute = () => {
    routeActive.current = false;
    if (routeLine.current) {
      routeLine.current.setMap(null);
      routeLine.current = null;
    }
    routeMarks.current.forEach(m => m.setMap(null));
    routeMarks.current = [];
  };
  const openHistory = async o => {
    setHistOfficer(o);
    setDates(null);
    setSelDate('');
    setRouteInfo(null);
    clearRoute();
    try {
      const ds = await api(`/api/tracking/officer/${o.officer_id}/history-dates`);
      setDates(ds);
      if (ds.length) setSelDate(ds[0].date);
    } catch (e) {
      toast(e.message, 'err');
    }
  };
  const showRoute = async () => {
    if (!histOfficer || !selDate || !window.google) return;
    clearRoute();
    try {
      const pts = await api(`/api/tracking/officer/${histOfficer.officer_id}/route?date=${selDate}`);
      if (!pts.length) {
        toast('No route recorded that day', 'err');
        return;
      }
      const g = window.google;
      const path = pts.map(p => ({
        lat: p.latitude,
        lng: p.longitude
      }));
      routeLine.current = new g.maps.Polyline({
        path,
        strokeColor: '#E9C877',
        strokeWeight: 4,
        strokeOpacity: .95,
        map: map.current
      });
      const mk = (pos, txt, fill, stroke) => new g.maps.Marker({
        position: pos,
        map: map.current,
        label: {
          text: txt,
          color: '#0b0a06',
          fontWeight: '700',
          fontSize: '11px'
        },
        icon: {
          path: g.maps.SymbolPath.CIRCLE,
          scale: 11,
          fillColor: fill,
          fillOpacity: 1,
          strokeColor: stroke,
          strokeWeight: 2
        }
      });
      routeMarks.current = [mk(path[0], 'S', '#5FD08A', '#0b3d1f'), mk(path[path.length - 1], 'E', '#F0776B', '#5a1710')];
      const b = new g.maps.LatLngBounds();
      path.forEach(p => b.extend(p));
      map.current.fitBounds(b, 60);
      routeActive.current = true;
      setRouteInfo((dates || []).find(d => d.date === selDate) || {
        points: pts.length
      });
    } catch (e) {
      toast(e.message, 'err');
    }
  };
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "toolbar"
  }, /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, "Live field-officer positions · auto-refresh every ", config.location_ping_seconds || 60, "s"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), routeActive.current && /*#__PURE__*/React.createElement("button", {
    className: "btn sm",
    onClick: () => {
      clearRoute();
      setRouteInfo(null);
      refresh();
    }
  }, "✕ Clear route"), /*#__PURE__*/React.createElement("button", {
    className: "btn sm",
    onClick: refresh
  }, "↻ Refresh")), status === 'nokey' && /*#__PURE__*/React.createElement("div", {
    className: "glass card",
    style: {
      marginBottom: 12,
      color: 'var(--warn)'
    }
  }, "Google Maps key not set. Add ", /*#__PURE__*/React.createElement("b", null, "GOOGLE_MAPS_API_KEY"), " to the backend .env to see the live map."), /*#__PURE__*/React.createElement("div", {
    className: "grid2",
    style: {
      gridTemplateColumns: '1fr 320px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "glass",
    style: {
      padding: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "map tall",
    ref: mapEl
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "glass card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-h"
  }, /*#__PURE__*/React.createElement("h3", null, "Officers (", officers.length, ")")), officers.length === 0 && /*#__PURE__*/React.createElement("p", {
    className: "muted"
  }, "No recent pings. Field officers appear here when their app is open."), officers.map(o => /*#__PURE__*/React.createElement("div", {
    key: o.officer_id,
    style: {
      padding: '9px 0',
      borderBottom: '1px solid rgba(255,255,255,.06)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("b", null, "🟢 ", o.name), /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 11.5
    }
  }, "seen ", new Date(o.last_seen).toLocaleTimeString())), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn sm gold",
    onClick: () => navigateTo(o),
    title: "Directions to live location"
  }, "🧭"), /*#__PURE__*/React.createElement("button", {
    className: "btn sm",
    onClick: () => openHistory(o),
    title: "Route history"
  }, "🕘")))))), histOfficer && /*#__PURE__*/React.createElement("div", {
    className: "glass card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-h"
  }, /*#__PURE__*/React.createElement("h3", null, "Route history — ", histOfficer.name), /*#__PURE__*/React.createElement("button", {
    className: "btn ghost sm",
    onClick: () => {
      setHistOfficer(null);
      clearRoute();
      setRouteInfo(null);
    }
  }, "✕")), dates === null ? /*#__PURE__*/React.createElement(Loader, null) : dates.length === 0 ? /*#__PURE__*/React.createElement("p", {
    className: "muted"
  }, "No route recorded in the last 30 days.") : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Date (last 30 days)"), /*#__PURE__*/React.createElement("select", {
    className: "input",
    value: selDate,
    onChange: e => setSelDate(e.target.value)
  }, dates.map(d => /*#__PURE__*/React.createElement("option", {
    key: d.date,
    value: d.date
  }, d.date, " · ", d.points, " pts · ", d.distance_km, " km")))), /*#__PURE__*/React.createElement("button", {
    className: "btn gold block",
    onClick: showRoute
  }, "Show route on map"), routeInfo && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "stat-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "k"
  }, "Points logged"), /*#__PURE__*/React.createElement("b", null, routeInfo.points)), routeInfo.distance_km != null && /*#__PURE__*/React.createElement("div", {
    className: "stat-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "k"
  }, "Distance"), /*#__PURE__*/React.createElement("b", null, routeInfo.distance_km, " km")), routeInfo.first_seen && /*#__PURE__*/React.createElement("div", {
    className: "stat-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "k"
  }, "Active"), /*#__PURE__*/React.createElement("b", null, routeInfo.first_seen, "–", routeInfo.last_seen)), /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 11.5,
      marginTop: 6
    }
  }, "🟢 S = start · 🔴 E = end of day")))))));
}
const DARK_MAP_STYLE = [{
  elementType: 'geometry',
  stylers: [{
    color: '#1a1710'
  }]
}, {
  elementType: 'labels.text.stroke',
  stylers: [{
    color: '#0e0c08'
  }]
}, {
  elementType: 'labels.text.fill',
  stylers: [{
    color: '#a99f86'
  }]
}, {
  featureType: 'road',
  elementType: 'geometry',
  stylers: [{
    color: '#2a2417'
  }]
}, {
  featureType: 'water',
  elementType: 'geometry',
  stylers: [{
    color: '#0f1a24'
  }]
}, {
  featureType: 'poi',
  stylers: [{
    visibility: 'off'
  }]
}];

/* ============================== Staff (admin) ============================== */
function StaffModal({
  editing,
  onClose,
  onDone
}) {
  const [f, setF] = useState(editing || {
    name: '',
    email: '',
    role: 'fos',
    branch: '',
    password: '',
    banks: [],
    assigned_pincodes: [],
    home_lat: '',
    home_lng: ''
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const upd = (k, v) => setF(s => ({
    ...s,
    [k]: v
  }));
  const toggleBank = b => setF(s => ({
    ...s,
    banks: s.banks.includes(b) ? s.banks.filter(x => x !== b) : [...s.banks, b]
  }));
  const save = async () => {
    setErr('');
    setBusy(true);
    const body = {
      ...f,
      assigned_pincodes: typeof f.assigned_pincodes === 'string' ? f.assigned_pincodes.split(',').map(x => x.trim()).filter(Boolean) : f.assigned_pincodes,
      home_lat: f.home_lat === '' ? null : Number(f.home_lat),
      home_lng: f.home_lng === '' ? null : Number(f.home_lng)
    };
    try {
      if (editing) await api('/api/users/' + editing.id, {
        method: 'PATCH',
        body
      });else await api('/api/users', {
        method: 'POST',
        body
      });
      toast('Saved.');
      onDone();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "modal-bg",
    onClick: onClose
  }, /*#__PURE__*/React.createElement("div", {
    className: "modal glass",
    onClick: e => e.stopPropagation()
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-h"
  }, /*#__PURE__*/React.createElement("h3", null, editing ? 'Edit' : 'Add', " staff"), /*#__PURE__*/React.createElement("button", {
    className: "btn ghost sm",
    onClick: onClose
  }, "✕")), /*#__PURE__*/React.createElement("div", {
    className: "grid2",
    style: {
      gridTemplateColumns: '1fr 1fr'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Name"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: f.name,
    onChange: e => upd('name', e.target.value)
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Email"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: f.email,
    disabled: !!editing,
    onChange: e => upd('email', e.target.value)
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Role"), /*#__PURE__*/React.createElement("select", {
    className: "input",
    value: f.role,
    onChange: e => upd('role', e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: "fos"
  }, "Field Officer"), /*#__PURE__*/React.createElement("option", {
    value: "telecaller"
  }, "Telecaller"), /*#__PURE__*/React.createElement("option", {
    value: "admin"
  }, "Admin"))), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Branch"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: f.branch || '',
    onChange: e => upd('branch', e.target.value)
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Phone"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: f.phone || '',
    onChange: e => upd('phone', e.target.value)
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, editing ? 'New password (blank = keep)' : 'Password'), /*#__PURE__*/React.createElement("input", {
    className: "input",
    type: "password",
    value: f.password || '',
    onChange: e => upd('password', e.target.value)
  }))), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Banks"), /*#__PURE__*/React.createElement("div", {
    className: "toolbar",
    style: {
      margin: 0
    }
  }, ['ICICI', 'RBL', 'AXIS'].map(b => /*#__PURE__*/React.createElement("div", {
    key: b,
    className: cx('chip', f.banks.includes(b) && 'on'),
    onClick: () => toggleBank(b)
  }, b)))), f.role === 'fos' && /*#__PURE__*/React.createElement("div", {
    className: "grid2",
    style: {
      gridTemplateColumns: '1fr 1fr'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Assigned pincodes (comma-separated)"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: Array.isArray(f.assigned_pincodes) ? f.assigned_pincodes.join(', ') : f.assigned_pincodes,
    onChange: e => upd('assigned_pincodes', e.target.value),
    placeholder: "530001, 530016"
  })), /*#__PURE__*/React.createElement("div", {
    className: "field",
    style: {
      display: 'flex',
      flexDirection: 'row',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", null, "Base lat"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: f.home_lat || '',
    onChange: e => upd('home_lat', e.target.value)
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", null, "Base lng"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: f.home_lng || '',
    onChange: e => upd('home_lng', e.target.value)
  })))), err && /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--bad)',
      fontSize: 13
    }
  }, err), /*#__PURE__*/React.createElement("button", {
    className: "btn gold block",
    onClick: save,
    disabled: busy,
    style: {
      marginTop: 8
    }
  }, busy ? 'Saving…' : 'Save')));
}
function StaffView() {
  const [users, setUsers] = useState(null);
  const [modal, setModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const load = () => api('/api/users').then(setUsers);
  useEffect(() => {
    load();
  }, []);
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "toolbar"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn gold",
    onClick: () => {
      setEditing(null);
      setModal(true);
    }
  }, "+ Add staff")), !users ? /*#__PURE__*/React.createElement(Loader, null) : /*#__PURE__*/React.createElement("div", {
    className: "glass card",
    style: {
      padding: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "tablewrap"
  }, /*#__PURE__*/React.createElement("table", null, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Name"), /*#__PURE__*/React.createElement("th", null, "Role"), /*#__PURE__*/React.createElement("th", null, "Branch"), /*#__PURE__*/React.createElement("th", null, "Banks"), /*#__PURE__*/React.createElement("th", null, "Pincodes"), /*#__PURE__*/React.createElement("th", null, "Status"), /*#__PURE__*/React.createElement("th", null))), /*#__PURE__*/React.createElement("tbody", null, users.map(u => /*#__PURE__*/React.createElement("tr", {
    key: u.id
  }, /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("b", null, u.name), /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 12
    }
  }, u.email)), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("span", {
    className: "badge allocated"
  }, u.role)), /*#__PURE__*/React.createElement("td", null, u.branch || '—'), /*#__PURE__*/React.createElement("td", null, (u.banks || []).join(', ') || '—'), /*#__PURE__*/React.createElement("td", null, (u.assigned_pincodes || []).join(', ') || '—'), /*#__PURE__*/React.createElement("td", null, u.is_active ? /*#__PURE__*/React.createElement("span", {
    className: "badge paid"
  }, "active") : /*#__PURE__*/React.createElement("span", {
    className: "badge unpaid"
  }, "off")), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("button", {
    className: "btn sm",
    onClick: () => {
      setEditing(u);
      setModal(true);
    }
  }, "Edit")))))))), modal && /*#__PURE__*/React.createElement(StaffModal, {
    editing: editing,
    onClose: () => setModal(false),
    onDone: () => {
      setModal(false);
      load();
    }
  }));
}

/* ============================== Field Officer ============================== */
const DISPOS_FIELD = ['PAID', 'PTP', 'NOT AVAILABLE', 'MOVED', 'WRONG ADDRESS', 'DISPUTE', 'REFUSED', 'RNR'];
function VisitModal({
  c,
  onClose,
  onDone
}) {
  const [coords, setCoords] = useState(null);
  const [photo, setPhoto] = useState(null);
  const [photoUrl, setPhotoUrl] = useState(null);
  const [locOk, setLocOk] = useState(true);
  const [moved, setMoved] = useState(false);
  const [paid, setPaid] = useState(false);
  const [amount, setAmount] = useState('');
  const [dispo, setDispo] = useState('PTP');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [gps, setGps] = useState('idle');
  const grab = async () => {
    setGps('getting');
    try {
      const c = await getGPS();
      setCoords(c);
      setGps('ok');
    } catch (e) {
      setGps('fail');
      setErr('GPS: ' + e.message);
    }
  };
  useEffect(() => {
    grab();
  }, []);
  const onPhoto = e => {
    const file = e.target.files[0];
    if (!file) return;
    setPhoto(file);
    setPhotoUrl(URL.createObjectURL(file));
  };
  const submit = async () => {
    setErr('');
    setBusy(true);
    try {
      const f = new FormData();
      f.append('case_id', c.id);
      if (coords) {
        f.append('latitude', coords.latitude);
        f.append('longitude', coords.longitude);
        if (coords.accuracy) f.append('gps_accuracy', coords.accuracy);
      }
      f.append('location_correct', locOk);
      f.append('person_moved', moved);
      f.append('paid', paid);
      f.append('amount_collected', paid ? amount || '0' : '0');
      f.append('disposition', moved ? 'MOVED' : dispo);
      f.append('note', note);
      if (photo) f.append('photo', photo);
      await api('/api/visits', {
        method: 'POST',
        form: f
      });
      toast('Visit saved.');
      onDone();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "modal-bg",
    onClick: onClose
  }, /*#__PURE__*/React.createElement("div", {
    className: "modal glass",
    onClick: e => e.stopPropagation()
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-h"
  }, /*#__PURE__*/React.createElement("h3", null, "Log visit — ", c.customer_name), /*#__PURE__*/React.createElement("button", {
    className: "btn ghost sm",
    onClick: onClose
  }, "✕")), /*#__PURE__*/React.createElement("div", {
    className: "glass card",
    style: {
      marginBottom: 12,
      background: 'rgba(0,0,0,.2)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "stat-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "k"
  }, "Pending"), /*#__PURE__*/React.createElement("b", {
    className: "mono",
    style: {
      color: 'var(--warn)'
    }
  }, INR2(c.pending_amount))), /*#__PURE__*/React.createElement("div", {
    className: "stat-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "k"
  }, "GPS"), /*#__PURE__*/React.createElement("span", null, gps === 'ok' && coords ? /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--good)'
    }
  }, "±", Math.round(coords.accuracy), "m ✓") : gps === 'getting' ? 'locating…' : /*#__PURE__*/React.createElement("button", {
    className: "btn sm",
    onClick: grab
  }, "Get GPS")))), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "GPS camera photo"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    type: "file",
    accept: "image/*",
    capture: "environment",
    onChange: onPhoto
  }), photoUrl && /*#__PURE__*/React.createElement("img", {
    src: photoUrl,
    style: {
      marginTop: 8,
      borderRadius: 12,
      maxHeight: 160
    }
  })), /*#__PURE__*/React.createElement("div", {
    className: "toolbar"
  }, /*#__PURE__*/React.createElement("div", {
    className: cx('chip', locOk && 'on'),
    onClick: () => setLocOk(!locOk)
  }, locOk ? '✓ ' : '', "Location correct"), /*#__PURE__*/React.createElement("div", {
    className: cx('chip', moved && 'on'),
    onClick: () => setMoved(!moved)
  }, moved ? '✓ ' : '', "Person moved"), /*#__PURE__*/React.createElement("div", {
    className: cx('chip', paid && 'on'),
    onClick: () => setPaid(!paid)
  }, paid ? '✓ ' : '', "Payment collected")), paid && /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Amount collected (₹)"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    type: "number",
    inputMode: "decimal",
    value: amount,
    onChange: e => setAmount(e.target.value),
    placeholder: "0.00"
  })), !moved && /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Disposition"), /*#__PURE__*/React.createElement("select", {
    className: "input",
    value: dispo,
    onChange: e => setDispo(e.target.value)
  }, DISPOS_FIELD.map(d => /*#__PURE__*/React.createElement("option", {
    key: d
  }, d)))), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Note"), /*#__PURE__*/React.createElement("textarea", {
    className: "input",
    value: note,
    onChange: e => setNote(e.target.value),
    placeholder: "What happened at the location…"
  })), err && /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--bad)',
      fontSize: 13,
      marginBottom: 8
    }
  }, err), /*#__PURE__*/React.createElement("button", {
    className: "btn gold block",
    onClick: submit,
    disabled: busy
  }, busy ? 'Saving…' : 'Save visit')));
}

// Priority + grouping helpers for the field-officer queue
const bucketRank = b => {
  const s = (b || '').toUpperCase();
  if (s.includes('X')) return 0; // cross-bucket = most overdue
  const m = s.match(/(\d+)/);
  if (m) return 10 - Math.min(9, parseInt(m[1], 10)); // higher bucket number = higher priority
  return 50;
};
function casePriority(c) {
  const pend = Number(c.pending_amount || 0);
  const b = (c.bucket || '').toUpperCase();
  if (b.includes('X') || pend >= 50000) return {
    label: 'High',
    cls: 'unpaid'
  };
  if (/[23456789]/.test(b) || pend >= 10000) return {
    label: 'Medium',
    cls: 'partial'
  };
  return {
    label: 'Low',
    cls: 'paid'
  };
}
function groupCases(cases) {
  const banks = {};
  cases.forEach(c => {
    const bank = c.bank || '—';
    const bucket = c.bucket || 'No bucket';
    banks[bank] = banks[bank] || {};
    (banks[bank][bucket] = banks[bank][bucket] || []).push(c);
  });
  return Object.keys(banks).sort().map(bank => {
    const buckets = Object.keys(banks[bank]).sort((a, b) => bucketRank(a) - bucketRank(b)).map(bucket => {
      const list = banks[bank][bucket].slice().sort((a, b) => Number(b.pending_amount || 0) - Number(a.pending_amount || 0));
      return {
        bucket,
        cases: list,
        pending: list.reduce((s, c) => s + Number(c.pending_amount || 0), 0)
      };
    });
    return {
      bank,
      buckets,
      count: buckets.reduce((s, bk) => s + bk.cases.length, 0),
      pending: buckets.reduce((s, bk) => s + bk.pending, 0)
    };
  });
}
function CaseCard({
  c,
  onVisit,
  onNav
}) {
  const p = casePriority(c);
  return /*#__PURE__*/React.createElement("div", {
    className: "glass card"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("b", null, c.customer_name), /*#__PURE__*/React.createElement("span", {
    className: cx('badge', p.cls)
  }, p.label)), /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 13,
      margin: '4px 0 8px'
    }
  }, c.bank, " · ", c.bucket || '—', " · cyc ", c.cycle || '—'), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      color: 'var(--ink-soft)',
      minHeight: 34
    }
  }, c.address || 'No address', " ", c.pincode ? `(${c.pincode})` : ''), /*#__PURE__*/React.createElement("div", {
    className: "stat-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "k"
  }, "Pending"), /*#__PURE__*/React.createElement("b", {
    className: "mono",
    style: {
      color: 'var(--warn)'
    }
  }, INR(c.pending_amount))), /*#__PURE__*/React.createElement("div", {
    className: "toolbar",
    style: {
      margin: '10px 0 0'
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn sm gold",
    style: {
      flex: 1
    },
    onClick: onVisit
  }, "Log visit"), /*#__PURE__*/React.createElement("button", {
    className: "btn sm",
    onClick: onNav
  }, "🧭 Navigate"), c.phone && /*#__PURE__*/React.createElement("a", {
    className: "btn sm",
    href: 'tel:' + c.phone
  }, "📞")));
}
function FOCases({
  config
}) {
  const [cases, setCases] = useState(null);
  const [view, setView] = useState('list');
  const [active, setActive] = useState(null);
  const [collapsed, setCollapsed] = useState({});
  const mapEl = useRef(null);
  const map = useRef(null);
  const load = () => api('/api/cases').then(setCases);
  useEffect(() => {
    load();
  }, []);
  useEffect(() => {
    if (view !== 'map' || !cases) return;
    loadMaps(config && config.google_maps_api_key).then(g => {
      map.current = new g.maps.Map(mapEl.current, {
        center: {
          lat: 17.72,
          lng: 83.30
        },
        zoom: 11,
        styles: DARK_MAP_STYLE
      });
      const bounds = new g.maps.LatLngBounds();
      let any = false;
      cases.forEach(c => {
        if (c.latitude && c.longitude) {
          any = true;
          const m = new g.maps.Marker({
            position: {
              lat: c.latitude,
              lng: c.longitude
            },
            map: map.current,
            title: c.customer_name
          });
          m.addListener('click', () => setActive(c));
          bounds.extend({
            lat: c.latitude,
            lng: c.longitude
          });
        }
      });
      if (any) map.current.fitBounds(bounds, 60);
    }).catch(() => {});
  }, [view, cases]);
  const openNav = c => {
    const q = c.latitude && c.longitude ? `${c.latitude},${c.longitude}` : encodeURIComponent(c.address || c.pincode || '');
    window.open(`https://www.google.com/maps/dir/?api=1&destination=${q}`, '_blank');
  };
  if (!cases) return /*#__PURE__*/React.createElement(Loader, null);
  const groups = groupCases(cases);
  const toggle = bank => setCollapsed(s => ({
    ...s,
    [bank]: !s[bank]
  }));
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "toolbar"
  }, /*#__PURE__*/React.createElement("div", {
    className: cx('chip', view === 'list' && 'on'),
    onClick: () => setView('list')
  }, "☰ Grouped"), /*#__PURE__*/React.createElement("div", {
    className: cx('chip', view === 'map' && 'on'),
    onClick: () => setView('map')
  }, "◎ Map"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, cases.length, " assigned")), view === 'map' ? /*#__PURE__*/React.createElement("div", {
    className: "glass",
    style: {
      padding: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "map tall",
    ref: mapEl
  })) : cases.length === 0 ? /*#__PURE__*/React.createElement("p", {
    className: "muted"
  }, "No cases assigned to you yet.") : /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 16
    }
  }, groups.map(bank => /*#__PURE__*/React.createElement("div", {
    key: bank.bank,
    className: "glass card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-h",
    style: {
      cursor: 'pointer',
      margin: 0
    },
    onClick: () => toggle(bank.bank)
  }, /*#__PURE__*/React.createElement("h3", null, collapsed[bank.bank] ? '▸' : '▾', " ", bank.bank, /*#__PURE__*/React.createElement("span", {
    className: "muted",
    style: {
      fontWeight: 400,
      fontSize: 13
    }
  }, " · ", bank.count, " cases · ", INR(bank.pending), " pending"))), !collapsed[bank.bank] && bank.buckets.map(bk => /*#__PURE__*/React.createElement("div", {
    key: bk.bucket,
    style: {
      marginTop: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      margin: '4px 2px 8px'
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "badge allocated"
  }, bk.bucket), /*#__PURE__*/React.createElement("span", {
    className: "muted",
    style: {
      fontSize: 12.5
    }
  }, bk.cases.length, " cases · ", INR(bk.pending), " pending")), /*#__PURE__*/React.createElement("div", {
    className: "grid3"
  }, bk.cases.map(c => /*#__PURE__*/React.createElement(CaseCard, {
    key: c.id,
    c: c,
    onVisit: () => setActive(c),
    onNav: () => openNav(c)
  })))))))), active && /*#__PURE__*/React.createElement(VisitModal, {
    c: active,
    onClose: () => setActive(null),
    onDone: () => {
      setActive(null);
      load();
    }
  }));
}

/* Background location ping loop for field officers */
function useLocationPing(user, config) {
  useEffect(() => {
    if (!user || user.role !== 'fos') return;
    let alive = true;
    const send = async () => {
      try {
        const c = await getGPS({
          timeout: 20000
        });
        if (!alive) return;
        await api('/api/tracking/ping', {
          method: 'POST',
          body: {
            latitude: c.latitude,
            longitude: c.longitude,
            accuracy: c.accuracy,
            speed: c.speed
          }
        });
      } catch {}
    };
    send();
    const secs = Math.max(30, config && config.location_ping_seconds || 60);
    const t = setInterval(send, secs * 1000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [user && user.id]);
}

/* ============================== Telecaller ============================== */
const DISPOS_CALL = ['RTP', 'PTP', 'RNR', 'SWITCHED OFF', 'WRONG NUMBER', 'BUSY', 'NOT REACHABLE', 'DISPUTE', 'PAID'];
function CallModal({
  c,
  onClose,
  onDone
}) {
  const [dispo, setDispo] = useState('PTP');
  const [amt, setAmt] = useState('');
  const [date, setDate] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const save = async () => {
    setErr('');
    setBusy(true);
    try {
      await api('/api/calls', {
        method: 'POST',
        body: {
          case_id: c.id,
          disposition: dispo,
          ptp_amount: amt || '0',
          ptp_date: date ? new Date(date).toISOString() : null,
          note
        }
      });
      toast('Call logged.');
      onDone();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "modal-bg",
    onClick: onClose
  }, /*#__PURE__*/React.createElement("div", {
    className: "modal glass",
    onClick: e => e.stopPropagation()
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-h"
  }, /*#__PURE__*/React.createElement("h3", null, "Log call — ", c.customer_name), /*#__PURE__*/React.createElement("button", {
    className: "btn ghost sm",
    onClick: onClose
  }, "✕")), /*#__PURE__*/React.createElement("div", {
    className: "glass card",
    style: {
      marginBottom: 12,
      background: 'rgba(0,0,0,.2)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "stat-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "k"
  }, "Phone"), /*#__PURE__*/React.createElement("b", null, c.phone || '—')), /*#__PURE__*/React.createElement("div", {
    className: "stat-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "k"
  }, "Pending"), /*#__PURE__*/React.createElement("b", {
    className: "mono",
    style: {
      color: 'var(--warn)'
    }
  }, INR2(c.pending_amount)))), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Disposition"), /*#__PURE__*/React.createElement("select", {
    className: "input",
    value: dispo,
    onChange: e => setDispo(e.target.value)
  }, DISPOS_CALL.map(d => /*#__PURE__*/React.createElement("option", {
    key: d
  }, d)))), (dispo === 'PTP' || dispo === 'RTP') && /*#__PURE__*/React.createElement("div", {
    className: "grid2",
    style: {
      gridTemplateColumns: '1fr 1fr'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "PTP amount (₹)"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    type: "number",
    value: amt,
    onChange: e => setAmt(e.target.value)
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "PTP date"), /*#__PURE__*/React.createElement("input", {
    className: "input",
    type: "date",
    value: date,
    onChange: e => setDate(e.target.value)
  }))), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Note"), /*#__PURE__*/React.createElement("textarea", {
    className: "input",
    value: note,
    onChange: e => setNote(e.target.value)
  })), err && /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--bad)',
      fontSize: 13,
      marginBottom: 8
    }
  }, err), /*#__PURE__*/React.createElement("button", {
    className: "btn gold block",
    onClick: save,
    disabled: busy
  }, busy ? 'Saving…' : 'Save call')));
}
function CallQueue() {
  const [cases, setCases] = useState(null);
  const [active, setActive] = useState(null);
  const [q, setQ] = useState('');
  const load = () => {
    const p = new URLSearchParams();
    if (q) p.set('search', q);
    api('/api/cases?' + p).then(setCases);
  };
  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [q]);
  if (!cases) return /*#__PURE__*/React.createElement(Loader, null);
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "toolbar"
  }, /*#__PURE__*/React.createElement("input", {
    className: "input",
    style: {
      maxWidth: 280
    },
    placeholder: "Search queue…",
    value: q,
    onChange: e => setQ(e.target.value)
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, cases.length, " in queue")), /*#__PURE__*/React.createElement("div", {
    className: "grid3"
  }, cases.map(c => /*#__PURE__*/React.createElement("div", {
    key: c.id,
    className: "glass card"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("b", null, c.customer_name), /*#__PURE__*/React.createElement(PaidBadge, {
    s: c.paid_status
  })), /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 13,
      margin: '4px 0'
    }
  }, c.bank, " · ", c.bucket || '', " · cyc ", c.cycle || '—'), /*#__PURE__*/React.createElement("div", {
    className: "stat-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "k"
  }, "Pending"), /*#__PURE__*/React.createElement("b", {
    className: "mono",
    style: {
      color: 'var(--warn)'
    }
  }, INR(c.pending_amount))), c.disposition && /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 12,
      marginTop: 4
    }
  }, "Last: ", c.disposition), /*#__PURE__*/React.createElement("div", {
    className: "toolbar",
    style: {
      margin: '10px 0 0'
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn sm gold",
    style: {
      flex: 1
    },
    onClick: () => setActive(c)
  }, "Log call"), c.phone && /*#__PURE__*/React.createElement("a", {
    className: "btn sm",
    href: 'tel:' + c.phone
  }, "📞 Call")))), cases.length === 0 && /*#__PURE__*/React.createElement("p", {
    className: "muted"
  }, "Your call queue is empty.")), active && /*#__PURE__*/React.createElement(CallModal, {
    c: active,
    onClose: () => setActive(null),
    onDone: () => {
      setActive(null);
      load();
    }
  }));
}

/* ============================== AI Assist ============================== */
function AIAssist({
  user
}) {
  const [msgs, setMsgs] = useState([{
    who: 'bot',
    text: `Hi ${user.name.split(' ')[0]} — I'm your recovery assistant. Ask me to prioritise cases, draft a payment reminder, write a call script, or explain your numbers.`
  }]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  useEffect(() => {
    end.current && end.current.scrollIntoView({
      behavior: 'smooth'
    });
  }, [msgs]);
  const send = async () => {
    if (!input.trim() || busy) return;
    const prompt = input.trim();
    setMsgs(m => [...m, {
      who: 'me',
      text: prompt
    }]);
    setInput('');
    setBusy(true);
    try {
      const r = await api('/api/ai', {
        method: 'POST',
        body: {
          prompt
        }
      });
      setMsgs(m => [...m, {
        who: 'bot',
        text: r.reply
      }]);
    } catch (e) {
      setMsgs(m => [...m, {
        who: 'bot',
        text: 'Error: ' + e.message
      }]);
    } finally {
      setBusy(false);
    }
  };
  const quick = ['Which cases should I prioritise today?', 'Draft a polite WhatsApp payment reminder', 'Write a firm but compliant call script', 'Summarise my current recovery numbers'];
  return /*#__PURE__*/React.createElement("div", {
    className: "glass card",
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: 'calc(100vh - 150px)',
      minHeight: 420
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflowY: 'auto',
      display: 'flex',
      flexDirection: 'column'
    }
  }, msgs.map((m, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: cx('ai-msg', m.who === 'me' ? 'me' : 'bot')
  }, m.text)), busy && /*#__PURE__*/React.createElement("div", {
    className: "ai-msg bot"
  }, "…thinking"), /*#__PURE__*/React.createElement("div", {
    ref: end
  })), /*#__PURE__*/React.createElement("div", {
    className: "toolbar",
    style: {
      margin: '10px 0 0'
    }
  }, quick.map(q => /*#__PURE__*/React.createElement("div", {
    key: q,
    className: "chip",
    onClick: () => setInput(q)
  }, q))), /*#__PURE__*/React.createElement("div", {
    className: "toolbar",
    style: {
      margin: '8px 0 0'
    }
  }, /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: input,
    onChange: e => setInput(e.target.value),
    onKeyDown: e => e.key === 'Enter' && send(),
    placeholder: "Ask the assistant…"
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn gold",
    onClick: send,
    disabled: busy
  }, "Send")));
}

/* ============================== Shell + App ============================== */
const NAV = {
  admin: [['dashboard', '📊', 'Dashboard'], ['cases', '🗂️', 'Cases'], ['map', '📍', 'Live Map'], ['staff', '👥', 'Staff'], ['ai', '✨', 'AI Assist']],
  fos: [['dashboard', '📊', 'My Stats'], ['fcases', '🗂️', 'My Cases'], ['ai', '✨', 'AI Assist']],
  telecaller: [['dashboard', '📊', 'My Stats'], ['queue', '📞', 'Call Queue'], ['ai', '✨', 'AI Assist']]
};
function Shell({
  user,
  config,
  onLogout
}) {
  const nav = NAV[user.role] || NAV.telecaller;
  const [view, setView] = useState(nav[0][0]);
  useLocationPing(user, config);
  const title = (nav.find(n => n[0] === view) || [,, ''])[2];
  const render = () => {
    switch (view) {
      case 'dashboard':
        return /*#__PURE__*/React.createElement(Dashboard, {
          user: user
        });
      case 'cases':
        return /*#__PURE__*/React.createElement(CasesView, {
          user: user
        });
      case 'map':
        return /*#__PURE__*/React.createElement(LiveMap, {
          config: config
        });
      case 'staff':
        return /*#__PURE__*/React.createElement(StaffView, null);
      case 'fcases':
        return /*#__PURE__*/React.createElement(FOCases, {
          config: config
        });
      case 'queue':
        return /*#__PURE__*/React.createElement(CallQueue, null);
      case 'ai':
        return /*#__PURE__*/React.createElement(AIAssist, {
          user: user
        });
      default:
        return null;
    }
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "app"
  }, /*#__PURE__*/React.createElement("aside", {
    className: "sidebar glass",
    style: {
      borderRadius: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "brand"
  }, /*#__PURE__*/React.createElement("img", {
    src: "assets/logo.png",
    alt: ""
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "n brandfont",
    style: {
      fontSize: 16
    }
  }, "SSD Recovery"), /*#__PURE__*/React.createElement("div", {
    className: "s",
    style: {
      fontSize: 10
    }
  }, user.role))), nav.map(([id, ic, label]) => /*#__PURE__*/React.createElement("div", {
    key: id,
    className: cx('navitem', view === id && 'active'),
    onClick: () => setView(id)
  }, /*#__PURE__*/React.createElement("span", {
    className: "ic"
  }, ic), label)), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("div", {
    className: "navitem",
    onClick: onLogout
  }, /*#__PURE__*/React.createElement("span", {
    className: "ic"
  }, "⎋"), "Sign out")), /*#__PURE__*/React.createElement("main", {
    className: "main"
  }, /*#__PURE__*/React.createElement("div", {
    className: "topbar"
  }, /*#__PURE__*/React.createElement("h1", null, title), /*#__PURE__*/React.createElement("div", {
    className: "usertag"
  }, /*#__PURE__*/React.createElement("div", {
    className: "avatar"
  }, initials(user.name)), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600,
      fontSize: 14
    }
  }, user.name), /*#__PURE__*/React.createElement("div", {
    className: "muted",
    style: {
      fontSize: 12
    }
  }, user.branch || user.email)))), render()), /*#__PURE__*/React.createElement("nav", {
    className: "mobnav"
  }, nav.map(([id, ic, label]) => /*#__PURE__*/React.createElement("div", {
    key: id,
    className: cx('navitem', view === id && 'active'),
    onClick: () => setView(id)
  }, /*#__PURE__*/React.createElement("span", {
    className: "ic"
  }, ic), label))));
}
function App() {
  const [user, setUser] = useState(store.u);
  const [config, setConfig] = useState(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    api('/api/config', {
      auth: false
    }).then(setConfig).catch(() => setConfig({}));
    if (store.t) api('/api/auth/me').then(u => {
      setUser(u);
      store.u = u;
    }).catch(() => {
      store.t = null;
      setUser(null);
    }).finally(() => setReady(true));else setReady(true);
  }, []);
  const logout = () => {
    store.t = null;
    store.u = null;
    setUser(null);
  };
  if (!ready || !config) return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      height: '100vh',
      alignItems: 'center',
      justifyContent: 'center'
    }
  }, /*#__PURE__*/React.createElement(Loader, null));
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Toaster, null), user ? /*#__PURE__*/React.createElement(Shell, {
    user: user,
    config: config,
    onLogout: logout
  }) : /*#__PURE__*/React.createElement(Login, {
    onLogin: setUser,
    config: config
  }));
}
ReactDOM.createRoot(document.getElementById('root')).render(/*#__PURE__*/React.createElement(App, null));