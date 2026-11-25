// Thư viện Video bài giảng YouTube theo từng Chủ đề / Bài học
// Giáo viên tự nhúng, sắp xếp và quản lý đường dẫn YouTube ngay trong từng Chủ đề

import { api } from "./api.js";
import { escapeHtml } from "./format.js";

export function parseYoutubeId(url) {
  if (!url) return null;
  const s = String(url).trim();
  const patterns = [
    /(?:youtube\.com\/watch\?v=)([A-Za-z0-9_-]{6,})/,
    /(?:youtu\.be\/)([A-Za-z0-9_-]{6,})/,
    /(?:youtube\.com\/embed\/)([A-Za-z0-9_-]{6,})/,
    /(?:youtube\.com\/shorts\/)([A-Za-z0-9_-]{6,})/,
  ];
  for (const re of patterns) {
    const m = s.match(re);
    if (m) return m[1];
  }
  return null;
}

export function mountYoutubeLibrary(container, topic, { canManage, onTopicUpdated, showToast }) {
  if (!container || !topic) return;

  const lessons = topic.lessons || [];
  let selectedLessonId = "all";
  let showAddForm = false;

  function getVideos() {
    return Array.isArray(topic.youtube_videos) ? topic.youtube_videos : [];
  }

  async function saveVideos(newList, msg) {
    const updated = structuredClone(topic);
    updated.youtube_videos = newList;
    try {
      const res = await api.updateTopic(topic.id, updated);
      topic.youtube_videos = res.topic.youtube_videos || newList;
      onTopicUpdated(res.topic);
      showToast(msg || "Đã cập nhật thư viện Video YouTube.", "success");
      render();
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  function render() {
    const videos = getVideos();
    const filtered =
      selectedLessonId === "all"
        ? videos
        : videos.filter((v) => v.lesson_id === selectedLessonId);

    container.innerHTML = `
      <div class="yt-section">
        <div class="yt-toolbar">
          <div class="yt-toolbar-left">
            <select id="yt-lesson-filter" class="form-control form-control-sm" style="width:auto;min-width:220px;">
              <option value="all" ${selectedLessonId === "all" ? "selected" : ""}>Tất cả các bài (${videos.length} video)</option>
              ${lessons
                .map((l) => {
                  const cnt = videos.filter((v) => v.lesson_id === l.id).length;
                  return `<option value="${l.id}" ${selectedLessonId === l.id ? "selected" : ""}>${escapeHtml(l.number)}: ${escapeHtml(l.title)} (${cnt})</option>`;
                })
                .join("")}
            </select>
          </div>
          ${
            canManage
              ? `
                <button class="btn btn-primary btn-sm" id="yt-toggle-add">
                  ${showAddForm ? "Đóng biểu mẫu" : "+ Nhúng link YouTube mới"}
                </button>
              `
              : ""
          }
        </div>

        ${
          canManage && showAddForm
            ? `
              <form id="yt-add-form" class="card yt-add-form">
                <h4 style="margin:0 0 12px;font-size:0.96rem;">Thêm Video bài giảng YouTube vào ${escapeHtml(topic.title)}</h4>
                <div class="form-row-2">
                  <div class="form-group">
                    <label>Tiêu đề video</label>
                    <input class="form-control" name="title" required placeholder="VD: Bài 1 — Cơ chế tái bản DNA" />
                  </div>
                  <div class="form-group">
                    <label>Thuộc bài học</label>
                    <select class="form-control" name="lesson_id">
                      <option value="all">Chung cho cả chủ đề</option>
                      ${lessons
                        .map(
                          (l) =>
                            `<option value="${l.id}">${escapeHtml(l.number)}: ${escapeHtml(l.title)}</option>`
                        )
                        .join("")}
                    </select>
                  </div>
                </div>
                <div class="form-group">
                  <label>Đường dẫn YouTube (youtube.com/watch?v=... hoặc youtu.be/...)</label>
                  <input class="form-control" name="url" required placeholder="https://www.youtube.com/watch?v=..." />
                </div>
                <div class="form-group">
                  <label>Mô tả ngắn (tuỳ chọn)</label>
                  <input class="form-control" name="description" placeholder="Ghi chú nội dung trọng tâm cần xem trong video..." />
                </div>
                <div style="display:flex;gap:8px;justify-content:flex-end;">
                  <button type="button" class="btn btn-secondary btn-sm" id="yt-cancel-add">Huỷ</button>
                  <button type="submit" class="btn btn-primary btn-sm">Lưu video vào thư mục Chủ đề</button>
                </div>
              </form>
            `
            : ""
        }

        ${
          filtered.length
            ? `
              <div class="yt-grid">
                ${filtered
                  .map((v) => {
                    const yid = parseYoutubeId(v.url);
                    const lessonObj = lessons.find((l) => l.id === v.lesson_id);
                    return `
                      <article class="card yt-card">
                        <div class="yt-embed-wrap">
                          ${
                            yid
                              ? `<iframe src="https://www.youtube.com/embed/${yid}?rel=0" title="${escapeHtml(v.title)}" allowfullscreen loading="lazy"></iframe>`
                              : `<div class="yt-invalid">Link YouTube không hợp lệ</div>`
                          }
                        </div>
                        <div class="yt-card-body">
                          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
                            <div>
                              <span class="pill pill-muted">${lessonObj ? escapeHtml(lessonObj.number) : "Chung"}</span>
                              <h4 class="yt-card-title">${escapeHtml(v.title)}</h4>
                            </div>
                            ${
                              canManage
                                ? `<button type="button" class="btn btn-ghost btn-sm" data-yt-delete="${v.id}" title="Xoá video">Xoá</button>`
                                : ""
                            }
                          </div>
                          ${v.description ? `<p class="yt-card-desc">${escapeHtml(v.description)}</p>` : ""}
                        </div>
                      </article>
                    `;
                  })
                  .join("")}
              </div>
            `
            : `
              <div class="empty-state">
                <div class="empty-state-title">Chưa có video YouTube nào trong mục này</div>
                <p class="empty-state-desc">
                  ${
                    canManage
                      ? "Nhấn nút <strong>+ Nhúng link YouTube mới</strong> ở góc trên để thêm video bài giảng cho học sinh."
                      : "Giáo viên sẽ cập nhật danh sách video bài giảng YouTube tại đây."
                  }
                </p>
              </div>
            `
        }
      </div>
    `;

    container.querySelector("#yt-lesson-filter")?.addEventListener("change", (e) => {
      selectedLessonId = e.target.value;
      render();
    });

    container.querySelector("#yt-toggle-add")?.addEventListener("click", () => {
      showAddForm = !showAddForm;
      render();
    });

    container.querySelector("#yt-cancel-add")?.addEventListener("click", () => {
      showAddForm = false;
      render();
    });

    container.querySelector("#yt-add-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const url = String(fd.get("url") || "").trim();
      if (!parseYoutubeId(url)) {
        showToast("Đường dẫn YouTube chưa đúng định dạng (cần link youtube.com hoặc youtu.be).", "error");
        return;
      }
      const newItem = {
        id: `yt-${Date.now()}`,
        lesson_id: String(fd.get("lesson_id") || "all"),
        title: String(fd.get("title") || "").trim(),
        url,
        description: String(fd.get("description") || "").trim(),
      };
      showAddForm = false;
      await saveVideos([...getVideos(), newItem], "Đã nhúng video YouTube vào Chủ đề!");
    });

    container.querySelectorAll("[data-yt-delete]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.ytDelete;
        const next = getVideos().filter((v) => v.id !== id);
        await saveVideos(next, "Đã xoá video khỏi danh sách.");
      });
    });
  }

  render();
}
