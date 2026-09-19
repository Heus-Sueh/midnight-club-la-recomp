#pragma once

#include <cstdint>
#include <memory>
#include <string>

#include <rex/cvar.h>
#include <rex/runtime.h>
#include <rex/ui/window.h>

namespace mcla {

// CVars for tuning native presentation.
REXCVAR_DECLARE(bool, mcla_use_native_renderer);
REXCVAR_DECLARE(std::string, mcla_resolution);
REXCVAR_DECLARE(double, mcla_target_fps);
REXCVAR_DECLARE(bool, mcla_smooth_motion);
REXCVAR_DECLARE(double, mcla_aspect_ratio);
REXCVAR_DECLARE(int32_t, mcla_resolution_scale);
REXCVAR_DECLARE(bool, mcla_dump_shaders);
REXCVAR_DECLARE(bool, mcla_use_fsi);
REXCVAR_DECLARE(bool, mcla_interpolate_camera);
REXCVAR_DECLARE(bool, mcla_native_scene_capture);
REXCVAR_DECLARE(int32_t, mcla_capture_present);
REXCVAR_DECLARE(std::string, mcla_capture_path);

class NativeRenderer {
 public:
  static NativeRenderer& Get();

  void OnPreSetup(rex::RuntimeConfig& config);
  void Initialize(rex::Runtime* runtime, rex::ui::Window* window);
  void OnPostLoadXex();
  void OnGuestPresent();
  void OnWindowResize(uint32_t width, uint32_t height);
  void Shutdown();

 private:
  NativeRenderer() = default;
  ~NativeRenderer() = default;

  void SampleGuestCamera();
  void CaptureDiagnosticFrame();

  rex::Runtime* runtime_ = nullptr;
  rex::ui::Window* window_ = nullptr;
  bool initialized_ = false;
  uint64_t guest_frame_count_ = 0;
  uint64_t total_guest_frame_count_ = 0;
  bool diagnostic_frame_captured_ = false;
  std::chrono::steady_clock::time_point next_present_time_{};
  std::chrono::steady_clock::time_point last_report_time_{};
};

}  // namespace mcla
