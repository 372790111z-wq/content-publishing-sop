(function () {
  "use strict";

  var data = window.CONTENT_SOP_DATA || { generated_at: null, summary: {}, projects: [] };
  var state = { selectedId: null, query: "", status: "all", issuesOnly: false };
  var select = function (selector) { return document.querySelector(selector); };

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>'"]/g, function (character) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;" }[character];
    });
  }

  function statusLabel(status) {
    var labels = {
      published: "已发布",
      paused: "已暂停",
      ready_to_publish: "可发布",
      blocked: "阻塞",
      under_review: "审核中",
      submitted: "已提交",
      failed: "失败",
      verified: "已验证",
      pending: "等待",
      unknown: "未知",
      passed: "通过",
      draft: "草稿",
      not_started: "未开始",
      not_collected: "未采集",
      captured: "已采集",
      partial: "部分采集",
      unavailable: "不可获取",
      frozen: "已冻结",
      active: "有效",
      consumed: "已消费"
    };
    return labels[status] || status || "未知";
  }

  function badge(status) {
    var safeStatus = escapeHtml(status || "unknown");
    return '<span class="badge badge--' + safeStatus + '">' + escapeHtml(statusLabel(status)) + "</span>";
  }

  function dateText(value) {
    if (!value) return "未知";
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(date);
  }

  function valueText(value) {
    return value === null || value === undefined
      ? '<span class="unknown">unknown</span>'
      : escapeHtml(value);
  }

  function valueWithTrend(value, delta) {
    var trend = "";
    if (typeof delta === "number") {
      trend = '<small class="metric-delta metric-delta--' + (delta >= 0 ? "up" : "down") + '">' +
        (delta >= 0 ? "+" : "") + escapeHtml(delta) + "</small>";
    }
    return valueText(value) + trend;
  }

  function sourceLabel(source) {
    var labels = {
      platform_api: "平台 API",
      creator_backend: "创作者后台",
      public_page: "公开页面",
      manual: "人工录入",
      unknown: "未知"
    };
    return labels[source] || source || "未知";
  }

  function evidenceHtml(evidence) {
    if (!Array.isArray(evidence) || !evidence.length) {
      return '<span class="unknown">无</span>';
    }
    return evidence.map(function (item) {
      var value = String(item || "");
      if (/^https?:\/\//i.test(value)) {
        return '<a href="' + escapeHtml(value) + '" target="_blank" rel="noreferrer">查看来源</a>';
      }
      return '<span>' + escapeHtml(value) + "</span>";
    }).join("<br>");
  }

  function setSummary() {
    var platformStatuses = (data.summary && data.summary.platform_statuses) || {};
    var readerFailures = data.projects.reduce(function (count, project) {
      return count + project.platforms.filter(function (platform) {
        return platform.reader_validation === "failed";
      }).length;
    }, 0);
    var blockedProjects = data.projects.filter(function (project) {
      return project.validation && project.validation.status === "blocked";
    }).length;
    select("#summary-projects").textContent = (data.summary && data.summary.projects) || 0;
    select("#summary-examples").textContent = (data.summary && data.summary.examples) || 0;
    select("#summary-published").textContent = platformStatuses.published || 0;
    select("#summary-pending").textContent =
      (platformStatuses.under_review || 0) +
      (platformStatuses.submitted || 0) +
      (platformStatuses.awaiting_authorization || 0);
    select("#summary-blocked").textContent =
      (platformStatuses.failed || 0) + (platformStatuses.paused || 0) + readerFailures + blockedProjects;
    var metrics = (data.summary && data.summary.metrics) || {};
    select("#summary-metrics").textContent =
      (metrics.complete_published_platforms || 0) + "/" + (metrics.published_platforms || 0);
    select("#generated-at").textContent = dateText(data.generated_at);
  }

  function filteredProjects() {
    return data.projects.filter(function (project) {
      var platformNames = project.platforms.map(function (item) { return item.platform; });
      var haystack = [project.project_id, project.title, project.summary]
        .concat(platformNames)
        .join(" ")
        .toLowerCase();
      var queryMatch = !state.query || haystack.indexOf(state.query.toLowerCase()) >= 0;
      var statusMatch = state.status === "all" || project.status === state.status;
      var gateStatus = project.validation && project.validation.status;
      var hasIssue = ["blocked", "failed", "pending", "unknown"].indexOf(gateStatus) >= 0 ||
        project.platforms.some(function (item) {
          return item.reader_validation === "failed" || Boolean(item.blocker);
        }) || Object.keys(project.metrics || {}).some(function (platform) {
          return ["not_collected", "failed"].indexOf(project.metrics[platform].collection_status) >= 0;
        });
      return queryMatch && statusMatch && (!state.issuesOnly || hasIssue);
    });
  }

  function renderList() {
    var projects = filteredProjects();
    var list = select("#project-list");
    select("#empty-state").hidden = projects.length > 0;
    if (!projects.length) {
      list.innerHTML = "";
      select("#project-detail").innerHTML = '<div class="empty-detail">没有符合当前条件的内容项目。运行 <code>content-publishing new-project --help</code> 创建第一个项目；命令不会替你编造验收证据。</div>';
      return;
    }
    if (!projects.some(function (project) { return project.project_id === state.selectedId; })) {
      state.selectedId = projects[0].project_id;
    }
    list.innerHTML = projects.map(function (project) {
      return [
        '<button class="project-button" type="button" data-project-id="', escapeHtml(project.project_id),
        '" aria-current="', project.project_id === state.selectedId, '">',
        '<div class="project-button__top"><span class="project-button__id">', project.kind === "example" ? "DEMO · " : "", escapeHtml(project.project_id),
        "</span>", badge(project.status), "</div>",
        "<h3>", escapeHtml(project.title), "</h3>",
        '<div class="project-button__meta"><span>', project.counts.platforms,
        " 个平台</span><span>门禁 ", escapeHtml(statusLabel(project.validation && project.validation.status)),
        "</span></div></button>"
      ].join("");
    }).join("");
    Array.prototype.forEach.call(list.querySelectorAll("button"), function (button) {
      button.addEventListener("click", function () {
        state.selectedId = button.dataset.projectId;
        renderList();
      });
    });
    renderDetail();
  }

  function renderTimeline(events) {
    return '<div class="timeline">' + events.map(function (event) {
      return [
        '<article class="timeline-item"><div class="timeline-item__number">',
        String(event.sequence).padStart(2, "0"),
        '</div><div><div class="timeline-item__stage">', escapeHtml(event.stage),
        "</div><h4>", escapeHtml(event.summary), "</h4>",
        event.details ? "<p>" + escapeHtml(event.details) + "</p>" : "",
        "</div></article>"
      ].join("");
    }).join("") + "</div>";
  }

  function renderPlatforms(platforms) {
    return '<div class="platform-grid">' + platforms.map(function (item) {
      var publicLink = item.public_url
        ? '<a href="' + escapeHtml(item.public_url) + '" target="_blank" rel="noreferrer">打开页面</a>'
        : '<span class="unknown">unknown</span>';
      return [
        '<article class="platform-card"><div class="platform-card__top"><h4>',
        escapeHtml(item.platform), "</h4>", badge(item.status), "</div><dl>",
        "<dt>读者验收</dt><dd>", badge(item.reader_validation), "</dd>",
        "<dt>提示词交付</dt><dd>", escapeHtml(item.prompt_delivery || "unknown"), "</dd>",
        "<dt>线上版本</dt><dd>", item.release_digest ? "<code>" + escapeHtml(item.release_digest.slice(0, 12)) + "…</code>" : '<span class="unknown">unknown</span>', "</dd>",
        "<dt>公开入口</dt><dd>", publicLink, "</dd></dl>",
        item.blocker ? '<div class="platform-card__blocker">' + escapeHtml(item.blocker) + "</div>" : "",
        "</article>"
      ].join("");
    }).join("") + "</div>";
  }

  function renderMetrics(project) {
    var rows = project.platforms.map(function (platform) {
      var snapshot = (project.metrics && project.metrics[platform.platform]) || {};
      var values = snapshot.values || {};
      var trends = (project.metrics_trends && project.metrics_trends[platform.platform]) || {};
      return [
        "<tr><td>", escapeHtml(platform.platform), "</td><td>", badge(snapshot.collection_status || "not_collected"),
        "</td><td>", escapeHtml(dateText(snapshot.captured_at || snapshot.attempted_at)),
        "</td><td>", escapeHtml(sourceLabel(snapshot.source)),
        "</td><td>", valueWithTrend(values.views, trends.views),
        "</td><td>", valueWithTrend(values.likes, trends.likes), "</td><td>", valueWithTrend(values.favorites, trends.favorites),
        "</td><td>", valueWithTrend(values.comments, trends.comments), "</td><td>", valueWithTrend(values.shares, trends.shares),
        '</td><td class="metrics-evidence">', evidenceHtml(snapshot.evidence),
        "</td></tr>"
      ].join("");
    }).join("");
    var summary = project.metrics_summary || {};
    var published = summary.published_platforms || 0;
    var complete = summary.complete_published_platforms || 0;
    return [
      '<div class="metrics-overview"><div><strong>', complete, "/", published,
      '</strong><span>已发布平台指标闭环</span></div><div><strong>',
      escapeHtml(dateText(summary.latest_at)), '</strong><span>最近采集或尝试</span></div></div>',
      '<div class="table-wrap"><table class="metrics-table"><thead><tr>',
      "<th>平台</th><th>采集状态</th><th>时间</th><th>来源</th><th>浏览 / 变化</th><th>点赞 / 变化</th><th>收藏 / 变化</th><th>评论 / 变化</th><th>分享 / 变化</th><th>证据</th>",
      "</tr></thead><tbody>", rows, "</tbody></table></div>"
    ].join("");
  }

  function renderDetail() {
    var project = data.projects.find(function (item) { return item.project_id === state.selectedId; });
    if (!project) return;
    var validationStatus = (project.validation && project.validation.status) || "unknown";
    var sourceWork = project.source_work || {};
    var activeGrants = Array.isArray(project.active_grants) ? project.active_grants : [];
    var publishGrants = activeGrants.filter(function (grant) {
      return ["public_publish", "update_publication"].indexOf(grant.action) >= 0;
    });
    var publishAuthorized = publishGrants.length > 0;
    var releaseFrozen = project.release && project.release.status === "frozen";
    var editorial = project.editorial || {};
    var editorialReady = editorial.author_voice_status === "verified" &&
      editorial.verified_reviews === editorial.required_reviews;
    var stats = [
      [project.counts.decisions, "决策节点"],
      [project.counts.deliverables, "内容文件"],
      [project.counts.images, "图片"],
      [project.counts.videos, "视频"],
      [project.counts.platforms, "平台"],
      [project.counts.receipts || 0, "发布回执"]
    ];
    var statsHtml = stats.map(function (item) {
      return '<div class="detail-stat"><strong>' + item[0] + "</strong><span>" + item[1] + "</span></div>";
    }).join("");
    select("#project-detail").innerHTML = [
      '<header class="detail-head"><div><div class="section-label">', escapeHtml(project.project_id),
      "</div><h2>", escapeHtml(project.title), "</h2><p>", escapeHtml(project.summary),
      '</p></div><div class="gate-stamp gate-stamp--', escapeHtml(validationStatus), '">',
      escapeHtml(statusLabel(validationStatus)), "<span>CONTENT GATE</span></div></header>",
      '<div class="source-banner"><div class="source-banner__label">已验收来源需求</div><div><strong>',
      escapeHtml(sourceWork.title || "来源需求未登记"), "</strong><small>",
      escapeHtml(sourceWork.reuse_reason || "未记录复用理由"), "</small></div><div class=\"source-banner__time\">",
      escapeHtml(dateText(sourceWork.accepted_at)), "</div></div>",
      '<div class="detail-stats">', statsHtml, "</div>",
      '<div class="authorization-banner"><div class="authorization-banner__icon">',
      publishAuthorized ? "✓" : "×", "</div><div><strong>",
      publishAuthorized ? "最终内容与平台清单已确认" : "等待最终内容与平台清单确认",
      "</strong><small>", publishAuthorized
        ? escapeHtml(publishGrants.map(function (grant) { return grant.id + " → " + grant.platforms.join("、"); }).join("；"))
        : escapeHtml((project.authorization && project.authorization.note) || "确认后将直接生成一次性发布授权，不再二次询问"),
      "</small></div>", badge(publishAuthorized ? "verified" : "blocked"), "</div>",
      '<div class="authorization-banner"><div class="authorization-banner__icon">', releaseFrozen ? "✓" : "×",
      "</div><div><strong>", releaseFrozen ? "内容版本已冻结" : "内容版本尚未冻结",
      "</strong><small>", escapeHtml((project.release && project.release.release_digest) || "没有 release digest"),
      "</small></div>", badge((project.release && project.release.status) || "unknown"), "</div>",
      '<div class="authorization-banner"><div class="authorization-banner__icon">', editorialReady ? "✓" : "×",
      "</div><div><strong>", editorialReady ? "个人表达与逐稿审校已完成" : "个人表达或逐稿审校未完成",
      "</strong><small>个人表达：", escapeHtml(statusLabel(editorial.author_voice_status)),
      "；平台档案：", escapeHtml(editorial.platform_profiles || 0),
      "；逐稿审校：", escapeHtml(editorial.verified_reviews || 0), "/", escapeHtml(editorial.required_reviews || 0),
      "</small></div>", badge(editorialReady ? "verified" : (editorial.author_voice_status || "unknown")), "</div>",
      '<div class="section-heading"><h3>平台状态</h3><span>作者后台状态 ≠ 公开读者结果</span></div>',
      renderPlatforms(project.platforms),
      '<div class="section-heading"><h3>文章覆盖的完整需求过程</h3><span>',
      project.decisions.length, " 个节点</span></div>", renderTimeline(project.decisions),
      '<div class="section-heading"><h3>效果数据</h3><span>unknown = 未采集；0 = 有证据的真实零值</span></div>',
      renderMetrics(project)
    ].join("");
  }

  select("#search").addEventListener("input", function (event) {
    state.query = event.target.value.trim();
    renderList();
  });
  select("#status-filter").addEventListener("change", function (event) {
    state.status = event.target.value;
    renderList();
  });
  select("#issues-only").addEventListener("change", function (event) {
    state.issuesOnly = event.target.checked;
    renderList();
  });

  setSummary();
  renderList();
})();
