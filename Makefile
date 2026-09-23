.PHONY: all portal shim test lint format clean fetch-google-deps

CC ?= gcc
CXX ?= g++
CMAKE ?= cmake
NINJA ?= ninja
PYTHON ?= python3

all: portal shim

portal:
	@mkdir -p portal/build bin
	$(CMAKE) -B portal/build -S portal -G Ninja -DCMAKE_BUILD_TYPE=Release
	$(CMAKE) --build portal/build

shim:
	@mkdir -p bin
	$(CC) -shared -fPIC -O2 -Wall -Wextra core/pam_shim.c -o bin/pam_shim.so \
		$$(pkg-config --cflags --libs gio-2.0 libpipewire-0.3 pam) -ldl

test:
	@./test/run_all_tests.sh

lint:
	@uv tool run black --check bin/hyprcrd core/daemon.py test/unit_python/
	@uv tool run flake8 bin/hyprcrd core/daemon.py test/unit_python/ --count --max-line-length=140 --statistics

format:
	@uv tool run black bin/hyprcrd core/daemon.py test/unit_python/
	@if command -v clang-format >/dev/null 2>&1; then \
		clang-format -i core/pam_shim.c portal/src/*.cpp portal/src/*.h portal/*.cpp 2>/dev/null || true; \
	fi

fetch-google-deps:
	@./scripts/fetch_google_binaries.sh

clean:
	@rm -rf portal/build build .coverage *.gcov test/unit/*.gcda test/unit/*.gcno test/unit/run_test_*
