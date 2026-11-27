#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch TWRP gui2 to add the extra tools page (home card + 进阶功能 pages).

v2 (2026-11-19) changes, on top of the first version:
  * 安装 OTA 包  -> 先在 /sdcard 里浏览、选一个 zip / payload.bin，
                   再勾选要写入的物理分区，确认后才执行。
  * 备份分区     -> 列出 by-name 里的物理分区，勾选多个，确认后打包备份，
                   备份完在控制台打印每个分区的 md5 与回读校对结果。
  * 还原分区     -> 可以在 /sdcard 下任意浏览文件夹（不只 TWRP/BF*），
                   选中文件夹后勾选要写回的 .img，确认后还原并做 md5 校对。
  * 其余功能（9008 / 关闭模组 / 一键 root / 导出日志）保持一键执行。

Rows of the top page still come from /sdcard/TWRP/nf_menu.conf, so later items
(7, 8, 9 ...) can be added by editing that text file instead of rebuilding.

Usage: nf_gui2_patch.py [recovery_source_root]   (default: bootable/recovery)

Every edit is an exact-match replacement with an assertion, so a moved anchor
fails the build immediately instead of producing a silently wrong binary.
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "bootable/recovery"
GUI = os.path.join(ROOT, "gui2")


def edit(rel, pairs):
    path = os.path.join(GUI, rel)
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    for index, (old, new) in enumerate(pairs):
        if old not in text:
            raise SystemExit("anchor %d missing in %s:\n%s" % (index, rel, old))
        text = text.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    print("patched %d edit(s) in %s" % (len(pairs), rel))


# ---------------------------------------------------------------- home card ---
edit(
    "pages/home_page.h",
    [(
        """  const char* notice_text = nullptr;
  lv_event_cb_t notice_event_callback = nullptr;
};""",
        """  const char* notice_text = nullptr;
  lv_event_cb_t notice_event_callback = nullptr;
  // One extra card after the built-in ones. The target comes back as the event
  // user data of extra_event_callback, which is what lets a device build add
  // its own tools without touching the shared action table.
  const char* extra_title = nullptr;
  const void* extra_target = nullptr;
  lv_event_cb_t extra_event_callback = nullptr;
};""",
    )],
)

edit(
    "pages/home_page.cpp",
    [(
        """  for (size_t i = 0; i < options.action_count; ++i) {
    create_action_card(options, cards, options.actions[i], card_width, metrics.card_height,
                       metrics.icon_size);
  }""",
        """  for (size_t i = 0; i < options.action_count; ++i) {
    create_action_card(options, cards, options.actions[i], card_width, metrics.card_height,
                       metrics.icon_size);
  }
  if (options.extra_title != nullptr && options.extra_event_callback != nullptr) {
    gui2_components::icon_card_options card;
    card.metrics = options.metrics;
    card.icon = &kGui2IconAdvanced;
    card.icon_color = 0x9AA7B0;
    card.title = options.extra_title;
    card.width = card_width;
    card.height = metrics.card_height;
    card.icon_size = metrics.icon_size;
    card.event_callback = options.extra_event_callback;
    card.user_data = options.extra_target;
    card.press_guard_callback = options.press_guard_callback;
    gui2_components::create_icon_card(cards, card);
  }""",
    )],
)

# ------------------------------------------------------------- page routing ---
edit(
    "pages/page_router.h",
    [(
        """  TOOL_INPUT,
};""",
        """  TOOL_INPUT,
  NF_TOOLS,
};""",
    )],
)

# ------------------------------------------------------------ tools page api ---
edit(
    "pages/tool_pages.h",
    [(
        """void build_confirm_page(const confirm_page_options& options);

}  // namespace gui2_pages""",
        """void build_confirm_page(const confirm_page_options& options);

// The device's own extra tools: one row per line of its menu file. The target
// is handed straight back as the event user data.
struct nf_menu_entry {
  const char* title = nullptr;
  const char* detail = nullptr;
  const void* target = nullptr;
};
struct nf_tools_page_options {
  lv_obj_t* content = nullptr;
  const gui2_core::ui_metrics* metrics = nullptr;
  lv_event_cb_t event_callback = nullptr;
  lv_event_cb_t press_guard_callback = nullptr;
  const nf_menu_entry* items = nullptr;
  size_t item_count = 0;
};
void build_nf_tools_page(const nf_tools_page_options& options);
}  // namespace gui2_pages""",
    )],
)

edit(
    "pages/tool_pages.cpp",
    [(
        """  gui2_components::create_tip_card(body, metrics, options.text, text, surface);
}

}  // namespace gui2_pages""",
        """  gui2_components::create_tip_card(body, metrics, options.text, text, surface);
}

void build_nf_tools_page(const nf_tools_page_options& options) {
  if (options.content == nullptr || options.metrics == nullptr || options.items == nullptr)
    return;
  const auto& metrics = *options.metrics;
  lv_obj_t* body = create_body(options.content, metrics);
  for (size_t i = 0; i < options.item_count; ++i) {
    const auto& item = options.items[i];
    gui2_components::create_setting_card(body, metrics, item.title, item.detail,
                                         options.event_callback, item.target,
                                         options.press_guard_callback);
  }
}

}  // namespace gui2_pages""",
    )],
)

