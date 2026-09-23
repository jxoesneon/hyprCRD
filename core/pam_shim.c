#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <gio/gio.h>
#include <pipewire/pipewire.h>
#if __has_include(<security/pam_appl.h>)
#include <security/pam_appl.h>
#else
typedef struct pam_handle pam_handle_t;
struct pam_conv;
#define PAM_SUCCESS 0
#endif
#include <stdio.h>
#include <string.h>

/* --- PAM Hooking --- */
static pam_handle_t* crd_handles[16];
static int n_handles;

int pam_start(const char* service, const char* user, const struct pam_conv* conv,
              pam_handle_t** handle) {
    static int (*real)(const char*, const char*, const struct pam_conv*, pam_handle_t**);
    if (!real)
        real = dlsym(RTLD_NEXT, "pam_start");
    int r = real(service, user, conv, handle);
    if (r == PAM_SUCCESS && service && strcmp(service, "chrome-remote-desktop") == 0 &&
        n_handles < 16)
        crd_handles[n_handles++] = *handle;
    return r;
}

int pam_acct_mgmt(pam_handle_t* handle, int flags) {
    static int (*real)(pam_handle_t*, int);
    if (!real)
        real = dlsym(RTLD_NEXT, "pam_acct_mgmt");
    for (int i = 0; i < n_handles; i++)
        if (crd_handles[i] == handle)
            return PAM_SUCCESS;
    return real(handle, flags);
}

int pam_end(pam_handle_t* handle, int status) {
    static int (*real)(pam_handle_t*, int);
    if (!real)
        real = dlsym(RTLD_NEXT, "pam_end");
    for (int i = 0; i < n_handles; i++)
        if (crd_handles[i] == handle) {
            crd_handles[i] = crd_handles[--n_handles];
            break;
        }
    return real(handle, status);
}

/* --- PipeWire Stream Renegotiation Protection --- */
/*
 * On Wayland/Hyprland, screen capture streams originate from physical monitors
 * (e.g. eDP-1 at 2560x1600). When a remote client (e.g. Android phone) connects,
 * it sends a ClientResolution message with its phone dimensions (e.g. 1440x2560).
 * CRD's PortalDesktopResizer erroneously attempts to renegotiate the PipeWire stream
 * resolution by calling pw_stream_update_params while the stream is already streaming.
 * xdg-desktop-portal-hyprland cannot resize physical display capture streams, causing
 * PipeWire to error out with "no more input formats" and permanently kill the stream
 * after the first frame.
 *
 * We intercept pw_stream_update_params: if the stream is already actively STREAMING,
 * we drop the resolution renegotiation and return 0 (success). WebRTC's video encoder
 * automatically handles client scaling without crashing the PipeWire capture stream.
 */
static int (*real_pw_stream_update_params)(struct pw_stream*, const struct spa_pod**,
                                           uint32_t) = NULL;
static enum pw_stream_state (*real_pw_stream_get_state)(struct pw_stream*, const char**) = NULL;

#ifdef TESTING_COVERAGE
void set_mock_pw_stream_state(enum pw_stream_state (*fn)(struct pw_stream*, const char**)) {
    real_pw_stream_get_state = fn;
}
#endif

static void init_pw_symbols(void) {
    if (!real_pw_stream_update_params) {
        void* (*sys_dlsym)(void*, const char*) = dlvsym(RTLD_NEXT, "dlsym", "GLIBC_2.34");
        if (!sys_dlsym)
            sys_dlsym = dlvsym(RTLD_NEXT, "dlsym", "GLIBC_2.2.5");
        if (sys_dlsym) {
            void* pw_lib = dlopen("libpipewire-0.3.so.0", RTLD_LAZY | RTLD_GLOBAL);
            if (pw_lib) {
                real_pw_stream_update_params = sys_dlsym(pw_lib, "pw_stream_update_params");
                real_pw_stream_get_state = sys_dlsym(pw_lib, "pw_stream_get_state");
            }
            if (!real_pw_stream_update_params) {
                real_pw_stream_update_params = sys_dlsym(RTLD_NEXT, "pw_stream_update_params");
            }
            if (!real_pw_stream_get_state) {
                real_pw_stream_get_state = sys_dlsym(RTLD_NEXT, "pw_stream_get_state");
            }
        }
    }
}

int pw_stream_update_params(struct pw_stream* stream, const struct spa_pod** params,
                            uint32_t n_params) {
    if (!stream) {
        return -EINVAL;
    }
    init_pw_symbols();

    if (stream && real_pw_stream_get_state) {
        const char* err = NULL;
        enum pw_stream_state state = real_pw_stream_get_state(stream, &err);
        if (state == PW_STREAM_STATE_STREAMING) {
            fprintf(stderr,
                    "[pam_shim] Blocked pw_stream_update_params while STREAMING (prevented stream "
                    "crash on resize)\n");
            return 0; /* Report success without crashing PipeWire stream */
        }
    }

    if (real_pw_stream_update_params) {
        return real_pw_stream_update_params(stream, params, n_params);
    }
    return 0;
}

