/* ==========================================================================
 * 轻记账 · records.js
 * 首页「快速记一笔」Ajax 提交 + 记账表单的分类随收支类型联动
 * 依赖：app.js（window.APP）
 * ========================================================================== */
(function () {
  'use strict';

  var APP = window.APP || {};
  var AMOUNT_RE = /^\d{1,8}(\.\d{1,2})?$/;

  function todayStr() {
    var now = new Date();
    return (
      now.getFullYear() +
      '-' +
      String(now.getMonth() + 1).padStart(2, '0') +
      '-' +
      String(now.getDate()).padStart(2, '0')
    );
  }

  /* ---------- 字段错误显示 ---------- */
  function setFieldError(form, name, message) {
    var slot = form.querySelector('[data-error-for="' + name + '"]');
    if (slot) {
      slot.textContent = message || '';
    }
    var input = form.querySelector('[name="' + name + '"]');
    if (input) {
      input.classList.toggle('is-invalid', !!message);
      if (message) {
        input.setAttribute('aria-invalid', 'true');
      } else {
        input.removeAttribute('aria-invalid');
      }
    }
  }

  function clearFieldErrors(form) {
    APP.qsa('[data-error-for]', form).forEach(function (slot) {
      slot.textContent = '';
    });
    APP.qsa('.is-invalid', form).forEach(function (input) {
      input.classList.remove('is-invalid');
      input.removeAttribute('aria-invalid');
    });
  }

  /* ---------- 分类下拉随 types 过滤 ---------- */
  function currentType(form) {
    var checked = form.querySelector('input[name="type"]:checked');
    return checked ? checked.value : 'expense';
  }

  function filterCategoriesByType(form, type) {
    var select = form.querySelector('select[name="category_id"]');
    if (!select) return;

    var firstMatch = null;
    var current = select.value;
    var currentOk = false;

    APP.qsa('option', select).forEach(function (option) {
      var optionType = option.getAttribute('data-type');
      if (!optionType) return; // “请选择分类 / 未分类”这类占位项
      var match = optionType === type;
      option.disabled = !match;
      option.hidden = !match;
      if (match) {
        if (!firstMatch) firstMatch = option;
        if (option.value === current) currentOk = true;
      }
    });

    APP.qsa('optgroup[data-type]', select).forEach(function (group) {
      var match = group.getAttribute('data-type') === type;
      group.disabled = !match;
      group.hidden = !match;
    });

    if (!currentOk) {
      select.value = firstMatch ? firstMatch.value : '';
    }
  }

  function bindTypeCategoryFilter(form) {
    var select = form.querySelector('select[name="category_id"]');
    if (!select) return;

    filterCategoriesByType(form, currentType(form));

    APP.qsa('input[name="type"]', form).forEach(function (radio) {
      radio.addEventListener('change', function () {
        if (radio.checked) {
          filterCategoriesByType(form, radio.value);
          setFieldError(form, 'category_id', '');
        }
      });
    });
  }

  /* ---------- 快速记账：前端校验 ---------- */
  function validateQuick(payload) {
    var errors = {};

    if (!payload.amount) {
      errors.amount = '请输入金额';
    } else if (!AMOUNT_RE.test(payload.amount) || Number(payload.amount) <= 0) {
      errors.amount = '金额格式不对：只能是正数且最多两位小数（如 12.50）';
    }

    if (!payload.category_id) {
      errors.category_id = '请选择分类';
    }

    if (!payload.record_date) {
      errors.record_date = '请选择日期';
    } else if (!/^\d{4}-\d{2}-\d{2}$/.test(payload.record_date)) {
      errors.record_date = '日期格式不对，应为 YYYY-MM-DD';
    } else if (payload.record_date > todayStr()) {
      errors.record_date = '日期不能晚于今天';
    } else if (payload.record_date < '2000-01-01') {
      errors.record_date = '日期不能早于 2000-01-01';
    }

    if (payload.note && payload.note.length > 200) {
      errors.note = '备注最多 200 个字';
    }

    return errors;
  }

  function initQuickForm(form) {
    bindTypeCategoryFilter(form);

    var submitBtn = form.querySelector('button[type="submit"]');
    var originalText = submitBtn ? submitBtn.textContent : '';

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      if (form.getAttribute('data-submitting') === '1') {
        return;
      }
      clearFieldErrors(form);

      var type = currentType(form);
      var payload = {
        amount: String((form.querySelector('[name="amount"]') || {}).value || '').trim(),
        type: type,
        category_id: (form.querySelector('[name="category_id"]') || {}).value || '',
        account_id: (form.querySelector('[name="account_id"]') || {}).value || '',
        record_date: (form.querySelector('[name="record_date"]') || {}).value || '',
        note: String((form.querySelector('[name="note"]') || {}).value || '').trim()
      };

      var errors = validateQuick(payload);
      var names = Object.keys(errors);
      if (names.length) {
        names.forEach(function (name) {
          setFieldError(form, name, errors[name]);
        });
        APP.toast('请检查表单中标红的字段', 'warning');
        var firstInput = form.querySelector('.is-invalid');
        if (firstInput && firstInput.focus) firstInput.focus();
        return;
      }

      var endpoint = form.getAttribute('data-endpoint');
      if (!endpoint) {
        APP.toast('表单缺少提交地址，请刷新页面重试', 'danger');
        return;
      }

      form.setAttribute('data-submitting', '1');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = '保存中…';
      }

      APP.api(endpoint, {
        method: 'POST',
        body: JSON.stringify({
          amount: payload.amount,
          type: payload.type,
          category_id: payload.category_id || null,
          account_id: payload.account_id || null,
          record_date: payload.record_date,
          note: payload.note
        })
      })
        .then(function () {
          APP.toast('记账成功', 'success');
          setTimeout(function () {
            window.location.reload();
          }, 600);
        })
        .catch(function (error) {
          if (error && error.field) {
            setFieldError(form, error.field, error.message);
          }
        })
        .then(function () {
          form.removeAttribute('data-submitting');
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText || '保存这笔记录';
          }
        });
    });
  }

  /* ---------- 记账表单（新增 / 编辑） ---------- */
  function initRecordForm(form) {
    bindTypeCategoryFilter(form);
  }

  function init() {
    var quickForm = document.getElementById('quick-record-form');
    if (quickForm) initQuickForm(quickForm);

    var recordForm = document.getElementById('record-form');
    if (recordForm) initRecordForm(recordForm);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
