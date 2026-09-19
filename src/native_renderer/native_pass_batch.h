#pragma once

#include <cstdint>
#include <vector>

namespace mcla {

struct NativeFrameScene;

// Host-native representation of the proven vertex layout consumed by
// VS 0x88F617431F7D9C9B. The guest input is 9 dwords (36 bytes): position at
// words 0..2, packed color at word 6, and texture coordinates at words 7..8.
struct NativeStripVertex {
  float position_x = 0.0f;
  float position_y = 0.0f;
  float position_z = 0.0f;
  uint32_t color_rgba8 = 0;
  float texture_u = 0.0f;
  float texture_v = 0.0f;
};

// CPU-side, compare-only batch for the dominant four-vertex strip pass. It is
// not submitted to Vulkan yet and never suppresses the authoritative Xenos
// draw. source_draw_indices preserves the original scene ordering and makes
// later image-comparison failures traceable to a captured record.
struct NativeStripBatch {
  uint64_t scene_generation = 0;
  uint64_t candidate_draws = 0;
  uint64_t accepted_draws = 0;
  uint64_t unsupported_draws = 0;
  uint64_t missing_data_draws = 0;
  uint64_t invalid_vertex_draws = 0;
  std::vector<uint32_t> source_draw_indices;
  std::vector<NativeStripVertex> vertices;
  std::vector<uint32_t> indices;
};

NativeStripBatch BuildDominantStripBatch(const NativeFrameScene& scene);

}  // namespace mcla