void* dlsym(void* handle, const char* name) {
    static void* (*real_dlsym)(void*, const char*) = NULL;
    if (!real_dlsym) {
        real_dlsym = dlvsym(RTLD_NEXT, "dlsym", "GLIBC_2.34");
        if (!real_dlsym) {
            real_dlsym = dlvsym(RTLD_NEXT, "dlsym", "GLIBC_2.2.5");
        }
    }

    if (name && strcmp(name, "pw_stream_update_params") == 0) {
        return (void*)pw_stream_update_params;
    }

    return real_dlsym ? real_dlsym(handle, name) : NULL;
}

/* --- GLib GDBus ScreenCast cursor_mode Hooking --- */
/*
 * Google Chrome Remote Desktop requests cursor_mode = 4 (METADATA) in
 * ScreenCast.SelectSources. On Hyprland, xdg-desktop-portal-hyprland advertises
 * AvailableCursorModes = 3 (HIDDEN | EMBEDDED) and rejects cursor_mode 4 with:
 * "Unavailable cursor mode 4".
 * We rewrite cursor_mode = 4 to cursor_mode = 2 (EMBEDDED) so the screen capture
 * is accepted by xdg-desktop-portal and streamed via PipeWire.
 */
GVariant* patch_screencast_select_sources(GVariant* parameters) {
    if (!parameters)
        return parameters;
    if (!g_variant_is_of_type(parameters, G_VARIANT_TYPE("(oa{sv})"))) {
        return parameters;
    }

    const gchar* session_handle = NULL;
    GVariantIter* iter = NULL;
    g_variant_get(parameters, "(&oa{sv})", &session_handle, &iter);

    GVariantBuilder builder;
    g_variant_builder_init(&builder, G_VARIANT_TYPE("a{sv}"));

    const gchar* key;
    GVariant* val;
    while (g_variant_iter_next(iter, "{&sv}", &key, &val)) {
        if (strcmp(key, "cursor_mode") == 0) {
            guint32 mode = g_variant_get_uint32(val);
            if (mode == 4 || (mode & 4)) {
                mode = 2; /* Change from METADATA (4) to EMBEDDED (2) */
            }
            g_variant_builder_add(&builder, "{sv}", key, g_variant_new_uint32(mode));
        } else {
            g_variant_builder_add(&builder, "{sv}", key, val);
        }
        g_variant_unref(val);
    }
    g_variant_iter_free(iter);

    return g_variant_new("(o@a{sv})", session_handle, g_variant_builder_end(&builder));
}

void g_dbus_connection_call(GDBusConnection* connection, const gchar* bus_name,
                            const gchar* object_path, const gchar* interface_name,
                            const gchar* method_name, GVariant* parameters,
                            const GVariantType* reply_type, GDBusCallFlags flags, gint timeout_msec,
                            GCancellable* cancellable, GAsyncReadyCallback callback,
                            gpointer user_data) {
    static void (*real_call)(GDBusConnection*, const gchar*, const gchar*, const gchar*,
                             const gchar*, GVariant*, const GVariantType*, GDBusCallFlags, gint,
                             GCancellable*, GAsyncReadyCallback, gpointer);

    if (!real_call) {
        real_call = dlsym(RTLD_NEXT, "g_dbus_connection_call");
    }

    if (interface_name && strcmp(interface_name, "org.freedesktop.portal.ScreenCast") == 0 &&
        method_name && strcmp(method_name, "SelectSources") == 0) {
        parameters = patch_screencast_select_sources(parameters);
    }

    real_call(connection, bus_name, object_path, interface_name, method_name, parameters,
              reply_type, flags, timeout_msec, cancellable, callback, user_data);
}

void g_dbus_connection_call_with_unix_fd_list(GDBusConnection* connection, const gchar* bus_name,
                                              const gchar* object_path, const gchar* interface_name,
                                              const gchar* method_name, GVariant* parameters,
                                              const GVariantType* reply_type, GDBusCallFlags flags,
                                              gint timeout_msec, GUnixFDList* fd_list,
                                              GCancellable* cancellable,
                                              GAsyncReadyCallback callback, gpointer user_data) {
    static void (*real_call_fd)(GDBusConnection*, const gchar*, const gchar*, const gchar*,
                                const gchar*, GVariant*, const GVariantType*, GDBusCallFlags, gint,
                                GUnixFDList*, GCancellable*, GAsyncReadyCallback, gpointer);

    if (!real_call_fd) {
        real_call_fd = dlsym(RTLD_NEXT, "g_dbus_connection_call_with_unix_fd_list");
    }

    if (interface_name && strcmp(interface_name, "org.freedesktop.portal.ScreenCast") == 0 &&
        method_name && strcmp(method_name, "SelectSources") == 0) {
        parameters = patch_screencast_select_sources(parameters);
    }

    real_call_fd(connection, bus_name, object_path, interface_name, method_name, parameters,
                 reply_type, flags, timeout_msec, fd_list, cancellable, callback, user_data);
}
