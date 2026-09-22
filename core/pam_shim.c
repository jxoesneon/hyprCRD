#define _GNU_SOURCE
#include <dlfcn.h>
#include <string.h>
#include <stdio.h>
#include <security/pam_appl.h>
#include <gio/gio.h>

/* --- PAM Hooking --- */
static pam_handle_t *crd_handles[16];
static int n_handles;

int pam_start(const char *service, const char *user,
              const struct pam_conv *conv, pam_handle_t **handle) {
  static int (*real)(const char *, const char *,
                     const struct pam_conv *, pam_handle_t **);
  if (!real) real = dlsym(RTLD_NEXT, "pam_start");
  int r = real(service, user, conv, handle);
  if (r == PAM_SUCCESS && service &&
      strcmp(service, "chrome-remote-desktop") == 0 && n_handles < 16)
    crd_handles[n_handles++] = *handle;
  return r;
}

int pam_acct_mgmt(pam_handle_t *handle, int flags) {
  static int (*real)(pam_handle_t *, int);
  if (!real) real = dlsym(RTLD_NEXT, "pam_acct_mgmt");
  for (int i = 0; i < n_handles; i++)
    if (crd_handles[i] == handle) return PAM_SUCCESS;
  return real(handle, flags);
}

int pam_end(pam_handle_t *handle, int status) {
  static int (*real)(pam_handle_t *, int);
  if (!real) real = dlsym(RTLD_NEXT, "pam_end");
  for (int i = 0; i < n_handles; i++)
    if (crd_handles[i] == handle) {
      crd_handles[i] = crd_handles[--n_handles];
      break;
    }
  return real(handle, status);
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
static GVariant *patch_screencast_select_sources(GVariant *parameters) {
  if (!parameters) return parameters;
  if (!g_variant_is_of_type(parameters, G_VARIANT_TYPE("(oa{sv})"))) {
    return parameters;
  }

  const gchar *session_handle = NULL;
  GVariantIter *iter = NULL;
  g_variant_get(parameters, "(&oa{sv})", &session_handle, &iter);

  GVariantBuilder builder;
  g_variant_builder_init(&builder, G_VARIANT_TYPE("a{sv}"));

  const gchar *key;
  GVariant *val;
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

void g_dbus_connection_call(
    GDBusConnection *connection,
    const gchar *bus_name,
    const gchar *object_path,
    const gchar *interface_name,
    const gchar *method_name,
    GVariant *parameters,
    const GVariantType *reply_type,
    GDBusCallFlags flags,
    gint timeout_msec,
    GCancellable *cancellable,
    GAsyncReadyCallback callback,
    gpointer user_data
) {
  static void (*real_call)(
      GDBusConnection *, const gchar *, const gchar *, const gchar *,
      const gchar *, GVariant *, const GVariantType *, GDBusCallFlags,
      gint, GCancellable *, GAsyncReadyCallback, gpointer);

  if (!real_call) {
    real_call = dlsym(RTLD_NEXT, "g_dbus_connection_call");
  }

  if (interface_name && strcmp(interface_name, "org.freedesktop.portal.ScreenCast") == 0 &&
      method_name && strcmp(method_name, "SelectSources") == 0) {
    parameters = patch_screencast_select_sources(parameters);
  }

  real_call(connection, bus_name, object_path, interface_name,
            method_name, parameters, reply_type, flags,
            timeout_msec, cancellable, callback, user_data);
}

void g_dbus_connection_call_with_unix_fd_list(
    GDBusConnection *connection,
    const gchar *bus_name,
    const gchar *object_path,
    const gchar *interface_name,
    const gchar *method_name,
    GVariant *parameters,
    const GVariantType *reply_type,
    GDBusCallFlags flags,
    gint timeout_msec,
    GUnixFDList *fd_list,
    GCancellable *cancellable,
    GAsyncReadyCallback callback,
    gpointer user_data
) {
  static void (*real_call_fd)(
      GDBusConnection *, const gchar *, const gchar *, const gchar *,
      const gchar *, GVariant *, const GVariantType *, GDBusCallFlags,
      gint, GUnixFDList *, GCancellable *, GAsyncReadyCallback, gpointer);

  if (!real_call_fd) {
    real_call_fd = dlsym(RTLD_NEXT, "g_dbus_connection_call_with_unix_fd_list");
  }

  if (interface_name && strcmp(interface_name, "org.freedesktop.portal.ScreenCast") == 0 &&
      method_name && strcmp(method_name, "SelectSources") == 0) {
    parameters = patch_screencast_select_sources(parameters);
  }

  real_call_fd(connection, bus_name, object_path, interface_name,
               method_name, parameters, reply_type, flags,
               timeout_msec, fd_list, cancellable, callback, user_data);
}
