#include "portal.h"
#include "libei_handler.h"
#include "wayland_virtual_keyboard.h"
#include "wayland_virtual_pointer.h"
#include <iostream>
#include <thread>
#include <chrono>
#include <cstring>
#include <cerrno>
#include <unistd.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <poll.h>
#include <algorithm>
#include <sys/mman.h>
#include <fcntl.h>

extern "C" {
#include <libei.h>
#include "libei-1.0/libeis.h"
#include <wayland-client-protocol.h>
#include <xkbcommon/xkbcommon.h>
}

static const char* PORTAL_INTERFACE = "org.freedesktop.impl.portal.RemoteDesktop";
static const char* PORTAL_PATH = "/org/freedesktop/portal/desktop";
static const char* PORTAL_NAME = "org.freedesktop.impl.portal.desktop.hypr-remote";

static MonitorInfo get_primary_monitor() {
    MonitorInfo m;
    FILE* fp = popen("hyprctl monitors -j", "r");
    if (!fp) return m;
    
    std::string out;
    char buf[512];
    while (fgets(buf, sizeof(buf), fp)) {
        out += buf;
    }
    pclose(fp);

    auto extract_str = [&](const std::string& key) -> std::string {
        size_t p = out.find("\"" + key + "\":");
        if (p == std::string::npos) return "";
        size_t start = out.find("\"", p + key.length() + 3);
        if (start == std::string::npos) return "";
        size_t end = out.find("\"", start + 1);
        if (end == std::string::npos) return "";
        return out.substr(start + 1, end - start - 1);
    };

    auto extract_num = [&](const std::string& key, double def_val) -> double {
        size_t p = out.find("\"" + key + "\":");
        if (p == std::string::npos) return def_val;
        size_t val_start = out.find_first_of("0123456789-", p + key.length() + 2);
        if (val_start == std::string::npos) return def_val;
        size_t val_end = out.find_first_not_of("0123456789.-", val_start);
        try {
            return std::stod(out.substr(val_start, val_end - val_start));
        } catch (...) {
            return def_val;
        }
    };

    std::string name = extract_str("name");
    if (!name.empty()) m.name = name;
    m.width = static_cast<uint32_t>(extract_num("width", 2560));
    m.height = static_cast<uint32_t>(extract_num("height", 1600));
    m.scale = extract_num("scale", 2.0);
    m.x = static_cast<uint32_t>(extract_num("x", 0));
    m.y = static_cast<uint32_t>(extract_num("y", 0));
    return m;
}

Portal::Portal() : libei_handler(nullptr), running(false) {
}

Portal::~Portal() {
    cleanup();
}

