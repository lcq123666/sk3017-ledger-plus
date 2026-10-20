/* ==========================================================================
 * 轻记账 · stats.js
 * 统计页：6 个接口并发拉取 → 4 张指标卡 + 5 张 ECharts 图表
 * 交互：筛选变化重新拉取全部；点击饼图扇区联动当每日支出；主题切换重绘
 * 依赖：app.js（window.APP）、vendor/echarts.min.js
 * ========================================================================== */
(function () {
  'use strict';

  var page = document.getElementById('stats-page');
  if (!page || typeof window.echarts === 'undefined') {
    return;
  }

  var APP = window.APP || {};

  var URLS = {
    overview: page.getAttribute('data-overview-url'),
    pie: page.getAttribute('data-pie-url'),
    monthly: page.getAttribute('data-monthly-url'),
    daily: page.getAttribute('data-daily-url'),
    heatmap: page.getAttribute('data-heatmap-url'),
    top: page.getAttribute('data-top-url')
  };

  var state = {
    year: parseInt(page.getAttribute('data-default-year'), 10) || new Date().getFullYear(),
    month: parseInt(page.getAttribute('data-default-month'), 10) || new Date().getMonth() + 1,
    type: 'expense',
    categoryId: null,
    categoryName: ''
  };

  var charts = {};
  var lastData = {
    overview: null,
    pie: null,
    monthly: null,
    daily: null,
    heatmap: null,
    top: null
  };

  /* ---------- 基础工具 ---------- */
  function $(id) {
    return document.getElementById(id);
  }

  function setText(id, text) {
    var el = $(id);
    if (el) el.textContent = text;
  }

  function setHtml(id, html) {
    var el = $(id);
    if (el) el.innerHTML = html;
  }

  function money(value) {
    var num = Number(value || 0);
    if (!isFinite(num)) num = 0;
    return num.toLocaleString('zh-CN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  }

  function moneyText(value) {
    return '¥' + money(value);
  }

  function shortNumber(value) {
    var num = Number(value || 0);
    if (!isFinite(num)) return '0';
    if (Math.abs(num) >= 10000) {
      return (num / 10000).toFixed(1) + '万';
    }
    return String(Math.round(num));
  }

  function isDark() {
    return document.documentElement.getAttribute('data-theme') === 'dark';
  }

  function palette() {
    if (isDark()) {
      return {
        text: '#aebbd0',
        muted: '#7c8aa3',
        axis: '#33415e',
        split: 'rgba(148, 163, 184, 0.16)',
        cellBorder: '#0b1020',
        tooltipBg: 'rgba(20, 27, 45, 0.96)',
        tooltipBorder: '#33415e',
        tooltipText: '#e8edf7',
        income: '#4ade80',
        expense: '#f87171',
        selected: '#a5b4fc'
      };
    }
    return {
      text: '#475569',
      muted: '#94a3b8',
      axis: '#d7dded',
      split: 'rgba(148, 163, 184, 0.22)',
      cellBorder: '#ffffff',
      tooltipBg: 'rgba(255, 255, 255, 0.98)',
      tooltipBorder: '#e5e9f2',
      tooltipText: '#0f172a',
      income: '#16a34a',
      expense: '#ef4444',
      selected: '#6366f1'
    };
  }

  function tooltipStyle(p) {
    return {
      backgroundColor: p.tooltipBg,
      borderColor: p.tooltipBorder,
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: p.tooltipText, fontSize: 12 },
      extraCssText: 'border-radius:10px;box-shadow:0 10px 30px -14px rgba(15,23,42,.45);'
    };
  }

  function getChart(id) {
    var el = $(id);
    if (!el) return null;
    if (!charts[id]) {
      charts[id] = window.echarts.init(el);
    }
    return charts[id];
  }

  function emptyOption(text) {
    var p = palette();
    return {
      animationDuration: 300,
      graphic: [
        {
          type: 'text',
          left: 'center',
          top: 'middle',
          silent: true,
          style: { text: text, fill: p.muted, fontSize: 13, fontWeight: 500 }
        }
      ]
    };
  }

  /* ---------- 指标卡 ---------- */
  function rateHtml(label, rate) {
    var cls = 'rate-flat';
    var text = '—';
    var value = rate === null || rate === undefined ? NaN : Number(rate);
    if (isFinite(value)) {
      cls = value > 0 ? 'rate-up' : value < 0 ? 'rate-down' : 'rate-flat';
      text = (value > 0 ? '+' : '') + value.toFixed(1) + '%';
    }
    return label + ' <span class="' + cls + '">' + text + '</span>';
  }

  function renderCards(overview) {
    var o = overview || {};
    var income = Number(o.income || 0);
    var expense = Number(o.expense || 0);
    var balance = Number(o.balance || 0);
    var count = Number(o.count || 0);

    setText('stat-income-value', moneyText(income));
    setText('stat-expense-value', moneyText(expense));

    var balanceEl = $('stat-balance-value');
    if (balanceEl) {
      balanceEl.textContent = (balance < 0 ? '-' : '') + moneyText(Math.abs(balance));
      balanceEl.classList.remove('text-income', 'text-expense');
      balanceEl.classList.add(balance < 0 ? 'text-expense' : 'text-income');
    }
    var balanceCard = $('stat-balance-card');
    if (balanceCard) {
      balanceCard.classList.remove('tone-income', 'tone-expense');
      balanceCard.classList.add(balance < 0 ? 'tone-expense' : 'tone-income');
    }

    var mom = o.mom || {};
    var yoy = o.yoy || {};
    setHtml(
      'stat-income-hint',
      rateHtml('环比', mom.income_rate) + ' · ' + rateHtml('同比', yoy.income_rate)
    );
    setHtml(
      'stat-expense-hint',
      rateHtml('环比', mom.expense_rate) + ' · ' + rateHtml('同比', yoy.expense_rate)
    );
    setHtml(
      'stat-balance-hint',
      rateHtml('环比', mom.balance_rate) + ' · 本月共 ' + count + ' 笔记录'
    );

    var budget = o.budget || null;
    var budgetEl = $('stat-budget-value');
    if (budget && Number(budget.amount) > 0) {
      var usage = Number(budget.usage || 0);
      if (budgetEl) {
        budgetEl.textContent = usage.toFixed(1) + '%';
        budgetEl.classList.remove('text-income', 'text-expense', 'text-income');
        budgetEl.classList.add(budget.level === 'over' ? 'text-expense' : 'text-income');
      }
      setText(
        'stat-budget-hint',
        '已用 ' + moneyText(budget.spent) + ' / 预算 ' + moneyText(budget.amount)
      );
    } else {
      if (budgetEl) {
        budgetEl.textContent = '—';
        budgetEl.classList.remove('text-income', 'text-expense');
      }
      setText('stat-budget-hint', '本月未设置预算');
    }
  }

  /* ---------- 各图表标题 / 提示 ---------- */
  function syncTitles() {
    var typeLabel = state.type === 'income' ? '收入' : '支出';
    setText('pie-title', typeLabel + '分类占比');
    setText('top-title', typeLabel + ' TOP5');

    var pieHint = $('pie-hint');
    if (pieHint) {
      pieHint.textContent =
        state.categoryId != null
          ? '已筛选：' + state.categoryName + '（再点扇区取消）'
          : '点击扇区查看每日走势';
    }
    var dailyHint = $('daily-hint');
    if (dailyHint) {
      dailyHint.textContent =
        state.categoryId != null ? '当前分类：' + state.categoryName : '单位：元';
    }
    var dailyTitle = $('daily-title');
    if (dailyTitle) {
      dailyTitle.textContent =
        state.categoryId != null ? '当月每日支出 · ' + state.categoryName : '当月每日支出';
    }
    var periodLabel = $('stats-period-label');
    if (periodLabel) {
      periodLabel.textContent =
        state.year + ' 年 ' + state.month + ' 月 · ' + typeLabel + '视角';
    }
  }

  /* ---------- 1. 分类占比（环形饼图） ---------- */
  function renderPie(data) {
    var chart = getChart('chart-category-pie');
    if (!chart) return;
    var items = (data && data.items) || [];
    var p = palette();

    if (!items.length) {
      chart.setOption(emptyOption('本月暂无数据'), true);
      bindPieClick(chart);
      return;
    }

    var seriesData = items.map(function (item) {
      var selected = state.categoryId != null && item.id === state.categoryId;
      return {
        name: item.name,
        value: item.value,
        id: item.id,
        selected: selected,
        itemStyle: {
          color: item.color || p.selected,
          borderColor: isDark() ? '#141b2d' : '#ffffff',
          borderWidth: 2,
          borderRadius: 6
        }
      };
    });

    chart.setOption(
      {
        animationDuration: 600,
        tooltip: Object.assign(
          {
            trigger: 'item',
            formatter: function (params) {
              return (
                params.marker +
                params.name +
                '<br/>金额：' + moneyText(params.value) +
                '<br/>占比：' + (params.percent != null ? params.percent : 0) + '%'
              );
            }
          },
          tooltipStyle(p)
        ),
        legend: {
          type: 'scroll',
          bottom: 0,
          left: 'center',
          icon: 'circle',
          itemWidth: 8,
          itemHeight: 8,
          textStyle: { color: p.text, fontSize: 11 },
          pageTextStyle: { color: p.text }
        },
        series: [
          {
            name: '分类占比',
            type: 'pie',
            radius: ['46%', '70%'],
            center: ['50%', '46%'],
            avoidLabelOverlap: true,
            selectedMode: 'single',
            label: {
              show: true,
              color: p.text,
              fontSize: 11,
              formatter: '{b}\n{d}%'
            },
            labelLine: { length: 10, length2: 10, lineStyle: { color: p.axis } },
            emphasis: {
              scaleSize: 6,
              itemStyle: { shadowBlur: 16, shadowColor: 'rgba(79, 70, 229, 0.35)' }
            },
            data: seriesData
          }
        ]
      },
      true
    );
    bindPieClick(chart);
  }

  function bindPieClick(chart) {
    chart.off('click');
    chart.on('click', function (params) {
      var item = params && params.data;
      if (!item) return;
      var id = item.id;
      if (id === null || id === undefined) {
        if (state.categoryId != null) {
          state.categoryId = null;
          state.categoryName = '';
          syncTitles();
          renderPie(lastData.pie);
          loadDaily();
        } else if (APP.toast) {
          APP.toast('「其他」是合并后的分类，无法单独查看日报', 'info');
        }
        return;
      }
      if (state.categoryId === id) {
        state.categoryId = null;
        state.categoryName = '';
      } else {
        state.categoryId = id;
        state.categoryName = item.name;
      }
      syncTitles();
      // 先按选中状态重绘饼图，再拉取该分类的每日支出
      renderPie(lastData.pie);
      loadDaily();
    });
  }

  /* ---------- 2. 近 6 个月收支趋势（并列柱状图） ---------- */
  function renderMonthly(data) {
    var chart = getChart('chart-monthly-trend');
    if (!chart) return;
    var p = palette();
    var labels = (data && data.labels) || [];
    var incomes = (data && data.income) || [];
    var expenses = (data && data.expense) || [];
    var hasData =
      labels.length > 0 &&
      (incomes.some(function (v) { return Number(v) > 0; }) ||
        expenses.some(function (v) { return Number(v) > 0; }));

    if (!hasData) {
      chart.setOption(emptyOption('近 6 个月暂无数据'), true);
      return;
    }

    chart.setOption(
      {
        animationDuration: 600,
        color: [p.income, p.expense],
        tooltip: Object.assign(
          {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            valueFormatter: function (value) {
              return moneyText(value);
            }
          },
          tooltipStyle(p)
        ),
        legend: {
          top: 0,
          right: 4,
          icon: 'roundRect',
          itemWidth: 10,
          itemHeight: 10,
          textStyle: { color: p.text, fontSize: 12 }
        },
        grid: { left: 8, right: 16, top: 40, bottom: 6, containLabel: true },
        xAxis: {
          type: 'category',
          data: labels,
          axisLine: { lineStyle: { color: p.axis } },
          axisTick: { show: false },
          axisLabel: { color: p.text, fontSize: 11 }
        },
        yAxis: {
          type: 'value',
          splitLine: { lineStyle: { color: p.split } },
          axisLabel: { color: p.text, fontSize: 11, formatter: shortNumber }
        },
        series: [
          {
            name: '收入',
            type: 'bar',
            data: incomes,
            barMaxWidth: 22,
            itemStyle: { borderRadius: [5, 5, 0, 0] }
          },
          {
            name: '支出',
            type: 'bar',
            data: expenses,
            barMaxWidth: 22,
            itemStyle: { borderRadius: [5, 5, 0, 0] }
          }
        ]
      },
      true
    );
  }

  /* ---------- 3. 当月每日支出（面积折线） ---------- */
  function renderDaily(data) {
    var chart = getChart('chart-daily-trend');
    if (!chart) return;
    var p = palette();
    var labels = (data && data.labels) || [];
    var expenses = (data && data.expense) || [];
    var hasData = expenses.some(function (v) { return Number(v) > 0; });

    if (!labels.length || !hasData) {
      chart.setOption(
        emptyOption(state.categoryId != null ? '该分类本月暂无数据' : '本月暂无数据'),
        true
      );
      return;
    }

    var expenseColor = p.expense;
    chart.setOption(
      {
        animationDuration: 600,
        tooltip: Object.assign(
          {
            trigger: 'axis',
            valueFormatter: function (value) {
              return moneyText(value);
            }
          },
          tooltipStyle(p)
        ),
        grid: { left: 8, right: 16, top: 22, bottom: 6, containLabel: true },
        xAxis: {
          type: 'category',
          boundaryGap: false,
          data: labels,
          axisLine: { lineStyle: { color: p.axis } },
          axisTick: { show: false },
          axisLabel: { color: p.text, fontSize: 11, interval: 4 }
        },
        yAxis: {
          type: 'value',
          splitLine: { lineStyle: { color: p.split } },
          axisLabel: { color: p.text, fontSize: 11, formatter: shortNumber }
        },
        series: [
          {
            name: '支出',
            type: 'line',
            smooth: true,
            showSymbol: false,
            data: expenses,
            lineStyle: { width: 2.5, color: expenseColor },
            itemStyle: { color: expenseColor },
            emphasis: { focus: 'series' },
            areaStyle: {
              color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: isDark() ? 'rgba(248, 113, 113, 0.32)' : 'rgba(239, 68, 68, 0.26)' },
                { offset: 1, color: 'rgba(239, 68, 68, 0)' }
              ])
            }
          }
        ]
      },
      true
    );
  }

  /* ---------- 4. 年度支出日历热力图 ---------- */
  function renderHeatmap(data) {
    var chart = getChart('chart-heatmap');
    if (!chart) return;
    var p = palette();
    var values = (data && data.values) || [];

    if (!values.length) {
      chart.setOption(emptyOption('当年暂无支出数据'), true);
      return;
    }

    var maxValue = Math.max(Number((data && data.max) || 0), 1);

    chart.setOption(
      {
        animationDuration: 600,
        tooltip: Object.assign(
          {
            formatter: function (params) {
              var value = params.value || [];
              return (value[0] || '') + '<br/>支出：' + moneyText(value[1] || 0);
            }
          },
          tooltipStyle(p)
        ),
        visualMap: {
          min: 0,
          max: maxValue,
          orient: 'horizontal',
          left: 'center',
          bottom: 0,
          itemWidth: 12,
          itemHeight: 100,
          textStyle: { color: p.text, fontSize: 11 },
          inRange: {
            color: isDark()
              ? ['#1e293b', '#3730a3', '#6366f1', '#a5b4fc']
              : ['#eef2ff', '#c7d2fe', '#818cf8', '#4f46e5']
          }
        },
        calendar: {
          range: String((data && data.year) || state.year),
          left: 46,
          right: 20,
          top: 34,
          bottom: 46,
          cellSize: ['auto', 13],
          orient: 'horizontal',
          yearLabel: { show: true, color: p.text, fontSize: 12, fontWeight: 600 },
          monthLabel: { color: p.text, fontSize: 11 },
          dayLabel: { color: p.muted, fontSize: 10, firstDay: 1 },
          itemStyle: {
            color: 'transparent',
            borderColor: isDark() ? '#1a2336' : '#f8fafc',
            borderWidth: 2
          },
          splitLine: { lineStyle: { color: p.split } }
        },
        series: [
          {
            type: 'heatmap',
            coordinateSystem: 'calendar',
            data: values,
            itemStyle: { borderRadius: 2 }
          }
        ]
      },
      true
    );
  }

  /* ---------- 5. 支出 TOP5（横向条形图） ---------- */
  function renderTop(data) {
    var chart = getChart('chart-top');
    if (!chart) return;
    var p = palette();
    var items = ((data && data.items) || []).slice();

    if (!items.length) {
      chart.setOption(emptyOption('本月暂无数据'), true);
      return;
    }

    items.sort(function (a, b) {
      return Number(a.value) - Number(b.value);
    });

    var names = items.map(function (item) { return item.name; });
    var seriesData = items.map(function (item) {
      return {
        value: Number(item.value) || 0,
        percent: item.percent,
        itemStyle: { color: item.color || p.selected, borderRadius: [0, 6, 6, 0] }
      };
    });

    chart.setOption(
      {
        animationDuration: 600,
        tooltip: Object.assign(
          {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            formatter: function (params) {
              var first = (params && params[0]) || {};
              var percent = first.data && first.data.percent != null ? first.data.percent : '';
              return (
                (first.marker || '') +
                first.name +
                '<br/>金额：' + moneyText(first.value) +
                (percent !== '' ? '<br/>占比：' + percent + '%' : '')
              );
            }
          },
          tooltipStyle(p)
        ),
        grid: { left: 8, right: 62, top: 8, bottom: 6, containLabel: true },
        xAxis: {
          type: 'value',
          splitLine: { lineStyle: { color: p.split } },
          axisLabel: { color: p.text, fontSize: 11, formatter: shortNumber }
        },
        yAxis: {
          type: 'category',
          data: names,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { color: p.text, fontSize: 12 }
        },
        series: [
          {
            name: '金额',
            type: 'bar',
            data: seriesData,
            barMaxWidth: 20,
            label: {
              show: true,
              position: 'right',
              color: p.text,
              fontSize: 11,
              formatter: function (params) {
                return moneyText(params.value);
              }
            }
          }
        ]
      },
      true
    );
  }

  /* ---------- 数据拉取 ---------- */
  function queryBase() {
    return '?year=' + state.year + '&month=' + state.month;
  }

  function dailyQuery() {
    var query = queryBase();
    if (state.categoryId != null) {
      query += '&category_id=' + encodeURIComponent(state.categoryId);
    }
    return query;
  }

  function fetchJson(url) {
    return APP.api(url, { silent: true }).catch(function () {
      return null;
    });
  }

  function fetchAll() {
    syncTitles();
    var base = queryBase();
    var requests = [
      fetchJson(URLS.overview + base),
      fetchJson(URLS.pie + base + '&type=' + encodeURIComponent(state.type)),
      fetchJson(
        URLS.monthly +
          '?end_year=' + state.year +
          '&end_month=' + state.month +
          '&months=6'
      ),
      fetchJson(URLS.daily + dailyQuery()),
      fetchJson(URLS.heatmap + '?year=' + state.year),
      fetchJson(
        URLS.top +
          base +
          '&type=' + encodeURIComponent(state.type) +
          '&limit=5'
      )
    ];

    return Promise.all(requests).then(function (results) {
      var failed = results.filter(function (item) { return item === null; }).length;
      if (failed === results.length) {
        APP.toast('统计数据加载失败，请稍后重试', 'danger');
      }

      lastData.overview = results[0];
      lastData.pie = results[1];
      lastData.monthly = results[2];
      lastData.daily = results[3];
      lastData.heatmap = results[4];
      lastData.top = results[5];

      renderCards(lastData.overview);
      renderPie(lastData.pie);
      renderMonthly(lastData.monthly);
      renderDaily(lastData.daily);
      renderHeatmap(lastData.heatmap);
      renderTop(lastData.top);

      var updated = $('stats-updated');
      if (updated) {
        var now = new Date();
        updated.textContent =
          '更新于 ' +
          String(now.getHours()).padStart(2, '0') + ':' +
          String(now.getMinutes()).padStart(2, '0') + ':' +
          String(now.getSeconds()).padStart(2, '0');
      }
    });
  }

  function loadDaily() {
    fetchJson(URLS.daily + dailyQuery()).then(function (data) {
      lastData.daily = data;
      renderDaily(data);
    });
  }

  /* ---------- 事件绑定 ---------- */
  function readFilters() {
    var yearEl = $('stats-year');
    var monthEl = $('stats-month');
    var typeEl = $('stats-type');
    state.year = parseInt(yearEl && yearEl.value, 10) || state.year;
    state.month = parseInt(monthEl && monthEl.value, 10) || state.month;
    state.type = (typeEl && typeEl.value) || 'expense';
  }

  function bindEvents() {
    ['stats-year', 'stats-month', 'stats-type'].forEach(function (id) {
      var el = $(id);
      if (!el) return;
      el.addEventListener('change', function () {
        readFilters();
        // 换月份/类型后原来的分类筛选不再有意义，重置
        state.categoryId = null;
        state.categoryName = '';
        fetchAll();
      });
    });

    var refresh = $('stats-refresh');
    if (refresh) {
      refresh.addEventListener('click', function () {
        readFilters();
        fetchAll();
      });
    }

    window.addEventListener(
      'resize',
      APP.debounce(function () {
        Object.keys(charts).forEach(function (id) {
          if (charts[id]) charts[id].resize();
        });
      }, 160)
    );

    window.addEventListener('themechange', function () {
      // 用新主题色重绘全部图表（不重新请求接口）
      renderCards(lastData.overview);
      renderPie(lastData.pie);
      renderMonthly(lastData.monthly);
      renderDaily(lastData.daily);
      renderHeatmap(lastData.heatmap);
      renderTop(lastData.top);
    });
  }

  function init() {
    readFilters();
    bindEvents();
    fetchAll();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
