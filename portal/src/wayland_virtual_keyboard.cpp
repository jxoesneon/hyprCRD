#include "wayland_virtual_keyboard.h"
#include <iostream>
#include <cstring>
#include <sys/mman.h>
#include <unistd.h>
#include <fcntl.h>

static const struct wl_registry_listener registry_listener = {
    .global = WaylandVirtualKeyboard::registry_global,
    .global_remove = WaylandVirtualKeyboard::registry_global_remove,
};

// Basic US QWERTY keymap
static const char keymap_str[] =
    "xkb_keymap {\n"
    "xkb_keycodes  { include \"evdev+aliases(qwerty)\" };\n"
    "xkb_types     { include \"complete\" };\n"
    "xkb_compat    { include \"complete\" };\n"
    "xkb_symbols   { include \"pc+us+inet(evdev)\" };\n"
    "xkb_geometry  { include \"pc(pc104)\" };\n"
    "};\n";

WaylandVirtualKeyboard::WaylandVirtualKeyboard()
    : display(nullptr), registry(nullptr), seat(nullptr), 
      keyboard_manager(nullptr), virtual_keyboard(nullptr) {
}

WaylandVirtualKeyboard::~WaylandVirtualKeyboard() {
    cleanup();
}

bool WaylandVirtualKeyboard::init() {
    display = wl_display_connect(nullptr);
    if (!display) {
        std::cerr << "Failed to connect to Wayland display" << std::endl;
        return false;
    }

    registry = wl_display_get_registry(display);
    if (!registry) {
        std::cerr << "Failed to get Wayland registry" << std::endl;
        cleanup();
        return false;
    }

    wl_registry_add_listener(registry, &registry_listener, this);
    wl_display_roundtrip(display);

    if (!keyboard_manager) {
        std::cerr << "Compositor does not support virtual-keyboard protocol" << std::endl;
        cleanup();
        return false;
    }

    // Create virtual keyboard
    virtual_keyboard = zwp_virtual_keyboard_manager_v1_create_virtual_keyboard(keyboard_manager, seat);
    if (!virtual_keyboard) {
        std::cerr << "Failed to create virtual keyboard" << std::endl;
        cleanup();
        return false;
    }

    if (!setup_keymap()) {
        std::cerr << "Failed to setup keymap" << std::endl;
        cleanup();
        return false;
    }

    wl_display_roundtrip(display);
    std::cout << "Wayland Virtual Keyboard initialized successfully" << std::endl;
    return true;
}

void WaylandVirtualKeyboard::cleanup() {
    if (virtual_keyboard) {
        zwp_virtual_keyboard_v1_destroy(virtual_keyboard);
        virtual_keyboard = nullptr;
    }
    if (keyboard_manager) {
        zwp_virtual_keyboard_manager_v1_destroy(keyboard_manager);
        keyboard_manager = nullptr;
    }
    if (seat) {
        wl_seat_destroy(seat);
        seat = nullptr;
    }
    if (registry) {
        wl_registry_destroy(registry);
        registry = nullptr;
    }
    if (display) {
        wl_display_disconnect(display);
        display = nullptr;
    }
}

bool WaylandVirtualKeyboard::setup_keymap() {
    if (!virtual_keyboard) return false;

    size_t keymap_size = strlen(keymap_str) + 1;
    
    // Create shared memory file
    int fd = memfd_create("keymap", MFD_CLOEXEC);
    if (fd < 0) {
        std::cerr << "Failed to create memfd" << std::endl;
        return false;
    }

    if (ftruncate(fd, keymap_size) < 0) {
        std::cerr << "Failed to resize memfd" << std::endl;
        close(fd);
        return false;
    }

    void* data = mmap(nullptr, keymap_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (data == MAP_FAILED) {
        std::cerr << "Failed to mmap keymap" << std::endl;
        close(fd);
        return false;
    }

    strcpy(static_cast<char*>(data), keymap_str);
    munmap(data, keymap_size);

    // Send keymap to compositor
    zwp_virtual_keyboard_v1_keymap(virtual_keyboard, 1, fd, keymap_size); // XKB_KEYMAP_FORMAT_TEXT_V1 = 1
    close(fd);

    return true;
}

void WaylandVirtualKeyboard::registry_global(void* data, struct wl_registry* registry,
                                            uint32_t name, const char* interface, uint32_t version) {
    WaylandVirtualKeyboard* self = static_cast<WaylandVirtualKeyboard*>(data);
    
    if (strcmp(interface, zwp_virtual_keyboard_manager_v1_interface.name) == 0) {
        self->keyboard_manager = static_cast<struct zwp_virtual_keyboard_manager_v1*>(
            wl_registry_bind(registry, name, &zwp_virtual_keyboard_manager_v1_interface, 1));
    } else if (strcmp(interface, wl_seat_interface.name) == 0) {
        self->seat = static_cast<struct wl_seat*>(
            wl_registry_bind(registry, name, &wl_seat_interface, 1));
    }
}

void WaylandVirtualKeyboard::registry_global_remove(void* data, struct wl_registry* registry, uint32_t name) {
    // Handle global removal if needed
}

void WaylandVirtualKeyboard::send_key(uint32_t time, uint32_t key, uint32_t state) {
    if (virtual_keyboard) {
        zwp_virtual_keyboard_v1_key(virtual_keyboard, time, key, state);
        wl_display_flush(display);
    }
}

void WaylandVirtualKeyboard::send_modifiers(uint32_t mods_depressed, uint32_t mods_latched, 
                                          uint32_t mods_locked, uint32_t group) {
    if (virtual_keyboard) {
        zwp_virtual_keyboard_v1_modifiers(virtual_keyboard, mods_depressed, 
                                        mods_latched, mods_locked, group);
        wl_display_flush(display);
    }
} 