#pragma once

extern "C" {
#include <libei.h>
}

class WaylandVirtualKeyboard;
class WaylandVirtualPointer;

class LibEIHandler {
public:
    LibEIHandler();
    ~LibEIHandler();
    
    bool init(WaylandVirtualKeyboard* kb, WaylandVirtualPointer* ptr);
    void cleanup();
    void run();
    void stop();
    bool is_running() const { return running; }
    
    // Public access to ei_context for portal integration
    struct ei* ei_context;
    
    // Public access to virtual input devices for portal integration
    WaylandVirtualKeyboard* keyboard;
    WaylandVirtualPointer* pointer;
    
    // Public event handling for portal integration
    void handle_event(struct ei_event* event);
    void handle_keyboard_event(struct ei_event* event);
    void handle_pointer_event(struct ei_event* event);
    
private:
    struct ei_seat* seat;
    
    bool running;
}; 