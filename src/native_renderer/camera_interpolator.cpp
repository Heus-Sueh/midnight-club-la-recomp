#include "native_renderer/camera_interpolator.h"

namespace mcla {

CameraInterpolator& CameraInterpolator::Get() {
  static CameraInterpolator instance;
  return instance;
}

void CameraInterpolator::OnGuestCameraSample(const Vec3& pos, const Quat& rot, float fov) {
  const auto now = std::chrono::steady_clock::now();

  if (curr_pose_.valid) {
    auto delta = std::chrono::duration_cast<std::chrono::nanoseconds>(now - curr_pose_.timestamp);
    if (delta > std::chrono::milliseconds(5) && delta < std::chrono::milliseconds(100)) {
      // Exponential moving average for guest tick interval estimation
      guest_tick_interval_ = (guest_tick_interval_ * 3 + delta) / 4;
    }
    prev_pose_ = curr_pose_;
  } else {
    prev_pose_.position = pos;
    prev_pose_.rotation = rot;
    prev_pose_.fov = fov;
    prev_pose_.timestamp = now;
    prev_pose_.valid = true;
  }

  curr_pose_.position = pos;
  curr_pose_.rotation = rot;
  curr_pose_.fov = fov;
  curr_pose_.timestamp = now;
  curr_pose_.valid = true;
}

CameraPose CameraInterpolator::GetInterpolatedPose(std::chrono::steady_clock::time_point host_time) {
  if (!curr_pose_.valid) {
    return CameraPose{};
  }

  if (!prev_pose_.valid || guest_tick_interval_.count() <= 0) {
    return curr_pose_;
  }

  // Calculate normalized interpolation alpha
  double elapsed_ns = std::chrono::duration<double, std::nano>(host_time - curr_pose_.timestamp).count();
  double interval_ns = static_cast<double>(guest_tick_interval_.count());
  float alpha = static_cast<float>(elapsed_ns / interval_ns);

  // Clamp alpha between 0.0 (current guest sample) and 1.5 (extrapolation ceiling)
  alpha = std::clamp(alpha, 0.0f, 1.5f);

  CameraPose out;
  out.position = Vec3::Lerp(prev_pose_.position, curr_pose_.position, 1.0f + alpha);
  out.rotation = Quat::Slerp(prev_pose_.rotation, curr_pose_.rotation, 1.0f + alpha);
  out.fov = prev_pose_.fov + (curr_pose_.fov - prev_pose_.fov) * (1.0f + alpha);
  out.timestamp = host_time;
  out.valid = true;
  return out;
}

}  // namespace mcla
