.PHONY: all portal shim test lint format check gate clean fetch-google-deps

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
	@uv tool run --from shellcheck-py shellcheck scripts/*.sh test/*.sh bin/hyprcrd-enroll
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

clean:
	@rm -rf portal/build build .coverage *.gcov test/unit/*.gcda test/unit/*.gcno test/unit/run_test_*
