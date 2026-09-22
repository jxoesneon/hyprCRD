#pragma once

#include <sdbus-c++/sdbus-c++.h>
#include <memory>
#include <map>
#include <tuple>
#include <string>

extern "C" {
#include "libei-1.0/libeis.h"
}

class LibEIHandler;

class Portal {
public:
    Portal();
    ~Portal();
    
    bool init(LibEIHandler* handler);
    void cleanup();
    void run();
    void stop();
    
private:
    std::unique_ptr<sdbus::IConnection> connection;
    std::unique_ptr<sdbus::IObject> object;
    std::map<std::string, std::unique_ptr<sdbus::IObject>> session_objects;
    LibEIHandler* libei_handler;
    bool running;
    
    uint32_t modifier_state_depressed = 0;
    uint32_t modifier_state_latched = 0;
    uint32_t modifier_state_locked = 0;
    uint32_t modifier_state_group = 0;
    
    static constexpr uint32_t MOD_SHIFT = 1 << 0;
    static constexpr uint32_t MOD_CAPS = 1 << 1;
    static constexpr uint32_t MOD_CTRL = 1 << 2;
    static constexpr uint32_t MOD_ALT = 1 << 3;
    static constexpr uint32_t MOD_NUM = 1 << 4;
    static constexpr uint32_t MOD_META = 1 << 6;
    
    void update_modifier_state(uint32_t keycode, bool is_press);
    
    std::tuple<uint32_t, std::map<std::string, sdbus::Variant>> CreateSession(
        sdbus::ObjectPath request_handle,
        sdbus::ObjectPath session_handle,
        std::string app_id,
        std::map<std::string, sdbus::Variant> options);

    std::tuple<uint32_t, std::map<std::string, sdbus::Variant>> SelectDevices(
        sdbus::ObjectPath request_handle,
        sdbus::ObjectPath session_handle,
        std::string app_id,
        std::map<std::string, sdbus::Variant> options);

    std::tuple<uint32_t, std::map<std::string, sdbus::Variant>> Start(
        sdbus::ObjectPath request_handle,
        sdbus::ObjectPath session_handle,
        std::string app_id,
        std::string parent_window,
        std::map<std::string, sdbus::Variant> options);
    
    void NotifyPointerMotion(
        sdbus::ObjectPath session_handle,
        std::map<std::string, sdbus::Variant> options,
        double dx, double dy);

    void NotifyPointerButton(
        sdbus::ObjectPath session_handle,
        std::map<std::string, sdbus::Variant> options,
        int32_t button, uint32_t state);

    void NotifyKeyboardKeycode(
        sdbus::ObjectPath session_handle,
        std::map<std::string, sdbus::Variant> options,
        int32_t keycode, uint32_t state);

    void NotifyPointerAxis(
        sdbus::ObjectPath session_handle,
        std::map<std::string, sdbus::Variant> options,
        double dx, double dy);
    
    sdbus::UnixFd ConnectToEIS(
        sdbus::ObjectPath session_handle,
        std::string app_id,
        std::map<std::string, sdbus::Variant> options);
    
    void handle_eis_event(struct eis_event* event);
};