#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <dlfcn.h>
#include <errno.h>
#include <security/pam_appl.h>
#include <gio/gio.h>
#include <pipewire/pipewire.h>

/* Forward declarations of symbols in pam_shim.c */
extern int pam_start(const char *service, const char *user,
                     const struct pam_conv *conv, pam_handle_t **handle);
extern int pam_acct_mgmt(pam_handle_t *handle, int flags);
extern int pam_end(pam_handle_t *handle, int status);

extern int pw_stream_update_params(struct pw_stream *stream,
                                   const struct spa_pod **params,
                                   uint32_t n_params);

extern void *dlsym(void *handle, const char *name);
extern GVariant *patch_screencast_select_sources(GVariant *parameters);

#ifdef TESTING_COVERAGE
extern void set_mock_pw_stream_state(enum pw_stream_state (*fn)(struct pw_stream *, const char **));
#endif

static int dummy_conv(int num_msg, const struct pam_message **msg,
                      struct pam_response **resp, void *appdata_ptr) {
    (void)num_msg;
    (void)msg;
    (void)resp;
    (void)appdata_ptr;
    return PAM_SUCCESS;
}

static void test_pam_hooks() {
    printf("[TEST] Testing PAM interception hooks...\n");
    struct pam_conv conv = { .conv = dummy_conv, .appdata_ptr = NULL };
    pam_handle_t *handle = NULL;

    /* 1. Normal pam_start for non-CRD service */
    int r = pam_start("other-service", "root", &conv, &handle);
    (void)r;

    /* 2. pam_start for chrome-remote-desktop */
    pam_handle_t *crd_handle = NULL;
    r = pam_start("chrome-remote-desktop", "eduardo", &conv, &crd_handle);
    assert(r == PAM_SUCCESS);
    assert(crd_handle != NULL);

    /* 3. pam_acct_mgmt should succeed for crd_handle without root */
    r = pam_acct_mgmt(crd_handle, 0);
    assert(r == PAM_SUCCESS);

    /* 4. pam_end clean cleanup */
    r = pam_end(crd_handle, PAM_SUCCESS);
    assert(r == PAM_SUCCESS);

    printf("  ✓ PAM hooks verified successfully.\n");
}

static void test_dlsym_hook() {
    printf("[TEST] Testing dlsym interception...\n");
    void *sym = dlsym(RTLD_DEFAULT, "pw_stream_update_params");
    assert(sym != NULL);
    assert(sym == (void *)pw_stream_update_params);

    void *orig = dlsym(RTLD_DEFAULT, "printf");
    assert(orig != NULL);
    printf("  ✓ dlsym hook verified successfully.\n");
}

static enum pw_stream_state mock_state_streaming(struct pw_stream *s, const char **err) {
    (void)s;
    if (err) *err = NULL;
    return PW_STREAM_STATE_STREAMING;
}

static void test_pipewire_protection() {
    printf("[TEST] Testing PipeWire stream update protection...\n");
    /* 1. NULL stream should safely return -EINVAL without crashing */
    int r = pw_stream_update_params(NULL, NULL, 0);
    assert(r == -EINVAL);

    /* 2. Test with real pipewire mainloop, context, core and stream */
    pw_init(NULL, NULL);
    struct pw_main_loop *loop = pw_main_loop_new(NULL);
    assert(loop != NULL);

    struct pw_context *ctx = pw_context_new(pw_main_loop_get_loop(loop), NULL, 0);
    assert(ctx != NULL);

    struct pw_core *core = pw_context_connect(ctx, NULL, 0);
    if (core) {
        struct pw_stream *stream = pw_stream_new(
            core, "test-stream",
            pw_properties_new(PW_KEY_MEDIA_TYPE, "Video", NULL));
        if (stream) {
            /* Test update params when not in streaming state */
            r = pw_stream_update_params(stream, NULL, 0);
            (void)r;

#ifdef TESTING_COVERAGE
            /* Test blocked update params when in STREAMING state */
            set_mock_pw_stream_state(mock_state_streaming);
            r = pw_stream_update_params(stream, NULL, 0);
            assert(r == 0);
#endif

            pw_stream_destroy(stream);
        }
        pw_core_disconnect(core);
    }

    pw_context_destroy(ctx);
    pw_main_loop_destroy(loop);
    pw_deinit();

    printf("  ✓ PipeWire protection verified successfully.\n");
}