bool Portal::init(LibEIHandler* handler) {
    libei_handler = handler;
    current_monitor = get_primary_monitor();
    std::cout << "[portal] Detected monitor: " << current_monitor.name << " ("
              << current_monitor.width << "x" << current_monitor.height 
              << ", scale=" << current_monitor.scale << ") at ("
              << current_monitor.x << "," << current_monitor.y << ")" << std::endl;
    
    try {
        connection = sdbus::createSessionBusConnection();
        connection->requestName(sdbus::ServiceName{PORTAL_NAME});
        
        object = sdbus::createObject(*connection, sdbus::ObjectPath{PORTAL_PATH});
        std::cout << "Portal D-Bus interface registered at " << PORTAL_NAME << std::endl;
        std::cout << "Portal registered on SESSION bus" << std::endl;
        std::cout << "Portal version: 2" << std::endl;
        std::cout << "Portal path: " << PORTAL_PATH << std::endl;
        std::cout << "Portal interface: " << PORTAL_INTERFACE << std::endl;

        object->addVTable(
            sdbus::registerMethod("CreateSession").implementedAs([this](sdbus::ObjectPath req, sdbus::ObjectPath sess, std::string app, std::map<std::string, sdbus::Variant> opts) {
                return CreateSession(req, sess, app, opts);
            }),
            sdbus::registerMethod("SelectDevices").implementedAs([this](sdbus::ObjectPath req, sdbus::ObjectPath sess, std::string app, std::map<std::string, sdbus::Variant> opts) {
                return SelectDevices(req, sess, app, opts);
            }),
            sdbus::registerMethod("Start").implementedAs([this](sdbus::ObjectPath req, sdbus::ObjectPath sess, std::string app, std::string win, std::map<std::string, sdbus::Variant> opts) {
                return Start(req, sess, app, win, opts);
            }),
            sdbus::registerMethod("NotifyPointerMotion").implementedAs([this](sdbus::ObjectPath sess, std::map<std::string, sdbus::Variant> opts, double dx, double dy) {
                NotifyPointerMotion(sess, opts, dx, dy);
            }),
            sdbus::registerMethod("NotifyPointerButton").implementedAs([this](sdbus::ObjectPath sess, std::map<std::string, sdbus::Variant> opts, int32_t btn, uint32_t st) {
                NotifyPointerButton(sess, opts, btn, st);
            }),
            sdbus::registerMethod("NotifyKeyboardKeycode").implementedAs([this](sdbus::ObjectPath sess, std::map<std::string, sdbus::Variant> opts, int32_t key, uint32_t st) {
                NotifyKeyboardKeycode(sess, opts, key, st);
            }),
            sdbus::registerMethod("NotifyPointerAxis").implementedAs([this](sdbus::ObjectPath sess, std::map<std::string, sdbus::Variant> opts, double dx, double dy) {
                NotifyPointerAxis(sess, opts, dx, dy);
            }),
            sdbus::registerMethod("ConnectToEIS").implementedAs([this](sdbus::ObjectPath sess, std::string app, std::map<std::string, sdbus::Variant> opts) {
                return ConnectToEIS(sess, app, opts);
            }),
            sdbus::registerProperty("version").withGetter([]() -> uint32_t { return 2; })
        ).forInterface(PORTAL_INTERFACE);
        
        std::cout << "Portal D-Bus methods registered successfully." << std::endl;
        return true;
        
    } catch (const sdbus::Error& e) {
        std::cerr << "Failed to initialize D-Bus portal: " << e.what() << std::endl;
        cleanup();
        return false;
    }
}

void Portal::cleanup() {
    running = false;
    if (object) {
        object.reset();
    }
    if (connection) {
        connection.reset();
    }
}

void Portal::run() {
    if (!connection) return;
    running = true;
    std::cout << "Starting sdbus D-Bus event loop..." << std::endl;
    std::cout << "Portal ready to receive D-Bus calls!" << std::endl;
    try {
        connection->enterEventLoop();
    } catch (const sdbus::Error& e) {
        std::cerr << "D-Bus error in portal loop: " << e.what() << std::endl;
    }
    std::cout << "D-Bus event loop stopped." << std::endl;
}

void Portal::stop() {
    running = false;
    if (connection) {
        connection->leaveEventLoop();
    }
}