# ------------------------------------------------------------------ gui2.cpp ---
edit(
    "gui2.cpp",
    [
        # extra includes for the directory scan and string building
        (
            """#include <unistd.h>""",
            """#include <unistd.h>
#include <dirent.h>
#include <sys/stat.h>
#include <cstdio>
#include <cstring>
#include <algorithm>""",
        ),
        # forward declarations
        (
            """static void open_advanced_tool(settings_target target);""",
            """static void open_advanced_tool(settings_target target);
static void open_nf_main_menu(page_transition transition);
static void show_nf_tools_page(page_transition transition);
static void nf_row_event_cb(lv_event_t* event);
static void nf_refresh_current(void);
static void nf_refresh_or_back(void);""",
        ),
        # the menu state, declared before any page code can read it
        (
            """static bool home_page_active;
static bool home_navigation_active;""",
            """static bool home_page_active;
static bool home_navigation_active;
// ---- Extra tools state ------------------------------------------------------
struct nf_menu_item {
  std::string title;
  std::string detail;
  std::string command;
};
static std::vector<nf_menu_item> nf_menu;
static std::vector<gui2_pages::nf_menu_entry> nf_entries;
static const char* nf_page_title = "进阶功能";
static std::string nf_running_text;
static std::string nf_done_text;
// Which picker is on screen. The top menu is NF_M_NONE.
enum nf_mode_t {
  NF_M_NONE,
  NF_M_OTA_FILE,
  NF_M_OTA_PARTS,
  NF_M_BACKUP,
  NF_M_RESTORE_DIR,
  NF_M_RESTORE_FILES,
};
static nf_mode_t nf_mode = NF_M_NONE;
static std::string nf_dir = "/sdcard";
static std::string nf_file;
static std::vector<std::string> nf_sel;
static std::vector<std::string> nf_list;""",
        ),
        # enum
        (
            """  UNMAP_SUPER,
};""",
            """  UNMAP_SUPER,
  NF_TOOLS,
};""",
        ),
        # target instance
        (
            """static constexpr settings_target unmap_super_target = settings_target::UNMAP_SUPER;""",
            """static constexpr settings_target unmap_super_target = settings_target::UNMAP_SUPER;
static constexpr settings_target nf_tools_target = settings_target::NF_TOOLS;""",
        ),
        # click routing
        (
            """             *target == settings_target::UNMAP_SUPER)
    open_advanced_tool(*target);
}""",
            """             *target == settings_target::UNMAP_SUPER)
    open_advanced_tool(*target);
  else if (*target == settings_target::NF_TOOLS)
    open_nf_main_menu(page_transition::PUSH);
}""",
        ),
        # back behaviour
        (
            """  } else if (!home_page_active) {""",
            """  } else if (page_router.current() == page_kind::NF_TOOLS) {
    if (nf_mode != NF_M_NONE)
      nf_refresh_or_back();
    else
      navigate_to(page_kind::HOME, nullptr, page_transition::POP);
  } else if (!home_page_active) {""",
        ),
        # home page card
        (
            """  options.action_event_callback = action_card_event_cb;
  options.press_guard_callback = press_cancel_guard_cb;""",
            """  options.action_event_callback = action_card_event_cb;
  options.press_guard_callback = press_cancel_guard_cb;
  options.extra_title = "进阶功能";
  options.extra_target = &nf_tools_target;
  options.extra_event_callback = settings_option_event_cb;""",
        ),
        # the pages themselves, placed next to the legacy tool helpers
        (
            """  open_tool_confirm(request);
}

// Targets the mount page hands back through its events. The partition rows""",
            """  open_tool_confirm(request);
}

// ---- Extra tools: data driven menu + pickers ---------------------------------
// The top page rows come from a text file, so items 7, 8, 9 and later can be
// added by editing it on the device instead of rebuilding recovery.
static bool nf_read_text(const char* path, std::string* out) {
  FILE* file = std::fopen(path, "r");
  if (file == nullptr) return false;
  char line[512];
  out->clear();
  while (std::fgets(line, sizeof(line), file) != nullptr) out->append(line);
  std::fclose(file);
  return true;
}

static std::string nf_trim(const std::string& value) {
  const size_t first = value.find_first_not_of(" \\t\\r\\n");
  if (first == std::string::npos) return std::string();
  const size_t last = value.find_last_not_of(" \\t\\r\\n");
  return value.substr(first, last - first + 1);
}

static void nf_adds(const std::string& title, const std::string& detail, const std::string& command) {
  nf_menu_item item;
  item.title = title;
  item.detail = detail;
  item.command = command;
  nf_menu.push_back(item);
}

static void nf_add(const char* title, const char* detail, const char* command) {
  nf_adds(std::string(title), std::string(detail), std::string(command));
}

// What the top page shows when the device has no menu file yet.
static void nf_load_defaults(void) {
  nf_menu.clear();
  nf_add("安装 OTA 包", "选 zip / payload.bin，再勾选要写入的分区", "@ota");
  nf_add("备份分区", "勾选分区，存到 /sdcard/TWRP/BF日期时间", "@backup");
  nf_add("还原分区", "浏览 /sdcard 任意文件夹，勾选镜像写回", "@restore");
  nf_add("一键进入 9008", "切到 EDL 下载模式",
         "/system/bin/sh /system/bin/nf/nf_gui.sh edl");
  nf_add("关闭所有 Magisk 模组", "给每个启用中的模组放 disable 标记",
         "/system/bin/sh /system/bin/nf/nf_gui.sh magisk_off");
  nf_add("一键 root", "Magisk v31.1 补丁 init_boot 并写回",
         "/system/bin/sh /system/bin/nf/nf_gui.sh magisk_on");
  nf_add("导出恢复日志", "把 recovery.log 复制到 /sdcard",
         "/system/bin/sh /system/bin/nf/nf_gui.sh log");
}

// One row per line: 标题|副标题|命令。以 # 开头的行与空行忽略。
// 命令写 @ota / @backup / @restore 就是内置的选择流程。
static void nf_parse_config(const std::string& text) {
  std::vector<nf_menu_item> items;
  size_t start = 0;
  while (start <= text.size()) {
    const size_t end = text.find('\\n', start);
    const std::string line = nf_trim(
        text.substr(start, end == std::string::npos ? std::string::npos : end - start));
    start = end == std::string::npos ? text.size() + 1 : end + 1;
    if (line.empty() || line[0] == '#') continue;
    const size_t bar1 = line.find('|');
    if (bar1 == std::string::npos) continue;
    const size_t bar2 = line.find('|', bar1 + 1);
    if (bar2 == std::string::npos) continue;
    nf_menu_item item;
    item.title = nf_trim(line.substr(0, bar1));
    item.detail = nf_trim(line.substr(bar1 + 1, bar2 - bar1 - 1));
    item.command = nf_trim(line.substr(bar2 + 1));
    if (!item.title.empty() && !item.command.empty()) items.push_back(item);
  }
  if (!items.empty()) nf_menu = items;
}

static void nf_load_config(void) {
  nf_load_defaults();
  std::string text;
  if (nf_read_text("/sdcard/TWRP/nf_menu.conf", &text) ||
      nf_read_text("/data/media/0/TWRP/nf_menu.conf", &text))
    nf_parse_config(text);
}

static void nf_build_entries(void) {
  nf_entries.clear();
  for (size_t i = 0; i < nf_menu.size(); ++i) {
    gui2_pages::nf_menu_entry entry;
    entry.title = nf_menu[i].title.c_str();
    entry.detail = nf_menu[i].detail.c_str();
    entry.target = &nf_menu[i];
    nf_entries.push_back(entry);
  }
}

static bool nf_is_dir(const std::string& full_path) {
  struct stat info;
  return stat(full_path.c_str(), &info) == 0 && S_ISDIR(info.st_mode);
}

static bool nf_is_file(const std::string& full_path) {
  struct stat info;
  return stat(full_path.c_str(), &info) == 0 && S_ISREG(info.st_mode);
}

static long long nf_file_size(const std::string& full_path) {
  struct stat info;
  if (stat(full_path.c_str(), &info) != 0) return 0;
  return static_cast<long long>(info.st_size);
}

static std::string nf_human(long long bytes) {
  static const char* units[] = {"B", "KB", "MB", "GB", "TB"};
  double value = static_cast<double>(bytes);
  int unit = 0;
  while (value >= 1024.0 && unit < 4) {
    value /= 1024.0;
    ++unit;
  }
  char buffer[32];
  std::snprintf(buffer, sizeof(buffer), "%.1f%s", value, units[unit]);
  return std::string(buffer);
}

static std::vector<std::string> nf_scan(const std::string& dir) {
  std::vector<std::string> names;
  DIR* handle = opendir(dir.c_str());
  if (handle == nullptr) return names;
  while (dirent* entry = readdir(handle)) {
    const std::string name = entry->d_name;
    if (name == "." || name == "..") continue;
    names.push_back(name);
  }
  closedir(handle);
  std::sort(names.begin(), names.end());
  return names;
}

static std::string nf_join(const std::string& dir, const std::string& name) {
  if (dir.empty()) return name;
  if (dir == "/") return "/" + name;
  return dir + "/" + name;
}

static bool nf_ends_with(const std::string& value, const char* suffix) {
  const size_t len = std::strlen(suffix);
  if (value.size() < len) return false;
  return value.compare(value.size() - len, len, suffix) == 0;
}

static bool nf_selected(const std::string& name) {
  return std::find(nf_sel.begin(), nf_sel.end(), name) != nf_sel.end();
}

static void nf_toggle(const std::string& name) {
  auto it = std::find(nf_sel.begin(), nf_sel.end(), name);
  if (it == nf_sel.end())
    nf_sel.push_back(name);
  else
    nf_sel.erase(it);
}

// by-name 里的杂项分区不作为可选候选
static bool nf_part_skip(const std::string& name) {
  static const char* const skipped[] = {
      "cdt", "ddr", "devinfo", "dpm", "efisp", "fsg", "fsc", "fs_bkup", "apdp", "apdpb",
      "connsec", "frp", "misc", "persist", "persistbak", "rawdump", "secdata", "devinfo",
      "ALIGN_TO_128K_1", "ALIGN_TO_128K_2"};
  for (const char* entry : skipped)
    if (name == entry) return true;
  return name.compare(0, 12, "ALIGN_TO_128") == 0;
}

static void nf_load_parts(void) {
  nf_list = nf_scan("/dev/block/by-name");
  std::vector<std::string> kept;
  for (const auto& name : nf_list)
    if (!nf_part_skip(name)) kept.push_back(name);
  nf_list = kept;
}

static std::string nf_sel_joined(void) {
  std::string value;
  for (const auto& name : nf_sel) {
    if (!value.empty()) value += " ";
    value += name;
  }
  return value;
}

static void nf_show(void) {
  navigate_to(page_kind::NF_TOOLS, nullptr, page_transition::REPLACE);
}

// ---- pickers ----------------------------------------------------------------
static void nf_show_menu(void) {
  nf_mode = NF_M_NONE;
  nf_sel.clear();
  nf_load_config();
  nf_page_title = "进阶功能";
  nf_show();
}

static void nf_show_ota_files(void) {
  nf_page_title = "选择 OTA 包";
  nf_menu.clear();
  nf_add("返回", nf_dir.c_str(), "@menu");
  if (nf_dir != "/sdcard") nf_add("上一级", "回到上一层文件夹", "@up");
  int hits = 0;
  for (const auto& name : nf_scan(nf_dir)) {
    const std::string path = nf_join(nf_dir, name);
    if (nf_is_dir(path)) {
      nf_adds(name, "文件夹", "@go:" + path);
      continue;
    }
    if (!nf_is_file(path)) continue;
    if (!(nf_ends_with(name, ".zip") || nf_ends_with(name, ".bin"))) continue;
    nf_adds(name, nf_human(nf_file_size(path)), "@pick:" + path);
    ++hits;
  }
  if (hits == 0)
    nf_add("这个文件夹里没有 zip/bin", "把 OTA 包放进 /sdcard 再来", "@none");
  nf_show();
}

static void nf_show_parts(const char* title, const char* action_command, const std::string& hint) {
  nf_page_title = title;
  nf_menu.clear();
  nf_add("返回", hint.c_str(), "@menu");
  nf_load_parts();
  for (const auto& name : nf_list) {
    const std::string mark = nf_selected(name) ? "[✓] " : "[    ] ";
    nf_adds(mark + name, "物理分区", "@t:" + name);
  }
  nf_add("全选", "把列出的分区都勾上", "@all");
  nf_add("清空选择", "取消所有勾选", "@clearsel");
  const std::string count = std::to_string(nf_sel.size());
  nf_adds(std::string("开始（已选 ") + count + " 项）", hint, action_command);
  nf_show();
}

static void nf_show_backup(void) {
  nf_show_parts("备份分区", "@do_backup", "勾选要备份的分区，完成后打印 md5");
}

static void nf_show_ota_parts(void) {
  nf_show_parts("选择要写入的分区", "@do_ota", nf_file);
}

static void nf_show_restore_dirs(void) {
  nf_page_title = "选择文件夹";
  nf_menu.clear();
  nf_add("返回上一页", nf_dir.c_str(), "@menu");
  if (nf_dir != "/sdcard") nf_add("上一级", "回到上一层文件夹", "@up");
  // 当前文件夹里有多少 .img，决定“用这个文件夹”这一行怎么显示
  std::vector<std::string> imgs;
  for (const auto& name : nf_scan(nf_dir)) {
    const std::string path = nf_join(nf_dir, name);
    if (nf_is_file(path) && nf_ends_with(name, ".img")) imgs.push_back(name);
  }
  const std::string count = std::to_string(imgs.size());
  nf_adds(std::string("用这个文件夹（") + count + " 个 img）", nf_dir, "@usedir");
  for (const auto& name : nf_scan(nf_dir)) {
    const std::string path = nf_join(nf_dir, name);
    if (!nf_is_dir(path)) continue;
    nf_adds(name, "文件夹", "@go:" + path);
  }
  nf_show();
}

static void nf_show_restore_files(void) {
  nf_page_title = "选择要还原的分区";
  nf_menu.clear();
  nf_add("返回文件夹列表", nf_dir.c_str(), "@up");
  for (const auto& name : nf_scan(nf_dir)) {
    const std::string path = nf_join(nf_dir, name);
    if (!nf_is_file(path) || !nf_ends_with(name, ".img")) continue;
    const std::string base = name.substr(0, name.size() - 4);
    const std::string mark = nf_selected(base) ? "[✓] " : "[    ] ";
    nf_adds(mark + base, nf_human(nf_file_size(path)), "@t:" + base);
  }
  nf_add("全选", "把这里的 img 都勾上", "@all");
  nf_add("清空选择", "取消所有勾选", "@clearsel");
  const std::string count = std::to_string(nf_sel.size());
  nf_adds(std::string("开始还原（已选 ") + count + " 项）", nf_dir, "@do_restore");
  nf_show();
}

static void nf_refresh_current(void) {
  switch (nf_mode) {
    case NF_M_OTA_FILE: nf_show_ota_files(); return;
    case NF_M_OTA_PARTS: nf_show_ota_parts(); return;
    case NF_M_BACKUP: nf_show_backup(); return;
    case NF_M_RESTORE_DIR: nf_show_restore_dirs(); return;
    case NF_M_RESTORE_FILES: nf_show_restore_files(); return;
    default: nf_show_menu(); return;
  }
}

// 返回键：选择页逐级退回，顶级页退出到主界面
static void nf_refresh_or_back(void) {
  if (nf_mode == NF_M_OTA_FILE || nf_mode == NF_M_RESTORE_DIR) {
    if (nf_dir == "/sdcard") {
      nf_show_menu();
      return;
    }
    const size_t slash = nf_dir.find_last_of('/');
    if (slash != std::string::npos)
      nf_dir = slash == 0 ? std::string("/") : nf_dir.substr(0, slash);
    if (nf_dir == "/") nf_dir = "/sdcard";
    nf_refresh_current();
    return;
  }
  if (nf_mode == NF_M_OTA_PARTS) {
    nf_mode = NF_M_OTA_FILE;
    nf_refresh_current();
    return;
  }
  if (nf_mode == NF_M_RESTORE_FILES) {
    nf_mode = NF_M_RESTORE_DIR;
    nf_sel.clear();
    nf_refresh_current();
    return;
  }
  nf_show_menu();
}

static void nf_run_command(const std::string& title, const std::string& detail,
                           const std::string& command) {
  if (tools == nullptr) return;
  tool_request request;
  request.job = gui2_backend::tool_job::COMMAND;
  request.title = title.c_str();
  request.summary = detail.c_str();
  request.text = (detail + "\\n\\n" + command).c_str();
  nf_running_text = "正在执行：" + title;
  nf_done_text = "执行完成";
  request.running = nf_running_text.c_str();
  request.done = nf_done_text.c_str();
  request.swipe = "滑动开始";
  request.back = page_at(page_kind::NF_TOOLS);
  request.after = request.back;
  request.tone = gui2_pages::confirm_tone::INFO;
  request.value = command + " </dev/null 2>&1";
  open_tool_confirm(request);
}

static void open_nf_main_menu(page_transition transition) {
  nf_mode = NF_M_NONE;
  nf_sel.clear();
  nf_load_config();
  nf_page_title = "进阶功能";
  navigate_to(page_kind::NF_TOOLS, nullptr, transition);
}

static void nf_row_event_cb(lv_event_t* event) {
  if (lv_event_get_code(event) != LV_EVENT_CLICKED || !accept_click(event)) return;
  const auto* item = static_cast<const nf_menu_item*>(lv_event_get_user_data(event));
  if (item == nullptr) return;
  const std::string command = item->command;
  if (command == "@none") return;

  if (command == "@menu") { nf_show_menu(); return; }
  if (command == "@ota") {
    nf_mode = NF_M_OTA_FILE;
    nf_dir = "/sdcard";
    nf_file.clear();
    nf_sel.clear();
    nf_show_ota_files();
    return;
  }
  if (command == "@backup") {
    nf_mode = NF_M_BACKUP;
    nf_sel.clear();
    nf_show_backup();
    return;
  }
  if (command == "@restore") {
    nf_mode = NF_M_RESTORE_DIR;
    nf_dir = "/sdcard";
    nf_sel.clear();
    nf_show_restore_dirs();
    return;
  }
  if (command == "@up") {
    if (nf_mode == NF_M_RESTORE_FILES) {
      nf_mode = NF_M_RESTORE_DIR;
      nf_sel.clear();
      nf_refresh_current();
      return;
    }
    const size_t slash = nf_dir.find_last_of('/');
    if (slash != std::string::npos && nf_dir != "/sdcard")
      nf_dir = slash == 0 ? std::string("/sdcard") : nf_dir.substr(0, slash);
    nf_refresh_current();
    return;
  }
  if (command == "@all") {
    nf_sel.clear();
    if (nf_mode == NF_M_RESTORE_FILES) {
      for (const auto& name : nf_scan(nf_dir)) {
        const std::string path = nf_join(nf_dir, name);
        if (nf_is_file(path) && nf_ends_with(name, ".img"))
          nf_sel.push_back(name.substr(0, name.size() - 4));
      }
    } else {
      nf_load_parts();
      nf_sel = nf_list;
    }
    nf_refresh_current();
    return;
  }
  if (command == "@clearsel") {
    nf_sel.clear();
    nf_refresh_current();
    return;
  }
  if (command == "@usedir") {
    nf_mode = NF_M_RESTORE_FILES;
    nf_sel.clear();
    nf_show_restore_files();
    return;
  }
  if (command.compare(0, 4, "@go:") == 0) {
    nf_dir = command.substr(4);
    if (nf_mode == NF_M_RESTORE_DIR)
      nf_show_restore_dirs();
    else
      nf_show_ota_files();
    return;
  }
  if (command.compare(0, 6, "@pick:") == 0) {
    nf_file = command.substr(6);
    nf_mode = NF_M_OTA_PARTS;
    nf_sel.clear();
    nf_show_ota_parts();
    return;
  }
  if (command.compare(0, 3, "@t:") == 0) {
    nf_toggle(command.substr(3));
    nf_refresh_current();
    return;
  }
  if (command == "@do_backup") {
    if (nf_sel.empty()) {
      nf_done_text = "";
      nf_run_command("备份分区", "还没有勾选分区", "echo 请先勾选至少一个分区");
      return;
    }
    nf_run_command("备份分区", "备份 " + std::to_string(nf_sel.size()) + " 个分区",
                   "/system/bin/sh /system/bin/nf/nf_gui.sh backup " + nf_sel_joined());
    return;
  }
  if (command == "@do_ota") {
    if (nf_file.empty()) return;
    if (nf_sel.empty()) {
      nf_run_command("安装 OTA 包", "还没有勾选分区", "echo 请先勾选至少一个分区");
      return;
    }
    nf_run_command("安装 OTA 包", nf_file,
                   "/system/bin/sh /system/bin/nf/nf_gui.sh ota \\"" + nf_file + "\\" " +
                       nf_sel_joined());
    return;
  }
  if (command == "@do_restore") {
    if (nf_sel.empty()) {
      nf_run_command("还原分区", "还没有勾选镜像", "echo 请先勾选至少一个镜像");
      return;
    }
    nf_run_command("还原分区", nf_dir,
                   "/system/bin/sh /system/bin/nf/nf_gui.sh restore \\"" + nf_dir + "\\" " +
                       nf_sel_joined());
    return;
  }

  nf_run_command(item->title, item->detail, command);
}

static void show_nf_tools_page(page_transition transition) {
  create_page_scaffold(page_kind::NF_TOOLS, false, nf_page_title, "", 0, transition);
  nf_build_entries();
  gui2_pages::nf_tools_page_options options;
  options.content = main_content;
  options.metrics = &ui;
  options.event_callback = nf_row_event_cb;
  options.press_guard_callback = press_cancel_guard_cb;
  options.items = nf_entries.empty() ? nullptr : nf_entries.data();
  options.item_count = nf_entries.size();
  gui2_pages::build_nf_tools_page(options);
}

// Targets the mount page hands back through its events. The partition rows""",
        ),
        # router case
        (
            """    case page_kind::TOOL_INPUT:
      show_tool_input_page(request.transition);
      return;
  }""",
            """    case page_kind::TOOL_INPUT:
      show_tool_input_page(request.transition);
      return;
    case page_kind::NF_TOOLS:
      show_nf_tools_page(request.transition);
      return;
  }""",
        ),
    ],
)

