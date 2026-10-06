#include "select_marker.h"

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cstdlib>

static std::string select_marker_path() {
    const char* runtime_dir = getenv("XDG_RUNTIME_DIR");
    if (!runtime_dir || !*runtime_dir)
        return "";
    return std::string(runtime_dir) + "/hyprcrd/select-pending";
}

void writeSelectMarker(const std::string& session_handle) {
    std::string path = select_marker_path();
    if (path.empty())
        return;

    std::string dir = path.substr(0, path.rfind('/'));
    mkdir(dir.c_str(), 0700);

    int fd = open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0)
        return;
    ssize_t written = write(fd, session_handle.data(), session_handle.size());
    (void)written;
    close(fd);
}

void clearSelectMarker() {
    std::string path = select_marker_path();
    if (!path.empty())
        unlink(path.c_str());
}