std::tuple<uint32_t, std::map<std::string, sdbus::Variant>> Portal::CreateSession(
    sdbus::ObjectPath request_handle,
    sdbus::ObjectPath session_handle,
    std::string app_id,
    std::map<std::string, sdbus::Variant> options) {
    
    std::cout << "RemoteDesktop CreateSession called for " << app_id << " (session: " << session_handle << ")" << std::endl;
    
    // Register the session object on D-Bus so xdg-desktop-portal can manage its lifecycle
    try {
        auto sess_obj = sdbus::createObject(*connection, session_handle);
        sess_obj->addVTable(
            sdbus::registerMethod("Close").implementedAs([this, session_handle]() {
                std::cout << "Session Close called for " << session_handle << std::endl;
                try {
                    auto hypr_sess = sdbus::createProxy(*connection,
                        sdbus::ServiceName{"org.freedesktop.impl.portal.desktop.hyprland"},
                        session_handle);
                    hypr_sess->callMethod("Close")
                        .onInterface("org.freedesktop.impl.portal.Session");
                } catch (...) {}
                session_objects.erase(session_handle);
            }),
            sdbus::registerProperty("version").withGetter([]() -> uint32_t { return 1; })
        ).forInterface("org.freedesktop.impl.portal.Session");
        
        session_objects[session_handle] = std::move(sess_obj);
    } catch (const std::exception& e) {
        std::cerr << "Warning: Could not export session object at " << session_handle << ": " << e.what() << std::endl;
    }

    // Also register paired session in xdg-desktop-portal-hyprland so SelectSources succeeds
    try {
        auto hypr_proxy = sdbus::createProxy(*connection,
            sdbus::ServiceName{"org.freedesktop.impl.portal.desktop.hyprland"},
            sdbus::ObjectPath{"/org/freedesktop/portal/desktop"});
        
        uint32_t resp_code = 0;
        std::map<std::string, sdbus::Variant> results;
        hypr_proxy->callMethod("CreateSession")
            .onInterface("org.freedesktop.impl.portal.ScreenCast")
            .withArguments(request_handle, session_handle, app_id, options)
            .storeResultsTo(resp_code, results);
            
        std::cout << "Hyprland ScreenCast.CreateSession returned code: " << resp_code << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "Warning: Failed to create paired ScreenCast session on hyprland: " << e.what() << std::endl;
    }

    std::map<std::string, sdbus::Variant> response;
    response["session_handle"] = sdbus::Variant(session_handle);
    return {0, response};
}

std::tuple<uint32_t, std::map<std::string, sdbus::Variant>> Portal::SelectDevices(
    sdbus::ObjectPath request_handle,
    sdbus::ObjectPath session_handle,
    std::string app_id,
    std::map<std::string, sdbus::Variant> options) {
    
    std::cout << "RemoteDesktop SelectDevices called for session: " << session_handle << std::endl;
    std::map<std::string, sdbus::Variant> response;
    response["types"] = sdbus::Variant(static_cast<uint32_t>(7)); // keyboard | pointer | touchscreen
    return {0, response};
}

std::tuple<uint32_t, std::map<std::string, sdbus::Variant>> Portal::Start(
    sdbus::ObjectPath request_handle,
    sdbus::ObjectPath session_handle,
    std::string app_id,
    std::string parent_window,
    std::map<std::string, sdbus::Variant> options) {
    
    std::cout << "RemoteDesktop Start called for session: " << session_handle << std::endl;
    std::map<std::string, sdbus::Variant> response;
    response["devices"] = sdbus::Variant(static_cast<uint32_t>(7));
    
    // Call Start on xdg-desktop-portal-hyprland ScreenCast to obtain streams
    try {
        auto hypr_proxy = sdbus::createProxy(*connection,
            sdbus::ServiceName{"org.freedesktop.impl.portal.desktop.hyprland"},
            sdbus::ObjectPath{"/org/freedesktop/portal/desktop"});
        
        uint32_t resp_code = 0;
        std::map<std::string, sdbus::Variant> sc_results;
        hypr_proxy->callMethod("Start")
            .onInterface("org.freedesktop.impl.portal.ScreenCast")
            .withArguments(request_handle, session_handle, app_id, parent_window, options)
            .storeResultsTo(resp_code, sc_results);
            
        std::cout << "Hyprland ScreenCast.Start returned code: " << resp_code << std::endl;
        if (sc_results.find("streams") != sc_results.end()) {
            response["streams"] = sc_results["streams"];
            std::cout << "Propagated screencast streams to RemoteDesktop.Start response." << std::endl;
        }
        if (resp_code != 0) {
            return {resp_code, response};
        }
    } catch (const std::exception& e) {
        std::cerr << "Warning: ScreenCast.Start on hyprland failed: " << e.what() << std::endl;
    }

    return {0, response};
}

void Portal::NotifyPointerMotion(
    sdbus::ObjectPath session_handle,
    std::map<std::string, sdbus::Variant> options,
    double dx, double dy) {
    
    uint32_t time = static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
    
    if (libei_handler && libei_handler->pointer) {
        libei_handler->pointer->send_motion(time, dx, dy);
        libei_handler->pointer->send_frame();
    }
}

