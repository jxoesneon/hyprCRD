.PHONY: all portal shim test lint format check gate clean fetch-google-deps install uninstall

CC ?= gcc
CXX ?= g++
CMAKE ?= cmake
NINJA ?= ninja
PYTHON ?= python3

PREFIX ?= /usr/local
DESTDIR ?=
BINDIR = $(PREFIX)/bin
LIBEXECDIR = $(PREFIX)/lib/hyprcrd

all: portal shim

portal:
	@mkdir -p portal/build bin
	$(CMAKE) -B portal/build -S portal -G Ninja -DCMAKE_BUILD_TYPE=Release
	$(CMAKE) --build portal/build

shim:
	@mkdir -p bin
	$(CC) -shared -fPIC -O2 -Wall -Wextra core/pam_shim.c -o bin/pam_shim.so \
		$$(pkg-config --cflags --libs gio-2.0 libpipewire-0.3) -ldl

test:
	@./test/run_all_tests.sh

lint:
	@echo "Checking Python formatting (black)..."
	@uv tool run black --check bin/hyprcrd core/daemon.py test/unit_python/ scripts/
	@echo "Checking Python style (flake8)..."
	@uv tool run flake8 bin/hyprcrd core/daemon.py test/unit_python/ scripts/ --count --max-line-length=140 --statistics
	@echo "Checking Python typing (mypy)..."
	@uv tool run mypy bin/hyprcrd core/daemon.py scripts/check_hygiene.py --ignore-missing-imports
	@echo "Checking C/C++ formatting (clang-format)..."
	@clang-format --dry-run --Werror core/pam_shim.c portal/src/*.cpp portal/src/*.h portal/test_virtual_input.cpp
	@echo "Checking shell scripts (shellcheck)..."
	@uv tool run --from shellcheck-py shellcheck scripts/*.sh test/*.sh bin/hyprcrd-enroll bin/hyprcrd-picker
	@echo "Checking security and AST safety (bandit)..."
	@uv tool run bandit -r bin/hyprcrd core/daemon.py -s B108,B110,B404,B603,B607
	@echo "Checking repository hygiene (binaries and secrets)..."
	@$(PYTHON) scripts/check_hygiene.py

format:
	@uv tool run black bin/hyprcrd core/daemon.py test/unit_python/ scripts/
	@if command -v clang-format >/dev/null 2>&1; then \
		clang-format -i core/pam_shim.c portal/src/*.cpp portal/src/*.h portal/*.cpp 2>/dev/null || true; \
	fi

gate: check

check: lint test
	@echo "Enforcing test coverage threshold (>= 95%)..."
	@uv tool run --with psutil coverage report --fail-under=95
	@echo "All quality and safety gates passed."

fetch-google-deps:
	@./scripts/fetch_google_binaries.sh

install:
	install -dm755 "$(DESTDIR)$(BINDIR)" "$(DESTDIR)$(LIBEXECDIR)"
	install -m755 bin/hyprcrd "$(DESTDIR)$(BINDIR)/hyprcrd"
	install -m755 bin/hyprcrd-portal "$(DESTDIR)$(LIBEXECDIR)/hyprcrd-portal"
	install -m755 bin/pam_shim.so "$(DESTDIR)$(LIBEXECDIR)/pam_shim.so"
	install -m755 bin/hyprcrd-picker "$(DESTDIR)$(LIBEXECDIR)/hyprcrd-picker"
	install -m755 core/daemon.py "$(DESTDIR)$(LIBEXECDIR)/daemon.py"
	# Official Google components (populated by scripts/fetch_google_binaries.sh)
	for f in chrome-remote-desktop-host crashpad-handler native-messaging-host start-host; do \
		if [ -f "bin/$$f" ]; then install -m755 "bin/$$f" "$(DESTDIR)$(LIBEXECDIR)/$$f"; fi; \
	done
	for f in libremoting_core.so icudtl.dat; do \
		if [ -f "bin/$$f" ]; then install -m644 "bin/$$f" "$(DESTDIR)$(LIBEXECDIR)/$$f"; fi; \
	done
	if [ -d bin/remoting_locales ]; then cp -r bin/remoting_locales "$(DESTDIR)$(LIBEXECDIR)/"; fi
	# systemd user unit and D-Bus activation service, with install paths substituted
	install -dm755 "$(DESTDIR)$(PREFIX)/lib/systemd/user" \
		"$(DESTDIR)$(PREFIX)/share/dbus-1/services" \
		"$(DESTDIR)$(PREFIX)/share/xdg-desktop-portal/portals" \
		"$(DESTDIR)$(PREFIX)/share/hyprcrd"
	sed -e 's|@BINDIR@|$(BINDIR)|g' -e 's|@LIBEXECDIR@|$(LIBEXECDIR)|g' \
		systemd/hyprcrd.service.in > "$(DESTDIR)$(PREFIX)/lib/systemd/user/hyprcrd.service"
	sed -e 's|@LIBEXECDIR@|$(LIBEXECDIR)|g' \
		config/org.freedesktop.impl.portal.desktop.hypr-remote.service.in \
		> "$(DESTDIR)$(PREFIX)/share/dbus-1/services/org.freedesktop.impl.portal.desktop.hypr-remote.service"
	install -m644 config/hypr-remote.portal \
		"$(DESTDIR)$(PREFIX)/share/xdg-desktop-portal/portals/hypr-remote.portal"
	# Example configuration (xdg-desktop-portal reads the user-level copies from
	# ~/.config/xdg-desktop-portal/ and ~/.config/hypr/; see README "Configuration")
	install -m644 config/hyprland-portals.conf \
		"$(DESTDIR)$(PREFIX)/share/hyprcrd/hyprland-portals.conf"
	install -m644 scripts/crd_version.env \
		"$(DESTDIR)$(PREFIX)/share/hyprcrd/crd_version.env"
	sed -e 's|@LIBEXECDIR@|$(LIBEXECDIR)|g' \
		config/xdph-screencopy.conf.in \
		> "$(DESTDIR)$(PREFIX)/share/hyprcrd/xdph-screencopy.conf.example"

uninstall:
	rm -f "$(DESTDIR)$(BINDIR)/hyprcrd"
	rm -f "$(DESTDIR)$(LIBEXECDIR)/hyprcrd-portal" \
		"$(DESTDIR)$(LIBEXECDIR)/pam_shim.so" \
		"$(DESTDIR)$(LIBEXECDIR)/hyprcrd-picker" \
		"$(DESTDIR)$(LIBEXECDIR)/daemon.py" \
		"$(DESTDIR)$(LIBEXECDIR)/chrome-remote-desktop-host" \
		"$(DESTDIR)$(LIBEXECDIR)/libremoting_core.so" \
		"$(DESTDIR)$(LIBEXECDIR)/icudtl.dat" \
		"$(DESTDIR)$(LIBEXECDIR)/crashpad-handler" \
		"$(DESTDIR)$(LIBEXECDIR)/native-messaging-host" \
		"$(DESTDIR)$(LIBEXECDIR)/start-host"
	rm -rf "$(DESTDIR)$(LIBEXECDIR)/remoting_locales"
	rm -f "$(DESTDIR)$(PREFIX)/lib/systemd/user/hyprcrd.service" \
		"$(DESTDIR)$(PREFIX)/share/dbus-1/services/org.freedesktop.impl.portal.desktop.hypr-remote.service" \
		"$(DESTDIR)$(PREFIX)/share/xdg-desktop-portal/portals/hypr-remote.portal" \
		"$(DESTDIR)$(PREFIX)/share/hyprcrd/hyprland-portals.conf" \
		"$(DESTDIR)$(PREFIX)/share/hyprcrd/crd_version.env" \
		"$(DESTDIR)$(PREFIX)/share/hyprcrd/xdph-screencopy.conf.example"

clean:
	@rm -rf portal/build build .coverage *.gcov test/unit/*.gcda test/unit/*.gcno test/unit/run_test_*
