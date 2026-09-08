#pragma once

#include <chrono>
#include <cmath>
#include <cstdint>
#include <algorithm>

namespace mcla {

struct Vec3 {
  float x = 0.0f;
  float y = 0.0f;
  float z = 0.0f;

  Vec3() = default;
  Vec3(float x_, float y_, float z_) : x(x_), y(y_), z(z_) {}

  static Vec3 Lerp(const Vec3& a, const Vec3& b, float t) {
    return Vec3(
        a.x + (b.x - a.x) * t,
        a.y + (b.y - a.y) * t,
        a.z + (b.z - a.z) * t
    );
  }
};

struct Quat {
  float x = 0.0f;
  float y = 0.0f;
  float z = 0.0f;
  float w = 1.0f;

  Quat() = default;
  Quat(float x_, float y_, float z_, float w_) : x(x_), y(y_), z(z_), w(w_) {}

  static float Dot(const Quat& a, const Quat& b) {
    return a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w;
  }

  static Quat Slerp(Quat a, Quat b, float t) {
    float dot = Dot(a, b);
    if (dot < 0.0f) {
      b.x = -b.x;
      b.y = -b.y;
      b.z = -b.z;
      b.w = -b.w;
      dot = -dot;
    }

    if (dot > 0.9995f) {
      // Linear interpolation fallback for close angles
      Quat result(
          a.x + (b.x - a.x) * t,
          a.y + (b.y - a.y) * t,
          a.z + (b.z - a.z) * t,
          a.w + (b.w - a.w) * t
      );
      float len = std::sqrt(Dot(result, result));
      if (len > 0.0001f) {
        result.x /= len;
        result.y /= len;
        result.z /= len;
        result.w /= len;
      }
      return result;
    }

    float theta_0 = std::acos(std::clamp(dot, -1.0f, 1.0f));
    float theta = theta_0 * t;
    float sin_theta = std::sin(theta);
    float sin_theta_0 = std::sin(theta_0);

    float s0 = std::cos(theta) - dot * sin_theta / sin_theta_0;
    float s1 = sin_theta / sin_theta_0;

    return Quat(
        s0 * a.x + s1 * b.x,
        s0 * a.y + s1 * b.y,
        s0 * a.z + s1 * b.z,
        s0 * a.w + s1 * b.w
    );
  }
};

struct CameraPose {
  Vec3 position{};
  Quat rotation{};
  float fov = 60.0f;
  std::chrono::steady_clock::time_point timestamp{};
  bool valid = false;
};

class CameraInterpolator {
 public:
  static CameraInterpolator& Get();

  void OnGuestCameraSample(const Vec3& pos, const Quat& rot, float fov);
  CameraPose GetInterpolatedPose(std::chrono::steady_clock::time_point host_time);
  bool HasValidHistory() const { return curr_pose_.valid; }

 private:
  CameraPose prev_pose_{};
  CameraPose curr_pose_{};
  std::chrono::nanoseconds guest_tick_interval_{33333333}; // ~30 Hz default
};

}  // namespace mcla
