#include "native_renderer/native_renderer.h"
#include "native_renderer/camera_interpolator.h"
#include "native_renderer/native_scene.h"
#ifdef MCLA_ENABLE_HOTSPOT_PROBE
#include "hotspot_probe.h"
#endif

#include <chrono>
#include <algorithm>
#include <cmath>
#include <fstream>
#include <thread>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/memory/utils.h>
#include <rex/ppc/context.h>
#include <rex/ui/presenter.h>

// Mid-assembly hook target at RAGE grcDevice::Present (0x8241A0E4)
void mcla_native_present_hook() {
  mcla::NativeRenderer::Get().OnGuestPresent();
}

// Observation-only hook at the entry of the proven DRAW_INDX_2 packet builder
// (0x82427898). It preserves r3/r4/r5 and lets the original guest function emit
// the packet normally, so rexgpu-xenos remains the authoritative renderer.
void mcla_native_draw_indx2_hook(PPCRegister& r3, PPCRegister& r4, PPCRegister& r5) {
  if (mcla::FLAGS_mcla_native_scene_capture_storage_()) {
    mcla::NativeSceneCapture::Get().ObserveBuilderCall(0x82427898);
    mcla::NativeSceneCapture::Get().ObserveDrawIndx2(r3.u32, r4.u32, r5.u32);
  }
}

#define MCLA_DEFINE_DRAW_BUILDER_PROBE(name, address)              \
  void name() {                                                    \
    if (mcla::FLAGS_mcla_native_scene_capture_storage_()) {        \
      mcla::NativeSceneCapture::Get().ObserveBuilderCall(address); \
    }                                                              \
  }

MCLA_DEFINE_DRAW_BUILDER_PROBE(mcla_draw_builder_82413068_hook, 0x82413068)
MCLA_DEFINE_DRAW_BUILDER_PROBE(mcla_draw_builder_82417538_hook, 0x82417538)
MCLA_DEFINE_DRAW_BUILDER_PROBE(mcla_draw_builder_82418350_hook, 0x82418350)
MCLA_DEFINE_DRAW_BUILDER_PROBE(mcla_draw_builder_82422488_hook, 0x82422488)
MCLA_DEFINE_DRAW_BUILDER_PROBE(mcla_draw_builder_824225e0_hook, 0x824225E0)
MCLA_DEFINE_DRAW_BUILDER_PROBE(mcla_draw_builder_8242de08_hook, 0x8242DE08)

#undef MCLA_DEFINE_DRAW_BUILDER_PROBE

void mcla_draw_builder_8241cd88_hook(PPCRegister& r3, PPCRegister& r4,
                                     PPCRegister& r5, PPCRegister& r6) {
  if (!mcla::FLAGS_mcla_native_scene_capture_storage_()) {
    return;
  }
  mcla::NativeSceneCapture::Get().ObserveBuilderCall(0x8241CD88);
  mcla::NativeSceneCapture::Get().ObserveDrawCall(
      0x8241CD88, 0xC0012201, r3.u32, r4.u32, r5.u32, r6.u32, 0,
      ((r5.u32 & 0xFFFFu) << 16) | (r4.u32 & 0x3Fu) | 0x80u);
}

// Observation-only hook immediately after 0x8241D200 has moved the returned
// guest vertex allocation into r3. The caller fills this allocation after the
// function returns, so the bytes are deliberately copied later at Present.
void mcla_draw_builder_8241cd88_return_hook(PPCRegister& r3) {
  if (mcla::FLAGS_mcla_native_scene_capture_storage_()) {
    mcla::NativeSceneCapture::Get().ObserveDrawPrimitiveUpReturn(r3.u32);
  }
}