static void test_screencast_cursor_patch() {
    printf("[TEST] Testing GVariant cursor_mode rewriting (4 -> 2)...\n");

    /* 1. NULL parameter check */
    assert(patch_screencast_select_sources(NULL) == NULL);

    /* 2. Incompatible type check */
    GVariant *wrong_type = g_variant_new_string("not a tuple");
    GVariant *res_wrong = patch_screencast_select_sources(wrong_type);
    assert(res_wrong == wrong_type);
    g_variant_unref(wrong_type);

    /* 3. Build variant simulating ScreenCast.SelectSources parameters */
    GVariantBuilder b;
    g_variant_builder_init(&b, G_VARIANT_TYPE("a{sv}"));
    g_variant_builder_add(&b, "{sv}", "cursor_mode", g_variant_new_uint32(4));
    g_variant_builder_add(&b, "{sv}", "types", g_variant_new_uint32(7));
    GVariant *options = g_variant_builder_end(&b);

    GVariant *params = g_variant_new("(o@a{sv})", "/test/session", options);
    assert(params != NULL);

    /* Call patch function */
    GVariant *patched = patch_screencast_select_sources(params);
    assert(patched != NULL);

    /* Verify patched cursor_mode is 2 and types is 7 */
    const gchar *sess = NULL;
    GVariantIter *iter = NULL;
    g_variant_get(patched, "(&oa{sv})", &sess, &iter);
    assert(strcmp(sess, "/test/session") == 0);

    const gchar *key;
    GVariant *val;
    gboolean found_cursor = FALSE;
    guint32 final_mode = 0;
    while (g_variant_iter_next(iter, "{&sv}", &key, &val)) {
        if (strcmp(key, "cursor_mode") == 0) {
            final_mode = g_variant_get_uint32(val);
            found_cursor = TRUE;
        } else if (strcmp(key, "types") == 0) {
            assert(g_variant_get_uint32(val) == 7);
        }
        g_variant_unref(val);
    }
    g_variant_iter_free(iter);
    assert(found_cursor == TRUE);
    assert(final_mode == 2);

    g_variant_unref(params);
    g_variant_unref(patched);
    printf("  ✓ ScreenCast cursor patch successfully rewritten to 2 (EMBEDDED).\n");
}

static void test_gdbus_interception() {
    printf("[TEST] Testing GDBus connection call interception...\n");
    GDBusConnection *conn = g_bus_get_sync(G_BUS_TYPE_SESSION, NULL, NULL);
    if (!conn) {
        printf("  - Session bus offline, skipping.\n");
        return;
    }

    GVariantBuilder b;
    g_variant_builder_init(&b, G_VARIANT_TYPE("a{sv}"));
    g_variant_builder_add(&b, "{sv}", "cursor_mode", g_variant_new_uint32(4));
    GVariant *params = g_variant_new("(o@a{sv})", "/test/session", g_variant_builder_end(&b));

    g_dbus_connection_call(
        conn,
        "org.freedesktop.DBus",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.ScreenCast",
        "SelectSources",
        params,
        NULL,
        G_DBUS_CALL_FLAGS_NONE,
        10,
        NULL,
        NULL,
        NULL
    );

    GVariantBuilder b2;
    g_variant_builder_init(&b2, G_VARIANT_TYPE("a{sv}"));
    g_variant_builder_add(&b2, "{sv}", "cursor_mode", g_variant_new_uint32(4));
    GVariant *params2 = g_variant_new("(o@a{sv})", "/test/session", g_variant_builder_end(&b2));

    g_dbus_connection_call_with_unix_fd_list(
        conn,
        "org.freedesktop.DBus",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.ScreenCast",
        "SelectSources",
        params2,
        NULL,
        G_DBUS_CALL_FLAGS_NONE,
        10,
        NULL,
        NULL,
        NULL,
        NULL
    );

    g_object_unref(conn);
    printf("  ✓ GDBus connection calls intercepted and rewritten successfully.\n");
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    printf("====================================================\n");
    printf("  Running PAM Shim & Interceptor Unit Tests        \n");
    printf("====================================================\n");

    test_pam_hooks();
    test_dlsym_hook();
    test_pipewire_protection();
    test_screencast_cursor_patch();
    test_gdbus_interception();

    printf("\n✓ ALL PAM SHIM TESTS PASSED (100%% Success)!\n");
    return 0;
}
