#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch TWRP gui2 to add the extra tools page (home card + data driven rows).

Rows are read from /sdcard/TWRP/nf_menu.conf (falling back to the built-in
defaults), so more items can be added later by editing that text file instead
of rebuilding recovery.

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
  }
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
  }
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
        # extra includes for the directory scan
        (
            """#include <unistd.h>""",
            """#include <unistd.h>
#include <dirent.h>
#include <sys/stat.h>""",
        ),
        # forward declarations
        (
            """static void open_advanced_tool(settings_target target);""",
            """static void open_advanced_tool(settings_target target);
static void open_nf_main_menu(page_transition transition);
static void show_nf_tools_page(page_transition transition);
static void nf_row_event_cb(lv_event_t* event);""",
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
static bool nf_from_restore = false;
static const char* nf_page_title = "进阶功能";
static std::string nf_running_text;
static std::string nf_done_text;""",
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
    if (nf_from_restore)
      open_nf_main_menu(page_transition::POP);
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
        # the menu itself, placed next to the legacy tool helpers
        (
            """  open_tool_confirm(request);
}

// Targets the mount page hands back through its events. The partition rows""",
            """  open_tool_confirm(request);
}

// ---- Extra tools: a data driven menu ----------------------------------------
// The rows come from a text file, so items 7, 8, 9 and later can be added by
// editing it on the device instead of rebuilding recovery.
static bool nf_read_file(const char* path, std::string* out) {
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

static void nf_add(const char* title, const char* detail, const char* command) {
  nf_menu_item item;
  item.title = title;
  item.detail = detail;
  item.command = command;
  nf_menu.push_back(item);
}

// What the page shows when the device has no menu file yet.
static void nf_load_defaults(void) {
  nf_menu.clear();
  nf_add("安装 OTA 包", "解析 payload.bin 并逐个分区写入",
         "/system/bin/sh /system/bin/nf/nf_gui.sh ota");
  nf_add("备份分区", "存到 /sdcard/TWRP/BF日期时间",
         "/system/bin/sh /system/bin/nf/nf_gui.sh backup");
  nf_add("还原分区", "从备份目录里挑一个写回", "@restore");
  nf_add("一键进入 9008", "切到 EDL 下载模式",
         "/system/bin/sh /system/bin/nf/nf_gui.sh edl");
  nf_add("关闭所有 Magisk 模组", "清掉所有已启用的模组标记",
         "/system/bin/sh /system/bin/nf/nf_gui.sh magisk_off");
  nf_add("一键 root", "Magisk v31.1 补丁 init_boot 并写回",
         "/system/bin/sh /system/bin/nf/nf_gui.sh magisk_on");
  nf_add("导出恢复日志", "把 recovery.log 复制到 /sdcard",
         "/system/bin/sh /system/bin/nf/nf_gui.sh log");
}

// One row per line: 标题|副标题|命令。以 # 开头的行与空行忽略。
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
  if (nf_read_file("/sdcard/TWRP/nf_menu.conf", &text) ||
      nf_read_file("/data/media/0/TWRP/nf_menu.conf", &text))
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

// Every BF* folder in the storage root, newest first.
static void open_nf_restore_menu(page_transition transition) {
  std::vector<std::string> names;
  const char* roots[2] = { "/sdcard/TWRP", "/data/media/0/TWRP" };
  for (const char* root : roots) {
    DIR* dir = opendir(root);
    if (dir == nullptr) continue;
    while (dirent* entry = readdir(dir)) {
      const std::string name = entry->d_name;
      if (name.compare(0, 2, "BF") != 0) continue;
      if (!nf_is_dir(std::string(root) + "/" + name)) continue;
      names.push_back(name);
    }
    closedir(dir);
    if (!names.empty()) break;
  }
  std::sort(names.begin(), names.end());
  std::reverse(names.begin(), names.end());
  nf_menu.clear();
  for (const auto& name : names) {
    nf_add(name.c_str(), "写回这个目录里的镜像",
           ("/system/bin/sh /system/bin/nf/nf_gui.sh restore /sdcard/TWRP/" + name).c_str());
  }
  if (nf_menu.empty()) nf_add("没有找到备份", "先做一次分区备份，再做还原", "@none");
  nf_from_restore = true;
  nf_page_title = "选择备份目录";
  navigate_to(page_kind::NF_TOOLS, nullptr, transition);
}

static void open_nf_main_menu(page_transition transition) {
  nf_load_config();
  nf_from_restore = false;
  nf_page_title = "进阶功能";
  navigate_to(page_kind::NF_TOOLS, nullptr, transition);
}

static void nf_row_event_cb(lv_event_t* event) {
  if (lv_event_get_code(event) != LV_EVENT_CLICKED || !accept_click(event)) return;
  const auto* item = static_cast<const nf_menu_item*>(lv_event_get_user_data(event));
  if (item == nullptr || tools == nullptr) return;
  if (item->command.compare(0, 1, "@") == 0) {
    if (item->command == "@restore") open_nf_restore_menu(page_transition::PUSH);
    return;
  }
  tool_request request;
  request.job = gui2_backend::tool_job::COMMAND;
  request.title = item->title;
  request.summary = item->detail;
  request.text = item->detail + "\\n\\n" + item->command;
  nf_running_text = "正在执行：" + item->title;
  nf_done_text = "执行完成";
  request.running = nf_running_text.c_str();
  request.done = nf_done_text.c_str();
  request.swipe = "滑动开始";
  request.back = request.after = page_at(page_kind::NF_TOOLS);
  request.tone = gui2_pages::confirm_tone::INFO;
  request.value = item->command + " </dev/null 2>&1";
  open_tool_confirm(request);
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

# ------------------------------------------------------- live command output ---
# The progress page polls the recovery console buffer, but TWFunc::ExecCmd forks
# and lets the child write straight into /tmp/recovery.log, so a script's
# progress never reaches the page while it runs. Stream it instead: the console
# buffer is what poll_tool_console() drains.
edit(
    "backend/twrp_tools_backend.cpp",
    [
        (
            """#include <unistd.h>""",
            """#include <cstdio>
#include <unistd.h>""",
        ),
        (
            """// GUIAction::cmd
int cmd(std::string arg) {""",
            """// Runs a command and copies its output into the recovery console line by line,
// so the progress page scrolls while the command is still running.
int run_streaming(const std::string& command) {
  std::string popen_command = command;
  if (popen_command.find("2>&1") == std::string::npos) popen_command += " 2>&1";
  FILE* pipe = popen(popen_command.c_str(), "r");
  if (pipe == nullptr) return -1;
  char buffer[1024];
  while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
    std::string line(buffer);
    while (!line.empty() && (line.back() == '\\n' || line.back() == '\\r')) line.pop_back();
    if (line.empty()) continue;
    line += '\\n';
    gui2_console::write_raw(gui2_console::severity::normal, line);
  }
  const int status = pclose(pipe);
  return status == 0 ? 0 : 1;
}

// GUIAction::cmd
int cmd(std::string arg) {""",
        ),
        (
            """  op_status = TWFunc::ExecCmd(arg);""",
            """  op_status = run_streaming(arg);""",
        ),
    ],
)

print("gui2 extra tools patch applied")