void Portal::NotifyPointerButton(
    sdbus::ObjectPath session_handle,
    std::map<std::string, sdbus::Variant> options,
    int32_t button, uint32_t state) {
    
    uint32_t time = static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
    
    if (libei_handler && libei_handler->pointer) {
        libei_handler->pointer->send_button(time, static_cast<uint32_t>(button), state);
        libei_handler->pointer->send_frame();
    }
}

void Portal::NotifyKeyboardKeycode(
    sdbus::ObjectPath session_handle,
    std::map<std::string, sdbus::Variant> options,
    int32_t keycode, uint32_t state) {
    
    uint32_t time = static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
    
    if (libei_handler && libei_handler->keyboard) {
        update_modifier_state(static_cast<uint32_t>(keycode), state != 0);
        libei_handler->keyboard->send_modifiers(modifier_state_depressed, modifier_state_latched, modifier_state_locked, modifier_state_group);
        libei_handler->keyboard->send_key(time, static_cast<uint32_t>(keycode), state);
        libei_handler->keyboard->send_modifiers(modifier_state_depressed, modifier_state_latched, modifier_state_locked, modifier_state_group);
    }
}

void Portal::NotifyPointerAxis(
    sdbus::ObjectPath session_handle,
    std::map<std::string, sdbus::Variant> options,
    double dx, double dy) {
    
    uint32_t time = static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
    
    if (libei_handler && libei_handler->pointer) {
        libei_handler->pointer->send_axis_source(WL_POINTER_AXIS_SOURCE_WHEEL);
        if (dx != 0.0) {
            libei_handler->pointer->send_axis(time, WL_POINTER_AXIS_HORIZONTAL_SCROLL, dx);
            libei_handler->pointer->send_axis_stop(time, WL_POINTER_AXIS_HORIZONTAL_SCROLL);
        }
        if (dy != 0.0) {
            libei_handler->pointer->send_axis(time, WL_POINTER_AXIS_VERTICAL_SCROLL, dy);
            libei_handler->pointer->send_axis_stop(time, WL_POINTER_AXIS_VERTICAL_SCROLL);
        }
        libei_handler->pointer->send_frame();
    }
}

sdbus::UnixFd Portal::ConnectToEIS(
    sdbus::ObjectPath session_handle,
    std::string app_id,
    std::map<std::string, sdbus::Variant> options) {
    
    std::cout << "RemoteDesktop ConnectToEIS called by " << app_id << std::endl;
    
    if (!libei_handler || !libei_handler->keyboard || !libei_handler->pointer) {
        throw sdbus::Error(sdbus::Error::Name{"org.freedesktop.portal.Error.Failed"}, "Virtual devices not available");
    }
    
    struct eis* eis_context = eis_new(nullptr);
    if (!eis_context) {
        throw sdbus::Error(sdbus::Error::Name{"org.freedesktop.portal.Error.Failed"}, "Failed to initialize EIS context");
    }

    int rc = eis_setup_backend_fd(eis_context);
    if (rc != 0) {
        eis_unref(eis_context);
        throw sdbus::Error(sdbus::Error::Name{"org.freedesktop.portal.Error.Failed"}, "Failed to setup EIS fd backend");
    }

    int client_fd = eis_backend_fd_add_client(eis_context);
    if (client_fd < 0) {
        eis_unref(eis_context);
        throw sdbus::Error(sdbus::Error::Name{"org.freedesktop.portal.Error.Failed"}, "Failed to add EIS client");
    }

    int eis_fd = eis_get_fd(eis_context);
    if (eis_fd < 0) {
        close(client_fd);
        eis_unref(eis_context);
        throw sdbus::Error(sdbus::Error::Name{"org.freedesktop.portal.Error.Failed"}, "Failed to get EIS fd");
    }

    std::thread([this, eis_context, eis_fd]() {
        struct pollfd pfd = { eis_fd, POLLIN, 0 };
        while (running) {
            int ret = poll(&pfd, 1, 50);
            if (ret < 0) break;

            if (pfd.revents & POLLIN) {
                eis_dispatch(eis_context);
            }

            struct eis_event* event;
            while ((event = eis_get_event(eis_context)) != nullptr) {
                handle_eis_event(event);
                eis_event_unref(event);
            }
        }
        eis_unref(eis_context);
    }).detach();

    return sdbus::UnixFd{client_fd};
}

