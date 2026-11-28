import { BASE_PATH } from "./api.js";

export const VALID_TABS = new Set(["theory", "knowledge", "review", "mock_exam", "teacher", "profile"]);
export const VALID_TEACHER_SUBTABS = new Set([
  "members",
  "attendance",
  "exam_mixer",
  "content",
  "scores",
  "pw_alerts",
]);
export const VALID_CONTENT_SUBMODES = new Set([
  "add_topic",
  "add_question",
  "edit_lesson",
  "youtube",
  "import",
]);
export const VALID_EXAM_MIXER_MODES = new Set(["word", "matrix"]);

const ADMIN_SLUG_TO_SUBTAB = {
  members: "members",
  attendance: "attendance",
  "exam-mixer": "exam_mixer",
  exam_mixer: "exam_mixer",
  content: "content",
  scores: "scores",
  reports: "scores",
  "pw-alerts": "pw_alerts",
  pw_alerts: "pw_alerts",
};

const SUBTAB_TO_ADMIN_SLUG = {
  members: "members",
  attendance: "attendance",
  exam_mixer: "exam-mixer",
  content: "content",
  scores: "scores",
  pw_alerts: "pw-alerts",
};

export function stripBaseFromPathname(pathname = "/", basePath = BASE_PATH) {
  let path = String(pathname || "/");
  if (!path.startsWith("/")) path = "/" + path;
  if (basePath && basePath !== "/") {
    const cleanBase = "/" + String(basePath).replace(/^\/+|\/+$/g, "");
    if (path === cleanBase) return "/";
    if (path.startsWith(cleanBase + "/")) {
      path = path.slice(cleanBase.length) || "/";
    }
  }
  return path;
}

export function parseRoute(
  pathname = typeof window !== "undefined" ? window.location.pathname : "/",
  search = typeof window !== "undefined" ? window.location.search : "",
  basePath = BASE_PATH
) {
  const cleanPath = stripBaseFromPathname(pathname, basePath);
  const trimmed = cleanPath.replace(/^\/+|\/+$/g, "");
  const segments = trimmed ? trimmed.split("/").filter(Boolean) : [];
  const params = new URLSearchParams(search || "");

  const route = {
    hasExplicitRoute: false,
    activeTab: "theory",
    topicId: "",
    lessonId: "",
    theoryMode: "lessons",
    knowledgeMode: "source",
    knowledgeUnitIdx: 0,
    teacherSubtab: "members",
    teacherContentSubMode: "add_topic",
    teacherExamMixerMode: "word",
  };

  if (!segments.length) {
    return route;
  }

  const first = segments[0].toLowerCase();

  if (first === "topic" && segments[1]) {
    let topicId = segments[1];
    try {
      topicId = decodeURIComponent(segments[1]);
    } catch {}
    const sub = (segments[2] || "theory").toLowerCase();
    const tab = sub === "theory" || sub === "knowledge" || sub === "review" ? sub : "theory";
    route.hasExplicitRoute = true;
    route.topicId = topicId;
    route.activeTab = tab;

    if (tab === "theory") {
      const modeParam = (params.get("mode") || "").toLowerCase();
      route.theoryMode = modeParam === "youtube" ? "youtube" : "lessons";
      route.lessonId = params.get("lesson") || "";
    } else if (tab === "knowledge") {
      const modeParam = (params.get("mode") || "").toLowerCase();
      route.knowledgeMode = modeParam === "mindmap" ? "mindmap" : "source";
      const unitNum = parseInt(params.get("unit") || "0", 10);
      route.knowledgeUnitIdx = Number.isFinite(unitNum) && unitNum > 0 ? unitNum : 0;
    }
    return route;
  }

  if (first === "mock-exam" || first === "mock_exam") {
    route.hasExplicitRoute = true;
    route.activeTab = "mock_exam";
    return route;
  }

  if (first === "profile") {
    route.hasExplicitRoute = true;
    route.activeTab = "profile";
    return route;
  }

  if (first === "admin" || first === "teacher") {
    route.hasExplicitRoute = true;
    route.activeTab = "teacher";
    const subSlug = (segments[1] || "members").toLowerCase();
    route.teacherSubtab = ADMIN_SLUG_TO_SUBTAB[subSlug] || "members";

    if (route.teacherSubtab === "content") {
      const sec = (params.get("section") || "").toLowerCase();
      if (VALID_CONTENT_SUBMODES.has(sec)) {
        route.teacherContentSubMode = sec;
      }
    } else if (route.teacherSubtab === "exam_mixer") {
      const mode = (params.get("mode") || "").toLowerCase();
      if (VALID_EXAM_MIXER_MODES.has(mode)) {
        route.teacherExamMixerMode = mode;
      }
    }
    return route;
  }

  return route;
}