void mcla_draw_builder_8241d230_hook(PPCRegister& r3, PPCRegister& r4,
                                     PPCRegister& r5, PPCRegister& r6) {
  if (!mcla::FLAGS_mcla_native_scene_capture_storage_()) {
    return;
  }
  mcla::NativeSceneCapture::Get().ObserveBuilderCall(0x8241D230);
  mcla::NativeSceneCapture::Get().ObserveDrawCall(
      0x8241D230, 0xC0012201, r3.u32, r4.u32, r5.u32, r6.u32, 0,
      ((r6.u32 & 0xFFFFu) << 16) | (r4.u32 & 0x3Fu) | 0x80u);
}

void mcla_draw_builder_8241d620_hook(PPCRegister& r3, PPCRegister& r4,
                                     PPCRegister& r5, PPCRegister& r6,
                                     PPCRegister& r7) {
  if (!mcla::FLAGS_mcla_native_scene_capture_storage_()) {
    return;
  }
  mcla::NativeSceneCapture::Get().ObserveBuilderCall(0x8241D620);
  mcla::NativeSceneCapture::Get().ObserveDrawCall(
      0x8241D620, 0xC0032201, r3.u32, r4.u32, r5.u32, r6.u32, r7.u32,
      0);
}

namespace mcla {

REXCVAR_DEFINE_BOOL(mcla_use_native_renderer, true, "Graphics",
                    "Enable native renderer and presentation pipeline")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_STRING(mcla_resolution, "1080p", "Graphics",
                      "Display and render resolution preset (720p, 1080p, 1440p, 4k)")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_DOUBLE(mcla_target_fps, 30.0, "Graphics",
                      "Target frame rate for host presentation pacing (0 = unthrottled)")
    .range(0.0, 360.0)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

REXCVAR_DEFINE_BOOL(mcla_smooth_motion, true, "Graphics",
                    "Microsecond-accurate frame pacing to eliminate display judder")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

REXCVAR_DEFINE_BOOL(mcla_interpolate_camera, false, "Graphics",
                    "Experimental guest camera sampling prototype (does not alter rendering yet)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

REXCVAR_DEFINE_BOOL(mcla_native_scene_capture, false, "Graphics/Native Renderer",
                    "Capture proven RAGE draw submissions into immutable frame scenes")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

REXCVAR_DEFINE_INT32(mcla_capture_present, 0, "Graphics/Diagnostics",
                     "Capture the first guest output at or after this absolute "
                     "Present number (0 = disabled)")
    .range(0, 1000000)
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_STRING(mcla_capture_path, "mcla-frame.ppm", "Graphics/Diagnostics",
                      "PPM output path used by mcla_capture_present")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_DOUBLE(mcla_aspect_ratio, 0.0, "Graphics",
                      "Target aspect ratio (0.0 = auto 16:9, 2.333 = 21:9 ultrawide, 3.555 = 32:9)")
    .range(0.0, 4.0)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

REXCVAR_DEFINE_INT32(mcla_resolution_scale, 1, "Graphics",
                     "Internal render resolution multiplier (1 = 720p native, 2 = 1440p, 3 = 4K)")
    .range(1, 4)
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_BOOL(mcla_use_fsi, true, "Graphics",
                    "Use Fragment Shader Interlock (ROV) to eliminate eDRAM tile copy passes")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_BOOL(mcla_dump_shaders, false, "Graphics",
                    "Dump extracted RAGE microcode shaders to shaders_dump/ for AOT pipeline")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

NativeRenderer& NativeRenderer::Get() {
  static NativeRenderer instance;
  return instance;
}

void NativeRenderer::OnPreSetup(rex::RuntimeConfig& config) {
  // Enforce Vulkan with Xenos emulation plugin
  config.gpu_plugin = "xenos";

  if (!REXCVAR_GET(mcla_use_native_renderer)) {
    return;
  }

  // Tier 2 Native Renderer Pipeline optimizations:
  // 1. EDRAM emulation path: Fragment Shader Interlock (FSI) eliminates eDRAM tile copies
  if (REXCVAR_GET(mcla_use_fsi)) {
    rex::cvar::SetFlagByName("render_target_path_vulkan", "fsi");
  } else {
    rex::cvar::SetFlagByName("render_target_path_vulkan", "fbo");
  }

  // 2. Shader and pipeline compilation policy is owned by the TOML / CLI.
  // Do not overwrite it at runtime: command-line A/B testing and per-machine
  // tuning must remain possible.
  // 3. Readback and guest-memory coherency policies are owned by TOML / CLI.
  // Keeping them out of runtime overrides makes safe compatibility fallbacks
  // possible without rebuilding the recomp.

  // 4. Shader microcode extraction pipeline (active only if mcla_dump_shaders is enabled)
  if (REXCVAR_GET(mcla_dump_shaders)) {
    rex::cvar::SetFlagByName("dump_shaders", "shaders_dump");
  }

  // 5. Configure 1080p or custom requested window resolution while keeping guest eDRAM fast
  const std::string& res = REXCVAR_GET(mcla_resolution);
  if (res == "1080p" || res == "1920x1080") {
    rex::cvar::SetFlagByName("window_width", "1920");
    rex::cvar::SetFlagByName("window_height", "1080");
    rex::cvar::SetFlagByName("video_mode_width", "1280");
    rex::cvar::SetFlagByName("video_mode_height", "720");
    rex::cvar::SetFlagByName("present_effect", "bilinear");
  } else if (res == "1440p" || res == "2560x1440") {
    rex::cvar::SetFlagByName("window_width", "2560");
    rex::cvar::SetFlagByName("window_height", "1440");
    rex::cvar::SetFlagByName("video_mode_width", "1280");
    rex::cvar::SetFlagByName("video_mode_height", "720");
    rex::cvar::SetFlagByName("present_effect", "bilinear");
  } else if (res == "4k" || res == "2160p" || res == "3840x2160") {
    rex::cvar::SetFlagByName("window_width", "3840");
    rex::cvar::SetFlagByName("window_height", "2160");
    rex::cvar::SetFlagByName("video_mode_width", "1280");
    rex::cvar::SetFlagByName("video_mode_height", "720");
    rex::cvar::SetFlagByName("present_effect", "bilinear");
  }

  // 6. Set render resolution scale
  int32_t scale = std::max(1, REXCVAR_GET(mcla_resolution_scale));
  rex::cvar::SetFlagByName("draw_resolution_scale_x", std::to_string(scale));
  rex::cvar::SetFlagByName("draw_resolution_scale_y", std::to_string(scale));

  REXLOG_INFO("[NativeRenderer] Native renderer ENABLED: resolution={}, scale={}x, target_fps={}, fsi={}",
              res, scale, REXCVAR_GET(mcla_target_fps), REXCVAR_GET(mcla_use_fsi));
}

void NativeRenderer::Initialize(rex::Runtime* runtime, rex::ui::Window* window) {
  if (!REXCVAR_GET(mcla_use_native_renderer)) {
    return;
  }
  runtime_ = runtime;
  window_ = window;
  initialized_ = true;

  if (REXCVAR_GET(mcla_dump_shaders)) {
    rex::cvar::SetFlagByName("dump_shaders", "shaders_dump");
    REXLOG_INFO("[NativeRenderer] Shader microcode extraction pipeline active -> shaders_dump/");
  }

  REXLOG_INFO("[NativeRenderer] Native renderer initialized on Vulkan (mode: {}, window: {})",
              REXCVAR_GET(mcla_resolution), window ? "windowed" : "headless");
}

void NativeRenderer::OnPostLoadXex() {
  if (!runtime_ || !runtime_->memory()) {
    return;
  }

  // Guest patches are emitted by codegen. Avoid modifying executable bytes in
  // the loaded image: recompilation runs the generated host code instead.
}

void NativeRenderer::SampleGuestCamera() {
  if (!runtime_ || !runtime_->memory()) {
    return;
  }

  auto* mem = runtime_->memory();

  // 1. Read active camera pointer at 0x8286D048
  auto* cam_ptr_addr = mem->TranslateVirtual<const uint32_t*>(0x8286D048);
  if (!cam_ptr_addr) {
    return;
  }
  uint32_t cam_ea = rex::memory::load_and_swap<uint32_t>(cam_ptr_addr);
  if (cam_ea == 0 || cam_ea < 0x80000000) {
    return;
  }

  auto* cam_base = mem->TranslateVirtual<const uint8_t*>(cam_ea);
  if (!cam_base) {
    return;
  }

  // In RAGE camBase / camDirector:
  // Position vector is stored at offset 12 as 3x IEEE-754 32-bit floats.
  // Rotation quaternion is stored at offset 64.
  float x = rex::memory::load_and_swap<float>(cam_base + 12);
  float y = rex::memory::load_and_swap<float>(cam_base + 16);
  float z = rex::memory::load_and_swap<float>(cam_base + 20);

  if (std::isfinite(x) && std::isfinite(y) && std::isfinite(z)) {
    float qx = rex::memory::load_and_swap<float>(cam_base + 64);
    float qy = rex::memory::load_and_swap<float>(cam_base + 68);
    float qz = rex::memory::load_and_swap<float>(cam_base + 72);
    float qw = rex::memory::load_and_swap<float>(cam_base + 76);

    Quat rot(0.0f, 0.0f, 0.0f, 1.0f);
    if (std::isfinite(qx) && std::isfinite(qy) && std::isfinite(qz) && std::isfinite(qw)) {
      rot = Quat(qx, qy, qz, qw);
    }

    CameraInterpolator::Get().OnGuestCameraSample(Vec3(x, y, z), rot, 60.0f);
  }
}

void NativeRenderer::OnGuestPresent() {
  if (!initialized_) {
    return;
  }
  ++guest_frame_count_;
  ++total_guest_frame_count_;

  if (REXCVAR_GET(mcla_native_scene_capture)) {
    NativeSceneCapture::Get().PublishFrame(
        total_guest_frame_count_, runtime_ ? runtime_->memory() : nullptr);
  }

  const int32_t capture_present = REXCVAR_GET(mcla_capture_present);
  if (!diagnostic_frame_captured_ && capture_present > 0 &&
      total_guest_frame_count_ >= static_cast<uint64_t>(capture_present)) {
    CaptureDiagnosticFrame();
  }

  // Sample guest camera for 1 kHz motion interpolation
  if (REXCVAR_GET(mcla_interpolate_camera)) {
    SampleGuestCamera();
  }

  // Periodic performance report
  const auto now = std::chrono::steady_clock::now();
  if (last_report_time_.time_since_epoch().count() == 0) {
    last_report_time_ = now;
  } else {
    auto elapsed = std::chrono::duration<double>(now - last_report_time_).count();
    if (elapsed >= 5.0) {
      double guest_fps = static_cast<double>(guest_frame_count_) / elapsed;
      const auto native_scene = NativeSceneCapture::Get().AcquireLatest();
      REXLOG_INFO(
          "[NativeRenderer] Presentation stats: guest_fps={:.1f}, frames={}, "
          "camera_sampling={}, native_scene_draws={}, dropped_draws={}, "
          "vertex_buffers={}/{}, vertex_bytes={}, missing_vertex_buffers={}, "
          "dropped_vertex_buffers={}, unmatched_vertex_returns={}",
          guest_fps, guest_frame_count_, CameraInterpolator::Get().HasValidHistory() ? "active" : "standby",
          native_scene ? native_scene->draws.size() : 0,
          native_scene ? native_scene->dropped_draws : 0,
          native_scene ? native_scene->captured_vertex_buffers : 0,
          native_scene ? native_scene->expected_vertex_buffers : 0,
          native_scene ? native_scene->vertex_data.size() : 0,
          native_scene ? native_scene->missing_vertex_buffers : 0,
          native_scene ? native_scene->dropped_vertex_buffers : 0,
          native_scene ? native_scene->unmatched_vertex_returns : 0);
      for (const NativeBuilderActivity& activity : NativeSceneCapture::Get().DrainBuilderActivity()) {
        REXLOG_INFO("[NativeRenderer] PM4 builder 0x{:08X}: calls={}", activity.source_address, activity.calls);
      }
#ifdef MCLA_ENABLE_HOTSPOT_PROBE
      ReportHotspotProbe(elapsed);
#endif
      guest_frame_count_ = 0;
      last_report_time_ = now;
    }
  }

  double target_fps = REXCVAR_GET(mcla_target_fps);
  if (target_fps <= 0.0 || !REXCVAR_GET(mcla_smooth_motion)) {
    return;
  }

  // Precise pacing: absolute target scheduling so sleep jitter never accumulates
  const auto interval = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
      std::chrono::duration<double>(1.0 / target_fps));

  if (next_present_time_.time_since_epoch().count() == 0 || now > next_present_time_ + interval) {
    next_present_time_ = now + interval;
    return;
  }

  // Sleep for most of the interval and reserve only the final 0.5 ms for a
  // hybrid yield/spin phase. This avoids burning roughly 2 ms of a CPU core on
  // every frame while retaining accurate deadlines on Windows and Linux.
  const auto sleep_deadline = next_present_time_ - std::chrono::microseconds(500);
  if (std::chrono::steady_clock::now() < sleep_deadline) {
    std::this_thread::sleep_until(sleep_deadline);
  }
  while (true) {
    const auto remaining = next_present_time_ - std::chrono::steady_clock::now();
    if (remaining <= std::chrono::steady_clock::duration::zero()) {
      break;
    }
    if (remaining > std::chrono::microseconds(75)) {
      std::this_thread::yield();
    } else {
      #if defined(__x86_64__) || defined(_M_X64)
      __builtin_ia32_pause();
      #endif
    }
  }
  next_present_time_ += interval;
}

void NativeRenderer::CaptureDiagnosticFrame() {
  rex::ui::Presenter* presenter =
      runtime_ && runtime_->graphics_system() ? runtime_->graphics_system()->presenter() : nullptr;
  if (!presenter) {
    return;
  }

  rex::ui::RawImage image;
  if (!presenter->CaptureGuestOutput(image) || image.width == 0 ||
      image.height == 0 || image.stride < size_t(image.width) * 4) {
    return;
  }

  const std::string& path = REXCVAR_GET(mcla_capture_path);
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  if (!output) {
    REXLOG_ERROR("[NativeRenderer] Failed to open diagnostic capture: {}", path);
    diagnostic_frame_captured_ = true;
    return;
  }

  output << "P6\n" << image.width << ' ' << image.height << "\n255\n";
  for (uint32_t y = 0; y < image.height; ++y) {
    const uint8_t* row = image.data.data() + size_t(y) * image.stride;
    for (uint32_t x = 0; x < image.width; ++x) {
      output.write(reinterpret_cast<const char*>(row + size_t(x) * 4), 3);
    }
  }

  diagnostic_frame_captured_ = true;
  if (output) {
    REXLOG_INFO("[NativeRenderer] Captured guest Present {} to {} ({}x{})",
                total_guest_frame_count_, path, image.width, image.height);
  } else {
    REXLOG_ERROR("[NativeRenderer] Failed while writing diagnostic capture: {}", path);
  }
}

void NativeRenderer::OnWindowResize(uint32_t width, uint32_t height) {
  if (width == 0 || height == 0) {
    return;
  }

  double custom_aspect = REXCVAR_GET(mcla_aspect_ratio);
  if (custom_aspect > 0.0) {
    rex::cvar::SetFlagByName("present_letterbox", "false");
  } else {
    rex::cvar::SetFlagByName("present_letterbox", "true");
  }
}

void NativeRenderer::Shutdown() {
  initialized_ = false;
  runtime_ = nullptr;
  window_ = nullptr;
  guest_frame_count_ = 0;
  total_guest_frame_count_ = 0;
  diagnostic_frame_captured_ = false;
  NativeSceneCapture::Get().Reset();
}

}  // namespace mcla
