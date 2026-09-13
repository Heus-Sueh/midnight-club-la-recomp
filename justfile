# Override tools with: just cmake=/path/to/cmake python=python3 build
set windows-shell := ["cmd.exe", "/c"]

cmake := "cmake"
python := "python"
preset := if os() == "windows" { "win-amd64-release" } else { "linux-amd64-release" }
exe := if os() == "windows" { "midnight_club_la.exe" } else { "midnight_club_la" }

# Show available tasks.
default:
    @just --list

# Validate cumulative physical-memory profile analysis without game data.
test-memory:
    "{{ python }}" -m unittest discover -s scripts -p test_analyze_physical_access.py

# Configure the selected preset (Vulkan enabled, D3D12 disabled).
configure:
    "{{ cmake }}" --preset {{ preset }}

# Build and refresh the GPU plugin even when the executable does not relink.
build:
    "{{ cmake }}" --build --preset {{ preset }} --parallel
    "{{ python }}" scripts/stage_gpu_plugin.py {{ preset }}

# Run the selected build with its existing executable-local configuration.
run:
    "out/build/{{ preset }}/{{ exe }}"

# Explicitly restore the checked-in runtime configuration beside the executable.
config-reset:
    "{{ cmake }}" -E copy_if_different midnight_club_la.toml "out/build/{{ preset }}/midnight_club_la.toml"

# Linux host capture; enter the same scene for comparable runs.
[linux]
profile output duration="60":
    "{{ python }}" scripts/profile_linux_runtime.py --duration {{ duration }} --output "{{ output }}" -- "out/build/{{ preset }}/{{ exe }}"

# Summarize host CPU/GPU captures after warm-up.
analyze-profile capture warmup="25":
    "{{ python }}" scripts/analyze_runtime_profile.py "{{ capture }}" --warmup-seconds {{ warmup }} --window-seconds 5

# Summarize guest presentation telemetry after warm-up.
analyze-present log warmup="25":
    "{{ python }}" scripts/analyze_present_log.py "{{ log }}" --warmup-seconds {{ warmup }}

# Summarize Vulkan queue diagnostics.
analyze-queue log:
    "{{ python }}" scripts/analyze_gpu_queue_log.py "{{ log }}"

# Compare write-watch protection and callback breadth by physical alias.
analyze-memory log:
    "{{ python }}" scripts/analyze_physical_access.py "{{ log }}"

# Extract only the executable from an owned disc image.
extract-xex iso:
    "{{ python }}" scripts/extract_xex.py "{{ iso }}"

# Extract the complete owned game image.
extract-game iso:
    "{{ python }}" scripts/extract_game.py "{{ iso }}"

# Reuse the local Ghidra analysis for one explicit guest address.
ghidra address:
    "{{ python }}" scripts/ghidra/analyze_xex.py --no-analysis --address {{ address }}
