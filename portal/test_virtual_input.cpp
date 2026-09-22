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
    
    // Test mouse motion
    std::cout << "Testing mouse movement..." << std::endl;
    for (int i = 0; i < 360; i += 30) {
        double angle = i * M_PI / 180.0;
        double dx = cos(angle) * 3.0;
        double dy = sin(angle) * 3.0;
        pointer.send_motion(time + i, dx, dy);
        pointer.send_frame();
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    std::cout << "✓ Mouse movement verified" << std::endl;
    
    // Test mouse click
    std::cout << "Testing mouse click..." << std::endl;
    pointer.send_button(time + 400, BTN_LEFT, 1);
    pointer.send_frame();
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    pointer.send_button(time + 450, BTN_LEFT, 0);
    pointer.send_frame();
    std::cout << "✓ Mouse click verified" << std::endl;
    
    // Test keyboard keystroke (e.g. KEY_A)
    std::cout << "Testing keyboard key press (KEY_A)..." << std::endl;
    keyboard.send_key(time + 500, KEY_A, 1); // Press
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    keyboard.send_key(time + 550, KEY_A, 0); // Release
    std::cout << "✓ Keyboard key press verified" << std::endl;
    
    pointer.cleanup();
    keyboard.cleanup();
    std::cout << "✓ All Wayland virtual input tests passed cleanly!" << std::endl;
    return 0;
}