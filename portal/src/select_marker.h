#pragma once

#include <string>

// Handshake marker between hyprcrd-portal and hyprcrd-picker: the portal
// writes $XDG_RUNTIME_DIR/hyprcrd/select-pending while a screencast source
// selection triggered by our RemoteDesktop session is in flight, so the
// picker can safely auto-approve only our own request.
void writeSelectMarker(const std::string& session_handle);
void clearSelectMarker();