export function buildRouteUrl(routeState = {}, basePath = BASE_PATH) {
  const cleanBase =
    basePath && basePath !== "/" ? "/" + String(basePath).replace(/^\/+|\/+$/g, "") : "";
  const tab = VALID_TABS.has(routeState.activeTab) ? routeState.activeTab : "theory";

  if (tab === "teacher") {
    const sub = VALID_TEACHER_SUBTABS.has(routeState.teacherSubtab)
      ? routeState.teacherSubtab
      : "members";
    const slug = SUBTAB_TO_ADMIN_SLUG[sub] || "members";
    const q = new URLSearchParams();
    if (
      sub === "content" &&
      routeState.teacherContentSubMode &&
      VALID_CONTENT_SUBMODES.has(routeState.teacherContentSubMode) &&
      routeState.teacherContentSubMode !== "add_topic"
    ) {
      q.set("section", routeState.teacherContentSubMode);
    }
    if (
      sub === "exam_mixer" &&
      routeState.teacherExamMixerMode &&
      VALID_EXAM_MIXER_MODES.has(routeState.teacherExamMixerMode) &&
      routeState.teacherExamMixerMode !== "word"
    ) {
      q.set("mode", routeState.teacherExamMixerMode);
    }
    const qs = q.toString();
    return `${cleanBase}/admin/${slug}${qs ? `?${qs}` : ""}`;
  }

  if (tab === "mock_exam") {
    return `${cleanBase}/mock-exam`;
  }

  if (tab === "profile") {
    return `${cleanBase}/profile`;
  }

  const topicId = encodeURIComponent(routeState.topicId || "chu-de-1");
  const q = new URLSearchParams();
  if (tab === "theory") {
    if (routeState.theoryMode === "youtube") {
      q.set("mode", "youtube");
    } else if (routeState.lessonId) {
      q.set("lesson", routeState.lessonId);
    }
  } else if (tab === "knowledge") {
    if (routeState.knowledgeMode === "mindmap") {
      q.set("mode", "mindmap");
    } else if (Number(routeState.knowledgeUnitIdx || 0) > 0) {
      q.set("unit", String(Number(routeState.knowledgeUnitIdx)));
    }
  }
  const qs = q.toString();
  return `${cleanBase}/topic/${topicId}/${tab}${qs ? `?${qs}` : ""}`;
}

export function syncBrowserUrl(routeState, { replace = false, basePath = BASE_PATH } = {}) {
  if (typeof window === "undefined" || !window.history) return "";
  const targetUrl = buildRouteUrl(routeState, basePath);
  const currentUrl = window.location.pathname + window.location.search;
  if (currentUrl === targetUrl) return targetUrl;
  try {
    if (replace) {
      window.history.replaceState({ sh12Route: targetUrl }, "", targetUrl);
    } else {
      window.history.pushState({ sh12Route: targetUrl }, "", targetUrl);
    }
  } catch {}
  return targetUrl;
}

export function resetUrlToHome(basePath = BASE_PATH) {
  if (typeof window === "undefined" || !window.history) return;
  const cleanBase =
    basePath && basePath !== "/" ? "/" + String(basePath).replace(/^\/+|\/+$/g, "") : "";
  const homeUrl = `${cleanBase}/`;
  if (window.location.pathname + window.location.search === homeUrl) return;
  try {
    window.history.replaceState({ sh12Route: homeUrl }, "", homeUrl);
  } catch {}
}