void Portal::handle_eis_event(struct eis_event* event) {
    enum eis_event_type type = eis_event_get_type(event);
    
    switch (type) {
        case EIS_EVENT_CLIENT_CONNECT: {
            struct eis_client* client = eis_event_get_client(event);
            eis_client_connect(client);
            
            struct eis_seat* seat = eis_client_new_seat(client, "hyprland-portal-seat");
            eis_seat_configure_capability(seat, EIS_DEVICE_CAP_POINTER);
            eis_seat_configure_capability(seat, EIS_DEVICE_CAP_POINTER_ABSOLUTE);
            eis_seat_configure_capability(seat, EIS_DEVICE_CAP_KEYBOARD);
            eis_seat_configure_capability(seat, EIS_DEVICE_CAP_BUTTON);
            eis_seat_configure_capability(seat, EIS_DEVICE_CAP_SCROLL);
            eis_seat_add(seat);
            break;
        }
        
        case EIS_EVENT_CLIENT_DISCONNECT:
            break;
            
        case EIS_EVENT_SEAT_BIND: {
            struct eis_seat* seat = eis_event_get_seat(event);
            
            struct eis_device* pointer = eis_seat_new_device(seat);
            eis_device_configure_name(pointer, "Hyprland Portal Pointer");
            eis_device_configure_capability(pointer, EIS_DEVICE_CAP_POINTER);
            eis_device_configure_capability(pointer, EIS_DEVICE_CAP_POINTER_ABSOLUTE);
            eis_device_configure_capability(pointer, EIS_DEVICE_CAP_BUTTON);
            eis_device_configure_capability(pointer, EIS_DEVICE_CAP_SCROLL);
            
            // Primary region mapped to monitor name (e.g. eDP-1) for Google CRD matching
            struct eis_region* region = eis_device_new_region(pointer);
            eis_region_set_offset(region, current_monitor.x, current_monitor.y);
            eis_region_set_size(region, current_monitor.width, current_monitor.height);
            eis_region_set_physical_scale(region, current_monitor.scale);
            eis_region_set_mapping_id(region, current_monitor.name.c_str());
            eis_region_add(region);

            // Fallback unmapped region
            struct eis_region* fallback_region = eis_device_new_region(pointer);
            eis_region_set_offset(fallback_region, 0, 0);
            eis_region_set_size(fallback_region, current_monitor.width, current_monitor.height);
            eis_region_set_physical_scale(fallback_region, 1.0);
            eis_region_add(fallback_region);
            
            eis_device_add(pointer);
            eis_device_resume(pointer);
            
            struct eis_device* keyboard = eis_seat_new_device(seat);
            eis_device_configure_name(keyboard, "Hyprland Portal Keyboard");
            eis_device_configure_capability(keyboard, EIS_DEVICE_CAP_KEYBOARD);
            
            // Build keymap from the system's active XKB configuration so Google CRD
            // can construct a full KeyboardLayout proto (Ctrl, Alt, Super, Fn keys etc.).
            char* keymap_str_alloc = nullptr;
            size_t keymap_size = 0;
            {
                struct xkb_context* xkb_ctx = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
                if (xkb_ctx) {
                    // NULL names → use system defaults (respects XKBLAYOUT env var etc.)
                    struct xkb_rule_names names = {};
                    struct xkb_keymap* xkb_km = xkb_keymap_new_from_names(
                        xkb_ctx, &names, XKB_KEYMAP_COMPILE_NO_FLAGS);
                    if (xkb_km) {
                        keymap_str_alloc = xkb_keymap_get_as_string(
                            xkb_km, XKB_KEYMAP_FORMAT_TEXT_V1);
                        if (keymap_str_alloc) {
                            keymap_size = strlen(keymap_str_alloc) + 1; // include NUL
                            std::cout << "[portal] XKB keymap loaded (" << keymap_size
                                      << " bytes)" << std::endl;
                        } else {
                            std::cerr << "[portal] xkb_keymap_get_as_string failed" << std::endl;
                        }
                        xkb_keymap_unref(xkb_km);
                    } else {
                        std::cerr << "[portal] xkb_keymap_new_from_names failed" << std::endl;
                    }
                    xkb_context_unref(xkb_ctx);
                } else {
                    std::cerr << "[portal] xkb_context_new failed" << std::endl;
                }
            }

            // Fallback: minimal keymap if xkbcommon failed
            const char* keymap_fallback =
                "xkb_keymap {\n"
                "xkb_keycodes  { include \"evdev+aliases(qwerty)\" };\n"
                "xkb_types     { include \"complete\" };\n"
                "xkb_compat    { include \"complete\" };\n"
                "xkb_symbols   { include \"pc+us+inet(evdev)\" };\n"
                "xkb_geometry  { include \"pc(pc105)\" };\n"
                "};\n";

            const char* keymap_to_write = keymap_str_alloc
                ? keymap_str_alloc
                : keymap_fallback;
            if (!keymap_str_alloc) {
                keymap_size = strlen(keymap_fallback) + 1;
                std::cerr << "[portal] Using fallback keymap" << std::endl;
            }

            int memfd = memfd_create("keymap", MFD_CLOEXEC | MFD_ALLOW_SEALING);
            if (memfd >= 0) {
                if (write(memfd, keymap_to_write, keymap_size) == (ssize_t)keymap_size) {
                    lseek(memfd, 0, SEEK_SET);
                    struct eis_keymap* keymap = eis_device_new_keymap(keyboard,
                        EIS_KEYMAP_TYPE_XKB, memfd, keymap_size);
                    if (keymap) {
                        eis_keymap_add(keymap);
                        eis_keymap_unref(keymap);
                    } else {
                        std::cerr << "[portal] eis_device_new_keymap failed" << std::endl;
                    }
                } else {
                    std::cerr << "[portal] write keymap to memfd failed: " << strerror(errno) << std::endl;
                }
                close(memfd);
            } else {
                std::cerr << "[portal] memfd_create failed: " << strerror(errno) << std::endl;
            }

            if (keymap_str_alloc) {
                free(keymap_str_alloc);
            }

            
            eis_device_add(keyboard);
            eis_device_resume(keyboard);
            break;
        }
        
        case EIS_EVENT_DEVICE_START_EMULATING:
        case EIS_EVENT_DEVICE_STOP_EMULATING:
            break;
            
        case EIS_EVENT_POINTER_MOTION: {
            double dx = eis_event_pointer_get_dx(event);
            double dy = eis_event_pointer_get_dy(event);
            if (libei_handler && libei_handler->pointer) {
                uint32_t time = static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now().time_since_epoch()).count());
                libei_handler->pointer->send_motion(time, dx, dy);
                libei_handler->pointer->send_frame();
            }
            break;
        }
        
        case EIS_EVENT_POINTER_MOTION_ABSOLUTE: {
            double x = eis_event_pointer_get_absolute_x(event);
            double y = eis_event_pointer_get_absolute_y(event);
            if (libei_handler && libei_handler->pointer) {
                uint32_t time = static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now().time_since_epoch()).count());
                libei_handler->pointer->send_motion_absolute(time, 
                    static_cast<uint32_t>(x), static_cast<uint32_t>(y), 
                    current_monitor.width, current_monitor.height);
                libei_handler->pointer->send_frame();
            }
            break;
        }
        
        case EIS_EVENT_BUTTON_BUTTON: {
            uint32_t button = eis_event_button_get_button(event);
            bool is_press = eis_event_button_get_is_press(event);
            if (libei_handler && libei_handler->pointer) {
                uint32_t time = static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now().time_since_epoch()).count());
                libei_handler->pointer->send_button(time, button, is_press ? 1 : 0);
                libei_handler->pointer->send_frame();
            }
            break;
        }
        
        case EIS_EVENT_SCROLL_DELTA: {
            double dx = eis_event_scroll_get_dx(event);
            double dy = eis_event_scroll_get_dy(event);
            if (libei_handler && libei_handler->pointer) {
                uint32_t time = static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now().time_since_epoch()).count());
                libei_handler->pointer->send_axis_source(WL_POINTER_AXIS_SOURCE_WHEEL);
                double scale_factor = 15.0;
                if (dx != 0.0) {
                    libei_handler->pointer->send_axis(time, WL_POINTER_AXIS_HORIZONTAL_SCROLL, dx * scale_factor);
                    libei_handler->pointer->send_axis_stop(time, WL_POINTER_AXIS_HORIZONTAL_SCROLL);
                }
                if (dy != 0.0) {
                    libei_handler->pointer->send_axis(time, WL_POINTER_AXIS_VERTICAL_SCROLL, dy * scale_factor);
                    libei_handler->pointer->send_axis_stop(time, WL_POINTER_AXIS_VERTICAL_SCROLL);
                }
                libei_handler->pointer->send_frame();
            }
            break;
        }
        
        case EIS_EVENT_SCROLL_DISCRETE: {
            int32_t dx = eis_event_scroll_get_discrete_dx(event);
            int32_t dy = eis_event_scroll_get_discrete_dy(event);
            if (libei_handler && libei_handler->pointer && (dx != 0 || dy != 0)) {
                uint32_t time = static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now().time_since_epoch()).count());
                libei_handler->pointer->send_axis_source(WL_POINTER_AXIS_SOURCE_WHEEL);
                libei_handler->pointer->send_axis_discrete(time, dx, dy);
                libei_handler->pointer->send_frame();
            }
            break;
        }
        
        case EIS_EVENT_KEYBOARD_KEY: {
            uint32_t keycode = eis_event_keyboard_get_key(event);
            bool is_press = eis_event_keyboard_get_key_is_press(event);
            if (libei_handler && libei_handler->keyboard) {
                uint32_t time = static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now().time_since_epoch()).count());
                update_modifier_state(keycode, is_press);
                libei_handler->keyboard->send_modifiers(modifier_state_depressed, 
                                                      modifier_state_latched,
                                                      modifier_state_locked, 
                                                      modifier_state_group);
                libei_handler->keyboard->send_key(time, keycode, is_press ? 1 : 0);
                libei_handler->keyboard->send_modifiers(modifier_state_depressed, 
                                                      modifier_state_latched,
                                                      modifier_state_locked, 
                                                      modifier_state_group);
            }
            break;
        }
        
        case EIS_EVENT_FRAME:
            break;
            
        default:
            break;
    }
}

void Portal::update_modifier_state(uint32_t keycode, bool is_press) {
    bool is_modifier = false;
    uint32_t modifier_mask = 0;
    
    switch (keycode) {
        case 42:
        case 54:
            is_modifier = true;
            modifier_mask = MOD_SHIFT;
            break;
        case 29:
        case 97:
            is_modifier = true;
            modifier_mask = MOD_CTRL;
            break;
        case 56:
        case 100:
            is_modifier = true;
            modifier_mask = MOD_ALT;
            break;
        case 125:
        case 126:
            is_modifier = true;
            modifier_mask = MOD_META;
            break;
        case 58:
            if (is_press) {
                modifier_state_locked ^= MOD_CAPS;
            }
            return;
        case 69:
            if (is_press) {
                modifier_state_locked ^= MOD_NUM;
            }
            return;
    }
    
    if (is_modifier) {
        if (is_press) {
            modifier_state_depressed |= modifier_mask;
        } else {
            modifier_state_depressed &= ~modifier_mask;
        }
    }
}