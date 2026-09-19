#include "native_renderer/native_pass_batch.h"
#include "native_renderer/native_scene.h"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <limits>
#include <vector>

namespace {

#define CHECK(expression)                                                    \
  do {                                                                       \
    if (!(expression)) {                                                     \
      std::fprintf(stderr, "check failed at %s:%d: %s\n", __FILE__, __LINE__, \
                   #expression);                                             \
      std::abort();                                                          \
    }                                                                        \
  } while (false)

void AppendK8In32Word(std::vector<uint8_t>& output, uint32_t word) {
  output.push_back(static_cast<uint8_t>(word >> 24));
  output.push_back(static_cast<uint8_t>(word >> 16));
  output.push_back(static_cast<uint8_t>(word >> 8));
  output.push_back(static_cast<uint8_t>(word));
}

void AppendVertex(std::vector<uint8_t>& output, float x, float y, float z,
                  uint32_t color, float u, float v) {
  AppendK8In32Word(output, std::bit_cast<uint32_t>(x));
  AppendK8In32Word(output, std::bit_cast<uint32_t>(y));
  AppendK8In32Word(output, std::bit_cast<uint32_t>(z));
  AppendK8In32Word(output, 0);
  AppendK8In32Word(output, 0);
  AppendK8In32Word(output, 0);
  AppendK8In32Word(output, color);
  AppendK8In32Word(output, std::bit_cast<uint32_t>(u));
  AppendK8In32Word(output, std::bit_cast<uint32_t>(v));
}

void AppendQuad(mcla::NativeFrameScene& scene, float x_offset) {
  const uint32_t data_offset = static_cast<uint32_t>(scene.vertex_data.size());
  AppendVertex(scene.vertex_data, x_offset + 0.0f, 0.0f, 1.0f,
               0x11223344, 0.0f, 0.0f);
  AppendVertex(scene.vertex_data, x_offset + 1.0f, 0.0f, 1.0f,
               0x11223344, 1.0f, 0.0f);
  AppendVertex(scene.vertex_data, x_offset + 0.0f, 1.0f, 1.0f,
               0x11223344, 0.0f, 1.0f);
  AppendVertex(scene.vertex_data, x_offset + 1.0f, 1.0f, 1.0f,
               0x11223344, 1.0f, 1.0f);

  mcla::NativeDrawRecord& draw = scene.draws.emplace_back();
  draw.source_address =
      mcla::NativeSceneCapture::kDrawPrimitiveUpBuilderAddress;
  draw.primitive_type = 6;
  draw.vertex_count = 4;
  draw.vertex_stride_bytes = 36;
  draw.vertex_data_offset = data_offset;
  draw.vertex_data_size = 144;
}

void TestIndependentStripTopologyAndEndianDecode() {
  mcla::NativeFrameScene scene;
  scene.generation = 7;
  AppendQuad(scene, 0.0f);
  AppendQuad(scene, 10.0f);

  const mcla::NativeStripBatch batch =
      mcla::BuildDominantStripBatch(scene);
  CHECK(batch.scene_generation == 7);
  CHECK(batch.candidate_draws == 2);
  CHECK(batch.accepted_draws == 2);
  CHECK(batch.vertices.size() == 8);
  const std::array<uint32_t, 12> expected_indices = {
      0, 1, 2, 2, 1, 3, 4, 5, 6, 6, 5, 7,
  };
  CHECK(std::equal(batch.indices.begin(), batch.indices.end(),
                   expected_indices.begin(), expected_indices.end()));

  // The second strip must start at vertex 4. A naive concatenated strip would
  // incorrectly generate a triangle that references vertices 2, 3, and 4.
  for (size_t triangle = 0; triangle < batch.indices.size(); triangle += 3) {
    const bool crosses_draw_boundary =
        batch.indices[triangle] < 4 && batch.indices[triangle + 2] >= 4;
    CHECK(!crosses_draw_boundary);
  }

  CHECK(batch.vertices[0].position_z == 1.0f);
  CHECK(batch.vertices[4].position_x == 10.0f);
  CHECK(batch.vertices[1].texture_u == 1.0f);
  CHECK(batch.vertices[2].texture_v == 1.0f);
  CHECK(batch.vertices[0].color_rgba8 == 0x11443322);
}

void TestUnsupportedAndMissingDrawsAreRejected() {
  mcla::NativeFrameScene scene;
  AppendQuad(scene, 0.0f);
  scene.draws[0].primitive_type = 4;

  mcla::NativeDrawRecord& missing = scene.draws.emplace_back();
  missing.source_address =
      mcla::NativeSceneCapture::kDrawPrimitiveUpBuilderAddress;
  missing.primitive_type = 6;
  missing.vertex_count = 4;
  missing.vertex_stride_bytes = 36;
  missing.vertex_data_size = 144;

  const mcla::NativeStripBatch batch =
      mcla::BuildDominantStripBatch(scene);
  CHECK(batch.candidate_draws == 2);
  CHECK(batch.accepted_draws == 0);
  CHECK(batch.unsupported_draws == 1);
  CHECK(batch.missing_data_draws == 1);
}

void TestNonFiniteVerticesAreRejected() {
  mcla::NativeFrameScene scene;
  AppendQuad(scene, 0.0f);
  const uint32_t nan_word =
      std::bit_cast<uint32_t>(std::numeric_limits<float>::quiet_NaN());
  scene.vertex_data[0] = static_cast<uint8_t>(nan_word >> 24);
  scene.vertex_data[1] = static_cast<uint8_t>(nan_word >> 16);
  scene.vertex_data[2] = static_cast<uint8_t>(nan_word >> 8);
  scene.vertex_data[3] = static_cast<uint8_t>(nan_word);

  const mcla::NativeStripBatch batch =
      mcla::BuildDominantStripBatch(scene);
  CHECK(batch.accepted_draws == 0);
  CHECK(batch.invalid_vertex_draws == 1);
}

}  // namespace

int main() {
  TestIndependentStripTopologyAndEndianDecode();
  TestUnsupportedAndMissingDrawsAreRejected();
  TestNonFiniteVerticesAreRejected();
  return 0;
}

#undef CHECK
