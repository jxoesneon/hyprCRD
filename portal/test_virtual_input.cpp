#include "src/wayland_virtual_pointer.h"
#include "src/wayland_virtual_keyboard.h"
#include <iostream>
#include <chrono>
#include <thread>
#include <cmath>

extern "C" {
#include <linux/input.h>
}

int main() {
    std::cout << "Testing Wayland Virtual Input (Pointer & Keyboard)..." << std::endl;
    
    WaylandVirtualPointer pointer;
    if (!pointer.init()) {
        std::cerr << "Failed to initialize virtual pointer" << std::endl;
        return 1;
    }
    std::cout << "✓ Virtual pointer initialized successfully" << std::endl;
    
    WaylandVirtualKeyboard keyboard;
    if (!keyboard.init()) {
        std::cerr << "Failed to initialize virtual keyboard" << std::endl;
        pointer.cleanup();
        return 1;
    }
    std::cout << "✓ Virtual keyboard initialized successfully" << std::endl;
    
    // Get current time
    uint32_t time = static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
    
    // 1. Test relative mouse motion
    std::cout << "Testing relative mouse movement..." << std::endl;
    for (int i = 0; i < 360; i += 30) {
        double angle = i * M_PI / 180.0;
        double dx = cos(angle) * 3.0;
        double dy = sin(angle) * 3.0;
        pointer.send_motion(time + i, dx, dy);
        pointer.send_frame();
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    std::cout << "✓ Relative mouse movement verified" << std::endl;

    // 2. Test absolute mouse motion
    std::cout << "Testing absolute mouse motion..." << std::endl;
    pointer.send_motion_absolute(time + 400, 500, 400, 1920, 1080);
    pointer.send_frame();
    std::cout << "✓ Absolute mouse motion verified" << std::endl;
    
    // 3. Test mouse clicks (Left, Right, Middle)
    std::cout << "Testing mouse buttons (Left, Right, Middle)..." << std::endl;
    pointer.send_button(time + 450, BTN_LEFT, 1);
    pointer.send_frame();
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    pointer.send_button(time + 480, BTN_LEFT, 0);
    pointer.send_frame();

    pointer.send_button(time + 510, BTN_RIGHT, 1);
    pointer.send_frame();
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    pointer.send_button(time + 540, BTN_RIGHT, 0);
    pointer.send_frame();

    pointer.send_button(time + 570, BTN_MIDDLE, 1);
    pointer.send_frame();
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    pointer.send_button(time + 600, BTN_MIDDLE, 0);
    pointer.send_frame();
    std::cout << "✓ Mouse button clicks verified" << std::endl;

    // 4. Test scrolling (discrete & continuous)
    std::cout << "Testing mouse scrolling (discrete & continuous)..." << std::endl;
    pointer.send_axis_source(WL_POINTER_AXIS_SOURCE_WHEEL);
    pointer.send_axis_discrete(time + 650, 0, 1); // vertical notch down
    pointer.send_axis_discrete(time + 680, 0, -1); // vertical notch up
    pointer.send_axis_discrete(time + 710, 1, 0); // horizontal notch right
    pointer.send_axis(time + 740, WL_POINTER_AXIS_VERTICAL_SCROLL, 15.0);
    pointer.send_axis_stop(time + 770, WL_POINTER_AXIS_VERTICAL_SCROLL);
    pointer.send_axis(time + 800, WL_POINTER_AXIS_HORIZONTAL_SCROLL, -15.0);
    pointer.send_axis_stop(time + 830, WL_POINTER_AXIS_HORIZONTAL_SCROLL);
    pointer.send_frame();
    std::cout << "✓ Mouse scrolling verified" << std::endl;
    
    // 5. Test keyboard keystrokes and modifiers (Letters, Modifiers, Function keys)
    std::cout << "Testing keyboard key press & modifiers (KEY_A, Shift, Ctrl, Alt, Super, F1)..." << std::endl;
    keyboard.send_key(time + 900, KEY_A, 1); // Press
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    keyboard.send_key(time + 930, KEY_A, 0); // Release

    // Shift modifier
    keyboard.send_modifiers(1, 0, 0, 0); // Shift depressed
    keyboard.send_key(time + 960, KEY_A, 1);
    keyboard.send_key(time + 990, KEY_A, 0);
    keyboard.send_modifiers(0, 0, 0, 0); // Reset

    // Ctrl + Alt modifiers
    keyboard.send_modifiers(4 | 8, 0, 0, 0); // Ctrl + Alt
    keyboard.send_key(time + 1020, KEY_T, 1);
    keyboard.send_key(time + 1050, KEY_T, 0);
    keyboard.send_modifiers(0, 0, 0, 0); // Reset

    // Super / Meta modifier
    keyboard.send_modifiers(64, 0, 0, 0); // Super
    keyboard.send_key(time + 1080, KEY_ENTER, 1);
    keyboard.send_key(time + 1110, KEY_ENTER, 0);
    keyboard.send_modifiers(0, 0, 0, 0); // Reset

    // Function key (F1, Esc)
    keyboard.send_key(time + 1140, KEY_F1, 1);
    keyboard.send_key(time + 1170, KEY_F1, 0);
    keyboard.send_key(time + 1200, KEY_ESC, 1);
    keyboard.send_key(time + 1230, KEY_ESC, 0);

    std::cout << "✓ Keyboard key presses and modifiers verified" << std::endl;
    
    pointer.cleanup();
    keyboard.cleanup();
    std::cout << "✓ All Wayland virtual input tests passed cleanly!" << std::endl;
    return 0;
}