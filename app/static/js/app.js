/* ==========================================================================
 * 轻记账 · app.js
 * 全局能力：主题切换、CSRF fetch 封装、Toast、确认弹窗、表单即时校验、侧边栏
 * 暴露命名空间：window.APP
 * ========================================================================== */
(function () {
  'use strict';

  var APP = (window.APP = window.APP || {});

  /* ---------- 0. 小工具 ---------- */
  APP.qs = function (selector, root) {
    return (root || document).querySelector(selector);
  };
  APP.qsa = function (selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  };

  APP.debounce = function (fn, wait) {
    var timer = null;
    return function () {
      var args = arguments;
      var ctx = this;
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        timer = null;
        fn.apply(ctx, args);
      }, wait || 150);
    };
  };

  APP.money = function (value) {
    var num = Number(value || 0);
    if (!isFinite(num)) num = 0;
    return num.toLocaleString('zh-CN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  };

  /* ---------- 1. CSRF ---------- */
  APP.csrfToken = function () {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  };

  APP.loginUrl = function () {
    var body = document.body;
    return (
      (body && body.getAttribute('data-login-url')) ||
      (document.querySelector('meta[name="login-url"]') || {}).content ||
      '/login'
    );
  };

  /* ---------- 2. Toast ---------- */
  var TOAST_ICONS = {
    success: '✅',
    danger: '⚠️',
    warning: '🔔',
    info: 'ℹ️'
  };

  APP.toast = function (message, type) {
    var stack = document.getElementById('toast-stack');
    if (!stack) {
      return;
    }
    var kind = TOAST_ICONS[type] ? type : 'info';

    var item = document.createElement('div');
    item.className = 'toast-item toast-' + kind;
    item.setAttribute('role', kind === 'danger' ? 'alert' : 'status');

    var icon = document.createElement('span');
    icon.className = 'toast-icon';
    icon.textContent = TOAST_ICONS[kind];

    var msg = document.createElement('span');
    msg.className = 'toast-msg';
    msg.textContent = String(message == null ? '' : message);

    item.appendChild(icon);
    item.appendChild(msg);
    stack.appendChild(item);

    var removed = false;
    function remove() {
      if (removed) return;
      removed = true;
      item.classList.add('toast-leave');
      setTimeout(function () {
        if (item.parentNode) item.parentNode.removeChild(item);
      }, 220);
    }
    var timer = setTimeout(remove, kind === 'danger' ? 5200 : 3200);
    item.addEventListener('click', function () {
      clearTimeout(timer);
      remove();
    });
  };

  /* ---------- 3. fetch 封装（自动 CSRF / 401 / 错误提示） ---------- */
  APP.api = function (url, options) {
    var opts = options || {};
    var method = (opts.method || 'GET').toUpperCase();
    var headers = new Headers(opts.headers || {});
    if (!headers.has('Accept')) {
      headers.set('Accept', 'application/json');
    }
    if (method !== 'GET' && method !== 'HEAD') {
      headers.set('X-CSRFToken', APP.csrfToken());
      if (typeof opts.body === 'string' && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
      }
    }

    var fetchOptions = {
      method: method,
      headers: headers,
      credentials: 'same-origin',
      cache: 'no-store'
    };
    if (opts.body !== undefined) {
      fetchOptions.body = opts.body;
    }

    return fetch(url, fetchOptions)
      .catch(function (error) {
        if (!opts.silent) {
          APP.toast('网络连接失败，请检查网络后重试', 'danger');
        }
        throw error;
      })
      .then(function (response) {
        if (response.status === 401) {
          APP.toast('登录已过期，请重新登录', 'warning');
          setTimeout(function () {
            window.location.href = APP.loginUrl();
          }, 600);
          throw new Error('unauthorized');
        }

        var contentType = response.headers.get('Content-Type') || '';
        var parse = contentType.indexOf('application/json') >= 0
          ? response.json()
          : Promise.resolve(null);

        return parse.then(function (payload) {
          // 成功：{code:0, data:...}；失败：{code:1, msg:...}
          if (payload && typeof payload === 'object' && typeof payload.code === 'number' && payload.code !== 0) {
            var err = new Error(payload.msg || '操作失败，请稍后重试');
            err.payload = payload;
            err.field = payload.field || '';
            if (!opts.silent) {
              APP.toast(err.message, 'danger');
            }
            throw err;
          }
          if (!response.ok) {
            var httpErr = new Error((payload && payload.msg) || '请求失败（HTTP ' + response.status + '）');
            httpErr.status = response.status;
            httpErr.payload = payload;
            httpErr.field = (payload && payload.field) || '';
            if (!opts.silent) {
              APP.toast(httpErr.message, 'danger');
            }
            throw httpErr;
          }
          if (payload && typeof payload === 'object' && 'data' in payload) {
            return payload.data;
          }
          return payload;
        });
      });
  };

  /* ---------- 4. 确认弹窗 + [data-confirm] 表单托管 ---------- */
  APP.confirm = function (text, options) {
    var opts = options || {};
    return new Promise(function (resolve) {
      var previousFocus = document.activeElement;

      var wrap = document.createElement('div');
      wrap.className = 'confirm-dialog';
      wrap.innerHTML =
        '<div class="confirm-card" role="alertdialog" aria-modal="true" aria-labelledby="appConfirmTitle">' +
        '<div class="confirm-title" id="appConfirmTitle">' + (opts.danger === false ? 'ℹ️ 请确认' : '⚠️ 操作确认') + '</div>' +
        '<div class="confirm-text"></div>' +
        '<div class="confirm-actions">' +
        '<button type="button" class="btn btn-soft" data-confirm-cancel>取消</button>' +
        '<button type="button" class="btn btn-primary" data-confirm-ok>确定</button>' +
        '</div></div>';
      wrap.querySelector('.confirm-text').textContent = text || '确定执行该操作吗？';

      var okBtn = wrap.querySelector('[data-confirm-ok]');
      var cancelBtn = wrap.querySelector('[data-confirm-cancel]');

      function close(result) {
        document.removeEventListener('keydown', onKeydown, true);
        if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
        if (previousFocus && previousFocus.focus) {
          try { previousFocus.focus(); } catch (e) { /* ignore */ }
        }
        resolve(result);
      }
      function onKeydown(event) {
        if (event.key === 'Escape') {
          event.preventDefault();
          close(false);
        } else if (event.key === 'Enter') {
          event.preventDefault();
          close(true);
        }
      }

      okBtn.addEventListener('click', function () { close(true); });
      cancelBtn.addEventListener('click', function () { close(false); });
      wrap.addEventListener('click', function (event) {
        if (event.target === wrap) close(false);
      });
      document.addEventListener('keydown', onKeydown, true);

      document.body.appendChild(wrap);
      okBtn.focus();
    });
  };

  // 接管所有带 data-confirm 的表单提交
  document.addEventListener(
    'submit',
    function (event) {
      var form = event.target;
      if (!form || form.tagName !== 'FORM' || !form.hasAttribute('data-confirm')) {
        return;
      }
      event.preventDefault();
      if (form.getAttribute('data-confirming') === '1') {
        return;
      }
      form.setAttribute('data-confirming', '1');

      APP.confirm(form.getAttribute('data-confirm')).then(function (ok) {
        form.removeAttribute('data-confirming');
        if (!ok) return;
        // 用原生 submit 跳过事件监听，避免再次触发确认
        HTMLFormElement.prototype.submit.call(form);
      });
    },
    true
  );

  /* ---------- 5. 主题切换 ---------- */
  function currentTheme() {
    return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  }

  APP.applyTheme = function (theme) {
    var next = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);
    document.documentElement.setAttribute('data-bs-theme', next);
    try {
      localStorage.setItem('theme', next);
    } catch (e) { /* localStorage 不可用则仅本次生效 */ }
    return next;
  };

  APP.currentTheme = currentTheme;

  function initTheme() {
    var stored = null;
    try { stored = localStorage.getItem('theme'); } catch (e) { stored = null; }
    // head 里的内联脚本已经应用过；这里兜底保证 data-bs-theme 同步
    var theme = stored === 'dark' || stored === 'light' ? stored : currentTheme();
    document.documentElement.setAttribute('data-bs-theme', theme);

    var toggle = document.getElementById('theme-toggle');
    if (toggle) {
      toggle.addEventListener('click', function () {
        var next = APP.applyTheme(currentTheme() === 'dark' ? 'light' : 'dark');
        toggle.setAttribute('aria-pressed', next === 'dark' ? 'true' : 'false');
        window.dispatchEvent(new CustomEvent('themechange', { detail: { theme: next } }));
        APP.toast(next === 'dark' ? '已切换到深色主题' : '已切换到浅色主题', 'info');
      });
    }
  }

  /* ---------- 6. 侧边栏（移动端抽屉） ---------- */
  function initSidebar() {
    var body = document.body;
    var toggle = document.getElementById('sidebarToggle');
    var backdrop = document.getElementById('sidebarBackdrop');
    if (!toggle) return;

    function setOpen(open) {
      body.classList.toggle('sidebar-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    toggle.addEventListener('click', function () {
      setOpen(!body.classList.contains('sidebar-open'));
    });
    if (backdrop) {
      backdrop.addEventListener('click', function () { setOpen(false); });
    }
    // 点击导航后自动收起
    APP.qsa('.app-sidebar a').forEach(function (link) {
      link.addEventListener('click', function () { setOpen(false); });
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') setOpen(false);
    });
  }

  /* ---------- 7. 输入即时校验（data-validate="amount|date"） ---------- */
  var AMOUNT_RE = /^\d{1,8}(\.\d{1,2})?$/;

  function todayStr() {
    var now = new Date();
    var month = String(now.getMonth() + 1).padStart(2, '0');
    var day = String(now.getDate()).padStart(2, '0');
    return now.getFullYear() + '-' + month + '-' + day;
  }

  function validateField(input) {
    var rule = input.getAttribute('data-validate');
    var raw = String(input.value == null ? '' : input.value).trim();
    var required = input.hasAttribute('required');
    var message = '';

    if (!raw) {
      if (required) {
        message = rule === 'amount' ? '请输入金额' : '请选择日期';
      }
      return { valid: !message, message: message };
    }

    if (rule === 'amount') {
      if (!AMOUNT_RE.test(raw) || Number(raw) <= 0) {
        message = '金额格式不对：只能是正数且最多两位小数（如 12.50）';
      }
    } else if (rule === 'date') {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
        message = '日期格式不对，应为 YYYY-MM-DD';
      } else if (raw > todayStr()) {
        message = '日期不能晚于今天';
      } else if (raw < '2000-01-01') {
        message = '日期不能早于 2000-01-01';
      }
    }
    return { valid: !message, message: message };
  }

  function errorSlotFor(input) {
    var form = input.form;
    var name = input.getAttribute('name');
    if (!form || !name) return null;
    return form.querySelector('[data-error-for="' + name + '"]');
  }

  function paintValidation(input, result) {
    input.classList.toggle('is-invalid', !result.valid);
    input.setAttribute('aria-invalid', result.valid ? 'false' : 'true');
    var slot = errorSlotFor(input);
    if (slot) {
      slot.textContent = result.valid ? '' : result.message;
    }
  }

  APP.validateField = validateField;

  function initValidation() {
    APP.qsa('[data-validate]').forEach(function (input) {
      // 失焦时校验；输入过程中只在已报错或已有内容时实时校验
      input.addEventListener('blur', function () {
        paintValidation(input, validateField(input));
      });
      input.addEventListener('input', function () {
        if (input.classList.contains('is-invalid') || String(input.value).trim() !== '') {
          var result = validateField(input);
          if (!result.valid || input.classList.contains('is-invalid')) {
            paintValidation(input, result);
          }
        }
      });
    });
  }

  /* ---------- 8. 初始化 ---------- */
  function init() {
    initTheme();
    initSidebar();
    initValidation();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
