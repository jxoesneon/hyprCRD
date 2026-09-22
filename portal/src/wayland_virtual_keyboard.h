#pragma once

extern "C" {
#include <wayland-client.h>
#include "virtual-keyboard-unstable-v1-client-protocol.h"
}

class WaylandVirtualKeyboard {
public:
    WaylandVirtualKeyboard();
    ~WaylandVirtualKeyboard();
    
    bool init();
    void cleanup();
    
    // Keyboard input methods
    void send_key(uint32_t time, uint32_t key, uint32_t state);
    void send_modifiers(uint32_t mods_depressed, uint32_t mods_latched, 
                       uint32_t mods_locked, uint32_t group);

    // Registry callback functions (must be public)
    static void registry_global(void* data, struct wl_registry* registry,
                              uint32_t name, const char* interface, uint32_t version);
    static void registry_global_remove(void* data, struct wl_registry* registry, uint32_t name);
    
private:
    struct wl_display* display;
    struct wl_registry* registry;
    struct wl_seat* seat;
    struct zwp_virtual_keyboard_manager_v1* keyboard_manager;
    struct zwp_virtual_keyboard_v1* virtual_keyboard;
    
    bool setup_keymap();
}; 