# 主界面左上角标题：源码里写死了 "YARP"，改成 "TWRP"
edit(
    "gui2.cpp",
    [
        (
            'create_page_scaffold(page_kind::HOME, true, "YARP", "", 0, transition);',
            'create_page_scaffold(page_kind::HOME, true, "TWRP", "", 0, transition);',
        ),
    ],
)

# ---- 实时进度页 + 勾选保持滚动位置 ----------------------------------------
edit(
    "pages/page_router.h",
    [
        (
            """  TOOL_INPUT,
  NF_TOOLS,
};""",
            """  TOOL_INPUT,
  NF_TOOLS,
  NF_PROGRESS,
};""",
        ),
    ],
)

edit(
    "gui2.cpp",
    [
        (
            """#include <cstring>
#include <algorithm>""",
            """#include <cstring>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>""",
        ),
        (
            """static void nf_refresh_or_back(void);""",
            """static void nf_refresh_or_back(void);
static void show_nf_progress_page(page_transition transition);
static void nf_prog_tick(lv_timer_t* timer);
static void nf_prog_stop(void);
static void nf_prog_back(void);
static void nf_start_job(const std::string& caption, const std::string& command);
static void nf_save_scroll(void);
static void nf_restore_scroll(void);""",
        ),
        (
            """static std::string nf_done_text;""",
            """static std::string nf_done_text;
// ---- live progress page -------------------------------------------------------
static lv_obj_t* nf_prog_status = nullptr;
static lv_obj_t* nf_prog_log = nullptr;
static lv_obj_t* nf_prog_box = nullptr;
static lv_timer_t* nf_prog_timer = nullptr;
static pid_t nf_prog_pid = -1;
static bool nf_prog_finished = false;
static int nf_prog_rc = -1;
static std::string nf_prog_caption;
static const char* nf_prog_log_path = "/tmp/nf_run.log";
// ---- keep the picker scrolled where the user left it --------------------------
static bool nf_keep_scroll = false;
static int nf_scroll_outer = 0;
static int nf_scroll_inner = 0;""",
        ),
        (
            """static void nf_run_command(const std::string& title, const std::string& detail,
                           const std::string& command) {
  if (tools == nullptr) return;
  tool_request request;
  request.job = gui2_backend::tool_job::COMMAND;
  request.title = title.c_str();
  request.summary = detail.c_str();
  request.text = (detail + "\\n\\n" + command).c_str();
  nf_running_text = "正在执行：" + title;
  nf_done_text = "执行完成";
  request.running = nf_running_text.c_str();
  request.done = nf_done_text.c_str();
  request.swipe = "滑动开始";
  request.back = page_at(page_kind::NF_TOOLS);
  request.after = request.back;
  request.tone = gui2_pages::confirm_tone::INFO;
  request.value = command + " </dev/null 2>&1";
  open_tool_confirm(request);
}""",
            """static void nf_run_command(const std::string& title, const std::string& detail,
                           const std::string& command) {
  nf_prog_caption = detail.empty() ? title : (title + " · " + detail);
  nf_start_job(title, command);
}""",
        ),
        (
            """static void open_nf_main_menu(page_transition transition) {""",
            """static void nf_save_scroll(void) {
  nf_scroll_outer = 0;
  nf_scroll_inner = 0;
  if (main_content == nullptr) return;
  nf_scroll_outer = static_cast<int>(lv_obj_get_scroll_y(main_content));
  lv_obj_t* body = lv_obj_get_child(main_content, 0);
  if (body != nullptr) nf_scroll_inner = static_cast<int>(lv_obj_get_scroll_y(body));
}

static void nf_restore_scroll(void) {
  if (main_content == nullptr) return;
  if (nf_scroll_outer > 0 && lv_obj_get_scroll_y(main_content) == 0)
    lv_obj_scroll_to_y(main_content, nf_scroll_outer, LV_ANIM_OFF);
  lv_obj_t* body = lv_obj_get_child(main_content, 0);
  if (body != nullptr && nf_scroll_inner > 0)
    lv_obj_scroll_to_y(body, nf_scroll_inner, LV_ANIM_OFF);
}

static std::string nf_prog_tail(size_t keep) {
  std::string all;
  FILE* handle = std::fopen(nf_prog_log_path, "r");
  if (handle == nullptr) return all;
  char buffer[4096];
  size_t got = 0;
  while ((got = std::fread(buffer, 1, sizeof(buffer), handle)) > 0) all.append(buffer, got);
  std::fclose(handle);
  if (all.size() > keep) {
    size_t start = all.size() - keep;
    const size_t newline = all.find(static_cast<char>(10), start);
    start = (newline == std::string::npos) ? start : newline + 1;
    all.erase(0, start);
  }
  return all;
}

static void nf_prog_stop(void) {
  if (nf_prog_timer != nullptr) {
    lv_timer_delete(nf_prog_timer);
    nf_prog_timer = nullptr;
  }
}

static void nf_prog_tick(lv_timer_t* timer) {
  (void)timer;
  if (nf_prog_pid > 0) {
    int status = 0;
    if (waitpid(nf_prog_pid, &status, WNOHANG) == nf_prog_pid) {
      nf_prog_pid = -1;
      nf_prog_rc = WIFEXITED(status) ? WEXITSTATUS(status) : 1;
      nf_prog_finished = true;
    }
  }
  std::string text = nf_prog_tail(3000);
  if (nf_prog_log != nullptr)
    lv_label_set_text(nf_prog_log, text.empty() ? "正在启动..." : text.c_str());
  if (nf_prog_box != nullptr) lv_obj_scroll_to_y(nf_prog_box, 32000, LV_ANIM_OFF);
  if (nf_prog_status != nullptr) {
    if (nf_prog_finished)
      lv_label_set_text(nf_prog_status, nf_prog_rc == 0 ? "执行完成：成功" : "执行完成：失败");
    else
      lv_label_set_text(nf_prog_status, "正在执行，请稍候...");
  }
  if (nf_prog_finished) nf_prog_stop();
}

static void nf_prog_back(void) {
  nf_prog_stop();
  nf_prog_log = nullptr;
  nf_prog_status = nullptr;
  navigate_to(page_kind::NF_TOOLS, nullptr, page_transition::POP);
}

static void nf_start_job(const std::string& caption, const std::string& command) {
  nf_prog_caption = caption;
  nf_prog_finished = false;
  nf_prog_rc = -1;
  std::remove(nf_prog_log_path);
  const pid_t pid = fork();
  if (pid == 0) {
    const int log_fd = open(nf_prog_log_path, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (log_fd >= 0) {
      dup2(log_fd, STDOUT_FILENO);
      dup2(log_fd, STDERR_FILENO);
      close(log_fd);
    }
    const int null_fd = open("/dev/null", O_RDONLY);
    if (null_fd >= 0) {
      dup2(null_fd, STDIN_FILENO);
      close(null_fd);
    }
    execl("/system/bin/sh", "sh", "-c", command.c_str(), static_cast<char*>(nullptr));
    _exit(127);
  }
  nf_prog_pid = pid;
  navigate_to(page_kind::NF_PROGRESS, nullptr, page_transition::PUSH);
}

static void show_nf_progress_page(page_transition transition) {
  create_page_scaffold(page_kind::NF_PROGRESS, false, "执行中", nf_prog_caption.c_str(), 0,
                       transition);
  if (main_content == nullptr) return;
  nf_prog_status = lv_label_create(main_content);
  lv_label_set_text(nf_prog_status, "正在执行，请稍候...");
  lv_obj_set_style_text_color(nf_prog_status, lv_color_hex(0xFFFFFF), 0);
  lv_obj_t* box = lv_obj_create(main_content);
  nf_prog_box = box;
  lv_obj_set_width(box, lv_pct(100));
  lv_obj_set_height(box, lv_pct(70));
  lv_obj_set_style_pad_all(box, 6, 0);
  lv_obj_set_style_bg_opa(box, LV_OPA_TRANSP, 0);
  lv_obj_set_style_border_width(box, 0, 0);
  lv_obj_set_scroll_dir(box, LV_DIR_VER);
  lv_obj_set_scrollbar_mode(box, LV_SCROLLBAR_MODE_AUTO);
  nf_prog_log = lv_label_create(box);
  lv_obj_set_width(nf_prog_log, lv_pct(96));
  lv_label_set_long_mode(nf_prog_log, LV_LABEL_LONG_WRAP);
  lv_obj_set_style_text_color(nf_prog_log, lv_color_hex(0xE6E6E6), 0);
  lv_label_set_text(nf_prog_log, "正在启动...");
  nf_prog_stop();
  nf_prog_timer = lv_timer_create(nf_prog_tick, 400, nullptr);
}

static void open_nf_main_menu(page_transition transition) {""",
        ),
        (
            """  if (command.compare(0, 3, "@t:") == 0) {
    nf_toggle(command.substr(3));
    nf_refresh_current();
    return;
  }""",
            """  if (command.compare(0, 3, "@t:") == 0) {
    nf_save_scroll();
    nf_keep_scroll = true;
    nf_toggle(command.substr(3));
    nf_refresh_current();
    return;
  }""",
        ),
        (
            """static void show_nf_tools_page(page_transition transition) {
  create_page_scaffold(page_kind::NF_TOOLS, false, nf_page_title, "", 0, transition);
  nf_build_entries();
  gui2_pages::nf_tools_page_options options;
  options.content = main_content;
  options.metrics = &ui;
  options.event_callback = nf_row_event_cb;
  options.press_guard_callback = press_cancel_guard_cb;
  options.items = nf_entries.empty() ? nullptr : nf_entries.data();
  options.item_count = nf_entries.size();
  gui2_pages::build_nf_tools_page(options);
}""",
            """static void show_nf_tools_page(page_transition transition) {
  create_page_scaffold(page_kind::NF_TOOLS, false, nf_page_title, "", 0, transition);
  nf_build_entries();
  gui2_pages::nf_tools_page_options options;
  options.content = main_content;
  options.metrics = &ui;
  options.event_callback = nf_row_event_cb;
  options.press_guard_callback = press_cancel_guard_cb;
  options.items = nf_entries.empty() ? nullptr : nf_entries.data();
  options.item_count = nf_entries.size();
  gui2_pages::build_nf_tools_page(options);
  if (nf_keep_scroll) {
    nf_keep_scroll = false;
    nf_restore_scroll();
  }
}""",
        ),
        (
            """  } else if (page_router.current() == page_kind::NF_TOOLS) {
    if (nf_mode != NF_M_NONE)
      nf_refresh_or_back();
    else
      navigate_to(page_kind::HOME, nullptr, page_transition::POP);
  } else if (!home_page_active) {""",
            """  } else if (page_router.current() == page_kind::NF_PROGRESS) {
    nf_prog_back();
  } else if (page_router.current() == page_kind::NF_TOOLS) {
    if (nf_mode != NF_M_NONE)
      nf_refresh_or_back();
    else
      navigate_to(page_kind::HOME, nullptr, page_transition::POP);
  } else if (!home_page_active) {""",
        ),
        (
            """    case page_kind::NF_TOOLS:
      show_nf_tools_page(request.transition);
      return;""",
            """    case page_kind::NF_TOOLS:
      show_nf_tools_page(request.transition);
      return;
    case page_kind::NF_PROGRESS:
      show_nf_progress_page(request.transition);
      return;""",
        ),
    ],
)
print("gui2 extra tools patch applied")
